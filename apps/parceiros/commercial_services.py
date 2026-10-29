# apps/parceiros/commercial_services.py
"""Regras comerciais novas do portal de parceiros.

Todos os modelos Partner/Empresa/Licenca aqui usados são globais (schema public).
Não chamar estes serviços de dentro de schema_context(tenant) sem entrar em
schema_context('public') primeiro.
"""
import calendar
import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, models
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.licenca.models import Licenca, PlanoLicenca, HistoricoLicenca
from apps.parceiros.models import Partner, PartnerClient, PartnerAudit, PartnerNotification
from apps.parceiros.models_comercial import PartnerCommission, PartnerBusinessEvent

logger = logging.getLogger("parceiros.comercial")
User = get_user_model()
COMISSAO_PERCENTAGEM = Decimal("10.00")
ATIVIDADES_QUE_MANTEM_ATIVO = {"CLIENT_CREATED", "CLIENT_LICENSE_RENEWED"}


def _adicionar_meses(data, meses):
    if meses < 1 or meses > 36:
        raise ValidationError("O período de renovação deve ser entre 1 e 36 meses.")
    indice = data.month - 1 + meses
    ano = data.year + indice // 12
    mes = indice % 12 + 1
    dia = min(data.day, calendar.monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


def registar_atividade_comercial(partner, acao, utilizador=None, *, objeto_tipo="", objeto_id="", descricao="", ip=None):
    """Regista actividade relevante e auditável. Login/chat não contam para evitar falsos activos."""
    if acao not in ATIVIDADES_QUE_MANTEM_ATIVO:
        raise ValidationError("Esta acção não conta como actividade comercial para manter o parceiro activo.")
    PartnerAudit.objects.create(
        partner=partner,
        acao=acao,
        objeto_tipo=objeto_tipo,
        objeto_id=str(objeto_id or ""),
        executado_por=utilizador,
        ip_address=ip,
        origem="portal",
        valor_novo={"descricao": descricao} if descricao else {},
    )
    if partner.status == "inactivo":
        # Não reactivar automaticamente um parceiro que já foi inactivado.
        # Exige intervenção explícita de um superuser.
        return
    logger.info("Actividade comercial %s registada para partner_id=%s", acao, partner.pk)


def _criar_evento(partner, tipo, chave, titulo, descricao="", *, cliente=None, licenca=None, dados=None, visivel=True):
    evento, criado = PartnerBusinessEvent.objects.get_or_create(
        chave_evento=chave,
        defaults={
            "partner": partner,
            "partner_client": cliente,
            "licenca_cliente": licenca,
            "tipo": tipo,
            "titulo": titulo,
            "descricao": descricao,
            "dados": dados or {},
            "visivel_parceiro": visivel,
        },
    )
    if criado and visivel:
        PartnerNotification.objects.create(partner=partner, tipo="info", titulo=titulo, mensagem=descricao or titulo)
    if criado:
        from django.db import transaction as db_transaction
        def _enviar_alerta_staff(evento_pk=evento.pk):
            try:
                from apps.parceiros.tasks import notificar_evento_comercial_staff
                notificar_evento_comercial_staff.delay(evento_pk)
            except Exception:
                logger.exception("Evento comercial guardado, mas o alerta assíncrono não foi enfileirado (evento=%s).", evento_pk)
        db_transaction.on_commit(_enviar_alerta_staff)
    return evento


@transaction.atomic
def registar_cliente_ilimitado(*, partner_id, empresa_id, plano_cliente_id, criado_por, ip=None, meses_iniciais=1):
    """Liga tenant ao parceiro e cria licença/comissão pendentes de confirmação de pagamento.

    A criação física do tenant/schema deve continuar a ser feita pelo provisionador
    existente do projecto; esta função não inventa campos obrigatórios de Empresa.
    """
    partner = Partner.objects.select_for_update().get(pk=partner_id)
    if partner.status != "activo":
        raise PermissionDenied("O parceiro não está activo. A reactivação exige um superuser SOTARQ.")
    empresa = Empresa.objects.get(pk=empresa_id)
    plano = PlanoLicenca.objects.get(pk=plano_cliente_id, ativo=True)
    if PartnerClient.objects.filter(empresa=empresa).exists():
        raise ValidationError("Esta empresa já está associada a um parceiro.")

    hoje = timezone.localdate()
    if meses_iniciais < 1 or meses_iniciais > 36:
        raise ValidationError("O período inicial deve estar entre 1 e 36 meses.")
    # O prazo real começa quando a SOTARQ confirma o recebimento; não confiar
    # num valor declarado pelo parceiro nem dar acesso com pagamento por confirmar.
    vencimento_provisorio = hoje
    licenca = Licenca.objects.select_for_update().filter(empresa=empresa).first()
    if licenca is None:
        licenca = Licenca.objects.create(
            plano=plano, data_inicio=hoje,
            data_vencimento=vencimento_provisorio, status="pendente_pagamento",
        )
        HistoricoLicenca.objects.create(
            licenca=licenca, acao="activacao_pendente_pagamento", data_anterior=None,
            data_nova=vencimento_provisorio,
            observacoes=f"A activação aguarda confirmação do pagamento pela SOTARQ; duração solicitada: {meses_iniciais} mês(es).",
        )
    else:
        if licenca.status in {"suspensa", "cancelada"}:
            raise ValidationError("A licença existente está suspensa/cancelada; a SOTARQ deve rever antes de activar.")
        if licenca.status == "ativa" and not licenca.esta_vencida:
            raise ValidationError("A empresa já tem uma licença válida. Use o fluxo de renovação.")
        data_anterior = licenca.data_vencimento
        plano_anterior = licenca.plano_id
        licenca.plano = plano
        licenca.data_inicio = hoje
        licenca.data_vencimento = vencimento_provisorio
        licenca.status = "pendente_pagamento"
        licenca.data_cancelamento = None
        licenca.save(update_fields=["plano", "data_inicio", "data_vencimento", "status", "data_cancelamento", "updated_at"])
        HistoricoLicenca.objects.create(
            licenca=licenca, acao="activacao_pendente_pagamento", data_anterior=data_anterior,
            data_nova=vencimento_provisorio,
            observacoes=f"Activação proposta pelo parceiro {partner.nome}; aguarda confirmação do pagamento. Plano anterior ID={plano_anterior}; duração solicitada: {meses_iniciais} mês(es).",
        )

    cliente = PartnerClient.objects.create(
        partner=partner,
        empresa=empresa,
        status="activo",
        licenca_cliente=licenca,
        criado_por=criado_por,
    )
    # O valor enviado no POST pelo parceiro não é uma fonte contabilística confiável.
    # A base esperada vem do plano/preço oficial; a SOTARQ confirma o recebimento separadamente.
    base = (plano.preco_mensal * meses_iniciais).quantize(Decimal("0.01"))
    if base <= 0:
        raise ValidationError("O preço oficial do plano deve ser superior a zero.")
    PartnerCommission.objects.get_or_create(
        chave_evento=f"novo_cliente:{cliente.pk}:{licenca.pk}",
        defaults={
            "partner": partner, "partner_client": cliente, "licenca_cliente": licenca,
            "tipo": "novo_cliente", "periodo_meses": meses_iniciais,
            "base_calculo": base, "percentagem": COMISSAO_PERCENTAGEM,
            "status": "aguarda_confirmacao", "criado_por": criado_por,
            "observacoes": "Comissão prevista; requer confirmação de pagamento pela equipa SOTARQ.",
        },
    )
    _criar_evento(
        partner, "tenant_criado", f"tenant_criado:{cliente.pk}",
        "Novo cliente associado", f"A empresa {empresa.nome} foi associada ao parceiro; a licença aguarda confirmação do pagamento pela SOTARQ.",
        cliente=cliente, licenca=licenca, dados={"empresa_id": empresa.pk},
    )
    _criar_evento(
        partner, "pagamento_pendente", f"pagamento_pendente:nova_licenca:{licenca.pk}",
        "Pagamento por confirmar", f"Pagamento esperado: {base:.2f} AOA; comissão prevista: {(base * COMISSAO_PERCENTAGEM / Decimal('100')):.2f} AOA.",
        cliente=cliente, licenca=licenca, dados={"base_calculo": str(base), "percentagem": "10.00"}, visivel=False,
    )
    registar_atividade_comercial(partner, "CLIENT_CREATED", criado_por, objeto_tipo="PartnerClient", objeto_id=cliente.pk, descricao=f"Empresa {empresa.nome} associada", ip=ip)
    return cliente


@transaction.atomic
def renovar_licenca_cliente(*, partner_id, partner_client_id, meses, executado_por, ip=None, referencia_pagamento=""):
    """Renova a licença de cliente e prepara comissão; confirmação monetária fica com SOTARQ."""
    partner = Partner.objects.select_for_update().get(pk=partner_id)
    if partner.status != "activo":
        raise PermissionDenied("O parceiro não está activo. A reactivação exige um superuser SOTARQ.")
    cliente = PartnerClient.objects.select_for_update().select_related("licenca_cliente", "empresa").get(
        pk=partner_client_id, partner=partner
    )
    licenca = cliente.licenca_cliente
    if not licenca:
        raise ValidationError("Este cliente não tem uma licença associada para renovar.")
    if licenca.status in {"cancelada", "suspensa", "pendente_pagamento"}:
        raise ValidationError("Uma licença cancelada ou suspensa precisa de revisão da equipa SOTARQ.")
    hoje = timezone.localdate()
    meses = int(meses)
    antiga = licenca.data_vencimento
    inicio_base = antiga if (antiga and antiga >= hoje and licenca.status == "ativa") else hoje
    vencimento_proposto = _adicionar_meses(inicio_base, meses)
    # Ignorar valor declarado na requisição: a comissão usa o preço oficial do plano.
    base = (licenca.plano.preco_mensal * meses).quantize(Decimal("0.01"))
    if base <= 0:
        raise ValidationError("O preço oficial do plano deve ser superior a zero.")

    key = f"renovacao:{licenca.pk}:{vencimento_proposto.isoformat()}:{meses}:{base:.2f}"
    PartnerCommission.objects.get_or_create(
        chave_evento=key,
        defaults={
            "partner": partner, "partner_client": cliente, "licenca_cliente": licenca,
            "tipo": "renovacao", "periodo_meses": meses,
            "base_calculo": base, "percentagem": COMISSAO_PERCENTAGEM,
            "status": "aguarda_confirmacao", "criado_por": executado_por,
            "comprovativo_referencia": referencia_pagamento,
            "observacoes": "Renovação registada; confirmar recebimento antes de reconhecer a comissão.",
        },
    )
    _criar_evento(
        partner, "pagamento_pendente", f"renovacao_pendente:{licenca.pk}:{vencimento_proposto.isoformat()}:{meses}:{base:.2f}",
        "Renovação submetida — pagamento por confirmar",
        f"O pedido de renovação da licença de {cliente.empresa.nome} por {meses} mês(es) aguarda confirmação do pagamento pela SOTARQ. A data de vencimento só será alterada depois da confirmação.",
        cliente=cliente, licenca=licenca, dados={"data_anterior": str(antiga), "data_vencimento_proposto": str(vencimento_proposto), "meses": meses, "base_calculo": str(base)},
    )
    _criar_evento(
        partner, "pagamento_pendente", f"pagamento_pendente:renovacao:{licenca.pk}:{vencimento_proposto.isoformat()}:{meses}:{base:.2f}",
        "Pagamento de renovação por confirmar",
        f"Pagamento esperado pelo preço oficial do plano: {base:.2f} AOA; comissão prevista: {(base * COMISSAO_PERCENTAGEM / Decimal('100')):.2f} AOA.",
        cliente=cliente, licenca=licenca, dados={"base_calculo": str(base), "percentagem": "10.00", "vencimento_proposto": str(vencimento_proposto), "meses": meses}, visivel=False,
    )
    # Não contar um pedido por pagar como renovação concluída. A actividade comercial
    # é registada em confirmar_comissao, após conciliação pela equipa SOTARQ.
    return licenca


@transaction.atomic
def confirmar_comissao(comissao_id, confirmado_por, referencia=""):
    """Apenas equipa autorizada deve chamar esta função após conciliar o pagamento."""
    if not (getattr(confirmado_por, "is_superuser", False) or getattr(confirmado_por, "has_perm", lambda p: False)("parceiros.change_partnercommission")):
        raise PermissionDenied("Sem permissão para confirmar comissões.")
    comissao = PartnerCommission.objects.select_for_update().get(pk=comissao_id)
    if comissao.status == "confirmada" or comissao.status == "paga":
        return comissao
    if comissao.status != "aguarda_confirmacao":
        raise ValidationError("Esta comissão já foi rejeitada ou cancelada.")
    # Uma referência escrita pelo próprio parceiro não substitui prova documental.
    # Exigir anexo privado associado à comissão; a equipa deve abrir e validar o comprovativo.
    from apps.parceiros.models_comercial import PartnerMessage
    tem_comprovativo = PartnerMessage.objects.filter(comissao=comissao).exclude(
        anexo__isnull=True
    ).exclude(anexo="").exists()
    if not tem_comprovativo:
        raise ValidationError(
            "Não é possível confirmar sem um comprovativo anexado a uma mensagem do chat e associado a esta comissão."
        )
    # Validar ligações financeiras antes de alterar estados.
    licenca = comissao.licenca_cliente
    if licenca is None:
        raise ValidationError("A comissão não tem uma licença de cliente associada; verifique o registo antes de confirmar.")
    comissao.status = "confirmada"
    comissao.confirmado_por = confirmado_por
    comissao.confirmado_em = timezone.now()
    if referencia:
        comissao.comprovativo_referencia = referencia
    comissao.save(update_fields=["status", "confirmado_por", "confirmado_em", "comprovativo_referencia", "updated_at"])

    # A licença só fica activa depois de a SOTARQ conciliar e confirmar o pagamento.
    hoje = timezone.localdate()
    data_anterior = licenca.data_vencimento
    if comissao.tipo == "novo_cliente":
        inicio = hoje
        vencimento = _adicionar_meses(inicio, comissao.periodo_meses)
        acao_licenca = "activacao_confirmada_por_sotarq"
    else:
        inicio = licenca.data_vencimento if (licenca.data_vencimento and licenca.data_vencimento >= hoje and licenca.status == "ativa") else hoje
        vencimento = _adicionar_meses(inicio, comissao.periodo_meses)
        acao_licenca = "renovacao_confirmada_por_sotarq"
    licenca.data_inicio = inicio
    licenca.data_vencimento = vencimento
    licenca.status = "ativa"
    licenca.data_cancelamento = None
    licenca.save(update_fields=["data_inicio", "data_vencimento", "status", "data_cancelamento", "updated_at"])
    HistoricoLicenca.objects.create(
        licenca=licenca, acao=acao_licenca, data_anterior=data_anterior,
        data_nova=vencimento,
        observacoes=(f"Pagamento conciliado por {confirmado_por}; comissão #{comissao.pk}; "
                     f"período aplicado: {comissao.periodo_meses} mês(es)."),
    )
    cliente = comissao.partner_client
    if cliente.status != "activo":
        cliente.status = "activo"
        cliente.save(update_fields=["status", "updated_at"])
    if comissao.tipo == "renovacao":
        PartnerAudit.objects.create(
            partner=comissao.partner, acao="CLIENT_LICENSE_RENEWED",
            objeto_tipo="Licenca", objeto_id=str(licenca.pk), executado_por=confirmado_por,
            origem="admin", valor_anterior={"data_vencimento": str(data_anterior)},
            valor_novo={"data_vencimento": str(vencimento), "periodo_meses": comissao.periodo_meses,
                        "confirmado_por": getattr(confirmado_por, "pk", None), "comissao_id": comissao.pk},
        )
        _criar_evento(
            comissao.partner, "renovacao", f"renovacao_confirmada:comissao:{comissao.pk}",
            "Renovação confirmada", f"A licença de {cliente.empresa.nome} foi renovada até {vencimento.strftime('%d/%m/%Y')}.",
            cliente=cliente, licenca=licenca,
            dados={"data_anterior": str(data_anterior), "data_nova": str(vencimento), "comissao_id": comissao.pk},
        )
    PartnerAudit.objects.create(
        partner=comissao.partner, acao="COMMISSION_CONFIRMED", objeto_tipo="PartnerCommission",
        objeto_id=str(comissao.pk), executado_por=confirmado_por, origem="admin",
        valor_anterior={"status": "aguarda_confirmacao"},
        valor_novo={"status": "confirmada", "base_calculo": str(comissao.base_calculo), "comissao": str(comissao.valor_comissao)},
    )
    _criar_evento(
        comissao.partner, "pagamento_confirmado", f"pagamento_confirmado:comissao:{comissao.pk}",
        "Pagamento confirmado", f"Pagamento de {comissao.base_calculo:.2f} AOA confirmado. Comissão de 10%: {comissao.valor_comissao:.2f} AOA.",
        cliente=comissao.partner_client, licenca=comissao.licenca_cliente,
        dados={"comissao_id": comissao.pk, "valor_comissao": str(comissao.valor_comissao)},
    )
    return comissao


@transaction.atomic
def marcar_comissao_paga(comissao_id, pago_por, referencia=""):
    if not (getattr(pago_por, "is_superuser", False) or getattr(pago_por, "has_perm", lambda p: False)("parceiros.change_partnercommission")):
        raise PermissionDenied("Sem permissão para liquidar comissões.")
    comissao = PartnerCommission.objects.select_for_update().get(pk=comissao_id)
    if comissao.status == "paga":
        return comissao
    if comissao.status != "confirmada":
        raise ValidationError("Só comissões confirmadas podem ser pagas.")
    comissao.status = "paga"
    comissao.pago_em = timezone.now()
    if referencia:
        comissao.comprovativo_referencia = referencia
    comissao.save(update_fields=["status", "pago_em", "comprovativo_referencia", "updated_at"])
    PartnerAudit.objects.create(
        partner=comissao.partner, acao="COMMISSION_PAID", objeto_tipo="PartnerCommission",
        objeto_id=str(comissao.pk), executado_por=pago_por, origem="admin",
        valor_novo={"valor": str(comissao.valor_comissao), "referencia": referencia},
    )
    return comissao


@transaction.atomic
def reativar_parceiro_superuser(partner_id, utilizador, motivo):
    if not getattr(utilizador, "is_superuser", False):
        raise PermissionDenied("Só um superuser pode reactivar um parceiro inactivo.")
    if not (motivo or "").strip():
        raise ValidationError("Indique o motivo da reactivação.")
    partner = Partner.objects.select_for_update().get(pk=partner_id)
    if partner.status != "inactivo":
        raise ValidationError("Só parceiros inactivos podem ser reactivados por este fluxo.")
    anterior = partner.status
    partner.status = "activo"
    partner.save(update_fields=["status", "updated_at"])
    PartnerAudit.objects.create(
        partner=partner, acao="PARTNER_REACTIVATED", objeto_tipo="Partner", objeto_id=str(partner.pk),
        executado_por=utilizador, origem="admin", valor_anterior={"status": anterior},
        valor_novo={"status": "activo", "motivo": motivo.strip()},
    )
    _criar_evento(
        partner, "parceiro_reativado", f"parceiro_reativado:{partner.pk}:{partner.updated_at.isoformat()}",
        "Conta reactivada", f"A equipa SOTARQ reactivou a sua conta. Motivo: {motivo.strip()}",
        dados={"reativado_por": utilizador.pk, "motivo": motivo.strip()},
    )
    return partner



@transaction.atomic
def rejeitar_comissao(comissao_id, respondido_por, motivo):
    if not (getattr(respondido_por, "is_superuser", False) or getattr(respondido_por, "has_perm", lambda p: False)("parceiros.change_partnercommission")):
        raise PermissionDenied("Sem permissão para rejeitar comissões.")
    if not (motivo or "").strip():
        raise ValidationError("Indique o motivo da rejeição.")
    comissao = PartnerCommission.objects.select_for_update().get(pk=comissao_id)
    if comissao.status != "aguarda_confirmacao":
        raise ValidationError("Só comissões a aguardar confirmação podem ser rejeitadas.")
    anterior = comissao.status
    comissao.status = "rejeitada"
    comissao.confirmado_por = respondido_por
    comissao.confirmado_em = timezone.now()
    comissao.observacoes = (comissao.observacoes + "\nRejeitada: " + motivo.strip()).strip()
    comissao.save(update_fields=["status", "confirmado_por", "confirmado_em", "observacoes", "updated_at"])
    # Se o pagamento inicial foi rejeitado, não deixar a licença a aguardar
    # confirmação indefinidamente. O parceiro poderá voltar a submeter o pagamento
    # pela via de renovação; a licença continua sem acesso até nova confirmação.
    if comissao.tipo == "novo_cliente" and comissao.licenca_cliente_id:
        licenca = comissao.licenca_cliente
        if licenca.status == "pendente_pagamento":
            data_anterior = licenca.data_vencimento
            licenca.status = "expirada"
            licenca.save(update_fields=["status", "updated_at"])
            HistoricoLicenca.objects.create(
                licenca=licenca, acao="activacao_rejeitada_pagamento",
                data_anterior=data_anterior, data_nova=data_anterior,
                observacoes=f"Pagamento da comissão #{comissao.pk} rejeitado por {respondido_por}; motivo: {motivo.strip()}",
            )
            comissao.partner_client.status = "expirado"
            comissao.partner_client.save(update_fields=["status", "updated_at"])
    PartnerAudit.objects.create(
        partner=comissao.partner, acao="COMMISSION_REJECTED", objeto_tipo="PartnerCommission",
        objeto_id=str(comissao.pk), executado_por=respondido_por, origem="admin",
        valor_anterior={"status": anterior}, valor_novo={"status": "rejeitada", "motivo": motivo.strip()},
    )
    PartnerNotification.objects.create(
        partner=comissao.partner, tipo="rejeicao", titulo="Pagamento não confirmado",
        mensagem=f"A comissão #{comissao.pk} aguarda regularização: {motivo.strip()}",
    )
    return comissao


def tempo_status_partner(partner, agora=None):
    """Devolve dias registados como activo/inactivo com base nas transições auditadas.

    O cálculo é tão completo quanto o histórico disponível: transições manuais antigas
    não auditadas não podem ser reconstruídas retroactivamente.
    """
    from datetime import datetime
    agora = agora or timezone.now()
    inicio = partner.created_at
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
    estado = "activo"
    cursor = inicio
    segundos_activo = 0.0
    segundos_inactivo = 0.0
    transicoes = PartnerAudit.objects.filter(
        partner=partner,
        acao__in=("PARTNER_AUTO_INACTIVATED", "PARTNER_REACTIVATED"),
        created_at__gte=inicio,
        created_at__lte=agora,
    ).order_by("created_at", "pk").values_list("acao", "created_at")
    for acao, quando in transicoes:
        if timezone.is_naive(quando):
            quando = timezone.make_aware(quando, timezone.get_current_timezone())
        delta = max(0.0, (quando - cursor).total_seconds())
        if estado == "activo":
            segundos_activo += delta
        else:
            segundos_inactivo += delta
        if acao == "PARTNER_AUTO_INACTIVATED":
            estado = "inactivo"
        elif acao == "PARTNER_REACTIVATED":
            estado = "activo"
        cursor = quando
    delta_final = max(0.0, (agora - cursor).total_seconds())
    if partner.status == "inactivo":
        # Se a transição de inactividade não tiver sido auditada (dados anteriores ao patch),
        # não inventar períodos; o tempo final começa na última transição registada.
        segundos_inactivo += delta_final
    else:
        segundos_activo += delta_final
    return {
        "dias_registados_activo": int(segundos_activo // 86400),
        "dias_registados_inactivo": int(segundos_inactivo // 86400),
        "historico_status_limitado": True,
    }



def ultima_atividade_comercial(partner):
    """Timestamp mais recente de tenant criado ou renovação confirmada.

    Usa auditoria primeiro, mas também reconhece clientes/históricos anteriores ao
    patch para não tornar inactivo um parceiro activo por falta de logs antigos.
    """
    from django.db.models import Max
    from apps.licenca.models import HistoricoLicenca
    candidatos = []
    audit = PartnerAudit.objects.filter(
        partner=partner, acao__in=("CLIENT_CREATED", "CLIENT_LICENSE_RENEWED")
    ).order_by("-created_at").values_list("created_at", flat=True).first()
    if audit:
        candidatos.append(audit)
    cliente_data = PartnerClient.objects.filter(partner=partner).aggregate(v=Max("created_at"))["v"]
    if cliente_data:
        candidatos.append(cliente_data)
    historico_data = HistoricoLicenca.objects.filter(
        licenca__partner_clients__partner=partner,
        acao__in=("renovacao_por_parceiro", "renovacao_confirmada_por_sotarq"),
    ).aggregate(v=Max("created_at"))["v"]
    if historico_data:
        candidatos.append(historico_data)
    return max(candidatos) if candidatos else None

def metricas_dashboard_parceiro(partner):
    """Métricas sem expor dados de outros parceiros."""
    hoje = timezone.localdate()
    clientes = PartnerClient.objects.filter(partner=partner).select_related("empresa", "licenca_cliente")
    comissoes = PartnerCommission.objects.filter(partner=partner)
    vencimento = hoje + timezone.timedelta(days=30)
    return {
        "clientes_total": clientes.count(),
        "clientes_activos": clientes.filter(status="activo", licenca_cliente__status="ativa", licenca_cliente__data_vencimento__gte=hoje).count(),
        "clientes_pendentes_pagamento": comissoes.filter(status="aguarda_confirmacao").count(),
        "clientes_expirados": clientes.filter(status="expirado").count(),
        "clientes_a_vencer": clientes.filter(licenca_cliente__status="ativa", licenca_cliente__data_vencimento__gte=hoje, licenca_cliente__data_vencimento__lte=vencimento).count(),
        "licencas_renovadas": PartnerAudit.objects.filter(partner=partner, acao="CLIENT_LICENSE_RENEWED").count(),
        "comissao_prevista": comissoes.filter(status="aguarda_confirmacao").aggregate(v=models.Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "comissao_confirmada": comissoes.filter(status="confirmada").aggregate(v=models.Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "comissao_paga": comissoes.filter(status="paga").aggregate(v=models.Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "ultimos_eventos": partner.eventos_comerciais.filter(visivel_parceiro=True).order_by("-created_at")[:10],
    }


def metricas_dashboard_staff():
    """Indicadores globais SOTARQ; usar apenas na área staff autorizada."""
    from apps.parceiros.models_comercial import PartnerBusinessEvent
    from django.db.models import Sum, Count
    hoje = timezone.localdate()
    return {
        "total_parceiros": Partner.objects.count(),
        "parceiros_activos": Partner.objects.filter(status="activo").count(),
        "parceiros_inactivos": Partner.objects.filter(status="inactivo").count(),
        "total_tenants_associados": PartnerClient.objects.count(),
        "clientes_expirados": PartnerClient.objects.filter(status="expirado").count(),
        "clientes_a_vencer": PartnerClient.objects.filter(
            licenca_cliente__status="ativa",
            licenca_cliente__data_vencimento__gte=hoje,
            licenca_cliente__data_vencimento__lte=hoje + timezone.timedelta(days=30),
        ).count(),
        "comissao_aguarda_confirmacao": PartnerCommission.objects.filter(status="aguarda_confirmacao").aggregate(v=Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "comissao_confirmada": PartnerCommission.objects.filter(status="confirmada").aggregate(v=Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "comissao_paga": PartnerCommission.objects.filter(status="paga").aggregate(v=Sum("valor_comissao"))["v"] or Decimal("0.00"),
        "eventos_nao_resolvidos": PartnerBusinessEvent.objects.filter(resolvido=False).count(),
        "ultimos_eventos_staff": PartnerBusinessEvent.objects.select_related("partner", "partner_client", "licenca_cliente").order_by("-created_at")[:50],
        "novos_tenants_mes": PartnerClient.objects.filter(created_at__year=hoje.year, created_at__month=hoje.month).count(),
    }
