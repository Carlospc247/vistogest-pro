#apps/vendas/services.py

from django.db import connection, transaction
from django.utils import timezone
from decimal import Decimal
from apps.fiscal.utility import gerar_atcud_documento, gerar_hash_anterior
from apps.vendas.models import FormaPagamento, Venda, ItemVenda
from django.core.exceptions import ValidationError




def validar_itens_por_regime(itens_data):
    """
    Valida os produtos e serviços permitidos pelo regime de actividade
    do tenant actual, sem depender de uma FK para Empresa.
    """
    tenant = getattr(connection, 'tenant', None)

    if (
        tenant is None
        or getattr(tenant, 'schema_name', 'public') == 'public'
    ):
        raise ValidationError(
            'Não foi possível determinar a empresa do tenant actual.'
        )

    regime = getattr(tenant, 'regime', None)

    if regime not in {'COMERCIO', 'SERVICOS', 'MISTO'}:
        raise ValidationError(
            'O tipo de actividade da empresa não está configurado correctamente.'
        )

    for item in itens_data:
        # Uma chave existente com valor None não significa que há um item.
        has_produto = bool(
            item.get('produto_id') or item.get('produto')
        )
        has_servico = bool(
            item.get('servico_id') or item.get('servico')
        )

        # Cada linha deve representar exactamente um tipo de item.
        if has_produto == has_servico:
            raise ValidationError(
                'Cada item deve conter exactamente um produto ou um serviço.'
            )

        if regime == 'COMERCIO' and has_servico:
            raise ValidationError(
                f"A empresa opera apenas em COMÉRCIO. "
                f"O serviço '{item.get('nome_item', '')}' não é permitido."
            )

        if regime == 'SERVICOS' and has_produto:
            raise ValidationError(
                f"A empresa opera apenas em SERVIÇOS. "
                f"O produto '{item.get('nome_item', '')}' não é permitido."
            )

    return True

