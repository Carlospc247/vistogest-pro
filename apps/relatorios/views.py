# apps/relatorios/views.py
from django.forms import CharField
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404, HttpResponseForbidden, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import transaction, connection
from django.db.models import Q, Sum, Count, F, Avg, Max, Min, Case, When, Value, Variance, StdDev
from django.db.models.functions import TruncDate, TruncHour, TruncMonth, TruncYear, TruncWeek, Cast
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User, Group, Permission
from django.core.mail import send_mail, EmailMessage
from django.core.cache import cache
from django.conf import settings
from django.core.management import call_command
from datetime import datetime, timedelta, date, time
from decimal import Decimal
import json
import logging
import csv
import io
import os
import subprocess
import calendar
import statistics
import pandas as pd
import numpy as np
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import zipfile
import shutil
from pathlib import Path
import tempfile
import openpyxl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import xml.etree.ElementTree as ET
from django.core.serializers import serialize
import xlsxwriter
from celery import shared_task
import csv
import json
import io
from openpyxl import Workbook
from weasyprint import HTML
from django.db.models import Sum, Count, Avg, F
from django.db.models.functions import ExtractHour
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, CreateView, DetailView, View, FormView, TemplateView
)
from django.db.models import Sum, Count, Avg, F
from django.db.models.functions import ExtractHour

from apps.analytics import models
from apps.compras.models import Compra, ItemCompra
from apps.vendas.api.serializers import VendaSerializer
import pandas as pd
from sklearn.cluster import KMeans
from statsmodels.tsa.api import SimpleExpSmoothing
from django.http import JsonResponse
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from .models import (
    LogAtividade, TipoRelatorio, RelatorioGerado, MetricaKPI, DashboardConfig,
    AnaliseVendas, AnaliseEstoque, AnaliseClientes, AlertaGerencial,
    TemplateRelatorio, Relatorio, AgendamentoRelatorio, LogRelatorio
)
from .forms import (
    TipoRelatorioForm, RelatorioGeradoForm, MetricaKPIForm,
    DashboardConfigForm, FiltroAnaliseVendasForm, FiltroAnaliseEstoqueForm,
    FiltroAnaliseClientesForm, AlertaGerencialForm, TemplateRelatorioForm,
    GerarRelatorioForm, AgendamentoRelatorioForm, ExportarRelatorioForm,
    FiltroRelatoriosForm
)
from .utils import (
    calcular_metricas_vendas, calcular_analise_abc_produtos,
    calcular_segmentacao_rfm_clientes, gerar_relatorio_pdf,
    gerar_relatorio_excel, gerar_relatorio_csv, processar_relatorio_assincrono,
    calcular_previsao_vendas, analisar_sazonalidade, calcular_tendencias,
    gerar_cubo_olap, executar_data_mining, calcular_correlacoes
)
from .tasks import processar_relatorio_task, enviar_relatorio_email_task
from apps.core.mixins import BaseViewMixin
from apps.vendas.models import Venda, ItemVenda, Orcamento
from apps.produtos.models import ControleVencimento, Produto, Categoria
from apps.clientes.models import Cliente, GrupoCliente
from apps.funcionarios.models import (
    AvaliacaoDesempenho, Capacitacao, Cargo, Departamento, FolhaPagamento, Funcionario, RegistroPonto, Ferias,
    Capacitacao, AvaliacaoDesempenho, Departamento
)
from apps.fornecedores.models import (
    Fornecedor, AvaliacaoFornecedor
)
from apps.financeiro.models import (
    ContaReceber, ContaPagar, LancamentoFinanceiro, MovimentacaoFinanceira, CentroCusto,
    PlanoContas
)
from apps.estoque.models import MovimentacaoEstoque, Inventario, AlertaEstoque
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, F, Q, Case, When, Value, DecimalField
from django.db.models.functions import TruncMonth, TruncDay
from django.views.generic import TemplateView
from datetime import datetime, date, timedelta
from django.contrib.auth.mixins import AccessMixin


logger = logging.getLogger(__name__)




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




class RelatoriosDashboardView(BaseViewMixin, TemplateView):

    def get_empresa(self):
        """Retorna a empresa associada ao usuário logado."""
        # Exemplo: se o modelo de usuário tem um campo empresa
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        usuario = self.request.user
        
        # Relatórios mais executados
        relatorios_populares = RelatorioGerado.objects.filter(
            empresa=empresa
        ).values(
            'tipo_relatorio__nome',
            'tipo_relatorio__categoria'
        ).annotate(
            total_execucoes=Count('id')
        ).order_by('-total_execucoes')[:10]
        
        # Relatórios recentes do usuário
        relatorios_recentes = RelatorioGerado.objects.filter(
            empresa=empresa,
            solicitante=usuario
        ).select_related('tipo_relatorio').order_by('-data_solicitacao')[:5]
        
        # Estatísticas gerais
        hoje = timezone.now().date()
        stats = {
            'total_relatorios': RelatorioGerado.objects.filter(empresa=empresa).count(),
            'relatorios_hoje': RelatorioGerado.objects.filter(
                empresa=empresa,
                data_solicitacao__date=hoje
            ).count(),
            'templates_ativos': TipoRelatorio.objects.filter(ativo=True).count(),
            'agendamentos_ativos': AgendamentoRelatorio.objects.filter(ativo=True).count(),
            'templates_ativos': TemplateRelatorio.objects.filter(ativo=True).count(),
            'relatorios_erro': RelatorioGerado.objects.filter(
                empresa=empresa,
                status='erro'
            ).count()
        }
        
        # Relatórios por categoria (últimos 30 dias)
        relatorios_por_categoria = RelatorioGerado.objects.filter(
            empresa=empresa,
            data_solicitacao__gte=hoje - timedelta(days=30)
        ).values(
            'tipo_relatorio__categoria'
        ).annotate(
            total=Count('id')
        ).order_by('-total')
        
        # KPIs em destaque (métricas importantes)
        kpis_destaque = self._obter_kpis_destaque(empresa)
        
        # Alertas ativos
        alertas_ativos = AlertaGerencial.objects.filter(
            empresa=empresa,
            ativo=True,
            data_referencia__gte=hoje
        ).order_by('-prioridade', '-created_at')[:5]
        
        # Relatórios agendados para hoje #empresa=empresa,
        agendamentos_hoje = AgendamentoRelatorio.objects.filter(
            
            ativo=True,
            frequencia=hoje
        ).order_by('frequencia')
        
        # Últimos acessos a relatórios #empresa=empresa,
        ultimos_acessos = LogRelatorio.objects.filter(
            
            acao='visualizacao'
        ).order_by('-timestamp')[:10]
        
        # Tempo médio de geração de relatórios
        tempo_medio_geracao = RelatorioGerado.objects.filter(
            empresa=empresa,
            status='concluido',
            tempo_processamento__isnull=False
        ).aggregate(Avg('tempo_processamento'))['tempo_processamento__avg']
        
        # Formatos mais utilizados
        formatos_populares = RelatorioGerado.objects.filter(
            empresa=empresa
        ).values('formato').annotate(
            total=Count('id')
        ).order_by('-total')[:5]
        
        context.update({
            'relatorios_populares': relatorios_populares,
            'relatorios_recentes': relatorios_recentes,
            'stats': stats,
            'relatorios_por_categoria': relatorios_por_categoria,
            'kpis_destaque': kpis_destaque,
            'alertas_ativos': alertas_ativos,
            'agendamentos_hoje': agendamentos_hoje,
            'ultimos_acessos': ultimos_acessos,
            'tempo_medio_geracao': tempo_medio_geracao,
            'formatos_populares': formatos_populares,
            'title': 'Dashboard de Relatórios'
        })
        
        return context
    
    def _obter_kpis_destaque(self, empresa):
        hoje = timezone.now().date()
        
        # Vendas hoje
        vendas_hoje = Venda.objects.filter(
            empresa=empresa,
            data_venda__date=hoje,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        # Produtos em estoque baixo
        produtos_estoque_baixo = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual__lte=F('estoque_minimo')
        ).count()
        
        # Contas vencidas (somando valor_saldo)
        # Contas vencidas: total e quantidade
        contas_vencidas_qs = ContaReceber.objects.filter(
            empresa=empresa,
            status__in=['aberta', 'vencida'],
            data_vencimento__lt=hoje
        )
        contas_vencidas_total = contas_vencidas_qs.aggregate(Sum('valor_saldo'))['valor_saldo__sum'] or 0
        contas_vencidas_qtd = contas_vencidas_qs.count()


        contas_vencidas = contas_vencidas_qs.aggregate(
            total=Sum('valor_saldo'),
            quantidade=Count('id')
        )
        
        # Novos clientes este mês
        novos_clientes = Cliente.objects.filter(
            empresa=empresa,
            created_at__month=hoje.month,
            created_at__year=hoje.year
        ).count()
        
        return {
            'vendas_hoje': vendas_hoje,
            'produtos_estoque_baixo': produtos_estoque_baixo,
            'contas_vencidas_total': contas_vencidas_total,
            'contas_vencidas_qtd': contas_vencidas_qtd,
            'novos_clientes': novos_clientes
        }

    
class CentralRelatoriosView(BaseViewMixin, TemplateView):
    template_name = 'relatorios/central.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Todos os tipos de relatório por categoria
        relatorios_por_categoria = {}
        categorias = TipoRelatorio.CATEGORIA_CHOICES
        
        for categoria_code, categoria_name in categorias:
            tipos = TipoRelatorio.objects.filter(
                categoria=categoria_code,
                ativo=True,
                publico=True
            ).order_by('ordem_exibicao', 'nome')
            
            if tipos.exists():
                # Adicionar estatísticas de uso para cada relatório
                tipos_com_stats = []
                for tipo in tipos:
                    execucoes = RelatorioGerado.objects.filter(
                        tipo_relatorio=tipo,
                        empresa=empresa
                    ).count()
                    
                    ultima_execucao = RelatorioGerado.objects.filter(
                        tipo_relatorio=tipo,
                        empresa=empresa
                    ).order_by('-data_solicitacao').first()
                    
                    tipos_com_stats.append({
                        'tipo': tipo,
                        'execucoes': execucoes,
                        'ultima_execucao': ultima_execucao
                    })
                
                relatorios_por_categoria[categoria_name] = tipos_com_stats
        
        # Templates personalizados da empresa
        templates_personalizados = TemplateRelatorio.objects.filter(
            empresa=empresa,
            ativo=True
        ).annotate(
            execucoes=Count('relatorio')
        ).order_by('-execucoes', 'nome')
        
        # Relatórios favoritos do usuário (mais executados pelo usuário)
        relatorios_favoritos = RelatorioGerado.objects.filter(
            empresa=empresa,
            solicitante=self.request.user
        ).values(
            'tipo_relatorio__nome',
            'tipo_relatorio__id'
        ).annotate(
            total_execucoes=Count('id')
        ).order_by('-total_execucoes')[:8]
        
        # Estatísticas da central
        stats_central = {
            'total_tipos': TipoRelatorio.objects.filter(ativo=True, publico=True).count(),
            'templates_empresa': templates_personalizados.count(),
            'relatorios_executados_mes': RelatorioGerado.objects.filter(
                empresa=empresa,
                data_solicitacao__month=timezone.now().month
            ).count(),
            'usuarios_ativos': RelatorioGerado.objects.filter(
                empresa=empresa,
                data_solicitacao__gte=timezone.now().date() - timedelta(days=30)
            ).values('solicitante').distinct().count()
        }
        
        context.update({
            'relatorios_por_categoria': relatorios_por_categoria,
            'templates_personalizados': templates_personalizados,
            'relatorios_favoritos': relatorios_favoritos,
            'stats_central': stats_central,
            'title': 'Central de Relatórios'
        })
        
        return context


class RelatoriosFavoritosView(BaseViewMixin, ListView):
    model = RelatorioGerado
    template_name = 'relatorios/favoritos.html'
    context_object_name = 'relatorios'
    paginate_by = 20
    
    def get_queryset(self):
        # Relatórios mais executados pelo usuário
        return RelatorioGerado.objects.filter(
            empresa=self.get_empresa(),
            solicitante=self.request.user
        ).values(
            'tipo_relatorio__nome',
            'tipo_relatorio__id',
            'tipo_relatorio__categoria',
            'tipo_relatorio__descricao'
        ).annotate(
            total_execucoes=Count('id'),
            ultima_execucao=Max('data_solicitacao'),
            tempo_medio=Avg('tempo_processamento')
        ).order_by('-total_execucoes')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Estatísticas dos favoritos
        usuario_stats = RelatorioGerado.objects.filter(
            empresa=self.get_empresa(),
            solicitante=self.request.user
        ).aggregate(
            total_relatorios=Count('id'),
            formatos_usados=Count('formato', distinct=True),
            tempo_total=Sum('tempo_processamento')
        )
        
        context.update({
            'usuario_stats': usuario_stats,
            'title': 'Meus Relatórios Favoritos'
        })
        
        return context


class RelatoriosRecentesView(BaseViewMixin, ListView):
    model = RelatorioGerado
    template_name = 'relatorios/recentes.html'
    context_object_name = 'relatorios'
    paginate_by = 20
    
    def get_queryset(self):
        return RelatorioGerado.objects.filter(
            empresa=self.get_empresa(),
            solicitante=self.request.user
        ).select_related('tipo_relatorio').order_by('-data_solicitacao')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Relatórios por status
        relatorios_por_status = RelatorioGerado.objects.filter(
            empresa=self.get_empresa(),
            solicitante=self.request.user
        ).values('status').annotate(
            total=Count('id')
        ).order_by('-total')
        
        context.update({
            'relatorios_por_status': relatorios_por_status,
            'title': 'Relatórios Recentes'
        })
        
        return context


# =====================================
# CONSTRUTOR DE RELATÓRIOS
# =====================================

class ConstrutorRelatorioView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/construtor/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Templates disponíveis para edição
        templates_disponiveis = TemplateRelatorio.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('-updated_at')
        
        # Modelos de dados disponíveis
        modelos_disponiveis = [
            {
                'nome': 'Vendas',
                'model': 'vendas.Venda',
                'descricao': 'Dados de vendas e faturamento',
                'campos_principais': ['data_venda', 'total', 'cliente', 'funcionario']
            },
            {
                'nome': 'Produtos',
                'model': 'produtos.Produto',
                'descricao': 'Catálogo de produtos e estoque',
                'campos_principais': ['nome_comercial', 'categoria', 'preco_venda', 'estoque_atual']
            },
            {
                'nome': 'Clientes',
                'model': 'clientes.Cliente',
                'descricao': 'Base de clientes cadastrados',
                'campos_principais': ['nome', 'cidade', 'data_nascimento', 'tipo_pessoa']
            },
            {
                'nome': 'Funcionários',
                'model': 'funcionarios.Funcionario',
                'descricao': 'Quadro de funcionários',
                'campos_principais': ['user__first_name', 'cargo', 'departamento', 'salario']
            },
            {
                'nome': 'Fornecedores',
                'model': 'fornecedores.Fornecedor',
                'descricao': 'Cadastro de fornecedores',
                'campos_principais': ['nome', 'cidade', 'categoria', 'ativo']
            },
            {
                'nome': 'Financeiro',
                'model': 'financeiro.ContaReceber',
                'descricao': 'Contas a receber e pagar',
                'campos_principais': ['valor', 'data_vencimento', 'status', 'cliente']
            }
        ]
        
        # Templates de exemplo por categoria
        templates_exemplo = {
            'Vendas': [
                'Relatório de Vendas Diário',
                'Ranking de Produtos',
                'Performance de Vendedores'
            ],
            'Estoque': [
                'Posição de Estoque',
                'Movimentação por Período',
                'Produtos Vencidos'
            ],
            'Financeiro': [
                'Fluxo de Caixa',
                'Contas em Aberto',
                'DRE Gerencial'
            ]
        }
        
        # Estatísticas do construtor
        stats_construtor = {
            'templates_criados': TemplateRelatorio.objects.filter(empresa=empresa).count(),
            'relatorios_gerados': Relatorio.objects.filter(
                template__empresa=empresa
            ).count(),
            'usuarios_criadores': Relatorio.objects.filter(
                template__empresa=empresa
            ).values('gerado_por').distinct().count()
        }
        
        context.update({
            'templates_disponiveis': templates_disponiveis,
            'modelos_disponiveis': modelos_disponiveis,
            'templates_exemplo': templates_exemplo,
            'stats_construtor': stats_construtor,
            'title': 'Construtor de Relatórios'
        })
        
        return context


class NovoRelatorioView(BaseViewMixin, CreateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    model = TemplateRelatorio
    form_class = TemplateRelatorioForm
    template_name = 'relatorios/construtor/novo.html'
    success_url = reverse_lazy('relatorios:template_lista')
    
    def form_valid(self, form):
        form.instance.empresa = self.get_empresa()
        form.instance.created_by = self.request.user
        
        # Log da criação
        LogRelatorio.objects.create(
            empresa=self.get_empresa(),
            usuario=self.request.user,
            acao='criacao_template',
            detalhes=f'Template "{form.instance.nome}" criado',
            objeto_id=form.instance.id
        )
        
        messages.success(self.request, 'Template de relatório criado com sucesso!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        #kwargs['empresa'] = self.get_empresa()
        kwargs['usuario'] = self.request.user
        return kwargs


class EditarRelatorioView(BaseViewMixin, UpdateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    model = TemplateRelatorio
    form_class = TemplateRelatorioForm
    template_name = 'relatorios/construtor/editar.html'
    
    def get_success_url(self):
        return reverse_lazy('relatorios:template_detail', kwargs={'pk': self.object.pk})
    
    def get_queryset(self):
        return TemplateRelatorio.objects.filter(empresa=self.get_empresa())
    
    def form_valid(self, form):
        # Log da alteração
        LogRelatorio.objects.create(
            empresa=self.get_empresa(),
            usuario=self.request.user,
            acao='edicao_template',
            detalhes=f'Template "{form.instance.nome}" editado',
            objeto_id=form.instance.id
        )
        
        messages.success(self.request, 'Template atualizado com sucesso!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        kwargs['usuario'] = self.request.user
        return kwargs


class CamposDisponiveisView(BaseViewMixin, View):
    def get(self, request):
        model_name = request.GET.get('model')
        
        if not model_name:
            return JsonResponse({'error': 'Parâmetro model é obrigatório'}, status=400)
        
        try:
            # Mapeamento de modelos disponíveis
            models_map = {
                'vendas': Venda,
                'produtos': Produto,
                'clientes': Cliente,
                'funcionarios': Funcionario,
                'fornecedores': Fornecedor,
                'contas_receber': ContaReceber,
                'contas_pagar': ContaPagar
            }
            
            if model_name not in models_map:
                return JsonResponse({'error': 'Modelo não encontrado'}, status=404)
            
            model_class = models_map[model_name]
            
            campos = []
            for field in model_class._meta.fields:
                campo_info = {
                    'name': field.name,
                    'verbose_name': str(field.verbose_name),
                    'type': field.get_internal_type(),
                    'required': not field.null,
                    'help_text': field.help_text or '',
                    'choices': []
                }
                
                # Adicionar choices se existirem
                if hasattr(field, 'choices') and field.choices:
                    campo_info['choices'] = [
                        {'value': choice[0], 'label': choice[1]}
                        for choice in field.choices
                    ]
                
                campos.append(campo_info)
            
            # Adicionar campos relacionados mais comuns
            if model_name == 'vendas':
                campos.extend([
                    {
                        'name': 'cliente__nome',
                        'verbose_name': 'Nome do Cliente',
                        'type': 'CharField',
                        'required': False
                    },
                    {
                        'name': 'funcionario__user__first_name',
                        'verbose_name': 'Nome do Vendedor',
                        'type': 'CharField',
                        'required': False
                    }
                ])
            
            return JsonResponse({
                'success': True,
                'campos': campos,
                'model_name': model_class._meta.verbose_name
            })
            
        except Exception as e:
            logger.error(f'Erro ao obter campos do modelo {model_name}: {e}')
            return JsonResponse({'error': str(e)}, status=500)


# =====================================
# TEMPLATES DE RELATÓRIOS
# =====================================

class TemplateRelatorioListView(BaseViewMixin, ListView):
    model = TemplateRelatorio
    template_name = 'relatorios/templates/lista.html'
    context_object_name = 'templates'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = TemplateRelatorio.objects.filter(
            empresa=self.get_empresa()
        )
        
        # Filtros
        categoria = self.request.GET.get('categoria')
        busca = self.request.GET.get('busca')
        ativo = self.request.GET.get('ativo')
        
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        
        if busca:
            queryset = queryset.filter(
                Q(nome__icontains=busca) |
                Q(descricao__icontains=busca)
            )
        
        if ativo is not None:
            queryset = queryset.filter(ativo=ativo == 'true')
        
        return queryset.order_by('-updated_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Categorias disponíveis
        categorias = TemplateRelatorio.objects.filter(
            empresa=self.get_empresa()
        ).values_list('categoria', flat=True).distinct()
        
        # Estatísticas
        stats = {
            'total_templates': TemplateRelatorio.objects.filter(empresa=self.get_empresa()).count(),
            'templates_ativos': TemplateRelatorio.objects.filter(
                empresa=self.get_empresa(), ativo=True
            ).count(),
            'templates_usados': TemplateRelatorio.objects.filter(
                empresa=self.get_empresa(),
                relatorio__isnull=False
            ).distinct().count()
        }
        
        context.update({
            'categorias': categorias,
            'stats': stats,
            'filtros': {
                'categoria': self.request.GET.get('categoria'),
                'busca': self.request.GET.get('busca'),
                'ativo': self.request.GET.get('ativo')
            },
            'title': 'Templates de Relatórios'
        })
        
        return context


class TemplateRelatorioCreateView(BaseViewMixin, CreateView):
    model = TemplateRelatorio
    form_class = TemplateRelatorioForm
    template_name = 'relatorios/templates/form.html'
    success_url = reverse_lazy('relatorios:template_lista')
    
    def form_valid(self, form):
        form.instance.empresa = self.get_empresa()
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Template criado com sucesso!')
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empresa'] = self.get_empresa()
        kwargs['usuario'] = self.request.user
        return kwargs


class TemplateRelatorioDetailView(BaseViewMixin, DetailView):
    model = TemplateRelatorio
    template_name = 'relatorios/templates/detail.html'
    context_object_name = 'template'
    
    def get_queryset(self):
        return TemplateRelatorio.objects.filter(empresa=self.get_empresa())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.get_object()
        
        # Relatórios gerados com este template
        relatorios_gerados = Relatorio.objects.filter(
            template=template
        ).order_by('-data_geracao')[:10]
        
        # Estatísticas de uso
        stats_uso = {
            'total_execucoes': Relatorio.objects.filter(template=template).count(),
            'execucoes_mes': Relatorio.objects.filter(
                template=template,
                data_geracao__month=timezone.now().month
            ).count(),
            'ultimo_uso': relatorios_gerados.first().data_geracao if relatorios_gerados.exists() else None,
            'tempo_medio_geracao': Relatorio.objects.filter(
                template=template
            ).aggregate(Avg('tempo_processamento'))['tempo_processamento__avg']
        }
        
        # Usuários que mais usam este template
        usuarios_frequentes = Relatorio.objects.filter(
            template=template
        ).values(
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total_usos=Count('id')
        ).order_by('-total_usos')[:5]
        
        context.update({
            'relatorios_gerados': relatorios_gerados,
            'stats_uso': stats_uso,
            'usuarios_frequentes': usuarios_frequentes,
            'title': f'Template: {template.nome}'
        })
        
        return context


class DuplicarTemplateView(BaseViewMixin, View):
    def post(self, request, pk):
        template_original = get_object_or_404(
            TemplateRelatorio, pk=pk, empresa=self.get_empresa()
        )
        
        try:
            with transaction.atomic():
                # Criar cópia
                novo_template = TemplateRelatorio.objects.create(
                    empresa=self.get_empresa(),
                    nome=f"{template_original.nome} (Cópia)",
                    descricao=template_original.descricao,
                    categoria=template_original.categoria,
                    modelo_base=template_original.modelo_base,
                    campos=template_original.campos,
                    filtros_disponiveis=template_original.filtros_disponiveis,
                    ordenacao_padrao=template_original.ordenacao_padrao,
                    formato_padrao=template_original.formato_padrao,
                    layout_personalizado=template_original.layout_personalizado,
                    configuracoes_avancadas=template_original.configuracoes_avancadas,
                    ativo=True,
                    created_by=request.user
                )
                
                # Log da duplicação
                LogRelatorio.objects.create(
                    empresa=self.get_empresa(),
                    usuario=request.user,
                    acao='duplicacao_template',
                    detalhes=f'Template "{template_original.nome}" duplicado como "{novo_template.nome}"',
                    objeto_id=novo_template.id
                )
                
                messages.success(request, f'Template duplicado com sucesso!')
                return redirect('relatorios:template_detail', pk=novo_template.pk)
                
        except Exception as e:
            logger.error(f'Erro ao duplicar template: {e}')
            messages.error(request, f'Erro ao duplicar template: {str(e)}')
            return redirect('relatorios:template_detail', pk=pk)


class CompartilharTemplateView(BaseViewMixin, TemplateView):
    template_name = 'relatorios/templates/compartilhar.html'
    
    def get_object(self):
        return get_object_or_404(
            TemplateRelatorio, pk=self.kwargs['pk'], empresa=self.get_empresa()
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template = self.get_object()
        
        # Usuários da empresa que podem receber o compartilhamento
        usuarios_empresa = User.objects.filter(
            funcionario__empresa=self.get_empresa(),
            is_active=True
        ).exclude(id=self.request.user.id)
        
        # Grupos de usuários
        grupos_disponíveis = Group.objects.all()
        
        context.update({
            'template': template,
            'usuarios_empresa': usuarios_empresa,
            'grupos_disponíveis': grupos_disponíveis,
            'title': f'Compartilhar Template: {template.nome}'
        })
        
        return context
    
    def post(self, request, pk):
        template = self.get_object()
        
        try:
            usuarios_ids = request.POST.getlist('usuarios')
            grupos_ids = request.POST.getlist('grupos')
            permissoes = request.POST.getlist('permissoes')
            mensagem = request.POST.get('mensagem', '')
            
            # Criar registros de compartilhamento
            usuarios_compartilhados = []
            
            # Compartilhar com usuários específicos
            for user_id in usuarios_ids:
                usuario = User.objects.get(id=user_id)
                usuarios_compartilhados.append(usuario)
            
            # Compartilhar com grupos
            for grupo_id in grupos_ids:
                grupo = Group.objects.get(id=grupo_id)
                usuarios_compartilhados.extend(grupo.user_set.all())
            
            # Enviar notificações por email
            if usuarios_compartilhados:
                for usuario in set(usuarios_compartilhados):  # Remove duplicatas
                    if usuario.email:
                        self._enviar_notificacao_compartilhamento(
                            template, usuario, request.user, mensagem
                        )
                
                # Log do compartilhamento
                LogRelatorio.objects.create(
                    empresa=self.get_empresa(),
                    usuario=request.user,
                    acao='compartilhamento_template',
                    detalhes=f'Template "{template.nome}" compartilhado com {len(set(usuarios_compartilhados))} usuário(s)',
                    objeto_id=template.id
                )
                
                messages.success(
                    request, 
                    f'Template compartilhado com {len(set(usuarios_compartilhados))} usuário(s)!'
                )
            else:
                messages.warning(request, 'Nenhum usuário foi selecionado para compartilhamento.')
            
            return redirect('relatorios:template_detail', pk=pk)
            
        except Exception as e:
            logger.error(f'Erro ao compartilhar template: {e}')
            messages.error(request, f'Erro ao compartilhar template: {str(e)}')
            return redirect('relatorios:template_compartilhar', pk=pk)
    
    def _enviar_notificacao_compartilhamento(self, template, usuario_destino, usuario_origem, mensagem):
        try:
            assunto = f'Template de Relatório Compartilhado: {template.nome}'
            
            corpo = f"""
            Olá {usuario_destino.get_full_name() or usuario_destino.username},
            
            O usuário {usuario_origem.get_full_name() or usuario_origem.username} compartilhou um template de relatório com você.
            
            Template: {template.nome}
            Descrição: {template.descricao}
            
            {f'Mensagem: {mensagem}' if mensagem else ''}
            
            Para acessar o template, faça login no sistema e vá para a seção de Relatórios.
            
            Atenciosamente,
            Sistema VistoGEST
            """
            
            send_mail(
                subject=assunto,
                message=corpo,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[usuario_destino.email],
                fail_silently=False
            )
            
        except Exception as e:
            logger.error(f'Erro ao enviar email de compartilhamento: {e}')


# =====================================
# RELATÓRIOS DE VENDAS
# =====================================


from django.db.models import Sum, Count
from datetime import timedelta
from django.utils import timezone

class RelatoriosVendasView(TemplateView):
    template_name = 'relatorios/vendas/dashboard.html'

    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        if not empresa:
            context["erro"] = "Nenhuma empresa associada ao usuário."
            return context

        hoje = timezone.now().date()
        inicio_mes = hoje.replace(day=1)
        inicio_ano = hoje.replace(month=1, day=1)

        # === ESTATÍSTICAS GERAIS ===
        vendas_hoje_qs = Venda.objects.filter(
            empresa=empresa,
            data_venda__date=hoje,
            status='finalizada'
        )

        vendas_hoje = vendas_hoje_qs.aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )

        vendas_hoje['ticket_medio'] = (
            (vendas_hoje['total'] or 0) / vendas_hoje['quantidade']
        ) if vendas_hoje['quantidade'] else 0

        # === VENDAS MÊS ===
        vendas_mes_qs = Venda.objects.filter(
            empresa=empresa, data_venda__date__gte=inicio_mes, status="finalizada"
        )
        vendas_mes = vendas_mes_qs.aggregate(
            total_vendas=Sum("total"),
            quantidade=Count("id")
        )
        vendas_mes['ticket_medio'] = (
            (vendas_mes['total_vendas'] or 0) / vendas_mes['quantidade']
        ) if vendas_mes['quantidade'] else 0

        # === VENDAS ANO ===
        vendas_ano_qs = Venda.objects.filter(
            empresa=empresa, data_venda__date__gte=inicio_ano, status="finalizada"
        )
        vendas_ano = vendas_ano_qs.aggregate(
            total_vendas=Sum("total"),
            quantidade=Count("id")
        )
        vendas_ano['ticket_medio'] = (
            (vendas_ano['total_vendas'] or 0) / vendas_ano['quantidade']
        ) if vendas_ano['quantidade'] else 0

        # === COMPARAÇÃO COM MÊS ANTERIOR ===
        mes_anterior = inicio_mes - timedelta(days=1)
        inicio_mes_anterior = mes_anterior.replace(day=1)
        vendas_mes_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__date__gte=inicio_mes_anterior,
            data_venda__date__lt=inicio_mes,
            status="finalizada"
        ).aggregate(Sum("total"))["total__sum"] or 0

        crescimento_mes = 0
        if vendas_mes_anterior > 0:
            crescimento_mes = (
                ((vendas_mes['total_vendas'] or 0) - vendas_mes_anterior)
                / vendas_mes_anterior
            ) * 100

        top_produtos = (
            ItemVenda.objects.filter(
                venda__empresa=empresa,
                venda__data_venda__date__gte=inicio_mes,
                venda__status="finalizada",
                produto__isnull=False,
            )
            .select_related("produto")
            .annotate(
                nome=F("produto__nome_produto"),
                quantidade_vendida=Sum("quantidade"),
                faturamento=Sum(F("quantidade") * F("preco_unitario")),
            )
            .values("nome", "quantidade_vendida", "faturamento")
            .order_by("-faturamento")[:10]
        )

        # === VENDAS POR VENDEDOR ===
        vendas_por_vendedor = (
            Venda.objects.filter(
                empresa=empresa,
                data_venda__date__gte=inicio_mes,
                status="finalizada",
                vendedor__isnull=False,
            )
            .values("vendedor__nome_completo")
            .annotate(
                total_vendas=Count("id"),
                faturamento=Sum("total"),
                ticket_medio=Avg("total"),
            )
            .order_by("-faturamento")[:10]
        )

        # === VENDAS POR FORMA DE PAGAMENTO ===
        vendas_forma_pagamento = (
            Venda.objects.filter(
                empresa=empresa,
                data_venda__date__gte=inicio_mes,
                status="finalizada",
            )
            .values("forma_pagamento__nome")
            .annotate(total=Sum("total"), quantidade=Count("id"))
            .order_by("-total")
        )

        # === VENDAS POR DIA (últimos 30 dias) ===
        vendas_por_dia = (
            Venda.objects.filter(
                empresa=empresa,
                data_venda__date__gte=hoje - timedelta(days=30),
                status="finalizada",
            )
            .values("data_venda__date")
            .annotate(total=Sum("total"), quantidade=Count("id"))
            .order_by("data_venda__date")
        )

        # === META (se houver tabela de métricas) ===
        meta_mes = MetricaKPI.objects.filter(
            empresa=empresa,
            codigo="META_VENDAS_MES",
            data_referencia__month=hoje.month,
            data_referencia__year=hoje.year,
        ).first()

        percentual_meta = 0
        if meta_mes and meta_mes.valor_meta > 0:
            percentual_meta = (
                (vendas_mes["total_vendas"] or 0) / meta_mes.valor_meta
            ) * 100

        context.update({
            "vendas_hoje": vendas_hoje,
            "vendas_mes": vendas_mes,
            "vendas_ano": vendas_ano,
            "crescimento_mes": round(crescimento_mes, 1),
            "meta_mes": meta_mes,
            "percentual_meta": round(percentual_meta, 1),
            "title": "Relatório de Vendas",
        })
        return context


class RelatorioVendasDiarioView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/diario.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Data selecionada
        data_str = self.request.GET.get('data')
        if data_str:
            data_selecionada = datetime.strptime(data_str, '%Y-%m-%d').date()
        else:
            data_selecionada = timezone.now().date()
        
        # Vendas do dia
        vendas_dia = Venda.objects.filter(
            empresa=empresa,
            data_venda=data_selecionada,
            status='finalizada'
        ).select_related('cliente', 'vendedor').order_by('-created_at')
        
        vendas_dia = vendas_dia.annotate(
            total_itens = Sum('itens__quantidade')
        )
        # Estatísticas do dia
        stats_dia = vendas_dia.aggregate(
            total_vendas=Count('id'),
            faturamento_total=Sum('total'),
            ticket_medio=Avg('total'),
            total_itens=Sum('itens__quantidade'),
            desconto_total = Sum('itens__desconto_item')
        )
        
        

        vendas_por_hora = vendas_dia.annotate(
            hora=ExtractHour(F('created_at'))
        ).values('hora').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('hora')

        
        # Completar todas as horas (0-23)
        vendas_hora_completa = []
        vendas_dict = {int(v['hora']): v for v in vendas_por_hora}
        
        for hora in range(24):
            if hora in vendas_dict:
                vendas_hora_completa.append(vendas_dict[hora])
            else:
                vendas_hora_completa.append({
                    'hora': hora,
                    'total': 0,
                    'quantidade': 0
                })
        
        # Top produtos do dia
        top_produtos_dia = ItemVenda.objects.filter(
            venda__in=vendas_dia
        ).values(
            'produto__nome_comercial',
            'produto__codigo_interno'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario'))
        ).order_by('-faturamento')[:10]
        
     
        # Vendedores do dia
        vendedores_dia = vendas_dia.filter(
            vendedor__isnull=False
        ).values(
            'vendedor__nome_completo'  # pega diretamente o nome completo do Funcionario
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total')
        ).order_by('-faturamento')

        
        # Formas de pagamento
        formas_pagamento = vendas_dia.values(
            'forma_pagamento'
        ).annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('-total')
        
        # Clientes do dia
        clientes_dia = vendas_dia.filter(
            cliente__isnull=False
        ).values(
            'cliente__nome_completo'
        ).annotate(
            total_compras=Sum('total'),
            quantidade_compras=Count('id')
        ).order_by('-total_compras')[:10]
        
        # Comparação com o mesmo dia da semana anterior
        data_semana_anterior = data_selecionada - timedelta(days=7)
        vendas_semana_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda=data_semana_anterior,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        # Análise de desempenho por período do dia
        periodos_dia = {
            'manha': vendas_dia.annotate(hora=ExtractHour(F('created_at'))).filter(hora__range=(6, 11)).aggregate(total=Sum('total'), qtd=Count('id')),
            'tarde': vendas_dia.annotate(hora=ExtractHour(F('created_at'))).filter(hora__range=(12, 17)).aggregate(total=Sum('total'), qtd=Count('id')),
            'noite': vendas_dia.annotate(hora=ExtractHour(F('created_at'))).filter(hora__range=(18, 23)).aggregate(total=Sum('total'), qtd=Count('id')),
        }

        
        context.update({
            'data_selecionada': data_selecionada,
            'vendas_dia': vendas_dia,
            'stats_dia': stats_dia,
            'vendas_por_hora': vendas_hora_completa,
            'top_produtos_dia': top_produtos_dia,
            'vendedores_dia': vendedores_dia,
            'formas_pagamento': formas_pagamento,
            'clientes_dia': clientes_dia,
            'vendas_semana_anterior': vendas_semana_anterior,
            'periodos_dia': periodos_dia,
            'title': f'Relatório Diário - {data_selecionada.strftime("%d/%m/%Y")}'
        })
        
        return context


class RelatorioVendasMensalView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/mensal.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Mês e ano selecionados
        mes = int(self.request.GET.get('mes', timezone.now().month))
        ano = int(self.request.GET.get('ano', timezone.now().year))
        
        # Primeiro e último dia do mês
        primeiro_dia = date(ano, mes, 1)
        if mes == 12:
            ultimo_dia = date(ano + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(ano, mes + 1, 1) - timedelta(days=1)
        
        
        vendas_mes = vendas_mes.annotate(
            total_itens=Sum('itens__quantidade')  # aqui criamos o campo calculado
        )

        stats_mes = vendas_mes.aggregate(
            total_vendas=Count('id'),
            faturamento_total=Sum('total'),
            ticket_medio=Avg('total'),
            total_itens=Sum('total_itens'),  # agora funciona
            desconto_total=Sum('desconto_valor')  # se o campo correto for desconto_valor
        )

        
        # Vendas por dia do mês
        vendas_por_dia = vendas_mes.values('data_venda').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('data_venda')
        
        # Criar lista completa de dias do mês
        vendas_dia_completa = []
        vendas_dict = {v['data_venda']: v for v in vendas_por_dia}
        
        current_date = primeiro_dia
        while current_date <= ultimo_dia:
            if current_date in vendas_dict:
                vendas_dia_completa.append({
                    'data': current_date,
                    'total': vendas_dict[current_date]['total'],
                    'quantidade': vendas_dict[current_date]['quantidade']
                })
            else:
                vendas_dia_completa.append({
                    'data': current_date,
                    'total': 0,
                    'quantidade': 0
                })
            current_date += timedelta(days=1)
        
        # Vendas por semana
        vendas_por_semana = vendas_mes.annotate(
            semana=TruncWeek('data_venda')
        ).values('semana').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('semana')
        
        # Top vendedores do mês
        top_vendedores = vendas_mes.filter(
            funcionario__isnull=False
        ).values(
            'vendedor__user__first_name',
            'vendedor__user__last_name',
            'funcionario__id'
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total'),
            ticket_medio=Avg('total')
        ).order_by('-faturamento')[:10]
        
        # Top clientes do mês
        top_clientes = vendas_mes.filter(
            cliente__isnull=False
        ).values(
            'cliente__nome',
            'cliente__id'
        ).annotate(
            total_compras=Count('id'),
            faturamento=Sum('total')
        ).order_by('-faturamento')[:10]
        
        # Produtos mais vendidos
        produtos_mais_vendidos = ItemVenda.objects.filter(
            venda__in=vendas_mes
        ).values(
            'produto__nome_produto',
            'produto__categoria__nome'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario'))
        ).order_by('-faturamento')[:15]
        
        # Vendas por categoria
        vendas_por_categoria = ItemVenda.objects.filter(
            venda__in=vendas_mes
        ).values(
            'produto__categoria__nome'
        ).annotate(
            faturamento=Sum(F('quantidade') * F('preco_unitario')),
            quantidade=Sum('quantidade')
        ).order_by('-faturamento')
        
        # Análise de crescimento
        # Mês anterior
        if mes == 1:
            mes_anterior = 12
            ano_anterior = ano - 1
        else:
            mes_anterior = mes - 1
            ano_anterior = ano
        
        primeiro_dia_anterior = date(ano_anterior, mes_anterior, 1)
        if mes_anterior == 12:
            ultimo_dia_anterior = date(ano_anterior + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia_anterior = date(ano_anterior, mes_anterior + 1, 1) - timedelta(days=1)
        
        vendas_mes_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=primeiro_dia_anterior,
            data_venda__lte=ultimo_dia_anterior,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        # Calcular variações
        variacao_faturamento = 0
        variacao_quantidade = 0
        
        if vendas_mes_anterior['total']:
            variacao_faturamento = (
                (stats_mes['faturamento_total'] or 0) - vendas_mes_anterior['total']
            ) / vendas_mes_anterior['total'] * 100
        
        if vendas_mes_anterior['quantidade']:
            variacao_quantidade = (
                (stats_mes['total_vendas'] or 0) - vendas_mes_anterior['quantidade']
            ) / vendas_mes_anterior['quantidade'] * 100
        
        # Metas do mês
        meta_faturamento = MetricaKPI.objects.filter(
            empresa=empresa,
            codigo='META_FATURAMENTO_MES',
            data_referencia__month=mes,
            data_referencia__year=ano
        ).first()
        
        meta_vendas = MetricaKPI.objects.filter(
            empresa=empresa,
            codigo='META_VENDAS_MES',
            data_referencia__month=mes,
            data_referencia__year=ano
        ).first()
        
        # Calcular percentual das metas
        percentual_meta_faturamento = 0
        percentual_meta_vendas = 0
        
        if meta_faturamento and meta_faturamento.valor_meta > 0:
            percentual_meta_faturamento = (
                (stats_mes['faturamento_total'] or 0) / meta_faturamento.valor_meta
            ) * 100
        
        if meta_vendas and meta_vendas.valor_meta > 0:
            percentual_meta_vendas = (
                (stats_mes['total_vendas'] or 0) / meta_vendas.valor_meta
            ) * 100
        
        context.update({
            'mes': mes,
            'ano': ano,
            'nome_mes': calendar.month_name[mes],
            'primeiro_dia': primeiro_dia,
            'ultimo_dia': ultimo_dia,
            'stats_mes': stats_mes,
            'vendas_por_dia': vendas_dia_completa,
            'vendas_por_semana': list(vendas_por_semana),
            'top_vendedores': top_vendedores,
            'top_clientes': top_clientes,
            'produtos_mais_vendidos': produtos_mais_vendidos,
            'vendas_por_categoria': vendas_por_categoria,
            'vendas_mes_anterior': vendas_mes_anterior,
            'variacao_faturamento': round(variacao_faturamento, 1),
            'variacao_quantidade': round(variacao_quantidade, 1),
            'meta_faturamento': meta_faturamento,
            'meta_vendas': meta_vendas,
            'percentual_meta_faturamento': round(percentual_meta_faturamento, 1),
            'percentual_meta_vendas': round(percentual_meta_vendas, 1),
            'title': f'Relatório Mensal - {calendar.month_name[mes]}/{ano}'
        })
        
        return context


class RelatorioVendasAnualView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/anual.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Ano selecionado
        ano = int(self.request.GET.get('ano', timezone.now().year))
        
        # Vendas do ano
        vendas_ano = Venda.objects.filter(
            empresa=empresa,
            data_venda__year=ano,
            status='finalizada'
        )
        
        # Estatísticas do ano
        stats_ano = vendas_ano.aggregate(
            total_vendas=Count('id'),
            faturamento_total=Sum('total'),
            ticket_medio=Avg('total'),
            total_itens=Sum('total_itens'),
            desconto_total=Sum('desconto')
        )
        
        # Vendas por mês
        vendas_por_mes = vendas_ano.annotate(
            mes=TruncMonth('data_venda')
        ).values('mes').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('mes')
        
        # Criar lista completa de meses
        vendas_mes_completa = []
        vendas_dict = {v['mes']: v for v in vendas_por_mes}
        
        for mes_num in range(1, 13):
            mes_date = date(ano, mes_num, 1)
            if mes_date in vendas_dict:
                vendas_mes_completa.append({
                    'mes': mes_num,
                    'nome_mes': calendar.month_name[mes_num],
                    'total': vendas_dict[mes_date]['total'],
                    'quantidade': vendas_dict[mes_date]['quantidade']
                })
            else:
                vendas_mes_completa.append({
                    'mes': mes_num,
                    'nome_mes': calendar.month_name[mes_num],
                    'total': 0,
                    'quantidade': 0
                })
        
        # Vendas por trimestre
        vendas_por_trimestre = []
        trimestres = [
            (1, 'Q1', [1, 2, 3]),
            (2, 'Q2', [4, 5, 6]),
            (3, 'Q3', [7, 8, 9]),
            (4, 'Q4', [10, 11, 12])
        ]
        
        for trimestre_num, trimestre_nome, meses in trimestres:
            vendas_trimestre = vendas_ano.filter(
                data_venda__month__in=meses
            ).aggregate(
                total=Sum('total'),
                quantidade=Count('id')
            )
            
            vendas_por_trimestre.append({
                'trimestre': trimestre_num,
                'nome': trimestre_nome,
                'total': vendas_trimestre['total'] or 0,
                'quantidade': vendas_trimestre['quantidade'] or 0
            })
        
        # Performance dos vendedores no ano
        performance_vendedores = vendas_ano.filter(
            funcionario__isnull=False
        ).values(
            'funcionario__user__first_name',
            'funcionario__user__last_name',
            'funcionario__id'
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total'),
            ticket_medio=Avg('total')
        ).order_by('-faturamento')[:15]
        
        # Análise de sazonalidade
        sazonalidade = []
        for mes_data in vendas_mes_completa:
            media_anual = stats_ano['faturamento_total'] / 12 if stats_ano['faturamento_total'] else 0
            if media_anual > 0:
                indice_sazonalidade = (mes_data['total'] / media_anual) * 100
            else:
                indice_sazonalidade = 0
            
            sazonalidade.append({
                'mes': mes_data['mes'],
                'nome_mes': mes_data['nome_mes'],
                'indice': round(indice_sazonalidade, 1)
            })
        
        # Top produtos do ano
        top_produtos_ano = ItemVenda.objects.filter(
            venda__in=vendas_ano
        ).values(
            'produto__nome_comercial',
            'produto__categoria__nome'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario'))
        ).order_by('-faturamento')[:20]
        
        # Comparação com ano anterior
        vendas_ano_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__year=ano-1,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        # Calcular crescimento anual
        crescimento_faturamento = 0
        crescimento_vendas = 0
        
        if vendas_ano_anterior['total']:
            crescimento_faturamento = (
                (stats_ano['faturamento_total'] or 0) - vendas_ano_anterior['total']
            ) / vendas_ano_anterior['total'] * 100
        
        if vendas_ano_anterior['quantidade']:
            crescimento_vendas = (
                (stats_ano['total_vendas'] or 0) - vendas_ano_anterior['quantidade']
            ) / vendas_ano_anterior['quantidade'] * 100
        
        # Meta anual
        meta_anual = MetricaKPI.objects.filter(
            empresa=empresa,
            codigo='META_FATURAMENTO_ANUAL',
            data_referencia__year=ano
        ).first()
        
        percentual_meta_anual = 0
        if meta_anual and meta_anual.valor_meta > 0:
            percentual_meta_anual = (
                (stats_ano['faturamento_total'] or 0) / meta_anual.valor_meta
            ) * 100
        
        context.update({
            'ano': ano,
            'stats_ano': stats_ano,
            'vendas_por_mes': vendas_mes_completa,
            'vendas_por_trimestre': vendas_por_trimestre,
            'performance_vendedores': performance_vendedores,
            'sazonalidade': sazonalidade,
            'top_produtos_ano': top_produtos_ano,
            'vendas_ano_anterior': vendas_ano_anterior,
            'crescimento_faturamento': round(crescimento_faturamento, 1),
            'crescimento_vendas': round(crescimento_vendas, 1),
            'meta_anual': meta_anual,
            'percentual_meta_anual': round(percentual_meta_anual, 1),
            'title': f'Relatório Anual - {ano}'
        })
        
        return context


class RelatorioVendasProdutoView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/produto.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        produto_id = self.request.GET.get('produto_id')
        categoria_id = self.request.GET.get('categoria_id')
        marca_id = self.request.GET.get('marca_id')
        
        # Definir período padrão (últimos 30 dias)
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Query base de vendas
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        )
        
        itens_vendidos = ItemVenda.objects.filter(venda__in=vendas)
        
        # Aplicar filtros
        if produto_id:
            itens_vendidos = itens_vendidos.filter(produto_id=produto_id)
        
        if categoria_id:
            itens_vendidos = itens_vendidos.filter(produto__categoria_id=categoria_id)
        
        if marca_id:
            itens_vendidos = itens_vendidos.filter(produto__marca_id=marca_id)
        
        # Ranking de produtos
        ranking_produtos = itens_vendidos.values(
            'produto__nome_comercial',
            'produto__codigo',
            'produto__categoria__nome',
            'produto__marca__nome',
            'produto__id'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario')),
            numero_documentos=Count('venda', distinct=True),
            ticket_medio=Avg(F('quantidade') * F('preco_unitario')),
            margem_media=Avg(F('preco_unitario') - F('produto__preco_custo'))
        ).order_by('-faturamento')[:100]
        
        # Adicionar informações de estoque e giro
        for produto in ranking_produtos:
            produto_obj = Produto.objects.get(id=produto['produto__id'])
            produto['estoque_atual'] = produto_obj.estoque_atual
            produto['preco_venda'] = produto_obj.preco_venda
            
            # Calcular giro do produto
            if produto_obj.estoque_atual > 0:
                dias_periodo = (data_fim - data_inicio).days or 1
                giro_periodo = produto['quantidade_vendida'] / produto_obj.estoque_atual
                produto['giro_anual'] = (giro_periodo * 365) / dias_periodo
            else:
                produto['giro_anual'] = 0
        
        # Produtos por categoria
        produtos_por_categoria = itens_vendidos.values(
            'produto__categoria__nome',
            'produto__categoria__id'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario')),
            produtos_distintos=Count('produto', distinct=True)
        ).order_by('-faturamento')
        
        # Produtos por marca
        produtos_por_marca = itens_vendidos.values(
            'produto__marca__nome',
            'produto__marca__id'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario')),
            produtos_distintos=Count('produto', distinct=True)
        ).order_by('-faturamento')
        
        # Evolução de vendas por período
        if produto_id:
            # Para produto específico
            evolucao_vendas = itens_vendidos.filter(
                produto_id=produto_id
            ).extra(
                select={'data': 'DATE(venda.data_venda)'}
            ).values('data').annotate(
                quantidade=Sum('quantidade'),
                faturamento=Sum(F('quantidade') * F('preco_unitario'))
            ).order_by('data')
        else:
            # Para todos os produtos
            evolucao_vendas = itens_vendidos.extra(
                select={'data': 'DATE(venda.data_venda)'}
            ).values('data').annotate(
                quantidade=Sum('quantidade'),
                faturamento=Sum(F('quantidade') * F('preco_unitario'))
            ).order_by('data')
        
        # Análise ABC dos produtos
        produtos_abc = []
        total_faturamento = sum(p['faturamento'] for p in ranking_produtos)
        
        if total_faturamento > 0:
            faturamento_acumulado = 0
            for produto in ranking_produtos:
                faturamento_acumulado += produto['faturamento']
                percentual_acumulado = (faturamento_acumulado / total_faturamento) * 100
                
                if percentual_acumulado <= 80:
                    classificacao = 'A'
                elif percentual_acumulado <= 95:
                    classificacao = 'B'
                else:
                    classificacao = 'C'
                
                produto['classificacao_abc'] = classificacao
                produto['percentual_acumulado'] = round(percentual_acumulado, 1)
                produtos_abc.append(produto)
        
        # Estatísticas gerais
        stats_gerais = itens_vendidos.aggregate(
            total_produtos_vendidos=Count('produto', distinct=True),
            quantidade_total=Sum('quantidade'),
            faturamento_total=Sum(F('quantidade') * F('preco_unitario')),
            ticket_medio=Avg(F('quantidade') * F('preco_unitario'))
        )
        
        # Produtos sem vendas no período
        produtos_sem_vendas = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).exclude(
            id__in=itens_vendidos.values('produto_id').distinct()
        ).count()
        
        # Filtros para formulário
        produtos_disponiveis = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('nome_comercial')[:1000]  # Limitar para performance
        
        categorias_disponiveis = Categoria.objects.filter(
            empresa=empresa,
            ativa=True
        ).order_by('nome')
        
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'ranking_produtos': ranking_produtos[:50],  # Limitar exibição
            'produtos_por_categoria': produtos_por_categoria,
            'produtos_por_marca': produtos_por_marca,
            'evolucao_vendas': list(evolucao_vendas),
            'produtos_abc': produtos_abc[:30],  # Top 30 para análise ABC
            'stats_gerais': stats_gerais,
            'produtos_sem_vendas': produtos_sem_vendas,
            'produtos_disponiveis': produtos_disponiveis,
            'categorias_disponiveis': categorias_disponiveis,
            'produto_selecionado': produto_id,
            'categoria_selecionada': categoria_id,
            'marca_selecionada': marca_id,
            'title': 'Relatório de Vendas por Produto'
        })
        
        return context


class RelatorioVendasCategoriaView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/categoria.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        categoria_id = self.request.GET.get('categoria_id')
        
        # Definir período padrão
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Vendas por categoria
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        )
        
        itens_query = ItemVenda.objects.filter(venda__in=vendas)
        
        if categoria_id:
            itens_query = itens_query.filter(produto__categoria_id=categoria_id)
        
        vendas_por_categoria = itens_query.values(
            'produto__categoria__nome',
            'produto__categoria__id'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario')),
            numero_produtos=Count('produto', distinct=True),
            numero_documentos=Count('venda', distinct=True),
            ticket_medio=Avg(F('quantidade') * F('preco_unitario'))
        ).order_by('-faturamento')
        
        # Calcular participação percentual
        faturamento_total = sum(item['faturamento'] for item in vendas_por_categoria)
        
        for categoria in vendas_por_categoria:
            categoria['participacao'] = (
                categoria['faturamento'] / faturamento_total * 100
            ) if faturamento_total > 0 else 0
            categoria['participacao'] = round(categoria['participacao'], 1)
        
        # Evolução das categorias por período
        evolucao_categorias = {}
        
        for categoria in vendas_por_categoria[:10]:  # Top 10 categorias
            evolucao = ItemVenda.objects.filter(
                venda__empresa=empresa,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim,
                venda__status='finalizada',
                produto__categoria_id=categoria['produto__categoria__id']
            ).extra(
                select={'data': 'DATE(venda.data_venda)'}
            ).values('data').annotate(
                faturamento=Sum(F('quantidade') * F('preco_unitario')),
                quantidade=Sum('quantidade')
            ).order_by('data')
            
            evolucao_categorias[categoria['produto__categoria__nome']] = list(evolucao)
        
        # Top produtos por categoria
        top_produtos_categoria = {}
        
        for categoria in vendas_por_categoria[:5]:  # Top 5 categorias
            produtos = ItemVenda.objects.filter(
                venda__empresa=empresa,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim,
                venda__status='finalizada',
                produto__categoria_id=categoria['produto__categoria__id']
            ).values(
                'produto__nome_comercial',
                'produto__codigo'
            ).annotate(
                quantidade_vendida=Sum('quantidade'),
                faturamento=Sum(F('quantidade') * F('preco_unitario'))
            ).order_by('-faturamento')[:5]
            
            top_produtos_categoria[categoria['produto__categoria__nome']] = list(produtos)
        
        # Análise de crescimento por categoria (comparar com período anterior)
        dias_periodo = (data_fim - data_inicio).days
        data_inicio_anterior = data_inicio - timedelta(days=dias_periodo)
        data_fim_anterior = data_inicio - timedelta(days=1)
        
        vendas_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio_anterior,
            data_venda__lte=data_fim_anterior,
            status='finalizada'
        )
        
        crescimento_categorias = []
        
        for categoria in vendas_por_categoria:
            vendas_categoria_anterior = ItemVenda.objects.filter(
                venda__in=vendas_anterior,
                produto__categoria_id=categoria['produto__categoria__id']
            ).aggregate(
                faturamento=Sum(F('quantidade') * F('preco_unitario'))
            )['faturamento'] or 0
            
            crescimento = 0
            if vendas_categoria_anterior > 0:
                crescimento = (
                    (categoria['faturamento'] - vendas_categoria_anterior) /
                    vendas_categoria_anterior * 100
                )
            
            crescimento_categorias.append({
                'categoria': categoria['produto__categoria__nome'],
                'faturamento_atual': categoria['faturamento'],
                'faturamento_anterior': vendas_categoria_anterior,
                'crescimento': round(crescimento, 1)
            })
        
        # Distribuição de margem por categoria
        margem_por_categoria = []
        
        for categoria in vendas_por_categoria:
            itens_categoria = ItemVenda.objects.filter(
                venda__empresa=empresa,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim,
                venda__status='finalizada',
                produto__categoria_id=categoria['produto__categoria__id']
            ).select_related('produto')
            
            margem_total = 0
            custo_total = 0
            
            for item in itens_categoria:
                preco_venda = item.preco_unitario * item.quantidade
                preco_custo = (item.produto.preco_custo or 0) * item.quantidade
                margem_total += preco_venda - preco_custo
                custo_total += preco_custo
            
            percentual_margem = 0
            if custo_total > 0:
                percentual_margem = (margem_total / custo_total) * 100
            
            margem_por_categoria.append({
                'categoria': categoria['produto__categoria__nome'],
                'margem_valor': margem_total,
                'percentual_margem': round(percentual_margem, 1)
            })
        
        # Categorias disponíveis para filtro
        categorias_disponiveis = Categoria.objects.filter(
            empresa=empresa,
            ativa=True
        ).order_by('nome')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'vendas_por_categoria': vendas_por_categoria,
            'evolucao_categorias': evolucao_categorias,
            'top_produtos_categoria': top_produtos_categoria,
            'crescimento_categorias': crescimento_categorias,
            'margem_por_categoria': margem_por_categoria,
            'faturamento_total': faturamento_total,
            'categorias_disponiveis': categorias_disponiveis,
            'categoria_selecionada': categoria_id,
            'title': 'Relatório de Vendas por Categoria'
        })
        
        return context


class RelatorioVendasVendedorView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/vendedor.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        vendedor_id = self.request.GET.get('vendedor_id')
        departamento_id = self.request.GET.get('departamento_id')
        
        # Definir período padrão
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Vendas por vendedor
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada',
            funcionario__isnull=False
        )
        
        if vendedor_id:
            vendas = vendas.filter(funcionario_id=vendedor_id)
        
        if departamento_id:
            vendas = vendas.filter(funcionario__departamento_id=departamento_id)
        
        vendas_por_vendedor = vendas.values(
            'funcionario__user__first_name',
            'funcionario__user__last_name',
            'funcionario__id',
            'funcionario__cargo__nome',
            'funcionario__departamento__nome'
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total'),
            ticket_medio=Avg('total'),
            total_itens=Sum('total_itens'),
            desconto_total=Sum('desconto')
        ).order_by('-faturamento')
        
        # Adicionar informações adicionais para cada vendedor
        vendedores_detalhado = []
        
        for vendedor_data in vendas_por_vendedor:
            vendedor_id_atual = vendedor_data['funcionario__id']
            vendedor_obj = Funcionario.objects.get(id=vendedor_id_atual)
            
            # Vendas do vendedor
            vendas_vendedor = vendas.filter(funcionario_id=vendedor_id_atual)
            
            # Clientes únicos atendidos
            clientes_unicos = vendas_vendedor.filter(
                cliente__isnull=False
            ).values('cliente').distinct().count()
            
            # Produtos vendidos
            produtos_vendidos = ItemVenda.objects.filter(
                venda__in=vendas_vendedor
            ).values('produto').distinct().count()
            
            # Meta do vendedor (se existir)
            meta_vendedor = MetricaKPI.objects.filter(
                funcionario=vendedor_obj,
                codigo='META_VENDAS_MENSAL',
                data_referencia__month=data_fim.month,
                data_referencia__year=data_fim.year
            ).first()
            
            percentual_meta = 0
            if meta_vendedor and meta_vendedor.valor_meta > 0:
                percentual_meta = (vendedor_data['faturamento'] / meta_vendedor.valor_meta) * 100
            
            # Comissão estimada (assumindo 5% do faturamento)
            comissao_estimada = vendedor_data['faturamento'] * Decimal('0.05')
            
            # Crescimento em relação ao período anterior
            dias_periodo = (data_fim - data_inicio).days
            data_inicio_anterior = data_inicio - timedelta(days=dias_periodo)
            data_fim_anterior = data_inicio - timedelta(days=1)
            
            vendas_periodo_anterior = Venda.objects.filter(
                empresa=empresa,
                funcionario_id=vendedor_id_atual,
                data_venda__gte=data_inicio_anterior,
                data_venda__lte=data_fim_anterior,
                status='finalizada'
            ).aggregate(Sum('total'))['total__sum'] or 0
            
            crescimento = 0
            if vendas_periodo_anterior > 0:
                crescimento = (
                    (vendedor_data['faturamento'] - vendas_periodo_anterior) /
                    vendas_periodo_anterior * 100
                )
            
            vendedores_detalhado.append({
                **vendedor_data,
                'vendedor_obj': vendedor_obj,
                'clientes_unicos': clientes_unicos,
                'produtos_vendidos': produtos_vendidos,
                'meta_vendedor': meta_vendedor,
                'percentual_meta': round(percentual_meta, 1),
                'comissao_estimada': comissao_estimada,
                'crescimento': round(crescimento, 1)
            })
        
        # Performance diária dos vendedores (top 5)
        top_vendedores_ids = [v['funcionario__id'] for v in vendas_por_vendedor[:5]]
        
        performance_diaria = vendas.filter(
            funcionario_id__in=top_vendedores_ids
        ).values(
            'data_venda',
            'funcionario__user__first_name',
            'funcionario__user__last_name',
            'funcionario__id'
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total')
        ).order_by('data_venda', '-faturamento')
        
        # Ranking de comissões
        ranking_comissoes = []
        for vendedor in vendedores_detalhado[:20]:  # Top 20
            ranking_comissoes.append({
                'vendedor': f"{vendedor['funcionario__user__first_name']} {vendedor['funcionario__user__last_name']}",
                'faturamento': vendedor['faturamento'],
                'comissao': vendedor['comissao_estimada'],
                'total_vendas': vendedor['total_vendas'],
                'ticket_medio': vendedor['ticket_medio']
            })
        
        # Vendas por departamento
        vendas_por_departamento = vendas.values(
            'funcionario__departamento__nome'
        ).annotate(
            total_vendas=Count('id'),
            faturamento=Sum('total'),
            vendedores=Count('funcionario', distinct=True)
        ).order_by('-faturamento')
        
        # Análise de produtividade
        dias_uteis_periodo = self._calcular_dias_uteis(data_inicio, data_fim)
        
        produtividade_vendedores = []
        for vendedor in vendedores_detalhado[:15]:
            vendas_por_dia = vendedor['total_vendas'] / dias_uteis_periodo if dias_uteis_periodo > 0 else 0
            faturamento_por_dia = vendedor['faturamento'] / dias_uteis_periodo if dias_uteis_periodo > 0 else 0
            
            produtividade_vendedores.append({
                'vendedor': f"{vendedor['funcionario__user__first_name']} {vendedor['funcionario__user__last_name']}",
                'vendas_por_dia': round(vendas_por_dia, 1),
                'faturamento_por_dia': round(faturamento_por_dia, 2),
                'clientes_por_venda': round(vendedor['clientes_unicos'] / vendedor['total_vendas'], 1) if vendedor['total_vendas'] > 0 else 0
            })
        
        # Filtros disponíveis
        vendedores_disponiveis = Funcionario.objects.filter(
            empresa=empresa,
            ativo=True,
            cargo__nome__icontains='vendedor'
        ).select_related('user', 'departamento')
        
        departamentos_disponiveis = Departamento.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('nome')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'vendedores_detalhado': vendedores_detalhado,
            'performance_diaria': performance_diaria,
            'ranking_comissoes': ranking_comissoes,
            'vendas_por_departamento': vendas_por_departamento,
            'produtividade_vendedores': produtividade_vendedores,
            'vendedores_disponiveis': vendedores_disponiveis,
            'departamentos_disponiveis': departamentos_disponiveis,
            'vendedor_selecionado': vendedor_id,
            'departamento_selecionado': departamento_id,
            'dias_uteis_periodo': dias_uteis_periodo,
            'title': 'Relatório de Vendas por Vendedor'
        })
        
        return context
    
    def _calcular_dias_uteis(self, data_inicio, data_fim):
        """Calcula o número de dias úteis entre duas datas (excluindo sábados e domingos)"""
        dias_uteis = 0
        current_date = data_inicio
        
        while current_date <= data_fim:
            # 0 = Segunda, 6 = Domingo
            if current_date.weekday() < 5:  # Segunda a Sexta
                dias_uteis += 1
            current_date += timedelta(days=1)
        
        return dias_uteis


class RelatorioVendasClienteView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/cliente.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        cliente_id = self.request.GET.get('cliente_id')
        tipo_pessoa = self.request.GET.get('tipo_pessoa')
        cidade = self.request.GET.get('cidade')
        
        # Definir período padrão
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Vendas por cliente
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada',
            cliente__isnull=False
        )
        
        if cliente_id:
            vendas = vendas.filter(cliente_id=cliente_id)
        
        if tipo_pessoa:
            vendas = vendas.filter(cliente__tipo_pessoa=tipo_pessoa)
        
        if cidade:
            vendas = vendas.filter(cliente__cidade__icontains=cidade)
        
        vendas_por_cliente = vendas.values(
            'cliente__nome',
            'cliente__cpf_cnpj',
            'cliente__id',
            'cliente__tipo_pessoa',
            'cliente__cidade',
            'cliente__telefone',
            'cliente__email'
        ).annotate(
            total_compras=Count('id'),
            total=Sum('total'),
            ticket_medio=Avg('total'),
            primeira_compra=Min('data_venda'),
            ultima_compra=Max('data_venda'),
            total_itens=Sum('total_itens')
        ).order_by('-total')[:200]  # Top 200 clientes
        
        # Análise RFM (Recência, Frequência, Valor Monetário)
        clientes_rfm = []
        
        for cliente_data in vendas_por_cliente[:100]:  # Top 100 para análise RFM
            # Recência (dias desde última compra)
            recencia = (data_fim - cliente_data['ultima_compra']).days
            
            # Frequência (número de compras)
            frequencia = cliente_data['total_compras']
            
            # Valor Monetário
            valor_monetario = cliente_data['total']
            
            # Classificação RFM simplificada
            score_recencia = 5 if recencia <= 7 else 4 if recencia <= 30 else 3 if recencia <= 90 else 2 if recencia <= 180 else 1
            score_frequencia = 5 if frequencia >= 10 else 4 if frequencia >= 5 else 3 if frequencia >= 3 else 2 if frequencia >= 2 else 1
            score_monetario = 5 if valor_monetario >= 5000 else 4 if valor_monetario >= 2000 else 3 if valor_monetario >= 1000 else 2 if valor_monetario >= 500 else 1
            
            # Determinar segmento
            if score_recencia >= 4 and score_frequencia >= 4 and score_monetario >= 4:
                segmento = 'Campeões'
            elif score_recencia >= 3 and score_frequencia >= 4:
                segmento = 'Clientes Fiéis'
            elif score_recencia >= 4 and score_monetario >= 4:
                segmento = 'Potenciais Fiéis'
            elif score_recencia >= 4:
                segmento = 'Novos Clientes'
            elif score_monetario >= 4:
                segmento = 'Não Podem Perder'
            elif score_frequencia >= 3:
                segmento = 'Promissores'
            elif recencia <= 90:
                segmento = 'Precisam de Atenção'
            elif recencia <= 180:
                segmento = 'Prestes a Dormir'
            else:
                segmento = 'Hibernando'
            
            clientes_rfm.append({
                'cliente': cliente_data,
                'recencia': recencia,
                'frequencia': frequencia,
                'valor_monetario': valor_monetario,
                'score_r': score_recencia,
                'score_f': score_frequencia,
                'score_m': score_monetario,
                'segmento': segmento
            })
        
        # Distribuição por segmento RFM
        segmentos_rfm = {}
        for cliente_rfm in clientes_rfm:
            segmento = cliente_rfm['segmento']
            if segmento not in segmentos_rfm:
                segmentos_rfm[segmento] = {'clientes': 0, 'valor': 0}
            segmentos_rfm[segmento]['clientes'] += 1
            segmentos_rfm[segmento]['valor'] += cliente_rfm['valor_monetario']
        
        # Top clientes por valor
        top_clientes_valor = vendas_por_cliente[:20]
        
        # Clientes por cidade
        clientes_por_cidade = vendas.values(
            'cliente__cidade'
        ).annotate(
            total_clientes=Count('cliente', distinct=True),
            faturamento_total=Sum('total')
        ).order_by('-faturamento_total')[:15]
        
        # Análise de fidelidade (baseada em recorrência)
        analise_fidelidade = []
        
        for cliente_data in vendas_por_cliente[:50]:
            cliente_vendas = vendas.filter(cliente_id=cliente_data['cliente__id'])
            
            # Calcular intervalos entre compras
            datas_compras = list(cliente_vendas.values_list('data_venda', flat=True).order_by('data_venda'))
            
            if len(datas_compras) > 1:
                intervalos = []
                for i in range(1, len(datas_compras)):
                    intervalo = (datas_compras[i] - datas_compras[i-1]).days
                    intervalos.append(intervalo)
                
                intervalo_medio = sum(intervalos) / len(intervalos)
                regularidade = 100 - min(100, (statistics.stdev(intervalos) / intervalo_medio * 100)) if len(intervalos) > 1 else 100
            else:
                intervalo_medio = 0
                regularidade = 0
            
            # Índice de fidelidade
            if cliente_data['total_compras'] >= 5 and regularidade >= 70:
                indice_fidelidade = 'Alto'
            elif cliente_data['total_compras'] >= 3 and regularidade >= 50:
                indice_fidelidade = 'Médio'
            elif cliente_data['total_compras'] >= 2:
                indice_fidelidade = 'Baixo'
            else:
                indice_fidelidade = 'Novo'
            
            analise_fidelidade.append({
                'cliente': cliente_data,
                'intervalo_medio': round(intervalo_medio, 1),
                'regularidade': round(regularidade, 1),
                'indice_fidelidade': indice_fidelidade
            })
        
        # Produtos preferidos por cliente (para clientes selecionados)
        produtos_por_cliente = {}
        
        if cliente_id:
            produtos_cliente = ItemVenda.objects.filter(
                venda__cliente_id=cliente_id,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim
            ).values(
                'produto__nome_comercial',
                'produto__categoria__nome'
            ).annotate(
                quantidade_total=Sum('quantidade'),
                total=Sum(F('quantidade') * F('preco_unitario'))
            ).order_by('-total')[:10]
            
            produtos_por_cliente[cliente_id] = list(produtos_cliente)
        
        # Estatísticas gerais
        stats_clientes = {
            'total_clientes_periodo': vendas.values('cliente').distinct().count(),
            'ticket_medio_geral': vendas.aggregate(Avg('total'))['total__avg'] or 0,
            'faturamento_total': vendas.aggregate(Sum('total'))['total__sum'] or 0,
            'clientes_recorrentes': vendas_por_cliente.filter(total_compras__gt=1).count()
        }
        
        # Filtros disponíveis
        clientes_disponiveis = Cliente.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('nome')[:1000]
        
        cidades_disponiveis = Cliente.objects.filter(
            empresa=empresa
        ).values_list('cidade', flat=True).distinct().order_by('cidade')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'vendas_por_cliente': vendas_por_cliente[:100],  # Limitar exibição
            'clientes_rfm': clientes_rfm,
            'segmentos_rfm': segmentos_rfm,
            'top_clientes_valor': top_clientes_valor,
            'clientes_por_cidade': clientes_por_cidade,
            'analise_fidelidade': analise_fidelidade,
            'produtos_por_cliente': produtos_por_cliente,
            'stats_clientes': stats_clientes,
            'clientes_disponiveis': clientes_disponiveis,
            'cidades_disponiveis': filter(None, cidades_disponiveis),
            'cliente_selecionado': cliente_id,
            'tipo_pessoa_selecionado': tipo_pessoa,
            'cidade_selecionada': cidade,
            'title': 'Relatório de Vendas por Cliente'
        })
        
        return context


class RelatorioVendasFormaPagamentoView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/vendas/forma_pagamento.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        forma_pagamento = self.request.GET.get('forma_pagamento')
        
        # Definir período padrão
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Vendas por forma de pagamento
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        )
        
        if forma_pagamento:
            vendas = vendas.filter(forma_pagamento=forma_pagamento)
        
        vendas_por_forma = vendas.values(
            'forma_pagamento'
        ).annotate(
            total_vendas=Count('id'),
            total=Sum('total'),
            ticket_medio=Avg('total'),
            valor_maximo=Max('total'),
            valor_minimo=Min('total')
        ).order_by('-total')
        
        # Calcular participação percentual
        total_geral = sum(item['total'] for item in vendas_por_forma)
        
        for forma in vendas_por_forma:
            forma['participacao'] = (
                forma['total'] / total_geral * 100
            ) if total_geral > 0 else 0
            forma['participacao'] = round(forma['participacao'], 1)
        
        # Evolução por forma de pagamento ao longo do período
        evolucao_formas = {}
        
        for forma in vendas_por_forma:
            evolucao = vendas.filter(
                forma_pagamento=forma['forma_pagamento']
            ).values('data_venda').annotate(
                valor=Sum('total'),
                quantidade=Count('id')
            ).order_by('data_venda')
            
            evolucao_formas[forma['forma_pagamento']] = list(evolucao)
        
        # Vendas por forma de pagamento e faixa de valor
        faixas_valor = [
            (0, 50, 'Até R$ 50'),
            (50, 100, 'R$ 50 - R$ 100'),
            (100, 200, 'R$ 100 - R$ 200'),
            (200, 500, 'R$ 200 - R$ 500'),
            (500, 1000, 'R$ 500 - R$ 1.000'),
            (1000, float('inf'), 'Acima de R$ 1.000')
        ]
        
        vendas_por_faixa = {}
        
        for forma in vendas_por_forma:
            vendas_forma = vendas.filter(forma_pagamento=forma['forma_pagamento'])
            faixas = []
            
            for min_val, max_val, faixa_nome in faixas_valor:
                if max_val == float('inf'):
                    count = vendas_forma.filter(total__gte=min_val).count()
                    valor = vendas_forma.filter(total__gte=min_val).aggregate(
                        Sum('total'))['total__sum'] or 0
                else:
                    count = vendas_forma.filter(
                        total__gte=min_val,
                        total__lt=max_val
                    ).count()
                    valor = vendas_forma.filter(
                        total__gte=min_val,
                        total__lt=max_val
                    ).aggregate(Sum('total'))['total__sum'] or 0
                
                faixas.append({
                    'faixa': faixa_nome,
                    'quantidade': count,
                    'valor': valor,
                    'percentual': (count / forma['total_vendas'] * 100) if forma['total_vendas'] > 0 else 0
                })
            
            vendas_por_faixa[forma['forma_pagamento']] = faixas
        
        # Análise por período do dia
        vendas_por_periodo = {}
        
        periodos = [
            ('manha', 'Manhã', 6, 11),
            ('tarde', 'Tarde', 12, 17),
            ('noite', 'Noite', 18, 23)
        ]
        
        for codigo, nome, hora_inicio, hora_fim in periodos:
            vendas_periodo = vendas.extra(
                where=["EXTRACT(hour FROM created_at) BETWEEN %s AND %s"],
                params=[hora_inicio, hora_fim]
            ).values('forma_pagamento').annotate(
                total=Sum('total'),
                quantidade=Count('id')
            ).order_by('-total')
            
            vendas_por_periodo[nome] = list(vendas_periodo)
        
        # Comparação com período anterior
        dias_periodo = (data_fim - data_inicio).days
        data_inicio_anterior = data_inicio - timedelta(days=dias_periodo)
        data_fim_anterior = data_inicio - timedelta(days=1)
        
        vendas_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio_anterior,
            data_venda__lte=data_fim_anterior,
            status='finalizada'
        ).values('forma_pagamento').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        # Criar dicionário para fácil acesso
        vendas_anterior_dict = {
            v['forma_pagamento']: v for v in vendas_anterior
        }
        
        # Calcular crescimento por forma de pagamento
        crescimento_formas = []
        
        for forma in vendas_por_forma:
            forma_nome = forma['forma_pagamento']
            vendas_ant = vendas_anterior_dict.get(forma_nome, {'total': 0, 'quantidade': 0})
            
            crescimento_valor = 0
            crescimento_qtd = 0
            
            if vendas_ant['total'] > 0:
                crescimento_valor = (
                    (forma['total'] - vendas_ant['total']) /
                    vendas_ant['total'] * 100
                )
            
            if vendas_ant['quantidade'] > 0:
                crescimento_qtd = (
                    (forma['total_vendas'] - vendas_ant['quantidade']) /
                    vendas_ant['quantidade'] * 100
                )
            
            crescimento_formas.append({
                'forma_pagamento': forma_nome,
                'crescimento_valor': round(crescimento_valor, 1),
                'crescimento_quantidade': round(crescimento_qtd, 1)
            })
        
        # Análise de concentração (índice Herfindahl)
        # Mede a concentração de mercado por forma de pagamento
        indice_concentracao = sum(
            (forma['participacao'] / 100) ** 2 for forma in vendas_por_forma
        )
        
        # Classificação da concentração
        if indice_concentracao < 0.15:
            nivel_concentracao = 'Baixa'
        elif indice_concentracao < 0.25:
            nivel_concentracao = 'Moderada'
        else:
            nivel_concentracao = 'Alta'
        
        # Formas de pagamento disponíveis
        formas_disponiveis = vendas.values_list(
            'forma_pagamento', flat=True
        ).distinct().order_by('forma_pagamento')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'vendas_por_forma': vendas_por_forma,
            'evolucao_formas': evolucao_formas,
            'vendas_por_faixa': vendas_por_faixa,
            'vendas_por_periodo': vendas_por_periodo,
            'crescimento_formas': crescimento_formas,
            'total_geral': total_geral,
            'indice_concentracao': round(indice_concentracao, 3),
            'nivel_concentracao': nivel_concentracao,
            'formas_disponiveis': formas_disponiveis,
            'forma_selecionada': forma_pagamento,
            'title': 'Relatório de Vendas por Forma de Pagamento'
        })
        
        return context

# =====================================
# RELATÓRIOS DE ESTOQUE
# =====================================

class RelatoriosEstoqueView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Estatísticas gerais de estoque
        hoje = timezone.now().date()
        
        # Total de produtos
        total_produtos = Produto.objects.filter(empresa=empresa, ativo=True).count()
        
        # Produtos com estoque baixo
        produtos_estoque_baixo = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual__lte=F('estoque_minimo')
        ).count()
        
        # Produtos sem estoque
        produtos_sem_estoque = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual=0
        ).count()
        
        # Valor total do estoque
        total_estoque = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).aggregate(
            total=Sum(F('estoque_atual') * F('preco_custo'))
        )['total'] or 0
        
        # Movimentações do dia
        movimentacoes_hoje = MovimentacaoEstoque.objects.filter(
            produto__empresa=empresa,
            updated_at=hoje
        ).count()
        
        # Produtos vencidos/próximos ao vencimento
        produtos_vencendo = AlertaEstoque.objects.filter(
            produto__empresa=empresa,
            data_notificacao__lte=hoje + timedelta(days=30),
            data_notificacao__gte=hoje
        ).count()
        
        produtos_vencidos = AlertaEstoque.objects.filter(
            produto__empresa=empresa,
            data_notificacao__lt=hoje
        ).count()
        
        # Giro de estoque (últimos 12 meses)
        vendas_12_meses = ItemVenda.objects.filter(
            venda__empresa=empresa,
            venda__data_venda__gte=hoje - timedelta(days=365),
            venda__status='finalizada'
        ).aggregate(
            quantidade_vendida=Sum('quantidade')
        )['quantidade_vendida'] or 0
        
        estoque_medio = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).aggregate(
            estoque_medio=Avg('estoque_atual')
        )['estoque_medio'] or 0
        
        giro_estoque_anual = vendas_12_meses / estoque_medio if estoque_medio > 0 else 0
        
        # Top categorias por valor de estoque
        estoque_por_categoria = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).values(
            'categoria__nome'
        ).annotate(
            valor_estoque=Sum(F('estoque_atual') * F('preco_custo')),
            quantidade_produtos=Count('id'),
            quantidade_itens=Sum('estoque_atual')
        ).order_by('-valor_estoque')[:10]
        
        # Movimentações recentes
        movimentacoes_recentes = MovimentacaoEstoque.objects.filter(
            produto__empresa=empresa
        ).select_related('produto').order_by('-updated_at')[:10]
        
        # Produtos mais vendidos (impacto no estoque)
        produtos_mais_vendidos = ItemVenda.objects.filter(
            venda__empresa=empresa,
            venda__data_venda__gte=hoje - timedelta(days=30),
            venda__status='finalizada'
        ).values(
            'produto__nome_produto',
            'produto__estoque_atual',
            'produto__estoque_minimo'
        ).annotate(
            quantidade_vendida=Sum('quantidade')
        ).order_by('-quantidade_vendida')[:10]
        
        stats_estoque = {
            'total_produtos': total_produtos,
            'produtos_estoque_baixo': produtos_estoque_baixo,
            'produtos_sem_estoque': produtos_sem_estoque,
            'total_estoque': total_estoque,
            'movimentacoes_hoje': movimentacoes_hoje,
            'produtos_vencendo': produtos_vencendo,
            'produtos_vencidos': produtos_vencidos,
            'giro_estoque_anual': round(giro_estoque_anual, 2)
        }
        
        context.update({
            'stats_estoque': stats_estoque,
            'estoque_por_categoria': estoque_por_categoria,
            'movimentacoes_recentes': movimentacoes_recentes,
            'produtos_mais_vendidos': produtos_mais_vendidos,
            'title': 'Relatórios de Estoque'
        })
        
        return context


class RelatorioPosicaoEstoqueView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/posicao.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        categoria_id = self.request.GET.get('categoria_id')
        marca_id = self.request.GET.get('marca_id')
        situacao = self.request.GET.get('situacao')
        busca = self.request.GET.get('busca')
        
        # Query base
        produtos = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).select_related('categoria', 'marca')
        
        # Aplicar filtros
        if categoria_id:
            produtos = produtos.filter(categoria_id=categoria_id)
        
        if marca_id:
            produtos = produtos.filter(marca_id=marca_id)
        
        if busca:
            produtos = produtos.filter(
                Q(nome_comercial__icontains=busca) |
                Q(codigo__icontains=busca)
            )
        
        # Filtrar por situação do estoque
        if situacao == 'baixo':
            produtos = produtos.filter(estoque_atual__lte=F('estoque_minimo'))
        elif situacao == 'zerado':
            produtos = produtos.filter(estoque_atual=0)
        elif situacao == 'acima_maximo':
            produtos = produtos.filter(estoque_atual__gte=F('estoque_maximo'))
        elif situacao == 'normal':
            produtos = produtos.filter(
                estoque_atual__gt=F('estoque_minimo'),
                estoque_atual__lt=F('estoque_maximo')
            )
        
        # Calcular informações adicionais
        posicao_estoque = []
        
        for produto in produtos:
            # Vendas últimos 30 dias
            vendas_30_dias = ItemVenda.objects.filter(
                produto=produto,
                venda__data_venda__gte=timezone.now().date() - timedelta(days=30),
                venda__status='finalizada'
            ).aggregate(Sum('quantidade'))['quantidade__sum'] or 0
            
            # Média de vendas diárias
            media_vendas_diaria = vendas_30_dias / 30
            
            # Dias de estoque (baseado na média de vendas)
            dias_estoque = produto.estoque_atual / media_vendas_diaria if media_vendas_diaria > 0 else float('inf')
            
            # Valor do estoque
            valor_estoque = produto.estoque_atual * (produto.preco_custo or 0)
            
            # Classificação da situação
            if produto.estoque_atual == 0:
                situacao_estoque = 'Zerado'
                cor_situacao = 'danger'
            elif produto.estoque_atual <= produto.estoque_minimo:
                situacao_estoque = 'Baixo'
                cor_situacao = 'warning'
            elif produto.estoque_maximo and produto.estoque_atual >= produto.estoque_maximo:
                situacao_estoque = 'Excesso'
                cor_situacao = 'info'
            else:
                situacao_estoque = 'Normal'
                cor_situacao = 'success'
            
            # Última movimentação
            ultima_movimentacao = MovimentacaoEstoque.objects.filter(
                produto=produto
            ).order_by('-updated_at').first()
            
            posicao_estoque.append({
                'produto': produto,
                'vendas_30_dias': vendas_30_dias,
                'media_vendas_diaria': round(media_vendas_diaria, 2),
                'dias_estoque': round(dias_estoque, 1) if dias_estoque != float('inf') else 'Infinito',
                'valor_estoque': valor_estoque,
                'situacao_estoque': situacao_estoque,
                'cor_situacao': cor_situacao,
                'ultima_movimentacao': ultima_movimentacao
            })
        
        # Ordenar por situação crítica primeiro
        posicao_estoque.sort(key=lambda x: (
            0 if x['situacao_estoque'] == 'Zerado' else
            1 if x['situacao_estoque'] == 'Baixo' else
            2 if x['situacao_estoque'] == 'Excesso' else 3
        ))
        
        # Paginação
        paginator = Paginator(posicao_estoque, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Resumo por situação
        resumo_situacao = {
            'zerado': len([p for p in posicao_estoque if p['situacao_estoque'] == 'Zerado']),
            'baixo': len([p for p in posicao_estoque if p['situacao_estoque'] == 'Baixo']),
            'normal': len([p for p in posicao_estoque if p['situacao_estoque'] == 'Normal']),
            'excesso': len([p for p in posicao_estoque if p['situacao_estoque'] == 'Excesso'])
        }
        
        # Valor total por situação
        valor_por_situacao = {}
        for situacao_nome in ['Zerado', 'Baixo', 'Normal', 'Excesso']:
            valor_por_situacao[situacao_nome.lower()] = sum(
                p['valor_estoque'] for p in posicao_estoque 
                if p['situacao_estoque'] == situacao_nome
            )
        
        # Filtros disponíveis
        categorias = Categoria.objects.filter(empresa=empresa, ativa=True).order_by('nome')
        
        context.update({
            'page_obj': page_obj,
            'resumo_situacao': resumo_situacao,
            'valor_por_situacao': valor_por_situacao,
            'categorias': categorias,
            'filtros': {
                'categoria_id': categoria_id,
                'marca_id': marca_id,
                'situacao': situacao,
                'busca': busca
            },
            'title': 'Posição de Estoque'
        })
        
        return context


class RelatorioMovimentacaoEstoqueView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/movimentacao.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        tipo_movimentacao = self.request.GET.get('tipo_movimentacao')
        produto_id = self.request.GET.get('produto_id')
        
        # Definir período padrão (últimos 30 dias)
        if not data_inicio:
            data_inicio = timezone.now().date() - timedelta(days=30)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            data_fim = timezone.now().date()
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        # Movimentações do período
        movimentacoes = MovimentacaoEstoque.objects.filter(
            produto__empresa=empresa,
            updated_at__gte=data_inicio,
            updated_at__lte=data_fim
        ).select_related('produto', 'usuario')
        
        if tipo_movimentacao:
            movimentacoes = movimentacoes.filter(tipo_movimentacao=tipo_movimentacao)
        
        if produto_id:
            movimentacoes = movimentacoes.filter(produto_id=produto_id)
        
        movimentacoes = movimentacoes.order_by('-updated_at')
        
        # Estatísticas das movimentações
        stats_movimentacao = movimentacoes.aggregate(
            total_movimentacoes=Count('id'),
            total_entradas=Count(Case(When(tipo_movimentacao='entrada', then=1))),
            total_saidas=Count(Case(When(tipo_movimentacao='saida', then=1))),
            total_ajustes=Count(Case(When(tipo_movimentacao='ajuste', then=1))),
            quantidade_entrada=Sum(
                Case(When(tipo_movimentacao='entrada', then='quantidade'), default=0)
            ),
            quantidade_saida=Sum(
                Case(When(tipo_movimentacao='saida', then='quantidade'), default=0)
            )
        )
        
        # Movimentações por dia
        movimentacoes_por_dia = movimentacoes.values('updated_at').annotate(
            total=Count('id'),
            entradas=Count(Case(When(tipo_movimentacao='entrada', then=1))),
            saidas=Count(Case(When(tipo_movimentacao='saida', then=1)))
        ).order_by('updated_at')
        
        # Produtos com mais movimentações
        produtos_movimento = movimentacoes.values(
            'produto__nome_comercial',
            'produto__codigo',
            'produto__id'
        ).annotate(
            total_movimentacoes=Count('id'),
            total_entradas=Count(Case(When(tipo_movimentacao='entrada', then=1))),
            total_saidas=Count(Case(When(tipo_movimentacao='saida', then=1))),
            saldo_movimentacao=Sum(
                Case(
                    When(tipo_movimentacao='entrada', then='quantidade'),
                    When(tipo_movimentacao='saida', then=-F('quantidade')),
                    default=0
                )
            )
        ).order_by('-total_movimentacoes')[:20]
        
        # Movimentações por usuário
        movimentacoes_usuario = movimentacoes.values(
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total_movimentacoes=Count('id'),
            entradas=Count(Case(When(tipo_movimentacao='entrada', then=1))),
            saidas=Count(Case(When(tipo_movimentacao='saida', then=1)))
        ).order_by('-total_movimentacoes')
        
        # Análise de motivos de movimentação
        motivos_movimentacao = movimentacoes.values('motivo').annotate(
            total=Count('id'),
            quantidade_total=Sum('quantidade')
        ).order_by('-total')
        
        # Movimentações por categoria
        movimentacoes_categoria = movimentacoes.values(
            'produto__categoria__nome'
        ).annotate(
            total_movimentacoes=Count('id'),
            quantidade_total=Sum('quantidade')
        ).order_by('-total_movimentacoes')
        
        # Paginação
        paginator = Paginator(movimentacoes, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Produtos para filtro
        produtos_com_movimento = Produto.objects.filter(
            id__in=movimentacoes.values('produto_id').distinct()
        ).order_by('nome_comercial')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'page_obj': page_obj,
            'stats_movimentacao': stats_movimentacao,
            'movimentacoes_por_dia': list(movimentacoes_por_dia),
            'produtos_movimento': produtos_movimento,
            'movimentacoes_usuario': movimentacoes_usuario,
            'motivos_movimentacao': motivos_movimentacao,
            'movimentacoes_categoria': movimentacoes_categoria,
            'produtos_com_movimento': produtos_com_movimento,
            'filtros': {
                'tipo_movimentacao': tipo_movimentacao,
                'produto_id': produto_id
            },
            'title': 'Relatório de Movimentação de Estoque'
        })
        
        return context


class RelatorioVencimentosView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/vencimentos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        situacao = self.request.GET.get('situacao', 'todos')
        categoria_id = self.request.GET.get('categoria_id')
        dias_vencimento = int(self.request.GET.get('dias_vencimento', 30))
        
        hoje = timezone.now().date()
        data_limite = hoje + timedelta(days=dias_vencimento)
        
        # Query base
        controles_vencimento = ControleVencimento.objects.filter(
            produto__empresa=empresa,
            produto__ativo=True
        ).select_related('produto')
        
        if categoria_id:
            controles_vencimento = controles_vencimento.filter(
                produto__categoria_id=categoria_id
            )
        
        # Filtrar por situação
        if situacao == 'vencidos':
            controles_vencimento = controles_vencimento.filter(data_vencimento__lt=hoje)
        elif situacao == 'vencendo':
            controles_vencimento = controles_vencimento.filter(
                data_vencimento__gte=hoje,
                data_vencimento__lte=data_limite
            )
        elif situacao == 'validos':
            controles_vencimento = controles_vencimento.filter(data_vencimento__gt=data_limite)
        
        controles_vencimento = controles_vencimento.order_by('data_vencimento')
        
        # Classificar e calcular informações
        produtos_vencimento = []
        
        for controle in controles_vencimento:
            dias_para_vencer = (controle.data_vencimento - hoje).days
            
            # Determinar situação
            if dias_para_vencer < 0:
                situacao_item = 'Vencido'
                cor_situacao = 'danger'
                prioridade = 1
            elif dias_para_vencer <= 7:
                situacao_item = 'Vence em 7 dias'
                cor_situacao = 'danger'
                prioridade = 2
            elif dias_para_vencer <= 30:
                situacao_item = 'Vence em 30 dias'
                cor_situacao = 'warning'
                prioridade = 3
            elif dias_para_vencer <= 90:
                situacao_item = 'Vence em 90 dias'
                cor_situacao = 'info'
                prioridade = 4
            else:
                situacao_item = 'Válido'
                cor_situacao = 'success'
                prioridade = 5
            
            # Valor do lote
            valor_lote = controle.quantidade * (controle.produto.preco_custo or 0)
            
            produtos_vencimento.append({
                'controle': controle,
                'dias_para_vencer': dias_para_vencer,
                'situacao_item': situacao_item,
                'cor_situacao': cor_situacao,
                'prioridade': prioridade,
                'valor_lote': valor_lote
            })
        
        # Ordenar por prioridade
        produtos_vencimento.sort(key=lambda x: (x['prioridade'], x['dias_para_vencer']))
        
        # Estatísticas de vencimento
        stats_vencimento = {
            'total_lotes': len(produtos_vencimento),
            'lotes_vencidos': len([p for p in produtos_vencimento if p['situacao_item'] == 'Vencido']),
            'lotes_vencendo_7_dias': len([p for p in produtos_vencimento if p['situacao_item'] == 'Vence em 7 dias']),
            'lotes_vencendo_30_dias': len([p for p in produtos_vencimento if p['situacao_item'] == 'Vence em 30 dias']),
            'total_vencidos': sum(p['valor_lote'] for p in produtos_vencimento if p['situacao_item'] == 'Vencido'),
            'total_vencendo': sum(p['valor_lote'] for p in produtos_vencimento if 'Vence em' in p['situacao_item'])
        }
        
        # Produtos com mais lotes próximos ao vencimento
        produtos_criticos = {}
        for item in produtos_vencimento:
            if item['prioridade'] <= 3:  # Vencidos ou vencendo em até 30 dias
                produto_id = item['controle'].produto.id
                if produto_id not in produtos_criticos:
                    produtos_criticos[produto_id] = {
                        'produto': item['controle'].produto,
                        'lotes_criticos': 0,
                        'quantidade_critica': 0,
                        'valor_critico': 0
                    }
                
                produtos_criticos[produto_id]['lotes_criticos'] += 1
                produtos_criticos[produto_id]['quantidade_critica'] += item['controle'].quantidade
                produtos_criticos[produto_id]['valor_critico'] += item['valor_lote']
        
        produtos_criticos = sorted(
            produtos_criticos.values(),
            key=lambda x: x['valor_critico'],
            reverse=True
        )[:20]
        
        # Vencimentos por categoria
        vencimentos_categoria = {}
        for item in produtos_vencimento:
            categoria = item['controle'].produto.categoria
            categoria_nome = categoria.nome if categoria else 'Sem Categoria'
            
            if categoria_nome not in vencimentos_categoria:
                vencimentos_categoria[categoria_nome] = {
                    'total_lotes': 0,
                    'lotes_vencidos': 0,
                    'lotes_vencendo': 0,
                    'total': 0
                }
            
            vencimentos_categoria[categoria_nome]['total_lotes'] += 1
            vencimentos_categoria[categoria_nome]['total'] += item['valor_lote']
            
            if item['situacao_item'] == 'Vencido':
                vencimentos_categoria[categoria_nome]['lotes_vencidos'] += 1
            elif 'Vence em' in item['situacao_item']:
                vencimentos_categoria[categoria_nome]['lotes_vencendo'] += 1
        
        # Evolução dos vencimentos (próximos 90 dias)
        evolucao_vencimentos = []
        for i in range(90):
            data_check = hoje + timedelta(days=i)
            lotes_dia = len([
                p for p in produtos_vencimento 
                if p['controle'].data_vencimento == data_check
            ])
            
            if lotes_dia > 0:
                evolucao_vencimentos.append({
                    'data': data_check,
                    'lotes': lotes_dia
                })
        
        # Paginação
        paginator = Paginator(produtos_vencimento, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Categorias para filtro
        categorias = Categoria.objects.filter(empresa=empresa, ativa=True).order_by('nome')
        
        context.update({
            'page_obj': page_obj,
            'stats_vencimento': stats_vencimento,
            'produtos_criticos': produtos_criticos,
            'vencimentos_categoria': vencimentos_categoria,
            'evolucao_vencimentos': evolucao_vencimentos,
            'categorias': categorias,
            'filtros': {
                'situacao': situacao,
                'categoria_id': categoria_id,
                'dias_vencimento': dias_vencimento
            },
            'title': 'Relatório de Vencimentos'
        })
        
        return context


class RelatorioRupturaEstoqueView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/ruptura.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Produtos em ruptura (estoque zerado)
        produtos_ruptura = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual=0
        ).select_related('categoria', 'marca')
        
        # Análise detalhada de cada produto em ruptura
        analise_ruptura = []
        
        for produto in produtos_ruptura:
            # Última venda
            ultima_venda = ItemVenda.objects.filter(
                produto=produto,
                venda__status='finalizada'
            ).order_by('-venda__data_venda').first()
            
            # Vendas últimos 30 dias antes da ruptura
            vendas_30_dias = ItemVenda.objects.filter(
                produto=produto,
                venda__data_venda__gte=timezone.now().date() - timedelta(days=30),
                venda__status='finalizada'
            ).aggregate(Sum('quantidade'))['quantidade__sum'] or 0
            
            # Última entrada no estoque
            ultima_entrada = MovimentacaoEstoque.objects.filter(
                produto=produto,
                tipo_movimentacao='entrada'
            ).order_by('-updated_at').first()
            
            # Tempo em ruptura
            if ultima_venda:
                dias_ruptura = (timezone.now().date() - ultima_venda.venda.data_venda).days
            else:
                dias_ruptura = None
            
            # Perda estimada de vendas
            if vendas_30_dias > 0:
                media_vendas_diaria = vendas_30_dias / 30
                perda_estimada = media_vendas_diaria * dias_ruptura if dias_ruptura else 0
                valor_perda = perda_estimada * (produto.preco_venda or 0)
            else:
                perda_estimada = 0
                valor_perda = 0
            
            # Classificar criticidade
            if vendas_30_dias >= 30:  # Mais de 1 venda por dia
                criticidade = 'Alta'
                cor_criticidade = 'danger'
            elif vendas_30_dias >= 10:  # Mais de 1 venda a cada 3 dias
                criticidade = 'Média'
                cor_criticidade = 'warning'
            elif vendas_30_dias > 0:
                criticidade = 'Baixa'
                cor_criticidade = 'info'
            else:
                criticidade = 'Sem Vendas'
                cor_criticidade = 'secondary'
            
            analise_ruptura.append({
                'produto': produto,
                'ultima_venda': ultima_venda,
                'vendas_30_dias': vendas_30_dias,
                'ultima_entrada': ultima_entrada,
                'dias_ruptura': dias_ruptura,
                'perda_estimada': round(perda_estimada, 2),
                'valor_perda': valor_perda,
                'criticidade': criticidade,
                'cor_criticidade': cor_criticidade
            })
        
        # Ordenar por criticidade e valor de perda
        analise_ruptura.sort(key=lambda x: (
            0 if x['criticidade'] == 'Alta' else
            1 if x['criticidade'] == 'Média' else
            2 if x['criticidade'] == 'Baixa' else 3,
            -x['valor_perda']
        ))
        
        # Estatísticas de ruptura
        stats_ruptura = {
            'total_produtos_ruptura': len(analise_ruptura),
            'ruptura_alta_criticidade': len([a for a in analise_ruptura if a['criticidade'] == 'Alta']),
            'ruptura_media_criticidade': len([a for a in analise_ruptura if a['criticidade'] == 'Média']),
            'total_perda': sum(a['valor_perda'] for a in analise_ruptura),
            'produtos_sem_vendas': len([a for a in analise_ruptura if a['criticidade'] == 'Sem Vendas'])
        }
        
        # Ruptura por categoria
        ruptura_por_categoria = {}
        for item in analise_ruptura:
            categoria = item['produto'].categoria
            categoria_nome = categoria.nome if categoria else 'Sem Categoria'
            
            if categoria_nome not in ruptura_por_categoria:
                ruptura_por_categoria[categoria_nome] = {
                    'produtos': 0,
                    'alta_criticidade': 0,
                    'valor_perda': 0
                }
            
            ruptura_por_categoria[categoria_nome]['produtos'] += 1
            ruptura_por_categoria[categoria_nome]['valor_perda'] += item['valor_perda']
            
            if item['criticidade'] == 'Alta':
                ruptura_por_categoria[categoria_nome]['alta_criticidade'] += 1
        
        # Produtos que podem substituir os em ruptura
        sugestoes_reposicao = []
        
        for item in analise_ruptura[:10]:  # Top 10 produtos críticos
            produto_ruptura = item['produto']
            
            # Buscar produtos similares (mesma categoria)
            produtos_similares = Produto.objects.filter(
                empresa=empresa,
                ativo=True,
                categoria=produto_ruptura.categoria,
                estoque_atual__gt=0
            ).exclude(id=produto_ruptura.id)[:3]
            
            if produtos_similares.exists():
                sugestoes_reposicao.append({
                    'produto_ruptura': produto_ruptura,
                    'criticidade': item['criticidade'],
                    'produtos_similares': produtos_similares
                })
        
        # Histórico de rupturas (produtos que voltaram ao estoque)
        produtos_repostos = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual__gt=0
        ).annotate(
            ruptura_recente=Case(
                When(
                    movimentacaoestoque__tipo_movimentacao='entrada',
                    movimentacaoestoque__updated_at__gte=timezone.now().date() - timedelta(days=7),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=models.BooleanField()
            )
        ).filter(ruptura_recente=True)
        
        # Produtos com risco de ruptura
        risco_ruptura = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual__gt=0,
            estoque_atual__lte=F('estoque_minimo')
        ).select_related('categoria')
        
        # Calcular dias para ruptura baseado na média de vendas
        produtos_risco = []
        
        for produto in risco_ruptura[:20]:
            vendas_30_dias = ItemVenda.objects.filter(
                produto=produto,
                venda__data_venda__gte=timezone.now().date() - timedelta(days=30),
                venda__status='finalizada'
            ).aggregate(Sum('quantidade'))['quantidade__sum'] or 0
            
            if vendas_30_dias > 0:
                media_vendas_diaria = vendas_30_dias / 30
                dias_para_ruptura = produto.estoque_atual / media_vendas_diaria
                
                produtos_risco.append({
                    'produto': produto,
                    'dias_para_ruptura': round(dias_para_ruptura, 1),
                    'vendas_30_dias': vendas_30_dias
                })
        
        produtos_risco.sort(key=lambda x: x['dias_para_ruptura'])
        
        context.update({
            'analise_ruptura': analise_ruptura,
            'stats_ruptura': stats_ruptura,
            'ruptura_por_categoria': ruptura_por_categoria,
            'sugestoes_reposicao': sugestoes_reposicao,
            'produtos_repostos': produtos_repostos,
            'produtos_risco': produtos_risco,
            'title': 'Relatório de Ruptura de Estoque'
        })
        
        return context


class RelatorioGiroEstoqueView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/giro.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        periodo = int(self.request.GET.get('periodo', 90))  # Dias
        categoria_id = self.request.GET.get('categoria_id')
        
        data_inicio = timezone.now().date() - timedelta(days=periodo)
        data_fim = timezone.now().date()
        
        # Produtos para análise
        produtos = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual__gt=0
        ).select_related('categoria', 'marca')
        
        if categoria_id:
            produtos = produtos.filter(categoria_id=categoria_id)
        
        # Análise de giro por produto
        analise_giro = []
        
        for produto in produtos:
            # Vendas no período
            vendas_periodo = ItemVenda.objects.filter(
                produto=produto,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim,
                venda__status='finalizada'
            ).aggregate(
                quantidade_vendida=Sum('quantidade'),
                valor_vendido=Sum(F('quantidade') * F('preco_unitario'))
            )
            
            quantidade_vendida = vendas_periodo['quantidade_vendida'] or 0
            valor_vendido = vendas_periodo['valor_vendido'] or 0
            
            # Estoque médio (simplificado - usando estoque atual)
            estoque_medio = produto.estoque_atual
            
            # Calcular giro
            if estoque_medio > 0:
                giro_periodo = quantidade_vendida / estoque_medio
                giro_anual = (giro_periodo * 365) / periodo
            else:
                giro_periodo = 0
                giro_anual = 0
            
            # Dias de estoque
            if quantidade_vendida > 0:
                media_vendas_diaria = quantidade_vendida / periodo
                dias_estoque = estoque_medio / media_vendas_diaria
            else:
                dias_estoque = float('inf')
            
            # Classificação do giro
            if giro_anual >= 12:  # Mais de 1 giro por mês
                classificacao_giro = 'Alto'
                cor_giro = 'success'
            elif giro_anual >= 6:  # Giro a cada 2 meses
                classificacao_giro = 'Médio'
                cor_giro = 'warning'
            elif giro_anual >= 2:  # Giro a cada 6 meses
                classificacao_giro = 'Baixo'
                cor_giro = 'info'
            else:
                classificacao_giro = 'Muito Baixo'
                cor_giro = 'danger'
            
            # Valor investido no estoque
            valor_estoque = produto.estoque_atual * (produto.preco_custo or 0)
            
            analise_giro.append({
                'produto': produto,
                'quantidade_vendida': quantidade_vendida,
                'valor_vendido': valor_vendido,
                'estoque_atual': produto.estoque_atual,
                'giro_periodo': round(giro_periodo, 2),
                'giro_anual': round(giro_anual, 2),
                'dias_estoque': round(dias_estoque, 1) if dias_estoque != float('inf') else 'Sem Vendas',
                'classificacao_giro': classificacao_giro,
                'cor_giro': cor_giro,
                'valor_estoque': valor_estoque
            })
        
        # Ordenar por giro anual (maiores primeiro)
        analise_giro.sort(key=lambda x: x['giro_anual'], reverse=True)
        
        # Estatísticas de giro
        giros_validos = [a['giro_anual'] for a in analise_giro if a['giro_anual'] > 0]
        
        stats_giro = {
            'total_produtos': len(analise_giro),
            'giro_alto': len([a for a in analise_giro if a['classificacao_giro'] == 'Alto']),
            'giro_medio': len([a for a in analise_giro if a['classificacao_giro'] == 'Médio']),
            'giro_baixo': len([a for a in analise_giro if a['classificacao_giro'] == 'Baixo']),
            'giro_muito_baixo': len([a for a in analise_giro if a['classificacao_giro'] == 'Muito Baixo']),
            'giro_medio_empresa': statistics.mean(giros_validos) if giros_validos else 0,
            'total_estoque': sum(a['valor_estoque'] for a in analise_giro)
        }
        
        # Giro por categoria
        giro_por_categoria = {}
        
        for item in analise_giro:
            categoria = item['produto'].categoria
            categoria_nome = categoria.nome if categoria else 'Sem Categoria'
            
            if categoria_nome not in giro_por_categoria:
                giro_por_categoria[categoria_nome] = {
                    'produtos': 0,
                    'giro_total': 0,
                    'valor_estoque': 0,
                    'valor_vendido': 0
                }
            
            giro_por_categoria[categoria_nome]['produtos'] += 1
            giro_por_categoria[categoria_nome]['giro_total'] += item['giro_anual']
            giro_por_categoria[categoria_nome]['valor_estoque'] += item['valor_estoque']
            giro_por_categoria[categoria_nome]['valor_vendido'] += item['valor_vendido']
        
        # Calcular giro médio por categoria
        for categoria in giro_por_categoria:
            if giro_por_categoria[categoria]['produtos'] > 0:
                giro_por_categoria[categoria]['giro_medio'] = (
                    giro_por_categoria[categoria]['giro_total'] /
                    giro_por_categoria[categoria]['produtos']
                )
            else:
                giro_por_categoria[categoria]['giro_medio'] = 0
        
        # Top produtos por giro
        top_giro = analise_giro[:20]
        
        # Produtos com giro muito baixo (candidatos à promoção/liquidação)
        baixo_giro = [a for a in analise_giro if a['classificacao_giro'] == 'Muito Baixo'][:20]
        
        # Produtos parados (sem vendas no período)
        produtos_parados = [a for a in analise_giro if a['giro_anual'] == 0]
        
        # Análise ABC baseada no giro
        produtos_abc_giro = []
        total_valor_vendido = sum(a['valor_vendido'] for a in analise_giro)
        
        if total_valor_vendido > 0:
            valor_acumulado = 0
            for item in analise_giro:
                valor_acumulado += item['valor_vendido']
                percentual_acumulado = (valor_acumulado / total_valor_vendido) * 100
                
                if percentual_acumulado <= 80:
                    classificacao_abc = 'A'
                elif percentual_acumulado <= 95:
                    classificacao_abc = 'B'
                else:
                    classificacao_abc = 'C'
                
                item['classificacao_abc'] = classificacao_abc
                produtos_abc_giro.append(item)
        
        # Distribuição ABC
        distribuicao_abc = {
            'A': len([p for p in produtos_abc_giro if p['classificacao_abc'] == 'A']),
            'B': len([p for p in produtos_abc_giro if p['classificacao_abc'] == 'B']),
            'C': len([p for p in produtos_abc_giro if p['classificacao_abc'] == 'C'])
        }
        
        # Paginação
        paginator = Paginator(analise_giro, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Categorias para filtro
        categorias = Categoria.objects.filter(empresa=empresa, ativa=True).order_by('nome')
        
        context.update({
            'periodo': periodo,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'page_obj': page_obj,
            'stats_giro': stats_giro,
            'giro_por_categoria': giro_por_categoria,
            'top_giro': top_giro,
            'baixo_giro': baixo_giro,
            'produtos_parados': produtos_parados,
            'distribuicao_abc': distribuicao_abc,
            'categorias': categorias,
            'categoria_selecionada': categoria_id,
            'title': 'Relatório de Giro de Estoque'
        })
        
        return context


class RelatorioABCView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/abc.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        criterio = self.request.GET.get('criterio', 'faturamento')  # faturamento, quantidade, margem
        periodo = int(self.request.GET.get('periodo', 90))
        categoria_id = self.request.GET.get('categoria_id')
        
        data_inicio = timezone.now().date() - timedelta(days=periodo)
        data_fim = timezone.now().date()
        
        # Base query para produtos
        produtos = Produto.objects.filter(
            empresa=empresa,
            ativo=True
        ).select_related('categoria', 'marca')
        
        if categoria_id:
            produtos = produtos.filter(categoria_id=categoria_id)
        
        # Análise ABC
        analise_abc = []
        
        for produto in produtos:
            # Vendas no período
            vendas_produto = ItemVenda.objects.filter(
                produto=produto,
                venda__data_venda__gte=data_inicio,
                venda__data_venda__lte=data_fim,
                venda__status='finalizada'
            )
            
            quantidade_vendida = vendas_produto.aggregate(
                Sum('quantidade')
            )['quantidade__sum'] or 0
            
            faturamento = vendas_produto.aggregate(
                valor=Sum(F('quantidade') * F('preco_unitario'))
            )['valor'] or 0
            
            # Calcular margem
            custo_total = quantidade_vendida * (produto.preco_custo or 0)
            margem = faturamento - custo_total
            
            # Determinar valor para classificação baseado no critério
            if criterio == 'faturamento':
                valor_classificacao = faturamento
            elif criterio == 'quantidade':
                valor_classificacao = quantidade_vendida
            elif criterio == 'margem':
                valor_classificacao = margem
            else:
                valor_classificacao = faturamento
            
            analise_abc.append({
                'produto': produto,
                'quantidade_vendida': quantidade_vendida,
                'faturamento': faturamento,
                'margem': margem,
                'valor_classificacao': valor_classificacao,
                'custo_total': custo_total,
                'percentual_margem': (margem / faturamento * 100) if faturamento > 0 else 0
            })
        
        # Ordenar por valor de classificação
        analise_abc.sort(key=lambda x: x['valor_classificacao'], reverse=True)
        
        # Calcular classificação ABC
        total_valor = sum(item['valor_classificacao'] for item in analise_abc)
        valor_acumulado = 0
        
        for item in analise_abc:
            valor_acumulado += item['valor_classificacao']
            percentual_acumulado = (valor_acumulado / total_valor * 100) if total_valor > 0 else 0
            
            if percentual_acumulado <= 80:
                item['classificacao'] = 'A'
                item['cor_classificacao'] = 'success'
            elif percentual_acumulado <= 95:
                item['classificacao'] = 'B'
                item['cor_classificacao'] = 'warning'
            else:
                item['classificacao'] = 'C'
                item['cor_classificacao'] = 'info'
            
            item['percentual_acumulado'] = round(percentual_acumulado, 2)
            item['participacao'] = round(
                (item['valor_classificacao'] / total_valor * 100) if total_valor > 0 else 0, 2
            )
        
        # Estatísticas ABC
        stats_abc = {
            'total_produtos': len(analise_abc),
            'produtos_a': len([p for p in analise_abc if p['classificacao'] == 'A']),
            'produtos_b': len([p for p in analise_abc if p['classificacao'] == 'B']),
            'produtos_c': len([p for p in analise_abc if p['classificacao'] == 'C']),
            'total': total_valor
        }
        
        # Valor por classificação
        valor_por_classe = {
            'A': sum(p['valor_classificacao'] for p in analise_abc if p['classificacao'] == 'A'),
            'B': sum(p['valor_classificacao'] for p in analise_abc if p['classificacao'] == 'B'),
            'C': sum(p['valor_classificacao'] for p in analise_abc if p['classificacao'] == 'C')
        }
        
        # Percentuais por classe
        percentual_por_classe = {}
        for classe in ['A', 'B', 'C']:
            percentual_por_classe[classe] = {
                'produtos': round((stats_abc[f'produtos_{classe.lower()}'] / stats_abc['total_produtos'] * 100), 1) if stats_abc['total_produtos'] > 0 else 0,
                'valor': round((valor_por_classe[classe] / total_valor * 100), 1) if total_valor > 0 else 0
            }
        
        # ABC por categoria
        abc_por_categoria = {}
        
        for item in analise_abc:
            categoria = item['produto'].categoria
            categoria_nome = categoria.nome if categoria else 'Sem Categoria'
            
            if categoria_nome not in abc_por_categoria:
                abc_por_categoria[categoria_nome] = {'A': 0, 'B': 0, 'C': 0, 'total': 0}
            
            abc_por_categoria[categoria_nome][item['classificacao']] += 1
            abc_por_categoria[categoria_nome]['total'] += item['valor_classificacao']
        
        # Comparação entre critérios
        comparacao_criterios = {}
        
        for criterio_comp in ['faturamento', 'quantidade', 'margem']:
            if criterio_comp != criterio:
                # Recalcular classificação para o critério de comparação
                analise_temp = []
                for produto in produtos[:50]:  # Limitar para performance
                    vendas_produto = ItemVenda.objects.filter(
                        produto=produto,
                        venda__data_venda__gte=data_inicio,
                        venda__data_venda__lte=data_fim,
                        venda__status='finalizada'
                    )
                    
                    if criterio_comp == 'faturamento':
                        valor = vendas_produto.aggregate(
                            valor=Sum(F('quantidade') * F('preco_unitario'))
                        )['valor'] or 0
                    elif criterio_comp == 'quantidade':
                        valor = vendas_produto.aggregate(Sum('quantidade'))['quantidade__sum'] or 0
                    elif criterio_comp == 'margem':
                        faturamento = vendas_produto.aggregate(
                            valor=Sum(F('quantidade') * F('preco_unitario'))
                        )['valor'] or 0
                        quantidade = vendas_produto.aggregate(Sum('quantidade'))['quantidade__sum'] or 0
                        valor = faturamento - (quantidade * (produto.preco_custo or 0))
                    
                    analise_temp.append({'produto': produto, 'valor': valor})
                
                analise_temp.sort(key=lambda x: x['valor'], reverse=True)
                total_temp = sum(item['valor'] for item in analise_temp)
                
                # Classificar
                valor_acum_temp = 0
                for item in analise_temp:
                    valor_acum_temp += item['valor']
                    perc_acum = (valor_acum_temp / total_temp * 100) if total_temp > 0 else 0
                    
                    if perc_acum <= 80:
                        item['classe'] = 'A'
                    elif perc_acum <= 95:
                        item['classe'] = 'B'
                    else:
                        item['classe'] = 'C'
                
                comparacao_criterios[criterio_comp] = {
                    'A': len([p for p in analise_temp if p['classe'] == 'A']),
                    'B': len([p for p in analise_temp if p['classe'] == 'B']),
                    'C': len([p for p in analise_temp if p['classe'] == 'C'])
                }
        
        # Produtos que mudaram de classe (comparando faturamento vs quantidade)
        mudancas_classe = []
        if criterio == 'faturamento' and 'quantidade' in comparacao_criterios:
            # Implementar lógica de comparação detalhada se necessário
            pass
        
        # Recomendações baseadas na análise ABC
        recomendacoes = {
            'A': [
                'Manter sempre em estoque',
                'Negociar melhores condições com fornecedores',
                'Monitorar de perto a demanda',
                'Avaliar aumento de margem'
            ],
            'B': [
                'Controle de estoque moderado',
                'Revisar política de reposição',
                'Avaliar sazonalidade',
                'Considerar promoções pontuais'
            ],
            'C': [
                'Reduzir estoque',
                'Avaliar descontinuação',
                'Fazer liquidação',
                'Revisar fornecedores'
            ]
        }
        
        # Paginação
        paginator = Paginator(analise_abc, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Categorias para filtro
        categorias = Categoria.objects.filter(empresa=empresa, ativa=True).order_by('nome')
        
        context.update({
            'criterio': criterio,
            'periodo': periodo,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'page_obj': page_obj,
            'stats_abc': stats_abc,
            'valor_por_classe': valor_por_classe,
            'percentual_por_classe': percentual_por_classe,
            'abc_por_categoria': abc_por_categoria,
            'comparacao_criterios': comparacao_criterios,
            'recomendacoes': recomendacoes,
            'categorias': categorias,
            'categoria_selecionada': categoria_id,
            'title': f'Análise ABC - {criterio.title()}'
        })
        
        return context


class RelatorioInventarioView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/estoque/inventario.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        inventario_id = self.request.GET.get('inventario_id')
        situacao = self.request.GET.get('situacao')  # divergencia, ok, nao_contado
        
        # Inventários disponíveis
        inventarios = Inventario.objects.filter(
            empresa=empresa
        ).order_by('-data_inicio')
        
        if not inventario_id and inventarios.exists():
            inventario_id = inventarios.first().id
        
        inventario_selecionado = None
        if inventario_id:
            inventario_selecionado = get_object_or_404(
                Inventario, id=inventario_id, empresa=empresa
            )
        
        if not inventario_selecionado:
            context.update({
                'inventarios': inventarios,
                'error': 'Nenhum inventário encontrado',
                'title': 'Relatório de Inventário'
            })
            return context
        
        # Itens do inventário
        itens_inventario = inventario_selecionado.itens.select_related(
            'produto', 'produto__categoria'
        ).order_by('produto__nome_comercial')
        
        # Aplicar filtro de situação
        if situacao == 'divergencia':
            itens_inventario = itens_inventario.exclude(
                quantidade_contada=F('quantidade_sistema')
            )
        elif situacao == 'ok':
            itens_inventario = itens_inventario.filter(
                quantidade_contada=F('quantidade_sistema')
            )
        elif situacao == 'nao_contado':
            itens_inventario = itens_inventario.filter(quantidade_contada__isnull=True)
        
        # Análise dos itens
        analise_inventario = []
        
        for item in itens_inventario:
            quantidade_sistema = item.quantidade_sistema or 0
            quantidade_contada = item.quantidade_contada or 0
            
            # Calcular divergência
            divergencia_quantidade = quantidade_contada - quantidade_sistema
            divergencia_percentual = 0
            
            if quantidade_sistema > 0:
                divergencia_percentual = (divergencia_quantidade / quantidade_sistema) * 100
            elif quantidade_contada > 0:
                divergencia_percentual = 100  # 100% de divergência se sistema zerado mas tem estoque físico
            
            # Valor da divergência
            preco_custo = item.produto.preco_custo or 0
            valor_divergencia = divergencia_quantidade * preco_custo
            
            # Classificar tipo de divergência
            if divergencia_quantidade == 0:
                tipo_divergencia = 'OK'
                cor_divergencia = 'success'
            elif divergencia_quantidade > 0:
                tipo_divergencia = 'Sobra'
                cor_divergencia = 'info'
            else:
                tipo_divergencia = 'Falta'
                cor_divergencia = 'danger'
            
            # Classificar criticidade baseada no percentual
            if abs(divergencia_percentual) >= 50:
                criticidade = 'Alta'
            elif abs(divergencia_percentual) >= 20:
                criticidade = 'Média'
            elif abs(divergencia_percentual) > 0:
                criticidade = 'Baixa'
            else:
                criticidade = 'Nenhuma'
            
            analise_inventario.append({
                'item': item,
                'divergencia_quantidade': divergencia_quantidade,
                'divergencia_percentual': round(divergencia_percentual, 2),
                'valor_divergencia': valor_divergencia,
                'tipo_divergencia': tipo_divergencia,
                'cor_divergencia': cor_divergencia,
                'criticidade': criticidade
            })
        
        # Estatísticas do inventário
        total_itens = len(analise_inventario)
        itens_ok = len([a for a in analise_inventario if a['tipo_divergencia'] == 'OK'])
        itens_sobra = len([a for a in analise_inventario if a['tipo_divergencia'] == 'Sobra'])
        itens_falta = len([a for a in analise_inventario if a['tipo_divergencia'] == 'Falta'])
        
        total_divergencia = sum(a['valor_divergencia'] for a in analise_inventario)
        valor_sobras = sum(a['valor_divergencia'] for a in analise_inventario if a['valor_divergencia'] > 0)
        valor_faltas = sum(abs(a['valor_divergencia']) for a in analise_inventario if a['valor_divergencia'] < 0)
        
        stats_inventario = {
            'total_itens': total_itens,
            'itens_ok': itens_ok,
            'itens_sobra': itens_sobra,
            'itens_falta': itens_falta,
            'percentual_ok': round((itens_ok / total_itens * 100), 2) if total_itens > 0 else 0,
            'total_divergencia': total_divergencia,
            'valor_sobras': valor_sobras,
            'valor_faltas': valor_faltas,
            'acuracidade': round((itens_ok / total_itens * 100), 2) if total_itens > 0 else 0
        }
        
        # Divergências por categoria
        divergencias_categoria = {}
        
        for item in analise_inventario:
            categoria = item['item'].produto.categoria
            categoria_nome = categoria.nome if categoria else 'Sem Categoria'
            
            if categoria_nome not in divergencias_categoria:
                divergencias_categoria[categoria_nome] = {
                    'total': 0,
                    'ok': 0,
                    'sobra': 0,
                    'falta': 0,
                    'valor_divergencia': 0
                }
            
            divergencias_categoria[categoria_nome]['total'] += 1
            divergencias_categoria[categoria_nome]['valor_divergencia'] += item['valor_divergencia']
            
            if item['tipo_divergencia'] == 'OK':
                divergencias_categoria[categoria_nome]['ok'] += 1
            elif item['tipo_divergencia'] == 'Sobra':
                divergencias_categoria[categoria_nome]['sobra'] += 1
            elif item['tipo_divergencia'] == 'Falta':
                divergencias_categoria[categoria_nome]['falta'] += 1
        
        # Top divergências (maiores valores)
        top_divergencias = sorted(
            [a for a in analise_inventario if a['valor_divergencia'] != 0],
            key=lambda x: abs(x['valor_divergencia']),
            reverse=True
        )[:20]
        
        # Produtos com maior variação percentual
        maior_variacao = sorted(
            [a for a in analise_inventario if a['divergencia_percentual'] != 0],
            key=lambda x: abs(x['divergencia_percentual']),
            reverse=True
        )[:20]
        
        # Produtos não contados
        nao_contados = [a for a in analise_inventario if a['item'].quantidade_contada is None]
        
        # Recomendações baseadas na análise
        recomendacoes = []
        
        if stats_inventario['percentual_ok'] < 80:
            recomendacoes.append('Revisar processos de controle de estoque')
        
        if valor_faltas > valor_sobras * 2:
            recomendacoes.append('Investigar possíveis perdas ou furtos')
        
        if len(nao_contados) > total_itens * 0.1:
            recomendacoes.append('Melhorar organização física do estoque')
        
        if stats_inventario['acuracidade'] < 95:
            recomendacoes.append('Implementar contagem cíclica')
        
        # Paginação
        paginator = Paginator(analise_inventario, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context.update({
            'inventarios': inventarios,
            'inventario_selecionado': inventario_selecionado,
            'page_obj': page_obj,
            'stats_inventario': stats_inventario,
            'divergencias_categoria': divergencias_categoria,
            'top_divergencias': top_divergencias,
            'maior_variacao': maior_variacao,
            'nao_contados': nao_contados,
            'recomendacoes': recomendacoes,
            'filtros': {
                'inventario_id': inventario_id,
                'situacao': situacao
            },
            'title': f'Relatório de Inventário - {inventario_selecionado.nome if inventario_selecionado else ""}'
        })
        
        return context


# =====================================
# RELATÓRIOS FINANCEIROS
# =====================================

class RelatoriosFinanceiroView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Data atual e períodos
        hoje = timezone.now().date()
        inicio_mes = hoje.replace(day=1)
        inicio_ano = hoje.replace(month=1, day=1)
        
        # Contas a Receber
        contas_receber = ContaReceber.objects.filter(empresa=empresa)
        
        contas_receber_stats = {
            'total_aberto': contas_receber.filter(status='aberto').aggregate(
                Sum('valor'))['valor__sum'] or 0,
            'vencidas': contas_receber.filter(
                status='aberto', data_vencimento__lt=hoje
            ).aggregate(Sum('valor'))['valor__sum'] or 0,
            'vencendo_30_dias': contas_receber.filter(
                status='aberto',
                data_vencimento__gte=hoje,
                data_vencimento__lte=hoje + timedelta(days=30)
            ).aggregate(Sum('valor'))['valor__sum'] or 0,
            'recebido_mes': contas_receber.filter(
                status='pago',
                data_pagamento__gte=inicio_mes
            ).aggregate(Sum('valor'))['valor__sum'] or 0
        }
        
        # Contas a Pagar
        contas_pagar = ContaPagar.objects.filter(empresa=empresa)
        
        contas_pagar_stats = {
            'total_aberto': contas_pagar.filter(status='aberto').aggregate(
                Sum('valor'))['valor__sum'] or 0,
            'vencidas': contas_pagar.filter(
                status='aberto', data_vencimento__lt=hoje
            ).aggregate(Sum('valor'))['valor__sum'] or 0,
            'vencendo_30_dias': contas_pagar.filter(
                status='aberto',
                data_vencimento__gte=hoje,
                data_vencimento__lte=hoje + timedelta(days=30)
            ).aggregate(Sum('valor'))['valor__sum'] or 0,
            'pago_mes': contas_pagar.filter(
                status='pago',
                data_pagamento__gte=inicio_mes
            ).aggregate(Sum('valor'))['valor__sum'] or 0
        }
        
        # Fluxo de Caixa
        movimentacoes_mes = MovimentacaoFinanceira.objects.filter(
            empresa=empresa,
            data_movimentacao__gte=inicio_mes
        )
        
        fluxo_caixa = {
            'entradas_mes': movimentacoes_mes.filter(tipo='entrada').aggregate(
                Sum('valor'))['valor__sum'] or 0,
            'saidas_mes': movimentacoes_mes.filter(tipo='saida').aggregate(
                Sum('valor'))['valor__sum'] or 0
        }
        
        fluxo_caixa['saldo_mes'] = fluxo_caixa['entradas_mes'] - fluxo_caixa['saidas_mes']
        
        # Vendas vs Recebimentos
        vendas_mes = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=inicio_mes,
            status='finalizada'
        ).aggregate(Sum('total'))['total__sum'] or 0
        
        # Indicadores financeiros
        if vendas_mes > 0:
            taxa_conversao_recebimento = (contas_receber_stats['recebido_mes'] / vendas_mes) * 100
        else:
            taxa_conversao_recebimento = 0
        
        # Contas vencendo nos próximos 7 dias
        contas_receber_7_dias = contas_receber.filter(
            status='aberto',
            data_vencimento__gte=hoje,
            data_vencimento__lte=hoje + timedelta(days=7)
        ).order_by('data_vencimento')[:10]
        
        contas_pagar_7_dias = contas_pagar.filter(
            status='aberto',
            data_vencimento__gte=hoje,
            data_vencimento__lte=hoje + timedelta(days=7)
        ).order_by('data_vencimento')[:10]
        
        # Centros de custo com maior gasto
        gastos_centro_custo = MovimentacaoFinanceira.objects.filter(
            empresa=empresa,
            tipo='saida',
            data_movimentacao__gte=inicio_mes,
            centro_custo__isnull=False
        ).values(
            'centro_custo__nome'
        ).annotate(
            total_gasto=Sum('valor')
        ).order_by('-total_gasto')[:10]
        
        # Evolução do saldo (últimos 30 dias)
        evolucao_saldo = []
        saldo_acumulado = 0
        
        for i in range(30):
            data_dia = hoje - timedelta(days=29-i)
            
            entradas_dia = MovimentacaoFinanceira.objects.filter(
                empresa=empresa,
                tipo='entrada',
                data_movimentacao=data_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            saidas_dia = MovimentacaoFinanceira.objects.filter(
                empresa=empresa,
                tipo='saida',
                data_movimentacao=data_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            saldo_dia = entradas_dia - saidas_dia
            saldo_acumulado += saldo_dia
            
            evolucao_saldo.append({
                'data': data_dia,
                'entradas': entradas_dia,
                'saidas': saidas_dia,
                'saldo_dia': saldo_dia,
                'saldo_acumulado': saldo_acumulado
            })
        
        # Top clientes inadimplentes
        clientes_inadimplentes = contas_receber.filter(
            status='aberto',
            data_vencimento__lt=hoje
        ).values(
            'cliente__nome'
        ).annotate(
            total=Sum('valor'),
            quantidade_contas=Count('id')
        ).order_by('-total')[:10]
        
        # Resumo mensal
        resumo_financeiro = {
            'receitas': vendas_mes,
            'recebimentos': contas_receber_stats['recebido_mes'],
            'pagamentos': contas_pagar_stats['pago_mes'],
            'saldo_periodo': fluxo_caixa['saldo_mes'],
            'contas_vencidas_receber': contas_receber_stats['vencidas'],
            'contas_vencidas_pagar': contas_pagar_stats['vencidas']
        }
        
        context.update({
            'contas_receber_stats': contas_receber_stats,
            'contas_pagar_stats': contas_pagar_stats,
            'fluxo_caixa': fluxo_caixa,
            'vendas_mes': vendas_mes,
            'taxa_conversao_recebimento': round(taxa_conversao_recebimento, 2),
            'contas_receber_7_dias': contas_receber_7_dias,
            'contas_pagar_7_dias': contas_pagar_7_dias,
            'gastos_centro_custo': gastos_centro_custo,
            'evolucao_saldo': evolucao_saldo,
            'clientes_inadimplentes': clientes_inadimplentes,
            'resumo_financeiro': resumo_financeiro,
            'title': 'Dashboard Financeiro'
        })
        
        return context


class RelatorioFluxoCaixaView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/fluxo_caixa.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        centro_custo_id = self.request.GET.get('centro_custo_id')
        tipo_fluxo = self.request.GET.get('tipo_fluxo', 'realizado')  # realizado ou projetado
        
        # Definir período padrão (mês atual)
        if not data_inicio:
            data_inicio = timezone.now().date().replace(day=1)
        else:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
        
        if not data_fim:
            # Último dia do mês
            if data_inicio.month == 12:
                data_fim = data_inicio.replace(year=data_inicio.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                data_fim = data_inicio.replace(month=data_inicio.month + 1, day=1) - timedelta(days=1)
        else:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
        
        if tipo_fluxo == 'realizado':
            # Fluxo de caixa realizado
            movimentacoes = MovimentacaoFinanceira.objects.filter(
                empresa=empresa,
                data_movimentacao__gte=data_inicio,
                data_movimentacao__lte=data_fim
            )
            
            if centro_custo_id:
                movimentacoes = movimentacoes.filter(centro_custo_id=centro_custo_id)
            
            # Fluxo diário
            fluxo_diario = {}
            
            # Inicializar todos os dias do período
            current_date = data_inicio
            while current_date <= data_fim:
                fluxo_diario[current_date] = {
                    'data': current_date,
                    'entradas': 0,
                    'saidas': 0,
                    'saldo': 0,
                    'saldo_acumulado': 0
                }
                current_date += timedelta(days=1)
            
            # Preencher com dados reais
            movimentacoes_por_dia = movimentacoes.values('data_movimentacao', 'tipo').annotate(
                total=Sum('valor')
            ).order_by('data_movimentacao')
            
            for mov in movimentacoes_por_dia:
                data = mov['data_movimentacao']
                if data in fluxo_diario:
                    if mov['tipo'] == 'entrada':
                        fluxo_diario[data]['entradas'] = mov['total']
                    else:
                        fluxo_diario[data]['saidas'] = mov['total']
            
            # Calcular saldos
            saldo_acumulado = 0
            for data in sorted(fluxo_diario.keys()):
                fluxo_diario[data]['saldo'] = fluxo_diario[data]['entradas'] - fluxo_diario[data]['saidas']
                saldo_acumulado += fluxo_diario[data]['saldo']
                fluxo_diario[data]['saldo_acumulado'] = saldo_acumulado
            
            fluxo_diario_lista = [fluxo_diario[data] for data in sorted(fluxo_diario.keys())]
            
        else:
            # Fluxo de caixa projetado
            fluxo_diario_lista = []
            saldo_inicial = 0  # Implementar saldo inicial real
            
            # Projeção baseada em contas a receber e pagar
            current_date = data_inicio
            saldo_acumulado = saldo_inicial
            
            while current_date <= data_fim:
                # Recebimentos previstos
                recebimentos = ContaReceber.objects.filter(
                    empresa=empresa,
                    status='aberto',
                    data_vencimento=current_date
                ).aggregate(Sum('valor'))['valor__sum'] or 0
                
                # Pagamentos previstos
                pagamentos = ContaPagar.objects.filter(
                    empresa=empresa,
                    status='aberto',
                    data_vencimento=current_date
                ).aggregate(Sum('valor'))['valor__sum'] or 0
                
                # Vendas médias (para projeção)
                vendas_medias = Venda.objects.filter(
                    empresa=empresa,
                    data_venda__gte=current_date - timedelta(days=30),
                    data_venda__lt=current_date,
                    status='finalizada'
                ).aggregate(Avg('total'))['total__avg'] or 0
                
                saldo_dia = recebimentos - pagamentos + vendas_medias
                saldo_acumulado += saldo_dia
                
                fluxo_diario_lista.append({
                    'data': current_date,
                    'entradas': recebimentos + vendas_medias,
                    'saidas': pagamentos,
                    'saldo': saldo_dia,
                    'saldo_acumulado': saldo_acumulado
                })
                
                current_date += timedelta(days=1)
        
        # Resumo do período
        total_entradas = sum(dia['entradas'] for dia in fluxo_diario_lista)
        total_saidas = sum(dia['saidas'] for dia in fluxo_diario_lista)
        saldo_periodo = total_entradas - total_saidas
        
        # Análise por centro de custo
        if tipo_fluxo == 'realizado':
            fluxo_centro_custo = MovimentacaoFinanceira.objects.filter(
                empresa=empresa,
                data_movimentacao__gte=data_inicio,
                data_movimentacao__lte=data_fim,
                centro_custo__isnull=False
            ).values(
                'centro_custo__nome',
                'tipo'
            ).annotate(
                total=Sum('valor')
            ).order_by('centro_custo__nome', 'tipo')
            
            # Reorganizar por centro de custo
            centros_custo_resumo = {}
            for item in fluxo_centro_custo:
                centro = item['centro_custo__nome']
                if centro not in centros_custo_resumo:
                    centros_custo_resumo[centro] = {'entradas': 0, 'saidas': 0, 'saldo': 0}
                
                if item['tipo'] == 'entrada':
                    centros_custo_resumo[centro]['entradas'] = item['total']
                else:
                    centros_custo_resumo[centro]['saidas'] = item['total']
                
                centros_custo_resumo[centro]['saldo'] = (
                    centros_custo_resumo[centro]['entradas'] - 
                    centros_custo_resumo[centro]['saidas']
                )
        else:
            centros_custo_resumo = {}
        
        # Análise semanal
        fluxo_semanal = []
        semana_atual = []
        
        for dia in fluxo_diario_lista:
            semana_atual.append(dia)
            
            # Se for domingo ou último dia, fechar a semana
            if dia['data'].weekday() == 6 or dia['data'] == data_fim:
                entradas_semana = sum(d['entradas'] for d in semana_atual)
                saidas_semana = sum(d['saidas'] for d in semana_atual)
                
                fluxo_semanal.append({
                    'semana_inicio': semana_atual[0]['data'],
                    'semana_fim': semana_atual[-1]['data'],
                    'entradas': entradas_semana,
                    'saidas': saidas_semana,
                    'saldo': entradas_semana - saidas_semana
                })
                
                semana_atual = []
        
        # Indicadores
        dias_periodo = (data_fim - data_inicio).days + 1
        media_entradas_dia = total_entradas / dias_periodo if dias_periodo > 0 else 0
        media_saidas_dia = total_saidas / dias_periodo if dias_periodo > 0 else 0
        
        # Projeção para próximos 30 dias (se estiver vendo realizado)
        projecao_30_dias = None
        if tipo_fluxo == 'realizado':
            # Calcular projeção baseada na média dos últimos 30 dias
            data_projecao_inicio = data_fim + timedelta(days=1)
            data_projecao_fim = data_projecao_inicio + timedelta(days=30)
            
            projecao_30_dias = {
                'periodo': f"{data_projecao_inicio.strftime('%d/%m')} a {data_projecao_fim.strftime('%d/%m')}",
                'entradas_previstas': media_entradas_dia * 30,
                'saidas_previstas': media_saidas_dia * 30,
                'saldo_previsto': (media_entradas_dia - media_saidas_dia) * 30
            }
        
        # Centros de custo para filtro
        centros_custo = CentroCusto.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('nome')
        
        context.update({
            'data_inicio': data_inicio,
            'data_fim': data_fim,
            'tipo_fluxo': tipo_fluxo,
            'fluxo_diario': fluxo_diario_lista,
            'fluxo_semanal': fluxo_semanal,
            'total_entradas': total_entradas,
            'total_saidas': total_saidas,
            'saldo_periodo': saldo_periodo,
            'centros_custo_resumo': centros_custo_resumo,
            'media_entradas_dia': round(media_entradas_dia, 2),
            'media_saidas_dia': round(media_saidas_dia, 2),
            'projecao_30_dias': projecao_30_dias,
            'centros_custo': centros_custo,
            'centro_custo_selecionado': centro_custo_id,
            'title': f'Fluxo de Caixa {tipo_fluxo.title()}'
        })
        
        return context


class RelatorioContasReceberView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/contas_receber.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        situacao = self.request.GET.get('situacao', 'todas')  # todas, aberto, vencidas, pagas
        cliente_id = self.request.GET.get('cliente_id')
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        
        hoje = timezone.now().date()
        
        # Query base
        contas = ContaReceber.objects.filter(empresa=empresa)
        
        if cliente_id:
            contas = contas.filter(cliente_id=cliente_id)
        
        if data_inicio:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            contas = contas.filter(data_vencimento__gte=data_inicio)
        
        if data_fim:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            contas = contas.filter(data_vencimento__lte=data_fim)
        
        # Aplicar filtro de situação
        if situacao == 'aberto':
            contas = contas.filter(status='aberto')
        elif situacao == 'vencidas':
            contas = contas.filter(status='aberto', data_vencimento__lt=hoje)
        elif situacao == 'pagas':
            contas = contas.filter(status='pago')
        
        contas = contas.select_related('cliente').order_by('data_vencimento')
        
        # Análise das contas
        analise_contas = []
        
        for conta in contas:
            dias_vencimento = (conta.data_vencimento - hoje).days
            
            # Classificar situação
            if conta.status == 'pago':
                situacao_conta = 'Paga'
                cor_situacao = 'success'
                prioridade = 5
            elif dias_vencimento < 0:
                situacao_conta = f'Vencida há {abs(dias_vencimento)} dias'
                cor_situacao = 'danger'
                prioridade = 1
            elif dias_vencimento == 0:
                situacao_conta = 'Vence hoje'
                cor_situacao = 'warning'
                prioridade = 2
            elif dias_vencimento <= 7:
                situacao_conta = f'Vence em {dias_vencimento} dias'
                cor_situacao = 'warning'
                prioridade = 3
            else:
                situacao_conta = f'Vence em {dias_vencimento} dias'
                cor_situacao = 'info'
                prioridade = 4
            
            # Histórico de pagamentos do cliente
            pagamentos_cliente = ContaReceber.objects.filter(
                empresa=empresa,
                cliente=conta.cliente,
                status='pago'
            ).count()
            
            total_devedor_cliente = ContaReceber.objects.filter(
                empresa=empresa,
                cliente=conta.cliente,
                status='aberto'
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            analise_contas.append({
                'conta': conta,
                'dias_vencimento': dias_vencimento,
                'situacao_conta': situacao_conta,
                'cor_situacao': cor_situacao,
                'prioridade': prioridade,
                'pagamentos_cliente': pagamentos_cliente,
                'total_devedor_cliente': total_devedor_cliente
            })
        
        # Ordenar por prioridade
        analise_contas.sort(key=lambda x: (x['prioridade'], x['dias_vencimento']))
        
        # Estatísticas
        stats_contas = {
            'total_contas': contas.count(),
            'total': contas.aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_abertas': contas.filter(status='aberto').count(),
            'valor_aberto': contas.filter(status='aberto').aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_vencidas': contas.filter(status='aberto', data_vencimento__lt=hoje).count(),
            'valor_vencido': contas.filter(status='aberto', data_vencimento__lt=hoje).aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_pagas': contas.filter(status='pago').count(),
            'valor_pago': contas.filter(status='pago').aggregate(Sum('valor'))['valor__sum'] or 0
        }
        
        # Aging (análise por faixa de vencimento)
        aging_faixas = [
            ('current', 'A vencer', 0, float('inf')),
            ('1_30', '1-30 dias', 1, 30),
            ('31_60', '31-60 dias', 31, 60),
            ('61_90', '61-90 dias', 61, 90),
            ('over_90', 'Mais de 90 dias', 91, float('inf'))
        ]
        
        aging_analysis = []
        
        for codigo, descricao, min_dias, max_dias in aging_faixas:
            if codigo == 'current':
                # Contas a vencer
                contas_faixa = contas.filter(status='aberto', data_vencimento__gte=hoje)
            else:
                # Contas vencidas
                if max_dias == float('inf'):
                    contas_faixa = contas.filter(
                        status='aberto',
                        data_vencimento__lt=hoje - timedelta(days=min_dias-1)
                    )
                else:
                    contas_faixa = contas.filter(
                        status='aberto',
                        data_vencimento__gte=hoje - timedelta(days=max_dias),
                        data_vencimento__lt=hoje - timedelta(days=min_dias-1)
                    )
            
            valor_faixa = contas_faixa.aggregate(Sum('valor'))['valor__sum'] or 0
            
            aging_analysis.append({
                'codigo': codigo,
                'descricao': descricao,
                'quantidade': contas_faixa.count(),
                'valor': valor_faixa,
                'percentual': (valor_faixa / stats_contas['valor_aberto'] * 100) if stats_contas['valor_aberto'] > 0 else 0
            })
        
        # Top clientes devedores
        clientes_devedores = contas.filter(status='aberto').values(
            'cliente__nome',
            'cliente__id'
        ).annotate(
            total_devido=Sum('valor'),
            quantidade_contas=Count('id'),
            maior_atraso=Min('data_vencimento')
        ).order_by('-total_devido')[:15]
        
        # Calcular dias de atraso para cada cliente
        for cliente in clientes_devedores:
            if cliente['maior_atraso']:
                cliente['dias_atraso'] = max(0, (hoje - cliente['maior_atraso']).days)
            else:
                cliente['dias_atraso'] = 0
        
        # Evolução dos recebimentos (últimos 12 meses)
        evolucao_recebimentos = []
        
        for i in range(12):
            data_mes = hoje.replace(day=1) - timedelta(days=30 * i)
            primeiro_dia = data_mes.replace(day=1)
            
            if data_mes.month == 12:
                ultimo_dia = data_mes.replace(year=data_mes.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                ultimo_dia = data_mes.replace(month=data_mes.month + 1, day=1) - timedelta(days=1)
            
            recebimentos_mes = ContaReceber.objects.filter(
                empresa=empresa,
                status='pago',
                data_pagamento__gte=primeiro_dia,
                data_pagamento__lte=ultimo_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            evolucao_recebimentos.append({
                'mes': primeiro_dia,
                'valor': recebimentos_mes,
                'mes_nome': primeiro_dia.strftime('%m/%Y')
            })
        
        evolucao_recebimentos.reverse()
        
        # Previsão de recebimentos (próximos 30 dias)
        previsao_recebimentos = []
        
        for i in range(30):
            data_dia = hoje + timedelta(days=i)
            
            recebimentos_previstos = ContaReceber.objects.filter(
                empresa=empresa,
                status='aberto',
                data_vencimento=data_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            if recebimentos_previstos > 0:
                previsao_recebimentos.append({
                    'data': data_dia,
                    'valor': recebimentos_previstos
                })
        
        # Clientes para filtro
        clientes_com_contas = Cliente.objects.filter(
            id__in=contas.values('cliente_id').distinct()
        ).order_by('nome')
        
        # Paginação
        paginator = Paginator(analise_contas, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context.update({
            'page_obj': page_obj,
            'stats_contas': stats_contas,
            'aging_analysis': aging_analysis,
            'clientes_devedores': clientes_devedores,
            'evolucao_recebimentos': evolucao_recebimentos,
            'previsao_recebimentos': previsao_recebimentos,
            'clientes_com_contas': clientes_com_contas,
            'filtros': {
                'situacao': situacao,
                'cliente_id': cliente_id,
                'data_inicio': data_inicio,
                'data_fim': data_fim
            },
            'title': 'Relatório de Contas a Receber'
        })
        
        return context


class RelatorioContasPagarView(BaseViewMixin, TemplateView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/contas_pagar.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        # Filtros
        situacao = self.request.GET.get('situacao', 'todas')
        fornecedor_id = self.request.GET.get('fornecedor_id')
        centro_custo_id = self.request.GET.get('centro_custo_id')
        data_inicio = self.request.GET.get('data_inicio')
        data_fim = self.request.GET.get('data_fim')
        
        hoje = timezone.now().date()
        
        # Query base
        contas = ContaPagar.objects.filter(empresa=empresa)
        
        if fornecedor_id:
            contas = contas.filter(fornecedor_id=fornecedor_id)
        
        if centro_custo_id:
            contas = contas.filter(centro_custo_id=centro_custo_id)
        
        if data_inicio:
            data_inicio = datetime.strptime(data_inicio, '%Y-%m-%d').date()
            contas = contas.filter(data_vencimento__gte=data_inicio)
        
        if data_fim:
            data_fim = datetime.strptime(data_fim, '%Y-%m-%d').date()
            contas = contas.filter(data_vencimento__lte=data_fim)
        
        # Aplicar filtro de situação
        if situacao == 'aberto':
            contas = contas.filter(status='aberto')
        elif situacao == 'vencidas':
            contas = contas.filter(status='aberto', data_vencimento__lt=hoje)
        elif situacao == 'pagas':
            contas = contas.filter(status='pago')
        
        contas = contas.select_related('fornecedor', 'centro_custo').order_by('data_vencimento')
        
        # Análise das contas
        analise_contas = []
        
        for conta in contas:
            dias_vencimento = (conta.data_vencimento - hoje).days
            
            # Classificar situação e urgência
            if conta.status == 'pago':
                situacao_conta = 'Paga'
                cor_situacao = 'success'
                urgencia = 5
            elif dias_vencimento < 0:
                situacao_conta = f'Vencida há {abs(dias_vencimento)} dias'
                cor_situacao = 'danger'
                urgencia = 1
            elif dias_vencimento == 0:
                situacao_conta = 'Vence hoje'
                cor_situacao = 'danger'
                urgencia = 1
            elif dias_vencimento <= 3:
                situacao_conta = f'Vence em {dias_vencimento} dias'
                cor_situacao = 'warning'
                urgencia = 2
            elif dias_vencimento <= 7:
                situacao_conta = f'Vence em {dias_vencimento} dias'
                cor_situacao = 'warning'
                urgencia = 3
            else:
                situacao_conta = f'Vence em {dias_vencimento} dias'
                cor_situacao = 'info'
                urgencia = 4
            
            # Calcular multa e juros se vencida
            multa_juros = 0
            if dias_vencimento < 0 and conta.status == 'aberto':
                # Assumir 2% de multa + 1% ao mês de juros
                dias_atraso = abs(dias_vencimento)
                multa = conta.valor * Decimal('0.02')  # 2% multa
                juros = conta.valor * Decimal('0.01') * (dias_atraso / 30)  # 1% ao mês
                multa_juros = multa + juros
            
            total_com_encargos = conta.valor + multa_juros
            
            analise_contas.append({
                'conta': conta,
                'dias_vencimento': dias_vencimento,
                'situacao_conta': situacao_conta,
                'cor_situacao': cor_situacao,
                'urgencia': urgencia,
                'multa_juros': multa_juros,
                'total_com_encargos': total_com_encargos
            })
        
        # Ordenar por urgência
        analise_contas.sort(key=lambda x: (x['urgencia'], x['dias_vencimento']))
        
        # Estatísticas
        stats_contas = {
            'total_contas': contas.count(),
            'total': contas.aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_abertas': contas.filter(status='aberto').count(),
            'valor_aberto': contas.filter(status='aberto').aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_vencidas': contas.filter(status='aberto', data_vencimento__lt=hoje).count(),
            'valor_vencido': contas.filter(status='aberto', data_vencimento__lt=hoje).aggregate(Sum('valor'))['valor__sum'] or 0,
            'contas_pagas': contas.filter(status='pago').count(),
            'valor_pago': contas.filter(status='pago').aggregate(Sum('valor'))['valor__sum'] or 0,
            'total_multas_juros': sum(c['multa_juros'] for c in analise_contas)
        }
        
        # Contas por centro de custo
        contas_por_centro = contas.filter(
            centro_custo__isnull=False
        ).values(
            'centro_custo__nome'
        ).annotate(
            total_valor=Sum('valor'),
            quantidade=Count('id')
        ).order_by('-total_valor')
        
        # Top fornecedores (maior valor em aberto)
        fornecedores_maior_valor = contas.filter(
            status='aberto'
        ).values(
            'fornecedor__nome',
            'fornecedor__id'
        ).annotate(
            total_devido=Sum('valor'),
            quantidade_contas=Count('id'),
            maior_atraso=Min('data_vencimento')
        ).order_by('-total_devido')[:15]
        
        # Calcular dias de atraso
        for fornecedor in fornecedores_maior_valor:
            if fornecedor['maior_atraso']:
                fornecedor['dias_atraso'] = max(0, (hoje - fornecedor['maior_atraso']).days)
            else:
                fornecedor['dias_atraso'] = 0
        
        # Fluxo de pagamentos (próximos 30 dias)
        fluxo_pagamentos = []
        
        for i in range(30):
            data_dia = hoje + timedelta(days=i)
            
            pagamentos_dia = ContaPagar.objects.filter(
                empresa=empresa,
                status='aberto',
                data_vencimento=data_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            if pagamentos_dia > 0:
                fluxo_pagamentos.append({
                    'data': data_dia,
                    'valor': pagamentos_dia,
                    'dia_semana': data_dia.strftime('%A')[:3]
                })
        
        # Contas vencendo por categoria de urgência
        urgencia_categorias = {
            'hoje': contas.filter(status='aberto', data_vencimento=hoje),
            'amanha': contas.filter(status='aberto', data_vencimento=hoje + timedelta(days=1)),
            '3_dias': contas.filter(
                status='aberto',
                data_vencimento__gt=hoje + timedelta(days=1),
                data_vencimento__lte=hoje + timedelta(days=3)
            ),
            '7_dias': contas.filter(
                status='aberto',
                data_vencimento__gt=hoje + timedelta(days=3),
                data_vencimento__lte=hoje + timedelta(days=7)
            )
        }
        
        resumo_urgencia = {}
        for categoria, queryset in urgencia_categorias.items():
            resumo_urgencia[categoria] = {
                'quantidade': queryset.count(),
                'valor': queryset.aggregate(Sum('valor'))['valor__sum'] or 0
            }
        
        # Histórico de pagamentos (últimos 12 meses)
        historico_pagamentos = []
        
        for i in range(12):
            data_mes = hoje.replace(day=1) - timedelta(days=30 * i)
            primeiro_dia = data_mes.replace(day=1)
            
            if data_mes.month == 12:
                ultimo_dia = data_mes.replace(year=data_mes.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                ultimo_dia = data_mes.replace(month=data_mes.month + 1, day=1) - timedelta(days=1)
            
            pagamentos_mes = ContaPagar.objects.filter(
                empresa=empresa,
                status='pago',
                data_pagamento__gte=primeiro_dia,
                data_pagamento__lte=ultimo_dia
            ).aggregate(Sum('valor'))['valor__sum'] or 0
            
            historico_pagamentos.append({
                'mes': primeiro_dia,
                'valor': pagamentos_mes,
                'mes_nome': primeiro_dia.strftime('%m/%Y')
            })
        
        historico_pagamentos.reverse()
        
        # Análise de atraso médio por fornecedor
        analise_atraso_fornecedor = []
        
        for fornecedor_data in fornecedores_maior_valor[:10]:
            contas_fornecedor = ContaPagar.objects.filter(
                empresa=empresa,
                fornecedor_id=fornecedor_data['fornecedor__id'],
                status='pago',
                data_pagamento__isnull=False
            )
            
            atrasos = []
            for conta in contas_fornecedor:
                if conta.data_pagamento > conta.data_vencimento:
                    atraso_dias = (conta.data_pagamento - conta.data_vencimento).days
                    atrasos.append(atraso_dias)
            
            if atrasos:
                atraso_medio = sum(atrasos) / len(atrasos)
                percentual_atraso = (len(atrasos) / contas_fornecedor.count()) * 100
            else:
                atraso_medio = 0
                percentual_atraso = 0
            
            analise_atraso_fornecedor.append({
                'fornecedor': fornecedor_data['fornecedor__nome'],
                'atraso_medio': round(atraso_medio, 1),
                'percentual_atraso': round(percentual_atraso, 1),
                'total_contas': contas_fornecedor.count()
            })
        
        # Filtros disponíveis
        fornecedores_com_contas = Fornecedor.objects.filter(
            id__in=contas.values('fornecedor_id').distinct()
        ).order_by('nome')
        
        centros_custo = CentroCusto.objects.filter(
            empresa=empresa,
            ativo=True
        ).order_by('nome')
        
        # Paginação
        paginator = Paginator(analise_contas, 50)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context.update({
            'page_obj': page_obj,
            'stats_contas': stats_contas,
            'contas_por_centro': contas_por_centro,
            'fornecedores_maior_valor': fornecedores_maior_valor,
            'fluxo_pagamentos': fluxo_pagamentos,
            'resumo_urgencia': resumo_urgencia,
            'historico_pagamentos': historico_pagamentos,
            'analise_atraso_fornecedor': analise_atraso_fornecedor,
            'fornecedores_com_contas': fornecedores_com_contas,
            'centros_custo': centros_custo,
            'filtros': {
                'situacao': situacao,
                'fornecedor_id': fornecedor_id,
                'centro_custo_id': centro_custo_id,
                'data_inicio': data_inicio,
                'data_fim': data_fim
            },
            'title': 'Relatório de Contas a Pagar'
        })
        
        return context




class BaseRelatorioView(LoginRequiredMixin, TemplateView):
    """
    View base para todos os relatórios do sistema.
    Gere a autenticação e a lógica de filtragem por período (data de início e fim).
    Esta abordagem centraliza o código comum, seguindo o princípio DRY (Don't Repeat Yourself).
    """
    login_url = '/contas/login/' # Redireciona para a página de login se o utilizador não estiver autenticado.
    redirect_field_name = 'next'

    def get_context_data(self, **kwargs):
        """
        Adiciona as datas de filtro ao contexto para serem usadas no template e nas queries.
        """
        context = super().get_context_data(**kwargs)
        
        # Obtém as datas do GET request ou define um padrão (ex: último mês)
        hoje = date.today()
        primeiro_dia_mes = hoje.replace(day=1)
        
        context['data_inicio'] = self.request.GET.get('data_inicio', primeiro_dia_mes.strftime('%Y-%m-%d'))
        context['data_fim'] = self.request.GET.get('data_fim', hoje.strftime('%Y-%m-%d'))
        return context

    def get_datas_filtro(self):
        """
        Retorna as datas de início e fim convertidas para objetos datetime.
        """
        data_inicio_str = self.request.GET.get('data_inicio')
        data_fim_str = self.request.GET.get('data_fim')
        
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None
        except ValueError:
            data_inicio, data_fim = None, None
            
        return data_inicio, data_fim

# =====================================
# RELATÓRIOS FINANCEIROS
# =====================================

class RelatorioDREView(BaseRelatorioView):
    """
    Demonstração de Resultados do Exercício (DRE).
    Calcula receitas, custos, despesas e o lucro líquido num determinado período.
    Essencial para a tomada de decisão estratégica.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/dre.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        # Lógica para DRE (exemplo com um modelo 'LancamentoContabil')
        # Esta é uma simplificação. Um DRE real depende de um plano de contas estruturado.
        receita_bruta = LancamentoFinanceiro.objects.filter(
            conta__natureza='receita', data__range=(data_inicio, data_fim)
        ).aggregate(total=Sum('valor'))['total'] or 0

        custos = LancamentoFinanceiro.objects.filter(
            conta__natureza='custo', data__range=(data_inicio, data_fim)
        ).aggregate(total=Sum('valor'))['total'] or 0

        despesas = LancamentoFinanceiro.objects.filter(
            conta__natureza='despesa', data__range=(data_inicio, data_fim)
        ).aggregate(total=Sum('valor'))['total'] or 0

        lucro_bruto = receita_bruta - custos
        lucro_liquido = lucro_bruto - despesas

        context['dre_data'] = {
            'receita_bruta': receita_bruta,
            'custos': custos,
            'lucro_bruto': lucro_bruto,
            'despesas': despesas,
            'lucro_liquido': lucro_liquido
        }
        context['titulo'] = 'Relatório DRE'
        return context

class RelatorioBalancoView(BaseRelatorioView):
    """
    Balanço Patrimonial.
    Apresenta a posição financeira da empresa (Ativos, Passivos, Património Líquido).
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/balanco.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Lógica para Balanço Patrimonial (altamente dependente do plano de contas)
        # Exemplo simplificado:
        ativos = LancamentoFinanceiro.objects.filter(conta__grupo='ativo').aggregate(total=Sum('valor'))['total'] or 0
        passivos = LancamentoFinanceiro.objects.filter(conta__grupo='passivo').aggregate(total=Sum('valor'))['total'] or 0
        patrimonio_liquido = ativos - passivos

        context['balanco_data'] = {
            'ativos': ativos,
            'passivos': passivos,
            'patrimonio_liquido': patrimonio_liquido
        }
        context['titulo'] = 'Balanço Patrimonial'
        return context

class RelatorioInadimplenciaView(BaseRelatorioView):
    """
    Relatório de Inadimplência.
    Lista clientes com faturas vencidas e não pagas.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/financeiro/inadimplencia.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = date.today()
        
        contas_vencidas = ContaReceber.objects.filter(
            data_vencimento__lt=hoje, data_pagamento__isnull=True
        ).select_related('cliente').order_by('data_vencimento')

        total_inadimplencia = contas_vencidas.aggregate(total=Sum('valor'))['total'] or 0

        context['contas_vencidas'] = contas_vencidas
        context['total_inadimplencia'] = total_inadimplencia
        context['total_clientes_inadimplentes'] = contas_vencidas.values('cliente').distinct().count()
        context['titulo'] = 'Relatório de Inadimplência'
        return context

# =====================================
# RELATÓRIOS DE CLIENTES
# =====================================

class RelatoriosClientesView(BaseRelatorioView):
    """
    Página central (dashboard) para os relatórios de clientes.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/dashboard_clientes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Relatórios de Clientes'
        return context

class RelatorioCadastrosClientesView(BaseRelatorioView):
    """
    Relatório de novos cadastros de clientes por período.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/cadastros.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        clientes = Cliente.objects.filter(data_cadastro__range=(data_inicio, data_fim)).order_by('-data_cadastro')
        
        context['clientes'] = clientes
        context['total_cadastros'] = clientes.count()
        context['titulo'] = 'Novos Cadastros de Clientes'
        return context

class RelatorioAniversariantesView(BaseRelatorioView):
    """
    Relatório de clientes aniversariantes do mês ou de um período específico.
    Útil para ações de marketing e relacionamento.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/aniversariantes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mes_atual = self.request.GET.get('mes', date.today().month)
        
        aniversariantes = Cliente.objects.filter(data_nascimento__month=mes_atual).order_by('data_nascimento__day')
        
        context['aniversariantes'] = aniversariantes
        context['mes_selecionado'] = mes_atual
        context['titulo'] = f'Aniversariantes do Mês {mes_atual}'
        return context

class RelatorioComprasClientesView(BaseRelatorioView):
    """
    Relatório de compras por cliente, mostrando o valor total gasto e a quantidade de compras.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/compras.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        compras_por_cliente = Venda.objects.filter(
            data__range=(data_inicio, data_fim)
        ).values(
            'cliente__nome'
        ).annotate(
            total_gasto=Sum('total'),
            quantidade_compras=Count('id')
        ).order_by('-total_gasto')
        
        context['compras_por_cliente'] = compras_por_cliente
        context['titulo'] = 'Relatório de Compras por Cliente'
        return context

class RelatorioFidelidadeView(BaseRelatorioView):
    """
    Relatório de Fidelidade (RFV - Recência, Frequência, Valor).
    Identifica os clientes mais leais com base na frequência de compras.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/fidelidade.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        clientes_fieis = Cliente.objects.filter(
            venda__data__range=(data_inicio, data_fim)
        ).annotate(
            num_compras=Count('venda')
        ).filter(
            num_compras__gt=1  # Considera fiéis clientes com mais de 1 compra no período
        ).order_by('-num_compras')
        
        context['clientes_fieis'] = clientes_fieis
        context['titulo'] = 'Relatório de Fidelidade de Clientes'
        return context

class RelatorioSegmentacaoView(BaseRelatorioView):
    """
    Relatório de Segmentação de Clientes.
    Agrupa clientes em categorias (ex: Alto Valor, Recentes, Inativos).
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/clientes/segmentacao.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        # Exemplo de segmentação
        clientes = Cliente.objects.annotate(
            total_gasto=Sum('venda__total', filter=Q(venda__data__range=(data_inicio, data_fim))),
            ultima_compra=Max('venda__data', filter=Q(venda__data__range=(data_inicio, data_fim)))
        ).annotate(
            segmento=Case(
                When(total_gasto__gte=1000, then=Value('Alto Valor')),
                When(ultima_compra__gte=date.today() - timedelta(days=30), then=Value('Recente')),
                When(ultima_compra__lt=date.today() - timedelta(days=90), then=Value('Inativo')),
                default=Value('Regular'),
                output_field=CharField()
            )
        ).order_by('-total_gasto')
        
        context['clientes_segmentados'] = clientes
        context['titulo'] = 'Segmentação de Clientes'
        return context

# =====================================
# RELATÓRIOS DE FUNCIONÁRIOS
# =====================================

class RelatoriosFuncionariosView(BaseRelatorioView):
    """
    Página central (dashboard) para os relatórios de funcionários.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/dashboard_funcionarios.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Relatórios de Funcionários'
        return context

class RelatorioPontoView(BaseRelatorioView):
    """
    Relatório de Ponto Eletrónico.
    Exibe os registos de entrada e saída dos funcionários.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/ponto.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        registos = RegistroPonto.objects.filter(
            data__range=(data_inicio, data_fim)
        ).select_related('funcionario').order_by('funcionario', 'data')
        
        context['registos_ponto'] = registos
        context['titulo'] = 'Relatório de Ponto'
        return context

class RelatorioFolhaView(BaseRelatorioView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/folha.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mes_referencia = self.request.GET.get('mes_referencia') # Formato: YYYY-MM
        
        if mes_referencia:
            ano, mes = map(int, mes_referencia.split('-'))
            holerites = FolhaPagamento.objects.filter(
                mes_referencia__year=ano, mes_referencia__month=mes
            ).select_related('funcionario')
        else:
            holerites = FolhaPagamento.objects.none()

        context['holerites'] = holerites
        context['titulo'] = 'Relatório da Folha de Pagamento'
        return context

class RelatorioFeriasView(BaseRelatorioView):
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/ferias.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ferias = Ferias.objects.all().select_related('funcionario').order_by('data_inicio')
        
        context['ferias'] = ferias
        context['titulo'] = 'Controlo de Férias'
        return context

class RelatorioTreinamentosView(BaseRelatorioView):
    """
    Relatório de Treinamentos e Desenvolvimento.
    Lista os treinamentos realizados e os funcionários participantes.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/treinamentos.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        treinamentos = Capacitacao.objects.filter(
            data_realizacao__range=(data_inicio, data_fim)
        ).prefetch_related('participantes') # prefetch_related para otimizar a query
        
        context['treinamentos'] = treinamentos
        context['titulo'] = 'Relatório de Treinamentos'
        return context

class RelatorioPerformanceView(BaseRelatorioView):
    """
    Relatório de Avaliação de Performance.
    Apresenta os resultados das avaliações de desempenho dos funcionários.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/funcionarios/performance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        avaliacoes = AvaliacaoDesempenho.objects.filter(
            data_avaliacao__range=(data_inicio, data_fim)
        ).select_related('funcionario', 'avaliador').order_by('-data_avaliacao')
        
        context['avaliacoes'] = avaliacoes
        context['titulo'] = 'Avaliações de Performance'
        return context

from django.db.models import Avg, StdDev, Min, Max, ExpressionWrapper, DurationField
from django.utils import timezone


class RelatoriosFornecedoresView(BaseRelatorioView):
    """
    Página central (dashboard) para os relatórios de fornecedores.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/fornecedores/dashboard_fornecedores.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Relatórios de Fornecedores'
        return context

class RelatorioComprasView(BaseRelatorioView):
    """
    Relatório de compras por fornecedor, detalhando o volume e o valor financeiro.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/fornecedores/compras.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        compras = Compra.objects.filter(
            data_pedido__range=(data_inicio, data_fim)
        ).values(
            'fornecedor__nome'
        ).annotate(
            total_comprado=Sum('total'),
            quantidade_pedidos=Count('id')
        ).order_by('-total_comprado')
        
        context['compras_por_fornecedor'] = compras
        context['titulo'] = 'Relatório de Compras por Fornecedor'
        return context

class RelatorioPerformanceFornecedorView(BaseRelatorioView):
    """
    Análise da performance geral dos fornecedores, combinando múltiplos indicadores.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/fornecedores/performance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()

        # Calcula o tempo de entrega médio
        delivery_times = Compra.objects.filter(
            data_pedido__range=(data_inicio, data_fim),
            data_entrega_real__isnull=False
        ).annotate(
            tempo_entrega=ExpressionWrapper(F('data_entrega_real') - F('data_pedido'), output_field=DurationField())
        ).values('fornecedor__nome').annotate(
            tempo_medio=Avg('tempo_entrega')
        )
        
        # Calcula a taxa de defeitos
        quality_rates = ItemCompra.objects.filter(
            compra__data_pedido__range=(data_inicio, data_fim)
        ).values('compra__fornecedor__nome').annotate(
            total_recebido=Sum('quantidade_recebida'),
            total_defeituoso=Sum('quantidade_defeituosa')
        ).annotate(
            taxa_defeito=Case(
                When(total_recebido__gt=0, then=(F('total_defeituoso') * 100.0 / F('total_recebido'))),
                default=Value(0),
                output_field=DecimalField()
            )
        )
        
        # Pode-se combinar estes dados num único objeto no Python para exibir no template.
        context['performance_data'] = {
            'prazos': list(delivery_times),
            'qualidade': list(quality_rates)
        }
        context['titulo'] = 'Performance de Fornecedores'
        return context

class RelatorioPrazosEntregaView(BaseRelatorioView):
    """
    Relatório focado nos prazos de entrega, comparando o previsto com o real.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/fornecedores/prazos.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        prazos = Compra.objects.filter(
            data_pedido__range=(data_inicio, data_fim),
            data_entrega_real__isnull=False
        ).annotate(
            dias_atraso=ExpressionWrapper(F('data_entrega_real') - F('data_entrega_prevista'), output_field=DurationField())
        ).values(
            'fornecedor__nome'
        ).annotate(
            atraso_medio=Avg('dias_atraso')
        ).order_by('atraso_medio')
        
        context['prazos_entrega'] = prazos
        context['titulo'] = 'Análise de Prazos de Entrega'
        return context

class RelatorioQualidadeFornecedorView(BaseRelatorioView):
    """
    Relatório de qualidade, medindo a percentagem de produtos defeituosos por fornecedor.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/fornecedores/qualidade.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        qualidade = ItemCompra.objects.filter(
            compra__data_pedido__range=(data_inicio, data_fim)
        ).values('compra__fornecedor__nome').annotate(
            total_recebido=Sum('quantidade_recebida'),
            total_defeituoso=Sum('quantidade_defeituosa')
        ).annotate(
            taxa_defeito_percentual=Case(
                When(total_recebido__gt=0, then=(F('total_defeituoso') * 100.0 / F('total_recebido'))),
                default=Value(0),
                output_field=DecimalField()
            )
        ).order_by('taxa_defeito_percentual')
        
        context['relatorio_qualidade'] = qualidade
        context['titulo'] = 'Qualidade de Produtos por Fornecedor'
        return context

# =====================================
# ANÁLISES E DASHBOARDS
# =====================================

class AnalisesDashboardView(BaseRelatorioView):
    """
    Dashboard central para visualizações analíticas de negócio.
    """
    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)
    
    template_name = 'relatorios/analises/dashboard_analises.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Dashboard de Análises'
        return context

class AnaliseVendasView(BaseRelatorioView):
    """
    Análise de vendas ao longo do tempo, ideal para gráficos.
    """
    template_name = 'relatorios/analises/vendas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        vendas_por_dia = Venda.objects.filter(
            data__range=(data_inicio, data_fim)
        ).annotate(
            dia=TruncDay('data')
        ).values('dia').annotate(
            total_vendido=Sum('total')
        ).order_by('dia')
        
        # Estes dados são perfeitos para serem consumidos por uma biblioteca como Chart.js no frontend.
        context['vendas_por_dia'] = list(vendas_por_dia)
        context['titulo'] = 'Análise de Vendas por Período'
        return context

class AnaliseLucratividadeView(BaseRelatorioView):
    """
    Análise da lucratividade por produto ou categoria.
    """
    template_name = 'relatorios/analises/lucratividade.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        lucratividade_por_produto = ItemVenda.objects.filter(
            venda__data__range=(data_inicio, data_fim)
        ).values(
            'produto__nome'
        ).annotate(
            lucro_bruto=Sum(F('preco_unitario') - F('custo_unitario')) * F('quantidade')
        ).order_by('-lucro_bruto')
        
        context['lucratividade'] = lucratividade_por_produto
        context['titulo'] = 'Análise de Lucratividade por Produto'
        return context


# =====================================
# KPIs E INDICADORES
# =====================================

class KPIsDashboardView(BaseRelatorioView):
    """
    Dashboard principal que exibe os KPIs mais importantes para o negócio.
    """
    template_name = 'relatorios/kpis/dashboard_kpis.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = 'Dashboard de KPIs'
        return context

class KPIsVendasView(BaseRelatorioView):
    """
    Calcula e exibe os principais Indicadores-Chave de Performance para a área de Vendas.
    """
    template_name = 'relatorios/kpis/vendas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        vendas_periodo = Venda.objects.filter(data__range=(data_inicio, data_fim))
        total_vendas = vendas_periodo.aggregate(Sum('total'))['total__sum'] or 0
        num_vendas = vendas_periodo.count()
        
        ticket_medio = total_vendas / num_vendas if num_vendas > 0 else 0
        
        context['kpis'] = {
            'total_vendas': total_vendas,
            'numero_de_vendas': num_vendas,
            'ticket_medio': ticket_medio,
            # Outros KPIs como LTV e CAC requerem queries mais complexas.
        }
        context['titulo'] = 'KPIs de Vendas'
        return context

class KPIsFinanceirosView(BaseRelatorioView):
    """
    Calcula e exibe os principais Indicadores-Chave de Performance Financeiros.
    """
    template_name = 'relatorios/kpis/financeiros.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Lógica para DRE (simplificada)
        receita = ... 
        custos = ...
        margem_bruta = (receita - custos) / receita if receita > 0 else 0
        
        context['kpis'] = {
            'margem_lucro_bruta': margem_bruta,
            'ponto_equilibrio': "Cálculo depende de custos fixos e variáveis",
            'liquidez_corrente': "Ativo Circulante / Passivo Circulante"
        }
        context['titulo'] = 'KPIs Financeiros'
        return context

class KPIsOperacionaisView(BaseRelatorioView):
    """
    Calcula e exibe os principais Indicadores-Chave de Performance Operacionais.
    """
    template_name = 'relatorios/kpis/operacionais.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Giro de Estoque = Custo das Mercadorias Vendidas / Valor Médio do Estoque
        # Tempo Médio de Entrega (já calculado em RelatorioPrazosEntregaView)
        
        context['kpis'] = {
            'giro_de_estoque': "Cálculo complexo, requer dados de CMV e estoque médio.",
            'taxa_retencao_clientes': "Cálculo requer análise de coortes."
        }
        context['titulo'] = 'KPIs Operacionais'
        return context

class KPIsPersonalizadosView(BaseRelatorioView):
    """
    Exibe KPIs que foram definidos pelo próprio utilizador no sistema.
    """
    template_name = 'relatorios/kpis/personalizados.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Assume um modelo 'KPI' onde utilizadores podem definir nome, meta e fórmula.
        # A execução da 'fórmula' é um desafio avançado. Esta view irá apenas listá-los.
        kpis_personalizados = KPI.objects.filter(ativo=True)
        
        context['kpis_personalizados'] = kpis_personalizados
        context['titulo'] = 'KPIs Personalizados'
        return context




class AgendamentoListView(LoginRequiredMixin, ListView):
    """
    Lista todos os agendamentos de relatórios.
    """
    model = AgendamentoRelatorio
    template_name = 'agendamentos/lista.html'
    context_object_name = 'agendamentos'

class AgendamentoCreateView(LoginRequiredMixin, CreateView):
    """
    Cria um novo agendamento para a geração e envio de um relatório.
    """
    model = AgendamentoRelatorio
    template_name = 'agendamentos/form.html'
    fields = ['nome_relatorio', 'tipo_relatorio', 'frequencia', 'destinatarios', 'ativo']
    success_url = reverse_lazy('agendamento_lista')

    def form_valid(self, form):
        messages.success(self.request, "Agendamento criado com sucesso.")
        return super().form_valid(form)

class AgendamentoDetailView(LoginRequiredMixin, DetailView):
    """
    Exibe os detalhes de um agendamento específico.
    """
    model = AgendamentoRelatorio
    template_name = 'agendamentos/detalhe.html'
    context_object_name = 'agendamento'

class ExecutarAgendamentoView(LoginRequiredMixin, View):
    """
    Dispara a execução imediata de um relatório agendado como uma tarefa em background.
    """
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoRelatorio, pk=kwargs['pk'])
        
        # Dispara a tarefa Celery em background
        # executar_relatorio_agendado_task.delay(agendamento.id)
        
        messages.info(request, f"A execução do relatório '{agendamento.nome_relatorio}' foi iniciada em segundo plano.")
        return redirect('agendamento_lista')

class AtivarAgendamentoView(LoginRequiredMixin, View):
    """
    Ativa um agendamento para que ele seja executado conforme a frequência.
    """
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoRelatorio, pk=kwargs['pk'])
        agendamento.ativo = True
        agendamento.save()
        messages.success(request, f"O agendamento '{agendamento.nome_relatorio}' foi ativado.")
        return redirect('agendamento_lista')

class DesativarAgendamentoView(LoginRequiredMixin, View):
    """
    Desativa um agendamento para pausar sua execução.
    """
    def post(self, request, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoRelatorio, pk=kwargs['pk'])
        agendamento.ativo = False
        agendamento.save()
        messages.warning(request, f"O agendamento '{agendamento.nome_relatorio}' foi desativado.")
        return redirect('agendamento_lista')

# =====================================
# DISTRIBUIÇÃO DE RELATÓRIOS
# =====================================

class DistribuicaoRelatoriosView(LoginRequiredMixin, TemplateView):
    """
    Página central para opções de distribuição de relatórios.
    """
    template_name = 'distribuicao/dashboard.html'

class EnvioEmailView(LoginRequiredMixin, FormView):
    """
    View para envio manual de um relatório por e-mail.
    """
    template_name = 'distribuicao/envio_email.html'
    # form_class = SeuFormularioDeEmail # Crie um forms.py com este formulário
    success_url = reverse_lazy('distribuicao')

    def form_valid(self, form):
        # Lógica de envio de e-mail aqui
        # send_mail(...)
        messages.success(self.request, "E-mail enviado com sucesso.")
        return super().form_valid(form)

class ImpressaoRelatoriosView(LoginRequiredMixin, DetailView):
    """
    Gera uma versão de um relatório otimizada para impressão.
    """
    model = RelatorioGerado # Um modelo que armazena um relatório já processado
    template_name = 'distribuicao/impressao.html' # Um template com CSS @media print
    context_object_name = 'relatorio'

class CompartilhamentoView(LoginRequiredMixin, DetailView):
    """
    Gera um link seguro e temporário para compartilhamento de um relatório.
    """
    model = RelatorioGerado
    template_name = 'distribuicao/compartilhamento.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Lógica para gerar um link assinado (usando django.core.signing)
        # context['link_compartilhamento'] = ...
        return context



class HistoricoRelatoriosView(LoginRequiredMixin, ListView):
    model = LogAtividade  # Usar o modelo correto
    template_name = 'historico/lista.html'
    queryset = LogAtividade.objects.filter(tipo='HISTORICO') # Usar o modelo correto
    context_object_name = 'logs'
    paginate_by = 25

class AuditoriaRelatoriosView(LoginRequiredMixin, ListView):
    model = LogAtividade  # Usar o modelo correto
    template_name = 'historico/lista.html'
    queryset = LogAtividade.objects.filter(tipo='AUDITORIA') # Usar o modelo correto
    context_object_name = 'logs'
    paginate_by = 25

class LogsRelatoriosView(LoginRequiredMixin, ListView):
    model = LogAtividade  # Usar o modelo correto
    template_name = 'historico/lista_completa.html'
    context_object_name = 'logs'
    paginate_by = 50

class LogAcessoRelatoriosView(LoginRequiredMixin, ListView):
    model = LogAtividade  # Usar o modelo correto
    template_name = 'historico/lista.html'
    queryset = LogAtividade.objects.filter(tipo='HISTORICO', acao__icontains='Acesso') # Usar o modelo correto
    context_object_name = 'logs'
    paginate_by = 25
# =====================================
# EXPORTAÇÃO EM DIVERSOS FORMATOS
# =====================================

class BaseExportView(LoginRequiredMixin, View):
    """
    View base para exportação. Obtém os dados do relatório.
    """
    def get_dados(self, pk):
        # Lógica para obter os dados do relatório com base no PK.
        # Isto é um placeholder. Substitua pela sua lógica real.
        # relatorio = get_object_or_404(RelatorioGerado, pk=pk)
        # return relatorio.get_dados_como_lista_de_dicionarios()
        return [
            {'ID': 1, 'Produto': 'Laptop', 'Vendas': 150, 'Região': 'Norte'},
            {'ID': 2, 'Produto': 'Monitor', 'Vendas': 300, 'Região': 'Sul'},
            {'ID': 3, 'Produto': 'Teclado', 'Vendas': 500, 'Região': 'Norte'},
        ]

class ExportarPDFView(BaseExportView):
    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        dados = self.get_dados(pk)
        
        html_string = render_to_string('export/template.html', {'dados': dados})
        html = HTML(string=html_string)
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{pk}.pdf"'
        return response

class ExportarExcelView(BaseExportView):
    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        dados = self.get_dados(pk)
        
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{pk}.xlsx"'
        
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Relatório'

        headers = list(dados[0].keys())
        sheet.append(headers)

        for item in dados:
            sheet.append(list(item.values()))

        workbook.save(response)
        return response

class ExportarCSVView(BaseExportView):
    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        dados = self.get_dados(pk)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{pk}.csv"'

        writer = csv.writer(response)
        if dados:
            headers = dados[0].keys()
            writer.writerow(headers)
            for item in dados:
                writer.writerow(item.values())
        
        return response

class ExportarXMLView(BaseExportView):
    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        dados = self.get_dados(pk)
        
        # A geração de XML pode ser feita com ElementTree para maior robustez
        xml_string = render_to_string('export/template.xml', {'dados': dados})
        
        response = HttpResponse(xml_string, content_type='application/xml')
        response['Content-Disposition'] = f'attachment; filename="relatorio_{pk}.xml"'
        return response

class ExportarJSONView(BaseExportView):
    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        dados = self.get_dados(pk)
        
        return JsonResponse(dados, safe=False, json_dumps_params={'indent': 2})


class BusinessIntelligenceView(LoginRequiredMixin, TemplateView):
    """
    Dashboard principal de Business Intelligence.
    """
    template_name = 'bi/dashboard.html'

class CubosOLAPView(LoginRequiredMixin, TemplateView):
    """
    Simula a criação de um Cubo OLAP para análise multidimensional de vendas.
    """
    template_name = 'bi/cubos_olap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Usando pandas para criar uma tabela dinâmica (pivot table) que simula um cubo
        queryset = Venda.objects.all().values('data', 'produto__categoria', 'cliente__regiao', 'total')
        df = pd.DataFrame(list(queryset))
        
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'])
            df['mes'] = df['data'].dt.month
            
            # Cruzamento de Categoria de Produto vs. Região do Cliente
            cubo = pd.pivot_table(df, values='total', index='produto__categoria', columns='cliente__regiao', aggfunc='sum', fill_value=0)
            context['cubo_html'] = cubo.to_html(classes='table table-bordered')
        else:
            context['cubo_html'] = "<p>Não há dados suficientes para gerar o cubo.</p>"
            
        context['titulo'] = 'Análise com Cubo OLAP'
        return context

class DataMiningView(LoginRequiredMixin, TemplateView):
    """
    Aplica um algoritmo de clusterização (K-Means) para segmentar clientes.
    """
    template_name = 'bi/data_mining.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Exemplo: Segmentação de clientes com base no valor gasto e frequência
        dados_clientes = Cliente.objects.annotate(
            total=Sum('venda__total'),
            frequencia=Count('venda')
        ).values('id', 'nome', 'total', 'frequencia')
        
        df = pd.DataFrame(list(dados_clientes)).dropna()

        if len(df) > 3: # K-Means precisa de um número mínimo de amostras
            kmeans = KMeans(n_clusters=3, random_state=0, n_init=10)
            df['cluster'] = kmeans.fit_predict(df[['total', 'frequencia']])
            context['clientes_clusterizados'] = df.to_dict('records')
        else:
            context['clientes_clusterizados'] = None

        context['titulo'] = 'Data Mining: Segmentação de Clientes'
        return context

class PrevisoesView(LoginRequiredMixin, TemplateView):
    """
    Utiliza modelos estatísticos para prever vendas futuras.
    """
    template_name = 'bi/previsoes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Previsão de vendas mensais
        vendas_mensais = Venda.objects.annotate(mes=TruncMonth('data')).values('mes').annotate(total=Sum('total')).order_by('mes')
        
        df = pd.DataFrame(list(vendas_mensais), columns=['mes', 'total']).set_index('mes')
        
        if len(df) > 2:
            # Modelo de Suavização Exponencial Simples
            model = SimpleExpSmoothing(df['total'], initialization_method="estimated").fit()
            previsao = model.forecast(3) # Prever os próximos 3 meses
            context['dados_historicos'] = df.reset_index().to_dict('records')
            context['previsao'] = previsao.to_dict()
        else:
            context['dados_historicos'] = None
            context['previsao'] = None

        context['titulo'] = 'Previsão de Vendas'
        return context

# =====================================
# AJAX E UTILITÁRIOS
# =====================================

class GerarRelatorioAjaxView(LoginRequiredMixin, View):
    """
    Inicia a geração de um relatório via AJAX e retorna um ID de tarefa.
    """
    def post(self, request, *args, **kwargs):
        # ...lógica para obter parâmetros do request.POST...
        # task = gerar_relatorio_task.delay(parametros)
        # return JsonResponse({'status': 'iniciado', 'task_id': task.id})
        return JsonResponse({'status': 'simulado', 'task_id': 'xyz-123'})

class PreviewRelatorioView(LoginRequiredMixin, View):
    """
    Retorna uma amostra de dados de um relatório para pré-visualização.
    """
    def get(self, request, *args, **kwargs):
        tipo_relatorio = request.GET.get('tipo')
        # ...lógica para buscar os 10 primeiros registos do relatório...
        dados_preview = list(Venda.objects.all()[:5].values())
        return JsonResponse(dados_preview, safe=False)

class ValidarCamposView(LoginRequiredMixin, View):
    """
    Valida um campo de formulário em tempo real (ex: se um email já existe).
    """
    def get(self, request, *args, **kwargs):
        email = request.GET.get('email')
        existe = Cliente.objects.filter(email=email).exists()
        return JsonResponse({'is_valid': not existe, 'message': 'Este email já está em uso.' if existe else ''})

class BuscarDadosView(LoginRequiredMixin, View):
    """
    Endpoint AJAX para autocompletar ou popular selects dinamicamente.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        clientes = list(Cliente.objects.filter(nome__icontains=query)[:10].values('id', 'nome'))
        return JsonResponse(clientes, safe=False)
        
# =====================================
# CONFIGURAÇÕES
# =====================================

class ConfiguracoesRelatoriosView(LoginRequiredMixin, TemplateView):
    """
    Página central de configurações do sistema de relatórios.
    """
    template_name = 'configuracoes/dashboard.html'

class ConfiguracoesFormatosView(LoginRequiredMixin, FormView):
    """
    Permite ao administrador ativar/desativar formatos de exportação.
    """
    template_name = 'configuracoes/formatos.html'
    # form_class = FormatoConfigForm
    success_url = reverse_lazy('configuracoes')

    def form_valid(self, form):
        # ...lógica para salvar as configurações no modelo ConfiguracaoSistema...
        messages.success(self.request, "Configurações de formatos salvas.")
        return super().form_valid(form)

class ConfiguracoesPermissoesView(LoginRequiredMixin, FormView):
    """
    Permite atribuir permissões de acesso a relatórios por grupo de utilizadores.
    """
    template_name = 'configuracoes/permissoes.html'
    # form_class = PermissoesRelatorioForm
    success_url = reverse_lazy('configuracoes')

    def form_valid(self, form):
        # ...lógica para associar Grupos do Django a relatórios específicos...
        messages.success(self.request, "Permissões atualizadas com sucesso.")
        return super().form_valid(form)
        


class GerarRelatorioAPIView(APIView):
    """
    Endpoint para disparar a geração de um relatório via API.
    """
    permission_classes = [IsAuthenticated] # Usar TokenAuthentication na configuração do DRF

    def post(self, request, format=None):
        parametros = request.data
        
        return Response({'status': 'simulado', 'task_id': 'xyz-123'}, status=status.HTTP_202_ACCEPTED)

class DadosGraficoAPIView(APIView):
    """
    Fornece dados agregados prontos para serem consumidos por bibliotecas de gráficos.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, format=None):
        vendas_por_mes = Venda.objects.annotate(
            mes=TruncMonth('data')
        ).values('mes').annotate(
            total=Sum('total')
        ).order_by('mes')
        
        # Formata para o formato { labels: [], data: [] }
        labels = [item['mes'].strftime('%Y-%m') for item in vendas_por_mes]
        data = [item['total'] for item in vendas_por_mes]
        
        return Response({'labels': labels, 'data': data})

class EstatisticasAPIView(APIView):
    """
    Retorna estatísticas-chave do negócio em tempo real.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        total_vendas = Venda.objects.aggregate(Sum('total'))['total__sum'] or 0
        novos_clientes_mes = Cliente.objects.filter(data_cadastro__month=timezone.now().month).count()
        ticket_medio = Venda.objects.aggregate(Avg('total'))['total__avg'] or 0

        data = {
            'total_vendas_geral': total_vendas,
            'novos_clientes_este_mes': novos_clientes_mes,
            'ticket_medio': round(ticket_medio, 2)
        }
        return Response(data)


