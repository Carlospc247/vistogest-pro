# apps/vendas/models.py
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
import uuid
from django.db import models
from django.conf import settings
from apps.core.models import Empresa
from django.conf import settings
from decimal import Decimal
from apps.core.models import TimeStampedModel, Empresa,  Loja
from apps.clientes.models import Cliente


from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from apps.core.services import gerar_numero_documento
from django.db.models import Sum, F



class FormaPagamento(models.Model):
    FORMA_PAGAMENTO_CHOICES = [
        ('dinheiro', 'Dinheiro'),
        ('cartao_debito', 'Cartão de Débito'),
        ('cartao_credito', 'Cartão de Crédito'),
        ('transferencia', 'Transferência'),
        ('cheque', 'Cheque'),
        ('vale', 'Vale'),
        ('outros', 'Outros'),
    ]
    # Identificação e Associação
    empresa = models.ForeignKey(
        Empresa, 
        on_delete=models.CASCADE, 
        related_name='formas_pagamento'
    )
    nome = models.CharField("Nome", max_length=100)
    codigo = models.CharField("Código", max_length=20, blank=True, null=True, help_text="Código interno para identificação rápida.")
    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=FORMA_PAGAMENTO_CHOICES,
        default='dinheiro'
    )
    ativa = models.BooleanField("Ativa", default=True, help_text="Desmarque para desativar esta forma de pagamento.")

    conta_destino = models.ForeignKey(
        'financeiro.ContaBancaria',
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        verbose_name="Conta Bancária de Crédito"
    )
    
    # Configurações de Parcelamento e Taxas
    permite_parcelamento = models.BooleanField("Permite Parcelamento", default=False)
    max_parcelas = models.PositiveIntegerField("Máximo de Parcelas", default=1, help_text="Número máximo de parcelas permitidas.")
    taxa_administracao = models.DecimalField(
        "Taxa de Administração (%)", 
        max_digits=5, 
        decimal_places=2, 
        default=0.00,
        help_text="Percentual da taxa. Ex: 2.5 para 2.5%"
    )

    # Configurações de Integração e Autorização
    requer_autorizacao = models.BooleanField("Requer Autorização", default=False, help_text="Ex: transações de cartão de crédito.")
    necessita_tef = models.BooleanField("Necessita TEF/POS", default=False, help_text="Marque se requer um terminal de pagamento eletrónico.")
    codigo_integracao = models.CharField("Código de Integração", max_length=50, blank=True, null=True, help_text="Código para integrações com gateways de pagamento.")
    
    # Regras de Validação
    valor_minimo = models.DecimalField("Valor Mínimo", max_digits=10, decimal_places=2, null=True, blank=True)
    valor_maximo = models.DecimalField("Valor Máximo", max_digits=10, decimal_places=2, null=True, blank=True)

    # Organização
    ordem_exibicao = models.PositiveIntegerField("Ordem de Exibição", default=0, help_text="Quanto menor o número, mais acima aparecerá na lista de opções.")

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        # Garante que não há duas formas de pagamento com o mesmo nome para a mesma empresa
        unique_together = ('nome', 'empresa')
        ordering = ['ordem_exibicao', 'nome']

    def __str__(self):
        return self.nome



class Venda(TimeStampedModel):
    """Venda realizada"""
    TIPO_VENDA_CHOICES = [
            ('fatura_recibo', 'Fatura Recibo'),
            ('balcao', 'Balcão'),
            ('entrega', 'Entrega'),
            ('online', 'Online'),
        ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='vendas')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='vendas')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='vendas')
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    #numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Documento Fiscal")
    numero_documento = models.CharField(max_length=200, unique=True)
    #numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Documento Fiscal")
    tipo_venda = models.CharField(max_length=20, choices=TIPO_VENDA_CHOICES, default='fatura_recibo')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    # Data
    data_venda = models.DateTimeField(auto_now_add=True)
    #data_venda = models.DateTimeField(auto_now_add=True, default=timezone.now)

    # Status
    STATUS_CHOICES = [
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
        ('pendente', 'Pendente'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='finalizada')

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)


    def gerar_documento_fiscal(self, usuario):
        """
        Gera número, hash e ATCUD da venda.
        Deve ser chamado apenas **após adicionar todos os itens**.
        """
        if not usuario:
            raise ValueError("Usuário é obrigatório para gerar Documento Fiscal")
        if not self.itens.exists():
            raise ValueError("Não é possível gerar documento sem itens")
        if self.total <= 0:
            raise ValueError("Total da venda inválido para gerar documento")

        from apps.fiscal.services import DocumentoFiscalService
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=self.empresa,
            tipo_documento='FR',
            cliente=self.cliente,
            usuario=usuario,
            linhas=[{
                'produto': item.produto,
                'quantidade': item.quantidade,
                'preco_unitario': item.preco_unitario,
                'desconto': item.desconto_item,
                'iva_valor': item.iva_valor,
            } for item in self.itens.all()],
            dados_extra={'data_emissao': self.data_venda, 'valor_total': self.total},
        )

        self.numero_documento = documento.numero
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['numero_documento', 'hash_documento', 'atcud'])


    def __str__(self):
        return f"Venda {self.numero_documento}"

    class Meta:
        verbose_name = 'Venda'
        verbose_name_plural = 'Vendas'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    desconto_percentual.short_description = 'Desconto %'
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all())
    margem_lucro_total.short_description = 'Margem de Lucro'
    
    def quantidade_itens(self):
        return self.itens.count()
    quantidade_itens.short_description = 'Qtd Itens'



class ItemVenda(TimeStampedModel):
    """Item da venda"""
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens')
    
    # Este é o campo ForeignKey para o modelo Produto
    produto = models.ForeignKey(
        'produtos.Produto', 
        on_delete=models.PROTECT, 
        related_name='itens_venda'
    )
    servico = models.ForeignKey(
        'servicos.Servico',
        on_delete=models.PROTECT,
        related_name='itens_venda',
        null=True, blank=True
    )
    
    # Detalhes da venda no momento da transação (cópia dos dados)
    nome_produto = models.CharField("Nome do Produto", max_length=255, blank=True, null=True)  
    quantidade = models.IntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Campos para serviços
    nome_servico = models.CharField(max_length=255, blank=True, null=True)
    duracao_servico_padrao = models.DurationField(blank=True, null=True)
    instrucoes_servico = models.TextField(blank=True, null=True)


    # Valores calculados
    subtotal_sem_iva = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00
    )
    iva_valor = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00
    )
    taxa_iva = models.ForeignKey(
        'fiscal.TaxaIVAAGT',
        on_delete=models.PROTECT,
        verbose_name="Regime Fiscal (AGT)",
        null=True,  # permite vazio
        blank=True
    )


    tax_type = models.CharField(max_length=3, blank=True, null=True, verbose_name="Tipo de Imposto") # IVA/IS/NS
    tax_code = models.CharField(max_length=3, blank=True, null=True, verbose_name="Código da Taxa") # NOR/ISE/NSU
    

    total = models.DecimalField(max_digits=10, decimal_places=2)

    # ADICIONAR UM MÉTODO SAVE PARA PREENCHER OS NOVOS CAMPOS
    from decimal import Decimal

    def save(self, *args, **kwargs):
        """
        Atualiza automaticamente os campos fiscais (tax_type, tax_code)
        e calcula valores de IVA antes de salvar.
        """
        if self.taxa_iva:
            self.tax_type = self.taxa_iva.tax_type
            self.tax_code = self.taxa_iva.tax_code

            # Define o percentual de IVA
            percentual_iva = getattr(self.taxa_iva, 'tax_percentage', Decimal('0.00'))

            # Calcula valores
            base_calculo = (self.preco_unitario - self.desconto_item) * self.quantidade
            self.subtotal_sem_iva = base_calculo
            self.iva_valor = (base_calculo * percentual_iva) / Decimal('100.00')
            self.total = base_calculo + self.iva_valor
        else:
            self.tax_type = None
            self.tax_code = None
            self.subtotal_sem_iva = (self.preco_unitario - self.desconto_item) * self.quantidade
            self.iva_valor = Decimal('0.00')
            self.total = self.subtotal_sem_iva

        super().save(*args, **kwargs)



      
    class Meta:
        verbose_name = 'Item da Venda'
        verbose_name_plural = 'Itens da Venda'
        
    def __str__(self):
        return f"{self.nome_produto} - {self.quantidade}x"
    
    def clean(self):
        """Validação: precisa ser Produto OU Serviço, não os dois nem nenhum."""
        from django.core.exceptions import ValidationError
        if not self.produto and not self.servico:
            raise ValidationError("O item precisa estar associado a um Produto ou a um Serviço.")
        if self.produto and self.servico:
            raise ValidationError("O item não pode ser associado a Produto e Serviço ao mesmo tempo.")

    @property
    def desconto_percentual(self):
        """Calcula o desconto percentual baseado no preço cheio."""
        if self.preco_unitario > 0:
            return (self.desconto_item / self.preco_unitario) * 100
        return 0
    
    @property
    def iva_percentual(self):
        """Retorna a taxa percentual de IVA configurada."""
        if self.taxa_iva:
            return getattr(self.taxa_iva, 'tax_percentage', Decimal('0.00'))
        return Decimal('0.00')
    
    @property
    def tipo(self):
        if self.produto:
            return "produto"
        elif self.servico:
            return "servico"
        return "indefinido"

class PagamentoVenda(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('aprovado', 'Aprovado'),
        ('rejeitado', 'Rejeitado'),
        ('estornado', 'Estornado'),
        ('cancelado', 'Cancelado'),
    ]

    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='pagamentos')
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)
    observacoes = models.CharField(max_length=255, blank=True, null=True)
    nsu = models.CharField(max_length=100, blank=True)

    valor_pago = models.DecimalField(max_digits=10, decimal_places=2)
    numero_parcelas = models.PositiveIntegerField("Número de Parcelas", default=1)
    valor_parcela = models.DecimalField("Valor da Parcela", max_digits=10, decimal_places=2, default=0.00)
    
    # Campos calculados
    valor_taxa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_liquido = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Dados da transação (gateway de pagamento)
    numero_autorizacao = models.CharField("Autorização", max_length=100, blank=True)
    nsu = models.CharField("NSU", max_length=100, blank=True)
    tid = models.CharField("TID", max_length=100, blank=True)
    
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_processamento = models.DateTimeField("Processado em", null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.forma_pagamento.taxa_administracao > 0:
            self.valor_taxa = (self.valor_pago * self.forma_pagamento.taxa_administracao) / 100
        self.valor_liquido = self.valor_pago - self.valor_taxa

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pagamento de {self.valor_pago} para a Venda {self.venda.numero_documento}"
            

    class Meta:
        verbose_name = "Pagamento de Venda"
        verbose_name_plural = "Pagamentos de Vendas"

class DevolucaoVenda(models.Model):
    MOTIVO_CHOICES = [
        ('arrependimento', 'Arrependimento/Desistência'),
        ('produto_danificado', 'Produto Danificado'),
        ('produto_errado', 'Produto Errado'),
        ('outros', 'Outros'),
    ]

    numero_devolucao = models.CharField("Número da Devolução", max_length=50, unique=True)
    venda_original = models.ForeignKey(Venda, on_delete=models.PROTECT, related_name='devolucoes')
    motivo = models.CharField("Motivo", max_length=30, choices=MOTIVO_CHOICES)
    descricao_motivo = models.TextField("Descrição do Motivo", blank=True)
    
    valor_devolvido = models.DecimalField("Valor Devolvido", max_digits=10, decimal_places=2)
    valor_restituido = models.DecimalField("Valor Restituído", max_digits=10, decimal_places=2, default=0.00)
    taxa_devolucao = models.DecimalField("Taxa de Devolução", max_digits=10, decimal_places=2, default=0.00)
    
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='cliente')
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='devolucoes_solicitadas')
    aprovador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='devolucoes_aprovadas')

    aprovada = models.BooleanField("Aprovada", default=False)
    processada = models.BooleanField("Processada", default=False)
    
    data_devolucao = models.DateTimeField("Data da Devolução", auto_now_add=True)
    observacoes = models.TextField("Observações", blank=True)

    def __str__(self):
        return self.numero_devolucao
        
    class Meta:
        verbose_name = "Devolução de Venda"
        verbose_name_plural = "Devoluções de Vendas"

class ItemDevolucao(models.Model):
    """
    Representa um item de produto específico que está a ser devolvido.
    """
    devolucao = models.ForeignKey('DevolucaoVenda', on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(
        'ItemVenda', 
        on_delete=models.PROTECT,
        help_text="O item exato da venda original que está a ser devolvido."
    )
    quantidade_devolvida = models.DecimalField("Quantidade Devolvida", max_digits=10, decimal_places=3)
    valor_restituido = models.DecimalField("Valor a Restituir", max_digits=10, decimal_places=2)
    motivo = models.TextField("Motivo", blank=True)

    class Meta:
        verbose_name = "Item de Devolução"
        verbose_name_plural = "Itens de Devolução"

    def __str__(self):
        return f"{self.quantidade_devolvida} x {self.item_venda_original.produto.nome} na Devolução #{self.devolucao.id}"

class HistoricoVenda(models.Model):
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='historico')
    status_anterior = models.CharField("Status Anterior", max_length=50)
    status_novo = models.CharField("Status Novo", max_length=50)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    observacoes = models.TextField("Observações", blank=True)

    def __str__(self):
        return f"Venda {self.venda.id}: {self.status_anterior} -> {self.status_novo}"
    
    class Meta:
        verbose_name = "Histórico de Venda"
        verbose_name_plural = "Históricos de Vendas"
        ordering = ['-created_at']
    
class Convenio(models.Model):
    """
    Representa um convênio ou plano de saúde/seguradora que oferece descontos.
    Ex: 'ESSA Seguros', 'Fidelidade Angola', 'Tranquilidade'.
    """
    empresa = models.ForeignKey(
        'core.Empresa', 
        on_delete=models.CASCADE, 
        related_name='convenios'
    )
    nome = models.CharField("Nome do Convênio", max_length=200)
    contato = models.CharField("Pessoa de contato do convenio", max_length=200)
    telefone = models.CharField("Telefone da Seguradora", max_length=9)
    observacoes = models.CharField("OBS:", max_length=200)
    codigo = models.CharField(
        "Código", 
        max_length=50, 
        blank=True, 
        null=True, 
        help_text="Código de identificação do convênio."
    )
    percentual_desconto = models.DecimalField(
        "Percentual de Desconto (%)", 
        max_digits=5, 
        decimal_places=2, 
        default=0.00
    )
    ativa = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Convênio"
        verbose_name_plural = "Convênios"
        unique_together = ('nome', 'empresa')
        ordering = ['nome']

    def __str__(self):
        return self.nome

class Entrega(models.Model):
    """
    Representa o processo de entrega de uma venda.
    """
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('em_preparacao', 'Em Preparação'),
        ('em_rota', 'Em Rota'),
        ('entregue', 'Entregue'),
        ('falhou', 'Falha na Entrega'),
        ('cancelada', 'Cancelada'),
    ]

    venda = models.OneToOneField('Venda', on_delete=models.CASCADE, related_name='entrega')
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    entregador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entregas_realizadas',
        help_text="Utilizador responsável pela entrega."
    )
    endereco = models.TextField("Endereço de Entrega")
    taxa_entrega = models.DecimalField("Taxa de Entrega", max_digits=10, decimal_places=2, default=0.00)
    previsao_entrega = models.DateTimeField("Previsão de Entrega", null=True, blank=True)
    data_entrega_real = models.DateTimeField("Data da Entrega Real", null=True, blank=True)
    observacoes = models.TextField("Observações", blank=True)
    
    class Meta:
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"

    def __str__(self):
        return f"Entrega para a Venda #{self.venda.id} - {self.get_status_display()}"

class Orcamento(models.Model):
    """
    Representa um orçamento ou cotação para um cliente antes de se tornar uma venda.
    """
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('convertido', 'Convertido em Venda'),
        ('cancelado', 'Cancelado'),
        ('expirado', 'Expirado'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.PROTECT)
    numero_orcamento = models.CharField("Número do Orçamento", max_length=50, unique=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='orcamentos')
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orcamentos_criados')
    
    data_emissao = models.DateTimeField("Data de Emissão", auto_now_add=True)
    data_validade = models.DateField("Data de Validade")
    
    valor_subtotal = models.DecimalField("Subtotal", max_digits=10, decimal_places=2, default=0.00)
    valor_desconto = models.DecimalField("Desconto", max_digits=10, decimal_places=2, default=0.00)
    total = models.DecimalField("Valor Total", max_digits=10, decimal_places=2, default=0.00)
    
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    observacoes = models.TextField("Observações", blank=True)
    venda_convertida = models.OneToOneField('Venda', on_delete=models.SET_NULL, null=True, blank=True, related_name='orcamento_origem')

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"
        ordering = ['-data_emissao']

    def __str__(self):
        return self.numero_orcamento

class ItemOrcamento(models.Model):
    """
    Representa um item de produto dentro de um Orçamento.
    """
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT)
    quantidade = models.DecimalField("Quantidade", max_digits=10, decimal_places=3)
    valor_unitario = models.DecimalField("Valor Unitário", max_digits=10, decimal_places=2)
    total = models.DecimalField("Valor Total", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Item de Orçamento"
        verbose_name_plural = "Itens de Orçamentos"

    def __str__(self):
        return f"{self.quantidade} x {self.produto.nome} no Orçamento #{self.orcamento.id}"

class Comissao(models.Model):
    """
    Representa a comissão de um vendedor sobre uma venda específica.
    """
    STATUS_CHOICES = [
        ('pendente', 'Pendente de Pagamento'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
    ]

    venda = models.ForeignKey('Venda', on_delete=models.CASCADE, related_name='comissoes')
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comissoes_ganhas'
    )
    valor_base = models.DecimalField(
        "Valor Base para Comissão", 
        max_digits=10, 
        decimal_places=2,
        help_text="Valor da venda sobre o qual a comissão é calculada."
    )
    percentual = models.DecimalField("Percentual da Comissão (%)", max_digits=5, decimal_places=2)
    valor_comissao = models.DecimalField("Valor da Comissão", max_digits=10, decimal_places=2)
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateField("Data de Pagamento", null=True, blank=True)
    observacoes = models.CharField("OBS", max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comissão"
        verbose_name_plural = "Comissões"
        ordering = ['-created_at']

    def __str__(self):
        return f"Comissão de {self.valor_comissao} Kz para {self.vendedor.username} na Venda #{self.venda.id}"

    def save(self, *args, **kwargs):
        # Calcula o valor da comissão automaticamente antes de guardar
        self.valor_comissao = (self.valor_base * self.percentual) / 100
        super().save(*args, **kwargs)

class MetaVenda(models.Model):
    """Modelo para gerenciar metas de vendas"""
    
    TIPO_META_CHOICES = [
        ('faturamento', 'Faturamento'),
        ('quantidade', 'Quantidade de Vendas'),
        ('produtos', 'Quantidade de Produtos'),
        ('clientes', 'Novos Clientes'),
        ('tickets', 'Ticket Médio'),
        ('mista', 'Meta Mista'),
    ]
    
    STATUS_META_CHOICES = [
        ('ativa', 'Ativa'),
        ('pausada', 'Pausada'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ]
    
    PERIODO_CHOICES = [
        ('mensal', 'Mensal'),
        ('trimestral', 'Trimestral'),
        ('semestral', 'Semestral'),
        ('anual', 'Anual'),
    ]
    
    # Identificação
    codigo_meta = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name='Código da Meta'
    )
    
    nome = models.CharField(
        max_length=100,
        verbose_name='Nome da Meta'
    )
    
    # Relacionamentos
    empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.PROTECT,
        related_name='metas_vendas',
        verbose_name='Empresa'
    )
    
    vendedor = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.PROTECT,
        related_name='metas_vendas',
        null=True,
        blank=True,
        verbose_name='Vendedor',
        help_text='Deixe vazio para meta geral da empresa'
    )
    
    equipe = models.ForeignKey(
        'funcionarios.Equipe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='metas_vendas',
        verbose_name='Equipe'
    )
    
    # Período da meta
    tipo_periodo = models.CharField(
        max_length=20,
        choices=PERIODO_CHOICES,
        default='mensal',
        verbose_name='Tipo de Período'
    )
    
    mes = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        null=True,
        blank=True,
        verbose_name='Mês'
    )
    
    trimestre = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        null=True,
        blank=True,
        verbose_name='Trimestre'
    )
    
    semestre = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(2)],
        null=True,
        blank=True,
        verbose_name='Semestre'
    )
    
    ano = models.PositiveIntegerField(
        validators=[MinValueValidator(2020), MaxValueValidator(2050)],
        verbose_name='Ano'
    )
    
    data_inicio = models.DateField(
        verbose_name='Data de Início'
    )
    
    data_fim = models.DateField(
        verbose_name='Data de Fim'
    )
    
    # Metas específicas
    tipo_meta = models.CharField(
        max_length=20,
        choices=TIPO_META_CHOICES,
        default='faturamento',
        verbose_name='Tipo de Meta'
    )
    
    # Valores das metas
    meta_faturamento = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Meta de Faturamento (AKZ)'
    )
    
    meta_quantidade_vendas = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Meta de Quantidade de Vendas'
    )
    
    meta_quantidade_produtos = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Meta de Quantidade de Produtos'
    )
    
    meta_novos_clientes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Meta de Novos Clientes'
    )
    
    meta_ticket_medio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Meta de Ticket Médio (AKZ)'
    )
    
    # Pesos para meta mista (soma deve ser 100%)
    peso_faturamento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Peso Faturamento (%)'
    )
    
    peso_quantidade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Peso Quantidade (%)'
    )
    
    peso_clientes = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Peso Clientes (%)'
    )
    
    # Status e controle
    status = models.CharField(
        max_length=20,
        choices=STATUS_META_CHOICES,
        default='ativa',
        verbose_name='Status'
    )
    
    # Recompensas e incentivos
    comissao_extra_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Comissão Extra (%)',
        help_text='Percentual extra de comissão ao atingir a meta'
    )
    
    bonus_monetario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Bônus Monetário (AKZ)',
        help_text='Valor fixo pago ao atingir a meta'
    )
    
    premio_descricao = models.TextField(
        blank=True,
        verbose_name='Descrição do Prêmio',
        help_text='Descrição de outros prêmios ou benefícios'
    )
    
    # Configurações avançadas
    permite_superacao = models.BooleanField(
        default=True,
        verbose_name='Permite Superação',
        help_text='Se permite ultrapassar 100% da meta'
    )
    
    bonus_superacao_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name='Bônus por Superação (%)',
        help_text='Percentual extra para cada % acima de 100%'
    )
    
    meta_minima_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80,
        verbose_name='Meta Mínima (%)',
        help_text='Percentual mínimo para receber recompensas'
    )
    
    # Observações e notas
    observacoes = models.TextField(
        blank=True,
        verbose_name='Observações'
    )
    
    criterios_avaliacao = models.TextField(
        blank=True,
        verbose_name='Critérios de Avaliação',
        help_text='Critérios específicos para avaliação desta meta'
    )
    
    # Controle de usuários
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='metas_criadas',
        verbose_name='Criado Por'
    )
    
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='metas_aprovadas',
        verbose_name='Aprovado Por'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    data_aprovacao = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Data de Aprovação'
    )
    
    class Meta:
        verbose_name = 'Meta de Venda'
        verbose_name_plural = 'Metas de Vendas'
        ordering = ['-ano', '-mes', 'vendedor']
        unique_together = [
            ['empresa', 'vendedor', 'tipo_periodo', 'mes', 'ano'],
            ['empresa', 'vendedor', 'tipo_periodo', 'trimestre', 'ano'],
            ['empresa', 'vendedor', 'tipo_periodo', 'semestre', 'ano'],
        ]
        indexes = [
            models.Index(fields=['empresa', 'vendedor', 'status']),
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['data_inicio', 'data_fim']),
            models.Index(fields=['codigo_meta']),
        ]
    
    def __str__(self):
        periodo_str = self.get_periodo_display()
        vendedor_str = f" - {self.vendedor}" if self.vendedor else " - Geral"
        return f"Meta {periodo_str} {self.ano}{vendedor_str}"
    
    def save(self, *args, **kwargs):
        # Gerar código da meta se não existir
        if not self.codigo_meta:
            prefixo = 'MT'
            if self.vendedor:
                prefixo += f"V{self.vendedor.id:03d}"
            else:
                prefixo += "GER"
            
            self.codigo_meta = f"{prefixo}{self.ano}{self.mes or 0:02d}"
        
        # Validar período
        self.validar_periodo()
        
        super().save(*args, **kwargs)
    
    def validar_periodo(self):
        """Validar campos de período baseado no tipo"""
        if self.tipo_periodo == 'mensal' and not self.mes:
            raise ValidationError('Mês é obrigatório para meta mensal')
        elif self.tipo_periodo == 'trimestral' and not self.trimestre:
            raise ValidationError('Trimestre é obrigatório para meta trimestral')
        elif self.tipo_periodo == 'semestral' and not self.semestre:
            raise ValidationError('Semestre é obrigatório para meta semestral')
    
    def get_periodo_display(self):
        """Retornar descrição do período"""
        if self.tipo_periodo == 'mensal':
            meses = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                    'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            return f"{meses[self.mes]}/{self.ano}"
        elif self.tipo_periodo == 'trimestral':
            return f"{self.trimestre}º Tri/{self.ano}"
        elif self.tipo_periodo == 'semestral':
            return f"{self.semestre}º Sem/{self.ano}"
        else:
            return str(self.ano)
    
    def calcular_realizado(self):
        """Calcular valores realizados no período"""
        vendas = Venda.objects.filter(
            empresa=self.empresa,
            data_venda__gte=self.data_inicio,
            data_venda__lte=self.data_fim,
            status='finalizada'
        )
        
        if self.vendedor:
            vendas = vendas.filter(vendedor=self.vendedor)
        
        # Agregar dados
        resultado = vendas.aggregate(
            faturamento_realizado=models.Sum('total'),
            quantidade_vendas_realizada=models.Count('id'),
            quantidade_produtos_realizada=models.Sum('itens__quantidade'),
            ticket_medio_realizado=models.Avg('total')
        )
        
        # Novos clientes
        clientes_periodo = vendas.filter(
            cliente__isnull=False
        ).values('cliente').distinct()
        
        # Clientes que fizeram primeira compra no período
        novos_clientes = 0
        for cliente_data in clientes_periodo:
            primeira_compra = Venda.objects.filter(
                empresa=self.empresa,
                cliente_id=cliente_data['cliente'],
                status='finalizada'
            ).order_by('data_venda').first()
            
            if (primeira_compra and 
                self.data_inicio <= primeira_compra.data_venda.date() <= self.data_fim):
                novos_clientes += 1
        
        resultado['novos_clientes_realizados'] = novos_clientes
        
        # Tratar valores None
        for key, value in resultado.items():
            if value is None:
                resultado[key] = 0
        
        return resultado
    
    def calcular_percentual_atingimento(self):
        """Calcular percentual de atingimento da meta"""
        realizado = self.calcular_realizado()
        percentuais = {}
        
        if self.meta_faturamento and self.meta_faturamento > 0:
            percentuais['faturamento'] = (
                realizado['faturamento_realizado'] / float(self.meta_faturamento) * 100
            )
        
        if self.meta_quantidade_vendas and self.meta_quantidade_vendas > 0:
            percentuais['quantidade_vendas'] = (
                realizado['quantidade_vendas_realizada'] / self.meta_quantidade_vendas * 100
            )
        
        if self.meta_quantidade_produtos and self.meta_quantidade_produtos > 0:
            percentuais['quantidade_produtos'] = (
                realizado['quantidade_produtos_realizada'] / self.meta_quantidade_produtos * 100
            )
        
        if self.meta_novos_clientes and self.meta_novos_clientes > 0:
            percentuais['novos_clientes'] = (
                realizado['novos_clientes_realizados'] / self.meta_novos_clientes * 100
            )
        
        if self.meta_ticket_medio and self.meta_ticket_medio > 0:
            percentuais['ticket_medio'] = (
                realizado['ticket_medio_realizado'] / float(self.meta_ticket_medio) * 100
            )
        
        return percentuais
    
    def calcular_percentual_geral(self):
        """Calcular percentual geral baseado no tipo de meta"""
        percentuais = self.calcular_percentual_atingimento()
        
        if self.tipo_meta == 'mista':
            # Meta mista: calcular média ponderada
            total_peso = float(self.peso_faturamento + self.peso_quantidade + self.peso_clientes)
            if total_peso == 0:
                return 0
            
            percentual_geral = 0
            if self.peso_faturamento > 0 and 'faturamento' in percentuais:
                percentual_geral += (percentuais['faturamento'] * float(self.peso_faturamento) / 100)
            
            if self.peso_quantidade > 0 and 'quantidade_vendas' in percentuais:
                percentual_geral += (percentuais['quantidade_vendas'] * float(self.peso_quantidade) / 100)
            
            if self.peso_clientes > 0 and 'novos_clientes' in percentuais:
                percentual_geral += (percentuais['novos_clientes'] * float(self.peso_clientes) / 100)
            
            return percentual_geral * 100 / total_peso
        
        else:
            # Meta simples: retornar percentual do tipo específico
            tipo_map = {
                'faturamento': 'faturamento',
                'quantidade': 'quantidade_vendas',
                'produtos': 'quantidade_produtos',
                'clientes': 'novos_clientes',
                'tickets': 'ticket_medio',
            }
            
            key = tipo_map.get(self.tipo_meta)
            return percentuais.get(key, 0)
    
    def meta_atingida(self):
        """Verificar se a meta foi atingida"""
        percentual = self.calcular_percentual_geral()
        return percentual >= float(self.meta_minima_percentual)
    
    def calcular_bonus(self):
        """Calcular bônus baseado no atingimento"""
        if not self.meta_atingida():
            return 0
        
        percentual = self.calcular_percentual_geral()
        bonus_total = float(self.bonus_monetario)
        
        # Bônus por superação
        if percentual > 100 and self.permite_superacao:
            superacao = percentual - 100
            bonus_superacao = superacao * float(self.bonus_superacao_percentual) / 100
            bonus_total += bonus_superacao
        
        return bonus_total
    
    def calcular_comissao_extra(self):
        """Calcular comissão extra baseada no atingimento"""
        if not self.meta_atingida():
            return 0
        
        realizado = self.calcular_realizado()
        faturamento = realizado['faturamento_realizado']
        
        comissao_extra = faturamento * float(self.comissao_extra_percentual) / 100
        
        return comissao_extra
    
    def gerar_relatorio_atingimento(self):
        """Gerar relatório completo de atingimento"""
        realizado = self.calcular_realizado()
        percentuais = self.calcular_percentual_atingimento()
        percentual_geral = self.calcular_percentual_geral()
        
        return {
            'meta': self,
            'realizado': realizado,
            'percentuais': percentuais,
            'percentual_geral': percentual_geral,
            'meta_atingida': self.meta_atingida(),
            'bonus_calculado': self.calcular_bonus(),
            'comissao_extra': self.calcular_comissao_extra(),
            'dias_restantes': (self.data_fim - timezone.now().date()).days,
            'periodo_display': self.get_periodo_display(),
        }
    
    @property
    def esta_ativa(self):
        """Verificar se a meta está no período ativo"""
        hoje = timezone.now().date()
        return (
            self.status == 'ativa' and
            self.data_inicio <= hoje <= self.data_fim
        )
    
    @property
    def periodo_vencido(self):
        """Verificar se o período da meta já venceu"""
        return timezone.now().date() > self.data_fim

@receiver(post_save, sender=MetaVenda)
def verificar_meta_vencida(sender, instance, **kwargs):
    """Verificar e finalizar metas vencidas automaticamente"""
    if instance.periodo_vencido and instance.status == 'ativa':
        instance.status = 'finalizada'
        instance.save(update_fields=['status'])    


class FaturaCredito(TimeStampedModel):
    """Fatura de Crédito (FT) - Documento de venda a crédito"""
    TIPO_FATURA_CHOICES = [
        ('credito', 'Crédito'),
        ('prazo', 'A Prazo'),
        ('parcelada', 'Parcelada'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='faturas_credito')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='faturas_credito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Fatura")
    tipo_fatura = models.CharField(max_length=20, choices=TIPO_FATURA_CHOICES, default='credito')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    data_fatura = models.DateTimeField(auto_now_add=True)
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")

    # Status
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('parcial', 'Pago Parcialmente'),
        ('liquidada', 'Liquidada'),
        ('cancelada', 'Cancelada'),
        ('vencida', 'Vencida'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    tem_fatura = models.BooleanField(default=True)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    def gerar_documento_fiscal(self, usuario):
        if not usuario:
            raise ValueError("Usuário obrigatório para gerar Documento Fiscal")
        if not self.itens.exists():
            raise ValueError("Não é possível gerar documento sem itens")
        if self.total <= 0:
            raise ValueError("Total da fatura inválido")

        from apps.fiscal.services import DocumentoFiscalService
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=self.empresa,
            tipo_documento='FT',
            cliente=self.cliente,
            usuario=usuario,
            linhas=[{
                'produto': item.produto,
                'quantidade': item.quantidade,
                'preco_unitario': item.preco_unitario,
                'desconto': item.desconto_item,
                'iva_valor': item.iva_valor,
            } for item in self.itens.all()],
            dados_extra={'data_emissao': self.data_fatura, 'valor_total': self.total},
        )

        self.numero_documento = documento.numero
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['numero_documento', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"Fatura {self.numero_documento}"

    class Meta:
        verbose_name = 'Fatura de Crédito'
        verbose_name_plural = 'Faturas de Crédito'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    
    def quantidade_itens(self):
        return self.itens.count()
    
    def valor_pendente(self):
        """Calcula o saldo devedor."""
        return self.total - self.valor_pago


class Recibo(TimeStampedModel):
    """Recibo (REC) - Documento de quitação de pagamento"""
    TIPO_RECIBO_CHOICES = [
        ('pagamento_fatura', 'Pagamento de Fatura'),
        ('prestacao_servico', 'Prestação de Serviço'),
        ('venda_avulsa', 'Venda Avulsa'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='recibos')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='recibos')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_recibo = models.CharField(max_length=200, unique=True, verbose_name="Nº Recibo")
    tipo_recibo = models.CharField(max_length=20, choices=TIPO_RECIBO_CHOICES, default='venda_avulsa')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    data_recibo = models.DateTimeField(auto_now_add=True)

    # Status
    STATUS_CHOICES = [
        ('emitido', 'Emitido'),
        ('cancelado', 'Cancelado'),
        ('pendente', 'Pendente'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitido')

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=True)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    def gerar_documento_fiscal(self):
        if not self.vendedor:
            raise ValueError("Vendedor obrigatório para gerar Documento Fiscal")
        if not self.total > 0:
            raise ValueError("Total do recibo inválido")

        from apps.fiscal.services import DocumentoFiscalService
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=self.empresa,
            tipo_documento='REC',
            cliente=self.cliente,
            usuario=self.vendedor.user,
            linhas=[{
                'produto': item.produto,
                'quantidade': item.quantidade,
                'preco_unitario': item.preco_unitario,
                'desconto': item.desconto_item,
                'iva_valor': item.iva_valor,
            } for item in getattr(self, 'itens', [])],
            dados_extra={'data_emissao': self.data_recibo, 'valor_total': self.total},
        )

        self.numero_recibo = documento.numero
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['numero_recibo', 'hash_documento', 'atcud'])

        
    def __str__(self):
        return f"Recibo {self.numero_recibo}"

    class Meta:
        verbose_name = 'Recibo'
        verbose_name_plural = 'Recibos'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    
    def quantidade_itens(self):
        return self.itens.count()


class ItemFatura(models.Model):
    """
    Representa um item (produto ou serviço) dentro de uma Fatura a Crédito (FT).
    """
    # Relação com a Fatura (dívida)
    fatura = models.ForeignKey(
        'vendas.FaturaCredito', 
        on_delete=models.CASCADE, 
        related_name='itens', 
        verbose_name="Fatura de Crédito"
    )
    
    # Relações Opcionais (Um item pode ser produto OU serviço)
    produto = models.ForeignKey(
        'produtos.Produto', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        verbose_name="Produto"
    )
    servico = models.ForeignKey(
        'servicos.Servico', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        verbose_name="Serviço"
    )
    
    # Dados de Venda do Item (Snapshot)
    # Estes campos devem armazenar os valores no momento da faturação (snapshot)
    nome_item = models.CharField(max_length=255, verbose_name="Nome/Descrição")
    quantidade = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário")
    
    # Descontos e Impostos
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Desconto (Valor)")
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name="% IVA")
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    taxa_iva = models.ForeignKey(
        'fiscal.TaxaIVAAGT',
        on_delete=models.PROTECT,
        verbose_name="Regime Fiscal (AGT)",
        null=True,  # permite vazio
        blank=True
    )
    # Totais
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Subtotal Bruto")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total do Item (c/ IVA)")

    def save(self, *args, **kwargs):
        """
        Garante que nome_item seja preenchido e recalcula os totais 
        se necessário antes de salvar. (Prática recomendada)
        """
        # Preenche o nome do item para evitar problemas se o produto/serviço for apagado (SET_NULL)
        if not self.nome_item:
            if self.produto:
                self.nome_item = self.produto.nome
            elif self.servico:
                self.nome_item = self.servico.nome
            else:
                self.nome_item = "Item Genérico" # Fallback

        # A lógica de cálculo deve idealmente ocorrer no serviço de criação da Fatura,
        # mas podemos colocar um cálculo básico de segurança aqui.
        self.subtotal = self.preco_unitario * self.quantidade
        
        # Calcular total com desconto e IVA
        valor_liquido = self.subtotal - self.desconto_item
        self.iva_valor = valor_liquido * (self.iva_percentual / Decimal('100.00'))
        self.total = valor_liquido + self.iva_valor
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome_item} ({self.quantidade}x)"

    class Meta:
        verbose_name = 'Item da Fatura de Crédito'
        verbose_name_plural = 'Itens da Fatura de Crédito'



class FaturaProforma(TimeStampedModel):
    """Fatura Proforma (FP) - Documento de orçamento formal"""
    TIPO_PROFORMA_CHOICES = [
        ('orcamento', 'Orçamento'),
        ('proposta', 'Proposta'),
        ('cotacao', 'Cotação'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='faturas_proforma')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='faturas_proforma')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Proforma")
    tipo_proforma = models.CharField(max_length=20, choices=TIPO_PROFORMA_CHOICES, default='orcamento')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    data_proforma = models.DateTimeField(auto_now_add=True)
    data_validade = models.DateField(verbose_name="Data de Validade")

    # Status
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('aceite', 'Aceite'),
        ('rejeitada', 'Rejeitada'),
        ('convertida', 'Convertida'),
        ('cancelada', 'Cancelada'),
        ('expirada', 'Expirada'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=True)

    def save(self, *args, criar_documento=True, usuario_criacao=None, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()

            # Usuário que será registrado como criador do DocumentoFiscal
            usuario = self.vendedor.user if self.vendedor else usuario_criacao
            if usuario is None:
                raise ValueError("É necessário fornecer um usuário para criar o documento fiscal.")

            documento = service.criar_documento(
                empresa=self.empresa,
                tipo_documento='FP',
                cliente=self.cliente,
                usuario=usuario,
                linhas=[],
                dados_extra={'data_emissao': self.data_proforma, 'valor_total': self.total},
            )

            self.numero_documento = documento.numero
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['numero_documento', 'hash_documento', 'atcud'])


    def __str__(self):
        return f"Proforma {self.numero_documento}"

    class Meta:
        verbose_name = 'Fatura Proforma'
        verbose_name_plural = 'Faturas Proforma'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    
    def quantidade_itens(self):
        return self.itens.count()

    def get_itens_proforma(self):
        from django.db.models import F, Value
        from django.db.models.functions import Coalesce

        return list(
            self.itens.select_related('produto', 'servico').annotate(
                nome_item=Coalesce('produto__nome_produto', 'servico__nome')
            ).values(
                'quantidade',
                'preco_unitario',
                'desconto_item',
                'iva_percentual',
                'iva_valor',
                'total',
                'nome_item'
            )
        )



class ItemProforma(models.Model):
    """
    Itens associados a uma Fatura Proforma. Essencialmente igual ao ItemVenda.
    """
    proforma = models.ForeignKey(
        FaturaProforma, 
        on_delete=models.CASCADE, 
        related_name='itens' # Nome usado no método get_itens_proforma
    )
    
    # Assumindo que você tem modelos Produto e Servico
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)
    
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxa_iva = models.ForeignKey(
        'fiscal.TaxaIVAAGT',
        on_delete=models.PROTECT,
        verbose_name="Regime Fiscal (AGT)",
        null=True,  # permite vazio
        blank=True
    )
    
    def save(self, *args, **kwargs):
        # Lógica de negócio: Recálculo do total e IVA ANTES de salvar o item
        subtotal_base = self.quantidade * self.preco_unitario
        self.total = subtotal_base - self.desconto_item
        self.iva_valor = self.total * (self.iva_percentual / 100)
        self.total += self.iva_valor
        
        super().save(*args, **kwargs)
        
        # Opcional: Recalcular e salvar os totais da FaturaProforma após salvar o item
        #self.proforma.calcular_totais()



class NotaCredito(TimeStampedModel):
    """Nota de Crédito (NC) - Documento que reduz o valor de uma fatura"""
    TIPO_NOTA_CHOICES = [
        ('devolucao', 'Devolução'),
        ('desconto', 'Desconto'),
        ('correcao', 'Correção'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='notas_credito')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='notas_credito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_nota = models.CharField(max_length=200, unique=True, verbose_name="Nº Nota de Crédito")
    tipo_nota = models.CharField(max_length=20, choices=TIPO_NOTA_CHOICES, default='devolucao')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    data_nota = models.DateTimeField(auto_now_add=True)

    # Status
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('aplicada', 'Aplicada'),
        ('cancelada', 'Cancelada'),
        ('pendente', 'Pendente'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    # ✅ Campos de aprovação/aplicação
    requer_aprovacao = models.BooleanField(default=False, verbose_name="Requer Aprovação?")
    aplicada_por = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notas_credito_aplicadas'
    )
    aprovada_por = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notas_credito_aprovadas'
    )
    data_aplicacao = models.DateTimeField(null=True, blank=True, verbose_name="Data da Aplicação")
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name="Data da Aprovação")

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    # Documento de origem
    venda_origem = models.ForeignKey(
        'Venda', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='notas_credito_origem',
        verbose_name="Venda de Origem (FR)"
    )
    fatura_credito_origem = models.ForeignKey(
        'FaturaCredito', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='notas_credito_origem',
        verbose_name="Fatura Crédito de Origem (FT)"
    )

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService
    
            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=self.empresa,
                tipo_documento='NC',
                cliente=self.cliente,
                usuario=self.vendedor.user if self.vendedor else None,
                linhas=[],
                dados_extra={'data_emissao': self.data_nota, 'valor_total': self.total},
            )

            self.numero_nota = documento.numero
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['numero_nota', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"NC {self.numero_nota}"

    class Meta:
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    
    def quantidade_itens(self):
        return self.itens.count()

    @property
    def documento_origem(self):
        """Retorna o documento de origem (Venda ou Fatura Crédito)"""
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        """Retorna o número do documento de origem"""
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"

class ItemNotaCredito(TimeStampedModel):
    """Itens específicos da Nota de Crédito"""
    nota_credito = models.ForeignKey(NotaCredito, on_delete=models.CASCADE, related_name='itens')
    
    # Referência ao item original
    item_venda_original = models.ForeignKey(
        'ItemVenda', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        verbose_name="Item da Venda Original"
    )
    item_fatura_original = models.ForeignKey(
        'ItemFatura', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        verbose_name="Item da Fatura Original"
    )
    
    # Produto/Serviço
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)
    
    # Dados do item (snapshot)
    descricao_item = models.CharField(max_length=255, verbose_name="Descrição do Item")
    quantidade_creditada = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade Creditada")
    valor_unitario_credito = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Unitário do Crédito")
    
    # Impostos
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey(
        'fiscal.TaxaIVAAGT',
        on_delete=models.PROTECT,
        verbose_name="Regime Fiscal (AGT)",
        null=True,  # permite vazio
        blank=True
    )
    # Total
    total_item_credito = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total do Item Creditado")
    
    # Motivo específico do item
    motivo_item = models.TextField(blank=True, verbose_name="Motivo Específico do Item")

    class Meta:
        verbose_name = 'Item da Nota de Crédito'
        verbose_name_plural = 'Itens da Nota de Crédito'

    def save(self, *args, **kwargs):
        # Calcular valores automaticamente
        subtotal = self.quantidade_creditada * self.valor_unitario_credito
        self.iva_valor = subtotal * (self.iva_percentual / Decimal('100.00'))
        self.total_item_credito = subtotal + self.iva_valor
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_item} - Qtd: {self.quantidade_creditada}"

class NotaDebito(TimeStampedModel):
    """Nota de Débito (ND) - Documento que aumenta o valor de uma fatura"""
    TIPO_NOTA_CHOICES = [
        ('cobranca', 'Cobrança Adicional'),
        ('juros', 'Juros'),
        ('multa', 'Multa'),
        ('correcao', 'Correção'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='notas_debito')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='notas_debito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_nota = models.CharField(max_length=200, unique=True, verbose_name="Nº Nota de Débito")
    tipo_nota = models.CharField(max_length=20, choices=TIPO_NOTA_CHOICES, default='cobranca')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    data_nota = models.DateTimeField(auto_now_add=True)
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")

    # Status
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('aplicada', 'Aplicada'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
        ('vencida', 'Vencida'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    # ✅ Campos de aprovação/aplicação
    requer_aprovacao = models.BooleanField(default=False, verbose_name="Requer Aprovação?")
    aplicada_por = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notas_debito_aplicadas'
    )
    aprovada_por = models.ForeignKey(
        'funcionarios.Funcionario',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notas_debito_aprovadas'
    )
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name="Data da Aprovação")
    data_aplicacao = models.DateTimeField(null=True, blank=True, verbose_name="Data da Aprovação")

    

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    # Documento de origem
    venda_origem = models.ForeignKey(
        Venda, 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='notas_debito_origem',
        verbose_name="Venda de Origem (FR)"
    )
    fatura_credito_origem = models.ForeignKey(
        FaturaCredito, 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='notas_debito_origem',
        verbose_name="Fatura Crédito de Origem (FT)"
    )

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=self.empresa,
                tipo_documento='ND',
                cliente=self.cliente,
                usuario=self.vendedor.user if self.vendedor else None,
                linhas=[],
                dados_extra={'data_emissao': self.data_nota, 'valor_total': self.total},
            )

            self.numero_nota = documento.numero
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['numero_nota', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"ND {self.numero_nota}"

    class Meta:
        verbose_name = 'Nota de Débito'
        verbose_name_plural = 'Notas de Débito'
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    
    def quantidade_itens(self):
        return self.itens.count()

    @property
    def documento_origem(self):
        """Retorna o documento de origem (Venda ou Fatura Crédito)"""
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        """Retorna o número do documento de origem"""
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"

    @property
    def valor_pendente(self):
        """Calcula o valor pendente de pagamento"""
        return self.total - self.valor_pago

    @property
    def esta_paga(self):
        """Verifica se a nota de débito está totalmente paga"""
        return self.valor_pendente <= Decimal('0.00')

class ItemNotaDebito(TimeStampedModel):
    """Itens específicos da Nota de Débito"""
    nota_debito = models.ForeignKey(NotaDebito, on_delete=models.CASCADE, related_name='itens')
    
    # Produto/Serviço (pode ser novo, não necessariamente da fatura original)
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)
    
    # Dados do item
    descricao_item = models.CharField(max_length=255, verbose_name="Descrição do Item")
    quantidade = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade")
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor Unitário")
    
    # Impostos
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey(
        'fiscal.TaxaIVAAGT',
        on_delete=models.PROTECT,
        verbose_name="Regime Fiscal (AGT)",
        null=True,  # permite vazio
        blank=True
    )
    # Total
    total_item = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total do Item")
    
    # Justificativa específica do item
    justificativa = models.TextField(blank=True, verbose_name="Justificativa do Item")

    class Meta:
        verbose_name = 'Item da Nota de Débito'
        verbose_name_plural = 'Itens da Nota de Débito'

    def save(self, *args, **kwargs):
        # Calcular valores automaticamente
        subtotal = self.quantidade * self.valor_unitario
        self.iva_valor = subtotal * (self.iva_percentual / Decimal('100.00'))
        self.total_item = subtotal + self.iva_valor
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_item} - Qtd: {self.quantidade}"


class DocumentoTransporte(TimeStampedModel):
    """Documento de Transporte (GT) - Documento que acompanha mercadorias em trânsito"""
    TIPO_TRANSPORTE_CHOICES = [
        ('proprio', 'Transporte Próprio'),
        ('terceirizado', 'Transporte Terceirizado'),
        ('correios', 'Correios'),
        ('transportadora', 'Transportadora'),
        ('entrega_propria', 'Entrega Própria'),
    ]

    TIPO_OPERACAO_CHOICES = [
        ('venda', 'Venda de Mercadoria'),
        ('transferencia', 'Transferência entre Lojas'),
        ('consignacao', 'Consignação'),
        ('demonstracao', 'Demonstração'),
        ('devolucao', 'Devolução'),
        ('garantia', 'Garantia'),
        ('outros', 'Outros'),
    ]
    
    empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE, related_name='documentos_transporte')
    loja = models.ForeignKey('core.Loja', on_delete=models.SET_NULL, null=True, blank=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True)
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True, related_name='documentos_transporte')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, default=1)
    
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Valor do IVA")
    
    # Identificação
    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Documento de Transporte")
    tipo_operacao = models.CharField(max_length=20, choices=TIPO_OPERACAO_CHOICES, default='venda')
    tipo_transporte = models.CharField(max_length=20, choices=TIPO_TRANSPORTE_CHOICES, default='proprio')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    hash_documento = models.CharField(
        max_length=256, 
        unique=True, 
        null=True, 
        blank=True,
        verbose_name="Hash Criptográfico (SAF-T)"
    )
    atcud = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        verbose_name="ATCUD (Código Único do Documento)"
    )
    
    # Data
    data_documento = models.DateTimeField(auto_now_add=True)
    data_inicio_transporte = models.DateTimeField(verbose_name="Data/Hora de Início do Transporte")
    data_previsao_entrega = models.DateTimeField(verbose_name="Previsão de Entrega")
    data_entrega_real = models.DateTimeField(null=True, blank=True, verbose_name="Data/Hora da Entrega Real")

    # Status
    STATUS_CHOICES = [
        ('preparando', 'Preparando Carga'),
        ('em_transito', 'Em Trânsito'),
        ('entregue', 'Entregue'),
        ('devolvido', 'Devolvido'),
        ('cancelado', 'Cancelado'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preparando')

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    # Documento de Origem
    venda_origem = models.ForeignKey(
        'Venda', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='documentos_transporte',
        verbose_name="Venda de Origem"
    )
    fatura_credito_origem = models.ForeignKey(
        'FaturaCredito', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='documentos_transporte',
        verbose_name="Fatura Crédito de Origem"
    )

    # === REMETENTE (Empresa) ===
    remetente_nome = models.CharField(max_length=200, verbose_name="Nome do Remetente")
    remetente_nif = models.CharField(max_length=20, verbose_name="NIF do Remetente")
    remetente_endereco = models.CharField(max_length=300, verbose_name="Endereço do Remetente")
    remetente_telefone = models.CharField(max_length=20, verbose_name="Telefone do Remetente")
    remetente_provincia = models.CharField(max_length=50, verbose_name="Província do Remetente")
    
    # === DESTINATÁRIO ===
    destinatario_cliente = models.ForeignKey(
        'clientes.Cliente', 
        on_delete=models.PROTECT, 
        null=True, blank=True,
        related_name='documentos_transporte_destinatario'
    )
    destinatario_nome = models.CharField(max_length=200, verbose_name="Nome do Destinatário")
    destinatario_nif = models.CharField(max_length=20, blank=True, verbose_name="NIF/BI do Destinatário")
    destinatario_endereco = models.CharField(max_length=300, verbose_name="Endereço de Entrega")
    destinatario_telefone = models.CharField(max_length=20, verbose_name="Telefone do Destinatário")
    destinatario_provincia = models.CharField(max_length=50, verbose_name="Província do Destinatário")
    
    # === TRANSPORTADOR ===
    transportador_nome = models.CharField(max_length=200, verbose_name="Nome do Transportador")
    transportador_nif = models.CharField(max_length=20, blank=True, verbose_name="NIF do Transportador")
    transportador_telefone = models.CharField(max_length=20, verbose_name="Telefone do Transportador")
    
    # === VEÍCULO ===
    veiculo_matricula = models.CharField(max_length=20, verbose_name="Matrícula do Veículo")
    veiculo_modelo = models.CharField(max_length=100, verbose_name="Modelo do Veículo")
    condutor_nome = models.CharField(max_length=200, verbose_name="Nome do Condutor")
    condutor_carta = models.CharField(max_length=20, verbose_name="Número da Carta de Condução")
    
    # === ITINERÁRIO ===
    local_carregamento = models.CharField(max_length=300, verbose_name="Local de Carregamento")
    local_descarga = models.CharField(max_length=300, verbose_name="Local de Descarga")
    itinerario = models.TextField(verbose_name="Itinerário Detalhado")
    
    # === VALORES ADICIONAIS DE TRANSPORTE ===
    valor_transporte = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        verbose_name="Valor do Transporte"
    )
    peso_total = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        default=Decimal('0.000'),
        verbose_name="Peso Total (Kg)"
    )
    volume_total = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        default=Decimal('0.000'),
        verbose_name="Volume Total (m³)"
    )
    quantidade_volumes = models.PositiveIntegerField(default=1, verbose_name="Quantidade de Volumes")
    
    # Instruções e Controle
    instrucoes_especiais = models.TextField(blank=True, verbose_name="Instruções Especiais")
    
    # Assinaturas e Confirmações
    assinatura_remetente = models.CharField(max_length=200, blank=True, verbose_name="Assinatura do Remetente")
    assinatura_transportador = models.CharField(max_length=200, blank=True, verbose_name="Assinatura do Transportador")
    assinatura_destinatario = models.CharField(max_length=200, blank=True, verbose_name="Assinatura do Destinatário")
    
    # Auditoria
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_transporte_emitidos'
    )
    confirmado_entrega_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documentos_transporte_confirmados'
    )

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding
        
        # Preencher dados do remetente automaticamente
        if not self.remetente_nome and self.empresa:
            config_fiscal = getattr(self.empresa, 'config_fiscal', None)
            if config_fiscal:
                self.remetente_nome = config_fiscal.razao_social or self.empresa.nome
                self.remetente_nif = config_fiscal.nif
                self.remetente_endereco = config_fiscal.endereco
                self.remetente_telefone = config_fiscal.telefone
        
        # Preencher dados do destinatário se cliente selecionado
        if self.destinatario_cliente and not self.destinatario_nome:
            cliente = self.destinatario_cliente
            self.destinatario_nome = cliente.nome_completo
            self.destinatario_nif = cliente.nif or cliente.bi or ''
            self.destinatario_telefone = cliente.telefone
            
            # Buscar endereço principal
            endereco_principal = cliente.enderecos.filter(endereco_principal=True).first()
            if endereco_principal:
                self.destinatario_endereco = endereco_principal.endereco_completo
                self.destinatario_provincia = endereco_principal.provincia

        super().save(*args, **kwargs)

        # Só gera hash e numeração se for um novo documento
        if criar_documento and is_new and self.status in ['preparando', 'em_transito']:
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=self.empresa,
                tipo_documento='GT',
                cliente=self.cliente or self.destinatario_cliente,
                usuario=self.vendedor.user if self.vendedor else self.emitido_por,
                linhas=[],
                dados_extra={'data_emissao': self.data_documento, 'valor_total': self.total},
            )

            self.numero_documento = documento.numero
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['numero_documento', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"GT {self.numero_documento}"

    class Meta:
        verbose_name = 'Documento de Transporte'
        verbose_name_plural = 'Documentos de Transporte'
        ordering = ['-data_documento']
        permissions = [
            ("emitir_documentotransporte", "Pode emitir Documentos de Transporte"),
            ("confirmar_entrega", "Pode confirmar entregas"),
        ]
    
    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    desconto_percentual.short_description = 'Desconto %'
    
    def margem_lucro_total(self):
        return self.total - sum(item.produto.preco_custo * item.quantidade for item in self.itens.all() if item.produto)
    margem_lucro_total.short_description = 'Margem de Lucro'
    
    def quantidade_itens(self):
        return self.itens.count()
    quantidade_itens.short_description = 'Qtd Itens'

    @property
    def documento_origem(self):
        """Retorna o documento de origem"""
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        """Retorna o número do documento de origem"""
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"

    @property
    def tempo_transporte(self):
        """Calcula o tempo de transporte"""
        if self.data_entrega_real:
            return self.data_entrega_real - self.data_inicio_transporte
        return None

    @property
    def esta_atrasado(self):
        """Verifica se a entrega está atrasada"""
        if self.status in ['entregue', 'cancelado']:
            return False
        return timezone.now() > self.data_previsao_entrega

    def confirmar_entrega(self, usuario, assinatura_destinatario=None):
        """Confirma a entrega da mercadoria"""
        if self.status != 'em_transito':
            raise ValidationError("Só é possível confirmar entregas em trânsito")
        
        self.status = 'entregue'
        self.data_entrega_real = timezone.now()
        self.confirmado_entrega_por = usuario
        if assinatura_destinatario:
            self.assinatura_destinatario = assinatura_destinatario
        
        self.save()

    def iniciar_transporte(self):
        """Inicia o transporte"""
        if self.status != 'preparando':
            raise ValidationError("Transporte já foi iniciado")
        
        self.status = 'em_transito'
        self.data_inicio_transporte = timezone.now()
        self.save()

class ItemDocumentoTransporte(TimeStampedModel):
    """Itens do Documento de Transporte"""
    documento = models.ForeignKey(DocumentoTransporte, on_delete=models.CASCADE, related_name='itens')
    
    # Referência ao item original
    item_venda_original = models.ForeignKey(
        ItemVenda, 
        on_delete=models.PROTECT, 
        null=True, blank=True
    )
    item_fatura_original = models.ForeignKey(
        ItemFatura, 
        on_delete=models.PROTECT, 
        null=True, blank=True
    )
    
    # Produto
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    
    # Dados do item (snapshot)
    codigo_produto = models.CharField(max_length=50, verbose_name="Código do Produto")
    descricao_produto = models.CharField(max_length=255, verbose_name="Descrição do Produto")
    unidade_medida = models.CharField(max_length=10, default='UN', verbose_name="Unidade de Medida")
    
    # Quantidades
    quantidade_enviada = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantidade Enviada")
    quantidade_recebida = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        verbose_name="Quantidade Recebida"
    )
    
    # Características físicas
    peso_unitario = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        default=Decimal('0.000'),
        verbose_name="Peso Unitário (Kg)"
    )
    peso_total = models.DecimalField(
        max_digits=10, 
        decimal_places=3, 
        default=Decimal('0.000'),
        verbose_name="Peso Total (Kg)"
    )
    
    # Embalagem
    tipo_embalagem = models.CharField(max_length=50, blank=True, verbose_name="Tipo de Embalagem")
    numero_serie = models.CharField(max_length=100, blank=True, verbose_name="Número de Série")
    lote = models.CharField(max_length=50, blank=True, verbose_name="Lote")
    
    # Valores (para fins de seguro)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Estado da mercadoria
    observacoes_item = models.TextField(blank=True, verbose_name="Observações do Item")

    class Meta:
        verbose_name = 'Item do Documento de Transporte'
        verbose_name_plural = 'Itens do Documento de Transporte'

    def save(self, *args, **kwargs):
        # Calcular peso total e valor total
        self.peso_total = self.quantidade_enviada * self.peso_unitario
        self.valor_total = self.quantidade_enviada * self.valor_unitario
        
        # Preencher dados do produto se disponível
        if self.produto and not self.descricao_produto:
            self.codigo_produto = self.produto.codigo or ''
            self.descricao_produto = self.produto.nome_produto
            self.unidade_medida = getattr(self.produto, 'unidade_medida', 'UN')
            self.peso_unitario = getattr(self.produto, 'peso', Decimal('0.000'))
            self.valor_unitario = self.produto.preco_venda
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_produto} - Qtd: {self.quantidade_enviada}"

    @property
    def divergencia_quantidade(self):
        """Calcula a divergência entre enviado e recebido"""
        return self.quantidade_enviada - self.quantidade_recebida

    @property
    def tem_divergencia(self):
        """Verifica se há divergência na quantidade"""
        return self.divergencia_quantidade != Decimal('0.00')

