# apps/parceiros/services.py
"""
PartnerService — lógica de negócio central do Portal de Parceiros.

Regras críticas:
  - Quota protegida com select_for_update() dentro de transaction.atomic().
  - Parceiro NÃO cria planos de cliente — vincula os existentes em apps.licenca.
  - Tokens armazenados apenas como hash SHA-256.
  - Toda operação sensível regista PartnerAudit.
"""
import logging
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.parceiros.models import (
    Partner, PartnerLicense, PartnerLicensePlan, PartnerToken,
    PartnerClient, PartnerQuotaUsage, PartnerLicenseRequest,
    PartnerBilling, PartnerNotification, PartnerAudit,
)

Usuario = get_user_model()
logger  = logging.getLogger('parceiros.service')


class PartnerServiceError(Exception):
    """Erro de negócio do Portal de Parceiros."""


def _auditar(partner, acao, executado_por, objeto_tipo='', objeto_id='',
             anterior=None, novo=None, ip=None, origem='service'):
    """Regista entrada de auditoria. Não levanta excepção se falhar."""
    try:
        PartnerAudit.objects.create(
            partner=partner, acao=acao,
            objeto_tipo=objeto_tipo, objeto_id=str(objeto_id),
            valor_anterior=anterior, valor_novo=novo,
            executado_por=executado_por,
            ip_address=ip, origem=origem,
        )
    except Exception as exc:
        logger.warning("Falha ao registar auditoria de parceiro: %s", exc)


class PartnerService:

    # ─────────────────────────────────────────────────────────────────
    # Gestão do parceiro
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def criar_partner(dados: dict, criado_por, ip: Optional[str] = None) -> Partner:
        """
        Cria um novo parceiro e a sua conta de utilizador.
        dados: {'nome','email','nif','tipo','telefone','endereco','username','password'}
        """
        username = dados.get('username', '').strip()
        email    = dados.get('email', '').strip()
        password = dados.get('password', '').strip()

        if not username or not email or not password:
            raise PartnerServiceError("username, email e password são obrigatórios.")

        if Usuario.objects.filter(username=username).exists():
            raise PartnerServiceError(f"O username '{username}' já está em uso.")

        user = Usuario.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_staff=False,
            is_active=True,
        )

        partner = Partner.objects.create(
            usuario=user,
            nome=dados.get('nome', username),
            tipo=dados.get('tipo', 'empresa'),
            nif=dados.get('nif', ''),
            telefone=dados.get('telefone', ''),
            email=email,
            endereco=dados.get('endereco', ''),
            registado_por=criado_por,
            observacoes=dados.get('observacoes', ''),
        )

        _auditar(partner, 'PARTNER_CREATED', criado_por, 'Partner', partner.pk,
                 novo={'username': username, 'email': email}, ip=ip)
        logger.info("Parceiro '%s' criado por %s.", partner.nome, criado_por)
        return partner

    # ─────────────────────────────────────────────────────────────────
    # Gestão de licença
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def criar_licenca(partner: Partner, plano: PartnerLicensePlan,
                      metodo_pagamento: str, valor_pago: Decimal,
                      registada_por, ip: Optional[str] = None) -> PartnerLicense:
        """
        Cria uma PartnerLicense em estado 'pendente'.
        Gera automaticamente um PartnerToken de activação.
        Devolve (licenca, token_valor_claro).
        """
        licenca = PartnerLicense.objects.create(
            partner=partner,
            plano=plano,
            status='pendente',
            metodo_pagamento=metodo_pagamento,
            valor_pago=valor_pago,
            registada_por=registada_por,
        )
        token_obj, token_valor = PartnerToken.gerar(
            partner=partner,
            tipo='activacao',
            plano_destino=plano,
            criado_por=registada_por,
            validade_horas=72,
        )
        licenca.token_activacao = token_obj
        licenca.save(update_fields=['token_activacao'])

        _auditar(partner, 'LICENSE_CREATED', registada_por, 'PartnerLicense', licenca.pk,
                 novo={'plano': plano.nome, 'metodo': metodo_pagamento}, ip=ip)
        # Retornamos o token para que o funcionário SOTARQ o entregue ao parceiro
        return licenca, token_valor

    @staticmethod
    @transaction.atomic
    def ativar_licenca(partner: Partner, token_valor: str,
                       ip: Optional[str] = None) -> PartnerLicense:
        """
        Valida o token e activa a licença do parceiro.
        O token só pode ser usado uma vez e deve pertencer ao parceiro.
        """
        token = PartnerToken.validar(partner, token_valor, tipo='activacao')
        licenca = token.licenca_activada

        if licenca is None:
            raise PartnerServiceError(
                "Token válido mas sem licença associada. "
                "Contacte a SOTARQ."
            )
        if licenca.status != 'pendente':
            raise PartnerServiceError(
                f"Esta licença não pode ser activada (status: '{licenca.status}')."
            )

        hoje = timezone.now().date()
        plano = licenca.plano

        # Calcular data de expiração com base na duração do plano
        from dateutil.relativedelta import relativedelta
        if plano.unidade_duracao == 'dias':
            delta = timezone.timedelta(days=plano.duracao)
            expiracao = hoje + delta
        elif plano.unidade_duracao == 'meses':
            expiracao = hoje + relativedelta(months=plano.duracao)
        else:  # anos
            expiracao = hoje + relativedelta(years=plano.duracao)

        licenca.status        = 'activa'
        licenca.data_inicio   = hoje
        licenca.data_expiracao = expiracao
        licenca.save(update_fields=['status', 'data_inicio', 'data_expiracao'])

        token.marcar_utilizado()

        _auditar(partner, 'LICENSE_ACTIVATED', partner.usuario, 'PartnerLicense', licenca.pk,
                 novo={'expiracao': str(expiracao)}, ip=ip)

        PartnerNotification.objects.create(
            partner=partner,
            tipo='aprovacao',
            titulo='Licença activada',
            mensagem=(
                f"A sua licença '{plano.nome}' foi activada com sucesso. "
                f"Válida até {expiracao.strftime('%d/%m/%Y')}."
            ),
        )
        logger.info("Licença %s activada para parceiro '%s'.", licenca.pk, partner.nome)
        return licenca

    # ─────────────────────────────────────────────────────────────────
    # Gestão de clientes (quota com select_for_update)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def verificar_quota(partner_license: PartnerLicense) -> dict:
        """
        Verifica e devolve o estado da quota da licença.
        Usa select_for_update() para evitar race conditions.
        """
        # Bloquear a linha da licença durante esta transacção
        licenca_lock = PartnerLicense.objects.select_for_update().get(pk=partner_license.pk)
        saldo = licenca_lock.saldo()

        # Verificar se pode criar (total)
        if saldo['total_disponivel'] is not None and saldo['total_disponivel'] <= 0:
            saldo['pode_criar'] = False
            saldo['motivo_bloqueio'] = (
                f"Limite total atingido: {saldo['total_usado']}/{saldo['total_limite']} empresas."
            )
        # Verificar se pode criar (mensal)
        elif saldo['mes_disponivel'] is not None and saldo['mes_disponivel'] <= 0:
            saldo['pode_criar'] = False
            saldo['motivo_bloqueio'] = (
                f"Limite mensal atingido: {saldo['mes_usado']}/{saldo['mes_limite']} empresas este mês."
            )
        else:
            saldo['pode_criar'] = True
            saldo['motivo_bloqueio'] = None

        return saldo

    @staticmethod
    @transaction.atomic
    def registar_cliente(
        partner: Partner,
        empresa,          # instância de Empresa já criada (ou criar aqui)
        plano_cliente_id: int,
        criado_por,
        ip: Optional[str] = None,
    ) -> PartnerClient:
        """
        Regista uma empresa como cliente de um parceiro.

        Fluxo:
          1. Verificar quota com select_for_update (protecção de concorrência).
          2. Verificar que plano_cliente_id está autorizado pela licença.
          3. Criar PartnerClient.
          4. Vincular Licenca do cliente (app licenca existente).
          5. Registar PartnerQuotaUsage.
          6. Auditar.
        """
        # 1. Verificar quota (select_for_update interno)
        licenca = partner.licenca_activa
        if not licenca:
            raise PartnerServiceError(
                "Este parceiro não tem licença activa. "
                "Não é possível cadastrar clientes."
            )
        if not licenca.esta_activa:
            raise PartnerServiceError("Licença do parceiro expirada ou suspensa.")

        saldo = PartnerService.verificar_quota(licenca)
        if not saldo['pode_criar']:
            raise PartnerServiceError(saldo['motivo_bloqueio'])

        # 2. Verificar plano de cliente autorizado
        planos_autorizados = licenca.plano.planos_cliente_autorizados.values_list('id', flat=True)
        if plano_cliente_id not in list(planos_autorizados):
            raise PartnerServiceError(
                f"O plano #{plano_cliente_id} não está autorizado pela sua licença de parceiro. "
                f"Solicite um upgrade ou escolha um plano diferente."
            )

        # 3. Criar PartnerClient
        if PartnerClient.objects.filter(empresa=empresa).exists():
            raise PartnerServiceError(
                f"A empresa '{empresa.nome}' já está associada a um parceiro."
            )

        partner_client = PartnerClient.objects.create(
            partner=partner,
            empresa=empresa,
            status='activo',
            criado_por=criado_por,
        )

        # 4. Vincular Licenca do cliente (usa a app licenca existente)
        try:
            from apps.licenca.models import Licenca, PlanoLicenca
            plano_obj = PlanoLicenca.objects.get(pk=plano_cliente_id)
            licenca_cliente = Licenca.objects.create(
                empresa=empresa,
                plano=plano_obj,
                criada_por_parceiro=True if hasattr(Licenca, 'criada_por_parceiro') else None,
            )
            partner_client.licenca_cliente = licenca_cliente
            partner_client.save(update_fields=['licenca_cliente'])
        except Exception as exc:
            logger.warning(
                "Não foi possível criar licença de cliente automaticamente: %s. "
                "Criar manualmente em Configurações.", exc
            )

        # 5. Registar uso de quota (dentro da mesma transaction.atomic)
        PartnerQuotaUsage.objects.create(
            partner_license=licenca,
            partner_client=partner_client,
            operation='create',
            quantity=1,
            created_by=criado_por,
        )

        # 6. Auditar
        _auditar(partner, 'CLIENT_CREATED', criado_por, 'PartnerClient', partner_client.pk,
                 novo={'empresa': empresa.nome, 'plano_cliente': plano_cliente_id}, ip=ip)

        logger.info(
            "Cliente '%s' registado pelo parceiro '%s'.",
            empresa.nome, partner.nome
        )
        return partner_client

    # ─────────────────────────────────────────────────────────────────
    # Solicitações de plano superior
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def solicitar_upgrade(
        partner: Partner,
        plano_solicitado_id: int,
        motivo: str,
        tipo: str = 'upgrade',
        partner_client: Optional[PartnerClient] = None,
        ip: Optional[str] = None,
    ) -> PartnerLicenseRequest:
        """Cria uma solicitação de upgrade/renovação para um parceiro."""
        plano_atual = None
        if partner.licenca_activa:
            plano_atual = partner.licenca_activa.plano

        try:
            plano_solicitado = PartnerLicensePlan.objects.get(pk=plano_solicitado_id, ativo=True)
        except PartnerLicensePlan.DoesNotExist:
            raise PartnerServiceError(f"Plano #{plano_solicitado_id} não encontrado ou inactivo.")

        request = PartnerLicenseRequest.objects.create(
            partner=partner,
            tipo=tipo,
            plano_atual=plano_atual,
            plano_solicitado=plano_solicitado,
            partner_client=partner_client,
            motivo=motivo,
            status='pendente',
        )

        _auditar(partner, 'REQUEST_CREATED', partner.usuario, 'PartnerLicenseRequest', request.pk,
                 novo={'tipo': tipo, 'plano': plano_solicitado.nome}, ip=ip)

        # Notificar o parceiro
        PartnerNotification.objects.create(
            partner=partner,
            tipo='info',
            titulo='Solicitação recebida',
            mensagem=f"A sua solicitação de {plano_solicitado.nome} foi recebida e está em análise.",
        )
        return request

    @staticmethod
    @transaction.atomic
    def responder_solicitacao(
        request_obj: PartnerLicenseRequest,
        aprovado: bool,
        resposta: str,
        respondido_por,
        ip: Optional[str] = None,
    ) -> PartnerLicenseRequest:
        """Aprova ou rejeita uma solicitação de parceiro."""
        if request_obj.status not in ('pendente', 'em_analise'):
            raise PartnerServiceError(
                f"Solicitação não pode ser respondida no estado '{request_obj.status}'."
            )

        request_obj.status       = 'aprovado' if aprovado else 'rejeitado'
        request_obj.resposta     = resposta
        request_obj.respondido_por = respondido_por
        request_obj.respondido_em  = timezone.now()
        request_obj.save()

        partner = request_obj.partner
        _auditar(
            partner,
            'REQUEST_APPROVED' if aprovado else 'REQUEST_REJECTED',
            respondido_por, 'PartnerLicenseRequest', request_obj.pk,
            novo={'aprovado': aprovado, 'resposta': resposta[:100]}, ip=ip,
        )
        PartnerNotification.objects.create(
            partner=partner,
            tipo='aprovacao' if aprovado else 'rejeicao',
            titulo='Resposta à sua solicitação',
            mensagem=resposta,
        )
        return request_obj

    # ─────────────────────────────────────────────────────────────────
    # Transferência de cliente entre parceiros
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def transferir_cliente(
        partner_client: PartnerClient,
        novo_partner: Partner,
        executado_por,
        motivo: str = '',
        ip: Optional[str] = None,
    ) -> PartnerClient:
        """
        Transfere um cliente de um parceiro para outro.
        O histórico (parceiro_anterior) é preservado.
        """
        parceiro_anterior = partner_client.partner

        if parceiro_anterior.pk == novo_partner.pk:
            raise PartnerServiceError("O parceiro de destino é o mesmo que o actual.")

        partner_client.parceiro_anterior    = parceiro_anterior
        partner_client.partner              = novo_partner
        partner_client.data_transferencia   = timezone.now()
        partner_client.motivo_transferencia = motivo
        partner_client.save()

        _auditar(
            novo_partner, 'CLIENT_TRANSFERRED', executado_por,
            'PartnerClient', partner_client.pk,
            anterior={'parceiro': parceiro_anterior.nome},
            novo={'parceiro': novo_partner.nome, 'motivo': motivo},
            ip=ip,
        )
        logger.info(
            "Cliente '%s' transferido de '%s' para '%s'.",
            partner_client.empresa.nome, parceiro_anterior.nome, novo_partner.nome
        )
        return partner_client

    # ─────────────────────────────────────────────────────────────────
    # Faturamento
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def registar_pagamento(
        partner: Partner,
        licenca: PartnerLicense,
        valor: Decimal,
        metodo: str,
        registado_por,
        referencia: str = '',
        observacoes: str = '',
        ip: Optional[str] = None,
    ) -> PartnerBilling:
        """Regista um pagamento do parceiro à SOTARQ."""
        billing = PartnerBilling.objects.create(
            partner=partner,
            partner_license=licenca,
            valor=valor,
            moeda='AOA',
            metodo=metodo,
            status='pago',
            referencia=referencia,
            registado_por=registado_por,
            data_pagamento=timezone.now(),
            observacoes=observacoes,
        )
        _auditar(partner, 'BILLING_REGISTERED', registado_por, 'PartnerBilling', billing.pk,
                 novo={'valor': str(valor), 'metodo': metodo}, ip=ip)
        return billing

    # ─────────────────────────────────────────────────────────────────
    # Expirar licenças vencidas (chamado pelo Celery Beat)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def expirar_licencas_vencidas() -> int:
        """Verifica e expira licenças cuja data_expiracao < hoje."""
        hoje = timezone.now().date()
        vencidas = PartnerLicense.objects.filter(
            status='activa',
            data_expiracao__lt=hoje,
        )
        count = 0
        for lic in vencidas:
            lic.status = 'expirada'
            lic.save(update_fields=['status'])
            PartnerNotification.objects.create(
                partner=lic.partner,
                tipo='alerta',
                titulo='Licença expirada',
                mensagem=(
                    f"A sua licença '{lic.plano.nome}' expirou em "
                    f"{lic.data_expiracao.strftime('%d/%m/%Y')}. "
                    f"Renove para continuar a usar o Portal de Parceiros."
                ),
            )
            count += 1
        if count:
            logger.info("%d licença(s) de parceiro expirada(s).", count)
        return count
