# apps/vendas/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from decimal import Decimal
from datetime import date, timedelta
from .models import Convenio

from .models import *
from apps.clientes.models import Cliente
from apps.produtos.models import Produto
from apps.funcionarios.models import Funcionario


# =====================================
# FORM BASE
# =====================================

class BaseVendaForm(forms.ModelForm):
    """Form base para vendas com métodos comuns"""
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Aplicar classes CSS padrão
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
    
    def filter_by_empresa(self, queryset):
        """Filtrar queryset pela empresa do usuário"""
        if self.empresa:
            return queryset.filter(empresa=self.empresa)
        return queryset.none()


# =====================================
# VENDA FORMS
# =====================================

class VendaForm(BaseVendaForm):
    """Form principal para criação e edição de vendas"""
    
    class Meta:
        model = Venda
        fields = ['cliente', 'vendedor', 'forma_pagamento', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar opções pela empresa
            self.fields['cliente'].queryset = Cliente.objects.filter(empresa=self.empresa, ativo=True)
            self.fields['vendedor'].queryset = Funcionario.objects.filter(empresa=self.empresa, ativo=True)
            self.fields['forma_pagamento'].queryset = FormaPagamento.objects.filter(empresa=self.empresa, ativa=True)
        
        # Campos opcionais
        self.fields['cliente'].required = False
        self.fields['observacoes'].required = False
        
        # Labels personalizados
        self.fields['cliente'].label = 'Cliente (Opcional - deixe vazio para consumidor final)'
        self.fields['forma_pagamento'].label = 'Forma de Pagamento'


class ItemVendaForm(forms.ModelForm):
    """Form para itens da venda"""
    
    class Meta:
        model = ItemVenda
        fields = ['produto', 'quantidade', 'preco_unitario']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'min': '1', 'step': '1'}),
            'preco_unitario': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['produto'].queryset = Produto.objects.filter(
                empresa=self.empresa, 
                ativo=True
            ).order_by('nome_comercial')
        
        # Configurar campo de preço
        if self.instance.pk and self.instance.produto:
            self.fields['preco_unitario'].initial = self.instance.produto.preco_venda
        
        self.fields['preco_unitario'].label = 'Preço Unitário (AKZ)'
    
    def clean(self):
        cleaned_data = super().clean()
        produto = cleaned_data.get('produto')
        quantidade = cleaned_data.get('quantidade')
        
        if produto and quantidade:
            # Verificar estoque
            if produto.estoque_atual < quantidade:
                raise ValidationError(
                    f'Estoque insuficiente. Disponível: {produto.estoque_atual}'
                )
        
        return cleaned_data


# =====================================
# PAGAMENTO FORMS
# =====================================

class PagamentoVendaForm(BaseVendaForm):
    """Form para pagamentos"""
    
    class Meta:
        model = PagamentoVenda
        fields = ['forma_pagamento', 'valor_pago', 'observacoes']
        widgets = {
            'valor_pago': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['forma_pagamento'].queryset = FormaPagamento.objects.filter(
                empresa=self.empresa, ativa=True
            )
        
        # Campos opcionais
        self.fields['observacoes'].required = False
        
        # Labels
        self.fields['valor_pago'].label = 'Valor Pago (AKZ)'


class FormaPagamentoForm(BaseVendaForm):
    """Form para formas de pagamento"""
    
    class Meta:
        model = FormaPagamento
        fields = ['nome', 'tipo', 'ativa']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Valores padrão
        self.fields['ativa'].initial = True



class ConvenioForm(forms.ModelForm):
    """
    RIGOR SOTARQ: Formulário para gestão de convênios e seguradoras.
    Garante integridade multi-tenant e estilização padronizada.
    """
    class Meta:
        model = Convenio
        fields = [
            'nome', 'codigo', 'contato', 'telefone', 
            'percentual_desconto', 'ativa', 'observacoes'
        ]
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Notas adicionais sobre o convênio...'}),
            'percentual_desconto': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'telefone': forms.TextInput(attrs={'placeholder': 'Ex: 923000000'}),
        }
        help_texts = {
            'percentual_desconto': 'Este valor será aplicado automaticamente em vendas vinculadas a este convênio.',
        }

    def __init__(self, *args, **kwargs):
        # Extrai a empresa do kwargs para garantir o rigor multi-tenant
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        # 1. Estilização Automática SOTARQ
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-checkbox h-5 w-5 text-primary-600 border-gray-300 rounded focus:ring-primary-500'
            else:
                field.widget.attrs['class'] = 'form-input block w-full px-4 py-3 rounded-lg border-gray-300 focus:ring-primary-500 focus:border-primary-500'

    def clean_nome(self):
        """Validação de unicidade por empresa (Rigor SOTARQ)"""
        nome = self.cleaned_data.get('nome')
        if self.empresa:
            exists = Convenio.objects.filter(
                empresa=self.empresa, 
                nome__iexact=nome
            ).exclude(pk=self.instance.pk).exists()
            
            if exists:
                raise forms.ValidationError("Já existe um convênio cadastrado com este nome na sua empresa.")
        return nome
# =====================================
# DEVOLUÇÃO E TROCA FORMS
# =====================================

class DevolucaoForm(BaseVendaForm):
    """Form para devoluções"""
    
    class Meta:
        model = DevolucaoVenda
        fields = ['venda_original', 'cliente', 'motivo', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar vendas finalizadas da empresa
            self.fields['venda'].queryset = Venda.objects.filter(
                empresa=self.empresa,
                status='finalizada'
            ).order_by('-data_venda')
            
            self.fields['cliente'].queryset = Cliente.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Campos obrigatórios
        self.fields['motivo'].required = True


class ItemDevolucaoForm(forms.ModelForm):
    """Form para itens devolvidos"""
    
    class Meta:
        model = ItemDevolucao
        fields = ['produto', 'quantidade_devolvida', 'motivo']
        widgets = {
            'quantidade': forms.NumberInput(attrs={'min': '1', 'step': '1'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.venda = kwargs.pop('venda', None)
        super().__init__(*args, **kwargs)
        
        if self.venda:
            # Filtrar apenas produtos da venda
            produtos_venda = self.venda.itens.values_list('produto', flat=True)
            self.fields['produto'].queryset = Produto.objects.filter(id__in=produtos_venda)


class DevolucaoForm(BaseVendaForm):
    """Form para trocas"""
    
    class Meta:
        model = DevolucaoVenda
        fields = ['venda_original', 'cliente', 'motivo', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['venda_original'].queryset = Venda.objects.filter(
                empresa=self.empresa,
                status='finalizada'
            ).order_by('-data_venda')
            
            self.fields['cliente'].queryset = Cliente.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Campos opcionais
        self.fields['observacoes'].required = False
        
        # Labels
        self.fields['venda_original'].label = 'Venda Original'
        self.fields['motivo_troca'].label = 'Motivo da Troca'


# =====================================
# DELIVERY E ENTREGA FORMS
# =====================================

class AgendarEntregaForm(BaseVendaForm):
    """Form para agendar entregas"""
    
    class Meta:
        model = Venda
        fields = ['observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Campos opcionais
        self.fields['observacoes'].required = False
        self.fields['observacoes'].label = 'Observações da Entrega'


class EntregaForm(BaseVendaForm):
    """Form para entregas"""
    
    class Meta:
        model = Entrega
        fields = ['venda', 'entregador', 'endereco', 'observacoes']
        widgets = {
            'endereco': forms.Textarea(attrs={'rows': 3}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            # Filtrar vendas da empresa
            self.fields['venda'].queryset = Venda.objects.filter(empresa=self.empresa)
            
            # Filtrar entregadores ativos
            self.fields['entregador'].queryset = Funcionario.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Campos opcionais
        self.fields['observacoes'].required = False


# =====================================
# CONVÊNIO FORMS
# =====================================

class ConvenioForm(BaseVendaForm):
    """Form para convênios"""
    
    class Meta:
        model = Convenio
        fields = ['nome', 'contato', 'telefone', 'ativa', 'percentual_desconto', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Campos opcionais
        self.fields['telefone'].required = False
        self.fields['observacoes'].required = False
        
        # Valores padrão
        self.fields['ativo'].initial = True


# =====================================
# META E COMISSÃO FORMS
# =====================================

class MetaVendaForm(BaseVendaForm):
    """Form para metas de venda"""
    
    class Meta:
        model = MetaVenda
        fields = ['vendedor', 'mes', 'ano', 'meta_faturamento', 'observacoes']
        widgets = {
            'mes': forms.Select(),
            'ano': forms.NumberInput(attrs={'min': '2020', 'max': '2030'}),
            'meta_faturamento': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['vendedor'].queryset = Funcionario.objects.filter(
                empresa=self.empresa, ativo=True
            )
        
        # Choices para mês
        MESES = [
            (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'),
            (4, 'Abril'), (5, 'Maio'), (6, 'Junho'),
            (7, 'Julho'), (8, 'Agosto'), (9, 'Setembro'),
            (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro'),
        ]
        self.fields['mes'].widget.choices = MESES
        
        # Valores padrão
        hoje = date.today()
        self.fields['mes'].initial = hoje.month
        self.fields['ano'].initial = hoje.year
        
        # Campos opcionais
        self.fields['observacoes'].required = False
        
        # Labels
        self.fields['meta_faturamento'].label = 'Meta de Faturamento (AKZ)'


class ComissaoForm(BaseVendaForm):
    """Form para comissões"""
    
    class Meta:
        model = Comissao
        fields = ['vendedor', 'venda', 'valor_comissao', 'observacoes']
        widgets = {
            'valor_comissao': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.empresa:
            self.fields['vendedor'].queryset = Funcionario.objects.filter(
                empresa=self.empresa, ativo=True
            )
            self.fields['venda'].queryset = Venda.objects.filter(
                empresa=self.empresa, status='finalizada'
            )
        
        # Campos opcionais
        self.fields['observacoes'].required = False
        
        # Labels
        self.fields['valor_comissao'].label = 'Valor da Comissão (AKZ)'


# =====================================
# BUSCA E FILTRO FORMS
# =====================================

class VendaBuscaForm(forms.Form):
    """Form para busca e filtro de vendas"""
    
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
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Buscar por número, cliente, vendedor...',
            'class': 'form-control'
        })
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    periodo = forms.ChoiceField(
        choices=PERIODO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    data_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    data_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.none(),
        required=False,
        empty_label='Todos os clientes',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    vendedor = forms.ModelChoiceField(
        queryset=Funcionario.objects.none(),
        required=False,
        empty_label='Todos os vendedores',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['cliente'].queryset = Cliente.objects.filter(
                empresa=empresa,
                ativo=True
            ).order_by('nome_completo')
            
            self.fields['vendedor'].queryset = Funcionario.objects.filter(
                empresa=empresa,
                ativo=True
            ).order_by('nome_completo')


class ProdutoVendaBuscaForm(forms.Form):
    """Form para busca de produtos na venda"""
    
    busca = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Buscar produto por nome, código ou princípio ativo...',
            'class': 'form-control',
            'autocomplete': 'off'
        })
    )
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)


# Adicionar ao arquivo apps/vendas/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import (
    NotaCredito, ItemNotaCredito, NotaDebito, ItemNotaDebito,
    DocumentoTransporte, ItemDocumentoTransporte
)
from apps.clientes.models import Cliente
from apps.produtos.models import Produto


class NotaCreditoForm(forms.ModelForm):
    """Form para criar/editar Nota de Crédito"""

    class Meta:
        model = NotaCredito
        fields = [
            'venda_origem', 'fatura_credito_origem', 'cliente', 'vendedor',
            'observacoes', 'total'
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
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)

        if empresa:
            if 'cliente' in self.fields:
                self.fields['cliente'].queryset = Cliente.objects.filter(empresa=empresa, ativo=True)
            try:
                from apps.funcionarios.models import Funcionario
                if 'vendedor' in self.fields:
                    self.fields['vendedor'].queryset = Funcionario.objects.filter(empresa=empresa, ativo=True)
            except ImportError:
                pass

            from .models import Venda, FaturaCredito
            if 'venda_origem' in self.fields:
                self.fields['venda_origem'].queryset = Venda.objects.filter(
                    empresa=empresa, status='finalizada'
                ).order_by('-data_venda')
            if 'fatura_credito_origem' in self.fields:
                try:
                    self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.filter(
                        empresa=empresa
                    ).order_by('-data_emissao')
                except:
                    self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        venda_origem = cleaned_data.get('venda_origem')
        fatura_credito_origem = cleaned_data.get('fatura_credito_origem')
        total = cleaned_data.get('total')

        # Deve haver uma origem
        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")

        # Não pode haver ambas
        if venda_origem and fatura_credito_origem:
            raise ValidationError("Selecione apenas uma origem: Venda OU Fatura a Crédito, não ambas.")

        # Valor do crédito não pode ser maior que o documento origem
        documento_origem = venda_origem or fatura_credito_origem
        if documento_origem and total:
            valor_origem = getattr(documento_origem, 'total', getattr(documento_origem, 'total_faturado', None))
            if valor_origem and total > valor_origem:
                raise ValidationError(
                    f"O valor do crédito (Kz {total}) não pode ser maior que o documento de origem (Kz {valor_origem})."
                )

        # Auto-preenche cliente se não selecionado
        if documento_origem and not cleaned_data.get('cliente'):
            cleaned_data['cliente'] = documento_origem.cliente

        return cleaned_data


class ItemNotaCreditoForm(forms.ModelForm):
    """Form para itens da Nota de Crédito"""
    
    class Meta:
        model = ItemNotaCredito
        fields = [
            'produto', 'servico', 'descricao_item', 'quantidade_creditada',
            'valor_unitario_credito', 'iva_percentual', 'motivo_item'
        ]
        widgets = {
            'produto': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'servico': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'descricao_item': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Descrição do item creditado'
            }),
            'quantidade_creditada': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0.01'
            }),
            'valor_unitario_credito': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0.01'
            }),
            'iva_percentual': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'value': '14'
            }),
            'motivo_item': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Motivo específico para este item (opcional)'
            })
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['produto'].queryset = Produto.objects.filter(empresa=empresa, ativo=True)
            
            try:
                from apps.servicos.models import Servico
                self.fields['servico'].queryset = Servico.objects.filter(empresa=empresa, ativo=True)
            except ImportError:
                pass


class NotaDebitoForm(forms.ModelForm):
    """Form para criar/editar Nota de Débito"""
    
    class Meta:
        model = NotaDebito
        fields = [
            'venda_origem', 'fatura_credito_origem', 'cliente', 'vendedor',
            'data_vencimento', 'observacoes', 'total'
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
            'data_vencimento': forms.DateInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'date',
                'required': True
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
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            # Filtrar opções por empresa
            self.fields['cliente'].queryset = Cliente.objects.filter(empresa=empresa, ativo=True)
            
            # Vendedores da empresa
            try:
                from apps.funcionarios.models import Funcionario
                self.fields['vendedor'].queryset = Funcionario.objects.filter(empresa=empresa, ativo=True)
            except ImportError:
                pass
            
            # Vendas e faturas da empresa
            from .models import Venda, FaturaCredito
            self.fields['venda_origem'].queryset = Venda.objects.filter(
                empresa=empresa, 
                status='finalizada'
            ).order_by('-data_venda')
            
            try:
                self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.filter(
                    empresa=empresa
                ).order_by('-data_emissao')
            except:
                self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.none()
        
        # Data de vencimento padrão (30 dias)
        if not self.instance.pk:
            self.fields['data_vencimento'].initial = timezone.now().date() + timedelta(days=30)

    def clean(self):
        cleaned_data = super().clean()
        venda_origem = cleaned_data.get('venda_origem')
        fatura_credito_origem = cleaned_data.get('fatura_credito_origem')
        data_vencimento = cleaned_data.get('data_vencimento')
        
        # Validação: deve ter pelo menos uma origem
        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")
        
        # Validação: não pode ter ambas
        if venda_origem and fatura_credito_origem:
            raise ValidationError("Selecione apenas uma origem: Venda OU Fatura a Crédito, não ambas.")
        
        # Validação: data de vencimento não pode ser passada
        if data_vencimento and data_vencimento <= timezone.now().date():
            raise ValidationError("A data de vencimento deve ser futura.")
        
        # Auto-preencher cliente se não selecionado
        documento_origem = venda_origem or fatura_credito_origem
        if documento_origem and not cleaned_data.get('cliente'):
            cleaned_data['cliente'] = documento_origem.cliente
        
        return cleaned_data


class ItemNotaDebitoForm(forms.ModelForm):
    """Form para itens da Nota de Débito"""
    
    class Meta:
        model = ItemNotaDebito
        fields = [
            'produto', 'servico', 'descricao_item', 'quantidade',
            'valor_unitario', 'iva_percentual', 'justificativa'
        ]
        widgets = {
            'produto': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'servico': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'descricao_item': forms.TextInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'placeholder': 'Descrição do item debitado'
            }),
            'quantidade': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0.01'
            }),
            'valor_unitario': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0.01'
            }),
            'iva_percentual': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'value': '14'
            }),
            'justificativa': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Justificativa para este item (opcional)'
            })
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['produto'].queryset = Produto.objects.filter(empresa=empresa, ativo=True)
            
            try:
                from apps.servicos.models import Servico
                self.fields['servico'].queryset = Servico.objects.filter(empresa=empresa, ativo=True)
            except ImportError:
                pass


class DocumentoTransporteForm(forms.ModelForm):
    """Form para criar/editar Documento de Transporte"""
    
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
            'venda_origem': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'fatura_credito_origem': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'tipo_operacao': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'tipo_transporte': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
            'data_inicio_transporte': forms.DateTimeInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
            'data_previsao_entrega': forms.DateTimeInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'type': 'datetime-local'
            }),
            'destinatario_cliente': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
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
            ], attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
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
                'rows': 3,
                'placeholder': 'Descreva o itinerário detalhado do transporte...'
            }),
            'valor_transporte': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.01',
                'min': '0'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 3,
                'placeholder': 'Observações gerais do transporte...'
            }),
            'instrucoes_especiais': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Instruções especiais para o transporte...'
            })
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            # Filtrar opções por empresa
            self.fields['destinatario_cliente'].queryset = Cliente.objects.filter(empresa=empresa, ativo=True)
            
            # Vendas e faturas da empresa
            from .models import Venda, FaturaCredito
            self.fields['venda_origem'].queryset = Venda.objects.filter(
                empresa=empresa, 
                status='finalizada'
            ).order_by('-data_venda')
            
            try:
                self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.filter(
                    empresa=empresa
                ).order_by('-data_emissao')
            except:
                self.fields['fatura_credito_origem'].queryset = FaturaCredito.objects.none()
        
        # Dados padrão
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
        
        # Validação: deve ter pelo menos uma origem
        if not venda_origem and not fatura_credito_origem:
            raise ValidationError("Selecione uma Venda (FR) ou Fatura a Crédito (FT) de origem.")
        
        # Validação: data de previsão deve ser posterior ao início
        if data_inicio and data_previsao and data_previsao <= data_inicio:
            raise ValidationError("A data de previsão de entrega deve ser posterior à data de início do transporte.")
        
        # Validação: destinatário
        if not destinatario_cliente and not destinatario_nome:
            raise ValidationError("Selecione um cliente ou informe o nome do destinatário.")
        
        return cleaned_data


class ItemDocumentoTransporteForm(forms.ModelForm):
    """Form para itens do Documento de Transporte"""
    
    class Meta:
        model = ItemDocumentoTransporte
        fields = [
            'produto', 'codigo_produto', 'descricao_produto', 'unidade_medida',
            'quantidade_enviada', 'peso_unitario', 'tipo_embalagem',
            'numero_serie', 'lote', 'valor_unitario', 'observacoes_item'
        ]
        widgets = {
            'produto': forms.Select(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white'
            }),
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
                'step': '0.01',
                'min': '0.01'
            }),
            'peso_unitario': forms.NumberInput(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'step': '0.001',
                'min': '0'
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
                'step': '0.01',
                'min': '0'
            }),
            'observacoes_item': forms.Textarea(attrs={
                'class': 'text-base w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white',
                'rows': 2,
                'placeholder': 'Observações específicas do item...'
            })
        }

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['produto'].queryset = Produto.objects.filter(empresa=empresa, ativo=True)


