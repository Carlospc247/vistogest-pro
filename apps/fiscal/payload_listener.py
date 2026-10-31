# apps/fiscal/payload_listener.py
from __future__ import annotations

import logging

from django.db import connection, transaction

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.models_payload_agt import EventoAuditoriaPayloadAGT

logger = logging.getLogger("fiscal.payload_listener")

ESTADOS_EMITIDOS = {"confirmed", "posted", "paid"}


class PayloadListenerService:
    @staticmethod
    def _validar_tenant(schema_name: str | None = None) -> str:
        actual = getattr(connection, "schema_name", "public")
        if not actual or actual == "public":
            raise RuntimeError("O Inspector AGT não pode gravar eventos no schema public.")
        if schema_name and schema_name != actual:
            raise RuntimeError(
                f"Schema recebido ({schema_name}) diferente do schema activo ({actual})."
            )
        return actual

    @staticmethod
    @transaction.atomic
    def registar_evento(
        documento,
        tipo_evento: str,
        chave: str,
        descricao: str,
        *,
        payload=None,
        dados: dict | None = None,
    ):
        evento, _ = EventoAuditoriaPayloadAGT.objects.get_or_create(
            idempotency_key=chave,
            defaults={
                "documento": documento,
                "payload": payload,
                "tipo_evento": tipo_evento,
                "descricao": descricao,
                "dados": dados or {},
            },
        )
        return evento

    @classmethod
    @transaction.atomic
    def registar_emissao(cls, documento_id: int, schema_name: str | None = None):
        schema = cls._validar_tenant(schema_name)
        documento = DocumentoFiscal.objects.get(pk=documento_id)

        if documento.status not in ESTADOS_EMITIDOS:
            logger.info(
                "[%s] Documento #%s não está emitido (%s); evento ignorado.",
                schema, documento.pk, documento.status,
            )
            return None

        from apps.fiscal.services.agt_payload_builder import AGT_DOCUMENT_TYPES

        elegivel = documento.tipo_documento in AGT_DOCUMENT_TYPES
        dados = {
            "schema_name": schema,
            "tipo_documento": documento.tipo_documento,
            "numero_documento": documento.numero_documento,
            "data_emissao": (
                documento.data_emissao.isoformat() if documento.data_emissao else None
            ),
            "data_confirmacao": (
                documento.data_confirmacao.isoformat()
                if getattr(documento, "data_confirmacao", None) else None
            ),
            "estado": documento.status,
            "agt_elegivel": elegivel,
        }

        cls.registar_evento(
            documento,
            "DOCUMENTO_EMITIDO",
            f"documento:{documento.pk}:emitido",
            "Documento fiscal emitido localmente.",
            dados=dados,
        )

        if elegivel:
            cls.registar_evento(
                documento,
                "AGUARDANDO_PAYLOAD",
                f"documento:{documento.pk}:aguardando_payload",
                "Documento elegível; aguarda captura do envelope JSON real.",
                dados=dados,
            )
        else:
            cls.registar_evento(
                documento,
                "NAO_APLICAVEL",
                f"documento:{documento.pk}:nao_aplicavel",
                "Tipo documental não suportado pelo AGTPayloadBuilder.",
                dados=dados,
            )

        return {"documento_id": documento.pk, "elegivel": elegivel}

    @classmethod
    @transaction.atomic
    def registar_payload_capturado(
        cls,
        payload,
        documentos: list,
        *,
        indices_por_documento: dict[int, list[int]] | None = None,
    ):
        schema = cls._validar_tenant()
        indices_por_documento = indices_por_documento or {}

        for documento in documentos:
            indices = indices_por_documento.get(documento.pk, [])
            dados = {
                "schema_name": schema,
                "payload_id": payload.pk,
                "submission_uuid": payload.submission_uuid,
                "hash_payload": getattr(payload, "hash_payload", ""),
                "document_indices": indices,
                "quantidade_documentos_envelope": payload.quantidade_documentos,
            }
            cls.registar_evento(
                documento,
                "PAYLOAD_CAPTURADO",
                f"payload:{payload.pk}:documento:{documento.pk}:capturado",
                "Envelope JSON real capturado e associado ao documento.",
                payload=payload,
                dados=dados,
            )

    @classmethod
    @transaction.atomic
    def registar_evento_transporte(
        cls,
        payload,
        tipo_evento: str,
        sufixo: str,
        descricao: str,
        dados_extra: dict | None = None,
    ):
        cls._validar_tenant()
        documentos = list(payload.documentos.all())
        for documento in documentos:
            dados = {
                "payload_id": payload.pk,
                "submission_uuid": payload.submission_uuid,
                "request_id": payload.request_id,
            }
            if dados_extra:
                dados.update(dados_extra)
            cls.registar_evento(
                documento,
                tipo_evento,
                f"payload:{payload.pk}:documento:{documento.pk}:{sufixo}",
                descricao,
                payload=payload,
                dados=dados,
            )

    @classmethod
    @transaction.atomic
    def registar_erro_preparacao(cls, documento, payload, erro):
        cls._validar_tenant()
        cls.registar_evento(
            documento,
            "ERRO_PREPARACAO",
            f"payload:{payload.pk}:documento:{documento.pk}:erro_preparacao",
            "O construtor não conseguiu produzir um envelope AGT válido.",
            payload=payload,
            dados={
                "payload_id": payload.pk,
                "erro": str(erro)[:3000],
            },
        )
