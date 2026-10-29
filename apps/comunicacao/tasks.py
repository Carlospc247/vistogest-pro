# apps/comunicacao/tasks.py
"""Asynchronous email alerts for chat messages."""
import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


@shared_task(name="comunicacao.notificar_mensagem_chat", ignore_result=True)
def notificar_mensagem_chat(schema_name, mensagem_id):
    from apps.comunicacao.models import MensagemChat
    with schema_context(schema_name):
        msg = MensagemChat.objects.select_related(
            "conversa", "conversa__cliente", "autor_usuario", "autor_cliente_site"
        ).filter(pk=mensagem_id).first()
        if not msg:
            return {"status": "ignorada", "mensagem": mensagem_id}
        conversa = msg.conversa
        autor_user_id = msg.autor_usuario_id
        autor_cliente_id = msg.autor_cliente_site_id
        destinatarios = set()
        if conversa.tipo == "cliente":
            if autor_cliente_id:
                # Customer wrote: notify only participating staff users.
                destinatarios.update(
                    conversa.participantes.filter(usuario__isnull=False)
                    .exclude(usuario_id=autor_user_id).values_list("usuario__email", flat=True)
                )
            else:
                # Staff wrote: notify the linked customer account.
                destinatarios.add(getattr(conversa.cliente, "email", ""))
        else:
            destinatarios.update(
                conversa.participantes.filter(usuario__isnull=False)
                .exclude(usuario_id=autor_user_id).values_list("usuario__email", flat=True)
            )
        destinatarios = sorted({e.strip() for e in destinatarios if e and e.strip()})
        if not destinatarios:
            return {"status": "sem_destinatarios", "mensagem": mensagem_id}
        autor = (getattr(msg.autor_cliente_site, "nome", None) or
                 (str(msg.autor_usuario) if msg.autor_usuario else "Utilizador"))
        excerpt = msg.texto[:500] or "Foi enviado um anexo."
        try:
            send_mail(
                subject=f"Nova mensagem: {conversa.titulo or 'Conversa'}",
                message=f"{autor} enviou uma mensagem.\n\n{excerpt}\n\nAbra o portal para responder.",
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=destinatarios,
                fail_silently=False,
            )
            return {"status": "enviada", "mensagem": mensagem_id, "destinatarios": len(destinatarios)}
        except Exception:
            logger.exception("Falha no alerta da mensagem %s", mensagem_id)
            return {"status": "erro", "mensagem": mensagem_id}
