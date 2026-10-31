# apps/fiscal/services/payload_inspector.py
"""
Captura imutável dos envelopes AGT.

O payload_json é o corpo serializado em UTF-8 que o AGTClient deve enviar.
PayloadAGT.payload conserva também a representação JSON estruturada para consulta.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.fiscal.models_payload_agt import PayloadAGT

logger = logging.getLogger("fiscal.payload_inspector")


def _json_default(value: Any):
    raise TypeError(
        f"Tipo não serializável no JSON AGT: {type(value).__name__}. "
        "Converta Decimal/datas no construtor do payload."
    )


class PayloadInspectorService:
    @staticmethod
    def serializar_payload(payload: dict) -> str:
        if not isinstance(payload, dict):
            raise ValueError("O envelope AGT tem de ser um objecto JSON.")
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            default=_json_default,
        )

    @staticmethod
    def _validar_snapshot(raw_json: str) -> dict:
        snapshot = json.loads(raw_json)
        if not isinstance(snapshot, dict):
            raise ValueError("O envelope AGT tem de ser um objecto JSON.")
        documents = snapshot.get("documents")
        if not isinstance(documents, list):
            raise ValueError("O envelope registarFactura tem de conter documents como lista.")
        if not documents:
            raise ValueError("O envelope registarFactura não contém documentos.")
        if len(documents) > 30:
            raise ValueError("A AGT permite no máximo 30 documentos por submissão.")
        if any(not isinstance(item, dict) for item in documents):
            raise ValueError("Cada elemento de documents tem de ser um objecto.")
        return snapshot

    @staticmethod
    def _normalizar_ambiente(value: str | None) -> str:
        value = str(value or getattr(settings, "AGT_ENVIRONMENT", "") or "").strip().upper()
        if value in {"HOMOLOGAÇÃO", "HOMOLOGACAO", "HML", "TEST", "TESTE"}:
            return "HOMOLOGACAO"
        if value in {"PRODUÇÃO", "PRODUCAO", "PRODUCTION", "PROD"}:
            return "PRODUCTION"
        return "DESCONHECIDO"

    @staticmethod
    def _signature_flags(payload: dict) -> tuple[bool, bool, bool]:
        software = payload.get("softwareInfo")
        software = software if isinstance(software, dict) else {}
        docs = payload.get("documents") or []
        return (
            bool(str(payload.get("jwsSignature") or "").strip()),
            bool(str(software.get("jwsSoftwareSignature") or "").strip()),
            bool(docs) and all(
                bool(str(doc.get("jwsDocumentSignature") or "").strip())
                for doc in docs
            ),
        )

    @staticmethod
    def _metadados_documentos(payload: dict):
        docs = payload["documents"]
        types = sorted({
            str(item.get("documentType") or "").strip()
            for item in docs if item.get("documentType")
        })
        numbers = [
            str(item.get("documentNo") or "").strip()
            for item in docs if item.get("documentNo")
        ]
        tipo = types[0][:8] if len(types) == 1 else ("MULTI" if len(types) > 1 else "")
        if len(numbers) == 1:
            numero = numbers[0]
        elif numbers:
            numero = f"{len(numbers)} documentos: " + ", ".join(numbers[:3])
            if len(numbers) > 3:
                numero += ", …"
        else:
            numero = ""
        pairs = [
            (str(item.get("documentType") or "").strip(),
             str(item.get("documentNo") or "").strip())
            for item in docs
        ]
        return tipo, numero[:200], pairs

    @staticmethod
    def _associar_documentos(registo, documents: list[dict]):
        """
        Associa apenas correspondências exactas e únicas (tipo + número).
        Não rejeita o snapshot quando não encontra um documento: o JSON real
        continua preservado e a auditoria assinala a associação incompleta.
        """
        from apps.fiscal.models import DocumentoFiscal

        pares = []
        for item in documents:
            tipo = str(item.get("documentType") or "").strip()
            numero = str(item.get("documentNo") or "").strip()
            pares.append((tipo, numero))

        filtro = Q()
        for tipo, numero in set(pares):
            if tipo and numero:
                filtro |= Q(tipo_documento=tipo, numero_documento=numero)

        encontrados = (
            list(DocumentoFiscal.objects.filter(filtro))
            if filtro else []
        )
        por_par = {}
        for documento in encontrados:
            por_par.setdefault(
                (documento.tipo_documento, documento.numero_documento), []
            ).append(documento)

        associados = {}
        indices = {}
        ocorrencias = {}
        for index, par in enumerate(pares):
            ocorrencias[par] = ocorrencias.get(par, 0) + 1
            candidatos = por_par.get(par, [])
            if len(candidatos) == 1 and par[0] and par[1]:
                doc = candidatos[0]
                associados[doc.pk] = doc
                indices.setdefault(doc.pk, []).append(index)
            elif not par[0] or not par[1]:
                logger.warning(
                    "Payload #%s: documents[%s] sem documentType/documentNo.",
                    registo.pk, index,
                )

        duplicados_envelope = [
            {"documentType": p[0], "documentNo": p[1]}
            for p, count in ocorrencias.items() if count > 1
        ]
        nao_encontrados = []
        ambiguos = []
        for par in set(pares):
            candidatos = por_par.get(par, [])
            if not par[0] or not par[1] or not candidatos:
                nao_encontrados.append({
                    "documentType": par[0], "documentNo": par[1],
                })
            elif len(candidatos) > 1:
                ambiguos.append({
                    "documentType": par[0], "documentNo": par[1],
                    "documentos_locais": [x.pk for x in candidatos],
                })

        registo.documentos.add(*associados.values())
        resultado = {
            "associados": [
                {"documento_id": pk, "indices": indices[pk]}
                for pk in associados
            ],
            "nao_encontrados": nao_encontrados,
            "ambiguos": ambiguos,
            "duplicados_no_envelope": duplicados_envelope,
            "quantidade_json": len(documents),
            "quantidade_associada": len(associados),
        }
        registo.associacao_resultado = resultado
        registo.save(update_fields=["associacao_resultado", "updated_at"])

        from apps.fiscal.payload_listener import PayloadListenerService
        PayloadListenerService.registar_payload_capturado(
            registo,
            list(associados.values()),
            indices_por_documento=indices,
        )
        return resultado

    @staticmethod
    @transaction.atomic
    def registar_payload(
        payload: dict,
        endpoint: str = "",
        ambiente: str | None = None,
        raw_json: str | None = None,
    ) -> PayloadAGT:
        raw = raw_json if raw_json is not None else PayloadInspectorService.serializar_payload(payload)
        snapshot = PayloadInspectorService._validar_snapshot(raw)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        submission_uuid = str(snapshot.get("submissionUUID") or "").strip()[:64]
        tipo, numero, _pares = PayloadInspectorService._metadados_documentos(snapshot)
        req_sig, sw_sig, doc_sig = PayloadInspectorService._signature_flags(snapshot)

        if submission_uuid:
            existente = (
                PayloadAGT.objects.select_for_update()
                .filter(submission_uuid=submission_uuid)
                .first()
            )
            if existente:
                hash_existente = (
                    existente.hash_payload
                    or hashlib.sha256(
                        (getattr(existente, "payload_json", "") or "").encode("utf-8")
                    ).hexdigest()
                )
                if existente.payload != snapshot or (
                    existente.hash_payload and hash_existente != digest
                ):
                    raise ValueError(
                        "submissionUUID já registado com conteúdo diferente. "
                        "Não é seguro reutilizá-lo."
                    )
                return existente

        try:
            # Savepoint para recuperar uma corrida protegida pela constraint SQL.
            with transaction.atomic():
                registo = PayloadAGT.objects.create(
                    submission_uuid=submission_uuid,
                    tipo_documento=tipo,
                    numero_documento=numero,
                    quantidade_documentos=len(snapshot["documents"]),
                    ambiente=PayloadInspectorService._normalizar_ambiente(ambiente),
                    endpoint=str(endpoint or "")[:512],
                    payload=snapshot,
                    payload_json=raw,
                    hash_payload=digest,
                    associacao_resultado={},
                    assinatura_pedido_presente=req_sig,
                    assinatura_software_presente=sw_sig,
                    assinaturas_documentos_presentes=doc_sig,
                    status=PayloadAGT.STATUS_PREPARADO,
                )
        except IntegrityError:
            if not submission_uuid:
                raise
            registo = (
                PayloadAGT.objects.select_for_update()
                .get(submission_uuid=submission_uuid)
            )
            if registo.payload != snapshot or registo.hash_payload != digest:
                raise ValueError(
                    "Conflito de concorrência: submissionUUID usado por outro conteúdo."
                )

        PayloadInspectorService._associar_documentos(registo, snapshot["documents"])

        logger.info(
            "Payload AGT #%s capturado. uuid=%s hash=%s docs=%s",
            registo.pk, submission_uuid, digest, len(snapshot["documents"]),
        )

        # Auditoria técnica é independente do envio. Uma falha no motor de
        # auditoria não apaga a captura nem deve provocar um segundo POST.
        try:
            from apps.fiscal.services.payload_audit_service import PayloadAuditService
            PayloadAuditService.auditar_payload(registo)
        except Exception:
            logger.exception(
                "Payload #%s capturado, mas a auditoria técnica falhou.",
                registo.pk,
            )

        return registo

    @staticmethod
    @transaction.atomic
    def marcar_enviado(registo: PayloadAGT) -> bool:
        """
        Reivindica atomicamente o envio do envelope.
        Só PREPARADO e NAO_ENVIADO podem avançar.
        Retorna:
            True  -> este processo ganhou o direito de efectuar o POST.
            False -> envelope já enviado, reivindicado ou indeterminado.
        """

        locked = (PayloadAGT.objects.select_for_update().get(pk=registo.pk))

        if getattr(locked, "resultado_indeterminado", False):
            return False

        permitidos = {
            PayloadAGT.STATUS_PREPARADO,
            PayloadAGT.STATUS_NAO_ENVIADO,
        }

        if locked.status not in permitidos:
            logger.warning(
                "POST AGT bloqueado: Payload #%s encontra-se no estado %s.",
                locked.pk,
                locked.status,
            )
            return False

        locked.status = PayloadAGT.STATUS_ENVIADO
        locked.resultado_indeterminado = False
        locked.enviado_em = timezone.now()
        locked.erro = ""

        locked.save(
            update_fields=[
                "status",
                "resultado_indeterminado",
                "enviado_em",
                "erro",
                "updated_at",
            ]
        )

        from apps.fiscal.payload_listener import PayloadListenerService

        PayloadListenerService.registar_evento_transporte(
            locked,
            "PEDIDO_ENVIADO",
            "enviado",
            "Envelope reivindicado e marcado como enviado antes do POST.",
        )

        # Actualizar a instância que foi passada ao método.
        registo.status = locked.status
        registo.enviado_em = locked.enviado_em
        registo.resultado_indeterminado = False

        return True

    
    @staticmethod
    @transaction.atomic
    def registar_resposta(registo: PayloadAGT, response) -> PayloadAGT:
        locked = PayloadAGT.objects.select_for_update().get(pk=registo.pk)
        locked.http_status = getattr(response, "status_code", None)
        locked.resposta_em = timezone.now()

        try:
            body = response.json()
            locked.resposta = body if isinstance(body, dict) else {"response": body}
        except Exception:
            locked.resposta = {
                "content_type": str(
                    getattr(response, "headers", {}).get("Content-Type", "")
                )[:120],
                "body_preview": str(getattr(response, "text", ""))[:1500],
            }

        body_data = locked.resposta if isinstance(locked.resposta, dict) else {}
        locked.request_id = str(
            body_data.get("requestID") or body_data.get("requestId") or ""
        )[:200]
        status_code = int(getattr(response, "status_code", 0) or 0)
        locked.status = (
            PayloadAGT.STATUS_RESPOSTA if 200 <= status_code < 400
            else PayloadAGT.STATUS_FALHOU
        )
        locked.resultado_indeterminado = status_code >= 500
        #locked.resultado_indeterminado = False
        locked.erro = (
            f"A API respondeu HTTP {status_code}. Consultar a resposta registada."
            if status_code >= 400 else ""
        )
        locked.save(update_fields=[
            "http_status", "resposta_em", "resposta", "request_id",
            "status", "resultado_indeterminado", "erro", "updated_at",
        ])

        from apps.fiscal.payload_listener import PayloadListenerService
        PayloadListenerService.registar_evento_transporte(
            locked,
            "RESPOSTA_RECEBIDA",
            "resposta",
            "Resposta HTTP da AGT registada no Inspector.",
            {
                "http_status": status_code,
                "request_id": locked.request_id,
            },
        )
        return locked

    @staticmethod
    @transaction.atomic
    def marcar_falha(registo: PayloadAGT, erro: object, *, pedido_enviado: bool = False,) -> PayloadAGT:
        locked = PayloadAGT.objects.select_for_update().get(pk=registo.pk)
        locked.erro = str(erro or "Falha não especificada")[:3000]
        locked.status = (
            PayloadAGT.STATUS_FALHOU
            if pedido_enviado else PayloadAGT.STATUS_NAO_ENVIADO
        )
        locked.resultado_indeterminado = bool(pedido_enviado)
        locked.save(update_fields=["erro", "status", "resultado_indeterminado", "updated_at"])

        from apps.fiscal.payload_listener import PayloadListenerService
        tipo_evento = (
            "RESULTADO_INDETERMINADO" if pedido_enviado else "FALHA_COMUNICACAO"
        )
        PayloadListenerService.registar_evento_transporte(
            locked,
            tipo_evento,
            "falha",
            locked.erro,
            {"pedido_enviado_ou_iniciado": pedido_enviado},
        )
        return locked

    @staticmethod
    @transaction.atomic
    def registar_erro_preparacao(
        documento,
        erro: object,
        endpoint: str = "",
        ambiente: str | None = None,
    ) -> PayloadAGT:
        registo = PayloadAGT.objects.create(
            tipo_documento=str(getattr(documento, "tipo_documento", "") or "")[:8],
            numero_documento=str(getattr(documento, "numero_documento", "") or "")[:200],
            quantidade_documentos=1 if documento else 0,
            ambiente=PayloadInspectorService._normalizar_ambiente(ambiente),
            endpoint=str(endpoint or "")[:512],
            payload={},
            payload_json="",
            hash_payload="",
            associacao_resultado={},
            status=PayloadAGT.STATUS_ERRO_PREPARACAO,
            erro=str(erro or "Falha ao construir o payload")[:3000],
        )
        if documento and getattr(documento, "pk", None):
            registo.documentos.add(documento)
            from apps.fiscal.payload_listener import PayloadListenerService
            PayloadListenerService.registar_erro_preparacao(documento, registo, erro)
        return registo
