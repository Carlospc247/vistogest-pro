# apps/fiscal/middleware.py
from django.utils import timezone
from django.shortcuts import HttpResponseForbidden
from django.urls import resolve
from .models import AssinaturaDigital
from datetime import timedelta

class ProtegeRegeneracaoChaveMiddleware:
    """
    Bloqueia regeneração de chaves via views se a ultima geração for
    mais recente que X minutos e o user não for superuser.
    Regra apenas aplica para URLs nomeadas 'fiscal:gerar_chaves' (exemplo).
    """
    window_minutes = 60  # ajustar conforme politica

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resolver = resolve(request.path_info)
        nome = getattr(resolver, 'url_name', '')
        if nome in ('baixar_chave_publica', 'gerar_chaves_admin', 'assinar_documento_api'):
            # permite downloads e assinaturas normais
            return self.get_response(request)

        if nome == 'gerar_chaves_rsa':  # adapta para o nome real que usares
            if not request.user.is_superuser:
                # encontram-se empresas específicas no POST (ou queryset) — aqui apenas um bloqueio simples
                empresa_id = request.POST.get('empresa_id') or request.GET.get('empresa_id')
                if empresa_id:
                    assinatura = AssinaturaDigital.objects.filter(empresa_id=empresa_id).first()
                    if assinatura and assinatura.data_geracao:
                        delta = timezone.now() - assinatura.data_geracao
                        if delta < timedelta(minutes=self.window_minutes):
                            return HttpResponseForbidden("Regeneração de chave bloqueada: janela de segurança ativa.")
        return self.get_response(request)
