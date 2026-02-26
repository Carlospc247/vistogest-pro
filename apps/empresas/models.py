# apps/empresas/models.py
from django.db import connection, models
from django.contrib.auth.models import User
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField
from django.forms import ValidationError
from django.utils import timezone
from django_tenants.models import DomainMixin, TenantMixin

from apps.core.models import TimeStampedModel



class Empresa(TenantMixin):
    """Empresa cliente que usa o sistema"""
    REGIME_CHOICES = [
        ('COMERCIO', 'Regime de Comércio'),
        ('SERVICOS', 'Regime de Prestação de Serviços'),
        ('MISTO', 'Regime Misto (Comércio e Serviços)'),
    ]
    # Dados básicos
    regime = models.CharField(
        "Regime Fiscal",
        max_length=20,
        choices=REGIME_CHOICES,
        default='MISTO',
        help_text="Define as regras de tributação e incidência de IVA da empresa."
    )
    nome = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=200, blank=True)
    nif = models.CharField(max_length=10, unique=True)
    codigo_validacao = models.CharField(
        max_length=500,  # ou maior, se precisar
        blank=True,
        null=True,
        help_text="Código de validação fornecido pela AGT para ATCUD"
    )
    
    # Endereço
    endereco = models.CharField(max_length=200)
    numero = models.CharField(max_length=10, blank=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50, choices=[
        ('BGO', 'Bengo'),
        ('ICB', 'Icolo e Bengo'),
        ('BGU', 'Benguela'),
        ('BIE', 'Bié'),
        ('CAB', 'Cabinda'),
        ('CCS', 'Cuando Cubango'),
        ('CNO', 'Cuanza Norte'),
        ('CUS', 'Cuanza Sul'),
        ('CNN', 'Cunene'),
        ('HUA', 'Huambo'),
        ('HUI', 'Huíla'),
        ('LUA', 'Luanda'),
        ('LNO', 'Lunda Norte'),
        ('LSU', 'Lunda Sul'),
        ('MAL', 'Malanje'),
        ('MOX', 'Moxico'),
        ('NAM', 'Namibe'),
        ('UIG', 'Uíge'),
        ('ZAI', 'Zaire'),
    ])

    postal = models.CharField(max_length=9)
    
    
    # Contato
    telefone = models.CharField(max_length=20)
    email = models.EmailField()

    #foto = models.ImageField(upload_to='core/empresa/', null=True, blank=True, default='https://res.cloudinary.com/drb9m2gwz/image/upload/v1762087442/logo_wovikm.png')
    foto = CloudinaryField('foto', blank=True, null=True)

    # Status
    ativa = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    from django.core.exceptions import ValidationError
    from django.db import connection

    def clean(self):
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = %s
            """, [self.schema_name])
            if cursor.fetchone():
                raise ValidationError("Já existe um schema com este nome.")
    
    def delete(self, *args, **kwargs):
        # 🛡️ RIGOR SOTARQ: Deleção Bruta para evitar Collector de Tenants
        if connection.schema_name == 'public':
            with connection.cursor() as cursor:
                # Nota: django-tenants cuida do DROP SCHEMA se usarmos o super(), 
                # mas aqui forçamos a limpeza da linha se o coletor travar.
                cursor.execute(f"DELETE FROM {self._meta.db_table} WHERE id = %s", [self.pk])
            return 1
        return super().delete(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        
    def __str__(self):
        return self.nome


class Loja(TimeStampedModel):
    """Loja/Filial da empresa"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='lojas')
    nome = models.CharField(max_length=200)
    codigo = models.CharField(max_length=20)
    
    # Endereço
    endereco = models.CharField(max_length=200)
    numero = models.CharField(max_length=10, blank=True)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    postal = models.CharField(max_length=9)
    provincia = models.CharField(max_length=50, choices=[
        ('BGO', 'Bengo'),
        ('ICB', 'Icolo e Bengo'),
        ('BGU', 'Benguela'),
        ('BIE', 'Bié'),
        ('CAB', 'Cabinda'),
        ('CCS', 'Cuando Cubango'),
        ('CNO', 'Cuanza Norte'),
        ('CUS', 'Cuanza Sul'),
        ('CNN', 'Cunene'),
        ('HUA', 'Huambo'),
        ('HUI', 'Huíla'),
        ('LUA', 'Luanda'),
        ('LNO', 'Lunda Norte'),
        ('LSU', 'Lunda Sul'),
        ('MAL', 'Malanje'),
        ('MOX', 'Moxico'),
        ('NAM', 'Namibe'),
        ('UIG', 'Uíge'),
        ('ZAI', 'Zaire'),
    ])

    #foto = models.ImageField(upload_to='core/loja/', null=True, blank=True, default='https://res.cloudinary.com/drb9m2gwz/image/upload/v1762087442/logo_wovikm.png')
    foto = CloudinaryField('foto', blank=True, null=True)
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Status
    ativa = models.BooleanField(default=True)
    eh_matriz = models.BooleanField(default=False)

    def delete(self, *args, **kwargs):
        if connection.schema_name == 'public':
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {self._meta.db_table} WHERE id = %s", [self.pk])
            return 1
        return super().delete(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Loja'
        verbose_name_plural = 'Lojas'
        unique_together = ['empresa', 'codigo']
        
    def __str__(self):
        return f"{self.nome} - {self.empresa.nome}"



class Categoria(TimeStampedModel ):
    """Categoria de produtos, específica para cada empresa"""
    empresa = models.ForeignKey(
        Empresa, 
        on_delete=models.CASCADE, 
        related_name='categorias'
    )
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, blank=True)
    descricao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'nome'], name='unique_categoria_empresa_nome')
        ]
        ordering = ['nome']

        
    def __str__(self):
        return self.nome


class Domain(DomainMixin):
    """
    Roteador de Domínios SOTARQ.
    Vincula uma URL (ex: escola1.sotarq.com ou localhost) a uma Empresa específica.
    """
    # O DomainMixin já traz os campos 'domain' (CharField) e 'is_primary' (BooleanField)
    # Vinculação obrigatória ao seu modelo Tenant (Empresa)
    tenant = models.ForeignKey(
        'Empresa', 
        on_delete=models.CASCADE, 
        related_name='domains'
    )

    class Meta:
        verbose_name = "Domínio de Acesso"
        verbose_name_plural = "Domínios de Acesso"

    def __str__(self):
        return self.domain

