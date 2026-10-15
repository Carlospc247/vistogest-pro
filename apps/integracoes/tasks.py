# apps/integracoes/tasks.py
import logging

from celery import shared_task

logger = logging.getLogger('integracoes')


@shared_task(
    name='integracoes.processar_webhook',
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def processar_webhook_task(self, webhook_id, schema_name=None):
    """
    Processa um webhook de forma assíncrona.
    """

    try:
        from apps.integracoes.models import WebhookIntegracao
        from apps.integracoes.services.webhooks import processar

        # Em instalações multi-tenant, a consulta deve ocorrer
        # dentro do schema correto.
        if schema_name:
            from django_tenants.utils import schema_context

            with schema_context(schema_name):
                webhook = WebhookIntegracao.objects.get(pk=webhook_id)
                processar(webhook)
        else:
            webhook = WebhookIntegracao.objects.get(pk=webhook_id)
            processar(webhook)

    except Exception as exc:
        logger.exception(
            "Erro na task de processamento do webhook %s",
            webhook_id,
        )
        raise self.retry(exc=exc)