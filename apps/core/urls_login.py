# apps/core/urls_login.py
# URLs usados no schema PUBLIC (urls_public.py).
# Contém apenas login, logout e reset de senha — sem dashboard nem módulos ERP.
from django.conf import settings
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'core'

_extra_email_ctx = {'support_email': getattr(settings, 'SUPPORT_EMAIL', 'suporte@vistogest.pro')}

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ── Segurança — Rate Limit ────────────────────────────────────────────────
    path('ajax/login-status/', views.LoginStatusView.as_view(), name='login_status'),
    path('ajax/login-unblock/', views.LoginUnblockView.as_view(), name='login_unblock'),

    # ── PWA — necessário no public schema para o base.html funcionar ──────────
    path('manifest.json', views.PWAManifestView.as_view(), name='pwa_manifest'),
    path('offline/', views.PWAOfflineView.as_view(), name='pwa_offline'),
    path('service-worker.js', views.PWAServiceWorkerView.as_view(), name='pwa_service_worker'),
    path('api/sync-offline/', views.PWASyncOfflineView.as_view(), name='pwa_sync_offline'),
    path('api/error-report/', views.error_report, name='error_report'),

    # ── URLs usadas no base.html — necessitam de existir em ambos os schemas ──
    path('bypass-control/', views.PlanoBypassView.as_view(), name='plano_bypass'),
    
    # ── Reset de senha — fluxo completo ──────────────────────────────────────
    # 1. Formulário: utilizador introduz o email
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name            ="registration/password_reset_form.html",
            email_template_name      ="registration/password_reset_email.html",
            html_email_template_name ="registration/password_reset_email.html",
            subject_template_name    ="registration/password_reset_subject.txt",
            success_url              ='/password-reset-done/',
            extra_email_context      =_extra_email_ctx,
        ),
        name="password_reset",
    ),
    # 2. Confirmação: "verifique o seu email"
    path(
        "password-reset-done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    # 3. Link do email: formulário de nova senha
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name ="registration/password_reset_confirm.html",
            success_url   ='/password-reset-complete/',
            post_reset_login=False,
        ),
        name="password_reset_confirm",
    ),
    # 4. Conclusão: "senha alterada com sucesso"
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]
