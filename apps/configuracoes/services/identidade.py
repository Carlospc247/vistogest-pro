# apps/configuracoes/services/identidade.py
"""
Fonte única da identidade fiscal: a Empresa (public) manda.

    Empresa  ──►  ConfiguracaoFiscal (tenant)   espelho, nunca editado à mão

* Formulários: IdentidadeSomenteLeituraMixin.
* Qualquer outro caminho: ConfiguracaoFiscal.save() chama aplicar_identidade().
* Leitura: obter_config_fiscal() repõe o espelho se divergir.
"""
from django.db import transaction
from django_tenants.utils import get_public_schema_name, schema_context

from apps.empresas.services import obter_empresa_do_schema

CAMPOS_ESPELHADOS = (
    "razao_social", "nome_fantasia", "nif", "email", "telefone",
    "endereco", "cidade", "provincia", "postal", "regime_tributario",
)
_REGIME = {
    "GERAL": "geral",
    "SIMPLIFICADO": "simplificado",
    "EXCLUSAO": "exclusao",
    "ESPECIAL": "outros",
}


def campos_da_empresa(empresa) -> dict:
    partes = (empresa.endereco, empresa.numero, empresa.bairro)
    return {
        "razao_social": empresa.nome,
        "nome_fantasia": empresa.nome_fantasia,
        "nif": empresa.nif,
        "email": empresa.email,
        "telefone": empresa.telefone,
        "endereco": ", ".join(p for p in partes if p)[:255],
        "cidade": empresa.cidade,
        "provincia": empresa.get_provincia_display(),
        "postal": empresa.postal,
        "regime_tributario": _REGIME.get(empresa.regime_fiscal, "geral"),
    }


def aplicar_identidade(config) -> None:
    """Copia a identidade da Empresa do schema activo para `config` (sem gravar)."""
    for campo, valor in campos_da_empresa(obter_empresa_do_schema()).items():
        setattr(config, campo, valor)


def divergencias(config, empresa) -> dict:
    """{campo: (esperado, actual)}; vazio quando o espelho está correcto."""
    if config is None:
        return {"registo": ("existir", "em falta")}
    esperado = campos_da_empresa(empresa)
    return {c: (v, getattr(config, c)) for c, v in esperado.items() if getattr(config, c) != v}


def sincronizar_identidade(empresa):
    """Empresa -> ConfiguracaoFiscal do tenant. Idempotente."""
    from apps.configuracoes.models import ConfiguracaoFiscal

    if empresa.schema_name == get_public_schema_name():
        return None
    with schema_context(empresa.schema_name), transaction.atomic():
        config = ConfiguracaoFiscal.objects.select_for_update().order_by("pk").first()
        if divergencias(config, empresa):
            config = config or ConfiguracaoFiscal()
            for campo, valor in campos_da_empresa(empresa).items():
                setattr(config, campo, valor)
            config.save()
        return config


def obter_config_fiscal():
    """ÚNICO ponto de leitura da ConfiguracaoFiscal do schema activo."""
    from apps.configuracoes.models import ConfiguracaoFiscal

    empresa = obter_empresa_do_schema()
    config = ConfiguracaoFiscal.objects.order_by("pk").first()
    if divergencias(config, empresa):
        config = sincronizar_identidade(empresa)
    return config


class IdentidadeSomenteLeituraMixin:
    """ModelForms de ConfiguracaoFiscal: com disabled=True o POST é ignorado."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in CAMPOS_ESPELHADOS:
            if campo in self.fields:
                self.fields[campo].disabled = True
                self.fields[campo].help_text = "Gerido pela administração da plataforma."