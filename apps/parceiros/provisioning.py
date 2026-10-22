"""Bridge para o provisionador de tenants que já existe no projecto.

Não cria schemas manualmente, porque Empresa/Domain e o pipeline de provisionamento
real não foram fornecidos. Define PARTNER_TENANT_PROVISIONER para o callable existente.
Contrato do callable: provisioner(dados: dict, partner: Partner, request) -> Empresa.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.module_loading import import_string


def provisionar_tenant_para_parceiro(*, dados, partner, request):
    caminho = getattr(settings, "PARTNER_TENANT_PROVISIONER", "")
    if not caminho:
        raise ImproperlyConfigured(
            "Define PARTNER_TENANT_PROVISIONER com o caminho para o provisionador de tenants já usado pela SOTARQ."
        )
    try:
        provisioner = import_string(caminho)
    except (ImportError, AttributeError) as exc:
        raise ImproperlyConfigured(f"Provisionador de tenants inválido: {caminho}") from exc
    empresa = provisioner(dados=dados, partner=partner, request=request)
    if empresa is None or not getattr(empresa, "pk", None) or not getattr(empresa, "schema_name", None):
        raise ValidationError("O provisionador não devolveu uma Empresa/tenant válida.")
    return empresa
