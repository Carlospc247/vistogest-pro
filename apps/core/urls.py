#apps/core/urls.py
from django.shortcuts import redirect
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

def root_redirect(request):
    return redirect('core:login')


urlpatterns = [
    
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', views.DashboardView.as_view(), name='dashboard'),
    # 💎 ROTA ELITE: Painel de Comissões 2%
    path('bypass-control/', views.PlanoBypassView.as_view(), name='plano_bypass'),
    path('', root_redirect),
   
    path('security/history/', views.SecurityHistoryView.as_view(), name='security_history'),
    path('security/terminate-sessions/', views.TerminarOutrasSessoesView.as_view(), name='terminate_sessions'),
    path('verify-device/', views.VerifyIPView.as_view(), name='verify_ip'),

    
    # Categorias
    path('categorias/criar/', views.CriarCategoriaView.as_view(), name='criar_categoria'),
    path('categorias/editar/<int:categoria_id>/', views.EditarCategoriaView.as_view(), name='editar_categoria'),
    path('categorias/deletar/<int:categoria_id>/', views.DeletarCategoriaView.as_view(), name='deletar_categoria'),
    path('categorias/toggle/<int:categoria_id>/', views.ToggleCategoriaView.as_view(), name='toggle_categoria'),
    
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    
    # APIs AJAX (para dados dinâmicos quando necessário)
    path('ajax/dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard_stats_api'),
    path('api/error-report/', views.error_report, name='error_report'),

    # Reset de senha
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.html",     # Fallback texto
            html_email_template_name="registration/password_reset_email.html",# Versão visual HTML
            subject_template_name="registration/password_reset_subject.txt"   # Assunto personalizado
        ),
        name="password_reset",
    ),

    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="registration/password_reset_form.html",
        email_template_name="registration/password_reset_email.html",
        html_email_template_name="registration/password_reset_email.html",
        subject_template_name="registration/password_reset_subject.txt"
    ), name="password_reset"),

    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),

    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
