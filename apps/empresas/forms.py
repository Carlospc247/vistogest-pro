# apps/empresas/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils.text import slugify

from .models import Empresa

Usuario = get_user_model()


class CadastroEmpresaForm(forms.Form):
    # --- Dados da Empresa ---
    nome = forms.CharField(label="Nome da Empresa", max_length=200)
    nome_fantasia = forms.CharField(label="Nome Fantasia", max_length=200, required=False)
    nif = forms.CharField(label="NIF", max_length=10)
    # 'regime' = tipo de actividade (Comércio/Serviços/Misto) — NÃO é o regime fiscal
    regime = forms.ChoiceField(label="Tipo de Actividade", choices=Empresa.REGIME_CHOICES)
    # 'regime_fiscal' = regime tributário AGT (Geral, Simplificado, Exclusão, Especial)
    regime_fiscal = forms.ChoiceField(
        label="Regime Fiscal (AGT)",
        choices=Empresa.REGIME_FISCAL_CHOICES,
        initial='GERAL',
        help_text="Regime tributário para efeitos fiscais/AGT. Aparece nos documentos e SAF-T.",
    )
    endereco = forms.CharField(label="Endereço", max_length=200)
    numero = forms.CharField(label="Número", max_length=10, required=False)
    bairro = forms.CharField(label="Bairro", max_length=100)
    cidade = forms.CharField(label="Cidade", max_length=100)
    provincia = forms.ChoiceField(label="Província", choices=Empresa._meta.get_field('provincia').choices)
    postal = forms.CharField(label="Código Postal", max_length=9)
    telefone_empresa = forms.CharField(label="Telefone da Empresa", max_length=20)
    email_empresa = forms.EmailField(label="E-mail da Empresa")

    # --- Dados do primeiro utilizador (Administrador da Empresa) ---
    admin_username = forms.CharField(label="Nome de utilizador", max_length=150)
    admin_first_name = forms.CharField(label="Primeiro Nome", max_length=150)
    admin_last_name = forms.CharField(label="Último Nome", max_length=150)
    admin_email = forms.EmailField(label="E-mail do Administrador")
    admin_password = forms.CharField(label="Senha", widget=forms.PasswordInput)
    admin_password_confirm = forms.CharField(label="Confirmar Senha", widget=forms.PasswordInput)

    def clean_nif(self):
        nif = self.cleaned_data['nif']
        if Empresa.objects.filter(nif=nif).exists():
            raise forms.ValidationError("Já existe uma empresa registada com este NIF.")
        return nif

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username']
        if Usuario.objects.filter(username=username).exists():
            raise forms.ValidationError("Este nome de utilizador já está em uso.")
        return username

    def clean_admin_email(self):
        email = self.cleaned_data['admin_email']
        if Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError("Este e-mail já está registado na plataforma.")
        return email

    def clean(self):
        cleaned = super().clean()
        pwd, pwd2 = cleaned.get('admin_password'), cleaned.get('admin_password_confirm')
        if pwd and pwd2 and pwd != pwd2:
            self.add_error('admin_password_confirm', "As senhas não coincidem.")
        return cleaned

    def gerar_schema_name(self):
        """Gera um schema_name único, verificando tanto a tabela Empresa
        quanto o PostgreSQL diretamente (defesa dupla)."""
        base = slugify(self.cleaned_data['nome']).replace('-', '_')
        schema_name = base
        contador = 1
        while Empresa.objects.filter(schema_name=schema_name).exists() or self._schema_existe_no_postgres(schema_name):
            contador += 1
            schema_name = f"{base}_{contador}"
        return schema_name

    def _schema_existe_no_postgres(self, schema_name):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                [schema_name]
            )
            return cursor.fetchone() is not None