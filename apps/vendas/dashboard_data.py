from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import (
    Coalesce, TruncDate, TruncMonth, TruncWeek, TruncYear,
)
from django.utils import timezone

from apps.vendas.models import ItemVenda

MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
         'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
ZERO = Decimal('0.00')
TRUNC = {'diario': TruncDate, 'semanal': TruncWeek,
         'mensal': TruncMonth, 'anual': TruncYear}


def _como_data(valor):
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.date()
    return valor


def _lucro_item():
    """Lucro por linha: base sem IVA (já com desconto de linha) - custo."""
    custo = Coalesce(F('produto__preco_custo'), Value(ZERO),
                     output_field=DecimalField(max_digits=12, decimal_places=2))
    return ExpressionWrapper(
        F('subtotal_sem_iva') - custo * F('quantidade'),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )


def _inicios(tipo, hoje):
    if tipo == 'diario':
        return [hoje - timedelta(days=i) for i in range(29, -1, -1)]
    if tipo == 'semanal':
        base = hoje - timedelta(days=hoje.weekday())
        return [base - timedelta(weeks=i) for i in range(11, -1, -1)]
    if tipo == 'mensal':
        meses, ano, mes = [], hoje.year, hoje.month
        for _ in range(12):
            meses.append(date(ano, mes, 1))
            mes -= 1
            if mes == 0:
                mes, ano = 12, ano - 1
        return meses[::-1]
    return [date(hoje.year - i, 1, 1) for i in range(4, -1, -1)]


def _rotulo(tipo, d):
    if tipo == 'diario':
        return d.strftime('%d/%m')
    if tipo == 'semanal':
        return f"Sem {d.strftime('%d/%m')}"
    if tipo == 'mensal':
        return f"{MESES[d.month - 1]}/{str(d.year)[2:]}"
    return str(d.year)


def _serie(tipo, hoje, vendas_qs):
    inicios = _inicios(tipo, hoje)
    trunc = TRUNC[tipo]

    vendas = (vendas_qs
              .filter(data_venda__date__gte=inicios[0])
              .annotate(p=trunc('data_venda')).values('p')
              .annotate(total_v=Sum('total'), desc_v=Sum('desconto_valor'))
              .order_by('p'))
    itens = (ItemVenda.objects
             .filter(venda__in=vendas_qs, venda__data_venda__date__gte=inicios[0])
             .annotate(p=trunc('venda__data_venda')).values('p')
             .annotate(lucro_v=Sum(_lucro_item()))
             .order_by('p'))

    fat = {_como_data(r['p']): r for r in vendas}
    luc = {_como_data(r['p']): (r['lucro_v'] or ZERO) for r in itens}

    labels, faturamento, lucro = [], [], []
    for ini in inicios:
        r = fat.get(ini)
        total = (r['total_v'] or ZERO) if r else ZERO
        desc = (r['desc_v'] or ZERO) if r else ZERO
        labels.append(_rotulo(tipo, ini))
        faturamento.append(float(round(total, 2)))
        lucro.append(float(round(luc.get(ini, ZERO) - desc, 2)))
    return {'labels': labels, 'faturamento': faturamento, 'lucro': lucro}


def dados_analise_vendas(vendas_qs):
    hoje = timezone.localdate()
    return {t: _serie(t, hoje, vendas_qs) for t in TRUNC}


def lucro_total(vendas_qs):
    """Mesma fórmula do gráfico, para o cartão e o gráfico coincidirem."""
    itens = (ItemVenda.objects.filter(venda__in=vendas_qs)
             .aggregate(v=Sum(_lucro_item()))['v'] or ZERO)
    desc = vendas_qs.aggregate(d=Sum('desconto_valor'))['d'] or ZERO
    return itens - desc