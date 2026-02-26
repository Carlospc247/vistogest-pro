# apps/analytics/models.py
from django.db import connection, models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import json
# apps/analytics/models.py
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from apps.core.models import TimeStampedModel
from apps.produtos.models import Lote, Fabricante
from apps.empresas.models import Empresa



# Para evitar que o "coletor" do Django tente encontrar a tabela no schema public e o sistema exploda novamente.
def is_managed():
    return connection.schema_name != 'public'



class EventoAnalytics(models.Model):
    """Eventos para analytics"""
    CATEGORIA_CHOICES = [
        ('navegacao', 'Navegação'),
        ('vendas', 'Vendas'),
        ('estoque', 'Estoque'),
        ('financeiro', 'Financeiro'),
        ('usuario', 'Usuário'),
        ('sistema', 'Sistema'),
        ('erro', 'Erro'),
    ]
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='eventos_analytics')
    usuario = models.ForeignKey('core.Usuario', on_delete=models.SET_NULL, null=True, blank=True)
    
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    acao = models.CharField(max_length=100)
    label = models.CharField(max_length=200, blank=True)
    
    propriedades = models.JSONField(default=dict)
    valor = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    url = models.URLField(blank=True)
    referrer = models.URLField(blank=True)
    
    pais = models.CharField(max_length=2, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        managed = is_managed()
        db_table = 'analytics_eventoanalytics'
        verbose_name = 'Evento Analytics'
        verbose_name_plural = 'Eventos Analytics'
        ordering = ['-timestamp']



class AuditoriaAlteracao(models.Model):
    """Log de auditoria para alterações em registros"""
    TIPO_OPERACAO_CHOICES = [
        ('create', 'Criação'),
        ('update', 'Alteração'),
        ('delete', 'Exclusão'),
    ]
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='auditorias')
    usuario = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    tipo_operacao = models.CharField(max_length=10, choices=TIPO_OPERACAO_CHOICES)
    
    dados_anteriores = models.JSONField(null=True, blank=True)
    dados_posteriores = models.JSONField(null=True, blank=True)
    campos_alterados = models.JSONField(default=list)
    
    motivo = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    
    class Meta:
        managed = is_managed()
        db_table = 'analytics_auditoriaalteracao'
        verbose_name = 'Auditoria'
        verbose_name_plural = 'Auditorias'
        ordering = ['-timestamp']



class AlertaInteligente(models.Model):
    """Sistema de alertas inteligentes"""
    TIPO_CHOICES = [
        ('estoque_baixo', 'Estoque Baixo'),
        ('vendas_baixas', 'Vendas Baixas'),
        ('erro_sistema', 'Erro do Sistema'),
        ('performance', 'Performance'),
        ('seguranca', 'Segurança'),
        ('financeiro', 'Financeiro'),
    ]
    
    PRIORIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]
    
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('resolvido', 'Resolvido'),
        ('ignorado', 'Ignorado'),
    ]
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='alertas')
    
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ativo')
    
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField()
    dados_contexto = models.JSONField(default=dict)
    
    acoes_sugeridas = models.JSONField(default=list)
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)
    resolvido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    
    usuarios_notificados = models.ManyToManyField(settings.AUTH_USER_MODEL, through='NotificacaoAlerta', related_name='alertas_recebidos')
    
    class Meta:
        managed = is_managed()
        db_table = 'analytics_alertainteligente'
        verbose_name = 'Alerta Inteligente'
        verbose_name_plural = 'Alertas Inteligentes'
        ordering = ['-created_at']


class NotificacaoAlerta(models.Model):
    """Notificações de alertas para usuários"""
    alerta = models.ForeignKey(AlertaInteligente, on_delete=models.CASCADE)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    enviada = models.BooleanField(default=False)
    lida = models.BooleanField(default=False)
    
    via_email = models.BooleanField(default=True)
    via_sistema = models.BooleanField(default=True)
    via_whatsapp = models.BooleanField(default=False)
    
    enviada_em = models.DateTimeField(null=True, blank=True)
    lida_em = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        managed = is_managed()
        db_table = 'analytics_notificacaoalerta'
        unique_together = ['alerta', 'usuario']

class DashboardPersonalizado(models.Model):
    """Dashboards personalizados por usuário"""
    usuario = models.ForeignKey('core.Usuario', on_delete=models.CASCADE, related_name='dashboards')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    
    layout = models.JSONField(default=dict)
    widgets = models.JSONField(default=list)
    filtros_padrao = models.JSONField(default=dict)
    
    padrao = models.BooleanField(default=False)
    publico = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        managed = is_managed()
        db_table = 'analytics_dashboardpersonalizado'
        verbose_name = 'Dashboard Personalizado'
        verbose_name_plural = 'Dashboards Personalizados'
        ordering = ['nome']


class AuditoriaInvestimento(TimeStampedModel):
    """
    Controla o acesso granular de Investidores/Auditores.
    Vincula o utilizador a ativos específicos (Lotes/Fabricantes).
    """
    usuario = models.OneToOneField(
        'core.Usuario', 
        on_delete=models.CASCADE, 
        related_name='vinculo_auditoria'
    )
    # Ativos vinculados para filtro restritivo
    lotes_vinculados = models.ManyToManyField(Lote, blank=True, verbose_name="Lotes Financiados")
    fabricantes_vinculados = models.ManyToManyField(Fabricante, blank=True, verbose_name="Fabricantes Financiados")
    
    # Permissões por Módulo (TENANT_APPS)
    pode_auditar_vendas = models.BooleanField(default=False)
    pode_auditar_estoque = models.BooleanField(default=False)
    pode_auditar_financeiro = models.BooleanField(default=False)
    pode_auditar_produtos = models.BooleanField(default=False)
    pode_auditar_fiscal = models.BooleanField(default=False)
    pode_auditar_tudo = models.BooleanField(default=False, help_text="Libera auditoria de todas as apps")

    class Meta:
        managed = is_managed()
        db_table = 'analytics_auditoriainvestimento'
        verbose_name = "Vínculo de Auditoria de Investimento"
        verbose_name_plural = "Vínculos de Auditoria de Investimento"

    def __str__(self):
        return f"Auditor: {self.usuario.username} - {self.usuario.empresa.nome}"

class RegistroAuditoriaOperacional(models.Model):
    """
    Log mestre de auditoria para o Tenant.
    Registra toda e qualquer mudança em registros das TENANT_APPS.
    """
    TIPO_OPERACAO_CHOICES = [
        ('CREATE', 'Criação'),
        ('UPDATE', 'Alteração'),
        ('DELETE', 'Exclusão'),
        ('SECURITY', 'Segurança/Permissão'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='logs_auditoria')
    usuario = models.ForeignKey('core.Usuario', on_delete=models.SET_NULL, null=True)
    
    # Rastreio genérico (ContentType)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # Contexto da Auditoria
    app_origem = models.CharField(max_length=50, help_text="Slug da app (ex: vendas, estoque)")
    operacao = models.CharField(max_length=10, choices=TIPO_OPERACAO_CHOICES)
    
    # Detalhes técnicos
    dados_anteriores = models.JSONField(null=True, blank=True)
    dados_posteriores = models.JSONField(null=True, blank=True)
    
    # Rastreio de Ativos (Para o Investidor)
    lote_relacionado = models.ForeignKey(Lote, on_delete=models.SET_NULL, null=True, blank=True)
    fabricante_relacionado = models.ForeignKey(Fabricante, on_delete=models.SET_NULL, null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = is_managed()
        db_table = 'analytics_registroauditoriaoperacional'
        verbose_name = "Registro de Auditoria Operacional"
        verbose_name_plural = "Registros de Auditoria Operacional"
        ordering = ['-timestamp']

