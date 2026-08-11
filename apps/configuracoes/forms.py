from django import forms
from .models import ConfiguracaoFiscal, BackupConfiguracao, DadosBancarios, PersonalizacaoInterface


class ConfiguracaoFiscalForm(forms.ModelForm):
    """
    Formulário para editar as configurações fiscais da empresa.
    """
    class Meta:
        model = ConfiguracaoFiscal
        exclude = []
        
        # Widgets para aplicar classes CSS e tipos de input adequados
        widgets = {
            'razao_social': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: vistoGEST (SU), LDA'}),
            'nome_fantasia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Campo opcional'}),
            'nif': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 5001304461'}),
            'site': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: empresa.com'}),
            'email': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: empresa@gmail.com'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contacto da empresa'}),
            'endereco': forms.TextInput(attrs={'class': 'form-control'}),
            'cidade': forms.TextInput(attrs={'class': 'form-control'}),
            'provincia': forms.TextInput(attrs={'class': 'form-control'}),
            'regime_tributario': forms.Select(attrs={'class': 'form-select'}),
            'impressora_cupom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: POS-80'}),
        }
        labels = {
            'nif': "NIF (Número de Identificação Fiscal)",
            'impressora_cupom': "Nome da Impressora de Talões",
        }
        help_texts = {
            'nif': "O NIF deve ser válido e corresponder ao da sua empresa.",
        }


class BackupConfiguracoesForm(forms.ModelForm):
    """
    Formulário para editar as configurações de backup da empresa.
    """
    class Meta:
        model = BackupConfiguracao
        # Excluímos campos geridos automaticamente pelo sistema
        exclude = ['ultimo_backup', 'status_ultimo_backup']
        
        widgets = {
            'backup_automatico': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'frequencia_backup': forms.Select(attrs={'class': 'form-select'}),
            'horario_backup': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'dias_retencao_backup': forms.NumberInput(attrs={'class': 'form-control'}),
            'notificar_erro': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'email_notificacao': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'admin@suaempresa.com'}),
        }
        labels = {
            'dias_retencao_backup': "Reter backups por (dias)",
            'email_notificacao': "Email para receber alertas de erro",
        }


class PersonalizacaoInterfaceForm(forms.ModelForm):
    """
    Formulário para que o utilizador possa personalizar a aparência do sistema.
    """
    class Meta:
        model = PersonalizacaoInterface
        # Excluímos os campos de escopo, que são definidos pela view
        exclude = ['usuario']
        
        widgets = {
            'tema': forms.Select(attrs={'class': 'form-select'}),
            'cor_primaria': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'logo_principal': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'tema': "Tema da Interface",
            'cor_primaria': "Cor Principal",
            'logo_principal': "Logótipo Principal (Opcional)",
        }
        help_texts = {
            'logo_principal': "O seu logótipo aparecerá no topo da navegação. Deixe em branco para usar o padrão.",
        }



class ContactForm(forms.Form):
    nome = forms.CharField(
        max_length=100,
        required=True,
        label="Nome Completo",
        widget=forms.TextInput(attrs={'placeholder': 'O seu nome completo'})
    )
    email = forms.EmailField(
        required=True,
        label="O seu Email",
        widget=forms.EmailInput(attrs={'placeholder': 'exemplo@email.com'})
    )
    assunto = forms.CharField(
        max_length=150,
        required=True,
        label="Assunto",
        widget=forms.TextInput(attrs={'placeholder': 'Sobre o que precisa de ajuda?'})
    )
    mensagem = forms.CharField(
        required=True,
        label="Mensagem",
        widget=forms.Textarea(attrs={'rows': 5, 'placeholder': 'Descreva o seu problema ou dúvida em detalhe...'})
    )



class DadosBancariosForm(forms.ModelForm):
    """
    Formulário para a criação e edição de dados bancários da empresa.
    """
    class Meta:
        model = DadosBancarios
        fields = [
            'nome_banco', 
            'numero_conta', 
            'iban', 
            'swift'
        ]
        widgets = {
            'nome_banco': forms.TextInput(attrs={
                'class': 'form-control block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50',
                'placeholder': 'Nome do Banco',
            }),
            'numero_conta': forms.TextInput(attrs={
                'class': 'form-control block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50',
                'placeholder': 'Número da Conta',
            }),
            'iban': forms.TextInput(attrs={
                'class': 'form-control block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50',
                'placeholder': 'AO06004400012345678910152',
            }),
            'swift': forms.TextInput(attrs={
                'class': 'form-control block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50',
                'placeholder': 'BCOMAOXXXX',
            }),
        }
        labels = {
            'nome_banco': 'Nome do Banco',
            'numero_conta': 'Número da Conta',
            'iban': 'IBAN',
            'swift': 'SWIFT/BIC',
        }


