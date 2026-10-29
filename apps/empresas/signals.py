# apps/empresas/signals.py
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_tenants.signals import post_schema_sync

from .models import Empresa

logger = logging.getLogger(__name__)


def _sincronizar(empresa):
    from apps.configuracoes.services.identidade import sincronizar_identidade

    try:
        sincronizar_identidade(empresa)
    except Exception:
        # Não bloqueia o save da Empresa; fica no log e obter_config_fiscal()
        # repõe o espelho na próxima leitura.
        logger.exception("Falha a sincronizar identidade (schema=%s)", empresa.schema_name)


@receiver(post_save, sender=Empresa)
def ao_guardar_empresa(sender, instance, created, raw=False, **kwargs):
    # Na criação o schema ainda não existe: quem sincroniza é post_schema_sync.
    if not (created or raw):
        transaction.on_commit(lambda: _sincronizar(instance))


@receiver(post_schema_sync)
def ao_criar_schema(sender, tenant, **kwargs):
    if isinstance(tenant, Empresa):
        _sincronizar(tenant)