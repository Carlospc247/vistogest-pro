# apps/configuracoes/urls.py
from django.urls import path, include
from . import views



# API Router

app_name = 'configuracoes'


urlpatterns = [
    # ==============================================================================
    # PAINEL PRINCIPAL
    # ==============================================================================
    # A página de entrada da secção de configurações.
    path('', views.ConfiguracoesDashboardView.as_view(), name='dashboard'),

    path('fiscal/detalhes/', views.ConfiguracaoFiscalDetailView.as_view(), name='fiscal_detail'),

    # 📝 Página para editar os dados da empresa e as configurações fiscais.
    path('fiscal/editar/', views.ConfiguracaoFiscalUpdateView.as_view(), name='fiscal_update'),
    
    # 📝 URL para eliminar a configuração fiscal.
    path('fiscal/eliminar/', views.ConfiguracaoFiscalDeleteView.as_view(), name='fiscal_delete'),
   
    path('fiscal/banco/adicionar/', views.DadosBancariosCreateView.as_view(), name='dados_bancarios_create'),
    path('fiscal/banco/editar/<int:pk>/', views.DadosBancariosUpdateView.as_view(), name='dados_bancarios_update'),
    path('fiscal/banco/apagar/<int:pk>/', views.DadosBancariosDeleteView.as_view(), name='dados_bancarios_delete'),
    # ==============================================================================
    # PERSONALIZAÇÃO
    # ==============================================================================
    # Página para o utilizador ou empresa alterar a aparência do sistema.
    path('interface/', views.PersonalizacaoInterfaceUpdateView.as_view(), name='interface'),

    # Página para contactar o suporte.
    path('suporte/', views.SuporteView.as_view(), name='suporte'),

    # ==============================================================================
    # BACKUP & RESTAURAÇÃO
    # ==============================================================================
    # Página para configurar a política de backups automáticos.
    path('backup/', views.BackupConfiguracaoUpdateView.as_view(), name='backup_config'),
    
    # Página para ver a lista de backups já realizados.
    path('backup/historico/', views.BackupListView.as_view(), name='backup_historico'),
    
    # URL de ação para iniciar um backup manual (via POST).
    path('backup/executar/', views.BackupManualCreateView.as_view(), name='backup_manual'),
    
    # URL para descarregar um ficheiro de backup específico.
    path('backup/download/<int:pk>/', views.BackupDownloadView.as_view(), name='backup_download'),
    
    # URL de ação para restaurar um backup (operação crítica).
    path('backup/restaurar/<int:pk>/', views.BackupRestoreView.as_view(), name='backup_restore'),

]