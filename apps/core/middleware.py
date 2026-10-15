# apps/core/middleware.py
import threading
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.db import connection
import logging


# ==============================================================
# 🔹 1. REDIRECIONAMENTO DE PERFIL (Protegido)
# ==============================================================
class AccountsProfileRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/accounts/profile'):
            if request.user.is_authenticated:
                return HttpResponseRedirect('/')
            else:
                return HttpResponseRedirect('/accounts/login/')
        
        return self.get_response(request)



   
# ==============================================================
# 🔹 5. THREAD LOCAL USER (O Cérebro)
# ==============================================================

_thread_locals = threading.local()


class ThreadLocalUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)

        try:
            return self.get_response(request)
        finally:
            if hasattr(_thread_locals, 'user'):
                del _thread_locals.user


def get_current_authenticated_user():
    """Retorna o usuário armazenado na thread atual."""
    return getattr(_thread_locals, 'user', None)




# ==============================================================
# 🔹 6. RATE LIMIT NO ENDPOINT DE LOGIN (DDoS + Brute-Force)
# ==============================================================

logger = logging.getLogger('core.security')


class RateLimitLoginMiddleware:
    """
    Middleware de rate limiting para o endpoint de login.

    Posição na stack (base.py): imediatamente APÓS SessionMiddleware e
    CsrfViewMiddleware, ANTES de AuthenticationMiddleware — para bloquear
    ataques antes de qualquer query ao BD de utilizadores.

    O que faz:
      ┌────────────────────────────────────────────────────────────────┐
      │  1. Só actua em POST /login/ (deixa tudo o resto passar)      │
      │  2. Verifica lockout de IP no cache Redis (microsegundos)     │
      │  3. Verifica lockout de username no cache Redis               │
      │  4. Se bloqueado: devolve 429 imediatamente, sem tocar no BD │
      │  5. Adiciona cabeçalhos Retry-After e X-RateLimit-*          │
      └────────────────────────────────────────────────────────────────┘

    Separação de responsabilidades:
      - Este middleware apenas BLOQUEIA com base no cache.
      - O REGISTO de novas falhas e incremento de contadores é feito
        na CustomLoginView.form_invalid() — onde sabemos que a password
        estava errada e não apenas o CSRF token ou outro erro.
    """

    # URL paths onde aplicar a protecção (sem namespace — middleware actua
    # antes da resolução de URLs pelo Django)
    LOGIN_PATHS = {'/login/', '/accounts/login/'}

    def __init__(self, get_response):
        self.get_response = get_response
        # Importar o serviço aqui para evitar import circular no arranque
        self._svc = None

    def _get_svc(self):
        if self._svc is None:
            from apps.core.services.rate_limit_service import LoginRateLimitService
            self._svc = LoginRateLimitService
        return self._svc

    def __call__(self, request):
        # Só aplicar em POST ao endpoint de login
        if request.method == 'POST' and self._is_login_path(request.path):
            response = self._check_rate_limit(request)
            if response is not None:
                return response

        response = self.get_response(request)

        # Injectar cabeçalhos informativos em respostas do login
        if self._is_login_path(request.path):
            self._add_security_headers(request, response)

        return response

    def _is_login_path(self, path: str) -> bool:
        """True se o path corresponde a um endpoint de login."""
        # Suporte a paths com ou sem trailing slash e com prefixos de subdomínio
        clean = path.rstrip('/')
        return any(clean.endswith(p.rstrip('/')) for p in self.LOGIN_PATHS)

    def _check_rate_limit(self, request) -> 'HttpResponse | None':
        """
        Verifica lockout. Retorna uma resposta de bloqueio (429) ou None
        se o request pode continuar.
        """
        try:
            svc = self._get_svc()
            ip       = svc.get_ip(request)
            username = request.POST.get('username', '').strip()

            ip_locked   = svc.is_ip_locked(ip)
            user_locked = svc.is_user_locked(username) if username else False

            if not (ip_locked or user_locked):
                return None  # Sem bloqueio — deixar passar

            ttl = svc.lockout_ttl(request, username)

            # Logar a tentativa bloqueada
            logger.warning(
                "BLOQUEIO RATE LIMIT — IP: %s | username: %s | ttl: %ds | path: %s",
                ip, username or '(vazio)', ttl, request.path
            )

            # Determinar tipo de resposta (JSON para AJAX, HTML para browser)
            is_ajax = (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or 'application/json' in request.headers.get('Accept', '')
            )

            if is_ajax:
                resp = JsonResponse({
                    'locked':          True,
                    'lockout_seconds': ttl,
                    'message':         self._lockout_message(ttl),
                }, status=429)
            else:
                minutos  = ttl // 60
                segundos = ttl % 60
                tempo_msg = f"{minutos}m {segundos}s" if minutos else f"{ttl}s"
                resp = render(request, 'registration/login.html', {
                    'locked_out':            True,
                    'lockout_seconds':       ttl,
                    'lockout_tempo_legivel': tempo_msg,
                    'show_captcha':          False,
                    'login_attempts':        0,
                    'hcaptcha_site_key':     getattr(settings, 'HCAPTCHA_SITE_KEY', ''),
                }, status=429)

            # Cabeçalhos standard para rate limiting (RFC 6585 + RFC 7231)
            resp['Retry-After']        = str(ttl)
            resp['X-RateLimit-Limit']  = str(getattr(settings, 'LOGIN_MAX_ATTEMPTS_IP', 10))
            resp['X-RateLimit-Reset']  = str(ttl)
            resp['X-Content-Type-Options'] = 'nosniff'
            return resp

        except Exception as exc:
            # Nunca deixar o middleware quebrar o fluxo normal do sistema
            logger.error("RateLimitLoginMiddleware erro inesperado: %s", exc)
            return None

    def _add_security_headers(self, request, response):
        """Adiciona cabeçalhos de segurança e informativos nas respostas do login."""
        try:
            svc  = self._get_svc()
            ip   = svc.get_ip(request)
            attempts = svc.get_ip_attempts(ip)
            limit    = getattr(settings, 'LOGIN_MAX_ATTEMPTS_IP', 10)

            response['X-RateLimit-Limit']     = str(limit)
            response['X-RateLimit-Remaining'] = str(max(0, limit - attempts))
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options']        = 'DENY'
        except Exception:
            pass  # Silencioso — não quebrar por causa de cabeçalhos

    @staticmethod
    def _lockout_message(ttl: int) -> str:
        minutos = ttl // 60
        if minutos > 0:
            return (f"Demasiadas tentativas de login falhadas. "
                    f"Tente novamente em {minutos} minuto(s).")
        return f"Demasiadas tentativas. Aguarde {ttl} segundo(s)."
