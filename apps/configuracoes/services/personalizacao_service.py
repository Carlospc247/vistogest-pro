from apps.configuracoes.models import PersonalizacaoInterface

def get_personalizacao_empresa(empresa):
    """
    Retorna a personalização de interface mais recente para a empresa.
    Se houver mais de uma, retorna a última criada.
    """
    if not empresa:
        return None
    return PersonalizacaoInterface.objects.filter(empresa=empresa).order_by('-id').first()

def personalizacao_context(personalizacao, request=None):
    """
    Retorna um dicionário padronizado com as configurações de personalização
    para ser usado em templates de PDF.
    
    Garante fallback seguro para valores padrão caso a personalização não exista.
    """
    
    # Valores padrão (Fallback)
    context = {
        "logo": None,
        "tema": "claro",
        "cor_primaria": "#1a202c", # Cor padrão escura/profissional
        "cor_secundaria": "#64748b", # Cor secundária padrão
        "mostrar_endereco": True,
        "mostrar_banco": True,
    }

    if personalizacao:
        # Se tiver logo, tenta obter a URL absoluta ou relativa
        if personalizacao.logo_principal:
            try:
                context["logo"] = personalizacao.logo_principal.url
            except Exception:
                context["logo"] = None
        
        if personalizacao.tema:
            context["tema"] = personalizacao.tema
            
        if personalizacao.cor_primaria:
            context["cor_primaria"] = personalizacao.cor_primaria
            
        # Adicione aqui lógica para cor secundária se o modelo suportar no futuro
        # Por enquanto mantemos o padrão ou derivamos se necessário
        
        # Adicione aqui lógica para mostrar_endereco/banco se o modelo suportar no futuro
        # Por enquanto assumimos True como padrão de negócio
        
    return context
