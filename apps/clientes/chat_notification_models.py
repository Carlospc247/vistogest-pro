# apps/clientes/chat_notification_models.py
"""Outbox idempotente de alertas assíncronos do chat, guardada no schema do tenant."""
from datetime import timedelta
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel
from apps.clientes.models import MensagemChat


class EntregaNotificacaoChat(TimeStampedModel):
    ESTADO_CHOICES = [
        ("pendente", "Pendente"),
        ("processando", "Em processamento"),
        ("enviada", "Enviada"),
        ("sem_destinatario", "Sem destinatário"),
        ("erro", "Erro"),
    ]
    mensagem = models.OneToOneField(MensagemChat, on_delete=models.CASCADE, related_name="entrega_alerta_email")
    estado = models.CharField(max_length=24, choices=ESTADO_CHOICES, default="pendente", db_index=True)
    tentativas = models.PositiveIntegerField(default=0)
    destinatarios = models.JSONField(default=list, blank=True)
    processamento_iniciado_em = models.DateTimeField(null=True, blank=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)

    class Meta:
        verbose_name = "Entrega de Alerta do Chat"
        verbose_name_plural = "Entregas de Alertas do Chat"
        indexes = [models.Index(fields=["estado", "updated_at"])]

    def marcar_enviada(self, destinatarios):
        self.estado = "enviada"
        self.destinatarios = list(destinatarios)
        self.enviada_em = timezone.now()
        self.processamento_iniciado_em = None
        self.ultimo_erro = ""
        self.save(update_fields=["estado", "destinatarios", "enviada_em", "processamento_iniciado_em", "ultimo_erro", "updated_at"])
