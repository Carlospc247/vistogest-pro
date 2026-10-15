from django.urls import path
from . import views
app_name="configuracoes"
urlpatterns=[
    path("dashboard/",views.ConfiguracoesDashboardView.as_view(),name="dashboard_configuracoes"),
    path("fiscal/detalhes/",views.ConfiguracaoFiscalDetailView.as_view(),name="fiscal_detail"),
    path("fiscal/editar/",views.ConfiguracaoFiscalUpdateView.as_view(),name="fiscal_update"),
    path("fiscal/eliminar/",views.ConfiguracaoFiscalDeleteView.as_view(),name="fiscal_delete"),
    path("fiscal/banco/adicionar/",views.DadosBancariosCreateView.as_view(),name="dados_bancarios_create"),
    path("fiscal/banco/editar/<int:pk>/",views.DadosBancariosUpdateView.as_view(),name="dados_bancarios_update"),
    path("fiscal/banco/apagar/<int:pk>/",views.DadosBancariosDeleteView.as_view(),name="dados_bancarios_delete"),
    path("interface/",views.PersonalizacaoInterfaceUpdateView.as_view(),name="interface"),
    path("suporte/",views.SuporteView.as_view(),name="suporte"),
    path("backup/",views.BackupConfiguracaoUpdateView.as_view(),name="backup_config"),
    path("backup/historico/",views.BackupListView.as_view(),name="backup_historico"),
    path("backup/executar/",views.BackupManualCreateView.as_view(),name="backup_manual"),
    path("backup/download/<int:pk>/",views.BackupDownloadView.as_view(),name="backup_download"),
    path("backup/restaurar/<int:pk>/",views.BackupRestoreView.as_view(),name="backup_restore"),
]
