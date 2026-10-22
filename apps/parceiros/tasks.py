"""Tarefas globais do Portal de Parceiros. Executar sempre no schema public."""
import logging
from calendar import monthrange

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger("parceiros.tasks")


def _subtrair_meses(data, meses):
    idx = data.month - 1 - meses
    ano = data.year + idx // 12
    mes = idx % 12 + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


def _ultima_atividade_comercial(partner):
    """Inclui dados existentes antes da introdução da auditoria comercial."""
    from django.db.models import Max
    from apps.parceiros.models import PartnerAudit, PartnerClient
    from apps.licenca.models import HistoricoLicenca
    candidatos = []
    auditoria = PartnerAudit.objects.filter(
        partner=partner, acao__in=("CLIENT_CREATED", "CLIENT_LICENSE_RENEWED")
    ).order_by("-created_at").values_list("created_at", flat=True).first()
    if auditoria:
        candidatos.append(auditoria)
    cliente = PartnerClient.objects.filter(partner=partner).aggregate(v=Max("created_at"))["v"]
    if cliente:
        candidatos.append(cliente)
    renovacao = HistoricoLicenca.objects.filter(
        licenca__partner_clients__partner=partner,
        acao__in=("renovacao_por_parceiro", "renovacao_confirmada_por_sotarq"),
    ).aggregate(v=Max("created_at"))["v"]
    if renovacao:
        candidatos.append(renovacao)
    return max(candidatos) if candidatos else None


@shared_task(name="parceiros.verificar_inatividade_e_licencas_global", ignore_result=True)
def verificar_inatividade_e_licencas_global():
    """Actualiza inactividade comercial e cria alertas sobre licenças dos clientes.

    Só a criação de tenant e uma renovação de licença contam como actividade
    comercial. A conversa ou o login não prolongam artificialmente a actividade.
    Parceiros já inactivos nunca são reactivados automaticamente.
    """
    from apps.empresas.models import Empresa
    from apps.parceiros.models import Partner, PartnerClient, PartnerAudit, PartnerNotification
    from apps.parceiros.models_comercial import PartnerBusinessEvent
    from apps.licenca.models import HistoricoLicenca

    meses = int(getattr(settings, "PARTNER_INACTIVITY_MONTHS", 6))
    meses = max(3, min(meses, 6))
    hoje = timezone.localdate()
    limite_inactividade = _subtrair_meses(hoje, meses)
    total_inactivos = 0
    avisos_expiracao = 0
    expiradas = 0

    with schema_context("public"):
        # Garante que os modelos globais são sempre consultados na BD/schema correcto.
        schemas_validos = set(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))
        for partner in Partner.objects.filter(status="activo").iterator(chunk_size=300):
            ultima = _ultima_atividade_comercial(partner)
            referencia = timezone.localtime(ultima).date() if ultima else partner.created_at.date()
            if referencia < limite_inactividade:
                with transaction.atomic():
                    partner_lock = Partner.objects.select_for_update().get(pk=partner.pk)
                    # Evita marcar inactivo se uma renovação entrou depois da leitura inicial.
                    ultima_actual = _ultima_atividade_comercial(partner_lock)
                    referencia_actual = timezone.localtime(ultima_actual).date() if ultima_actual else partner_lock.created_at.date()
                    if partner_lock.status == "activo" and referencia_actual < limite_inactividade:
                        partner_lock.status = "inactivo"
                        partner_lock.save(update_fields=["status", "updated_at"])
                        PartnerAudit.objects.create(
                            partner=partner_lock,
                            acao="PARTNER_AUTO_INACTIVATED",
                            objeto_tipo="Partner",
                            objeto_id=str(partner_lock.pk),
                            origem="celery",
                            valor_anterior={"status": "activo"},
                            valor_novo={"status": "inactivo", "ultima_atividade": str(referencia_actual), "meses": meses},
                        )
                        PartnerNotification.objects.create(
                            partner=partner_lock, tipo="alerta", titulo="Conta inactiva",
                            mensagem=(f"A sua conta foi marcada como inactiva por {meses} meses sem "
                                      "novos tenants ou renovações. Contacte a SOTARQ para solicitar reactivação."),
                        )
                        evento_inactivo, evento_novo = PartnerBusinessEvent.objects.get_or_create(
                            chave_evento=f"partner_inactivo:{partner_lock.pk}:{hoje.isoformat()}",
                            defaults={
                                "partner": partner_lock, "tipo": "parceiro_inactivo",
                                "titulo": "Parceiro marcado como inactivo",
                                "descricao": f"Última actividade comercial em {referencia_actual}.",
                                "dados": {"ultima_atividade": str(referencia_actual), "meses": meses},
                                "visivel_parceiro": True,
                            },
                        )
                        if evento_novo:
                            _enfileirar_alerta_staff(evento_inactivo.pk)
                        total_inactivos += 1

        qs = PartnerClient.objects.select_related("partner", "empresa", "licenca_cliente")
        for cliente in qs.iterator(chunk_size=500):
            lic = cliente.licenca_cliente
            if lic is None:
                continue
            # A relação Empresa é shared. O schema_name serve apenas para confirmar
            # que a empresa é um tenant válido, não para consultar tabelas do tenant.
            if cliente.empresa.schema_name not in schemas_validos:
                continue
            dias = (lic.data_vencimento - hoje).days if lic.data_vencimento else -1
            if lic.status == "ativa" and 0 <= dias <= 30:
                chave = f"licenca_a_vencer:{lic.pk}:{lic.data_vencimento.isoformat()}"
                evento, created = PartnerBusinessEvent.objects.get_or_create(
                    chave_evento=chave,
                    defaults={
                        "partner": cliente.partner, "partner_client": cliente,
                        "licenca_cliente": lic, "tipo": "licenca_a_vencer",
                        "titulo": "Licença de cliente prestes a expirar",
                        "descricao": f"A licença de {cliente.empresa.nome} vence em {lic.data_vencimento.strftime('%d/%m/%Y')} ({dias} dias). Contacte o cliente para renovar.",
                        "dados": {"empresa_id": cliente.empresa_id, "data_vencimento": str(lic.data_vencimento), "dias": dias},
                        "visivel_parceiro": True,
                    },
                )
                if created:
                    _enfileirar_alerta_staff(evento.pk)
                    PartnerNotification.objects.create(
                        partner=cliente.partner, tipo="aviso", titulo="Cliente prestes a expirar",
                        mensagem=f"A licença de {cliente.empresa.nome} vence em {lic.data_vencimento.strftime('%d/%m/%Y')}. Contacte o cliente.",
                    )
                    avisos_expiracao += 1
            elif lic.data_vencimento < hoje and lic.status not in ("cancelada", "suspensa", "pendente_pagamento"):
                if lic.status != "expirada":
                    anterior = lic.status
                    lic.status = "expirada"
                    lic.save(update_fields=["status", "updated_at"])
                    HistoricoLicenca.objects.create(
                        licenca=lic, acao="expiracao_automatica", data_anterior=lic.data_vencimento,
                        data_nova=lic.data_vencimento, observacoes=f"Estado alterado automaticamente de {anterior} para expirada.",
                    )
                if cliente.status != "expirado":
                    cliente.status = "expirado"
                    cliente.save(update_fields=["status", "updated_at"])
                chave = f"licenca_expirada:{lic.pk}:{lic.data_vencimento.isoformat()}"
                evento, created = PartnerBusinessEvent.objects.get_or_create(
                    chave_evento=chave,
                    defaults={
                        "partner": cliente.partner, "partner_client": cliente,
                        "licenca_cliente": lic, "tipo": "licenca_expirada",
                        "titulo": "Licença de cliente expirada",
                        "descricao": f"A licença de {cliente.empresa.nome} expirou em {lic.data_vencimento.strftime('%d/%m/%Y')}. Contacte o cliente para recuperar a subscrição.",
                        "dados": {"empresa_id": cliente.empresa_id, "data_vencimento": str(lic.data_vencimento)},
                        "visivel_parceiro": True,
                    },
                )
                if created:
                    _enfileirar_alerta_staff(evento.pk)
                    PartnerNotification.objects.create(
                        partner=cliente.partner, tipo="alerta", titulo="Cliente com licença expirada",
                        mensagem=f"A licença de {cliente.empresa.nome} expirou. Contacte o cliente para renovar.",
                    )
                    expiradas += 1

    logger.info("Parceiros inactivos=%s, avisos de expiração=%s, licenças expiradas=%s", total_inactivos, avisos_expiracao, expiradas)
    return {"parceiros_inactivos": total_inactivos, "avisos_expiracao": avisos_expiracao, "licencas_expiradas": expiradas}


@shared_task(bind=True, name="parceiros.notificar_mensagem_parceiro", max_retries=3, default_retry_delay=60, ignore_result=True)
def notificar_mensagem_parceiro(self, mensagem_id):
    """Email assíncrono para membros de uma conversa global do portal."""
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.parceiros.models_comercial import PartnerMessage

    with schema_context("public"):
        msg = PartnerMessage.objects.select_related("conversa", "autor_partner", "autor_usuario").filter(pk=mensagem_id).first()
        if not msg:
            return {"estado": "mensagem_inexistente"}
        emails = set()
        for membro in msg.conversa.participantes.select_related("partner", "usuario"):
            if msg.autor_partner_id and membro.partner_id == msg.autor_partner_id:
                continue
            if msg.autor_usuario_id and membro.usuario_id == msg.autor_usuario_id:
                continue
            email = (membro.partner.email if membro.partner_id else membro.usuario.email if membro.usuario_id else "") or ""
            if email.strip() and "@" in email:
                emails.add(email.strip())
        destinatarios = sorted(emails)
        if not destinatarios:
            return {"estado": "sem_destinatarios"}
        autor = msg.autor_partner.nome if msg.autor_partner_id else str(msg.autor_usuario or "Equipa SOTARQ")
        texto = (msg.texto or "").strip()[:500] or "Foi enviado um anexo. Entre no portal para o consultar."
        try:
            send_mail(
                subject=f"Nova mensagem do portal: {msg.conversa.titulo}",
                message=f"{autor} enviou uma mensagem.\n\n{texto}\n\nEntre no Portal de Parceiros para consultar a conversa.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=destinatarios,
                fail_silently=False,
            )
            return {"estado": "enviada", "destinatarios": len(destinatarios)}
        except Exception as exc:
            logger.exception("Falha ao notificar mensagem do parceiro %s", mensagem_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return {"estado": "erro"}


@shared_task(bind=True, name="parceiros.notificar_evento_comercial_staff", max_retries=3, default_retry_delay=60, ignore_result=True)
def notificar_evento_comercial_staff(self, evento_id):
    """Aviso por email à equipa SOTARQ; detalhes completos ficam no portal/admin."""
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.parceiros.models_comercial import PartnerBusinessEvent

    with schema_context("public"):
        evento = PartnerBusinessEvent.objects.select_related("partner", "partner_client", "licenca_cliente").filter(pk=evento_id).first()
        if not evento:
            return {"estado": "evento_inexistente"}
        raw = getattr(settings, "PARTNERS_STAFF_ALERT_EMAILS", "") or ""
        if isinstance(raw, (list, tuple, set)):
            emails = sorted({str(e).strip() for e in raw if str(e).strip()})
        else:
            emails = sorted({e.strip() for e in str(raw).replace(";", ",").split(",") if e.strip()})
        if not emails:
            logger.info("Evento comercial %s registado; PARTNERS_STAFF_ALERT_EMAILS não está configurado.", evento.pk)
            return {"estado": "staff_email_nao_configurado", "evento_id": evento.pk}
        texto = (
            f"Evento: {evento.get_tipo_display()}\nParceiro: {evento.partner.nome}\n"
            f"Título: {evento.titulo}\nDescrição: {evento.descricao}\n"
            f"Data: {timezone.localtime(evento.created_at).isoformat()}\n\n"
            "Entre na área de parceiros do VistoGest para consultar detalhes e tomar medidas."
        )
        try:
            send_mail(
                subject=f"[SOTARQ Parceiros] {evento.titulo}", message=texto,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=emails, fail_silently=False,
            )
            return {"estado": "enviada", "evento_id": evento.pk}
        except Exception as exc:
            logger.exception("Falha ao notificar equipa do evento comercial %s", evento_id)
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return {"estado": "erro", "evento_id": evento_id}


def _enfileirar_alerta_staff(evento_id):
    try:
        notificar_evento_comercial_staff.delay(evento_id)
    except Exception:
        logger.exception("Evento comercial %s ficou registado, mas não foi enfileirado para email staff.", evento_id)
