from django.conf import settings
from .models import PersonalizacaoInterface

def get_personalizacao(tenant=None, usuario=None):
    """Obtém personalização do usuário no schema actualmente activo; fallback para configuração global."""
    if usuario is not None:
        propria=PersonalizacaoInterface.objects.filter(usuario=usuario).order_by("-pk").first()
        if propria: return propria
    return PersonalizacaoInterface.objects.filter(usuario__isnull=True).order_by("-pk").first()

def personalizacao_context(personalizacao=None, request=None):
    if personalizacao is None and request is not None:
        personalizacao=get_personalizacao(usuario=getattr(request,"user",None))
    context={"logo":None,"tema":"claro","cor_primaria":"#1a202c","cor_secundaria":"#64748b","mostrar_endereco":True,"mostrar_banco":True}
    if personalizacao:
        try: context["logo"]=personalizacao.logo_principal.url if personalizacao.logo_principal else None
        except Exception: context["logo"]=None
        context["tema"]=personalizacao.tema or context["tema"]
        context["cor_primaria"]=personalizacao.cor_primaria or context["cor_primaria"]
    return context
