# vistogest-pro/config/tasks_celery.py
import ssl
import os
from celery import Celery
from django.conf import settings

# RIGOR: Em produção, o Render define essa variável automaticamente. 
# Se não estiver definida, ele usa development.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("config")

# Configurações prefixadas com CELERY_ no settings.py
app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# --- RIGOR SOTARQ: TRATAMENTO DE SSL DINÂMICO ---
# O Render exige SSL. O seu PC provavelmente não.
if os.environ.get('RENDER'): 
    app.conf.broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }
    app.conf.redis_backend_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_REQUIRED,
    }
else:
    # Localmente (Windows), desativamos para não dar erro de conexão
    app.conf.broker_use_ssl = False
    app.conf.redis_backend_use_ssl = False


# ─────────────────────────────────────────────────────────────────────────────
# Tasks globais (percorrem todos os tenants activos)
# Registadas aqui porque o Celery Beat precisa de tasks no módulo raiz da app.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(name='fiscal.polling_global_agt')
def polling_global_agt():
    """
    Percorre todos os tenants activos e, para cada DocumentoFiscal
    'confirmed' com requestID pendente, agenda polling individual.
    Fallback para documentos que não foram agendados individualmente.
    """
    from apps.empresas.models import Empresa
    from django_tenants.utils import schema_context

    tenants = Empresa.objects.exclude(schema_name='public')
    total = 0
    for tenant in tenants:
        with schema_context(tenant.schema_name):
            from apps.fiscal.models import DocumentoFiscal
            from apps.fiscal.tasks import polling_estado_agt
            docs = DocumentoFiscal.objects.filter(
                status='confirmed',
                metadados__has_key='request_id_agt',
            ).exclude(
                metadados__has_key='polling_max_retries',
            )
            for doc in docs:
                polling_estado_agt.delay(tenant.schema_name, doc.pk)
                total += 1
    return {'total_agendados': total}


@app.task(name='fiscal.sincronizar_series_agt_global')
def sincronizar_series_agt_global():
    """
    Percorre todos os tenants activos e sincroniza as séries com a AGT.
    Deve correr uma vez por dia (configurado no CELERY_BEAT_SCHEDULE).
    """
    from apps.empresas.models import Empresa
    from apps.fiscal.tasks import sincronizar_series_agt

    tenants = Empresa.objects.exclude(schema_name='public')
    for tenant in tenants:
        sincronizar_series_agt.delay(tenant.schema_name)
    return {'tenants': tenants.count()}


# ─────────────────────────────────────────────────────────────────────────────
# Task global de expiração de licenças de parceiros
# Corre diariamente via CELERY_BEAT_SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@app.task(name='parceiros.expirar_licencas_global')
def expirar_licencas_parceiros_global():
    """
    Verifica e expira licenças de parceiros cuja data_expiracao < hoje.
    Cria notificação automática para cada parceiro afectado.
    Corre no schema public (parceiros é SHARED_APP).
    """
    from apps.parceiros.services import PartnerService
    count = PartnerService.expirar_licencas_vencidas()
    return {'licencas_expiradas': count}
