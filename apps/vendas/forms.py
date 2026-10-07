# apps/vendas/forms.py
"""
Forms do módulo de Vendas.

Isolamento físico via django-tenants: os querysets já não filtram por
empresa (o campo nem existe mais nos modelos de vendas). O parâmetro
`empresa` continua a ser aceite nos __init__ apenas por compatibilidade
com views antigas que ainda o passem via get_form_kwargs — mas nunca é
usado para filtrar, e a filtragem por estado (ativo/status) acontece
sempre, independentemente de o kwarg ter sido passado ou não.
"""

from datetime import date, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.funcionarios.models import Funcionario
from apps.produtos.models import Produto

from .models import (
    Comissao, Convenio, DevolucaoVenda, DocumentoTransporte, Entrega,
    FaturaCredito, FormaPagamento, ItemDevolucao, ItemDocumentoTransporte,
    ItemNotaCredito, ItemNotaDebito, ItemVenda, MetaVenda, NotaCredito,
    NotaDebito, PagamentoVenda, Venda,
)


# =====================================
# FORM BASE
# =====================================

class BaseVendaForm(forms.ModelForm):
    """
    Form base para vendas com estilização automática.

    O kwarg `empresa` é aceite apenas por compatibilidade com views que
    ainda o passem — não é usado para filtrar querysets (isolamento já
    é feito pelo schema do tenant).
    """

    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput,
                                          forms.URLInput, forms.PasswordInput, forms.Textarea)):
                field.widget.attrs.update({
                    'class': 'form-control border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent'
                })
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    'class': 'form-select border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary focus:border-transparent'
                })
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    'class': 'form-check-input rounded border-gray-300 text-primary focus:ring-primary'
                })


# =====================================
# VENDA FORMS
# =====================================

class VendaForm(BaseVendaForm):
    """Form principal para criação e edição de vendas."""

    class Meta:
        model = Venda
        fields = ['cliente', 'vendedor', 'forma_pagamento', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True)
        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True)
        self.fields['forma_pagamento'].queryset = FormaPagamento.objects.filter(ativa=True)

        self.fields['cliente'].required = False
        self.fields['observacoes'].required = False

        self.fields['cliente'].label = 'Cliente (Opcional - deixe vazio para consumidor final)'
        self.fields['forma_pagamento'].label = 'Forma de Pagamento'


class ItemVendaForm(forms.ModelForm):
    """Form para itens da venda."""

    class Meta:
        model = ItemVenda
        fields = ['produto', 'quantidade', 'preco_unitario']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'min': '1', 'step': '1'}),
            'preco_unitario': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['produto'].queryset = Produto.objects.filter(ativo=True).order_by('nome_comercial')

        if self.instance.pk and self.instance.produto:
            self.fields['preco_unitario'].initial = self.instance.produto.preco_venda

        self.fields['preco_unitario'].label = 'Preço Unitário (AKZ)'

    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        quantidade = cleaned_data.get('quantidade')

        if produto and quantidade and produto.estoque_atual < quantidade:
            raise ValidationError(f'Estoque insuficiente. Disponível: {produto.estoque_atual}')

        return cleaned_data


# =====================================
# PAGAMENTO FORMS
# =====================================

class PagamentoVendaForm(BaseVendaForm):
    """Form para pagamentos."""

    class Meta:
        model = PagamentoVenda
        fields = ['forma_pagamento', 'valor_pago', 'observacoes']
        widgets = {
            'valor_pago': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['forma_pagamento'].queryset = FormaPagamento.objects.filter(ativa=True)
        self.fields['observacoes'].required = False
        self.fields['valor_pago'].label = 'Valor Pago (AKZ)'


class FormaPagamentoForm(BaseVendaForm):
    """Form para formas de pagamento."""

    class Meta:
        model = FormaPagamento
        fields = ['nome', 'tipo', 'ativa']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ativa'].initial = True


# =====================================
# CONVÊNIO FORM
# =====================================

class ConvenioForm(forms.ModelForm):
    """Formulário para gestão de convênios e seguradoras."""

    class Meta:
        model = Convenio
        fields = ['nome', 'codigo', 'contato', 'telefone', 'percentual_desconto', 'ativa', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Notas adicionais sobre o convênio...'}),
            'percentual_desconto': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'telefone': forms.TextInput(attrs={'placeholder': 'Ex: 923000000'}),
        }
        help_texts = {
            'percentual_desconto': 'Este valor será aplicado automaticamente em vendas vinculadas a este convênio.',
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-checkbox h-5 w-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            else:
                field.widget.attrs['class'] = 'form-input block w-full px-4 py-3 rounded-lg border-gray-300 focus:ring-primary-500 focus:border-primary-500'

    def clean_nome(self):
        """Validação de unicidade (o modelo já tem nome único por schema)."""
        nome = self.cleaned_data.get('nome')
        exists = Convenio.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk).exists()
        if exists:
            raise forms.ValidationError("Já existe um convênio cadastrado com este nome.")
        return nome


# =====================================
# DEVOLUÇÃO E TROCA FORMS
# =====================================

class DevolucaoForm(BaseVendaForm):
    """Form para devoluções/trocas."""

    class Meta:
        model = DevolucaoVenda
        fields = ['venda_original', 'cliente', 'motivo', 'descricao_motivo', 'valor_devolvido', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'descricao_motivo': forms.Textarea(attrs={'rows': 2}),
            'valor_devolvido': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['venda_original'].queryset = Venda.objects.filter(status='finalizada').order_by('-data_venda')
        self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True)

        self.fields['motivo'].required = True
        self.fields['observacoes'].required = False
        self.fields['venda_original'].label = 'Venda Original'


class ItemDevolucaoForm(forms.ModelForm):
    """Form para itens devolvidos — vinculado ao ItemVenda original."""

    class Meta:
        model = ItemDevolucao
        fields = ['item_venda_original', 'quantidade_devolvida', 'valor_restituido', 'motivo']
        widgets = {
            'quantidade_devolvida': forms.NumberInput(attrs={'min': '0.001', 'step': '0.001'}),
            'valor_restituido': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'motivo': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.venda = kwargs.pop('venda', None)
        super().__init__(*args, **kwargs)

        if self.venda:
            self.fields['item_venda_original'].queryset = self.venda.itens.all()


# =====================================
# DELIVERY E ENTREGA FORMS
# =====================================

class AgendarEntregaForm(BaseVendaForm):
    """Form para agendar entregas (dentro da própria Venda)."""

    class Meta:
        model = Venda
        fields = ['observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['observacoes'].required = False
        self.fields['observacoes'].label = 'Observações da Entrega'


class EntregaForm(BaseVendaForm):
    """Form para o modelo Entrega (entidade separada, ligada 1-para-1 com Venda)."""

    class Meta:
        model = Entrega
        fields = ['venda', 'entregador', 'endereco', 'taxa_entrega', 'data_agendada', 'observacoes']
        widgets = {
            'endereco': forms.Textarea(attrs={'rows': 3}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
            'data_agendada': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'taxa_entrega': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['venda'].queryset = Venda.objects.all()
        self.fields['entregador'].queryset = Funcionario.objects.filter(ativo=True)
        self.fields['observacoes'].required = False


# =====================================
# META E COMISSÃO FORMS
# =====================================

class MetaVendaForm(BaseVendaForm):
    """Form para metas de venda."""

    class Meta:
        model = MetaVenda
        fields = ['vendedor', 'tipo_periodo', 'mes', 'ano', 'meta_faturamento', 'observacoes']
        widgets = {
            'mes': forms.Select(choices=[
                (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'),
                (4, 'Abril'), (5, 'Maio'), (6, 'Junho'),
                (7, 'Julho'), (8, 'Agosto'), (9, 'Setembro'),
                (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
            ]),
            'ano': forms.NumberInput(attrs={'min': '2020', 'max': '2050'}),
            'meta_faturamento': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True)

        hoje = date.today()
        self.fields['mes'].initial = hoje.month
        self.fields['ano'].initial = hoje.year

        self.fields['observacoes'].required = False
        self.fields['meta_faturamento'].label = 'Meta de Faturamento (AKZ)'


class ComissaoForm(BaseVendaForm):
    """Form para comissões (edição manual — o valor é recalculado no save() do modelo)."""

    class Meta:
        model = Comissao
        fields = ['vendedor', 'venda', 'percentual', 'observacoes']
        widgets = {
            'percentual': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True)
        self.fields['venda'].queryset = Venda.objects.filter(status='finalizada')
        self.fields['observacoes'].required = False


# =====================================
# BUSCA E FILTRO FORMS
# =====================================

class VendaBuscaForm(forms.Form):
    """Form para busca e filtro de vendas."""

    STATUS_CHOICES = [
        ('', 'Todos os Status'),
        ('rascunho', 'Rascunho'),
        ('pendente', 'Pendente'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ]

    PERIODO_CHOICES = [
        ('', 'Selecione o período'),
        ('hoje', 'Hoje'),
        ('ontem', 'Ontem'),
        ('semana', 'Esta semana'),
        ('mes', 'Este mês'),
        ('trimestre', 'Este trimestre'),
        ('ano', 'Este ano'),
        ('personalizado', 'Período personalizado'),
    ]

    busca = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Buscar por número, cliente, vendedor...', 'class': 'form-control'})
    )
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    periodo = forms.ChoiceField(choices=PERIODO_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    data_inicio = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    data_fim = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.none(), required=False, empty_label='Todos os clientes',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    vendedor = forms.ModelChoiceField(
        queryset=Funcionario.objects.none(), required=False, empty_label='Todos os vendedores',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True).order_by('nome_completo')
        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True).order_by('nome_completo')


class ProdutoVendaBuscaForm(forms.Form):
    """Form para busca de produtos na venda."""

    busca = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Buscar produto por nome, código ou princípio ativo...',
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)


# =====================================
# NOTA DE CRÉDITO FORMS
# =====================================

class NotaCreditoForm(forms.ModelForm):
    """Form para criar/editar Nota de Crédito."""

    class Meta:
        model = NotaCredito
        fields = [
            'venda_origem', 'fatura_credito_origem', 'cliente', 'vendedor',
            'motivo', 'observacoes', 'total'
        ]
        widgets = {
            'venda_origem': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'fatura_credito_origem': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'cliente': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'required': True
            }),
            'vendedor': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'motivo': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 3,
                'placeholder': 'Observações adicionais (opcional)...'
            }),
            'total': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0.01',
                'required': True
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True)
        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True)
        self.fields['venda_origem'].queryset = Venda.objects.filter(status='finalizada').order_by('-data_venda')
        self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.all().order_by('-data_fatura')

    def clean(self):
        cleaned_data = super().clean()
        venda_origem = cleaned_data.get('venda_origem')
        fatura_credito_origem = cleaned_data.get('fatura_credito_origem')
        total = cleaned_data.get('total')

        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")

        if venda_origem and fatura_credito_origem:
            raise ValidationError("Selecione apenas uma origem: Venda OU Fatura a Crédito, não ambas.")

        documento_origem = venda_origem or fatura_credito_origem
        if documento_origem and total and total > documento_origem.total:
            raise ValidationError(
                f"O valor do crédito (Kz {total}) não pode ser maior que o documento de origem (Kz {documento_origem.total})."
            )

        if documento_origem and not cleaned_data.get('cliente'):
            cleaned_data['cliente'] = documento_origem.cliente

        return cleaned_data


class ItemNotaCreditoForm(forms.ModelForm):
    """Form para itens da Nota de Crédito."""

    class Meta:
        model = ItemNotaCredito
        fields = [
            'produto', 'servico', 'descricao_item', 'quantidade_creditada',
            'valor_unitario_credito', 'iva_percentual', 'motivo_item'
        ]
        widgets = {
            'produto': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'servico': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'descricao_item': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Descrição do item creditado'
            }),
            'quantidade_creditada': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01'
            }),
            'valor_unitario_credito': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01'
            }),
            'iva_percentual': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0', 'max': '100', 'value': '14'
            }),
            'motivo_item': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2, 'placeholder': 'Motivo específico para este item (opcional)'
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['produto'].queryset = Produto.objects.filter(ativo=True)
        try:
            from apps.servicos.models import Servico
            self.fields['servico'].queryset = Servico.objects.filter(ativo=True)
        except ImportError:
            pass


class NotaDebitoForm(forms.ModelForm):
    """Form para criar/editar Nota de Débito."""

    class Meta:
        model = NotaDebito
        fields = [
            'venda_origem', 'fatura_credito_origem', 'cliente', 'vendedor',
            'motivo', 'data_vencimento', 'observacoes', 'total'
        ]
        widgets = {
            'venda_origem': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'fatura_credito_origem': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'cliente': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'required': True
            }),
            'vendedor': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'motivo': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'data_vencimento': forms.DateInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'date', 'required': True
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 3, 'placeholder': 'Observações adicionais (opcional)...'
            }),
            'total': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01', 'required': True
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True)
        self.fields['vendedor'].queryset = Funcionario.objects.filter(ativo=True)
        self.fields['venda_origem'].queryset = Venda.objects.filter(status='finalizada').order_by('-data_venda')
        self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.all().order_by('-data_fatura')

        if not self.instance.pk:
            self.fields['data_vencimento'].initial = timezone.now().date() + timedelta(days=30)

    def clean(self):
        cleaned_data = super().clean()
        venda_origem = cleaned_data.get('venda_origem')
        fatura_credito_origem = cleaned_data.get('fatura_credito_origem')
        data_vencimento = cleaned_data.get('data_vencimento')

        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")

        if venda_origem and fatura_credito_origem:
            raise ValidationError("Selecione apenas uma origem: Venda OU Fatura a Crédito, não ambas.")

        if data_vencimento and data_vencimento <= timezone.now().date():
            raise ValidationError("A data de vencimento deve ser futura.")

        documento_origem = venda_origem or fatura_credito_origem
        if documento_origem and not cleaned_data.get('cliente'):
            cleaned_data['cliente'] = documento_origem.cliente

        return cleaned_data


class ItemNotaDebitoForm(forms.ModelForm):
    """Form para itens da Nota de Débito."""

    class Meta:
        model = ItemNotaDebito
        fields = [
            'produto', 'servico', 'descricao_item', 'quantidade',
            'valor_unitario', 'iva_percentual', 'justificativa'
        ]
        widgets = {
            'produto': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'servico': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'descricao_item': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Descrição do item debitado'
            }),
            'quantidade': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01'
            }),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01'
            }),
            'iva_percentual': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0', 'max': '100', 'value': '14'
            }),
            'justificativa': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2, 'placeholder': 'Justificativa para este item (opcional)'
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['produto'].queryset = Produto.objects.filter(ativo=True)
        try:
            from apps.servicos.models import Servico
            self.fields['servico'].queryset = Servico.objects.filter(ativo=True)
        except ImportError:
            pass


# =====================================
# DOCUMENTO DE TRANSPORTE FORMS
# =====================================

class DocumentoTransporteForm(forms.ModelForm):
    """Form para criar/editar Documento de Transporte."""

    class Meta:
        model = DocumentoTransporte
        fields = [
            'venda_origem', 'fatura_credito_origem', 'tipo_operacao', 'tipo_transporte',
            'data_inicio_transporte', 'data_previsao_entrega',
            'destinatario_cliente', 'destinatario_nome', 'destinatario_nif',
            'destinatario_endereco', 'destinatario_telefone', 'destinatario_provincia',
            'transportador_nome', 'transportador_nif', 'transportador_telefone',
            'veiculo_matricula', 'veiculo_modelo', 'condutor_nome', 'condutor_carta',
            'local_carregamento', 'local_descarga', 'itinerario',
            'valor_transporte', 'observacoes', 'instrucoes_especiais'
        ]
        widgets = {
            'venda_origem': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'fatura_credito_origem': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'tipo_operacao': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'tipo_transporte': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'data_inicio_transporte': forms.DateTimeInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
            'data_previsao_entrega': forms.DateTimeInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
            'destinatario_cliente': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'destinatario_nome': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Nome completo do destinatário'
            }),
            'destinatario_nif': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'NIF ou BI do destinatário'
            }),
            'destinatario_endereco': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Endereço completo de entrega'
            }),
            'destinatario_telefone': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Telefone do destinatário'
            }),
            'destinatario_provincia': forms.Select(choices=[
                ('', 'Selecione...'),
                ('BGO', 'Bengo'), ('ICB', 'Icolo e Bengo'), ('BGU', 'Benguela'),
                ('BIE', 'Bié'), ('CAB', 'Cabinda'), ('CCS', 'Cuando Cubango'),
                ('CNO', 'Cuanza Norte'), ('CUS', 'Cuanza Sul'), ('CNN', 'Cunene'),
                ('HUA', 'Huambo'), ('HUI', 'Huíla'), ('LUA', 'Luanda'),
                ('LNO', 'Lunda Norte'), ('LSU', 'Lunda Sul'), ('MAL', 'Malanje'),
                ('MOX', 'Moxico'), ('NAM', 'Namibe'), ('UIG', 'Uíge'), ('ZAI', 'Zaire'),
            ], attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'transportador_nome': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Nome da transportadora ou condutor'
            }),
            'transportador_nif': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'NIF da transportadora'
            }),
            'transportador_telefone': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Telefone da transportadora'
            }),
            'veiculo_matricula': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Matrícula do veículo'
            }),
            'veiculo_modelo': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Marca/modelo do veículo'
            }),
            'condutor_nome': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Nome completo do condutor'
            }),
            'condutor_carta': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Número da carta de condução'
            }),
            'local_carregamento': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Local onde a mercadoria será carregada'
            }),
            'local_descarga': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Local onde a mercadoria será descarregada'
            }),
            'itinerario': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 3, 'placeholder': 'Descreva o itinerário detalhado do transporte...'
            }),
            'valor_transporte': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 3, 'placeholder': 'Observações gerais do transporte...'
            }),
            'instrucoes_especiais': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2, 'placeholder': 'Instruções especiais para o transporte...'
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        self.fields['destinatario_cliente'].queryset = Cliente.objects.filter(ativo=True)
        self.fields['venda_origem'].queryset = Venda.objects.filter(status='finalizada').order_by('-data_venda')
        self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.all().order_by('-data_fatura')

        if not self.instance.pk:
            agora = timezone.now()
            self.fields['data_inicio_transporte'].initial = agora
            self.fields['data_previsao_entrega'].initial = agora + timedelta(days=1)

    def clean(self):
        cleaned_data = super().clean()
        venda_origem = cleaned_data.get('venda_origem')
        fatura_credito_origem = cleaned_data.get('fatura_credito_origem')
        data_inicio = cleaned_data.get('data_inicio_transporte')
        data_previsao = cleaned_data.get('data_previsao_entrega')
        destinatario_cliente = cleaned_data.get('destinatario_cliente')
        destinatario_nome = cleaned_data.get('destinatario_nome')

        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")

        if data_inicio and data_previsao and data_previsao <= data_inicio:
            raise ValidationError("A data de previsão de entrega deve ser posterior à data de início do transporte.")

        if not destinatario_cliente and not destinatario_nome:
            raise ValidationError("Selecione um cliente ou informe o nome do destinatário.")

        return cleaned_data


class ItemDocumentoTransporteForm(forms.ModelForm):
    """Form para itens do Documento de Transporte."""

    class Meta:
        model = ItemDocumentoTransporte
        fields = [
            'produto', 'codigo_produto', 'descricao_produto', 'unidade_medida',
            'quantidade_enviada', 'peso_unitario', 'tipo_embalagem',
            'numero_serie', 'lote', 'valor_unitario', 'observacoes_item'
        ]
        widgets = {
            'produto': forms.Select(attrs={'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'}),
            'codigo_produto': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Código do produto'
            }),
            'descricao_produto': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Descrição detalhada do produto'
            }),
            'unidade_medida': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'UN, KG, LT, etc.'
            }),
            'quantidade_enviada': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0.01'
            }),
            'peso_unitario': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.001', 'min': '0'
            }),
            'tipo_embalagem': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Caixa, saco, pallet, etc.'
            }),
            'numero_serie': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Número de série (se aplicável)'
            }),
            'lote': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Lote (se aplicável)'
            }),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01', 'min': '0'
            }),
            'observacoes_item': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2, 'placeholder': 'Observações específicas do item...'
            })
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        self.fields['produto'].queryset = Produto.objects.filter(ativo=True)
