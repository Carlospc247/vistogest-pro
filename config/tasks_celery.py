# vistogest-pro/config/tasks_celery.py
"""Celery app configuration, independent of the cloud provider.

Keep/merge the existing global AGT and partner tasks below this configuration.
Production must set DJANGO_SETTINGS_MODULE explicitly to the production settings module.
"""
import os
import ssl
from urllib.parse import urlparse

from celery import Celery

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.development"),
)

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def _configure_tls_from_url(url, *, backend=False):
    """Enable certificate validation only for TLS URLs; do not identify providers by name."""
    if not url:
        return
    if urlparse(url).scheme == "rediss":
        options = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
        if backend:
            app.conf.redis_backend_use_ssl = options
        else:
            app.conf.broker_use_ssl = options


_configure_tls_from_url(app.conf.broker_url)
_configure_tls_from_url(app.conf.result_backend, backend=True)

# Periodically discover newly-created notifications and enqueue due messages.
# Existing schedules are preserved.
_schedule = dict(app.conf.beat_schedule or {})
_schedule["servicos-processar-notificacoes"] = {
    "task": "servicos.processar_notificacoes_global",
    "schedule": 60.0,
    "options": {"expires": 55},
}
app.conf.beat_schedule = _schedule

# Preserve the existing global tasks from the supplied config/tasks_celery.py.
@app.task(name="fiscal.polling_global_agt")
def polling_global_agt():
    from apps.empresas.models import Empresa
    from django_tenants.utils import schema_context

    with schema_context("public"):
        tenants = list(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))

    total = 0
    for schema_name in tenants:
        with schema_context(schema_name):
            from apps.fiscal.models import DocumentoFiscal
            from apps.fiscal.tasks import polling_estado_agt
            docs = DocumentoFiscal.objects.filter(
                status="confirmed", metadados__has_key="request_id_agt"
            ).exclude(metadados__has_key="polling_max_retries")
            for doc in docs:
                polling_estado_agt.delay(schema_name, doc.pk)
                total += 1
    return {"total_agendados": total}


@app.task(name="fiscal.sincronizar_series_agt_global")
def sincronizar_series_agt_global():
    from apps.empresas.models import Empresa
    from django_tenants.utils import schema_context

    with schema_context("public"):
        schemas = list(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))
    from apps.fiscal.tasks import sincronizar_series_agt
    for schema_name in schemas:
        sincronizar_series_agt.delay(schema_name)
    return {"tenants": len(schemas)}


@app.task(name="parceiros.expirar_licencas_global")
def expirar_licencas_parceiros_global():
    from django_tenants.utils import schema_context
    from apps.parceiros.services import PartnerService
    with schema_context("public"):
        count = PartnerService.expirar_licencas_vencidas()
    return {"licencas_expiradas": count}
