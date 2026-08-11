from django.db import connection, models
from django.core.exceptions import ValidationError
from cloudinary.models import CloudinaryField
from django_tenants.models import DomainMixin, TenantMixin

from apps.core.models import TimeStampedModel


# ==============================================================================
# MODELOS DE PLATAFORMA / SHARED_APPS
# Estes modelos residem APENAS no schema 'public'.
# ==============================================================================

class Empresa(TenantMixin):
    """
    Empresa cliente (Tenant) que usa o sistema SOTARQ.
    Tabela residente no schema 'public' (SHARED_APPS).
    """
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
        max_length=500,
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

    foto = CloudinaryField('foto', blank=True, null=True)

    # Status
    ativa = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        # Garante que não criamos um tenant apontando para um schema PostgreSQL já existente
        if self.schema_name and self.pk is None:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name = %s
                """, [self.schema_name])
                if cursor.fetchone():
                    raise ValidationError({"schema_name": "Já existe um schema PostgreSQL com este nome."})

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        
    def __str__(self):
        return self.nome


class Domain(DomainMixin):
    class Meta:
        verbose_name = "Domínio de Acesso"
        verbose_name_plural = "Domínios de Acesso"





class Categoria(TimeStampedModel):
    """
    Categoria de produtos.
    Reside dentro do Schema Físico do Tenant.
    """
    nome = models.CharField(max_length=100)
    codigo = models.CharField(max_length=20, blank=True)
    descricao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        constraints = [
            models.UniqueConstraint(fields=['nome'], name='unique_categoria_nome_por_tenant')
        ]
        ordering = ['nome']

    def __str__(self):
        return self.nome
