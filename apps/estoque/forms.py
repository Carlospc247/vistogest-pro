# apps/estoque/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from datetime import date, timedelta

from apps.produtos.models import Lote

from .models import (
    TipoMovimentacao, MovimentacaoEstoque, Inventario, 
    ItemInventario, AlertaEstoque, LocalizacaoEstoque
)

User = get_user_model()

class TipoMovimentacaoForm(forms.ModelForm):
    """Formulário para Tipo de Movimentação"""
    
    class Meta:
        model = TipoMovimentacao
        fields = [
            'nome', 'codigo', 'natureza', 'requer_documento', 
            'requer_aprovacao', 'automatico', 'controla_lote', 
            'controla_validade', 'descricao', 'ativo'
        ]
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome do tipo de movimentação'
            }),
            'codigo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código único (ex: ENT_COMPRA)',
                'style': 'text-transform: uppercase;'
            }),
            'natureza': forms.Select(attrs={'class': 'form-control'}),
            'requer_documento': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requer_aprovacao': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'automatico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'controla_lote': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'controla_validade': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descrição opcional do tipo de movimentação'
            }),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
    
    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].upper()
        
        # Verificar se já existe outro tipo com este código
        if TipoMovimentacao.objects.filter(codigo=codigo).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Já existe um tipo de movimentação com este código.')
        
        return codigo

class MovimentacaoEstoqueForm(forms.ModelForm):
    """Formulário para Movimentação de Estoque"""
    
    class Meta:
        model = MovimentacaoEstoque
        fields = ['produto', 'tipo', 'quantidade', 'motivo', 'observacoes']
        widgets = {
            'produto': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Selecione o produto'
            }),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'quantidade': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'step': '1'
            }),
            'motivo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Motivo da movimentação',
                'maxlength': '200'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observações adicionais (opcional)'
            })
        }
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            # Usar get_model para evitar problemas de import
            from django.apps import apps
            Produto = apps.get_model('produtos', 'Produto')
            self.fields['produto'].queryset = Produto.objects.filter(
                empresa=empresa, 
                ativo=True
            ).order_by('nome_produto')
        
        # Observações é opcional
        self.fields['observacoes'].required = False




# Em apps/estoque/forms.py

from django import forms
from .models import Inventario, Loja, Usuario
from apps.empresas.models import Categoria

# ... (suas outras classes de estilo) ...
form_field_classes = 'block w-full rounded-md border-0 py-1.5 text-gray-900 dark:text-white shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-blue-600 sm:text-sm sm:leading-6 dark:bg-gray-700'
checkbox_classes = 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-600'


class InventarioForm(forms.ModelForm):
    class Meta:
        model = Inventario
        fields = [
            'titulo', 'descricao', 'loja', 'data_planejada', 
            'categorias', 'responsaveis_contagem', 'requer_dupla_contagem',
            'apenas_produtos_ativos', 'apenas_com_estoque', 'bloqueio_movimentacao'
        ]
        widgets = {
            'data_planejada': forms.DateInput(attrs={'type': 'date'}),
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'categorias': forms.SelectMultiple(),
            'responsaveis_contagem': forms.SelectMultiple(),
        }

    # --- A CORREÇÃO ESTÁ AQUI ---
    def __init__(self, *args, **kwargs):
        # 1. "Apanha" o argumento 'empresa' antes de o passar ao ModelForm.
        empresa = kwargs.pop('empresa', None)
        
        # 2. Chama o __init__ original, mas já sem o argumento 'empresa'.
        super().__init__(*args, **kwargs)
        
        # 3. Agora, aplica estilos e usa a 'empresa' para filtrar os campos.
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = checkbox_classes
            elif isinstance(field.widget, forms.SelectMultiple):
                field.widget.attrs['class'] = 'select2 w-full'
            else:
                field.widget.attrs['class'] = form_field_classes

        # Filtra os campos ForeignKey/ManyToMany para a empresa correta
        if empresa:
            if 'loja' in self.fields:
                self.fields['loja'].queryset = Loja.objects.filter(empresa=empresa)
            if 'categorias' in self.fields:
                self.fields['categorias'].queryset = Categoria.objects.filter(empresa=empresa, ativa=True)
            if 'responsaveis_contagem' in self.fields:
                self.fields['responsaveis_contagem'].queryset = Usuario.objects.filter(funcionario__empresa=empresa)


class InventarioCategoriasForm(forms.Form):
    """Formulário separado para categorias do inventário"""
    
    categorias = forms.ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Selecione as categorias (vazio = todas)'
        }),
        label='Categorias'
    )
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            from django.apps import apps
            Categoria = apps.get_model('produtos', 'Categoria')
            self.fields['categorias'].queryset = Categoria.objects.filter(
                empresa=empresa,
                ativa=True
            )

class InventarioResponsaveisForm(forms.Form):
    """Formulário separado para responsáveis do inventário"""
    
    responsaveis_contagem = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.SelectMultiple(attrs={
            'class': 'form-control select2-multiple',
            'data-placeholder': 'Selecione os responsáveis'
        }),
        label='Responsáveis pela Contagem'
    )
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            from django.apps import apps
            Usuario = apps.get_model('core', 'Usuario')
            self.fields['responsaveis_contagem'].queryset = Usuario.objects.filter(
                empresa=empresa
            )

class ItemInventarioForm(forms.ModelForm):
    """Formulário para Item do Inventário"""
    
    class Meta:
        model = ItemInventario
        fields = ['quantidade_contada_1', 'quantidade_contada_2', 'observacoes']
        widgets = {
            'quantidade_contada_1': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
                'placeholder': 'Primeira contagem'
            }),
            'quantidade_contada_2': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
                'placeholder': 'Segunda contagem'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Observações sobre este item'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Todos os campos são opcionais inicialmente
        self.fields['quantidade_contada_1'].required = False
        self.fields['quantidade_contada_2'].required = False
        self.fields['observacoes'].required = False

class ContagemRapidaForm(forms.Form):
    """Formulário para contagem rápida de um item"""
    
    quantidade_contada = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'min': '0',
            'step': '1',
            'autofocus': True
        }),
        label='Quantidade Contada'
    )
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Observações (opcional)'
        }),
        label='Observações'
    )

class AlertaEstoqueForm(forms.ModelForm):
    """Formulário para Alerta de Estoque"""
    
    class Meta:
        model = AlertaEstoque
        fields = [
            'tipo_alerta', 'prioridade', 'produto', 'loja',
            'titulo', 'descricao', 'quantidade_atual', 
            'quantidade_recomendada'
        ]
        widgets = {
            'tipo_alerta': forms.Select(attrs={'class': 'form-control'}),
            'prioridade': forms.Select(attrs={'class': 'form-control'}),
            'produto': forms.Select(attrs={
                'class': 'form-control select2',
                'data-placeholder': 'Selecione o produto'
            }),
            'loja': forms.Select(attrs={'class': 'form-control'}),
            'titulo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Título do alerta'
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descrição detalhada do alerta'
            }),
            'quantidade_atual': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            }),
            'quantidade_recomendada': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0'
            })
        }
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            from django.apps import apps
            Produto = apps.get_model('produtos', 'Produto')
            Loja = apps.get_model('core', 'Loja')
            
            self.fields['produto'].queryset = Produto.objects.filter(
                empresa=empresa,
                ativo=True
            ).order_by('nome_produto')
            
            self.fields['loja'].queryset = Loja.objects.filter(
                empresa=empresa,
                ativa=True
            )
        
        # Campos opcionais
        self.fields['quantidade_recomendada'].required = False

class LocalizacaoEstoqueForm(forms.ModelForm):
    """Formulário para Localização de Estoque"""
    
    class Meta:
        model = LocalizacaoEstoque
        fields = ['nome', 'descricao', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome da localização (ex: Depósito A, Prateleira 1)'
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descrição opcional da localização'
            }),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Descrição é opcional
        self.fields['descricao'].required = False
    
    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        
        # Verificar se já existe outra localização com este nome
        if LocalizacaoEstoque.objects.filter(nome__iexact=nome).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Já existe uma localização com este nome.')
        
        return nome

class FiltroMovimentacaoForm(forms.Form):
    """Formulário para filtrar movimentações"""
    
    data_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Data Início'
    )
    data_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Data Fim'
    )
    produto = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do produto'
        }),
        label='Produto'
    )
    tipo = forms.ChoiceField(
        choices=[('', 'Todos os tipos')] + MovimentacaoEstoque.TIPO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Tipo'
    )

class FiltroInventarioForm(forms.Form):
    """Formulário para filtrar inventários"""
    
    status = forms.ChoiceField(
        choices=[('', 'Todos os status')] + Inventario.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Status'
    )
    data_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Data Início'
    )
    data_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='Data Fim'
    )

class MovimentacaoRapidaForm(forms.Form):
    """Formulário para movimentação rápida"""
    
    produto_codigo = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Código do produto'
        }),
        label='Código do Produto'
    )
    tipo = forms.ChoiceField(
        choices=MovimentacaoEstoque.TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Tipo'
    )
    quantidade = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1'
        }),
        label='Quantidade'
    )
    motivo = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Motivo da movimentação'
        }),
        label='Motivo'
    )

class ImportacaoEstoqueForm(forms.Form):
    """Formulário para importação de dados de estoque via CSV"""
    
    arquivo_csv = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        }),
        label='Arquivo CSV',
        help_text='Formato: codigo_produto,quantidade,motivo'
    )
    tipo_movimentacao = forms.ChoiceField(
        choices=MovimentacaoEstoque.TIPO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Tipo de Movimentação'
    )
    
    def clean_arquivo_csv(self):
        arquivo = self.cleaned_data['arquivo_csv']
        
        if not arquivo.name.endswith('.csv'):
            raise ValidationError('Arquivo deve ser do tipo CSV.')
        
        if arquivo.size > 5 * 1024 * 1024:  # 5MB
            raise ValidationError('Arquivo muito grande. Máximo 5MB.')
        
        return arquivo

class ResolverAlertaForm(forms.Form):
    """Formulário para resolver alertas"""
    
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Observações sobre a resolução do alerta'
        }),
        label='Observações'
    )

# Formset para edição em lote de itens de inventário
ItemInventarioFormSet = forms.modelformset_factory(
    ItemInventario,
    form=ItemInventarioForm,
    fields=['quantidade_contada_1', 'observacoes'],
    extra=0,
    can_delete=False
)




