# apps/analytics/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'analytics'

# Router para API REST
router = DefaultRouter()
router.register(r'eventos', views.EventoAnalyticsViewSet)
router.register(r'auditorias', views.AuditoriaAlteracaoViewSet)
router.register(r'alertas', views.AlertaInteligenteViewSet)
router.register(r'dashboards', views.DashboardPersonalizadoViewSet)

urlpatterns = [
    # =====================================
    # DASHBOARD PRINCIPAL
    # =====================================
    path('', views.AnalyticsDashboardView.as_view(), name='dashboard'),
    path('overview/', views.AnalyticsOverviewView.as_view(), name='overview'),
    
    # =====================================
    # EVENTOS ANALYTICS
    # =====================================
    path('eventos/', views.EventoAnalyticsListView.as_view(), name='eventos_lista'),
    path('eventos/tempo-real/', views.EventosTempoRealView.as_view(), name='eventos_tempo_real'),
    path('eventos/categoria/<str:categoria>/', views.EventosPorCategoriaView.as_view(), name='eventos_categoria'),
    path('eventos/usuario/<int:usuario_id>/', views.EventosPorUsuarioView.as_view(), name='eventos_usuario'),
    path('eventos/mapa/', views.EventosMapaView.as_view(), name='eventos_mapa'),
    path('eventos/funil/', views.FunilConversaoView.as_view(), name='funil_conversao'),
    
    # =====================================
    # AUDITORIA
    # =====================================
    path('auditoria/', views.AuditoriaListView.as_view(), name='auditoria_lista'),
    path('auditoria/<int:pk>/', views.AuditoriaDetailView.as_view(), name='auditoria_detail'),
    path('auditoria/objeto/<int:content_type_id>/<int:object_id>/', views.AuditoriaObjetoView.as_view(), name='auditoria_objeto'),
    path('auditoria/usuario/<int:usuario_id>/', views.AuditoriaPorUsuarioView.as_view(), name='auditoria_usuario'),
    path('auditoria/relatorio/', views.AuditoriaRelatorioView.as_view(), name='auditoria_relatorio'),
    path('auditoria/exportar/', views.ExportarAuditoriaView.as_view(), name='auditoria_exportar'),
    
    # =====================================
    # ALERTAS INTELIGENTES
    # =====================================
    path('alertas/', views.AlertasListView.as_view(), name='alertas_lista'),
    path('alertas/<int:pk>/', views.AlertaDetailView.as_view(), name='alerta_detail'),
    path('alertas/criar/', views.AlertaCreateView.as_view(), name='alerta_create'),
    path('alertas/<int:pk>/resolver/', views.ResolverAlertaView.as_view(), name='alerta_resolver'),
    path('alertas/<int:pk>/ignorar/', views.IgnorarAlertaView.as_view(), name='alerta_ignorar'),
    path('alertas/configuracoes/', views.ConfiguracoesAlertasView.as_view(), name='alertas_configuracoes'),
    path('alertas/ativos/', views.AlertasAtivosView.as_view(), name='alertas_ativos'),
    path('alertas/resolvidos/', views.AlertasResolvidosView.as_view(), name='alertas_resolvidos'),
    
    # =====================================
    # DASHBOARDS PERSONALIZADOS
    # =====================================
    path('dashboards/', views.DashboardsListView.as_view(), name='dashboards_lista'),
    path('dashboards/criar/', views.DashboardCreateView.as_view(), name='dashboard_create'),
    path('dashboards/<int:pk>/', views.DashboardPersonalizadoDetailView.as_view(), name='dashboard_detail'),
    path('dashboards/<int:pk>/editar/', views.DashboardUpdateView.as_view(), name='dashboard_update'),
    path('dashboards/<int:pk>/deletar/', views.DashboardDeleteView.as_view(), name='dashboard_delete'),
    path('dashboards/<int:pk>/preview/', views.DashboardPreviewView.as_view(), name='dashboard_personalizado_preview'),
    path('dashboards/<int:pk>/duplicar/', views.DuplicarDashboardView.as_view(), name='dashboard_duplicar'),
    path('dashboards/<int:pk>/compartilhar/', views.CompartilharDashboardView.as_view(), name='dashboard_compartilhar'),
    path('dashboards/<int:pk>/definir-padrao/', views.DefinirDashboardPadraoView.as_view(), name='dashboard_definir_padrao'),
    
    # =====================================
    # RELATÓRIOS
    # =====================================
    path('relatorios/', views.RelatoriosAnalyticsView.as_view(), name='relatorios'),
    path('relatorios/vendas/', views.RelatorioVendasView.as_view(), name='relatorio_vendas'),
    path('relatorios/usuarios/', views.RelatorioUsuariosView.as_view(), name='relatorio_usuarios'),
    path('relatorios/performance/', views.RelatorioPerformanceView.as_view(), name='relatorio_performance'),
    path('relatorios/comportamento/', views.RelatorioComportamentoView.as_view(), name='relatorio_comportamento'),
    path('relatorios/conversoes/', views.RelatorioConversoesView.as_view(), name='relatorio_conversoes'),
    path('relatorios/segmentacao/', views.RelatorioSegmentacaoView.as_view(), name='relatorio_segmentacao'),
    
    # =====================================
    # MÉTRICAS E KPIs
    # =====================================
    path('metricas/', views.MetricasView.as_view(), name='metricas'),
    path('metricas/vendas/', views.MetricasVendasView.as_view(), name='metricas_vendas'),
    path('metricas/financeiras/', views.MetricasFinanceirasView.as_view(), name='metricas_financeiras'),
    path('metricas/operacionais/', views.MetricasOperacionaisView.as_view(), name='metricas_operacionais'),
    path('metricas/customizadas/', views.MetricasCustomizadasView.as_view(), name='metricas_customizadas'),
    
    # =====================================
    # ANÁLISES AVANÇADAS
    # =====================================
    path('analises/', views.AnalisesAvancadasView.as_view(), name='analises'),
    path('analises/cohort/', views.AnaliseCohortView.as_view(), name='analise_cohort'),
    path('analises/rfm/', views.AnaliseRFMView.as_view(), name='analise_rfm'),
    path('analises/abc/', views.AnaliseABCView.as_view(), name='analise_abc'),
    path('analises/tendencias/', views.AnaliseTendenciasView.as_view(), name='analise_tendencias'),
    path('analises/sazonalidade/', views.AnaliseSazonalidadeView.as_view(), name='analise_sazonalidade'),
    path('analises/comparativa/', views.AnaliseComparativaView.as_view(), name='analise_comparativa'),
    
    # =====================================
    # WIDGETS E COMPONENTES
    # =====================================
    path('widgets/', views.WidgetsView.as_view(), name='widgets'),
    path('widgets/vendas-hoje/', views.WidgetVendasHojeView.as_view(), name='widget_vendas_hoje'),
    path('widgets/top-produtos/', views.WidgetTopProdutosView.as_view(), name='widget_top_produtos'),
    path('widgets/alertas-ativos/', views.WidgetAlertasAtivosView.as_view(), name='widget_alertas_ativos'),
    path('widgets/performance/', views.WidgetPerformanceView.as_view(), name='widget_performance'),
    path('widgets/mapa-usuarios/', views.WidgetMapaUsuariosView.as_view(), name='widget_mapa_usuarios'),
    
    # =====================================
    # CONFIGURAÇÕES
    # =====================================
    path('configuracoes/', views.ConfiguracoesAnalyticsView.as_view(), name='configuracoes'),
    path('configuracoes/tracking/', views.ConfiguracoesTrackingView.as_view(), name='configuracoes_tracking'),
    path('configuracoes/retencao/', views.ConfiguracoesRetencaoView.as_view(), name='configuracoes_retencao'),
    path('configuracoes/alertas/', views.ConfiguracoesAlertasView.as_view(), name='configuracoes_alertas'),
    path('configuracoes/exportacao/', views.ConfiguracoesExportacaoView.as_view(), name='configuracoes_exportacao'),
    
    # =====================================
    # EXPORTAÇÃO E IMPORTAÇÃO
    # =====================================
    path('exportar/', views.ExportarDadosView.as_view(), name='exportar_dados'),
    path('exportar/eventos/', views.ExportarEventosView.as_view(), name='exportar_eventos'),
    path('exportar/relatorio/', views.ExportarRelatorioView.as_view(), name='exportar_relatorio'),
    path('importar/', views.ImportarDadosView.as_view(), name='importar_dados'),
    
    # =====================================
    # AJAX E UTILITÁRIOS
    # =====================================
    path('ajax/evento/', views.RegistrarEventoAjaxView.as_view(), name='ajax_registrar_evento'),
    path('ajax/metricas-tempo-real/', views.MetricasTempoRealAjaxView.as_view(), name='ajax_metricas_tempo_real'),
    path('ajax/alertas-count/', views.AlertasCountAjaxView.as_view(), name='ajax_alertas_count'),
    path('ajax/dashboard-dados/', views.DashboardDadosAjaxView.as_view(), name='ajax_dashboard_dados'),
    path('ajax/widget-dados/', views.WidgetDadosAjaxView.as_view(), name='ajax_widget_dados'),
    path('ajax/filtrar-dados/', views.FiltrarDadosAjaxView.as_view(), name='ajax_filtrar_dados'),
    
    # =====================================
    # API REST
    # =====================================
    
    # API Personalizada
    path('api/registrar-evento/', views.RegistrarEventoAPIView.as_view(), name='api_registrar_evento'),
    path('api/metricas/', views.MetricasAPIView.as_view(), name='api_metricas'),
    path('api/alertas-ativos/', views.AlertasAtivosAPIView.as_view(), name='api_alertas_ativos'),
    path('api/dashboard-dados/', views.DashboardDadosAPIView.as_view(), name='api_dashboard_dados'),
    path('api/auditoria/', views.AuditoriaAPIView.as_view(), name='api_auditoria'),
]