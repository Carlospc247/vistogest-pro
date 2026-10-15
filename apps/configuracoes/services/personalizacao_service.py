# apps/configuracoes/services/personalizacao_service.py
from django_tenants.utils import schema_context
from apps.configuracoes.models import PersonalizacaoInterface


def get_personalizacao(tenant=None):
    """
    Retorna a personalização de interface mais recente para o tenant ativo (ou especificado).
    """
    if tenant:
        with schema_context(tenant.schema_name):
            return PersonalizacaoInterface.objects.order_by('-id').first()

    return PersonalizacaoInterface.objects.order_by('-id').first()


def personalizacao_context(personalizacao=None, request=None):
    """
    Retorna um dicionário padronizado com as configurações de personalização
    para ser usado em templates de PDF ou contextos de página.
    
    Garante fallback seguro para valores padrão caso a personalização não exista.
    """
    # Se nenhuma personalização for fornecida explicitamente, obtém a do tenant atual
    if personalizacao is None:
        personalizacao = get_personalizacao()
    
    # Valores padrão (Fallback)
    context = {
        "logo": None,
        "tema": "claro",
        "cor_primaria": "#1a202c",   # Cor padrão escura/profissional
        "cor_secundaria": "#64748b", # Cor secundária padrão
        "mostrar_endereco": True,
        "mostrar_banco": True,
    }

    if personalizacao:
        # Se tiver logo, tenta obter a URL
        if getattr(personalizacao, 'logo_principal', None):
            try:
                context["logo"] = personalizacao.logo_principal.url
            except Exception:
                context["logo"] = None
        
        if getattr(personalizacao, 'tema', None):
            context["tema"] = personalizacao.tema
            
        if getattr(personalizacao, 'cor_primaria', None):
            context["cor_primaria"] = personalizacao.cor_primaria
            
    return context
