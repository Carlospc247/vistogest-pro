"""Captura segura de JSON construído para os pedidos da API AGT.

Este serviço não envia pedidos, não muda o estado do documento fiscal e não
armazena credenciais HTTP. Guarda apenas o corpo JSON preparado e metadados
operacionais para inspecção de certificação.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.fiscal.models_payload_agt import PayloadAGT

logger = logging.getLogger("fiscal.payload_inspector")


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "pk"):
        return value.pk
    return str(value)


def _json_snapshot(value: Any) -> dict:
    """Faz cópia serializável sem guardar objetos Python mutáveis."""
    raw = json.dumps(value, ensure_ascii=False, default=_json_default, separators=(",", ":"))
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("O payload AGT deve ser um objecto JSON/dicionário.")
    return result


def _signature_flags(payload: dict) -> tuple[bool, bool, bool]:
    software_info = payload.get("softwareInfo") or {}
    software_signature = software_info.get("jwsSoftwareSignature")
    request_signature = payload.get("jwsSignature")
    documents = payload.get("documents") or []
    document_signatures = bool(documents) and all(
        isinstance(doc, dict) and bool(str(doc.get("jwsDocumentSignature") or "").strip())
        for doc in documents
    )
    return bool(str(request_signature or "").strip()), bool(str(software_signature or "").strip()), document_signatures


class PayloadInspectorService:
    """API central usada pelos diferentes caminhos de submissão fiscal."""

    @staticmethod
    @transaction.atomic
    def registar_payload(payload: dict, endpoint: str = "", ambiente: str | None = None) -> PayloadAGT:
        snapshot = _json_snapshot(payload)
        documents = snapshot.get("documents") or []
        if not isinstance(documents, list):
            raise ValueError("O campo 'documents' do payload deve ser uma lista.")

        types = sorted({
            str(item.get("documentType") or "").strip()
            for item in documents
            if isinstance(item, dict) and str(item.get("documentType") or "").strip()
        })
        numbers = [
            str(item.get("documentNo") or "").strip()
            for item in documents
            if isinstance(item, dict) and str(item.get("documentNo") or "").strip()
        ]
        if len(types) == 1:
            tipo_documento = types[0][:8]
        elif len(types) > 1:
            tipo_documento = "MULTI"
        else:
            tipo_documento = ""

        if len(numbers) == 1:
            numero_documento = numbers[0]
        elif numbers:
            numero_documento = f"{len(numbers)} documentos: " + ", ".join(numbers[:3])
            if len(numbers) > 3:
                numero_documento += ", …"
        else:
            numero_documento = ""

        request_sig, software_sig, document_sigs = _signature_flags(snapshot)
        ambiente = (ambiente or getattr(settings, "AGT_ENVIRONMENT", "") or "DESCONHECIDO").strip().upper()
        if ambiente in {"HOMOLOGAÇÃO", "HOMOLOGACAO", "HML", "TEST"}:
            ambiente = "HOMOLOGACAO"
        elif ambiente in {"PRODUCAO", "PRODUÇÃO", "PRODUCTION", "PROD"}:
            ambiente = "PRODUCTION"
        else:
            ambiente = "DESCONHECIDO"

        registo = PayloadAGT.objects.create(
            submission_uuid=str(snapshot.get("submissionUUID") or "")[:64],
            tipo_documento=tipo_documento,
            numero_documento=numero_documento[:200],
            quantidade_documentos=len(documents),
            ambiente=ambiente,
            endpoint=str(endpoint or "")[:512],
            payload=snapshot,
            assinatura_pedido_presente=request_sig,
            assinatura_software_presente=software_sig,
            assinaturas_documentos_presentes=document_sigs,
            status=PayloadAGT.STATUS_PREPARADO,
        )

        # Associar documentos que existam no schema/tenant activo. Não consulta public.
        if numbers:
            from apps.fiscal.models import DocumentoFiscal
            encontrados = DocumentoFiscal.objects.filter(numero_documento__in=numbers)
            registo.documentos.set(encontrados)

        logger.info(
            "Payload AGT #%s registado: tipo=%s docs=%s ambiente=%s; assinaturas presentes pedido/software/documentos=%s/%s/%s",
            registo.pk, registo.tipo_documento, registo.quantidade_documentos,
            registo.ambiente, request_sig, software_sig, document_sigs,
        )
        return registo

    @staticmethod
    @transaction.atomic
    def marcar_enviado(registo: PayloadAGT) -> PayloadAGT:
        registo.status = PayloadAGT.STATUS_ENVIADO
        registo.enviado_em = timezone.now()
        registo.erro = ""
        registo.save(update_fields=["status", "enviado_em", "erro", "updated_at"])
        return registo

    @staticmethod
    @transaction.atomic
    def registar_resposta(registo: PayloadAGT, response) -> PayloadAGT:
        registo.http_status = getattr(response, "status_code", None)
        registo.resposta_em = timezone.now()
        try:
            body = response.json()
            registo.resposta = body if isinstance(body, dict) else {"response": body}
        except Exception:
            # Regista apenas uma amostra da resposta; nunca inclui cabeçalhos HTTP.
            registo.resposta = {
                "content_type": str(getattr(response, "headers", {}).get("Content-Type", ""))[:120],
                "body_preview": str(getattr(response, "text", ""))[:1500],
            }

        data = registo.resposta if isinstance(registo.resposta, dict) else {}
        registo.request_id = str(data.get("requestID") or data.get("requestId") or "")[:200]
        status_code = int(getattr(response, "status_code", 0) or 0)
        registo.status = PayloadAGT.STATUS_RESPOSTA if 200 <= status_code < 400 else PayloadAGT.STATUS_FALHOU
        if status_code >= 400:
            registo.erro = f"A API respondeu HTTP {status_code}. Consultar a resposta registada."
        else:
            registo.erro = ""
        registo.save(update_fields=[
            "http_status", "resposta_em", "resposta", "request_id", "status", "erro", "updated_at"
        ])
        return registo

    @staticmethod
    @transaction.atomic
    def marcar_falha(registo: PayloadAGT, erro: object, *, pedido_enviado: bool = False) -> PayloadAGT:
        mensagem = str(erro or "Falha não especificada")
        # Não incluir repr(request), headers ou credenciais.
        registo.erro = mensagem[:3000]
        registo.status = PayloadAGT.STATUS_FALHOU if pedido_enviado else PayloadAGT.STATUS_NAO_ENVIADO
        registo.save(update_fields=["erro", "status", "updated_at"])
        return registo

    @staticmethod
    @transaction.atomic
    def registar_erro_preparacao(documento, erro: object, endpoint: str = "", ambiente: str | None = None):
        """Regista falha antes de existir JSON completo, sem inventar um payload."""
        registo = PayloadAGT.objects.create(
            tipo_documento=str(getattr(documento, "tipo_documento", "") or "")[:8],
            numero_documento=str(getattr(documento, "numero_documento", "") or "")[:200],
            quantidade_documentos=1 if documento else 0,
            ambiente=(ambiente or getattr(settings, "AGT_ENVIRONMENT", "") or "DESCONHECIDO").upper()[:20],
            endpoint=str(endpoint or "")[:512],
            payload={},
            status=PayloadAGT.STATUS_ERRO_PREPARACAO,
            erro=str(erro or "Falha ao construir o payload")[:3000],
        )
        if documento and getattr(documento, "pk", None):
            registo.documentos.add(documento)
        return registo
