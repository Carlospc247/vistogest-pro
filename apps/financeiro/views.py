# apps/financeiro/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, 
    TemplateView, FormView, View
)
import logging
from datetime import timedelta
from django.db.models.functions import TruncDate
from django.urls import reverse, NoReverseMatch
from apps.vendas.models import PagamentoVenda
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import ProtectedError, Sum, Count, Q, Avg, F
from django.utils import timezone
from django.urls import reverse_lazy
from datetime import date, timedelta, datetime
from decimal import Decimal, InvalidOperation
import json
import csv
from rest_framework import viewsets
from django.core.exceptions import ValidationError
from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.core.views import BaseMPAView
from apps.fornecedores.models import Fornecedor
from apps.vendas.models import Venda
from .models import (
    ConciliacaoBancaria, ContaReceber, ContaPagar, FluxoCaixa,
    CentroCusto, ContaBancaria, MovimentacaoFinanceira, MovimentoCaixa,
    ImpostoTributo, PlanoConta
)
from .forms import (
    ContaReceberForm, ContaPagarForm, ImpostoTributoForm, CentroCustoForm, MovimentoCaixaForm, PlanoContaForm
)
from django.contrib.auth.mixins import AccessMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.http import JsonResponse
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_POST
from datetime import date
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from datetime import date, timedelta
import json
from decimal import Decimal
from django.views.generic import ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from .models import FluxoCaixa
from .forms import FluxoCaixaForm
from datetime import datetime, date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection, transaction
from django.http import Http404
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.vendas.models import FormaPagamento






class PermissaoAcaoMixin:
    """Usa o reverse relation real: Funcionario.usuario -> funcionario_relacionado."""
    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        funcionario = getattr(request.user, "funcionario_relacionado", None)
        if funcionario is None:
            # Compatibilidade com instalações antigas que usavam related_name='funcionario'.
            funcionario = getattr(request.user, "funcionario", None)
        if funcionario is None:
            messages.error(request, "O utilizador não está associado a um funcionário.")
            return HttpResponseForbidden("Acesso reservado a funcionários autorizados.")
        if self.acao_requerida and not funcionario.pode_realizar_acao(self.acao_requerida):
            messages.error(request, "O seu cargo não tem permissão para esta operação.")
            return HttpResponseForbidden("Permissão insuficiente.")
        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(self.request.get_full_path())



def permissao_acao_required(acao_requerida=None):
    """
    Decorator para function-based views que verifica:
    1. Usuário autenticado
    2. Usuário ligado a um registro Funcionario
    3. Permissão de ação específica
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Acesso negado. Usuário não autenticado.")
                return redirect(reverse_lazy('core:login'))  # ou handle customizado

            try:
                funcionario = request.user.funcionario
            except Exception:
                messages.error(
                    request,
                    "Acesso negado. O seu usuário não está ligado a um registro de funcionário."
                )
                return redirect(reverse_lazy('core_tenants:dashboard'))

            if acao_requerida:
                if not funcionario.pode_realizar_acao(acao_requerida):
                    messages.error(
                        request,
                        f"Acesso negado. O seu cargo não permite realizar a ação de '{acao_requerida}'."
                    )
                    return redirect(reverse_lazy('core_tenants:dashboard'))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator



def _decimal_post(request, name, default=None):
    raw = request.POST.get(name)
    if raw in (None, ""):
        if default is not None:
            return Decimal(default)
        raise ValidationError(f"O campo {name} é obrigatório.")
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        raise ValidationError(f"O campo {name} tem um valor inválido.")
    if not value.is_finite():
        raise ValidationError(f"O campo {name} tem um valor inválido.")
    return value


def _date_post(request, name, default=None):
    raw = request.POST.get(name)
    if not raw:
        return default or timezone.localdate()
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise ValidationError(f"A data indicada em {name} é inválida.")


def _tipo_documento(request):
    value = request.POST.get("tipo_documento", "transferencia")
    valid = {choice[0] for choice in MovimentacaoFinanceira.TIPO_DOCUMENTO_CHOICES}
    if value not in valid:
        raise ValidationError("Forma de pagamento inválida.")
    return value


class FinanceiroView(BaseMPAView, PermissaoAcaoMixin):
    acao_requerida = 'acessar_financeiro'
    template_name = 'core/financeiro.html'
    module_name = 'financeiro'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        empresa = self.get_empresa()
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)
        
        # Receitas do mês
        receitas_mes = Venda.objects.filter(
            data_venda__gte=mes_atual,
            status='finalizada'
        ).aggregate(total=Sum('total'))['total'] or 0
        
        # Stats mock
        financeiro_stats = {
            'receitas_mes': float(receitas_mes),
            'despesas_mes': float(receitas_mes) * 0.3,
            'lucro_mes': float(receitas_mes) * 0.7,
            'contas_receber': float(receitas_mes) * 0.1,
        }
        
        context.update({
            'financeiro_stats': financeiro_stats,
        })
        
        return context


# =====================================
# FORMAS DE PAGAMENTOS
# =====================================


# ======================================================================
# FORMAS DE PAGAMENTO (cada tenant escolhe as que usa)
# ======================================================================

# O fecho de turno (funcionarios.FecharTurnoView) soma pagamentos por
# forma_pagamento__codigo = 'numerario' | 'tpa' | 'transferencia'.
# Os códigos criados aqui mantêm essa compatibilidade.
CODIGO_COMPAT = {
    'dinheiro': 'numerario',
    'cartao_debito': 'tpa',
    'cartao_credito': 'tpa',
    'transferencia': 'transferencia',
}

"""
def _pode_acessar_financeiro(user):
    if connection.schema_name == 'public':
        return False
    tenant = connection.tenant
    if user.e_administrador_empresa and user.empresa_id == tenant.pk:
        return True
    funcionario = user.funcionario  # None no schema public / sem ficha de funcionário
    return bool(funcionario and funcionario.pode_realizar_acao('acessar_financeiro'))

class FinanceiroPermissaoMixin(LoginRequiredMixin):

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not _pode_acessar_financeiro(request.user):
            messages.error(request, "Não tem permissão para aceder ao módulo financeiro.")
            return redirect('core_tenants:dashboard')
        return super().dispatch(request, *args, **kwargs)

"""


def _garantir_formas_padrao():
    """Cria (inativa) uma forma de pagamento por cada tipo que o tenant ainda não tenha."""
    for ordem, (tipo, rotulo) in enumerate(FormaPagamento.FORMA_PAGAMENTO_CHOICES, start=1):
        if not FormaPagamento.objects.filter(tipo=tipo).exists():
            FormaPagamento.objects.get_or_create(
                nome=rotulo,
                defaults=dict(
                    tipo=tipo,
                    codigo=CODIGO_COMPAT.get(tipo, tipo),
                    ativa=False,
                    ordem_exibicao=ordem * 10,
                ),
            )


class FormasPagamentoView(PermissaoAcaoMixin, TemplateView):
    template_name = 'financeiro/formas_pagamento.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        _garantir_formas_padrao()

        por_tipo = {}
        for forma in FormaPagamento.objects.select_related('conta_destino').order_by('ordem_exibicao', 'nome'):
            por_tipo.setdefault(forma.tipo, []).append(forma)

        formas = []
        for tipo, rotulo in FormaPagamento.FORMA_PAGAMENTO_CHOICES:
            registos = por_tipo.get(tipo, [])
            formas.append({
                'tipo': tipo,
                'rotulo': rotulo,
                'ativa': any(r.ativa for r in registos),
                'registos': registos,
            })

        ctx['formas'] = formas
        ctx['total_ativas'] = sum(1 for f in formas if f['ativa'])
        ctx['total'] = len(formas)
        return ctx


class AlternarFormaPagamentoView(PermissaoAcaoMixin, View):
    http_method_names = ['post']

    def post(self, request, tipo):
        if tipo not in dict(FormaPagamento.FORMA_PAGAMENTO_CHOICES):
            raise Http404
        acao = request.POST.get('acao')
        if acao not in ('ativar', 'desativar'):
            messages.error(request, "Ação inválida.")
            return redirect('financeiro:formas_pagamento')

        rotulo = dict(FormaPagamento.FORMA_PAGAMENTO_CHOICES)[tipo]
        with transaction.atomic():
            _garantir_formas_padrao()
            if acao == 'desativar':
                # Sem nenhuma forma ativa, a empresa deixa de conseguir vender.
                if not FormaPagamento.objects.exclude(tipo=tipo).filter(ativa=True).exists():
                    messages.error(
                        request,
                        "A empresa tem de manter pelo menos uma forma de pagamento ativa."
                    )
                    return redirect('financeiro:formas_pagamento')
            FormaPagamento.objects.filter(tipo=tipo).update(ativa=(acao == 'ativar'))

        if acao == 'ativar':
            messages.success(request, f"“{rotulo}” ativada: já está disponível para a empresa.")
        else:
            messages.warning(request, f"“{rotulo}” desativada: deixa de estar disponível.")
        return redirect('financeiro:formas_pagamento')



# =====================================
# MOVIMENTAÇÃO FINANCEIRA
# =====================================

class MovimentacaoFinanceiraListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentacaoFinanceira
    template_name = 'financeiro/movimentacao/lista.html'
    context_object_name = 'movimentacoes'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = MovimentacaoFinanceira.objects.all().select_related(
            'conta_bancaria', 'centro_custo',
            'fornecedor', 'cliente', 'usuario_responsavel'
        ).order_by('-data_movimentacao', '-created_at')
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo_movimentacao=tipo)
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        conta = self.request.GET.get('conta')
        if conta:
            queryset = queryset.filter(conta_bancaria_id=conta)
        
        data_inicio = self.request.GET.get('data_inicio')
        if data_inicio:
            queryset = queryset.filter(data_movimentacao__gte=data_inicio)
        
        data_fim = self.request.GET.get('data_fim')
        if data_fim:
            queryset = queryset.filter(data_movimentacao__lte=data_fim)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Totais
        queryset = self.get_queryset()
        context['total_entradas'] = queryset.filter(
            tipo_movimentacao='entrada', confirmada=True
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['total_saidas'] = queryset.filter(
            tipo_movimentacao='saida', confirmada=True
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['saldo_periodo'] = context['total_entradas'] - context['total_saidas']
        
        # Contas para filtro
        context['contas_bancarias'] = ContaBancaria.objects.filter(
            ativa=True
        )
        
        return context

class MovimentacaoFinanceiraCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentacaoFinanceira
    template_name = 'financeiro/movimentacao/form.html'
    fields = [
        'tipo_movimentacao', 'tipo_documento', 'numero_documento',
        'data_movimentacao', 'data_vencimento', 'valor', 'valor_juros',
        'valor_multa', 'valor_desconto', 'conta_bancaria', 'conta_destino',
        'centro_custo', 'fornecedor', 'cliente',
        'descricao', 'observacoes', 'numero_cheque', 'banco_cheque',
        'emissor_cheque'
    ]
    success_url = reverse_lazy('financeiro:movimentacao_lista')
    
    def form_valid(self, form):
        form.instance.usuario_responsavel = self.request.user
        
        messages.success(self.request, 'Movimentação criada com sucesso!')
        return super().form_valid(form)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # Filtrar por empresa
        form.fields['conta_bancaria'].queryset = ContaBancaria.objects.filter(
           ativa=True
        )
        form.fields['conta_destino'].queryset = ContaBancaria.objects.filter(
           ativa=True
        )
        form.fields['centro_custo'].queryset = CentroCusto.objects.filter(
           ativo=True
        )
        form.fields['fornecedor'].queryset = Fornecedor.objects.filter(
           ativo=True
        )
        form.fields['cliente'].queryset = Cliente.objects.filter(
           ativo=True
        )
        
        return form

class MovimentacaoFinanceiraDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentacaoFinanceira
    template_name = 'financeiro/movimentacao/detail.html'
    context_object_name = 'movimentacao'

class MovimentacaoFinanceiraUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentacaoFinanceira
    template_name = 'financeiro/movimentacao/form.html'
    fields = [
        'tipo_documento', 'numero_documento', 'data_movimentacao',
        'data_vencimento', 'valor', 'valor_juros', 'valor_multa',
        'valor_desconto', 'descricao', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:movimentacao_lista')
    
    def get_object(self):
        obj = super().get_object()
        if obj.confirmada:
            raise Http404("Movimentação confirmada não pode ser editada")
        return obj
    
    def form_valid(self, form):
        messages.success(self.request, 'Movimentação atualizada com sucesso!')
        return super().form_valid(form)

class ConfirmarMovimentacaoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        movimentacao = get_object_or_404(MovimentacaoFinanceira, pk=pk)
        
        try:
            movimentacao.confirmar_movimentacao(request.user)
            messages.success(request, 'Movimentação confirmada com sucesso!')
        except ValidationError as e:
            messages.error(request, str(e))
        
        return redirect('financeiro:movimentacao_detail', pk=pk)

class EstornarMovimentacaoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        movimentacao = get_object_or_404(MovimentacaoFinanceira, pk=pk)
        motivo = request.POST.get('motivo', '')
        
        try:
            movimentacao.estornar_movimentacao(request.user, motivo)
            messages.success(request, 'Movimentação estornada com sucesso!')
        except ValidationError as e:
            messages.error(request, str(e))
        
        return redirect('financeiro:movimentacao_detail', pk=pk)

# =====================================
# FLUXO DE CAIXA
# =====================================

class FluxoCaixaListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    template_name = 'financeiro/fluxo_caixa/lista.html'
    context_object_name = 'fluxos'
    paginate_by = 31  # Um mês
    
    def get_queryset(self):
        queryset = FluxoCaixa.objects.all().select_related('conta_bancaria', 'centro_custo').order_by('data_referencia')
        
        # Filtro por período
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        
        if data_inicio:
            queryset = queryset.filter(data_referencia__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(data_referencia__lte=data_fim)
        else:
            # Padrão: próximos 30 dias
            hoje = date.today()
            fim_mes = hoje + timedelta(days=30)
            queryset = queryset.filter(data_referencia__range=[hoje, fim_mes])
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calcular totais
        queryset = self.get_queryset()
        
        context['total_entradas_previstas'] = queryset.filter(
            tipo='entrada'
        ).aggregate(total=Sum('valor_previsto'))['total'] or 0
        
        context['total_saidas_previstas'] = queryset.filter(
            tipo='saida'
        ).aggregate(total=Sum('valor_previsto'))['total'] or 0
        
        context['saldo_previsto'] = (
            context['total_entradas_previstas'] - context['total_saidas_previstas']
        )
        
        context['total_entradas_realizadas'] = queryset.filter(
            tipo='entrada', realizado=True
        ).aggregate(total=Sum('valor_realizado'))['total'] or 0
        
        context['total_saidas_realizadas'] = queryset.filter(
            tipo='saida', realizado=True
        ).aggregate(total=Sum('valor_realizado'))['total'] or 0
        
        # Gráfico de fluxo acumulado
        context['dados_grafico'] = self._preparar_dados_grafico(queryset)
        
        return context
    
    def _preparar_dados_grafico(self, queryset):
        dados = []
        saldo_acumulado = 0
        
        for fluxo in queryset.order_by('data_referencia'):
            if fluxo.tipo == 'entrada':
                saldo_acumulado += fluxo.valor_previsto
            else:
                saldo_acumulado -= fluxo.valor_previsto
            
            dados.append({
                'data': fluxo.data_referencia.strftime('%Y-%m-%d'),
                'saldo': float(saldo_acumulado),
                'categoria': fluxo.categoria
            })
        
        return dados

class FluxoCaixaCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    template_name = 'financeiro/fluxo_caixa/form.html'
    fields = [
        'data_referencia', 'tipo', 'valor_previsto', 'categoria',
        'descricao', 'conta_bancaria', 'centro_custo', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:fluxo_caixa_lista')
    
    def form_valid(self, form):
        messages.success(self.request, 'Projeção de fluxo criada com sucesso!')
        return super().form_valid(form)

class FluxoCaixaUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    template_name = 'financeiro/fluxo_caixa/form.html'
    fields = [
        'data_referencia', 'tipo', 'valor_previsto', 'valor_realizado',
        'categoria', 'descricao', 'conta_bancaria', 'centro_custo',
        'realizado', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:fluxo_caixa_lista')

class MarcarFluxoRealizadoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        fluxo = get_object_or_404(FluxoCaixa, pk=pk)
        valor_realizado = Decimal(request.POST.get('valor_realizado', fluxo.valor_previsto))
        
        fluxo.valor_realizado = valor_realizado
        fluxo.realizado = True
        fluxo.save()
        
        messages.success(request, 'Fluxo marcado como realizado!')
        return redirect('financeiro:fluxo_caixa_lista')

class GerarFluxoAutomaticoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request):
        """Gera fluxo de caixa baseado nas contas a pagar e receber"""
        data_inicio = request.POST.get('data_inicio')
        data_fim = request.POST.get('data_fim')
        
        if not data_inicio or not data_fim:
            messages.error(request, 'Período obrigatório')
            return redirect('financeiro:fluxo_caixa_lista')
        
        # Limpar fluxos existentes do período
        FluxoCaixa.objects.filter(
            
            data_referencia__range=[data_inicio, data_fim]
        ).delete()
        
        contador = 0
        
        # Contas a receber em aberto
        contas_receber = ContaReceber.objects.filter(
            
            status__in=['aberta', 'vencida'],
            data_vencimento__range=[data_inicio, data_fim]
        )
        
        for conta in contas_receber:
            FluxoCaixa.objects.create(
                
                data_referencia=conta.data_vencimento,
                tipo='entrada',
                valor_previsto=conta.valor_saldo,
                categoria='Recebimento de Clientes',
                descricao=f"Recebimento: {conta.descricao}",
                conta_bancaria=ContaBancaria.objects.filter(
                     conta_principal=True
                ).first(),
                conta_receber=conta
            )
            contador += 1
        
        # Contas a pagar em aberto
        contas_pagar = ContaPagar.objects.filter(
            
            status__in=['aberta', 'vencida'],
            data_vencimento__range=[data_inicio, data_fim]
        )
        
        for conta in contas_pagar:
            FluxoCaixa.objects.create(
                
                data_referencia=conta.data_vencimento,
                tipo='saida',
                valor_previsto=conta.valor_saldo,
                categoria='Pagamento a Fornecedores',
                descricao=f"Pagamento: {conta.descricao}",
                conta_bancaria=ContaBancaria.objects.filter(
                     conta_principal=True
                ).first(),
                conta_pagar=conta
            )
            contador += 1
        
        messages.success(request, f'{contador} lançamentos de fluxo gerados automaticamente!')
        return redirect('financeiro:fluxo_caixa_lista')

# =====================================
# CONCILIAÇÃO BANCÁRIA
# =====================================

class ConciliacaoBancariaListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ConciliacaoBancaria
    template_name = 'financeiro/conciliacao/lista.html'
    context_object_name = 'conciliacoes'
    paginate_by = 20
    
    def get_queryset(self):
        return ConciliacaoBancaria.objects.all(
        ).select_related('conta_bancaria', 'responsavel').order_by('-data_fim')

class ConciliacaoBancariaCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ConciliacaoBancaria
    template_name = 'financeiro/conciliacao/form.html'
    fields = [
        'conta_bancaria', 'data_inicio', 'data_fim',
        'saldo_banco_inicial', 'saldo_banco_final', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:conciliacao_lista')
    
    def form_valid(self, form):
        form.instance.responsavel = self.request.user
        
        # Calcular saldo do sistema
        conta = form.instance.conta_bancaria
        
        # Saldo inicial do sistema
        movimentacoes_anteriores = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=conta,
            data_movimentacao__lt=form.instance.data_inicio,
            confirmada=True
        )
        
        entradas_anteriores = movimentacoes_anteriores.filter(
            tipo_movimentacao='entrada'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        saidas_anteriores = movimentacoes_anteriores.filter(
            tipo_movimentacao='saida'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        form.instance.saldo_sistema_inicial = (
            conta.saldo_inicial + entradas_anteriores - saidas_anteriores
        )
        
        # Saldo final do sistema
        movimentacoes_periodo = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=conta,
            data_movimentacao__range=[form.instance.data_inicio, form.instance.data_fim],
            confirmada=True
        )
        
        entradas_periodo = movimentacoes_periodo.filter(
            tipo_movimentacao='entrada'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        saidas_periodo = movimentacoes_periodo.filter(
            tipo_movimentacao='saida'
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        form.instance.saldo_sistema_final = (
            form.instance.saldo_sistema_inicial + entradas_periodo - saidas_periodo
        )
        
        messages.success(self.request, 'Conciliação criada com sucesso!')
        return super().form_valid(form)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['conta_bancaria'].queryset = ContaBancaria.objects.filter(
            ativa=True
        )
        return form

class ConciliacaoBancariaDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ConciliacaoBancaria
    template_name = 'financeiro/conciliacao/detail.html'
    context_object_name = 'conciliacao'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Movimentações do período
        context['movimentacoes'] = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=self.object.conta_bancaria,
            data_movimentacao__range=[self.object.data_inicio, self.object.data_fim]
        ).order_by('data_movimentacao')
        
        # Movimentações não conciliadas
        context['movimentacoes_nao_conciliadas'] = context['movimentacoes'].filter(
            conciliada=False
        )
        
        return context

class ConciliarMovimentacaoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        movimentacao = get_object_or_404(MovimentacaoFinanceira, pk=pk)
        
        movimentacao.conciliada = True
        movimentacao.data_conciliacao = date.today()
        movimentacao.save()
        
        messages.success(request, 'Movimentação conciliada!')
        return redirect(request.META.get('HTTP_REFERER'))

class DesconciliarMovimentacaoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        movimentacao = get_object_or_404(MovimentacaoFinanceira, pk=pk)
        
        movimentacao.conciliada = False
        movimentacao.data_conciliacao = None
        movimentacao.save()
        
        messages.success(request, 'Movimentação desconciliada!')
        return redirect(request.META.get('HTTP_REFERER'))

# =====================================
# ORÇAMENTO FINANCEIRO COMPLETO
# =====================================


# =====================================
# CONTA BANCÁRIA COMPLETA
# =====================================

class ContaBancariaListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/conta_bancaria/lista.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaBancaria.objects.all().order_by('-conta_principal', 'banco', 'conta')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Atualizar saldos
        for conta in context['contas']:
            conta.atualizar_saldo()
        
        # Total em todas as contas
        context['saldo_total'] = sum(conta.saldo_atual for conta in context['contas'])
        
        return context

class ContaBancariaCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/conta_bancaria/form.html'
    fields = [
        'nome', 'banco', 'agencia', 'conta', 'digito', 'tipo_conta',
        'saldo_inicial', 'limite_credito',
        'ativa', 'conta_principal', 'permite_saldo_negativo',
        'codigo_integracao', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:conta_bancaria_lista')
    
    def form_valid(self, form):
        form.instance.saldo_atual = form.instance.saldo_inicial
        
        # Se marcada como principal, desmarcar outras
        if form.instance.conta_principal:
            ContaBancaria.objects.filter(
                conta_principal=True
            ).update(conta_principal=False)
        
        messages.success(self.request, 'Conta bancária criada com sucesso!')
        return super().form_valid(form)

class ContaBancariaDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/conta_bancaria/detail.html'
    context_object_name = 'conta'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Atualizar saldo
        self.object.atualizar_saldo()
        
        # Movimentações recentes
        context['movimentacoes_recentes'] = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=self.object,
            confirmada=True
        ).order_by('-data_movimentacao')[:20]
        
        # Totais do mês
        hoje = date.today()
        inicio_mes = hoje.replace(day=1)
        
        movimentacoes_mes = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=self.object,
            data_movimentacao__range=[inicio_mes, hoje],
            confirmada=True
        )
        
        context['entradas_mes'] = movimentacoes_mes.filter(
            tipo_movimentacao='entrada'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['saidas_mes'] = movimentacoes_mes.filter(
            tipo_movimentacao='saida'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        # Última conciliação
        context['ultima_conciliacao'] = ConciliacaoBancaria.objects.filter(
            conta_bancaria=self.object
        ).order_by('-data_fim').first()
        
        return context

class ContaBancariaUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/conta_bancaria/form.html'
    fields = [
        'nome', 'banco', 'agencia', 'conta', 'digito', 'tipo_conta',
        'saldo_inicial', 'limite_credito',
        'ativa', 'conta_principal', 'permite_saldo_negativo',
        'codigo_integracao', 'observacoes'
    ]
    success_url = reverse_lazy('financeiro:conta_bancaria_lista')
    
    def form_valid(self, form):
        # Se marcada como principal, desmarcar outras
        if form.instance.conta_principal:
            ContaBancaria.objects.filter(
                conta_principal=True
            ).exclude(id=form.instance.id).update(conta_principal=False)
        
        messages.success(self.request, 'Conta bancária atualizada com sucesso!')
        return super().form_valid(form)
    
# =====================================
# DASHBOARD FINANCEIRO
# =====================================
# =====================================
# CATÁLOGO DINÂMICO DE PÁGINAS + ATALHOS
# =====================================
# (título, nota, nome da rota[, função(hoje) -> args])  — só páginas GET sem ID.
_CATALOGO = [
    ("Visão geral e fluxo de caixa", "fa-chart-line", [
        ("Painel financeiro", "Resumo geral de tesouraria", "dashboard"),
        ("Fluxo de caixa", "Previsões e movimentos de caixa", "fluxo_caixa"),
        ("Nova previsão de fluxo", "Registar nova previsão", "fluxo_caixa_create"),
        ("Demonstração de resultados (DRE)", "Receitas, despesas e resultado", "dre"),
        ("Balanço patrimonial", "Posição patrimonial", "balanco"),
    ]),
    ("Movimentações financeiras", "fa-exchange-alt", [
        ("Movimentações", "Movimentos registados", "movimentacao_lista"),
        ("Nova movimentação", "Entrada, saída ou transferência", "movimentacao_create"),
    ]),
    ("Contas a receber", "fa-hand-holding-usd", [
        ("Contas a receber", "Cobranças de clientes", "conta_receber_lista"),
        ("Nova conta a receber", "Registar cobrança", "conta_receber_create"),
        ("Contas vencidas", "Cobranças em atraso", "contas_vencidas"),
        ("Contas a vencer", "Vencimentos próximos", "contas_vencendo"),
    ]),
    ("Contas a pagar", "fa-file-invoice-dollar", [
        ("Contas a pagar", "Compromissos financeiros", "conta_pagar_lista"),
        ("Nova conta a pagar", "Registar compromisso", "conta_pagar_create"),
        ("Agenda de pagamentos", "Pagamentos programados", "agenda_pagamentos"),
        ("Aprovação de pagamentos", "Aguardam aprovação", "aprovacao_pagamentos"),
        ("Pagamentos em lote", "Pagar várias contas", "pagamento_lote"),
    ]),
    ("Bancos e caixa", "fa-building-columns", [
        ("Contas bancárias", "Saldos e extratos", "conta_bancaria_lista"),
        ("Nova conta bancária", "Registar conta", "conta_bancaria_create"),
        ("Painel do caixa", "Caixa físico", "caixa"),
        ("Abrir caixa", "Abertura do caixa", "abrir_caixa"),
        ("Fechar caixa", "Fecho do caixa", "fechar_caixa"),
        ("Conferência de caixa", "Conferir valores", "conferencia_caixa"),
        ("Relatório diário do caixa", "Fecho e movimentos do dia", "relatorio_caixa_diario"),
        ("Movimentos de caixa", "Todos os movimentos", "movimento_caixa"),
        ("Histórico do caixa", "Operações anteriores", "historico_caixa"),
    ]),
    ("Formas de pagamento, cartões e TEF", "fa-credit-card", [
        ("Formas de pagamento", "Escolher as que a empresa aceita", "formas_pagamento"),
        ("Cartões", "Visão geral das operações", "cartao_lista"),
        ("Vendas com cartão", "Pagamentos por cartão", "vendas_cartao"),
        ("Recebimentos de cartões", "Valores líquidos", "recebimentos_cartao"),
        ("Taxas de cartão", "Taxas e encargos", "taxas_cartao"),
        ("Conciliação de cartões", "Conferência de referências", "conciliacao_cartao"),
        ("Terminal TEF", "Controlo de transações eletrónicas", "tef"),
        ("Transações TEF", "Consultar e cancelar", "tef_transacoes"),
    ]),
    ("Centros de custo e conciliações", "fa-scale-balanced", [
        ("Centros de custo", "Listar centros de custo", "centro_custo_lista"),
        ("Novo centro de custo", "Registar centro de custo", "centro_custo_create"),
        ("Conciliações bancárias", "Consultar conciliações", "conciliacao_lista"),
        ("Nova conciliação bancária", "Registar conciliação", "conciliacao_bancaria_create"),
        ("Conciliação", "Módulo de conciliação", "conciliacao"),
        ("Conciliação automática", "Executar conciliação automática", "conciliacao_automatica"),
        ("Plano de contas", "Plano Geral de Contabilidade (PGC)", "plano_conta_lista"),
        ("Nova conta do plano", "Registar conta contabilística", "plano_conta_create"),
    ]),
    ("Planeamento financeiro", "fa-calendar-check", [
        ("Projeções", "Antecipar fluxos", "projecoes"),
        ("Cenários", "Comparar cenários", "cenarios"),
        ("Metas", "Definir e acompanhar metas", "metas"),
    ]),
    ("Impostos e tributos", "fa-file-invoice", [
        ("Impostos e tributos", "Obrigações fiscais", "imposto_list"),
        ("Novo imposto / tributo", "Registar obrigação", "imposto_create"),
    ]),
    ("Fecho, relatórios e análises", "fa-chart-pie", [
        ("Fecho mensal", "Fecho financeiro", "fechamento_mensal"),
        ("Fecho do mês corrente", "Detalhes do período atual", "fechamento_detalhes",
         lambda hoje: (hoje.month, hoje.year)),
        ("Relatórios", "Painel de relatórios", "relatorios"),
        ("Relatório de fluxo de caixa", "Fluxo de caixa", "relatorio_fluxo_caixa"),
        ("Relatório da DRE", "Resultado do exercício", "relatorio_dre"),
        ("Relatório do balanço", "Posição patrimonial", "relatorio_balanco"),
        ("Relatório de inadimplência", "Valores em atraso", "relatorio_inadimplencia"),
        ("Relatório de contas a receber", "Cobranças", "relatorio_contas_receber"),
        ("Relatório de contas a pagar", "Compromissos", "relatorio_contas_pagar"),
        ("Relatório de movimento bancário", "Movimentos bancários", "relatorio_movimento_bancario"),
        ("Análises", "Painel de análises", "analises"),
        ("Análise de liquidez", "Indicadores de liquidez", "analise_liquidez"),
        ("Análise de rentabilidade", "Indicadores de rentabilidade", "analise_rentabilidade"),
        ("Análise de endividamento", "Indicadores de endividamento", "analise_endividamento"),
    ]),
    ("Importação e exportação", "fa-file-arrow-down", [
        ("Importar dados", "Importação", "importar"),
        ("Importar OFX", "Extrato bancário OFX", "importar_ofx"),
        ("Importar CNAB", "Ficheiro CNAB", "importar_cnab"),
        ("Exportar dados", "Exportação", "exportar"),
    ]),
]


def _catalogo_urls(hoje):
    """Gera o catálogo com reverse(); rotas que deixem de existir são ignoradas."""
    categorias, total = [], 0
    for titulo, icone, itens in _CATALOGO:
        visiveis = []
        for item in itens:
            nome, nota, rota = item[:3]
            args = item[3](hoje) if len(item) > 3 else ()
            try:
                url = reverse(f"financeiro:{rota}", args=args)
            except NoReverseMatch:
                logging.getLogger(__name__).warning("Rota financeiro:%s não encontrada", rota)
                continue
            visiveis.append({"titulo": nome, "nota": nota, "rota": f"financeiro:{rota}", "url": url})
        if visiveis:
            categorias.append({"titulo": titulo, "icone": icone, "itens": visiveis})
            total += len(visiveis)
    return categorias, total


def _atalhos_registos(hoje, limite=5):
    """Registos reais que precisam de atenção, com ligação direta."""
    def sec(titulo, icone, lista, vazio, itens):
        return {"titulo": titulo, "icone": icone, "lista": reverse(f"financeiro:{lista}"),
                "vazio": vazio, "itens": itens}

    receber = [{
        "titulo": f"{c.numero_documento} — {c.descricao}",
        "detalhe": f"{c.cliente or 'Sem cliente'} · vence {c.data_vencimento:%d/%m/%Y} · {c.valor_saldo:,.2f} AOA",
        "url": reverse("financeiro:conta_receber_detail", args=[c.pk]),
        "alerta": c.data_vencimento < hoje,
    } for c in ContaReceber.objects.filter(status__in=("aberta", "vencida"))
        .select_related("cliente").order_by("data_vencimento")[:limite]]

    pagar = [{
        "titulo": f"{c.numero_documento} — {c.descricao}",
        "detalhe": f"{c.fornecedor or 'Sem fornecedor'} · vence {c.data_vencimento:%d/%m/%Y} · {c.valor_saldo:,.2f} AOA",
        "url": reverse("financeiro:conta_pagar_detail", args=[c.pk]),
        "alerta": c.data_vencimento < hoje,
    } for c in ContaPagar.objects.filter(status__in=("aberta", "vencida"))
        .select_related("fornecedor").order_by("data_vencimento")[:limite]]

    movimentos = [{
        "titulo": m.descricao,
        "detalhe": f"{m.get_tipo_movimentacao_display()} · {m.data_movimentacao:%d/%m/%Y} · {m.valor:,.2f} AOA",
        "url": reverse("financeiro:movimentacao_detail", args=[m.pk]),
        "alerta": False,
    } for m in MovimentacaoFinanceira.objects.filter(confirmada=False)
        .exclude(status__in=("cancelada", "estornada")).order_by("-data_movimentacao")[:limite]]

    bancos = [{
        "titulo": c.nome,
        "detalhe": f"{c.banco} · saldo {c.saldo_atual:,.2f} AOA",
        "url": reverse("financeiro:extrato_bancario", args=[c.pk]),
        "alerta": c.saldo_atual < 0,
    } for c in ContaBancaria.objects.filter(ativa=True)[:limite]]

    impostos = [{
        "titulo": i.nome,
        "detalhe": f"{i.mes_referencia:02d}/{i.ano_referencia} · vence {i.data_vencimento:%d/%m/%Y} · {i.total_agt:,.2f} AOA",
        "url": reverse("financeiro:imposto_detail", args=[i.pk]),
        "alerta": i.data_vencimento < hoje,
    } for i in ImpostoTributo.objects.filter(situacao__in=("pendente", "calculado", "vencido"))
        .order_by("data_vencimento")[:limite]]

    return [
        sec("Contas a receber em aberto", "fa-hand-holding-usd", "conta_receber_lista", "Sem cobranças em aberto.", receber),
        sec("Contas a pagar em aberto", "fa-file-invoice-dollar", "conta_pagar_lista", "Sem compromissos em aberto.", pagar),
        sec("Movimentações por confirmar", "fa-right-left", "movimentacao_lista", "Nenhuma movimentação pendente.", movimentos),
        sec("Contas bancárias", "fa-building-columns", "conta_bancaria_lista", "Ainda não há contas bancárias ativas.", bancos),
        sec("Impostos pendentes", "fa-file-invoice", "imposto_list", "Sem impostos pendentes.", impostos),
    ]


class FinanceiroDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "acessar_financeiro"
    template_name = "financeiro/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        inicio_mes = hoje.replace(day=1)
        fim = hoje
        movimentos_mes = MovimentacaoFinanceira.objects.filter(
            data_movimentacao__range=(inicio_mes, fim), confirmada=True
        )
        receitas_mes = movimentos_mes.filter(tipo_movimentacao="entrada").aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
        despesas_mes = movimentos_mes.filter(tipo_movimentacao="saida").aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
        total_vendas_mes = Venda.objects.filter(
            data_venda__range=(inicio_mes, fim), status="finalizada"
        ).aggregate(v=Sum("total"))["v"] or Decimal("0.00")
        total_receber = ContaReceber.objects.filter(status__in=["aberta", "vencida"]).aggregate(v=Sum("valor_saldo"))["v"] or Decimal("0.00")
        total_pagar = ContaPagar.objects.filter(status__in=["aberta", "vencida"]).aggregate(v=Sum("valor_saldo"))["v"] or Decimal("0.00")
        saldo_caixa = MovimentoCaixa.objects.filter(confirmado=True).aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
        saldo_bancos = ContaBancaria.objects.filter(ativa=True).aggregate(v=Sum("saldo_atual"))["v"] or Decimal("0.00")
        context.update({
            "receitas_mes": receitas_mes,
            "despesas_mes": despesas_mes,
            "total_vendas_mes": total_vendas_mes,
            "total_receber": total_receber,
            "total_pagar": total_pagar,
            "saldo_caixa": saldo_caixa,
            "saldo_bancos": saldo_bancos,
            "lucro_mes": receitas_mes - despesas_mes,
            "liquidez": saldo_caixa + saldo_bancos,
            "saldo_liquido": total_receber - total_pagar,
            "contas_receber_vencidas": ContaReceber.objects.filter(status__in=["aberta", "vencida"], data_vencimento__lt=hoje).count(),
            "contas_pagar_vencidas": ContaPagar.objects.filter(status__in=["aberta", "vencida"], data_vencimento__lt=hoje).count(),
            "contas_receber_vencendo": ContaReceber.objects.filter(status="aberta", data_vencimento__range=(hoje, hoje + timedelta(days=7))).count(),
            "contas_pagar_vencendo": ContaPagar.objects.filter(status="aberta", data_vencimento__range=(hoje, hoje + timedelta(days=7))).count(),
            "impostos_pendentes": ImpostoTributo.objects.filter(situacao__in=["pendente", "calculado", "vencido"]).count(),
            "impostos_valor_devido": ImpostoTributo.objects.filter(situacao__in=["calculado", "vencido"]).aggregate(v=Sum("valor_devido"))["v"] or Decimal("0.00"),
            "dados_fluxo_caixa": json.dumps({"labels": [], "entradas": [], "saidas": [], "saldo_acumulado": []}),
            "receitas_por_categoria": json.dumps([]),
            "despesas_por_categoria": json.dumps([]),
            "evolucao_saldos": json.dumps({"labels": [], "valores": []}),
            "contas_vencimento": json.dumps({"labels": [], "valores": []}),
        })
        catalogo, total_rotas = _catalogo_urls(hoje)
        context.update({
            "catalogo_urls": catalogo,
            "total_rotas": total_rotas,
            "atalhos": _atalhos_registos(hoje),
        })
        return context




class FluxoCaixaView(LoginRequiredMixin, ListView):
    model = FluxoCaixa
    template_name = 'financeiro/fluxo_caixa/lista.html'
    context_object_name = 'fluxos'
    paginate_by = 25

    def get_queryset(self):
        qs = FluxoCaixa.objects.all()
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')

        if data_inicio:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            qs = qs.filter(data_referencia__gte=data_inicio)
        if data_fim:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            qs = qs.filter(data_referencia__lte=data_fim)
        return qs.order_by('data_referencia')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fluxos = self.get_queryset()
        entradas = fluxos.filter(tipo='entrada').aggregate(total=Sum('valor_previsto'))['total'] or 0
        saidas = fluxos.filter(tipo='saida').aggregate(total=Sum('valor_previsto'))['total'] or 0
        context['entradas'] = entradas
        context['saidas'] = saidas
        context['saldo_periodo'] = entradas - saidas
        context['data_inicio'] = self.request.GET.get('data_inicio', date.today().replace(day=1))
        context['data_fim'] = self.request.GET.get('data_fim', date.today())
        return context


from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from .models import FluxoCaixa
from .forms import FluxoCaixaForm
from django.contrib.auth.mixins import LoginRequiredMixin

class FluxoCaixaCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    form_class = FluxoCaixaForm
    template_name = 'financeiro/fluxo_caixa/form.html'
    success_url = reverse_lazy('financeiro:fluxo_caixa')

    def form_valid(self, form):
        # Associa automaticamente a empresa do usuário
        return super().form_valid(form)


class FluxoCaixaUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    form_class = FluxoCaixaForm
    template_name = 'financeiro/fluxo_caixa/form.html'
    success_url = reverse_lazy('financeiro:fluxo_caixa')




class DREView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "acessar_financeiro"
    template_name = "financeiro/dre.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        try:
            mes = int(self.request.GET.get("mes", hoje.month))
            ano = int(self.request.GET.get("ano", hoje.year))
            if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
                raise ValueError
        except (TypeError, ValueError):
            mes, ano = hoje.month, hoje.year
            messages.warning(self.request, "Mês ou ano inválido; foi seleccionado o período actual.")
        inicio = date(ano, mes, 1)
        fim = date(ano + 1, 1, 1) - timedelta(days=1) if mes == 12 else date(ano, mes + 1, 1) - timedelta(days=1)
        movimentos = MovimentacaoFinanceira.objects.filter(
            data_movimentacao__range=(inicio, fim), confirmada=True
        )
        receitas = movimentos.filter(tipo_movimentacao="entrada").aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
        despesas = movimentos.filter(tipo_movimentacao="saida").aggregate(v=Sum("valor"))["v"] or Decimal("0.00")
        nomes = [(1,"Janeiro"),(2,"Fevereiro"),(3,"Março"),(4,"Abril"),(5,"Maio"),(6,"Junho"),(7,"Julho"),(8,"Agosto"),(9,"Setembro"),(10,"Outubro"),(11,"Novembro"),(12,"Dezembro")]
        total = receitas + despesas
        context.update({
            "mes": mes, "ano": ano, "inicio_periodo": inicio, "fim_periodo": fim,
            "total_receitas": receitas, "total_despesas": despesas,
            "resultado": receitas - despesas, "meses_choices": nomes,
            "receitas_percentual": float(receitas / total * 100) if total else 0,
            "despesas_percentual": float(despesas / total * 100) if total else 0,
        })
        return context



class BalancoPatrimonialView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/balanco.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Implementar cálculo do balanço patrimonial
        context.update({
            'ativo_circulante': self._calcular_ativo_circulante(),
            'ativo_nao_circulante': self._calcular_ativo_nao_circulante(),
            'passivo_circulante': self._calcular_passivo_circulante(),
            'passivo_nao_circulante': self._calcular_passivo_nao_circulante(),
            'patrimonio_liquido': self._calcular_patrimonio_liquido()
        })
        
        return context
    
    def _calcular_ativo_circulante(self):
        return 0  # Implementar
    
    def _calcular_ativo_nao_circulante(self):
        return 0  # Implementar
    
    def _calcular_passivo_circulante(self):
        return 0  # Implementar
    
    def _calcular_passivo_nao_circulante(self):
        return 0  # Implementar
    
    def _calcular_patrimonio_liquido(self):
        return 0  # Implementar

# =====================================
# CONTAS A RECEBER
# =====================================

class ContaReceberListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    template_name = 'financeiro/conta_receber/lista.html'
    context_object_name = 'contas'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtros
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        cliente = self.request.GET.get('cliente')
        if cliente:
            queryset = queryset.filter(cliente__nome__icontains=cliente)
        
        vencimento = self.request.GET.get('vencimento')
        if vencimento == 'vencidas':
            queryset = queryset.filter(
                status='pendente',
                data_vencimento__lt=date.today()
            )
        elif vencimento == 'hoje':
            queryset = queryset.filter(data_vencimento=date.today())
        elif vencimento == 'proximos_7_dias':
            queryset = queryset.filter(
                data_vencimento__range=[
                    date.today(),
                    date.today() + timedelta(days=7)
                ]
            )
        
        return queryset.select_related('cliente').order_by('data_vencimento')


class ContaReceberDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = "acessar_financeiro"
    model = ContaReceber
    template_name = "financeiro/conta_receber/detail.html"
    context_object_name = "conta"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contas_bancarias"] = ContaBancaria.objects.filter(ativa=True)
        return context






class ContaReceberCreateView(LoginRequiredMixin, PermissaoAcaoMixin,  CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    form_class = ContaReceberForm
    template_name = 'financeiro/conta_receber/form.html'
    success_url = reverse_lazy('financeiro:conta_receber_lista')
    
    def form_valid(self, form):
        messages.success(self.request, 'Conta a receber criada com sucesso!')
        return super().form_valid(form)

class ContaReceberUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    form_class = ContaReceberForm
    template_name = 'financeiro/conta_receber/form.html'
    success_url = reverse_lazy('financeiro:conta_receber_lista')
    
    def form_valid(self, form):
        messages.success(self.request, 'Conta a receber atualizada com sucesso!')
        return super().form_valid(form)



class ReceberContaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                conta = get_object_or_404(ContaReceber.objects.select_for_update(), pk=pk)
                if conta.status not in ("aberta", "vencida"):
                    raise ValidationError("Só é possível receber contas abertas ou vencidas.")
                valor = _decimal_post(request, "valor_recebido")
                if valor <= 0 or valor > conta.valor_saldo:
                    raise ValidationError("O valor deve ser positivo e não pode ultrapassar o saldo em aberto.")
                banco = get_object_or_404(ContaBancaria, pk=request.POST.get("conta_bancaria"), ativa=True)
                dia = _date_post(request, "data_recebimento")
                movimento = MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="entrada",
                    tipo_documento=_tipo_documento(request),
                    numero_documento=conta.numero_documento,
                    data_movimentacao=dia,
                    valor=valor,
                    conta_bancaria=banco,
                    centro_custo=conta.centro_custo,
                    cliente=conta.cliente,
                    venda_relacionada=conta.venda,
                    descricao=f"Recebimento: {conta.descricao}",
                    observacoes=f"Conta a receber {conta.numero_documento}. {request.POST.get('observacoes', '')}".strip(),
                    status="confirmada",
                    confirmada=True,
                    data_confirmacao=timezone.now(),
                    usuario_responsavel=request.user,
                )
                conta.valor_recebido += valor
                if conta.valor_recebido >= (conta.valor_original + conta.valor_juros + conta.valor_multa - conta.valor_desconto):
                    conta.data_recebimento = dia
                conta.save()
            messages.success(request, "Recebimento registado com sucesso.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("financeiro:conta_receber_detail", pk=pk)




class ParcelarContaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/conta_receber/parcelar.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['conta'] = get_object_or_404(ContaReceber, pk=self.kwargs['pk'])
        return context
    
    def post(self, request, pk):
        conta = get_object_or_404(ContaReceber, pk=pk)
        numero_parcelas = int(request.POST.get('numero_parcelas'))
        
        # Implementar lógica de parcelamento
        valor_parcela = conta.valor / numero_parcelas
        
        for i in range(numero_parcelas):
            data_vencimento = conta.data_vencimento + timedelta(days=30 * i)
            
            ContaReceber.objects.create(
                cliente=conta.cliente,
                descricao=f"{conta.descricao} - Parcela {i+1}/{numero_parcelas}",
                valor=valor_parcela,
                data_vencimento=data_vencimento,
                categoria=conta.categoria,
                observacoes=f"Parcelamento da conta {conta.id}"
            )
        
        # Marcar conta original como parcelada
        conta.status = 'parcelada'
        conta.save()
        
        messages.success(request, f'Conta parcelada em {numero_parcelas}x com sucesso!')
        return redirect('financeiro:conta_receber_lista')

class ContasVencidasView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    template_name = 'financeiro/conta_receber/vencidas.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaReceber.objects.filter(
            status='pendente',
            data_vencimento__lt=date.today()
        ).select_related('cliente').order_by('data_vencimento')

class ContasVencendoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    template_name = 'financeiro/conta_receber/vencendo.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaReceber.objects.filter(
            status='pendente',
            data_vencimento__range=[
                date.today(),
                date.today() + timedelta(days=7)
            ]
        ).select_related('cliente').order_by('data_vencimento')


class NegociarContaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/conta_receber/negociar.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['conta'] = get_object_or_404(ContaReceber, pk=self.kwargs['pk'])
        return context

class ProtestarContaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaReceber, pk=pk)
        
        # Implementar lógica de protesto
        conta.status = 'protestada'
        conta.save()
        
        messages.success(request, 'Conta enviada para protesto!')
        return redirect('financeiro:conta_receber_detail', pk=pk)



# ADICIONAR a apps/financeiro/views.py
# Imports a garantir no topo:
#   from django.db.models import ProtectedError
#   from .models import PlanoConta
#   from .forms import PlanoContaForm
# (Q, Count, Sum, View, ListView, DetailView, CreateView, UpdateView, DeleteView,
#  messages, transaction, get_object_or_404, redirect, reverse_lazy já existem no ficheiro.)

# =====================================
# PLANO DE CONTAS (PGC)
# =====================================

def _pode_gerir_financeiro(user):
    """Superuser, administrador da empresa ou funcionário com a permissão 'acessar_financeiro'."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or getattr(user, "e_administrador_empresa", False):
        return True
    funcionario = getattr(user, "funcionario_relacionado", None) or getattr(user, "funcionario", None)
    return bool(funcionario and funcionario.pode_realizar_acao("acessar_financeiro"))


class PlanoContaAcessoMixin(LoginRequiredMixin):
    """Acesso ao Plano de Contas: admin ou quem tem permissão de financeiro."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not _pode_gerir_financeiro(request.user):
            messages.error(request, "Não tem permissão para gerir o Plano de Contas.")
            return redirect("financeiro:dashboard")
        return super().dispatch(request, *args, **kwargs)


def _impedimentos_plano_conta(conta):
    """Motivos que impedem a eliminação (as FKs são PROTECT)."""
    motivos = []
    n = conta.subcontas.count()
    if n:
        motivos.append(f"tem {n} subconta(s) agregada(s)")
    n = conta.movimentacoes.count()
    if n:
        motivos.append(f"está associada a {n} movimentação(ões) financeira(s)")
    n = conta.categorias_financeiras.count()
    if n:
        motivos.append(f"está associada a {n} categoria(s) financeira(s)")
    return motivos


class PlanoContaListView(PlanoContaAcessoMixin, ListView):
    model = PlanoConta
    template_name = "financeiro/plano_contas/lista.html"
    context_object_name = "contas"
    paginate_by = 100

    def get_queryset(self):
        qs = PlanoConta.objects.select_related("conta_pai").order_by("codigo")
        g = self.request.GET
        q = (g.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(codigo__icontains=q) | Q(nome__icontains=q))
        if g.get("classe") in dict(PlanoConta.CLASSE_CHOICES):
            qs = qs.filter(classe=g["classe"])
        if g.get("natureza") in dict(PlanoConta.NATUREZA_CHOICES):
            qs = qs.filter(natureza=g["natureza"])
        if g.get("estado") == "ativas":
            qs = qs.filter(ativa=True)
        elif g.get("estado") == "inativas":
            qs = qs.filter(ativa=False)
        if g.get("tipo") == "movimento":
            qs = qs.filter(aceita_lancamentos=True)
        elif g.get("tipo") == "agregadora":
            qs = qs.filter(aceita_lancamentos=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        total = PlanoConta.objects.count()
        ctx.update({
            "querystring": params.urlencode(),
            "classes": PlanoConta.CLASSE_CHOICES,
            "naturezas": PlanoConta.NATUREZA_CHOICES,
            "filtros": self.request.GET,
            "total_contas": total,
            "total_ativas": PlanoConta.objects.filter(ativa=True).count(),
            "total_movimento": PlanoConta.objects.filter(aceita_lancamentos=True).count(),
            "total_filtrado": self.get_queryset().count(),
        })
        return ctx


class PlanoContaDetailView(PlanoContaAcessoMixin, DetailView):
    model = PlanoConta
    template_name = "financeiro/plano_contas/detail.html"
    context_object_name = "conta"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conta = self.object
        ctx["subcontas"] = conta.subcontas.order_by("codigo")
        ctx["movimentacoes_recentes"] = (conta.movimentacoes
                                         .select_related("conta_bancaria")
                                         .order_by("-data_movimentacao")[:10])
        ctx["total_movimentacoes"] = conta.movimentacoes.count()
        ctx["total_categorias"] = conta.categorias_financeiras.count()
        ctx["impedimentos"] = _impedimentos_plano_conta(conta)
        return ctx


class PlanoContaCreateView(PlanoContaAcessoMixin, CreateView):
    model = PlanoConta
    form_class = PlanoContaForm
    template_name = "financeiro/plano_contas/form.html"
    success_url = reverse_lazy("financeiro:plano_conta_lista")

    def get_initial(self):
        initial = super().get_initial()
        pai = self.request.GET.get("conta_pai")
        if pai and pai.isdigit():
            initial["conta_pai"] = pai
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Conta do plano criada com sucesso.")
        return super().form_valid(form)


class PlanoContaUpdateView(PlanoContaAcessoMixin, UpdateView):
    model = PlanoConta
    form_class = PlanoContaForm
    template_name = "financeiro/plano_contas/form.html"

    def get_success_url(self):
        return reverse_lazy("financeiro:plano_conta_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, "Conta do plano atualizada com sucesso.")
        return super().form_valid(form)


class PlanoContaDeleteView(PlanoContaAcessoMixin, DeleteView):
    model = PlanoConta
    template_name = "financeiro/plano_contas/confirm_delete.html"
    context_object_name = "conta"
    success_url = reverse_lazy("financeiro:plano_conta_lista")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["impedimentos"] = _impedimentos_plano_conta(self.object)
        return ctx

    def form_valid(self, form):
        conta = self.object
        motivos = _impedimentos_plano_conta(conta)
        if motivos:
            messages.error(
                self.request,
                f"Não é possível eliminar {conta.codigo}: a conta {'; '.join(motivos)}. "
                "Pode desativá-la em vez de a eliminar.")
            return redirect("financeiro:plano_conta_detail", pk=conta.pk)
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "A conta está em uso e não pode ser eliminada. Desative-a em vez disso.")
            return redirect("financeiro:plano_conta_detail", pk=conta.pk)
        messages.success(self.request, f"Conta {conta.codigo} eliminada.")
        return response


class PlanoContaAlternarView(PlanoContaAcessoMixin, View):
    """Ativa/desativa uma conta (alternativa segura à eliminação)."""
    http_method_names = ["post"]

    def post(self, request, pk):
        conta = get_object_or_404(PlanoConta, pk=pk)
        conta.ativa = not conta.ativa
        conta.save(update_fields=["ativa", "updated_at"] if hasattr(conta, "updated_at") else ["ativa"])
        messages.success(request, f"Conta {conta.codigo} {'ativada' if conta.ativa else 'desativada'}.")
        return redirect(request.POST.get("next") or "financeiro:plano_conta_lista")


# ---- No catálogo do dashboard (_CATALOGO), na categoria "Centros de custo e conciliações",
# ---- acrescentar estes dois itens:
#     ("Plano de contas", "Plano Geral de Contabilidade (PGC)", "plano_conta_lista"),
#     ("Nova conta do plano", "Registar conta contabilística", "plano_conta_create"),

# =====================================
# CONTAS A PAGAR
# =====================================

class ContaPagarListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaPagar
    template_name = 'financeiro/conta_pagar/lista.html'
    context_object_name = 'contas'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtros similares às contas a receber
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset.select_related('fornecedor').order_by('data_vencimento')



class ContaPagarDetailView(DetailView):
    """Integre get_context_data desta classe na ContaPagarDetailView existente."""
    acao_requerida = "acessar_financeiro"
    model = ContaReceber
    template_name = "financeiro/conta_pagar/detail.html"
    context_object_name = "conta"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contas_bancarias"] = ContaBancaria.objects.filter(ativa=True)
        return context




class ContaPagarCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaPagar
    form_class = ContaPagarForm
    template_name = 'financeiro/conta_pagar/form.html'
    success_url = reverse_lazy('financeiro:conta_pagar_lista')

class ContaPagarUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaPagar
    form_class = ContaPagarForm
    template_name = 'financeiro/conta_pagar/form.html'
    success_url = reverse_lazy('financeiro:conta_pagar_lista')




class PagarContaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                conta = get_object_or_404(ContaPagar.objects.select_for_update(), pk=pk)
                if conta.status not in ("aberta", "vencida"):
                    raise ValidationError("Só é possível pagar contas abertas ou vencidas.")
                valor = _decimal_post(request, "valor_pago")
                if valor <= 0 or valor > conta.valor_saldo:
                    raise ValidationError("O valor deve ser positivo e não pode ultrapassar o saldo a pagar.")
                banco = get_object_or_404(ContaBancaria, pk=request.POST.get("conta_bancaria"), ativa=True)
                dia = _date_post(request, "data_pagamento")
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="saida",
                    tipo_documento=_tipo_documento(request),
                    numero_documento=conta.numero_documento,
                    data_movimentacao=dia,
                    valor=valor,
                    conta_bancaria=banco,
                    centro_custo=conta.centro_custo,
                    fornecedor=conta.fornecedor,
                    descricao=f"Pagamento: {conta.descricao}",
                    observacoes=f"Conta a pagar {conta.numero_documento}. {request.POST.get('observacoes', '')}".strip(),
                    status="confirmada",
                    confirmada=True,
                    data_confirmacao=timezone.now(),
                    usuario_responsavel=request.user,
                )
                conta.valor_pago += valor
                if conta.valor_pago >= (conta.valor_original + conta.valor_juros + conta.valor_multa - conta.valor_desconto):
                    conta.data_pagamento = dia
                conta.save()
            messages.success(request, "Pagamento registado com sucesso.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("financeiro:conta_pagar_detail", pk=pk)



class AgendarPagamentoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaPagar, pk=pk)
        
        data_agendamento = request.POST.get('data_agendamento')
        
        conta.data_agendamento = data_agendamento
        conta.status = 'agendada'
        conta.save()
        
        messages.success(request, 'Pagamento agendado com sucesso!')
        return redirect('financeiro:conta_pagar_detail', pk=pk)

class AgendaPagamentosView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaPagar
    template_name = 'financeiro/conta_pagar/agenda.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaPagar.objects.filter(
            status='agendada'
        ).order_by('data_agendamento')

##########################

class AprovacaoPagamentosView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaPagar
    template_name = 'financeiro/conta_pagar/aprovacao.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaPagar.objects.filter(
            status='aguardando_aprovacao'
        ).order_by('data_vencimento')

class PagamentoLoteView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/conta_pagar/pagamento_lote.html'
    
    def post(self, request):
        contas_ids = request.POST.getlist('contas')
        data_pagamento = request.POST.get('data_pagamento')
        
        for conta_id in contas_ids:
            conta = get_object_or_404(ContaPagar, pk=conta_id)
            # Implementar lógica de pagamento em lote
        
        messages.success(request, f'{len(contas_ids)} contas pagas em lote!')
        return redirect('financeiro:conta_pagar_lista')

# =====================================
# MOVIMENTAÇÃO FINANCEIRA
# =====================================



# =====================================
# BANCOS E CONTAS
# =====================================

class BancoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/banco/lista.html'
    context_object_name = 'contas'

class BancoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/banco/detail.html'
    context_object_name = 'conta'

class BancoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/banco/form.html'
    fields = '__all__'
    success_url = reverse_lazy('financeiro:banco_lista')

from django.urls import reverse_lazy


class BancoEditarView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = "financeiro/banco/form.html"
    fields = [
        "nome", "banco", "agencia", "conta", "digito", "tipo_conta",
        "saldo_inicial", "saldo_atual",
        "limite_credito",
        "ativa", "conta_principal", "permite_saldo_negativo",
        "codigo_integracao", "ultima_conciliacao",
        "observacoes",
    ]

    def get_success_url(self):
        # Redireciona para os detalhes da conta após editar
        return reverse_lazy("financeiro:banco_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        # Aqui podes adicionar lógica extra, como logs ou auditoria
        self.object = form.save(commit=False)
        # Exemplo: garantir que só uma conta seja principal
        if self.object.conta_principal:
            ContaBancaria.objects.filter(
                conta_principal=True
            ).exclude(pk=self.object.pk).update(conta_principal=False)
        self.object.save()
        return super().form_valid(form)


class ExtratoBancarioView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/banco/extrato.html'
    context_object_name = 'conta'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Movimentações da conta
        context['movimentacoes'] = MovimentacaoFinanceira.objects.filter(
            conta_bancaria=self.object
        ).order_by('-data_movimentacao')
        
        return context

class ConciliacaoBancariaView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/banco/conciliacao.html'
    context_object_name = 'conta'


class DepositoBancarioView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                conta = get_object_or_404(ContaBancaria.objects.select_for_update(), pk=pk, ativa=True)
                valor = _decimal_post(request, "valor")
                if valor <= 0:
                    raise ValidationError("O valor do depósito deve ser maior que zero.")
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="entrada", tipo_documento=_tipo_documento(request),
                    data_movimentacao=timezone.localdate(), valor=valor, conta_bancaria=conta,
                    descricao=(request.POST.get("descricao") or "Depósito bancário")[:255],
                    status="confirmada", confirmada=True, data_confirmacao=timezone.now(),
                    usuario_responsavel=request.user,
                )
            messages.success(request, "Depósito registado com sucesso.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("financeiro:banco_detail", pk=pk)






class SaqueBancarioView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                conta = get_object_or_404(ContaBancaria.objects.select_for_update(), pk=pk, ativa=True)
                valor = _decimal_post(request, "valor")
                if valor <= 0:
                    raise ValidationError("O valor do saque deve ser maior que zero.")
                if not conta.permite_saldo_negativo and valor > conta.saldo_atual:
                    raise ValidationError("Saldo insuficiente para efectuar o saque.")
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="saida", tipo_documento=_tipo_documento(request),
                    data_movimentacao=timezone.localdate(), valor=valor, conta_bancaria=conta,
                    descricao=(request.POST.get("descricao") or "Saque bancário")[:255],
                    status="confirmada", confirmada=True, data_confirmacao=timezone.now(),
                    usuario_responsavel=request.user,
                )
            messages.success(request, "Saque registado com sucesso.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("financeiro:banco_detail", pk=pk)





class TransferenciaBancariaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
    acao_requerida = "acessar_financeiro"
    template_name = "financeiro/banco/transferencia.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.conta_origem = get_object_or_404(ContaBancaria, pk=self.kwargs["pk"], ativa=True)
        context["conta_origem"] = self.conta_origem
        context["contas_bancarias"] = ContaBancaria.objects.filter(ativa=True).exclude(pk=self.conta_origem.pk)
        return context

    def post(self, request, pk):
        try:
            with transaction.atomic():
                origem = get_object_or_404(ContaBancaria.objects.select_for_update(), pk=pk, ativa=True)
                destino = get_object_or_404(ContaBancaria.objects.select_for_update(), pk=request.POST.get("conta_destino"), ativa=True)
                if origem.pk == destino.pk:
                    raise ValidationError("A conta de origem e de destino têm de ser diferentes.")
                valor = _decimal_post(request, "valor")
                if valor <= 0:
                    raise ValidationError("O valor da transferência deve ser maior que zero.")
                if not origem.permite_saldo_negativo and valor > origem.saldo_atual:
                    raise ValidationError("Saldo insuficiente na conta de origem.")
                dia = timezone.localdate()
                descricao = (request.POST.get("descricao") or "Transferência bancária")[:255]
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="transferencia", tipo_documento="transferencia",
                    data_movimentacao=dia, valor=valor, conta_bancaria=origem,
                    conta_destino=destino, descricao=descricao,
                    observacoes=f"Transferência para {destino.nome}", status="confirmada",
                    confirmada=True, data_confirmacao=timezone.now(), usuario_responsavel=request.user,
                )
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="entrada", tipo_documento="transferencia",
                    data_movimentacao=dia, valor=valor, conta_bancaria=destino,
                    descricao=f"Transferência recebida de {origem.nome}",
                    observacoes=f"Transferência originada na conta {origem.pk}", status="confirmada",
                    confirmada=True, data_confirmacao=timezone.now(), usuario_responsavel=request.user,
                )
            messages.success(request, "Transferência registada com sucesso.")
            return redirect("financeiro:banco_detail", pk=origem.pk)
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
            return redirect("financeiro:transferencia_bancaria", pk=pk)





# =====================================
# CAIXA
# =====================================

class CaixaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/caixa/caixa.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Status do caixa
        context['caixa_aberto'] = self._verificar_caixa_aberto()
        context['saldo_atual'] = self._calcular_saldo_caixa()
        context['movimentacoes_hoje'] = self._get_movimentacoes_hoje()
        
        return context
    
    def _verificar_caixa_aberto(self):
        # Implementar verificação se caixa está aberto
        return True
    
    def _calcular_saldo_caixa(self):
        return MovimentoCaixa.objects.aggregate(
            saldo=Sum('valor')
        )['saldo'] or 0
    
    def _get_movimentacoes_hoje(self):
        return MovimentoCaixa.objects.filter(
            data_movimento=date.today()
        ).order_by('-hora_movimento')

class AbrirCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/caixa/abrir.html'
    
    def post(self, request):
        valor_inicial = Decimal(request.POST.get('valor_inicial', 0))
        
        # Criar movimento de abertura
        MovimentoCaixa.objects.create(
            tipo_movimento='abertura',
            valor=valor_inicial,
            descricao='Abertura do caixa',
            data_movimento=date.today(),
            usuario=request.user
        )
        
        messages.success(request, 'Caixa aberto com sucesso!')
        return redirect('financeiro:caixa')

class FecharCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/caixa/fechar.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['saldo_sistema'] = self._calcular_saldo_caixa()
        return context
    
    def post(self, request):
        valor_informado = Decimal(request.POST.get('valor_informado'))
        saldo_sistema = self._calcular_saldo_caixa()
        diferenca = valor_informado - saldo_sistema
        
        # Criar movimento de fechamento
        MovimentoCaixa.objects.create(
            tipo_movimento='fechamento',
            valor=saldo_sistema,
            descricao='Fechamento do caixa',
            data_movimento=date.today(),
            usuario=request.user,
            observacoes=f'Diferença: {diferenca}'
        )
        
        messages.success(request, 'Caixa fechado com sucesso!')
        return redirect('financeiro:caixa')
    
    def _calcular_saldo_caixa(self):
        return MovimentoCaixa.objects.aggregate(
            saldo=Sum('valor')
        )['saldo'] or 0

class SangriaCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request):
        valor = Decimal(request.POST.get('valor'))
        motivo = request.POST.get('motivo')
        
        MovimentoCaixa.objects.create(
            tipo_movimento='sangria',
            valor=-valor,  # Valor negativo
            descricao=f'Sangria - {motivo}',
            data_movimento=date.today(),
            usuario=request.user
        )
        
        messages.success(request, 'Sangria realizada com sucesso!')
        return redirect('financeiro:caixa')

class SuprimentoCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request):
        valor = Decimal(request.POST.get('valor'))
        motivo = request.POST.get('motivo')
        
        MovimentoCaixa.objects.create(
            tipo_movimento='suprimento',
            valor=valor,
            descricao=f'Suprimento - {motivo}',
            data_movimento=date.today(),
            usuario=request.user
        )
        
        messages.success(request, 'Suprimento realizado com sucesso!')
        return redirect('financeiro:caixa')

class ConferenciaCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/caixa/conferencia.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Movimentações do dia
        context['movimentacoes'] = MovimentoCaixa.objects.filter(
            data_movimento=date.today()
        ).order_by('hora_movimento')
        
        # Totais por tipo
        context['total_vendas'] = MovimentoCaixa.objects.filter(
            data_movimento=date.today(),
            tipo_movimento='venda'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['total_sangrias'] = MovimentoCaixa.objects.filter(
            data_movimento=date.today(),
            tipo_movimento='sangria'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['saldo_final'] = self._calcular_saldo_caixa()
        
        return context
    
    def _calcular_saldo_caixa(self):
        return MovimentoCaixa.objects.aggregate(
            saldo=Sum('valor')
        )['saldo'] or 0

class RelatorioCaixaDiarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/caixa/relatorio_diario.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        data = self.request.GET.get('data', date.today())
        
        context['data'] = data
        context['movimentacoes'] = MovimentoCaixa.objects.filter(
            data_movimento=data
        ).order_by('hora_movimento')
        
        return context

class MovimentoCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentoCaixa
    template_name = 'financeiro/caixa/movimento.html'
    context_object_name = 'movimentacoes'
    paginate_by = 50
    
    def get_queryset(self):
        return super().get_queryset().order_by('-data_movimento', '-hora_movimento')

class HistoricoCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = MovimentoCaixa
    template_name = 'financeiro/caixa/historico.html'
    context_object_name = 'movimentacoes'
    paginate_by = 100

# =====================================
# CARTÕES E TEF (Implementação básica)
# =====================================

# =====================================
# CARTÕES E TEF (sobre PagamentoVenda — sem tabelas novas)
# =====================================
# Transação eletrónica = pagamento cuja forma é de cartão ou marcada necessita_tef.
# NSU/TID/autorização são registados a partir do terminal; não há integração
# com fornecedor de TEF.
TIPOS_CARTAO = ("cartao_debito", "cartao_credito")
STATUS_ANULADOS = ("estornado", "cancelado", "rejeitado")
STATUS_PENDENTES = ("pendente", "processando")
STATUS_CANCELAVEIS = ("pendente", "processando", "aprovado")


def _pagamentos_eletronicos():
    return (PagamentoVenda.objects
            .filter(Q(forma_pagamento__necessita_tef=True) | Q(forma_pagamento__tipo__in=TIPOS_CARTAO))
            .select_related("venda", "forma_pagamento"))


def _formas_eletronicas():
    return FormaPagamento.objects.filter(Q(necessita_tef=True) | Q(tipo__in=TIPOS_CARTAO))


def _totais(qs):
    t = qs.exclude(status__in=STATUS_ANULADOS).aggregate(
        bruto=Sum("valor_pago"), taxas=Sum("valor_taxa"),
        liquido=Sum("valor_liquido"), n=Count("id"))
    return {k: (v or 0) for k, v in t.items()}


def _periodo_get(request):
    hoje = timezone.localdate()
    try:
        ini = date.fromisoformat(request.GET.get("inicio", ""))
    except ValueError:
        ini = hoje.replace(day=1)
    try:
        fim = date.fromisoformat(request.GET.get("fim", ""))
    except ValueError:
        fim = hoje
    return (fim, ini) if ini > fim else (ini, fim)


class _CartaoPeriodoMixin(LoginRequiredMixin, PermissaoAcaoMixin):
    acao_requerida = "acessar_financeiro"

    def pagamentos_periodo(self):
        self.inicio, self.fim = _periodo_get(self.request)
        return _pagamentos_eletronicos().filter(data_pagamento__date__range=(self.inicio, self.fim))

    def contexto_periodo(self):
        params = self.request.GET.copy()
        params.pop("page", None)
        return {"inicio": self.inicio, "fim": self.fim, "querystring": params.urlencode()}


def _marcar_cancelaveis(pagamentos):
    lista = list(pagamentos)
    for p in lista:
        p.pode_cancelar = p.status in STATUS_CANCELAVEIS
    return lista


class CartaoListView(_CartaoPeriodoMixin, TemplateView):
    template_name = "financeiro/cartao/lista.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.pagamentos_periodo()
        ctx.update(self.contexto_periodo())
        ctx["totais"] = _totais(qs)
        ctx["por_forma"] = (qs.exclude(status__in=STATUS_ANULADOS)
                            .values("forma_pagamento__nome")
                            .annotate(n=Count("id"), bruto=Sum("valor_pago"),
                                      taxas=Sum("valor_taxa"), liquido=Sum("valor_liquido"))
                            .order_by("-bruto"))
        rotulos = dict(PagamentoVenda.STATUS_CHOICES)
        ctx["por_estado"] = [{"rotulo": rotulos.get(r["status"], r["status"]), "n": r["n"]}
                             for r in qs.values("status").annotate(n=Count("id")).order_by("-n")]
        ctx["sem_formas"] = not _formas_eletronicas().filter(ativa=True).exists()
        return ctx


class VendasCartaoView(_CartaoPeriodoMixin, ListView):
    template_name = "financeiro/cartao/vendas.html"
    context_object_name = "pagamentos"
    paginate_by = 50

    def get_queryset(self):
        qs = self.pagamentos_periodo()
        self.estado = self.request.GET.get("estado", "")
        if self.estado in dict(PagamentoVenda.STATUS_CHOICES):
            qs = qs.filter(status=self.estado)
        return qs.order_by("-data_pagamento")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self.contexto_periodo())
        ctx["totais"] = _totais(self.pagamentos_periodo())
        ctx["estados"] = PagamentoVenda.STATUS_CHOICES
        ctx["estado"] = self.estado
        return ctx


class RecebimentosCartaoView(_CartaoPeriodoMixin, TemplateView):
    template_name = "financeiro/cartao/recebimentos.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self.pagamentos_periodo()
        aprovados = base.filter(status="aprovado")
        ctx.update(self.contexto_periodo())
        ctx["totais"] = _totais(aprovados)
        ctx["pendentes"] = _totais(base.filter(status__in=STATUS_PENDENTES))
        ctx["dias"] = (aprovados.annotate(dia=TruncDate("data_pagamento")).values("dia")
                       .annotate(n=Count("id"), bruto=Sum("valor_pago"),
                                 taxas=Sum("valor_taxa"), liquido=Sum("valor_liquido"))
                       .order_by("-dia"))
        return ctx


class TaxasCartaoView(_CartaoPeriodoMixin, TemplateView):
    template_name = "financeiro/cartao/taxas.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.pagamentos_periodo()
        ctx.update(self.contexto_periodo())
        por_forma = {r["forma_pagamento"]: r for r in
                     qs.exclude(status__in=STATUS_ANULADOS).values("forma_pagamento")
                     .annotate(bruto=Sum("valor_pago"), taxas=Sum("valor_taxa"))}
        ctx["formas"] = [{
            "forma": f,
            "bruto": por_forma.get(f.pk, {}).get("bruto") or 0,
            "taxas": por_forma.get(f.pk, {}).get("taxas") or 0,
        } for f in _formas_eletronicas().order_by("ordem_exibicao", "nome")]
        ctx["totais"] = _totais(qs)
        return ctx


class ConciliacaoCartaoView(_CartaoPeriodoMixin, TemplateView):
    """Conferência interna (sem extrato do adquirente): lacunas e duplicados."""
    template_name = "financeiro/cartao/conciliacao.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self.pagamentos_periodo()
        aprovados = base.filter(status="aprovado")
        ctx.update(self.contexto_periodo())

        sem_ref = aprovados.filter(Q(nsu="") | Q(numero_autorizacao="")).order_by("-data_pagamento")
        nsus_dup = [r["nsu"] for r in aprovados.exclude(nsu="").values("nsu")
                    .annotate(n=Count("id")).filter(n__gt=1)]
        duplicados = aprovados.filter(nsu__in=nsus_dup).order_by("nsu", "-data_pagamento")
        parados = base.filter(status__in=STATUS_PENDENTES,
                              data_pagamento__lt=timezone.now() - timedelta(days=1)).order_by("data_pagamento")

        ctx["totais"] = _totais(aprovados)
        ctx["sem_ref_total"], ctx["duplicados_total"], ctx["parados_total"] = (
            sem_ref.count(), duplicados.count(), parados.count())
        ctx["sem_ref"], ctx["duplicados"], ctx["parados"] = sem_ref[:100], duplicados[:100], parados[:100]
        return ctx


class TEFView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = "acessar_financeiro"
    template_name = "financeiro/tef/tef.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        do_dia = _pagamentos_eletronicos().filter(data_pagamento__date=hoje)
        ctx["hoje"] = hoje
        ctx["totais"] = _totais(do_dia)
        ctx["pendentes"] = do_dia.filter(status__in=STATUS_PENDENTES).count()
        ctx["estornados"] = do_dia.filter(status="estornado").count()
        ctx["recentes"] = _marcar_cancelaveis(_pagamentos_eletronicos().order_by("-data_pagamento")[:10])
        ctx["formas_ativas"] = _formas_eletronicas().filter(ativa=True).order_by("ordem_exibicao", "nome")
        return ctx


class TransacoesTEFView(_CartaoPeriodoMixin, ListView):
    template_name = "financeiro/tef/transacoes.html"
    context_object_name = "pagamentos"
    paginate_by = 50

    def get_queryset(self):
        qs = self.pagamentos_periodo()
        self.estado = self.request.GET.get("estado", "")
        self.busca = (self.request.GET.get("q") or "").strip()
        if self.estado in dict(PagamentoVenda.STATUS_CHOICES):
            qs = qs.filter(status=self.estado)
        if self.busca:
            qs = qs.filter(Q(nsu__icontains=self.busca) | Q(tid__icontains=self.busca) |
                           Q(numero_autorizacao__icontains=self.busca) |
                           Q(venda__numero_documento__icontains=self.busca))
        return qs.order_by("-data_pagamento")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(self.contexto_periodo())
        ctx["pagamentos"] = _marcar_cancelaveis(ctx["pagamentos"])
        ctx["estados"] = PagamentoVenda.STATUS_CHOICES
        ctx["estado"], ctx["busca"] = self.estado, self.busca
        return ctx


class CancelarTEFView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """Regista o estorno do pagamento. A devolução ao cliente faz-se no terminal."""
    acao_requerida = "acessar_financeiro"
    http_method_names = ["post"]

    def post(self, request, pk):
        motivo = (request.POST.get("motivo") or "").strip()
        if len(motivo) < 5:
            messages.error(request, "Indique o motivo do cancelamento (mínimo 5 caracteres).")
            return redirect("financeiro:tef_transacoes")

        with transaction.atomic():
            pagamento = get_object_or_404(
                _pagamentos_eletronicos().select_for_update(of=("self",)), pk=pk)
            if pagamento.status not in STATUS_CANCELAVEIS:
                messages.error(request, "Esta transação já não pode ser cancelada.")
                return redirect("financeiro:tef_transacoes")
            pagamento.status = "estornado"
            pagamento.data_estorno = timezone.now()
            pagamento.motivo_estorno = motivo[:255]
            pagamento.usuario_estorno = request.user
            pagamento.save(update_fields=["status", "data_estorno", "motivo_estorno", "usuario_estorno"])
            pagamento.venda.calcular_saldo_e_atualizar_status()

        messages.success(request, "Transação cancelada e valor estornado na venda.")
        if pagamento.venda.documento_fiscal_id:
            messages.warning(
                request,
                "A venda tem documento fiscal emitido e este cancelamento não o altera. "
                "Se houve devolução ao cliente, emita a Nota de Crédito correspondente.")
        return redirect("financeiro:tef_transacoes")
    
# =====================================
# CATEGORIAS E CENTROS DE CUSTO
# =====================================

class CentroCustoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = CentroCusto
    template_name = 'financeiro/centro_custo/lista.html'
    context_object_name = 'centros_custo'

class CentroCustoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = CentroCusto
    form_class = CentroCustoForm
    template_name = 'financeiro/centro_custo/form.html'
    success_url = reverse_lazy('financeiro:centro_custo_lista')

class CentroCustoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = CentroCusto
    template_name = 'financeiro/centro_custo/detail.html'
    context_object_name = 'centro_custo'

# =====================================
# PLANEJAMENTO FINANCEIRO (Implementação básica)
# =====================================


class ProjecoesFinanceirasView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/planejamento/projecoes.html'

class CenariosFinanceirosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/planejamento/cenarios.html'

class MetasFinanceirasView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/planejamento/metas.html'



class ImpostoTributoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    template_name = 'tributacao/imposto_list.html'
    context_object_name = 'impostos'
    paginate_by = 20

    def get_queryset(self):
        return ImpostoTributo.objects.filter().order_by('-ano_referencia', '-mes_referencia')



class ImpostoTributoDetailView(DetailView):
    """Integre get_context_data desta classe na ImpostoTributoDetailView existente."""
    acao_requerida = "acessar_financeiro"
    template_name = "tributacao/imposto_detail.html"
    context_object_name = "imposto"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contas_bancarias"] = ContaBancaria.objects.filter(ativa=True)
        return context


class ImpostoTributoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    form_class = ImpostoTributoForm
    template_name = 'tributacao/imposto_form.html'
    success_url = reverse_lazy('tributacao:imposto_list')

    def form_valid(self, form):
        imposto = form.save(commit=False)
        imposto.usuario_responsavel = self.request.user
        imposto.save()
        messages.success(self.request, 'Imposto/Tributo criado com sucesso.')
        return super().form_valid(form)


class ImpostoTributoUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    form_class = ImpostoTributoForm
    template_name = 'tributacao/imposto_form.html'
    success_url = reverse_lazy('tributacao:imposto_list')

    def form_valid(self, form):
        messages.success(self.request, 'Imposto/Tributo atualizado com sucesso.')
        return super().form_valid(form)


class ImpostoTributoDeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    template_name = 'tributacao/imposto_confirm_delete.html'
    success_url = reverse_lazy('tributacao:imposto_list')

    def delete(self, request, *args, **kwargs):
        messages.warning(self.request, 'Imposto/Tributo excluído permanentemente.')
        return super().delete(request, *args, **kwargs)


class ImpostoCalcularView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def get(self, request, pk):
        imposto = get_object_or_404(ImpostoTributo, pk=pk)
        try:
            imposto.calcular_imposto_angola(forcar_recalculo=True)
            messages.success(request, 'Cálculo do imposto efetuado com sucesso.')
        except Exception as e:
            messages.error(request, f'Erro ao calcular imposto: {e}')
        return redirect('tributacao:imposto_detail', pk=imposto.pk)


logger = logging.getLogger(__name__)



class ImpostoPagarView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        try:
            with transaction.atomic():
                imposto = get_object_or_404(ImpostoTributo.objects.select_for_update(), pk=pk)
                if imposto.situacao == "pago":
                    raise ValidationError("Este imposto já está marcado como pago.")
                conta = get_object_or_404(ContaBancaria.objects.select_for_update(), pk=request.POST.get("conta_bancaria"), ativa=True)
                pendente = (imposto.total_agt or imposto.valor_devido) - imposto.valor_pago
                if pendente <= 0:
                    raise ValidationError("Não existe saldo fiscal pendente para pagar.")
                movimento = MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao="saida", tipo_documento="transferencia",
                    data_movimentacao=timezone.localdate(), valor=pendente,
                    conta_bancaria=conta, centro_custo=imposto.centro_custo,
                    descricao=f"Pagamento do imposto {imposto.nome}",
                    observacoes=f"Imposto {imposto.codigo_imposto_interno}",
                    status="confirmada", confirmada=True, data_confirmacao=timezone.now(),
                    usuario_responsavel=request.user,
                )
                imposto.valor_pago += pendente
                imposto.data_pagamento = timezone.localdate()
                imposto.conta_bancaria_pagamento = conta
                imposto.movimentacao_pagamento = movimento
                imposto.usuario_responsavel = request.user
                imposto.situacao = "pago"
                imposto.save()
            messages.success(request, "Pagamento do imposto registado com sucesso.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("financeiro:imposto_detail", pk=pk)





class ImpostoCalcularView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = "acessar_financeiro"

    def post(self, request, pk):
        imposto = get_object_or_404(ImpostoTributo, pk=pk)
        try:
            imposto.calcular_imposto_angola(forcar_recalculo=True)
            messages.success(request, "Cálculo do imposto concluído.")
        except Exception:
            messages.error(request, "Não foi possível calcular este imposto. Consulte os logs técnicos.")
        return redirect("financeiro:imposto_detail", pk=pk)



@login_required
def estornar_imposto_view(request, pk):
    """View pública para usuários solicitarem estorno de imposto"""
    imposto = get_object_or_404(ImpostoTributo, pk=pk)

    if imposto.situacao != "pago":
        messages.error(request, "⚠️ Este imposto não está pago, portanto não pode ser estornado.")
        return redirect("financeiro:imposto_detail", pk=imposto.pk)

    try:
        resultado = imposto.estornar_imposto_agt(usuario=request.user)
        if resultado["status"] == "sucesso":
            messages.success(request, resultado["mensagem"])
        else:
            messages.error(request, resultado["mensagem"])
    except Exception as e:
        messages.error(request, f"❌ Erro ao estornar imposto: {e}")

    return redirect("financeiro:detalhe_imposto", pk=imposto.pk)


# Conciliação
class ConciliacaoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/conciliacao/conciliacao.html'

class ConciliacaoAutomaticaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/conciliacao/automatica.html'

class FechamentoMensalView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/fechamento/mensal.html'

class FechamentoDetalhesView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/fechamento/detalhes.html'

# Relatórios
class FinanceiroRelatoriosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/index.html'

class RelatorioFluxoCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/fluxo_caixa.html'

class RelatorioDREView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/dre.html'

class RelatorioBalancoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/balanco.html'

class RelatorioInadimplenciaView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/inadimplencia.html'

class RelatorioContasReceberView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/contas_receber.html'

class RelatorioContasPagarView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/contas_pagar.html'

class RelatorioMovimentoBancarioView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/relatorios/movimento_bancario.html'

# Análises
class AnalisesFinanceirasView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/analises/index.html'

class AnaliseLiquidezView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/analises/liquidez.html'

class AnaliseRentabilidadeView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/analises/rentabilidade.html'

class AnaliseEndividamentoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/analises/endividamento.html'

# Cobrança


# AJAX
class CalcularJurosView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        valor = Decimal(request.GET.get('valor', 0))
        taxa = Decimal(request.GET.get('taxa', 0))
        dias = int(request.GET.get('dias', 0))
        
        juros = valor * (taxa / 100) * (dias / 30)
        total = valor + juros
        
        return JsonResponse({
            'juros': str(juros),
            'total': str(total)
        })

class ConsultarSaldoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        conta_id = request.GET.get('conta_id')
        
        if conta_id:
            # Implementar consulta de saldo
            saldo = 0
        else:
            saldo = 0
        
        return JsonResponse({'saldo': str(saldo)})

class ValidarContaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        banco = request.GET.get('banco')
        agencia = request.GET.get('agencia')
        conta = request.GET.get('conta')
        
        # Implementar validação de conta
        valida = True
        
        return JsonResponse({'valida': valida})

class BuscarBancoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        codigo = request.GET.get('codigo')
        
        # Implementar busca de banco por código
        banco = {'nome': 'Banco Exemplo', 'codigo': codigo}
        
        return JsonResponse(banco)

# Importação/Exportação
class ImportarFinanceiroView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/importar/index.html'

class ImportarOFXView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/importar/ofx.html'

class ImportarCNABView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/importar/cnab.html'

class ExportarFinanceiroView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/exportar/index.html'

# =====================================
# API VIEWS
# =====================================

class SaldoAtualAPIView(APIView, PermissaoAcaoMixin):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        saldo_caixa = self._calcular_saldo_caixa()
        saldo_bancos = self._calcular_saldo_bancos()
        
        return Response({
            'saldo_caixa': saldo_caixa,
            'saldo_bancos': saldo_bancos,
            'saldo_total': saldo_caixa + saldo_bancos
        })
    
    def _calcular_saldo_caixa(self):
        return MovimentoCaixa.objects.aggregate(
            saldo=Sum('valor')
        )['saldo'] or 0
    
    def _calcular_saldo_bancos(self):
        return MovimentacaoFinanceira.objects.aggregate(
            saldo=Sum('valor')
        )['saldo'] or 0


class ProjecaoFluxoAPIView(APIView, PermissaoAcaoMixin):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        # Implementar projeção de fluxo de caixa
        return Response({
            'projecao_30_dias': 0,
            'projecao_60_dias': 0,
            'projecao_90_dias': 0
        })

class IndicadoresFinanceirosAPIView(APIView, PermissaoAcaoMixin):
    acao_requerida = 'acessar_financeiro'
    def get(self, request):
        # Calcular indicadores financeiros
        return Response({
            'liquidez_corrente': 0,
            'endividamento': 0,
            'rentabilidade': 0,
            'margem_liquida': 0
        })





