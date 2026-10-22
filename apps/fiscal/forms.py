from django import forms
from .models import RetencaoFonte

class RetencaoFonteForm(forms.ModelForm):
    class Meta:
        model = RetencaoFonte
        fields = [
            'fornecedor',          # Fornecedor/Prestador
            'conta_pagar',         # Conta a pagar relacionada
            'referencia_documento',# Número do documento/fatura
            'valor_base',          # Base tributável
            'taxa_retencao',       # Percentual da retenção
            'tipo_retencao',       # Tipo de imposto (IRPC, IRT etc)
        ]
        widgets = {
            'fornecedor': forms.Select(attrs={'class': 'form-select'}),
            'conta_pagar': forms.Select(attrs={'class': 'form-select'}),
            'referencia_documento': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: Fatura 123'}),
            'valor_base': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'taxa_retencao': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'tipo_retencao': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'referencia_documento': 'Número da fatura ou recibo do fornecedor',
            'valor_base': 'Base tributável da retenção',
            'taxa_retencao': 'Percentual aplicado sobre o valor base',
            'tipo_retencao': 'Escolha o tipo de imposto retido (IRPC, IRT etc)',
        }
