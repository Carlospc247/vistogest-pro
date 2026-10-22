"""Views tenant-aware para catálogo, agendamentos e notificações.

Compatível com isolamento físico por schema (django-tenants). Quando um modelo
possui um campo `empresa`, também limita as consultas a essa empresa.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from apps.empresas.models import Empresa
from .forms import (
    ServicoForm, AgendamentoServicoForm, FinalizarServicoForm,
    NotificacaoAgendamentoForm, ConfiguracaoNotificacaoForm,
)
from .models import Servico, AgendamentoServico, NotificacaoAgendamento, ConfiguracaoNotificacao

logger = logging.getLogger(__name__)


def empresa_da_requisicao(request):
    """Devolve o tenant activo; nunca trata o schema público como empresa."""
    tenant = getattr(request, "tenant", None) or getattr(connection, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", getattr(connection, "schema_name", "public")) == "public":
        return None
    return tenant


def _tem_campo(modelo, nome):
    try:
        modelo._meta.get_field(nome)
        return True
    except (FieldDoesNotExist, AttributeError):
        return False


def _qs_tenant(modelo, tenant):
    """Consulta segura no schema actual, com filtro adicional se existir empresa FK."""
    if tenant is None or getattr(connection, "schema_name", "public") == "public":
        return modelo.objects.none()
    qs = modelo.objects.all()
    if not _tem_campo(modelo, "empresa"):
        # Estes modelos são tenant-local por schema e não têm FK `empresa`.
        return qs
    try:
        return qs.filter(empresa=tenant)
    except (TypeError, ValueError):
        # Algumas instalações usam um modelo Tenant e uma FK para Empresa.
        tenant_pk = getattr(tenant, "pk", None)
        if tenant_pk is not None:
            try:
                return qs.filter(empresa_id=tenant_pk)
            except Exception:
                logger.warning("Não foi possível resolver a FK empresa de %s", modelo.__name__)
        return qs.none()


def _atribuir_empresa_se_existir(obj, empresa):
    if _tem_campo(type(obj), "empresa"):
        try:
            obj.empresa = empresa
        except (TypeError, ValueError):
            if getattr(empresa, "pk", None) is not None:
                obj.empresa_id = empresa.pk


def _sem_empresa_json():
    return JsonResponse({"success": False, "message": "Empresa/tenant não encontrada para esta requisição."}, status=400)


class ServicoPermissionMixin(LoginRequiredMixin):
    """Exige sessão autenticada e impede operações no schema público."""
    def get_empresa(self):
        return empresa_da_requisicao(self.request)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if self.get_empresa() is None:
            messages.error(request, "Não foi possível identificar a empresa activa.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return _qs_tenant(self.model, self.get_empresa())


class ServicoDashboard(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = "servicos/dashboard_servicos.html"
    context_object_name = "servicos"
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().select_related("categoria", "taxa_iva").order_by("nome", "pk")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query:
            qs = qs.filter(Q(nome__icontains=query) | Q(instrucoes_padrao__icontains=query) | Q(instrucoes_servico__icontains=query))
        if estado == "ativo":
            qs = qs.filter(ativo=True)
        elif estado == "inativo":
            qs = qs.filter(ativo=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tenant = self.get_empresa()
        servicos = _qs_tenant(Servico, tenant)
        agendamentos = _qs_tenant(AgendamentoServico, tenant)
        notificacoes = _qs_tenant(NotificacaoAgendamento, tenant)
        ctx.update({
            "total_servicos": servicos.count(),
            "servico_destaque": servicos.order_by("-pk").first(),
            "servicos_ativos": servicos.filter(ativo=True).count(),
            "servicos_inativos": servicos.filter(ativo=False).count(),
            "agendamentos_pendentes": agendamentos.filter(status="agendado").count(),
            "agendamentos_em_andamento": agendamentos.filter(status="em_andamento").count(),
            "agendamentos_finalizados": agendamentos.filter(status="finalizado").count(),
            "total_agendamentos": agendamentos.count(),
            "agendamentos_recentes": agendamentos.select_related("servico", "cliente", "funcionario").order_by("-data_hora")[:6],
            "agendamento_destaque": agendamentos.select_related("servico", "cliente", "funcionario").order_by("-data_hora").first(),
            "notificacoes_recentes": notificacoes.select_related("cliente", "agendamento", "agendamento__servico").order_by("-data_agendada_envio")[:5],
            "notificacao_destaque": notificacoes.order_by("-data_agendada_envio").first(),
            "filtro_q": self.request.GET.get("q", "").strip(),
            "filtro_estado": self.request.GET.get("estado", ""),
        })
        return ctx


class ServicoListView(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = "servicos/servico_list.html"
    context_object_name = "servicos"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("categoria", "taxa_iva")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query:
            qs = qs.filter(Q(nome__icontains=query) | Q(instrucoes_padrao__icontains=query) | Q(instrucoes_servico__icontains=query))
        if estado == "ativo":
            qs = qs.filter(ativo=True)
        elif estado == "inativo":
            qs = qs.filter(ativo=False)
        return qs.order_by("nome", "pk")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"filtro_q": self.request.GET.get("q", "").strip(), "filtro_estado": self.request.GET.get("estado", "")})
        return ctx


class ServicoCreateView(ServicoPermissionMixin, CreateView):
    model = Servico
    form_class = ServicoForm
    template_name = "servicos/servico_form.html"
    success_url = reverse_lazy("servicos:servico_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        _atribuir_empresa_se_existir(form.instance, self.get_empresa())
        response = super().form_valid(form)
        messages.success(self.request, "Serviço de catálogo criado com sucesso.")
        return response


class ServicoUpdateView(ServicoPermissionMixin, UpdateView):
    model = Servico
    form_class = ServicoForm
    template_name = "servicos/servico_form.html"
    success_url = reverse_lazy("servicos:servico_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        _atribuir_empresa_se_existir(form.instance, self.get_empresa())
        response = super().form_valid(form)
        messages.success(self.request, "Serviço de catálogo actualizado com sucesso.")
        return response


class ServicoDeleteView(ServicoPermissionMixin, DeleteView):
    model = Servico
    template_name = "servicos/servico_confirm_delete.html"
    success_url = reverse_lazy("servicos:servico_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.agendamentos.exists():
            messages.error(request, "Este serviço já está associado a agendamentos. Desactive-o em vez de o eliminar, para preservar o histórico.")
            return redirect(self.success_url)
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "O serviço está protegido por registos relacionados e não pode ser eliminado.")
            return redirect(self.success_url)

    def form_valid(self, form):
        nome = self.object.nome
        response = super().form_valid(form)
        messages.success(self.request, f"Serviço '{nome}' eliminado com sucesso.")
        return response


class AgendamentoListView(ServicoPermissionMixin, ListView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_list.html"
    context_object_name = "agendamentos"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = AgendamentoServico.STATUS_CHOICES
        context["filtro_q"] = self.request.GET.get("q", "").strip()
        context["filtro_status"] = self.request.GET.get("status", "")
        return context

    def get_queryset(self):
        qs = super().get_queryset().select_related("servico", "cliente", "funcionario")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("status", "")
        if query:
            qs = qs.filter(Q(cliente__nome_completo__icontains=query) | Q(servico__nome__icontains=query) | Q(funcionario__nome_completo__icontains=query))
        if estado in dict(AgendamentoServico.STATUS_CHOICES):
            qs = qs.filter(status=estado)
        return qs.order_by("-data_hora")


class AgendamentoCreateView(ServicoPermissionMixin, CreateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = "servicos/agendamento_form.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        _atribuir_empresa_se_existir(form.instance, self.get_empresa())
        if not form.instance.valor_cobrado and form.cleaned_data.get("servico"):
            form.instance.valor_cobrado = form.cleaned_data["servico"].preco_com_desconto
        response = super().form_valid(form)
        messages.success(self.request, "Agendamento criado com sucesso.")
        return response


class AgendamentoUpdateView(ServicoPermissionMixin, UpdateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = "servicos/agendamento_form.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["empresa"] = self.get_empresa()
        return kwargs

    def form_valid(self, form):
        _atribuir_empresa_se_existir(form.instance, self.get_empresa())
        response = super().form_valid(form)
        messages.success(self.request, "Agendamento actualizado com sucesso.")
        return response


class AgendamentoDeleteView(ServicoPermissionMixin, DeleteView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_confirm_delete.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.notificacoes.exists():
            messages.error(request, "Este agendamento tem notificações associadas. Preserve o histórico ou elimine primeiro as notificações com autorização.")
            return redirect("servicos:agendamento_detail", pk=self.object.pk)
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "O agendamento está protegido por registos relacionados.")
            return redirect("servicos:agendamento_detail", pk=self.object.pk)

    def form_valid(self, form):
        description = f"{self.object.servico} — {self.object.cliente}"
        response = super().form_valid(form)
        messages.success(self.request, f"Agendamento '{description}' eliminado.")
        return response


class AgendamentoDetailView(ServicoPermissionMixin, DetailView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_detail.html"
    context_object_name = "agendamento"

    def get_queryset(self):
        return super().get_queryset().select_related("servico", "cliente", "funcionario")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["finalizar_form"] = FinalizarServicoForm()
        return context


def _criar_evento_operacional(request, agendamento, tipo, titulo, descricao=""):
    try:
        from apps.servicos.tracking_services import registar_evento_agendamento
        registar_evento_agendamento(
            agendamento=agendamento, tipo=tipo, titulo=titulo, descricao=descricao,
            autor_usuario=request.user, schema_name=getattr(connection, "schema_name", None),
        )
    except Exception:
        logger.exception("Não foi possível registar o evento do agendamento %s", agendamento.pk)


def _iniciar_agendamento(agendamento, request):
    iniciar = getattr(agendamento, "iniciar", None)
    if callable(iniciar):
        iniciar()
    else:
        if agendamento.status != "agendado":
            raise ValidationError("Só é possível iniciar um agendamento que esteja agendado.")
        agendamento.status = "em_andamento"
        if hasattr(agendamento, "data_inicio_real"):
            agendamento.data_inicio_real = timezone.now()
            agendamento.save(update_fields=["status", "data_inicio_real", "updated_at"])
        else:
            agendamento.save(update_fields=["status", "updated_at"])
    _criar_evento_operacional(request, agendamento, "iniciado", "Serviço iniciado")


def _finalizar_agendamento(agendamento, request, resultado, recomendacoes):
    finalizar = getattr(agendamento, "finalizar", None)
    if callable(finalizar):
        finalizar(resultado, recomendacoes)
    else:
        if agendamento.status not in {"em_andamento", "pausado"}:
            raise ValidationError("Só é possível finalizar um serviço em execução ou pausado.")
        agendamento.status = "finalizado"
        if hasattr(agendamento, "resultado"):
            extra = f"\n\nRecomendações: {recomendacoes}" if recomendacoes else ""
            agendamento.resultado = f"{resultado}{extra}".strip()
        if hasattr(agendamento, "data_fim_real"):
            agendamento.data_fim_real = timezone.now()
            agendamento.save(update_fields=["status", "data_fim_real", "resultado", "updated_at"] if hasattr(agendamento, "resultado") else ["status", "data_fim_real", "updated_at"])
        else:
            agendamento.save(update_fields=["status", "resultado", "updated_at"] if hasattr(agendamento, "resultado") else ["status", "updated_at"])
    _criar_evento_operacional(request, agendamento, "finalizado", "Serviço finalizado", resultado)


class IniciarServicoView(ServicoPermissionMixin, View):
    http_method_names = ["post"]
    def post(self, request, pk, *args, **kwargs):
        agendamento = get_object_or_404(_qs_tenant(AgendamentoServico, self.get_empresa()), pk=pk)
        try:
            _iniciar_agendamento(agendamento, request)
            messages.success(request, f"O serviço '{agendamento.servico.nome}' foi iniciado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("servicos:agendamento_detail", pk=agendamento.pk)


class FinalizarServicoView(ServicoPermissionMixin, View):
    http_method_names = ["post"]
    def post(self, request, pk, *args, **kwargs):
        agendamento = get_object_or_404(_qs_tenant(AgendamentoServico, self.get_empresa()), pk=pk)
        form = FinalizarServicoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Preencha o resultado do serviço antes de finalizar.")
        else:
            try:
                _finalizar_agendamento(agendamento, request, form.cleaned_data["resultado_servico"], form.cleaned_data["recomendacoes"])
                messages.success(request, "Agendamento finalizado com sucesso.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        return redirect("servicos:agendamento_detail", pk=agendamento.pk)


def _api_tenant(request):
    return empresa_da_requisicao(request)


@login_required
@require_GET
def buscar_agendamento_api(request):
    empresa = _api_tenant(request)
    if empresa is None:
        return _sem_empresa_json()
    qs = _qs_tenant(AgendamentoServico, empresa).select_related("cliente", "servico", "funcionario")
    query, estado = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if estado in dict(AgendamentoServico.STATUS_CHOICES):
        qs = qs.filter(status=estado)
    if query:
        qs = qs.filter(Q(cliente__nome_completo__icontains=query) | Q(servico__nome__icontains=query) | Q(funcionario__nome_completo__icontains=query))
    rows = [{
        "id": a.pk, "data_hora": a.data_hora.isoformat(), "servico": a.servico.nome,
        "cliente": getattr(a.cliente, "nome_completo", str(a.cliente)),
        "funcionario": getattr(a.funcionario, "nome_completo", "") if a.funcionario_id else "",
        "status": a.status, "status_display": a.get_status_display(),
    } for a in qs.order_by("data_hora")[:100]]
    return JsonResponse({"success": True, "agendamentos": rows, "total_encontrados": len(rows)})


@login_required
@require_GET
def listar_servicos_api(request):
    empresa = _api_tenant(request)
    if empresa is None:
        return _sem_empresa_json()
    qs = _qs_tenant(Servico, empresa).filter(ativo=True).select_related("categoria", "taxa_iva").order_by("nome")[:500]
    rows = [{
        "id": s.pk, "nome": s.nome, "categoria": str(s.categoria), "categoria_id": s.categoria_id,
        "preco": float(s.preco_com_desconto), "preco_padrao": float(s.preco_padrao),
        "desconto_percentual": float(s.desconto_percentual), "iva_percentual": float(s.iva_percentual),
        "descricao": s.instrucoes_padrao or getattr(s, "instrucoes_servico", ""), "disponivel": s.ativo,
    } for s in qs]
    return JsonResponse({"success": True, "servicos": rows, "total_encontrados": len(rows)})


@login_required
@require_GET
def buscar_servicos_api(request):
    empresa = _api_tenant(request)
    if empresa is None:
        return _sem_empresa_json()
    qs = _qs_tenant(Servico, empresa).filter(ativo=True).select_related("categoria", "taxa_iva")
    query, categoria = request.GET.get("q", "").strip(), request.GET.get("categoria", "").strip()
    if query:
        qs = qs.filter(Q(nome__icontains=query) | Q(instrucoes_padrao__icontains=query))
    if categoria and categoria != "todos":
        if not categoria.isdigit():
            return JsonResponse({"success": False, "message": "Categoria inválida."}, status=400)
        qs = qs.filter(categoria_id=int(categoria))
    rows = [{
        "id": s.pk, "nome": s.nome, "categoria": str(s.categoria), "categoria_id": s.categoria_id,
        "preco_padrao": float(s.preco_padrao), "preco_com_desconto": float(s.preco_com_desconto),
        "desconto_percentual": float(s.desconto_percentual), "iva_percentual": float(s.iva_percentual),
    } for s in qs.order_by("nome")[:100]]
    return JsonResponse({"success": True, "servicos": rows, "total_encontrados": len(rows)})


def _qs_notificacoes(empresa):
    return _qs_tenant(NotificacaoAgendamento, empresa)


@login_required
def notificacao_list(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    qs = _qs_notificacoes(empresa).select_related("cliente", "agendamento", "agendamento__servico")
    query, estado = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if query:
        qs = qs.filter(Q(titulo__icontains=query) | Q(cliente__nome_completo__icontains=query) | Q(mensagem__icontains=query))
    if estado in dict(NotificacaoAgendamento.STATUS_CHOICES):
        qs = qs.filter(status=estado)
    return render(request, "servicos/notificacao_list.html", {
        "notificacoes": qs.order_by("-data_agendada_envio")[:100],
        "status_choices": NotificacaoAgendamento.STATUS_CHOICES,
        "query": query, "status_filter": estado,
    })


@login_required
def notificacao_create(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    form = NotificacaoAgendamentoForm(request.POST or None, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        notificacao = form.save(commit=False)
        _atribuir_empresa_se_existir(notificacao, empresa)
        agendamento_id = getattr(notificacao, "agendamento_id", None)
        if not agendamento_id or not _qs_tenant(AgendamentoServico, empresa).filter(pk=agendamento_id).exists():
            form.add_error("agendamento", "Seleccione um agendamento válido desta empresa.")
        else:
            notificacao.save()
            messages.success(request, "Notificação criada com sucesso.")
            return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_form.html", {"form": form, "titulo": "Criar notificação"})


@login_required
def notificacao_update(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    notificacao = get_object_or_404(_qs_notificacoes(empresa), pk=pk)
    form = NotificacaoAgendamentoForm(request.POST or None, instance=notificacao, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        _atribuir_empresa_se_existir(updated, empresa)
        if not _qs_tenant(AgendamentoServico, empresa).filter(pk=updated.agendamento_id).exists():
            form.add_error("agendamento", "Seleccione um agendamento válido desta empresa.")
        else:
            updated.save()
            messages.success(request, "Notificação actualizada com sucesso.")
            return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_form.html", {"form": form, "titulo": "Editar notificação", "notificacao": notificacao})


@login_required
def notificacao_delete(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    notificacao = get_object_or_404(_qs_notificacoes(empresa), pk=pk)
    if request.method == "POST":
        notificacao.delete()
        messages.success(request, "Notificação eliminada com sucesso.")
        return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_confirm_delete.html", {"notificacao": notificacao})


@login_required
@require_GET
def buscar_notificacao_api(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        return _sem_empresa_json()
    qs = _qs_notificacoes(empresa).select_related("cliente", "agendamento", "agendamento__servico")
    query, estado = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if query:
        qs = qs.filter(Q(titulo__icontains=query) | Q(cliente__nome_completo__icontains=query) | Q(mensagem__icontains=query))
    if estado in dict(NotificacaoAgendamento.STATUS_CHOICES):
        qs = qs.filter(status=estado)
    rows = [{
        "id": n.pk, "titulo": n.titulo,
        "cliente": getattr(n.cliente, "nome_completo", str(n.cliente)),
        "tipo_notificacao": n.get_tipo_notificacao_display(), "status": n.get_status_display(),
        "data_agendada_envio": timezone.localtime(n.data_agendada_envio).strftime("%d/%m/%Y %H:%M"),
    } for n in qs.order_by("-data_agendada_envio")[:50]]
    return JsonResponse({"success": True, "notificacoes": rows, "total": len(rows)})


def _resolver_empresa_configuracao(tenant):
    """Resolve Empresa para ConfiguracaoNotificacao sem assumir o modelo Tenant usado."""
    if tenant is None:
        return None
    if isinstance(tenant, Empresa):
        return tenant
    campos = {f.name: f for f in Empresa._meta.get_fields() if getattr(f, "concrete", False)}
    for nome in ("schema_name", "schema", "slug"):
        if nome in campos:
            try:
                obj = Empresa.objects.filter(**{nome: getattr(connection, "schema_name", "")}).first()
                if obj:
                    return obj
            except Exception:
                pass
    for nome, campo in campos.items():
        remote = getattr(campo, "remote_field", None)
        remoto_modelo = getattr(remote, "model", None)
        if remoto_modelo is type(tenant):
            try:
                obj = Empresa.objects.filter(**{nome: tenant}).first()
                if obj:
                    return obj
            except Exception:
                pass
    # Em instalações com uma Empresa única dentro de cada schema.
    try:
        if Empresa.objects.count() == 1:
            return Empresa.objects.first()
    except Exception:
        pass
    return None


@login_required
def configuracao_notificacao_update(request):
    tenant = empresa_da_requisicao(request)
    if tenant is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    empresa = _resolver_empresa_configuracao(tenant)
    if empresa is None:
        messages.error(request, "Não foi possível associar o tenant a um registo de Empresa para configurar notificações.")
        return redirect("servicos:servico_dashboard")
    config, _ = ConfiguracaoNotificacao.objects.get_or_create(empresa=empresa)
    form = ConfiguracaoNotificacaoForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        saved.empresa = empresa
        saved.save()
        messages.success(request, "Configurações de notificação guardadas.")
        return redirect("servicos:config_notificacao")
    return render(request, "servicos/configuracao_form.html", {"form": form, "config": config})
