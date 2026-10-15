# apps/relatorios/utils.py
"""Serviços de geração de relatórios compatíveis com os models tenant-scoped.

Não aceita SQL arbitrário de TipoRelatorio.query_sql. Os dados são recolhidos por
queries ORM aprovadas e executados no schema activo do django-tenants.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from django.core.files.base import ContentFile
from django.db import connection
from django.db.models import Count, F, Max, Sum
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.produtos.models import Produto
from apps.vendas.models import ItemVenda, Venda
from .models import AlertaGerencial, DashboardConfig, MetricaKPI, RelatorioGerado

logger = logging.getLogger(__name__)


def _has_field(model, path):
    current = model
    field = None
    for part in path.split("__"):
        try:
            field = current._meta.get_field(part)
        except Exception:
            return False
        if getattr(field, "is_relation", False) and getattr(field, "related_model", None):
            current = field.related_model
    return field is not None


def _date_filter(qs, model, path, start, end):
    if not _has_field(model, path):
        return qs
    try:
        field = model._meta.get_field(path)
        if field.get_internal_type() == "DateTimeField":
            return qs.filter(**{f"{path}__date__range": (start, end)})
    except Exception:
        # Para um path relacional, resolve o último campo a partir do model.
        current = model
        field = None
        for part in path.split("__"):
            field = current._meta.get_field(part)
            if getattr(field, "is_relation", False) and getattr(field, "related_model", None):
                current = field.related_model
        if field and field.get_internal_type() == "DateTimeField":
            return qs.filter(**{f"{path}__date__range": (start, end)})
    return qs.filter(**{f"{path}__range": (start, end)})


def _normalizar_valor(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _normalizar_valor(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalizar_valor(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _rows_for(queryset, fields, limit=10000):
    rows = []
    for obj in queryset[:limit]:
        row = {}
        for label, path in fields:
            value = obj
            for part in path.split("__"):
                value = getattr(value, part, None) if value is not None else None
                if callable(value):
                    try:
                        value = value()
                    except TypeError:
                        value = None
            row[label] = _normalizar_valor(value)
        rows.append(row)
    return rows


def calcular_metricas_vendas(empresa=None, data_inicio=None, data_fim=None):
    """Calcula métricas de venda no schema actual; ``empresa`` é ignorada por compatibilidade.

    Datas finais inclusivas são tratadas correctamente, incluindo todo o último dia.
    """
    hoje = timezone.localdate()
    data_inicio = data_inicio or (hoje.replace(day=1))
    data_fim = data_fim or hoje
    qs = Venda.objects.all()
    if _has_field(Venda, "status"):
        qs = qs.filter(status="finalizada")
    date_field = "data_venda" if _has_field(Venda, "data_venda") else ("data" if _has_field(Venda, "data") else None)
    if date_field:
        qs = _date_filter(qs, Venda, date_field, data_inicio, data_fim)
    total_vendas = qs.count()
    faturamento = qs.aggregate(total=Sum("total"))["total"] or Decimal("0") if _has_field(Venda, "total") else Decimal("0")
    ticket_medio = faturamento / total_vendas if total_vendas else Decimal("0")
    itens = ItemVenda.objects.filter(venda__in=qs)
    total_itens = itens.aggregate(total=Sum("quantidade"))["total"] or 0 if _has_field(ItemVenda, "quantidade") else 0

    vendas_por_dia = []
    if date_field:
        from django.db.models.functions import TruncDate
        vendas_por_dia = list(qs.annotate(dia=TruncDate(date_field)).values("dia").annotate(total=Sum("total"), quantidade=Count("pk")).order_by("dia"))
        for row in vendas_por_dia:
            row["dia"] = _normalizar_valor(row.get("dia")); row["total"] = _normalizar_valor(row.get("total"))

    top_produtos = []
    if _has_field(ItemVenda, "produto") and _has_field(ItemVenda, "quantidade") and _has_field(ItemVenda, "preco_unitario"):
        top_produtos = list(itens.filter(produto__isnull=False).values("produto_id", "produto__nome_comercial", "produto__codigo_interno").annotate(
            quantidade=Sum("quantidade"), faturamento=Sum(F("quantidade") * F("preco_unitario"))
        ).order_by("-faturamento")[:10])
        for row in top_produtos:
            row["faturamento"] = _normalizar_valor(row.get("faturamento"))

    top_clientes = []
    if _has_field(Venda, "cliente"):
        name_field = "cliente__nome_completo" if _has_field(Venda, "cliente__nome_completo") else ("cliente__razao_social" if _has_field(Venda, "cliente__razao_social") else None)
        values = ["cliente_id"] + ([name_field] if name_field else [])
        top_clientes = list(qs.filter(cliente__isnull=False).values(*values).annotate(
            compras=Count("pk"), total=Sum("total")
        ).order_by("-total")[:10])
        for row in top_clientes:
            row["total"] = _normalizar_valor(row.get("total"))

    return {
        "data_inicio": data_inicio.isoformat(), "data_fim": data_fim.isoformat(),
        "total_vendas": total_vendas, "faturamento_total": _normalizar_valor(faturamento),
        "ticket_medio": _normalizar_valor(ticket_medio), "total_itens": total_itens,
        "vendas_por_dia": vendas_por_dia, "top_produtos": top_produtos, "top_clientes": top_clientes,
    }


def calcular_analise_abc_produtos(empresa=None, data_inicio=None, data_fim=None):
    hoje = timezone.localdate(); data_inicio = data_inicio or (hoje - timedelta(days=89)); data_fim = data_fim or hoje
    qs = ItemVenda.objects.all()
    if _has_field(ItemVenda, "venda__status"): qs = qs.filter(venda__status="finalizada")
    qs = _date_filter(qs, ItemVenda, "venda__data_venda", data_inicio, data_fim)
    agrupado = qs.filter(produto__isnull=False).values("produto_id", "produto__codigo_interno", "produto__nome_comercial").annotate(
        quantidade=Sum("quantidade"), faturamento=Sum(F("quantidade") * F("preco_unitario"))
    ).order_by("-faturamento")
    rows = list(agrupado); total = sum((r.get("faturamento") or Decimal("0")) for r in rows); acum = Decimal("0")
    result = []
    for row in rows:
        valor = row.get("faturamento") or Decimal("0"); acum += valor
        perc = (acum / total * 100) if total else Decimal("0")
        classe = "A" if perc <= 80 else "B" if perc <= 95 else "C"
        result.append({**row, "faturamento": _normalizar_valor(valor), "percentual_acumulado": round(float(perc), 2), "classificacao": classe})
    return {"total_faturamento": _normalizar_valor(total), "produtos": result}


def calcular_segmentacao_rfm_clientes(empresa=None, data_inicio=None, data_fim=None):
    hoje = timezone.localdate(); data_inicio = data_inicio or (hoje - timedelta(days=364)); data_fim = data_fim or hoje
    results = []
    clients = Cliente.objects.all()
    if _has_field(Cliente, "ativo"): clients = clients.filter(ativo=True)
    for cliente in clients.iterator():
        vendas = Venda.objects.filter(cliente=cliente)
        if _has_field(Venda, "status"): vendas = vendas.filter(status="finalizada")
        vendas = _date_filter(vendas, Venda, "data_venda", data_inicio, data_fim) if _has_field(Venda, "data_venda") else vendas
        values = vendas.aggregate(frequencia=Count("pk"), monetario=Sum("total"), ultima=Max("data_venda"))
        if not values["frequencia"]: continue
        ultima = values["ultima"]
        if isinstance(ultima, datetime): ultima = timezone.localtime(ultima).date() if timezone.is_aware(ultima) else ultima.date()
        recencia = (data_fim - ultima).days if ultima else None
        results.append({"cliente_id": cliente.pk, "cliente": str(getattr(cliente, "nome_exibicao", None) or getattr(cliente, "nome_completo", None) or cliente),
            "recencia_dias": recencia, "frequencia": values["frequencia"], "valor_monetario": _normalizar_valor(values["monetario"] or 0)})
    return sorted(results, key=lambda item: (item["recencia_dias"] if item["recencia_dias"] is not None else 10**9, -item["frequencia"]))


def gerar_relatorio_pdf(dados, titulo="Relatório VistoGEST"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from xml.sax.saxutils import escape
    rows = dados if isinstance(dados, list) else dados.get("linhas", []) if isinstance(dados, dict) else []
    stream = BytesIO(); doc = SimpleDocTemplate(stream, pagesize=landscape(A4)); styles = getSampleStyleSheet()
    story = [Paragraph(escape(str(titulo)), styles["Title"]), Spacer(1, 12)]
    if rows:
        if not isinstance(rows[0], dict): rows = [{"Valor": row} for row in rows]
        headers = list(rows[0].keys()); table_data = [headers] + [[str(row.get(key, "")) for key in headers] for row in rows]
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16345f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(table)
    else:
        story.append(Paragraph("Sem dados para o período seleccionado.", styles["BodyText"]))
    doc.build(story); return stream.getvalue()


def gerar_relatorio_excel(dados):
    from openpyxl import Workbook
    rows = dados if isinstance(dados, list) else dados.get("linhas", []) if isinstance(dados, dict) else []
    if rows and not isinstance(rows[0], dict): rows = [{"Valor": row} for row in rows]
    headers = list(rows[0].keys()) if rows else ["Informação"]
    book = Workbook(); sheet = book.active; sheet.title = "Relatório"; sheet.append(headers)
    for row in rows: sheet.append([_normalizar_valor(row.get(h)) for h in headers])
    output = BytesIO(); book.save(output); return output.getvalue()


def gerar_relatorio_csv(dados):
    rows = dados if isinstance(dados, list) else dados.get("linhas", []) if isinstance(dados, dict) else []
    if rows and not isinstance(rows[0], dict): rows = [{"Valor": row} for row in rows]
    headers = list(rows[0].keys()) if rows else ["Informação"]
    output = StringIO(); writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore"); writer.writeheader()
    for row in rows: writer.writerow({k: _normalizar_valor(v) for k, v in row.items()})
    return output.getvalue()


def _gerar_dados_relatorio(relatorio):
    """Whitelist de relatórios: nunca executa `TipoRelatorio.query_sql` sem parametrização."""
    codigo = (getattr(relatorio.tipo_relatorio, "codigo", "") or "").upper()
    start = relatorio.data_inicio or (timezone.localdate() - timedelta(days=29))
    end = relatorio.data_fim or timezone.localdate()
    if codigo in {"VENDAS_GERAL", "VENDAS", "RELATORIO_VENDAS"} or "VENDA" in codigo:
        metricas = calcular_metricas_vendas(None, start, end)
        return {"titulo": getattr(relatorio.tipo_relatorio, "nome", "Relatório de Vendas"), "resumo": {k: metricas[k] for k in ("total_vendas", "faturamento_total", "ticket_medio", "total_itens")}, "linhas": metricas["vendas_por_dia"], "top_produtos": metricas["top_produtos"], "top_clientes": metricas["top_clientes"]}
    if "ABC" in codigo or "ESTOQUE" in codigo or "PRODUTO" in codigo:
        data = calcular_analise_abc_produtos(None, start, end)
        return {"titulo": getattr(relatorio.tipo_relatorio, "nome", "Análise de Produtos"), "resumo": {"total_faturamento": data["total_faturamento"], "total_produtos": len(data["produtos"])}, "linhas": data["produtos"]}
    if "CLIENTE" in codigo or "RFM" in codigo or "FIDEL" in codigo:
        data = calcular_segmentacao_rfm_clientes(None, start, end)
        return {"titulo": getattr(relatorio.tipo_relatorio, "nome", "Segmentação de Clientes"), "resumo": {"total_clientes": len(data)}, "linhas": data}
    categoria = str(getattr(relatorio.tipo_relatorio, "categoria", "")).lower()
    if categoria == "estoque":
        qs = Produto.objects.all()
        fields = [("Código", "codigo_interno"), ("Produto", "nome_comercial"), ("Stock", "estoque_atual"), ("Mínimo", "estoque_minimo"), ("Custo", "preco_custo")]
        fields = [(label, path) for label, path in fields if _has_field(Produto, path)]
        rows = _rows_for(qs.order_by("pk"), fields)
    elif categoria == "clientes":
        fields = [("Código", "codigo_cliente"), ("Nome", "nome_completo"), ("NIF", "nif"), ("Telefone", "telefone"), ("Activo", "ativo")]
        fields = [(label, path) for label, path in fields if _has_field(Cliente, path)]
        rows = _rows_for(Cliente.objects.order_by("pk"), fields)
    else:
        rows = []
    return {"titulo": getattr(relatorio.tipo_relatorio, "nome", "Relatório"), "resumo": {"total_registos": len(rows)}, "linhas": rows}


def processar_relatorio_assincrono(relatorio_id, schema_name=None):
    """Processa um relatório dentro do schema já seleccionado pelo task.

    O worker deve entrar em `schema_context(schema_name)` antes desta função.
    """
    relatorio = RelatorioGerado.objects.select_related("tipo_relatorio").get(pk=relatorio_id)
    start_time = timezone.now(); started = time.monotonic()
    relatorio.status = "processando"
    for field, value in (("inicio_processamento", start_time), ("data_inicio_processamento", start_time), ("mensagem_erro", "")):
        if _has_field(RelatorioGerado, field): setattr(relatorio, field, value)
    relatorio.save()
    try:
        data = _gerar_dados_relatorio(relatorio)
        fmt = (relatorio.formato or "json").lower()
        if fmt == "pdf": payload = gerar_relatorio_pdf(data.get("linhas", []), data.get("titulo", "Relatório")); ext = "pdf"
        elif fmt == "excel": payload = gerar_relatorio_excel(data.get("linhas", [])); ext = "xlsx"
        elif fmt == "csv": payload = gerar_relatorio_csv(data.get("linhas", [])); ext = "csv"
        elif fmt == "html":
            from django.utils.html import escape
            rows = data.get("linhas", []); headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
            pieces = ["<!doctype html><html lang='pt-PT'><meta charset='utf-8'><title>", escape(data.get("titulo", "Relatório")), "</title><h1>", escape(data.get("titulo", "Relatório")), "</h1><table border='1'><thead><tr>"]
            pieces.extend(f"<th>{escape(str(h))}</th>" for h in headers); pieces.append("</tr></thead><tbody>")
            for row in rows:
                pieces.append("<tr>"); pieces.extend(f"<td>{escape(str(row.get(h, '')))}</td>" for h in headers); pieces.append("</tr>")
            pieces.append("</tbody></table></html>"); payload = "".join(pieces); ext = "html"
        else: payload = json.dumps(data, ensure_ascii=False, indent=2, default=str); ext = "json"
        if isinstance(payload, str): payload = payload.encode("utf-8")
        filename = f"{relatorio.codigo_relatorio or ('relatorio-' + str(relatorio.pk))}.{ext}"
        relatorio.arquivo_resultado.save(filename, ContentFile(payload), save=False)
        relatorio.dados_resultado = data
        relatorio.total_registros = len(data.get("linhas", []))
        relatorio.status = "concluido"
        if _has_field(RelatorioGerado, "mensagem_erro"): relatorio.mensagem_erro = ""
        end_time = timezone.now()
        for field in ("fim_processamento", "data_fim_processamento"):
            if _has_field(RelatorioGerado, field): setattr(relatorio, field, end_time)
        for field in ("tempo_processamento", "duracao_processamento"):
            if _has_field(RelatorioGerado, field): setattr(relatorio, field, timedelta(seconds=max(0, time.monotonic() - started)))
        relatorio.save()
        return relatorio
    except Exception as exc:
        logger.exception("Falha ao processar RelatorioGerado pk=%s no schema=%s", relatorio_id, schema_name or connection.schema_name)
        relatorio.status = "erro"
        if _has_field(RelatorioGerado, "mensagem_erro"): relatorio.mensagem_erro = str(exc)[:4000]
        for field in ("fim_processamento", "data_fim_processamento"):
            if _has_field(RelatorioGerado, field): setattr(relatorio, field, timezone.now())
        relatorio.save()
        raise


def criar_kpi_automatico(empresa=None, codigo=None, nome=None, tipo_metrica="monetario", periodo="diario", data_referencia=None, valor_meta=None):
    """Cria/actualiza um KPI no schema actual; `empresa` é mantido por compatibilidade."""
    if not codigo:
        raise ValueError("codigo é obrigatório")
    data_referencia = data_referencia or timezone.localdate()
    metric_value = Decimal("0")
    if "VENDA" in codigo.upper() and _has_field(Venda, "total"):
        qs = Venda.objects.all()
        if _has_field(Venda, "status"): qs = qs.filter(status="finalizada")
        qs = _date_filter(qs, Venda, "data_venda", data_referencia, data_referencia) if _has_field(Venda, "data_venda") else qs.none()
        metric_value = qs.aggregate(v=Sum("total"))["v"] or Decimal("0")
    defaults = {}
    for field, value in (("nome", nome or codigo.replace("_", " ").title()), ("tipo_metrica", tipo_metrica), ("periodo", periodo), ("data_referencia", data_referencia), ("valor_atual", metric_value), ("valor_meta", valor_meta)):
        if value is not None and _has_field(MetricaKPI, field): defaults[field] = value
    # Preferência por chave composta quando suportada; fallback para codigo único do model actual.
    try:
        obj, created = MetricaKPI.objects.update_or_create(codigo=codigo, data_referencia=data_referencia, defaults=defaults)
    except Exception:
        obj = MetricaKPI.objects.filter(codigo=codigo).first()
        if obj:
            for key, value in defaults.items(): setattr(obj, key, value)
            obj.save(); created = False
        else:
            obj = MetricaKPI.objects.create(codigo=codigo, **defaults); created = True
    return obj


def detectar_alertas_automaticos(empresa=None):
    """Devolve alertas calculados sem presumir campos persistentes inexistentes."""
    alerts = []; low_stock = Produto.objects.all()
    if _has_field(Produto, "estoque_minimo") and _has_field(Produto, "estoque_atual"):
        low_stock = low_stock.filter(estoque_atual__lte=F("estoque_minimo"))
        for product in low_stock[:100]:
            alerts.append({"tipo": "estoque_baixo", "titulo": f"Stock baixo: {getattr(product, 'nome_comercial', product)}", "descricao": f"Stock actual: {getattr(product, 'estoque_atual', '—')}; mínimo: {getattr(product, 'estoque_minimo', '—')}.", "produto_id": product.pk})
    # Persistência só ocorre se os campos obrigatórios do model forem compatíveis.
    for item in alerts:
        try:
            kwargs = {}
            for field, value in (("titulo", item["titulo"]), ("descricao", item["descricao"]), ("tipo", item["tipo"]), ("prioridade", "media"), ("status", "aberto")):
                if _has_field(AlertaGerencial, field): kwargs[field] = value
            if _has_field(AlertaGerencial, "dados"): kwargs["dados"] = item
            if _has_field(AlertaGerencial, "detalhes"): kwargs["detalhes"] = item["descricao"]
            required_fk = [f.name for f in AlertaGerencial._meta.fields if getattr(f, "many_to_one", False) and not f.null and not f.has_default() and f.name not in kwargs]
            required_simple = [f.name for f in AlertaGerencial._meta.fields if f.concrete and not getattr(f, "many_to_one", False) and not f.primary_key and not f.null and not f.blank and not f.has_default() and f.name not in kwargs]
            if not required_fk and not required_simple:
                AlertaGerencial.objects.create(**kwargs)
        except Exception:
            logger.debug("Não foi possível persistir alerta automático: %s", item.get("titulo"), exc_info=True)
    return alerts


def gerar_dashboard_dados(dashboard_config):
    hoje = timezone.localdate(); start = hoje - timedelta(days=29)
    metricas = calcular_metricas_vendas(None, start, hoje)
    alertas = AlertaGerencial.objects.all().order_by("-pk")[:10]
    kpis = MetricaKPI.objects.all().order_by("-data_referencia")[:10]
    return {"data_inicio": start.isoformat(), "data_fim": hoje.isoformat(), "metricas_vendas": metricas, "alertas": list(alertas), "kpis": list(kpis), "layout": getattr(dashboard_config, "layout", {}), "widgets": getattr(dashboard_config, "widgets", [])}


def exportar_dashboard_pdf(dashboard_config):
    data = gerar_dashboard_dados(dashboard_config)
    return gerar_relatorio_pdf([{"Indicador": key, "Valor": json.dumps(value, ensure_ascii=False, default=str)} for key, value in data["metricas_vendas"].items()], "Dashboard de Relatórios")


def calcular_previsao_vendas(empresa=None, meses_historico=12, meses_previsao=3):
    from django.db.models.functions import TruncMonth
    qs = Venda.objects.all()
    if _has_field(Venda, "status"): qs = qs.filter(status="finalizada")
    if not (_has_field(Venda, "data_venda") and _has_field(Venda, "total")):
        return {"historico": [], "previsao": [], "aviso": "Campos de data/total não disponíveis."}
    grouped = list(qs.annotate(mes=TruncMonth("data_venda")).values("mes").annotate(total=Sum("total")).order_by("mes"))
    hist = [{"mes": row["mes"].strftime("%Y-%m"), "total": float(row["total"] or 0)} for row in grouped if row["mes"]]
    if len(hist) < 3:
        return {"historico": hist, "previsao": [], "aviso": "São necessários pelo menos três meses de dados para uma previsão simples."}
    vals = [row["total"] for row in hist[-meses_historico:]]; avg = sum(vals[-3:]) / min(3, len(vals))
    last = grouped[-1]["mes"].date().replace(day=1); future = []
    for i in range(1, meses_previsao + 1):
        month = last.month + i; year = last.year + (month - 1) // 12; month = ((month - 1) % 12) + 1
        future.append({"mes": f"{year:04d}-{month:02d}", "total_previsto": round(avg, 2), "metodo": "média móvel de 3 meses"})
    return {"historico": hist, "previsao": future}


def analisar_sazonalidade(empresa=None, ano=None):
    from django.db.models.functions import ExtractMonth
    qs = Venda.objects.all()
    if _has_field(Venda, "status"): qs = qs.filter(status="finalizada")
    if ano and _has_field(Venda, "data_venda"): qs = qs.filter(data_venda__year=ano)
    if not (_has_field(Venda, "data_venda") and _has_field(Venda, "total")): return []
    return list(qs.annotate(mes=ExtractMonth("data_venda")).values("mes").annotate(total=Sum("total"), quantidade=Count("pk")).order_by("mes"))


def calcular_tendencias(empresa=None, data_inicio=None, data_fim=None):
    metrics = calcular_metricas_vendas(empresa, data_inicio, data_fim)
    daily = metrics["vendas_por_dia"]
    if len(daily) < 2: return {"tendencia": "dados_insuficientes", "variacao_percentual": 0, "dias": daily}
    first, last = float(daily[0].get("total") or 0), float(daily[-1].get("total") or 0)
    change = ((last - first) / first * 100) if first else 0
    return {"tendencia": "crescente" if change > 0 else "decrescente" if change < 0 else "estável", "variacao_percentual": round(change, 2), "dias": daily}


def gerar_cubo_olap(dimensoes=None, metrica="total", empresa=None, data_inicio=None, data_fim=None):
    """Cubo OLAP simples e parametrizado; aceita apenas dimensões conhecidas."""
    allowed_dims = {"dia": "data_venda", "mes": "data_venda", "estado": "status", "forma_pagamento": "forma_pagamento__nome"}
    dims = [d for d in (dimensoes or ["mes"]) if d in allowed_dims and _has_field(Venda, allowed_dims[d])]
    if not dims or not _has_field(Venda, metrica): return []
    qs = Venda.objects.all()
    if _has_field(Venda, "status"): qs = qs.filter(status="finalizada")
    if data_inicio and data_fim: qs = _date_filter(qs, Venda, "data_venda", data_inicio, data_fim)
    field_list = [allowed_dims[d] for d in dims]
    return list(qs.values(*field_list).annotate(valor=Sum(metrica), quantidade=Count("pk")).order_by(*field_list)[:1000])


def executar_data_mining(empresa=None, data_inicio=None, data_fim=None):
    return calcular_segmentacao_rfm_clientes(empresa, data_inicio, data_fim)


def calcular_correlacoes(empresa=None, data_inicio=None, data_fim=None):
    # Sem biblioteca estatística obrigatória: devolve métricas de entrada validadas.
    return calcular_metricas_vendas(empresa, data_inicio, data_fim)
