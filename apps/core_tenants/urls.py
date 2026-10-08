# apps/core_tenants/urls.py
from django.urls import path

from . import views

app_name = 'core_tenants'

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    path('security/history/', views.SecurityHistoryView.as_view(), name='security_history'),
    path('security/terminate-sessions/', views.TerminarOutrasSessoesView.as_view(), name='terminate_sessions'),
    path('verify-device/', views.VerifyIPView.as_view(), name='verify_ip'),

    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('ajax/notifications/count/', views.NotificacaoCountAjaxView.as_view(), name='notifications_count_ajax'),
    path('ajax/notifications/<int:pk>/read/', views.NotificacaoMarcarLidaView.as_view(), name='notification_mark_read'),
    path('ajax/notifications/read-all/', views.NotificacaoMarcarTodasLidasView.as_view(), name='notifications_read_all'),

    path('ajax/dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard_stats_api'),
]