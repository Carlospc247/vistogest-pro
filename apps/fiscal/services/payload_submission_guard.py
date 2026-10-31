# apps/fiscal/services/payload_submission_guard.py
"""Claim SQL por DocumentoFiscal para impedir submissões concorrentes."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.models_payload_agt import ControloSubmissaoAGT

logger = logging.getLogger("fiscal.payload_submission_guard")
LEASE_MINUTES = 20


class PayloadSubmissionGuardService:
    @classmethod
    @transaction.atomic
    def reivindicar(cls, documento_id: int):
        schema = getattr(connection, "schema_name", "public")
        if not schema or schema == "public":
            raise RuntimeError("Submissão AGT proibida no schema public.")

        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento_id)

        try:
            with transaction.atomic():
                ControloSubmissaoAGT.objects.get_or_create(
                    documento=documento,
                    defaults={"estado": "PENDENTE"},
                )
        except IntegrityError:
            # Outra tarefa criou o OneToOne em simultâneo.
            pass

        controlo = ControloSubmissaoAGT.objects.select_for_update().get(
            documento=documento
        )

        if controlo.estado == "SUBMETENDO":
            iniciado = controlo.iniciado_em
            if iniciado and iniciado <= timezone.now() - timedelta(minutes=LEASE_MINUTES):
                controlo.estado = "RESULTADO_INDETERMINADO"
                controlo.detalhe = (
                    "Lease de submissão expirou sem conclusão registada. "
                    "Não reenviar automaticamente; reconciliar com a AGT."
                )
                controlo.save(update_fields=["estado", "detalhe", "atualizado_em"])
            return None

        permitidos = {"PENDENTE", "NAO_ENVIADO"}
        if controlo.estado not in permitidos:
            return None

        token = uuid.uuid4()
        controlo.estado = "SUBMETENDO"
        controlo.token_tentativa = token
        controlo.iniciado_em = timezone.now()
        controlo.detalhe = ""
        controlo.save(update_fields=[
            "estado", "token_tentativa", "iniciado_em", "detalhe", "atualizado_em"
        ])
        return token

    @classmethod
    @transaction.atomic
    def finalizar(
        cls,
        documento_id: int,
        token,
        estado: str,
        *,
        payload=None,
        submission_uuid: str = "",
        request_id: str = "",
        detalhe: str = "",
    ):
        controlo = (
            ControloSubmissaoAGT.objects.select_for_update()
            .get(documento_id=documento_id)
        )
        if controlo.token_tentativa != token:
            raise RuntimeError(
                "Token de submissão inválido: a tarefa já não detém o claim deste documento."
            )
        controlo.estado = estado
        controlo.ultimo_payload = payload
        controlo.submission_uuid = str(submission_uuid or "")[:64]
        controlo.request_id = str(request_id or "")[:200]
        controlo.detalhe = str(detalhe or "")[:3000]
        controlo.token_tentativa = None
        controlo.iniciado_em = None
        controlo.save(update_fields=[
            "estado", "ultimo_payload", "submission_uuid", "request_id",
            "detalhe", "token_tentativa", "iniciado_em", "atualizado_em",
        ])
        return controlo

    @classmethod
    @transaction.atomic
    def registar_resultado_polling(cls, documento_id: int, *, validado: bool, request_id: str, detalhe=""):
        controlo = (
            ControloSubmissaoAGT.objects.select_for_update()
            .filter(documento_id=documento_id)
            .first()
        )
        if not controlo:
            return None
        controlo.estado = "AGT_VALIDADO" if validado else "AGT_REJEITADO"
        controlo.request_id = str(request_id or "")[:200]
        controlo.detalhe = str(detalhe or "")[:3000]
        controlo.save(update_fields=["estado", "request_id", "detalhe", "atualizado_em"])
        return controlo
