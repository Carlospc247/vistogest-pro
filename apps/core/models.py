# apps/core/models.py
from django.db import connection, models
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin
from django.conf import settings
import random




class TimeStampedModel(models.Model):
    """Modelo base com timestamps"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True




class Usuario(AbstractUser):
    # --- Campos de Relacionamento ---
    empresa = models.ForeignKey(
        'empresas.Empresa', 
        on_delete=models.CASCADE, 
        related_name='usuarios',
        null=True,
        blank=True
    )
    loja = models.ForeignKey(
        'empresas.Loja', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='usuarios'
    )

    # --- Campos de Identificação e Perfil ---
    telefone = models.CharField(max_length=20, blank=True)
    foto = CloudinaryField('foto', blank=True, null=True)
    
    e_administrador_empresa = models.BooleanField(
        "É Administrador da Empresa?",
        default=False,
        help_text="Se marcado, este utilizador pode gerir todas as lojas e utilizadores da sua empresa."
    )

    # --- Propriedades de Blindagem Multi-tenant (O Cérebro) ---

    @property
    def funcionario(self):
        """
        RIGOR SOTARQ: Intercepta a chamada antes que o Django dispare o SQL.
        No schema public, retornamos None imediatamente sem tocar no banco.
        """
        if connection.schema_name == 'public':
            return None
        
        try:
            from django.apps import apps
            FuncionarioModel = apps.get_model('funcionarios', 'Funcionario')
            # Usamos filter().first() para evitar exceções de DoesNotExist
            return FuncionarioModel.objects.filter(usuario=self).first()
        except (LookupError, Exception):
            return None

    @property
    def funcionario_profile(self):
        """Alias de compatibilidade para o perfil do funcionário."""
        return self.funcionario

    def get_funcionario(self):
        """Método auxiliar para recuperação segura do funcionário."""
        return self.funcionario
    
    def delete(self, *args, **kwargs):
        # 🛡️ RIGOR SOTARQ: Engenharia de Proteção de Schema
        if connection.schema_name == 'public':
            # Se estamos no public, deletamos via SQL bruto para saltar o 
            # Collector do Django que tenta buscar tabelas de inquilinos.
            with connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {self._meta.db_table} WHERE id = %s", 
                    [self.pk]
                )
            return 1 # Retorna o número de linhas afetadas
        
        # Comportamento normal para deleções dentro de inquilinos
        return super().delete(*args, **kwargs)

    def _get_pk_val(self, meta=None):
        return getattr(self, (meta or self._meta).pk.name)

    # --- Configurações do Modelo ---
    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
    
    def __str__(self):
        return self.username    


class AuditoriaAcesso(models.Model):
    ACAO_CHOICES = [
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('RESET_REQ', 'Solicitação de Reset de Senha'),
        ('RESET_CONF', 'Senha Alterada com Sucesso'),
    ]
    
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='logs_acesso') # settings.AUTH_USER_MODEL
    acao = models.CharField(max_length=10, choices=ACAO_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auditoria de Acesso"
        verbose_name_plural = "Auditorias de Acessos"
        ordering = ['-timestamp']

# apps/core/models.py

class IPConhecido(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='ips_conhecidos')
    ip_address = models.GenericIPAddressField()
    primeiro_acesso = models.DateTimeField(auto_now_add=True)
    ultimo_acesso = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('usuario', 'ip_address')


class VerificacaoSeguranca(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token = models.CharField(max_length=6)
    ip_address = models.GenericIPAddressField()
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    foi_verificado = models.BooleanField(default=False)

    def esta_valido(self):
        return not self.foi_verificado and timezone.now() < self.expira_em

    def gerar_token(self):
        self.token = str(random.randint(100000, 999999))
        self.expira_em = timezone.now() + timezone.timedelta(minutes=10)
        self.save()
        return self.token

