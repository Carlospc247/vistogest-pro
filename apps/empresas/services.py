# apps/empresas/services.py
"""
Ponto ÚNICO para obter a Empresa (public) correspondente ao schema activo.

Usado por: configuracoes.services.identidade, fiscal.AssinaturaDigital e,
na fase seguinte, por DocumentoFiscal/SAFTExport (NIF do ATCUD) quando o
campo `empresa` for removido.
"""
from django.core.exceptions import ValidationError
from django.db import connection
from django_tenants.utils import get_public_schema_name, schema_context

from .models import Empresa


def schemas_dos_tenants() -> list:
    """Schemas das empresas activas, sem o public. É o que as tasks globais percorrem."""
    with schema_context(get_public_schema_name()):
        return list(
            Empresa.objects.filter(ativa=True)
            .exclude(schema_name=get_public_schema_name())
            .order_by("schema_name")
            .values_list("schema_name", flat=True)
        )


def obter_empresa_do_schema(schema=None) -> Empresa:
    schema = schema or connection.schema_name
    if schema == get_public_schema_name():
        raise ValidationError("Operação válida apenas no schema de um tenant.")

    # Num pedido normal o middleware já carregou a Empresa: zero queries.
    tenant = getattr(connection, "tenant", None)
    if isinstance(tenant, Empresa) and tenant.schema_name == schema:
        return tenant

    # Dentro de schema_context() (Celery, comandos) o tenant é um FakeTenant.
    try:
        with schema_context(get_public_schema_name()):
            return Empresa.objects.get(schema_name=schema)
    except Empresa.DoesNotExist:
        raise ValidationError(f"Não existe Empresa para o schema '{schema}'.") from None