# apps/funcionarios/forms_recibo.py
from datetime import date

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Cargo, Funcionario
from .models_recibo import (
    ConfiguracaoRecibo, DadosSalariaisFuncionario, EscalaIRT, ParametroFiscal, ProcessamentoSalarial,
    ReciboVencimento, Rubrica, RubricaFuncionario, TabelaIRT,
)


class DataMixin:
    """Todos os DateField passam a ter selector de data nativo."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for f in self.fields.values():
            if isinstance(f, forms.DateField):
                f.widget = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class RubricaForm(DataMixin, forms.ModelForm):
    categorias = forms.MultipleChoiceField(choices=Cargo.CATEGORIA_CHOICES, required=False,
                                           widget=forms.CheckboxSelectMultiple, label="Categorias de cargo")
    tipos_contrato = forms.MultipleChoiceField(choices=Funcionario.TIPO_CONTRATO_CHOICES, required=False,
                                               widget=forms.CheckboxSelectMultiple, label="Tipos de contrato")

    class Meta:
        model = Rubrica
        exclude = ('created_at', 'updated_at')

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        if self.instance.pk and self.instance.codigo_sistema:       # rubricas de sistema: só nome/descrição/ordem
            for n in [n for n in self.fields if n not in ('nome', 'descricao', 'ordem_calculo')]:
                del self.fields[n]

    def clean(self):
        d = super().clean()
        if 'ambito' not in d:
            return d
        a = d.get('ambito')
        if a == 'GRUPO' and not any([d.get('departamentos'), d.get('cargos'), d.get('categorias'), d.get('tipos_contrato')]):
            self.add_error('ambito', "No âmbito de grupo escolha pelo menos um critério.")
        if a == 'SELECIONADOS' and not d.get('funcionarios'):
            self.add_error('funcionarios', "Selecione os funcionários.")
        if a == 'INDIVIDUAL' and len(d.get('funcionarios') or []) != 1:
            self.add_error('funcionarios', "No âmbito individual escolha exatamente um funcionário.")
        return d


class AtribuicaoForm(DataMixin, forms.ModelForm):
    class Meta:
        model = RubricaFuncionario
        exclude = ('rubrica', 'criado_por', 'created_at', 'updated_at')

    def __init__(self, *a, rubrica=None, **k):
        super().__init__(*a, **k)
        self.instance.rubrica = rubrica


class ParametroFiscalForm(DataMixin, forms.ModelForm):
    class Meta:
        model = ParametroFiscal
        exclude = ('created_at', 'updated_at')


class TabelaIRTForm(DataMixin, forms.ModelForm):
    class Meta:
        model = TabelaIRT
        exclude = ('created_at', 'updated_at')


class BaseEscalaFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        escalas = sorted([f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')],
                         key=lambda c: c['ordem'])
        if len(escalas) < 2:
            raise forms.ValidationError("Defina pelo menos dois escalões.")
        if escalas[0]['limite_inferior'] != 0:
            raise forms.ValidationError("O 1.º escalão tem de começar em 0.")
        for ant, seg in zip(escalas, escalas[1:]):
            if ant.get('limite_superior') is None or ant['limite_superior'] != seg['limite_inferior']:
                raise forms.ValidationError("Os escalões têm de ser contíguos (o 'Até' de um é o 'Acima de' do seguinte).")
        if escalas[-1].get('limite_superior') is not None:
            raise forms.ValidationError("O último escalão não tem limite superior.")


EscalaFormSet = inlineformset_factory(
    TabelaIRT, EscalaIRT, formset=BaseEscalaFormSet, extra=2, can_delete=True,
    fields=('ordem', 'limite_inferior', 'limite_superior', 'parcela_fixa', 'taxa', 'excesso_de'))


class ConfiguracaoReciboForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoRecibo
        exclude = ('created_at', 'updated_at')


class DadosSalariaisForm(forms.ModelForm):
    class Meta:
        model = DadosSalariaisFuncionario
        exclude = ('funcionario', 'created_at', 'updated_at')


class ProcessamentoForm(forms.ModelForm):
    class Meta:
        model = ProcessamentoSalarial
        fields = ('mes', 'ano', 'descricao', 'moeda', 'observacoes')

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        hoje = date.today()
        self.fields['mes'].initial, self.fields['ano'].initial = hoje.month, hoje.year


class ConfirmacaoForm(DataMixin, forms.ModelForm):
    class Meta:
        model = ReciboVencimento
        fields = ('nome_responsavel', 'contabilista_nome', 'contabilista_numero_ordem', 'data_assinatura',
                  'referencia_pagamento', 'observacoes')


class PagamentoForm(DataMixin, forms.Form):
    data_pagamento = forms.DateField(initial=date.today)
    referencia_pagamento = forms.CharField(max_length=100, required=False, label="Referência do pagamento")


class MotivoForm(forms.Form):
    motivo = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), min_length=5)


class LancamentoForm(forms.Form):
    rubrica = forms.ModelChoiceField(queryset=Rubrica.objects.none())
    quantidade = forms.DecimalField(required=False, max_digits=12, decimal_places=2)
    valor = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=0)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields['rubrica'].queryset = Rubrica.objects.filter(ativa=True, codigo_sistema__isnull=True).exclude(
            tipo='ENCARGO_PATRONAL')


class AjusteForm(forms.Form):
    ajuste_salario_base = forms.DecimalField(required=False, max_digits=14, decimal_places=2, min_value=0)
