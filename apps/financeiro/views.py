# apps/financeiro/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, 
    TemplateView, FormView, View
)
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.db.models import Sum, Count, Q, Avg, F
from django.utils import timezone
from django.urls import reverse_lazy
from datetime import date, timedelta, datetime
from decimal import Decimal, InvalidOperation
import json
import csv
from rest_framework import viewsets
from jsonschema import ValidationError
from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.core.views import BaseMPAView
from apps.fornecedores.models import Fornecedor
from apps.vendas.models import Venda
from .models import (
    ConciliacaoBancaria, ContaReceber, ContaPagar, FluxoCaixa,
    CentroCusto, ContaBancaria, MovimentacaoFinanceira, MovimentoCaixa,
    ImpostoTributo
)
from .forms import (
    ContaReceberForm, ContaPagarForm, ImpostoTributoForm, CentroCustoForm, MovimentoCaixaForm
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
# PLANO DE CONTAS
# =====================================




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
        ).select_related('plano_contas').order_by('-data_movimentacao')[:20]
        
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



class ContaReceberDetailView(DetailView):
    """Integre get_context_data desta classe na ContaReceberDetailView existente."""
    model = ContaReceber
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




class ParcelarContaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
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


class NegociarContaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
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
    model = ContaPagar
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

class PagamentoLoteView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
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
    template_name = "financeiro/banco/form.html"  # Template para edição
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
                empresa=self.object.empresa, conta_principal=True
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

class AbrirCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
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

class FecharCaixaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
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

class CartaoListView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/cartao/lista.html'

class VendasCartaoView(LoginRequiredMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/cartao/vendas.html'

class RecebimentosCartaoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/cartao/recebimentos.html'

class TaxasCartaoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/cartao/taxas.html'

class ConciliacaoCartaoView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/cartao/conciliacao.html'

class TEFView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/tef/tef.html'

class TransacoesTEFView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/tef/transacoes.html'

class CancelarTEFView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        # Implementar cancelamento TEF
        messages.success(request, 'Transação TEF cancelada!')
        return redirect('financeiro:tef')

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
    model = ImpostoTributo
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
        return redirect("financeiro:detalhe_imposto", pk=imposto.pk)

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





