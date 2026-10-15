# apps/fiscal/middleware.py
"""Implementação corrigida do bloqueio de regeneração de chaves.

A configuração AssinaturaDigital é singleton dentro do schema do tenant e não
possui FK `empresa`; por isso não deve ser consultada por `empresa_id`.
O bloqueio acontece em `process_view`, quando `resolver_match` já existe.
"""
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from .models import AssinaturaDigital


class ProtegeRegeneracaoChaveMiddleware:
    def __init__(self, get_response, cooldown_minutes=10):
        self.get_response = get_response
        self.cooldown = timedelta(minutes=cooldown_minutes)

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, "resolver_match", None)
        url_name = getattr(match, "url_name", "")
        if url_name not in {"regenerar_chave", "regenerar_chaves_fiscais"} or request.method != "POST":
            return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_superuser:
            return None

        # Uma linha por schema/tenant: não filtrar por empresa_id.
        configuracao = AssinaturaDigital.objects.filter(pk=1).first()
        momento = None
        if configuracao:
            for attr in ("configurada_em", "configured_at", "updated_at"):
                momento = getattr(configuracao, attr, None)
                if momento:
                    break
        if momento:
            if timezone.is_naive(momento):
                momento = timezone.make_aware(momento, timezone.get_current_timezone())
            if timezone.now() - momento < self.cooldown:
                messages.error(request, "A regeneração das chaves foi recentemente executada. Aguarde antes de repetir a operação.")
                return redirect(request.META.get("HTTP_REFERER") or "/")
        return None
