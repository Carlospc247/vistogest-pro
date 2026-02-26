# apps/saft/services/retencao_service.py

from typing import List, Dict
from apps.fiscal.models import RetencaoFonte
from apps.empresas.models import Empresa 
from datetime import datetime

class SaftRetencaoService:
    """
    Serviço para extrair e formatar o bloco <WithholdingTax> para o SAF-T (AO).
    """
    
    def __init__(self, empresa: Empresa):
        self.empresa = empresa

    def get_withholding_tax_entries(self, data_inicio: datetime, data_fim: datetime) -> List[Dict]:
        """
        Busca todos os registos de Retenção na Fonte dentro do período especificado.
        """
        # 1. Buscar Retenções confirmadas (retidas) no período
        retenções = RetencaoFonte.objects.filter(
            empresa=self.empresa,
            data_retencao__range=[data_inicio.date(), data_fim.date()]
        ).select_related('fornecedor', 'conta_pagar') # Otimização de queries

        saft_entries = []
        for retenção in retenções:
            
            # O SAF-T exige 1 registro por documento, mesmo que haja múltiplos impostos retidos.
            # Aqui, estamos a mapear 1 RetencaoFonte = 1 Linha no SAF-T.
            
            # 2. Mapeamento dos campos SAF-T
            saft_entries.append({
                # Code: Código do imposto retido (IRPC, IRT, etc.)
                'WithholdingTaxCode': retenção.tipo_retencao, 
                
                # WithholdingTaxDescription: Descrição (ex: Imposto sobre Rendimento)
                'WithholdingTaxDescription': retenção.get_tipo_retencao_display(), 
                
                # TaxableBase: Base tributável sobre a qual o imposto foi calculado
                'TaxableBase': float(retenção.valor_base),
                
                # WithholdingTaxRate: Taxa de retenção em percentagem
                'WithholdingTaxRate': float(retenção.taxa_retencao), 
                
                # WithholdingTaxAmount: Valor do imposto retido
                'WithholdingTaxAmount': float(retenção.valor_retido),
                
                # WithholdingTaxType: Tipo de Rendimento (ex: 'Rendimento de Capital', 'Serviços') - Requer mapeamento!
                'WithholdingTaxType': 'Services', # 🚨 NECESSITA DE AJUSTE CONFORME O SEU TIPO_RETENCAO
                
                # SourceDocumentID: Documento que originou a retenção (ex: Fatura do Fornecedor)
                'SourceDocumentID': retenção.referencia_documento,
            })

        return saft_entries

