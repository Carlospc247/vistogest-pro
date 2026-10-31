# apps/fiscal/services/polling_service.py
import logging

from django.db import transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services.agt_client import AGTClient, AGTError
from .utils import FiscalServiceError
from apps.fiscal.models_payload_agt import PayloadAGT
from apps.fiscal.payload_listener import PayloadListenerService
from apps.fiscal.services.payload_submission_guard import (
    PayloadSubmissionGuardService,
)


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
        """
        Processa o resultado final da validação AGT.

        V/P = documento validado.
        Outros estados finais = documento não validado/rejeitado.

        O resultado é reflectido no DocumentoFiscal, no controlo da submissão
        e no histórico de acontecimentos do Inspector.
        """

        if str(data.get("resultCode")) == "8":
            logger.info(
                "AGT continua a processar o RequestID %s.",
                request_id,
            )
            return "PROCESSING"

        lista = data.get("documentStatusList") or []

        if not isinstance(lista, list):
            logger.error(
                "AGT devolveu documentStatusList inválida para RequestID %s.",
                request_id,
            )
            return False

        for item in lista:
            if not isinstance(item, dict):
                logger.warning(
                    "Item inválido em documentStatusList: %r",
                    item,
                )
                continue

            numero = str(item.get("documentNo") or "").strip()
            tipo = str(
                item.get("documentType")
                or item.get("documentTypeCode")
                or ""
            ).strip().upper()

            estado = str(item.get("documentStatus") or "").strip().upper()

            if not numero or not estado:
                logger.warning(
                    "Resultado AGT sem documentNo/documentStatus: %s",
                    item,
                )
                continue

            # Procurar por número e, quando a AGT o fornece, também pelo tipo.
            qs = DocumentoFiscal.objects.select_for_update().filter(
                numero_documento=numero
            )

            if tipo:
                qs = qs.filter(tipo_documento=tipo)

            candidatos = list(qs[:2])

            if len(candidatos) != 1:
                logger.error(
                    "Resultado AGT ambíguo ou sem correspondência: "
                    "tipo=%s, número=%s, RequestID=%s, encontrados=%s",
                    tipo,
                    numero,
                    request_id,
                    len(candidatos),
                )
                continue

            doc = candidatos[0]
            validado = estado in ESTADOS_VALIDADOS

            with transaction.atomic():
                # Bloquear novamente dentro da transacção que altera o documento.
                doc = (
                    DocumentoFiscal.objects
                    .select_for_update()
                    .get(pk=doc.pk)
                )

                meta = (
                    dict(doc.metadados)
                    if isinstance(doc.metadados, dict)
                    else {}
                )

                meta["ultimo_estado_agt"] = estado
                meta["estado_verificado_em"] = timezone.now().isoformat()
                meta["request_id_agt"] = request_id

                if validado:
                    meta["estado_agt"] = "validado"
                    meta["agt_submission_state"] = "AGT_VALIDADO"
                    meta["validacao_agt"] = data
                    meta.pop("erros_agt", None)

                    if doc.status == "confirmed":
                        doc.status = "posted"

                    logger.info(
                        "Documento %s validado pela AGT (%s).",
                        numero,
                        estado,
                    )

                else:
                    meta["estado_agt"] = "rejeitado"
                    meta["agt_submission_state"] = "AGT_REJEITADO"
                    meta["erros_agt"] = item.get("errorList", [])

                    logger.warning(
                        "Documento %s rejeitado/não validado pela AGT (%s).",
                        numero,
                        estado,
                    )

                doc.metadados = meta
                doc.save(update_fields=["status", "metadados"])

                # Actualizar o controlo persistente da submissão.
                try:
                    PayloadSubmissionGuardService.registar_resultado_polling(
                        documento_id=doc.pk,
                        validado=validado,
                        request_id=request_id,
                        detalhe=(
                            f"Estado AGT: {estado}. "
                            f"Erros: {item.get('errorList', [])}"
                        ),
                    )
                except Exception:
                    logger.exception(
                        "Não foi possível actualizar ControloSubmissaoAGT "
                        "para DocumentoFiscal #%s.",
                        doc.pk,
                    )

                # Encontrar o envelope exacto que originou este RequestID.
                payload = (
                    PayloadAGT.objects
                    .filter(
                        request_id=request_id,
                        documentos=doc,
                    )
                    .order_by("-created_at", "-pk")
                    .first()
                )

                evento = (
                    "DOCUMENTO_VALIDADO"
                    if validado
                    else "DOCUMENTO_REJEITADO"
                )

                if payload:
                    try:
                        PayloadListenerService.registar_evento(
                            documento=doc,
                            tipo_evento=evento,
                            chave=(
                                f"payload:{payload.pk}:"
                                f"documento:{doc.pk}:resultado:{estado}"
                            ),
                            descricao=(
                                f"Resultado final da validação AGT: {estado}."
                            ),
                            payload=payload,
                            dados={
                                "request_id": request_id,
                                "document_status": estado,
                                "validado": validado,
                                "error_list": item.get("errorList", []),
                            },
                        )
                    except Exception:
                        logger.exception(
                            "Falha ao guardar evento final AGT do documento #%s.",
                            doc.pk,
                        )
                else:
                    # Não perder o resultado só porque a relação PayloadAGT
                    # ainda não foi localizada.
                    try:
                        PayloadListenerService.registar_evento(
                            documento=doc,
                            tipo_evento=evento,
                            chave=(
                                f"documento:{doc.pk}:"
                                f"request:{request_id}:resultado:{estado}"
                            ),
                            descricao=(
                                f"AGT devolveu resultado final {estado}; "
                                "o payload correspondente não foi localizado."
                            ),
                            dados={
                                "request_id": request_id,
                                "document_status": estado,
                                "validado": validado,
                                "error_list": item.get("errorList", []),
                            },
                        )
                    except Exception:
                        logger.exception(
                            "Não foi possível registar o resultado AGT "
                            "sem relação de payload para #%s.",
                            doc.pk,
                        )

        return "FINISHED"
