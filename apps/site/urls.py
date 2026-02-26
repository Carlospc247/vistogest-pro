# apps/site/urls.py
from django.urls import path, include
from .views import *

app_name = 'site'

urlpatterns = [
    # Dashboard e Edição
    path('dashboard/', SiteConfigDashboardView.as_view(), name='configuracao_dashboard'),
    path('publicar/<int:pk>/', PublicarSiteView.as_view(), name='publicar'),
    path('design-global/', AtualizarDesignGlobalView.as_view(), name='design_global'),
    
    # Gestão de Blocos (AJAX/Post)
    path('pagina/<int:pagina_id>/adicionar-secao/', AdicionarSecaoView.as_view(), name='adicionar_secao'),
    path('reordenar-secoes/', ReordenarSecoesView.as_view(), name='reordenar_secoes'),
    path('secao/<int:secao_id>/dados/', EditarConteudoSecaoView.as_view(), name='get_secao_dados'),
    path('secao/<int:secao_id>/editar/', EditarConteudoSecaoView.as_view(), name='editar_secao'),
    
    # Integrações
    path('processar-agendamento/', ProcessarAgendamentoSiteView.as_view(), name='processar_agendamento'),
    
    # Site Público
    path('<slug:slug>/', PaginaDetailView.as_view(), name='pagina_detalhe'),
    path('<slug:slug>/preview/<uuid:token>/', SitePreviewView.as_view(), name='preview'),
]