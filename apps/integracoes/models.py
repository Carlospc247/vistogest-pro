# apps/integracoes/models.py
import secrets

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .services.crypto import cifrar_dict, decifrar_dict


def _novo_token():
    return secrets.token_urlsafe(24)


class TipoIntegracao(models.Model):
    """Catálogo de integrações suportadas (gerido por código/seed, não pelo utilizador)."""
    CATEGORIA_CHOICES = [
        ('fiscal', 'Fiscal'),
        ('pagamento', 'Pagamentos'),
        ('mensageria', 'Mensagens (WhatsApp/SMS)'),
        ('email', 'E-mail'),
        ('api', 'API / Webhook genérico'),
        ('outros', 'Outros'),
    ]
    AUTENTICACAO_CHOICES = [
        ('api_key', 'API Key'),
        ('bearer_token', 'Bearer Token'),
        ('oauth2', 'OAuth 2.0'),
        ('basic_auth', 'Basic Auth'),
        ('hmac', 'Assinatura HMAC'),
    ]

    nome = models.CharField(max_length=100)
    codigo = models.SlugField(max_length=50, unique=True)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='outros')
    descricao = models.TextField(blank=True)
    icone = models.CharField(max_length=50, default='fas fa-plug')
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=100)

    url_base = models.URLField(blank=True)
    metodo_autenticacao = models.CharField(max_length=20, choices=AUTENTICACAO_CHOICES, default='api_key')
    url_documentacao = models.URLField(blank=True)

    # [{"chave","label","segredo":bool,"obrigatorio":bool,"ajuda"}]
    esquema_credenciais = models.JSONField(default=list, blank=True)
    # [{"chave","label","tipo":"text|number|bool|choice","padrao","opcoes":[]}]
    esquema_configuracoes = models.JSONField(default=list, blank=True)
    suporta_webhook = models.BooleanField(default=False, help_text="Recebe eventos externos via webhook.")
    passos = models.JSONField(default=list, blank=True, help_text="Passos de configuração (lista de textos).")

    class Meta:
        verbose_name = 'Tipo de Integração'
        verbose_name_plural = 'Tipos de Integração'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return self.nome

    @property
    def implementado(self):
        from .services.providers import REGISTRO
        return self.codigo in REGISTRO


class ConfiguracaoIntegracao(models.Model):
    """Configuração de uma integração neste tenant (o schema já isola por empresa)."""
    AMBIENTE_CHOICES = [('sandbox', 'Teste (sandbox)'), ('producao', 'Produção')]
    STATUS_LABELS = {'ativa': 'Activa', 'inativa': 'Desactivada', 'incompleta': 'Incompleta', 'erro': 'Com erro'}

    tipo_integracao = models.OneToOneField(TipoIntegracao, on_delete=models.PROTECT, related_name='configuracao')
    ambiente = models.CharField(max_length=10, choices=AMBIENTE_CHOICES, default='sandbox')
    ativa = models.BooleanField(default=False)

    credenciais_criptografadas = models.TextField(blank=True)
    configuracoes = models.JSONField(default=dict, blank=True)

    # Comportamento do cliente HTTP
    timeout_segundos = models.PositiveSmallIntegerField(default=15)
    tentativas_max = models.PositiveSmallIntegerField(default=2)

    # Quota diária (reinicia sozinha a cada dia)
    limite_requests_dia = models.PositiveIntegerField(default=1000)
    requests_utilizadas_hoje = models.PositiveIntegerField(default=0)
    data_contagem = models.DateField(null=True, blank=True)
    ultima_utilizacao = models.DateTimeField(null=True, blank=True)

    # Estado
    ultima_sincronizacao = models.DateTimeField(null=True, blank=True)
    erro_ultima_sincronizacao = models.TextField(blank=True)
    ultimo_teste_em = models.DateTimeField(null=True, blank=True)
    ultimo_teste_ok = models.BooleanField(null=True, blank=True)

    # Webhook de entrada
    webhook_token = models.CharField(max_length=64, unique=True, default=_novo_token, editable=False)
    webhook_segredo_cifrado = models.TextField(blank=True, editable=False)

    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de Integração'
        verbose_name_plural = 'Configurações de Integração'

    def __str__(self):
        return self.tipo_integracao.nome

    # ── credenciais ─────────────────────────────────────────────────────────
    def set_credenciais(self, credenciais: dict):
        self.credenciais_criptografadas = cifrar_dict(credenciais) if credenciais else ''

    def get_credenciais(self) -> dict:
        return decifrar_dict(self.credenciais_criptografadas)

    def credenciais_mascaradas(self):
        cred = self.get_credenciais()
        saida = []
        for c in self.tipo_integracao.esquema_credenciais:
            valor = cred.get(c['chave'], '')
            if c.get('segredo') and valor:
                valor = '••••' + valor[-4:] if len(valor) > 8 else '••••'
            saida.append((c.get('label', c['chave']), valor or '—'))
        return saida

    @property
    def configurada(self):
        if not self.credenciais_criptografadas:
            return False
        try:
            cred = self.get_credenciais()
        except Exception:
            return False
        return all(cred.get(c['chave']) for c in self.tipo_integracao.esquema_credenciais
                   if c.get('obrigatorio', True))

    # ── estado ──────────────────────────────────────────────────────────────
    @property
    def status(self):
        if not self.configurada:
            return 'incompleta'
        if not self.ativa:
            return 'inativa'
        if self.ultimo_teste_ok is False or self.erro_ultima_sincronizacao:
            return 'erro'
        return 'ativa'

    @property
    def status_label(self):
        return self.STATUS_LABELS[self.status]

    # ── webhook ─────────────────────────────────────────────────────────────
    def get_webhook_segredo(self) -> str:
        return decifrar_dict(self.webhook_segredo_cifrado).get('s', '') if self.webhook_segredo_cifrado else ''

    def regenerar_webhook_segredo(self) -> str:
        novo = secrets.token_urlsafe(32)
        self.webhook_segredo_cifrado = cifrar_dict({'s': novo})
        return novo

    def save(self, *args, **kwargs):
        if not self.webhook_segredo_cifrado:
            self.regenerar_webhook_segredo()
        super().save(*args, **kwargs)

    # ── quota ───────────────────────────────────────────────────────────────
    def consumir_quota(self) -> bool:
        """Reserva 1 pedido da quota diária (atómico). False se o limite foi atingido."""
        hoje = timezone.localdate()
        with transaction.atomic():
            c = type(self).objects.select_for_update().get(pk=self.pk)
            if c.data_contagem != hoje:
                c.data_contagem, c.requests_utilizadas_hoje = hoje, 0
            if c.requests_utilizadas_hoje >= c.limite_requests_dia:
                return False
            c.requests_utilizadas_hoje += 1
            c.ultima_utilizacao = timezone.now()
            c.save(update_fields=['data_contagem', 'requests_utilizadas_hoje', 'ultima_utilizacao'])
        self.data_contagem = c.data_contagem
        self.requests_utilizadas_hoje = c.requests_utilizadas_hoje
        return True


class LogIntegracao(models.Model):
    """Uma linha por chamada (saída) ou por evento recebido (entrada)."""
    DIRECAO_CHOICES = [('saida', 'Saída'), ('entrada', 'Entrada')]
    STATUS_CHOICES = [
        ('sucesso', 'Sucesso'),
        ('erro', 'Erro'),
        ('timeout', 'Timeout'),
        ('limite_excedido', 'Limite excedido'),
    ]

    configuracao = models.ForeignKey(ConfiguracaoIntegracao, on_delete=models.CASCADE, related_name='logs')
    direcao = models.CharField(max_length=8, choices=DIRECAO_CHOICES, default='saida')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    metodo = models.CharField(max_length=10)
    url = models.URLField(max_length=2000)
    headers = models.JSONField(default=dict, blank=True)   # já mascarados
    payload = models.TextField(blank=True)                  # já mascarado e truncado

    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_data = models.TextField(blank=True)
    tempo_resposta = models.FloatField(null=True, blank=True)  # segundos
    tentativas = models.PositiveSmallIntegerField(default=1)

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='+')
    contexto = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Log de Integração'
        verbose_name_plural = 'Logs de Integração'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['configuracao', '-timestamp']),
            models.Index(fields=['status', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.configuracao} — {self.get_status_display()}"


class WebhookIntegracao(models.Model):
    """Eventos recebidos (apenas os que passaram a verificação de assinatura)."""
    configuracao = models.ForeignKey(ConfiguracaoIntegracao, on_delete=models.CASCADE, related_name='webhooks')
    evento = models.CharField(max_length=100, blank=True)
    identificador_externo = models.CharField(max_length=255, blank=True)
    ip_origem = models.GenericIPAddressField(null=True, blank=True)

    headers = models.JSONField(default=dict, blank=True)
    payload = models.TextField()
    assinatura = models.CharField(max_length=255, blank=True)

    processado = models.BooleanField(default=False)
    processado_em = models.DateTimeField(null=True, blank=True)
    erro_processamento = models.TextField(blank=True)
    tentativas_processamento = models.PositiveSmallIntegerField(default=0)

    recebido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Webhook'
        verbose_name_plural = 'Webhooks'
        ordering = ['-recebido_em']
        constraints = [
            models.UniqueConstraint(fields=['configuracao', 'identificador_externo'],
                                    condition=~Q(identificador_externo=''),
                                    name='uniq_webhook_id_por_config'),
        ]
        indexes = [models.Index(fields=['processado', '-recebido_em'])]

    def __str__(self):
        return f"{self.configuracao} — {self.evento or 'evento'} ({self.recebido_em:%d/%m/%Y %H:%M})"
