# apps/fiscal/services/payload_reconciliation_service.py

"""
Reconciliação tenant-local dos documentos fiscais com PayloadAGT.

A reconciliação:
- não constrói JSON;
- não envia pedidos HTTP;
- não altera valores fiscais;
- pode reparar relações M2M inequivocamente identificadas;
- regista documentos emitidos sem envelope real;
- identifica envelopes órfãos e tentativas múltiplas.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.models_payload_agt import (
    PayloadAGT,
    EventoAuditoriaPayloadAGT,
)

logger = logging.getLogger("fiscal.payload_reconciliation")


class PayloadReconciliationService:

    @staticmethod
    def _schema():
        schema = getattr(connection, "schema_name", "public")

        if not schema or schema == "public":
            raise RuntimeError(
                "A reconciliação AGT só pode correr num schema tenant."
            )

        return schema

    @staticmethod
    def _pares_payload(payload):
        body = payload.payload if isinstance(payload.payload, dict) else {}
        documents = body.get("documents")

        if not isinstance(documents, list):
            return []

        return [
            (
                str(item.get("documentType") or "").strip().upper(),
                str(item.get("documentNo") or "").strip(),
            )
            for item in documents
            if isinstance(item, dict)
        ]

    @staticmethod
    def _tem_json_real(payload):
        """
        Um erro de preparação não constitui captura de JSON.

        PREPARADO, ENVIADO, RESPOSTA, FALHOU e NAO_ENVIADO podem
        representar envelopes reais, desde que o corpo tenha documents.
        """
        if payload.status == PayloadAGT.STATUS_ERRO_PREPARACAO:
            return False

        body = payload.payload if isinstance(payload.payload, dict) else {}
        documents = body.get("documents")

        return isinstance(documents, list) and bool(documents)

    @staticmethod
    def _data_emissao(documento):
        dt = getattr(documento, "data_confirmacao", None)

        if dt:
            return dt

        dia = getattr(documento, "data_emissao", None)

        if not dia:
            return None

        dt = datetime.combine(dia, time.min)

        if timezone.is_naive(dt):
            dt = timezone.make_aware(
                dt,
                timezone.get_current_timezone(),
            )

        return dt

    @staticmethod
    def _evento(
        documento,
        tipo_evento,
        chave,
        descricao,
        payload=None,
        dados=None,
    ):
        return EventoAuditoriaPayloadAGT.objects.get_or_create(
            idempotency_key=chave,
            defaults={
                "documento": documento,
                "payload": payload,
                "tipo_evento": tipo_evento,
                "descricao": descricao,
                "dados": dados or {},
            },
        )

    @staticmethod
    def _obter_documentos_locais(pares):
        """
        Obtém documentos por correspondência exacta de tipo e número.
        Não utiliza dois __in independentes.
        """
        filtro = Q()

        for tipo, numero in pares:
            if tipo and numero:
                filtro |= Q(
                    tipo_documento=tipo,
                    numero_documento=numero,
                )

        if not filtro:
            return {}

        encontrados = DocumentoFiscal.objects.filter(filtro)

        resultado = {}

        for documento in encontrados:
            par = (
                documento.tipo_documento,
                documento.numero_documento,
            )
            resultado.setdefault(par, []).append(documento)

        return resultado

    @classmethod
    @transaction.atomic
    def reconciliar(
        cls,
        *,
        dry_run=True,
        grace_minutes=10,
    ):
        schema = cls._schema()

        from apps.fiscal.services.agt_payload_builder import (
            AGT_DOCUMENT_TYPES,
        )

        grace_minutes = max(0, int(grace_minutes))
        limite = timezone.now() - timedelta(minutes=grace_minutes)

        documentos = list(
            DocumentoFiscal.objects.filter(
                tipo_documento__in=AGT_DOCUMENT_TYPES,
                status__in=("confirmed", "posted", "paid"),
            ).order_by("pk")
        )

        payloads = list(
            PayloadAGT.objects.all().order_by("pk")
        )

        pares_por_payload = {
            payload.pk: cls._pares_payload(payload)
            for payload in payloads
        }

        pares_totais = {
            par
            for pares in pares_por_payload.values()
            for par in pares
            if par[0] and par[1]
        }

        locais = cls._obter_documentos_locais(pares_totais)

        relatorio = {
            "schema": schema,
            "dry_run": dry_run,
            "documentos_analisados": len(documentos),
            "documentos_sem_payload": [],
            "documentos_reconciliados": [],
            "documentos_com_multiplos_payloads": [],
            "payloads_orfaos": [],
            "associacoes_incorrectas": [],
            "payloads_preparados_nao_enviados": [],
            "payloads_com_resultado_indeterminado": [],
            "payloads_com_documentos_duplicados": [],
        }

        # -----------------------------------------------------------
        # A. Inspeccionar cada envelope e recuperar M2M incompleto.
        # -----------------------------------------------------------
        for payload in payloads:
            pares = pares_por_payload[payload.pk]
            locais_do_payload = cls._obter_documentos_locais(set(pares))

            ocorrencias = {}

            for par in pares:
                ocorrencias[par] = ocorrencias.get(par, 0) + 1

            duplicados = [
                {
                    "tipo": par[0],
                    "numero": par[1],
                    "ocorrencias": quantidade,
                }
                for par, quantidade in ocorrencias.items()
                if quantidade > 1
            ]

            if duplicados:
                relatorio["payloads_com_documentos_duplicados"].append({
                    "payload_id": payload.pk,
                    "duplicados": duplicados,
                })

            associados = list(payload.documentos.all())
            associados_ids = {doc.pk for doc in associados}

            pares_associados = {
                (doc.tipo_documento, doc.numero_documento)
                for doc in associados
            }

            # Detectar associações M2M que não existem no JSON.
            incorrectos = [
                doc for doc in associados
                if (
                    doc.tipo_documento,
                    doc.numero_documento,
                ) not in set(pares)
            ]

            if incorrectos:
                relatorio["associacoes_incorrectas"].append({
                    "payload_id": payload.pk,
                    "documentos_incorrectos": [
                        {
                            "documento_id": doc.pk,
                            "tipo": doc.tipo_documento,
                            "numero": doc.numero_documento,
                        }
                        for doc in incorrectos
                    ],
                })

            # Reparar apenas associações exactas e inequívocas.
            reparados = []

            if cls._tem_json_real(payload):
                for par in set(pares):
                    candidatos = locais_do_payload.get(par, [])

                    if len(candidatos) != 1:
                        continue

                    doc = candidatos[0]

                    if doc.pk in associados_ids:
                        continue

                    reparados.append(doc)

                    if not dry_run:
                        payload.documentos.add(doc)

                        cls._evento(
                            doc,
                            "PAYLOAD_RECONCILIADO",
                            (
                                f"documento:{doc.pk}:"
                                f"payload_reconciliado:{payload.pk}"
                            ),
                            "Relação M2M recuperada pela reconciliação.",
                            payload,
                            {
                                "payload_id": payload.pk,
                                "submission_uuid": payload.submission_uuid,
                            },
                        )

                if reparados:
                    relatorio["documentos_reconciliados"].extend([
                        {
                            "documento_id": doc.pk,
                            "numero": doc.numero_documento,
                            "payload_id": payload.pk,
                        }
                        for doc in reparados
                    ])

            # Registar pares do envelope que não correspondem a um
            # único documento local.
            sem_correspondencia = []

            for par in set(pares):
                candidatos = locais_do_payload.get(par, [])

                if len(candidatos) != 1:
                    sem_correspondencia.append({
                        "tipo": par[0],
                        "numero": par[1],
                        "quantidade_local": len(candidatos),
                    })

            if sem_correspondencia:
                relatorio["payloads_orfaos"].append({
                    "payload_id": payload.pk,
                    "submission_uuid": payload.submission_uuid,
                    "documentos": sem_correspondencia,
                })

            # Envelope preparado mas ainda não enviado.
            if payload.status in {
                PayloadAGT.STATUS_PREPARADO,
                PayloadAGT.STATUS_NAO_ENVIADO,
            }:
                relatorio["payloads_preparados_nao_enviados"].append({
                    "payload_id": payload.pk,
                    "status": payload.status,
                    "submission_uuid": payload.submission_uuid,
                    "documentos": pares,
                })

            # Resultados sem confirmação definitiva.
            indeterminado = bool(
                getattr(payload, "resultado_indeterminado", False)
            )

            if payload.status == PayloadAGT.STATUS_ENVIADO:
                enviado_em = getattr(payload, "enviado_em", None)

                if enviado_em and enviado_em <= limite:
                    indeterminado = True

            if indeterminado:
                relatorio["payloads_com_resultado_indeterminado"].append({
                    "payload_id": payload.pk,
                    "submission_uuid": payload.submission_uuid,
                    "request_id": payload.request_id,
                    "erro": payload.erro[:500],
                })

        # -----------------------------------------------------------
        # B. Verificar todos os documentos fiscais emitidos.
        # -----------------------------------------------------------
        for documento in documentos:
            par = (
                documento.tipo_documento,
                documento.numero_documento,
            )

            # Payloads com JSON real que contêm exactamente este par.
            candidatos = [
                payload
                for payload in payloads
                if (
                    cls._tem_json_real(payload)
                    and par in set(pares_por_payload[payload.pk])
                )
            ]

            # Adicionar relações M2M existentes, mas não contar
            # erros de preparação como captura real.
            relacionados = list(documento.payloads_agt.all())

            for payload in relacionados:
                pares_envelope = set(
                    pares_por_payload.get(payload.pk, [])
                )

                if (
                    cls._tem_json_real(payload)
                    and par in pares_envelope
                    and payload.pk not in {p.pk for p in candidatos}
                ):
                    candidatos.append(payload)

            candidatos_ids = {p.pk for p in candidatos}

            # Se existe uma única correspondência real, reparar a relação
            # M2M caso esteja em falta.
            if len(candidatos) == 1:
                payload = candidatos[0]

                if not payload.documentos.filter(pk=documento.pk).exists():
                    relatorio["documentos_reconciliados"].append({
                        "documento_id": documento.pk,
                        "numero": documento.numero_documento,
                        "payload_id": payload.pk,
                    })

                    if not dry_run:
                        payload.documentos.add(documento)

                        cls._evento(
                            documento,
                            "PAYLOAD_RECONCILIADO",
                            (
                                f"documento:{documento.pk}:"
                                f"payload_reconciliado:{payload.pk}"
                            ),
                            "Documento local associado ao envelope encontrado.",
                            payload,
                            {
                                "payload_id": payload.pk,
                                "submission_uuid": payload.submission_uuid,
                            },
                        )

            if len(candidatos) > 1:
                relatorio["documentos_com_multiplos_payloads"].append({
                    "documento_id": documento.pk,
                    "numero": documento.numero_documento,
                    "payload_ids": sorted(candidatos_ids),
                })

            # Um erro de preparação não é um payload capturado.
            if not candidatos:
                emitted_at = cls._data_emissao(documento)

                # Dar tempo à task de submissão para iniciar e construir.
                if emitted_at and emitted_at > limite:
                    continue

                erros_preparacao = [
                    payload for payload in relacionados
                    if payload.status == PayloadAGT.STATUS_ERRO_PREPARACAO
                ]

                ocorrencia = {
                    "documento_id": documento.pk,
                    "tipo": documento.tipo_documento,
                    "numero": documento.numero_documento,
                    "estado": documento.status,
                    "motivo": (
                        "ERRO_PREPARACAO"
                        if erros_preparacao
                        else "SEM_PAYLOAD_CAPTURADO"
                    ),
                    "payloads_erro_preparacao": [
                        payload.pk for payload in erros_preparacao
                    ],
                }

                relatorio["documentos_sem_payload"].append(ocorrencia)

                if not dry_run:
                    cls._evento(
                        documento,
                        "DOCUMENTO_SEM_PAYLOAD",
                        f"documento:{documento.pk}:sem_payload",
                        (
                            "Documento emitido sem envelope JSON capturado. "
                            f"Motivo: {ocorrencia['motivo']}."
                        ),
                        dados=ocorrencia,
                    )

        logger.info(
            "[%s] Reconciliação Inspector AGT concluída: "
            "documentos=%d sem_payload=%d reparados=%d dry_run=%s",
            schema,
            relatorio["documentos_analisados"],
            len(relatorio["documentos_sem_payload"]),
            len(relatorio["documentos_reconciliados"]),
            dry_run,
        )

        return relatorio
