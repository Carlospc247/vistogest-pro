# apps/fiscal/web_views.py
"""Views web da área fiscal, separadas das views da API.

Adiciona uma camada web consistente sem substituir os ViewSets/API/webhooks já
existentes em apps.fiscal.views. Todas as queries de modelos com FK Empresa são
filtradas pela empresa do utilizador; modelos singleton/tenant-local são lidos
no esquema actual.
"""
from datetime import date
from decimal import Decimal
from inspect import signature

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, connection
from django.db.models import DateTimeField, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from .forms_web import DateRangeForm, DocumentoFiscalWebForm, RetencaoFonteWebForm, TaxaIVAWebForm
from .views import PermissaoAcaoMixin
from .models import (
    AssinaturaDigital,
    DocumentoFiscal,
    DocumentoFiscalLinha,
    RetencaoFonte,
    SAFTExport,
    TaxaIVAAGT,
)
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import render
from django.views import View




# ---------------------------------------------------------------------------
# Helpers de compatibilidade de campos e isolamento
# ---------------------------------------------------------------------------
def _field_exists(model, name):
    try:
        model._meta.get_field(name)
        return True
    except (FieldDoesNotExist, AttributeError):
        return False


def _empresa_do_utilizador(user):
    empresa = getattr(user, "empresa", None)
    if empresa is not None:
        return empresa
    funcionario = getattr(user, "funcionario", None)
    return getattr(funcionario, "empresa", None) if funcionario else None


def _exigir_empresa(request):
    """Resolve a empresa pelo schema activo e rejeita vínculos cruzados."""
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise PermissionDenied("Esta operação fiscal só está disponível no schema de um tenant.")

    empresa_utilizador = _empresa_do_utilizador(request.user)
    tenant_actual = getattr(connection, "tenant", None)

    if tenant_actual is not None and getattr(tenant_actual, "schema_name", None) == schema_actual:
        if empresa_utilizador is not None:
            schema_utilizador = getattr(empresa_utilizador, "schema_name", None)
            if schema_utilizador and schema_utilizador != schema_actual:
                raise PermissionDenied("O utilizador está associado a uma empresa diferente do tenant activo.")
            if getattr(empresa_utilizador, "pk", None) != getattr(tenant_actual, "pk", None):
                raise PermissionDenied("O vínculo do utilizador não corresponde ao tenant activo.")
        return tenant_actual

    if empresa_utilizador is not None and getattr(empresa_utilizador, "schema_name", None) == schema_actual:
        return empresa_utilizador

    raise PermissionDenied("O utilizador não está associado ao tenant activo.")


def _por_empresa(queryset, model, empresa, *, relacoes=()):
    """Filtra sempre por empresa quando o modelo/relacionamento o suporta."""
    if _field_exists(model, "empresa"):
        return queryset.filter(empresa=empresa)
    for relation in relacoes:
        related_model = None
        try:
            related_model = model._meta.get_field(relation).related_model
        except (FieldDoesNotExist, AttributeError):
            continue
        if related_model and _field_exists(related_model, "empresa"):
            return queryset.filter(**{f"{relation}__empresa": empresa})
    # É aceitável somente para modelos sem Empresa que sejam garantidamente
    # tenant-local pelo django-tenants. O chamador limita-se a estes modelos.
    return queryset


def _ordenar_se_disponivel(queryset, model, *fields):
    chosen = [name for name in fields if _field_exists(model, name)]
    return queryset.order_by(*chosen) if chosen else queryset.order_by("pk")


def _campo_estado(model):
    if _field_exists(model, "estado"):
        return "estado"
    if _field_exists(model, "status"):
        return "status"
    return None


def _escolhas_estado(model):
    name = _campo_estado(model)
    if not name:
        return []
    return list(model._meta.get_field(name).choices or [])


def _pesquisa_documentos(qs, termo):
    if not termo:
        return qs
    model = qs.model
    campos = ("numero", "numero_documento", "nif_cliente", "nome_cliente", "cliente_nome", "atcud", "tipo_documento")
    query = Q()
    aplicou = False
    for name in campos:
        if _field_exists(model, name):
            query |= Q(**{f"{name}__icontains": termo})
            aplicou = True
    if _field_exists(model, "cliente"):
        try:
            related = model._meta.get_field("cliente").related_model
            for candidate in ("nome", "razao_social", "nif"):
                if related and _field_exists(related, candidate):
                    query |= Q(**{f"cliente__{candidate}__icontains": termo})
                    aplicou = True
        except (FieldDoesNotExist, AttributeError):
            pass
    return qs.filter(query) if aplicou else qs.none()


def _retencoes_empresa(empresa):
    qs = RetencaoFonte.objects.all()
    # Este modelo pode não ter FK Empresa: preferir a empresa do fornecedor ou
    # da conta a pagar; em tenant schemas separados, o queryset já é isolado.
    if _field_exists(RetencaoFonte, "empresa"):
        return qs.filter(empresa=empresa)
    if _field_exists(RetencaoFonte, "fornecedor") and _field_exists(RetencaoFonte._meta.get_field("fornecedor").related_model, "empresa"):
        return qs.filter(fornecedor__empresa=empresa)
    if _field_exists(RetencaoFonte, "conta_pagar") and _field_exists(RetencaoFonte._meta.get_field("conta_pagar").related_model, "empresa"):
        return qs.filter(conta_pagar__empresa=empresa)
    # A app é tenant-local segundo a arquitectura descrita. Não há FK Empresa
    # para filtrar em tenants distintos; o middleware django-tenants isola schema.
    return qs


def _assinar_estado_configuracao(configuracao):
    for name in ("configurada", "esta_configurada", "is_configured"):
        value = getattr(configuracao, name, None)
        if value is not None:
            return bool(value() if callable(value) else value)
    return bool(
        getattr(configuracao, "nif_contribuinte", None)
        and getattr(configuracao, "chave_contribuinte_privada", None)
        and getattr(configuracao, "chave_contribuinte_publica", None)
    )


# ---------------------------------------------------------------------------
# Dashboard e documentos
# ---------------------------------------------------------------------------
class FiscalDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "acessar_dashboard_fiscal"
    template_name = "fiscal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        docs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        taxas = _por_empresa(TaxaIVAAGT.objects.all(), TaxaIVAAGT, empresa)
        retencoes = _retencoes_empresa(empresa)
        state_field = _campo_estado(DocumentoFiscal)
        draft_values = []
        if state_field:
            choices = {value for value, _label in DocumentoFiscal._meta.get_field(state_field).choices}
            draft_values = [value for value in ("draft", "rascunho") if value in choices]
        rascunhos = docs.filter(**{f"{state_field}__in": draft_values}).count() if state_field and draft_values else 0
        ativo_field = "ativo" if _field_exists(TaxaIVAAGT, "ativo") else None
        context.update({
            "empresa": empresa,
            "total_documentos": docs.count(),
            "documentos_rascunho": rascunhos,
            "total_retencoes": retencoes.count(),
            "taxas_ativas": taxas.filter(ativo=True).count() if ativo_field else 0,
            "documentos_recentes": _ordenar_se_disponivel(docs, DocumentoFiscal, "-data_emissao", "-created_at", "-pk")[:8],
            "novo_documento_url": reverse_lazy("fiscal:documento_novo"),
        })
        return context


class DocumentoFiscalListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = "acessar_painel_principal_fiscal"
    template_name = "fiscal/documentos/lista.html"
    context_object_name = "documentos"
    paginate_by = 25

    def get_queryset(self):
        empresa = _exigir_empresa(self.request)
        qs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        qs = _pesquisa_documentos(qs, self.request.GET.get("q", "").strip())
        estado = self.request.GET.get("estado")
        state_field = _campo_estado(DocumentoFiscal)
        if estado and state_field:
            qs = qs.filter(**{state_field: estado})
        return _ordenar_se_disponivel(qs, DocumentoFiscal, "-data_emissao", "-created_at", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["estados"] = _escolhas_estado(DocumentoFiscal)
        context["novo_documento_url"] = reverse_lazy("fiscal:documento_novo")
        return context


class DocumentoFiscalDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = "acessar_painel_principal_fiscal"
    template_name = "fiscal/documentos/detalhe.html"
    context_object_name = "documento"
    model = DocumentoFiscal

    def get_queryset(self):
        empresa = _exigir_empresa(self.request)
        return _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        doc = self.object
        linhas = getattr(doc, "linhas", None)
        if linhas is not None and hasattr(linhas, "all"):
            context["linhas"] = linhas.all()
        else:
            context["linhas"] = DocumentoFiscalLinha.objects.filter(documento=doc)
        return context


class DocumentoFiscalCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = "acessar_painel_principal_fiscal"
    model = DocumentoFiscal
    form_class = DocumentoFiscalWebForm
    template_name = "fiscal/documentos/formulario.html"
    success_url = reverse_lazy("fiscal:documentos")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        return kwargs

    def form_valid(self, form):
        empresa = _exigir_empresa(self.request)
        obj = form.save(commit=False)
        if _field_exists(DocumentoFiscal, "empresa"):
            obj.empresa = empresa
        if _field_exists(DocumentoFiscal, "usuario_criacao"):
            obj.usuario_criacao = self.request.user
        elif _field_exists(DocumentoFiscal, "criado_por"):
            obj.criado_por = self.request.user
        elif _field_exists(DocumentoFiscal, "created_by"):
            obj.created_by = self.request.user
        if _field_exists(DocumentoFiscal, "origem") and not obj.origem:
            obj.origem = "manual"
        state_field = _campo_estado(DocumentoFiscal)
        if state_field and not getattr(obj, state_field, None):
            field = DocumentoFiscal._meta.get_field(state_field)
            values = {v for v, _ in field.choices}
            for initial in ("rascunho", "draft"):
                if initial in values:
                    setattr(obj, state_field, initial)
                    break
        try:
            obj.save()
            form.save_m2m()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Documento guardado como rascunho. Valide-o antes de confirmar.")
        return redirect("fiscal:documento_detalhe", pk=obj.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Novo documento fiscal"
        return context


class DocumentoFiscalUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = "acessar_painel_principal_fiscal"
    model = DocumentoFiscal
    form_class = DocumentoFiscalWebForm
    template_name = "fiscal/documentos/formulario.html"
    success_url = reverse_lazy("fiscal:documentos")

    def get_queryset(self):
        empresa = _exigir_empresa(self.request)
        qs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        state_field = _campo_estado(DocumentoFiscal)
        if state_field:
            # A edição web fica limitada a rascunhos; documentos confirmados são imutáveis.
            allowed = [value for value in ("rascunho", "draft") if value in {v for v, _ in DocumentoFiscal._meta.get_field(state_field).choices}]
            if allowed:
                qs = qs.filter(**{f"{state_field}__in": allowed})
        return qs

    def form_valid(self, form):
        try:
            form.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Rascunho actualizado.")
        return redirect("fiscal:documento_detalhe", pk=self.object.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["titulo"] = "Editar rascunho"
        return context


# ---------------------------------------------------------------------------
# Taxas de imposto
# ---------------------------------------------------------------------------
class TaxaIVAListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = "ver_taxas_iva"
    template_name = "fiscal/taxas_iva/lista.html"
    context_object_name = "taxas"
    paginate_by = 50

    def get_queryset(self):
        empresa = _exigir_empresa(self.request)
        qs = _por_empresa(TaxaIVAAGT.objects.all(), TaxaIVAAGT, empresa)
        termo = self.request.GET.get("q", "").strip()
        if termo:
            qs = qs.filter(Q(nome__icontains=termo) | Q(tax_code__icontains=termo) | Q(tax_type__icontains=termo))
        if self.request.GET.get("ativas") and _field_exists(TaxaIVAAGT, "ativo"):
            qs = qs.filter(ativo=True)
        return qs.order_by("nome", "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["taxa_nova_url"] = reverse_lazy("fiscal:taxa_iva_nova")
        return context


class TaxaIVACreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = "criar_taxas_iva"
    model = TaxaIVAAGT
    form_class = TaxaIVAWebForm
    template_name = "fiscal/taxas_iva/formulario.html"
    success_url = reverse_lazy("fiscal:taxas_iva")

    def form_valid(self, form):
        # TaxaIVAAGT não possui FK Empresa: o schema activo já isola os registos.
        _exigir_empresa(self.request)
        obj = form.save(commit=False)
        try:
            obj.full_clean()
            obj.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Taxa de imposto criada.")
        return redirect(self.success_url)


class TaxaIVAUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = "criar_taxas_iva"
    model = TaxaIVAAGT
    form_class = TaxaIVAWebForm
    template_name = "fiscal/taxas_iva/formulario.html"
    success_url = reverse_lazy("fiscal:taxas_iva")

    def get_queryset(self):
        return _por_empresa(TaxaIVAAGT.objects.all(), TaxaIVAAGT, _exigir_empresa(self.request))

    def form_valid(self, form):
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            obj.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Taxa de imposto actualizada.")
        return redirect(self.success_url)


# ---------------------------------------------------------------------------
# Retenções na fonte
# ---------------------------------------------------------------------------
class RetencaoFonteListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = "gerir_retencoes_na_fonte"
    template_name = "fiscal/retencoes/lista.html"
    context_object_name = "retencoes"
    paginate_by = 25

    def get_queryset(self):
        empresa = _exigir_empresa(self.request)
        qs = _retencoes_empresa(empresa)
        termo = self.request.GET.get("q", "").strip()
        if termo:
            query = Q()
            applied = False
            for field in ("referencia_documento", "documento_referencia", "tipo_retencao", "codigo_imposto"):
                if _field_exists(RetencaoFonte, field):
                    query |= Q(**{f"{field}__icontains": termo})
                    applied = True
            if _field_exists(RetencaoFonte, "fornecedor"):
                for field in ("nome", "razao_social", "nif"):
                    if _field_exists(RetencaoFonte._meta.get_field("fornecedor").related_model, field):
                        query |= Q(**{f"fornecedor__{field}__icontains": termo})
                        applied = True
            qs = qs.filter(query) if applied else qs.none()
        return _ordenar_se_disponivel(qs, RetencaoFonte, "-data_retencao", "-created_at", "-pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["retencao_nova_url"] = reverse_lazy("fiscal:retencao_nova")
        return context


class RetencaoFonteCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = "criar_retencoes_na_fonte"
    model = RetencaoFonte
    form_class = RetencaoFonteWebForm
    template_name = "fiscal/retencoes/formulario.html"
    success_url = reverse_lazy("fiscal:retencoes")

    def form_valid(self, form):
        try:
            obj = form.save(commit=False)
            if _field_exists(RetencaoFonte, "criado_por"):
                obj.criado_por = self.request.user
            # O valor é calculado antes de full_clean porque não é editável no formulário.
            obj.valor_retido = (obj.valor_base * obj.taxa_retencao / Decimal("100.00")).quantize(Decimal("0.01"))
            obj.full_clean()
            # A transação evita gravação parcial durante o registo.
            with transaction.atomic():
                obj.save()
        except (ValidationError, ValueError, AttributeError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Retenção registada.")
        return redirect(self.success_url)


class RetencaoFonteUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = "criar_retencoes_na_fonte"
    model = RetencaoFonte
    form_class = RetencaoFonteWebForm
    template_name = "fiscal/retencoes/formulario.html"
    success_url = reverse_lazy("fiscal:retencoes")

    def get_queryset(self):
        return _retencoes_empresa(_exigir_empresa(self.request))

    def form_valid(self, form):
        try:
            obj = form.save(commit=False)
            obj.valor_retido = (obj.valor_base * obj.taxa_retencao / Decimal("100.00")).quantize(Decimal("0.01"))
            obj.full_clean()
            with transaction.atomic():
                obj.save()
        except (ValidationError, ValueError, AttributeError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Retenção actualizada.")
        return redirect(self.success_url)


# ---------------------------------------------------------------------------
# Detalhe/exclusão e acções de retenção, sempre limitados ao schema activo
# ---------------------------------------------------------------------------
class TaxaIVADetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = "ver_taxas_iva"
    model = TaxaIVAAGT
    template_name = "fiscal/taxaiva_detail.html"
    context_object_name = "taxa"

    def get_queryset(self):
        _exigir_empresa(self.request)
        return TaxaIVAAGT.objects.all()


class TaxaIVADeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = "apagar_taxas_iva"
    model = TaxaIVAAGT
    template_name = "fiscal/taxaiva_confirm_delete.html"
    context_object_name = "taxa"
    success_url = reverse_lazy("fiscal:taxas_iva")

    def get_queryset(self):
        _exigir_empresa(self.request)
        return TaxaIVAAGT.objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Taxa de imposto eliminada.")
        return super().form_valid(form)


class RetencaoFonteDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = "gerir_retencoes_na_fonte"
    model = RetencaoFonte
    template_name = "fiscal/retencao_detail.html"
    context_object_name = "retencao"

    def get_queryset(self):
        return _retencoes_empresa(_exigir_empresa(self.request))


class RetencaoFonteDeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = "apagar_retencoes_na_fonte"
    model = RetencaoFonte
    template_name = "fiscal/retencao_confirm_delete.html"
    context_object_name = "retencao"
    success_url = reverse_lazy("fiscal:retencoes")

    def get_queryset(self):
        return _retencoes_empresa(_exigir_empresa(self.request))

    def form_valid(self, form):
        messages.success(self.request, "Retenção eliminada.")
        return super().form_valid(form)


class RetencaoMarcarPagaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "marcar_retencoes_como_pago"
    def post(self, request, *args, **kwargs):
        empresa = _exigir_empresa(request)
        retencao = get_object_or_404(_retencoes_empresa(empresa), pk=kwargs["pk"])
        try:
            from .services.utils import RetencaoFonteService, FiscalServiceError
            actualizada = RetencaoFonteService.processar_pagamento_estado(retencao.pk, timezone.localdate())
            if actualizada is None:
                raise FiscalServiceError("O serviço não devolveu a retenção actualizada.")
            messages.success(request, "Pagamento da retenção registado.")
        except Exception as exc:
            messages.error(request, f"Não foi possível confirmar o pagamento: {exc}")
        return redirect("fiscal:retencoes")


# ---------------------------------------------------------------------------
# Configuração, relatórios, SAF-T, integridade e homologação
# ---------------------------------------------------------------------------
"""

class AssinaturaDigitalView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "ver_status_atual_assinatura_digital"
    template_name = "fiscal/assinatura_digital.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # AssinaturaDigital é um singleton por tenant; não filtrar por empresa_id.
        get_solo = getattr(AssinaturaDigital, "get_solo", None)
        if callable(get_solo):
            configuracao = get_solo()
        else:
            manager_get_solo = getattr(AssinaturaDigital.objects, "get_solo", None)
            configuracao = manager_get_solo() if callable(manager_get_solo) else AssinaturaDigital.objects.filter(pk=1).first()
        context["configuracao"] = configuracao
        context["configurado"] = _assinar_estado_configuracao(configuracao) if configuracao else False
        return context

    def post(self, request, *args, **kwargs):
        messages.warning(request, "A alteração de chaves deve ser feita pelo fluxo seguro de assinatura digital; este ecrã não recebe nem exibe chaves privadas.")
        return redirect("fiscal:assinatura_digital")

"""
class RelatoriosFiscaisView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView,):
    acao_requerida = "ver_relatorio_fiscal"
    template_name = "fiscal/relatorios/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        empresa = _exigir_empresa(self.request)

        docs = _por_empresa(
            DocumentoFiscal.objects.all(),
            DocumentoFiscal,
            empresa,
        )
        taxas = _por_empresa(
            TaxaIVAAGT.objects.all(),
            TaxaIVAAGT,
            empresa,
        )
        retencoes = _retencoes_empresa(empresa)

        # Um formulário sem filtros deve funcionar normalmente.
        inicio = self.request.GET.get("data_inicio", "").strip()
        fim = self.request.GET.get("data_fim", "").strip()

        if _field_exists(DocumentoFiscal, "data_emissao"):
            date_field = DocumentoFiscal._meta.get_field("data_emissao")

            date_lookup = (
                "data_emissao__date"
                if isinstance(date_field, DateTimeField)
                else "data_emissao"
            )

            if inicio:
                docs = docs.filter(
                    **{f"{date_lookup}__gte": inicio}
                )

            if fim:
                docs = docs.filter(
                    **{f"{date_lookup}__lte": fim}
                )

        context.update({
            "empresa": empresa,
            "data_inicio": inicio,
            "data_fim": fim,
            "total_documentos": docs.count(),
            "total_taxas": taxas.count(),
            "total_retencoes": retencoes.count(),
            "documentos_recentes": _ordenar_se_disponivel(
                docs,
                DocumentoFiscal,
                "-data_emissao",
                "-created_at",
                "-pk",
            )[:10],
            "retencoes_recentes": _ordenar_se_disponivel(
                retencoes,
                RetencaoFonte,
                "-data_retencao",
                "-created_at",
                "-pk",
            )[:10],
        })

        return context

 
class SAFTExportWebView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "exportar_saft"
    template_name = "fiscal/saft/exportar.html"

    def get(self, request, *args, **kwargs):
        empresa = _exigir_empresa(request)

        exportacoes = SAFTExport.objects.all()

        if _field_exists(SAFTExport, "empresa"):
            exportacoes = exportacoes.filter(empresa=empresa)

        exportacoes = _ordenar_se_disponivel(
            exportacoes,
            SAFTExport,
            "-created_at",
            "-pk",
        )[:10]

        hoje = timezone.localdate()

        form = DateRangeForm(
            initial={
                "data_inicio": hoje.replace(day=1),
                "data_fim": hoje,
            }
        )

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "exportacoes": exportacoes,
            },
        )

    def post(self, request, *args, **kwargs):
        import logging
        import re

        from django.http import HttpResponse

        from .services.saft_xml_generator_service import (
            SaftXmlGeneratorService,
        )
        from .services.saft_validacao_service import (
            SaftValidacaoService,
        )

        logger = logging.getLogger("fiscal.saft_export")

        empresa = _exigir_empresa(request)
        form = DateRangeForm(request.POST)

        exportacoes = SAFTExport.objects.all()

        if _field_exists(SAFTExport, "empresa"):
            exportacoes = exportacoes.filter(empresa=empresa)

        exportacoes = _ordenar_se_disponivel(
            exportacoes,
            SAFTExport,
            "-created_at",
            "-pk",
        )[:10]

        context = {
            "form": form,
            "exportacoes": exportacoes,
        }

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                context,
                status=400,
            )

        data_inicio = form.cleaned_data["data_inicio"]
        data_fim = form.cleaned_data["data_fim"]

        if data_inicio > data_fim:
            form.add_error(
                "data_fim",
                "A data final não pode ser anterior à data inicial.",
            )
            return render(
                request,
                self.template_name,
                context,
                status=400,
            )

        try:
            # O construtor exige a empresa e as duas datas.
            gerador = SaftXmlGeneratorService(
                data_inicio=data_inicio,
                data_fim=data_fim,
            )

            xml_bytes = gerador.generate_xml()

            # Não aceitar texto, URLs ou outros resultados como se fossem XML.
            if (
                not isinstance(xml_bytes, bytes)
                or not xml_bytes.lstrip().startswith(b"<")
            ):
                raise ValueError(
                    "O gerador não devolveu um documento XML válido em bytes."
                )

            # O resultado da validação é a condição para autorizar o download.
            valido, erros = SaftValidacaoService.validar(xml_bytes)
            erros = erros or []

            if isinstance(erros, str):
                erros = [erros]

            if not valido:
                logger.warning(
                    "SAF-T reprovado na validação XSD. "
                    "Empresa=%s, erros=%s",
                    getattr(empresa, "pk", "desconhecida"),
                    len(erros),
                )

                context.update({
                    "erro": (
                        "O XML SAF-T foi gerado, mas não passou "
                        "na validação XSD. Corrija os erros antes "
                        "de descarregar o ficheiro."
                    ),
                    "resultado": "Validação XSD falhou.",
                    "valido": False,
                    "erros_validacao": erros,
                })

                return render(
                    request,
                    self.template_name,
                    context,
                    status=422,
                )

            # Usar apenas caracteres seguros no nome do ficheiro.
            nif = re.sub(
                r"[^A-Za-z0-9_-]",
                "",
                str(getattr(empresa, "nif", "") or ""),
            ) or "empresa"

            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            nome_ficheiro = f"SAFT_{nif}_{timestamp}.xml"

            response = HttpResponse(
                xml_bytes,
                content_type="application/xml; charset=utf-8",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{nome_ficheiro}"'
            )
            response["X-SAFT-XSD-Valid"] = "true"
            response["X-SAFT-XSD-Errors"] = "0"
            response["X-Content-Type-Options"] = "nosniff"

            logger.info(
                "SAF-T gerado e validado. Empresa=%s, período=%s a %s",
                getattr(empresa, "pk", "desconhecida"),
                data_inicio,
                data_fim,
            )

            # O XML é entregue directamente. Não se aceita um URL externo.
            return response

        except Exception as exc:
            logger.exception(
                "Erro ao gerar SAF-T para a empresa %s.",
                getattr(empresa, "pk", "desconhecida"),
            )

            context["erro"] = (
                "Não foi possível gerar o ficheiro SAF-T. "
                "Consulte os logs do servidor para identificar o problema."
            )

            if settings.DEBUG:
                context["detalhe_erro"] = str(exc)

            return render(
                request,
                self.template_name,
                context,
                status=422,
            )




class VerificarIntegridadeView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "verificar_integridade_cadeia_hash_fiscal"
    template_name = "fiscal/integridade.html"
    SESSION_KEY_PREFIX = "integridade_fiscal"
    MAX_FALHAS_SESSAO = 100

    def _session_key(self):
        # Evita misturar o resultado de um tenant com o de outro na mesma sessão.
        schema = getattr(connection, "schema_name", "public")
        return f"{self.SESSION_KEY_PREFIX}:{schema}"

    @staticmethod
    def _valor_texto(valor):
        if valor is None:
            return ""
        if isinstance(valor, (str, int, float, bool)):
            return valor
        return str(valor)

    @classmethod
    def _normalizar_falha(cls, item):
        """Converte falhas do serviço em dicionários serializáveis para a sessão/template."""
        if isinstance(item, dict):
            obter = item.get
        elif isinstance(item, (str, int, float, bool)):
            return {
                "documento": "", "numero": "", "documento_id": None,
                "tipo": "", "verificacao": "", "mensagem": str(item), "erro": "",
            }
        else:
            obter = lambda nome, padrao=None: getattr(item, nome, padrao)

        documento_obj = obter("documento", None)
        documento_id = obter("documento_id", None)
        if documento_id is None and documento_obj is not None:
            documento_id = getattr(documento_obj, "pk", None)

        try:
            documento_id = int(documento_id) if documento_id is not None else None
        except (TypeError, ValueError):
            documento_id = None

        numero = obter("numero", None)
        if numero is None and documento_obj is not None:
            numero = getattr(documento_obj, "numero_documento", None)

        return {
            "documento": cls._valor_texto(
                documento_obj if isinstance(documento_obj, (str, int, float)) else
                getattr(documento_obj, "numero_documento", "") if documento_obj is not None else ""
            ),
            "numero": cls._valor_texto(numero),
            "documento_id": documento_id,
            "tipo": cls._valor_texto(obter("tipo", "")),
            "verificacao": cls._valor_texto(obter("verificacao", "")),
            "mensagem": cls._valor_texto(obter("mensagem", "")),
            "erro": cls._valor_texto(obter("erro", "")),
        }

    @classmethod
    def _normalizar_resultado(cls, resultado):
        if isinstance(resultado, dict):
            falhas_raw = resultado.get("falhas", resultado.get("erros", []))
            total_falhas_fornecido = resultado.get("total_falhas")
            if isinstance(falhas_raw, (list, tuple)):
                falhas_raw = list(falhas_raw)
            elif falhas_raw is None:
                falhas_raw = []
            elif isinstance(falhas_raw, int):
                total_falhas_fornecido = falhas_raw if total_falhas_fornecido is None else total_falhas_fornecido
                falhas_raw = []
            else:
                falhas_raw = [falhas_raw]

            falhas = [cls._normalizar_falha(item) for item in falhas_raw]
            try:
                total_falhas = int(total_falhas_fornecido) if total_falhas_fornecido is not None else len(falhas)
            except (TypeError, ValueError):
                total_falhas = len(falhas)

            total_verificados = resultado.get(
                "total_verificados",
                resultado.get("total", resultado.get("documentos_verificados")),
            )
            try:
                total_verificados = int(total_verificados) if total_verificados is not None else None
            except (TypeError, ValueError):
                total_verificados = None

            ok = bool(resultado.get("ok", resultado.get("valido", total_falhas == 0)))
            mensagem = resultado.get("mensagem", "Verificação concluída.")
        else:
            ok = bool(resultado)
            falhas = []
            total_falhas = 0
            total_verificados = None
            mensagem = str(resultado)

        return {
            "resultado": {"ok": ok, "mensagem": str(mensagem)},
            "falhas": falhas,
            "total_verificados": total_verificados,
            "total_falhas": total_falhas,
            "falhas_limitadas": total_falhas > min(len(falhas), cls.MAX_FALHAS_SESSAO),
        }

    def _contexto(self, request):
        # Confirma que a requisição está associada a uma empresa/tenant válido.
        _exigir_empresa(request)

        from .models import AssinaturaDigital, DocumentoFiscal

        # Considera emitidos os documentos confirmados/lançados/pagos/rectificados
        # e os cancelados que chegaram a ser confirmados. Um rascunho cancelado
        # não deve ser tratado como documento fiscal emitido.
        emitidos = DocumentoFiscal.objects.filter(
            Q(status__in=("confirmed", "posted", "paid", "rectified"))
            | Q(status="cancelled", data_confirmacao__isnull=False)
        )
        total_documentos = emitidos.count()
        total_sem_hash = emitidos.filter(Q(hash_documento__isnull=True) | Q(hash_documento="")).count()
        total_sem_assinatura = emitidos.filter(
            Q(assinatura_digital__isnull=True) | Q(assinatura_digital="")
        ).count()

        estado = request.session.get(self._session_key(), {})
        ultima_execucao = parse_datetime(estado.get("ultima_execucao", "")) if estado else None

        contexto = {
            "total_documentos": total_documentos,
            "total_sem_hash": total_sem_hash,
            "total_sem_assinatura": total_sem_assinatura,
            "documentos_recentes": list(emitidos.order_by("-data_emissao", "-numero")[:10]),
            "assinatura_fiscal": AssinaturaDigital.objects.filter(pk=1).first(),
            "ultima_execucao": ultima_execucao,
            "executado": bool(estado.get("executado")),
            "resultado": estado.get("resultado"),
            "falhas": estado.get("falhas", []),
            "total_verificados": estado.get("total_verificados"),
            "total_falhas": estado.get("total_falhas", 0),
            "falhas_limitadas": estado.get("falhas_limitadas", False),
        }
        return contexto

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._contexto(request))

    def post(self, request, *args, **kwargs):
        try:
            _exigir_empresa(request)
            from .services.assinatura_service import VerificadorIntegridadeService

            verificador = VerificadorIntegridadeService()
            metodo = getattr(verificador, "verificar_tenant", None)
            if not callable(metodo):
                metodo = getattr(VerificadorIntegridadeService, "verificar_tenant", None)
            if not callable(metodo):
                raise RuntimeError("VerificadorIntegridadeService não expõe verificar_tenant().")

            resultado_bruto = metodo()
            estado_resultado = self._normalizar_resultado(resultado_bruto)
            messages.success(
                request,
                "Verificação de integridade concluída." if estado_resultado["resultado"]["ok"]
                else "A verificação detectou divergências. Consulte os detalhes abaixo.",
            )
            status_code = 200
        except Exception as exc:
            # Conserva a mensagem para diagnóstico no ecrã; convém também registar a excepção no logger do projecto.
            estado_resultado = {
                "resultado": {"ok": False, "mensagem": str(exc)},
                "falhas": [],
                "total_verificados": None,
                "total_falhas": 1,
                "falhas_limitadas": False,
            }
            status_code = 422
            messages.error(request, "Não foi possível concluir a verificação de integridade.")

        estado_sessao = {
            "ultima_execucao": timezone.now().isoformat(),
            "executado": True,
            **estado_resultado,
        }
        # Não guardar um número ilimitado de falhas no cookie/sessão.
        estado_sessao["falhas"] = estado_sessao.get("falhas", [])[: self.MAX_FALHAS_SESSAO]
        request.session[self._session_key()] = estado_sessao
        request.session.modified = True

        contexto = self._contexto(request)
        return render(request, self.template_name, contexto, status=status_code)





class ValidacaoFiscalView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "validar_documentos_fiscais"
    template_name = "fiscal/validacao.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        docs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        erros = []
        # Verificações genéricas que não dependem de nomes de campos opcionais.
        for doc in docs[:500]:
            missing = []
            for field in ("tipo_documento", "numero", "data_emissao", "atcud"):
                if _field_exists(DocumentoFiscal, field) and not getattr(doc, field, None):
                    missing.append(field)
            if missing:
                erros.append({"titulo": f"Documento {getattr(doc, 'numero', doc.pk)}", "mensagem": "Campos em falta: " + ", ".join(missing), "nivel": "erro", "documento_id": doc.pk})
        context.update({"erros": erros, "resumo": {"total": min(docs.count(), 500), "validos": max(0, min(docs.count(), 500) - len(erros)), "erros": len(erros)}})
        return context


class ConfiguracoesFiscalView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "acessar_configuracao_fiscal"
    template_name = "fiscal/configuracoes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)

        context.update({
            "empresa": empresa,
            "empresa_nome": (
                getattr(empresa, "nome", None)
                or getattr(empresa, "razao_social", None)
                or str(empresa)
                or "Não identificada"
            ),
            "empresa_nif": (
                getattr(empresa, "nif", None)
                or getattr(empresa, "nif_contribuinte", None)
                or "—"
            ),
            "debug": settings.DEBUG,
        })
        alertas = []
        if not getattr(settings, "AES_KEY", None):
            alertas.append({"titulo": "AES_KEY", "mensagem": "A chave de cifra fiscal é definida por variável de ambiente e não deve ser codificada no repositório."})
        if not getattr(settings, "GATEWAY_WEBHOOK_SECRET", None):
            alertas.append({"titulo": "Assinatura de webhooks", "mensagem": "Configure GATEWAY_WEBHOOK_SECRET antes de activar webhooks em produção."})
        context["alertas"] = alertas
        return context

class HomologacaoDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "ver_status_atual_assinatura_digital"
    template_name = "fiscal/homologacao.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        config = AssinaturaDigital.objects.filter(pk=1).first()

        from .models import SerieFiscalAGT
        total_series = SerieFiscalAGT.objects.count()

        context.update({
            "empresa": empresa,
            "assinatura_configurada": (
                _assinar_estado_configuracao(config) if config else False
            ),
            "total_series": total_series,
            "nif_ok": bool(config and getattr(config, "nif_contribuinte", None)),
            "ambiente_agt": str(getattr(settings, "AGT_ENVIRONMENT", "não configurado")),
            "estado_agt": "Não verificado",
            "mensagem": (
                "Ainda não foi executada uma chamada real à AGT nesta visita. "
                "Use Actualizar estado para consultar o serviço oficial listarSeries."
            ),
            "teste_comunicacao": "Não executado",
            "verificado_em": None,
        })
        return context

    def post(self, request, *args, **kwargs):
        # _exigir_empresa valida tenant/schema antes de qualquer chamada externa.
        _exigir_empresa(request)
        contexto = self.get_context_data()

        try:
            from .services.serie_fiscal_service import SerieFiscalService
            from .models import SerieFiscalAGT

            series = SerieFiscalService().sincronizar_series()
            contexto.update({
                "estado_agt": "Resposta válida da AGT",
                "mensagem": (
                    f"O serviço oficial listarSeries respondeu com sucesso. "
                    f"Foram sincronizadas {len(series)} série(s)."
                ),
                "total_series": SerieFiscalAGT.objects.count(),
                "series_sincronizadas": len(series),
                "teste_comunicacao": "Concluído — listarSeries",
                "verificado_em": timezone.now(),
                "erro": False,
            })
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception(
                "Falha na verificação real da integração AGT (listarSeries)."
            )
            contexto.update({
                "estado_agt": "Falha de comunicação/configuração",
                "mensagem": str(exc),
                "teste_comunicacao": "Falhou — listarSeries",
                "verificado_em": timezone.now(),
                "erro": True,
            })

        return render(request, self.template_name, contexto)
