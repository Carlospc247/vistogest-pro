# apps/core/templatetags/pharma_tags.py
# register = template.Library() aparece UMA SÓ VEZ (linha 9).
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.urls import reverse, NoReverseMatch
from decimal import Decimal
import json

register = template.Library()


# ─────────────────────────────────────────────────────────────────────────────
# safe_url — URL reverso que nunca quebra o template
#
# Uso: {% load pharma_tags %}
#      <a href="{% safe_url 'vendas:pdv' %}">PDV</a>
#      {% safe_url 'funcionarios:perfil' user.funcionario.pk %}
#      {% safe_url 'vendas:pdv' as PDV_URL %}
#
# Retorna '#' silenciosamente quando o namespace não está registado.
# ─────────────────────────────────────────────────────────────────────────────

class _SafeURLNode(template.Node):
    def __init__(self, view_name, args, kwargs, asvar):
        self.view_name = view_name
        self.args      = args
        self.kwargs    = kwargs
        self.asvar     = asvar

    def render(self, context):
        view_name = self.view_name.resolve(context)
        args      = [a.resolve(context) for a in self.args]
        kwargs    = {k: v.resolve(context) for k, v in self.kwargs.items()}
        try:
            url = reverse(view_name, args=args or None, kwargs=kwargs or None)
        except (NoReverseMatch, Exception):
            url = '#'
        if self.asvar:
            context[self.asvar] = url
            return ''
        return url


@register.tag('safe_url')
def safe_url_tag(parser, token):
    """
    {% safe_url 'namespace:name' [args] [key=val] [as varname] %}
    Retorna '#' silenciosamente se o namespace não estiver registado.
    """
    bits      = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(
            f"'{bits[0]}' requires at least one argument."
        )
    view_name = parser.compile_filter(bits[1])
    args, kwargs, asvar = [], {}, None
    remaining = bits[2:]
    if len(remaining) >= 2 and remaining[-2] == 'as':
        asvar, remaining = remaining[-1], remaining[:-2]
    for bit in remaining:
        if '=' in bit:
            k, v = bit.split('=', 1)
            kwargs[k] = parser.compile_filter(v)
        else:
            args.append(parser.compile_filter(bit))
    return _SafeURLNode(view_name, args, kwargs, asvar)


# ─────────────────────────────────────────────────────────────────────────────
# Filtros de formatação
# ─────────────────────────────────────────────────────────────────────────────

@register.filter
def currency(value):
    """Formata valor como moeda Angolana"""
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
    numbers = ''.join(filter(str.isdigit, str(value)))
    if len(numbers) == 11:
        return f"{numbers[:3]}.{numbers[3:6]}.{numbers[6:9]}-{numbers[9:]}"
    elif len(numbers) == 14:
        return f"{numbers[:2]}.{numbers[2:5]}.{numbers[5:8]}/{numbers[8:12]}-{numbers[12:]}"
    return value


@register.filter
def phone_format(value):
    """Formata número de telefone"""
    if not value:
        return ""
    numbers = ''.join(filter(str.isdigit, str(value)))
    if len(numbers) == 10:
        return f"({numbers[:2]}) {numbers[2:6]}-{numbers[6:]}"
    elif len(numbers) == 11:
        return f"({numbers[:2]}) {numbers[2:7]}-{numbers[7:]}"
    return value


@register.filter
def postal_format(value):
    """Formata Postal"""
    if not value:
        return ""
    numbers = ''.join(filter(str.isdigit, str(value)))
    if len(numbers) == 8:
        return f"{numbers[:5]}-{numbers[5:]}"
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
    """Retorna badge de gravidade"""
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
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
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
    from django.utils import timezone
    if hasattr(date_value, 'date'):
        date_value = date_value.date()
    try:
        return (date_value - timezone.now().date()).days
    except (ValueError, TypeError):
        return 0


@register.filter
def days_since(date_value):
    """Calcula dias desde uma data"""
    if not date_value:
        return 0
    from django.utils import timezone
    if hasattr(date_value, 'date'):
        date_value = date_value.date()
    try:
        return (timezone.now().date() - date_value).days
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
        pct = min(100, max(0, (float(value) / float(max_value)) * 100))
        return format_html(
            '<div class="progress"><div class="progress-bar {}" style="width: {:.1f}%">{:.1f}%</div></div>',
            css_class, pct, pct
        )
    except (ValueError, TypeError, ZeroDivisionError):
        return format_html(
            '<div class="progress"><div class="progress-bar" style="width: 0%">0%</div></div>'
        )


@register.simple_tag
def alert_box(message, alert_type="info"):
    return format_html(
        '<div class="alert alert-{} alert-dismissible fade show" role="alert">'
        '{}'
        '<button type="button" class="close" data-dismiss="alert" aria-label="Close">'
        '<span aria-hidden="true">&times;</span>'
        '</button>'
        '</div>',
        alert_type, message
    )


@register.simple_tag
def icon(name, css_class=""):
    return format_html('<i class="fas fa-{} {}"></i>', name, css_class)


@register.inclusion_tag('core/templatetags/pagination.html')
def render_pagination(page_obj, request):
    return {'page_obj': page_obj, 'request': request}


@register.inclusion_tag('core/templatetags/breadcrumb.html')
def render_breadcrumb(items):
    return {'items': items}


@register.filter
def verbose_name(obj, field_name):
    try:
        return obj._meta.get_field(field_name).verbose_name
    except Exception:
        return field_name


@register.filter
def model_name(obj):
    return obj._meta.model_name


@register.filter
def app_label(obj):
    return obj._meta.app_label


@register.filter
def has_perm(user, perm):
    return user.has_perm(perm)


@register.simple_tag(takes_context=True)
def url_replace(context, **kwargs):
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
    try:
        return range(int(number))
    except (ValueError, TypeError):
        return range(0)


@register.filter
def startswith(text, starts):
    if not text or not starts:
        return False
    return str(text).startswith(str(starts))


@register.filter
def endswith(text, ends):
    if not text or not ends:
        return False
    return str(text).endswith(str(ends))


@register.filter
def contains(text, substring):
    if not text or not substring:
        return False
    return str(substring) in str(text)


@register.filter
def split(value, arg):
    """Divide string pelo separador"""
    return value.split(arg)
