# apps/core_tenants/signals.py
# Sinal de login — regista no AuditoriaAcesso (modelo em apps/core SHARED_APPS)
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

# AuditoriaAcesso fica em apps/core.models (SHARED_APPS), não aqui
from apps.core.models import AuditoriaAcesso


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0].strip() if x else request.META.get('REMOTE_ADDR', '')


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditoriaAcesso.objects.create(
        usuario=user,
        acao='LOGIN',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
    )
