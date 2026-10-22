# apps/servicos/tracking_services.py
"""Small service layer for recording service events from any existing view."""
import logging

from django.db import connection, transaction

from apps.servicos.tracking_models import EventoAgendamento

logger = logging.getLogger(__name__)


def registar_evento_agendamento(
    agendamento,
    tipo,
    titulo,
    descricao="",
    *,
    autor_usuario=None,
    autor_cliente_site=None,
    visivel_cliente=True,
    anexo=None,
    schema_name=None,
):
    """Persist an event and enqueue its email only after the transaction commits."""
    evento = EventoAgendamento.objects.create(
        agendamento=agendamento,
        tipo=tipo,
        titulo=titulo,
        descricao=descricao,
        autor_usuario=autor_usuario,
        autor_cliente_site=autor_cliente_site,
        visivel_cliente=visivel_cliente,
        anexo=anexo,
    )
    if visivel_cliente:
        schema = schema_name or connection.schema_name

        def enfileirar():
            try:
                from apps.servicos.tasks import notificar_evento_agendamento
                notificar_evento_agendamento.delay(schema, evento.pk)
            except Exception:
                # Keep the persisted timeline even when the broker is offline.
                logger.exception("Evento %s gravado, mas não foi possível enfileirar a notificação.", evento.pk)

        transaction.on_commit(enfileirar)
    return evento
