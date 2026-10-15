# apps/fiscal/web_views.py
"""Views web da área fiscal, separadas das views da API.

Adiciona uma camada web consistente sem substituir os ViewSets/API/webhooks já
existentes em apps.fiscal.views. Todas as queries de modelos com FK Empresa são
filtradas pela empresa do utilizador; modelos singleton/tenant-local são lidos
no esquema actual.
"""
from datetime import date
from inspect import signature

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import DateTimeField, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .forms_web import DateRangeForm, DocumentoFiscalWebForm, RetencaoFonteWebForm, TaxaIVAWebForm
from .models import (
    AssinaturaDigital,
    DocumentoFiscal,
    DocumentoFiscalLinha,
    RetencaoFonte,
    SAFTExport,
    TaxaIVAAGT,
)


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
    empresa = _empresa_do_utilizador(request.user)
    if empresa is None:
        raise PermissionDenied("O utilizador não está associado a uma empresa.")
    return empresa


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
class FiscalDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "fiscal/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        docs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        taxas = _por_empresa(TaxaIVAAGT.objects.all(), TaxaIVAAGT, empresa)
        retencoes = _retencoes_empresa(empresa)
        state_field = _campo_estado(DocumentoFiscal)
        rascunhos = docs.filter(**{state_field: "rascunho"}).count() if state_field else 0
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


class DocumentoFiscalListView(LoginRequiredMixin, ListView):
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


class DocumentoFiscalDetailView(LoginRequiredMixin, DetailView):
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


class DocumentoFiscalCreateView(LoginRequiredMixin, CreateView):
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
        if _field_exists(DocumentoFiscal, "criado_por"):
            obj.criado_por = self.request.user
        elif _field_exists(DocumentoFiscal, "created_by"):
            obj.created_by = self.request.user
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


class DocumentoFiscalUpdateView(LoginRequiredMixin, UpdateView):
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
class TaxaIVAListView(LoginRequiredMixin, ListView):
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


class TaxaIVACreateView(LoginRequiredMixin, CreateView):
    model = TaxaIVAAGT
    form_class = TaxaIVAWebForm
    template_name = "fiscal/taxas_iva/formulario.html"
    success_url = reverse_lazy("fiscal:taxas_iva")

    def form_valid(self, form):
        empresa = _exigir_empresa(self.request)
        obj = form.save(commit=False)
        obj.empresa = empresa
        try:
            obj.full_clean()
            obj.save()
        except (ValidationError, ValueError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Taxa de imposto criada.")
        return redirect(self.success_url)


class TaxaIVAUpdateView(LoginRequiredMixin, UpdateView):
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
class RetencaoFonteListView(LoginRequiredMixin, ListView):
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


class RetencaoFonteCreateView(LoginRequiredMixin, CreateView):
    model = RetencaoFonte
    form_class = RetencaoFonteWebForm
    template_name = "fiscal/retencoes/formulario.html"
    success_url = reverse_lazy("fiscal:retencoes")

    def form_valid(self, form):
        try:
            obj = form.save(commit=False)
            if _field_exists(RetencaoFonte, "criado_por"):
                obj.criado_por = self.request.user
            obj.full_clean()
            # A transação garante rollback se o hook contabilístico falhar.
            with transaction.atomic():
                obj.save()  # o model calcula o valor retido
        except (ValidationError, ValueError, AttributeError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Retenção registada.")
        return redirect(self.success_url)


class RetencaoFonteUpdateView(LoginRequiredMixin, UpdateView):
    model = RetencaoFonte
    form_class = RetencaoFonteWebForm
    template_name = "fiscal/retencoes/formulario.html"
    success_url = reverse_lazy("fiscal:retencoes")

    def get_queryset(self):
        return _retencoes_empresa(_exigir_empresa(self.request))

    def form_valid(self, form):
        try:
            obj = form.save(commit=False)
            obj.full_clean()
            with transaction.atomic():
                obj.save()
        except (ValidationError, ValueError, AttributeError) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Retenção actualizada.")
        return redirect(self.success_url)


# ---------------------------------------------------------------------------
# Configuração, relatórios, SAF-T, integridade e homologação
# ---------------------------------------------------------------------------
class AssinaturaDigitalConfigView(LoginRequiredMixin, TemplateView):
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


class RelatoriosFiscaisView(LoginRequiredMixin, TemplateView):
    template_name = "fiscal/relatorios/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        docs = _por_empresa(DocumentoFiscal.objects.all(), DocumentoFiscal, empresa)
        taxas = _por_empresa(TaxaIVAAGT.objects.all(), TaxaIVAAGT, empresa)
        retencoes = _retencoes_empresa(empresa)
        inicio = self.request.GET.get("data_inicio")
        fim = self.request.GET.get("data_fim")
        if _field_exists(DocumentoFiscal, "data_emissao"):
            date_field = DocumentoFiscal._meta.get_field("data_emissao")
            date_lookup = "data_emissao__date" if isinstance(date_field, DateTimeField) else "data_emissao"
            if inicio:
                docs = docs.filter(**{f"{date_lookup}__gte": inicio})
            if fim:
                docs = docs.filter(**{f"{date_lookup}__lte": fim})
        context.update({
            "empresa": empresa,
            "data_inicio": inicio,
            "data_fim": fim,
            "total_documentos": docs.count(),
            "total_taxas": taxas.count(),
            "total_retencoes": retencoes.count(),
            "documentos_recentes": _ordenar_se_disponivel(docs, DocumentoFiscal, "-data_emissao", "-created_at", "-pk")[:10],
            "retencoes_recentes": _ordenar_se_disponivel(retencoes, RetencaoFonte, "-data_retencao", "-created_at", "-pk")[:10],
        })
        return context


class SAFTExportWebView(LoginRequiredMixin, View):
    template_name = "fiscal/saft/exportar.html"

    def get(self, request, *args, **kwargs):
        empresa = _exigir_empresa(request)
        exportacoes = SAFTExport.objects.all()
        if _field_exists(SAFTExport, "empresa"):
            exportacoes = exportacoes.filter(empresa=empresa)
        exportacoes = _ordenar_se_disponivel(exportacoes, SAFTExport, "-created_at", "-pk")[:10]
        return render(request, self.template_name, {"form": DateRangeForm(initial={"data_inicio": date.today().replace(day=1), "data_fim": date.today()}), "exportacoes": exportacoes})

    def post(self, request, *args, **kwargs):
        empresa = _exigir_empresa(request)
        form = DateRangeForm(request.POST)
        exportacoes = SAFTExport.objects.all()
        if _field_exists(SAFTExport, "empresa"):
            exportacoes = exportacoes.filter(empresa=empresa)
        exportacoes = _ordenar_se_disponivel(exportacoes, SAFTExport, "-created_at", "-pk")[:10]
        context = {"form": form, "exportacoes": exportacoes}
        if not form.is_valid():
            return render(request, self.template_name, context, status=400)

        # Adapter tolerante a nomes de método das versões de serviço conhecidas.
        # O serviço é a autoridade para geração, numeração, XML e validação.
        try:
            from .services.saft_xml_generator_service import SaftXmlGeneratorService
            service = SaftXmlGeneratorService()
            data = {"empresa": empresa, "data_inicio": form.cleaned_data["data_inicio"], "data_fim": form.cleaned_data["data_fim"], "inicio": form.cleaned_data["data_inicio"], "fim": form.cleaned_data["data_fim"]}
            method = next((getattr(service, name) for name in ("gerar_saft_ao", "gerar_saft", "gerar_xml", "gerar") if callable(getattr(service, name, None))), None)
            if method is None:
                raise RuntimeError("O serviço SAF-T não expõe um método de geração conhecido.")
            params = signature(method).parameters
            kwargs_for_method = {name: data[name] for name in params if name in data}
            if kwargs_for_method and all(p.default is not p.empty or p.name in kwargs_for_method for p in params.values() if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)):
                result = method(**kwargs_for_method)
            else:
                result = method(empresa, form.cleaned_data["data_inicio"], form.cleaned_data["data_fim"])
            context.update({"resultado": "O gerador foi executado. O estado de validação deve ser confirmado pelo resultado do validador SAF-T.", "valido": False})
            if isinstance(result, dict):
                context["resultado"] = result.get("mensagem") or result.get("message") or context["resultado"]
                # Não indicar sucesso de validação se o serviço não o confirmou explicitamente.
                context["valido"] = bool(result.get("valido", result.get("valid", result.get("validado", False))))
                context["ficheiro_url"] = result.get("url") or result.get("download_url")
                context["erros_validacao"] = result.get("erros") or result.get("errors") or []
            elif isinstance(result, str) and result.startswith("http"):
                context["ficheiro_url"] = result
            elif isinstance(result, (str, bytes)) and ((isinstance(result, bytes) and result.lstrip().startswith(b"<")) or (isinstance(result, str) and result.lstrip().startswith("<"))):
                # Se o gerador devolver XML em memória, tentar a validação explícita.
                from .services.saft_validacao_service import SaftValidacaoService
                validator = SaftValidacaoService()
                validator_method = next((getattr(validator, name) for name in ("validar_xml", "validar", "validar_conteudo", "validar_xml_bytes") if callable(getattr(validator, name, None))), None)
                if validator_method is None:
                    context["resultado"] = "XML gerado, mas não foi encontrado um método de validação compatível."
                else:
                    validation = validator_method(result)
                    if isinstance(validation, tuple) and len(validation) >= 2:
                        context["valido"] = bool(validation[0])
                        context["erros_validacao"] = validation[1] or []
                    elif isinstance(validation, dict):
                        context["valido"] = bool(validation.get("valido", validation.get("valid", False)))
                        context["erros_validacao"] = validation.get("erros", validation.get("errors", []))
                    else:
                        context["valido"] = bool(validation)
        except Exception as exc:  # apresenta erro operacional sem ocultar logs do servidor
            context["erro"] = str(exc)
            return render(request, self.template_name, context, status=422)
        return render(request, self.template_name, context)


class VerificarIntegridadeView(LoginRequiredMixin, View):
    template_name = "fiscal/integridade.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {"ultima_execucao": None})

    def post(self, request, *args, **kwargs):
        _exigir_empresa(request)
        try:
            from .services.assinatura_service import VerificadorIntegridadeService
            verificador = VerificadorIntegridadeService()
            metodo = getattr(verificador, "verificar_tenant", None) or getattr(VerificadorIntegridadeService, "verificar_tenant", None)
            if not callable(metodo):
                raise RuntimeError("VerificadorIntegridadeService não expõe verificar_tenant().")
            try:
                resultado = metodo()
            except TypeError:
                # Pode estar implementado como método de classe na versão instalada.
                resultado = VerificadorIntegridadeService.verificar_tenant()
            if isinstance(resultado, dict):
                ok = bool(resultado.get("ok", resultado.get("valido", not resultado.get("falhas"))))
                falhas = resultado.get("falhas", resultado.get("erros", []))
                total = resultado.get("total_verificados", resultado.get("total", 0))
                mensagem = resultado.get("mensagem", "Verificação concluída.")
            else:
                ok, falhas, total, mensagem = bool(resultado), [], 0, str(resultado)
            messages.success(request, "Verificação de integridade concluída." if ok else "A verificação detectou divergências.")
            return render(request, self.template_name, {"resultado": {"ok": ok, "mensagem": mensagem}, "falhas": falhas, "total_verificados": total, "total_falhas": len(falhas), "ultima_execucao": timezone.now()})
        except Exception as exc:
            return render(request, self.template_name, {"resultado": {"ok": False, "mensagem": str(exc)}, "falhas": [], "total_falhas": 1, "ultima_execucao": timezone.now()}, status=422)


class ValidacaoFiscalView(LoginRequiredMixin, TemplateView):
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


class ConfiguracoesFiscalView(LoginRequiredMixin, TemplateView):
    template_name = "fiscal/configuracoes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"empresa": _exigir_empresa(self.request), "debug": settings.DEBUG})
        alertas = []
        if not getattr(settings, "AES_KEY", None):
            alertas.append({"titulo": "AES_KEY", "mensagem": "A chave de cifra fiscal é definida por variável de ambiente e não deve ser codificada no repositório."})
        if not getattr(settings, "GATEWAY_WEBHOOK_SECRET", None):
            alertas.append({"titulo": "Assinatura de webhooks", "mensagem": "Configure GATEWAY_WEBHOOK_SECRET antes de activar webhooks em produção."})
        context["alertas"] = alertas
        return context


class HomologacaoDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "fiscal/homologacao.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = _exigir_empresa(self.request)
        config = AssinaturaDigital.objects.filter(pk=1).first()
        context.update({"assinatura_configurada": _assinar_estado_configuracao(config) if config else False, "empresa": empresa, "verificado_em": timezone.now(), "teste_comunicacao": "Não executado"})
        series_model = None
        try:
            from .models import SerieFiscalAGT
            series_model = SerieFiscalAGT
        except ImportError:
            pass
        context["total_series"] = series_model.objects.count() if series_model else 0
        context["nif_ok"] = bool(config and getattr(config, "nif_contribuinte", None))
        try:
            from .services.web_service import AGTWebService
            service = AGTWebService()
            for method_name in ("verificar_estado", "obter_estado", "verificar_saude", "health_check"):
                method = getattr(service, method_name, None)
                if callable(method):
                    response = method()
                    context["estado_agt"] = response.get("estado", response.get("status", "Disponível")) if isinstance(response, dict) else str(response)
                    break
        except Exception as exc:
            context["estado_agt"] = "Indisponível"
            context["mensagem"] = str(exc)
            context["erro"] = True
        return context

    def post(self, request, *args, **kwargs):
        response = self.get_context_data()
        if not response.get("estado_agt"):
            response["estado_agt"] = "Sem resposta"
            response["mensagem"] = "O serviço de estado não devolveu informação. Consulte os logs de integração."
        return render(request, self.template_name, response)
