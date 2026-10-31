# apps/fiscal/services/submissao_documento_agt.py
"""Orquestra build, captura e submissão com claim por documento."""
from __future__ import annotations

import logging

from django.conf import settings
from django.db.models import Q

from apps.fiscal.models_payload_agt import PayloadAGT
from apps.fiscal.services.agt_payload_builder import (
    AGTPayloadBuilder,
    AGTPayloadBuildError,
)
from apps.fiscal.services.payload_inspector import PayloadInspectorService
from apps.fiscal.services.payload_submission_guard import PayloadSubmissionGuardService
from apps.fiscal.services.agt_client import AGTError
from apps.fiscal.services.utils import FiscalServiceError

logger = logging.getLogger("fiscal.submissao_agt")


class SubmissaoAGTBloqueada(FiscalServiceError):
    pass


def _payload_existente_reutilizavel(documento):
    return (
        PayloadAGT.objects.filter(
            documentos=documento,
            status__in=(
                PayloadAGT.STATUS_PREPARADO,
                PayloadAGT.STATUS_NAO_ENVIADO,
            ),
            resultado_indeterminado=False,
        )
        .exclude(payload={})
        .order_by("-created_at", "-pk")
        .first()
    )

def _tentativa_anterior_bloqueante(documento):
    return (
        PayloadAGT.objects.filter(documentos=documento)
        .filter(
            Q(status=PayloadAGT.STATUS_ENVIADO)
            | Q(status=PayloadAGT.STATUS_RESPOSTA)
            | (
                Q(status=PayloadAGT.STATUS_FALHOU)
                & Q(resultado_indeterminado=True)
            )
        )
        .order_by("-created_at", "-pk")
        .first()
    )

def _payload_ja_tentado(documento):
    return (
        PayloadAGT.objects.filter(documentos=documento)
        .exclude(status__in=(
            PayloadAGT.STATUS_PREPARADO,
            PayloadAGT.STATUS_NAO_ENVIADO,
            PayloadAGT.STATUS_ERRO_PREPARACAO,
        ))
        .order_by("-created_at", "-pk")
        .first()
    )


def submeter_documento_agt(documento, cliente_agt):
    """
    Um DocumentoFiscal só pode ter uma tentativa activa.

    PREPARADO/NAO_ENVIADO reutiliza exactamente o envelope já capturado.
    ENVIADO/RESPOSTA/FALHOU nunca provoca um novo build/POST automático.
    """
    token = PayloadSubmissionGuardService.reivindicar(documento.pk)
    if token is None:
        controlo = getattr(documento, "controlo_submissao_agt", None)
        if controlo and controlo.request_id:
            return {
                "success": True,
                "already_submitted": True,
                "requestID": controlo.request_id,
            }
        raise SubmissaoAGTBloqueada(
            "A submissão deste DocumentoFiscal já está em curso, foi concluída "
            "ou tem resultado indeterminado. Não foi efectuado outro POST."
        )

    payload_registo = None
    payload = None
    try:
        existente = _payload_existente_reutilizavel(documento)
        tentativa_anterior = _payload_ja_tentado(documento)

        if existente:
            # Não reconstruir: conservar UUID, assinaturas e conteúdo exacto.
            payload = existente.payload
            payload_registo = existente
        elif tentativa_anterior:
            raise SubmissaoAGTBloqueada(
                "Já existe uma tentativa de submissão sem resultado seguro para reenvio. "
                "Reconciliar o RequestID/estado AGT antes de qualquer nova tentativa."
            )
        else:
            payload = AGTPayloadBuilder.build(documento)

        resultado = cliente_agt.registar_documento_fiscal(payload)
        submission_uuid = str(payload.get("submissionUUID") or "")
        payload_registo = (
            PayloadAGT.objects.filter(submission_uuid=submission_uuid).first()
            if submission_uuid else payload_registo
        )
        request_id = str(resultado.get("requestID") or "")

        PayloadSubmissionGuardService.finalizar(
            documento.pk,
            token,
            "AGT_EM_PROCESSAMENTO" if request_id else "RESULTADO_INDETERMINADO",
            payload=payload_registo,
            submission_uuid=submission_uuid,
            request_id=request_id,
            detalhe="" if request_id else "Resposta sem RequestID.",
        )
        return resultado

    except AGTPayloadBuildError as exc:
        try:
            payload_registo = PayloadInspectorService.registar_erro_preparacao(
                documento=documento,
                erro=exc,
                endpoint=f"{getattr(cliente_agt, 'base_url', '')}/registarFactura",
                ambiente=getattr(cliente_agt, "ambiente", None)
                or getattr(settings, "AGT_ENVIRONMENT", ""),
            )
            PayloadSubmissionGuardService.finalizar(
                documento.pk, token, "ERRO_PREPARACAO",
                payload=payload_registo, detalhe=str(exc),
            )
        except Exception:
            logger.exception("Não foi possível persistir o erro de preparação AGT.")
        raise

    except AGTError as exc:
        if payload is not None:
            submission_uuid = str(payload.get("submissionUUID") or "")
            payload_registo = (
                PayloadAGT.objects.filter(submission_uuid=submission_uuid).first()
                if submission_uuid else payload_registo
            )

        if exc.rede:
            estado = "RESULTADO_INDETERMINADO"
        elif exc.http_status is not None and exc.http_status >= 500:
            estado = "RESULTADO_INDETERMINADO"
        else:
            estado = "FALHA_AGT"

        PayloadSubmissionGuardService.finalizar(
            documento.pk,
            token,
            estado,
            payload=payload_registo,
            submission_uuid=str(payload.get("submissionUUID") or "") if payload else "",
            request_id=getattr(payload_registo, "request_id", "") if payload_registo else "",
            detalhe=str(exc),
        )
        raise

    except Exception as exc:
        if payload is not None:
            submission_uuid = str(payload.get("submissionUUID") or "")
            payload_registo = (
                PayloadAGT.objects.filter(submission_uuid=submission_uuid).first()
                if submission_uuid else payload_registo
            )

        # Só se considera reexecutável quando o Inspector confirma NAO_ENVIADO.
        if payload_registo and payload_registo.status == PayloadAGT.STATUS_NAO_ENVIADO:
            estado = "NAO_ENVIADO"
        elif payload_registo and payload_registo.resultado_indeterminado:
            estado = "RESULTADO_INDETERMINADO"
        elif payload_registo and payload_registo.status == PayloadAGT.STATUS_RESPOSTA:
            estado = "RESULTADO_INDETERMINADO"
        else:
            estado = "ERRO_PREPARACAO"

        try:
            PayloadSubmissionGuardService.finalizar(
                documento.pk,
                token,
                estado,
                payload=payload_registo,
                submission_uuid=str(payload.get("submissionUUID") or "") if payload else "",
                request_id=getattr(payload_registo, "request_id", "") if payload_registo else "",
                detalhe=str(exc),
            )
        except Exception:
            logger.exception("Falha ao fechar o claim do DocumentoFiscal #%s.", documento.pk)
        raise
