# apps/vendas/tasks.py
"""
Alerta de margem crítica, por tenant.

O alerta de stock mínimo saiu daqui: vive em apps/estoque/tasks.py (AlertaEstoque).
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.empresas.services import schemas_dos_tenants

logger = logging.getLogger(__name__)

LIMITE_MARGEM_CRITICA = 0.10  # 10 %
DIAS_ANALISE = 7
_DINHEIRO = DecimalField(max_digits=16, decimal_places=2)


@shared_task(name="vendas.verificar_margem_critica_global", ignore_result=True)
def verificar_margem_critica_global():
    """Entrada do beat: uma task por tenant."""
    schemas = schemas_dos_tenants()
    for schema_name in schemas:
        verificar_margem_critica.delay(schema_name)
    return {"tenants": len(schemas)}


@shared_task(name="vendas.verificar_margem_critica")
def verificar_margem_critica(schema_name):
    """
    Produtos vendidos nos últimos DIAS_ANALISE dias com margem bruta abaixo do limite.
    Receita = subtotal sem IVA das linhas (já líquido de desconto); custo = quantidade * preco_custo.
    Serviços (sem produto) ficam de fora.
    """
    from apps.vendas.models import ItemVenda

    desde = timezone.now() - timedelta(days=DIAS_ANALISE)
    with schema_context(schema_name):
        linhas = (
            ItemVenda.objects
            .filter(venda__status="finalizada", venda__data_venda__gte=desde, produto__isnull=False)
            .values("produto_id", "produto__nome_produto")
            .annotate(
                receita=Sum("subtotal_sem_iva"),
                custo=Sum(ExpressionWrapper(F("quantidade") * F("produto__preco_custo"),
                                            output_field=_DINHEIRO)),
            )
            .filter(receita__gt=0)
        )
        criticos = []
        for linha in linhas:
            margem = float((linha["receita"] - linha["custo"]) / linha["receita"])
            if margem < LIMITE_MARGEM_CRITICA:
                criticos.append({
                    "produto_id": linha["produto_id"],
                    "produto": linha["produto__nome_produto"],
                    "margem_percentual": round(margem * 100, 2),
                })

    if criticos:
        logger.warning("[%s] %d produto(s) com margem abaixo de %d%% nos últimos %d dias.",
                       schema_name, len(criticos), LIMITE_MARGEM_CRITICA * 100, DIAS_ANALISE)
    return {"schema": schema_name, "criticos": criticos}