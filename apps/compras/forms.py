# apps/compras/forms.py
from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.core.validators import MinValueValidator
from .models import Compra, ItemCompra
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Produto

CONTROL = "block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-800 dark:text-white"

class CompraForm(forms.ModelForm):
    class Meta:
        model=Compra
        fields=["fornecedor"]
        widgets={"fornecedor": forms.Select(attrs={"class":CONTROL})}
        labels={"fornecedor":"Fornecedor"}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['fornecedor'].queryset=Fornecedor.objects.all().order_by('pk')
        self.fields['fornecedor'].required=False
        self.fields['fornecedor'].empty_label="Selecione um fornecedor (opcional)"

class ItemCompraForm(forms.ModelForm):
    class Meta:
        model=ItemCompra
        fields=["produto","quantidade","preco_unitario"]
        widgets={
            "produto":forms.Select(attrs={"class":CONTROL}),
            "quantidade":forms.NumberInput(attrs={"class":CONTROL,"step":"0.01","min":"0.01"}),
            "preco_unitario":forms.NumberInput(attrs={"class":CONTROL,"step":"0.01","min":"0"}),
        }
        labels={"produto":"Produto","quantidade":"Quantidade","preco_unitario":"Preço unitário (AKZ)"}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['produto'].queryset=Produto.objects.all().order_by('pk')
    def clean_quantidade(self):
        value=self.cleaned_data['quantidade']
        if value <= 0: raise forms.ValidationError("A quantidade deve ser superior a zero.")
        return value
    def clean_preco_unitario(self):
        value=self.cleaned_data['preco_unitario']
        if value < 0: raise forms.ValidationError("O preço não pode ser negativo.")
        return value

ItemCompraFormSet=inlineformset_factory(Compra, ItemCompra, form=ItemCompraForm, extra=1, can_delete=True, min_num=1, validate_min=True)

class CompraFiltroForm(forms.Form):
    data_inicio=forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date","class":CONTROL}),label="De")
    data_fim=forms.DateField(required=False,widget=forms.DateInput(attrs={"type":"date","class":CONTROL}),label="Até")
    fornecedor=forms.ModelChoiceField(required=False,queryset=Fornecedor.objects.none(),widget=forms.Select(attrs={"class":CONTROL}),empty_label="Todos",label="Fornecedor")
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.fields['fornecedor'].queryset=Fornecedor.objects.all().order_by('pk')
    def clean(self):
        data=super().clean()
        if data.get('data_inicio') and data.get('data_fim') and data['data_inicio']>data['data_fim']:
            raise forms.ValidationError("A data inicial não pode ser posterior à data final.")
        return data
