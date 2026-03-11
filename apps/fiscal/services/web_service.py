
#############################################
# WEBSERVICE
#############################################
import requests
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class AGTWebService:
    """
    ENGINEER_SOTARQ: Middleware de comunicação com a AGT.
    Implementa segurança, timeout e cache para não travar o Tenant.
    """
    def __init__(self):
        # Em DEBUG, usamos um Mock para o sistema não parar
        self.is_debug = getattr(settings, 'DEBUG', True)
        self.base_url = "https://sandbox.agt.minfin.gov.ao/api/v1"
        self.timeout = 5 # Rigor: Nunca esperar mais de 5s pelo governo

    def check_status(self):
        """Verifica se o portal da AGT está operante."""
        cache_key = 'agt_status_online'
        status = cache.get(cache_key)
        
        if status is not None:
            return status

        if self.is_debug:
            # Simulação de Rigor para Desenvolvimento
            import random
            is_online = random.choice([True, True, True, False]) # 75% chance online
        else:
            try:
                response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
                is_online = response.status_code == 200
            except Exception as e:
                logger.error(f"Erro de conexão AGT: {e}")
                is_online = False

        cache.set(cache_key, is_online, 60) # Cache de 1 minuto
        return is_online
    