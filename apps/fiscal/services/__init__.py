# apps/fiscal/services/__init__.py
"""API pública dos serviços fiscais.

Importações locais atrasadas evitam ciclos quando os modelos usam estes serviços
dentro de métodos save()/gerar_documento_fiscal().
"""

from apps.fiscal.services.documento_fiscal_service import DocumentoFiscalService
from .utils import FiscalServiceError, gerar_numero_documento

__all__ = ["DocumentoFiscalService", "FiscalServiceError", "gerar_numero_documento"]
