# apps/integracoes/urls.py
from django.urls import path

from . import views

app_name = 'integracoes'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('guia/', views.GuiaView.as_view(), name='guia'),
    path('configurar/<slug:codigo>/', views.ConfigurarView.as_view(), name='configurar'),
    path('<int:pk>/', views.DetalheView.as_view(), name='detalhe'),
    path('<int:pk>/ativar/', views.AtivarView.as_view(), name='ativar'),
    path('<int:pk>/desativar/', views.DesativarView.as_view(), name='desativar'),
    path('<int:pk>/testar/', views.TestarView.as_view(), name='testar'),
    path('<int:pk>/enviar-teste/', views.EnviarTesteView.as_view(), name='enviar_teste'),
    path('<int:pk>/regenerar-segredo/', views.RegenerarSegredoView.as_view(), name='regenerar_segredo'),
    path('<int:pk>/limpar-credenciais/', views.LimparCredenciaisView.as_view(), name='limpar_credenciais'),
    path('<int:pk>/remover/', views.RemoverView.as_view(), name='remover'),

    path('logs/', views.LogListView.as_view(), name='log_lista'),
    path('logs/<int:pk>/', views.LogDetailView.as_view(), name='log_detalhe'),
    path('webhooks/', views.WebhookListView.as_view(), name='webhook_lista'),
    path('webhooks/<int:pk>/', views.WebhookDetailView.as_view(), name='webhook_detalhe'),
    path('webhooks/<int:pk>/reprocessar/', views.ReprocessarWebhookView.as_view(), name='webhook_reprocessar'),

    # Receptor público (URL que se regista no serviço externo)
    path('webhook/<str:token>/', views.webhook_receber, name='webhook_receber'),
]