"""Modelos adicionais da área comercial de parceiros (tabelas no schema public).

Importar estes modelos no fim de apps/parceiros/models.py. Não mover esta app para
TENANT_APPS: o programa de parceiros é global, e as relações para Empresa/Licenca
são referências às tabelas partilhadas no schema public.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.parceiros.models import Partner, PartnerClient
from apps.parceiros.private_storage import PartnerPrivateStorage


class PartnerCommission(TimeStampedModel):
    """Livro-razão de comissões de 10%; só pagamentos confirmados são elegíveis."""
    TIPO_CHOICES = [
        ("novo_cliente", "Novo cliente"),
        ("renovacao", "Renovação de licença"),
    ]
    STATUS_CHOICES = [
        ("aguarda_confirmacao", "Aguarda confirmação do pagamento"),
        ("confirmada", "Comissão confirmada"),
        ("paga", "Comissão paga"),
        ("rejeitada", "Pagamento não confirmado"),
        ("cancelada", "Cancelada"),
    ]

    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="comissoes_10pct")
    partner_client = models.ForeignKey(PartnerClient, on_delete=models.PROTECT, related_name="comissoes")
    licenca_cliente = models.ForeignKey(
        "licenca.Licenca", on_delete=models.PROTECT, null=True, blank=True,
        related_name="comissoes_parceiros",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    chave_evento = models.CharField(max_length=160, unique=True)
    # Periodo autorizado; a licença só se activa/renova após confirmação de recebimento.
    periodo_meses = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(36)],
        help_text="Duração da licença a aplicar depois de a equipa SOTARQ confirmar o pagamento.",
    )
    base_calculo = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal("0.00"))])
    percentagem = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    valor_comissao = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="aguarda_confirmacao", db_index=True)
    comprovativo_referencia = models.CharField(max_length=180, blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comissoes_parceiros_criadas",
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comissoes_parceiros_confirmadas",
    )
    confirmado_em = models.DateTimeField(null=True, blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Comissão de Parceiro"
        verbose_name_plural = "Comissões de Parceiros"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["partner", "status", "created_at"])]

    def save(self, *args, **kwargs):
        self.valor_comissao = (self.base_calculo * self.percentagem / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.partner.nome} — {self.valor_comissao} AOA ({self.get_status_display()})"


class PartnerBusinessEvent(TimeStampedModel):
    """Timeline/auditável para a área de funcionários e alertas do parceiro."""
    TIPO_CHOICES = [
        ("tenant_criado", "Tenant registado"),
        ("pagamento_pendente", "Pagamento por confirmar"),
        ("pagamento_confirmado", "Pagamento confirmado"),
        ("renovacao", "Licença renovada"),
        ("licenca_a_vencer", "Licença prestes a expirar"),
        ("licenca_expirada", "Licença expirada"),
        ("licenca_nao_renovada", "Licença ainda não renovada"),
        ("parceiro_inactivo", "Parceiro inactivo"),
        ("parceiro_reativado", "Parceiro reactivado"),
        ("alerta_staff", "Alerta da equipa"),
    ]
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="eventos_comerciais")
    partner_client = models.ForeignKey(
        PartnerClient, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos_comerciais",
    )
    licenca_cliente = models.ForeignKey(
        "licenca.Licenca", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos_comerciais_parceiros",
    )
    tipo = models.CharField(max_length=32, choices=TIPO_CHOICES, db_index=True)
    chave_evento = models.CharField(max_length=180, unique=True)
    titulo = models.CharField(max_length=220)
    descricao = models.TextField(blank=True)
    dados = models.JSONField(default=dict, blank=True)
    visivel_parceiro = models.BooleanField(default=True)
    resolvido = models.BooleanField(default=False, db_index=True)
    resolvido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="eventos_parceiros_resolvidos",
    )
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Evento Comercial de Parceiro"
        verbose_name_plural = "Eventos Comerciais de Parceiros"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["partner", "tipo", "created_at"])]

    def marcar_resolvido(self, utilizador):
        if not self.resolvido:
            self.resolvido = True
            self.resolvido_por = utilizador
            self.resolvido_em = timezone.now()
            self.save(update_fields=["resolvido", "resolvido_por", "resolvido_em", "updated_at"])

    def __str__(self):
        return f"{self.partner.nome} — {self.titulo}"


class PartnerReactivationRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("aprovado", "Aprovado"),
        ("rejeitado", "Rejeitado"),
    ]
    partner = models.ForeignKey(Partner, on_delete=models.PROTECT, related_name="pedidos_reativacao")
    motivo = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pendente", db_index=True)
    resposta = models.TextField(blank=True)
    respondido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pedidos_reativacao_parceiros_respondidos",
    )
    respondido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Pedido de Reactivação de Parceiro"
        verbose_name_plural = "Pedidos de Reactivação de Parceiros"
        ordering = ["-created_at"]
        permissions = [("manage_partner_reactivation", "Pode gerir pedidos de reactivação de parceiros")]

    def __str__(self):
        return f"{self.partner.nome} — reactivação ({self.get_status_display()})"


class PartnerConversation(TimeStampedModel):
    """Conversa de suporte entre parceiro/equipa ou entre dois parceiros."""
    TIPO_CHOICES = [
        ("partner_staff", "Parceiro e equipa SOTARQ"),
        ("partner_partner", "Entre parceiros"),
        ("staff_interno", "Equipa SOTARQ"),
    ]
    tipo = models.CharField(max_length=24, choices=TIPO_CHOICES, db_index=True)
    titulo = models.CharField(max_length=180)
    ativa = models.BooleanField(default=True, db_index=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="conversas_parceiros_criadas",
    )
    ultimo_evento_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Conversa do Portal de Parceiros"
        verbose_name_plural = "Conversas do Portal de Parceiros"
        ordering = ["-ultimo_evento_em", "-pk"]

    def __str__(self):
        return self.titulo


class PartnerConversationParticipant(TimeStampedModel):
    conversa = models.ForeignKey(PartnerConversation, on_delete=models.CASCADE, related_name="participantes")
    partner = models.ForeignKey(
        Partner, on_delete=models.CASCADE, null=True, blank=True,
        related_name="participacoes_conversas",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
        related_name="participacoes_conversas_parceiros",
    )

    class Meta:
        verbose_name = "Participante de Conversa de Parceiros"
        verbose_name_plural = "Participantes de Conversas de Parceiros"
        constraints = [
            models.UniqueConstraint(fields=["conversa", "partner"], name="uniq_partner_chat_partner"),
            models.UniqueConstraint(fields=["conversa", "usuario"], name="uniq_partner_chat_user"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.partner_id) == bool(self.usuario_id):
            raise ValidationError("O participante deve ser um parceiro ou um utilizador interno, nunca ambos.")
        if self.conversa_id and self.conversa.tipo == "partner_partner" and self.usuario_id:
            raise ValidationError("Conversas entre parceiros não aceitam funcionários como participantes normais.")
        if self.conversa_id and self.conversa.tipo == "staff_interno" and self.partner_id:
            raise ValidationError("Conversas internas não aceitam parceiros externos.")

    def __str__(self):
        return f"Participante da conversa #{self.conversa_id}"


class PartnerMessage(TimeStampedModel):
    conversa = models.ForeignKey(PartnerConversation, on_delete=models.CASCADE, related_name="mensagens")
    autor_partner = models.ForeignKey(
        Partner, on_delete=models.PROTECT, null=True, blank=True, related_name="mensagens_enviadas",
    )
    autor_usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mensagens_portal_parceiros",
    )
    texto = models.TextField(blank=True)
    # Configure o storage deste campo como privado. As views não expõem o URL do storage.
    anexo = models.FileField(upload_to="partner_private/%Y/%m/", storage=PartnerPrivateStorage(), null=True, blank=True)
    comissao = models.ForeignKey(PartnerCommission, on_delete=models.SET_NULL, null=True, blank=True, related_name="mensagens_comprovativo")
    nome_original_anexo = models.CharField(max_length=255, blank=True)
    tipo_conteudo_anexo = models.CharField(max_length=120, blank=True)

    class Meta:
        verbose_name = "Mensagem do Portal de Parceiros"
        verbose_name_plural = "Mensagens do Portal de Parceiros"
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["conversa", "created_at"])]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.autor_partner_id) == bool(self.autor_usuario_id):
            raise ValidationError("Uma mensagem deve ter exactamente um autor.")
        if not (self.texto or "").strip() and not self.anexo:
            raise ValidationError("A mensagem precisa de texto ou anexo.")
        if self.autor_partner_id:
            if not self.conversa.participantes.filter(partner_id=self.autor_partner_id).exists():
                raise ValidationError("O parceiro remetente não participa nesta conversa.")
        elif self.autor_usuario_id:
            if not self.conversa.participantes.filter(usuario_id=self.autor_usuario_id).exists():
                raise ValidationError("O funcionário remetente não participa nesta conversa.")

    def __str__(self):
        return f"Mensagem #{self.pk} na conversa #{self.conversa_id}"
