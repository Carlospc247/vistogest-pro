# apps/analytics/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Q, Sum, Count, F, Avg, Max, Min, Case, When, Value
from django.db.models.functions import TruncDate, TruncHour, TruncMonth, TruncYear
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from datetime import datetime, timedelta, date
from decimal import Decimal
import json
import logging
import csv
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    EventoAnalytics, AuditoriaAlteracao, AlertaInteligente, 
    NotificacaoAlerta, DashboardPersonalizado
)
from .serializers import (
    EventoAnalyticsSerializer, AuditoriaAlteracaoSerializer,
    AlertaInteligenteSerializer, DashboardPersonalizadoSerializer
)
from .forms import (
    AlertaInteligenteForm, DashboardPersonalizadoForm,
    FiltroEventosForm, FiltroAuditoriaForm
)
from .utils import (
    registrar_evento, calcular_metricas, gerar_alerta,
    get_client_ip, get_user_agent, detectar_localizacao
)
from django.contrib.auth.mixins import AccessMixin
from apps.core.mixins import BaseViewMixin
from apps.vendas.models import Venda
from apps.produtos.models import Produto
from apps.clientes.models import Cliente

logger = logging.getLogger(__name__)


# =====================================
# DASHBOARD PRINCIPAL
# =====================================



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


class AnalyticsDashboardView(BaseViewMixin, TemplateView):
    template_name = 'analytics/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        usuario = self.request.user
        
        # Verificar se há dashboard personalizado padrão
        dashboard_padrao = DashboardPersonalizado.objects.filter(
            usuario=usuario,
            padrao=True
        ).first()
        
        if dashboard_padrao:
            context['dashboard_personalizado'] = dashboard_padrao
        
        # Métricas principais
        hoje = timezone.now().date()
        ontem = hoje - timedelta(days=1)
        mes_atual = hoje.replace(day=1)
        mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)
        
        # Eventos hoje vs ontem
        eventos_hoje = EventoAnalytics.objects.filter(
            timestamp__date=hoje
        ).count()
        
        eventos_ontem = EventoAnalytics.objects.filter(
            timestamp__date=ontem
        ).count()
        
        variacao_eventos = self._calcular_variacao(eventos_hoje, eventos_ontem)
        
        # Vendas do período
        vendas_mes = Venda.objects.filter(
            data_venda__gte=mes_atual,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        vendas_mes_anterior = Venda.objects.filter(
            data_venda__gte=mes_anterior,
            data_venda__lt=mes_atual,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        variacao_vendas = self._calcular_variacao(
            vendas_mes['total'] or 0,
            vendas_mes_anterior['total'] or 0
        )
        
        # Alertas ativos
        alertas_ativos = AlertaInteligente.objects.filter(
            status='ativo'
        ).count()
        
        # Top eventos por categoria
        eventos_por_categoria = EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).values('categoria').annotate(
            total=Count('id')
        ).order_by('-total')[:5]
        
        # Eventos por hora (últimas 24h)
        eventos_por_hora = EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=24)
        ).extra(
            select={'hora': 'EXTRACT(hour FROM timestamp)'}
        ).values('hora').annotate(
            total=Count('id')
        ).order_by('hora')
        
        # Usuários mais ativos
        usuarios_ativos = EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(days=7),
            usuario__isnull=False
        ).values(
            'usuario__username',
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total_eventos=Count('id')
        ).order_by('-total_eventos')[:10]
        
        context.update({
            'eventos_hoje': eventos_hoje,
            'eventos_ontem': eventos_ontem,
            'variacao_eventos': variacao_eventos,
            'vendas_mes': vendas_mes,
            'variacao_vendas': variacao_vendas,
            'alertas_ativos': alertas_ativos,
            'eventos_por_categoria': eventos_por_categoria,
            'eventos_por_hora': list(eventos_por_hora),
            'usuarios_ativos': usuarios_ativos,
            'title': 'Analytics Dashboard'
        })
        
        return context
    
    def _calcular_variacao(self, atual, anterior):
        if anterior == 0:
            return 100 if atual > 0 else 0
        return round(((atual - anterior) / anterior) * 100, 2)


class AnalyticsOverviewView(BaseViewMixin, TemplateView):
    template_name = 'analytics/overview.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Estatísticas gerais
        total_eventos = EventoAnalytics.objects.filter().count()
        total_usuarios = EventoAnalytics.objects.filter(
            usuario__isnull=False
        ).values('usuario').distinct().count()
        
        # Eventos por período
        eventos_periodo = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio
        )
        
        # Distribuição por categoria
        distribuicao_categoria = eventos_periodo.values('categoria').annotate(
            total=Count('id'),
            percentual=Count('id') * 100.0 / total_eventos
        ).order_by('-total')
        
        # Países mais ativos
        paises_ativos = eventos_periodo.exclude(
            pais=''
        ).values('pais').annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Eventos por dia
        eventos_por_dia = eventos_periodo.extra(
            select={'dia': 'DATE(timestamp)'}
        ).values('dia').annotate(
            total=Count('id')
        ).order_by('dia')
        
        context.update({
            'total_eventos': total_eventos,
            'total_usuarios': total_usuarios,
            'periodo': periodo,
            'distribuicao_categoria': distribuicao_categoria,
            'paises_ativos': paises_ativos,
            'eventos_por_dia': list(eventos_por_dia),
            'title': 'Visão Geral Analytics'
        })
        
        return context


# =====================================
# EVENTOS ANALYTICS
# =====================================
from django.db.models.functions import Coalesce

class EventoAnalyticsListView(BaseViewMixin, ListView):
    model = EventoAnalytics
    template_name = 'analytics/eventos/lista.html'
    context_object_name = 'eventos'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = EventoAnalytics.objects.filter(
            empresa=self.get_empresa()
        ).select_related('usuario').order_by('-timestamp')
        
        # Filtros
        categoria = self.request.GET.get('categoria')
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        
        acao = self.request.GET.get('acao')
        if acao:
            queryset = queryset.filter(acao__icontains=acao)
        
        usuario_id = self.request.GET.get('usuario')
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        
        data_inicio = self.request.GET.get('data_inicio')
        if data_inicio:
            queryset = queryset.filter(timestamp__gte=data_inicio)
        
        data_fim = self.request.GET.get('data_fim')
        if data_fim:
            queryset = queryset.filter(timestamp__lte=data_fim)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Estatísticas dos filtros aplicados
        queryset_filtrado = self.get_queryset()
        
        stats = queryset_filtrado.aggregate(
            total_eventos=Count('id'),
            usuarios_unicos=Count('usuario', distinct=True),
            soma_valores=Coalesce(Sum('valor'), 0)
        )
        
        # Categorias disponíveis
        categorias = EventoAnalytics.objects.filter(
            
        ).values_list('categoria', flat=True).distinct()
        
        # Usuários disponíveis
        usuarios = User.objects.all(
        ).distinct().order_by('first_name', 'username')
        
        context.update({
            'stats': stats,
            'categorias': categorias,
            'usuarios': usuarios,
            'filtro_form': FiltroEventosForm(self.request.GET),
            'title': 'Eventos Analytics'
        })
        
        return context


class EventosTempoRealView(BaseViewMixin, TemplateView):
    template_name = 'analytics/eventos/tempo_real.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Eventos das últimas 2 horas
        eventos_recentes = EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=2)
        ).select_related('usuario').order_by('-timestamp')[:100]
        
        # Usuários online (eventos nos últimos 5 minutos)
        usuarios_online = EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(minutes=5),
            usuario__isnull=False
        ).values('usuario').distinct().count()
        
        context.update({
            'eventos_recentes': eventos_recentes,
            'usuarios_online': usuarios_online,
            'title': 'Eventos em Tempo Real'
        })
        
        return context


class EventosPorCategoriaView(BaseViewMixin, TemplateView):
    template_name = 'analytics/eventos/categoria.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        categoria = kwargs.get('categoria')
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 7))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Eventos da categoria
        eventos = EventoAnalytics.objects.filter(
            categoria=categoria,
            timestamp__gte=data_inicio
        )
        
        # Estatísticas
        total_eventos = eventos.count()
        usuarios_unicos = eventos.values('usuario').distinct().count()
        total = eventos.aggregate(Sum('valor'))['valor__sum'] or 0
        
        # Ações mais comuns
        acoes_comuns = eventos.values('acao').annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Distribuição por hora
        eventos_por_hora = eventos.extra(
            select={'hora': 'EXTRACT(hour FROM timestamp)'}
        ).values('hora').annotate(
            total=Count('id')
        ).order_by('hora')
        
        # Labels mais usados
        labels_comuns = eventos.exclude(
            label=''
        ).values('label').annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        context.update({
            'categoria': categoria,
            'periodo': periodo,
            'total_eventos': total_eventos,
            'usuarios_unicos': usuarios_unicos,
            'total': total,
            'acoes_comuns': acoes_comuns,
            'eventos_por_hora': list(eventos_por_hora),
            'labels_comuns': labels_comuns,
            'title': f'Eventos - {categoria.title()}'
        })
        
        return context


class EventosPorUsuarioView(BaseViewMixin, TemplateView):
    template_name = 'analytics/eventos/usuario.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        usuario_id = kwargs.get('usuario_id')
        
        try:
            usuario = User.objects.get(id=usuario_id)
        except User.DoesNotExist:
            raise Http404('Usuário não encontrado')
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Eventos do usuário
        eventos = EventoAnalytics.objects.filter(
            usuario=usuario,
            timestamp__gte=data_inicio
        ).order_by('-timestamp')
        
        # Estatísticas
        total_eventos = eventos.count()
        categorias_usadas = eventos.values('categoria').distinct().count()
        ultimo_acesso = eventos.first().timestamp if eventos.exists() else None
        
        # Distribuição por categoria
        eventos_por_categoria = eventos.values('categoria').annotate(
            total=Count('id')
        ).order_by('-total')
        
        # Atividade por dia
        atividade_diaria = eventos.extra(
            select={'dia': 'DATE(timestamp)'}
        ).values('dia').annotate(
            total=Count('id')
        ).order_by('dia')
        
        # Ações mais comuns
        acoes_comuns = eventos.values('acao').annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Eventos recentes
        eventos_recentes = eventos[:20]
        
        context.update({
            'usuario_analytics': usuario,
            'periodo': periodo,
            'total_eventos': total_eventos,
            'categorias_usadas': categorias_usadas,
            'ultimo_acesso': ultimo_acesso,
            'eventos_por_categoria': eventos_por_categoria,
            'atividade_diaria': list(atividade_diaria),
            'acoes_comuns': acoes_comuns,
            'eventos_recentes': eventos_recentes,
            'title': f'Analytics - {usuario.get_full_name() or usuario.username}'
        })
        
        return context


class EventosMapaView(BaseViewMixin, TemplateView):
    template_name = 'analytics/eventos/mapa.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 7))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Eventos por país
        eventos_por_pais = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio
        ).exclude(pais='').values('pais').annotate(
            total=Count('id'),
            usuarios=Count('usuario', distinct=True)
        ).order_by('-total')
        
        # Eventos por cidade (top 20)
        eventos_por_cidade = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio
        ).exclude(cidade='').values('cidade', 'pais').annotate(
            total=Count('id')
        ).order_by('-total')[:20]
        
        context.update({
            'periodo': periodo,
            'eventos_por_pais': list(eventos_por_pais),
            'eventos_por_cidade': list(eventos_por_cidade),
            'title': 'Mapa de Eventos'
        })
        
        return context


class FunilConversaoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/eventos/funil.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Definir etapas do funil
        etapas_funil = [
            ('visualizacao_produto', 'Visualização de Produto'),
            ('adicionar_carrinho', 'Adicionou ao Carrinho'),
            ('iniciar_checkout', 'Iniciou Checkout'),
            ('finalizar_compra', 'Finalizou Compra'),
        ]
        
        # Calcular dados do funil
        dados_funil = []
        total_inicial = None
        
        for acao, nome in etapas_funil:
            total = EventoAnalytics.objects.filter(
                acao=acao,
                timestamp__gte=data_inicio
            ).count()
            
            if total_inicial is None:
                total_inicial = total
                taxa_conversao = 100
            else:
                taxa_conversao = (total / total_inicial * 100) if total_inicial > 0 else 0
            
            dados_funil.append({
                'acao': acao,
                'nome': nome,
                'total': total,
                'taxa_conversao': round(taxa_conversao, 2)
            })
        
        context.update({
            'periodo': periodo,
            'dados_funil': dados_funil,
            'title': 'Funil de Conversão'
        })
        
        return context


# =====================================
# AUDITORIA
# =====================================

class AuditoriaListView(BaseViewMixin, ListView):
    model = AuditoriaAlteracao
    template_name = 'analytics/auditoria/lista.html'
    context_object_name = 'auditorias'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = AuditoriaAlteracao.objects.filter(
            empresa=self.get_empresa()
        ).select_related('usuario', 'content_type').order_by('-timestamp')
        
        # Filtros
        usuario_id = self.request.GET.get('usuario')
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        
        tipo_operacao = self.request.GET.get('tipo_operacao')
        if tipo_operacao:
            queryset = queryset.filter(tipo_operacao=tipo_operacao)
        
        content_type_id = self.request.GET.get('content_type')
        if content_type_id:
            queryset = queryset.filter(content_type_id=content_type_id)
        
        data_inicio = self.request.GET.get('data_inicio')
        if data_inicio:
            queryset = queryset.filter(timestamp__gte=data_inicio)
        
        data_fim = self.request.GET.get('data_fim')
        if data_fim:
            queryset = queryset.filter(timestamp__lte=data_fim)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Estatísticas
        stats = self.get_queryset().aggregate(
            total=Count('id'),
            usuarios_unicos=Count('usuario', distinct=True),
            tipos_objeto=Count('content_type', distinct=True)
        )
        
        # Operações por tipo
        operacoes_por_tipo = self.get_queryset().values('tipo_operacao').annotate(
            total=Count('id')
        )
        
        # Usuários mais ativos
        usuarios_ativos = self.get_queryset().values(
            'usuario__username',
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Content types disponíveis
        content_types = ContentType.objects.all(
        ).distinct().order_by('model')
        
        # Usuários disponíveis
        usuarios = User.objects.all(
        ).distinct().order_by('first_name', 'username')
        
        context.update({
            'stats': stats,
            'operacoes_por_tipo': operacoes_por_tipo,
            'usuarios_ativos': usuarios_ativos,
            'content_types': content_types,
            'usuarios': usuarios,
            'filtro_form': FiltroAuditoriaForm(self.request.GET),
            'title': 'Auditoria de Alterações'
        })
        
        return context


class AuditoriaDetailView(BaseViewMixin, DetailView):
    model = AuditoriaAlteracao
    template_name = 'analytics/auditoria/detail.html'
    context_object_name = 'auditoria'
    
    def get_queryset(self):
        return AuditoriaAlteracao.objects.filter(empresa=self.get_empresa())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        auditoria = self.get_object()
        
        # Buscar outras alterações no mesmo objeto
        alteracoes_relacionadas = AuditoriaAlteracao.objects.filter(
            empresa=self.get_empresa(),
            content_type=auditoria.content_type,
            object_id=auditoria.object_id
        ).exclude(id=auditoria.id).order_by('-timestamp')[:10]
        
        # Buscar outras ações do mesmo usuário
        acoes_usuario = AuditoriaAlteracao.objects.filter(
            empresa=self.get_empresa(),
            usuario=auditoria.usuario,
            timestamp__date=auditoria.timestamp.date()
        ).exclude(id=auditoria.id).order_by('-timestamp')[:10]
        
        context.update({
            'alteracoes_relacionadas': alteracoes_relacionadas,
            'acoes_usuario': acoes_usuario,
            'title': f'Auditoria #{auditoria.id}'
        })
        
        return context


class AuditoriaObjetoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/auditoria/objeto.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        content_type_id = kwargs.get('content_type_id')
        object_id = kwargs.get('object_id')
        
        try:
            content_type = ContentType.objects.get(id=content_type_id)
        except ContentType.DoesNotExist:
            raise Http404('Tipo de conteúdo não encontrado')
        
        # Histórico de alterações do objeto
        historico = AuditoriaAlteracao.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).select_related('usuario').order_by('-timestamp')
        
        # Tentar obter o objeto atual
        objeto_atual = None
        try:
            model_class = content_type.model_class()
            objeto_atual = model_class.objects.get(id=object_id)
        except:
            pass
        
        # Estatísticas do objeto
        stats = {
            'total_alteracoes': historico.count(),
            'usuarios_alteraram': historico.values('usuario').distinct().count(),
            'primeira_alteracao': historico.last().timestamp if historico.exists() else None,
            'ultima_alteracao': historico.first().timestamp if historico.exists() else None,
        }
        
        context.update({
            'content_type': content_type,
            'object_id': object_id,
            'objeto_atual': objeto_atual,
            'historico': historico,
            'stats': stats,
            'title': f'Histórico - {content_type.model} #{object_id}'
        })
        
        return context


class AuditoriaPorUsuarioView(BaseViewMixin, TemplateView):
    template_name = 'analytics/auditoria/usuario.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        usuario_id = kwargs.get('usuario_id')
        
        try:
            usuario = User.objects.get(id=usuario_id)
        except User.DoesNotExist:
            raise Http404('Usuário não encontrado')
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Auditorias do usuário
        auditorias = AuditoriaAlteracao.objects.filter(
            usuario=usuario,
            timestamp__gte=data_inicio
        ).select_related('content_type').order_by('-timestamp')
        
        # Estatísticas
        stats = {
            'total_alteracoes': auditorias.count(),
            'tipos_objeto': auditorias.values('content_type').distinct().count(),
            'ultima_atividade': auditorias.first().timestamp if auditorias.exists() else None,
        }
        
        # Distribuição por tipo de operação
        operacoes = auditorias.values('tipo_operacao').annotate(
            total=Count('id')
        ).order_by('-total')
        
        # Distribuição por tipo de objeto
        tipos_objeto = auditorias.values(
            'content_type__model'
        ).annotate(
            total=Count('id')
        ).order_by('-total')
        
        # Atividade por dia
        atividade_diaria = auditorias.extra(
            select={'dia': 'DATE(timestamp)'}
        ).values('dia').annotate(
            total=Count('id')
        ).order_by('dia')
        
        context.update({
            'usuario_auditoria': usuario,
            'periodo': periodo,
            'stats': stats,
            'operacoes': operacoes,
            'tipos_objeto': tipos_objeto,
            'atividade_diaria': list(atividade_diaria),
            'auditorias_recentes': auditorias[:20],
            'title': f'Auditoria - {usuario.get_full_name() or usuario.username}'
        })
        
        return context


class AuditoriaRelatorioView(BaseViewMixin, TemplateView):
    template_name = 'analytics/auditoria/relatorio.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Auditorias do período
        auditorias = AuditoriaAlteracao.objects.filter(
            timestamp__gte=data_inicio
        )
        
        # Estatísticas gerais
        stats_gerais = auditorias.aggregate(
            total=Count('id'),
            usuarios_unicos=Count('usuario', distinct=True),
            tipos_objeto=Count('content_type', distinct=True)
        )
        
        # Distribuição por tipo de operação
        operacoes = auditorias.values('tipo_operacao').annotate(
            total=Count('id')
        ).order_by('-total')
        
        # Top usuários mais ativos
        usuarios_ativos = auditorias.values(
            'usuario__username',
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Tipos de objeto mais alterados
        tipos_alterados = auditorias.values(
            'content_type__model'
        ).annotate(
            total=Count('id')
        ).order_by('-total')[:10]
        
        # Atividade por dia
        atividade_diaria = auditorias.extra(
            select={'dia': 'DATE(timestamp)'}
        ).values('dia').annotate(
            total=Count('id')
        ).order_by('dia')
        
        # Atividade por hora
        atividade_horaria = auditorias.extra(
            select={'hora': 'EXTRACT(hour FROM timestamp)'}
        ).values('hora').annotate(
            total=Count('id')
        ).order_by('hora')
        
        context.update({
            'periodo': periodo,
            'stats_gerais': stats_gerais,
            'operacoes': operacoes,
            'usuarios_ativos': usuarios_ativos,
            'tipos_alterados': tipos_alterados,
            'atividade_diaria': list(atividade_diaria),
            'atividade_horaria': list(atividade_horaria),
            'title': 'Relatório de Auditoria'
        })
        
        return context


class ExportarAuditoriaView(BaseViewMixin, View):
    def get(self, request):
    
        
        # Parâmetros de filtro
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        usuario_id = request.GET.get('usuario')
        tipo_operacao = request.GET.get('tipo_operacao')
        
        # Query base
        queryset = AuditoriaAlteracao.objects.filter(
            
        ).select_related('usuario', 'content_type')
        
        # Aplicar filtros
        if data_inicio:
            queryset = queryset.filter(timestamp__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(timestamp__lte=data_fim)
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        if tipo_operacao:
            queryset = queryset.filter(tipo_operacao=tipo_operacao)
        
        queryset = queryset.order_by('-timestamp')
        
        # Criar resposta CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="auditoria_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Data/Hora', 'Usuário', 'Operação', 'Tipo de Objeto',
            'ID do Objeto', 'Campos Alterados', 'IP', 'Motivo'
        ])
        
        for auditoria in queryset:
            writer.writerow([
                auditoria.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                auditoria.usuario.get_full_name() or auditoria.usuario.username,
                auditoria.get_tipo_operacao_display(),
                auditoria.content_type.model,
                auditoria.object_id,
                ', '.join(auditoria.campos_alterados) if auditoria.campos_alterados else '',
                auditoria.ip_address or '',
                auditoria.motivo or ''
            ])
        
        return response


# =====================================
# ALERTAS INTELIGENTES
# =====================================

class AlertasListView(BaseViewMixin, ListView):
    model = AlertaInteligente
    template_name = 'analytics/alertas/lista.html'
    context_object_name = 'alertas'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = AlertaInteligente.objects.filter(
            empresa=self.get_empresa()
        ).order_by('-created_at')
        
        # Filtros
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        tipo = self.request.GET.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        prioridade = self.request.GET.get('prioridade')
        if prioridade:
            queryset = queryset.filter(prioridade=prioridade)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Estatísticas
        stats = AlertaInteligente.objects.filter().aggregate(
            total=Count('id'),
            ativos=Count(Case(When(status='ativo', then=1))),
            resolvidos=Count(Case(When(status='resolvido', then=1))),
            criticos=Count(Case(When(prioridade='critica', then=1)))
        )
        
        # Distribuição por tipo
        por_tipo = AlertaInteligente.objects.filter(
            
        ).values('tipo').annotate(
            total=Count('id')
        ).order_by('-total')
        
        context.update({
            'stats': stats,
            'por_tipo': por_tipo,
            'title': 'Alertas Inteligentes'
        })
        
        return context


class AlertaDetailView(BaseViewMixin, DetailView):
    model = AlertaInteligente
    template_name = 'analytics/alertas/detail.html'
    context_object_name = 'alerta'
    
    def get_queryset(self):
        return AlertaInteligente.objects.filter(empresa=self.get_empresa())
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        alerta = self.get_object()
        
        # Notificações do alerta
        notificacoes = alerta.notificacaoalerta_set.select_related('usuario').order_by('-enviada_em')
        
        # Alertas similares
        alertas_similares = AlertaInteligente.objects.filter(
            empresa=self.get_empresa(),
            tipo=alerta.tipo
        ).exclude(id=alerta.id).order_by('-created_at')[:5]
        
        context.update({
            'notificacoes': notificacoes,
            'alertas_similares': alertas_similares,
            'title': f'Alerta: {alerta.titulo}'
        })
        
        return context


class AlertaCreateView(BaseViewMixin, CreateView):
    model = AlertaInteligente
    form_class = AlertaInteligenteForm
    template_name = 'analytics/alertas/form.html'
    success_url = reverse_lazy('analytics:alertas_lista')
    
    def form_valid(self, form):
        form.instance
        
        with transaction.atomic():
            response = super().form_valid(form)
            
            # Criar notificações para usuários selecionados
            usuarios_notificar = form.cleaned_data.get('usuarios_notificar', [])
            for usuario in usuarios_notificar:
                NotificacaoAlerta.objects.create(
                    alerta=self.object,
                    usuario=usuario,
                    via_email=True,
                    via_sistema=True
                )
            
            messages.success(self.request, 'Alerta criado com sucesso!')
            return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Criar Alerta'
        return context


class ResolverAlertaView(BaseViewMixin, View):
    def post(self, request, pk):
        alerta = get_object_or_404(
            AlertaInteligente,
            pk=pk,
            empresa=self.get_empresa()
        )
        
        if alerta.status == 'ativo':
            alerta.status = 'resolvido'
            alerta.resolvido_em = timezone.now()
            alerta.resolvido_por = request.user
            alerta.save()
            
            messages.success(request, f'Alerta "{alerta.titulo}" foi resolvido.')
        else:
            messages.warning(request, 'Este alerta já foi resolvido.')
        
        return redirect('analytics:alerta_detail', pk=pk)


class IgnorarAlertaView(BaseViewMixin, View):
    def post(self, request, pk):
        alerta = get_object_or_404(
            AlertaInteligente,
            pk=pk,
            empresa=self.get_empresa()
        )
        
        if alerta.status == 'ativo':
            alerta.status = 'ignorado'
            alerta.resolvido_em = timezone.now()
            alerta.resolvido_por = request.user
            alerta.save()
            
            messages.success(request, f'Alerta "{alerta.titulo}" foi ignorado.')
        else:
            messages.warning(request, 'Este alerta já foi processado.')
        
        return redirect('analytics:alerta_detail', pk=pk)


class ConfiguracoesAlertasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/alertas/configuracoes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Configurações de Alertas'
        })
        
        return context


class AlertasAtivosView(BaseViewMixin, ListView):
    model = AlertaInteligente
    template_name = 'analytics/alertas/ativos.html'
    context_object_name = 'alertas'
    paginate_by = 25
    
    def get_queryset(self):
        return AlertaInteligente.objects.filter(
            empresa=self.get_empresa(),
            status='ativo'
        ).order_by('-created_at')


class AlertasResolvidosView(BaseViewMixin, ListView):
    model = AlertaInteligente
    template_name = 'analytics/alertas/resolvidos.html'
    context_object_name = 'alertas'
    paginate_by = 25
    
    def get_queryset(self):
        return AlertaInteligente.objects.filter(
            empresa=self.get_empresa(),
            status='resolvido'
        ).order_by('-resolvido_em')


# =====================================
# DASHBOARDS PERSONALIZADOS
# =====================================

class DashboardsListView(BaseViewMixin, ListView):
    model = DashboardPersonalizado
    template_name = 'analytics/dashboards/lista.html'
    context_object_name = 'dashboards'
    paginate_by = 20
    
    def get_queryset(self):
        return DashboardPersonalizado.objects.filter(
            Q(usuario=self.request.user) | Q(publico=True),
            empresa=self.get_empresa()
        ).order_by('-updated_at')


class DashboardCreateView(BaseViewMixin, CreateView):
    model = DashboardPersonalizado
    form_class = DashboardPersonalizadoForm
    template_name = 'analytics/dashboards/form.html'
    success_url = reverse_lazy('analytics:dashboards_lista')
    
    def form_valid(self, form):
        form.instance.usuario = self.request.user
        form.instance
        
        messages.success(self.request, 'Dashboard criado com sucesso!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Criar Dashboard'
        return context


class DashboardPersonalizadoDetailView(BaseViewMixin, DetailView):
    model = DashboardPersonalizado
    template_name = 'analytics/dashboards/detail.html'
    context_object_name = 'dashboard'
    
    def get_queryset(self):
        return DashboardPersonalizado.objects.filter(
            Q(usuario=self.request.user) | Q(publico=True),
            empresa=self.get_empresa()
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = self.get_object()
        
        # Dados dos widgets
        dados_widgets = self._carregar_dados_widgets(dashboard)
        
        context.update({
            'dados_widgets': dados_widgets,
            'title': dashboard.nome
        })
        
        return context
    
    def _carregar_dados_widgets(self, dashboard):
        """Carregar dados para os widgets do dashboard"""
    
        dados = {}
        
        for widget in dashboard.widgets:
            widget_id = widget.get('id')
            widget_type = widget.get('type')
            
            if widget_type == 'vendas_hoje':
                dados[widget_id] = self._dados_vendas_hoje()
            elif widget_type == 'top_produtos':
                dados[widget_id] = self._dados_top_produtos()
            elif widget_type == 'alertas_ativos':
                dados[widget_id] = self._dados_alertas_ativos()
            elif widget_type == 'eventos_tempo_real':
                dados[widget_id] = self._dados_eventos_tempo_real()
        
        return dados
    
    def _dados_vendas_hoje(self, empresa):
        hoje = timezone.now().date()
        return Venda.objects.filter(
            data_venda__date=hoje,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
    
    def _dados_top_produtos(self, empresa):
        # Implementar lógica para top produtos
        return []
    
    def _dados_alertas_ativos(self, empresa):
        return AlertaInteligente.objects.filter(
            status='ativo'
        ).count()
    
    def _dados_eventos_tempo_real(self, empresa):
        return EventoAnalytics.objects.filter(
            timestamp__gte=timezone.now() - timedelta(hours=1)
        ).count()


class DashboardUpdateView(BaseViewMixin, UpdateView):
    model = DashboardPersonalizado
    form_class = DashboardPersonalizadoForm
    template_name = 'analytics/dashboards/form.html'
    
    def get_success_url(self):
        return reverse_lazy('analytics:dashboard_detail', kwargs={'pk': self.object.pk})
    
    def get_queryset(self):
        return DashboardPersonalizado.objects.filter(
            usuario=self.request.user,
            empresa=self.get_empresa()
        )
    
    def form_valid(self, form):
        messages.success(self.request, 'Dashboard atualizado com sucesso!')
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Editar Dashboard: {self.object.nome}'
        return context


class DashboardDeleteView(BaseViewMixin, DeleteView):
    model = DashboardPersonalizado
    template_name = 'analytics/dashboards/delete.html'
    success_url = reverse_lazy('analytics:dashboards_lista')
    
    def get_queryset(self):
        return DashboardPersonalizado.objects.filter(
            usuario=self.request.user,
            empresa=self.get_empresa()
        )
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Dashboard excluído com sucesso!')
        return super().delete(request, *args, **kwargs)


class DashboardPreviewView(BaseViewMixin, DetailView):
    model = DashboardPersonalizado
    template_name = 'analytics/dashboards/preview.html'
    context_object_name = 'dashboard'
    
    def get_queryset(self):
        return DashboardPersonalizado.objects.filter(
            Q(usuario=self.request.user) | Q(publico=True),
            empresa=self.get_empresa()
        )


class DuplicarDashboardView(BaseViewMixin, View):
    def post(self, request, pk):
        dashboard_original = get_object_or_404(
            DashboardPersonalizado,
            pk=pk,
            empresa=self.get_empresa()
        )
        
        # Verificar se o usuário pode acessar este dashboard
        if not (dashboard_original.publico or dashboard_original.usuario == request.user):
            return HttpResponseForbidden()
        
        # Criar cópia
        novo_dashboard = DashboardPersonalizado.objects.create(
            usuario=request.user,
            empresa=self.get_empresa(),
            nome=f"{dashboard_original.nome} (Cópia)",
            descricao=dashboard_original.descricao,
            layout=dashboard_original.layout,
            widgets=dashboard_original.widgets,
            filtros_padrao=dashboard_original.filtros_padrao,
            padrao=False,
            publico=False
        )
        
        messages.success(request, f'Dashboard duplicado com sucesso!')
        return redirect('analytics:dashboard_detail', pk=novo_dashboard.pk)


class CompartilharDashboardView(BaseViewMixin, View):
    def post(self, request, pk):
        dashboard = get_object_or_404(
            DashboardPersonalizado,
            pk=pk,
            usuario=request.user,
            empresa=self.get_empresa()
        )
        
        dashboard.publico = not dashboard.publico
        dashboard.save()
        
        acao = 'compartilhado' if dashboard.publico else 'tornado privado'
        messages.success(request, f'Dashboard {acao} com sucesso!')
        
        return redirect('analytics:dashboard_detail', pk=pk)


class DefinirDashboardPadraoView(BaseViewMixin, View):
    def post(self, request, pk):
        # Remover padrão de outros dashboards do usuário
        DashboardPersonalizado.objects.filter(
            usuario=request.user,
            empresa=self.get_empresa(),
            padrao=True
        ).update(padrao=False)
        
        # Definir este como padrão
        dashboard = get_object_or_404(
            DashboardPersonalizado,
            pk=pk,
            usuario=request.user,
            empresa=self.get_empresa()
        )
        
        dashboard.padrao = True
        dashboard.save()
        
        messages.success(request, f'Dashboard "{dashboard.nome}" definido como padrão!')
        return redirect('analytics:dashboard_detail', pk=pk)


# =====================================
# RELATÓRIOS
# =====================================

class RelatoriosAnalyticsView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Relatórios Analytics'
        })
        
        return context


class RelatorioVendasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/vendas.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Vendas do período
        vendas = Venda.objects.filter(
            data_venda__gte=data_inicio,
            status='finalizada'
        )
        
        # Estatísticas
        stats = vendas.aggregate(
            total_vendas=Sum('total'),
            quantidade_vendas=Count('id'),
            ticket_medio=Avg('total')
        )
        
        # Vendas por dia
        vendas_por_dia = vendas.extra(
            select={'dia': 'DATE(data_venda)'}
        ).values('dia').annotate(
            total=Sum('total'),
            quantidade=Count('id')
        ).order_by('dia')
        
        context.update({
            'periodo': periodo,
            'stats': stats,
            'vendas_por_dia': list(vendas_por_dia),
            'title': 'Relatório de Vendas'
        })
        
        return context


class RelatorioUsuariosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/usuarios.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        # Período para análise
        periodo = int(self.request.GET.get('periodo', 30))
        data_inicio = timezone.now() - timedelta(days=periodo)
        
        # Usuários ativos
        usuarios_ativos = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio,
            usuario__isnull=False
        ).values('usuario').distinct().count()
        
        # Sessões por usuário
        sessoes_por_usuario = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio,
            usuario__isnull=False
        ).values(
            'usuario__username',
            'usuario__first_name',
            'usuario__last_name'
        ).annotate(
            total_eventos=Count('id'),
            ultima_atividade=Max('timestamp')
        ).order_by('-total_eventos')[:20]
        
        context.update({
            'periodo': periodo,
            'usuarios_ativos': usuarios_ativos,
            'sessoes_por_usuario': sessoes_por_usuario,
            'title': 'Relatório de Usuários'
        })
        
        return context


class RelatorioPerformanceView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/performance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Relatório de Performance'
        })
        
        return context


class RelatorioComportamentoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/comportamento.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Relatório de Comportamento'
        })
        
        return context


class RelatorioConversoesView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/conversoes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Relatório de Conversões'
        })
        
        return context


class RelatorioSegmentacaoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/relatorios/segmentacao.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Relatório de Segmentação'
        })
        
        return context


# =====================================
# MÉTRICAS E KPIs
# =====================================

class MetricasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/metricas/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Métricas e KPIs'
        })
        
        return context


class MetricasVendasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/metricas/vendas.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Métricas de Vendas'
        })
        
        return context


class MetricasFinanceirasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/metricas/financeiras.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Métricas Financeiras'
        })
        
        return context


class MetricasOperacionaisView(BaseViewMixin, TemplateView):
    template_name = 'analytics/metricas/operacionais.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Métricas Operacionais'
        })
        
        return context


class MetricasCustomizadasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/metricas/customizadas.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Métricas Customizadas'
        })
        
        return context


# =====================================
# ANÁLISES AVANÇADAS
# =====================================

class AnalisesAvancadasView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análises Avançadas'
        })
        
        return context


class AnaliseCohortView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/cohort.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análise de Cohort'
        })
        
        return context


class AnaliseRFMView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/rfm.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análise RFM'
        })
        
        return context


class AnaliseABCView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/abc.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análise ABC'
        })
        
        return context



class AnaliseTendenciasView(BaseViewMixin, TemplateView):
    """
    Apresenta dados de vendas ao longo do tempo para identificar tendências de crescimento ou declínio.
    """
    template_name = 'relatorios/analises/tendencias.html'
    
    def get_context_data(self, **kwargs):
        # A lógica é similar à de Análise de Vendas, mas o foco do template
        # seria em visualizações que mostrem a linha de tendência.
        context = super().get_context_data(**kwargs)
        data_inicio, data_fim = self.get_datas_filtro()
        
        vendas_tendencia = Venda.objects.filter(
            data__range=(data_inicio, data_fim)
        ).annotate(
            periodo=TruncMonth('data')  # Agrupar por mês para uma visão macro
        ).values('periodo').annotate(
            total=Sum('total'),
            media=Avg('total')
        ).order_by('periodo')
        
        context['dados_tendencia'] = list(vendas_tendencia)
        context['titulo'] = 'Análise de Tendências'
        return context



class AnaliseSazonalidadeView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/sazonalidade.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análise de Sazonalidade'
        })
        
        return context


class AnaliseComparativaView(BaseViewMixin, TemplateView):
    template_name = 'analytics/analises/comparativa.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Análise Comparativa'
        })
        
        return context


# =====================================
# WIDGETS E COMPONENTES
# =====================================

class WidgetsView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Widgets'
        })
        
        return context


class WidgetVendasHojeView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/vendas_hoje.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        hoje = timezone.now().date()
        
        vendas_hoje = Venda.objects.filter(
            data_venda__date=hoje,
            status='finalizada'
        ).aggregate(
            total=Sum('total'),
            quantidade=Count('id')
        )
        
        context.update({
            'vendas_hoje': vendas_hoje,
            'title': 'Vendas Hoje'
        })
        
        return context


class WidgetTopProdutosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/top_produtos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Top Produtos'
        })
        
        return context


class WidgetAlertasAtivosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/alertas_ativos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
    
        
        alertas_ativos = AlertaInteligente.objects.filter(
            status='ativo'
        ).order_by('-created_at')[:5]
        
        context.update({
            'alertas_ativos': alertas_ativos,
            'title': 'Alertas Ativos'
        })
        
        return context


class WidgetPerformanceView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/performance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Performance'
        })
        
        return context


class WidgetMapaUsuariosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/widgets/mapa_usuarios.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Mapa de Usuários'
        })
        
        return context


# =====================================
# CONFIGURAÇÕES
# =====================================

class ConfiguracoesAnalyticsView(BaseViewMixin, TemplateView):
    template_name = 'analytics/configuracoes/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Configurações Analytics'
        })
        
        return context


class ConfiguracoesTrackingView(BaseViewMixin, TemplateView):
    template_name = 'analytics/configuracoes/tracking.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Configurações de Tracking'
        })
        
        return context


class ConfiguracoesRetencaoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/configuracoes/retencao.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Configurações de Retenção'
        })
        
        return context


class ConfiguracoesExportacaoView(BaseViewMixin, TemplateView):
    template_name = 'analytics/configuracoes/exportacao.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Configurações de Exportação'
        })
        
        return context


# =====================================
# EXPORTAÇÃO E IMPORTAÇÃO
# =====================================

class ExportarDadosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/exportacao/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Exportar Dados'
        })
        
        return context


class ExportarEventosView(BaseViewMixin, View):
    def get(self, request):
    
        
        # Parâmetros de filtro
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        categoria = request.GET.get('categoria')
        
        # Query base
        queryset = EventoAnalytics.objects.filter()
        
        # Aplicar filtros
        if data_inicio:
            queryset = queryset.filter(timestamp__gte=data_inicio)
        if data_fim:
            queryset = queryset.filter(timestamp__lte=data_fim)
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        
        queryset = queryset.order_by('-timestamp')
        
        # Criar resposta CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="eventos_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Data/Hora', 'Usuário', 'Categoria', 'Ação', 'Label',
            'Valor', 'País', 'Cidade', 'IP', 'URL'
        ])
        
        for evento in queryset:
            writer.writerow([
                evento.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                evento.usuario.get_full_name() if evento.usuario else 'Anônimo',
                evento.categoria,
                evento.acao,
                evento.label or '',
                evento.valor or '',
                evento.pais or '',
                evento.cidade or '',
                evento.ip_address or '',
                evento.url or ''
            ])
        
        return response


class ExportarRelatorioView(BaseViewMixin, View):
    def get(self, request):
        # Implementar exportação de relatórios personalizados
        return JsonResponse({'status': 'not_implemented'})


class ImportarDadosView(BaseViewMixin, TemplateView):
    template_name = 'analytics/importacao/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'title': 'Importar Dados'
        })
        
        return context


# =====================================
# AJAX E UTILITÁRIOS
# =====================================

class RegistrarEventoAjaxView(BaseViewMixin, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Registrar evento
            evento = EventoAnalytics.objects.create(
                empresa=self.get_empresa(),
                usuario=request.user if request.user.is_authenticated else None,
                categoria=data.get('categoria', 'navegacao'),
                acao=data.get('acao'),
                label=data.get('label', ''),
                propriedades=data.get('propriedades', {}),
                valor=data.get('valor'),
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                url=data.get('url', ''),
                referrer=data.get('referrer', ''),
                pais=data.get('pais', ''),
                cidade=data.get('cidade', '')
            )
            
            return JsonResponse({
                'success': True,
                'evento_id': evento.id
            })
            
        except Exception as e:
            logger.error(f'Erro ao registrar evento: {e}')
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


class MetricasTempoRealAjaxView(BaseViewMixin, View):
    def get(self, request):
    
        
        # Últimas 24 horas
        agora = timezone.now()
        inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Eventos de hoje
        eventos_hoje = EventoAnalytics.objects.filter(
            timestamp__gte=inicio_dia
        ).count()
        
        # Usuários online (últimos 5 minutos)
        usuarios_online = EventoAnalytics.objects.filter(
            timestamp__gte=agora - timedelta(minutes=5),
            usuario__isnull=False
        ).values('usuario').distinct().count()
        
        # Eventos por hora
        eventos_por_hora = EventoAnalytics.objects.filter(
            timestamp__gte=agora - timedelta(hours=24)
        ).extra(
            select={'hora': 'EXTRACT(hour FROM timestamp)'}
        ).values('hora').annotate(
            total=Count('id')
        ).order_by('hora')
        
        return JsonResponse({
            'eventos_hoje': eventos_hoje,
            'usuarios_online': usuarios_online,
            'eventos_por_hora': list(eventos_por_hora)
        })


class AlertasCountAjaxView(BaseViewMixin, View):
    def get(self, request):
    
        
        alertas_count = AlertaInteligente.objects.filter(
            status='ativo'
        ).count()
        
        return JsonResponse({
            'alertas_ativos': alertas_count
        })


class DashboardDadosAjaxView(BaseViewMixin, View):
    def get(self, request):
        dashboard_id = request.GET.get('dashboard_id')
        widget_id = request.GET.get('widget_id')
        
        try:
            dashboard = DashboardPersonalizado.objects.get(
                id=dashboard_id,
                empresa=self.get_empresa()
            )
            
            # Verificar permissão
            if not (dashboard.publico or dashboard.usuario == request.user):
                return JsonResponse({'error': 'Acesso negado'}, status=403)
            
            # Carregar dados do widget específico
            widget = next((w for w in dashboard.widgets if w.get('id') == widget_id), None)
            if not widget:
                return JsonResponse({'error': 'Widget não encontrado'}, status=404)
            
            dados = self._carregar_dados_widget(widget, dashboard.empresa)
            
            return JsonResponse({
                'success': True,
                'dados': dados
            })
            
        except DashboardPersonalizado.DoesNotExist:
            return JsonResponse({'error': 'Dashboard não encontrado'}, status=404)
        except Exception as e:
            logger.error(f'Erro ao carregar dados do dashboard: {e}')
            return JsonResponse({'error': 'Erro interno'}, status=500)
    
    def _carregar_dados_widget(self, widget, empresa):
        """Carregar dados específicos do widget"""
        widget_type = widget.get('type')
        
        if widget_type == 'vendas_hoje':
            hoje = timezone.now().date()
            return Venda.objects.filter(
                ,
                data_venda__date=hoje,
                status='finalizada'
            ).aggregate(
                total=Sum('total'),
                quantidade=Count('id')
            )
        
        # Adicionar outros tipos de widget conforme necessário
        return {}


class WidgetDadosAjaxView(BaseViewMixin, View):
    def get(self, request):
        widget_type = request.GET.get('type')
    
        
        if widget_type == 'vendas_hoje':
            hoje = timezone.now().date()
            dados = Venda.objects.filter(
                ,
                data_venda__date=hoje,
                status='finalizada'
            ).aggregate(
                total=Sum('total'),
                quantidade=Count('id')
            )
        elif widget_type == 'alertas_ativos':
            dados = {
                'count': AlertaInteligente.objects.filter(
                    ,
                    status='ativo'
                ).count()
            }
        elif widget_type == 'eventos_tempo_real':
            dados = {
                'count': EventoAnalytics.objects.filter(
                    ,
                    timestamp__gte=timezone.now() - timedelta(hours=1)
                ).count()
            }
        else:
            dados = {}
        
        return JsonResponse({
            'success': True,
            'dados': dados
        })


class FiltrarDadosAjaxView(BaseViewMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            tipo_dados = data.get('tipo')
            filtros = data.get('filtros', {})
        
            
            if tipo_dados == 'eventos':
                queryset = EventoAnalytics.objects.filter()
                
                if filtros.get('categoria'):
                    queryset = queryset.filter(categoria=filtros['categoria'])
                if filtros.get('data_inicio'):
                    queryset = queryset.filter(timestamp__gte=filtros['data_inicio'])
                if filtros.get('data_fim'):
                    queryset = queryset.filter(timestamp__lte=filtros['data_fim'])
                
                dados = list(queryset.values(
                    'id', 'categoria', 'acao', 'label', 'timestamp'
                )[:100])
                
            elif tipo_dados == 'vendas':
                # Implementar filtros para vendas
                dados = []
            else:
                dados = []
            
            return JsonResponse({
                'success': True,
                'dados': dados
            })
            
        except Exception as e:
            logger.error(f'Erro ao filtrar dados: {e}')
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


# =====================================
# API REST
# =====================================

class EventoAnalyticsViewSet(viewsets.ModelViewSet):
    queryset = EventoAnalytics.objects.all()
    serializer_class = EventoAnalyticsSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        empresa = self.request.user.funcionario.empresa
        return EventoAnalytics.objects.filter()
    
    @action(detail=False, methods=['post'])
    def registrar(self, request):
        """Endpoint para registrar novos eventos"""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(
                empresa=request.user.funcionario.empresa,
                usuario=request.user,
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request)
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AuditoriaAlteracaoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditoriaAlteracao.objects.all()
    serializer_class = AuditoriaAlteracaoSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        empresa = self.request.user.funcionario.empresa
        return AuditoriaAlteracao.objects.filter()


class AlertaInteligenteViewSet(viewsets.ModelViewSet):
    queryset = AlertaInteligente.objects.all()
    serializer_class = AlertaInteligenteSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        empresa = self.request.user.funcionario.empresa
        return AlertaInteligente.objects.filter()
    
    @action(detail=True, methods=['post'])
    def resolver(self, request, pk=None):
        """Endpoint para resolver alertas"""
        alerta = self.get_object()
        if alerta.status == 'ativo':
            alerta.status = 'resolvido'
            alerta.resolvido_em = timezone.now()
            alerta.resolvido_por = request.user
            alerta.save()
            return Response({'status': 'resolvido'})
        return Response({'error': 'Alerta já foi processado'}, status=status.HTTP_400_BAD_REQUEST)


class DashboardPersonalizadoViewSet(viewsets.ModelViewSet):
    queryset = DashboardPersonalizado.objects.all()
    serializer_class = DashboardPersonalizadoSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        empresa = self.request.user.funcionario.empresa
        return DashboardPersonalizado.objects.filter(
            Q(usuario=self.request.user) | Q(publico=True),
            
        )


@method_decorator(csrf_exempt, name='dispatch')
class RegistrarEventoAPIView(BaseViewMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            evento = EventoAnalytics.objects.create(
                empresa=self.get_empresa(),
                usuario=request.user if request.user.is_authenticated else None,
                categoria=data.get('categoria', 'navegacao'),
                acao=data.get('acao'),
                label=data.get('label', ''),
                propriedades=data.get('propriedades', {}),
                valor=data.get('valor'),
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                url=data.get('url', ''),
                referrer=data.get('referrer', ''),
                pais=data.get('pais', ''),
                cidade=data.get('cidade', '')
            )
            
            return JsonResponse({
                'success': True,
                'evento_id': evento.id,
                'message': 'Evento registrado com sucesso'
            })
            
        except Exception as e:
            logger.error(f'Erro na API de registro de evento: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Erro interno do servidor'
            }, status=500)


class MetricasAPIView(BaseViewMixin, View):
    def get(self, request):
        try:
        
            periodo = int(request.GET.get('periodo', 7))
            data_inicio = timezone.now() - timedelta(days=periodo)
            
            # Eventos do período
            eventos = EventoAnalytics.objects.filter(
                ,
                timestamp__gte=data_inicio
            )
            
            # Métricas básicas
            metricas = {
                'total_eventos': eventos.count(),
                'usuarios_unicos': eventos.values('usuario').distinct().count(),
                'eventos_por_categoria': list(eventos.values('categoria').annotate(
                    total=Count('id')
                ).order_by('-total')),
                'eventos_por_dia': list(eventos.extra(
                    select={'dia': 'DATE(timestamp)'}
                ).values('dia').annotate(
                    total=Count('id')
                ).order_by('dia'))
            }
            
            return JsonResponse({
                'success': True,
                'periodo_dias': periodo,
                'metricas': metricas
            })
            
        except Exception as e:
            logger.error(f'Erro na API de métricas: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Erro interno do servidor'
            }, status=500)


class AlertasAtivosAPIView(BaseViewMixin, View):
    def get(self, request):
        try:
        
            
            alertas = AlertaInteligente.objects.filter(
                ,
                status='ativo'
            ).order_by('-created_at')
            
            dados_alertas = []
            for alerta in alertas:
                dados_alertas.append({
                    'id': alerta.id,
                    'tipo': alerta.tipo,
                    'prioridade': alerta.prioridade,
                    'titulo': alerta.titulo,
                    'mensagem': alerta.mensagem,
                    'created_at': alerta.created_at.isoformat(),
                    'dados_contexto': alerta.dados_contexto
                })
            
            return JsonResponse({
                'success': True,
                'total': len(dados_alertas),
                'alertas': dados_alertas
            })
            
        except Exception as e:
            logger.error(f'Erro na API de alertas ativos: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Erro interno do servidor'
            }, status=500)


class DashboardDadosAPIView(BaseViewMixin, View):
    def get(self, request):
        try:
            dashboard_id = request.GET.get('dashboard_id')
        
            
            dashboard = DashboardPersonalizado.objects.get(
                id=dashboard_id,
                
            )
            
            # Verificar permissão
            if not (dashboard.publico or dashboard.usuario == request.user):
                return JsonResponse({
                    'success': False,
                    'message': 'Acesso negado'
                }, status=403)
            
            # Carregar dados dos widgets
            dados_widgets = {}
            for widget in dashboard.widgets:
                widget_id = widget.get('id')
                widget_type = widget.get('type')
                
                # Implementar carregamento de dados por tipo de widget
                dados_widgets[widget_id] = self._carregar_dados_widget_api(widget_type, empresa)
            
            return JsonResponse({
                'success': True,
                'dashboard': {
                    'id': dashboard.id,
                    'nome': dashboard.nome,
                    'layout': dashboard.layout,
                    'widgets': dashboard.widgets,
                    'dados_widgets': dados_widgets
                }
            })
            
        except DashboardPersonalizado.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Dashboard não encontrado'
            }, status=404)
        except Exception as e:
            logger.error(f'Erro na API de dados do dashboard: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Erro interno do servidor'
            }, status=500)
    
    def _carregar_dados_widget_api(self, widget_type, empresa):
        """Carregar dados do widget para API"""
        if widget_type == 'vendas_hoje':
            hoje = timezone.now().date()
            return Venda.objects.filter(
                ,
                data_venda__date=hoje,
                status='finalizada'
            ).aggregate(
                total=Sum('total'),
                quantidade=Count('id')
            )
        elif widget_type == 'alertas_ativos':
            return {
                'count': AlertaInteligente.objects.filter(
                    ,
                    status='ativo'
                ).count()
            }
        else:
            return {}


class AuditoriaAPIView(BaseViewMixin, View):
    def get(self, request):
        try:
        
            
            # Parâmetros de filtro
            limit = int(request.GET.get('limit', 50))
            offset = int(request.GET.get('offset', 0))
            objeto_id = request.GET.get('objeto_id')
            content_type_id = request.GET.get('content_type_id')
            usuario_id = request.GET.get('usuario_id')
            
            # Query base
            queryset = AuditoriaAlteracao.objects.filter()
            
            # Aplicar filtros
            if objeto_id and content_type_id:
                queryset = queryset.filter(
                    object_id=objeto_id,
                    content_type_id=content_type_id
                )
            if usuario_id:
                queryset = queryset.filter(usuario_id=usuario_id)
            
            # Ordenar e paginar
            queryset = queryset.select_related('usuario', 'content_type').order_by('-timestamp')
            total = queryset.count()
            auditorias = queryset[offset:offset+limit]
            
            # Serializar dados
            dados_auditorias = []
            for auditoria in auditorias:
                dados_auditorias.append({
                    'id': auditoria.id,
                    'timestamp': auditoria.timestamp.isoformat(),
                    'usuario': {
                        'id': auditoria.usuario.id,
                        'username': auditoria.usuario.username,
                        'nome_completo': auditoria.usuario.get_full_name()
                    },
                    'tipo_operacao': auditoria.tipo_operacao,
                    'content_type': auditoria.content_type.model,
                    'object_id': auditoria.object_id,
                    'campos_alterados': auditoria.campos_alterados,
                    'motivo': auditoria.motivo,
                    'ip_address': auditoria.ip_address
                })
            
            return JsonResponse({
                'success': True,
                'total': total,
                'limit': limit,
                'offset': offset,
                'auditorias': dados_auditorias
            })
            
        except Exception as e:
            logger.error(f'Erro na API de auditoria: {e}')
            return JsonResponse({
                'success': False,
                'message': 'Erro interno do servidor'
            }, status=500)
