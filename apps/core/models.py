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
    telefone = models.CharField(max_length=20, blank=True)
    foto = CloudinaryField('foto', blank=True, null=True)
    
    empresa = models.ForeignKey(
        'empresas.Empresa',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usuarios',
        verbose_name="Empresa (Tenant)",
        help_text="Empresa/Tenant ao qual este utilizador pertence ou administra."
    )
    
    e_administrador_empresa = models.BooleanField(
        "É Administrador da Empresa?",
        default=False,
        help_text="Se marcado, este utilizador pode gerir todos utilizadores da sua empresa."
    )

    # --- Propriedades de Blindagem Multi-tenant (O Cérebro) ---

    @property
    def funcionario(self):
        """
        Retorna o perfil de funcionário do usuário somente quando
        estamos dentro de um schema Tenant.

        No schema public, retorna imediatamente None e não executa
        nenhuma consulta à aplicação funcionarios.
        """
        if connection.schema_name == 'public':
            return None

        try:
            from django.apps import apps

            FuncionarioModel = apps.get_model(
                'funcionarios',
                'Funcionario'
            )

            return (
                FuncionarioModel.objects
                .filter(usuario_id=self.pk)
                .first()
            )

        except LookupError:
            return None


    @property
    def funcionario_profile(self):
        """Método auxiliar para recuperação segura do funcionário."""
        return self.funcionario


    def get_funcionario(self):
        """Alias de compatibilidade para o perfil do funcionário."""
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


# ──────────────────────────────────────────────────────────────────────────────
# BRUTE FORCE PROTECTION — Registo persistente de tentativas de login falhadas
# ──────────────────────────────────────────────────────────────────────────────

class LoginAttempt(models.Model):
    """
    Regista cada tentativa de login falhada.

    Complementa o rate-limit em cache (Redis/LocMem) com um log persistente
    que sobrevive a reinícios do servidor e permite auditoria histórica.

    Isolamento: reside em SHARED_APPS (schema public) — não é tenant-specific
    porque o login acontece antes da determinação do tenant.
    """
    username_tentado = models.CharField(
        max_length=150, blank=True, db_index=True,
        verbose_name='Username tentado',
        help_text='Username introduzido na tentativa (pode não corresponder a nenhum utilizador).'
    )
    ip_address = models.GenericIPAddressField(
        db_index=True,
        verbose_name='Endereço IP'
    )
    user_agent = models.TextField(blank=True, verbose_name='User-Agent')
    timestamp   = models.DateTimeField(auto_now_add=True, db_index=True)
    bloqueado   = models.BooleanField(
        default=False,
        verbose_name='Tentativa em modo bloqueado',
        help_text='True se a tentativa ocorreu enquanto o IP/user já estava em lockout.'
    )
    schema_name = models.CharField(
        max_length=63, blank=True,
        verbose_name='Schema (Tenant)',
        help_text='Schema do tenant no momento da tentativa.'
    )

    class Meta:
        verbose_name = 'Tentativa de Login Falhada'
        verbose_name_plural = 'Tentativas de Login Falhadas'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ip_address', 'timestamp'],  name='loginattempt_ip_ts_idx'),
            models.Index(fields=['username_tentado', 'timestamp'], name='loginattempt_user_ts_idx'),
        ]

    def __str__(self):
        return f"{self.ip_address} → {self.username_tentado or '(sem username)'} @ {self.timestamp:%Y-%m-%d %H:%M}"

