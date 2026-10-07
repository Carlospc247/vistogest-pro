# apps/funcionarios/signals.py
import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_tenants.models import TenantMixin
from django_tenants.signals import post_schema_sync
from django_tenants.utils import get_public_schema_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Funcionário inativo/demitido  ->  desativa o utilizador (core.Usuario, public)
# ---------------------------------------------------------------------------
@receiver(post_save, sender="funcionarios.Funcionario",
          dispatch_uid="funcionarios_sincronizar_status_usuario")
def sincronizar_status_usuario(sender, instance, **kwargs):
    if kwargs.get("raw") or not instance.usuario_id:
        return

    # Evita trabalho em saves parciais que não tocam no estado do funcionário
    update_fields = kwargs.get("update_fields")
    if update_fields and not {"ativo", "data_demissao"} & set(update_fields):
        return

    if instance.ativo and not instance.data_demissao:
        return

    # update() não dispara sinais nem save(); só desativa, nunca reativa
    get_user_model().objects.filter(
        pk=instance.usuario_id, is_active=True
    ).update(is_active=False)


# ---------------------------------------------------------------------------
# Nova empresa (schema criado)  ->  cargos e departamentos padrão
# ---------------------------------------------------------------------------
@receiver(post_schema_sync, sender=TenantMixin,
          dispatch_uid="funcionarios_provisionar_padroes_novo_tenant")
def provisionar_padroes_no_novo_tenant(sender, tenant, **kwargs):
    from .cargos_padrao import aplicar_no_schema as aplicar_cargos
    from .departamentos_padrao import aplicar_no_schema as aplicar_departamentos

    schema = getattr(tenant, "schema_name", None)
    if not schema or schema == get_public_schema_name():
        return

    # Cada um isolado: nunca bloquear a criação da empresa.
    # Corrigir depois com: manage.py criar_cargos_padrao / setup_departamento --schema <nome>
    for nome, aplicar in (("cargos", aplicar_cargos), ("departamentos", aplicar_departamentos)):
        try:
            aplicar(schema)
        except Exception:
            logger.exception("Falha ao criar %s padrão no tenant %s", nome, schema)