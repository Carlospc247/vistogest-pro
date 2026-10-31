# vistogest-pro/config/tasks_celery.py
"""Celery app configuration, independent of the cloud provider.

Production must set DJANGO_SETTINGS_MODULE explicitly to the production settings module.
"""
import os
import ssl
from urllib.parse import urlparse

from celery import Celery
from celery.schedules import crontab

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


# ──────────────────────────────────────────────────────────────────────────────
# Agendamento (beat)
# ──────────────────────────────────────────────────────────────────────────────
def _agendar(nome, task, schedule, **options):
    """
    Regista a entrada no beat SÓ se nenhuma entrada existente (por exemplo em
    CELERY_BEAT_SCHEDULE nos settings) já agenda a mesma task. Evita duplicados.
    """
    atual = dict(app.conf.beat_schedule or {})
    if any(entrada.get("task") == task for entrada in atual.values()):
        return
    entrada = {"task": task, "schedule": schedule}
    if options:
        entrada["options"] = options
    atual[nome] = entrada
    app.conf.beat_schedule = atual


# Serviços: descobre notificações novas e enfileira as vencidas.
_agendar("servicos-processar-notificacoes", "servicos.processar_notificacoes_global",
         60.0, expires=55)

# Configurações: verificação horária; a própria task decide quais tenants estão "due".
_agendar("configuracoes-backup-automatico", "configuracoes.backup_automatico_diario",
         crontab(minute=5), expires=3300)

# Clientes: recupera o outbox de notificações de chat que ficou pendente.
_agendar("clientes-reenfileirar-chat", "clientes.reenfileirar_notificacoes_chat_global",
         300.0, expires=280)

# Estoque: alertas de stock mínimo/zerado e de validade (substitui produtos/tasks.py).
_agendar("estoque-alertas", "estoque.gerar_alertas_global",
         crontab(minute=15), expires=3000)

# Vendas: margem crítica, uma vez por dia.
_agendar("vendas-margem-critica", "vendas.verificar_margem_critica_global",
         crontab(hour=7, minute=0))

# Fiscal (AGT)
_agendar("fiscal-sincronizar-series", "fiscal.sincronizar_series_agt_global",
         crontab(hour=2, minute=0))
_agendar("fiscal-polling-varredura", "fiscal.polling_global_agt",
         crontab(minute=20), expires=3000)

# Parceiros
_agendar("parceiros-expirar-licencas", "parceiros.expirar_licencas_global",
         crontab(hour=0, minute=30))

_agendar(
    "fiscal-payload-reconciliacao", "fiscal.reconciliar_payloads_agt_global",
         crontab(minute=35),)

# Relatórios (as tasks não têm name=; confirma com `inspect registered`).
# executar_agendamentos_relatorios compara hora:minuto exactos: tem de correr de minuto a minuto.
_agendar("relatorios-agendamentos", "apps.relatorios.tasks.executar_agendamentos_relatorios",
         60.0, expires=55)
_agendar("relatorios-kpis", "apps.relatorios.tasks.gerar_kpis_automaticos",
         crontab(hour=23, minute=55))
_agendar("relatorios-alertas", "apps.relatorios.tasks.detectar_alertas_task",
         crontab(minute=40))
_agendar("relatorios-limpeza", "apps.relatorios.tasks.limpar_relatorios_antigos",
         crontab(hour=3, minute=30))

# NÃO agendar: relatorios.gerar_relatorio_mensal (repete executar_agendamentos_relatorios).


# ──────────────────────────────────────────────────────────────────────────────
# Tasks globais (percorrem todos os tenants)
# ──────────────────────────────────────────────────────────────────────────────
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
                status="confirmed",
                metadados__has_key="request_id_agt",
            ).exclude(
                metadados__has_key="polling_max_retries"
            ).exclude(
                metadados__estado_agt="rejeitado"
            )
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