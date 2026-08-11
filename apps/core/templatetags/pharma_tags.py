# apps/core/templatetags/pharma_tags.py
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from decimal import Decimal
import json

register = template.Library()

@register.filter
def currency(value):
    """Formata valor como moeda brasileira"""
    if value is None:
        return "AO 0,00"
    
    try:
        value = float(value)
        return f"AO {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return "AO 0,00"

@register.filter
def percentage(value, decimal_places=2):
    """Formata valor como percentual"""
    if value is None:
        return "0%"
    
    try:
        value = float(value)
        return f"{value:.{decimal_places}f}%"
    except (ValueError, TypeError):
        return "0%"

@register.filter
def bi_nif_format(value):
    """Formata BI ou NIF"""
    if not value:
        return ""
    
    # Remove caracteres não numéricos
    numbers = ''.join(filter(str.isdigit, str(value)))
    
    if len(numbers) == 11:  # BI
        return f"{numbers[:3]}.{numbers[3:6]}.{numbers[6:9]}-{numbers[9:]}"
    elif len(numbers) == 14:  # NIF
        return f"{numbers[:2]}.{numbers[2:5]}.{numbers[5:8]}/{numbers[8:12]}-{numbers[12:]}"
    else:
        return value

@register.filter
def phone_format(value):
    """Formata número de telefone"""
    if not value:
        return ""
    
    # Remove caracteres não numéricos
    numbers = ''.join(filter(str.isdigit, str(value)))
    
    if len(numbers) == 10:  # Telefone fixo
        return f"({numbers[:2]}) {numbers[2:6]}-{numbers[6:]}"
    elif len(numbers) == 11:  # Celular
        return f"({numbers[:2]}) {numbers[2:7]}-{numbers[7:]}"
    else:
        return value

@register.filter
def postal_format(value):
    """Formata Postal"""
    if not value:
        return ""
    
    numbers = ''.join(filter(str.isdigit, str(value)))
    
    if len(numbers) == 8:
        return f"{numbers[:5]}-{numbers[5:]}"
    else:
        return value

@register.filter
def status_badge(value):
    """Retorna badge HTML baseado no status"""
    if not value:
        return ""
    
    status_classes = {
        'ativo': 'badge badge-success',
        'inativo': 'badge badge-secondary',
        'pendente': 'badge badge-warning',
        'aprovado': 'badge badge-success',
        'rejeitado': 'badge badge-danger',
        'cancelado': 'badge badge-danger',
        'finalizado': 'badge badge-primary',
        'em_andamento': 'badge badge-info',
        'agendado': 'badge badge-warning',
        'concluido': 'badge badge-success',
    }
    
    css_class = status_classes.get(value.lower(), 'badge badge-secondary')
    return mark_safe(f'<span class="{css_class}">{value.title()}</span>')

@register.filter
def priority_badge(value):
    """Retorna badge de prioridade"""
    if not value:
        return ""
    
    priority_classes = {
        'baixa': 'badge badge-success',
        'media': 'badge badge-warning',
        'alta': 'badge badge-danger',
        'critica': 'badge badge-dark',
    }
    
    css_class = priority_classes.get(value.lower(), 'badge badge-secondary')
    return mark_safe(f'<span class="{css_class}">{value.title()}</span>')

@register.filter
def gravidade_badge(value):
    """Retorna badge de gravidade para farmacovigilância"""
    if not value:
        return ""
    
    gravidade_classes = {
        'leve': 'badge badge-success',
        'moderada': 'badge badge-warning',
        'grave': 'badge badge-danger',
        'severa': 'badge badge-dark',
        'fatal': 'badge badge-dark text-white',
    }
    
    css_class = gravidade_classes.get(value.lower(), 'badge badge-secondary')
    return mark_safe(f'<span class="{css_class}">{value.title()}</span>')

@register.filter
def json_script_filter(value):
    """Converte valor para JSON para uso em JavaScript"""
    return mark_safe(json.dumps(value))

@register.filter
def get_item(dictionary, key):
    """Obtém item de dicionário por chave"""
    return dictionary.get(key)

@register.filter
def multiply(value, arg):
    """Multiplica dois valores"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def subtract(value, arg):
    """Subtrai dois valores"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide dois valores"""
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def days_until(date_value):
    """Calcula dias até uma data"""
    if not date_value:
        return 0
    
    from datetime import date
    from django.utils import timezone
    
    if hasattr(date_value, 'date'):
        date_value = date_value.date()
    
    today = timezone.now().date() if hasattr(timezone.now(), 'date') else date.today()
    
    try:
        delta = date_value - today
        return delta.days
    except (ValueError, TypeError):
        return 0

@register.filter
def days_since(date_value):
    """Calcula dias desde uma data"""
    if not date_value:
        return 0
    
    from datetime import date
    from django.utils import timezone
    
    if hasattr(date_value, 'date'):
        date_value = date_value.date()
    
    today = timezone.now().date() if hasattr(timezone.now(), 'date') else date.today()
    
    try:
        delta = today - date_value
        return delta.days
    except (ValueError, TypeError):
        return 0

@register.filter
def age_from_birth(birth_date):
    """Calcula idade a partir da data de nascimento"""
    if not birth_date:
        return 0
    
    from datetime import date
    
    if hasattr(birth_date, 'date'):
        birth_date = birth_date.date()
    
    today = date.today()
    
    try:
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )
    except (ValueError, TypeError):
        return 0

@register.simple_tag
def progress_bar(value, max_value=100, css_class="progress-bar-success"):
    """Cria uma barra de progresso"""
    try:
        percentage = (float(value) / float(max_value)) * 100
        percentage = min(100, max(0, percentage))  # Limitar entre 0 e 100
        
        return format_html(
            '<div class="progress"><div class="progress-bar {}" style="width: {:.1f}%">{:.1f}%</div></div>',
            css_class,
            percentage,
            percentage
        )
    except (ValueError, TypeError, ZeroDivisionError):
        return format_html('<div class="progress"><div class="progress-bar" style="width: 0%">0%</div></div>')

@register.simple_tag
def alert_box(message, alert_type="info"):
    """Cria uma caixa de alerta"""
    return format_html(
        '<div class="alert alert-{} alert-dismissible fade show" role="alert">'
        '{}'
        '<button type="button" class="close" data-dismiss="alert" aria-label="Close">'
        '<span aria-hidden="true">&times;</span>'
        '</button>'
        '</div>',
        alert_type,
        message
    )

@register.simple_tag
def icon(name, css_class=""):
    """Cria um ícone FontAwesome"""
    return format_html('<i class="fas fa-{} {}"></i>', name, css_class)

@register.inclusion_tag('core/templatetags/pagination.html')
def render_pagination(page_obj, request):
    """Renderiza paginação"""
    return {
        'page_obj': page_obj,
        'request': request,
    }

@register.inclusion_tag('core/templatetags/breadcrumb.html')
def render_breadcrumb(items):
    """Renderiza breadcrumb"""
    return {'items': items}

@register.filter
def verbose_name(obj, field_name):
    """Retorna o verbose_name de um campo do model"""
    try:
        return obj._meta.get_field(field_name).verbose_name
    except:
        return field_name

@register.filter
def model_name(obj):
    """Retorna o nome do model"""
    return obj._meta.model_name

@register.filter
def app_label(obj):
    """Retorna o label da app"""
    return obj._meta.app_label

@register.filter
def has_perm(user, perm):
    """Verifica se usuário tem permissão"""
    return user.has_perm(perm)

@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
    """Substitui parâmetros na URL atual"""
    request = context['request']
    params = request.GET.copy()
    
    for key, value in kwargs.items():
        if value is not None:
            params[key] = value
        elif key in params:
            del params[key]
    
    return f"?{params.urlencode()}"

@register.filter
def times(number):
    """Retorna range para usar em template"""
    try:
        return range(int(number))
    except (ValueError, TypeError):
        return range(0)

@register.filter
def startswith(text, starts):
    """Verifica se texto começa com string"""
    if not text or not starts:
        return False
    return str(text).startswith(str(starts))

@register.filter
def endswith(text, ends):
    """Verifica se texto termina com string"""
    if not text or not ends:
        return False
    return str(text).endswith(str(ends))

@register.filter
def contains(text, substring):
    """Verifica se texto contém substring"""
    if not text or not substring:
        return False
    return str(substring) in str(text)