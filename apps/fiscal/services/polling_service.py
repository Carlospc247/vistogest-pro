# apps/fiscal/services/polling_service.py
import logging
import requests
from django.conf import settings
from django.utils import timezone
from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, AssinaturaSoftwareService
from apps.fiscal.utility.crypto import AESService

logger = logging.getLogger("fiscal")


class FiscalPollingService:
    """Consulta de estado assíncrono na AGT (obterEstado) no schema tenant corrente."""

    def __init__(self):
        if settings.AGT_ENVIRONMENT == "PRODUCTION":
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
        if not config.api_username or not config.api_password:
            logger.error("Polling AGT abortado: credenciais Basic Auth não configuradas.")
            return None

        payload = {
            "schemaVersion": "1.0",
            "taxRegistrationNumber": config.nif_contribuinte,
            "requestID": request_id,
            "submissionTimeStamp": timezone.now().isoformat(),
            "softwareInfo": AssinaturaSoftwareService.montar_software_info(),
        }
        payload_assinatura = {
            "taxRegistrationNumber": config.nif_contribuinte,
            "requestID": request_id,
        }
        payload["jwsSignature"] = AssinaturaDigitalService.assinar_requisicao(payload_assinatura)

        try:
            password = AESService.decrypt(config.api_password)
            response = requests.post(
                self.url,
                json=payload,
                auth=(config.api_username, password),
                timeout=30,
            )
            if response.status_code == 200:
                return self._processar_resposta_agt(response.json(), request_id)
            logger.error("Erro API AGT Polling [%s]: %s", response.status_code, response.text[:500])
            return False
        except requests.exceptions.RequestException as exc:
            logger.exception("Falha de rede na conexão com AGT (Polling): %s", exc)
            return False
        except Exception as exc:
            logger.exception("Falha ao preparar ou processar polling AGT: %s", exc)
            return False

    def _processar_resposta_agt(self, data, request_id):
        result_code = str(data.get("resultCode"))
        if result_code == "8":
            return "PROCESSING"

        for doc_status in data.get("documentStatusList", []):
            doc_no = doc_status.get("documentNo")
            status_agt = doc_status.get("documentStatus")  # V | I | P
            try:
                doc_fiscal = DocumentoFiscal.objects.get(numero_documento=doc_no)
                if status_agt in ("V", "P"):
                    doc_fiscal.status = "posted"
                    if not isinstance(doc_fiscal.metadados, dict):
                        doc_fiscal.metadados = {}
                    doc_fiscal.metadados["validacao_agt"] = data
                    logger.info("Documento %s validado pela AGT (status=%s).", doc_no, status_agt)
                else:
                    doc_fiscal.status = "cancelled"
                    if not isinstance(doc_fiscal.metadados, dict):
                        doc_fiscal.metadados = {}
                    doc_fiscal.metadados["erros_agt"] = doc_status.get("errorList", [])
                doc_fiscal.save()
            except DocumentoFiscal.DoesNotExist:
                logger.warning(
                    "Documento %s (RequestID %s) retornado pela AGT mas inexistente localmente.",
                    doc_no, request_id,
                )
        return "FINISHED"
