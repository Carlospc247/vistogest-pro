# apps/clientes/forms.py
from django import forms
from .models import (
    Ponto,
    Cliente,
    CategoriaCliente,
    EnderecoCliente,
    ContatoCliente,
    HistoricoCliente,
    CartaoFidelidade,
    MovimentacaoFidelidade,
    PreferenciaCliente,
    TelefoneCliente,
    GrupoCliente,
    ProgramaFidelidade,
    ModeloContrato,
)




form_field_classes = (
    "block w-full rounded-lg border-gray-300 bg-gray-50 py-2 px-3 text-gray-800 "
    "shadow-sm transition duration-200 ease-in-out "
    "focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 "
    "dark:bg-gray-700 dark:border-gray-600 dark:text-white dark:placeholder-gray-400 "
    "dark:focus:ring-blue-500/50 dark:focus:border-blue-500"
)

checkbox_classes = (
    "h-4 w-4 rounded border-gray-300 bg-gray-100 text-blue-600 "
    "focus:ring-blue-500 focus:ring-offset-0 "
    "dark:bg-gray-600 dark:border-gray-500"
)


# ===============================
# BASE PARA APLICAR ESTILO
# ===============================
class StyledModelForm(forms.ModelForm):
    """
    Classe base para aplicar automaticamente estilos Tailwind em todos os campos.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.update({'class': checkbox_classes})
            elif isinstance(widget, (forms.TextInput, forms.NumberInput, forms.EmailInput,
                                     forms.URLInput, forms.PasswordInput, forms.Textarea,
                                     forms.Select, forms.DateInput, forms.DateTimeInput,
                                     forms.TimeInput, forms.ClearableFileInput)):
                widget.attrs.update({'class': form_field_classes})


# -------------------------
# CLIENTE
# -------------------------
class ClienteForm(forms.ModelForm):
    """
    Formulário para o modelo Cliente.
    Utiliza ModelForm para gerar campos automaticamente e herdar validações.
    """
    class Meta:
        model = Cliente
        fields = '__all__'
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
            'observacoes_internas': forms.Textarea(attrs={'rows': 3}),
        }

# -------------------------
# PONTO
# -------------------------
class PontoForm(StyledModelForm):
    """Formulário para o modelo Ponto."""
    class Meta:
        model = Ponto
        fields = '__all__'

# -------------------------
# CATEGORIA CLIENTE
# -------------------------
class CategoriaClienteForm(StyledModelForm):
    """Formulário para o modelo CategoriaCliente."""
    class Meta:
        model = CategoriaCliente
        fields = '__all__'

# -------------------------
# ENDEREÇO CLIENTE
# -------------------------
class EnderecoClienteForm(StyledModelForm):
    """Formulário para o modelo EnderecoCliente."""
    class Meta:
        model = EnderecoCliente
        fields = '__all__'

# -------------------------
# CONTATO CLIENTE
# -------------------------
class ContatoClienteForm(StyledModelForm):
    """Formulário para o modelo ContatoCliente."""
    class Meta:
        model = ContatoCliente
        fields = '__all__'

# -------------------------
# HISTORICO CLIENTE
# -------------------------
class HistoricoClienteForm(StyledModelForm):
    """Formulário para o modelo HistoricoCliente."""
    class Meta:
        model = HistoricoCliente
        fields = '__all__'
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'resolucao': forms.Textarea(attrs={'rows': 3}),
            'data_interacao': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'data_resolucao': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

# -------------------------
# CARTÃO FIDELIDADE
# -------------------------
class CartaoFidelidadeForm(StyledModelForm):
    """Formulário para o modelo CartaoFidelidade."""
    class Meta:
        model = CartaoFidelidade
        fields = '__all__'
        widgets = {
            'data_ativacao': forms.DateInput(attrs={'type': 'date'}),
            'data_ultima_movimentacao': forms.DateInput(attrs={'type': 'date'}),
            'data_proximo_nivel': forms.DateInput(attrs={'type': 'date'}),
        }

# -------------------------
# MOVIMENTAÇÃO FIDELIDADE
# -------------------------
class MovimentacaoFidelidadeForm(StyledModelForm):
    """Formulário para o modelo MovimentacaoFidelidade."""
    class Meta:
        model = MovimentacaoFidelidade
        fields = '__all__'
        widgets = {
            'data_movimentacao': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

# -------------------------
# PREFERENCIA CLIENTE
# -------------------------
class PreferenciaClienteForm(StyledModelForm):
    """Formulário para o modelo PreferenciaCliente."""
    class Meta:
        model = PreferenciaCliente
        fields = '__all__'

# -------------------------
# TELEFONE CLIENTE
# -------------------------
class TelefoneClienteForm(StyledModelForm):
    """Formulário para o modelo TelefoneCliente."""
    class Meta:
        model = TelefoneCliente
        fields = '__all__'

# -------------------------
# GRUPO CLIENTE
# -------------------------
class GrupoClienteForm(StyledModelForm):
    """Formulário para o modelo GrupoCliente."""
    class Meta:
        model = GrupoCliente
        fields = '__all__'

# -------------------------
# PROGRAMA FIDELIDADE
# -------------------------
class ProgramaFidelidadeForm(StyledModelForm):
    """Formulário para o modelo ProgramaFidelidade."""
    class Meta:
        model = ProgramaFidelidade
        fields = '__all__'
        widgets = {
            'data_entrada': forms.DateInput(attrs={'type': 'date'}),
        }


####################
# Forms de Contrato
####################


class ModeloContratoForm(forms.ModelForm):
    class Meta:
        model = ModeloContrato
        fields = ["nome", "conteudo", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "w-full rounded border px-3 py-2"}),
            "conteudo": forms.Textarea(attrs={"class": "w-full rounded border px-3 py-2 font-mono", "rows": 12}),
            "ativo": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }


class EnviarContratoForm(forms.Form):
    cliente_id = forms.IntegerField(widget=forms.HiddenInput())
    nome = forms.CharField(max_length=160, required=False)
    conteudo = forms.CharField(widget=forms.Textarea(attrs={"rows": 14, "class": "w-full rounded border p-3"}))

