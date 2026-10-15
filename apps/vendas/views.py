# apps/vendas/views.py
"""
Views do módulo de Vendas.

Isolamento físico via django-tenants: cada schema pertence a uma única
empresa, então NENHUMA query aqui filtra por `empresa=...` (o campo nem
existe mais nos modelos de `vendas`). Quando é preciso algum dado da
empresa (NIF, regime fiscal, nome), usa-se `request.user.empresa`
(Usuario é SHARED e carrega essa FK legitimamente) ou `connection.tenant`
(já usado nos models). O modelo `Loja` foi removido do sistema.
"""

import decimal
import json
import logging
import traceback
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.core.serializers.json import DjangoJSONEncoder

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, AccessMixin
from django.core.cache import caches
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Q, Sum, Count, F, Avg, DecimalField
from django.http import FileResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics, viewsets, permissions, serializers

from apps.core.views import BaseMPAView

from apps.fiscal.models import TaxaIVAAGT
from apps.fiscal.services.pdf_agt_service import PDFDocumentoService

from apps.funcionarios.models import Funcionario

from apps.produtos.models import Produto
from apps.servicos.models import Servico

from apps.clientes.models import Cliente
from apps.vendas.serializers import ItemVendaSerializer, VendaSerializer

from .models import (
    ItemFatura, ItemProforma, Venda, ItemVenda, PagamentoVenda, FormaPagamento,
    Orcamento, ItemOrcamento, DevolucaoVenda,
    Comissao, Convenio, Entrega, FaturaCredito, Recibo, FaturaProforma,
    NotaCredito, ItemNotaCredito, NotaDebito,
    ItemNotaDebito, DocumentoTransporte, ItemDocumentoTransporte,
    MetaVenda
)
from .forms import (
    AgendarEntregaForm, ConvenioForm, DevolucaoForm, VendaForm, PagamentoVendaForm, NotaCreditoForm,
    NotaDebitoForm, DocumentoTransporteForm
)
from .services import validar_itens_por_regime
from .tasks import verificar_margem_critica

from django.core.cache import cache as bi_cache
from decimal import Decimal, InvalidOperation
from django.core.serializers.json import DjangoJSONEncoder


# ---------------------------------------------------------------------
# 1) HELPERS COMUNS (FP / FT)
# ---------------------------------------------------------------------
IVA_PADRAO = Decimal('14.00')
CENTIMO = Decimal('0.01')




logger = logging.getLogger(__name__)


# =====================================
# MIXINS / PERMISSÕES
# =====================================

class BaseVendaView(LoginRequiredMixin):
    """
    View base para o módulo de vendas.

    NÃO existe mais filtro por empresa: o isolamento já é feito pelo schema
    (django-tenants). `get_empresa()` só serve para exibir dados da empresa
    (NIF, nome, regime fiscal), nunca para filtrar querysets de Venda/etc.
    """

    def get_empresa(self):
        return getattr(self.request.user, 'empresa', None)


class PermissaoAcaoMixin(AccessMixin):
    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            funcionario = request.user.funcionario
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            if not funcionario or not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('core_tenants:dashboard'))

        return super().dispatch(request, *args, **kwargs)


def requer_permissao(acao_requerida):
    """Decorator para FBVs, usando a lógica do modelo Funcionario."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            funcionario = getattr(request.user, "funcionario", None)
            if not funcionario:
                return JsonResponse(
                    {"success": False, "message": "Usuário não está vinculado a um funcionário."},
                    status=403
                )
            if not funcionario.pode_realizar_acao(acao_requerida):
                return JsonResponse(
                    {"success": False, "message": f"Você não tem permissão para realizar a ação '{acao_requerida}'."},
                    status=403
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


# =====================================
# VENDAS (FR / VD / TV)
# =====================================

class VendasView(BaseMPAView):
    template_name = 'vendas/vendas.html'
    module_name = 'vendas'
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()

        periodo = self.request.GET.get('periodo', 'mes')
        status_filtro = self.request.GET.get('status', '')
        vendedor_id = self.request.GET.get('vendedor', '')
        cliente_nome = self.request.GET.get('cliente', '')
        valor_min = self.request.GET.get('valor_min', '')
        sort = self.request.GET.get('sort', '-data_venda')

        vendas = Venda.objects.all()

        if periodo == 'hoje':
            vendas = vendas.filter(data_venda__date=hoje)
        elif periodo == 'semana':
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            vendas = vendas.filter(data_venda__date__gte=inicio_semana)
        elif periodo == 'mes':
            vendas = vendas.filter(data_venda__year=hoje.year, data_venda__month=hoje.month)
        elif periodo == 'trimestre':
            inicio_trimestre = hoje.replace(month=((hoje.month - 1) // 3) * 3 + 1, day=1)
            vendas = vendas.filter(data_venda__date__gte=inicio_trimestre)

        if status_filtro:
            vendas = vendas.filter(status=status_filtro)
        if vendedor_id:
            vendas = vendas.filter(vendedor_id=vendedor_id)
        if cliente_nome:
            vendas = vendas.filter(
                Q(cliente__nome_completo__icontains=cliente_nome) |
                Q(cliente__nif__icontains=cliente_nome)
            )
        if valor_min:
            try:
                vendas = vendas.filter(total__gte=float(valor_min))
            except ValueError:
                pass

        vendas = vendas.order_by(sort)

        paginator = Paginator(vendas, self.paginate_by)
        page_number = self.request.GET.get('page')
        vendas_page = paginator.get_page(page_number)

        vendas_mes = Venda.objects.filter(
            data_venda__year=hoje.year, data_venda__month=hoje.month, status='finalizada'
        ).aggregate(total=Sum('total'), quantidade=Count('id'))

        vendas_hoje_qs = Venda.objects.filter(data_venda__date=hoje)
        vendas_hoje_total = vendas_hoje_qs.filter(status='finalizada').aggregate(total=Sum('total'))['total'] or 0
        vendas_hoje_count = vendas_hoje_qs.filter(status='finalizada').count()
        vendas_pendentes_count = vendas_hoje_qs.filter(status='pendente').count()
        vendas_canceladas_count = vendas_hoje_qs.filter(status='cancelada').count()

        vendedores = Funcionario.objects.filter(ativo=True).values('id', 'nome_completo')

        vendas_total = vendas.aggregate(total=Sum('total'))['total'] or 0

        context.update({
            'vendas': vendas_page,
            'vendas_total': vendas_total,
            'vendas_stats': {
                'vendas_mes': float(vendas_mes['total'] or 0),
                'quantidade_mes': vendas_mes['quantidade'] or 0,
                'ticket_medio': float(vendas_mes['total'] or 0) / max(vendas_mes['quantidade'] or 1, 1),
                'clientes_mes': vendas.filter(
                    data_venda__year=hoje.year, data_venda__month=hoje.month
                ).values('cliente').distinct().count(),
                'vendas_hoje': vendas_hoje_count,
                'vendas_hoje_total': float(vendas_hoje_total),
                'vendas_pendentes': vendas_pendentes_count,
                'vendas_canceladas': vendas_canceladas_count,
            },
            'vendedores': vendedores,
            'paginator': paginator,
            'is_paginated': vendas_page.has_other_pages(),
            'page_obj': vendas_page,
        })
        return context


class VendaDetailView(BaseVendaView, DetailView):
    """Detalhes de uma venda: itens, pagamentos e orçamento de origem (se houver)."""
    model = Venda
    template_name = 'vendas/venda_detail.html'
    context_object_name = 'venda'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = self.object

        context.update({
            'title': f'Venda {venda.numero_documento}',
            'itens': venda.itens.select_related('produto'),
            'pagamentos': venda.pagamentos.all(),
            'orcamento_origem': getattr(venda, 'orcamento_origem', None),
            'pode_editar': venda.status in ['rascunho', 'pendente'],
            'pode_cancelar': venda.status in ['pendente', 'finalizada'],
            'resumo': {
                'subtotal': venda.subtotal,
                'desconto_total': venda.desconto_valor,
                'criada_em': venda.data_venda,
                'status': venda.status,
            },
        })
        return context


class VendaCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'vender'

    model = Venda
    form_class = VendaForm
    template_name = 'vendas/venda_form.html'
    success_url = reverse_lazy('vendas:lista')

    def form_valid(self, form):
        form.instance.vendedor = getattr(self.request.user, 'funcionario', None)
        form.instance.usuario_criacao = self.request.user

        with transaction.atomic():
            response = super().form_valid(form)

            if not form.instance.numero_documento:
                form.instance.numero_documento = f"V{form.instance.id:06d}"
                form.instance.save(update_fields=['numero_documento'])

            messages.success(self.request, f'Venda {form.instance.numero_documento} criada com sucesso!')
            return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': 'Nova Venda',
            'clientes': Cliente.objects.filter(ativo=True),
            'produtos': Produto.objects.filter(ativo=True),
            'formas_pagamento': FormaPagamento.objects.filter(ativa=True),
        })
        return context


class VendaUpdateView(BaseVendaView, UpdateView):
    model = Venda
    form_class = VendaForm
    template_name = 'vendas/venda_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'pendente']:
            messages.error(self.request, 'Não é possível editar esta venda.')
            return redirect(self.get_success_url())

        form.instance.usuario_modificacao = self.request.user
        messages.success(self.request, 'Venda atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': f'Editar Venda {self.object.numero_documento}',
            'clientes': Cliente.objects.filter(ativo=True),
            'produtos': Produto.objects.filter(ativo=True),
            'formas_pagamento': FormaPagamento.objects.filter(ativa=True),
        })
        return context


class CancelarVendaView(BaseVendaView, View):
    acao_requerida = 'cancelar_venda'

    def post(self, request, pk):
        venda = get_object_or_404(Venda, pk=pk)

        if venda.status == 'cancelada':
            messages.warning(request, 'Venda já está cancelada.')
        elif (venda.total > Decimal('1000')
              and not (getattr(request.user, 'funcionario', None)
                       and request.user.funcionario.pode_realizar_acao('cancelar_venda_alto_valor'))):
            messages.error(request, "Cancelações de alto valor requerem autorização superior.")
            return redirect('vendas:detail', pk=pk)
        elif venda.status not in ['pendente', 'finalizada']:
            messages.error(request, 'Não é possível cancelar esta venda.')
        else:
            with transaction.atomic():
                for item in venda.itens.all():
                    if item.produto:
                        item.produto.estoque_atual = F('estoque_atual') + item.quantidade
                        item.produto.save(update_fields=['estoque_atual'])

                venda.status = 'cancelada'
                venda.data_cancelamento = timezone.now()
                venda.motivo_cancelamento = request.POST.get('motivo', 'Cancelamento solicitado')
                venda.usuario_cancelamento = request.user
                venda.save()

                messages.success(request, f'Venda {venda.numero_documento} cancelada com sucesso!')

        return redirect('vendas:detail', pk=pk)


class VendaDashboardView(BaseVendaView, TemplateView):
    template_name = 'vendas/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)

        vendas_hoje = Venda.objects.filter(data_venda__date=hoje, status='finalizada').aggregate(
            total=Sum('total'), quantidade=Count('id'))
        vendas_mes = Venda.objects.filter(data_venda__gte=mes_atual, status='finalizada').aggregate(
            total=Sum('total'), quantidade=Count('id'))

        top_produtos = ItemVenda.objects.filter(
            venda__data_venda__gte=mes_atual, venda__status='finalizada'
        ).values('produto__nome_comercial').annotate(
            quantidade_vendida=Sum('quantidade'), total=Sum('total')
        ).order_by('-quantidade_vendida')[:10]

        vendas_por_pagamento = Venda.objects.filter(
            data_venda__gte=mes_atual, status='finalizada'
        ).values('forma_pagamento__nome').annotate(total=Sum('total'), quantidade=Count('id'))

        context.update({
            'title': 'Dashboard de Vendas',
            'vendas_hoje': vendas_hoje,
            'vendas_mes': vendas_mes,
            'top_produtos': top_produtos,
            'vendas_por_pagamento': vendas_por_pagamento,
        })
        return context


class VendaAnalyticsView(BaseVendaView, TemplateView):
    template_name = 'vendas/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = self.request.GET.get('periodo', '30')
        data_inicio = timezone.now().date() - timedelta(days=int(periodo))

        vendas_por_dia = Venda.objects.filter(data_venda__gte=data_inicio, status='finalizada').extra(
            select={'dia': 'date(data_venda)'}
        ).values('dia').annotate(total=Sum('total'), quantidade=Count('id')).order_by('dia')

        vendas_por_vendedor = Venda.objects.filter(data_venda__gte=data_inicio, status='finalizada').values(
            'vendedor__nome_completo'
        ).annotate(total=Sum('total'), quantidade=Count('id')).order_by('-total')

        ticket_medio = Venda.objects.filter(
            data_venda__gte=data_inicio, status='finalizada'
        ).aggregate(Avg('total'))['total__avg'] or 0

        context.update({
            'title': 'Analytics de Vendas',
            'vendas_por_dia': vendas_por_dia,
            'vendas_por_vendedor': vendas_por_vendedor,
            'ticket_medio': ticket_medio,
            'periodo': periodo,
        })
        return context


class VendaKPIsView(BaseVendaView, TemplateView):
    template_name = 'vendas/kpis.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)
        mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)

        kpis_atual = Venda.objects.filter(data_venda__gte=mes_atual, status='finalizada').aggregate(
            faturamento=Sum('total'), quantidade_vendas=Count('id'), ticket_medio=Avg('total'))
        kpis_anterior = Venda.objects.filter(
            data_venda__gte=mes_anterior, data_venda__lt=mes_atual, status='finalizada'
        ).aggregate(faturamento=Sum('total'), quantidade_vendas=Count('id'), ticket_medio=Avg('total'))

        def calcular_crescimento(atual, anterior):
            if anterior and anterior > 0:
                return ((atual - anterior) / anterior) * 100
            return 0 if atual == 0 else 100

        context.update({
            'title': 'KPIs de Vendas',
            'kpis_atual': kpis_atual,
            'kpis_anterior': kpis_anterior,
            'crescimento_faturamento': calcular_crescimento(kpis_atual['faturamento'] or 0, kpis_anterior['faturamento'] or 0),
            'crescimento_vendas': calcular_crescimento(kpis_atual['quantidade_vendas'] or 0, kpis_anterior['quantidade_vendas'] or 0),
        })
        return context


class MetasVendaView(BaseVendaView, TemplateView):
    template_name = 'vendas/metas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)

        meta_mes = MetaVenda.objects.filter(mes=mes_atual.month, ano=mes_atual.year, vendedor__isnull=True).first()

        vendas_mes = Venda.objects.filter(data_venda__gte=mes_atual, status='finalizada').aggregate(
            total_vendido=Sum('total'), quantidade_vendas=Count('id'))

        percentual_faturamento = 0
        percentual_quantidade = 0
        if meta_mes:
            if meta_mes.meta_faturamento:
                percentual_faturamento = (vendas_mes['total_vendido'] or 0) / float(meta_mes.meta_faturamento) * 100
            if meta_mes.meta_quantidade_vendas:
                percentual_quantidade = (vendas_mes['quantidade_vendas'] or 0) / meta_mes.meta_quantidade_vendas * 100

        context.update({
            'title': 'Metas de Vendas',
            'meta_mes': meta_mes,
            'vendas_mes': vendas_mes,
            'percentual_faturamento': percentual_faturamento,
            'percentual_quantidade': percentual_quantidade,
        })
        return context


# =====================================
# ORÇAMENTOS
# =====================================

class OrcamentoListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Orcamento
    template_name = "vendas/orcamento_list.html"
    context_object_name = "orcamentos"
    permission_required = "vendas.view_orcamento"
    paginate_by = 20

    def get_queryset(self):
        qs = Orcamento.objects.all().select_related("cliente", "vendedor")
        status_filtro = self.request.GET.get("status")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        return qs


class OrcamentoDetailView(DetailView):
    model = Orcamento
    template_name = "orcamentos/orcamento_detail.html"
    context_object_name = "orcamento"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orcamento = self.get_object()
        context["itens"] = orcamento.itens.all()
        context["pode_converter"] = (orcamento.status == "aprovado")
        return context


def converter_orcamento_em_venda(request, pk):
    """Converte um orçamento aprovado em venda."""
    orcamento = get_object_or_404(Orcamento, pk=pk)

    if orcamento.status != "aprovado":
        messages.error(request, "Somente orçamentos aprovados podem ser convertidos em venda.")
        return redirect("vendas:orcamento_detail", pk=orcamento.pk)

    if orcamento.venda_convertida:
        messages.warning(request, "Este orçamento já foi convertido em uma venda.")
        return redirect("vendas:orcamento_detail", pk=orcamento.pk)

    with transaction.atomic():
        venda = Venda.objects.create(
            cliente=orcamento.cliente,
            subtotal=orcamento.valor_subtotal,
            desconto_valor=orcamento.valor_desconto,
            total=orcamento.total,
            status='finalizada',
            observacoes=f"Venda originada do orçamento {orcamento.numero_orcamento}"
        )

        for item in orcamento.itens.all():
            venda.itens.create(
                produto=item.produto,
                quantidade=item.quantidade,
                preco_unitario=item.valor_unitario,
                total=item.total,
            )

        orcamento.status = "convertido"
        orcamento.venda_convertida = venda
        orcamento.save()

    messages.success(request, f"Orçamento {orcamento.numero_orcamento} convertido em venda {venda.id}.")
    return redirect("vendas:detail", pk=venda.pk)


class OrcamentoCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Orcamento
    template_name = "vendas/orcamento_form.html"
    fields = ["numero_orcamento", "cliente", "data_validade", "valor_subtotal", "valor_desconto",
              "total", "status", "observacoes"]
    permission_required = "vendas.add_orcamento"
    success_url = reverse_lazy("vendas:orcamento_lista")

    def form_valid(self, form):
        form.instance.vendedor = self.request.user
        return super().form_valid(form)


class OrcamentoUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Orcamento
    template_name = "vendas/orcamento_form.html"
    fields = ["cliente", "data_validade", "valor_subtotal", "valor_desconto", "total", "status", "observacoes"]
    permission_required = "vendas.change_orcamento"
    success_url = reverse_lazy("vendas:orcamento_lista")


class OrcamentoDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Orcamento
    template_name = "vendas/orcamento_confirm_delete.html"
    permission_required = "vendas.delete_orcamento"
    success_url = reverse_lazy("vendas:orcamento_lista")


class OrcamentoConverterView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "vendas.add_venda"

    def post(self, request, pk):
        orcamento = get_object_or_404(Orcamento, pk=pk)

        if orcamento.status in ["convertido", "cancelado", "expirado"]:
            messages.error(request, "Este orçamento não pode ser convertido.")
            return redirect("vendas:orcamento_detail", pk=orcamento.pk)

        with transaction.atomic():
            venda = Venda.objects.create(
                cliente=orcamento.cliente,
                subtotal=orcamento.valor_subtotal,
                desconto_valor=orcamento.valor_desconto,
                total=orcamento.total,
                status="finalizada",
                observacoes=f"Venda originada do orçamento #{orcamento.numero_orcamento}",
            )

            for item in orcamento.itens.all():
                ItemVenda.objects.create(
                    venda=venda,
                    produto=item.produto,
                    quantidade=item.quantidade,
                    preco_unitario=item.valor_unitario,
                    total=item.total,
                )

            orcamento.status = "convertido"
            orcamento.venda_convertida = venda
            orcamento.save()

        messages.success(request, f"Orçamento {orcamento.numero_orcamento} convertido em venda {venda.id}.")
        return redirect("vendas:detail", pk=venda.pk)


# =====================================
# PAGAMENTOS
# =====================================

class PagamentoListView(BaseVendaView, ListView):
    model = PagamentoVenda
    template_name = 'vendas/pagamento_lista.html'
    context_object_name = 'pagamentos'

    def get_queryset(self):
        venda_pk = self.kwargs.get('venda_pk')
        return PagamentoVenda.objects.filter(venda__pk=venda_pk).order_by('-data_pagamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        context.update({'venda': venda, 'title': f'Pagamentos - Venda {venda.numero_documento}'})
        return context


class PagamentoCreateView(BaseVendaView, CreateView):
    model = PagamentoVenda
    form_class = PagamentoVendaForm
    template_name = 'vendas/pagamento_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:pagamento_lista', kwargs={'venda_pk': self.kwargs.get('venda_pk')})

    def form_valid(self, form):
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        form.instance.venda = venda
        messages.success(self.request, 'Pagamento registrado com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        context.update({'venda': venda, 'title': f'Novo Pagamento - Venda {venda.numero_documento}'})
        return context


class PagamentoDetailView(BaseVendaView, DetailView):
    model = PagamentoVenda
    template_name = 'vendas/pagamento_detail.html'
    context_object_name = 'pagamento'
    queryset = PagamentoVenda.objects.all()


class EstornarPagamentoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'estornar_pagamento'

    def post(self, request, pk):
        pagamento = get_object_or_404(PagamentoVenda, pk=pk)

        if pagamento.status == 'estornado':
            messages.warning(request, 'O pagamento já está marcado como estornado. Nenhuma ação foi executada.')
        else:
            try:
                with transaction.atomic():
                    pagamento.status = 'estornado'
                    pagamento.data_estorno = timezone.now()
                    pagamento.usuario_estorno = request.user
                    pagamento.motivo_estorno = request.POST.get('motivo', 'Estorno via sistema (motivo não especificado)')
                    pagamento.save()

                    pagamento.venda.calcular_saldo_e_atualizar_status()

                    messages.success(request, f'Pagamento de AO {pagamento.valor_pago} estornado com sucesso.')
            except Exception as e:
                messages.error(request, f'Falha crítica ao estornar pagamento. Transação revertida. Erro: {e}')
                logger.error(f"Erro no estorno de PagamentoVenda {pk}: {e}", exc_info=True)

        return redirect('vendas:pagamento_detail', pk=pk)


class PagamentoCartaoView(BaseVendaView, TemplateView):
    template_name = 'vendas/pagamento_cartao.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Pagamento Cartão'
        return context


class PagamentoConvenioView(BaseVendaView, TemplateView):
    template_name = 'vendas/pagamento_convenio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Pagamento Convênio'
        return context


class PagamentoCrediarioView(BaseVendaView, TemplateView):
    template_name = 'vendas/pagamento_crediario.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Pagamento Crediário'
        return context


# =====================================
# DEVOLUÇÕES E TROCAS
# =====================================

class DevolucaoListView(BaseVendaView, ListView):
    model = DevolucaoVenda
    template_name = 'vendas/devolucao_lista.html'
    context_object_name = 'devolucoes'
    paginate_by = 20

    def get_queryset(self):
        return DevolucaoVenda.objects.select_related('venda_original', 'cliente').order_by('-data_devolucao')


class DevolucaoVendaView(BaseVendaView, CreateView):
    acao_requerida = 'fazer_devolucao'

    model = DevolucaoVenda
    form_class = DevolucaoForm
    template_name = 'vendas/devolucao_form.html'
    success_url = reverse_lazy('vendas:devolucao_lista')

    def get_initial(self):
        initial = super().get_initial()
        venda = get_object_or_404(Venda, pk=self.kwargs.get('pk'))
        initial['venda_original'] = venda
        initial['cliente'] = venda.cliente
        return initial

    def form_valid(self, form):
        form.instance.solicitante = self.request.user

        with transaction.atomic():
            response = super().form_valid(form)

            devolucao = form.instance
            for item_dev in devolucao.itens.all():
                produto = item_dev.item_venda_original.produto
                if produto:
                    produto.estoque_atual = F('estoque_atual') + item_dev.quantidade_devolvida
                    produto.save(update_fields=['estoque_atual'])

            messages.success(self.request, 'Devolução registrada com sucesso!')
            return response


class DevolucaoDetailView(BaseVendaView, DetailView):
    model = DevolucaoVenda
    template_name = 'vendas/devolucao_detail.html'
    context_object_name = 'devolucao'
    queryset = DevolucaoVenda.objects.all()


# =====================================
# ENTREGAS
# =====================================

class DeliveryListView(BaseVendaView, ListView):
    model = Venda
    template_name = 'vendas/delivery_lista.html'
    context_object_name = 'vendas'
    paginate_by = 20

    def get_queryset(self):
        return Venda.objects.filter(tipo_venda='entrega').select_related('cliente').order_by('-data_venda')


class AgendarEntregaView(BaseVendaView, UpdateView):
    model = Venda
    form_class = AgendarEntregaForm
    template_name = 'vendas/agendar_entrega.html'

    def get_success_url(self):
        return reverse_lazy('vendas:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.status_entrega = 'agendada'
        messages.success(self.request, 'Entrega agendada com sucesso!')
        return super().form_valid(form)


class EntregaListView(BaseVendaView, ListView):
    model = Entrega
    template_name = 'vendas/entrega_lista.html'
    context_object_name = 'entregas'
    paginate_by = 20

    def get_queryset(self):
        return Entrega.objects.select_related('venda', 'entregador').order_by('-data_agendada')


class ConfirmarEntregaDeliveryView(BaseVendaView, View):
    """Confirma a entrega de uma Venda do tipo 'entrega' (não confundir com
    ConfirmarEntregaView, que confirma um DocumentoTransporte/GT)."""

    def post(self, request, pk):
        entrega = get_object_or_404(Entrega, pk=pk)

        entrega.status = 'entregue'
        entrega.data_entrega = timezone.now()
        entrega.confirmado_por = request.user
        entrega.observacoes_entrega = request.POST.get('observacoes', '')
        entrega.save()

        entrega.venda.status_entrega = 'entregue'
        entrega.venda.save(update_fields=['status_entrega'])

        messages.success(request, 'Entrega confirmada com sucesso!')
        return redirect('vendas:entrega_lista')


class RotaEntregaView(BaseVendaView, TemplateView):
    template_name = 'vendas/rota_entrega.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()

        entregas_hoje = Entrega.objects.filter(
            data_agendada__date=hoje, status__in=['agendada', 'saiu_entrega']
        ).select_related('venda', 'entregador')

        context.update({'title': 'Rota de Entrega', 'entregas_hoje': entregas_hoje})
        return context


# =====================================
# CONVÊNIOS E PARCERIAS
# =====================================

class ConvenioListView(BaseVendaView, ListView):
    model = Convenio
    template_name = 'vendas/convenio_lista.html'
    context_object_name = 'convenios'
    paginate_by = 20

    def get_queryset(self):
        return Convenio.objects.order_by('nome')


class ConvenioCreateView(BaseVendaView, CreateView):
    model = Convenio
    form_class = ConvenioForm
    template_name = 'vendas/convenio_form.html'
    success_url = reverse_lazy('vendas:convenio_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Convênio cadastrado com sucesso!')
        return super().form_valid(form)


class ConvenioDetailView(BaseVendaView, DetailView):
    model = Convenio
    template_name = 'vendas/convenio_detail.html'
    context_object_name = 'convenio'
    queryset = Convenio.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # NOTA: Venda não tem FK para Convenio hoje — este relatório de
        # "vendas recentes do convênio" não pode ser preenchido até essa
        # relação existir no modelo. Ajustar quando o campo for definido.
        context.update({'vendas_recentes': Venda.objects.none()})
        return context


class FaturarConvenioView(BaseVendaView, TemplateView):
    template_name = 'vendas/faturar_convenio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        convenio = get_object_or_404(Convenio, pk=self.kwargs.get('pk'))

        # NOTA: idem — sem FK Venda->Convenio e sem status_faturamento em
        # Venda, não há como buscar "vendas pendentes de faturamento" deste
        # convênio. Deixado vazio propositalmente até a modelagem ser
        # definida (ver observação em ConvenioDetailView).
        context.update({
            'convenio': convenio,
            'vendas_pendentes': Venda.objects.none(),
            'total_faturar': 0,
        })
        return context


# =====================================
# COMISSÕES
# =====================================

class ComissaoListView(BaseVendaView, ListView):
    model = Comissao
    template_name = 'vendas/comissao_lista.html'
    context_object_name = 'comissoes'
    paginate_by = 20

    def get_queryset(self):
        return Comissao.objects.select_related('vendedor', 'venda').order_by('-created_at')


class CalcularComissaoView(BaseVendaView, TemplateView):
    template_name = 'vendas/calcular_comissao.html'

    def post(self, request):
        mes = int(request.POST.get('mes'))
        ano = int(request.POST.get('ano'))
        vendedor_id = request.POST.get('vendedor_id')

        vendas = Venda.objects.filter(data_venda__month=mes, data_venda__year=ano, status='finalizada')
        if vendedor_id:
            vendas = vendas.filter(vendedor_id=vendedor_id)

        for venda in vendas:
            Comissao.calcular_comissao(venda)

        messages.success(request, 'Comissões calculadas com sucesso!')
        return redirect('vendas:comissao_lista')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Calcular Comissões', 'vendedores': Funcionario.objects.filter(ativo=True)})
        return context


class PagarComissaoView(BaseVendaView, View):
    def post(self, request):
        comissao_ids = request.POST.getlist('comissao_ids')

        with transaction.atomic():
            comissoes = Comissao.objects.filter(id__in=comissao_ids, status='calculada')
            for comissao in comissoes:
                comissao.status = 'paga'
                comissao.data_pagamento = timezone.now().date()
                comissao.save()

        messages.success(request, f'{len(comissoes)} comissões pagas com sucesso!')
        return redirect('vendas:comissao_lista')


# =====================================
# AJAX E UTILITÁRIOS
# =====================================

class CalcularDescontoView(BaseVendaView, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            subtotal = Decimal(str(data.get('subtotal', 0)))
            desconto_valor = Decimal(str(data.get('desconto_valor', 0)))
            desconto_tipo = data.get('desconto_tipo', 'valor')

            if desconto_tipo == 'percentual':
                valor_desconto = subtotal * (desconto_valor / 100)
            else:
                valor_desconto = desconto_valor

            total = subtotal - valor_desconto

            return JsonResponse({'success': True, 'valor_desconto': float(valor_desconto), 'total': float(total)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


class VerificarEstoqueVendaView(BaseVendaView, View):
    def get(self, request):
        produto_id = request.GET.get('produto_id')
        quantidade = int(request.GET.get('quantidade', 1))

        try:
            produto = Produto.objects.get(id=produto_id)
            disponivel = produto.estoque_atual >= quantidade
            return JsonResponse({
                'disponivel': disponivel,
                'estoque_atual': produto.estoque_atual,
                'quantidade_solicitada': quantidade
            })
        except Produto.DoesNotExist:
            return JsonResponse({'disponivel': False, 'error': 'Produto não encontrado'})


class CalcularTrocoView(BaseVendaView, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            total = Decimal(str(data.get('total', 0)))
            valor_recebido = Decimal(str(data.get('valor_recebido', 0)))
            troco = valor_recebido - total
            return JsonResponse({'success': True, 'troco': float(troco)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


# =====================================
# API REST
# =====================================

class CancelarVendaAPIView(BaseVendaView, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        try:
            data = json.loads(request.body)
            venda_id = data.get('venda_id')
            motivo = data.get('motivo', 'Cancelamento via API')

            venda = get_object_or_404(Venda, id=venda_id)

            if venda.status == 'cancelada':
                return JsonResponse({'success': False, 'message': 'Venda já está cancelada'})

            with transaction.atomic():
                for item in venda.itens.all():
                    if item.produto:
                        item.produto.estoque_atual = F('estoque_atual') + item.quantidade
                        item.produto.save(update_fields=['estoque_atual'])

                venda.status = 'cancelada'
                venda.data_cancelamento = timezone.now()
                venda.motivo_cancelamento = motivo
                venda.usuario_cancelamento = request.user
                venda.save()

            return JsonResponse({'success': True, 'message': f'Venda {venda.numero_documento} cancelada com sucesso'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})


class ConsultarPrecoAPIView(BaseVendaView, View):
    def get(self, request):
        produto_id = request.GET.get('produto_id')
        quantidade = int(request.GET.get('quantidade', 1))

        try:
            produto = Produto.objects.get(id=produto_id)
            preco_unitario = produto.preco_venda
            subtotal = preco_unitario * quantidade
            desconto = Decimal('0.00')
            total = subtotal - desconto

            return JsonResponse({
                'success': True,
                'produto': {
                    'id': produto.id,
                    'nome': produto.nome_comercial,
                    'preco_unitario': float(preco_unitario),
                    'quantidade': quantidade,
                    'subtotal': float(subtotal),
                    'desconto': float(desconto),
                    'total': float(total)
                }
            })
        except Produto.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Produto não encontrado'})


class AplicarDescontoAPIView(BaseVendaView, PermissaoAcaoMixin, View):
    acao_requerida = 'fazer_desconto'

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        try:
            data = json.loads(request.body)
            venda_id = data.get('venda_id')
            desconto_valor = Decimal(str(data.get('desconto_valor', 0)))
            desconto_tipo = data.get('desconto_tipo', 'valor')

            venda = get_object_or_404(Venda, id=venda_id)

            if venda.status not in ['rascunho', 'pendente']:
                return JsonResponse({'success': False, 'message': 'Não é possível aplicar desconto nesta venda'})

            if desconto_tipo == 'percentual':
                venda.desconto_valor = venda.subtotal * (desconto_valor / 100)
            else:
                venda.desconto_valor = desconto_valor

            venda.calcular_totais()
            venda.save()

            return JsonResponse({
                'success': True,
                'message': 'Desconto aplicado com sucesso',
                'venda': {
                    'subtotal': float(venda.subtotal),
                    'desconto': float(venda.desconto_valor),
                    'total': float(venda.total)
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})




class PDVView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    """Ponto de venda condicionado ao tipo de actividade do tenant."""

    acao_requerida = 'vender'
    template_name = 'vendas/pdv.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Obter a empresa através do tenant activo, não da FK do utilizador.
        tenant = (
            getattr(self.request, 'tenant', None)
            or getattr(connection, 'tenant', None)
        )

        if (
            tenant is None
            or getattr(tenant, 'schema_name', 'public') == 'public'
        ):
            raise PermissionDenied(
                'O PDV só está disponível no domínio de uma empresa.'
            )

        # regime = tipo de actividade: COMERCIO, SERVICOS ou MISTO.
        regime = getattr(tenant, 'regime', None)

        if regime not in {'COMERCIO', 'SERVICOS', 'MISTO'}:
            raise PermissionDenied(
                'O tipo de actividade da empresa não está configurado correctamente.'
            )

        context['clientes'] = list(
            Cliente.objects.filter(ativo=True).values(
                'id', 'nome_completo'
            )
        )

        context['formas_pagamento'] = list(
            FormaPagamento.objects.filter(ativa=True).values(
                'id', 'nome'
            )
        )

        # Produtos apenas para COMERCIO ou MISTO.
        if regime in {'COMERCIO', 'MISTO'}:
            context['produtos'] = list(
                Produto.objects.filter(ativo=True).values(
                    'id', 'nome_produto', 'preco_venda',
                    'estoque_atual'
                )
            )
        else:
            context['produtos'] = []

        # Serviços apenas para SERVICOS ou MISTO.
        if regime in {'SERVICOS', 'MISTO'}:
            context['servicos'] = list(
                Servico.objects.filter(ativo=True).values(
                    'id', 'nome', 'preco_padrao'
                )
            )
        else:
            context['servicos'] = []

        # O template recebe o nome correspondente ao campo do modelo.
        context['regime'] = regime

        return context






class PDVCreateAPIView(APIView):
    """View de API para criação de uma venda completa (PDV), atômica."""

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            venda_data = request.data.get('venda')
            itens_data = request.data.get('itens')

            if not itens_data:
                return Response({'detail': 'A venda deve conter pelo menos um item.'}, status=status.HTTP_400_BAD_REQUEST)

            venda_serializer = VendaSerializer(data=venda_data)
            if venda_serializer.is_valid():
                venda_serializer.validated_data['status'] = 'finalizada'
                venda = venda_serializer.save()

                for item_data in itens_data:
                    item_data['venda'] = venda.id
                    item_serializer = ItemVendaSerializer(data=item_data)

                    if item_serializer.is_valid():
                        item_serializer.save()
                        produto = item_serializer.validated_data.get('produto')
                        if produto:
                            produto.estoque_atual -= item_serializer.validated_data['quantidade']
                            produto.save()
                    else:
                        raise ValueError(f"Dados do item inválidos: {item_serializer.errors}")

                return Response(VendaSerializer(venda).data, status=status.HTTP_201_CREATED)
            return Response(venda_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SalvarRascunhoApiView(LoginRequiredMixin, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            data = json.loads(request.body)

            forma_pagamento = None
            if data.get('forma_pagamento_id'):
                forma_pagamento = FormaPagamento.objects.filter(pk=data['forma_pagamento_id']).first()

            venda = Venda.objects.create(
                cliente_id=data.get('cliente_id'),
                vendedor=getattr(request.user, 'funcionario', None),
                forma_pagamento=forma_pagamento,
                desconto_valor=to_decimal(data.get('desconto', 0)),
                observacoes=data.get('observacoes', ''),
                status='rascunho',
                usuario_criacao=request.user,
            )

            total = Decimal('0.00')
            for item_data in data.get('itens', []):
                produto = Produto.objects.get(id=item_data['produto_id'])
                item = ItemVenda.objects.create(
                    venda=venda,
                    produto=produto,
                    quantidade=item_data['quantidade'],
                    preco_unitario=to_decimal(item_data['preco_unitario']),
                )
                total += item.total

            venda.total = total - venda.desconto_valor
            venda.save(update_fields=['total'])

            return JsonResponse({'success': True, 'message': 'Rascunho salvo com sucesso', 'venda_id': venda.id})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao salvar rascunho: {str(e)}'})


class AbrirGavetaApiView(LoginRequiredMixin, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request):
        try:
            logger.info(f'Gaveta aberta por: {request.user.username}')
            return JsonResponse({'success': True, 'message': 'Gaveta aberta com sucesso'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro ao abrir gaveta: {str(e)}'})


def to_decimal(value):
    """Converte um valor (string ou numérico) para Decimal de forma segura."""
    if value is None or value == "":
        return Decimal('0.00')
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    value_str = str(value).strip()
    try:
        if ',' in value_str and '.' in value_str:
            if value_str.index('.') < value_str.index(','):
                value_str = value_str.replace('.', '')
        return Decimal(value_str.replace(',', '.'))
    except (ValueError, TypeError, decimal.InvalidOperation):
        logger.error(f"Erro de conversão para Decimal no valor: {value}")
        return Decimal('0.00')


def to_int(value):
    return int(value)


@login_required
@requer_permissao("liquidar_faturacredito")
def contas_receber(request):
    hoje = timezone.now()

    faturas_ativas = FaturaCredito.objects.filter(status__in=['emitida', 'parcial']).select_related('cliente')
    faturas_vencidas = faturas_ativas.filter(data_vencimento__lt=hoje)
    faturas_vencendo = faturas_ativas.filter(data_vencimento__range=[hoje, hoje + timedelta(days=7)])

    total_pendente = sum((f.valor_pendente() for f in faturas_ativas), Decimal('0.00'))

    context = {
        'title': 'Gestão de Contas a Receber',
        'total_a_receber': total_pendente,
        'faturas_pendentes': faturas_ativas,
        'qtd_vencidas': faturas_vencidas.count(),
        'qtd_vencendo': faturas_vencendo.count(),
        'valor_vencido': sum((f.valor_pendente() for f in faturas_vencidas), Decimal('0.00')),
    }
    return render(request, 'vendas/contas_receber.html', context)


@login_required
def formas_pagamento_api(request):
    """Lista todas as formas de pagamento ativas (a empresa já é implícita pelo schema)."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Método não permitido.'}, status=405)

    formas = FormaPagamento.objects.filter(ativa=True).order_by('ordem_exibicao')
    data = [{'id': f.id, 'nome': f.nome} for f in formas]
    return JsonResponse({'success': True, 'formas_pagamento': data})


# =====================================
# MOTOR DE VALIDAÇÃO E FINALIZAÇÃO
# =====================================

@require_GET
@requer_permissao("vender")
def fatura_pdf_view(request, venda_id, tipo='a4'):
    """Gera PDF para Vendas (Fatura-Recibo / FR)"""
    venda = get_object_or_404(Venda, id=venda_id)
    return _gerar_response_pdf(venda, "FR")


@require_GET
@requer_permissao("emitir_faturacredito")
def fatura_credito_pdf_view(request, fatura_id, tipo='a4'):
    """Gera PDF para Faturas de Crédito (FT)"""
    fatura = get_object_or_404(FaturaCredito, id=fatura_id)
    return _gerar_response_pdf(fatura, "FT")


@requer_permissao("emitir_recibos")
def recibo_pdf_view(request, recibo_id):
    """Gera PDF para Recibos de Quitação (REC)"""
    recibo = get_object_or_404(Recibo, id=recibo_id)
    return _gerar_response_pdf(recibo, "REC")


@require_GET
@requer_permissao("emitir_proforma")
def proforma_pdf_view(request, proforma_id):
    """Gera PDF para Faturas Proforma (FP)"""
    proforma = get_object_or_404(FaturaProforma, id=proforma_id)
    return _gerar_response_pdf(proforma, "FP")


@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("vender")
def finalizar_venda_api(request):
    """Finaliza Venda (FR - Fatura Recibo / VD - Venda a Dinheiro) no PDV."""
    try:
        data = json.loads(request.body)
        funcionario = request.user.funcionario

        validar_itens_por_regime(data['itens'])

        venda = Venda.objects.create(
            cliente_id=data.get('cliente_id'),
            vendedor=funcionario,
            forma_pagamento_id=data['forma_pagamento_id'],
            subtotal=Decimal(str(data['subtotal'])),
            iva_valor=Decimal(str(data['iva_valor'])),
            total=Decimal(str(data['total'])),
            status='finalizada',
            tipo_venda=data.get('tipo_venda', 'fatura_recibo')
        )

        for item in data['itens']:
            ItemVenda.objects.create(
                venda=venda,
                produto_id=item.get('produto_id'),
                servico_id=item.get('servico_id'),
                quantidade=item['quantidade'],
                preco_unitario=Decimal(str(item['preco_unitario'])),
                taxa_iva=TaxaIVAAGT.objects.get(id=item['taxa_iva_id']) if item.get('taxa_iva_id') else None
            )
            if item.get('produto_id'):
                Produto.objects.filter(id=item['produto_id']).update(estoque_atual=F('estoque_atual') - item['quantidade'])

        venda.gerar_documento_fiscal(request.user)

        email_avulso = data.get('email_cliente_avulso')
        whats_avulso = data.get('whatsapp_cliente_avulso')

        from apps.vendas.servicos.notificacao_service import NotificacaoVendaService
        NotificacaoVendaService.disparar_todas(venda, email_avulso, whats_avulso)

        return JsonResponse({'success': True, 'venda_id': venda.id, 'numero': venda.numero_documento})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("emitir_proforma")
def finalizar_proforma_api(request):
    """Cria Fatura Proforma (FP) validando regime."""
    try:
        data = json.loads(request.body)
        validar_itens_por_regime(data['itens'])

        proforma = FaturaProforma.objects.create(
            cliente_id=data['cliente_id'],
            vendedor=request.user.funcionario,
            data_validade=datetime.strptime(data['data_validade'], '%Y-%m-%d').date(),
            subtotal=Decimal(str(data['subtotal'])),
            total=Decimal(str(data['total'])),
            status='emitida'
        )

        for item in data['itens']:
            ItemProforma.objects.create(
                proforma=proforma,
                produto_id=item.get('produto_id'),
                servico_id=item.get('servico_id'),
                quantidade=item['quantidade'],
                preco_unitario=Decimal(str(item['preco_unitario']))
            )

        return JsonResponse({'success': True, 'proforma_id': proforma.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_POST
@requer_permissao("emitir_faturacredito")
def finalizar_fatura_credito_api(request, fatura_id):
    """Finaliza Fatura de Crédito (FT) e gera rastro AGT."""
    try:
        fatura = get_object_or_404(FaturaCredito, id=fatura_id)
        if fatura.status != 'emitida':
            return JsonResponse({'success': False, 'message': 'Fatura já processada.'})

        fatura.gerar_documento_fiscal(request.user)
        return JsonResponse({'success': True, 'numero': fatura.numero_documento})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_POST
@requer_permissao("aplicar_notadebito")
def finalizar_nota_debito_api(request, nota_id):
    """Finaliza Nota de Débito (ND) e gera rastro AGT."""
    try:
        nota = get_object_or_404(NotaDebito, id=nota_id)
        nota.save()
        return JsonResponse({'success': True, 'numero': nota.numero_nota})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("aplicar_notacredito")
def finalizar_nota_credito_api(request):
    """Finaliza Nota de Crédito (NC) para retificação de faturas."""
    try:
        data = json.loads(request.body)
        validar_itens_por_regime(data['itens'])

        nota = NotaCredito.objects.create(
            cliente_id=data['cliente_id'],
            emitida_por=request.user,
            motivo=data.get('motivo', 'outros'),
            venda_origem_id=data.get('venda_origem_id'),
            total=Decimal(str(data['total'])),
            status='emitida'
        )

        for item in data['itens']:
            ItemNotaCredito.objects.create(
                nota_credito=nota,
                produto_id=item.get('produto_id'),
                servico_id=item.get('servico_id'),
                quantidade_creditada=item['quantidade'],
                valor_unitario_credito=Decimal(str(item['preco_unitario']))
            )

        nota.save()
        return JsonResponse({'success': True, 'nota_id': nota.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("emitir_documentotransporte")
def finalizar_documento_transporte_api(request):
    """Finaliza Guia de Transporte (GT) validando itens e regime."""
    try:
        data = json.loads(request.body)

        tenant = getattr(connection, 'tenant', None)

        if (
            tenant is None
            or getattr(tenant, 'schema_name', 'public') == 'public'
        ):
            raise ValidationError(
                'Não foi possível determinar o tenant da empresa.'
            )

        if tenant.regime == 'SERVICOS':
            raise ValidationError(
                'Empresas em regime de serviços não emitem '
                'Guias de Transporte de mercadorias.'
            )

        gt = DocumentoTransporte.objects.create(
            emitido_por=request.user,
            destinatario_nome=data['destinatario_nome'],
            destinatario_endereco=data['destinatario_endereco'],
            data_inicio_transporte=data['data_inicio'],
            data_previsao_entrega=data.get('data_previsao_entrega', timezone.now()),
            veiculo_matricula=data['veiculo_matricula'],
            status='preparando'
        )

        for item in data['itens']:
            ItemDocumentoTransporte.objects.create(
                documento=gt,
                produto_id=item['produto_id'],
                quantidade_enviada=item['quantidade']
            )

        return JsonResponse({'success': True, 'documento_id': gt.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@transaction.atomic
@login_required
@require_http_methods(["POST"])
def finalizar_recibo_api(request):
    """Finaliza Recibo (RC) de quitação de fatura."""
    try:
        data = json.loads(request.body)
        fatura = get_object_or_404(FaturaCredito, id=data['fatura_id'])

        recibo = Recibo.objects.create(
            fatura=fatura,
            cliente=fatura.cliente,
            valor_pago=Decimal(str(data['valor_pago'])),
        )

        if fatura.valor_pendente() <= 0:
            fatura.status = 'liquidada'
            fatura.save()

        return JsonResponse({'success': True, 'recibo_id': recibo.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@require_http_methods(["POST"])
@login_required
def atualizar_observacoes_venda(request, venda_id):
    """Atualiza as observações de uma venda"""
    try:
        data = json.loads(request.body)
        observacoes = data.get('observacoes', '')

        venda = get_object_or_404(Venda, id=venda_id)
        venda.observacoes = observacoes
        venda.save(update_fields=['observacoes'])

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
@requer_permissao("acessar_documentos")
def documentos_dashboard_view(request):
    """Dashboard consolidado de todos os tipos de documentos emitidos"""
    data_inicio = timezone.now().date() - timedelta(days=30)

    vendas_qs = Venda.objects.filter(data_venda__gte=data_inicio)
    vendas_stats = vendas_qs.aggregate(
        total_faturamento=Sum('total'),
        qtd_fr=Count('id', filter=Q(tipo_venda='fatura_recibo')),
        qtd_vd=Count('id', filter=Q(tipo_venda='balcao')),
        qtd_tv=Count('id', filter=Q(tipo_venda='online'))
    )

    faturas_stats = FaturaCredito.objects.filter(data_fatura__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('total'),
        pendentes=Count('id', filter=Q(status__in=['emitida', 'parcial']))
    )

    recibos_stats = Recibo.objects.filter(data_recibo__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('valor_pago'))

    proformas_stats = FaturaProforma.objects.filter(data_proforma__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('total'))

    notas_stats = {
        'nc': NotaCredito.objects.filter(data_nota__gte=data_inicio).count(),
        'nd': NotaDebito.objects.filter(data_nota__gte=data_inicio).count(),
    }

    logistica_stats = {
        'gt': DocumentoTransporte.objects.filter(data_documento__gte=data_inicio).count(),
        'td': DevolucaoVenda.objects.filter(data_devolucao__gte=data_inicio).count()
    }

    vendas_recentes = vendas_qs.select_related('cliente').order_by('-data_venda')[:15]

    context = {
        'title': 'Painel de Gestão Documental',
        'vendas_stats': vendas_stats,
        'faturas_stats': faturas_stats,
        'recibos_stats': recibos_stats,
        'proformas_stats': proformas_stats,
        'notas_stats': notas_stats,
        'logistica_stats': logistica_stats,
        'vendas_recentes': vendas_recentes,
    }
    return render(request, 'vendas/documentos_dashboard.html', context)


@login_required
@requer_permissao("emitir_faturacredito")
def nova_fatura_credito(request):
    return render(request, 'vendas/nova_fatura_credito.html', {'title': 'Nova Fatura a Crédito (FT)', 'tipo_documento': 'FT'})


@login_required
@requer_permissao("emitir_proforma")
def nova_proforma(request):
    return render(request, 'vendas/nova_proforma.html', {'title': 'Nova Proforma (Orçamento)', 'tipo_documento': 'PF'})


@require_POST
@transaction.atomic
@requer_permissao("liquidar_faturacredito")
def liquidar_fatura_api(request, fatura_id):
    """Liquida a FT, gera o REC e cria a movimentação no Caixa/Banco, tudo atómico."""
    try:
        funcionario = request.user.funcionario
        fatura = get_object_or_404(FaturaCredito, pk=fatura_id)

        if fatura.status == 'liquidada':
            return JsonResponse({'success': False, 'message': 'Esta fatura já se encontra liquidada.'})

        valor_pendente = fatura.valor_pendente()

        forma_pagamento_id = request.POST.get('forma_pagamento_id')
        if forma_pagamento_id:
            forma = get_object_or_404(FormaPagamento, id=forma_pagamento_id)
        else:
            forma = FormaPagamento.objects.filter(ativa=True).first()

        with transaction.atomic():
            recibo = Recibo.objects.create(
                fatura=fatura,
                cliente=fatura.cliente,
                vendedor=funcionario,
                forma_pagamento=forma,
                valor_pago=valor_pendente,
                status='emitido'
            )

            recibo.gerar_documento_fiscal()

            conta_destino = forma.conta_destino if forma else None
            if conta_destino:
                from apps.financeiro.models import MovimentacaoFinanceira
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao='entrada',
                    tipo_documento='recibo',
                    data_movimentacao=timezone.now().date(),
                    valor=valor_pendente,
                    descricao=f"Liquidação da Fatura {fatura.numero_documento} - REC {recibo.numero_recibo}",
                    conta_bancaria=conta_destino,
                    usuario_responsavel=request.user,
                    confirmada=True,
                    recibo=recibo
                )

            fatura.valor_pago += valor_pendente
            fatura.status = 'liquidada'
            fatura.save()

        return JsonResponse({
            'success': True,
            'message': f'Fatura liquidada. Recibo {recibo.numero_recibo} gerado.',
            'recibo_id': recibo.id
        })
    except Exception as e:
        logger.error(f"Erro ao liquidar fatura {fatura_id}: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Erro técnico: {str(e)}'}, status=400)


@require_http_methods(["POST"])
@login_required
@requer_permissao("liquidar_faturacredito")
def converter_proforma_api(request, proforma_id):
    """API para converter Proforma (FP) em FR ou FT."""
    try:
        data = json.loads(request.body)
        tipo_conversao = data.get('tipo_conversao')

        if tipo_conversao not in ['fatura_recibo', 'fatura_credito']:
            return JsonResponse({'success': False, 'message': 'Tipo de conversão inválido.'})

        proforma = get_object_or_404(FaturaProforma, id=proforma_id)

        if proforma.status != 'emitida':
            return JsonResponse({'success': False, 'message': 'Apenas proformas pendentes podem ser convertidas.'})

        if proforma.data_validade < timezone.now().date():
            return JsonResponse({'success': False, 'message': 'A Proforma expirou e não pode ser convertida.'})

        with transaction.atomic():
            if tipo_conversao == 'fatura_recibo':
                documento_criado = _converter_para_fatura_recibo(proforma, request.user)
                tipo_nome = "Fatura Recibo (FR)"
                proforma.venda_convertida = documento_criado
            else:
                documento_criado = _converter_para_fatura_credito(proforma, request.user)
                tipo_nome = "Fatura a Crédito (FT)"

            proforma.status = 'convertida'
            proforma.save()

            numero_documento = documento_criado.numero_documento

        return JsonResponse({
            'success': True,
            'message': f'Proforma convertida com sucesso em {tipo_nome}: {numero_documento}',
            'documento_id': documento_criado.id,
            'numero_documento': numero_documento,
            'tipo': tipo_conversao
        })
    except Exception as e:
        logger.error(f"Erro na conversão da proforma {proforma_id}: {str(e)}")
        traceback.print_exc()
        return JsonResponse({'success': False, 'message': f'Erro técnico na conversão: {str(e)}'})


def _converter_para_fatura_recibo(proforma, user):
    """Cria uma Venda (FR) a partir da Proforma, migrando itens híbridos."""
    funcionario = user.funcionario

    venda = Venda.objects.create(
        cliente=proforma.cliente,
        vendedor=funcionario,
        subtotal=proforma.subtotal,
        desconto_valor=proforma.desconto_valor,
        iva_valor=proforma.iva_valor,
        total=proforma.total,
        status='finalizada',
        tipo_venda='fatura_recibo',
        observacoes=f'Convertido da Proforma {proforma.numero_documento}'
    )

    for item in proforma.itens.all():
        ItemVenda.objects.create(
            venda=venda,
            produto=item.produto,
            servico=item.servico,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            desconto_item=item.desconto_item,
            taxa_iva=item.taxa_iva,
            iva_valor=item.iva_valor,
            total=item.total
        )
        if item.produto:
            item.produto.estoque_atual = F('estoque_atual') - item.quantidade
            item.produto.save()

    venda.gerar_documento_fiscal(user)
    return venda


def _converter_para_fatura_credito(proforma, user):
    """Cria uma Fatura de Crédito (FT) a partir da Proforma."""
    fatura = FaturaCredito.objects.create(
        cliente=proforma.cliente,
        vendedor=user.funcionario,
        subtotal=proforma.subtotal,
        desconto_valor=proforma.desconto_valor,
        iva_valor=proforma.iva_valor,
        total=proforma.total,
        status='emitida',
        data_vencimento=timezone.now().date() + timedelta(days=30),
        observacoes=f'Convertido da Proforma {proforma.numero_documento}'
    )

    for item in proforma.itens.all():
        ItemFatura.objects.create(
            fatura=fatura,
            produto=item.produto,
            servico=item.servico,
            nome_item=item.produto.nome_produto if item.produto else item.servico.nome,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            desconto_item=item.desconto_item,
            taxa_iva=item.taxa_iva,
            iva_valor=item.iva_valor,
            total=item.total
        )

    fatura.gerar_documento_fiscal(user)
    return fatura


@login_required
@requer_permissao("acessar_documentos")
def faturas_recibo_lista(request):
    vendas = Venda.objects.select_related('cliente', 'forma_pagamento').order_by('-data_venda')
    return render(request, 'vendas/faturas_recibo_lista.html', {'vendas': vendas, 'title': 'Faturas Recibo (FR)'})


@login_required
@requer_permissao("acessar_documentos")
def faturas_credito_lista(request):
    faturas = FaturaCredito.objects.select_related('cliente').order_by('-data_fatura')
    return render(request, 'vendas/faturas_credito_lista.html', {'faturas': faturas, 'title': 'Faturas a Crédito (FT)'})


@login_required
@requer_permissao("acessar_documentos")
def recibos_lista(request):
    recibos = Recibo.objects.select_related('cliente', 'vendedor', 'forma_pagamento').order_by('-data_recibo')
    return render(request, 'vendas/recibos_lista.html', {'recibos': recibos, 'title': 'Recibos (REC)'})


@login_required
@requer_permissao("acessar_documentos")
def proformas_lista(request):
    proformas = FaturaProforma.objects.select_related('cliente').order_by('-data_proforma')
    return render(request, 'vendas/proformas_lista.html', {'proformas': proformas, 'title': 'Proformas'})


@login_required
@requer_permissao("vender")
def vendas_lista(request):
    vendas = Venda.objects.select_related('cliente', 'forma_pagamento').order_by('-data_venda')[:50]
    return render(request, 'vendas/vendas_lista.html', {'vendas': vendas, 'title': 'Vendas Realizadas'})


@require_http_methods(["POST"])
@login_required
@requer_permissao("aprovar_proforma")
def atualizar_status_proforma_api(request, proforma_id):
    """API para atualizar o status de uma Proforma"""
    try:
        data = json.loads(request.body)
        novo_status = data.get('status')

        status_validos = ['emitida', 'aceite', 'rejeitada', 'convertida', 'expirado']
        if novo_status not in status_validos:
            return JsonResponse({'success': False, 'message': 'Status inválido'})

        proforma = get_object_or_404(FaturaProforma, id=proforma_id)

        status_anterior = proforma.status
        proforma.status = novo_status
        proforma.save()

        status_nomes = {
            'emitida': 'Pendente', 'aceite': 'Aceita', 'rejeitada': 'Rejeitada',
            'convertida': 'Convertida', 'expirado': 'Expirada'
        }

        return JsonResponse({
            'success': True,
            'message': f'Status alterado de {status_nomes.get(status_anterior, status_anterior)} para {status_nomes.get(novo_status, novo_status)}',
            'status_anterior': status_anterior,
            'status_novo': novo_status
        })
    except Exception as e:
        logger.error(f"Erro ao atualizar status da proforma {proforma_id}: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Erro ao atualizar status: {str(e)}'})


@login_required
@requer_permissao("emitir_documentotransporte")
def buscar_documentos_origem_api(request):
    """API para buscar documentos de origem para notas de crédito/débito"""
    try:
        tipo = request.GET.get('tipo')
        termo = request.GET.get('termo', '')

        resultados = []

        if tipo == 'venda':
            vendas = Venda.objects.filter(status='finalizada')
            if termo:
                vendas = vendas.filter(
                    Q(numero_documento__icontains=termo) | Q(cliente__nome_completo__icontains=termo)
                )
            for venda in vendas[:20]:
                resultados.append({
                    'id': venda.id, 'numero': venda.numero_documento,
                    'cliente': venda.cliente.nome_completo if venda.cliente else 'N/A',
                    'data': venda.data_venda.strftime('%d/%m/%Y'), 'total': float(venda.total)
                })

        elif tipo == 'fatura_credito':
            faturas = FaturaCredito.objects.all()
            if termo:
                faturas = faturas.filter(
                    Q(numero_documento__icontains=termo) | Q(cliente__nome_completo__icontains=termo)
                )
            for fatura in faturas[:20]:
                resultados.append({
                    'id': fatura.id, 'numero': fatura.numero_documento,
                    'cliente': fatura.cliente.nome_completo if fatura.cliente else 'N/A',
                    'data': fatura.data_fatura.strftime('%d/%m/%Y'), 'total': float(fatura.total)
                })

        return JsonResponse({'success': True, 'documentos': resultados})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# =====================================
# VIEWS DE PDF
# =====================================

@require_GET
@login_required
@requer_permissao("aplicar_notacredito")
def nota_credito_pdf_view(request, nota_id):
    """Gera PDF para Notas de Crédito (NC) - Rectificativos"""
    nota = get_object_or_404(NotaCredito, id=nota_id)
    return _gerar_response_pdf(nota, "NC")


@require_http_methods(["POST"])
@login_required
@requer_permissao("aplicar_notacredito")
def nota_debito_pdf_view(request, nota_id):
    """Gera PDF para Notas de Débito (ND)"""
    nota = get_object_or_404(NotaDebito, id=nota_id)
    return _gerar_response_pdf(nota, "ND")


@require_GET
@login_required
@requer_permissao("emitir_documentotransporte")
def documento_transporte_pdf_view(request, documento_id):
    """Gera PDF para Guias de Transporte/Remessa (GT/GR)"""
    doc = get_object_or_404(DocumentoTransporte, id=documento_id)
    return _gerar_response_pdf(doc, "GT")


def _gerar_response_pdf(obj_documento, prefixo):
    """Helper para centralizar a chamada ao PDFDocumentoService."""
    try:
        pdf_service = PDFDocumentoService(obj_documento)
        pdf_buffer = pdf_service.gerar()

        safe_number = obj_documento.numero_documento.replace('/', '_').replace(' ', '_')
        filename = f"{prefixo}_{safe_number}.pdf"

        return FileResponse(pdf_buffer, as_attachment=False, content_type='application/pdf', filename=filename)
    except Exception as e:
        logger.error(f"Erro ao gerar PDF {prefixo} ID {obj_documento.id}: {str(e)}")
        raise Http404("Erro interno ao gerar o documento PDF.")


@login_required
def buscar_produtos_api(request):
    """API para buscar produtos por termo de pesquisa"""
    try:
        termo = request.GET.get('termo', '')
        produtos = Produto.objects.filter(ativo=True)
        if termo:
            produtos = produtos.filter(Q(nome__icontains=termo) | Q(codigo__icontains=termo))

        resultados = [{
            'id': p.id, 'codigo': p.codigo, 'nome': p.nome,
            'preco_venda': float(p.preco_venda),
            'peso': float(getattr(p, 'peso', 0)),
            'unidade': getattr(p, 'unidade', 'un')
        } for p in produtos[:20]]

        return JsonResponse({'success': True, 'produtos': resultados})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def buscar_servicos_api(request):
    """API para buscar serviços por termo de pesquisa"""
    try:
        termo = request.GET.get('termo', '')
        servicos = Servico.objects.filter(ativo=True)
        if termo:
            servicos = servicos.filter(Q(nome__icontains=termo) | Q(codigo__icontains=termo))

        resultados = [{
            'id': s.id, 'codigo': s.codigo, 'nome': s.nome,
            'preco': float(s.preco), 'unidade': getattr(s, 'unidade', 'un')
        } for s in servicos[:20]]

        return JsonResponse({'success': True, 'servicos': resultados})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def buscar_clientes_api(request):
    """API para buscar clientes por termo de pesquisa"""
    try:
        termo = request.GET.get('termo', '')
        clientes = Cliente.objects.filter(ativo=True)
        if termo:
            clientes = clientes.filter(
                Q(nome_completo__icontains=termo) | Q(nif__icontains=termo) | Q(email__icontains=termo)
            )

        resultados = [{
            'id': c.id, 'nome_completo': c.nome_completo, 'nif': c.nif, 'email': c.email,
            'telefone': getattr(c, 'telefone', ''), 'endereco': getattr(c, 'endereco', '')
        } for c in clientes[:20]]

        return JsonResponse({'success': True, 'clientes': resultados})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# =====================================
# ITENS: ADICIONAR / REMOVER
# =====================================

@require_POST
@login_required
def adicionar_item_nota_credito_api(request):
    try:
        data = json.loads(request.body)
        nota = get_object_or_404(NotaCredito, id=data['nota_id'])

        item = ItemNotaCredito.objects.create(
            nota_credito=nota,
            produto_id=data.get('produto_id'),
            servico_id=data.get('servico_id'),
            descricao_item=data['descricao'],
            quantidade_creditada=Decimal(str(data['quantidade'])),
            valor_unitario_credito=Decimal(str(data['preco_unitario'])),
            iva_percentual=Decimal(str(data.get('iva_percentual', 0)))
        )
        return JsonResponse({'success': True, 'item_id': item.id, 'total': float(item.total_item_credito)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@require_POST
@login_required
def adicionar_item_nota_debito_api(request):
    try:
        data = json.loads(request.body)
        nota = get_object_or_404(NotaDebito, id=data['nota_id'])

        item = ItemNotaDebito.objects.create(
            nota_debito=nota,
            produto_id=data.get('produto_id'),
            servico_id=data.get('servico_id'),
            descricao_item=data['descricao'],
            quantidade=Decimal(str(data['quantidade'])),
            valor_unitario=Decimal(str(data['preco_unitario'])),
            iva_percentual=Decimal(str(data.get('iva_percentual', 0)))
        )
        return JsonResponse({'success': True, 'item_id': item.id, 'total': float(item.total_item)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@require_POST
@login_required
def adicionar_item_documento_transporte_api(request):
    try:
        data = json.loads(request.body)
        doc = get_object_or_404(DocumentoTransporte, id=data['documento_id'])

        item = ItemDocumentoTransporte.objects.create(
            documento=doc,
            produto_id=data['produto_id'],
            quantidade_enviada=Decimal(str(data['quantidade'])),
            peso_unitario=Decimal(str(data.get('peso_unitario', 0))),
            valor_unitario=Decimal(str(data.get('preco_unitario', 0)))
        )
        return JsonResponse({'success': True, 'item_id': item.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@require_http_methods(["DELETE"])
@login_required
@requer_permissao("aplicar_notacredito")
def remover_item_nota_credito_api(request, item_id):
    try:
        item = get_object_or_404(ItemNotaCredito, pk=item_id)
        nota = item.nota_credito

        if nota.status not in ['rascunho', 'emitida']:
            return JsonResponse({'success': False, 'message': 'Não é possível remover itens desta nota.'}, status=400)

        item.delete()
        nota.recalcular_total()

        return JsonResponse({'success': True, 'message': 'Item removido com sucesso!', 'novo_total': float(nota.total)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro ao remover item: {str(e)}'}, status=500)


@require_http_methods(["DELETE"])
@login_required
@requer_permissao("aplicar_notadebito")
def remover_item_nota_debito_api(request, item_id):
    try:
        item = get_object_or_404(ItemNotaDebito, pk=item_id)
        nota = item.nota_debito

        if nota.status not in ['rascunho', 'emitida']:
            return JsonResponse({'success': False, 'message': 'Não é possível remover itens desta nota.'}, status=400)

        item.delete()
        nota.recalcular_total()

        return JsonResponse({'success': True, 'message': 'Item removido com sucesso!', 'novo_total': float(nota.total)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro ao remover item: {str(e)}'}, status=500)


@require_http_methods(["DELETE"])
@login_required
@requer_permissao("emitir_documentotransporte")
def remover_item_documento_transporte_api(request, item_id):
    try:
        item = get_object_or_404(ItemDocumentoTransporte, pk=item_id)
        documento = item.documento

        if documento.status != 'preparando':
            return JsonResponse({'success': False, 'message': 'Não é possível remover itens deste documento.'}, status=400)

        item.delete()

        peso_total = sum((i.peso_total for i in documento.itens.all()), Decimal('0.000'))
        documento.peso_total = peso_total
        documento.save()

        return JsonResponse({
            'success': True, 'message': 'Item removido com sucesso!',
            'novo_peso_total': float(documento.peso_total)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro ao remover item: {str(e)}'}, status=500)


# =====================================
# ESTATÍSTICAS RÁPIDAS
# =====================================

@login_required
def estatisticas_rapidas_api(request):
    try:
        hoje = timezone.now().date()

        nc_hoje = NotaCredito.objects.filter(data_emissao__date=hoje).aggregate(
            quantidade=Count('id'), valor_total=Sum('total'))
        nd_hoje = NotaDebito.objects.filter(data_emissao__date=hoje).aggregate(
            quantidade=Count('id'), valor_total=Sum('total'))
        gt_hoje = DocumentoTransporte.objects.filter(data_emissao__date=hoje).aggregate(
            quantidade=Count('id'), em_transito=Count('id', filter=Q(status='em_transito')))

        pendencias = {
            'nc_pendentes_aprovacao': NotaCredito.objects.filter(
                requer_aprovacao=True, aprovada_por__isnull=True).count(),
            'nd_vencidas': NotaDebito.objects.filter(
                data_vencimento__lt=hoje, status__in=['emitida', 'aplicada']).count(),
            'transportes_atrasados': DocumentoTransporte.objects.filter(
                data_previsao_entrega__lt=timezone.now(), status__in=['preparando', 'em_transito']).count()
        }

        return JsonResponse({'success': True, 'nc_hoje': nc_hoje, 'nd_hoje': nd_hoje, 'gt_hoje': gt_hoje,
                              'pendencias': pendencias})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# =====================================
# NOTAS DE CRÉDITO
# =====================================

class NotaCreditoListView(BaseVendaView, PermissaoAcaoMixin, ListView):
    acao_requerida = 'emitir_notacredito'
    model = NotaCredito
    template_name = 'vendas/nota_credito_lista.html'
    context_object_name = 'notas_credito'
    paginate_by = 100

    def get_queryset(self):
        queryset = NotaCredito.objects.all()

        status_filtro = self.request.GET.get('status')
        if status_filtro:
            queryset = queryset.filter(status=status_filtro)

        motivo = self.request.GET.get('motivo')
        if motivo:
            queryset = queryset.filter(motivo=motivo)

        cliente_nome = self.request.GET.get('cliente')
        if cliente_nome:
            queryset = queryset.filter(
                Q(cliente__nome_completo__icontains=cliente_nome) | Q(cliente__nif__icontains=cliente_nome)
            )

        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        if data_inicio:
            queryset = queryset.filter(data_nota__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_nota__date__lte=data_fim)

        return queryset.select_related('cliente', 'vendedor').order_by('-data_nota')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        stats = NotaCredito.objects.aggregate(
            total_creditos=Sum('total'),
            quantidade_total=Count('id'),
            pendentes_aprovacao=Count('id', filter=Q(requer_aprovacao=True, aprovada_por__isnull=True)),
            aplicadas=Count('id', filter=Q(status='aplicada'))
        )

        context.update({
            'title': 'Notas de Crédito',
            'stats': stats,
            'status': NotaCredito.STATUS_CHOICES,
            'tipo_nota': NotaCredito.MOTIVO_CHOICES,
        })
        return context


class NotaCreditoDetailView(BaseVendaView, DetailView):
    model = NotaCredito
    template_name = 'vendas/nota_credito_detail.html'
    context_object_name = 'nota_credito'
    queryset = NotaCredito.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nota = self.get_object()
        pode, motivo = nota.pode_ser_aplicada()

        context.update({
            'title': f'Nota de Crédito {nota.numero_nota}',
            'itens': nota.itens.select_related('produto', 'servico'),
            'pode_aplicar': pode,
            'motivo_nao_aplicar': motivo,
        })
        return context


class NotaCreditoCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_notacredito'

    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'vendas/nota_credito_form.html'
    success_url = reverse_lazy('vendas:nota_credito_lista')

    def form_valid(self, form):
        form.instance.emitida_por = self.request.user
        if hasattr(self.request.user, 'funcionario'):
            form.instance.vendedor = self.request.user.funcionario

        messages.success(self.request, f'Nota de Crédito {form.instance.numero_nota} criada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Nova Nota de Crédito',
                         'subtitle': 'Emitir documento de crédito para reduzir valor de fatura'})
        return context


class NotaCreditoUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_notacredito'

    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'vendas/nota_credito_form.html'
    queryset = NotaCredito.objects.all()

    def get_success_url(self):
        return reverse_lazy('vendas:nota_credito_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'emitida']:
            messages.error(self.request, 'Não é possível editar esta nota de crédito.')
            return redirect(self.get_success_url())

        messages.success(self.request, 'Nota de Crédito atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Nota de Crédito {self.object.numero_nota}',
                         'subtitle': 'Modificar dados da nota de crédito'})
        return context


class AplicarNotaCreditoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aplicar_notacredito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaCredito, pk=pk)
        try:
            with transaction.atomic():
                nota.aplicar_credito(request.user)
                messages.success(request, f'Nota de Crédito {nota.numero_nota} aplicada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao aplicar nota de crédito: {e}')
        except Exception as e:
            messages.error(request, f'Erro inesperado: {str(e)}')

        return redirect('vendas:nota_credito_detail', pk=pk)


class AprovarNotaCreditoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aprovar_notacredito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaCredito, pk=pk)

        if not nota.requer_aprovacao:
            messages.warning(request, 'Esta nota de crédito não requer aprovação.')
        elif nota.aprovada_por:
            messages.warning(request, 'Esta nota de crédito já foi aprovada.')
        else:
            nota.aprovada_por = request.user
            nota.data_aprovacao = timezone.now()
            nota.save()
            messages.success(request, f'Nota de Crédito {nota.numero_nota} aprovada com sucesso!')

        return redirect('vendas:nota_credito_detail', pk=pk)


# =====================================
# NOTAS DE DÉBITO
# =====================================

class NotaDebitoListView(BaseVendaView, PermissaoAcaoMixin, ListView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    template_name = 'vendas/nota_debito_lista.html'
    context_object_name = 'notas_debito'
    paginate_by = 100

    def get_queryset(self):
        queryset = NotaDebito.objects.all()

        status_filtro = self.request.GET.get('status')
        if status_filtro:
            queryset = queryset.filter(status=status_filtro)

        motivo = self.request.GET.get('motivo')
        if motivo:
            queryset = queryset.filter(motivo=motivo)

        cliente_nome = self.request.GET.get('cliente')
        if cliente_nome:
            queryset = queryset.filter(
                Q(cliente__nome_completo__icontains=cliente_nome) | Q(cliente__nif__icontains=cliente_nome)
            )

        if self.request.GET.get('vencidas') == '1':
            queryset = queryset.filter(data_vencimento__lt=timezone.now().date(), status__in=['emitida', 'aplicada'])

        return queryset.select_related('cliente', 'vendedor').order_by('-data_nota')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        stats = NotaDebito.objects.aggregate(
            total_debitos=Sum('total'),
            quantidade_total=Count('id'),
            vencidas=Count('id', filter=Q(data_vencimento__lt=timezone.now().date(), status__in=['emitida', 'aplicada'])),
            aplicadas=Count('id', filter=Q(status='aplicada'))
        )

        context.update({
            'title': 'Notas de Débito',
            'stats': stats,
            'status': NotaDebito.STATUS_CHOICES,
            'tipo_nota': NotaDebito.TIPO_NOTA_CHOICES,
        })
        return context


class NotaDebitoDetailView(BaseVendaView, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    template_name = 'vendas/nota_debito_detail.html'
    context_object_name = 'nota_debito'
    queryset = NotaDebito.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nota = self.get_object()
        pode, motivo = nota.pode_ser_aplicada()

        context.update({
            'title': f'Nota de Débito {nota.numero_nota}',
            'itens': nota.itens.select_related('produto', 'servico'),
            'pode_aplicar': pode,
            'motivo_nao_aplicar': motivo,
            'esta_vencida': nota.data_vencimento < timezone.now().date(),
            'dias_vencimento': (nota.data_vencimento - timezone.now().date()).days,
        })
        return context


class NotaDebitoCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_notadebito'

    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'vendas/nota_debito_form.html'
    success_url = reverse_lazy('vendas:nota_debito_lista')

    def form_valid(self, form):
        form.instance.emitida_por = self.request.user
        if hasattr(self.request.user, 'funcionario'):
            form.instance.vendedor = self.request.user.funcionario

        messages.success(self.request, f'Nota de Débito {form.instance.numero_nota} criada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Nova Nota de Débito',
                         'subtitle': 'Emitir documento de débito para cobrança adicional'})
        return context


class NotaDebitoUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_notadebito'

    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'vendas/nota_debito_form.html'
    queryset = NotaDebito.objects.all()

    def get_success_url(self):
        return reverse_lazy('vendas:nota_debito_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'emitida']:
            messages.error(self.request, 'Não é possível editar esta nota de débito.')
            return redirect(self.get_success_url())

        messages.success(self.request, 'Nota de Débito atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Nota de Débito {self.object.numero_nota}',
                         'subtitle': 'Modificar dados da nota de débito'})
        return context


class AplicarNotaDebitoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aplicar_notadebito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaDebito, pk=pk)
        try:
            with transaction.atomic():
                nota.aplicar_debito(request.user)
                messages.success(request, f'Nota de Débito {nota.numero_nota} aplicada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao aplicar nota de débito: {e}')
        except Exception as e:
            messages.error(request, f'Erro inesperado: {str(e)}')

        return redirect('vendas:nota_debito_detail', pk=pk)


class AprovarNotaDebitoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aprovar_notadebito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaDebito, pk=pk)

        if not nota.requer_aprovacao:
            messages.warning(request, 'Esta nota de débito não requer aprovação.')
        elif nota.aprovada_por:
            messages.warning(request, 'Esta nota de débito já foi aprovada.')
        else:
            nota.aprovada_por = request.user
            nota.data_aprovacao = timezone.now()
            nota.save()
            messages.success(request, f'Nota de Débito {nota.numero_nota} aprovada com sucesso!')

        return redirect('vendas:nota_debito_detail', pk=pk)


# =====================================
# DOCUMENTOS DE TRANSPORTE
# =====================================

class DocumentoTransporteListView(BaseVendaView, PermissaoAcaoMixin, ListView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    template_name = 'vendas/documento_transporte_lista.html'
    context_object_name = 'documentos_transporte'
    paginate_by = 100

    def get_queryset(self):
        queryset = DocumentoTransporte.objects.all()

        status_filtro = self.request.GET.get('status')
        if status_filtro:
            queryset = queryset.filter(status=status_filtro)

        tipo_operacao = self.request.GET.get('tipo_operacao')
        if tipo_operacao:
            queryset = queryset.filter(tipo_operacao=tipo_operacao)

        destinatario = self.request.GET.get('destinatario')
        if destinatario:
            queryset = queryset.filter(
                Q(destinatario_nome__icontains=destinatario) | Q(destinatario_nif__icontains=destinatario)
            )

        if self.request.GET.get('atrasados') == '1':
            queryset = queryset.filter(data_previsao_entrega__lt=timezone.now(),
                                        status__in=['preparando', 'em_transito'])

        return queryset.select_related('destinatario_cliente').order_by('-data_documento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        stats = DocumentoTransporte.objects.aggregate(
            total_documentos=Count('id'),
            em_transito=Count('id', filter=Q(status='em_transito')),
            entregues=Count('id', filter=Q(status='entregue')),
            atrasados=Count('id', filter=Q(data_previsao_entrega__lt=timezone.now(),
                                            status__in=['preparando', 'em_transito'])),
            peso_total=Sum('peso_total'),
            valor_total_transportes=Sum('valor_transporte')
        )

        context.update({
            'title': 'Documentos de Transporte',
            'stats': stats,
            'status': DocumentoTransporte.STATUS_CHOICES,
            'tipo_operacao': DocumentoTransporte.TIPO_OPERACAO_CHOICES,
        })
        return context


class DocumentoTransporteDetailView(BaseVendaView, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    template_name = 'vendas/documento_transporte_detail.html'
    context_object_name = 'documento'
    queryset = DocumentoTransporte.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documento = self.get_object()

        itens = documento.itens.all()
        total_peso = sum((item.peso_total for item in itens), Decimal('0.000'))
        total_valor = sum((item.valor_total for item in itens), Decimal('0.00'))

        tempo_transporte = None
        if documento.data_inicio_transporte:
            fim = documento.data_entrega_real or timezone.now()
            tempo_transporte = fim - documento.data_inicio_transporte

        context.update({
            'title': f'Documento de Transporte {documento.numero_documento}',
            'itens': itens,
            'total_peso_calculado': total_peso,
            'total_valor_calculado': total_valor,
            'pode_iniciar': documento.status == 'preparando',
            'pode_confirmar': documento.status == 'em_transito',
            'tempo_transporte': tempo_transporte,
        })
        return context


class DocumentoTransporteCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_documentotransporte'

    model = DocumentoTransporte
    form_class = DocumentoTransporteForm
    template_name = 'vendas/documento_transporte_form.html'
    success_url = reverse_lazy('vendas:documento_transporte_lista')

    def form_valid(self, form):
        form.instance.emitido_por = self.request.user
        messages.success(self.request, f'Documento de Transporte {form.instance.numero_documento} criado com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Novo Documento de Transporte',
                         'subtitle': 'Criar guia de transporte para mercadorias'})
        return context


class DocumentoTransporteUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_documentotransporte'

    model = DocumentoTransporte
    form_class = DocumentoTransporteForm
    template_name = 'vendas/documento_transporte_form.html'
    queryset = DocumentoTransporte.objects.all()

    def get_success_url(self):
        return reverse_lazy('vendas:documento_transporte_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status != 'preparando':
            messages.error(self.request, 'Só é possível editar documentos em preparação.')
            return redirect(self.get_success_url())

        messages.success(self.request, 'Documento de Transporte atualizado com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Documento {self.object.numero_documento}',
                         'subtitle': 'Modificar dados do documento de transporte'})
        return context


class IniciarTransporteView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'emitir_documentotransporte'

    def post(self, request, pk):
        documento = get_object_or_404(DocumentoTransporte, pk=pk)
        try:
            documento.iniciar_transporte()
            messages.success(request, f'Transporte {documento.numero_documento} iniciado com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao iniciar transporte: {e}')
        except Exception as e:
            messages.error(request, f'Erro inesperado: {str(e)}')

        return redirect('vendas:documento_transporte_detail', pk=pk)


class ConfirmarEntregaView(PermissaoAcaoMixin, BaseVendaView, View):
    """Confirma a entrega de um DocumentoTransporte (GT). Ver também
    ConfirmarEntregaDeliveryView, para o fluxo de Entrega de Venda."""
    acao_requerida = 'confirmar_entrega'

    def post(self, request, pk):
        documento = get_object_or_404(DocumentoTransporte, pk=pk)
        assinatura = request.POST.get('assinatura_destinatario', '')

        try:
            documento.confirmar_entrega(request.user, assinatura)
            messages.success(request, f'Entrega do documento {documento.numero_documento} confirmada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao confirmar entrega: {e}')
        except Exception as e:
            messages.error(request, f'Erro inesperado: {str(e)}')

        return redirect('vendas:documento_transporte_detail', pk=pk)


# =====================================
# DASHBOARDS E RELATÓRIOS
# =====================================

class DocumentosFiscaisAnalyticsView(BaseVendaView, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'emitir_documentotransporte'
    template_name = 'vendas/documentos_fiscais_analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = self.request.GET.get('periodo', '30')
        data_inicio = timezone.now().date() - timedelta(days=int(periodo))

        nc_stats = NotaCredito.objects.filter(data_emissao__gte=data_inicio).aggregate(
            total_nc=Count('id'),
            valor_total_nc=Sum('total'),
            aplicadas=Count('id', filter=Q(status='aplicada')),
            pendentes_aprovacao=Count('id', filter=Q(requer_aprovacao=True, aprovada_por__isnull=True))
        )

        nd_stats = NotaDebito.objects.filter(data_emissao__gte=data_inicio).aggregate(
            total_nd=Count('id'),
            valor_total_nd=Sum('total'),
            valor_pago_nd=Sum('valor_pago'),
            aplicadas=Count('id', filter=Q(status='aplicada')),
            vencidas=Count('id', filter=Q(data_vencimento__lt=timezone.now().date()))
        )

        gt_stats = DocumentoTransporte.objects.filter(data_emissao__gte=data_inicio).aggregate(
            total_gt=Count('id'),
            em_transito=Count('id', filter=Q(status='em_transito')),
            entregues=Count('id', filter=Q(status='entregue')),
            atrasados=Count('id', filter=Q(data_previsao_entrega__lt=timezone.now(),
                                            status__in=['preparando', 'em_transito'])),
            peso_total=Sum('peso_total'),
            valor_transportes=Sum('valor_transporte')
        )

        nc_por_motivo = NotaCredito.objects.filter(data_emissao__gte=data_inicio).values('motivo').annotate(
            quantidade=Count('id'), valor_total=Sum('total')).order_by('-valor_total')

        gt_por_status = DocumentoTransporte.objects.filter(data_emissao__gte=data_inicio).values('status').annotate(
            quantidade=Count('id'))

        context.update({
            'title': 'Analytics de Documentos Fiscais',
            'periodo': periodo,
            'data_inicio': data_inicio,
            'nc_stats': nc_stats,
            'nd_stats': nd_stats,
            'gt_stats': gt_stats,
            'nc_por_motivo': nc_por_motivo,
            'gt_por_status': gt_por_status,
        })
        return context


class RelatorioNotasCreditoView(BaseVendaView, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'aprovar_notacredito'
    template_name = 'vendas/relatorio_notas_credito.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        cliente_id = self.request.GET.get('cliente_id')
        motivo = self.request.GET.get('motivo')

        queryset = NotaCredito.objects.all()
        if data_inicio:
            queryset = queryset.filter(data_emissao__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_emissao__date__lte=data_fim)
        if cliente_id:
            queryset = queryset.filter(cliente_id=cliente_id)
        if motivo:
            queryset = queryset.filter(motivo=motivo)

        totais = queryset.aggregate(total_creditos=Sum('total'), quantidade=Count('id'), credito_medio=Avg('total'))

        por_cliente = queryset.values('cliente__nome_completo').annotate(
            total=Sum('total'), quantidade=Count('id')).order_by('-total')[:10]

        por_motivo = queryset.values('motivo').annotate(total=Sum('total'), quantidade=Count('id')).order_by('-total')

        context.update({
            'title': 'Relatório de Notas de Crédito',
            'notas_credito': queryset.select_related('cliente')[:100],
            'totais': totais,
            'por_cliente': por_cliente,
            'por_motivo': por_motivo,
            'clientes': Cliente.objects.filter(ativo=True),
            'motivo_choices': NotaCredito.MOTIVO_CHOICES,
        })
        return context


class RelatorioTransportesView(BaseVendaView, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'emitir_documentotransporte'
    template_name = 'vendas/relatorio_transportes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        status_filtro = self.request.GET.get('status')
        provincia = self.request.GET.get('provincia')

        queryset = DocumentoTransporte.objects.all()
        if data_inicio:
            queryset = queryset.filter(data_emissao__date__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_emissao__date__lte=data_fim)
        if status_filtro:
            queryset = queryset.filter(status=status_filtro)
        if provincia:
            queryset = queryset.filter(destinatario_provincia=provincia)

        totais = queryset.aggregate(
            total_documentos=Count('id'), peso_total=Sum('peso_total'),
            valor_total=Sum('valor_transporte'), valor_medio=Avg('valor_transporte'))

        entregues = queryset.filter(status='entregue', data_entrega_real__isnull=False)
        entregas_no_prazo = 0
        entregas_atrasadas = 0
        for doc in entregues:
            if doc.data_entrega_real.date() <= doc.data_previsao_entrega.date():
                entregas_no_prazo += 1
            else:
                entregas_atrasadas += 1

        por_provincia = queryset.values('destinatario_provincia').annotate(
            total=Count('id'), peso=Sum('peso_total'), valor=Sum('valor_transporte')).order_by('-total')

        context.update({
            'title': 'Relatório de Transportes',
            'documentos': queryset.select_related('destinatario_cliente')[:100],
            'totais': totais,
            'entregas_no_prazo': entregas_no_prazo,
            'entregas_atrasadas': entregas_atrasadas,
            'por_provincia': por_provincia,
            'status_choices': DocumentoTransporte.STATUS_CHOICES,
        })
        return context


# =====================================
# APIs REST ADICIONAIS
# =====================================

class VendaViewSet(viewsets.ModelViewSet):
    """API Endpoints para gestão de Vendas/Documentos Fiscais."""
    queryset = Venda.objects.all().order_by('-data_venda')
    serializer_class = VendaSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response({
            "message": "Venda registrada e assinada fiscalmente com sucesso.",
            "documento": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)


class VendaCreateAPIView(generics.CreateAPIView):
    """Cria uma nova venda e gera o documento fiscal (HASH, ATCUD)."""
    serializer_class = VendaSerializer

    def perform_create(self, serializer):
        with transaction.atomic():
            return serializer.save()

    def create(self, request, *args, **kwargs):
        bi_cache_local = caches["B_I"]

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                self.perform_create(serializer)
                verificar_margem_critica.delay()
                bi_cache_local.clear()

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            logger.error(f"ALERTA DE FALHA: {e}")
            return Response(
                {"message": "Erro de processamento interno. O administrador foi alertado.", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RentabilidadeItemSerializer(serializers.Serializer):
    """Estrutura os dados agregados do relatório de rentabilidade."""
    produto_id = serializers.IntegerField(read_only=True)
    produto_nome = serializers.CharField(source='produto__nome', read_only=True)
    total_vendido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    custo_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    margem_bruta = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    percentual_margem_bruta = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True,
                                                        coerce_to_string=False)


class RentabilidadeAPIView(APIView):
    """Endpoint de Rentabilidade com camada de Caching Redis."""
    CACHE_TTL = 60 * 60

    def get(self, request, *args, **kwargs):
        data_inicio = request.query_params.get('data_inicio', 'all')
        data_fim = request.query_params.get('data_fim', 'all')

        cache_key = f"bi_rentabilidade_{data_inicio}_{data_fim}"
        dados_cache = bi_cache.get(cache_key)

        if dados_cache:
            return Response(dados_cache)

        filtros = {}
        if data_inicio != 'all':
            filtros['venda__data_venda__gte'] = data_inicio
        if data_fim != 'all':
            filtros['venda__data_venda__lte'] = data_fim

        resultados = ItemVenda.objects.filter(**filtros).select_related('produto').values(
            'produto_id', 'produto__nome'
        ).annotate(
            total_vendido=Sum(F('quantidade') * F('preco_unitario')),
            custo_total=Sum(F('quantidade') * F('produto__preco_custo')),
        ).annotate(
            margem_bruta=F('total_vendido') - F('custo_total'),
            percentual_margem_bruta=F('margem_bruta') * 100 / F('total_vendido', output_field=DecimalField())
        ).order_by('-margem_bruta')

        serializer = RentabilidadeItemSerializer(resultados, many=True)
        response_data = {
            "relatorio_de_rentabilidade": serializer.data,
            "filtros_aplicados": request.query_params,
            "origem_dados": "Base de Dados (Cache Miss)"
        }

        bi_cache.set(cache_key, response_data, timeout=self.CACHE_TTL)
        return Response(response_data)