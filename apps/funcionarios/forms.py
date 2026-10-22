# apps/funcionarios/forms.py
from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    Funcionario, Cargo, Departamento, EscalaTrabalho, Ferias, Capacitacao,
    AvaliacaoDesempenho, JornadaTrabalho, RegistroPonto, Comunicado,
)

User = get_user_model()


# ============================================================
# FUNCIONÁRIO (edição genérica)
# ============================================================

class FuncionarioForm(forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = '__all__'
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}),
            'data_admissao': forms.DateInput(attrs={'type': 'date'}),
            'data_demissao': forms.DateInput(attrs={'type': 'date'}),
            'data_fim_experiencia': forms.DateInput(attrs={'type': 'date'}),
            'foto': forms.FileInput(),
        }

    def clean_bi(self):
        bi = self.cleaned_data['bi']
        if Funcionario.objects.exclude(pk=self.instance.pk).filter(bi=bi).exists():
            raise ValidationError("BI já cadastrado para outro funcionário.")
        return bi

    def clean_data_demissao(self):
        data_demissao = self.cleaned_data.get('data_demissao')
        data_admissao = self.cleaned_data.get('data_admissao')
        if data_demissao and data_admissao and data_demissao <= data_admissao:
            raise ValidationError("Data de demissão deve ser posterior à data de admissão.")
        return data_demissao

    def clean(self):
        cleaned_data = super().clean()
        data_admissao = cleaned_data.get('data_admissao')
        periodo_experiencia = cleaned_data.get('periodo_experiencia_dias')

        if data_admissao and periodo_experiencia:
            cleaned_data['data_fim_experiencia'] = data_admissao + timedelta(days=periodo_experiencia)

        return cleaned_data


# ============================================================
# CRIAÇÃO DE FUNCIONÁRIO COM ACESSO AO SISTEMA
# ------------------------------------------------------------
# Usuario vive no schema public (SHARED_APPS) e é comum a todos os
# tenants: o username/email é único globalmente e a empresa tem de
# vir SEMPRE do tenant ativo (connection.tenant), nunca do request.user.
# ============================================================

MSG_EMAIL = "Este email não está disponível para criar acesso."


def _email_em_uso(email, excluir_pk=None):
    qs = User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email))
    if excluir_pk:
        qs = qs.exclude(pk=excluir_pk)
    return qs.exists()


def _validar_senhas(form, email=""):
    p1, p2 = form.cleaned_data.get("password1"), form.cleaned_data.get("password2")
    if p1 and p2:
        if p1 != p2:
            form.add_error("password2", "As senhas não coincidem.")
        else:
            try:
                password_validation.validate_password(p1, User(username=email, email=email))
            except ValidationError as e:
                form.add_error("password1", e)


def _criar_usuario(funcionario, email, senha, empresa):
    if empresa is None:
        raise ValueError("A empresa (tenant) é obrigatória para criar o utilizador.")
    nome = funcionario.nome_completo.split()
    user = User(
        username=email,
        email=email,
        first_name=nome[0] if nome else "",
        last_name=" ".join(nome[1:]),
        empresa=empresa,
        is_active=funcionario.ativo,
    )
    user.set_password(senha)
    user.save()
    return user


class FuncionarioCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Senha de acesso",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="O funcionário entra no sistema com o email pessoal e esta senha.",
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = Funcionario
        fields = [
            'nome_completo', 'bi', 'data_nascimento', 'sexo', 'estado_civil',
            'endereco', 'numero', 'bairro', 'cidade', 'provincia', 'postal',
            'telefone', 'whatsapp', 'email_pessoal', 'email_corporativo',
            'cargo', 'departamento', 'supervisor',
            'tipo_contrato', 'data_admissao', 'salario_atual',
            'vale_alimentacao', 'vale_transporte', 'escolaridade',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email_pessoal'].required = True   # é o login
        self.fields['cargo'].required = True           # Funcionario.save() exige cargo

    def clean_email_pessoal(self):
        email = self.cleaned_data['email_pessoal'].strip().lower()
        if _email_em_uso(email):
            raise ValidationError(MSG_EMAIL)
        return email

    def clean(self):
        cleaned = super().clean()
        _validar_senhas(self, cleaned.get("email_pessoal", ""))
        return cleaned

    def save(self, commit=True, empresa=None):
        with transaction.atomic():
            func = super().save(commit=False)
            func.usuario = _criar_usuario(
                func, self.cleaned_data['email_pessoal'],
                self.cleaned_data['password1'], empresa,
            )
            func.save()
            self.save_m2m()
        return func


class CriarAcessoForm(forms.Form):
    """Para funcionários antigos que ainda não têm utilizador."""
    email = forms.EmailField(label="Email de login")
    password1 = forms.CharField(label="Nova senha", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, funcionario=None, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.funcionario, self.empresa = funcionario, empresa
        if not self.is_bound:
            self.initial['email'] = funcionario.email_pessoal

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if _email_em_uso(email):
            raise ValidationError(MSG_EMAIL)
        return email

    def clean(self):
        cleaned = super().clean()
        _validar_senhas(self, cleaned.get("email", ""))
        return cleaned

    def save(self):
        with transaction.atomic():
            f = self.funcionario
            f.usuario = _criar_usuario(f, self.cleaned_data['email'], self.cleaned_data['password1'], self.empresa)
            f.save()
        return f


# ============================================================
# ADMISSÃO DE CANDIDATOS
# ============================================================

class AdmissaoCandidatoForm(forms.ModelForm):
    """Recolhe os dados obrigatórios de RH para converter uma candidatura em funcionário."""

    class Meta:
        model = Funcionario
        fields = [
            "nome_completo", "bi", "data_nascimento", "sexo", "estado_civil",
            "nacionalidade", "naturalidade", "endereco", "numero", "bairro",
            "cidade", "provincia", "postal", "telefone", "whatsapp",
            "email_pessoal", "email_corporativo", "cargo", "departamento",
            "supervisor", "tipo_contrato", "data_admissao", "periodo_experiencia_dias",
            "salario_atual", "vale_alimentacao", "vale_transporte", "outros_beneficios",
            "comissao_percentual", "escolaridade", "curso_formacao",
            "instituicao_ensino", "ano_conclusao", "observacoes", "observacoes_rh",
        ]
        widgets = {
            "nome_completo": forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
            "bi": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off", "maxlength": 14}),
            "data_nascimento": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "sexo": forms.Select(attrs={"class": "form-select"}),
            "estado_civil": forms.Select(attrs={"class": "form-select"}),
            "nacionalidade": forms.TextInput(attrs={"class": "form-control"}),
            "naturalidade": forms.TextInput(attrs={"class": "form-control"}),
            "endereco": forms.TextInput(attrs={"class": "form-control", "autocomplete": "street-address"}),
            "numero": forms.TextInput(attrs={"class": "form-control"}),
            "bairro": forms.TextInput(attrs={"class": "form-control"}),
            "cidade": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-level2"}),
            "provincia": forms.TextInput(attrs={"class": "form-control", "autocomplete": "address-level1"}),
            "postal": forms.TextInput(attrs={"class": "form-control", "autocomplete": "postal-code"}),
            "telefone": forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
            "whatsapp": forms.TextInput(attrs={"class": "form-control"}),
            "email_pessoal": forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
            "email_corporativo": forms.EmailInput(attrs={"class": "form-control"}),
            "cargo": forms.Select(attrs={"class": "form-select"}),
            "departamento": forms.Select(attrs={"class": "form-select"}),
            "supervisor": forms.Select(attrs={"class": "form-select"}),
            "tipo_contrato": forms.Select(attrs={"class": "form-select"}),
            "data_admissao": forms.DateInput(attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"),
            "periodo_experiencia_dias": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "salario_atual": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "vale_alimentacao": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "vale_transporte": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "outros_beneficios": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "comissao_percentual": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "escolaridade": forms.Select(attrs={"class": "form-select"}),
            "curso_formacao": forms.TextInput(attrs={"class": "form-control"}),
            "instituicao_ensino": forms.TextInput(attrs={"class": "form-control"}),
            "ano_conclusao": forms.NumberInput(attrs={"class": "form-control", "min": 1900}),
            "observacoes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "observacoes_rh": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, candidatura=None, **kwargs):
        initial = dict(kwargs.pop("initial", {}) or {})
        if candidatura is not None:
            initial.setdefault("nome_completo", candidatura.nome)
            initial.setdefault("email_pessoal", candidatura.email)
            initial.setdefault("telefone", candidatura.telefone or "")
        initial.setdefault("data_admissao", timezone.localdate())
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)

        # O save() do modelo exige cargo mesmo que o ForeignKey aceite null/blank.
        self.fields["cargo"].required = True
        self.fields["cargo"].queryset = Cargo.objects.filter(ativo=True).order_by("nivel_hierarquico", "nome")
        self.fields["cargo"].empty_label = "Seleccione um cargo"
        self.fields["departamento"].queryset = Departamento.objects.filter(ativo=True).order_by("nome")
        self.fields["departamento"].empty_label = "Seleccione um departamento"
        supervisores = Funcionario.objects.filter(ativo=True).order_by("nome_completo")
        if self.instance.pk:
            supervisores = supervisores.exclude(pk=self.instance.pk)
        self.fields["supervisor"].queryset = supervisores
        self.fields["supervisor"].required = False
        self.fields["email_pessoal"].required = True

    def clean_bi(self):
        return self.cleaned_data["bi"].strip().upper()

    def clean_email_pessoal(self):
        return self.cleaned_data["email_pessoal"].strip().lower()

    def clean(self):
        cleaned = super().clean()
        admissao = cleaned.get("data_admissao")
        nascimento = cleaned.get("data_nascimento")
        if admissao and nascimento and nascimento >= admissao:
            self.add_error("data_nascimento", "A data de nascimento deve ser anterior à data de admissão.")

        for campo in ("salario_atual", "vale_alimentacao", "vale_transporte", "outros_beneficios"):
            valor = cleaned.get(campo)
            if valor is not None and valor < Decimal("0.00"):
                self.add_error(campo, "O valor não pode ser negativo.")

        comissao = cleaned.get("comissao_percentual")
        if comissao is not None and not Decimal("0.00") <= comissao <= Decimal("100.00"):
            self.add_error("comissao_percentual", "A comissão deve estar entre 0% e 100%.")
        return cleaned


# ============================================================
# CARGO
# ============================================================

# O formulário acompanha automaticamente os campos booleanos pode_* declarados
# em Cargo (incluindo pode_gerir_senhas), evitando esquecer permissões novas.
CARGO_BOOLEAN_FIELDS = tuple(
    field.name
    for field in Cargo._meta.fields
    if isinstance(field, models.BooleanField) and field.name.startswith("pode_")
)

CARGO_BASE_FIELDS = (
    "nome", "codigo", "descricao", "cargo_superior", "nivel_hierarquico",
    "categoria", "salario_base", "vale_alimentacao", "vale_transporte",
    "limite_desconto_percentual",
)


class CargoForm(forms.ModelForm):
    selecionar_todos = forms.BooleanField(
        required=False,
        label="Seleccionar todas as permissões",
        help_text="Marca todas as permissões pode_*; se ficar desmarcado, mantém as escolhas individuais.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Cargo
        fields = list(CARGO_BASE_FIELDS) + ["permissions"] + list(CARGO_BOOLEAN_FIELDS) + ["selecionar_todos", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nome do cargo"}),
            "codigo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Código único"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Descrição do cargo"}),
            "cargo_superior": forms.Select(attrs={"class": "form-select"}),
            "nivel_hierarquico": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "salario_base": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "vale_alimentacao": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "vale_transporte": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "limite_desconto_percentual": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "permissions": forms.CheckboxSelectMultiple(),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        widgets.update({
            nome: forms.CheckboxInput(attrs={"class": "form-check-input"})
            for nome in CARGO_BOOLEAN_FIELDS
        })

    @staticmethod
    def get_boolean_fields():
        """Permissões operacionais pode_*; exclui ativo e seleccionar_todos."""
        return list(CARGO_BOOLEAN_FIELDS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        superiores = Cargo.objects.filter(ativo=True).order_by("nivel_hierarquico", "nome")
        if self.instance.pk:
            superiores = superiores.exclude(pk=self.instance.pk)
        self.fields["cargo_superior"].queryset = superiores
        # É uma acção momentânea, não um espelho do estado actualmente guardado.
        # Assim, ao editar um cargo com todas as permissões activas, o utilizador
        # ainda pode desmarcar apenas uma permissão sem que ela seja reactivada.
        self.fields["selecionar_todos"].initial = False

    def clean(self):
        cleaned = super().clean()
        nivel = cleaned.get("nivel_hierarquico")
        categoria = cleaned.get("categoria")
        selecionar_todos = bool(cleaned.get("selecionar_todos"))
        pode_descontar = selecionar_todos or bool(cleaned.get("pode_fazer_desconto", False))
        pode_aprovar_proforma = selecionar_todos or bool(cleaned.get("pode_aprovar_proforma", False))
        pode_emitir_proforma = selecionar_todos or bool(cleaned.get("pode_emitir_proforma", False))
        pode_pagar_salario = selecionar_todos or bool(cleaned.get("pode_pagar_salario", False))
        limite = cleaned.get("limite_desconto_percentual")
        limite = limite if limite is not None else Decimal("0.00")

        if nivel is not None and nivel < 1:
            self.add_error("nivel_hierarquico", "O nível hierárquico deve ser 1 ou superior.")

        if limite < Decimal("0.00") or limite > Decimal("100.00"):
            self.add_error("limite_desconto_percentual", "O limite de desconto deve estar entre 0% e 100%.")
        elif not pode_descontar and limite > Decimal("0.00"):
            self.add_error(
                "limite_desconto_percentual",
                "O limite deve ser 0% quando o cargo não tem permissão para conceder descontos.",
            )
        elif pode_descontar and limite <= Decimal("0.00"):
            self.add_error(
                "limite_desconto_percentual",
                "Defina um limite superior a 0% para um cargo autorizado a conceder descontos.",
            )

        if pode_aprovar_proforma and not pode_emitir_proforma:
            self.add_error(
                "pode_aprovar_proforma",
                "O cargo não pode aprovar proformas sem ter também permissão para as emitir.",
            )

        if pode_pagar_salario and nivel is not None and nivel > 3:
            if categoria not in {"rh", "diretoria", "gerencia"}:
                self.add_error(
                    "pode_pagar_salario",
                    "Para pagar salários, o cargo deve ser de RH, Diretoria, Gerência ou ter nível hierárquico até 3.",
                )

        for campo in ("salario_base", "vale_alimentacao", "vale_transporte"):
            valor = cleaned.get(campo)
            if valor is not None and valor < Decimal("0.00"):
                self.add_error(campo, "O valor não pode ser negativo.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("selecionar_todos"):
            for campo in self.get_boolean_fields():
                setattr(instance, campo, True)

        # Esta checkbox é um comando de interface, não uma permissão persistente.
        # O modelo tem o campo por compatibilidade; não guardamos True após salvar.
        instance.selecionar_todos = False

        if commit:
            instance.save()
            self.save_m2m()
        return instance


# ============================================================
# ESCALAS, FÉRIAS, CAPACITAÇÃO, AVALIAÇÃO, ETC.
# ============================================================

class EscalaTrabalhoForm(forms.ModelForm):
    class Meta:
        model = EscalaTrabalho
        fields = [
            'funcionario', 'data_trabalho', 'turno', 'horario_entrada', 'horario_saida',
            'horario_almoco_inicio', 'horario_almoco_fim', 'departamento',
            'funcao_dia', 'confirmada', 'trabalhada', 'observacoes', 'criada_por'
        ]
        widgets = {
            'data_trabalho': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        entrada = cleaned_data.get('horario_entrada')
        saida = cleaned_data.get('horario_saida')
        if entrada and saida and entrada >= saida:
            raise ValidationError("Horário de saída deve ser maior que horário de entrada.")
        return cleaned_data


class FeriasForm(forms.ModelForm):
    class Meta:
        model = Ferias
        fields = [
            'funcionario', 'periodo_aquisitivo_inicio', 'periodo_aquisitivo_fim',
            'data_inicio', 'data_fim', 'dias_ferias', 'adiantamento_13', 'status',
            'aprovada_por', 'data_aprovacao', 'observacoes'
        ]
        widgets = {
            'periodo_aquisitivo_inicio': forms.DateInput(attrs={'type': 'date'}),
            'periodo_aquisitivo_fim': forms.DateInput(attrs={'type': 'date'}),
            'data_inicio': forms.DateInput(attrs={'type': 'date'}),
            'data_fim': forms.DateInput(attrs={'type': 'date'}),
            'data_aprovacao': forms.DateInput(attrs={'type': 'date'}),
        }


class CapacitacaoForm(forms.ModelForm):
    class Meta:
        model = Capacitacao
        fields = [
            'funcionario', 'titulo', 'descricao', 'tipo', 'carga_horaria',
            'data_inicio', 'data_fim', 'instituicao', 'instrutor', 'local', 'modalidade',
            'valor_inscricao', 'valor_transporte', 'valor_hospedagem', 'valor_alimentacao',
            'status', 'nota_final', 'certificado', 'aprovada_por', 'observacoes'
        ]
        widgets = {
            'data_inicio': forms.DateInput(attrs={'type': 'date'}),
            'data_fim': forms.DateInput(attrs={'type': 'date'}),
            'certificado': forms.FileInput(),
        }



class AvaliacaoDesempenhoForm(forms.ModelForm):
    """O funcionário avaliado vem da URL; avaliador e data são definidos na view."""

    class Meta:
        model = AvaliacaoDesempenho
        fields = [
            'tipo_avaliacao', 'periodo_inicio', 'periodo_fim',
            'pontualidade', 'assiduidade', 'qualidade_trabalho', 'produtividade',
            'iniciativa', 'relacionamento_interpessoal', 'conhecimento_tecnico', 'lideranca',
            'pontos_fortes', 'pontos_melhorar', 'metas_objetivos', 'plano_desenvolvimento',
            'recomenda_promocao', 'recomenda_aumento', 'recomenda_capacitacao', 'observacoes',
        ]
        widgets = {
            'periodo_inicio': forms.DateInput(attrs={'type': 'date'}),
            'periodo_fim': forms.DateInput(attrs={'type': 'date'}),
            'pontos_fortes': forms.Textarea(attrs={'rows': 3}),
            'pontos_melhorar': forms.Textarea(attrs={'rows': 3}),
            'metas_objetivos': forms.Textarea(attrs={'rows': 3}),
            'plano_desenvolvimento': forms.Textarea(attrs={'rows': 3}),
            'observacoes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ('pontualidade', 'assiduidade', 'qualidade_trabalho', 'produtividade',
                     'iniciativa', 'relacionamento_interpessoal', 'conhecimento_tecnico', 'lideranca'):
            self.fields[nome].widget.attrs.update({'min': 1, 'max': 5})
            self.fields[nome].help_text = 'Nota de 1 a 5'

    def clean(self):
        cleaned = super().clean()
        ini, fim = cleaned.get('periodo_inicio'), cleaned.get('periodo_fim')
        if ini and fim and fim < ini:
            self.add_error('periodo_fim', 'O fim do período deve ser igual ou posterior ao início.')
        return cleaned


     
class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = [
            'nome',
            'codigo',
            'descricao',
            'responsavel',
            'centro_custo',
            'ativo',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do departamento'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Código único'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descrição do departamento'}),
            'responsavel': forms.Select(attrs={'class': 'form-control'}),
            'centro_custo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Centro de custo'}),
        }

    def clean_nome(self):
        nome = self.cleaned_data['nome'].strip()
        if Departamento.objects.filter(nome__iexact=nome).exists():
            raise forms.ValidationError("Já existe um departamento com este nome nesta.")
        return nome

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        if Departamento.objects.filter(codigo__iexact=codigo).exists():
            raise forms.ValidationError("Já existe um departamento com este código.")
        return codigo


class RegistroPontoForm(forms.ModelForm):
    class Meta:
        model = RegistroPonto
        fields = [
            'funcionario',
            'data_registro',
            'hora_registro',
            'tipo_registro',
            'ip_registro',
            'registro_manual',
            'justificativa',
            'aprovado_por',
            'observacoes',
        ]
        widgets = {
            'funcionario': forms.Select(attrs={'class': 'form-control'}),
            'data_registro': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hora_registro': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'tipo_registro': forms.Select(attrs={'class': 'form-control'}),
            'ip_registro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IP do registro'}),
            'registro_manual': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'justificativa': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Justificativa'}),
            'aprovado_por': forms.Select(attrs={'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Observações'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        registro_manual = cleaned_data.get('registro_manual')
        justificativa = cleaned_data.get('justificativa')

        if registro_manual and not justificativa:
            self.add_error('justificativa', "É obrigatório informar uma justificativa para registros manuais.")
        return cleaned_data


class JornadaTrabalhoForm(forms.ModelForm):
    class Meta:
        model = JornadaTrabalho
        fields = [
            'nome',
            'turno',
            'horario_entrada',
            'horario_saida',
            'horario_almoco_inicio',
            'horario_almoco_fim',
            'departamento',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da jornada'}),
            'turno': forms.Select(attrs={'class': 'form-control'}),
            'horario_entrada': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'horario_saida': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'horario_almoco_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'horario_almoco_fim': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'departamento': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        entrada = cleaned_data.get('horario_entrada')
        saida = cleaned_data.get('horario_saida')
        almoco_inicio = cleaned_data.get('horario_almoco_inicio')
        almoco_fim = cleaned_data.get('horario_almoco_fim')

        if entrada and saida and saida <= entrada:
            self.add_error('horario_saida', "O horário de saída deve ser maior que o horário de entrada.")

        if (almoco_inicio and not almoco_fim) or (almoco_fim and not almoco_inicio):
            self.add_error('horario_almoco_fim', "Ambos os horários de almoço devem ser preenchidos ou deixados em branco.")

        if almoco_inicio and almoco_fim and almoco_fim <= almoco_inicio:
            self.add_error('horario_almoco_fim', "O horário de término do almoço deve ser maior que o início.")

        return cleaned_data


class PlanejarFeriasForm(forms.ModelForm):
    class Meta:
        model = Ferias
        # Apenas os campos que o utilizador deve preencher ao planejar férias
        fields = [
            'funcionario',
            'periodo_aquisitivo_inicio',
            'periodo_aquisitivo_fim',
            'data_inicio',
            'data_fim',
            'dias_ferias',
            'adiantamento_13',
            'observacoes',
        ]
        widgets = {
            'funcionario': forms.Select(attrs={'class': 'form-select'}),
            'periodo_aquisitivo_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'periodo_aquisitivo_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'data_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'data_fim': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'dias_ferias': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'adiantamento_13': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'observacoes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        dias_ferias = cleaned_data.get('dias_ferias')

        if data_inicio and data_fim and data_inicio > data_fim:
            self.add_error('data_fim', 'A data de fim deve ser maior ou igual à data de início.')

        if dias_ferias and data_inicio and data_fim:
            total_dias = (data_fim - data_inicio).days + 1
            if dias_ferias != total_dias:
                self.add_error('dias_ferias', f'Os dias de férias ({dias_ferias}) não correspondem ao período informado ({total_dias} dias).')

        return cleaned_data


class ComunicadoForm(forms.ModelForm):
    class Meta:
        model = Comunicado
        fields = ["titulo", "mensagem"]
        widgets = {
            "titulo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Digite o título do comunicado",
            }),
            "mensagem": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Escreva a mensagem do comunicado",
            }),
        }
        labels = {
            "titulo": "Título",
            "mensagem": "Mensagem",
        }
