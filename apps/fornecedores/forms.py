# apps/fornecedores/forms.py
from django.utils import timezone
from django import forms
from django.core.exceptions import ValidationError
from .models import AvaliacaoFornecedor, ContratoFornecedor, CotacaoFornecedor, Fornecedor, ContatoFornecedor, Pedido
import re
from django.core.validators import RegexValidator



class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = '__all__'
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'observacoes_internas': forms.Textarea(attrs={'rows': 3}),
            'motivo_bloqueio': forms.Textarea(attrs={'rows': 3}),
            'foto': forms.FileInput(),
        }

    
    def clean_nif(self):
        nif = self.cleaned_data['nif']
        # Remove caracteres não numéricos
        nif_numbers = re.sub(r'\D', '', nif)
        
        if len(nif_numbers) != 14:
            raise ValidationError('NIF deve ter 14 dígitos')
        
        # Validação básica de NIF
        if not self.validate_nif(nif_numbers):
            raise ValidationError('NIF inválido')
        
        return nif
    
    def validate_nif(self, nif):
        """Validação matemática do NIF"""
        if len(nif) != 14:
            return False
        
        # Verifica se todos os dígitos são iguais
        if nif == nif[0] * 11:
            return False
        
        # Cálculo do primeiro dígito verificador
        sum1 = 0
        weight1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        for i in range(12):
            sum1 += int(nif[i]) * weight1[i]
        
        remainder1 = sum1 % 11
        digit1 = 0 if remainder1 < 2 else 11 - remainder1
        
        if int(nif[12]) != digit1:
            return False
        
        # Cálculo do segundo dígito verificador
        sum2 = 0
        weight2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        for i in range(13):
            sum2 += int(nif[i]) * weight2[i]
        
        remainder2 = sum2 % 11
        digit2 = 0 if remainder2 < 2 else 11 - remainder2
        
        return int(nif[13]) == digit2
    
    def clean_email_principal(self):
        email = self.cleaned_data['email_principal']
        
        # Verifica se já existe outro fornecedor com mesmo email na empresa
        if self.instance.pk:
            existing = Fornecedor.objects.filter(
                email_principal=email,
                empresa=self.instance.empresa
            ).exclude(pk=self.instance.pk)
        else:
            # Para novos fornecedores, empresa será definida na view
            existing = Fornecedor.objects.filter(email_principal=email)
        
        if existing.exists():
            raise ValidationError('Já existe um fornecedor com este email')
        
        return email

class ContatoFornecedorForm(forms.ModelForm):
    class Meta:
        model = ContatoFornecedor
        fields = ['nome', 'cargo', 'tipo_contato', 'telefone', 'celular', 'email', 'ativo'] #'principal'
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'cargo': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo_contato': forms.Select(attrs={'class': 'form-select'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'celular': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'principal': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PedidoCompraForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            'fornecedor', 'data_pedido', 'data_entrega_prevista',
            'condicao_pagamento', 'forma_pagamento', 'total'
        ]
        widgets = {
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
           # 'tipo_pedido': forms.Select(attrs={'class': 'form-select'}),
            #'data_prevista_entrega': forms.DateInput(
            #    attrs={'class': 'form-control', 'type': 'date'}
           # ),
           # 'condicoes_pagamento': forms.TextInput(attrs={'class': 'form-control'}),
            'endereco_entrega': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['fornecedor'].queryset = Fornecedor.objects.filter(
                status='ativo'
            )
    
    def clean_data_prevista_entrega(self):
        data = self.cleaned_data['data_prevista_entrega']
        from datetime import date
        
        if data <= date.today():
            raise ValidationError('Data prevista de entrega deve ser futura')
        
        return data

class ContatoForm(forms.ModelForm):
    telefone = forms.CharField(
        required=False,
        validators=[RegexValidator(r'^\+?\d{10,15}$', message="Informe um telefone válido.")]
    )
    celular = forms.CharField(
        required=False,
        validators=[RegexValidator(r'^\+?\d{10,15}$', message="Informe um celular válido.")]
    )
    
    class Meta:
        model = ContatoFornecedor
        fields = ['nome', 'cargo', 'tipo_contato', 'telefone', 'celular', 'email', 'contato_principal', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Nome'}),
            'cargo': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Cargo'}),
            'tipo_contato': forms.Select(attrs={'class': 'select'}),
            'email': forms.EmailInput(attrs={'class': 'input', 'placeholder': 'Email'}),
        }


# =====================================
# FORM CONTRATO
# =====================================
class ContratoForm(forms.ModelForm):
    data_inicio = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    data_fim = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    
    class Meta:
        model = ContratoFornecedor
        fields = ['fornecedor', 'titulo', 'descricao', 'data_inicio', 'data_fim', 'total', 'ativo']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'input', 'placeholder': 'Título do contrato'}),
            'descricao': forms.Textarea(attrs={'class': 'textarea', 'placeholder': 'Descrição'}),
            'total': forms.NumberInput(attrs={'class': 'input', 'step': '0.01'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        if data_inicio and data_fim and data_inicio > data_fim:
            raise forms.ValidationError("A data de início não pode ser maior que a data de fim.")


# =====================================
# FORM AVALIACAO
# =====================================
class AvaliacaoForm(forms.ModelForm):
    class Meta:
        model = AvaliacaoFornecedor
        fields = [
            'fornecedor', 'nota_pontualidade', 'nota_qualidade', 'pontos_positivos', 
            'pontos_negativos', 'sugestoes', 'avaliador', 'pedido', 'nota_atendimento', 
            'nota_preco', 'nota_geral', 'recomendaria'
            ]
        widgets = {
            'nota_pontualidade': forms.NumberInput(attrs={'class': 'input', 'min': 0, 'max': 10, 'step': 0.1}),
            'nota_qualidade': forms.NumberInput(attrs={'class': 'input', 'min': 0, 'max': 10, 'step': 0.1}),
            'nota_preco': forms.NumberInput(attrs={'class': 'input', 'min': 0, 'max': 10, 'step': 0.1}),
            'nota_geral': forms.NumberInput(attrs={'class': 'input', 'min': 0, 'max': 10, 'step': 0.1}),
            'pontos_negativos': forms.Textarea(attrs={'class': 'textarea', 'placeholder': 'Pontos negativos'}),
            'pontos_positivos': forms.Textarea(attrs={'class': 'textarea', 'placeholder': 'Pontos positivos'}),
            'sugestoes': forms.Textarea(attrs={'class': 'textarea', 'placeholder': 'Sugestões'}),
            'recomendaria': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# =====================================
# FORM COTACAO
# =====================================
class CotacaoForm(forms.ModelForm):
    data_cotacao = forms.DateField(initial=timezone.now, widget=forms.DateInput(attrs={'type': 'date'}))
    
    class Meta:
        model = CotacaoFornecedor
        fields = ['fornecedor', 'descricao', 'data_validade', 'total', 'ativo', 'usuario_criador']
        widgets = {
            'data_validade': forms.DateInput(attrs={'type': 'date', 'class': 'input'}),
            'total': forms.NumberInput(attrs={'class': 'input', 'step': '0.01', 'min': 0}),
            'descricao': forms.Textarea(attrs={'class': 'textarea', 'placeholder': 'Descrições'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    # Ajuste para que o DateTimeInput funcione corretamente
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.data_criacao:
            self.fields['data_criacao'].initial = self.instance.data_criacao.strftime('%Y-%m-%dT%H:%M')
        if not self.instance.data_validade:
            self.fields['data_validade'].initial = timezone.now().date()
    





