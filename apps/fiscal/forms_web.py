"""Formulários da interface web fiscal.

Este módulo evita referenciar campos que não existam na versão instalada dos
modelos. Os campos canónicos documentados são preferidos e os campos geridos
pelo servidor (hash, contador, timestamps e totais calculados) ficam de fora.
"""
from django import forms
from django.forms import modelform_factory

from .models import DocumentoFiscal, RetencaoFonte, TaxaIVAAGT


def _model_fields(model, candidates):
    available = {field.name for field in model._meta.get_fields() if getattr(field, "concrete", False)}
    return tuple(name for name in candidates if name in available)


class DateRangeForm(forms.Form):
    data_inicio = forms.DateField(
        label="Data inicial", widget=forms.DateInput(attrs={"type": "date"}),
    )
    data_fim = forms.DateField(
        label="Data final", widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self):
        cleaned = super().clean()
        inicio, fim = cleaned.get("data_inicio"), cleaned.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data final não pode ser anterior à data inicial.")
        return cleaned


_TAXA_CANDIDATES = (
    "nome", "codigo_pais", "tax_type", "tax_code", "tax_percentage",
    "exemption_reason", "ativo",
)
TaxaIVAWebForm = modelform_factory(
    TaxaIVAAGT,
    fields=list(_model_fields(TaxaIVAAGT, _TAXA_CANDIDATES)),
    widgets={
        "nome": forms.TextInput(attrs={"class": "field", "autocomplete": "off"}),
        "codigo_pais": forms.TextInput(attrs={"class": "field"}),
        "tax_type": forms.Select(attrs={"class": "field"}),
        "tax_code": forms.Select(attrs={"class": "field"}),
        "tax_percentage": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0"}),
        "exemption_reason": forms.Select(attrs={"class": "field"}),
        "ativo": forms.CheckboxInput(),
    },
)

_DOCUMENT_FIELDS = (
    "tipo_documento", "cliente", "nome_cliente", "nif_cliente", "endereco_cliente",
    "data_emissao", "data_vencimento", "moeda", "taxa_cambio", "origem", "comentarios",
)
_DocumentFormBase = modelform_factory(
    DocumentoFiscal,
    fields=list(_model_fields(DocumentoFiscal, _DOCUMENT_FIELDS)),
)


class DocumentoFiscalWebForm(_DocumentFormBase):
    """Formulário de criação/edição de dados básicos do documento.

    A emissão, numeração, hash, assinatura e transições de estado permanecem
    responsabilidade do modelo/serviço fiscal; não são campos editáveis aqui.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " field").strip()


_RETENCAO_CANDIDATES = (
    "fornecedor", "conta_pagar", "referencia_documento", "documento_referencia",
    "data_retencao", "valor_base", "taxa_retencao", "percentual",
    "tipo_retencao", "codigo_imposto", "paga_ao_estado",
)
_RETENCAO_FIELDS = _model_fields(RetencaoFonte, _RETENCAO_CANDIDATES)
# A FK para o fornecedor é obrigatória no modelo conhecido; mantém-se fallback
# defensivo para projectos onde o nome do campo tenha sido personalizado.
if not _RETENCAO_FIELDS:
    _RETENCAO_FIELDS = tuple(
        field.name for field in RetencaoFonte._meta.fields
        if field.name not in {"id", "created_at", "updated_at", "valor_retido"}
    )
RetencaoFonteWebForm = modelform_factory(
    RetencaoFonte,
    fields=list(_RETENCAO_FIELDS),
    widgets={
        "data_retencao": forms.DateInput(attrs={"type": "date", "class": "field"}),
        "valor_base": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0"}),
        "taxa_retencao": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0"}),
        "percentual": forms.NumberInput(attrs={"class": "field", "step": "0.01", "min": "0"}),
        "tipo_retencao": forms.Select(attrs={"class": "field"}),
        "codigo_imposto": forms.Select(attrs={"class": "field"}),
        "fornecedor": forms.Select(attrs={"class": "field"}),
        "conta_pagar": forms.Select(attrs={"class": "field"}),
        "referencia_documento": forms.TextInput(attrs={"class": "field"}),
        "documento_referencia": forms.TextInput(attrs={"class": "field"}),
        "paga_ao_estado": forms.CheckboxInput(),
    },
)
