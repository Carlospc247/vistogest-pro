# apps/site/templatetags/site_builder_tags.py
import json
from django import template

register = template.Library()


@register.filter
def dados_json(secao):
    """Conteúdo da secção como JSON válido (o autoescape trata das aspas no atributo HTML)."""
    return json.dumps(secao.dados if isinstance(secao.dados, dict) else {}, ensure_ascii=False)


@register.filter
def secao_design_json(secao):
    return json.dumps({
        'fundo': secao.fundo,
        'cor_fundo_custom': secao.cor_fundo_custom,
        'padding_vertical': secao.padding_vertical,
        'largura_maxima': secao.largura_maxima,
        'animacao_entrada': secao.animacao_entrada,
        'classe_extra': secao.classe_extra,
    }, ensure_ascii=False)