"""Histórico tenant-local dos payloads construídos para a API AGT.

Importar PayloadAGT no final de apps/fiscal/models.py para o Django registar
este modelo na app fiscal e criar a migração correspondente.
"""
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class PayloadAGT(TimeStampedModel):
    STATUS_PREPARADO = "preparado"
    STATUS_ENVIADO = "enviado"
    STATUS_RESPOSTA = "resposta"
    STATUS_FALHOU = "falhou"
    STATUS_NAO_ENVIADO = "nao_enviado"
    STATUS_ERRO_PREPARACAO = "erro_preparacao"

    STATUS_CHOICES = [
        (STATUS_PREPARADO, "Preparado — ainda não enviado"),
        (STATUS_ENVIADO, "Pedido enviado — aguardando resposta"),
        (STATUS_RESPOSTA, "Resposta recebida"),
        (STATUS_FALHOU, "Falha de comunicação ou resposta HTTP de erro"),
        (STATUS_NAO_ENVIADO, "Não enviado — configuração/credenciais em falta"),
        (STATUS_ERRO_PREPARACAO, "Erro ao construir o payload"),
    ]

    AMBIENTE_CHOICES = [
        ("HOMOLOGACAO", "Homologação"),
        ("PRODUCTION", "Produção"),
        ("DESCONHECIDO", "Desconhecido"),
    ]

    # Um pedido AGT pode transportar um ou vários documentos.
    documentos = models.ManyToManyField(
        "fiscal.DocumentoFiscal",
        blank=True,
        related_name="payloads_agt",
        verbose_name="Documentos fiscais associados",
    )

    submission_uuid = models.CharField(max_length=64, blank=True, db_index=True)
    tipo_documento = models.CharField(
        max_length=8,
        blank=True,
        help_text="Tipo do único documento ou MULTI quando o pedido inclui tipos diferentes.",
    )
    numero_documento = models.CharField(
        max_length=200,
        blank=True,
        help_text="Número do documento ou resumo do pedido multi-documento.",
    )
    quantidade_documentos = models.PositiveSmallIntegerField(default=0)
    ambiente = models.CharField(
        max_length=20,
        choices=AMBIENTE_CHOICES,
        default="DESCONHECIDO",
        db_index=True,
    )
    endpoint = models.CharField(max_length=512, blank=True)

    # Snapshot do JSON realmente construído para o corpo HTTP. Não inclui Basic Auth.
    payload = models.JSONField(default=dict)
    resposta = models.JSONField(default=dict, blank=True)

    assinatura_pedido_presente = models.BooleanField(default=False)
    assinatura_software_presente = models.BooleanField(default=False)
    assinaturas_documentos_presentes = models.BooleanField(default=False)

    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_PREPARADO,
        db_index=True,
    )
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    request_id = models.CharField(max_length=200, blank=True, db_index=True)
    erro = models.TextField(blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    resposta_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Payload AGT"
        verbose_name_plural = "Payloads AGT"
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="payagt_status_created_idx"),
            models.Index(fields=["tipo_documento", "created_at"], name="payagt_type_created_idx"),
        ]
        permissions = [
            ("inspect_payloadagt", "Pode consultar e copiar payloads fiscais AGT"),
        ]

    def __str__(self):
        ref = self.numero_documento or self.submission_uuid or str(self.pk)
        return f"Payload AGT {ref} ({self.get_status_display()})"
