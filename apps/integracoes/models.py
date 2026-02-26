# apps/integracoes/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json
from cryptography.fernet import Fernet
from django.conf import settings

class TipoIntegracao(models.Model):
    """Tipos de integração disponíveis"""
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=50, unique=True)
    descricao = models.TextField(blank=True)
    icone = models.CharField(max_length=50, default='fas fa-plug')
    ativo = models.BooleanField(default=True)
    
    # Configurações da API
    url_base = models.URLField(blank=True)
    metodo_autenticacao = models.CharField(max_length=50, choices=[
        ('api_key', 'API Key'),
        ('bearer_token', 'Bearer Token'),
        ('oauth2', 'OAuth 2.0'),
        ('basic_auth', 'Basic Auth'),
    ], default='api_key')
    
    # Documentação
    url_documentacao = models.URLField(blank=True)
    
    class Meta:
        verbose_name = 'Tipo de Integração'
        verbose_name_plural = 'Tipos de Integração'
        
    def __str__(self):
        return self.nome

class ConfiguracaoIntegracao(models.Model):
    """Configurações de integração por empresa"""
    empresa = models.ForeignKey('empresas.Empresa', on_delete=models.CASCADE, related_name='integracoes_sistema')
    tipo_integracao = models.ForeignKey(TipoIntegracao, on_delete=models.CASCADE)
    
    # Status
    ativa = models.BooleanField(default=False)
    configurada = models.BooleanField(default=False)
    
    # Credenciais (criptografadas)
    credenciais_criptografadas = models.TextField(blank=True)
    
    # Configurações específicas
    configuracoes = models.JSONField(default=dict)
    
    # Limites e controles
    limite_requests_dia = models.IntegerField(default=1000)
    requests_utilizadas_hoje = models.IntegerField(default=0)
    ultima_utilizacao = models.DateTimeField(null=True, blank=True)
    
    # Logs
    ultima_sincronizacao = models.DateTimeField(null=True, blank=True)
    erro_ultima_sincronizacao = models.TextField(blank=True)
    
    criada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Configuração de Integração'
        verbose_name_plural = 'Configurações de Integração'
        unique_together = ['empresa', 'tipo_integracao']
        
    def __str__(self):
        return f"{self.empresa.nome} - {self.tipo_integracao.nome}"
    
    def set_credenciais(self, credenciais_dict):
        """Criptografar e armazenar credenciais"""
        if hasattr(settings, 'ENCRYPTION_KEY'):
            f = Fernet(settings.ENCRYPTION_KEY)
            credenciais_json = json.dumps(credenciais_dict)
            self.credenciais_criptografadas = f.encrypt(credenciais_json.encode()).decode()
    
    def get_credenciais(self):
        """Descriptografar e retornar credenciais"""
        if not self.credenciais_criptografadas:
            return {}
        
        if hasattr(settings, 'ENCRYPTION_KEY'):
            f = Fernet(settings.ENCRYPTION_KEY)
            credenciais_json = f.decrypt(self.credenciais_criptografadas.encode()).decode()
            return json.loads(credenciais_json)
        return {}

class LogIntegracao(models.Model):
    """Log de chamadas para integrações"""
    TIPO_CHOICES = [
        ('request', 'Request'),
        ('response', 'Response'),
        ('error', 'Erro'),
        ('webhook', 'Webhook'),
    ]
    
    STATUS_CHOICES = [
        ('sucesso', 'Sucesso'),
        ('erro', 'Erro'),
        ('timeout', 'Timeout'),
        ('limite_excedido', 'Limite Excedido'),
    ]
    
    configuracao = models.ForeignKey(ConfiguracaoIntegracao, on_delete=models.CASCADE, related_name='logs')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    
    # Detalhes da requisição
    metodo = models.CharField(max_length=10)
    url = models.URLField()
    headers = models.JSONField(default=dict)
    payload = models.TextField(blank=True)
    
    # Resposta
    status_code = models.IntegerField(null=True, blank=True)
    response_data = models.TextField(blank=True)
    tempo_resposta = models.FloatField(null=True, blank=True)  # em segundos
    
    # Contexto
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    contexto = models.JSONField(default=dict)  # IDs de venda, produto, etc.
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Log de Integração'
        verbose_name_plural = 'Logs de Integração'
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"{self.configuracao.tipo_integracao.nome} - {self.get_status_display()}"

class WebhookIntegracao(models.Model):
    """Webhooks recebidos de integrações"""
    configuracao = models.ForeignKey(ConfiguracaoIntegracao, on_delete=models.CASCADE, related_name='webhooks')
    
    # Dados do webhook
    headers = models.JSONField(default=dict)
    payload = models.TextField()
    assinatura = models.CharField(max_length=255, blank=True)
    
    # Processamento
    processado = models.BooleanField(default=False)
    processado_em = models.DateTimeField(null=True, blank=True)
    erro_processamento = models.TextField(blank=True)
    
    recebido_em = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Webhook'
        verbose_name_plural = 'Webhooks'
        ordering = ['-recebido_em']


