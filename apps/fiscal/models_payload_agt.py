# apps/fiscal/models_payload_agt.py
"""Histórico tenant-local dos payloads construídos para a API AGT.

Importar PayloadAGT no final de apps/fiscal/models.py para o Django registar
este modelo na app fiscal e criar a migração correspondente.
"""
from django.db import models
from django.db.models import Q
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
    resultado_indeterminado = models.BooleanField(default=False, db_index=True,
        help_text="True quando o POST foi iniciado mas não há confirmação do resultado remoto.",
    )
    payload_json = models.TextField(
        blank=True,
        help_text="Texto JSON exacto usado no corpo HTTP enviado à AGT.",
    )
    hash_payload = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="SHA-256 dos bytes UTF-8 de payload_json.",
    )
    associacao_resultado = models.JSONField(default=dict, blank=True)
   
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
        
        constraints = [
        # Restrição de unicidade para evitar reutilização
        # de submissionUUID em diferentes conteúdos.
        models.UniqueConstraint(
            fields=("submission_uuid",),
            condition=~models.Q(submission_uuid=""),
            name="uniq_payagt_submission_uuid",
        ),
        ]
        permissions = [
            ("inspect_payloadagt", "Pode consultar e copiar payloads fiscais AGT"),
        ]

    def __str__(self):
        ref = self.numero_documento or self.submission_uuid or str(self.pk)
        return f"Payload AGT {ref} ({self.get_status_display()})"


class EventoAuditoriaPayloadAGT(models.Model):
    """
    Cronologia dos acontecimentos observados pelo Inspector AGT.

    Tenant-local: cada evento pertence ao schema onde o DocumentoFiscal
    e o PayloadAGT estão registados.
    """

    TIPOS_EVENTO = [
        ("DOCUMENTO_EMITIDO", "Documento emitido"),
        ("AGUARDANDO_PAYLOAD", "Aguardando payload"),
        ("NAO_APLICAVEL", "Não aplicável à submissão AGT"),
        ("SUBMISSAO_AGENDADA", "Submissão agendada"),
        ("ERRO_AGENDAMENTO", "Erro ao agendar submissão"),
        ("PAYLOAD_CAPTURADO", "Payload capturado"),
        ("ERRO_PREPARACAO", "Erro de preparação"),
        ("PEDIDO_ENVIADO", "Pedido enviado"),
        ("RESPOSTA_RECEBIDA", "Resposta recebida"),
        ("FALHA_COMUNICACAO", "Falha de comunicação"),
        ("RESULTADO_INDETERMINADO", "Resultado indeterminado"),
        ("DOCUMENTO_SEM_PAYLOAD", "Documento emitido sem payload"),
        ("PAYLOAD_RECONCILIADO", "Payload localizado pela reconciliação"),
        ("AUDITORIA_EXECUTADA", "Auditoria técnica executada"),
        ("DOCUMENTO_VALIDADO", "Documento validado pela AGT"),
        ("DOCUMENTO_REJEITADO", "Documento rejeitado pela AGT"),
    ]

    documento = models.ForeignKey(
        "fiscal.DocumentoFiscal",
        on_delete=models.PROTECT,
        related_name="eventos_payload_agt",
        verbose_name="Documento fiscal",
    )

    payload = models.ForeignKey(
        "fiscal.PayloadAGT",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
        verbose_name="Payload relacionado",
    )

    tipo_evento = models.CharField(
        max_length=40,
        choices=TIPOS_EVENTO,
        db_index=True,
        verbose_name="Tipo de evento",
    )

    idempotency_key = models.CharField(
        max_length=180,
        unique=True,
        verbose_name="Chave de idempotência",
    )

    descricao = models.TextField(
        blank=True,
        verbose_name="Descrição técnica",
    )

    dados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Dados complementares",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="Data do acontecimento",
    )

    class Meta:
        verbose_name = "Evento de auditoria de Payload AGT"
        verbose_name_plural = "Eventos de auditoria de Payload AGT"
        ordering = ["-criado_em", "-pk"]

    def __str__(self):
        return (
            f"{self.tipo_evento} | "
            f"{self.documento.numero_documento}"
        )


class AuditoriaPayloadAGT(models.Model):
    ESTADOS = [
        ("CONFORME", "Conforme estruturalmente"),
        ("AVISO", "Conforme com avisos"),
        ("ERRO", "Com erros"),
        ("NAO_VERIFICAVEL", "Não verificável"),
    ]

    payload = models.ForeignKey(
        "fiscal.PayloadAGT",
        on_delete=models.CASCADE,
        related_name="auditorias",
    )
    versao_regras = models.CharField(max_length=40)
    estado = models.CharField(max_length=24, choices=ESTADOS, db_index=True)
    resumo = models.JSONField(default=dict, blank=True)
    resultados = models.JSONField(default=list, blank=True)
    executado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-executado_em", "-pk"]
        verbose_name = "Auditoria técnica de Payload AGT"
        verbose_name_plural = "Auditorias técnicas de Payload AGT"

    def __str__(self):
        return f"Auditoria Payload #{self.payload_id} — {self.estado}"


class ControloSubmissaoAGT(models.Model):
    """
    Claim persistente por DocumentoFiscal.

    Impede que tarefas Celery concorrentes criem UUIDs diferentes e submetam
    o mesmo documento duas vezes. O histórico de tentativas continua em
    PayloadAGT e EventoAuditoriaPayloadAGT.
    """
    ESTADOS = [
        ("PENDENTE", "Pendente"),
        ("SUBMETENDO", "Submissão em curso"),
        ("NAO_ENVIADO", "Não enviado — pode ser tentado novamente"),
        ("AGT_EM_PROCESSAMENTO", "A aguardar validação AGT"),
        ("RESULTADO_INDETERMINADO", "Resultado remoto indeterminado"),
        ("ERRO_PREPARACAO", "Erro de preparação"),
        ("FALHA_AGT", "Falha comunicada pela AGT"),
        ("AGT_VALIDADO", "Validado pela AGT"),
        ("AGT_REJEITADO", "Rejeitado pela AGT"),
    ]

    documento = models.OneToOneField(
        "fiscal.DocumentoFiscal",
        on_delete=models.PROTECT,
        related_name="controlo_submissao_agt",
    )
    estado = models.CharField(
        max_length=32,
        choices=ESTADOS,
        default="PENDENTE",
        db_index=True,
    )
    token_tentativa = models.UUIDField(null=True, blank=True, editable=False)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    ultimo_payload = models.ForeignKey(
        "fiscal.PayloadAGT",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="controlos_submissao",
    )
    submission_uuid = models.CharField(max_length=64, blank=True, db_index=True)
    request_id = models.CharField(max_length=200, blank=True, db_index=True)
    detalhe = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Controlo de submissão AGT"
        verbose_name_plural = "Controlos de submissão AGT"

    def __str__(self):
        return f"Controlo AGT — Documento #{self.documento_id} ({self.estado})"

