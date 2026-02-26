# apps/clientes/models.py
from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel, Usuario
from apps.empresas.models import Empresa
from decimal import Decimal
from datetime import date, datetime, timedelta
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone 
from datetime import date
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db import models, transaction
from cloudinary.models import CloudinaryField



class Ponto(models.Model):
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.CASCADE)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(auto_now_add=True)


class CategoriaCliente(TimeStampedModel):
    """Categorias de clientes"""
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True)
    cor = models.CharField(max_length=7, default='#6B7280', help_text="Cor em hexadecimal")
    
    # Benefícios da categoria
    desconto_padrao = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Desconto padrão em percentual"
    )
    limite_credito_padrao = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Limite de crédito padrão"
    )
    prazo_pagamento_dias = models.IntegerField(default=0, help_text="Prazo para pagamento em dias")
    
    # Critérios automáticos
    valor_minimo_compras = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Valor mínimo em compras para esta categoria"
    )
    quantidade_minima_compras = models.IntegerField(
        default=0,
        help_text="Quantidade mínima de compras para esta categoria"
    )
    
    ativa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Categoria de Cliente"
        verbose_name_plural = "Categorias de Clientes"
        ordering = ['nome']
    
    def __str__(self):
        return self.nome


class Cliente(TimeStampedModel):
    TIPO_CLIENTE_CHOICES = [
        ('pessoa_fisica', 'Pessoa Física'),
        ('pessoa_juridica', 'Pessoa Jurídica'),
    ]
    
    SEXO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Feminino'),
        ('O', 'Outro'),
        ('N', 'Não Informado'),
    ]
  
    # Identificação básica
    codigo_cliente = models.CharField(max_length=20, unique=True, editable=False, help_text="Código interno do cliente")

    tipo_cliente = models.CharField(max_length=15, choices=TIPO_CLIENTE_CHOICES, default='pessoa_fisica')
    
    # Pessoa Física
    # Razão Social é o nome oficial de uma empresa, usado em documentos legais
    nome_completo = models.CharField(max_length=255, blank=True, help_text="Nome completo do cliente")
    nome_social = models.CharField(max_length=255, blank=True, null=True, help_text="Nome usado para tratamento social")
    bi = models.CharField(max_length=13, blank=True, help_text="Se for pessoa física")
    
    # Pessoa Jurídica (quando aplicável)
    razao_social = models.CharField(max_length=255, blank=True, help_text="Se for empresa | nome oficial de uma empresa, ou seja, o nome jurídico do negócio")
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True, help_text="Nome comercial pelo qual os clientes vão reconhecer e chamar a empresa")
    nif = models.CharField(max_length=10, blank=True, help_text="Se for empresa")
    
    # Dados pessoais
    data_nascimento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, choices=SEXO_CHOICES, default='N')
   
    
    # Contato
    telefone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    

    #foto = models.ImageField(upload_to='clientes/fotos/', null=True, blank=True, default='https://res.cloudinary.com/drb9m2gwz/image/upload/v1762087442/logo_wovikm.png')
    foto = CloudinaryField('foto', blank=True, null=True)

    # Dados comerciais
    limite_credito = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Limite de crédito para compras"
    )
    desconto_padrao = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0,
        help_text="Desconto padrão em percentual"
    )
    forma_pagamento_preferida_id = models.IntegerField(null=True, blank=True, help_text="ID da forma de pagamento preferida")
    
    # Status e classificação
    ativo = models.BooleanField(default=True)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueio = models.TextField(blank=True)
    vip = models.BooleanField(default=False, help_text="Cliente VIP")
    categoria_cliente = models.ForeignKey(
        CategoriaCliente, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Datas importantes
    data_primeira_compra = models.DateField(null=True, blank=True)
    data_ultima_compra = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Observações
    observacoes = models.TextField(blank=True)
    observacoes_internas = models.TextField(blank=True, help_text="Observações internas (não visíveis ao cliente)")
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='clientes')
    
    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        unique_together = [['codigo_cliente', 'empresa']]
        indexes = [
            models.Index(fields=['codigo_cliente']),
            models.Index(fields=['bi']),
            models.Index(fields=['nome_completo', 'empresa']),
            models.Index(fields=['telefone']),
            models.Index(fields=['email']),
            models.Index(fields=['ativo', 'bloqueado']),
            models.Index(fields=['data_ultima_compra']),
        ]
        ordering = ['nome_completo']
    
    def __str__(self):
        # Simplificado para chamar apenas nome_exibicao para consistência
        return f"{self.codigo_cliente} - {self.nome_exibicao}"
    
    def clean(self):
        # Validações específicas por tipo
        if self.tipo_cliente == 'pessoa_fisica':
            if not self.nome_completo:
                raise ValidationError("Nome completo é obrigatório para pessoa física")
            if not self.bi:
                raise ValidationError("BI é obrigatório para pessoa física")
        else:
            if not self.razao_social:
                raise ValidationError("Razão social é obrigatória para pessoa jurídica")
            if not self.nif:
                raise ValidationError("NIF é obrigatório para pessoa jurídica")
    
    def save(self, *args, **kwargs):
        # Lógica de geração de código ATÓMICA e SEGURA (a única a manter)
        if not self.codigo_cliente:
            with transaction.atomic():
                ultimo = Cliente.objects.filter(empresa=self.empresa).order_by('-id').first()
                
                if not ultimo or not ultimo.codigo_cliente.startswith('CLI'):
                    novo_codigo = "CLI0001"
                else:
                    try:
                        numero = int(ultimo.codigo_cliente[3:]) + 1
                    except (ValueError, IndexError):
                        numero = 1
                    novo_codigo = f"CLI{numero:04d}"

                self.codigo_cliente = novo_codigo
                
        super().save(*args, **kwargs)
    
    
    @property
    def nome_exibicao(self):
        """Nome para exibição (social, fantasia ou completo/razão social)"""
        if self.tipo_cliente == 'pessoa_fisica':
            return self.nome_social or self.nome_completo
        else:
            return self.nome_fantasia or self.razao_social
    
    @property
    def idade(self):
        """Calcula a idade do cliente"""
        if self.data_nascimento:
            hoje = date.today()
            return hoje.year - self.data_nascimento.year - (
                (hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day)
            )
        return None
    
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
    def total_compras(self):
        """Total de compras realizadas"""
        return self.vendas.filter(status__in=['finalizada', 'entregue']).count()
    
    @property
    def total_comprado(self):
        """Valor total comprado pelo cliente"""
        total = self.vendas.filter(
            status__in=['finalizada', 'entregue']
        ).aggregate(total=models.Sum('total'))['total']
        return total or Decimal('0.00')
    
    @property
    def ticket_medio(self):
        """Ticket médio do cliente"""
        total_compras = self.total_compras
        if total_compras > 0:
            return self.total_comprado / total_compras
        return Decimal('0.00')
    
    @property
    def dias_sem_compra(self):
        """Dias desde a última compra"""
        if self.data_ultima_compra:
            return (date.today() - self.data_ultima_compra).days
        return None
    
    @property
    def classificacao_fidelidade(self):
        """Classificação de fidelidade baseada em compras"""
        total = self.total_compras
        if total >= 50:
            return 'Diamante'
        elif total >= 20:
            return 'Ouro'
        elif total >= 10:
            return 'Prata'
        elif total >= 5:
            return 'Bronze'
        else:
            return 'Novo'
    
    @property
    def total_pontos(self):
        return self.ponto_set.aggregate(Sum('valor'))['valor__sum'] or 0
    
    @property
    def credito_disponivel(self):
        """Crédito disponível considerando limite e vendas em aberto"""
        from django.db.models import Sum
        from decimal import Decimal

        vendas_em_aberto = self.vendas.filter(
            status__in=['pendente', 'finalizada']
        ).exclude(
            valor_pago__gte=models.F('total')
        )

        total_em_aberto = vendas_em_aberto.aggregate(
            total=Sum(models.F('total') - models.F('valor_pago'))
        )['total'] or Decimal('0.00')

        return self.limite_credito - total_em_aberto


class EnderecoCliente(TimeStampedModel):
    """Endereços adicionais do cliente"""
    TIPO_ENDERECO_CHOICES = [
        ('residencial', 'Residencial'),
        ('comercial', 'Comercial'),
        ('entrega', 'Entrega'),
        ('cobranca', 'Cobrança'),
        ('outro', 'Outro'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='enderecos')
    
    # Identificação
    nome_endereco = models.CharField(max_length=100, help_text="Ex: Casa, Trabalho, Clínica")
    tipo_endereco = models.CharField(max_length=15, choices=TIPO_ENDERECO_CHOICES, default='residencial')
    
    # Endereço
    endereco = models.CharField(max_length=255)
    numero = models.CharField(max_length=10)
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
    
    # Referências
    ponto_referencia = models.CharField(max_length=255, blank=True)
    observacoes_entrega = models.TextField(blank=True)
    
    # Configurações
    endereco_principal = models.BooleanField(default=False)
    endereco_entrega = models.BooleanField(default=True)
    
    ativo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Endereço do Cliente"
        verbose_name_plural = "Endereços dos Clientes"
        ordering = ['-endereco_principal', 'nome_endereco']
    
    def __str__(self):
        return f"{self.cliente.nome_exibicao} - {self.nome_endereco}"
    
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

class ContatoCliente(TimeStampedModel):
    """Contatos adicionais do cliente"""
    TIPO_CONTATO_CHOICES = [
        ('telefone', 'Telefone'),
        ('whatsapp', 'WhatsApp'),
        ('email', 'Email'),
        ('telegram', 'Telegram'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='contatos')
    
    tipo_contato = models.CharField(max_length=15, choices=TIPO_CONTATO_CHOICES)
    valor_contato = models.CharField(max_length=255, help_text="Número de telefone ou email")
    descricao = models.CharField(max_length=100, blank=True, help_text="Ex: Celular pessoal, Email trabalho")
    
    # Configurações
    contato_principal = models.BooleanField(default=False)
    permite_marketing = models.BooleanField(default=True)
    verificado = models.BooleanField(default=False)
    data_verificacao = models.DateTimeField(null=True, blank=True)
    
    ativo = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Contato do Cliente"
        verbose_name_plural = "Contatos dos Clientes"
        unique_together = ['cliente', 'tipo_contato', 'valor_contato']
        ordering = ['-contato_principal', 'tipo_contato']
    
    def __str__(self):
        return f"{self.cliente.nome_exibicao} - {self.get_tipo_contato_display()}: {self.valor_contato}"

class HistoricoCliente(TimeStampedModel):
    """Histórico de interações com o cliente"""
    TIPO_INTERACAO_CHOICES = [
        ('compra', 'Compra'),
        ('devolucao', 'Devolução'),
        ('reclamacao', 'Reclamação'),
        ('elogio', 'Elogio'),
        ('ligacao', 'Ligação'),
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('visita', 'Visita'),
        ('outros', 'Outros'),
    ]
    
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='historico')
    
    # Dados da interação
    tipo_interacao = models.CharField(max_length=15, choices=TIPO_INTERACAO_CHOICES)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    data_interacao = models.DateTimeField(default=datetime.now)
    
    # Responsável
    usuario_responsavel = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    
    # Classificação
    prioridade = models.CharField(max_length=10, choices=[
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ], default='media')
    
    # Resolução
    resolvido = models.BooleanField(default=True)
    data_resolucao = models.DateTimeField(null=True, blank=True)
    resolucao = models.TextField(blank=True)
    
    # Relacionamentos
    venda_relacionada = models.ForeignKey(
        'vendas.Venda', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        verbose_name = "Histórico do Cliente"
        verbose_name_plural = "Históricos dos Clientes"
        ordering = ['-data_interacao']
    
    def __str__(self):
        return f"{self.cliente.nome_exibicao} - {self.get_tipo_interacao_display()} - {self.data_interacao.strftime('%d/%m/%Y')}"

class CartaoFidelidade(TimeStampedModel):
    """Programa de fidelidade"""
    cliente = models.OneToOneField(Cliente, on_delete=models.CASCADE, related_name='cartao_fidelidade')
    
    # Identificação
    numero_cartao = models.CharField(max_length=20, unique=True)
    codigo_barras = models.CharField(max_length=50, blank=True)
    
    # Pontuação
    pontos_atuais = models.IntegerField(default=0)
    pontos_totais_acumulados = models.IntegerField(default=0)
    pontos_utilizados = models.IntegerField(default=0)
    
    # Configurações
    ativo = models.BooleanField(default=True)
    data_ativacao = models.DateField(auto_now_add=True)
    data_ultima_movimentacao = models.DateField(null=True, blank=True)
    
    # Níveis
    nivel_atual = models.CharField(max_length=20, default='Bronze')
    data_proximo_nivel = models.DateField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Cartão Fidelidade"
        verbose_name_plural = "Cartões Fidelidade"
    
    def __str__(self):
        return f"Cartão {self.numero_cartao} - {self.cliente.nome_exibicao}"
    
    def adicionar_pontos(self, pontos, descricao=""):
        """Adiciona pontos ao cartão"""
        self.pontos_atuais += pontos
        self.pontos_totais_acumulados += pontos
        self.data_ultima_movimentacao = date.today()
        self.save()
        
        # Registrar movimentação
        MovimentacaoFidelidade.objects.create(
            cartao=self,
            tipo_movimentacao='credito',
            pontos=pontos,
            descricao=descricao
        )
        
        # Verificar mudança de nível
        self.verificar_nivel()
    
    def utilizar_pontos(self, pontos, descricao=""):
        """Utiliza pontos do cartão"""
        if self.pontos_atuais < pontos:
            raise ValidationError("Pontos insuficientes")
        
        self.pontos_atuais -= pontos
        self.pontos_utilizados += pontos
        self.data_ultima_movimentacao = date.today()
        self.save()
        
        # Registrar movimentação
        MovimentacaoFidelidade.objects.create(
            cartao=self,
            tipo_movimentacao='debito',
            pontos=pontos,
            descricao=descricao
        )
    
    def verificar_nivel(self):
        """Verifica e atualiza o nível do cliente"""
        if self.pontos_totais_acumulados >= 10000:
            self.nivel_atual = 'Diamante'
        elif self.pontos_totais_acumulados >= 5000:
            self.nivel_atual = 'Ouro'
        elif self.pontos_totais_acumulados >= 2000:
            self.nivel_atual = 'Prata'
        else:
            self.nivel_atual = 'Bronze'
        
        self.save()

class MovimentacaoFidelidade(TimeStampedModel):
    """Movimentações do programa de fidelidade"""
    TIPO_CHOICES = [
        ('credito', 'Crédito'),
        ('debito', 'Débito'),
        ('expiracao', 'Expiração'),
        ('bonus', 'Bônus'),
        ('ajuste', 'Ajuste'),
    ]
    
    cartao = models.ForeignKey(CartaoFidelidade, on_delete=models.CASCADE, related_name='movimentacoes')
    
    tipo_movimentacao = models.CharField(max_length=15, choices=TIPO_CHOICES)
    pontos = models.IntegerField()
    descricao = models.CharField(max_length=255)
    data_movimentacao = models.DateTimeField(auto_now_add=True)
    
    # Relacionamentos
    venda_relacionada = models.ForeignKey(
        'vendas.Venda', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    usuario_responsavel = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    class Meta:
        verbose_name = "Movimentação Fidelidade"
        verbose_name_plural = "Movimentações Fidelidade"
        ordering = ['-data_movimentacao']
    
    def __str__(self):
        sinal = '+' if self.tipo_movimentacao == 'credito' else '-'
        return f"{sinal}{self.pontos} pts - {self.cartao.cliente.nome_exibicao}"

class PreferenciaCliente(TimeStampedModel):
    """Preferências de produtos e marcas do cliente"""
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='preferencias')
    
    # Produto/Categoria preferida
    produto = models.ForeignKey(
        'produtos.Produto', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    categoria = models.ForeignKey('empresas.Categoria', on_delete=models.CASCADE)
    
    fabricante = models.ForeignKey(
        'produtos.Fabricante', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    
    # Detalhes da preferência
    descricao = models.CharField(max_length=255, blank=True)
    prioridade = models.IntegerField(default=1, help_text="1 = Maior prioridade")
    
    # Frequência de compra
    frequencia_compra = models.CharField(max_length=20, choices=[
        ('diaria', 'Diária'),
        ('semanal', 'Semanal'),
        ('quinzenal', 'Quinzenal'),
        ('mensal', 'Mensal'),
        ('bimestral', 'Bimestral'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
        ('esporadica', 'Esporádica'),
    ], blank=True)
    
    observacoes = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Preferência do Cliente"
        verbose_name_plural = "Preferências dos Clientes"
        ordering = ['prioridade', '-created_at']
    
    def __str__(self):
        item = self.produto or self.categoria or self.fabricante
        return f"{self.cliente.nome_exibicao} - {item}"

class TelefoneCliente(models.Model):
    cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="telefones")
    numero = models.CharField(max_length=20)
    tipo = models.CharField(max_length=20, choices=[("celular", "Celular"), ("fixo", "Fixo")])
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cliente.nome} - {self.numero}"

class GrupoCliente(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, null=True)
    desconto_padrao = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)  # Ex: % de desconto
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    #empresa = models.ForeignKey(
     #   settings.AUTH_USER_MODEL,  # ou Empresa, se já tens esse model
      #  on_delete=models.CASCADE,
       # related_name="grupos_clientes"
    #)
    empresa = models.ForeignKey(
        Empresa,  # ou Empresa, se já tens esse model
        on_delete=models.CASCADE,
        related_name="grupos_clientes"
    )

class ProgramaFidelidade(models.Model):
    cliente = models.ForeignKey("Cliente", on_delete=models.CASCADE, related_name="programas")
    pontos = models.PositiveIntegerField(default=0)
    nivel = models.CharField(max_length=50, blank=True, null=True)
    data_entrada = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.cliente.nome} - {self.pontos} pontos"


