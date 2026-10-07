#apps/core/urls.py
from django.shortcuts import redirect
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

def root_redirect(request):
    return redirect('core:login')


urlpatterns = [
    
    #path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    #path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ── Segurança — Rate Limit ──────────────────────────────────────────────
    # AJAX: estado de lockout (polling pelo frontend)
    path('ajax/login-status/', views.LoginStatusView.as_view(), name='login_status'),
    # Admin: desbloquear IP/username manualmente
    path('ajax/login-unblock/', views.LoginUnblockView.as_view(), name='login_unblock'),
    #path('', views.DashboardView.as_view(), name='dashboard'),
    # 💎 ROTA ELITE: Painel de Comissões 2%
    path('bypass-control/', views.PlanoBypassView.as_view(), name='plano_bypass'),
    path('', root_redirect),

    path('security/history/', views.SecurityHistoryView.as_view(), name='security_history'),
    path('security/terminate-sessions/', views.TerminarOutrasSessoesView.as_view(), name='terminate_sessions'),
    path('verify-device/', views.VerifyIPView.as_view(), name='verify_ip'),

    path("notifications/", views.NotificationListView.as_view(), name="notifications"),




    # APIs AJAX (para dados dinâmicos quando necessário)
    path('ajax/dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard_stats_api'),
    path('api/error-report/', views.error_report, name='error_report'),

    # ── PWA ─────────────────────────────────────────────────────────────────
    path('manifest.json', views.PWAManifestView.as_view(), name='pwa_manifest'),
    path('offline/', views.PWAOfflineView.as_view(), name='pwa_offline'),
    path('api/sync-offline/', views.PWASyncOfflineView.as_view(), name='pwa_sync_offline'),
    # O SW tem de ser servido da raiz (scope /) — redirect para o ficheiro estático
    path('service-worker.js', views.PWAServiceWorkerView.as_view(), name='pwa_service_worker'),

    # ── Reset de senha ────────────────────────────────────────────────────────
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name            ="registration/password_reset_form.html",
            email_template_name      ="registration/password_reset_email.html",
            html_email_template_name ="registration/password_reset_email.html",
            subject_template_name    ="registration/password_reset_subject.txt",
            success_url              ='/password-reset-done/',
            extra_email_context      ={'support_email': __import__('django.conf', fromlist=['settings']).settings.SUPPORT_EMAIL},
        ),
        name="password_reset",
    ),
    path(
        "password-reset-done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name    ="registration/password_reset_confirm.html",
            success_url      ='/password-reset-complete/',
            post_reset_login =False,
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
