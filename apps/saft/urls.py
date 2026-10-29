from django.urls import path
from . import views

app_name = "saft"
urlpatterns = [
    #path("exportar/", views.SaftExportView.as_view(), name="saft_export"),
    #path("historico/", views.SaftHistoricoView.as_view(), name="historico"),
    #path("download/<int:export_id>/", views.SaftDownloadView.as_view(), name="download"),
    #path("visualizar/<int:export_id>/", views.SaftVisualizarView.as_view(), name="visualizar"),
    #path("validar/", views.SaftValidarView.as_view(), name="validar"),
    #path("ajax/status/", views.SaftStatusAjaxView.as_view(), name="ajax-status"),
]
