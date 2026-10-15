from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from .models import ConfiguracaoFiscal, BackupConfiguracao, DadosBancarios, PersonalizacaoInterface

CONTROL="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
CHECK="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"

class EstiloFormMixin:
    def aplicar_estilos(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", CHECK if isinstance(field.widget, forms.CheckboxInput) else CONTROL)

class ConfiguracaoFiscalForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=ConfiguracaoFiscal
        fields=["razao_social","nome_fantasia","nif","email","site","telefone","endereco","cidade","provincia","postal","regime_tributario","impressora_cupom"]
        widgets={"endereco":forms.TextInput(attrs={"placeholder":"Rua, número, bairro"}),"postal":forms.TextInput(attrs={"maxlength":4}),"site":forms.URLInput(attrs={"placeholder":"https://empresa.ao"}),"nif":forms.TextInput(attrs={"inputmode":"numeric"})}
        labels={"nif":"NIF (Número de Identificação Fiscal)","impressora_cupom":"Nome da impressora de talões"}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilos()
    def clean_nif(self):
        value=self.cleaned_data["nif"].strip().replace(" ","")
        if len(value)<8 or len(value)>14: raise ValidationError("Confirme o NIF; o comprimento parece inválido.")
        return value

class BackupConfiguracoesForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=BackupConfiguracao
        fields=["backup_automatico","frequencia_backup","horario_backup","dias_retencao_backup","notificar_erro","email_notificacao"]
        widgets={"horario_backup":forms.TimeInput(attrs={"type":"time"}),"dias_retencao_backup":forms.NumberInput(attrs={"min":1,"max":3650}),"email_notificacao":forms.EmailInput(attrs={"placeholder":"admin@empresa.ao"})}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilos()
    def clean(self):
        data=super().clean()
        if data.get("notificar_erro") and not data.get("email_notificacao"):
            self.add_error("email_notificacao","Indique um email se pretende receber notificações de falha.")
        return data

class PersonalizacaoInterfaceForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=PersonalizacaoInterface
        fields=["tema","cor_primaria","logo_principal"]
        widgets={"cor_primaria":forms.TextInput(attrs={"type":"color"}),"logo_principal":forms.FileInput()}
        labels={"tema":"Tema da interface","cor_primaria":"Cor principal","logo_principal":"Logótipo principal (opcional)"}
        help_texts={"logo_principal":"O logótipo será apresentado nos locais compatíveis com a personalização. Deixe vazio para manter o ficheiro actual."}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilos()
    def clean_cor_primaria(self):
        valor=self.cleaned_data["cor_primaria"]
        import re
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}",valor): raise ValidationError("Use o formato hexadecimal #RRGGBB.")
        return valor

class DadosBancariosForm(EstiloFormMixin, forms.ModelForm):
    class Meta:
        model=DadosBancarios
        fields=["nome_banco","numero_conta","iban","swift"]
        widgets={"nome_banco":forms.TextInput(attrs={"placeholder":"Nome do banco"}),"numero_conta":forms.TextInput(attrs={"placeholder":"Número da conta"}),"iban":forms.TextInput(attrs={"placeholder":"AO06004400012345678910152"}),"swift":forms.TextInput(attrs={"placeholder":"BCOMAOXXXX"})}
        labels={"nome_banco":"Nome do banco","numero_conta":"Número da conta","iban":"IBAN","swift":"SWIFT/BIC"}
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilos()
    def clean_iban(self):
        value="".join(self.cleaned_data["iban"].upper().split())
        if not 15 <= len(value) <= 34: raise ValidationError("O IBAN deve ter entre 15 e 34 caracteres.")
        return value
    def clean_swift(self):
        value=(self.cleaned_data.get("swift") or "").strip().upper()
        if value and len(value) not in (8,11): raise ValidationError("O SWIFT/BIC deve ter 8 ou 11 caracteres.")
        return value

class ContactForm(EstiloFormMixin, forms.Form):
    nome=forms.CharField(max_length=100,label="Nome completo",widget=forms.TextInput(attrs={"placeholder":"O seu nome completo"}))
    email=forms.EmailField(label="Email",widget=forms.EmailInput(attrs={"placeholder":"nome@empresa.ao"}))
    assunto=forms.CharField(max_length=150,label="Assunto",widget=forms.TextInput(attrs={"placeholder":"Como podemos ajudar?"}))
    mensagem=forms.CharField(label="Mensagem",widget=forms.Textarea(attrs={"rows":5,"placeholder":"Descreva o problema ou dúvida."}))
    def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.aplicar_estilos()
