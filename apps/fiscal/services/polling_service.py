# apps/fiscal/services/polling_service.py
import requests
import logging
from django.conf import settings
from django.utils import timezone
from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, AssinaturaSoftwareService

logger = logging.getLogger('fiscal')

class FiscalPollingService:
    """
    Serviço de consulta de estado assíncrono na AGT (obterEstado).
    Isolamento físico: nenhuma referência a `empresa` — o schema activo já
    identifica o tenant. Credenciais Basic Auth vêm de AssinaturaDigital.
    """

    def __init__(self):
        if settings.AGT_ENVIRONMENT == 'PRODUCTION':
            self.url = f"{settings.AGT_BASE_URL_PRODUCAO}/obterEstado"
        else:
            self.url = f"{settings.AGT_BASE_URL_HOMOLOGACAO}/obterEstado"

    def consultar_estado_documento(self, request_id):
        from apps.fiscal.models import AssinaturaDigital

        if not request_id:
            logger.error("Tentativa de polling sem RequestID.")
            return None

        config = AssinaturaDigital.obter_configuracao()
        if not config or not config.esta_configurada:
            logger.error("Polling AGT abortado: chave do contribuinte não configurada.")
            return None

        payload = {
            "schemaVersion": "1.0",
            "taxRegistrationNumber": config.nif_contribuinte,
            "requestID": request_id,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
        }

        # jwsSignature: assina taxRegistrationNumber + requestID (Anexo I)
        payload_assinatura = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "requestID": request_id
        }
        payload["jwsSignature"] = AssinaturaDigitalService.assinar_requisicao(payload_assinatura)

        try:
            response = requests.post(
                self.url,
                json=payload,
                auth=(config.api_username, config.api_password),  # TODO: decifrar api_password via AESService antes de usar
                timeout=30
            )
            if response.status_code == 200:
                return self._processar_resposta_agt(response.json(), request_id)
            logger.error(f"Erro API AGT Polling [{response.status_code}]: {response.text}")
            return False
        except requests.exceptions.RequestException as e:
            logger.exception(f"Falha de rede na conexão com AGT (Polling): {e}")
            return False

    def _processar_resposta_agt(self, data, request_id):
        result_code = str(data.get('resultCode'))
        if result_code == "8":
            return "PROCESSING"

        for doc_status in data.get('documentStatusList', []):
            doc_no = doc_status.get('documentNo')
            status_agt = doc_status.get('documentStatus')  # V | I | P
            try:
                doc_fiscal = DocumentoFiscal.objects.get(numero_documento=doc_no)
                if status_agt in ('V', 'P'):
                    doc_fiscal.status = 'posted'
                    doc_fiscal.metadados['validacao_agt'] = data
                    logger.info(f"Documento {doc_no} validado pela AGT (status={status_agt}).")
                else:
                    doc_fiscal.status = 'cancelled'
                    doc_fiscal.metadados['erros_agt'] = doc_status.get('errorList', [])
                doc_fiscal.save()
            except DocumentoFiscal.DoesNotExist:
                logger.warning(f"Documento {doc_no} (RequestID {request_id}) retornado pela AGT mas inexistente localmente.")

        return "FINISHED"