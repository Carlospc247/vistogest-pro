# apps/financeiro/models.py
from django.utils import timezone  
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel, Usuario
from apps.empresas.models import Empresa, Loja
from apps.fornecedores.models import Fornecedor
from apps.clientes.models import Cliente
from apps.vendas.models import Venda
from decimal import Decimal
from datetime import date, datetime, timedelta
import uuid

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from datetime import date
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

# models.py
from django.db import models
from django.utils import timezone
from decimal import Decimal






class CentroCusto(TimeStampedModel):
    """Centros de custo para controle gerencial"""
    codigo = models.CharField(max_length=20, unique=True)
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    
    # Responsável
    responsavel = models.ForeignKey(
        Usuario, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Configurações
    ativo = models.BooleanField(default=True)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, null=True, blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Centro de Custo"
        verbose_name_plural = "Centros de Custo"
        unique_together = [['codigo', 'empresa']]
        ordering = ['codigo']
    
    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class ContaBancaria(TimeStampedModel):
    """Contas bancárias da empresa"""
    TIPO_CONTA_CHOICES = [
        ('corrente', 'Conta Corrente'),
        ('poupanca', 'Poupança'),
        ('investimento', 'Conta Investimento'),
        ('cartao', 'Cartão de Crédito'),
        ('caixa', 'Caixa'),
    ]
    
    # Identificação
    nome = models.CharField(max_length=200)
    banco = models.CharField(max_length=100)
    agencia = models.CharField(max_length=20)
    conta = models.CharField(max_length=30)
    digito = models.CharField(max_length=5, blank=True)
    tipo_conta = models.CharField(max_length=15, choices=TIPO_CONTA_CHOICES, default='corrente')
    
    # Saldos
    saldo_inicial = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Saldo inicial da conta"
    )
    saldo_atual = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Saldo atual calculado"
    )
    
    # Limites
    limite_credito = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Limite de crédito/cheque especial"
    )
 
    # Configurações
    ativa = models.BooleanField(default=True)
    conta_principal = models.BooleanField(default=False)
    permite_saldo_negativo = models.BooleanField(default=False)
    
    # Integração
    codigo_integracao = models.CharField(max_length=50, blank=True)
    ultima_conciliacao = models.DateField(null=True, blank=True)
    
    observacoes = models.TextField(blank=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Conta Bancária"
        verbose_name_plural = "Contas Bancárias"
        ordering = ['-conta_principal', 'banco', 'conta']
    
    def __str__(self):
        return f"{self.banco} - Ag: {self.agencia} Cc: {self.conta}"
    
    def atualizar_saldo(self):
        """Atualiza o saldo atual da conta"""
        movimentacoes = self.movimentacoes.filter(confirmada=True)
        
        # Somar entradas e subtrair saídas
        entradas = movimentacoes.filter(tipo_movimentacao='entrada').aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0.00')
        
        saidas = movimentacoes.filter(tipo_movimentacao='saida').aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0.00')
        
        self.saldo_atual = self.saldo_inicial + entradas - saidas
        self.save()
        
        return self.saldo_atual
    
    @property
    def saldo_disponivel(self):
        """Saldo disponível (incluindo limite)"""
        return self.saldo_atual + self.limite_credito

class CategoriaFinanceira(TimeStampedModel):
    """Categorias simples para classificação de receitas e despesas"""
    TIPO_CHOICES = [
        ('receita', 'Receita'),
        ('despesa', 'Despesa'),
    ]
    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='receita')
    ativa = models.BooleanField(default=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Categoria Financeira"
        verbose_name_plural = "Categorias Financeiras"
        unique_together = [['nome', 'empresa', 'tipo']]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"

class MovimentacaoFinanceira(TimeStampedModel):
    """Movimentações financeiras"""
    TIPO_MOVIMENTACAO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
        ('transferencia', 'Transferência'),
    ]
    
    TIPO_DOCUMENTO_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cheque', 'Cheque'),
        ('transferencia', 'Transferência'),
        ('cartao', 'Cartão'),
        ('debito_automatico', 'Débito Automático'),
        ('outros', 'Outros'),
    ]
    
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('confirmada', 'Confirmada'),
        ('cancelada', 'Cancelada'),
        ('estornada', 'Estornada'),
    ]
    
    # Identificação
    numero_documento = models.CharField(max_length=50, blank=True)
    tipo_movimentacao = models.CharField(max_length=15, choices=TIPO_MOVIMENTACAO_CHOICES)
    tipo_documento = models.CharField(max_length=20, choices=TIPO_DOCUMENTO_CHOICES)
    
    # Datas
    data_movimentacao = models.DateField()
    data_vencimento = models.DateField(null=True, blank=True)
    data_confirmacao = models.DateTimeField(null=True, blank=True)
    
    # Valores
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    valor_juros = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_multa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    recibo = models.ForeignKey(
        'vendas.Recibo', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='movimentacoes_financeiras_origem',
        help_text="Recibo de Pagamento (REC) que originou esta entrada."
    )
    # Contas
    conta_bancaria = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, related_name='movimentacoes')
    conta_destino = models.ForeignKey(
        ContaBancaria, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='transferencias_recebidas',
        help_text="Para transferências entre contas"
    )
    categoria = models.ForeignKey(
        CategoriaFinanceira, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='%(class)s_relacionada'
    )
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True)
    
    # Relacionamentos
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    venda_relacionada = models.ForeignKey(Venda, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Descrição
    descricao = models.CharField(max_length=255)
    observacoes = models.TextField(blank=True)
    
    # Controle
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    confirmada = models.BooleanField(default=False)
    conciliada = models.BooleanField(default=False)
    data_conciliacao = models.DateField(null=True, blank=True)
    
    # Responsável
    usuario_responsavel = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    
    # Dados do cheque (se aplicável)
    numero_cheque = models.CharField(max_length=20, blank=True)
    banco_cheque = models.CharField(max_length=100, blank=True)
    emissor_cheque = models.CharField(max_length=200, blank=True)
    

    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    
    
    class Meta:
        verbose_name = "Movimentação Financeira"
        verbose_name_plural = "Movimentações Financeiras"
        indexes = [
            models.Index(fields=['data_movimentacao', 'empresa']),
            models.Index(fields=['conta_bancaria', 'confirmada']),
            models.Index(fields=['status', 'data_vencimento']),
            models.Index(fields=['tipo_movimentacao', 'data_movimentacao']),
        ]
        ordering = ['-data_movimentacao', '-created_at']
    
    def __str__(self):
        sinal = '+' if self.tipo_movimentacao == 'entrada' else '-'
        return f"{sinal}R$ {self.valor} - {self.descricao}"
    
    def save(self, *args, **kwargs):
        # Calcular valor total
        self.total = self.valor + self.valor_juros + self.valor_multa - self.valor_desconto
        
        super().save(*args, **kwargs)
        
        # Atualizar saldo da conta se confirmada
        if self.confirmada:
            self.conta_bancaria.atualizar_saldo()
            if self.conta_destino:
                self.conta_destino.atualizar_saldo()
    
    def confirmar_movimentacao(self, usuario):
        """Confirma a movimentação"""
        if self.confirmada:
            raise ValidationError("Movimentação já confirmada")
        
        self.confirmada = True
        self.status = 'confirmada'
        self.data_confirmacao = datetime.now()
        self.save()
        
        # Criar transferência de destino se for transferência
        if self.tipo_movimentacao == 'transferencia' and self.conta_destino:
            MovimentacaoFinanceira.objects.create(
                tipo_movimentacao='entrada',
                tipo_documento=self.tipo_documento,
                data_movimentacao=self.data_movimentacao,
                valor=self.valor,
                conta_bancaria=self.conta_destino,
                categoria=self.categoria,
                centro_custo=self.centro_custo,
                descricao=f"Transferência de {self.conta_bancaria}",
                status='confirmada',
                confirmada=True,
                data_confirmacao=datetime.now(),
                usuario_responsavel=usuario,
                empresa=self.empresa
            )
    
    def estornar_movimentacao(self, usuario, motivo=""):
        """Estorna a movimentação"""
        if not self.confirmada:
            raise ValidationError("Apenas movimentações confirmadas podem ser estornadas")
        
        self.status = 'estornada'
        self.observacoes += f"\nEstornada em {datetime.now()}: {motivo}"
        self.save()
        
        # Criar movimentação de estorno
        MovimentacaoFinanceira.objects.create(
            tipo_movimentacao='saida' if self.tipo_movimentacao == 'entrada' else 'entrada',
            tipo_documento='estorno',
            data_movimentacao=date.today(),
            valor=self.valor,
            conta_bancaria=self.conta_bancaria,
            categoria=self.categoria,
            centro_custo=self.centro_custo,
            descricao=f"Estorno: {self.descricao}",
            observacoes=f"Estorno da movimentação {self.id}: {motivo}",
            status='confirmada',
            confirmada=True,
            data_confirmacao=datetime.now(),
            usuario_responsavel=usuario,
            empresa=self.empresa
        )


class ContaPai(models.Model):
    """Conta principal que consolida parcelas"""
    
    STATUS_CHOICES = [
        ('aberta', 'Aberta'),
        ('vencida', 'Vencida'),
        ('paga', 'Paga'),
        ('recebida', 'Recebida'),
        ('cancelada', 'Cancelada'),
        ('renegociada', 'Renegociada'),
    ]

    # Identificação
    numero_documento = models.CharField(max_length=50)
    descricao = models.CharField(max_length=255)
    
    # Datas
    data_emissao = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    data_recebimento = models.DateField(null=True, blank=True)

    # Valores
    valor_original = models.DecimalField(max_digits=12, decimal_places=2)
    valor_juros = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_multa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_recebido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aberta')
    observacoes = models.TextField(blank=True)

    # Relacionamentos opcionais para integração com contas a pagar ou receber
    empresa = models.ForeignKey('empresas.Empresa', on_delete=models.CASCADE)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    fornecedor = models.ForeignKey('fornecedores.Fornecedor', on_delete=models.SET_NULL, null=True, blank=True)
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True)
    
    class Meta:
        verbose_name = "Conta Principal"
        verbose_name_plural = "Contas Principais"
        indexes = [
            models.Index(fields=['data_vencimento', 'status']),
            models.Index(fields=['status', 'empresa']),
        ]
        ordering = ['data_vencimento']

    def __str__(self):
        return f"{self.numero_documento} - {self.descricao} - R$ {self.valor_original}"

    def atualizar_saldo_status(self):
        """Atualiza saldo e status baseado nas parcelas"""
        # Para pagamento
        total_pago = self.parcelas.aggregate(total=models.Sum('valor_pago'))['total'] or 0
        self.valor_pago = total_pago

        # Para recebimento
        total_recebido = self.parcelas.aggregate(total=models.Sum('valor_recebido'))['total'] or 0
        self.valor_recebido = total_recebido

        # Calcula saldo
        self.valor_saldo = (self.valor_original + self.valor_juros + self.valor_multa - self.valor_desconto) - max(total_pago, total_recebido)

        # Atualiza status
        hoje = date.today()
        if self.valor_saldo <= 0:
            if self.valor_pago > 0:
                self.status = 'paga'
                if not self.data_pagamento:
                    self.data_pagamento = hoje
            elif self.valor_recebido > 0:
                self.status = 'recebida'
                if not self.data_recebimento:
                    self.data_recebimento = hoje
        elif self.data_vencimento < hoje:
            self.status = 'vencida'
        else:
            self.status = 'aberta'

        self.save()

    @property
    def dias_vencimento(self):
        """Dias para vencimento (negativo se vencida)"""
        return (self.data_vencimento - date.today()).days

    @property
    def esta_vencida(self):
        """Verifica se a conta está vencida"""
        return self.data_vencimento < date.today() and self.status in ['aberta', 'vencida']


class ContaPagar(TimeStampedModel):
    """Contas a pagar"""
    STATUS_CHOICES = [
        ('aberta', 'Aberta'),
        ('vencida', 'Vencida'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
        ('renegociada', 'Renegociada'),
    ]
    
    TIPO_CONTA_CHOICES = [
        ('fornecedor', 'Fornecedor'),
        ('funcionario', 'Funcionário'),
        ('servico', 'Serviço'),
        ('imposto', 'Imposto'),
        ('emprestimo', 'Empréstimo'),
        ('financiamento', 'Financiamento'),
        ('cartao', 'Cartão de Crédito'),
        ('outros', 'Outros'),
    ]
    
    # Identificação
    numero_documento = models.CharField(max_length=50)
    descricao = models.CharField(max_length=255)
    tipo_conta = models.CharField(max_length=15, choices=TIPO_CONTA_CHOICES)
    
    # Datas
    data_emissao = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    
    # Valores
    valor_original = models.DecimalField(max_digits=12, decimal_places=2)
    valor_juros = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_multa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Relacionamentos
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True)
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True)
    
    # Parcelamento
    numero_parcela = models.IntegerField(default=1)
    total_parcelas = models.IntegerField(default=1)
    categoria = models.ForeignKey(
        CategoriaFinanceira, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='%(class)s_relacionada'
    )
    conta_pai = models.ForeignKey(
        ContaPai, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='parcelas_pagar'
    )
    
    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aberta')
    observacoes = models.TextField(blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Conta a Pagar"
        verbose_name_plural = "Contas a Pagar"
        indexes = [
            models.Index(fields=['data_vencimento', 'status']),
            models.Index(fields=['fornecedor', 'status']),
            models.Index(fields=['status', 'empresa']),
        ]
        ordering = ['data_vencimento']
    
    def __str__(self):
        return f"{self.numero_documento} - {self.descricao} - R$ {self.valor_original}"
    
    
    def save(self, *args, **kwargs):
        # Calcular valor do saldo
        total = self.valor_original + self.valor_juros + self.valor_multa - self.valor_desconto
        self.valor_saldo = total - self.valor_pago
        
        # Atualizar status baseado no pagamento
        if self.valor_saldo <= 0 and self.valor_pago > 0:
            self.status = 'paga'
            if not self.data_pagamento:
                self.data_pagamento = date.today()
        elif self.data_vencimento < date.today() and self.status == 'aberta':
            self.status = 'vencida'
        
        super().save(*args, **kwargs)

        # Atualiza a conta pai se existir
        if self.conta_pai:
            self.conta_pai.atualizar_saldo_status()

    @property
    def dias_vencimento(self):
        """Dias para vencimento (negativo se vencida)"""
        return (self.data_vencimento - date.today()).days
    
    @property
    def esta_vencida(self):
        """Verifica se a conta está vencida"""
        return self.data_vencimento < date.today() and self.status in ['aberta', 'vencida']
    
    def pagar(self, valor_pagamento, conta_bancaria, tipo_documento='transferencia', observacoes=""):
        if self.status not in ['aberta', 'vencida']:
            raise ValidationError("Apenas contas abertas ou vencidas podem ser pagas")
        if valor_pagamento <= 0:
            raise ValidationError("Valor do pagamento deve ser maior que zero")
        
        # Registrar movimentação financeira
        movimentacao = MovimentacaoFinanceira.objects.create(
            tipo_movimentacao='saida',
            tipo_documento=tipo_documento,
            data_movimentacao=date.today(),
            valor=valor_pagamento,
            conta_bancaria=conta_bancaria,
            # plano_contas removido para leveza do sistema
            centro_custo=self.centro_custo,
            fornecedor=self.fornecedor,
            descricao=f"Pagamento: {self.descricao}",
            observacoes=f"Conta a pagar: {self.numero_documento}. {observacoes}",
            status='confirmada',
            confirmada=True,
            data_confirmacao=datetime.now(),
            usuario_responsavel=conta_bancaria.empresa.usuarios.first(), 
            empresa=self.empresa
        )
        
        # Atualizar valores da parcela
        self.valor_pago += valor_pagamento
        self.save()

        # Atualizar saldo da conta pai, se existir
        if self.conta_pai:
            total_pago = self.conta_pai.parcelas.aggregate(total=models.Sum('valor_pago'))['total'] or 0
            self.conta_pai.valor_pago = total_pago
            self.conta_pai.valor_saldo = self.conta_pai.valor_original + self.conta_pai.valor_juros + self.conta_pai.valor_multa - self.conta_pai.valor_desconto - total_pago
            if self.conta_pai.valor_saldo <= 0:
                self.conta_pai.status = 'paga'
                if not self.conta_pai.data_pagamento:
                    self.conta_pai.data_pagamento = date.today()
            self.conta_pai.save()

        return movimentacao


class ContaReceberManager(models.Manager):
    def abertas(self):
        return self.filter(status='aberta')

    def vencidas(self):
        return self.filter(status='vencida')

    def vencendo(self):
        hoje = date.today()
        return self.filter(
            status='aberta',
            data_vencimento__lte=hoje + timedelta(days=3),
            data_vencimento__gte=hoje
        )

    def recebidas(self):
        return self.filter(status='recebida')


class ContaReceber(TimeStampedModel):
    """Contas a receber"""
    STATUS_CHOICES = [
        ('aberta', 'Aberta'),
        ('vencida', 'Vencida'),
        ('recebida', 'Recebida'),
        ('cancelada', 'Cancelada'),
        ('renegociada', 'Renegociada'),
    ]
    
    TIPO_CONTA_CHOICES = [
        ('venda', 'Venda'),
        ('servico', 'Serviço'),
        ('aluguel', 'Aluguel'),
        ('juros', 'Juros'),
        ('outros', 'Outros'),
    ]
    
    # Identificação
    numero_documento = models.CharField(max_length=50)
    descricao = models.CharField(max_length=255)
    tipo_conta = models.CharField(max_length=15, choices=TIPO_CONTA_CHOICES, default='venda')
    
    # Datas
    data_emissao = models.DateField()
    data_vencimento = models.DateField()
    data_recebimento = models.DateField(null=True, blank=True)
    
    # Valores
    valor_original = models.DecimalField(max_digits=12, decimal_places=2)
    valor_juros = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_multa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_recebido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_saldo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Relacionamentos
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    venda = models.ForeignKey('vendas.Venda', on_delete=models.SET_NULL, null=True, blank=True)
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, null=True, blank=True)
    
    # Parcelamento
    numero_parcela = models.IntegerField(default=1)
    total_parcelas = models.IntegerField(default=1)
    categoria = models.ForeignKey(
        CategoriaFinanceira, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='%(class)s_relacionada'
    )
    conta_pai = models.ForeignKey(
        ContaPai, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='parcelas_receber'
    )
    
    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aberta')
    observacoes = models.TextField(blank=True)
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    objects = ContaReceberManager()
    
    class Meta:
        verbose_name = "Conta a Receber"
        verbose_name_plural = "Contas a Receber"
        indexes = [
            models.Index(fields=['data_vencimento', 'status']),
            models.Index(fields=['cliente', 'status']),
            models.Index(fields=['status', 'empresa']),
        ]
        ordering = ['data_vencimento']
    
    def __str__(self):
        return f"{self.numero_documento} - {self.descricao} - R$ {self.valor_original}"
    

    def save(self, *args, **kwargs):
        total = self.valor_original + self.valor_juros + self.valor_multa - self.valor_desconto
        self.valor_saldo = total - self.valor_recebido

        hoje = date.today()

        if self.valor_saldo <= 0 and self.valor_recebido > 0:
            self.status = 'recebida'
            if not self.data_recebimento:
                self.data_recebimento = hoje
        elif self.data_vencimento < hoje and self.status != 'recebida':
            self.status = 'vencida'
        elif (self.data_vencimento - hoje).days <= 3 and self.status == 'aberta':
            pass
        else:
            self.status = 'aberta'

        super().save(*args, **kwargs)

        # Atualiza a conta pai se existir
        if self.conta_pai:
            self.conta_pai.atualizar_saldo_status()

    @property
    def dias_vencimento(self):
        """Dias para vencimento (negativo se vencida)"""
        return (self.data_vencimento - date.today()).days
    
    @property
    def esta_vencida(self):
        """Verifica se a conta está vencida"""
        return self.data_vencimento < date.today() and self.status in ['aberta', 'vencida']
    
    def receber(self, valor_recebimento, conta_bancaria, tipo_documento='transferencia', observacoes=""):
        if self.status not in ['aberta', 'vencida']:
            raise ValidationError("Apenas contas abertas ou vencidas podem ser recebidas")
        if valor_recebimento <= 0:
            raise ValidationError("Valor do recebimento deve ser maior que zero")
        
        # Registrar movimentação financeira
        movimentacao = MovimentacaoFinanceira.objects.create(
            tipo_movimentacao='entrada',
            tipo_documento=tipo_documento,
            data_movimentacao=date.today(),
            valor=valor_recebimento,
            conta_bancaria=conta_bancaria,
            # plano_contas removido para leveza do sistema
            centro_custo=self.centro_custo,
            cliente=self.cliente,
            venda_relacionada=self.venda,
            descricao=f"Recebimento: {self.descricao}",
            observacoes=f"Conta a receber: {self.numero_documento}. {observacoes}",
            status='confirmada',
            confirmada=True,
            data_confirmacao=timezone.now(),
            usuario_responsavel=conta_bancaria.empresa.usuarios.first(),
            empresa=self.empresa
        )
        
        # Atualizar valores da parcela
        self.valor_recebido += valor_recebimento
        self.save()

        # Atualizar saldo da conta pai, se existir
        if self.conta_pai:
            total_recebido = self.conta_pai.parcelas.aggregate(total=models.Sum('valor_recebido'))['total'] or 0
            self.conta_pai.valor_recebido = total_recebido
            self.conta_pai.valor_saldo = self.conta_pai.valor_original + self.conta_pai.valor_juros + self.conta_pai.valor_multa - self.conta_pai.valor_desconto - total_recebido
            if self.conta_pai.valor_saldo <= 0:
                self.conta_pai.status = 'recebida'
                if not self.conta_pai.data_recebimento:
                    self.conta_pai.data_recebimento = date.today()
            self.conta_pai.save()

        return movimentacao



class FluxoCaixa(models.Model):
    TIPO_CHOICES = [
        ('entrada', 'Entrada'),
        ('saida', 'Saída'),
    ]

    empresa = models.ForeignKey('empresas.Empresa', on_delete=models.CASCADE)
    data_referencia = models.DateField()
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    valor_previsto = models.DecimalField(max_digits=12, decimal_places=2)
    valor_realizado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    categoria = models.CharField(max_length=100)
    descricao = models.CharField(max_length=255)
    conta_bancaria = models.ForeignKey(ContaBancaria, on_delete=models.CASCADE)
    centro_custo = models.ForeignKey(CentroCusto, on_delete=models.SET_NULL, null=True, blank=True)
    conta_pagar = models.ForeignKey(ContaPagar, on_delete=models.SET_NULL, null=True, blank=True)
    conta_receber = models.ForeignKey(ContaReceber, on_delete=models.SET_NULL, null=True, blank=True)
    realizado = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Fluxo de Caixa"
        verbose_name_plural = "Fluxos de Caixa"
        ordering = ['data_referencia']

    def __str__(self):
        sinal = '+' if self.tipo == 'entrada' else '-'
        return f"{self.data_referencia} - {sinal} AKZ {self.valor_previsto} - {self.categoria}"

    @property
    def saldo_acumulado(self):
        # Calcula dinamicamente
        entradas = FluxoCaixa.objects.filter(
            empresa=self.empresa,
            data_referencia__lte=self.data_referencia,
            tipo='entrada'
        ).aggregate(total=models.Sum('valor_previsto'))['total'] or Decimal('0')
        saidas = FluxoCaixa.objects.filter(
            empresa=self.empresa,
            data_referencia__lte=self.data_referencia,
            tipo='saida'
        ).aggregate(total=models.Sum('valor_previsto'))['total'] or Decimal('0')
        return entradas - saidas



class ConciliacaoBancaria(TimeStampedModel):
    """Conciliação bancária"""
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('conciliada', 'Conciliada'),
        ('divergente', 'Divergente'),
    ]
    
    conta_bancaria = models.ForeignKey(ContaBancaria, on_delete=models.CASCADE, related_name='conciliacoes')
    
    # Período
    data_inicio = models.DateField()
    data_fim = models.DateField()
    
    # Saldos
    saldo_banco_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_banco_final = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_sistema_inicial = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_sistema_final = models.DecimalField(max_digits=12, decimal_places=2)
    diferenca = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    data_conciliacao = models.DateTimeField(null=True, blank=True)
    responsavel = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    
    observacoes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Conciliação Bancária"
        verbose_name_plural = "Conciliações Bancárias"
        ordering = ['-data_fim']
    
    def __str__(self):
        return f"{self.conta_bancaria} - {self.data_inicio} a {self.data_fim}"
    
    def save(self, *args, **kwargs):
        # Calcular diferença
        self.diferenca = self.saldo_banco_final - self.saldo_sistema_final
        
        # Atualizar status baseado na diferença
        if abs(self.diferenca) <= Decimal('0.01'):  # Tolerância de 1 centavo
            self.status = 'conciliada'
            self.data_conciliacao = datetime.now()
        elif self.diferenca != 0:
            self.status = 'divergente'
        
        super().save(*args, **kwargs)




class MovimentoCaixa(TimeStampedModel):
    """Movimentações do caixa físico"""
    TIPO_MOVIMENTO_CHOICES = [
        ('abertura', 'Abertura do Caixa'),
        ('fechamento', 'Fechamento do Caixa'),
        ('venda', 'Venda'),
        ('recebimento', 'Recebimento'),
        ('pagamento', 'Pagamento'),
        ('sangria', 'Sangria'),
        ('suprimento', 'Suprimento'),
        ('troco', 'Troco'),
        ('devolucao', 'Devolução'),
        ('desconto', 'Desconto'),
        ('cancelamento', 'Cancelamento'),
        ('ajuste', 'Ajuste'),
        ('outros', 'Outros'),
    ]
    
    FORMA_PAGAMENTO_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao_debito', 'Cartão de Débito'),
        ('cartao_credito', 'Cartão de Crédito'),
        ('transferencia', 'Transferência'),
        ('cheque', 'Cheque'),
        ('vale', 'Vale'),
        ('outros', 'Outros'),
    ]
    
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado'),
        ('estornado', 'Estornado'),
    ]
    
    # Identificação
    numero_movimento = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Número sequencial do movimento"
    )
    
    # Data e hora
    data_movimento = models.DateField(default=date.today)
    hora_movimento = models.TimeField(auto_now_add=True)
    
    # Tipo e forma
    tipo_movimento = models.CharField(max_length=15, choices=TIPO_MOVIMENTO_CHOICES)
    forma_pagamento = models.CharField(
        "Tipo",
        max_length=20,
        choices=FORMA_PAGAMENTO_CHOICES,
        default='dinheiro'
    )
    
    # Valores
    valor = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Valor do movimento (positivo para entradas, negativo para saídas)"
    )
    valor_troco = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=0,
        help_text="Valor do troco dado"
    )
    
    # Descrição
    descricao = models.CharField(max_length=255)
    observacoes = models.TextField(blank=True)
    
    # Relacionamentos
    usuario = models.ForeignKey(
        Usuario, 
        on_delete=models.PROTECT,
        help_text="Usuário responsável pelo movimento"
    )
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    
    # Venda relacionada (se aplicável)
    venda_relacionada = models.ForeignKey(
        'vendas.Venda', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Venda que originou este movimento"
    )
    
    # Conta financeira relacionada
    conta_receber = models.ForeignKey(
        ContaReceber, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    conta_pagar = models.ForeignKey(
        ContaPagar, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Cliente/Fornecedor
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    fornecedor = models.ForeignKey(
        Fornecedor, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    
    # Status e controle
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pendente')
    confirmado = models.BooleanField(default=False)
    data_confirmacao = models.DateTimeField(null=True, blank=True)
    
    # Dados do documento (se aplicável)
    numero_documento = models.CharField(max_length=50, blank=True)
    
    # Dados do cheque (se aplicável)
    numero_cheque = models.CharField(max_length=20, blank=True)
    banco_cheque = models.CharField(max_length=100, blank=True)
    emissor_cheque = models.CharField(max_length=200, blank=True)
    data_cheque = models.DateField(null=True, blank=True)
    

    
    # Dados do cartão (se aplicável)
    numero_cartao_mascarado = models.CharField(max_length=20, blank=True)
    bandeira_cartao = models.CharField(max_length=50, blank=True)
    numero_autorizacao = models.CharField(max_length=20, blank=True)
    numero_comprovante = models.CharField(max_length=30, blank=True)
    
    # Movimento de estorno (se aplicável)
    movimento_original = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='estornos',
        help_text="Movimento original que está sendo estornado"
    )
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Movimento de Caixa"
        verbose_name_plural = "Movimentos de Caixa"
        indexes = [
            models.Index(fields=['data_movimento', 'loja']),
            models.Index(fields=['tipo_movimento', 'status']),
            models.Index(fields=['usuario', 'data_movimento']),
            models.Index(fields=['venda_relacionada']),
        ]
        ordering = ['-data_movimento', '-hora_movimento']
    
    def __str__(self):
        sinal = '+' if self.valor >= 0 else ''
        return f"{self.data_movimento} - {sinal}R$ {self.valor} - {self.get_tipo_movimento_display()}"
    
    def save(self, *args, **kwargs):
        # Gerar número do movimento se não existir
        if not self.numero_movimento:
            hoje = date.today()
            prefixo = f"CX{hoje.strftime('%Y%m%d')}"
            
            ultimo_numero = MovimentoCaixa.objects.filter(
                numero_movimento__startswith=prefixo,
                loja=self.loja
            ).count() + 1
            
            self.numero_movimento = f"{prefixo}{ultimo_numero:04d}"
        
        super().save(*args, **kwargs)
    
    def confirmar_movimento(self, usuario_confirmacao=None):
        """Confirma o movimento de caixa"""
        if self.confirmado:
            raise ValidationError("Movimento já confirmado")
        
        self.confirmado = True
        self.status = 'confirmado'
        self.data_confirmacao = datetime.now()
        self.save()
        
        # Se for movimento de venda, criar/atualizar movimentação financeira
        if self.tipo_movimento == 'venda' and self.venda_relacionada:
            self._criar_movimentacao_financeira()
    
    def estornar_movimento(self, motivo="", usuario_estorno=None):
        """Estorna o movimento de caixa"""
        if not self.confirmado:
            raise ValidationError("Apenas movimentos confirmados podem ser estornados")
        
        if self.status == 'estornado':
            raise ValidationError("Movimento já estornado")
        
        # Criar movimento de estorno
        MovimentoCaixa.objects.create(
            tipo_movimento='cancelamento',
            forma_pagamento=self.forma_pagamento,
            valor=-self.valor,  # Valor oposto
            descricao=f"Estorno: {self.descricao}",
            observacoes=f"Estorno do movimento {self.numero_movimento}. Motivo: {motivo}",
            usuario=usuario_estorno or self.usuario,
            loja=self.loja,
            venda_relacionada=self.venda_relacionada,
            movimento_original=self,
            status='confirmado',
            confirmado=True,
            data_confirmacao=datetime.now(),
            empresa=self.empresa
        )
        
        # Atualizar status do movimento original
        self.status = 'estornado'
        self.observacoes += f"\nEstornado em {datetime.now()}: {motivo}"
        self.save()
    
    def _criar_movimentacao_financeira(self):
        """Cria movimentação financeira correspondente sem dependência de plano de contas"""
        conta_principal = ContaBancaria.objects.filter(
            empresa=self.empresa,
            conta_principal=True,
            ativa=True
        ).first()
        
        if not conta_principal:
            return 

        # Criar movimentação apenas para dinheiro e transferencia
        if self.forma_pagamento in ['dinheiro', 'transferencia']:
            MovimentacaoFinanceira.objects.create(
                tipo_movimentacao='entrada',
                tipo_documento=self.forma_pagamento,
                data_movimentacao=self.data_movimento,
                valor=abs(self.valor),
                conta_bancaria=conta_principal,
                cliente=self.cliente,
                venda_relacionada=self.venda_relacionada,
                descricao=f"Recebimento venda: {self.descricao}",
                observacoes=f"Movimento caixa: {self.numero_movimento}",
                status='confirmada',
                confirmada=True,
                data_confirmacao=self.data_confirmacao,
                usuario_responsavel=self.usuario,
                empresa=self.empresa
            )

    @property
    def valor_liquido(self):
        """Valor líquido (valor - troco)"""
        return self.valor - self.valor_troco
    
    @property
    def eh_entrada(self):
        """Verifica se é uma entrada de caixa"""
        return self.valor > 0
    
    @property
    def eh_saida(self):
        """Verifica se é uma saída de caixa"""
        return self.valor < 0
    
    @classmethod
    def calcular_saldo_caixa(cls, loja, data=None):
        """Calcula saldo atual do caixa"""
        if data is None:
            data = date.today()
        
        movimentos = cls.objects.filter(
            loja=loja,
            data_movimento__lte=data,
            confirmado=True
        )
        
        saldo = movimentos.aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0.00')
        
        return saldo
    
    @classmethod
    def obter_ultimo_fechamento(cls, loja):
        """Obtém o último fechamento de caixa da loja"""
        return cls.objects.filter(
            loja=loja,
            tipo_movimento='fechamento',
            confirmado=True
        ).order_by('-data_movimento', '-hora_movimento').first()
    
    @classmethod
    def caixa_esta_aberto(cls, loja, data=None):
        """Verifica se o caixa está aberto"""
        if data is None:
            data = date.today()
        
        # Buscar última abertura e último fechamento do dia
        ultima_abertura = cls.objects.filter(
            loja=loja,
            data_movimento=data,
            tipo_movimento='abertura',
            confirmado=True
        ).order_by('-hora_movimento').first()
        
        ultimo_fechamento = cls.objects.filter(
            loja=loja,
            data_movimento=data,
            tipo_movimento='fechamento',
            confirmado=True
        ).order_by('-hora_movimento').first()
        
        # Se não há abertura, caixa fechado
        if not ultima_abertura:
            return False
        
        # Se não há fechamento, caixa aberto
        if not ultimo_fechamento:
            return True
        
        # Se abertura é posterior ao fechamento, caixa aberto
        return ultima_abertura.hora_movimento > ultimo_fechamento.hora_movimento


class ImpostoTributo(TimeStampedModel):
    """
    Impostos e Tributos - Sistema Tributário de Angola
    Baseado nas tabelas oficiais da AGT (Administração Geral Tributária)
    """
    
    # Tipos de Impostos baseados nos códigos oficiais da AGT
    TIPO_IMPOSTO_CHOICES = [
        # I - IMPOSTO SOBRE O VALOR ACRESCENTADO (IVA)
        ('01I', '01I - IVA - Regime Geral'),
        ('02I', '02I - IVA - Importação'),
        ('03I', '03I - IVA - Regime Geral'),
        ('04I', '04I - IVA - Regime Simplificado'),
        ('05I', '05I - IVA - Regime Transitório'),
        ('06I', '06I - IVA - Outros'),
        
        # B - IMPOSTO SOBRE RENDIMENTO DO TRABALHO
        ('01B', '01B - IRT - Grupo A - Conta de Outrem'),
        ('02B', '02B - IRT - Grupo B - Conta Própria'),
        ('03B', '03B - IRT - Grupo C - Atividades Comerciais e Industriais'),
        
        # C - IMPOSTO INDUSTRIAL
        ('01C', '01C - II - Regime Geral'),
        ('02C', '02C - II - Regime Simplificado'),
        ('03C', '03C - II - Retenção na Fonte - Residentes'),
        ('04C', '04C - II - Retenção na Fonte - Não Residentes'),
        ('05C', '05C - II - Diamantes'),
        ('06C', '06C - II - Ouro'),
        ('07C', '07C - II - Outros Minerais'),
        
        # E - IMPOSTOS PETROLÍFEROS
        ('01E', '01E - IP - Rendimentos do Petróleo'),
        ('02E', '02E - ITP - Transações de Petróleo'),
        
        # F - IMPOSTOS SOBRE BENS IMÓVEIS (PREDIAIS)
        ('01F', '01F - IP - Predial sobre a Detenção'),
        ('02F', '02F - IP - Predial sobre Transmissões Onerosas'),
        ('03F', '03F - IP - Predial sobre Transmissões Gratuitas'),
        ('04F', '04F - IP - Predial sobre a Renda'),
        
        # G - IMPOSTOS SOBRE BENS MÓVEIS
        ('01G', '01G - IBM - Veículos Automotores - Ligeiros'),
        ('02G', '02G - IBM - Veículos Automotores - Pesados'),
        ('03G', '03G - IBM - Motociclos, Ciclomotores, Triciclos e Quadriciclos'),
        ('04G', '04G - IBM - Veículos Automotores - Aeronaves'),
        ('05G', '05G - IBM - Veículos Automotores - Embarcações'),
        ('06G', '06G - IBM - Sucessões'),
        ('07G', '07G - IBM - Doações'),
        
        # H - IMPOSTOS SOBRE A PRODUÇÃO
        ('01H', '01H - IPD - Produção de Petróleo'),
        ('02H', '02H - IPD - Produção de Diamantes - Royalty'),
        ('03H', '03H - IPD - Produção de Ouro - Royalty'),
        ('04H', '04H - IPD - Produção de Outros Minerais - Royalty'),
        
        # J - IMPOSTO ESPECIAL DE CONSUMO
        ('01J', '01J - IEC - Aeronaves e Embarcações de Recreio'),
        ('02J', '02J - IEC - Álcool e Outras Bebidas Alcoólicas'),
        ('03J', '03J - IEC - Armas de Fogo'),
        ('04J', '04J - IEC - Artefatos de Joalharia, Ourivesaria e Outros'),
        ('05J', '05J - IEC - Bebidas Açucaradas'),
        ('06J', '06J - IEC - Bebidas Energéticas'),
        ('07J', '07J - IEC - Cerveja'),
        ('08J', '08J - IEC - Fogo-de-artifício'),
        ('09J', '09J - IEC - Objetos de Arte, Coleção e Antiguidades'),
        ('10J', '10J - IEC - Produtos Derivados do Petróleo: Gasolina e Gasóleo'),
        ('11J', '11J - IEC - Tabaco e seus Derivados'),
        ('12J', '12J - IEC - Veículos Automóveis'),
        ('13J', '13J - IEC - Produtos Derivados do Petróleo: Gás Natural, Butano, Propano'),
        ('14J', '14J - IEC - Produtos Derivados do Petróleo - Outros'),
        
        # K - IMPOSTOS SOBRE O COMÉRCIO EXTERNO
        ('01K', '01K - ICE - Exportação'),
        ('02K', '02K - ICE - Importação'),
        
        # L - IMPOSTOS DE SELO
        ('01L', '01L - IS - Contrato de Arrendamento'),
        ('02L', '02L - IS - Operações Bancárias'),
        ('03L', '03L - IS - Recibo de Quitação'),
        ('04L', '04L - IS - Operações Isentas (Regime Geral)'),
        ('05L', '05L - IS - Operações Isentas (Regime Simplificado)'),
        ('06L', '06L - IS - Outros'),
        
        # Q - CONTRIBUIÇÕES
        ('01Q', '01Q - Contribuições para o Fundo de Desenvolvimento Mineiro'),
        ('02Q', '02Q - Contribuições para Formação de Quadros Angolanos'),
    ]
    
    REGIME_TRIBUTARIO_CHOICES = [
        ('geral', 'Regime Geral'),
        ('simplificado', 'Regime Simplificado'),
        ('iva_geral', 'Regime do IVA - Geral'),
        ('iva_simplificado', 'Regime do IVA - Simplificado'),
        ('iva_transitorio', 'Regime Transitório do IVA'),
        ('excluido_iva', 'Regime de Exclusão do IVA'),
        ('especial_petrolifero_mineiro', 'Regime Especial do Sector Petrolífero e Mineiro'),
        ('retencao_fonte', 'Regime de Retenção na Fonte'),
        ('isencao', 'Regime de Isenção'),
    ]
    
    PERIODICIDADE_CHOICES = [
        ('mensal', 'Mensal'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
        ('eventual', 'Eventual'),
    ]
    
    SITUACAO_CHOICES = [
        ('pendente', 'Pendente de Cálculo'),
        ('calculado', 'Calculado'),
        ('declarado', 'Declarado à AGT'),
        ('pago', 'Pago'),
        ('parcelado', 'Parcelado'),
        ('vencido', 'Vencido'),
        ('isento', 'Isento'),
        ('suspenso', 'Suspenso'),
    ]
    
    METODO_CALCULO_CHOICES = [
        ('percentual_receita', 'Percentual sobre Receita'),
        ('percentual_lucro', 'Percentual sobre Lucro'),
        ('valor_fixo', 'Valor Fixo'),
        ('tabela_progressiva', 'Tabela Progressiva'),
        ('por_unidade', 'Por Unidade'),
        ('retencao_fonte', 'Retenção na Fonte'),
        ('outros', 'Outros'),
    ]
    
    # Identificação
    codigo_receita_agt = models.CharField(
        max_length=10,
        choices=TIPO_IMPOSTO_CHOICES,
        help_text="Código oficial da receita AGT"
    )
    codigo_imposto_interno = models.CharField(
        max_length=30,
        help_text="Código interno do sistema"
    )
    categoria = models.ForeignKey(
        CategoriaFinanceira, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='%(class)s_relacionada'
    )
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    
    # Regime e periodicidade
    regime_tributario = models.CharField(
        max_length=30, 
        choices=REGIME_TRIBUTARIO_CHOICES,
        help_text="Regime tributário aplicável"
    )
    periodicidade = models.CharField(
        max_length=15, 
        choices=PERIODICIDADE_CHOICES,
        default='mensal'
    )
    
    # Período de apuração
    ano_referencia = models.IntegerField(
        help_text="Ano de referência da apuração"
    )
    mes_referencia = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Mês de referência (1-12)"
    )
    data_inicio_periodo = models.DateField(
        help_text="Início do período de apuração"
    )
    data_fim_periodo = models.DateField(
        help_text="Fim do período de apuração"
    )
    
    # Datas importantes
    data_vencimento = models.DateField(
        help_text="Data de vencimento do imposto"
    )
    data_pagamento = models.DateField(
        null=True, 
        blank=True,
        help_text="Data efetiva do pagamento"
    )
    data_calculo = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Data/hora do último cálculo"
    )
    data_declaracao = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Data de envio da declaração à AGT"
    )
    
    # Método de cálculo
    metodo_calculo = models.CharField(
        max_length=20, 
        choices=METODO_CALCULO_CHOICES,
        default='percentual_receita'
    )
    
    # Alíquotas específicas de Angola
    aliquota_percentual = models.DecimalField(
        max_digits=8, 
        decimal_places=4, 
        default=0,
        help_text="Alíquota em percentual (ex: 7.0000 para IVA 7%)"
    )
    valor_fixo = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Valor fixo do imposto (se aplicável)",
        validators=[MinValueValidator(0)]
    )
    
    # Base de cálculo
    base_calculo = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Base de cálculo do imposto"
    )
    receita_bruta = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0,
        help_text="Receita bruta do período"
    )
    deducoes_permitidas = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Deduções permitidas pela legislação angolana"
    )
    
    # Valores em Kwanzas (AOA)
    valor_calculado = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Valor calculado do imposto em AOA"
    )
    valor_devido = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Valor devido (após compensações) em AOA"
    )
    valor_pago = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Valor efetivamente pago em AOA"
    )
    
    # Multas e juros segundo legislação angolana
    valor_multa = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Multa por atraso em AOA"
    )
    valor_juros = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Juros por atraso em AOA"
    )
    total_agt = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Valor total a pagar à AGT em AOA"
    )
    
    # Compensações e créditos
    creditos_periodo_anterior = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Créditos do período anterior"
    )
    compensacoes_utilizadas = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        help_text="Compensações utilizadas"
    )
    
    # Situação
    situacao = models.CharField(
        max_length=15, 
        choices=SITUACAO_CHOICES, 
        default='pendente'
    )
    
    # Dados da guia de pagamento AGT
    numero_guia_agt = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Número da guia de recolhimento AGT"
    )
    numero_declaracao_agt = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Número da declaração na AGT"
    )
    
    # Relacionamentos
    conta_bancaria_pagamento = models.ForeignKey(
        ContaBancaria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Conta utilizada para pagamento"
    )
    movimentacao_pagamento = models.ForeignKey(
        MovimentacaoFinanceira,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='impostos_angola_pagos',
        help_text="Movimentação de pagamento do imposto"
    )
    
    # Conta contábil
    
    centro_custo = models.ForeignKey(
        CentroCusto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # Controle de automatização
    calculo_automatico = models.BooleanField(
        default=True,
        help_text="Calcular automaticamente baseado nas vendas"
    )
    ultima_atualizacao_calculo = models.DateTimeField(
        null=True, 
        blank=True
    )
    
    # Observações e anexos
    observacoes = models.TextField(blank=True)
    arquivo_declaracao_agt = models.FileField(
        upload_to='impostos/declaracoes/',
        null=True,
        blank=True,
        help_text="Arquivo da declaração enviada à AGT"
    )
    arquivo_guia_pagamento = models.FileField(
        upload_to='impostos/guias/',
        null=True,
        blank=True,
        help_text="Arquivo da guia de pagamento AGT"
    )
    arquivo_comprovante_pagamento = models.FileField(
        upload_to='impostos/comprovantes/',
        null=True,
        blank=True,
        help_text="Comprovante de pagamento"
    )
    
    # Controle
    usuario_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Usuário responsável pela apuração"
    )
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    
    class Meta:
        verbose_name = "Imposto/Tributo Angola"
        verbose_name_plural = "Impostos/Tributos Angola"
        unique_together = [
            ['empresa', 'codigo_receita_agt', 'ano_referencia', 'mes_referencia']
        ]
        indexes = [
            models.Index(fields=['codigo_receita_agt', 'situacao']),
            models.Index(fields=['data_vencimento', 'situacao']),
            models.Index(fields=['ano_referencia', 'mes_referencia']),
            models.Index(fields=['regime_tributario', 'empresa']),
        ]
        ordering = ['-ano_referencia', '-mes_referencia', 'data_vencimento']
    
    def __str__(self):
        return f"{self.get_codigo_receita_agt_display()} - {self.mes_referencia:02d}/{self.ano_referencia} - {self.valor_devido:,.2f} AOA"
    
    def save(self, *args, **kwargs):
        # Calcular valor total
        self.total_agt = self.valor_devido + self.valor_multa + self.valor_juros
        
        # Atualizar situação baseada no pagamento
        if self.valor_pago >= self.total_agt and self.total_agt > 0:
            self.situacao = 'pago'
        elif self.data_vencimento < date.today() and self.situacao not in ['pago', 'isento']:
            self.situacao = 'vencido'
        
        # Gerar código interno se não existir
        if not self.codigo_imposto_interno:
            self.codigo_imposto_interno = self._gerar_codigo_interno()
        
        super().save(*args, **kwargs)
    
    def _gerar_codigo_interno(self):
        """Gera código único interno para o imposto"""
        prefixo = self.codigo_receita_agt
        sufixo = f"{self.ano_referencia}{self.mes_referencia:02d}"
        
        contador = ImpostoTributo.objects.filter(
            empresa=self.empresa,
            codigo_imposto_interno__startswith=f"{prefixo}{sufixo}"
        ).count() + 1
        
        return f"{prefixo}{sufixo}{contador:03d}"
    
    def calcular_imposto_angola(self, forcar_recalculo=False):
        """Calcula o valor do imposto baseado na legislação angolana"""
        if not forcar_recalculo and self.situacao in ['pago', 'calculado', 'declarado']:
            return self.valor_calculado
        
        # Aplicar alíquotas específicas de Angola
        if self.codigo_receita_agt.startswith('0') and self.codigo_receita_agt.endswith('I'):  # IVA
            self._calcular_iva_angola()
        elif self.codigo_receita_agt.startswith('0') and self.codigo_receita_agt.endswith('C'):  # Imposto Industrial
            self._calcular_imposto_industrial_angola()
        elif self.codigo_receita_agt.startswith('0') and self.codigo_receita_agt.endswith('A'):  # IAC
            self._calcular_iac_angola()
        elif self.metodo_calculo == 'valor_fixo':
            self.valor_calculado = self.valor_fixo
        else:
            self._calcular_por_percentual_receita()
        
        # Aplicar deduções e compensações
        self.valor_devido = max(
            0, 
            self.valor_calculado - self.deducoes_permitidas - self.compensacoes_utilizadas - self.creditos_periodo_anterior
        )
        
        # Calcular multa e juros se vencido (legislação angolana)
        if self.data_vencimento < date.today() and self.situacao != 'pago':
            self._calcular_multa_juros_angola()
        
        self.data_calculo = timezone.now()
        self.situacao = 'calculado'
        self.save()
        
        return self.valor_calculado
    
    def _calcular_iva_angola(self):
        """Calcula IVA segundo alíquotas de Angola"""
        # Alíquotas vigentes em Angola (2024)
        aliquota_iva = Decimal('7.0')  # Taxa geral de 7%
        
        # Verificar regimes especiais
        if self.regime_tributario == 'iva_simplificado':
            aliquota_iva = Decimal('5.0')  # 5% para produtos específicos
        elif 'cabinda' in self.empresa.endereco.lower():
            aliquota_iva = Decimal('1.0')  # 1% para Cabinda
        
        # Buscar receitas sujeitas ao IVA
        receitas_iva = self._obter_receitas_periodo()
        self.receita_bruta = receitas_iva
        self.base_calculo = receitas_iva
        self.aliquota_percentual = aliquota_iva
        self.valor_calculado = self.base_calculo * (aliquota_iva / 100)
    
    def _calcular_por_percentual_receita(self):
        """Cálculo genérico baseado em percentual da receita bruta"""
        self.receita_bruta = self._obter_receitas_periodo()
        self.base_calculo = self.receita_bruta
        self.valor_calculado = self.base_calculo * (self.aliquota_percentual / 100)

    def _calcular_imposto_industrial_angola(self):
        """Calcula Imposto Industrial segundo legislação angolana"""
        # Alíquotas do Imposto Industrial em Angola
        if self.empresa.sector_atividade in ['bancario', 'seguros', 'telecomunicacoes', 'petroleo']:
            aliquota = Decimal('35.0')  # 35% para setores específicos
        else:
            aliquota = Decimal('25.0')  # 25% taxa geral
        
        # Calcular lucro tributável
        receitas = self._obter_receitas_periodo()
        despesas_dedutiveis = self._obter_despesas_dedutiveis()
        lucro_tributavel = receitas - despesas_dedutiveis
        
        self.receita_bruta = receitas
        self.base_calculo = max(0, lucro_tributavel)
        self.aliquota_percentual = aliquota
        self.valor_calculado = self.base_calculo * (aliquota / 100)
    
    def _calcular_iac_angola(self):
        """Calcula Imposto sobre Aplicação de Capitais"""
        # Alíquotas IAC variam conforme o tipo
        aliquotas_iac = {
            '01A': Decimal('10.0'),  # Títulos do Banco Central
            '02A': Decimal('15.0'),  # Bilhetes e Obrigações do Tesouro
            '03A': Decimal('5.0'),   # Depósito à Ordem
            '04A': Decimal('10.0'),  # Depósito a Prazo
            '05A': Decimal('10.0'),  # Dividendos/Lucros
        }
        
        aliquota = aliquotas_iac.get(self.codigo_receita_agt, Decimal('10.0'))
        
        # Base de cálculo são os rendimentos de capitais
        base_rendimentos = self._obter_rendimentos_capitais()
        
        self.base_calculo = base_rendimentos
        self.aliquota_percentual = aliquota
        self.valor_calculado = self.base_calculo * (aliquota / 100)
    
    def _calcular_multa_juros_angola(self):
        """Calcula multa e juros segundo legislação angolana"""
        if self.data_vencimento >= date.today():
            return
        
        dias_atraso = (date.today() - self.data_vencimento).days
        
        # Multa conforme legislação angolana (exemplo: 10% sobre valor devido)
        self.valor_multa = self.valor_devido * Decimal('0.10')
        
        # Juros de mora: 1.5% ao mês (0.05% ao dia)
        self.valor_juros = self.valor_devido * Decimal('0.0005') * dias_atraso
    
    def _obter_receitas_periodo(self):
        """Obtém receitas do período para cálculo"""
        receitas = MovimentacaoFinanceira.objects.filter(
            empresa=self.empresa,
            tipo_movimentacao='entrada',
            data_movimentacao__range=[self.data_inicio_periodo, self.data_fim_periodo],
            confirmada=True
        ).aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0.00')
        
        return receitas
    
    def _obter_despesas_dedutiveis(self):
        """Obtém despesas dedutíveis para Imposto Industrial"""
        despesas = MovimentacaoFinanceira.objects.filter(
            empresa=self.empresa,
            tipo_movimentacao='saida',
            data_movimentacao__range=[self.data_inicio_periodo, self.data_fim_periodo],
            confirmada=True,
            # Filtrar apenas despesas dedutíveis conforme legislação
            plano_contas__tipo_conta='despesa'
        ).aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0.00')
        
        return despesas
    
    def _obter_rendimentos_capitais(self):
        """Obtém rendimentos de capitais para IAC"""
        # Implementar lógica específica para cada tipo de rendimento
        return Decimal('0.00')

    def pagar_imposto_agt(self):
        """Marca o imposto como pago à AGT"""
        from django.utils import timezone
        self.status = 'pago'
        self.data_pagamento = timezone.now()
        self.save(update_fields=['status', 'data_pagamento'])
        return "Imposto pago com sucesso à AGT."




    def estornar_imposto_agt(self, usuario):
        """
        Estorna manualmente um pagamento de imposto, revertendo a movimentação financeira.
        Este método pode ser chamado pelo painel admin ou interface do usuário.
        """
        if getattr(self, "status_pagamento", None) != "pago":
            return {"status": "erro", "mensagem": "Somente impostos pagos podem ser estornados."}

        try:
            with transaction.atomic():
                # 1. Estorna movimentação financeira vinculada
                movimentacao = getattr(self, "movimentacao_pagamento", None)
                if movimentacao and hasattr(movimentacao, "estornar_movimentacao"):
                    movimentacao.estornar_movimentacao(
                        usuario=usuario,
                        motivo=f"Estorno manual do imposto {self.nome}"
                    )

                # 2. Atualiza estado do imposto
                self.status_pagamento = "estornado"
                self.data_estorno = timezone.now().date() if hasattr(self, "data_estorno") else None
                self.save(update_fields=["status_pagamento"])

                return {
                    "status": "sucesso",
                    "mensagem": f"Imposto {self.nome} estornado com sucesso."
                }

        except Exception as e:
            return {"status": "erro", "mensagem": f"Erro ao estornar imposto: {e}"}


class ConfiguracaoImposto(TimeStampedModel):
    """
    Configurações de impostos por empresa angolana
    Baseado na legislação da AGT (Administração Geral Tributária)
    """
    
    empresa = models.OneToOneField(
        Empresa, 
        on_delete=models.CASCADE,
        related_name='configuracao_impostos_angola'
    )
    
    # Regime tributário principal (baseado na legislação angolana)
    regime_tributario_principal = models.CharField(
        max_length=30,
        choices=ImpostoTributo.REGIME_TRIBUTARIO_CHOICES,
        default='geral',
        help_text="Regime tributário principal da empresa"
    )
    
    # Regime de IVA específico
    regime_iva = models.CharField(
        max_length=30,
        choices=[
            ('iva_geral', 'Regime do IVA - Geral'),
            ('iva_simplificado', 'Regime do IVA - Simplificado'),
            ('iva_transitorio', 'Regime Transitório do IVA'),
            ('excluido_iva', 'Regime de Exclusão do IVA'),
        ],
        default='iva_geral',
        help_text="Regime específico do IVA"
    )
    
    # Setor de atividade (importante para alíquotas diferenciadas)
    setor_atividade = models.CharField(
        max_length=50,
        choices=[
            ('comercio', 'Comércio'),
            ('industria', 'Indústria'),
            ('servicos', 'Serviços'),
            ('construcao', 'Construção Civil'),
            ('bancario', 'Sector Bancário'),
            ('seguros', 'Sector de Seguros'),
            ('telecomunicacoes', 'Telecomunicações'),
            ('petroleo', 'Sector Petrolífero'),
            ('mineiro', 'Sector Mineiro'),
            ('transporte', 'Transporte'),
            ('turismo', 'Turismo e Hotelaria'),
            ('agricultura', 'Agricultura'),
            ('outros', 'Outros'),
        ],
        default='comercio',
        help_text="Setor principal de atividade da empresa"
    )
    
    # Localização (importante para IVA - Cabinda tem 1%)
    provincia = models.CharField(
        max_length=30,
        choices=[
            ('luanda', 'Luanda'),
            ('benguela', 'Benguela'),
            ('huila', 'Huíla'),
            ('cabinda', 'Cabinda'),
            ('huambo', 'Huambo'),
            ('cunene', 'Cunene'),
            ('namibe', 'Namibe'),
            ('cuando_cubango', 'Cuando Cubango'),
            ('lunda_norte', 'Lunda Norte'),
            ('lunda_sul', 'Lunda Sul'),
            ('malanje', 'Malanje'),
            ('moxico', 'Moxico'),
            ('bie', 'Bié'),
            ('kuanza_norte', 'Kwanza Norte'),
            ('kuanza_sul', 'Kwanza Sul'),
            ('uige', 'Uíge'),
            ('zaire', 'Zaire'),
            ('bengo', 'Bengo'),
        ],
        default='luanda',
        help_text="Província onde a empresa está localizada"
    )
    
    # Alíquotas personalizadas (baseadas na legislação angolana)
    
    # IVA - Alíquotas vigentes em Angola
    aliquota_iva_geral = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('7.00'),
        help_text="Alíquota do IVA - Regime Geral (%) - Padrão: 7%"
    )
    aliquota_iva_simplificado = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('5.00'),
        help_text="Alíquota do IVA - Regime Simplificado (%) - Padrão: 5%"
    )
    aliquota_iva_cabinda = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('1.00'),
        help_text="Alíquota do IVA para Cabinda (%) - Padrão: 1%"
    )
    
    # Imposto Industrial - Alíquotas diferenciadas por setor
    aliquota_imposto_industrial_geral = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('25.00'),
        help_text="Alíquota do Imposto Industrial - Geral (%) - Padrão: 25%"
    )
    aliquota_imposto_industrial_especial = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('35.00'),
        help_text="Alíquota do Imposto Industrial - Setores Especiais (%) - Padrão: 35%"
    )
    
    # Imposto sobre Aplicação de Capitais
    aliquota_iac_depositos = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('10.00'),
        help_text="Alíquota IAC - Depósitos (%) - Padrão: 10%"
    )
    aliquota_iac_titulos = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('15.00'),
        help_text="Alíquota IAC - Títulos (%) - Padrão: 15%"
    )
    
    # Imposto de Selo
    aliquota_imposto_selo = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.20'),
        help_text="Alíquota do Imposto de Selo (%) - Padrão: 0,2%"
    )
    
    # Impostos sobre bens móveis
    aliquota_imposto_veiculos = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('2.00'),
        help_text="Alíquota do Imposto sobre Veículos (%) - Padrão: 2%"
    )
    
    # Configurações específicas para setores especiais
    eh_setor_petrolifero = models.BooleanField(
        default=False,
        help_text="Empresa pertence ao setor petrolífero"
    )
    eh_setor_mineiro = models.BooleanField(
        default=False,
        help_text="Empresa pertence ao setor mineiro"
    )
    eh_setor_diamantifero = models.BooleanField(
        default=False,
        help_text="Empresa pertence ao setor diamantífero"
    )
    
    # Impostos específicos que a empresa está sujeita
    impostos_aplicaveis = models.JSONField(
        default=list,
        help_text="Lista de códigos AGT dos impostos aplicáveis à empresa",
        blank=True
    )
    
    # Configurações automáticas
    gerar_impostos_automaticamente = models.BooleanField(
        default=True,
        help_text="Gerar impostos automaticamente no final do mês"
    )
    dia_vencimento_impostos = models.IntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Dia do mês para vencimento dos impostos (padrão AGT: dia 15)"
    )
    
    # Configurações de retenção na fonte
    aplicar_retencao_fonte = models.BooleanField(
        default=False,
        help_text="Empresa sujeita à retenção na fonte"
    )
    percentual_retencao_ii = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('6.50'),
        help_text="Percentual de retenção do Imposto Industrial (%)"
    )
    percentual_retencao_iva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('6.50'),
        help_text="Percentual de retenção do IVA (%)"
    )
    
    # Configurações de multas e juros (legislação angolana)
    percentual_multa_atraso = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.00'),
        help_text="Percentual de multa por atraso (%) - Padrão: 10%"
    )
    percentual_juros_mora_mensal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.50'),
        help_text="Percentual de juros de mora mensal (%) - Padrão: 1,5%"
    )
    
    # Configurações contábeis
    
    centro_custo_impostos = models.ForeignKey(
        'CentroCusto',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Centro de custo padrão para impostos"
    )
    
    # Configurações de notificação
    notificar_vencimentos = models.BooleanField(
        default=True,
        help_text="Notificar sobre vencimentos de impostos"
    )
    dias_antecedencia_notificacao = models.IntegerField(
        default=7,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Dias de antecedência para notificação de vencimentos"
    )
    
    # Responsável fiscal
    responsavel_fiscal = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Funcionário responsável pelos assuntos fiscais"
    )
    
    # Observações
    observacoes = models.TextField(
        blank=True,
        help_text="Observações específicas sobre a configuração fiscal da empresa"
    )
    
    # Última atualização das alíquotas
    data_ultima_atualizacao_aliquotas = models.DateTimeField(
        auto_now=True,
        help_text="Data da última atualização das alíquotas"
    )
    
    class Meta:
        verbose_name = "Configuração de Impostos Angola"
        verbose_name_plural = "Configurações de Impostos Angola"
        indexes = [
            models.Index(fields=['regime_tributario_principal']),
            models.Index(fields=['setor_atividade']),
            models.Index(fields=['provincia']),
        ]
    
    def __str__(self):
        return f"Config. Impostos Angola - {self.empresa.razao_social}"
    
    def clean(self):
        """Validações específicas"""
        super().clean()
        
        # Validar alíquotas específicas por setor
        if self.setor_atividade in ['bancario', 'seguros', 'telecomunicacoes', 'petroleo']:
            if self.aliquota_imposto_industrial_geral < 35:
                raise ValidationError({
                    'aliquota_imposto_industrial_geral': 
                    f'Para o setor {self.get_setor_atividade_display()}, a alíquota mínima é 35%'
                })
        
        # Validar IVA para Cabinda
        if self.provincia == 'cabinda' and self.aliquota_iva_geral > 1:
            self.aliquota_iva_geral = self.aliquota_iva_cabinda
    
    def save(self, *args, **kwargs):
        # Configurar impostos aplicáveis automaticamente baseado no setor
        if not self.impostos_aplicaveis:
            self.impostos_aplicaveis = self._definir_impostos_aplicaveis()
        
        super().save(*args, **kwargs)
    
    def _definir_impostos_aplicaveis(self):
        """Define impostos aplicáveis baseado no setor de atividade"""
        impostos_base = [
            '03I',  # IVA - Regime Geral
            '01C',  # Imposto Industrial - Regime Geral
        ]
        
        # Adicionar impostos específicos por setor
        if self.setor_atividade == 'bancario':
            impostos_base.extend([
                '01A',  # IAC - Títulos do Banco Central
                '02L',  # IS - Operações Bancárias
            ])
        elif self.setor_atividade == 'petroleo':
            impostos_base.extend([
                '01E',  # IP - Rendimentos do Petróleo
                '02E',  # ITP - Transações de Petróleo
                '01H',  # IPD - Produção de Petróleo
            ])
        elif self.setor_atividade == 'mineiro':
            impostos_base.extend([
                '05C',  # II - Diamantes
                '06C',  # II - Ouro
                '07C',  # II - Outros Minerais
            ])
        elif self.setor_atividade in ['comercio', 'industria']:
            impostos_base.extend([
                '12J',  # IEC - Veículos Automóveis (se aplicável)
            ])
        
        # Adicionar impostos comuns a todos
        impostos_base.extend([
            '03L',  # IS - Recibo de Quitação
            '01G',  # IBM - Veículos (se tiver)
        ])
        
        return impostos_base
    
    def get_aliquota_iva_aplicavel(self):
        """Retorna a alíquota de IVA aplicável à empresa"""
        if self.provincia == 'cabinda':
            return self.aliquota_iva_cabinda
        elif self.regime_iva == 'iva_simplificado':
            return self.aliquota_iva_simplificado
        else:
            return self.aliquota_iva_geral
    
    def get_aliquota_imposto_industrial_aplicavel(self):
        """Retorna a alíquota de Imposto Industrial aplicável"""
        if self.setor_atividade in ['bancario', 'seguros', 'telecomunicacoes', 'petroleo']:
            return self.aliquota_imposto_industrial_especial
        else:
            return self.aliquota_imposto_industrial_geral
    
    def gerar_impostos_mes(self, ano, mes):
        """Gera impostos do mês baseado na configuração"""
        if not self.gerar_impostos_automaticamente:
            return []
        
        impostos_criados = []
        
        for codigo_agt in self.impostos_aplicaveis:
            # Verificar se já existe
            exists = ImpostoTributo.objects.filter(
                empresa=self.empresa,
                codigo_receita_agt=codigo_agt,
                ano_referencia=ano,
                mes_referencia=mes
            ).exists()
            
            if not exists:
                imposto = self._criar_imposto_configurado(codigo_agt, ano, mes)
                if imposto:
                    impostos_criados.append(imposto)
        
        return impostos_criados
    
    def _criar_imposto_configurado(self, codigo_agt, ano, mes):
        """Cria imposto com configurações personalizadas"""
        # Obter informações do imposto
        nome_imposto = dict(ImpostoTributo.TIPO_IMPOSTO_CHOICES).get(codigo_agt, '')
        
        # Definir alíquota baseada na configuração
        aliquota = self._get_aliquota_por_codigo(codigo_agt)
        
        # Definir regime
        regime = self._get_regime_por_codigo(codigo_agt)
        
        # Criar imposto
        return ImpostoTributo.objects.create(
            empresa=self.empresa,
            codigo_receita_agt=codigo_agt,
            nome=nome_imposto,
            regime_tributario=regime,
            ano_referencia=ano,
            mes_referencia=mes,
            aliquota_percentual=aliquota,
            calculo_automatico=True,
            usuario_responsavel=self.responsavel_fiscal.user if self.responsavel_fiscal else None,
        )
    
    def _get_aliquota_por_codigo(self, codigo_agt):
        """Retorna alíquota configurada para o código AGT"""
        if codigo_agt.endswith('I'):  # IVA
            return self.get_aliquota_iva_aplicavel()
        elif codigo_agt.endswith('C'):  # Imposto Industrial
            return self.get_aliquota_imposto_industrial_aplicavel()
        elif codigo_agt.endswith('A'):  # IAC
            if codigo_agt in ['01A', '04A']:  # Títulos e Depósitos
                return self.aliquota_iac_titulos
            else:
                return self.aliquota_iac_depositos
        elif codigo_agt.endswith('L'):  # Imposto de Selo
            return self.aliquota_imposto_selo
        elif codigo_agt.endswith('G'):  # Veículos
            return self.aliquota_imposto_veiculos
        else:
            return Decimal('0.00')
    
    def _get_regime_por_codigo(self, codigo_agt):
        """Retorna regime tributário para o código AGT"""
        if codigo_agt.endswith('I'):  # IVA
            return self.regime_iva
        else:
            return self.regime_tributario_principal
    
    @property
    def total_impostos_estimado_mensal(self):
        """Estima total de impostos mensais baseado na configuração"""
        # Esta é uma estimativa baseada no faturamento médio
        # Implementar lógica mais específica conforme necessário
        return Decimal('0.00')
    
    @classmethod
    def get_configuracao_padrao_angola(cls):
        """Retorna configuração padrão para empresas angolanas"""
        return {
            'regime_tributario_principal': 'geral',
            'regime_iva': 'iva_geral',
            'setor_atividade': 'comercio',
            'provincia': 'luanda',
            'aliquota_iva_geral': Decimal('7.00'),
            'aliquota_iva_simplificado': Decimal('5.00'),
            'aliquota_iva_cabinda': Decimal('1.00'),
            'aliquota_imposto_industrial_geral': Decimal('25.00'),
            'aliquota_imposto_industrial_especial': Decimal('35.00'),
            'dia_vencimento_impostos': 15,
            'gerar_impostos_automaticamente': True,
        }
