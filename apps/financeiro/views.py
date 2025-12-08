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
from decimal import Decimal
import json
import csv
from rest_framework import viewsets
from jsonschema import ValidationError
from apps.clientes.models import Cliente
from apps.core.models import Empresa
from apps.core.views import BaseMPAView
from apps.financeiro.api.serializers import CategoriaFinanceiraSerializer, LancamentoFinanceiroSerializer
from apps.fornecedores.models import Fornecedor
from apps.vendas.models import Venda
from .models import (
    ConciliacaoBancaria, ContaReceber, ContaPagar, FluxoCaixa, LancamentoFinanceiro, CategoriaFinanceira,
    CentroCusto, ContaBancaria, MovimentacaoFinanceira, MovimentoCaixa,
    ImpostoTributo, OrcamentoFinanceiro, PlanoContas
)
from .forms import (
    ContaReceberForm, ContaPagarForm, ImpostoTributoForm, LancamentoFinanceiroForm,
    CategoriaFinanceiraForm, CentroCustoForm, MovimentoCaixaForm
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
from .models import PlanoContas
from .forms import PlanoContasForm
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.http import HttpResponseForbidden




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
                return redirect(reverse_lazy('core:dashboard'))

            if acao_requerida:
                if not funcionario.pode_realizar_acao(acao_requerida):
                    messages.error(
                        request,
                        f"Acesso negado. O seu cargo não permite realizar a ação de '{acao_requerida}'."
                    )
                    return redirect(reverse_lazy('core:dashboard'))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator





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
            empresa=empresa,
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

class PlanoContasListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = PlanoContas
    template_name = 'financeiro/plano_contas/lista.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return PlanoContas.objects.filter(
            empresa=self.request.user.empresa
        ).select_related('conta_pai').order_by('codigo')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Organizar contas por hierarquia
        contas_hierarquia = {}
        for conta in context['contas']:
            nivel = conta.nivel
            if nivel not in contas_hierarquia:
                contas_hierarquia[nivel] = []
            contas_hierarquia[nivel].append(conta)
        
        context['contas_hierarquia'] = contas_hierarquia
        return context

class PlanoContasCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = PlanoContas
    template_name = 'financeiro/plano_contas/form.html'
    fields = [
        'codigo', 'nome', 'descricao', 'conta_pai', 'tipo_conta',
        'natureza', 'aceita_lancamento', 'ativa', 'ordem'
    ]
    success_url = reverse_lazy('financeiro:plano_contas_lista')
    
    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        
        # Calcular nível baseado na conta pai
        if form.instance.conta_pai:
            form.instance.nivel = form.instance.conta_pai.nivel + 1
        else:
            form.instance.nivel = 1
        
        messages.success(self.request, 'Conta criada com sucesso!')
        return super().form_valid(form)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filtrar contas pai pela empresa
        form.fields['conta_pai'].queryset = PlanoContas.objects.filter(
            empresa=self.request.user.empresa
        )
        return form

class PlanoContasUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = PlanoContas
    template_name = 'financeiro/plano_contas/form.html'
    fields = [
        'codigo', 'nome', 'descricao', 'conta_pai', 'tipo_conta',
        'natureza', 'aceita_lancamento', 'ativa', 'ordem'
    ]
    success_url = reverse_lazy('financeiro:plano_contas_lista')
    
    def form_valid(self, form):
        # Recalcular nível se conta pai mudou
        if form.instance.conta_pai:
            form.instance.nivel = form.instance.conta_pai.nivel + 1
        else:
            form.instance.nivel = 1
        
        messages.success(self.request, 'Conta atualizada com sucesso!')
        return super().form_valid(form)

class PlanoContasDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = PlanoContas
    template_name = 'financeiro/plano_contas/detail.html'
    context_object_name = 'conta'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Contas filhas
        context['contas_filhas'] = self.object.contas_filhas.all()
        
        # Movimentações recentes
        context['movimentacoes_recentes'] = MovimentacaoFinanceira.objects.filter(
            plano_contas=self.object
        ).select_related('conta_bancaria').order_by('-data_movimentacao')[:10]
        
        # Totais do mês
        hoje = date.today()
        inicio_mes = hoje.replace(day=1)
        
        movimentacoes_mes = MovimentacaoFinanceira.objects.filter(
            plano_contas=self.object,
            data_movimentacao__range=[inicio_mes, hoje],
            confirmada=True
        )
        
        context['total_entradas_mes'] = movimentacoes_mes.filter(
            tipo_movimentacao='entrada'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        context['total_saidas_mes'] = movimentacoes_mes.filter(
            tipo_movimentacao='saida'
        ).aggregate(total=Sum('valor'))['total'] or 0
        
        return context

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
        queryset = MovimentacaoFinanceira.objects.filter(
            empresa=self.request.user.empresa
        ).select_related(
            'conta_bancaria', 'plano_contas', 'centro_custo',
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
            empresa=self.request.user.empresa, ativa=True
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
        'plano_contas', 'centro_custo', 'fornecedor', 'cliente',
        'descricao', 'observacoes', 'numero_cheque', 'banco_cheque',
        'emissor_cheque'
    ]
    success_url = reverse_lazy('financeiro:movimentacao_lista')
    
    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        form.instance.usuario_responsavel = self.request.user
        
        messages.success(self.request, 'Movimentação criada com sucesso!')
        return super().form_valid(form)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        empresa = self.request.user.empresa
        
        # Filtrar por empresa
        form.fields['conta_bancaria'].queryset = ContaBancaria.objects.filter(
            empresa=empresa, ativa=True
        )
        form.fields['conta_destino'].queryset = ContaBancaria.objects.filter(
            empresa=empresa, ativa=True
        )
        form.fields['plano_contas'].queryset = PlanoContas.objects.filter(
            empresa=empresa, ativa=True, aceita_lancamento=True
        )
        form.fields['centro_custo'].queryset = CentroCusto.objects.filter(
            empresa=empresa, ativo=True
        )
        form.fields['fornecedor'].queryset = Fornecedor.objects.filter(
            empresa=empresa, ativo=True
        )
        form.fields['cliente'].queryset = Cliente.objects.filter(
            empresa=empresa, ativo=True
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
        queryset = FluxoCaixa.objects.filter(
            empresa=self.request.user.empresa
        ).select_related('conta_bancaria', 'centro_custo').order_by('data_referencia')
        
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
        form.instance.empresa = self.request.user.empresa
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
            empresa=request.user.empresa,
            data_referencia__range=[data_inicio, data_fim]
        ).delete()
        
        contador = 0
        
        # Contas a receber em aberto
        contas_receber = ContaReceber.objects.filter(
            empresa=request.user.empresa,
            status__in=['aberta', 'vencida'],
            data_vencimento__range=[data_inicio, data_fim]
        )
        
        for conta in contas_receber:
            FluxoCaixa.objects.create(
                empresa=request.user.empresa,
                data_referencia=conta.data_vencimento,
                tipo='entrada',
                valor_previsto=conta.valor_saldo,
                categoria='Recebimento de Clientes',
                descricao=f"Recebimento: {conta.descricao}",
                conta_bancaria=ContaBancaria.objects.filter(
                    empresa=request.user.empresa, conta_principal=True
                ).first(),
                conta_receber=conta
            )
            contador += 1
        
        # Contas a pagar em aberto
        contas_pagar = ContaPagar.objects.filter(
            empresa=request.user.empresa,
            status__in=['aberta', 'vencida'],
            data_vencimento__range=[data_inicio, data_fim]
        )
        
        for conta in contas_pagar:
            FluxoCaixa.objects.create(
                empresa=request.user.empresa,
                data_referencia=conta.data_vencimento,
                tipo='saida',
                valor_previsto=conta.valor_saldo,
                categoria='Pagamento a Fornecedores',
                descricao=f"Pagamento: {conta.descricao}",
                conta_bancaria=ContaBancaria.objects.filter(
                    empresa=request.user.empresa, conta_principal=True
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
        return ConciliacaoBancaria.objects.filter(
            conta_bancaria__empresa=self.request.user.empresa
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
            empresa=self.request.user.empresa, ativa=True
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

class OrcamentoFinanceiroListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = OrcamentoFinanceiro
    template_name = 'financeiro/orcamento/lista.html'
    context_object_name = 'orcamentos'
    
    def get_queryset(self):
        ano = int(self.request.GET.get('ano', date.today().year))
        mes = self.request.GET.get('mes')
        
        queryset = OrcamentoFinanceiro.objects.filter(
            empresa=self.request.user.empresa,
            ano=ano
        ).select_related('plano_contas', 'centro_custo')
        
        if mes:
            queryset = queryset.filter(mes=int(mes))
        
        return queryset.order_by('mes', 'plano_contas__codigo')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        ano = int(self.request.GET.get('ano', date.today().year))
        context['ano_selecionado'] = ano
        context['anos_disponiveis'] = range(ano - 2, ano + 3)
        
        # Totais por mês
        orcamentos_ano = self.get_queryset()
        
        context['resumo_mensal'] = {}
        for mes in range(1, 13):
            orcamentos_mes = orcamentos_ano.filter(mes=mes)
            
            receitas = orcamentos_mes.filter(tipo='receita').aggregate(
                orcado=Sum('valor_orcado'),
                realizado=Sum('valor_realizado')
            )
            
            despesas = orcamentos_mes.filter(tipo='despesa').aggregate(
                orcado=Sum('valor_orcado'),
                realizado=Sum('valor_realizado')
            )
            
            context['resumo_mensal'][mes] = {
                'receitas_orcadas': receitas['orcado'] or 0,
                'receitas_realizadas': receitas['realizado'] or 0,
                'despesas_orcadas': despesas['orcado'] or 0,
                'despesas_realizadas': despesas['realizado'] or 0,
            }
        
        return context

class OrcamentoFinanceiroCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = OrcamentoFinanceiro
    template_name = 'financeiro/orcamento/form.html'
    fields = [
        'ano', 'mes', 'tipo', 'plano_contas', 'centro_custo',
        'valor_orcado', 'justificativa_variacao'
    ]
    success_url = reverse_lazy('financeiro:orcamento_lista')
    
    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        messages.success(self.request, 'Orçamento criado com sucesso!')
        return super().form_valid(form)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        empresa = self.request.user.empresa
        
        form.fields['plano_contas'].queryset = PlanoContas.objects.filter(
            empresa=empresa, ativa=True, aceita_lancamento=True
        )
        form.fields['centro_custo'].queryset = CentroCusto.objects.filter(
            empresa=empresa, ativo=True
        )
        
        return form

class OrcamentoFinanceiroUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = OrcamentoFinanceiro
    template_name = 'financeiro/orcamento/form.html'
    fields = [
        'valor_orcado', 'justificativa_variacao'
    ]
    success_url = reverse_lazy('financeiro:orcamento_lista')

class AtualizarOrcamentoRealizadoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request):
        """Atualiza valores realizados de todos os orçamentos"""
        ano = int(request.POST.get('ano', date.today().year))
        mes = request.POST.get('mes')
        
        orcamentos = OrcamentoFinanceiro.objects.filter(
            empresa=request.user.empresa,
            ano=ano
        )
        
        if mes:
            orcamentos = orcamentos.filter(mes=int(mes))
        
        contador = 0
        for orcamento in orcamentos:
            orcamento.atualizar_realizado()
            contador += 1
        
        messages.success(request, f'{contador} orçamentos atualizados!')
        return redirect('financeiro:orcamento_lista')

class CopiarOrcamentoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request):
        """Copia orçamento de um ano para outro"""
        ano_origem = int(request.POST.get('ano_origem'))
        ano_destino = int(request.POST.get('ano_destino'))
        fator_reajuste = Decimal(request.POST.get('fator_reajuste', '1.0'))
        
        if ano_origem == ano_destino:
            messages.error(request, 'Anos de origem e destino devem ser diferentes')
            return redirect('financeiro:orcamento_lista')
        
        # Buscar orçamentos do ano origem
        orcamentos_origem = OrcamentoFinanceiro.objects.filter(
            empresa=request.user.empresa,
            ano=ano_origem
        )
        
        # Deletar orçamentos existentes do ano destino
        OrcamentoFinanceiro.objects.filter(
            empresa=request.user.empresa,
            ano=ano_destino
        ).delete()
        
        contador = 0
        for orcamento in orcamentos_origem:
            OrcamentoFinanceiro.objects.create(
                empresa=orcamento.empresa,
                ano=ano_destino,
                mes=orcamento.mes,
                tipo=orcamento.tipo,
                plano_contas=orcamento.plano_contas,
                centro_custo=orcamento.centro_custo,
                valor_orcado=orcamento.valor_orcado * fator_reajuste
            )
            contador += 1
        
        messages.success(
            request, 
            f'{contador} orçamentos copiados de {ano_origem} para {ano_destino} '
            f'com reajuste de {((fator_reajuste - 1) * 100):.1f}%'
        )
        return redirect('financeiro:orcamento_lista')

# =====================================
# CONTA BANCÁRIA COMPLETA
# =====================================

class ContaBancariaListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = ContaBancaria
    template_name = 'financeiro/conta_bancaria/lista.html'
    context_object_name = 'contas'
    
    def get_queryset(self):
        return ContaBancaria.objects.filter(
            empresa=self.request.user.empresa
        ).order_by('-conta_principal', 'banco', 'conta')
    
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
        form.instance.empresa = self.request.user.empresa
        form.instance.saldo_atual = form.instance.saldo_inicial
        
        # Se marcada como principal, desmarcar outras
        if form.instance.conta_principal:
            ContaBancaria.objects.filter(
                empresa=self.request.user.empresa,
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
                empresa=self.request.user.empresa,
                conta_principal=True
            ).exclude(id=form.instance.id).update(conta_principal=False)
        
        messages.success(self.request, 'Conta bancária atualizada com sucesso!')
        return super().form_valid(form)
    
# =====================================
# DASHBOARD FINANCEIRO
# =====================================
from datetime import date
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum

# IMPORTAÇÕES: Certifique-se que ContaPagar, ContaReceber, MovimentoCaixa, MovimentacaoFinanceira e LancamentoFinanceiro 
# estão corretamente importados no topo do seu views.py





from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone
from datetime import date, timedelta
import json
from decimal import Decimal

class FinanceiroDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa  # ou self.get_empresa()
        hoje = date.today()
        inicio_mes = hoje.replace(day=1)
        
        # ====== RESUMO FINANCEIRO ======
        context['total_receber'] = ContaReceber.objects.filter(
            empresa=empresa,
            status__in=['aberta', 'vencida']
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        context['total_pagar'] = ContaPagar.objects.filter(
            empresa=empresa,
            status__in=['aberta', 'vencida']
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        context['saldo_caixa'] = self._calcular_saldo_caixa(empresa)
        context['saldo_bancos'] = self._calcular_saldo_bancos(empresa)
        
        # ====== CONTAS VENCIDAS ======
        context['contas_receber_vencidas'] = ContaReceber.objects.filter(
            empresa=empresa,
            status__in=['aberta', 'vencida'],
            data_vencimento__lt=hoje
        ).count()
        
        context['contas_pagar_vencidas'] = ContaPagar.objects.filter(
            empresa=empresa,
            status__in=['aberta', 'vencida'],
            data_vencimento__lt=hoje
        ).count()
        
        # ====== RECEITAS E DESPESAS DO MÊS ======
        # CORRIGIDO: Usar plano_contas__tipo_conta em vez de tipo
        context['receitas_mes'] = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_contas__tipo_conta='receita',  # CORRIGIDO
            data_lancamento__gte=inicio_mes,
            data_lancamento__lte=hoje
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        context['despesas_mes'] = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_contas__tipo_conta='despesa',  # CORRIGIDO
            data_lancamento__gte=inicio_mes,
            data_lancamento__lte=hoje
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        
        # ====== CONTAS VENCENDO (próximos 7 dias) ======
        proximos_7_dias = hoje + timedelta(days=7)
        
        context['contas_receber_vencendo'] = ContaReceber.objects.filter(
            empresa=empresa,
            status='aberta',
            data_vencimento__gte=hoje,
            data_vencimento__lte=proximos_7_dias
        ).count()
        
        context['contas_pagar_vencendo'] = ContaPagar.objects.filter(
            empresa=empresa,
            status='aberta',
            data_vencimento__gte=hoje,
            data_vencimento__lte=proximos_7_dias
        ).count()
        
        # ====== IMPOSTOS ======
        context['impostos_pendentes'] = ImpostoTributo.objects.filter(
            empresa=empresa,
            situacao__in=['pendente', 'calculado', 'vencido']
        ).count()
        
        context['impostos_valor_devido'] = ImpostoTributo.objects.filter(
            empresa=empresa,
            situacao__in=['calculado', 'vencido']
        ).aggregate(total=Sum('valor_devido'))['total'] or Decimal('0.00')

        # ====== VENDAS DO MÊS ======
        context['total_vendas_mes'] = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=inicio_mes,
            data_venda__lte=hoje,
            status='finalizada'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')

        # ====== CÁLCULOS ======
        context['lucro_mes'] = context['total_vendas_mes'] - context['despesas_mes']
        context['liquidez'] = context['saldo_caixa'] + context['saldo_bancos']
        context['saldo_liquido'] = context['total_receber'] - context['total_pagar']

        
        # ====== CÁLCULOS ======
        context['lucro_mes'] = context['receitas_mes'] - context['despesas_mes']
        context['liquidez'] = context['saldo_caixa'] + context['saldo_bancos']
        context['saldo_liquido'] = context['total_receber'] - context['total_pagar']
        
        # ====== DADOS PARA GRÁFICOS ======
        context['dados_fluxo_caixa'] = json.dumps(self._get_dados_fluxo_caixa(empresa))
        context['receitas_por_categoria'] = json.dumps(self._get_receitas_por_categoria(empresa))
        context['despesas_por_categoria'] = json.dumps(self._get_despesas_por_categoria(empresa))
        context['evolucao_saldos'] = json.dumps(self._get_evolucao_saldos(empresa))
        context['contas_vencimento'] = json.dumps(self._get_contas_por_vencimento(empresa))
        
        return context
    
    def _calcular_saldo_caixa(self, empresa):
        """Calcula saldo atual do caixa"""
        return MovimentoCaixa.objects.filter(
            empresa=empresa,
            confirmado=True
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
    
    def _calcular_saldo_bancos(self, empresa):
        """Calcula saldo total das contas bancárias"""
        return ContaBancaria.objects.filter(
            empresa=empresa,
            ativa=True
        ).aggregate(total=Sum('saldo_atual'))['total'] or Decimal('0.00')
    
    def _get_dados_fluxo_caixa(self, empresa):
        """Dados para gráfico de fluxo de caixa (próximos 30 dias)"""
        hoje = date.today()
        dados = {'labels': [], 'entradas': [], 'saidas': [], 'saldo_acumulado': []}
        
        saldo_atual = self._calcular_saldo_caixa(empresa) + self._calcular_saldo_bancos(empresa)
        
        for i in range(30):
            data_ref = hoje + timedelta(days=i)
            
            # Entradas previstas (contas a receber)
            entradas = ContaReceber.objects.filter(
                empresa=empresa,
                data_vencimento=data_ref,
                status='aberta'
            ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
            
            # Saídas previstas (contas a pagar)
            saidas = ContaPagar.objects.filter(
                empresa=empresa,
                data_vencimento=data_ref,
                status='aberta'
            ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
            
            saldo_atual = saldo_atual + entradas - saidas
            
            dados['labels'].append(data_ref.strftime('%d/%m'))
            dados['entradas'].append(float(entradas))
            dados['saidas'].append(float(saidas))
            dados['saldo_acumulado'].append(float(saldo_atual))
        
        return dados
    
    def _get_receitas_por_categoria(self, empresa):
        """Dados para gráfico de receitas por categoria (mês atual)"""
        inicio_mes = date.today().replace(day=1)
        
        receitas = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_contas__tipo_conta='receita',
            data_lancamento__gte=inicio_mes
        ).values(
            'plano_contas__nome'
        ).annotate(
            total=Sum('valor')
        ).order_by('-total')
        
        return {
            'labels': [item['plano_contas__nome'] for item in receitas],
            'valores': [float(item['total']) for item in receitas]
        }
    
    def _get_despesas_por_categoria(self, empresa):
        """Dados para gráfico de despesas por categoria (mês atual)"""
        inicio_mes = date.today().replace(day=1)
        
        despesas = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_contas__tipo_conta='despesa',
            data_lancamento__gte=inicio_mes
        ).values(
            'plano_contas__nome'
        ).annotate(
            total=Sum('valor')
        ).order_by('-total')
        
        return {
            'labels': [item['plano_contas__nome'] for item in despesas],
            'valores': [float(item['total']) for item in despesas]
        }
    
    def _get_evolucao_saldos(self, empresa):
        """Evolução dos saldos bancários (últimos 12 meses)"""
        dados = {'labels': [], 'valores': []}
        
        for i in range(12):
            if i == 0:
                mes_ref = date.today().replace(day=1)
            else:
                mes_anterior = mes_ref - timedelta(days=1)
                mes_ref = mes_anterior.replace(day=1)
            
            fim_mes = mes_ref.replace(day=28)  # Aproximação
            
            # Calcular saldo no final do mês
            movimentacoes = MovimentacaoFinanceira.objects.filter(
                empresa=empresa,
                data_movimentacao__lte=fim_mes,
                confirmada=True
            )
            
            entradas = movimentacoes.filter(tipo_movimentacao='entrada').aggregate(
                total=Sum('valor')
            )['total'] or Decimal('0.00')
            
            saidas = movimentacoes.filter(tipo_movimentacao='saida').aggregate(
                total=Sum('valor')
            )['total'] or Decimal('0.00')
            
            saldo_mes = entradas - saidas
            
            dados['labels'].insert(0, mes_ref.strftime('%b/%Y'))
            dados['valores'].insert(0, float(saldo_mes))
        
        return dados
    
    def _get_contas_por_vencimento(self, empresa):
        """Distribuição de contas por status de vencimento"""
        hoje = date.today()
        
        # Contas a receber
        receber_aberta = ContaReceber.objects.filter(
            empresa=empresa, status='aberta', data_vencimento__gte=hoje
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        receber_vencida = ContaReceber.objects.filter(
            empresa=empresa, status='vencida'
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        # Contas a pagar
        pagar_aberta = ContaPagar.objects.filter(
            empresa=empresa, status='aberta', data_vencimento__gte=hoje
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        pagar_vencida = ContaPagar.objects.filter(
            empresa=empresa, status='vencida'
        ).aggregate(total=Sum('valor_saldo'))['total'] or Decimal('0.00')
        
        return {
            'labels': ['A Receber em Dia', 'A Receber Vencidas', 'A Pagar em Dia', 'A Pagar Vencidas'],
            'valores': [float(receber_aberta), float(receber_vencida), float(pagar_aberta), float(pagar_vencida)],
            'cores': ['#10B981', '#EF4444', '#F59E0B', '#DC2626']
        }


# views.py
from django.views.generic import ListView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from .models import FluxoCaixa
from .forms import FluxoCaixaForm
from datetime import datetime, date

class FluxoCaixaView(LoginRequiredMixin, ListView):
    model = FluxoCaixa
    template_name = 'financeiro/fluxo_caixa/lista.html'
    context_object_name = 'fluxos'
    paginate_by = 25

    def get_queryset(self):
        empresa = self.request.user.empresa
        qs = FluxoCaixa.objects.filter(empresa=empresa)
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
        form.instance.empresa = self.request.user.empresa
        return super().form_valid(form)


class FluxoCaixaUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = FluxoCaixa
    form_class = FluxoCaixaForm
    template_name = 'financeiro/fluxo_caixa/form.html'
    success_url = reverse_lazy('financeiro:fluxo_caixa')



class DREView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
   acao_requerida = 'acessar_financeiro'
   template_name = 'financeiro/dre.html'
    
   def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Período
        mes = int(self.request.GET.get('mes', date.today().month))
        ano = int(self.request.GET.get('ano', date.today().year))
        
        inicio_periodo = date(ano, mes, 1)
        if mes == 12:
            fim_periodo = date(ano + 1, 1, 1) - timedelta(days=1)
        else:
            fim_periodo = date(ano, mes + 1, 1) - timedelta(days=1)
        
        # Receitas
        receitas = LancamentoFinanceiro.objects.filter(
            tipo='entrada',
            data__range=[inicio_periodo, fim_periodo]
        ).values('categoria__nome').annotate(
            total=Sum('valor')
        )
        
        # Despesas
        despesas = LancamentoFinanceiro.objects.filter(
            tipo='saida',
            data__range=[inicio_periodo, fim_periodo]
        ).values('categoria__nome').annotate(
            total=Sum('valor')
        )
        
        total_receitas = sum(item['total'] for item in receitas)
        total_despesas = sum(item['total'] for item in despesas)
        
        context.update({
            'mes': mes,
            'ano': ano,
            'receitas': receitas,
            'despesas': despesas,
            'total_receitas': total_receitas,
            'total_despesas': total_despesas,
            'resultado': total_receitas - total_despesas
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
    acao_requerida = 'acessar_financeiro'
    model = ContaReceber
    template_name = 'financeiro/conta_receber/detail.html'
    context_object_name = 'conta'

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
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaReceber, pk=pk)
        
        valor_recebido = Decimal(request.POST.get('valor_recebido', conta.valor))
        data_recebimento = request.POST.get('data_recebimento', date.today())
        forma_pagamento = request.POST.get('forma_pagamento')
        
        # Atualizar conta
        conta.valor_pago = valor_recebido
        conta.data_pagamento = data_recebimento
        conta.forma_pagamento = forma_pagamento
        conta.status = 'paga'
        conta.save()
        
        # Criar lançamento financeiro
        LancamentoFinanceiro.objects.create(
            tipo='receita',
            categoria=conta.categoria,
            descricao=f'Recebimento - {conta.descricao}',
            valor=valor_recebido,
            data_lancamento=data_recebimento,
            conta_bancaria=conta.conta_bancaria
        )
        
        messages.success(request, 'Conta recebida com sucesso!')
        return redirect('financeiro:conta_receber_detail', pk=pk)

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

class ContaPagarDetailView(LoginRequiredMixin, DetailView):
    model = ContaPagar
    template_name = 'financeiro/conta_pagar/detail.html'
    context_object_name = 'conta'

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
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaPagar, pk=pk)
        
        valor_pago = Decimal(request.POST.get('valor_pago', conta.valor))
        data_pagamento = request.POST.get('data_pagamento', date.today())
        forma_pagamento = request.POST.get('forma_pagamento')
        
        # Atualizar conta
        conta.valor_pago = valor_pago
        conta.data_pagamento = data_pagamento
        conta.forma_pagamento = forma_pagamento
        conta.status = 'paga'
        conta.save()
        
        # Criar lançamento financeiro
        LancamentoFinanceiro.objects.create(
            tipo='despesa',
            categoria=conta.categoria,
            descricao=f'Pagamento - {conta.descricao}',
            valor=valor_pago,
            data_lancamento=data_pagamento,
            conta_bancaria=conta.conta_bancaria
        )
        
        messages.success(request, 'Conta paga com sucesso!')
        return redirect('financeiro:conta_pagar_detail', pk=pk)

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

class LancamentoListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    template_name = 'financeiro/lancamento/lista.html'
    context_object_name = 'lancamentos'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtros
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        categoria = self.request.GET.get('categoria')
        if categoria:
            queryset = queryset.filter(categoria_id=categoria)
        
        return queryset.select_related('categoria').order_by('-data')

class LancamentoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    template_name = 'financeiro/lancamento/detail.html'
    context_object_name = 'lancamento'

class LancamentoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    form_class = LancamentoFinanceiroForm
    template_name = 'financeiro/lancamento/form.html'
    success_url = reverse_lazy('financeiro:lancamento_lista')

class EstornarLancamentoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        lancamento = get_object_or_404(LancamentoFinanceiro, pk=pk)
        
        # Criar lançamento de estorno
        LancamentoFinanceiro.objects.create(
            tipo='receita' if lancamento.tipo == 'despesa' else 'despesa',
            categoria=lancamento.categoria,
            descricao=f'Estorno - {lancamento.descricao}',
            valor=lancamento.valor,
            data_lancamento=date.today(),
            observacoes=f'Estorno do lançamento {lancamento.id}'
        )
        
        # Marcar como estornado
        lancamento.estornado = True
        lancamento.save()
        
        messages.success(request, 'Lançamento estornado com sucesso!')
        return redirect('financeiro:lancamento_detail', pk=pk)

class ReceitasView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    template_name = 'financeiro/lancamento/receitas.html'
    context_object_name = 'receitas'
    
    def get_queryset(self):
        return LancamentoFinanceiro.objects.filter(
            tipo='receita'
        ).order_by('-data_lancamento')

class DespesasView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    template_name = 'financeiro/lancamento/despesas.html'
    context_object_name = 'despesas'
    
    def get_queryset(self):
        return LancamentoFinanceiro.objects.filter(
            tipo='despesa'
        ).order_by('-data_lancamento')

class TransferenciasView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = LancamentoFinanceiro
    template_name = 'financeiro/lancamento/transferencias.html'
    context_object_name = 'transferencias'
    
    def get_queryset(self):
        return LancamentoFinanceiro.objects.filter(
            tipo='transferencia'
        ).order_by('-data')

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
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaBancaria, pk=pk)
        valor = Decimal(request.POST.get('valor'))
        descricao = request.POST.get('descricao')
        
        # Criar movimento bancário
        MovimentacaoFinanceira.objects.create(
            conta_bancaria=conta,
            tipo_movimento='credito',
            valor=valor,
            descricao=descricao,
            data_movimento=date.today()
        )
        
        messages.success(request, 'Depósito realizado com sucesso!')
        return redirect('financeiro:detail', pk=pk)

class SaqueBancarioView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        conta = get_object_or_404(ContaBancaria, pk=pk)
        valor = Decimal(request.POST.get('valor'))
        descricao = request.POST.get('descricao')
        
        # Criar movimento bancário
        MovimentacaoFinanceira.objects.create(
            conta_bancaria=conta,
            tipo_movimento='debito',
            valor=valor,
            descricao=descricao,
            data_movimento=date.today()
        )
        
        messages.success(request, 'Saque realizado com sucesso!')
        return redirect('financeiro:banco_detail', pk=pk)

class TransferenciaBancariaView(LoginRequiredMixin, PermissaoAcaoMixin, FormView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/banco/transferencia.html'
    
    def post(self, request, pk):
        conta_origem = get_object_or_404(ContaBancaria, pk=pk)
        conta_destino_id = request.POST.get('conta_destino')
        conta_destino = get_object_or_404(ContaBancaria, pk=conta_destino_id)
        valor = Decimal(request.POST.get('valor'))
        
        # Débito na conta origem
        MovimentacaoFinanceira.objects.create(
            conta_bancaria=conta_origem,
            tipo_movimento='debito',
            valor=valor,
            descricao=f'Transferência para {conta_destino.nome}',
            data_movimento=date.today()
        )
        
        # Crédito na conta destino
        MovimentacaoFinanceira.objects.create(
            conta_bancaria=conta_destino,
            tipo_movimento='credito',
            valor=valor,
            descricao=f'Transferência de {conta_origem.nome}',
            data_movimento=date.today()
        )
        
        messages.success(request, 'Transferência realizada com sucesso!')
        return redirect('financeiro:banco_detail', pk=pk)

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

class CategoriaFinanceiraListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'acessar_financeiro'
    model = CategoriaFinanceira
    template_name = 'financeiro/categoria/lista.html'
    context_object_name = 'categorias'

class CategoriaFinanceiraCreateView(LoginRequiredMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = CategoriaFinanceira
    form_class = CategoriaFinanceiraForm
    template_name = 'financeiro/categoria/form.html'
    success_url = reverse_lazy('financeiro:categoria_lista')

class CategoriaFinanceiraUpdateView(LoginRequiredMixin, UpdateView):
    acao_requerida = 'acessar_financeiro'
    model = CategoriaFinanceira
    form_class = CategoriaFinanceiraForm
    template_name = 'financeiro/categoria/form.html'
    success_url = reverse_lazy('financeiro:categoria_lista')

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

class OrcamentoFinanceiroView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_financeiro'
    template_name = 'financeiro/planejamento/orcamento.html'

class NovoOrcamentoView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = OrcamentoFinanceiro
    template_name = 'financeiro/planejamento/novo_orcamento.html'
    fields = '__all__'

class AcompanharOrcamentoView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = OrcamentoFinanceiro
    template_name = 'financeiro/planejamento/acompanhar.html'

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
        empresa = self.request.user.empresa
        return ImpostoTributo.objects.filter(empresa=empresa).order_by('-ano_referencia', '-mes_referencia')


class ImpostoTributoDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    template_name = 'tributacao/imposto_detail.html'
    context_object_name = 'imposto'


class ImpostoTributoCreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'acessar_financeiro'
    model = ImpostoTributo
    form_class = ImpostoTributoForm
    template_name = 'tributacao/imposto_form.html'
    success_url = reverse_lazy('tributacao:imposto_list')

    def form_valid(self, form):
        imposto = form.save(commit=False)
        imposto.usuario_responsavel = self.request.user
        imposto.empresa = self.request.user.empresa
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
        imposto = get_object_or_404(ImpostoTributo, pk=pk, empresa=request.user.empresa)
        try:
            imposto.calcular_imposto_angola(forcar_recalculo=True)
            messages.success(request, 'Cálculo do imposto efetuado com sucesso.')
        except Exception as e:
            messages.error(request, f'Erro ao calcular imposto: {e}')
        return redirect('tributacao:imposto_detail', pk=imposto.pk)


logger = logging.getLogger(__name__)


class ImpostoPagarView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """
    View para efetuar o pagamento de um imposto via função pagar_imposto_agt().
    Integra com o módulo financeiro (movimentação de caixa ou pagamentos).
    """
    acao_requerida = 'acessar_financeiro'
    def post(self, request, pk):
        imposto = get_object_or_404(ImpostoTributo, pk=pk, empresa=request.user.empresa)
        try:
            with transaction.atomic():
                resultado = imposto.pagar_imposto_agt()
                # Aqui você pode adicionar integração real com o módulo financeiro:
                # exemplo:
                MovimentacaoFinanceira.objects.create(
                    empresa=request.user.empresa,
                    valor=imposto.valor_devido,
                    descricao=f"Pagamento do imposto {imposto.nome}",
                    tipo='saída',
                    categoria='imposto',
                    usuario=request.user,
                )

                messages.success(request, resultado["mensagem"])
                logger.info(f"Pagamento AGT concluído: {imposto.nome} ({imposto.id}) - {resultado['mensagem']}")
        except Exception as e:
            logger.error(f"Erro ao pagar imposto {imposto.id}: {str(e)}", exc_info=True)
            messages.error(request, f"Falha ao pagar imposto: {e}")

        return redirect('tributacao:imposto_detail', pk=imposto.pk)
    


def pagar_imposto(request, empresa_id):
    empresa = get_object_or_404('core.Empresa', id=empresa_id)
    impostos = empresa.impostos_angola.all()
    total = 0

    for imposto in impostos:
        if hasattr(imposto, 'pagar_imposto_agt'):
            imposto.pagar_imposto_agt()
            total += 1

    messages.success(request, f'{total} impostos pagos à AGT com sucesso.')
    return redirect('financeiro:detalhe_empresa', empresa_id=empresa_id)


@login_required
def estornar_imposto_view(request, pk):
    """View pública para usuários solicitarem estorno de imposto"""
    imposto = get_object_or_404(ImpostoTributo, pk=pk, empresa=request.user.empresa)

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

class LancamentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint para CRUD de lançamentos financeiros
    """
    queryset = LancamentoFinanceiro.objects.all()
    serializer_class = LancamentoFinanceiroSerializer


class CategoriaFinanceiraViewSet(viewsets.ModelViewSet):
    """
    API endpoint para CRUD de categorias financeiras
    """
    queryset = CategoriaFinanceira.objects.all()
    serializer_class = CategoriaFinanceiraSerializer




@login_required
@permissao_acao_required(acao_requerida='acessar_financeiro')
def lista_planos(request):
    planos = PlanoContas.objects.filter(empresa=request.user.empresa)
    return render(request, 'financeiro/plano_contas/lista.html', {'planos': planos})

@login_required
@permissao_acao_required(acao_requerida='acessar_financeiro')
def criar_plano(request):
    if request.method == 'POST':
        form = PlanoContasForm(request.POST)
        if form.is_valid():
            plano = form.save(commit=False)
            plano.empresa = request.user.empresa
            # Definir nível automaticamente
            plano.nivel = (plano.conta_pai.nivel + 1) if plano.conta_pai else 1
            plano.save()
            messages.success(request, "Plano de contas criado com sucesso!")
            return redirect('financeiro:lista_planos')
    else:
        form = PlanoContasForm()
    return render(request, 'financeiro/plano_contas/form.html', {'form': form, 'titulo': 'Criar Plano de Contas'})

@login_required
@permissao_acao_required(acao_requerida='acessar_financeiro')
def editar_plano(request, pk):
    plano = get_object_or_404(PlanoContas, pk=pk, empresa=request.user.empresa)
    if request.method == 'POST':
        form = PlanoContasForm(request.POST, instance=plano)
        if form.is_valid():
            plano = form.save(commit=False)
            plano.nivel = (plano.conta_pai.nivel + 1) if plano.conta_pai else 1
            plano.save()
            messages.success(request, "Plano de contas atualizado!")
            return redirect('financeiro:lista_planos')
    else:
        form = PlanoContasForm(instance=plano)
    return render(request, 'financeiro/plano_contas/form.html', {'form': form, 'titulo': 'Editar Plano de Contas'})

@login_required
@permissao_acao_required(acao_requerida='acessar_financeiro')
def deletar_plano(request, pk):
    plano = get_object_or_404(PlanoContas, pk=pk, empresa=request.user.empresa)
    if request.method == 'POST':
        plano.delete()
        messages.success(request, "Plano de contas deletado!")
        return redirect('financeiro:lista_planos')
    return render(request, 'financeiro/plano_contas/confirm_delete.html', {'plano': plano})



