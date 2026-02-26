# apps/licencas/urls.py
from django.urls import path, include
from . import views


# API Router

app_name = 'licencas'

urlpatterns = [
    # =====================================
    # DASHBOARD E LISTAGENS
    # =====================================
    path('', views.LicencaDashboardView.as_view(), name='dashboard'),
    path('lista/', views.LicencaListView.as_view(), name='lista'),
    path('vencimentos/', views.VencimentosView.as_view(), name='vencimentos'),
    
    # =====================================
    # GESTÃO DE LICENÇAS
    # =====================================
    path('nova/', views.LicencaCreateView.as_view(), name='create'),
    path('<int:pk>/', views.LicencaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.LicencaUpdateView.as_view(), name='update'),
    path('<int:pk>/deletar/', views.LicencaDeleteView.as_view(), name='delete'),
    
    # =====================================
    # RENOVAÇÕES
    # =====================================
    path('<int:pk>/renovar/', views.RenovarLicencaView.as_view(), name='renovar'),
    path('renovacoes/', views.RenovacaoListView.as_view(), name='renovacao_lista'),
    path('renovacoes/<int:pk>/', views.RenovacaoDetailView.as_view(), name='renovacao_detail'),
    path('renovacoes/<int:pk>/finalizar/', views.FinalizarRenovacaoView.as_view(), name='renovacao_finalizar'),
    
    
    
    # =====================================
    # ALERTAS E NOTIFICAÇÕES
    # =====================================
    path('alertas/', views.AlertasView.as_view(), name='alertas'),
    path('configurar-alertas/', views.ConfigurarAlertasView.as_view(), name='configurar_alertas'),
    path('notificacoes/', views.NotificacoesView.as_view(), name='notificacoes'),
    
    
    # =====================================
    # RELATÓRIOS E COMPLIANCE
    # =====================================
    path('relatorios/', views.LicencaRelatoriosView.as_view(), name='relatorios'),
    path('relatorios/compliance/', views.RelatorioComplianceView.as_view(), name='relatorio_compliance'),
    path('relatorios/vencimentos/', views.RelatorioVencimentosView.as_view(), name='relatorio_vencimentos'),
    path('relatorios/custos/', views.RelatorioCustosView.as_view(), name='relatorio_custos'),
    
    
    # =====================================
    # HISTÓRICO E AUDITORIA
    # =====================================
    path('historico/', views.HistoricoLicencasView.as_view(), name='historico'),
    path('auditoria/', views.AuditoriaLicencasView.as_view(), name='auditoria'),
    path('logs/', views.LogsLicencasView.as_view(), name='logs'),
    
    
    # =====================================
    # API REST
    # =====================================
    
    # API Personalizada
    path('api/verificar-status/', views.VerificarStatusAPIView.as_view(), name='api_verificar_status'),
    path('api/proximos-vencimentos/', views.ProximosVencimentosAPIView.as_view(), name='api_proximos_vencimentos'),
]