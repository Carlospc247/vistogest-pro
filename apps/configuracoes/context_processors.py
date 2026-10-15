from django_tenants.utils import get_public_schema_name
from .models import PersonalizacaoInterface

def interface_prefs(request):
    """Disponibiliza as preferências do utilizador ao base.html sem expor dados entre tenants."""
    default = {"tema": "light", "cor_primaria": "#5D5CDE", "logo_principal": None}
    tenant = getattr(request, "tenant", None)
    user = getattr(request, "user", None)
    if not tenant or getattr(tenant, "schema_name", get_public_schema_name()) == get_public_schema_name():
        return {"interface_prefs": default}
    if not user or not getattr(user, "is_authenticated", False):
        return {"interface_prefs": default}
    try:
        pref = PersonalizacaoInterface.objects.filter(usuario=user).order_by("-pk").first()
        if pref is None:
            pref = PersonalizacaoInterface.objects.filter(usuario__isnull=True).order_by("-pk").first()
        if pref:
            themes = {"claro": "light", "escuro": "dark", "auto": "auto"}
            default["tema"] = themes.get(pref.tema, "light")
            default["cor_primaria"] = pref.cor_primaria or default["cor_primaria"]
            try:
                default["logo_principal"] = pref.logo_principal.url if pref.logo_principal else None
            except Exception:
                default["logo_principal"] = None
    except Exception:
        # Fallback para páginas públicas/migrações ou tabelas ainda não criadas.
        pass
    return {"interface_prefs": default}
