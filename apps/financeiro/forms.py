# apps/financeiro/forms.py
from django import forms
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Row, Column, Submit, HTML, Div
from crispy_forms.bootstrap import FormActions
from decimal import Decimal
from datetime import date, timedelta
from .models import (
    ContaReceber, ContaPagar, ImpostoTributo,
    CentroCusto, MovimentoCaixa, ContaBancaria,
    MovimentacaoFinanceira
)

class ContaReceberForm(forms.ModelForm):
    """Formulário para Conta a Receber"""
    
    class Meta:
        model = ContaReceber
        fields = [
            'numero_documento', 'descricao', 'tipo_conta', 'data_emissao',
            'data_vencimento', 'valor_original', 'valor_juros', 'valor_multa',
            'valor_desconto', 'cliente', 'venda',
            'centro_custo', 'numero_parcela', 'total_parcelas',
            'conta_pai', 'observacoes'
        ]
        
        widgets = {
            'data_emissao': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'data_vencimento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'valor_original': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_juros': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_multa': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_desconto': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'numero_parcela': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '1'}
            ),
            'total_parcelas': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '1'}
            ),
            'observacoes': forms.Textarea(
                attrs={'rows': 3, 'class': 'form-control'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar querysets por empresa
        if self.empresa:
            self.fields['cliente'].queryset = self.empresa.clientes.filter(ativo=True)
            self.fields['venda'].queryset = self.empresa.vendas.all()
            self.fields['plano_contas'].queryset = self.empresa.plano_contas.filter(
                tipo_conta='receita', ativa=True, aceita_lancamento=True
            )
            self.fields['centro_custo'].queryset = self.empresa.centro_custos.filter(ativo=True)
            self.fields['conta_pai'].queryset = ContaReceber.objects.filter(
                empresa=self.empresa, conta_pai__isnull=True
            )
        
        # Configurar crispy forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-3'
        self.helper.field_class = 'col-lg-9'
        
        self.helper.layout = Layout(
            Fieldset(
                'Dados Básicos',
                Row(
                    Column('numero_documento', css_class='form-group col-md-6 mb-0'),
                    Column('tipo_conta', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                'descricao',
                Row(
                    Column('data_emissao', css_class='form-group col-md-6 mb-0'),
                    Column('data_vencimento', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Valores',
                Row(
                    Column('valor_original', css_class='form-group col-md-6 mb-0'),
                    Column('valor_desconto', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                Row(
                    Column('valor_juros', css_class='form-group col-md-6 mb-0'),
                    Column('valor_multa', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Relacionamentos',
                Row(
                    Column('cliente', css_class='form-group col-md-6 mb-0'),
                    Column('venda', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                Row(
                    Column('centro_custo', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Parcelamento',
                Row(
                    Column('numero_parcela', css_class='form-group col-md-4 mb-0'),
                    Column('total_parcelas', css_class='form-group col-md-4 mb-0'),
                    Column('conta_pai', css_class='form-group col-md-4 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Observações',
                'observacoes',
            ),
            FormActions(
                Submit('submit', 'Salvar Conta', css_class='btn btn-primary'),
                HTML('<a href="{% url "financeiro:conta_receber_lista" %}" class="btn btn-secondary ml-2">Cancelar</a>')
            )
        )
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validar datas
        data_emissao = cleaned_data.get('data_emissao')
        data_vencimento = cleaned_data.get('data_vencimento')
        
        if data_emissao and data_vencimento:
            if data_vencimento < data_emissao:
                raise ValidationError('Data de vencimento não pode ser anterior à data de emissão')
        
        # Validar valores
        valor_original = cleaned_data.get('valor_original', 0)
        valor_desconto = cleaned_data.get('valor_desconto', 0)
        
        if valor_desconto > valor_original:
            raise ValidationError('Desconto não pode ser maior que o valor original')
        
        # Validar parcelamento
        numero_parcela = cleaned_data.get('numero_parcela', 1)
        total_parcelas = cleaned_data.get('total_parcelas', 1)
        
        if numero_parcela > total_parcelas:
            raise ValidationError('Número da parcela não pode ser maior que o total de parcelas')
        
        return cleaned_data

class ContaPagarForm(forms.ModelForm):
    """Formulário para Conta a Pagar"""
    
    class Meta:
        model = ContaPagar
        fields = [
            'numero_documento', 'descricao', 'tipo_conta', 'data_emissao',
            'data_vencimento', 'valor_original', 'valor_juros', 'valor_multa',
            'valor_desconto', 'fornecedor', 'centro_custo',
            'numero_parcela', 'total_parcelas', 'conta_pai', 'observacoes'
        ]
        
        widgets = {
            'data_emissao': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'data_vencimento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'valor_original': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_juros': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_multa': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'valor_desconto': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'observacoes': forms.Textarea(
                attrs={'rows': 3, 'class': 'form-control'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar querysets por empresa
        if self.empresa:
            self.fields['fornecedor'].queryset = self.empresa.fornecedores.filter(ativo=True)
            self.fields['plano_contas'].queryset = self.empresa.plano_contas.filter(
                tipo_conta='despesa', ativa=True, aceita_lancamento=True
            )
            self.fields['centro_custo'].queryset = self.empresa.centro_custos.filter(ativo=True)
        
        # Configurar crispy forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-3'
        self.helper.field_class = 'col-lg-9'
        
        self.helper.layout = Layout(
            Fieldset(
                'Dados Básicos',
                Row(
                    Column('numero_documento', css_class='form-group col-md-6 mb-0'),
                    Column('tipo_conta', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                'descricao',
                Row(
                    Column('data_emissao', css_class='form-group col-md-6 mb-0'),
                    Column('data_vencimento', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Valores',
                Row(
                    Column('valor_original', css_class='form-group col-md-6 mb-0'),
                    Column('valor_desconto', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                Row(
                    Column('valor_juros', css_class='form-group col-md-6 mb-0'),
                    Column('valor_multa', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Relacionamentos',
                'fornecedor',
                Row(
                    Column('centro_custo', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Parcelamento',
                Row(
                    Column('numero_parcela', css_class='form-group col-md-4 mb-0'),
                    Column('total_parcelas', css_class='form-group col-md-4 mb-0'),
                    Column('conta_pai', css_class='form-group col-md-4 mb-0'),
                    css_class='form-row'
                ),
            ),
            'observacoes',
            FormActions(
                Submit('submit', 'Salvar Conta', css_class='btn btn-primary'),
                HTML('<a href="{% url "financeiro:conta_pagar_lista" %}" class="btn btn-secondary ml-2">Cancelar</a>')
            )
        )


class CentroCustoForm(forms.ModelForm):
    """Formulário para Centro de Custo"""
    
    class Meta:
        model = CentroCusto
        fields = [
            'codigo', 'nome', 'descricao', 'responsavel', 'ativo', 'loja'
        ]
        
        widgets = {
            'codigo': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '20'}
            ),
            'nome': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '200'}
            ),
            'descricao': forms.Textarea(
                attrs={'rows': 3, 'class': 'form-control'}
            ),
            'responsavel': forms.Select(
                attrs={'class': 'form-control'}
            ),
            'loja': forms.Select(
                attrs={'class': 'form-control'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar querysets por empresa
        if self.empresa:
            from apps.core.models import Usuario
            self.fields['responsavel'].queryset = Usuario.objects.filter(
                empresa=self.empresa, is_active=True
            )
            self.fields['loja'].queryset = self.empresa.lojas.filter(ativa=True)
        
        # Configurar crispy forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        
        self.helper.layout = Layout(
            Row(
                Column('codigo', css_class='form-group col-md-6 mb-0'),
                Column('nome', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'descricao',
            Row(
                Column('responsavel', css_class='form-group col-md-6 mb-0'),
                Column('loja', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'ativo',
            FormActions(
                Submit('submit', 'Salvar Centro de Custo', css_class='btn btn-primary'),
                HTML('<a href="{% url "financeiro:centro_custo_lista" %}" class="btn btn-secondary ml-2">Cancelar</a>')
            )
        )
    
    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        if not codigo:
            raise ValidationError('Código é obrigatório')
        
        # Verificar se código já existe na empresa
        if self.empresa:
            existe = CentroCusto.objects.filter(
                empresa=self.empresa,
                codigo=codigo
            ).exclude(id=self.instance.id if self.instance else None).exists()
            
            if existe:
                raise ValidationError('Código já existe nesta empresa')
        
        return codigo.upper()

class MovimentoCaixaForm(forms.ModelForm):
    """Formulário para Movimento de Caixa"""
    
    class Meta:
        model = MovimentoCaixa
        fields = [
            'tipo_movimento', 'forma_pagamento', 'data_movimento',
            'valor', 'valor_troco', 'descricao', 'observacoes',
            'cliente', 'fornecedor', 'numero_documento',
            'numero_cheque', 'banco_cheque', 'emissor_cheque', 'data_cheque',
            'numero_cartao_mascarado',
            'bandeira_cartao', 'numero_autorizacao', 'numero_comprovante'
        ]
        
        widgets = {
            'data_movimento': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'data_cheque': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'}
            ),
            'valor': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01'}
            ),
            'valor_troco': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}
            ),
            'descricao': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '255'}
            ),
            'observacoes': forms.Textarea(
                attrs={'rows': 3, 'class': 'form-control'}
            ),
            'numero_documento': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '50'}
            ),
            'numero_cheque': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '20'}
            ),
            'banco_cheque': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '100'}
            ),
            'emissor_cheque': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '200'}
            ),
            'numero_cartao_mascarado': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '20', 'placeholder': '**** **** **** 1234'}
            ),
            'bandeira_cartao': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '50'}
            ),
            'numero_autorizacao': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '20'}
            ),
            'numero_comprovante': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '30'}
            ),
        }
    
    def __init__(self, *args, **kwargs):
        self.empresa = kwargs.pop('empresa', None)
        self.loja = kwargs.pop('loja', None)
        super().__init__(*args, **kwargs)
        
        # Filtrar querysets por empresa
        if self.empresa:
            self.fields['cliente'].queryset = self.empresa.clientes.filter(ativo=True)
            self.fields['fornecedor'].queryset = self.empresa.fornecedores.filter(ativo=True)
        
        # Configurar crispy forms
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-3'
        self.helper.field_class = 'col-lg-9'
        
        self.helper.layout = Layout(
            Fieldset(
                'Dados do Movimento',
                Row(
                    Column('tipo_movimento', css_class='form-group col-md-6 mb-0'),
                    Column('forma_pagamento', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                'data_movimento',
                Row(
                    Column('valor', css_class='form-group col-md-6 mb-0'),
                    Column('valor_troco', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                'descricao',
            ),
            Fieldset(
                'Relacionamentos',
                Row(
                    Column('cliente', css_class='form-group col-md-6 mb-0'),
                    Column('fornecedor', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                'numero_documento',
            ),
            Fieldset(
                'Dados do Cheque',
                Row(
                    Column('numero_cheque', css_class='form-group col-md-4 mb-0'),
                    Column('banco_cheque', css_class='form-group col-md-4 mb-0'),
                    Column('data_cheque', css_class='form-group col-md-4 mb-0'),
                    css_class='form-row'
                ),
                'emissor_cheque',
                css_class='cheque-fields'
            ),
            Fieldset(
                'Dados de Transferência',
                Row(
                    Column('txid_p', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
            ),
            Fieldset(
                'Dados do Cartão',
                Row(
                    Column('numero_cartao_mascarado', css_class='form-group col-md-6 mb-0'),
                    Column('bandeira_cartao', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                Row(
                    Column('numero_autorizacao', css_class='form-group col-md-6 mb-0'),
                    Column('numero_comprovante', css_class='form-group col-md-6 mb-0'),
                    css_class='form-row'
                ),
                css_class='cartao-fields'
            ),
            'observacoes',
            FormActions(
                Submit('submit', 'Salvar Movimento', css_class='btn btn-primary'),
                HTML('<a href="{% url "financeiro:movimento_caixa" %}" class="btn btn-secondary ml-2">Cancelar</a>')
            )
        )
        
        # JavaScript para mostrar/esconder campos baseado na forma de pagamento
        self.helper.layout.append(
            HTML("""
            <script>
            $(document).ready(function(){
                function togglePaymentFields() {
                    var formaPagamento = $('#id_forma_pagamento').val();
                    
                    $('.cheque-fields').hide();
                    $('.cartao-fields').hide();
                    
                    if (formaPagamento === 'cheque') {
                        $('.cheque-fields').show();
                    } else if (formaPagamento.includes('cartao')) {
                        $('.cartao-fields').show();
                    }
                }
                
                $('#id_forma_pagamento').change(togglePaymentFields);
                togglePaymentFields(); // Executar no carregamento
            });
            </script>
            """)
        )
    
    def clean(self):
        cleaned_data = super().clean()
        
        tipo_movimento = cleaned_data.get('tipo_movimento')
        valor = cleaned_data.get('valor', 0)
        forma_pagamento = cleaned_data.get('forma_pagamento')
        
        # Validar valor baseado no tipo de movimento
        if tipo_movimento in ['sangria', 'pagamento', 'cancelamento']:
            if valor > 0:
                # Para saídas, o valor deve ser negativo
                cleaned_data['valor'] = -abs(valor)
        else:
            # Para entradas, o valor deve ser positivo
            if valor < 0:
                cleaned_data['valor'] = abs(valor)
        
        # Validar campos específicos por forma de pagamento
        if forma_pagamento == 'cheque':
            numero_cheque = cleaned_data.get('numero_cheque')
            if not numero_cheque:
                raise ValidationError('Número do cheque é obrigatório para pagamentos em cheque')
        
        
        elif forma_pagamento in ['cartao_debito', 'cartao_credito']:
            numero_autorizacao = cleaned_data.get('numero_autorizacao')
            if not numero_autorizacao:
                raise ValidationError('Número de autorização é obrigatório para pagamentos em cartão')
        
        return cleaned_data
    
    def save(self, commit=True):
        movimento = super().save(commit=False)
        
        # Definir empresa e loja
        if self.empresa:
            movimento.empresa = self.empresa
        if self.loja:
            movimento.loja = self.loja
        
        if commit:
            movimento.save()
        
        return movimento

# Formulários de filtro
class ContaReceberFiltroForm(forms.Form):
    """Formulário de filtros para contas a receber"""
    
    STATUS_CHOICES = [('', 'Todos')] + ContaReceber.STATUS_CHOICES
    TIPO_CHOICES = [('', 'Todos')] + ContaReceber.TIPO_CONTA_CHOICES
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    tipo_conta = forms.ChoiceField(
        choices=TIPO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    data_vencimento_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    data_vencimento_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    cliente = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do cliente...'
        })
    )

class ContaPagarFiltroForm(forms.Form):
    """Formulário de filtros para contas a pagar"""
    
    STATUS_CHOICES = [('', 'Todos')] + ContaPagar.STATUS_CHOICES
    TIPO_CHOICES = [('', 'Todos')] + ContaPagar.TIPO_CONTA_CHOICES
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    tipo_conta = forms.ChoiceField(
        choices=TIPO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    data_vencimento_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    data_vencimento_fim = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    fornecedor = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nome do fornecedor...'
        })
    )

# Formulários de ação
class ReceberContaForm(forms.Form):
    """Formulário para receber conta"""
    
    valor_recebido = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )
    
    data_recebimento = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        initial=date.today
    )
    
    forma_pagamento = forms.ChoiceField(
        choices=MovimentoCaixa.FORMA_PAGAMENTO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'form-control',
            'placeholder': 'Observações sobre o recebimento...'
        })
    )

class PagarContaForm(forms.Form):
    """Formulário para pagar conta"""
    
    valor_pago = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0'
        })
    )
    
    data_pagamento = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        }),
        initial=date.today
    )
    
    forma_pagamento = forms.ChoiceField(
        choices=MovimentoCaixa.FORMA_PAGAMENTO_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    conta_bancaria = forms.ModelChoiceField(
        queryset=ContaBancaria.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    observacoes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'class': 'form-control',
            'placeholder': 'Observações sobre o pagamento...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        if empresa:
            self.fields['conta_bancaria'].queryset = ContaBancaria.objects.filter(
                empresa=empresa, ativa=True
            )


from django import forms



class ImpostoTributoForm(forms.ModelForm):
    class Meta:
        model = ImpostoTributo
        exclude = ('codigo_imposto_interno', 'valor_calculado', 'valor_devido',
                   'valor_pago', 'valor_multa', 'valor_juros', 'total_agt',
                   'movimentacao_pagamento', 'usuario_responsavel', 
                   'ultima_atualizacao_calculo', 'situacao')
        widgets = {
            'data_inicio_periodo': forms.DateInput(attrs={'type': 'date'}),
            'data_fim_periodo': forms.DateInput(attrs={'type': 'date'}),
            'data_vencimento': forms.DateInput(attrs={'type': 'date'}),
            'data_pagamento': forms.DateInput(attrs={'type': 'date'}),
        }


# forms.py
from django import forms
from .models import FluxoCaixa

class FluxoCaixaForm(forms.ModelForm):
    class Meta:
        model = FluxoCaixa
        fields = [
            'data_referencia', 'tipo', 'valor_previsto', 'valor_realizado',
            'categoria', 'descricao', 'conta_bancaria', 'centro_custo',
            'conta_pagar', 'conta_receber', 'realizado', 'observacoes'
        ]
        widgets = {
            'data_referencia': forms.DateInput(attrs={'type': 'date', 'class': 'border p-2 rounded'}),
            'tipo': forms.Select(attrs={'class': 'border p-2 rounded'}),
            'valor_previsto': forms.NumberInput(attrs={'class': 'border p-2 rounded'}),
            'valor_realizado': forms.NumberInput(attrs={'class': 'border p-2 rounded'}),
            'categoria': forms.TextInput(attrs={'class': 'border p-2 rounded'}),
            'descricao': forms.TextInput(attrs={'class': 'border p-2 rounded'}),
            'observacoes': forms.Textarea(attrs={'class': 'border p-2 rounded', 'rows': 3}),
        }


