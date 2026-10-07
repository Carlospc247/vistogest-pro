# apps/vendas/models.py
"""
Módulo de Vendas.

REGRA DE ARQUITETURA (isolamento físico via django-tenants):
- `vendas` é um TENANT_APP. Cada schema pertence a exatamente UMA empresa.
- Por isso NENHUM modelo aqui tem FK para `empresas.Empresa` (SHARED_APP).
  A empresa "atual" já está implícita pela conexão/schema — quando for
  necessário algum dado da empresa (NIF, nome, regime fiscal, etc.), usa-se
  `connection.tenant` (dentro de models/services) ou `request.user.empresa`
  (dentro de views, já que `Usuario` é SHARED e carrega essa FK legitimamente).
- FKs para `funcionarios.Funcionario`, `clientes.Cliente`, `produtos.Produto`,
  `servicos.Servico`, `fiscal.TaxaIVAAGT`, `financeiro.*` são tenant->tenant:
  permitidas, pois todas essas tabelas vivem no mesmo schema.
- FKs para `settings.AUTH_USER_MODEL` (Usuario) são tenant->shared: permitidas
  (mesmo padrão já usado em apps.financeiro e apps.fiscal).
- O modelo `Loja` foi removido do sistema por completo: não existe mais em
  lugar nenhum, então toda referência a ele foi eliminada.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import connection, models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.models import TimeStampedModel


# =====================================
# FORMAS DE PAGAMENTO
# =====================================

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

    nome = models.CharField("Nome", max_length=100, unique=True)
    codigo = models.CharField("Código", max_length=20, blank=True, null=True,
                               help_text="Código interno para identificação rápida.")
    tipo = models.CharField("Tipo", max_length=20, choices=FORMA_PAGAMENTO_CHOICES, default='dinheiro')
    ativa = models.BooleanField("Ativa", default=True, help_text="Desmarque para desativar esta forma de pagamento.")

    conta_destino = models.ForeignKey(
        'financeiro.ContaBancaria',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Conta Bancária de Crédito"
    )

    permite_parcelamento = models.BooleanField("Permite Parcelamento", default=False)
    max_parcelas = models.PositiveIntegerField("Máximo de Parcelas", default=1)
    taxa_administracao = models.DecimalField("Taxa de Administração (%)", max_digits=5, decimal_places=2,
                                              default=Decimal('0.00'))

    requer_autorizacao = models.BooleanField("Requer Autorização", default=False)
    necessita_tef = models.BooleanField("Necessita TEF/POS", default=False)
    codigo_integracao = models.CharField("Código de Integração", max_length=50, blank=True, null=True)

    valor_minimo = models.DecimalField("Valor Mínimo", max_digits=10, decimal_places=2, null=True, blank=True)
    valor_maximo = models.DecimalField("Valor Máximo", max_digits=10, decimal_places=2, null=True, blank=True)

    ordem_exibicao = models.PositiveIntegerField("Ordem de Exibição", default=0)

    class Meta:
        verbose_name = "Forma de Pagamento"
        verbose_name_plural = "Formas de Pagamento"
        ordering = ['ordem_exibicao', 'nome']

    def __str__(self):
        return self.nome


# =====================================
# VENDA (FR / VD / TV)
# =====================================

class Venda(TimeStampedModel):
    """Venda realizada (Fatura-Recibo, Balcão, Entrega, Online)."""

    TIPO_VENDA_CHOICES = [
        ('fatura_recibo', 'Fatura Recibo'),
        ('balcao', 'Balcão'),
        ('entrega', 'Entrega'),
        ('online', 'Online'),
    ]

    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('pendente', 'Pendente'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ]

    STATUS_ENTREGA_CHOICES = [
        ('nao_aplicavel', 'Não Aplicável'),
        ('agendada', 'Agendada'),
        ('em_rota', 'Em Rota'),
        ('entregue', 'Entregue'),
    ]

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='vendas')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='vendas')
    forma_pagamento = models.ForeignKey(FormaPagamento, on_delete=models.PROTECT)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                     verbose_name="Valor do IVA")

    numero_documento = models.CharField(max_length=200, unique=True)
    tipo_venda = models.CharField(max_length=20, choices=TIPO_VENDA_CHOICES, default='fatura_recibo')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                       verbose_name="Hash Criptográfico (SAF-T)",
                                       help_text="Cache do hash gerado em DocumentoFiscal. Não é a fonte de verdade.")
    atcud = models.CharField(max_length=100, null=True, blank=True, verbose_name="ATCUD",
                              help_text="Cache do ATCUD gerado em DocumentoFiscal. Não é a fonte de verdade.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md):
    # DocumentoFiscal é a única fonte de verdade para hash/ATCUD.
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='venda',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_venda = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='finalizada')

    tem_fatura = models.BooleanField(default=False)
    tem_recibo = models.BooleanField(default=False)
    tem_nota_liquidacao = models.BooleanField(default=False)
    tem_fatura_proforma = models.BooleanField(default=False)

    # Entrega (usado por AgendarEntregaView / DeliveryListView)
    status_entrega = models.CharField(max_length=20, choices=STATUS_ENTREGA_CHOICES, default='nao_aplicavel')

    # Cancelamento (usado por CancelarVendaView / CancelarVendaAPIView)
    data_cancelamento = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.TextField(blank=True)
    # documentCancelReason (Decreto 683/25): obrigatório quando documentStatus = A
    # I = identificação incorrecta do adquirente; N = não enviado ao adquirente
    motivo_cancelamento_codigo = models.CharField(
        max_length=1,
        choices=[('I', 'I — Identificação incorrecta do adquirente'),
                 ('N', 'N — Não enviado ao adquirente')],
        blank=True,
        verbose_name="Código de Motivo de Anulação (documentCancelReason)",
        help_text="Obrigatório quando o documento é anulado (documentStatus='A')."
    )
    usuario_cancelamento = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendas_canceladas'
    )

    # Auditoria (usado por VendaCreateView / VendaUpdateView)
    usuario_criacao = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendas_criadas'
    )
    usuario_modificacao = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendas_modificadas'
    )

    class Meta:
        verbose_name = 'Venda'
        verbose_name_plural = 'Vendas'

    def __str__(self):
        return f"Venda {self.numero_documento}"

    def calcular_totais(self):
        """Recalcula subtotal/total a partir dos itens e do desconto aplicado."""
        self.subtotal = sum((item.preco_unitario * item.quantidade for item in self.itens.all()),
                             Decimal('0.00'))
        self.iva_valor = sum((item.iva_valor for item in self.itens.all()), Decimal('0.00'))
        self.total = self.subtotal - self.desconto_valor + self.iva_valor

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
            empresa=connection.tenant,
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

        # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
        # e sincronizar os campos de cache locais.
        self.documento_fiscal = documento
        self.numero_documento = documento.numero_documento
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])

    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')
    desconto_percentual.short_description = 'Desconto %'

    def margem_lucro_total(self):
        return self.total - sum((item.produto.preco_custo * item.quantidade
                                  for item in self.itens.all() if item.produto), Decimal('0.00'))
    margem_lucro_total.short_description = 'Margem de Lucro'

    def quantidade_itens(self):
        return self.itens.count()
    quantidade_itens.short_description = 'Qtd Itens'

    def calcular_saldo_e_atualizar_status(self):
        """Recalcula valor_pago/troco da venda a partir dos pagamentos não estornados."""
        total_pago = self.pagamentos.exclude(status='estornado').aggregate(
            total=models.Sum('valor_pago'))['total'] or Decimal('0.00')
        self.valor_pago = total_pago
        self.troco = max(total_pago - self.total, Decimal('0.00'))
        self.save(update_fields=['valor_pago', 'troco'])


class ItemVenda(TimeStampedModel):
    """Item da venda (produto ou serviço)."""
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name='itens')

    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, related_name='itens_venda',
                                 null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, related_name='itens_venda',
                                 null=True, blank=True)

    nome_produto = models.CharField("Nome do Produto", max_length=255, blank=True, null=True)
    quantidade = models.IntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    nome_servico = models.CharField(max_length=255, blank=True, null=True)
    duracao_servico_padrao = models.DurationField(blank=True, null=True)
    instrucoes_servico = models.TextField(blank=True, null=True)

    subtotal_sem_iva = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey('fiscal.TaxaIVAAGT', on_delete=models.PROTECT,
                                  verbose_name="Regime Fiscal (AGT)", null=True, blank=True)

    tax_type = models.CharField(max_length=3, blank=True, null=True, verbose_name="Tipo de Imposto")
    tax_code = models.CharField(max_length=3, blank=True, null=True, verbose_name="Código da Taxa")

    # operationType — obrigatório por linha (Decreto 683/25, Anexo I)
    # Identifica a natureza da operação: 'TB' para bens, 'SE' para serviços, etc.
    operation_type = models.CharField(
        max_length=3,
        choices=[
            ('SE',  'SE — Serviços em território nacional'),
            ('SS',  'SS — Serviços no estrangeiro'),
            ('STP', 'STP — Telecomunicações/via electrónica'),
            ('SR',  'SR — Serviços relacionados com imóveis'),
            ('SIF', 'SIF — Intermediação financeira'),
            ('SHS', 'SHS — Hotelaria e similares'),
            ('ST',  'ST — Transporte'),
            ('SG',  'SG — Serviços em geral'),
            ('TB',  'TB — Transmissão de bens'),
            ('AS',  'AS — Aquisição de serviços'),
            ('QT',  'QT — Outras operações tributáveis'),
            ('RD',  'RD — Regularizações e devoluções'),
        ],
        default='TB',
        verbose_name="Tipo de Operação (operationType)",
        help_text="Obrigatório no payload registarFactura. Use TB para produtos, SE para serviços."
    )

    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Item da Venda'
        verbose_name_plural = 'Itens da Venda'

    def save(self, *args, **kwargs):
        if self.taxa_iva:
            self.tax_type = self.taxa_iva.tax_type
            self.tax_code = self.taxa_iva.tax_code
            percentual_iva = getattr(self.taxa_iva, 'tax_percentage', Decimal('0.00'))

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

    def __str__(self):
        return f"{self.nome_produto} - {self.quantidade}x"

    def clean(self):
        if not self.produto and not self.servico:
            raise ValidationError("O item precisa estar associado a um Produto ou a um Serviço.")
        if self.produto and self.servico:
            raise ValidationError("O item não pode ser associado a Produto e Serviço ao mesmo tempo.")

    @property
    def desconto_percentual(self):
        if self.preco_unitario > 0:
            return (self.desconto_item / self.preco_unitario) * 100
        return 0

    @property
    def settlement_amount_calculado(self):
        """
        SettlementAmount por linha = desconto de linha +
        proporção proporcional do desconto global do cabeçalho.
        Regra SAF-T AO / Decreto 683/25: deve reflectir todos os descontos
        que afectam o GrossTotal, incluindo a fatia proporcional do cabeçalho.
        """
        desconto_linha = self.desconto_item or Decimal('0.00')
        try:
            subtotal_doc = self.venda.subtotal or Decimal('1.00')
            desconto_global = self.venda.desconto_valor or Decimal('0.00')
            if subtotal_doc > 0 and desconto_global > 0:
                subtotal_linha = self.subtotal_sem_iva or (self.preco_unitario * self.quantidade)
                proporcao = Decimal(str(subtotal_linha)) / Decimal(str(subtotal_doc))
                return round(desconto_linha + desconto_global * proporcao, 4)
        except Exception:
            pass
        return round(desconto_linha, 4)

    @property
    def iva_percentual(self):
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

    valor_pago = models.DecimalField(max_digits=10, decimal_places=2)
    numero_parcelas = models.PositiveIntegerField("Número de Parcelas", default=1)
    valor_parcela = models.DecimalField("Valor da Parcela", max_digits=10, decimal_places=2, default=0.00)

    valor_taxa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_liquido = models.DecimalField(max_digits=10, decimal_places=2)

    numero_autorizacao = models.CharField("Autorização", max_length=100, blank=True)
    nsu = models.CharField("NSU", max_length=100, blank=True)
    tid = models.CharField("TID", max_length=100, blank=True)

    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateTimeField("Data do Pagamento", auto_now_add=True)
    data_processamento = models.DateTimeField("Processado em", null=True, blank=True)

    # Estorno (usado por EstornarPagamentoView)
    data_estorno = models.DateTimeField(null=True, blank=True)
    motivo_estorno = models.CharField(max_length=255, blank=True)
    usuario_estorno = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pagamentos_estornados'
    )

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

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='devolucoes')
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     related_name='devolucoes_solicitadas')
    aprovador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='devolucoes_aprovadas')

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
    """Item de produto específico que está a ser devolvido."""
    devolucao = models.ForeignKey('DevolucaoVenda', on_delete=models.CASCADE, related_name='itens')
    item_venda_original = models.ForeignKey(
        'ItemVenda', on_delete=models.PROTECT,
        help_text="O item exato da venda original que está a ser devolvido."
    )
    quantidade_devolvida = models.DecimalField("Quantidade Devolvida", max_digits=10, decimal_places=3)
    valor_restituido = models.DecimalField("Valor a Restituir", max_digits=10, decimal_places=2)
    motivo = models.TextField("Motivo", blank=True)

    class Meta:
        verbose_name = "Item de Devolução"
        verbose_name_plural = "Itens de Devolução"

    def __str__(self):
        return f"{self.quantidade_devolvida} x {self.item_venda_original.produto} na Devolução #{self.devolucao.id}"


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
    """Convênio ou plano/seguradora que oferece descontos."""
    nome = models.CharField("Nome do Convênio", max_length=200, unique=True)
    contato = models.CharField("Pessoa de contato do convénio", max_length=200, blank=True)
    telefone = models.CharField("Telefone da Seguradora", max_length=20, blank=True)
    observacoes = models.CharField("OBS", max_length=200, blank=True)
    codigo = models.CharField("Código", max_length=50, blank=True, null=True)
    percentual_desconto = models.DecimalField("Percentual de Desconto (%)", max_digits=5, decimal_places=2,
                                               default=Decimal('0.00'))
    ativa = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Convênio"
        verbose_name_plural = "Convênios"
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Entrega(models.Model):
    """Processo de entrega de uma venda."""
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('agendada', 'Agendada'),
        ('em_preparacao', 'Em Preparação'),
        ('em_rota', 'Em Rota'),
        ('saiu_entrega', 'Saiu para Entrega'),
        ('entregue', 'Entregue'),
        ('falhou', 'Falha na Entrega'),
        ('cancelada', 'Cancelada'),
    ]

    venda = models.OneToOneField('Venda', on_delete=models.CASCADE, related_name='entrega')
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    entregador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='entregas_realizadas'
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='entregas_confirmadas'
    )
    endereco = models.TextField("Endereço de Entrega", blank=True)
    taxa_entrega = models.DecimalField("Taxa de Entrega", max_digits=10, decimal_places=2, default=0.00)
    data_agendada = models.DateTimeField("Data/Hora Agendada", null=True, blank=True)
    previsao_entrega = models.DateTimeField("Previsão de Entrega", null=True, blank=True)
    data_entrega = models.DateTimeField("Data da Entrega", null=True, blank=True)
    observacoes = models.TextField("Observações", blank=True)
    observacoes_entrega = models.TextField("Observações da Entrega", blank=True)

    class Meta:
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"

    def __str__(self):
        return f"Entrega para a Venda #{self.venda.id} - {self.get_status_display()}"


class Orcamento(models.Model):
    """Orçamento/cotação para um cliente antes de se tornar uma venda."""
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('convertido', 'Convertido em Venda'),
        ('cancelado', 'Cancelado'),
        ('expirado', 'Expirado'),
    ]

    numero_orcamento = models.CharField("Número do Orçamento", max_length=50, unique=True)
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, related_name='orcamentos')
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                  related_name='orcamentos_criados')

    data_emissao = models.DateTimeField("Data de Emissão", auto_now_add=True)
    data_validade = models.DateField("Data de Validade")

    valor_subtotal = models.DecimalField("Subtotal", max_digits=10, decimal_places=2, default=0.00)
    valor_desconto = models.DecimalField("Desconto", max_digits=10, decimal_places=2, default=0.00)
    total = models.DecimalField("Valor Total", max_digits=10, decimal_places=2, default=0.00)

    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    observacoes = models.TextField("Observações", blank=True)
    venda_convertida = models.OneToOneField('Venda', on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='orcamento_origem')

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"
        ordering = ['-data_emissao']

    def __str__(self):
        return self.numero_orcamento


class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT)
    quantidade = models.DecimalField("Quantidade", max_digits=10, decimal_places=3)
    valor_unitario = models.DecimalField("Valor Unitário", max_digits=10, decimal_places=2)
    total = models.DecimalField("Valor Total", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Item de Orçamento"
        verbose_name_plural = "Itens de Orçamentos"

    def __str__(self):
        return f"{self.quantidade} x {self.produto} no Orçamento #{self.orcamento.id}"


class Comissao(models.Model):
    """Comissão de um vendedor sobre uma venda específica."""
    STATUS_CHOICES = [
        ('pendente', 'Pendente de Pagamento'),
        ('calculada', 'Calculada'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
    ]

    venda = models.ForeignKey('Venda', on_delete=models.CASCADE, related_name='comissoes')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.PROTECT,
                                  related_name='comissoes_ganhas')
    valor_base = models.DecimalField("Valor Base para Comissão", max_digits=10, decimal_places=2)
    percentual = models.DecimalField("Percentual da Comissão (%)", max_digits=5, decimal_places=2)
    valor_comissao = models.DecimalField("Valor da Comissão", max_digits=10, decimal_places=2)
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    data_pagamento = models.DateField("Data de Pagamento", null=True, blank=True)
    observacoes = models.CharField("OBS", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comissão"
        verbose_name_plural = "Comissões"
        ordering = ['-created_at']

    def __str__(self):
        return f"Comissão de {self.valor_comissao} Kz para {self.vendedor} na Venda #{self.venda.id}"

    def save(self, *args, **kwargs):
        self.valor_comissao = (self.valor_base * self.percentual) / 100
        super().save(*args, **kwargs)


    @classmethod
    def calcular_comissao(cls, venda):
        """
        Cria (ou atualiza) a comissão do vendedor da venda informada,
        usando o percentual de comissão configurado no cadastro do
        próprio funcionário (Funcionario.comissao_percentual).
        Se o vendedor não tiver percentual configurado (ou for 0),
        nenhuma comissão é gerada.
        """
        if not venda.vendedor:
            return None

        percentual = venda.vendedor.comissao_percentual or Decimal('0.00')
        if percentual <= 0:
            return None

        comissao, _ = cls.objects.update_or_create(
            venda=venda,
            vendedor=venda.vendedor,
            defaults={
                'valor_base': venda.total,
                'percentual': percentual,
                'status': 'calculada',
            }
        )
        return comissao


class MetaVenda(models.Model):
    """Metas de vendas por vendedor/equipe/empresa (empresa = o próprio tenant)."""

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

    codigo_meta = models.CharField(max_length=20, unique=True, blank=True, verbose_name='Código da Meta')
    nome = models.CharField(max_length=100, verbose_name='Nome da Meta')

    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.PROTECT,
                                  related_name='metas_vendas', null=True, blank=True,
                                  help_text='Deixe vazio para meta geral da empresa')
    equipe = models.ForeignKey('funcionarios.Equipe', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='metas_vendas')

    tipo_periodo = models.CharField(max_length=20, choices=PERIODO_CHOICES, default='mensal')
    mes = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], null=True, blank=True)
    trimestre = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(4)], null=True, blank=True)
    semestre = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(2)], null=True, blank=True)
    ano = models.PositiveIntegerField(validators=[MinValueValidator(2020), MaxValueValidator(2050)])
    data_inicio = models.DateField()
    data_fim = models.DateField()

    tipo_meta = models.CharField(max_length=20, choices=TIPO_META_CHOICES, default='faturamento')

    meta_faturamento = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    meta_quantidade_vendas = models.PositiveIntegerField(null=True, blank=True)
    meta_quantidade_produtos = models.PositiveIntegerField(null=True, blank=True)
    meta_novos_clientes = models.PositiveIntegerField(null=True, blank=True)
    meta_ticket_medio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    peso_faturamento = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                            validators=[MinValueValidator(0), MaxValueValidator(100)])
    peso_quantidade = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                           validators=[MinValueValidator(0), MaxValueValidator(100)])
    peso_clientes = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                         validators=[MinValueValidator(0), MaxValueValidator(100)])

    status = models.CharField(max_length=20, choices=STATUS_META_CHOICES, default='ativa')

    comissao_extra_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    bonus_monetario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    premio_descricao = models.TextField(blank=True)

    permite_superacao = models.BooleanField(default=True)
    bonus_superacao_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    meta_minima_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=80)

    observacoes = models.TextField(blank=True)
    criterios_avaliacao = models.TextField(blank=True)

    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='metas_criadas')
    aprovado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='metas_aprovadas')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Meta de Venda'
        verbose_name_plural = 'Metas de Vendas'
        ordering = ['-ano', '-mes', 'vendedor']
        unique_together = [
            ['vendedor', 'tipo_periodo', 'mes', 'ano'],
            ['vendedor', 'tipo_periodo', 'trimestre', 'ano'],
            ['vendedor', 'tipo_periodo', 'semestre', 'ano'],
        ]
        indexes = [
            models.Index(fields=['vendedor', 'status']),
            models.Index(fields=['ano', 'mes']),
            models.Index(fields=['data_inicio', 'data_fim']),
            models.Index(fields=['codigo_meta']),
        ]

    def __str__(self):
        vendedor_str = f" - {self.vendedor}" if self.vendedor else " - Geral"
        return f"Meta {self.get_periodo_display()} {self.ano}{vendedor_str}"

    def save(self, *args, **kwargs):
        if not self.codigo_meta:
            prefixo = 'MT'
            prefixo += f"V{self.vendedor.id:03d}" if self.vendedor else "GER"
            self.codigo_meta = f"{prefixo}{self.ano}{(self.mes or 0):02d}"
        self.validar_periodo()
        super().save(*args, **kwargs)

    def validar_periodo(self):
        if self.tipo_periodo == 'mensal' and not self.mes:
            raise ValidationError('Mês é obrigatório para meta mensal')
        elif self.tipo_periodo == 'trimestral' and not self.trimestre:
            raise ValidationError('Trimestre é obrigatório para meta trimestral')
        elif self.tipo_periodo == 'semestral' and not self.semestre:
            raise ValidationError('Semestre é obrigatório para meta semestral')

    def get_periodo_display(self):
        if self.tipo_periodo == 'mensal':
            meses = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
            return f"{meses[self.mes]}/{self.ano}"
        elif self.tipo_periodo == 'trimestral':
            return f"{self.trimestre}º Tri/{self.ano}"
        elif self.tipo_periodo == 'semestral':
            return f"{self.semestre}º Sem/{self.ano}"
        return str(self.ano)

    def calcular_realizado(self):
        vendas = Venda.objects.filter(
            data_venda__gte=self.data_inicio,
            data_venda__lte=self.data_fim,
            status='finalizada'
        )
        if self.vendedor:
            vendas = vendas.filter(vendedor=self.vendedor)

        resultado = vendas.aggregate(
            faturamento_realizado=models.Sum('total'),
            quantidade_vendas_realizada=models.Count('id'),
            quantidade_produtos_realizada=models.Sum('itens__quantidade'),
            ticket_medio_realizado=models.Avg('total')
        )

        novos_clientes = 0
        for cliente_data in vendas.filter(cliente__isnull=False).values('cliente').distinct():
            primeira_compra = Venda.objects.filter(
                cliente_id=cliente_data['cliente'], status='finalizada'
            ).order_by('data_venda').first()
            if primeira_compra and self.data_inicio <= primeira_compra.data_venda.date() <= self.data_fim:
                novos_clientes += 1
        resultado['novos_clientes_realizados'] = novos_clientes

        for key, value in resultado.items():
            if value is None:
                resultado[key] = 0
        return resultado

    def calcular_percentual_atingimento(self):
        realizado = self.calcular_realizado()
        percentuais = {}
        if self.meta_faturamento:
            percentuais['faturamento'] = realizado['faturamento_realizado'] / float(self.meta_faturamento) * 100
        if self.meta_quantidade_vendas:
            percentuais['quantidade_vendas'] = realizado['quantidade_vendas_realizada'] / self.meta_quantidade_vendas * 100
        if self.meta_quantidade_produtos:
            percentuais['quantidade_produtos'] = realizado['quantidade_produtos_realizada'] / self.meta_quantidade_produtos * 100
        if self.meta_novos_clientes:
            percentuais['novos_clientes'] = realizado['novos_clientes_realizados'] / self.meta_novos_clientes * 100
        if self.meta_ticket_medio:
            percentuais['ticket_medio'] = realizado['ticket_medio_realizado'] / float(self.meta_ticket_medio) * 100
        return percentuais

    def calcular_percentual_geral(self):
        percentuais = self.calcular_percentual_atingimento()
        if self.tipo_meta == 'mista':
            total_peso = float(self.peso_faturamento + self.peso_quantidade + self.peso_clientes)
            if total_peso == 0:
                return 0
            percentual_geral = 0
            if self.peso_faturamento > 0 and 'faturamento' in percentuais:
                percentual_geral += percentuais['faturamento'] * float(self.peso_faturamento) / 100
            if self.peso_quantidade > 0 and 'quantidade_vendas' in percentuais:
                percentual_geral += percentuais['quantidade_vendas'] * float(self.peso_quantidade) / 100
            if self.peso_clientes > 0 and 'novos_clientes' in percentuais:
                percentual_geral += percentuais['novos_clientes'] * float(self.peso_clientes) / 100
            return percentual_geral * 100 / total_peso

        tipo_map = {
            'faturamento': 'faturamento',
            'quantidade': 'quantidade_vendas',
            'produtos': 'quantidade_produtos',
            'clientes': 'novos_clientes',
            'tickets': 'ticket_medio',
        }
        return percentuais.get(tipo_map.get(self.tipo_meta), 0)

    def meta_atingida(self):
        return self.calcular_percentual_geral() >= float(self.meta_minima_percentual)

    def calcular_bonus(self):
        if not self.meta_atingida():
            return 0
        percentual = self.calcular_percentual_geral()
        bonus_total = float(self.bonus_monetario)
        if percentual > 100 and self.permite_superacao:
            bonus_total += (percentual - 100) * float(self.bonus_superacao_percentual) / 100
        return bonus_total

    def calcular_comissao_extra(self):
        if not self.meta_atingida():
            return 0
        faturamento = self.calcular_realizado()['faturamento_realizado']
        return faturamento * float(self.comissao_extra_percentual) / 100

    def gerar_relatorio_atingimento(self):
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
        hoje = timezone.now().date()
        return self.status == 'ativa' and self.data_inicio <= hoje <= self.data_fim

    @property
    def periodo_vencido(self):
        return timezone.now().date() > self.data_fim


@receiver(post_save, sender=MetaVenda)
def verificar_meta_vencida(sender, instance, **kwargs):
    if instance.periodo_vencido and instance.status == 'ativa':
        instance.status = 'finalizada'
        instance.save(update_fields=['status'])


# =====================================
# FATURA DE CRÉDITO (FT)
# =====================================

class FaturaCredito(TimeStampedModel):
    TIPO_FATURA_CHOICES = [
        ('credito', 'Crédito'),
        ('prazo', 'A Prazo'),
        ('parcelada', 'Parcelada'),
        ('outros', 'Outros'),
    ]

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='faturas_credito')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='faturas_credito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Fatura")
    tipo_fatura = models.CharField(max_length=20, choices=TIPO_FATURA_CHOICES, default='credito')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fatura_credito',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_fatura = models.DateTimeField(auto_now_add=True)
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")

    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('parcial', 'Pago Parcialmente'),
        ('liquidada', 'Liquidada'),
        ('cancelada', 'Cancelada'),
        ('vencida', 'Vencida'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')
    # documentCancelReason (Decreto 683/25): obrigatório quando documentStatus = A
    motivo_cancelamento_codigo = models.CharField(
        max_length=1,
        choices=[('I', 'I — Identificação incorrecta do adquirente'),
                 ('N', 'N — Não enviado ao adquirente')],
        blank=True,
        verbose_name="Código de Motivo de Anulação (documentCancelReason)",
    )

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
            empresa=connection.tenant,
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

        # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
        self.documento_fiscal = documento
        self.numero_documento = documento.numero_documento
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])

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
        return self.total - sum((item.produto.preco_custo * item.quantidade
                                  for item in self.itens.all() if item.produto), Decimal('0.00'))

    def quantidade_itens(self):
        return self.itens.count()

    def valor_pendente(self):
        return self.total - self.valor_pago


class Recibo(TimeStampedModel):
    TIPO_RECIBO_CHOICES = [
        ('pagamento_fatura', 'Pagamento de Fatura'),
        ('prestacao_servico', 'Prestação de Serviço'),
        ('venda_avulsa', 'Venda Avulsa'),
        ('outros', 'Outros'),
    ]

    fatura = models.ForeignKey('FaturaCredito', on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='recibos')
    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='recibos')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='recibos')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_recibo = models.CharField(max_length=200, unique=True, verbose_name="Nº Recibo")
    tipo_recibo = models.CharField(max_length=20, choices=TIPO_RECIBO_CHOICES, default='venda_avulsa')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='recibo',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_recibo = models.DateTimeField(auto_now_add=True)

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
            empresa=connection.tenant,
            tipo_documento='REC',
            cliente=self.cliente,
            usuario=self.vendedor.usuario,
            linhas=[{
                'produto': item.produto,
                'quantidade': item.quantidade,
                'preco_unitario': item.preco_unitario,
                'desconto': item.desconto_item,
                'iva_valor': item.iva_valor,
            } for item in getattr(self, 'itens', [])],
            dados_extra={'data_emissao': self.data_recibo, 'valor_total': self.total},
        )

        # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
        self.documento_fiscal = documento
        self.numero_recibo = documento.numero_documento
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['documento_fiscal', 'numero_recibo', 'hash_documento', 'atcud'])

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
        return self.total - sum((item.produto.preco_custo * item.quantidade
                                  for item in self.itens.all() if item.produto), Decimal('0.00'))

    def quantidade_itens(self):
        return self.itens.count()


# =====================================
# FACTURA GENÉRICA (GF) — Proxy de FaturaCredito
# =====================================

class FaturaGenerica(FaturaCredito):
    """
    Proxy de FaturaCredito com tipo_documento fixo = 'GF'.
    Ponto 12 da Notificação AGT: factura genérica (resumo de múltiplas
    operações sem identificação específica do adquirente).
    No SAF-T vai para SalesInvoices/Invoice com InvoiceType='GF'.
    """

    class Meta:
        proxy = True
        verbose_name = 'Factura Genérica (GF)'
        verbose_name_plural = 'Facturas Genéricas (GF)'

    def save(self, *args, **kwargs):
        # Forçar tipo de documento correcto antes de persistir
        if self.pk is None:
            # Será propagado para DocumentoFiscal via gerar_documento_fiscal()
            pass
        super().save(*args, **kwargs)

    def gerar_documento_fiscal(self, usuario):
        """Usa tipo_documento='GF' em vez de 'FT'."""
        if not usuario:
            raise ValueError("Usuário obrigatório para gerar Documento Fiscal")
        if not self.itens.exists():
            raise ValueError("Não é possível gerar documento sem itens")
        if self.total <= 0:
            raise ValueError("Total da factura inválido")

        from django.db import connection
        from apps.fiscal.services import DocumentoFiscalService
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=connection.tenant,
            tipo_documento='GF',   # ← diferença crítica
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
        self.documento_fiscal = documento
        self.numero_documento = documento.numero_documento
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])


# =====================================
# FACTURA DE AUTOFACTURAÇÃO (AF) — Proxy de FaturaCredito
# =====================================

class FaturaAutofacturacao(FaturaCredito):
    """
    Proxy de FaturaCredito com tipo_documento fixo = 'AF'.
    Ponto 12 da Notificação AGT: factura emitida pelo comprador em nome
    do fornecedor (autofacturação).
    No SAF-T vai para SalesInvoices/Invoice com InvoiceType='AF' e
    SpecialRegimes.SelfBillingIndicator=1.
    """

    class Meta:
        proxy = True
        verbose_name = 'Factura de Autofacturação (AF)'
        verbose_name_plural = 'Facturas de Autofacturação (AF)'

    def gerar_documento_fiscal(self, usuario):
        """Usa tipo_documento='AF' em vez de 'FT'."""
        if not usuario:
            raise ValueError("Usuário obrigatório para gerar Documento Fiscal")
        if not self.itens.exists():
            raise ValueError("Não é possível gerar documento sem itens")
        if self.total <= 0:
            raise ValueError("Total da factura inválido")

        from django.db import connection
        from apps.fiscal.services import DocumentoFiscalService
        service = DocumentoFiscalService()
        documento = service.criar_documento(
            empresa=connection.tenant,
            tipo_documento='AF',   # ← diferença crítica
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
        self.documento_fiscal = documento
        self.numero_documento = documento.numero_documento
        self.hash_documento = documento.hash_documento
        self.atcud = documento.atcud
        self.save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])


class ItemFatura(models.Model):
    """Item (produto ou serviço) de uma Fatura de Crédito (FT)."""
    fatura = models.ForeignKey('vendas.FaturaCredito', on_delete=models.CASCADE, related_name='itens',
                                verbose_name="Fatura de Crédito")

    produto = models.ForeignKey('produtos.Produto', on_delete=models.SET_NULL, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.SET_NULL, null=True, blank=True)

    nome_item = models.CharField(max_length=255, verbose_name="Nome/Descrição")
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey('fiscal.TaxaIVAAGT', on_delete=models.PROTECT, null=True, blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Subtotal Bruto")
    total = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total do Item (c/ IVA)")

    # operationType — obrigatório por linha (Decreto 683/25, Anexo I)
    operation_type = models.CharField(
        max_length=3,
        choices=[
            ('SE',  'SE — Serviços em território nacional'),
            ('SS',  'SS — Serviços no estrangeiro'),
            ('STP', 'STP — Telecomunicações/via electrónica'),
            ('SR',  'SR — Serviços relacionados com imóveis'),
            ('SIF', 'SIF — Intermediação financeira'),
            ('SHS', 'SHS — Hotelaria e similares'),
            ('ST',  'ST — Transporte'),
            ('SG',  'SG — Serviços em geral'),
            ('TB',  'TB — Transmissão de bens'),
            ('AS',  'AS — Aquisição de serviços'),
            ('QT',  'QT — Outras operações tributáveis'),
            ('RD',  'RD — Regularizações e devoluções'),
        ],
        default='TB',
        verbose_name="Tipo de Operação (operationType)",
    )

    def save(self, *args, **kwargs):
        if not self.nome_item:
            if self.produto:
                self.nome_item = self.produto.nome_produto
            elif self.servico:
                self.nome_item = self.servico.nome
            else:
                self.nome_item = "Item Genérico"

        self.subtotal = self.preco_unitario * self.quantidade
        valor_liquido = self.subtotal - self.desconto_item
        self.iva_valor = valor_liquido * (self.iva_percentual / Decimal('100.00'))
        self.total = valor_liquido + self.iva_valor
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nome_item} ({self.quantidade}x)"

    @property
    def settlement_amount_calculado(self):
        """SettlementAmount = desconto linha + proporção do desconto global do cabeçalho."""
        desconto_linha = self.desconto_item or Decimal('0.00')
        try:
            subtotal_doc = self.fatura.subtotal or Decimal('1.00')
            desconto_global = self.fatura.desconto_valor or Decimal('0.00')
            if subtotal_doc > 0 and desconto_global > 0:
                proporcao = Decimal(str(self.subtotal)) / Decimal(str(subtotal_doc))
                return round(desconto_linha + desconto_global * proporcao, 4)
        except Exception:
            pass
        return round(desconto_linha, 4)

    class Meta:
        verbose_name = 'Item da Fatura de Crédito'
        verbose_name_plural = 'Itens da Fatura de Crédito'


class FaturaProforma(TimeStampedModel):
    TIPO_PROFORMA_CHOICES = [
        ('orcamento', 'Orçamento'),
        ('proposta', 'Proposta'),
        ('cotacao', 'Cotação'),
        ('outros', 'Outros'),
    ]

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='faturas_proforma')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='faturas_proforma')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Proforma")
    tipo_proforma = models.CharField(max_length=20, choices=TIPO_PROFORMA_CHOICES, default='orcamento')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='fatura_proforma',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_proforma = models.DateTimeField(auto_now_add=True)
    data_validade = models.DateField(verbose_name="Data de Validade")

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

    venda_convertida = models.OneToOneField('Venda', on_delete=models.SET_NULL, null=True, blank=True,
                                             related_name='proforma_origem')

    def save(self, *args, criar_documento=True, usuario_criacao=None, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            usuario = self.vendedor.usuario if self.vendedor else usuario_criacao
            if usuario is None:
                raise ValueError("É necessário fornecer um usuário para criar o documento fiscal.")

            documento = service.criar_documento(
                empresa=connection.tenant,
                tipo_documento='FP',
                cliente=self.cliente,
                usuario=usuario,
                linhas=[],
                dados_extra={'data_emissao': self.data_proforma, 'valor_total': self.total},
            )

            # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
            self.documento_fiscal = documento
            self.numero_documento = documento.numero_documento
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])

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
        return self.total - sum((item.produto.preco_custo * item.quantidade
                                  for item in self.itens.all() if item.produto), Decimal('0.00'))

    def quantidade_itens(self):
        return self.itens.count()

    def get_itens_proforma(self):
        from django.db.models.functions import Coalesce

        return list(
            self.itens.select_related('produto', 'servico').annotate(
                nome_item=Coalesce('produto__nome_produto', 'servico__nome')
            ).values(
                'quantidade', 'preco_unitario', 'desconto_item',
                'iva_percentual', 'iva_valor', 'total', 'nome_item'
            )
        )


class ItemProforma(models.Model):
    """Itens associados a uma Fatura Proforma."""
    proforma = models.ForeignKey(FaturaProforma, on_delete=models.CASCADE, related_name='itens')

    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)

    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    taxa_iva = models.ForeignKey('fiscal.TaxaIVAAGT', on_delete=models.PROTECT, null=True, blank=True)

    def save(self, *args, **kwargs):
        subtotal_base = self.quantidade * self.preco_unitario
        self.subtotal = subtotal_base
        self.total = subtotal_base - self.desconto_item
        self.iva_valor = self.total * (self.iva_percentual / 100)
        self.total += self.iva_valor
        super().save(*args, **kwargs)


# =====================================
# NOTAS DE CRÉDITO / DÉBITO
# =====================================

class NotaCredito(TimeStampedModel):
    MOTIVO_CHOICES = [
        ('devolucao', 'Devolução'),
        ('desconto', 'Desconto'),
        ('correcao', 'Correção'),
        ('outros', 'Outros'),
    ]

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='notas_credito')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='notas_credito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_nota = models.CharField(max_length=200, unique=True, verbose_name="Nº Nota de Crédito")
    motivo = models.CharField(max_length=30, choices=MOTIVO_CHOICES, default='outros')
    # documentCancelReason (Decreto 683/25)
    motivo_cancelamento_codigo = models.CharField(
        max_length=1,
        choices=[('I', 'I — Identificação incorrecta do adquirente'),
                 ('N', 'N — Não enviado ao adquirente')],
        blank=True,
        verbose_name="Código de Motivo de Anulação (documentCancelReason)",
    )
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='nota_credito',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_nota = models.DateTimeField(auto_now_add=True)
    data_emissao = models.DateTimeField(auto_now_add=True)

    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('aplicada', 'Aplicada'),
        ('cancelada', 'Cancelada'),
        ('pendente', 'Pendente'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    requer_aprovacao = models.BooleanField(default=False, verbose_name="Requer Aprovação?")
    emitida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='notas_credito_emitidas')
    aplicada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='notas_credito_aplicadas')
    aprovada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='notas_credito_aprovadas')
    data_aplicacao = models.DateTimeField(null=True, blank=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True)

    venda_origem = models.ForeignKey('Venda', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='notas_credito_origem', verbose_name="Venda de Origem (FR)")
    fatura_credito_origem = models.ForeignKey('FaturaCredito', on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='notas_credito_origem',
                                               verbose_name="Fatura Crédito de Origem (FT)")

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=connection.tenant,
                tipo_documento='NC',
                cliente=self.cliente,
                usuario=self.vendedor.usuario if self.vendedor else self.emitida_por,
                linhas=[],
                dados_extra={'data_emissao': self.data_nota, 'valor_total': self.total},
            )

            # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
            self.documento_fiscal = documento
            self.numero_nota = documento.numero_documento
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['documento_fiscal', 'numero_nota', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"NC {self.numero_nota}"

    class Meta:
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'

    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')

    def quantidade_itens(self):
        return self.itens.count()

    def recalcular_total(self):
        agregados = self.itens.aggregate(total=models.Sum('total_item_credito'))
        self.total = agregados['total'] or Decimal('0.00')
        self.save(update_fields=['total'])

    def pode_ser_aplicada(self):
        if self.status == 'aplicada':
            return False, 'Esta nota de crédito já foi aplicada.'
        if self.status == 'cancelada':
            return False, 'Nota de crédito cancelada.'
        if self.requer_aprovacao and not self.aprovada_por:
            return False, 'Aguardando aprovação.'
        if not self.itens.exists():
            return False, 'Nota de crédito sem itens.'
        return True, ''

    def aplicar_credito(self, usuario):
        pode, motivo = self.pode_ser_aplicada()
        if not pode:
            raise ValidationError(motivo)
        self.status = 'aplicada'
        self.aplicada_por = usuario
        self.data_aplicacao = timezone.now()
        self.save(update_fields=['status', 'aplicada_por', 'data_aplicacao'])

    @property
    def documento_origem(self):
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"


class ItemNotaCredito(TimeStampedModel):
    nota_credito = models.ForeignKey(NotaCredito, on_delete=models.CASCADE, related_name='itens')

    item_venda_original = models.ForeignKey('ItemVenda', on_delete=models.PROTECT, null=True, blank=True)
    item_fatura_original = models.ForeignKey('ItemFatura', on_delete=models.PROTECT, null=True, blank=True)

    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)

    descricao_item = models.CharField(max_length=255, verbose_name="Descrição do Item")
    quantidade_creditada = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario_credito = models.DecimalField(max_digits=10, decimal_places=2)

    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey('fiscal.TaxaIVAAGT', on_delete=models.PROTECT, null=True, blank=True)

    total_item_credito = models.DecimalField(max_digits=10, decimal_places=2)
    motivo_item = models.TextField(blank=True)

    # operationType (Decreto 683/25 — obrigatório por linha)
    operation_type = models.CharField(
        max_length=3,
        choices=[
            ('SE',  'SE — Serviços em território nacional'),
            ('SS',  'SS — Serviços no estrangeiro'),
            ('STP', 'STP — Telecomunicações/via electrónica'),
            ('SR',  'SR — Serviços relacionados com imóveis'),
            ('SIF', 'SIF — Intermediação financeira'),
            ('SHS', 'SHS — Hotelaria e similares'),
            ('ST',  'ST — Transporte'),
            ('SG',  'SG — Serviços em geral'),
            ('TB',  'TB — Transmissão de bens'),
            ('AS',  'AS — Aquisição de serviços'),
            ('QT',  'QT — Outras operações tributáveis'),
            ('RD',  'RD — Regularizações e devoluções'),
        ],
        default='RD',
        verbose_name="Tipo de Operação (operationType)",
        help_text="Para NC use RD (Regularizações e devoluções)."
    )

    # referenceInfo por linha (Decreto 683/25, Anexo I — obrigatório em NC)
    # `referencia_documento_origem` aponta para o número do documento de origem (ex.: FT A/123)
    # `motivo_referencia` é o campo `reason` (opcional) — ex.: "Devolução parcial"
    referencia_documento_origem = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Referência do Documento de Origem",
        help_text="Número do documento (ex.: FT A/123) ao qual esta linha de NC diz respeito. "
                  "Obrigatório no payload registarFactura (referenceInfo.reference)."
    )
    motivo_referencia = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Motivo da Referência",
        help_text="Motivo opcional da intervenção no documento de origem (referenceInfo.reason)."
    )

    class Meta:
        verbose_name = 'Item da Nota de Crédito'
        verbose_name_plural = 'Itens da Nota de Crédito'

    def save(self, *args, **kwargs):
        subtotal = self.quantidade_creditada * self.valor_unitario_credito
        self.iva_valor = subtotal * (self.iva_percentual / Decimal('100.00'))
        self.total_item_credito = subtotal + self.iva_valor
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_item} - Qtd: {self.quantidade_creditada}"


class NotaDebito(TimeStampedModel):
    TIPO_NOTA_CHOICES = [
        ('cobranca', 'Cobrança Adicional'),
        ('juros', 'Juros'),
        ('multa', 'Multa'),
        ('correcao', 'Correção'),
        ('outros', 'Outros'),
    ]

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='notas_debito')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='notas_debito')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_nota = models.CharField(max_length=200, unique=True, verbose_name="Nº Nota de Débito")
    motivo = models.CharField(max_length=30, choices=TIPO_NOTA_CHOICES, default='outros')
    # documentCancelReason (Decreto 683/25)
    motivo_cancelamento_codigo = models.CharField(
        max_length=1,
        choices=[('I', 'I — Identificação incorrecta do adquirente'),
                 ('N', 'N — Não enviado ao adquirente')],
        blank=True,
        verbose_name="Código de Motivo de Anulação (documentCancelReason)",
    )
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='nota_debito',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_nota = models.DateTimeField(auto_now_add=True)
    data_emissao = models.DateTimeField(auto_now_add=True)
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")

    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('aplicada', 'Aplicada'),
        ('paga', 'Paga'),
        ('cancelada', 'Cancelada'),
        ('vencida', 'Vencida'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')

    requer_aprovacao = models.BooleanField(default=False, verbose_name="Requer Aprovação?")
    emitida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='notas_debito_emitidas')
    aplicada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='notas_debito_aplicadas')
    aprovada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='notas_debito_aprovadas')
    data_aprovacao = models.DateTimeField(null=True, blank=True)
    data_aplicacao = models.DateTimeField(null=True, blank=True)

    venda_origem = models.ForeignKey(Venda, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='notas_debito_origem', verbose_name="Venda de Origem (FR)")
    fatura_credito_origem = models.ForeignKey(FaturaCredito, on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='notas_debito_origem',
                                               verbose_name="Fatura Crédito de Origem (FT)")

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status == 'emitida':
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=connection.tenant,
                tipo_documento='ND',
                cliente=self.cliente,
                usuario=self.vendedor.usuario if self.vendedor else self.emitida_por,
                linhas=[],
                dados_extra={'data_emissao': self.data_nota, 'valor_total': self.total},
            )

            # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
            self.documento_fiscal = documento
            self.numero_nota = documento.numero_documento
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['documento_fiscal', 'numero_nota', 'hash_documento', 'atcud'])

    def __str__(self):
        return f"ND {self.numero_nota}"

    class Meta:
        verbose_name = 'Nota de Débito'
        verbose_name_plural = 'Notas de Débito'

    def desconto_percentual(self):
        if self.subtotal > Decimal('0.00'):
            return (self.desconto_valor / self.subtotal) * Decimal('100.00')
        return Decimal('0.00')

    def quantidade_itens(self):
        return self.itens.count()

    def recalcular_total(self):
        agregados = self.itens.aggregate(total=models.Sum('total_item'))
        self.total = agregados['total'] or Decimal('0.00')
        self.save(update_fields=['total'])

    def pode_ser_aplicada(self):
        if self.status == 'aplicada':
            return False, 'Esta nota de débito já foi aplicada.'
        if self.status == 'cancelada':
            return False, 'Nota de débito cancelada.'
        if self.requer_aprovacao and not self.aprovada_por:
            return False, 'Aguardando aprovação.'
        if not self.itens.exists():
            return False, 'Nota de débito sem itens.'
        return True, ''

    def aplicar_debito(self, usuario):
        pode, motivo = self.pode_ser_aplicada()
        if not pode:
            raise ValidationError(motivo)
        self.status = 'aplicada'
        self.aplicada_por = usuario
        self.data_aplicacao = timezone.now()
        self.save(update_fields=['status', 'aplicada_por', 'data_aplicacao'])

    @property
    def documento_origem(self):
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"

    @property
    def valor_pendente(self):
        return self.total - self.valor_pago

    @property
    def esta_paga(self):
        return self.valor_pendente <= Decimal('0.00')


class ItemNotaDebito(TimeStampedModel):
    nota_debito = models.ForeignKey(NotaDebito, on_delete=models.CASCADE, related_name='itens')

    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)
    servico = models.ForeignKey('servicos.Servico', on_delete=models.PROTECT, null=True, blank=True)

    descricao_item = models.CharField(max_length=255, verbose_name="Descrição do Item")
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    iva_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    taxa_iva = models.ForeignKey('fiscal.TaxaIVAAGT', on_delete=models.PROTECT, null=True, blank=True)

    total_item = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Total do Item")
    justificativa = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Item da Nota de Débito'
        verbose_name_plural = 'Itens da Nota de Débito'

    def save(self, *args, **kwargs):
        subtotal = self.quantidade * self.valor_unitario
        self.iva_valor = subtotal * (self.iva_percentual / Decimal('100.00'))
        self.total_item = subtotal + self.iva_valor
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_item} - Qtd: {self.quantidade}"


# =====================================
# DOCUMENTO DE TRANSPORTE (GT)
# =====================================

class DocumentoTransporte(TimeStampedModel):
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

    cliente = models.ForeignKey('clientes.Cliente', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='documentos_transporte')
    vendedor = models.ForeignKey('funcionarios.Funcionario', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='documentos_transporte')
    forma_pagamento = models.ForeignKey('vendas.FormaPagamento', on_delete=models.PROTECT, null=True, blank=True)

    iva_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    numero_documento = models.CharField(max_length=200, unique=True, verbose_name="Nº Documento de Transporte")
    tipo_operacao = models.CharField(max_length=20, choices=TIPO_OPERACAO_CHOICES, default='venda')
    tipo_transporte = models.CharField(max_length=20, choices=TIPO_TRANSPORTE_CHOICES, default='proprio')
    observacoes = models.TextField(blank=True, null=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    desconto_valor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    hash_documento = models.CharField(max_length=256, unique=True, null=True, blank=True,
                                      help_text="Cache do hash gerado em DocumentoFiscal.")
    atcud = models.CharField(max_length=100, null=True, blank=True,
                              help_text="Cache do ATCUD gerado em DocumentoFiscal.")
    # Fase 2 — Unificação da cadeia de hash/ATCUD (PLANO_IMPLEMENTACAO.md)
    documento_fiscal = models.OneToOneField(
        'fiscal.DocumentoFiscal',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='documento_transporte',
        verbose_name="Documento Fiscal (AGT)"
    )

    data_documento = models.DateTimeField(auto_now_add=True)
    data_emissao = models.DateTimeField(auto_now_add=True)
    data_inicio_transporte = models.DateTimeField(verbose_name="Data/Hora de Início do Transporte",
                                                   null=True, blank=True)
    data_previsao_entrega = models.DateTimeField(verbose_name="Previsão de Entrega")
    data_entrega_real = models.DateTimeField(null=True, blank=True)

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

    venda_origem = models.ForeignKey('Venda', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='documentos_transporte', verbose_name="Venda de Origem")
    fatura_credito_origem = models.ForeignKey('FaturaCredito', on_delete=models.PROTECT, null=True, blank=True,
                                               related_name='documentos_transporte',
                                               verbose_name="Fatura Crédito de Origem")

    # Remetente (dados da empresa/tenant, preenchidos a partir de connection.tenant)
    remetente_nome = models.CharField(max_length=200, verbose_name="Nome do Remetente", blank=True)
    remetente_nif = models.CharField(max_length=20, verbose_name="NIF do Remetente", blank=True)
    remetente_endereco = models.CharField(max_length=300, verbose_name="Endereço do Remetente", blank=True)
    remetente_telefone = models.CharField(max_length=20, verbose_name="Telefone do Remetente", blank=True)
    remetente_provincia = models.CharField(max_length=50, verbose_name="Província do Remetente", blank=True)

    destinatario_cliente = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT, null=True, blank=True,
                                              related_name='documentos_transporte_destinatario')
    destinatario_nome = models.CharField(max_length=200, verbose_name="Nome do Destinatário")
    destinatario_nif = models.CharField(max_length=20, blank=True, verbose_name="NIF/BI do Destinatário")
    destinatario_endereco = models.CharField(max_length=300, verbose_name="Endereço de Entrega")
    destinatario_telefone = models.CharField(max_length=20, blank=True, verbose_name="Telefone do Destinatário")
    destinatario_provincia = models.CharField(max_length=50, blank=True, verbose_name="Província do Destinatário")

    transportador_nome = models.CharField(max_length=200, blank=True, verbose_name="Nome do Transportador")
    transportador_nif = models.CharField(max_length=20, blank=True, verbose_name="NIF do Transportador")
    transportador_telefone = models.CharField(max_length=20, blank=True, verbose_name="Telefone do Transportador")

    veiculo_matricula = models.CharField(max_length=20, verbose_name="Matrícula do Veículo")
    veiculo_modelo = models.CharField(max_length=100, blank=True, verbose_name="Modelo do Veículo")
    condutor_nome = models.CharField(max_length=200, blank=True, verbose_name="Nome do Condutor")
    condutor_carta = models.CharField(max_length=20, blank=True, verbose_name="Número da Carta de Condução")

    local_carregamento = models.CharField(max_length=300, blank=True, verbose_name="Local de Carregamento")
    local_descarga = models.CharField(max_length=300, blank=True, verbose_name="Local de Descarga")
    itinerario = models.TextField(blank=True, verbose_name="Itinerário Detalhado")

    valor_transporte = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    peso_total = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    volume_total = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    quantidade_volumes = models.PositiveIntegerField(default=1)

    instrucoes_especiais = models.TextField(blank=True)

    assinatura_remetente = models.CharField(max_length=200, blank=True)
    assinatura_transportador = models.CharField(max_length=200, blank=True)
    assinatura_destinatario = models.CharField(max_length=200, blank=True)

    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     related_name='documentos_transporte_emitidos')
    confirmado_entrega_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                                null=True, blank=True,
                                                related_name='documentos_transporte_confirmados')

    def save(self, *args, criar_documento=True, **kwargs):
        is_new = self._state.adding

        if not self.remetente_nome:
            tenant = connection.tenant
            config_fiscal = getattr(tenant, 'config_fiscal', None)
            if config_fiscal:
                self.remetente_nome = getattr(config_fiscal, 'razao_social', '') or tenant.nome
                self.remetente_nif = config_fiscal.nif
                self.remetente_endereco = config_fiscal.endereco
                self.remetente_telefone = config_fiscal.telefone
            else:
                self.remetente_nome = tenant.nome
                self.remetente_nif = tenant.nif
                self.remetente_endereco = tenant.endereco
                self.remetente_telefone = tenant.telefone

        if self.destinatario_cliente and not self.destinatario_nome:
            cliente = self.destinatario_cliente
            self.destinatario_nome = cliente.nome_completo
            self.destinatario_nif = cliente.nif or getattr(cliente, 'bi', '') or ''
            self.destinatario_telefone = cliente.telefone

            endereco_principal = cliente.enderecos.filter(endereco_principal=True).first()
            if endereco_principal:
                self.destinatario_endereco = endereco_principal.endereco_completo
                self.destinatario_provincia = endereco_principal.provincia

        super().save(*args, **kwargs)

        if criar_documento and is_new and self.status in ['preparando', 'em_transito']:
            from apps.fiscal.services import DocumentoFiscalService

            service = DocumentoFiscalService()
            documento = service.criar_documento(
                empresa=connection.tenant,
                tipo_documento='GT',
                cliente=self.cliente or self.destinatario_cliente,
                usuario=self.vendedor.usuario if self.vendedor else self.emitido_por,
                linhas=[],
                dados_extra={'data_emissao': self.data_documento, 'valor_total': self.total},
            )

            # Fase 2: guardar a FK para DocumentoFiscal (fonte de verdade)
            self.documento_fiscal = documento
            self.numero_documento = documento.numero_documento
            self.hash_documento = documento.hash_documento
            self.atcud = documento.atcud
            super().save(update_fields=['documento_fiscal', 'numero_documento', 'hash_documento', 'atcud'])

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

    def quantidade_itens(self):
        return self.itens.count()

    @property
    def documento_origem(self):
        return self.venda_origem or self.fatura_credito_origem

    @property
    def numero_documento_origem(self):
        if self.venda_origem:
            return self.venda_origem.numero_documento
        elif self.fatura_credito_origem:
            return self.fatura_credito_origem.numero_documento
        return "N/A"

    @property
    def tempo_transporte(self):
        if self.data_entrega_real and self.data_inicio_transporte:
            return self.data_entrega_real - self.data_inicio_transporte
        return None

    @property
    def esta_atrasado(self):
        if self.status in ['entregue', 'cancelado']:
            return False
        return timezone.now() > self.data_previsao_entrega

    def confirmar_entrega(self, usuario, assinatura_destinatario=None):
        if self.status != 'em_transito':
            raise ValidationError("Só é possível confirmar entregas em trânsito")
        self.status = 'entregue'
        self.data_entrega_real = timezone.now()
        self.confirmado_entrega_por = usuario
        if assinatura_destinatario:
            self.assinatura_destinatario = assinatura_destinatario
        self.save()

    def iniciar_transporte(self):
        if self.status != 'preparando':
            raise ValidationError("Transporte já foi iniciado")
        self.status = 'em_transito'
        self.data_inicio_transporte = timezone.now()
        self.save()


class ItemDocumentoTransporte(TimeStampedModel):
    documento = models.ForeignKey(DocumentoTransporte, on_delete=models.CASCADE, related_name='itens')

    item_venda_original = models.ForeignKey(ItemVenda, on_delete=models.PROTECT, null=True, blank=True)
    item_fatura_original = models.ForeignKey(ItemFatura, on_delete=models.PROTECT, null=True, blank=True)

    produto = models.ForeignKey('produtos.Produto', on_delete=models.PROTECT, null=True, blank=True)

    codigo_produto = models.CharField(max_length=50, blank=True, verbose_name="Código do Produto")
    descricao_produto = models.CharField(max_length=255, blank=True, verbose_name="Descrição do Produto")
    unidade_medida = models.CharField(max_length=10, default='UN')

    quantidade_enviada = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade_recebida = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    peso_unitario = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    peso_total = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))

    tipo_embalagem = models.CharField(max_length=50, blank=True)
    numero_serie = models.CharField(max_length=100, blank=True)
    lote = models.CharField(max_length=50, blank=True)

    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    observacoes_item = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Item do Documento de Transporte'
        verbose_name_plural = 'Itens do Documento de Transporte'

    def save(self, *args, **kwargs):
        if self.produto and not self.descricao_produto:
            self.codigo_produto = getattr(self.produto, 'codigo', '') or ''
            self.descricao_produto = self.produto.nome_produto
            self.unidade_medida = getattr(self.produto, 'unidade_medida', 'UN')
            self.peso_unitario = getattr(self.produto, 'peso', Decimal('0.000'))
            self.valor_unitario = self.produto.preco_venda

        self.peso_total = self.quantidade_enviada * self.peso_unitario
        self.valor_total = self.quantidade_enviada * self.valor_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao_produto} - Qtd: {self.quantidade_enviada}"

    @property
    def divergencia_quantidade(self):
        return self.quantidade_enviada - self.quantidade_recebida

    @property
    def tem_divergencia(self):
        return self.divergencia_quantidade != Decimal('0.00')