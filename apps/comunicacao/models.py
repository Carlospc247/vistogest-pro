"""Tenant-local chat shared by customer support and employee groups."""
from django.conf import settings
from django.db import models
from cloudinary.models import CloudinaryField
from apps.core.models import TimeStampedModel


class Conversa(TimeStampedModel):
    TIPO_CHOICES = [("cliente", "Cliente e empresa"), ("funcionarios", "Grupo de funcionários")]
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    titulo = models.CharField(max_length=180, blank=True)
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.CASCADE, related_name="conversas_chat")
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversas_chat_criadas")
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self):
        return self.titulo or f"Conversa #{self.pk}"


class ParticipanteConversa(TimeStampedModel):
    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="participantes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="participacoes_chat")
    cliente_site = models.ForeignKey("site.ClienteSite", null=True, blank=True, on_delete=models.CASCADE, related_name="participacoes_chat")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["conversa", "usuario"], name="uniq_chat_conversa_usuario"),
            models.UniqueConstraint(fields=["conversa", "cliente_site"], name="uniq_chat_conversa_cliente_site"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.usuario_id) == bool(self.cliente_site_id):
            raise ValidationError("Uma participação deve identificar exactamente um utilizador ou cliente do site.")
        if self.conversa.tipo == "funcionarios" and self.cliente_site_id:
            raise ValidationError("Grupos de funcionários não podem conter contas de clientes.")


class MensagemChat(TimeStampedModel):
    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name="mensagens")
    autor_usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="mensagens_chat")
    autor_cliente_site = models.ForeignKey("site.ClienteSite", null=True, blank=True, on_delete=models.SET_NULL, related_name="mensagens_chat")
    texto = models.TextField(blank=True)
    anexo = CloudinaryField("anexo", resource_type="auto", blank=True, null=True)
    mencoes = models.JSONField(default=list, blank=True, help_text="Links resolvidos no servidor a partir de referências permitidas.")

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["conversa", "created_at"])]

    def clean(self):
        from django.core.exceptions import ValidationError
        if bool(self.autor_usuario_id) == bool(self.autor_cliente_site_id):
            raise ValidationError("Uma mensagem deve ter exactamente um autor.")
        if not self.texto.strip() and not self.anexo:
            raise ValidationError("A mensagem precisa de texto ou anexo.")

    def __str__(self):
        return f"Mensagem #{self.pk} na conversa #{self.conversa_id}"
