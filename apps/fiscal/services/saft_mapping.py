# apps/fiscal/services/saft_mapping.py (novo ficheiro)
"""
Tradução entre o código interno de retenção (9 códigos, Decreto Executivo
683/25, usado na API de facturação electrónica) e o código aceite pelo
XSD do SAF-T AO 1.01_01 (7 códigos, WithholdingTaxType). Usar SEMPRE que
se serializar para XML — nunca escrever o código interno directamente.
"""

from .utils import FiscalServiceError

SAFT_WITHHOLDING_TAX_TYPE_MAP = {
    'IRT': 'IRT',
    'II': 'II',
    'IS': 'IS',
    'IVA': 'IVA',
    'IP': 'IPU',
    'IAC': 'IAC',
    'OU': 'OU',
    # IRPC / IRPS deliberadamente ausentes — ver mapear_withholding_tax_saft().
}


def mapear_withholding_tax_saft(tipo_retencao: str) -> str:
    codigo_saft = SAFT_WITHHOLDING_TAX_TYPE_MAP.get(tipo_retencao)
    if codigo_saft is None:
        raise FiscalServiceError(
            f"O código de retenção '{tipo_retencao}' ainda não é reconhecido pelo "
            f"schema SAF-T AO 1.01_01 (WithholdingTaxType). Não incluir esta "
            f"retenção na exportação SAF-T até a AGT actualizar o schema."
        )
    return codigo_saft