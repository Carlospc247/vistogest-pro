# apps/fornecedores/models.py
from django.utils import timezone
from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel
from decimal import Decimal
from datetime import date, datetime, timedelta
import uuid
from cloudinary.models import CloudinaryField
from django.conf import settings


class CondicaoPagamento(TimeStampedModel):
    """Condições de pagamento"""
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    
    # Configurações
    prazo_dias = models.IntegerField(help_text="Prazo em dias para pagamento")
    parcelas = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    intervalo_parcelas = models.IntegerField(default=30, help_text="Intervalo entre parcelas em dias")
    
    
    
    # Descontos
    desconto_a_vista = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Desconto percentual para pagamento à vista"
    )
    desconto_antecipado = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Desconto percentual para pagamento antecipado"
    )
    
    # Configurações adicionais
    permite_cartao = models.BooleanField(default=False)

    
    ativa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Condição de Pagamento"
        verbose_name_plural = "Condições de Pagamento"
        ordering = ['prazo_dias', 'nome']
    
    def __str__(self):
        if self.parcelas == 1:
            return f"{self.nome} ({self.prazo_dias} dias)"
        else:
            return f"{self.nome} ({self.parcelas}x de {self.intervalo_parcelas} dias)"


class Fornecedor(TimeStampedModel):

    TIPO_PESSOA_CHOICES = [
        ('fisica', 'Pessoa Física'),
        ('juridica', 'Pessoa Jurídica'),
    ]
    
    CATEGORIA_CHOICES = [
        ('laboratorio', 'Laboratório Farmacêutico'),
        ('distribuidor', 'Distribuidor'),
        ('atacadista', 'Atacadista'),
        ('importador', 'Importador'),
        ('representante', 'Representante'),
        ('cooperativa', 'Cooperativa'),
        ('prestador_servico', 'Prestador de Serviço'),
        ('outros', 'Outros'),
    ]
    
    PORTE_CHOICES = [
        ('micro', 'Microempresa'),
        ('pequeno', 'Pequeno Porte'),
        ('medio', 'Médio Porte'),
        ('grande', 'Grande Porte'),
    ]
    
    # Identificação básica
    codigo_fornecedor = models.CharField(max_length=20, unique=True, help_text="Código interno do fornecedor")
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True)
    tipo_pessoa = models.CharField(max_length=10, choices=TIPO_PESSOA_CHOICES, default='juridica')
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='distribuidor')
    porte = models.CharField(max_length=10, choices=PORTE_CHOICES, default='medio')
    
    #foto = models.ImageField(upload_to='fornecedores/fotos/', null=True, blank=True, default='https://res.cloudinary.com/drb9m2gwz/image/upload/v1762087442/logo_wovikm.png')
    foto = CloudinaryField('foto', blank=True, null=True)
    
    # Documentos
    nif_bi = models.CharField(
        verbose_name="NIF / BI",
        max_length=14,  # Mantém 14 para acomodar o BI que é mais longo
        unique=True,
        validators=[RegexValidator(
            # Regex CORRIGIDA para aceitar 10 dígitos para NIF
            regex=r'^(\d{10}|\d{9}[A-Z]{2}\d{3})$',
            message="Formato inválido. O NIF deve conter 10 dígitos (ex: 5001304461) ou o BI deve estar no formato 008693558LA042."
        )]
    )
    
    # Endereço principal
    endereco = models.CharField(max_length=255)
    numero = models.CharField(max_length=10)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50,
    choices=[
        ('BGO', 'Bengo'),
        ('ICB', 'Icolo e Bengo'),
        ('BGU', 'Benguela'),
        ('BIE', 'Bié'),
        ('CAB', 'Cabinda'),
        ('CCU', 'Cuando Cubango'),
        ('CNO', 'Cuanza Norte'),
        ('CUS', 'Cuanza Sul'),
        ('CUN', 'Cunene'),
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
    ]
)

    postal = models.CharField(max_length=9, validators=[
        RegexValidator(regex=r'^\d{5}-\d{3}$', message="Código postal deve estar no formato XXXXX-XXX")
    ])
    pais = models.CharField(max_length=50, default='Angola')
    
    # Contato principal
    telefone_principal = models.CharField(max_length=20, blank=True)
    telefone_secundario = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email_principal = models.EmailField()
    email_financeiro = models.EmailField(blank=True)
    email_comercial = models.EmailField(blank=True)
    site = models.URLField(blank=True)
    
    # Dados comerciais
    condicao_pagamento_padrao = models.ForeignKey('CondicaoPagamento', on_delete=models.SET_NULL, null=True, blank=True)
    prazo_entrega_dias = models.IntegerField(default=7, help_text="Prazo médio de entrega em dias")
    valor_minimo_pedido = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Valor mínimo para pedidos")
    
    # Dados bancários
    banco_principal = models.CharField(max_length=100, blank=True)
    agencia = models.CharField(max_length=20, blank=True)
    conta_corrente = models.CharField(max_length=30, blank=True)
    
    # Certificações e regulamentações #AGT
 
    # Configurações comerciais
    permite_devolucao = models.BooleanField(default=True)
    prazo_devolucao_dias = models.IntegerField(default=30)
    trabalha_consignacao = models.BooleanField(default=False)
    aceita_cartao = models.BooleanField(default=False)
    entrega_proprio = models.BooleanField(default=False, help_text="Faz entrega própria")
    
    # Avaliação e performance
    nota_avaliacao = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Nota de 0 a 10"
    )
    pontualidade_entrega = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Percentual de entregas pontuais"
    )
    qualidade_produtos = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    
    # Status e controle
    ativo = models.BooleanField(default=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueio = models.TextField(blank=True)
    data_primeiro_pedido = models.DateField(null=True, blank=True)
    data_ultimo_pedido = models.DateField(null=True, blank=True)
    
    # Observações
    observacoes = models.TextField(blank=True)
    observacoes_internas = models.TextField(blank=True, help_text="Observações internas (não visíveis ao fornecedor)")
    
    # Relacionamento
    empresa = models.ForeignKey('empresas.Empresa', on_delete=models.CASCADE, related_name='fornecedores')
    
    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        unique_together = [['codigo_fornecedor', 'empresa']]
        indexes = [
            models.Index(fields=['codigo_fornecedor']),
            models.Index(fields=['nif_bi']),
            models.Index(fields=['razao_social', 'empresa']),
            models.Index(fields=['categoria', 'ativo']),
            models.Index(fields=['ativo', 'bloqueado']),
        ]
        ordering = ['razao_social']
    
    def __str__(self):
        return f"{self.codigo_fornecedor} - {self.razao_social}"
    
    def save(self, *args, **kwargs):
        # Gera código automático se não fornecido
        if not self.codigo_fornecedor:
            self.codigo_fornecedor = self.gerar_codigo_fornecedor()
        
        super().save(*args, **kwargs)
    
    def gerar_codigo_fornecedor(self):
        """Gera código sequencial do fornecedor"""
        from django.db.models import Max
        ultimo_codigo = Fornecedor.objects.filter(
            empresa=self.empresa
        ).aggregate(Max('codigo_fornecedor'))['codigo_fornecedor__max']
        
        if ultimo_codigo:
            try:
                numero = int(ultimo_codigo.split('-')[-1]) + 1
            except:
                numero = 1
        else:
            numero = 1
        
        return f"FOR-{numero:05d}"
    
    def clean(self):
        # Validação de NIF/BI
        if self.tipo_pessoa == 'juridica' and len(self.nif_bi.replace('.', '').replace('/', '').replace('-', '')) != 10:
            raise ValidationError("NIF deve ter 10 dígitos")
        elif self.tipo_pessoa == 'fisica' and len(self.nif_bi.replace('.', '').replace('-', '')) != 13:
            raise ValidationError("bi deve ter 13 dígitos")
    
    @property
    def nome_exibicao(self):
        """Nome para exibição (fantasia ou razão social)"""
        return self.nome_fantasia or self.razao_social
    
    @property
    def endereco_completo(self):
        """Endereço completo formatado"""
        endereco_parts = [
            f"{self.endereco}, {self.numero}",
            self.bairro,
            f"{self.cidade}/{self.provincia}",
            f"Postal: {self.postal}"
        ]
        return " - ".join(filter(None, endereco_parts))
    
    @property
    def total_pedidos(self):
        """Total de pedidos realizados"""
        return self.pedidos.filter(status__in=['aprovado', 'recebido', 'finalizado']).count()
    
    @property
    def total_comprado(self):
        """Valor total comprado do fornecedor"""
        total = self.pedidos.filter(
            status__in=['aprovado', 'recebido', 'finalizado']
        ).aggregate(total=models.Sum('total'))['total']
        return total or Decimal('0.00')
    
    @property
    def dias_sem_pedido(self):
        """Dias desde o último pedido"""
        if self.data_ultimo_pedido:
            return (date.today() - self.data_ultimo_pedido).days
        return None
    """
    @property
    def licenca_vencida(self):
        
        if self.data_validade_licenca:
            return self.data_validade_licenca < date.today()
        return False"""



class ContatoFornecedor(TimeStampedModel):
    """Contatos do fornecedor"""
    TIPO_CONTATO_CHOICES = [
        ('comercial', 'Comercial'),
        ('financeiro', 'Financeiro'),
        ('tecnico', 'Técnico'),
        ('entrega', 'Entrega'),
        ('diretoria', 'Diretoria'),
        ('sac', 'SAC'),
    ]
    
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='contatos')
    
    # Dados pessoais
    nome = models.CharField(max_length=200)
    cargo = models.CharField(max_length=100, blank=True)
    departamento = models.CharField(max_length=100, blank=True)
    tipo_contato = models.CharField(max_length=15, choices=TIPO_CONTATO_CHOICES)
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True)
    celular = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Configurações
    contato_principal = models.BooleanField(default=False)
    recebe_pedidos = models.BooleanField(default=False)
    recebe_cobrancas = models.BooleanField(default=False)
    
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Contato do Fornecedor"
        verbose_name_plural = "Contatos do Fornecedor"
        ordering = ['-contato_principal', 'nome']
    
    def __str__(self):
        return f"{self.nome} ({self.fornecedor.razao_social})"


class Pedido(TimeStampedModel):
    """Pedidos de compra para fornecedores"""
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('enviado', 'Enviado'),
        ('confirmado', 'Confirmado'),
        ('aprovado', 'Aprovado'),
        ('em_producao', 'Em Produção'),
        ('em_transito', 'Em Trânsito'),
        ('recebido_parcial', 'Recebido Parcial'),
        ('recebido', 'Recebido'),
        ('finalizado', 'Finalizado'),
        ('cancelado', 'Cancelado'),
    ]
    
    URGENCIA_CHOICES = [
        ('baixa', 'Baixa'),
        ('normal', 'Normal'),
        ('alta', 'Alta'),
        ('urgente', 'Urgente'),
    ]
    
    # Identificação
    numero_pedido = models.CharField(max_length=20, unique=True, db_index=True)
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.PROTECT, related_name='pedidos')
    
    # Datas
    data_pedido = models.DateField(default=date.today)
    data_envio = models.DateTimeField(null=True, blank=True)
    data_confirmacao = models.DateTimeField(null=True, blank=True)
    data_entrega_prevista = models.DateField(null=True, blank=True)
    data_entrega_real = models.DateField(null=True, blank=True)
    
    # Status e urgência
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='rascunho')
    urgencia = models.CharField(max_length=10, choices=URGENCIA_CHOICES, default='normal')
    
    # Valores
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_frete = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_seguro = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outras_despesas = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Condições comerciais
    condicao_pagamento = models.ForeignKey(
        CondicaoPagamento, 
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    forma_pagamento = models.CharField(max_length=50, blank=True)
    
    # Entrega
    endereco_entrega = models.TextField(blank=True, help_text="Endereço de entrega se diferente do padrão")
    transportadora = models.CharField(max_length=200, blank=True)
    numero_rastreamento = models.CharField(max_length=50, blank=True)
    
    # Responsáveis
    solicitante = models.ForeignKey('core.Usuario', on_delete=models.PROTECT, related_name='pedidos_solicitados')
    aprovador = models.ForeignKey(
        'core.Usuario', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='pedidos_aprovados'
    )
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    
    # Observações
    observacoes = models.TextField(blank=True)
    observacoes_internas = models.TextField(blank=True)
    motivo_cancelamento = models.TextField(blank=True)
    
    # Documentos
    arquivo_pedido = models.FileField(upload_to='pedidos/documentos/', null=True, blank=True)
    numero_orcamento_fornecedor = models.CharField(max_length=50, blank=True)
    
    empresa = models.ForeignKey('empresas.Empresa', on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        indexes = [
            models.Index(fields=['numero_pedido']),
            models.Index(fields=['fornecedor', 'status']),
            models.Index(fields=['data_pedido', 'empresa']),
            models.Index(fields=['status', 'urgencia']),
        ]
        ordering = ['-data_pedido', '-numero_pedido']
    
    def __str__(self):
        return f"{self.numero_pedido} - {self.fornecedor.razao_social}"
    
    def save(self, *args, **kwargs):
        # Gera número automático se não fornecido
        if not self.numero_pedido:
            self.numero_pedido = self.gerar_numero_pedido()
        
        # Calcula valores totais
        self.calcular_totais()
        
        super().save(*args, **kwargs)
    
    def gerar_numero_pedido(self):
        """Gera número sequencial do pedido"""
        from django.db.models import Max
        ultimo_numero = Pedido.objects.filter(
            empresa=self.empresa
        ).aggregate(Max('numero_pedido'))['numero_pedido__max']
        
        if ultimo_numero:
            try:
                numero = int(ultimo_numero.split('-')[-1]) + 1
            except:
                numero = 1
        else:
            numero = 1
        
        return f"PED-{numero:06d}"
    
    def calcular_totais(self):
        """Calcula os totais do pedido"""
        # Subtotal dos itens
        self.subtotal = sum(item.total for item in self.itens.all())
        
        # Desconto em valor se percentual informado
        if self.desconto_percentual and not self.desconto_valor:
            self.desconto_valor = (self.subtotal * self.desconto_percentual) / 100
        
        # Total final
        self.total = (
            self.subtotal - 
            self.desconto_valor + 
            self.valor_frete + 
            self.valor_seguro + 
            self.outras_despesas
        )
    
    def enviar_pedido(self, usuario):
        """Envia o pedido para o fornecedor"""
        if self.status != 'rascunho':
            raise ValidationError("Apenas pedidos em rascunho podem ser enviados")
        
        if not self.itens.exists():
            raise ValidationError("Pedido deve ter pelo menos um item")
        
        self.status = 'enviado'
        self.data_envio = datetime.now()
        self.save()
        
        # Registrar histórico
        HistoricoPedido.objects.create(
            pedido=self,
            status_anterior='rascunho',
            status_novo='enviado',
            usuario=usuario,
            observacoes='Pedido enviado para o fornecedor'
        )
    
    def confirmar_pedido(self, usuario, data_entrega_prevista=None):
        """Confirma o pedido pelo fornecedor"""
        if self.status != 'enviado':
            raise ValidationError("Apenas pedidos enviados podem ser confirmados")
        
        self.status = 'confirmado'
        self.data_confirmacao = datetime.now()
        if data_entrega_prevista:
            self.data_entrega_prevista = data_entrega_prevista
        self.save()
        
        # Registrar histórico
        HistoricoPedido.objects.create(
            pedido=self,
            status_anterior='enviado',
            status_novo='confirmado',
            usuario=usuario,
            observacoes='Pedido confirmado pelo fornecedor'
        )
    
    def cancelar_pedido(self, usuario, motivo):
        """Cancela o pedido"""
        if self.status in ['recebido', 'finalizado']:
            raise ValidationError("Pedidos recebidos/finalizados não podem ser cancelados")
        
        status_anterior = self.status
        self.status = 'cancelado'
        self.motivo_cancelamento = motivo
        self.save()
        
        # Registrar histórico
        HistoricoPedido.objects.create(
            pedido=self,
            status_anterior=status_anterior,
            status_novo='cancelado',
            usuario=usuario,
            observacoes=f'Pedido cancelado: {motivo}'
        )
    
    @property
    def percentual_recebido(self):
        """Percentual de itens recebidos"""
        total_itens = self.itens.count()
        if total_itens == 0:
            return 0
        
        itens_recebidos = sum(1 for item in self.itens.all() if item.quantidade_recebida >= item.quantidade)
        return (itens_recebidos / total_itens) * 100
    
    @property
    def dias_em_atraso(self):
        """Dias de atraso na entrega"""
        if self.data_entrega_prevista and not self.data_entrega_real:
            atraso = (date.today() - self.data_entrega_prevista).days
            return max(0, atraso)
        return 0
    
    @property
    def cor_status(self):
        """Cor para exibição do status"""
        cores = {
            'rascunho': 'gray',
            'enviado': 'blue',
            'confirmado': 'orange',
            'aprovado': 'green',
            'em_producao': 'purple',
            'em_transito': 'yellow',
            'recebido_parcial': 'orange',
            'recebido': 'green',
            'finalizado': 'green',
            'cancelado': 'red',
        }
        return cores.get(self.status, 'gray')

class ItemPedido(TimeStampedModel):
    """Itens do pedido"""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT)
    
    # Quantidades
    quantidade = models.IntegerField(validators=[MinValueValidator(1)])
    quantidade_recebida = models.IntegerField(default=0)
    quantidade_devolvida = models.IntegerField(default=0)
    
    # Preços
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    preco_custo_atual = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Preço de custo atual do produto para comparação"
    )
    desconto_item = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Lote e validade (para produtos que exigem)
    numero_lote = models.CharField(max_length=50, blank=True)
    data_fabricacao = models.DateField(null=True, blank=True)
    data_vencimento = models.DateField(null=True, blank=True)
    
    # Recebimento
    data_recebimento = models.DateField(null=True, blank=True)
    usuario_recebimento = models.ForeignKey(
        'core.Usuario', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Item do Pedido"
        verbose_name_plural = "Itens do Pedido"
        unique_together = ['pedido', 'produto']
        ordering = ['produto']
    
    def __str__(self):
        return f"{self.produto.nome_comercial} ({self.quantidade})"
    
    def save(self, *args, **kwargs):
        # Calcula valor total do item
        self.total = (self.preco_unitario * self.quantidade) * (1 - self.desconto_item / 100)
        super().save(*args, **kwargs)
        
        # Recalcular totais do pedido
        self.pedido.calcular_totais()
        self.pedido.save()
    
    @property
    def saldo_pendente(self):
        """Quantidade ainda pendente de recebimento"""
        return max(0, self.quantidade - self.quantidade_recebida)
    
    @property
    def percentual_recebido(self):
        """Percentual recebido do item"""
        if self.quantidade:
            return (self.quantidade_recebida / self.quantidade) * 100
        return 0
    
    @property
    def variacao_preco(self):
        """Variação do preço em relação ao preço atual"""
        if self.preco_custo_atual:
            return ((self.preco_unitario - self.preco_custo_atual) / self.preco_custo_atual) * 100
        return 0

class HistoricoPedido(TimeStampedModel):
    """Histórico de alterações do pedido"""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='historico')
    
    status_anterior = models.CharField(max_length=20)
    status_novo = models.CharField(max_length=20)
    usuario = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    
    observacoes = models.TextField(blank=True)
    dados_alterados = models.JSONField(default=dict, blank=True)
    
    class Meta:
        verbose_name = "Histórico do Pedido"
        verbose_name_plural = "Históricos dos Pedidos"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.pedido.numero_pedido} - {self.status_anterior} → {self.status_novo}"

class AvaliacaoFornecedor(TimeStampedModel):
    """Avaliações dos fornecedores"""
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.CASCADE, related_name='avaliacoes')
    pedido = models.OneToOneField(Pedido, on_delete=models.CASCADE, related_name='avaliacao')
    avaliador = models.ForeignKey('core.Usuario', on_delete=models.PROTECT)
    
    # Notas (0 a 10)
    nota_pontualidade = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    nota_qualidade = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    nota_atendimento = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    nota_preco = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    nota_geral = models.DecimalField(
        max_digits=3, 
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )
    
    # Comentários
    pontos_positivos = models.TextField(blank=True)
    pontos_negativos = models.TextField(blank=True)
    sugestoes = models.TextField(blank=True)
    
    # Recomendação
    recomendaria = models.BooleanField(help_text="Recomendaria este fornecedor?", default=True)
    
    class Meta:
        verbose_name = "Avaliação do Fornecedor"
        verbose_name_plural = "Avaliações dos Fornecedores"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Avaliação {self.fornecedor.razao_social} - Nota {self.nota_geral}"
    
    def save(self, *args, **kwargs):
        # Calcula nota geral como média das outras notas
        notas = [self.nota_pontualidade, self.nota_qualidade, self.nota_atendimento, self.nota_preco]
        self.nota_geral = sum(notas) / len(notas)
        super().save(*args, **kwargs)
        
        # Atualizar nota média do fornecedor
        self.fornecedor.atualizar_nota_avaliacao()
    
    def delete(self, *args, **kwargs):
        fornecedor = self.fornecedor
        super().delete(*args, **kwargs)
        fornecedor.atualizar_nota_avaliacao()

class DocumentoFornecedor(models.Model):
    TIPO_DOCUMENTO_CHOICES = [
        ('NIF', 'NIF'),
        ('CC', 'Certidão Comercial'),
        ('CONTRATO', 'Contrato Social'),
        ('OUTRO', 'Outro'),
    ]

    fornecedor = models.ForeignKey(
        'Fornecedor',
        on_delete=models.CASCADE,
        related_name='documentos'
    )
    tipo_documento = models.CharField(
        max_length=50,
        choices=TIPO_DOCUMENTO_CHOICES
    )
    nome_documento = models.CharField(max_length=255)
    arquivo = models.FileField(upload_to='documentos_fornecedor/')
    data_validade = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True, null=True)
    usuario_upload = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento do Fornecedor"
        verbose_name_plural = "Documentos dos Fornecedores"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.nome_documento} - {self.fornecedor.nome}"

    @property
    def vencido(self):
        if self.data_validade:
            return timezone.now().date() > self.data_validade
        return False

class CotacaoFornecedor(models.Model):
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.CASCADE,
        related_name='cotacoes'
    )
    titulo = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_validade = models.DateField(default=timezone.now)
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00
    )
    ativo = models.BooleanField(default=True)
    usuario_criador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Cotação de Fornecedor"
        verbose_name_plural = "Cotações de Fornecedores"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.titulo} - {self.fornecedor.nome}"

class ContratoFornecedor(models.Model):
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.CASCADE,
        related_name='contratos'
    )
    titulo = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)
    data_inicio = models.DateField(default=timezone.now)
    data_fim = models.DateField()
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    ativo = models.BooleanField(default=True)
    usuario_criador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Contrato de Fornecedor"
        verbose_name_plural = "Contratos de Fornecedores"
        ordering = ['-data_inicio']

    def __str__(self):
        return f"{self.titulo} - {self.fornecedor.nome}"

    def esta_ativo(self):
        """Verifica se o contrato está vigente."""
        hoje = timezone.now().date()
        return self.ativo and self.data_inicio <= hoje <= self.data_fim




