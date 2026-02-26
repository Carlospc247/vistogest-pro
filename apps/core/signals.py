from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from .models import AuditoriaAcesso

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    AuditoriaAcesso.objects.create(
        usuario=user,
        acao='LOGIN',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT')
    )