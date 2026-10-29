# apps/fiscal/services/polling_service.py
"""
Consulta do estado assíncrono na AGT (obterEstado) no schema do tenant activo.

A comunicação HTTP está no AGTClient. Este serviço só interpreta a resposta e
actualiza o DocumentoFiscal.

Regras de actualização (documentStatus devolvido pela AGT):
  V / P  (validado)  -> status 'posted' SE o documento ainda está 'confirmed'.
                        Nunca sobrescreve 'paid', 'cancelled' ou 'rectified'.
  restantes (I, ...) -> o documento NÃO passa a 'cancelled'. Anulação é um acto
                        fiscal do emitente, não uma rejeição da AGT. Regista-se
                        em metadados: estado_agt='rejeitado' + erros_agt, para
                        o utilizador corrigir e re-emitir/rectificar.

Retorno (compatível com a versão anterior):
  None          -> chamada inválida / tenant sem configuração
  False         -> falha de comunicação ou erro da AGT (ver logs)
  "PROCESSING"  -> a AGT ainda está a processar (resultCode 8)
  "FINISHED"    -> resposta processada
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services.agt_client import AGTClient, AGTError
from .utils import FiscalServiceError

logger = logging.getLogger("fiscal")

ESTADOS_VALIDADOS = {"V", "P"}


class FiscalPollingService:
    def __init__(self, client: AGTClient = None):
        self.client = client or AGTClient()

    def consultar_estado_documento(self, request_id):
        if not request_id:
            logger.error("Tentativa de polling sem RequestID.")
            return None
        try:
            data = self.client.obter_estado(request_id)
        except AGTError as exc:
            logger.error("Polling AGT falhou (requestID=%s): %s", request_id, exc)
            return False
        except FiscalServiceError as exc:
            logger.error("Polling AGT abortado: %s", exc)
            return None
        except Exception:
            logger.exception("Falha inesperada no polling AGT (requestID=%s).", request_id)
            return False
        return self._processar_resposta_agt(data, request_id)

    def _processar_resposta_agt(self, data, request_id):
        if str(data.get("resultCode")) == "8":
            return "PROCESSING"

        for item in data.get("documentStatusList", []) or []:
            numero = item.get("documentNo")
            estado = item.get("documentStatus")
            if not numero:
                continue
            with transaction.atomic():
                doc = (DocumentoFiscal.objects.select_for_update()
                       .filter(numero_documento=numero).first())
                if doc is None:
                    logger.warning(
                        "Documento %s (RequestID %s) devolvido pela AGT mas inexistente localmente.",
                        numero, request_id,
                    )
                    continue

                meta = doc.metadados if isinstance(doc.metadados, dict) else {}
                meta["ultimo_estado_agt"] = estado
                meta["estado_verificado_em"] = timezone.now().isoformat()

                if estado in ESTADOS_VALIDADOS:
                    meta["estado_agt"] = "validado"
                    meta["validacao_agt"] = data
                    meta.pop("erros_agt", None)
                    if doc.status == "confirmed":
                        doc.status = "posted"
                    logger.info("Documento %s validado pela AGT (%s).", numero, estado)
                else:
                    meta["estado_agt"] = "rejeitado"
                    meta["erros_agt"] = item.get("errorList", [])
                    logger.warning("Documento %s NÃO validado pela AGT (%s).", numero, estado)

                doc.metadados = meta
                doc.save(update_fields=["status", "metadados"])
        return "FINISHED"