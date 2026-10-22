# apps/fiscal/forms_web.py
"""Formulários web da aplicação fiscal com os nomes reais dos modelos."""
from django import forms
from django.forms import modelform_factory

from .models import DocumentoFiscal, RetencaoFonte, TaxaIVAAGT


def _model_fields(model, candidates):
    available = {
        field.name
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False) and not getattr(field, "auto_created", False)
    }
    return tuple(name for name in candidates if name in available)


class DateRangeForm(forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date", "class": "field"}),
    )
    data_fim = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date", "class": "field"}),
    )

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get("data_inicio")
        fim = cleaned.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data final não pode ser anterior à data inicial.")
        return cleaned


_TAXA_CANDIDATES = (
    "nome", "codigo_pais", "tax_type", "tax_code", "tax_percentage",
    "exemption_reason", "legislacao_referencia", "ativo",
)
TaxaIVAWebForm = modelform_factory(
    TaxaIVAAGT,
    fields=list(_model_fields(TaxaIVAAGT, _TAXA_CANDIDATES)),
    widgets={
        "nome": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
        "codigo_pais": forms.TextInput(attrs={"class": "field"}),
        "tax_type": forms.Select(attrs={"class": "field"}),
        "tax_code": forms.Select(attrs={"class": "field"}),
        "tax_percentage": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0", "max": "100"}),
        "exemption_reason": forms.Select(attrs={"class": "field"}),
        "legislacao_referencia": forms.TextInput(attrs={"class": "field"}),
        "ativo": forms.CheckboxInput(),
    },
)


# Os snapshots cliente_nome/cliente_nif/etc são preenchidos pelo modelo ao guardar
# quando existe um Cliente seleccionado. Não usar os nomes antigos nome_cliente,
# nif_cliente ou endereco_cliente, que não existem no modelo actual.
_DOCUMENT_FIELDS = (
    "tipo_documento", "cliente", "data_emissao", "data_vencimento",
    "moeda", "taxa_cambio", "comentarios",
)
_DocumentFormBase = modelform_factory(
    DocumentoFiscal,
    fields=list(_model_fields(DocumentoFiscal, _DOCUMENT_FIELDS)),
    widgets={
        "tipo_documento": forms.Select(attrs={"class": "field"}),
        "cliente": forms.Select(attrs={"class": "field"}),
        "data_emissao": forms.DateInput(attrs={"type": "date", "class": "field"}),
        "data_vencimento": forms.DateInput(attrs={"type": "date", "class": "field"}),
        "moeda": forms.TextInput(attrs={"class": "field", "maxlength": "3"}),
        "taxa_cambio": forms.NumberInput(attrs={"class": "field", "step": "0.000001", "min": "0.000001"}),
        "comentarios": forms.Textarea(attrs={"class": "field", "rows": 3}),
    },
)


class DocumentoFiscalWebForm(_DocumentFormBase):
    """Formulário de dados comerciais; numeração/ATCUD e criador são geridos no servidor."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " field").strip()


_RETENCAO_CANDIDATES = (
    "fornecedor", "conta_pagar", "referencia_documento", "data_retencao",
    "valor_base", "taxa_retencao", "tipo_retencao", "codigo_tributario",
    "paga_ao_estado",
)
_RETENCAO_FIELDS = _model_fields(RetencaoFonte, _RETENCAO_CANDIDATES)
RetencaoFonteWebForm = modelform_factory(
    RetencaoFonte,
    fields=list(_RETENCAO_FIELDS),
    widgets={
        "data_retencao": forms.DateInput(attrs={"type": "date", "class": "field"}),
        "valor_base": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0.01"}),
        "taxa_retencao": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0", "max": "100"}),
        "tipo_retencao": forms.Select(attrs={"class": "field"}),
        "codigo_tributario": forms.TextInput(attrs={"class": "field"}),
        "fornecedor": forms.Select(attrs={"class": "field"}),
        "conta_pagar": forms.Select(attrs={"class": "field"}),
        "referencia_documento": forms.TextInput(attrs={"class": "field"}),
        "paga_ao_estado": forms.CheckboxInput(),
    },
)
