# apps/clientes/views.py
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages

from .models import (
    Cliente, CategoriaCliente, EnderecoCliente, ContatoCliente,
    HistoricoCliente, CartaoFidelidade, MovimentacaoFidelidade,
    PreferenciaCliente
)
from django.urls import reverse_lazy
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from .models import (
    Cliente,
    Ponto,
    CategoriaCliente,
    EnderecoCliente,
    ContatoCliente,
    HistoricoCliente,
    CartaoFidelidade,
    MovimentacaoFidelidade,
    PreferenciaCliente,
    TelefoneCliente,
    GrupoCliente,
    ProgramaFidelidade,
)
from .forms import (
    ClienteForm,
    PontoForm,
    CategoriaClienteForm,
    EnderecoClienteForm,
    ContatoClienteForm,
    HistoricoClienteForm,
    CartaoFidelidadeForm,
    MovimentacaoFidelidadeForm,
    PreferenciaClienteForm,
    TelefoneClienteForm,
    GrupoClienteForm,
    ProgramaFidelidadeForm,
)
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.http import HttpResponse
from django.contrib import messages
from django.views import View
from django.core.files.storage import FileSystemStorage

from .models import Cliente
from .forms import ClienteForm

# API
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.contrib import messages

from .models import (
    Cliente, CategoriaCliente, EnderecoCliente, ContatoCliente,
    HistoricoCliente, CartaoFidelidade, MovimentacaoFidelidade,
    PreferenciaCliente, TelefoneCliente, GrupoCliente, ProgramaFidelidade, Ponto
)
from django.db.models import Count, Sum, F, DecimalField
from django.views.generic import TemplateView
from .models import Cliente, Ponto, CategoriaCliente, HistoricoCliente
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth.mixins import AccessMixin




class PermissaoAcaoMixin(AccessMixin):
    # CRÍTICO: Definir esta variável na View
    acao_requerida = None 

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Tenta obter o Funcionario (ligação fundamental)
            funcionario = request.user.funcionario 
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            # Usa a lógica dinâmica do modelo Funcionario (que já criámos)
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('core:dashboard'))

        return super().dispatch(request, *args, **kwargs)





class ClienteDashboardView(TemplateView):
    """
    Dashboard de clientes com dados analíticos e KPIs.
    """
    template_name = "clientes/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # KPIs principais
        total_clientes = Cliente.objects.count()
        clientes_ativos = Cliente.objects.filter(ativo=True).count()
        clientes_novos_mes = Cliente.objects.filter(created_at__month=date.today().month, created_at__year=date.today().year).count()

        # Dados de fidelidade
        total_pontos_acumulados = Ponto.objects.aggregate(total=Sum('valor'))['total'] or 0
        total_pontos_usados = Cliente.objects.aggregate(total=Sum('cartao_fidelidade__pontos_utilizados'))['total'] or 0

        # Distribuição de clientes por tipo e categoria
        tipo_cliente_data = list(Cliente.objects.values('tipo_cliente').annotate(count=Count('tipo_cliente')))
        categoria_data = list(Cliente.objects.values('categoria_cliente__nome').annotate(count=Count('categoria_cliente__nome')))

        # Clientes VIP
        clientes_vip = Cliente.objects.filter(vip=True).order_by('-data_ultima_compra')[:5]

        # Clientes com mais pontos
        clientes_top_pontos = Cliente.objects.annotate(
            total_pontos=Sum('ponto__valor')
        ).order_by('-total_pontos')[:5]
        
        # Histórico de interações recentes
        interacoes_recentes = HistoricoCliente.objects.order_by('-data_interacao')[:10]

        # Dados para gráfico de crescimento
        crescimento_mensal = Cliente.objects.annotate(
            mes=TruncMonth('created_at')
        ).values('mes').annotate(
            total=Count('id')
        ).order_by('mes')

        crescimento_mensal_labels = [item['mes'].strftime('%Y-%m') for item in crescimento_mensal]
        crescimento_mensal_data = [item['total'] for item in crescimento_mensal]

        # Adiciona os dados ao contexto
        context['total_clientes'] = total_clientes
        context['clientes_ativos'] = clientes_ativos
        context['clientes_novos_mes'] = clientes_novos_mes
        context['total_pontos_acumulados'] = total_pontos_acumulados
        context['total_pontos_usados'] = total_pontos_usados
        context['tipo_cliente_data'] = tipo_cliente_data
        context['categoria_data'] = categoria_data
        context['clientes_vip'] = clientes_vip
        context['clientes_top_pontos'] = clientes_top_pontos
        context['interacoes_recentes'] = interacoes_recentes
        context['crescimento_labels'] = crescimento_mensal_labels
        context['crescimento_data'] = crescimento_mensal_data

        return context


from django.http import JsonResponse
from django.db.models import Q
from .models import Cliente # Supondo que o modelo Cliente está no mesmo app
from decimal import Decimal

def buscar_clientes_api(request):
    """
    API para buscar clientes por nome, BI, NIF ou telefone.
    Retorna uma lista de clientes em formato JSON.
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Método não permitido.'}, status=405)

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'success': True, 'clientes': []})

    # Usar Q objects para combinar buscas em múltiplos campos
    # A busca é case-insensitive (icontains)
    clientes_encontrados = Cliente.objects.filter(
        ativo=True,
        bloqueado=False
    ).filter(
        Q(nome_completo__icontains=q) | 
        Q(razao_social__icontains=q) | 
        Q(bi__icontains=q) |
        Q(nif__icontains=q) |
        Q(telefone__icontains=q) |
        Q(whatsapp__icontains=q)
    ).values('id', 'nome_completo', 'razao_social', 'nif', 'bi', 'tipo_cliente')[:10]

    # Formatar os resultados para uma resposta mais limpa
    clientes_formatados = []
    for c in clientes_encontrados:
        if c['tipo_cliente'] == 'pessoa_fisica':
            nome_exibicao = c['nome_completo']
            identificacao = f"BI: {c['bi']}"
        else:
            nome_exibicao = c['razao_social']
            identificacao = f"NIF: {c['nif']}"
        
        clientes_formatados.append({
            'id': c['id'],
            'nome_exibicao': nome_exibicao,
            'identificacao': identificacao,
        })
    
    return JsonResponse({'success': True, 'clientes': clientes_formatados})

class ClienteListView(ListView):
    model = Cliente
    template_name = "clientes/lista.html"
    context_object_name = "clientes"


class ClienteDetailView(DetailView):
    model = Cliente
    template_name = "clientes/detalhe.html"
    context_object_name = "cliente"


class ClienteCreateView(CreateView):
    model = Cliente
    fields = "__all__"
    template_name = "clientes/form.html"
    success_url = reverse_lazy("clientes:lista")


class ClienteUpdateView(UpdateView):
    model = Cliente
    fields = "__all__"
    template_name = "clientes/form.html"
    success_url = reverse_lazy("clientes:lista")


class ClienteDeleteView(DeleteView):
    model = Cliente
    template_name = "clientes/confirmar_excluir.html"
    success_url = reverse_lazy("clientes:lista")


def toggle_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    cliente.ativo = not cliente.ativo
    cliente.save()
    return redirect("clientes:lista")


# -------------------------
# CATEGORIA CLIENTE
# -------------------------
class CategoriaClienteListView(ListView):
    model = CategoriaCliente
    template_name = "clientes/categoria_lista.html"
    context_object_name = "categorias"


class CategoriaClienteDetailView(DetailView):
    model = CategoriaCliente
    template_name = "clientes/categoria_detalhe.html"
    context_object_name = "categoria"


class CategoriaClienteCreateView(CreateView):
    model = CategoriaCliente
    fields = "__all__"
    template_name = "clientes/categoria_form.html"
    success_url = reverse_lazy("clientes:categorias")


class CategoriaClienteUpdateView(UpdateView):
    model = CategoriaCliente
    fields = "__all__"
    template_name = "clientes/categoria_form.html"
    success_url = reverse_lazy("clientes:categorias")


class CategoriaClienteDeleteView(DeleteView):
    model = CategoriaCliente
    template_name = "clientes/categoria_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:categorias")


# -------------------------
# ENDEREÇO CLIENTE
# -------------------------
class EnderecoClienteListView(ListView):
    model = EnderecoCliente
    template_name = "clientes/endereco_lista.html"
    context_object_name = "enderecos"


class EnderecoClienteDetailView(DetailView):
    model = EnderecoCliente
    template_name = "clientes/endereco_detalhe.html"
    context_object_name = "endereco"


class EnderecoClienteCreateView(CreateView):
    model = EnderecoCliente
    fields = "__all__"
    template_name = "clientes/endereco_form.html"
    success_url = reverse_lazy("clientes:enderecos")


class EnderecoClienteUpdateView(UpdateView):
    model = EnderecoCliente
    fields = "__all__"
    template_name = "clientes/endereco_form.html"
    success_url = reverse_lazy("clientes:enderecos")


class EnderecoClienteDeleteView(DeleteView):
    model = EnderecoCliente
    template_name = "clientes/endereco_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:enderecos")


# -------------------------
# CONTATO CLIENTE
# -------------------------
class ContatoClienteListView(ListView):
    model = ContatoCliente
    template_name = "clientes/contato_lista.html"
    context_object_name = "contatos"


class ContatoClienteDetailView(DetailView):
    model = ContatoCliente
    template_name = "clientes/contato_detalhe.html"
    context_object_name = "contato"


class ContatoClienteCreateView(CreateView):
    model = ContatoCliente
    fields = "__all__"
    template_name = "clientes/contato_form.html"
    success_url = reverse_lazy("clientes:contatos")


class ContatoClienteUpdateView(UpdateView):
    model = ContatoCliente
    fields = "__all__"
    template_name = "clientes/contato_form.html"
    success_url = reverse_lazy("clientes:contatos")


class ContatoClienteDeleteView(DeleteView):
    model = ContatoCliente
    template_name = "clientes/contato_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:contatos")


# -------------------------
# HISTORICO CLIENTE
# -------------------------
class HistoricoClienteListView(ListView):
    model = HistoricoCliente
    template_name = "clientes/historico_lista.html"
    context_object_name = "historicos"


class HistoricoClienteDetailView(DetailView):
    model = HistoricoCliente
    template_name = "clientes/historico_detalhe.html"
    context_object_name = "historico"


class HistoricoClienteCreateView(CreateView):
    model = HistoricoCliente
    fields = "__all__"
    template_name = "clientes/historico_form.html"
    success_url = reverse_lazy("clientes:historicos")


class HistoricoClienteUpdateView(UpdateView):
    model = HistoricoCliente
    fields = "__all__"
    template_name = "clientes/historico_form.html"
    success_url = reverse_lazy("clientes:historicos")


class HistoricoClienteDeleteView(DeleteView):
    model = HistoricoCliente
    template_name = "clientes/historico_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:historicos")


# -------------------------
# CARTÃO FIDELIDADE
# -------------------------
class CartaoFidelidadeListView(ListView):
    model = CartaoFidelidade
    template_name = "clientes/cartao_lista.html"
    context_object_name = "cartoes"


class CartaoFidelidadeDetailView(DetailView):
    model = CartaoFidelidade
    template_name = "clientes/cartao_detalhe.html"
    context_object_name = "cartao"


class CartaoFidelidadeCreateView(CreateView):
    model = CartaoFidelidade
    fields = "__all__"
    template_name = "clientes/cartao_form.html"
    success_url = reverse_lazy("clientes:cartoes")


class CartaoFidelidadeUpdateView(UpdateView):
    model = CartaoFidelidade
    fields = "__all__"
    template_name = "clientes/cartao_form.html"
    success_url = reverse_lazy("clientes:cartoes")


class CartaoFidelidadeDeleteView(DeleteView):
    model = CartaoFidelidade
    template_name = "clientes/cartao_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:cartoes")


# -------------------------
# MOVIMENTAÇÃO FIDELIDADE
# -------------------------
class MovimentacaoFidelidadeListView(ListView):
    model = MovimentacaoFidelidade
    template_name = "clientes/movimentacao_lista.html"
    context_object_name = "movimentacoes"


class MovimentacaoFidelidadeDetailView(DetailView):
    model = MovimentacaoFidelidade
    template_name = "clientes/movimentacao_detalhe.html"
    context_object_name = "movimentacao"


class MovimentacaoFidelidadeCreateView(CreateView):
    model = MovimentacaoFidelidade
    fields = "__all__"
    template_name = "clientes/movimentacao_form.html"
    success_url = reverse_lazy("clientes:movimentacoes")


class MovimentacaoFidelidadeUpdateView(UpdateView):
    model = MovimentacaoFidelidade
    fields = "__all__"
    template_name = "clientes/movimentacao_form.html"
    success_url = reverse_lazy("clientes:movimentacoes")


class MovimentacaoFidelidadeDeleteView(DeleteView):
    model = MovimentacaoFidelidade
    template_name = "clientes/movimentacao_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:movimentacoes")


# -------------------------
# PREFERENCIA CLIENTE
# -------------------------
class PreferenciaClienteListView(ListView):
    model = PreferenciaCliente
    template_name = "clientes/preferencia_lista.html"
    context_object_name = "preferencias"


class PreferenciaClienteDetailView(DetailView):
    model = PreferenciaCliente
    template_name = "clientes/preferencia_detalhe.html"
    context_object_name = "preferencia"


class PreferenciaClienteCreateView(CreateView):
    model = PreferenciaCliente
    fields = "__all__"
    template_name = "clientes/preferencia_form.html"
    success_url = reverse_lazy("clientes:preferencias")


class PreferenciaClienteUpdateView(UpdateView):
    model = PreferenciaCliente
    fields = "__all__"
    template_name = "clientes/preferencia_form.html"
    success_url = reverse_lazy("clientes:preferencias")


class PreferenciaClienteDeleteView(DeleteView):
    model = PreferenciaCliente
    template_name = "clientes/preferencia_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:preferencias")


# -------------------------
# TELEFONE CLIENTE
# -------------------------
class TelefoneClienteListView(ListView):
    model = TelefoneCliente
    template_name = "clientes/telefone_lista.html"
    context_object_name = "telefones"


class TelefoneClienteDetailView(DetailView):
    model = TelefoneCliente
    template_name = "clientes/telefone_detalhe.html"
    context_object_name = "telefone"


class TelefoneClienteCreateView(CreateView):
    model = TelefoneCliente
    fields = "__all__"
    template_name = "clientes/telefone_form.html"
    success_url = reverse_lazy("clientes:telefones")


class TelefoneClienteUpdateView(UpdateView):
    model = TelefoneCliente
    fields = "__all__"
    template_name = "clientes/telefone_form.html"
    success_url = reverse_lazy("clientes:telefones")


class TelefoneClienteDeleteView(DeleteView):
    model = TelefoneCliente
    template_name = "clientes/telefone_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:telefones")


# -------------------------
# GRUPO CLIENTE
# -------------------------
class GrupoClienteListView(ListView):
    model = GrupoCliente
    template_name = "clientes/grupo_lista.html"
    context_object_name = "grupos"


class GrupoClienteDetailView(DetailView):
    model = GrupoCliente
    template_name = "clientes/grupo_detalhe.html"
    context_object_name = "grupo"


class GrupoClienteCreateView(CreateView):
    model = GrupoCliente
    fields = "__all__"
    template_name = "clientes/grupo_form.html"
    success_url = reverse_lazy("clientes:grupos")


class GrupoClienteUpdateView(UpdateView):
    model = GrupoCliente
    fields = "__all__"
    template_name = "clientes/grupo_form.html"
    success_url = reverse_lazy("clientes:grupos")


class GrupoClienteDeleteView(DeleteView):
    model = GrupoCliente
    template_name = "clientes/grupo_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:grupos")


# -------------------------
# PROGRAMA FIDELIDADE
# -------------------------
class ProgramaFidelidadeListView(ListView):
    model = ProgramaFidelidade
    template_name = "clientes/programa_lista.html"
    context_object_name = "programas"


class ProgramaFidelidadeDetailView(DetailView):
    model = ProgramaFidelidade
    template_name = "clientes/programa_detalhe.html"
    context_object_name = "programa"


class ProgramaFidelidadeCreateView(CreateView):
    model = ProgramaFidelidade
    fields = "__all__"
    template_name = "clientes/programa_form.html"
    success_url = reverse_lazy("clientes:programas")


class ProgramaFidelidadeUpdateView(UpdateView):
    model = ProgramaFidelidade
    fields = "__all__"
    template_name = "clientes/programa_form.html"
    success_url = reverse_lazy("clientes:programas")


class ProgramaFidelidadeDeleteView(DeleteView):
    model = ProgramaFidelidade
    template_name = "clientes/programa_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:programas")


# -------------------------
# PONTO
# -------------------------
class PontoListView(ListView):
    model = Ponto
    template_name = "clientes/ponto_lista.html"
    context_object_name = "pontos"


class PontoDetailView(DetailView):
    model = Ponto
    template_name = "clientes/ponto_detalhe.html"
    context_object_name = "ponto"


class PontoCreateView(CreateView):
    model = Ponto
    fields = "__all__"
    template_name = "clientes/ponto_form.html"
    success_url = reverse_lazy("clientes:pontos")


class PontoUpdateView(UpdateView):
    model = Ponto
    fields = "__all__"
    template_name = "clientes/ponto_form.html"
    success_url = reverse_lazy("clientes:pontos")


class PontoDeleteView(DeleteView):
    model = Ponto
    template_name = "clientes/ponto_confirmar_excluir.html"
    success_url = reverse_lazy("clientes:pontos")

######################
# Views de contrato
######################

"""Staff and customer-side contract workflow, scoped to current tenant/client."""
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django import forms
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template import Context, engines
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente
from apps.funcionarios.models import Funcionario
from apps.servicos.views import empresa_da_requisicao
from apps.site.models import ClienteSite
from .forms import ModeloContratoForm
from .models import ContratoCliente, EventoContrato, ModeloContrato

logger = logging.getLogger(__name__)


def _funcionario(request):
    user = request.user
    try:
        linked = getattr(user, "funcionario", None)
    except Exception:
        linked = None
    if linked:
        return linked
    try:
        return Funcionario.objects.filter(usuario=user, ativo=True).select_related("cargo").first()
    except Exception:
        return None


def _tem_permissao(request, codigo):
    if request.user.is_superuser:
        return True
    func = _funcionario(request)
    if not func:
        return False
    cargo = getattr(func, "cargo", None)
    return bool(getattr(func, codigo, False) or getattr(cargo, codigo, False))


def _ip(request):
    # Do not trust X-Forwarded-For unless the reverse proxy is configured as trusted.
    return request.META.get("REMOTE_ADDR") or None


def _render_template(texto, cliente, empresa):
    engine = engines["django"]
    template = engine.from_string(texto)
    return template.render({"cliente": cliente, "empresa": empresa, "data_emissao": timezone.localtime().strftime("%d/%m/%Y"), "hoje": timezone.localdate()})


@login_required
def lista_contratos(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    if not (_tem_permissao(request, "pode_gerir_contrato") or _tem_permissao(request, "pode_enviar_contrato")):
        raise PermissionDenied
    # Contract tables live inside the physical tenant schema; no empresa FK is needed.
    qs = ContratoCliente.objects.select_related("cliente", "modelo", "enviado_por").prefetch_related("eventos")
    estado = request.GET.get("estado", "").strip()
    vip = request.GET.get("vip", "todos").strip()
    q = request.GET.get("q", "").strip()
    if estado in dict(ContratoCliente.STATUS_CHOICES):
        qs = qs.filter(status=estado)
    if vip == "vip":
        qs = qs.filter(cliente__vip=True)
    elif vip == "outros":
        qs = qs.filter(cliente__vip=False)
    if q:
        qs = qs.filter(cliente__nome_completo__icontains=q) | qs.filter(cliente__razao_social__icontains=q)
    modelos = {m.cliente_vip: m for m in ModeloContrato.objects.filter(ativo=True)}
    contratos_filtrados = qs.order_by("-created_at")
    ids_clientes_com_contratos = contratos_filtrados.values_list("cliente_id", flat=True).distinct()
    historico_completo = ContratoCliente.objects.select_related(
        "modelo", "enviado_por"
    ).prefetch_related("eventos").order_by("-created_at")
    clientes_com_contrato = Cliente.objects.filter(pk__in=ids_clientes_com_contratos).order_by(
        "nome_completo", "razao_social"
    ).prefetch_related(
        Prefetch("contratos", queryset=contratos_filtrados, to_attr="contratos_filtrados"),
        Prefetch("contratos", queryset=historico_completo, to_attr="historico_contratos"),
    )
    return render(request, "clientes/lista.html", {
        "contratos": contratos_filtrados[:250], "clientes_com_contrato": clientes_com_contrato,
        "clientes_disponiveis": Cliente.objects.filter(ativo=True, bloqueado=False).order_by("nome_completo")[:1000],
        "status_choices": ContratoCliente.STATUS_CHOICES, "estado": estado, "vip_filter": vip, "q": q,
        "modelo_normal": modelos.get(False), "modelo_vip": modelos.get(True),
        "pode_enviar": _tem_permissao(request, "pode_enviar_contrato"),
        "pode_gerir": _tem_permissao(request, "pode_gerir_contrato"),
    })


@login_required
@require_POST
def guardar_modelo(request, tipo):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if not _tem_permissao(request, "pode_gerir_contrato"):
        raise PermissionDenied
    vip = tipo == "vip"
    modelo = ModeloContrato.objects.filter(cliente_vip=vip).order_by("pk").first()
    form = ModeloContratoForm(request.POST, instance=modelo)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.cliente_vip = vip
        obj.atualizado_por = request.user
        obj.save()
        messages.success(request, "Modelo de contrato guardado.")
    else:
        messages.error(request, "Não foi possível guardar o modelo: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
    return redirect("clientes:lista")


@login_required
@require_POST
def enviar_contrato(request, cliente_id):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if not _tem_permissao(request, "pode_enviar_contrato"):
        raise PermissionDenied
    cliente = get_object_or_404(Cliente.objects.filter(ativo=True, bloqueado=False), pk=cliente_id)
    modelo = ModeloContrato.objects.filter(cliente_vip=cliente.vip, ativo=True).order_by("pk").first()
    texto_override = request.POST.get("conteudo", "").strip()
    if texto_override and not _tem_permissao(request, "pode_gerir_contrato"):
        raise PermissionDenied
    if texto_override:
        origem = texto_override
    elif modelo:
        origem = modelo.conteudo
    else:
        messages.error(request, "Configure primeiro o modelo para clientes VIP/não VIP.")
        return redirect("clientes:lista")
    snapshot = _render_template(origem, cliente, empresa)
    with transaction.atomic():
        contrato = ContratoCliente.objects.create(
            cliente=cliente, modelo=modelo, conteudo_snapshot=snapshot,
            status="enviado", enviado_por=request.user, enviado_em=timezone.now(),
        )
        EventoContrato.objects.create(contrato=contrato, tipo="enviado", descricao="Contrato disponibilizado no portal do cliente.", autor_usuario=request.user, ip=_ip(request))
    messages.success(request, f"Contrato #{contrato.pk} enviado para o portal do cliente.")
    return redirect("clientes:lista")


@login_required
def detalhe_contrato_staff(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    if not (_tem_permissao(request, "pode_gerir_contrato") or _tem_permissao(request, "pode_enviar_contrato")):
        raise PermissionDenied
    contrato = get_object_or_404(
        ContratoCliente.objects.select_related("cliente", "modelo", "enviado_por").prefetch_related("eventos"),
        pk=pk,
    )
    return render(request, "clientes/staff_detalhe.html", {"contrato": contrato})


class RevisarContratoForm(forms.Form):
    conteudo = forms.CharField(widget=forms.Textarea(attrs={"rows": 24, "class": "w-full rounded border p-3 font-mono"}))


@login_required
def rever_contrato(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    if not _tem_permissao(request, "pode_gerir_contrato"):
        raise PermissionDenied
    original = get_object_or_404(ContratoCliente.objects.select_related("cliente", "modelo"), pk=pk)
    if original.status != "correcao_solicitada":
        messages.error(request, "Só é possível criar uma revisão nesta área quando o cliente pediu correção.")
        return redirect("clientes:lista")
    if request.method == "POST":
        form = RevisarContratoForm(request.POST)
        if form.is_valid():
            snapshot = _render_template(form.cleaned_data["conteudo"], original.cliente, empresa)
            ultima = ContratoCliente.objects.filter(cliente=original.cliente).order_by("-versao").first()
            nova_versao = (ultima.versao + 1) if ultima else (original.versao + 1)
            with transaction.atomic():
                nova = ContratoCliente.objects.create(
                    cliente=original.cliente, modelo=original.modelo,
                    contrato_anterior=original, versao=nova_versao, conteudo_snapshot=snapshot,
                    status="enviado", enviado_por=request.user, enviado_em=timezone.now(),
                )
                EventoContrato.objects.create(contrato=original, tipo="nova_versao", descricao=f"Foi emitida a versão {nova.versao} após o pedido de correção.", autor_usuario=request.user, ip=_ip(request))
                EventoContrato.objects.create(contrato=nova, tipo="enviado", descricao=f"Nova versão emitida a partir do contrato #{original.pk}.", autor_usuario=request.user, ip=_ip(request))
            messages.success(request, f"Nova versão #{nova.pk} emitida sem alterar o conteúdo histórico do contrato anterior.")
            return redirect("clientes:lista")
    else:
        # Prefill with the previous source template where possible, but allow staff to edit only this customer's revision.
        form = RevisarContratoForm(initial={"conteudo": original.modelo.conteudo if original.modelo else original.conteudo_snapshot})
    return render(request, "clientes/rever.html", {"form": form, "contrato": original})


class ClienteContratoDetalheView(View):
    template_name = "clientes/cliente_detalhe.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("cliente_site_id"):
            return redirect("site:cliente_login")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk):
        cliente_site = get_object_or_404(ClienteSite, pk=request.session["cliente_site_id"], ativo=True)
        contrato = get_object_or_404(ContratoCliente.objects.select_related("cliente"), pk=pk, cliente__email__iexact=cliente_site.email)
        if contrato.status == "enviado":
            contrato.status = "lido"
            contrato.lido_em = timezone.now()
            contrato.save(update_fields=["status", "lido_em", "updated_at"])
            EventoContrato.objects.create(contrato=contrato, tipo="lido", descricao="O cliente abriu o contrato.", autor_cliente_site=cliente_site)
        eventos = contrato.eventos.select_related("autor_usuario", "autor_cliente_site")
        return render(request, self.template_name, {"cliente": cliente_site, "contrato": contrato, "eventos": eventos})

    def post(self, request, pk):
        cliente_site = get_object_or_404(ClienteSite, pk=request.session["cliente_site_id"], ativo=True)
        contrato = get_object_or_404(ContratoCliente.objects.select_related("cliente"), pk=pk, cliente__email__iexact=cliente_site.email)
        if contrato.status not in {"enviado", "lido"}:
            messages.error(request, "Este contrato já recebeu uma resposta ou foi substituído por uma revisão.")
            return redirect("clientes:cliente_detalhe", pk=pk)
        acao = request.POST.get("acao", "").strip()
        comentario = request.POST.get("comentario", "").strip()
        with transaction.atomic():
            if acao == "assinar":
                contrato.registar_aceite(ip=_ip(request), user_agent=request.META.get("HTTP_USER_AGENT", ""))
                EventoContrato.objects.create(contrato=contrato, tipo="assinado", descricao="O cliente registou aceite electrónico explícito.", autor_cliente_site=cliente_site, ip=_ip(request))
                messages.success(request, "Aceite registado. Guarde o identificador e o hash para consulta posterior.")
            elif acao == "rejeitar":
                contrato.status = "rejeitado"
                contrato.respondido_em = timezone.now()
                contrato.comentario_cliente = comentario
                contrato.save(update_fields=["status", "respondido_em", "comentario_cliente", "updated_at"])
                EventoContrato.objects.create(contrato=contrato, tipo="rejeitado", descricao=comentario or "Contrato rejeitado pelo cliente.", autor_cliente_site=cliente_site, ip=_ip(request))
                messages.success(request, "A rejeição foi registada.")
            elif acao == "correcao":
                if not comentario:
                    messages.error(request, "Descreva as alterações solicitadas.")
                    return redirect("clientes:cliente_detalhe", pk=pk)
                contrato.status = "correcao_solicitada"
                contrato.respondido_em = timezone.now()
                contrato.comentario_cliente = comentario
                contrato.save(update_fields=["status", "respondido_em", "comentario_cliente", "updated_at"])
                EventoContrato.objects.create(contrato=contrato, tipo="correcao", descricao=comentario, autor_cliente_site=cliente_site, ip=_ip(request))
                messages.success(request, "Pedido de correção enviado à empresa.")
            else:
                return HttpResponseBadRequest("Acção inválida.")
        return redirect("clientes:cliente_detalhe", pk=pk)


######################
# FIM Views de contrato
#####################