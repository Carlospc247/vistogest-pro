# apps/servicos/tracking_models.py
"""Timeline and two-way message records for a specific service appointment.

Import EventoAgendamento from this module at the bottom of apps/servicos/models.py
so Django registers the model. Then generate and apply migrations.
"""
from django.conf import settings
from django.db import models
from cloudinary.models import CloudinaryField
from apps.core.models import TimeStampedModel


class EventoAgendamento(TimeStampedModel):
    TIPOS = [
        ("criado", "Agendamento criado"),
        ("iniciado", "Serviço iniciado"),
        ("pausado", "Serviço pausado"),
        ("retomado", "Serviço retomado"),
        ("adiado", "Serviço adiado"),
        ("cancelado", "Serviço cancelado"),
        ("finalizado", "Serviço finalizado"),
        ("mensagem_empresa", "Mensagem da empresa"),
        ("mensagem_cliente", "Mensagem do cliente"),
        ("notificacao", "Notificação"),
        ("correcao", "Pedido de esclarecimento/correcção"),
    ]

    agendamento = models.ForeignKey(
        "servicos.AgendamentoServico",
        on_delete=models.CASCADE,
        related_name="eventos_acompanhamento",
    )
    tipo = models.CharField(max_length=24, choices=TIPOS, db_index=True)
    titulo = models.CharField(max_length=180)
    descricao = models.TextField(blank=True)
    visivel_cliente = models.BooleanField(default=True, db_index=True)
    autor_usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_servico_criados",
    )
    autor_cliente_site = models.ForeignKey(
        "site.ClienteSite",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_servico_criados",
    )
    anexo = CloudinaryField("anexo", resource_type="auto", blank=True, null=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["agendamento", "created_at"])]

    def __str__(self):
        return f"{self.get_tipo_display()} — agendamento {self.agendamento_id}"
