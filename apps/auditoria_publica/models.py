# apps/auditoria_publica/models.py
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel
from apps.empresas.models import Empresa

class LogAuditoriaPublica(TimeStampedModel):
    """
    Rastro de auditoria de nível infraestrutura.
    Monitora ações que impactam o ecossistema SOTARQ globalmente.
    """
    TIPO_EVENTO_CHOICES = [
        ('SISTEMA', 'Manutenção de Sistema'),
        ('TENANT_CRUD', 'Gestão de Empresas/Clientes'),
        ('LICENCA', 'Gestão de Licenciamento'),
        ('SEGURANCA', 'Segurança e Acessos Admin'),
        ('MIGRATION', 'Alterações de Base de Dados'),
    ]

    NIVEL_CHOICES = [
        ('INFO', 'Informação'),
        ('AVISO', 'Aviso/Risco'),
        ('CRITICO', 'Erro Crítico/Invasão'),
    ]

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='logs_publicos'
    )
    # Referência opcional à empresa (se o evento for disparado por uma ação em um Tenant)
    empresa_relacionada = models.ForeignKey(
        Empresa, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    tipo_evento = models.CharField(max_length=20, choices=TIPO_EVENTO_CHOICES)
    nivel = models.CharField(max_length=10, choices=NIVEL_CHOICES, default='INFO')
    acao = models.CharField(max_length=255, help_text="Ex: Criação de novo Tenant 'Farmácia Central'")
    
    # Detalhes técnicos em JSON para flexibilidade
    dados_contexto = models.JSONField(default=dict, blank=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = "Log de Auditoria Pública"
        verbose_name_plural = "Logs de Auditoria Pública"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.tipo_evento}] {self.acao} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"