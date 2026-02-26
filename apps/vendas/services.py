#apps/vendas/services.py

from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from apps.fiscal.utility import gerar_atcud_documento, gerar_hash_anterior
from apps.vendas.models import FormaPagamento, Venda, ItemVenda
from apps.fiscal.services.utils import DocumentoFiscalService
from django.core.exceptions import ValidationError

def validar_itens_por_regime(empresa, itens_data):
    """
    Valida se os itens enviados no POST (produto ou serviço) 
    são permitidos pelo regime da empresa.
    """
    regime = empresa.regime_empresa
    
    for item in itens_data:
        has_produto = 'produto_id' in item or item.get('produto')
        has_servico = 'servico_id' in item or item.get('servico')

        if regime == 'COMERCIO' and has_servico:
            raise ValidationError(f"A empresa opera apenas em regime de COMÉRCIO. O serviço '{item.get('nome_item')}' não é permitido.")
        
        if regime == 'SERVICOS' and has_produto:
            raise ValidationError(f"A empresa opera apenas em regime de SERVIÇOS. O produto '{item.get('nome_item')}' não é permitido.")
        
        # No regime MISTO, ambos são permitidos, então não lançamos erro.
    return True


