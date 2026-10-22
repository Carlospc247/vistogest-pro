# apps/clientes/tasks.py
"""Tasks Celery do chat em tenant físico, com outbox para não perder avisos."""
import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger("clientes.chat_tasks")


def _validar_schema_tenant(schema_name):
    from apps.empresas.models import Empresa
    if not schema_name or schema_name == "public":
        return False
    with schema_context("public"):
        return Empresa.objects.filter(schema_name=schema_name).exists()


@shared_task(bind=True, name="clientes.notificar_mensagem_chat", max_retries=3, default_retry_delay=60, ignore_result=True)
def notificar_mensagem_chat(self, schema_name, mensagem_id):
    """Envia email aos restantes participantes e regista estado/tentativas no schema do tenant."""
    if not _validar_schema_tenant(schema_name):
        logger.error("Ignorada notificação de chat: schema inválido (%r).", schema_name)
        return {"estado": "schema_invalido", "mensagem_id": mensagem_id}

    with schema_context(schema_name):
        from apps.clientes.models import MensagemChat
        from apps.clientes.chat_notification_models import EntregaNotificacaoChat
        msg = MensagemChat.objects.select_related(
            "conversa", "conversa__cliente", "autor_usuario", "autor_cliente_site"
        ).filter(pk=mensagem_id).first()
        if msg is None:
            logger.warning("Mensagem de chat %s não existe no tenant %s.", mensagem_id, schema_name)
            return {"estado": "mensagem_inexistente", "mensagem_id": mensagem_id}

        agora = timezone.now()
        # Claim atómico: jobs duplicados do Beat/broker não enviam o mesmo aviso em paralelo.
        with transaction.atomic():
            entrega, _ = EntregaNotificacaoChat.objects.select_for_update().get_or_create(mensagem=msg)
            if entrega.estado in {"enviada", "sem_destinatario"}:
                return {"estado": entrega.estado, "mensagem_id": mensagem_id}
            if entrega.estado == "processando" and entrega.processamento_iniciado_em:
                em_curso = agora - entrega.processamento_iniciado_em < timedelta(minutes=15)
                if em_curso:
                    return {"estado": "ja_em_processamento", "mensagem_id": mensagem_id}
            entrega.estado = "processando"
            entrega.processamento_iniciado_em = agora
            entrega.tentativas += 1
            entrega.ultimo_erro = ""
            entrega.save(update_fields=["estado", "processamento_iniciado_em", "tentativas", "ultimo_erro", "updated_at"])

        conversa = msg.conversa
        emails = set()
        if conversa.tipo == "cliente":
            if msg.autor_cliente_site_id:
                qs = conversa.participantes.filter(usuario__isnull=False).select_related("usuario")
                for p in qs:
                    if p.usuario_id != msg.autor_usuario_id and p.usuario.email:
                        emails.add(p.usuario.email.strip())
            else:
                qs = conversa.participantes.filter(cliente_site__isnull=False).select_related("cliente_site")
                for p in qs:
                    email = (p.cliente_site.email or "").strip()
                    if email:
                        emails.add(email)
        else:
            qs = conversa.participantes.filter(usuario__isnull=False).select_related("usuario")
            for p in qs:
                if p.usuario_id != msg.autor_usuario_id and p.usuario.email:
                    emails.add(p.usuario.email.strip())

        destinatarios = sorted(e for e in emails if e and "@" in e)
        if not destinatarios:
            with transaction.atomic():
                entrega.estado = "sem_destinatario"
                entrega.destinatarios = []
                entrega.processamento_iniciado_em = None
                entrega.ultimo_erro = "Não foram encontrados participantes com email válido para notificar."
                entrega.save(update_fields=["estado", "destinatarios", "processamento_iniciado_em", "ultimo_erro", "updated_at"])
            return {"estado": "sem_destinatario", "mensagem_id": mensagem_id}

        autor = getattr(msg.autor_cliente_site, "nome", None) or (str(msg.autor_usuario) if msg.autor_usuario_id else "Utilizador")
        trecho = (msg.texto or "").strip()[:500] or "Foi enviado um anexo. Entre no portal para o consultar."
        assunto = f"Nova mensagem: {conversa.titulo or ('Conversa #' + str(conversa.pk))}"
        corpo = f"{autor} enviou uma mensagem.\n\n{trecho}\n\nEntre no VistoGest para consultar a conversa e responder."
        try:
            send_mail(
                subject=assunto, message=corpo,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=destinatarios, fail_silently=False,
            )
            with transaction.atomic():
                entrega.refresh_from_db()
                entrega.marcar_enviada(destinatarios)
            return {"estado": "enviada", "mensagem_id": mensagem_id, "destinatarios": len(destinatarios)}
        except Exception as exc:
            logger.exception("Falha de email para mensagem de chat %s no schema %s.", mensagem_id, schema_name)
            with transaction.atomic():
                entrega.refresh_from_db()
                entrega.estado = "erro"
                entrega.destinatarios = destinatarios
                entrega.processamento_iniciado_em = None
                entrega.ultimo_erro = str(exc)[:4000]
                entrega.save(update_fields=["estado", "destinatarios", "processamento_iniciado_em", "ultimo_erro", "updated_at"])
            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)
            return {"estado": "erro", "mensagem_id": mensagem_id}


@shared_task(name="clientes.reenfileirar_notificacoes_chat_global", ignore_result=True)
def reenfileirar_notificacoes_chat_global():
    """Recupera outbox pendente quando a fila estava indisponível no momento de envio."""
    from apps.empresas.models import Empresa
    agora = timezone.now()
    limite_stale = agora - timedelta(minutes=15)
    with schema_context("public"):
        schemas = list(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))

    agendadas = 0
    for schema_name in schemas:
        with schema_context(schema_name):
            from apps.clientes.chat_notification_models import EntregaNotificacaoChat
            qs = EntregaNotificacaoChat.objects.filter(estado="pendente").values_list("mensagem_id", flat=True)[:500]
            stale = EntregaNotificacaoChat.objects.filter(
                estado="processando", processamento_iniciado_em__lt=limite_stale
            ).values_list("mensagem_id", flat=True)[:500]
            ids = list(qs) + list(stale)
        for mensagem_id in set(ids):
            try:
                notificar_mensagem_chat.delay(schema_name, mensagem_id)
                agendadas += 1
            except Exception:
                logger.exception("Não foi possível recuperar o alerta de chat %s (%s).", mensagem_id, schema_name)
    return {"notificacoes_reenfileiradas": agendadas, "tenants_verificados": len(schemas)}
