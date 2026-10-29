# apps/estoque/tasks.py
"""
Alertas de stock e de validade, por tenant.

Substitui apps/produtos/tasks.py (não era uma task e usava o FK `empresa`) e
verificar_stock_critico de apps/vendas/tasks.py (corria no schema public).
O único sítio onde os alertas vivem é AlertaEstoque.
"""
from celery import shared_task
from django_tenants.utils import schema_context

from apps.empresas.services import schemas_dos_tenants


@shared_task(name="estoque.gerar_alertas_global", ignore_result=True)
def gerar_alertas_global():
    """Entrada do beat: uma task por tenant, para que um não afecte os outros."""
    schemas = schemas_dos_tenants()
    for schema_name in schemas:
        gerar_alertas.delay(schema_name)
    return {"tenants": len(schemas)}


@shared_task(name="estoque.gerar_alertas")
def gerar_alertas(schema_name):
    from apps.estoque.models import AlertaEstoque

    with schema_context(schema_name):
        resultado = AlertaEstoque.gerar_alertas_automaticos()
    return {"schema": schema_name, **resultado}