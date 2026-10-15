# apps/core/services/rate_limit_service.py
"""
Rate limiting do endpoint de login.

Camada 1: cache/Redis para bloquear tentativas rapidamente.
Camada 2: LoginAttempt na base de dados para auditoria.

Resiliência para desenvolvimento: se o Redis estiver indisponível, o serviço
usa temporariamente um cache em memória por processo, evitando que um erro de
cache transforme uma autenticação inválida num HTTP 500. Esse fallback não é
partilhado entre processos/servidores; Redis deve continuar ativo em produção.
"""

import hashlib
import logging
from threading import RLock
from time import monotonic

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("core.security")

MAX_IP = getattr(settings, "LOGIN_MAX_ATTEMPTS_IP", 10)
MAX_USER = getattr(settings, "LOGIN_MAX_ATTEMPTS_USER", 5)
WINDOW = getattr(settings, "LOGIN_RATE_WINDOW_SECONDS", 300)
LOCKOUT = getattr(settings, "LOGIN_LOCKOUT_DURATION_SECONDS", 900)
CAPTCHA_AT = getattr(settings, "LOGIN_CAPTCHA_THRESHOLD", 3)

# Cache de contingência (apenas processo local, utilizado quando Redis falha).
_FALLBACK_CACHE = {}
_FALLBACK_LOCK = RLock()
_CACHE_FAILURE_REPORTED = False


def _cache_key_ip_count(ip: str) -> str:
    return f"login_rl:ip:{ip}"


def _cache_key_ip_lock(ip: str) -> str:
    return f"login_rl:ip_lock:{ip}"


def _cache_key_user_count(username: str) -> str:
    digest = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()[:16]
    return f"login_rl:user:{digest}"


def _cache_key_user_lock(username: str) -> str:
    digest = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()[:16]
    return f"login_rl:user_lock:{digest}"


def _note_cache_failure(exc: Exception) -> None:
    """Regista uma única mensagem enquanto o backend de cache estiver em falha."""
    global _CACHE_FAILURE_REPORTED
    with _FALLBACK_LOCK:
        if not _CACHE_FAILURE_REPORTED:
            logger.error(
                "Cache/Redis indisponível; a limitação de tentativas está em modo "
                "de contingência local. Verifique o serviço Redis. Causa: %s",
                exc,
            )
            _CACHE_FAILURE_REPORTED = True


def _note_cache_success() -> None:
    global _CACHE_FAILURE_REPORTED
    with _FALLBACK_LOCK:
        if _CACHE_FAILURE_REPORTED:
            logger.info("Ligação ao cache/Redis restabelecida.")
            _CACHE_FAILURE_REPORTED = False


def _fallback_get_entry(key: str):
    """Devolve uma entrada de contingência, removendo-a se já expirou."""
    entry = _FALLBACK_CACHE.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at is not None and expires_at <= monotonic():
        _FALLBACK_CACHE.pop(key, None)
        return None
    return entry


def _fallback_get(key: str, default=None):
    with _FALLBACK_LOCK:
        entry = _fallback_get_entry(key)
        return default if entry is None else entry[0]


def _fallback_set(key: str, value, timeout=None) -> bool:
    with _FALLBACK_LOCK:
        if timeout is not None and timeout <= 0:
            _FALLBACK_CACHE.pop(key, None)
            return True
        expires_at = None if timeout is None else monotonic() + timeout
        _FALLBACK_CACHE[key] = (value, expires_at)
        return True


def _fallback_ttl(key: str) -> int:
    with _FALLBACK_LOCK:
        entry = _fallback_get_entry(key)
        if entry is None:
            return -2  # chave inexistente, de acordo com a convenção Redis
        expires_at = entry[1]
        if expires_at is None:
            return -1  # existe, mas sem expiração
        return max(0, int(expires_at - monotonic()))


def _fallback_expire(key: str, timeout: int) -> bool:
    with _FALLBACK_LOCK:
        entry = _fallback_get_entry(key)
        if entry is None:
            return False
        if timeout <= 0:
            _FALLBACK_CACHE.pop(key, None)
            return True
        _FALLBACK_CACHE[key] = (entry[0], monotonic() + timeout)
        return True


def _fallback_increment_window(key: str, timeout: int) -> int:
    """Incrementa um contador local, mantendo a expiração da janela original."""
    with _FALLBACK_LOCK:
        entry = _fallback_get_entry(key)
        if entry is None:
            value = 1
            expires_at = monotonic() + timeout if timeout and timeout > 0 else None
        else:
            value = int(entry[0]) + 1
            expires_at = entry[1]
            if expires_at is None and timeout and timeout > 0:
                expires_at = monotonic() + timeout
        _FALLBACK_CACHE[key] = (value, expires_at)
        return value


def _cache_get(key: str, default=None):
    try:
        value = cache.get(key, default)
        _note_cache_success()
        return value
    except Exception as exc:  # inclui falhas de ligação do cliente Redis
        _note_cache_failure(exc)
        return _fallback_get(key, default)


def _cache_set(key: str, value, timeout=None) -> bool:
    try:
        result = cache.set(key, value, timeout=timeout)
        _note_cache_success()
        return result
    except Exception as exc:
        _note_cache_failure(exc)
        return _fallback_set(key, value, timeout)


def _cache_ttl(key: str) -> int:
    try:
        ttl = cache.ttl(key)
        _note_cache_success()
        return -2 if ttl is None else int(ttl)
    except Exception as exc:
        _note_cache_failure(exc)
        return _fallback_ttl(key)


def _cache_expire(key: str, timeout: int) -> bool:
    try:
        result = cache.expire(key, timeout)
        _note_cache_success()
        return result
    except Exception as exc:
        _note_cache_failure(exc)
        return _fallback_expire(key, timeout)


def _cache_delete_many(keys) -> int:
    try:
        result = cache.delete_many(keys)
        _note_cache_success()
        return result
    except Exception as exc:
        _note_cache_failure(exc)
        with _FALLBACK_LOCK:
            deleted = 0
            for key in keys:
                if key in _FALLBACK_CACHE:
                    _FALLBACK_CACHE.pop(key, None)
                    deleted += 1
            return deleted


def _cache_increment_window(key: str, timeout: int) -> int:
    """Incrementa atomicamente no Redis e assegura TTL; usa memória se falhar."""
    try:
        # add() cria a chave já com TTL, se for a primeira tentativa da janela.
        if cache.add(key, 1, timeout=timeout):
            _note_cache_success()
            return 1

        try:
            value = int(cache.incr(key))
        except ValueError:
            # A chave pode ter expirado entre add() e incr().
            if cache.add(key, 1, timeout=timeout):
                _note_cache_success()
                return 1
            value = int(cache.incr(key))

        ttl = cache.ttl(key)
        if ttl is None or int(ttl) < 0:
            cache.expire(key, timeout)
        _note_cache_success()
        return value
    except Exception as exc:
        _note_cache_failure(exc)
        return _fallback_increment_window(key, timeout)


class LoginRateLimitService:
    """API para bloqueio de login por IP e por nome de utilizador."""

    @classmethod
    def get_ip(cls, request) -> str:
        """Obtém o IP; X-Forwarded-For só deve ser confiado atrás de proxy confiável."""
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "0.0.0.0")

    @classmethod
    def is_ip_locked(cls, ip: str) -> bool:
        return bool(_cache_get(_cache_key_ip_lock(ip), False))

    @classmethod
    def is_user_locked(cls, username: str) -> bool:
        if not username:
            return False
        return bool(_cache_get(_cache_key_user_lock(username), False))

    @classmethod
    def is_locked(cls, request, username: str = "") -> bool:
        ip = cls.get_ip(request)
        return cls.is_ip_locked(ip) or cls.is_user_locked(username)

    @classmethod
    def get_ip_attempts(cls, ip: str) -> int:
        return int(_cache_get(_cache_key_ip_count(ip), 0) or 0)

    @classmethod
    def get_user_attempts(cls, username: str) -> int:
        if not username:
            return 0
        return int(_cache_get(_cache_key_user_count(username), 0) or 0)

    @classmethod
    def get_attempts(cls, request, username: str = "") -> int:
        ip = cls.get_ip(request)
        return max(cls.get_ip_attempts(ip), cls.get_user_attempts(username))

    @classmethod
    def needs_captcha(cls, request, username: str = "") -> bool:
        return cls.get_attempts(request, username) >= CAPTCHA_AT

    @classmethod
    def lockout_ttl(cls, request, username: str = "") -> int:
        ip = cls.get_ip(request)
        ttl_ip = _cache_ttl(_cache_key_ip_lock(ip)) if cls.is_ip_locked(ip) else 0
        ttl_user = (
            _cache_ttl(_cache_key_user_lock(username))
            if cls.is_user_locked(username)
            else 0
        )
        return max(0, int(max(ttl_ip or 0, ttl_user or 0)))

    @classmethod
    def record_failure(cls, request, username: str = "", schema: str = "") -> dict:
        """Regista falha, actualiza contadores e aplica lockout quando necessário."""
        ip = cls.get_ip(request)
        ip_count = _cache_increment_window(_cache_key_ip_count(ip), WINDOW)
        user_count = (
            _cache_increment_window(_cache_key_user_count(username), WINDOW)
            if username
            else 0
        )

        ip_locked = ip_count >= MAX_IP
        user_locked = bool(username and user_count >= MAX_USER)

        if ip_locked:
            _cache_set(_cache_key_ip_lock(ip), True, timeout=LOCKOUT)
            logger.warning(
                "LOGIN LOCKOUT — IP %s bloqueado após %d falhas (schema: %s)",
                ip,
                ip_count,
                schema or "public",
            )

        if user_locked:
            _cache_set(_cache_key_user_lock(username), True, timeout=LOCKOUT)
            logger.warning(
                "LOGIN LOCKOUT — username '%s' bloqueado após %d falhas (ip: %s)",
                username,
                user_count,
                ip,
            )

        cls._persistir_tentativa(
            ip=ip,
            username=username,
            schema=schema,
            request=request,
            bloqueado=ip_locked or user_locked,
        )

        return {
            "ip": ip,
            "ip_attempts": ip_count,
            "user_attempts": user_count,
            "ip_locked": ip_locked,
            "user_locked": user_locked,
            "lockout_seconds": LOCKOUT if (ip_locked or user_locked) else 0,
        }

    @classmethod
    def _persistir_tentativa(cls, ip, username, schema, request, bloqueado=False):
        """Persiste auditoria sem deixar uma falha de auditoria derrubar o login."""
        try:
            from apps.core.models import LoginAttempt

            LoginAttempt.objects.create(
                ip_address=ip,
                username_tentado=username[:150] if username else "",
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                schema_name=schema or "",
                bloqueado=bloqueado,
            )
        except Exception:
            logger.exception("Falha ao persistir LoginAttempt")

    @classmethod
    def reset_on_success(cls, request, username: str = ""):
        """Limpa contadores e bloqueios após autenticação bem-sucedida."""
        ip = cls.get_ip(request)
        keys = [_cache_key_ip_count(ip), _cache_key_ip_lock(ip)]
        if username:
            keys.extend(
                [_cache_key_user_count(username), _cache_key_user_lock(username)]
            )
        _cache_delete_many(keys)
        logger.info(
            "Login bem-sucedido — contadores limpos para IP %s / user '%s'",
            ip,
            username,
        )

    @classmethod
    def unblock_ip(cls, ip: str):
        """Desbloqueia manualmente um IP (uso administrativo)."""
        _cache_delete_many([_cache_key_ip_count(ip), _cache_key_ip_lock(ip)])
        logger.info("IP %s desbloqueado manualmente", ip)

    @classmethod
    def unblock_user(cls, username: str):
        """Desbloqueia manualmente um utilizador (uso administrativo)."""
        _cache_delete_many(
            [_cache_key_user_count(username), _cache_key_user_lock(username)]
        )
        logger.info("Username '%s' desbloqueado manualmente", username)
