# apps/relatorios/views.py
"""Views consolidadas da app relatorios.

Esta versão evita filtros por Empresa em modelos tenant-scoped: o schema PostgreSQL
selecionado pelo django-tenants é o limite de isolamento. Os relatórios consultam
apenas o schema activo e recusam execução no schema public.
"""
from __future__ import annotations

import csv
import json
import logging
import mimetypes
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO, StringIO

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.core.exceptions import FieldDoesNotExist
from django.core.mail import EmailMessage, send_mail
from django.db import connection
from django.db.models import Avg, Count, F, Q, Sum, Max
from django.db.models.functions import ExtractHour, TruncDate, TruncMonth
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clientes.models import Cliente
from apps.compras.models import Compra
from apps.estoque.models import Inventario, MovimentacaoEstoque
from apps.financeiro.models import ContaPagar, ContaReceber, MovimentacaoFinanceira
from apps.fornecedores.models import Fornecedor
from apps.funcionarios.models import (
    AvaliacaoDesempenho,
    Capacitacao,
    Ferias,
    FolhaPagamento,
    Funcionario,
    RegistroPonto,
)
from apps.produtos.models import Categoria, ControleVencimento, Produto
from apps.vendas.models import ItemVenda, Venda

from .models import (
    AgendamentoRelatorio,
    LogAtividade,
    LogRelatorio,
    MetricaKPI,
    Relatorio,
    RelatorioGerado,
    TemplateRelatorio,
    TipoRelatorio,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers de metadados. Validam os campos antes de construir filtros/queries,
# evitando FieldError quando models relacionados têm nomes diferentes.
# ---------------------------------------------------------------------------
def _get_model_field(model, path):
    current_model = model
    field = None
    for part in path.split("__"):
        try:
            field = current_model._meta.get_field(part)
        except (FieldDoesNotExist, AttributeError):
            return None
        if getattr(field, "is_relation", False) and getattr(field, "related_model", None):
            current_model = field.related_model
    return field


def _path_exists(model, path):
    return _get_model_field(model, path) is not None


def _first_existing_path(model, paths):
    return next((path for path in paths if _path_exists(model, path)), None)


def _safe_order(queryset, model, candidates):
    field = _first_existing_path(model, candidates)
    if field:
        return queryset.order_by(f"-{field}")
    return queryset.order_by("-pk")


def _date_filtered(queryset, model, path, start, end):
    if not path or not _path_exists(model, path):
        return queryset
    field = _get_model_field(model, path)
    internal_type = field.get_internal_type() if field else ""
    if internal_type == "DateTimeField":
        return queryset.filter(**{f"{path}__date__range": (start, end)})
    return queryset.filter(**{f"{path}__range": (start, end)})


def _resolve_attr(obj, path):
    value = obj
    for part in path.split("__"):
        if value is None:
            return None
        try:
            value = getattr(value, part)
        except (AttributeError, TypeError):
            return None
        if callable(value):
            try:
                value = value()
            except TypeError:
                return None
    return value


def _display(value):
    if value is None:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y %H:%M" if isinstance(value, datetime) else "%d/%m/%Y")
    if isinstance(value, Decimal):
        return f"{value:,.2f}".replace(",", " ")
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _build_table(queryset, model, field_paths, title="Registos", limit=100, labels=None):
    labels = labels or {}
    paths = [p for p in field_paths if _path_exists(model, p)]
    if not paths:
        paths = [model._meta.pk.name]
    columns = [labels.get(path, path.replace("__", " · ").replace("_", " ").capitalize()) for path in paths]
    rows = []
    for obj in queryset[:limit]:
        rows.append([{"valor": _display(_resolve_attr(obj, path))} for path in paths])
    return {"titulo": title, "colunas": columns, "linhas": rows, "total_limitado": len(rows)}


def _model_fields(model):
    return [field for field in model._meta.get_fields() if getattr(field, "concrete", False) and not getattr(field, "many_to_many", False)]


def _dict_table(rows, columns, title="Registos", limit=100):
    selected = rows[:limit]
    return {
        "titulo": title,
        "colunas": [label for label, _key in columns],
        "linhas": [[{"valor": _display(row.get(key))} for _label, key in columns] for row in selected],
        "total_limitado": len(selected),
    }


def _sales_queryset(start=None, end=None):
    qs = Venda.objects.all()
    if _path_exists(Venda, "status"):
        qs = qs.filter(status="finalizada")
    if start and end:
        date_field = _first_existing_path(Venda, ("data_venda", "data"))
        if date_field:
            qs = _date_filtered(qs, Venda, date_field, start, end)
    return qs


def _items_sales_queryset(start=None, end=None):
    qs = ItemVenda.objects.all()
    if _path_exists(ItemVenda, "venda__status"):
        qs = qs.filter(venda__status="finalizada")
    if start and end and _path_exists(ItemVenda, "venda__data_venda"):
        qs = _date_filtered(qs, ItemVenda, "venda__data_venda", start, end)
    elif start and end and _path_exists(ItemVenda, "venda__data"):
        qs = _date_filtered(qs, ItemVenda, "venda__data", start, end)
    if _path_exists(ItemVenda, "produto"):
        qs = qs.filter(produto__isnull=False)
    return qs


def _item_revenue_expression():
    # Usa o subtotal gravado quando existe; caso contrário calcula a linha sem
    # presumir campos de desconto/IVA que podem variar entre versões do model.
    if _path_exists(ItemVenda, "subtotal"):
        return Sum("subtotal")
    return Sum(F("quantidade") * F("preco_unitario"))


def _grouped_items(start, end, group_candidates, limit=100, base_qs=None):
    qs = base_qs if base_qs is not None else _items_sales_queryset(start, end)
    group_paths = [(label, path) for label, path in group_candidates if _path_exists(ItemVenda, path)]
    if not group_paths:
        group_paths = [("Produto", "produto_id")] if _path_exists(ItemVenda, "produto") else []
    if not group_paths:
        return []
    paths = [path for _label, path in group_paths]
    values = qs.values(*paths).annotate(
        quantidade_vendida=Sum("quantidade"),
        faturamento=_item_revenue_expression(),
        documentos=Count("venda", distinct=True) if _path_exists(ItemVenda, "venda") else Count("pk"),
    ).order_by("-faturamento")
    rows = list(values[:limit])
    # Aliases visíveis para templates, sem depender de nomes de campos do cliente.
    for row in rows:
        for label, path in group_paths:
            row[f"display_{label}"] = _display(row.get(path))
        row["faturamento"] = row.get("faturamento") or 0
        row["quantidade_vendida"] = row.get("quantidade_vendida") or 0
    return rows


def _create_log(user, action, details=""):
    """Cria log usando apenas campos existentes no model LogRelatorio."""
    kwargs = {}
    if _path_exists(LogRelatorio, "usuario"):
        kwargs["usuario"] = user
    if _path_exists(LogRelatorio, "acao"):
        allowed = {choice[0] for choice in LogRelatorio._meta.get_field("acao").choices or []}
        kwargs["acao"] = action if action in allowed else (next(iter(allowed), action))
    if _path_exists(LogRelatorio, "detalhes"):
        kwargs["detalhes"] = str(details)[:4000]
    if _path_exists(LogRelatorio, "tipo"):
        allowed_tipo = {choice[0] for choice in LogRelatorio._meta.get_field("tipo").choices or []}
        if "HISTORICO" in allowed_tipo:
            kwargs["tipo"] = "HISTORICO"
    try:
        LogRelatorio.objects.create(**kwargs)
    except Exception:
        logger.exception("Não foi possível registar a actividade de relatórios")


def _report_payload(report):
    data = report.dados_resultado or {}
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("rows", "linhas", "dados", "results", "resultados"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def _normalise_rows(rows):
    normalised = []
    for row in rows:
        if isinstance(row, dict):
            normalised.append({str(k): _display(v) for k, v in row.items()})
        elif isinstance(row, (list, tuple)):
            normalised.append({f"Coluna {i + 1}": _display(v) for i, v in enumerate(row)})
        else:
            normalised.append({"Valor": _display(row)})
    return normalised


class TenantLoginRequiredMixin(LoginRequiredMixin):
    """A app de relatórios opera apenas dentro do schema de cada tenant."""
    login_url = "/contas/login/"
    redirect_field_name = "next"

    def dispatch(self, request, *args, **kwargs):
        if connection.schema_name == "public":
            return HttpResponseForbidden("Os relatórios só estão disponíveis no espaço de trabalho da empresa.")
        return super().dispatch(request, *args, **kwargs)


class RelatorioBaseView(TenantLoginRequiredMixin, TemplateView):
    template_name = "relatorios/pagina.html"
    titulo = "Relatórios"

    def get_periodo(self):
        hoje = timezone.localdate()
        inicio = parse_date(self.request.GET.get("data_inicio", ""))
        fim = parse_date(self.request.GET.get("data_fim", ""))
        return inicio or (hoje - timedelta(days=29)), fim or hoje

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        inicio, fim = self.get_periodo()
        context.setdefault("title", self.titulo)
        context.setdefault("titulo", self.titulo)
        context.setdefault("page_title", self.titulo)
        context["data_inicio"] = inicio
        context["data_fim"] = fim
        context["show_date_filters"] = getattr(self, "show_date_filters", bool(getattr(self, "date_fields", ())))
        context.setdefault("kpis", [])
        context.setdefault("tabelas", [])
        context.setdefault("filtros_ativos", bool(self.request.GET))
        return context


class ModeloRelatorioView(RelatorioBaseView):
    """Lista segura e filtrada por período para uma fonte de dados do tenant."""
    model = None
    fields = ()
    date_fields = ()
    amount_fields = ()
    template_name = "relatorios/pagina.html"
    table_title = "Registos"
    page_size = 100
    status_finalizada = False

    def get_queryset(self):
        if self.model is None:
            return []
        qs = self.model.objects.all()
        inicio, fim = self.get_periodo()
        date_field = _first_existing_path(self.model, self.date_fields)
        if date_field:
            qs = _date_filtered(qs, self.model, date_field, inicio, fim)
        if self.status_finalizada and _path_exists(self.model, "status"):
            qs = qs.filter(status="finalizada")
        return _safe_order(qs, self.model, ("data_venda", "data", "created_at", "data_emissao", "data_pedido", "pk"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.model is None:
            return context
        qs = self.get_queryset()
        model_fields = [field.name for field in _model_fields(self.model)]
        fields = [field for field in self.fields if _path_exists(self.model, field)]
        if not fields:
            fields = [field for field in ("id", "nome", "nome_completo", "nome_produto", "codigo", "status", "data") if field in model_fields]
        context["tabelas"] = [_build_table(qs, self.model, fields, self.table_title, self.page_size)]
        count = qs.count() if hasattr(qs, "count") else len(qs)
        context["kpis"] = [{"rotulo": "Registos", "valor": count}]
        amount_field = _first_existing_path(self.model, self.amount_fields)
        if amount_field:
            try:
                total = qs.aggregate(total=Sum(amount_field))["total"] or 0
                context["kpis"].append({"rotulo": "Total", "valor": _display(total)})
            except Exception:
                logger.debug("Não foi possível agregar %s.%s", self.model.__name__, amount_field)
        context["total_registos"] = count
        context["page_title"] = self.titulo
        context["title"] = self.titulo
        context["titulo"] = self.titulo
        return context


# ---------------------------------------------------------------------------
# Painel, biblioteca e construtor de relatórios
# ---------------------------------------------------------------------------
class RelatoriosDashboardView(RelatorioBaseView):
    template_name = "relatorios/dashboard.html"
    titulo = "Painel de Relatórios"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["kpis"] = [
            {"rotulo": "Tipos activos", "valor": TipoRelatorio.objects.filter(ativo=True).count()},
            {"rotulo": "Relatórios gerados", "valor": RelatorioGerado.objects.count()},
            {"rotulo": "Templates activos", "valor": TemplateRelatorio.objects.filter(ativo=True).count()},
            {"rotulo": "Agendamentos activos", "valor": AgendamentoRelatorio.objects.filter(ativo=True).count()},
        ]
        recentes = RelatorioGerado.objects.filter(solicitante=self.request.user).select_related("tipo_relatorio")
        recentes = recentes.order_by("-data_solicitacao")[:10]
        ctx["tabelas"] = [_build_table(recentes, RelatorioGerado,
            ("codigo_relatorio", "tipo_relatorio__nome", "formato", "status", "data_solicitacao"),
            "Os meus relatórios recentes", 10)]
        ctx["tipos_populares"] = TipoRelatorio.objects.filter(ativo=True).order_by("nome")[:8]
        return ctx


class CentralRelatoriosView(RelatorioBaseView):
    template_name = "relatorios/central.html"
    titulo = "Central de Relatórios"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tipos_relatorio"] = TipoRelatorio.objects.filter(ativo=True).order_by("categoria", "nome")
        ctx["templates_relatorio"] = TemplateRelatorio.objects.filter(ativo=True).order_by("nome")
        ctx["categorias_relatorio"] = sorted(set(TipoRelatorio.objects.filter(ativo=True).values_list("categoria", flat=True)))
        return ctx


class RelatoriosFavoritosView(RelatorioBaseView):
    template_name = "relatorios/favoritos.html"
    titulo = "Relatórios Favoritos"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # O model não possui campo de favoritos; não simulamos um favorito persistente.
        ctx["aviso"] = "A marcação de favoritos ainda não tem um campo persistente no model. São apresentados os seus relatórios recentes."
        qs = RelatorioGerado.objects.filter(solicitante=self.request.user).select_related("tipo_relatorio").order_by("-data_solicitacao")[:25]
        ctx["tabelas"] = [_build_table(qs, RelatorioGerado, ("codigo_relatorio", "tipo_relatorio__nome", "status", "formato", "data_solicitacao"), "Relatórios recentes", 25)]
        return ctx


class RelatoriosRecentesView(RelatorioBaseView):
    template_name = "relatorios/recentes.html"
    titulo = "Relatórios Recentes"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = RelatorioGerado.objects.filter(solicitante=self.request.user).select_related("tipo_relatorio").order_by("-data_solicitacao")[:50]
        ctx["tabelas"] = [_build_table(qs, RelatorioGerado, ("codigo_relatorio", "tipo_relatorio__nome", "status", "formato", "data_solicitacao"), "Relatórios recentes", 50)]
        return ctx


class ConstrutorRelatorioView(RelatorioBaseView):
    template_name = "relatorios/construtor.html"
    titulo = "Construtor de Relatórios"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["templates_relatorio"] = TemplateRelatorio.objects.filter(ativo=True).order_by("nome")
        ctx["modelos_disponiveis"] = [
            {"label": model._meta.verbose_name_plural.title(), "app_label": model._meta.app_label, "model": model._meta.model_name}
            for model in (Venda, ItemVenda, Produto, Cliente, Compra, Fornecedor, ContaReceber, ContaPagar)
        ]
        return ctx


class NovoRelatorioView(TenantLoginRequiredMixin, CreateView):
    model = TemplateRelatorio
    template_name = "relatorios/templates/form.html"
    fields = ("nome", "descricao", "modelo_base", "campos", "filtros_disponiveis", "ativo")
    success_url = reverse_lazy("relatorios:templates")

    def form_valid(self, form):
        response = super().form_valid(form)
        _create_log(self.request.user, "CRIACAO", f'Template criado: {self.object.nome}')
        messages.success(self.request, "Template criado com sucesso.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"title": "Novo template de relatório", "titulo": "Novo template de relatório"})
        return ctx


class EditarRelatorioView(TenantLoginRequiredMixin, UpdateView):
    model = TemplateRelatorio
    template_name = "relatorios/templates/form.html"
    fields = ("nome", "descricao", "modelo_base", "campos", "filtros_disponiveis", "ativo")
    success_url = reverse_lazy("relatorios:templates")

    def form_valid(self, form):
        response = super().form_valid(form)
        _create_log(self.request.user, "ALTERACAO", f'Template actualizado: {self.object.nome}')
        messages.success(self.request, "Template actualizado com sucesso.")
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"title": "Editar template", "titulo": "Editar template"})
        return ctx


class CamposDisponiveisView(RelatorioBaseView):
    template_name = "relatorios/campos.html"
    titulo = "Campos Disponíveis"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        model_key = self.request.GET.get("modelo", "vendas.venda")
        candidates = {f"{m._meta.app_label}.{m._meta.model_name}": m for m in (Venda, ItemVenda, Produto, Cliente, Compra, Fornecedor, ContaReceber, ContaPagar, Funcionario)}
        model = candidates.get(model_key, Venda)
        ctx["modelo_selecionado"] = f"{model._meta.app_label}.{model._meta.model_name}"
        ctx["modelos_disponiveis"] = [{"value": key, "label": m._meta.verbose_name_plural.title()} for key, m in candidates.items()]
        ctx["campos_disponiveis"] = [{"nome": f.name, "tipo": f.get_internal_type(), "obrigatorio": not getattr(f, "blank", True) and not getattr(f, "null", True)} for f in _model_fields(model)]
        return ctx


class TemplateRelatorioListView(TenantLoginRequiredMixin, ListView):
    model = TemplateRelatorio
    template_name = "relatorios/templates/lista.html"
    context_object_name = "templates_relatorio"
    paginate_by = 25

    def get_queryset(self):
        qs = TemplateRelatorio.objects.all().order_by("nome")
        query = self.request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(Q(nome__icontains=query) | Q(descricao__icontains=query))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"title": "Templates de Relatórios", "titulo": "Templates de Relatórios"})
        return ctx


class TemplateRelatorioCreateView(NovoRelatorioView):
    pass


class TemplateRelatorioDetailView(TenantLoginRequiredMixin, DetailView):
    model = TemplateRelatorio
    template_name = "relatorios/templates/detalhe.html"
    context_object_name = "template_relatorio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = Relatorio.objects.filter(template=self.object).order_by("-date_geracao") if _path_exists(Relatorio, "date_geracao") else Relatorio.objects.filter(template=self.object)
        ctx["relatorios_gerados"] = qs[:25]
        ctx.update({"title": self.object.nome, "titulo": self.object.nome})
        return ctx


class DuplicarTemplateView(TenantLoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        original = get_object_or_404(TemplateRelatorio, pk=pk)
        nome = (request.POST.get("nome") or f"{original.nome} (cópia)").strip()[:200]
        kwargs = {"nome": nome}
        for field in ("descricao", "modelo_base", "campos", "filtros_disponiveis"):
            if _path_exists(TemplateRelatorio, field):
                kwargs[field] = getattr(original, field)
        if _path_exists(TemplateRelatorio, "ativo"):
            kwargs["ativo"] = False
        clone = TemplateRelatorio.objects.create(**kwargs)
        _create_log(request.user, "CRIACAO", f'Template duplicado de {original.pk}: {clone.nome}')
        messages.success(request, "Template duplicado. Confirme os campos antes de o activar.")
        return redirect("relatorios:template_detail", pk=clone.pk)


class CompartilharTemplateView(TenantLoginRequiredMixin, DetailView):
    model = TemplateRelatorio
    template_name = "relatorios/templates/compartilhar.html"
    context_object_name = "template_relatorio"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["usuarios_empresa"] = User.objects.filter(is_active=True).exclude(pk=self.request.user.pk).order_by("username")
        ctx["grupos_disponiveis"] = Group.objects.order_by("name")
        ctx.update({"title": f"Compartilhar: {self.object.nome}", "titulo": f"Compartilhar: {self.object.nome}"})
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        user_ids = request.POST.getlist("usuarios")
        group_ids = request.POST.getlist("grupos")
        mensagem = request.POST.get("mensagem", "").strip()
        # O queryset de utilizadores é do schema actual, logo não atravessa tenants.
        recipients = {u.pk: u for u in User.objects.filter(pk__in=user_ids, is_active=True).exclude(pk=request.user.pk)}
        groups = Group.objects.filter(pk__in=group_ids)
        for group in groups:
            for user in group.user_set.filter(is_active=True).exclude(pk=request.user.pk):
                recipients[user.pk] = user
        sent = 0
        for user in recipients.values():
            if not user.email:
                continue
            try:
                send_mail(
                    subject=f"Template de relatório partilhado: {self.object.nome}",
                    message=(f"{request.user.get_full_name() or request.user.username} partilhou o template "
                             f'"{self.object.nome}" consigo.\n\nDescrição: {self.object.descricao or "—"}\n\n{mensagem}'),
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                sent += 1
            except Exception:
                logger.exception("Falha no envio de partilha de template para %s", user.pk)
        _create_log(request.user, "ACESSO", f"Partilha do template {self.object.pk}; emails enviados: {sent}")
        messages.success(request, f"Notificações enviadas para {sent} utilizador(es). O acesso continua sujeito às permissões do sistema.")
        return redirect("relatorios:template_detail", pk=self.object.pk)


# ---------------------------------------------------------------------------
# Relatórios operacionais. Os paths de campos são validados contra _meta.
# ---------------------------------------------------------------------------
class RelatoriosVendasView(ModeloRelatorioView):
    model = Venda; titulo = "Relatório de Vendas"; table_title = "Vendas"
    fields = ("numero_documento", "data_venda", "cliente__nome_completo", "funcionario__id", "status", "subtotal", "total")
    date_fields = ("data_venda",); amount_fields = ("total",); status_finalizada = True
    template_name = "relatorios/vendas/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        stats = qs.aggregate(
            quantidade=Count("pk"),
            faturamento=Sum("total") if _path_exists(Venda, "total") else Count("pk"),
            ticket=Avg("total") if _path_exists(Venda, "total") else Count("pk"),
        )
        ctx["kpis"] = [
            {"rotulo": "Vendas finalizadas", "valor": stats.get("quantidade") or 0},
            {"rotulo": "Faturamento", "valor": _display(stats.get("faturamento") or 0)},
            {"rotulo": "Ticket médio", "valor": _display(stats.get("ticket") or 0)},
        ]
        ctx["tabelas"] = [_build_table(qs, Venda, self.fields, "Vendas finalizadas no período", self.page_size)]
        return ctx


class RelatorioVendasDiarioView(RelatoriosVendasView):
    titulo = "Relatório Diário de Vendas"; template_name = "relatorios/vendas/diario.html"
    show_date_filters = False
    show_single_date_filter = True
    def get_periodo(self):
        selected = parse_date(self.request.GET.get("data", "")) or timezone.localdate()
        return selected, selected
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["data_selecionada"] = self.get_periodo()[0]
        qs = self.get_queryset()
        if _path_exists(Venda, "data_venda") and _get_model_field(Venda, "data_venda").get_internal_type() == "DateTimeField":
            rows = list(qs.annotate(hora=ExtractHour("data_venda")).values("hora").annotate(quantidade=Count("pk"), faturamento=Sum("total")).order_by("hora"))
            by_hour = {row["hora"]: row for row in rows}
            rows = [{"hora": hour, "quantidade": by_hour.get(hour, {}).get("quantidade", 0), "faturamento": by_hour.get(hour, {}).get("faturamento", 0)} for hour in range(24)]
            ctx["tabelas"].append(_dict_table(rows, [("Hora", "hora"), ("Vendas", "quantidade"), ("Faturamento", "faturamento")], "Vendas por hora", 24))
        return ctx


class RelatorioVendasMensalView(RelatoriosVendasView):
    titulo = "Relatório Mensal de Vendas"; template_name = "relatorios/vendas/mensal.html"
    show_date_filters = False
    show_month_filter = True
    def get_periodo(self):
        hoje = timezone.localdate()
        try: year, month = int(self.request.GET.get("ano", hoje.year)), int(self.request.GET.get("mes", hoje.month))
        except (TypeError, ValueError): year, month = hoje.year, hoje.month
        try: start = date(year, month, 1)
        except ValueError: start = hoje.replace(day=1)
        end = (start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)) if start.month == 12 else (start.replace(month=start.month + 1, day=1) - timedelta(days=1))
        return start, end
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        inicio, _fim = self.get_periodo()
        ctx["mes"] = inicio.month; ctx["ano"] = inicio.year
        ctx["meses_disponiveis"] = [(1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"), (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"), (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro")]
        qs = self.get_queryset()
        if _path_exists(Venda, "data_venda"):
            grouped = list(qs.annotate(dia=TruncDate("data_venda")).values("dia").annotate(quantidade=Count("pk"), faturamento=Sum("total")).order_by("dia"))
            ctx["tabelas"].append(_dict_table(grouped, [("Dia", "dia"), ("Vendas", "quantidade"), ("Faturamento", "faturamento")], "Evolução diária do mês", 40))
        return ctx


class RelatorioVendasAnualView(RelatoriosVendasView):
    titulo = "Relatório Anual de Vendas"; template_name = "relatorios/vendas/anual.html"
    show_date_filters = False
    show_year_filter = True
    def get_periodo(self):
        try: year = int(self.request.GET.get("ano", timezone.localdate().year))
        except (TypeError, ValueError): year = timezone.localdate().year
        return date(year, 1, 1), date(year, 12, 31)
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["ano"] = self.get_periodo()[0].year
        qs = self.get_queryset()
        if _path_exists(Venda, "data_venda"):
            grouped = list(qs.annotate(mes=TruncMonth("data_venda")).values("mes").annotate(quantidade=Count("pk"), faturamento=Sum("total")).order_by("mes"))
            for row in grouped:
                row["mes"] = row["mes"].date() if row.get("mes") else None
            ctx["tabelas"].append(_dict_table(grouped, [("Mês", "mes"), ("Vendas", "quantidade"), ("Faturamento", "faturamento")], "Evolução mensal do ano", 12))
        return ctx


class RelatorioVendasProdutoView(ModeloRelatorioView):
    model = ItemVenda; titulo = "Vendas por Produto"; table_title = "Produtos vendidos"
    fields = ("produto__codigo_interno", "produto__nome_comercial", "produto__nome_produto", "quantidade", "preco_unitario", "subtotal")
    date_fields = ("venda__data_venda",); amount_fields = ("subtotal",)
    template_name = "relatorios/vendas/produto.html"

    def get_queryset(self):
        qs = super().get_queryset()
        if _path_exists(ItemVenda, "venda__status"):
            qs = qs.filter(venda__status="finalizada")
        product_id = self.request.GET.get("produto_id")
        category_id = self.request.GET.get("categoria_id")
        if product_id and _path_exists(ItemVenda, "produto"):
            qs = qs.filter(produto_id=product_id)
        if category_id and _path_exists(ItemVenda, "produto__categoria"):
            qs = qs.filter(produto__categoria_id=category_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end = self.get_periodo()
        rows = _grouped_items(start, end, [("Código", "produto__codigo_interno"), ("Produto", "produto__nome_comercial"), ("Categoria", "produto__categoria__nome")], 100, base_qs=self.get_queryset())
        columns = [("Código", "display_Código"), ("Produto", "display_Produto"), ("Categoria", "display_Categoria"), ("Quantidade vendida", "quantidade_vendida"), ("Faturamento", "faturamento"), ("Documentos", "documentos")]
        ctx["tabelas"] = [_dict_table(rows, columns, "Ranking de produtos", 100)]
        ctx["kpis"] = [{"rotulo": "Produtos com vendas", "valor": len(rows)}, {"rotulo": "Unidades vendidas", "valor": sum((r.get("quantidade_vendida") or 0) for r in rows)}, {"rotulo": "Faturamento", "valor": _display(sum((r.get("faturamento") or 0) for r in rows))}]
        if _path_exists(Categoria, "nome"): ctx["categorias_disponiveis"] = Categoria.objects.all().order_by("nome")
        if _path_exists(Produto, "nome_comercial"): ctx["produtos_disponiveis"] = Produto.objects.all().order_by("nome_comercial")[:1000]
        return ctx


class RelatorioVendasCategoriaView(RelatorioVendasProdutoView):
    titulo = "Vendas por Categoria"; template_name = "relatorios/vendas/categoria.html"
    fields = ("produto__categoria__nome", "produto__nome_comercial", "quantidade", "preco_unitario", "subtotal")
    table_title = "Vendas por categoria"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start, end = self.get_periodo()
        rows = _grouped_items(start, end, [("Categoria", "produto__categoria__nome")], 100, base_qs=self.get_queryset())
        columns = [("Categoria", "display_Categoria"), ("Quantidade vendida", "quantidade_vendida"), ("Faturamento", "faturamento"), ("Documentos", "documentos")]
        total = sum((r.get("faturamento") or 0) for r in rows)
        for row in rows: row["participacao"] = round(float(row.get("faturamento") or 0) / float(total) * 100, 1) if total else 0
        columns.append(("Participação (%)", "participacao"))
        ctx["tabelas"] = [_dict_table(rows, columns, "Vendas por categoria", 100)]
        ctx["kpis"] = [{"rotulo": "Categorias com vendas", "valor": len(rows)}, {"rotulo": "Faturamento", "valor": _display(total)}]
        return ctx


class RelatorioVendasVendedorView(RelatoriosVendasView):
    titulo = "Vendas por Vendedor"; template_name = "relatorios/vendas/vendedor.html"
    fields = ("funcionario__id", "data_venda", "numero_documento", "total", "status")
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        name_field = _first_existing_path(Venda, ("funcionario__nome_completo", "funcionario__usuario__username", "funcionario__user__username"))
        groups = ["funcionario_id"] if _path_exists(Venda, "funcionario") else []
        if name_field: groups.append(name_field)
        if groups:
            rows = list(qs.values(*groups).annotate(quantidade=Count("pk"), faturamento=Sum("total"), ticket_medio=Avg("total")).order_by("-faturamento")[:100])
            cols = [("Vendedor", name_field)] if name_field else [("ID do funcionário", "funcionario_id")]
            if name_field and "funcionario_id" in groups: cols.append(("ID", "funcionario_id"))
            cols += [("Vendas", "quantidade"), ("Faturamento", "faturamento"), ("Ticket médio", "ticket_medio")]
            ctx["tabelas"] = [_dict_table(rows, cols, "Desempenho por vendedor", 100)]
        return ctx


class RelatorioVendasClienteView(RelatoriosVendasView):
    titulo = "Vendas por Cliente"; template_name = "relatorios/vendas/cliente.html"
    fields = ("cliente__codigo_cliente", "cliente__nome_completo", "cliente__nome_social", "data_venda", "total")
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        name_field = _first_existing_path(Venda, ("cliente__nome_completo", "cliente__nome_social", "cliente__razao_social"))
        groups = ["cliente_id"] if _path_exists(Venda, "cliente") else []
        if name_field: groups.append(name_field)
        if groups:
            rows = list(qs.filter(cliente__isnull=False).values(*groups).annotate(compras=Count("pk"), total=Sum("total"), ticket_medio=Avg("total"), ultima_compra=Max("data_venda") if _path_exists(Venda, "data_venda") else Max("pk")).order_by("-total")[:100])
            cols = [("Cliente", name_field)] if name_field else [("ID do cliente", "cliente_id")]
            if "cliente_id" in groups: cols.append(("ID", "cliente_id"))
            cols += [("Compras", "compras"), ("Total gasto", "total"), ("Ticket médio", "ticket_medio"), ("Última compra", "ultima_compra")]
            ctx["tabelas"] = [_dict_table(rows, cols, "Vendas por cliente", 100)]
        return ctx


class RelatorioVendasFormaPagamentoView(RelatoriosVendasView):
    titulo = "Vendas por Forma de Pagamento"; template_name = "relatorios/vendas/forma_pagamento.html"
    fields = ("forma_pagamento__nome", "data_venda", "numero_documento", "total")
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        label_field = _first_existing_path(Venda, ("forma_pagamento__nome", "forma_pagamento__tipo", "forma_pagamento__descricao"))
        group = label_field or ("forma_pagamento" if _path_exists(Venda, "forma_pagamento") else None)
        if group:
            rows = list(qs.values(group).annotate(quantidade=Count("pk"), total=Sum("total"), ticket_medio=Avg("total")).order_by("-total")[:50])
            ctx["tabelas"] = [_dict_table(rows, [("Forma de pagamento", group), ("Vendas", "quantidade"), ("Total", "total"), ("Ticket médio", "ticket_medio")], "Vendas por forma de pagamento", 50)]
        return ctx


class RelatoriosEstoqueView(ModeloRelatorioView):
    model = Produto; titulo = "Painel de Estoque"; table_title = "Produtos e stock"
    fields = ("codigo_interno", "codigo_barras", "nome_comercial", "categoria__nome", "estoque_atual", "estoque_minimo", "preco_custo", "preco_venda")
    template_name = "relatorios/estoque/dashboard.html"

    def get_queryset(self):
        qs = Produto.objects.all()
        if _path_exists(Produto, "ativo"): qs = qs.filter(ativo=True)
        return _safe_order(qs, Produto, ("nome_comercial", "nome_produto", "pk"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        total = qs.count()
        low = qs.filter(estoque_atual__lte=F("estoque_minimo")).count() if _path_exists(Produto, "estoque_atual") and _path_exists(Produto, "estoque_minimo") else 0
        zero = qs.filter(estoque_atual__lte=0).count() if _path_exists(Produto, "estoque_atual") else 0
        value = 0
        if _path_exists(Produto, "estoque_atual") and _path_exists(Produto, "preco_custo"):
            value = qs.aggregate(total=Sum(F("estoque_atual") * F("preco_custo")))["total"] or 0
        ctx["kpis"] = [
            {"rotulo": "Produtos activos", "valor": total},
            {"rotulo": "Stock baixo", "valor": low},
            {"rotulo": "Sem stock", "valor": zero},
            {"rotulo": "Valor estimado do stock", "valor": _display(value)},
        ]
        ctx["tabelas"] = [_build_table(qs, Produto, self.fields, "Posição actual do stock", 100)]
        return ctx


class RelatorioPosicaoEstoqueView(RelatoriosEstoqueView):
    titulo = "Posição de Estoque"; template_name = "relatorios/estoque/posicao.html"
    def get_queryset(self):
        qs = super().get_queryset()
        categoria_id = self.request.GET.get("categoria_id")
        situacao = self.request.GET.get("situacao", "")
        busca = self.request.GET.get("busca", "").strip()
        if categoria_id and _path_exists(Produto, "categoria"):
            qs = qs.filter(categoria_id=categoria_id)
        if busca:
            conditions = []
            for field in ("nome_comercial", "nome_produto", "codigo_interno", "codigo_barras"):
                if _path_exists(Produto, field): conditions.append(Q(**{f"{field}__icontains": busca}))
            if conditions:
                query = conditions[0]
                for condition in conditions[1:]: query |= condition
                qs = qs.filter(query)
        if situacao == "zerado" and _path_exists(Produto, "estoque_atual"):
            qs = qs.filter(estoque_atual__lte=0)
        elif situacao == "baixo" and _path_exists(Produto, "estoque_atual") and _path_exists(Produto, "estoque_minimo"):
            qs = qs.filter(estoque_atual__gt=0, estoque_atual__lte=F("estoque_minimo"))
        elif situacao == "normal" and _path_exists(Produto, "estoque_atual") and _path_exists(Produto, "estoque_minimo"):
            qs = qs.filter(estoque_atual__gt=F("estoque_minimo"))
        ctx_fields = ["id", "codigo_interno", "codigo_barras", "nome_comercial", "categoria__nome", "estoque_atual", "estoque_minimo", "preco_custo", "preco_venda"]
        self.fields = tuple(ctx_fields)
        return qs
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tabelas"] = [_build_table(self.get_queryset(), Produto, self.fields, "Posição actual do stock", 200)]
        if _path_exists(Categoria, "nome"):
            ctx["categorias_disponiveis"] = Categoria.objects.all().order_by("nome")
        ctx["filtros"] = {"categoria_id": self.request.GET.get("categoria_id", ""), "situacao": self.request.GET.get("situacao", ""), "busca": self.request.GET.get("busca", "")}
        return ctx


class RelatorioMovimentacaoEstoqueView(ModeloRelatorioView):
    model = MovimentacaoEstoque; titulo = "Movimentação de Estoque"; table_title = "Movimentações"
    fields = ("produto__nome_comercial", "tipo", "quantidade", "motivo", "usuario", "created_at", "updated_at")
    date_fields = ("created_at", "updated_at", "data_movimentacao"); template_name = "relatorios/estoque/movimentacao.html"
    def get_queryset(self):
        qs = super().get_queryset()
        tipo = self.request.GET.get("tipo_movimentacao") or self.request.GET.get("tipo")
        product_id = self.request.GET.get("produto_id")
        if tipo and _path_exists(MovimentacaoEstoque, "tipo"):
            qs = qs.filter(tipo=tipo)
        if product_id and _path_exists(MovimentacaoEstoque, "produto"):
            qs = qs.filter(produto_id=product_id)
        return qs
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        total_qty = qs.aggregate(total=Sum("quantidade"))["total"] or 0 if _path_exists(MovimentacaoEstoque, "quantidade") else 0
        ctx["kpis"] = [{"rotulo": "Movimentações", "valor": qs.count()}, {"rotulo": "Quantidade movimentada", "valor": _display(total_qty)}]
        ctx["tabelas"] = [_build_table(qs, MovimentacaoEstoque, self.fields, "Movimentações no período", 200)]
        ctx["filtros"] = {"tipo_movimentacao": self.request.GET.get("tipo_movimentacao", ""), "produto_id": self.request.GET.get("produto_id", "")}
        return ctx


class RelatorioVencimentosView(ModeloRelatorioView):
    model = ControleVencimento; titulo = "Vencimentos"; table_title = "Produtos por validade"
    show_date_filters = False
    fields = ("produto__nome_comercial", "data_vencimento", "quantidade"); date_fields = ("data_vencimento",)
    template_name = "relatorios/estoque/vencimentos.html"
    def get_queryset(self):
        qs = ControleVencimento.objects.all()
        if _path_exists(ControleVencimento, "produto__ativo"):
            qs = qs.filter(produto__ativo=True)
        situacao = self.request.GET.get("situacao", "todos")
        hoje = timezone.localdate()
        try: dias = max(0, min(3650, int(self.request.GET.get("dias_vencimento", 30))))
        except (TypeError, ValueError): dias = 30
        if _path_exists(ControleVencimento, "data_vencimento"):
            if situacao == "vencidos": qs = qs.filter(data_vencimento__lt=hoje)
            elif situacao == "vencendo": qs = qs.filter(data_vencimento__gte=hoje, data_vencimento__lte=hoje + timedelta(days=dias))
            elif situacao == "validos": qs = qs.filter(data_vencimento__gt=hoje + timedelta(days=dias))
        return _safe_order(qs, ControleVencimento, ("data_vencimento", "pk"))
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate(); qs = self.get_queryset(); rows = []
        for item in qs[:1000]:
            expiry = getattr(item, "data_vencimento", None)
            if isinstance(expiry, datetime): expiry = timezone.localtime(expiry).date() if timezone.is_aware(expiry) else expiry.date()
            days = (expiry - hoje).days if expiry else None
            product = getattr(item, "produto", None)
            qty = getattr(item, "quantidade", 0) or 0
            cost = getattr(product, "preco_custo", 0) or 0 if product else 0
            rows.append({"produto": str(getattr(product, "nome_comercial", None) or product or "—"), "validade": expiry, "dias": days, "quantidade": qty, "valor_estimado": qty * cost, "situacao": "Vencido" if days is not None and days < 0 else "A vencer" if days is not None and days <= 30 else "Válido"})
        ctx["tabelas"] = [_dict_table(rows, [("Produto", "produto"), ("Validade", "validade"), ("Dias até à validade", "dias"), ("Quantidade", "quantidade"), ("Valor estimado", "valor_estimado"), ("Situação", "situacao")], "Controlo de validade", 1000)]
        ctx["kpis"] = [{"rotulo": "Lotes/registos", "valor": len(rows)}, {"rotulo": "Vencidos", "valor": sum(1 for r in rows if r["situacao"] == "Vencido")}, {"rotulo": "A vencer em 30 dias", "valor": sum(1 for r in rows if r["situacao"] == "A vencer")}]
        ctx["filtros"] = {"situacao": self.request.GET.get("situacao", "todos"), "dias_vencimento": self.request.GET.get("dias_vencimento", "30")}
        return ctx


class RelatorioRupturaEstoqueView(RelatoriosEstoqueView):
    titulo = "Ruptura de Estoque"; template_name = "relatorios/estoque/ruptura.html"

    def get_queryset(self):
        qs = super().get_queryset()
        if _path_exists(Produto, "estoque_atual"):
            qs = qs.filter(estoque_atual__lte=0)
        return qs


class RelatorioGiroEstoqueView(RelatoriosEstoqueView):
    titulo = "Giro de Estoque"; template_name = "relatorios/estoque/giro.html"
    show_date_filters = False
    show_period_filter = True
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try: days = max(1, min(3650, int(self.request.GET.get("periodo", 90))))
        except (TypeError, ValueError): days = 90
        end = timezone.localdate(); start = end - timedelta(days=days - 1)
        sales = _grouped_items(start, end, [("ID", "produto__id"), ("Código", "produto__codigo_interno"), ("Produto", "produto__nome_comercial")], 1000)
        by_id = {row.get("produto__id"): row for row in sales}
        results = []
        qs = Produto.objects.all()
        if _path_exists(Produto, "ativo"): qs = qs.filter(ativo=True)
        category_id = self.request.GET.get("categoria_id")
        if category_id and _path_exists(Produto, "categoria"): qs = qs.filter(categoria_id=category_id)
        for product in qs[:1000]:
            sold = by_id.get(product.pk, {})
            qty = sold.get("quantidade_vendida", 0) or 0
            stock = getattr(product, "estoque_atual", 0) or 0
            daily = float(qty) / days
            turnover = float(qty) / float(stock) if stock else 0
            results.append({"codigo": getattr(product, "codigo_interno", "—"), "produto": getattr(product, "nome_comercial", str(product)), "stock": stock, "vendido": qty, "giro_periodo": round(turnover, 2), "giro_anualizado": round(turnover * 365 / days, 2), "dias_stock": round(float(stock) / daily, 1) if daily else "Sem vendas", "faturamento": sold.get("faturamento", 0)})
        results.sort(key=lambda row: row["giro_anualizado"], reverse=True)
        ctx["tabelas"] = [_dict_table(results, [("Código", "codigo"), ("Produto", "produto"), ("Stock", "stock"), ("Unidades vendidas", "vendido"), ("Giro no período", "giro_periodo"), ("Giro anualizado", "giro_anualizado"), ("Dias de stock estimados", "dias_stock"), ("Faturamento", "faturamento")], "Giro por produto", 1000)]
        ctx["kpis"] = [{"rotulo": "Produtos analisados", "valor": len(results)}, {"rotulo": "Produtos sem vendas", "valor": sum(1 for r in results if not r["vendido"])}, {"rotulo": "Período (dias)", "valor": days}]
        ctx["periodo"] = days
        return ctx


class RelatorioABCView(RelatoriosEstoqueView):
    titulo = "Análise ABC de Estoque"; template_name = "relatorios/estoque/abc.html"
    show_date_filters = False
    show_period_filter = True
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        criterio = self.request.GET.get("criterio", "faturamento")
        if criterio not in {"faturamento", "quantidade", "margem"}: criterio = "faturamento"
        try: days = max(1, min(3650, int(self.request.GET.get("periodo", 90))))
        except (TypeError, ValueError): days = 90
        end = timezone.localdate(); start = end - timedelta(days=days - 1)
        items = _items_sales_queryset(start, end)
        category_id = self.request.GET.get("categoria_id")
        if category_id and _path_exists(ItemVenda, "produto__categoria"): items = items.filter(produto__categoria_id=category_id)
        group_paths = [path for path in ("produto_id", "produto__codigo_interno", "produto__nome_comercial") if path != "produto_id" and _path_exists(ItemVenda, path)]
        if _path_exists(ItemVenda, "produto"): group_paths.insert(0, "produto")
        if not group_paths:
            rows = []
        else:
            rows = list(items.values(*group_paths).annotate(quantidade=Sum("quantidade"), faturamento=_item_revenue_expression()).order_by("-faturamento")[:5000])
        products = {p.pk: p for p in Produto.objects.filter(pk__in=[row.get("produto") for row in rows])} if rows and _path_exists(ItemVenda, "produto") else {}
        for row in rows:
            product = products.get(row.get("produto"))
            row["produto_nome"] = getattr(product, "nome_comercial", None) or row.get("produto__nome_comercial") or "—"
            row["codigo"] = getattr(product, "codigo_interno", None) or row.get("produto__codigo_interno") or "—"
            row["faturamento"] = row.get("faturamento") or 0
            row["quantidade"] = row.get("quantidade") or 0
            row["custo_estimado"] = (row["quantidade"] * (getattr(product, "preco_custo", 0) or 0)) if product else 0
            row["margem_estimada"] = row["faturamento"] - row["custo_estimado"]
            row["valor_classificacao"] = row["quantidade"] if criterio == "quantidade" else row["margem_estimada"] if criterio == "margem" else row["faturamento"]
        rows.sort(key=lambda row: row["valor_classificacao"], reverse=True)
        total = sum((row["valor_classificacao"] or 0) for row in rows)
        accumulated = 0
        for row in rows:
            accumulated += row["valor_classificacao"] or 0
            perc = float(accumulated / total * 100) if total else 0
            row["percentual_acumulado"] = round(perc, 2)
            row["participacao"] = round(float(row["valor_classificacao"] or 0) / float(total) * 100, 2) if total else 0
            row["classe"] = "A" if perc <= 80 else "B" if perc <= 95 else "C"
        ctx["tabelas"] = [_dict_table(rows, [("Código", "codigo"), ("Produto", "produto_nome"), ("Unidades", "quantidade"), ("Faturamento", "faturamento"), ("Custo estimado actual", "custo_estimado"), ("Margem estimada", "margem_estimada"), ("Valor de classificação", "valor_classificacao"), ("Participação (%)", "participacao"), ("Acumulado (%)", "percentual_acumulado"), ("Classe", "classe")], "Classificação ABC", 1000)]
        ctx["kpis"] = [{"rotulo": "Produtos classificados", "valor": len(rows)}, {"rotulo": "Classe A", "valor": sum(1 for r in rows if r["classe"] == "A")}, {"rotulo": "Classe B", "valor": sum(1 for r in rows if r["classe"] == "B")}, {"rotulo": "Classe C", "valor": sum(1 for r in rows if r["classe"] == "C")}]
        ctx["criterio"] = criterio; ctx["periodo"] = days; ctx["data_inicio"] = start; ctx["data_fim"] = end
        if criterio == "margem": ctx["aviso"] = "A margem é estimada com o preço de custo actual do produto, não com o custo histórico gravado na venda."
        return ctx


class RelatorioInventarioView(ModeloRelatorioView):
    model = Inventario; titulo = "Inventário de Estoque"; table_title = "Inventários"
    fields = ("numero", "titulo", "data_inicio", "data_fim", "status"); date_fields = ("data_inicio", "created_at")
    template_name = "relatorios/estoque/inventario.html"


class RelatoriosFinanceiroView(RelatorioBaseView):
    template_name = "relatorios/financeiro/dashboard.html"
    titulo = "Dashboard Financeiro"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        contas_receber = ContaReceber.objects.all()
        contas_pagar = ContaPagar.objects.all()
        movimentos = MovimentacaoFinanceira.objects.all()
        campos = []
        if _path_exists(ContaReceber, "valor_saldo"):
            recebivel = contas_receber.aggregate(v=Sum("valor_saldo"))["v"] or 0
        elif _path_exists(ContaReceber, "valor_original"):
            recebivel = contas_receber.aggregate(v=Sum("valor_original"))["v"] or 0
        else: recebivel = 0
        if _path_exists(ContaPagar, "valor_saldo"):
            pagavel = contas_pagar.aggregate(v=Sum("valor_saldo"))["v"] or 0
        elif _path_exists(ContaPagar, "valor_original"):
            pagavel = contas_pagar.aggregate(v=Sum("valor_original"))["v"] or 0
        else: pagavel = 0
        ctx["kpis"] = [
            {"rotulo": "Contas a receber", "valor": _display(recebivel)},
            {"rotulo": "Contas a pagar", "valor": _display(pagavel)},
            {"rotulo": "Movimentos financeiros", "valor": movimentos.count()},
            {"rotulo": "Data de referência", "valor": _display(hoje)},
        ]
        return ctx


class RelatorioFluxoCaixaView(ModeloRelatorioView):
    model = MovimentacaoFinanceira; titulo = "Fluxo de Caixa"; table_title = "Movimentações financeiras"
    fields = ("data_movimentacao", "tipo", "valor", "descricao", "centro_custo__nome", "confirmada")
    date_fields = ("data_movimentacao",); amount_fields = ("valor",); template_name = "relatorios/financeiro/fluxo_caixa.html"


class RelatorioContasReceberView(ModeloRelatorioView):
    model = ContaReceber; titulo = "Contas a Receber"; table_title = "Contas a receber"
    fields = ("cliente__nome_completo", "cliente__nome_social", "valor_original", "valor_saldo", "valor", "data_vencimento", "data_pagamento", "status")
    date_fields = ("data_vencimento", "created_at"); amount_fields = ("valor_saldo", "valor_original", "valor")
    template_name = "relatorios/financeiro/contas_receber.html"


class RelatorioContasPagarView(ModeloRelatorioView):
    model = ContaPagar; titulo = "Contas a Pagar"; table_title = "Contas a pagar"
    fields = ("fornecedor__nome", "valor_original", "valor_saldo", "valor", "data_vencimento", "data_pagamento", "status")
    date_fields = ("data_vencimento", "created_at"); amount_fields = ("valor_saldo", "valor_original", "valor")
    template_name = "relatorios/financeiro/contas_pagar.html"


class BaseRelatorioView(RelatorioBaseView):
    pass


class RelatorioDREView(RelatorioBaseView):
    titulo = "Demonstração de Resultados (DRE)"; template_name = "relatorios/financeiro/dre.html"
    show_date_filters = True
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "A DRE contabilística requer um plano de contas e lançamentos contabilísticos completos. Este relatório não inventa receitas, custos ou lucro a partir de movimentos incompletos."
        ctx["kpis"] = []
        return ctx


class RelatorioInadimplenciaView(RelatorioContasReceberView):
    titulo = "Relatório de Inadimplência"; template_name = "relatorios/financeiro/inadimplencia.html"
    def get_queryset(self):
        qs = super().get_queryset()
        if _path_exists(ContaReceber, "status"):
            qs = qs.filter(status="aberto")
        if _path_exists(ContaReceber, "data_vencimento"):
            qs = qs.filter(data_vencimento__lt=timezone.localdate())
        return qs


class RelatoriosClientesView(ModeloRelatorioView):
    model = Cliente; titulo = "Relatórios de Clientes"; table_title = "Clientes"
    fields = ("codigo_cliente", "nome_completo", "nome_social", "razao_social", "nif", "bi", "telefone", "email", "ativo")
    template_name = "relatorios/clientes/dashboard_clientes.html"


class RelatorioCadastrosClientesView(RelatoriosClientesView):
    titulo = "Novos Cadastros de Clientes"; template_name = "relatorios/clientes/cadastros.html"
    date_fields = ("created_at", "data_cadastro")


class RelatorioAniversariantesView(RelatoriosClientesView):
    titulo = "Aniversariantes"; template_name = "relatorios/clientes/aniversariantes.html"
    def get_queryset(self):
        qs = Cliente.objects.all()
        month = self.request.GET.get("mes")
        try: month = int(month) if month else timezone.localdate().month
        except (ValueError, TypeError): month = timezone.localdate().month
        if _path_exists(Cliente, "data_nascimento"):
            qs = qs.filter(data_nascimento__month=month)
        return _safe_order(qs, Cliente, ("data_nascimento", "nome_completo", "pk"))


class RelatorioComprasClientesView(RelatorioVendasClienteView):
    titulo = "Compras por Cliente"; template_name = "relatorios/clientes/compras.html"


class RelatorioFidelidadeView(RelatoriosClientesView):
    titulo = "Fidelidade de Clientes"; template_name = "relatorios/clientes/fidelidade.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "A análise de fidelidade será exacta quando as vendas estiverem ligadas pelo related_name configurado no model Venda. Consulte a lista de clientes e os seus registos de vendas no período."
        return ctx


class RelatorioSegmentacaoView(RelatoriosClientesView):
    titulo = "Segmentação de Clientes"; template_name = "relatorios/clientes/segmentacao.html"


class RelatoriosFuncionariosView(ModeloRelatorioView):
    model = Funcionario; titulo = "Relatórios de Funcionários"; table_title = "Funcionários"
    fields = ("id", "nome_completo", "usuario__username", "cargo__nome", "departamento__nome", "ativo")
    template_name = "relatorios/funcionarios/dashboard_funcionarios.html"


class RelatorioPontoView(ModeloRelatorioView):
    model = RegistroPonto; titulo = "Relatório de Ponto"; table_title = "Registos de ponto"
    fields = ("funcionario__id", "data", "entrada", "saida", "horas_trabalhadas", "estado")
    date_fields = ("data", "data_registo", "created_at"); template_name = "relatorios/funcionarios/ponto.html"


class RelatorioFolhaView(ModeloRelatorioView):
    model = FolhaPagamento; titulo = "Folha de Pagamento"; table_title = "Folhas de pagamento"
    fields = ("funcionario__id", "mes_referencia", "salario_base", "salario_liquido", "status")
    date_fields = ("mes_referencia", "created_at"); amount_fields = ("salario_liquido", "valor_liquido", "total")
    template_name = "relatorios/funcionarios/folha.html"


class RelatorioFeriasView(ModeloRelatorioView):
    model = Ferias; titulo = "Controlo de Férias"; table_title = "Férias"
    fields = ("funcionario__id", "data_inicio", "data_fim", "status"); date_fields = ("data_inicio",)
    template_name = "relatorios/funcionarios/ferias.html"


class RelatorioTreinamentosView(ModeloRelatorioView):
    model = Capacitacao; titulo = "Treinamentos"; table_title = "Capacitações"
    fields = ("nome", "titulo", "data_realizacao", "data_inicio", "data_fim", "carga_horaria")
    date_fields = ("data_realizacao", "data_inicio"); template_name = "relatorios/funcionarios/treinamentos.html"


class RelatorioPerformanceView(ModeloRelatorioView):
    model = AvaliacaoDesempenho; titulo = "Performance dos Funcionários"; table_title = "Avaliações"
    fields = ("funcionario__id", "data_avaliacao", "nota", "pontuacao", "avaliador__id")
    date_fields = ("data_avaliacao",); template_name = "relatorios/funcionarios/performance.html"


class RelatoriosFornecedoresView(ModeloRelatorioView):
    model = Fornecedor; titulo = "Relatórios de Fornecedores"; table_title = "Fornecedores"
    fields = ("codigo", "nome", "razao_social", "nif", "telefone", "email", "ativo")
    template_name = "relatorios/fornecedores/dashboard_fornecedores.html"


class RelatorioComprasView(ModeloRelatorioView):
    model = Compra; titulo = "Compras por Fornecedor"; table_title = "Compras"
    fields = ("id", "fornecedor__nome", "data", "total"); date_fields = ("data", "data_compra", "created_at")
    amount_fields = ("total",); template_name = "relatorios/fornecedores/compras.html"


class RelatorioPerformanceFornecedorView(ModeloRelatorioView):
    model = Fornecedor; titulo = "Performance de Fornecedores"; table_title = "Fornecedores"
    fields = ("codigo", "nome", "razao_social", "nif", "telefone", "email"); template_name = "relatorios/fornecedores/performance.html"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "Os models Compra/ItemCompra recebidos ainda não definem datas de entrega nem quantidades recebidas/defeituosas; esses indicadores não podem ser calculados sem adicionar esses campos ao domínio."
        return ctx


class RelatorioPrazosEntregaView(RelatorioPerformanceFornecedorView):
    titulo = "Prazos de Entrega"; template_name = "relatorios/fornecedores/prazos.html"


class RelatorioQualidadeFornecedorView(RelatorioPerformanceFornecedorView):
    titulo = "Qualidade de Fornecedores"; template_name = "relatorios/fornecedores/qualidade.html"


class AnalisesDashboardView(RelatorioBaseView):
    template_name = "relatorios/analises/dashboard_analises.html"; titulo = "Dashboard de Análises"


class AnaliseVendasView(RelatoriosVendasView):
    template_name = "relatorios/analises/vendas.html"; titulo = "Análise de Vendas"


class AnaliseLucratividadeView(RelatorioVendasProdutoView):
    template_name = "relatorios/analises/lucratividade.html"; titulo = "Análise de Lucratividade"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "A margem exacta deve usar o custo histórico de cada linha de venda. O model ItemVenda recebido não expõe um campo custo_unitario validado em todos os casos."
        return ctx


class KPIsDashboardView(RelatorioBaseView):
    template_name = "relatorios/kpis/dashboard_kpis.html"; titulo = "Dashboard de KPIs"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = MetricaKPI.objects.all().order_by("-data_referencia")
        ctx["tabelas"] = [_build_table(qs, MetricaKPI, ("codigo", "nome", "data_referencia", "valor_atual", "valor_meta", "variacao_percentual"), "Indicadores recentes", 30)]
        return ctx


class KPIsVendasView(RelatoriosVendasView):
    template_name = "relatorios/kpis/vendas.html"; titulo = "KPIs de Vendas"


class KPIsFinanceirosView(RelatoriosFinanceiroView):
    template_name = "relatorios/kpis/financeiros.html"; titulo = "KPIs Financeiros"


class KPIsOperacionaisView(RelatoriosEstoqueView):
    template_name = "relatorios/kpis/operacionais.html"; titulo = "KPIs Operacionais"


class KPIsPersonalizadosView(KPIsDashboardView):
    template_name = "relatorios/kpis/personalizados.html"; titulo = "KPIs Personalizados"


# ---------------------------------------------------------------------------
# Agendamentos, distribuição, histórico e auditoria
# ---------------------------------------------------------------------------
class AgendamentoListView(TenantLoginRequiredMixin, ListView):
    model = AgendamentoRelatorio; template_name = "agendamentos/lista.html"; context_object_name = "agendamentos"; paginate_by = 25
    def get_queryset(self): return AgendamentoRelatorio.objects.all().order_by("horario")


class AgendamentoCreateView(TenantLoginRequiredMixin, CreateView):
    model = AgendamentoRelatorio; template_name = "agendamentos/form.html"
    fields = tuple(field for field in ("template", "frequencia", "horario", "destinatarios", "ativo") if _path_exists(AgendamentoRelatorio, field))
    success_url = reverse_lazy("relatorios:agendamentos")
    def form_valid(self, form):
        messages.success(self.request, "Agendamento criado com sucesso.")
        return super().form_valid(form)


class AgendamentoDetailView(TenantLoginRequiredMixin, DetailView):
    model = AgendamentoRelatorio; template_name = "agendamentos/detalhe.html"; context_object_name = "agendamento"


class ExecutarAgendamentoView(TenantLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoRelatorio, pk=kwargs["pk"])
        try:
            from .tasks import executar_agendamento_individual_task
            executar_agendamento_individual_task.delay(agendamento.pk, connection.schema_name)
            messages.success(request, "A execução do agendamento foi colocada na fila.")
        except Exception:
            logger.exception("Não foi possível colocar o agendamento na fila Celery")
            messages.error(request, "Não foi possível iniciar a tarefa em segundo plano.")
        return redirect("relatorios:agendamento_detail", pk=agendamento.pk)


class AtivarAgendamentoView(TenantLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        obj = get_object_or_404(AgendamentoRelatorio, pk=kwargs["pk"]); obj.ativo = True; obj.save(update_fields=["ativo"])
        messages.success(request, "Agendamento activado."); return redirect("relatorios:agendamentos")


class DesativarAgendamentoView(TenantLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        obj = get_object_or_404(AgendamentoRelatorio, pk=kwargs["pk"]); obj.ativo = False; obj.save(update_fields=["ativo"])
        messages.warning(request, "Agendamento desactivado."); return redirect("relatorios:agendamentos")


class DistribuicaoRelatoriosView(RelatorioBaseView):
    template_name = "distribuicao/dashboard.html"; titulo = "Distribuição de Relatórios"


class EnvioEmailView(RelatorioBaseView):
    template_name = "distribuicao/envio_email.html"; titulo = "Enviar Relatório por E-mail"

    def post(self, request, *args, **kwargs):
        report_id = request.POST.get("relatorio_id")
        recipient = request.POST.get("email", "").strip()
        report = get_object_or_404(RelatorioGerado, pk=report_id, solicitante=request.user)
        if not recipient or "@" not in recipient:
            messages.error(request, "Indique um endereço de e-mail válido.")
            return redirect("relatorios:envio_email")
        if not report.arquivo_resultado:
            messages.error(request, "O relatório ainda não tem um ficheiro para anexar.")
            return redirect("relatorios:envio_email")
        try:
            report.arquivo_resultado.open("rb")
            try:
                payload = report.arquivo_resultado.read()
            finally:
                report.arquivo_resultado.close()
            filename = os.path.basename(str(report.arquivo_resultado.name)) or f"{report.codigo_relatorio}.bin"
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            email = EmailMessage(
                subject=f"Relatório {report.codigo_relatorio}",
                body="Segue em anexo o relatório solicitado.",
                to=[recipient],
            )
            email.attach(filename, payload, content_type)
            email.send(fail_silently=False)
            _create_log(request.user, "ENVIO", f"Envio do relatório {report.pk} para {recipient}")
            messages.success(request, "Relatório enviado por e-mail com o ficheiro anexado.")
        except Exception:
            logger.exception("Erro no envio de relatório por e-mail"); messages.error(request, "Falha ao enviar o e-mail.")
        return redirect("relatorios:envio_email")


class ImpressaoRelatoriosView(TenantLoginRequiredMixin, DetailView):
    model = RelatorioGerado; template_name = "distribuicao/impressao.html"; context_object_name = "relatorio"
    def get_queryset(self): return RelatorioGerado.objects.filter(solicitante=self.request.user)


class CompartilhamentoView(TenantLoginRequiredMixin, DetailView):
    model = RelatorioGerado; template_name = "distribuicao/compartilhamento.html"
    def get_queryset(self): return RelatorioGerado.objects.filter(solicitante=self.request.user)


class HistoricoRelatoriosView(TenantLoginRequiredMixin, ListView):
    model = LogAtividade; template_name = "historico/lista.html"; context_object_name = "logs"; paginate_by = 25
    def get_queryset(self): return LogAtividade.objects.all().order_by("-pk")


class AuditoriaRelatoriosView(HistoricoRelatoriosView):
    template_name = "historico/lista.html"
    def get_queryset(self):
        qs = LogAtividade.objects.all()
        if _path_exists(LogAtividade, "tipo"): qs = qs.filter(tipo__icontains="AUDITORIA")
        return _safe_order(qs, LogAtividade, ("timestamp", "created_at", "pk"))


class LogsRelatoriosView(HistoricoRelatoriosView):
    template_name = "historico/lista_completa.html"; paginate_by = 50


class LogAcessoRelatoriosView(HistoricoRelatoriosView):
    template_name = "historico/lista.html"
    def get_queryset(self):
        qs = LogAtividade.objects.all()
        if _path_exists(LogAtividade, "acao"): qs = qs.filter(acao__icontains="acesso")
        return _safe_order(qs, LogAtividade, ("timestamp", "created_at", "pk"))


# ---------------------------------------------------------------------------
# Exportações reais: sem dados fictícios e sempre limitadas ao utilizador.
# ---------------------------------------------------------------------------
class BaseExportView(TenantLoginRequiredMixin, View):
    def get_relatorio(self, pk):
        return get_object_or_404(RelatorioGerado, pk=pk, solicitante=self.request.user)

    def get_dados(self, pk):
        report = self.get_relatorio(pk)
        return _normalise_rows(_report_payload(report))


class ExportarPDFView(BaseExportView):
    def get(self, request, *args, **kwargs):
        rows = self.get_dados(kwargs["pk"])
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            stream = BytesIO(); doc = SimpleDocTemplate(stream, pagesize=landscape(A4))
            styles = getSampleStyleSheet(); story = [Paragraph("Relatório VistoGEST", styles["Title"]), Spacer(1, 12)]
            if rows:
                headers = list(rows[0].keys()); data = [headers] + [[row.get(h, "") for h in headers] for row in rows]
                table = Table(data, repeatRows=1)
                table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16345f")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.grey), ("VALIGN", (0,0), (-1,-1), "TOP")])); story.append(table)
            else: story.append(Paragraph("Este relatório não contém linhas de dados.", styles["BodyText"]))
            doc.build(story); response = HttpResponse(stream.getvalue(), content_type="application/pdf")
        except ImportError:
            return HttpResponse("A biblioteca reportlab é necessária para exportar PDF.", status=501, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="relatorio_{kwargs["pk"]}.pdf"'
        return response


class ExportarExcelView(BaseExportView):
    def get(self, request, *args, **kwargs):
        from openpyxl import Workbook
        rows = self.get_dados(kwargs["pk"]); book = Workbook(); sheet = book.active; sheet.title = "Relatório"
        headers = list(rows[0].keys()) if rows else ["Informação"]
        sheet.append(headers)
        for row in rows: sheet.append([row.get(h, "") for h in headers])
        output = BytesIO(); book.save(output)
        response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="relatorio_{kwargs["pk"]}.xlsx"'; return response


class ExportarCSVView(BaseExportView):
    def get(self, request, *args, **kwargs):
        rows = self.get_dados(kwargs["pk"]); output = StringIO(); headers = list(rows[0].keys()) if rows else ["Informação"]
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore"); writer.writeheader()
        for row in rows: writer.writerow(row)
        response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="relatorio_{kwargs["pk"]}.csv"'; return response


class ExportarXMLView(BaseExportView):
    def get(self, request, *args, **kwargs):
        rows = self.get_dados(kwargs["pk"]); root = ET.Element("relatorio")
        for row in rows:
            row_node = ET.SubElement(root, "registo")
            for key, value in row.items():
                node = ET.SubElement(row_node, "campo", nome=str(key)); node.text = str(value)
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        response = HttpResponse(payload, content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="relatorio_{kwargs["pk"]}.xml"'; return response


class ExportarJSONView(BaseExportView):
    def get(self, request, *args, **kwargs):
        response = JsonResponse(self.get_dados(kwargs["pk"]), safe=False, json_dumps_params={"indent": 2, "ensure_ascii": False})
        response["Content-Disposition"] = f'attachment; filename="relatorio_{kwargs["pk"]}.json"'; return response


# ---------------------------------------------------------------------------
# BI / data mining. Use only existing relations and display safe fallbacks.
# ---------------------------------------------------------------------------
class BusinessIntelligenceView(RelatorioBaseView):
    template_name = "bi/dashboard.html"; titulo = "Business Intelligence"


class CubosOLAPView(RelatoriosVendasView):
    template_name = "bi/cubos_olap.html"; titulo = "Cubo OLAP de Vendas"


class DataMiningView(RelatorioBaseView):
    template_name = "bi/data_mining.html"; titulo = "Segmentação de Clientes"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "A segmentação estatística exige uma fonte de features com vendas relacionadas pelo related_name correcto. Esta página evita calcular clusters com campos inexistentes."
        ctx["tabelas"] = [_build_table(Cliente.objects.all().order_by("pk"), Cliente, ("codigo_cliente", "nome_completo", "nome_social", "created_at"), "Clientes disponíveis", 50)]
        return ctx


class PrevisoesView(RelatoriosVendasView):
    template_name = "bi/previsoes.html"; titulo = "Previsões de Vendas"
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["aviso"] = "A previsão temporal será activada quando existirem séries mensais completas e validadas. Uma previsão não é calculada com datas/campos de venda não confirmados."
        return ctx


# ---------------------------------------------------------------------------
# AJAX, API e configurações
# ---------------------------------------------------------------------------
class GerarRelatorioAjaxView(TenantLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        tipo_id = request.POST.get("tipo_relatorio_id") or request.POST.get("tipo")
        tipo = get_object_or_404(TipoRelatorio, pk=tipo_id, ativo=True) if str(tipo_id).isdigit() else None
        if tipo is None:
            return JsonResponse({"status": "erro", "mensagem": "Seleccione um tipo de relatório válido."}, status=400)
        start = parse_date(request.POST.get("data_inicio", "")); end = parse_date(request.POST.get("data_fim", ""))
        if start and end and start > end:
            return JsonResponse({"status": "erro", "mensagem": "A data inicial não pode ser posterior à data final."}, status=400)
        report = RelatorioGerado.objects.create(tipo_relatorio=tipo, solicitante=request.user, data_inicio=start, data_fim=end,
            formato=request.POST.get("formato", "html"), parametros={k: v for k, v in request.POST.items() if k not in {"csrfmiddlewaretoken"}})
        try:
            from .tasks import processar_relatorio_task
            task = processar_relatorio_task.delay(report.pk, connection.schema_name)
            return JsonResponse({"status": "iniciado", "relatorio_id": report.pk, "task_id": task.id, "codigo": report.codigo_relatorio}, status=202)
        except Exception:
            logger.exception("Celery indisponível ao gerar relatório")
            return JsonResponse({"status": "criado", "relatorio_id": report.pk, "codigo": report.codigo_relatorio, "mensagem": "Relatório criado; a fila Celery não confirmou o processamento."}, status=202)


class PreviewRelatorioView(TenantLoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        model_key = request.GET.get("modelo", "vendas.venda")
        available = {f"{m._meta.app_label}.{m._meta.model_name}": m for m in (Venda, ItemVenda, Produto, Cliente, Compra, Fornecedor)}
        model = available.get(model_key)
        if model is None: return JsonResponse({"erro": "Modelo não permitido."}, status=400)
        rows = []
        for obj in model.objects.all().order_by("-pk")[:5]:
            rows.append({field.name: _display(getattr(obj, field.name, None)) for field in _model_fields(model)[:12]})
        return JsonResponse({"modelo": model_key, "total_preview": len(rows), "dados": rows})


class ValidarCamposView(TenantLoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        email = request.GET.get("email", "").strip()
        valid = True; message = ""
        if email and _path_exists(Cliente, "email"):
            exists = Cliente.objects.filter(email__iexact=email).exists()
            valid = not exists; message = "Este e-mail já está associado a um cliente." if exists else ""
        return JsonResponse({"is_valid": valid, "message": message})


class BuscarDadosView(TenantLoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        qs = Cliente.objects.all()
        conditions = []
        for field in ("nome_completo", "nome_social", "razao_social", "nif", "bi", "telefone", "email"):
            if _path_exists(Cliente, field): conditions.append(Q(**{f"{field}__icontains": query}))
        if query and conditions:
            combined = conditions[0]
            for cond in conditions[1:]: combined |= cond
            qs = qs.filter(combined)
        results = []
        for obj in qs.order_by("pk")[:10]:
            results.append({"id": obj.pk, "label": str(getattr(obj, "nome_exibicao", None) or getattr(obj, "nome_completo", None) or getattr(obj, "razao_social", None) or obj)})
        return JsonResponse(results, safe=False)


class ConfiguracoesRelatoriosView(RelatorioBaseView):
    template_name = "templates/relatorios/config_dashboard.html"; titulo = "Configurações de Relatórios"


class ConfiguracoesFormatosView(RelatorioBaseView):
    template_name = "templates/relatorios/config_formatos.html"; titulo = "Formatos de Exportação"


class ConfiguracoesPermissoesView(RelatorioBaseView):
    template_name = "templates/relatorios/config_permissoes.html"; titulo = "Permissões de Relatórios"


class GerarRelatorioAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, format=None):
        if connection.schema_name == "public": return Response({"detail": "Endpoint disponível apenas no schema tenant."}, status=status.HTTP_403_FORBIDDEN)
        tipo_id = request.data.get("tipo_relatorio_id") or request.data.get("tipo")
        try: tipo = TipoRelatorio.objects.get(pk=tipo_id, ativo=True)
        except (TipoRelatorio.DoesNotExist, TypeError, ValueError): return Response({"detail": "Tipo de relatório inválido."}, status=status.HTTP_400_BAD_REQUEST)
        report = RelatorioGerado.objects.create(tipo_relatorio=tipo, solicitante=request.user,
            data_inicio=parse_date(str(request.data.get("data_inicio", ""))), data_fim=parse_date(str(request.data.get("data_fim", ""))),
            formato=request.data.get("formato", "json"), parametros=dict(request.data))
        try:
            from .tasks import processar_relatorio_task
            task = processar_relatorio_task.delay(report.pk, connection.schema_name); task_id = task.id
        except Exception:
            logger.exception("Celery indisponível ao gerar relatório via API"); task_id = None
        return Response({"status": "criado", "relatorio_id": report.pk, "codigo": report.codigo_relatorio, "task_id": task_id}, status=status.HTTP_202_ACCEPTED)


class DadosGraficoAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, format=None):
        if connection.schema_name == "public": return Response({"detail": "Endpoint disponível apenas no schema tenant."}, status=status.HTTP_403_FORBIDDEN)
        if not _path_exists(Venda, "data_venda") or not _path_exists(Venda, "total"):
            return Response({"labels": [], "data": []})
        from django.db.models.functions import TruncMonth
        qs = Venda.objects.annotate(mes=TruncMonth("data_venda")).values("mes").annotate(total=Sum("total")).order_by("mes")
        return Response({"labels": [item["mes"].strftime("%Y-%m") for item in qs if item["mes"]], "data": [float(item["total"] or 0) for item in qs]})


class EstatisticasAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, format=None):
        if connection.schema_name == "public": return Response({"detail": "Endpoint disponível apenas no schema tenant."}, status=status.HTTP_403_FORBIDDEN)
        total_vendas = Venda.objects.aggregate(total=Sum("total"))["total"] or 0 if _path_exists(Venda, "total") else 0
        venda_count = Venda.objects.count()
        novos_clientes = Cliente.objects.filter(created_at__month=timezone.localdate().month).count() if _path_exists(Cliente, "created_at") else Cliente.objects.count()
        return Response({"total_vendas_geral": float(total_vendas), "numero_vendas": venda_count, "novos_clientes_este_mes": novos_clientes, "ticket_medio": round(float(total_vendas) / venda_count, 2) if venda_count else 0})


# Compatibilidade com nomes de endpoints antigos que podem existir em urls.py.
TemplateRelatorioUpdateView = EditarRelatorioView


def gerar_relatorio_corporativo(request):
    """Gera um PDF simples a partir de vendas reais do tenant, nunca dados de exemplo."""
    if not request.user.is_authenticated:
        return redirect("/contas/login/")
    if connection.schema_name == "public":
        return HttpResponseForbidden("Relatórios indisponíveis no schema public.")
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        rows = list(Venda.objects.order_by("-data_venda").values_list("numero_documento", "data_venda", "total", "status")[:100]) if _path_exists(Venda, "data_venda") else []
        stream = BytesIO(); doc = SimpleDocTemplate(stream, pagesize=landscape(A4)); styles = getSampleStyleSheet()
        story = [Paragraph("Relatório Corporativo — VistoGEST", styles["Title"]), Spacer(1, 12)]
        data = [["Documento", "Data", "Total", "Estado"]]
        for number, dt, total, state in rows: data.append([str(number or "—"), _display(dt), _display(total), str(state or "—")])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#16345f")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID", (0,0), (-1,-1), .4, colors.grey)]))
        story.append(table); doc.build(story)
        response = HttpResponse(stream.getvalue(), content_type="application/pdf"); response["Content-Disposition"] = "attachment; filename=relatorio_corporativo.pdf"; return response
    except ImportError:
        return HttpResponse("A biblioteca reportlab é necessária para gerar PDF.", status=501)


# Aliases de compatibilidade para rotas existentes em projectos que usavam nomes
# ligeiramente diferentes.
RelatoriosVendasDashboardView = RelatoriosVendasView
RelatoriosEstoqueDashboardView = RelatoriosEstoqueView
RelatoriosFinanceiroDashboardView = RelatoriosFinanceiroView
RelatoriosClientesDashboardView = RelatoriosClientesView
RelatoriosFuncionariosDashboardView = RelatoriosFuncionariosView
RelatoriosFornecedoresDashboardView = RelatoriosFornecedoresView
