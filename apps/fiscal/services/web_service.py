# apps/fiscal/services/web_service.py
#############################################
# WEBSERVICE
#############################################
import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

import logging

from apps.fiscal.services.serie_fiscal_service import SerieFiscalService

logger = logging.getLogger(__name__)


class AGTWebService:
    """Verificação real da API AGT através do serviço assinado listarSeries."""

    def __init__(self):
        self.last_result = None

    def check_status(self):
        # Sem mocks, sem endpoint /health não documentado e sem cache que
        # possa apresentar como actual uma resposta de uma tentativa anterior.
        series = SerieFiscalService().sincronizar_series()
        self.last_result = {
            "ok": True,
            "operation": "listarSeries",
            "series_count": len(series),
        }
        return True
