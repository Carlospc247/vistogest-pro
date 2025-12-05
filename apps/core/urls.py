#apps/core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard principal
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Categorias
    path('categorias/criar/', views.CriarCategoriaView.as_view(), name='criar_categoria'),
    path('categorias/editar/<int:categoria_id>/', views.EditarCategoriaView.as_view(), name='editar_categoria'),
    path('categorias/deletar/<int:categoria_id>/', views.DeletarCategoriaView.as_view(), name='deletar_categoria'),
    path('categorias/toggle/<int:categoria_id>/', views.ToggleCategoriaView.as_view(), name='toggle_categoria'),
    
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    
    # APIs AJAX (para dados dinâmicos quando necessário)
    path('ajax/dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard_stats_api'),
    path('api/error-report/', views.error_report, name='error_report'),
]
