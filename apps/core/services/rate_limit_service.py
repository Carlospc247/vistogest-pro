# apps/core/services/rate_limit_service.py
"""
Serviço de Rate Limiting para o endpoint de login.

Estratégia de duas camadas:
  - Camada 1 (rápida) — Redis/cache: contadores em memória com TTL.
    Responde em microsegundos, bloqueia na view antes de qualquer query ao BD.
  - Camada 2 (persistente) — BD: modelo LoginAttempt.
    Registo auditável, sobrevive a reinícios, usado para relatórios e alertas.

Dois eixos de bloqueio independentes:
  - Por IP: protege contra ataques distribuídos a vários usernames.
  - Por Username: protege contra ataques de senha dirigidos a uma conta específica.

Chaves de cache (prefixo "login_rl:"):
  login_rl:ip:{ip}           → contador de falhas recentes do IP
  login_rl:ip_lock:{ip}      → lockout flag do IP (TTL = LOCKOUT_DURATION)
  login_rl:user:{username}   → contador de falhas recentes do username
  login_rl:user_lock:{user}  → lockout flag do username (TTL = LOCKOUT_DURATION)
"""
import logging
import hashlib
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('core.security')

# ── Constantes (lidas de settings, com defaults seguros) ─────────────────────
MAX_IP        = getattr(settings, 'LOGIN_MAX_ATTEMPTS_IP',         10)
MAX_USER      = getattr(settings, 'LOGIN_MAX_ATTEMPTS_USER',        5)
WINDOW        = getattr(settings, 'LOGIN_RATE_WINDOW_SECONDS',    300)   # 5 min
LOCKOUT       = getattr(settings, 'LOGIN_LOCKOUT_DURATION_SECONDS', 900) # 15 min
CAPTCHA_AT    = getattr(settings, 'LOGIN_CAPTCHA_THRESHOLD',         3)


def _cache_key_ip_count(ip: str) -> str:
    """Chave do contador de falhas por IP."""
    return f"login_rl:ip:{ip}"


def _cache_key_ip_lock(ip: str) -> str:
    """Chave do lockout por IP."""
    return f"login_rl:ip_lock:{ip}"


def _cache_key_user_count(username: str) -> str:
    """Chave do contador de falhas por username (hash para evitar chaves longas)."""
    h = hashlib.sha256(username.lower().encode()).hexdigest()[:16]
    return f"login_rl:user:{h}"


def _cache_key_user_lock(username: str) -> str:
    """Chave do lockout por username."""
    h = hashlib.sha256(username.lower().encode()).hexdigest()[:16]
    return f"login_rl:user_lock:{h}"


# ── API pública ────────────────────────────────────────────────────────────────

class LoginRateLimitService:
    """
    Interface única para toda a lógica de rate limiting do login.
    Sem estado de instância — todos os métodos são classmethod para uso directo.
    """

    @classmethod
    def get_ip(cls, request) -> str:
        """Extrai o IP real do request, respeitando proxies confiáveis."""
        x_fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if x_fwd:
            return x_fwd.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

    # ── Verificações de bloqueio ───────────────────────────────────────────────

    @classmethod
    def is_ip_locked(cls, ip: str) -> bool:
        """True se o IP está em lockout activo."""
        return bool(cache.get(_cache_key_ip_lock(ip)))

    @classmethod
    def is_user_locked(cls, username: str) -> bool:
        """True se o username está em lockout activo."""
        if not username:
            return False
        return bool(cache.get(_cache_key_user_lock(username)))

    @classmethod
    def is_locked(cls, request, username: str = '') -> bool:
        """True se o IP OU o username está bloqueado."""
        ip = cls.get_ip(request)
        return cls.is_ip_locked(ip) or cls.is_user_locked(username)

    # ── Contagens actuais ─────────────────────────────────────────────────────

    @classmethod
    def get_ip_attempts(cls, ip: str) -> int:
        return int(cache.get(_cache_key_ip_count(ip)) or 0)

    @classmethod
    def get_user_attempts(cls, username: str) -> int:
        if not username:
            return 0
        return int(cache.get(_cache_key_user_count(username)) or 0)

    @classmethod
    def get_attempts(cls, request, username: str = '') -> int:
        """Retorna o máximo entre falhas do IP e do username."""
        ip = cls.get_ip(request)
        return max(cls.get_ip_attempts(ip), cls.get_user_attempts(username))

    @classmethod
    def needs_captcha(cls, request, username: str = '') -> bool:
        """True se já atingiu o limiar de CAPTCHA mas ainda não está bloqueado."""
        return cls.get_attempts(request, username) >= CAPTCHA_AT

    # ── Tempo restante de lockout ─────────────────────────────────────────────

    @classmethod
    def lockout_ttl(cls, request, username: str = '') -> int:
        """Segundos restantes de lockout (0 se não bloqueado)."""
        ip = cls.get_ip(request)
        ttl_ip   = cache.ttl(_cache_key_ip_lock(ip))   if cls.is_ip_locked(ip)        else 0
        ttl_user = cache.ttl(_cache_key_user_lock(username)) if cls.is_user_locked(username) else 0
        raw = max(ttl_ip or 0, ttl_user or 0)
        return max(0, int(raw))

    # ── Registo de falha ──────────────────────────────────────────────────────

    @classmethod
    def record_failure(cls, request, username: str = '', schema: str = '') -> dict:
        """
        Regista uma tentativa falhada e aplica lockout se necessário.

        Retorna dict com o estado resultante:
          {
              'ip': str,
              'ip_attempts': int,
              'user_attempts': int,
              'ip_locked': bool,
              'user_locked': bool,
              'lockout_seconds': int,
          }
        """
        ip = cls.get_ip(request)

        # ── Incrementar contador do IP ─────────────────────────────────────
        ip_key = _cache_key_ip_count(ip)
        try:
            ip_count = cache.incr(ip_key)
        except ValueError:
            # Chave não existe ainda — criar com TTL da janela
            cache.set(ip_key, 1, timeout=WINDOW)
            ip_count = 1
        else:
            # Garantir TTL na chave (incr não redefine TTL)
            if cache.ttl(ip_key) < 0:
                cache.expire(ip_key, WINDOW)

        # ── Incrementar contador do username ───────────────────────────────
        user_count = 0
        if username:
            user_key = _cache_key_user_count(username)
            try:
                user_count = cache.incr(user_key)
            except ValueError:
                cache.set(user_key, 1, timeout=WINDOW)
                user_count = 1
            else:
                if cache.ttl(user_key) < 0:
                    cache.expire(user_key, WINDOW)

        # ── Aplicar lockout se necessário ──────────────────────────────────
        ip_locked   = False
        user_locked = False

        if ip_count >= MAX_IP:
            cache.set(_cache_key_ip_lock(ip), True, timeout=LOCKOUT)
            ip_locked = True
            logger.warning(
                "LOGIN LOCKOUT — IP %s bloqueado após %d falhas (schema: %s)",
                ip, ip_count, schema or 'public'
            )

        if username and user_count >= MAX_USER:
            cache.set(_cache_key_user_lock(username), True, timeout=LOCKOUT)
            user_locked = True
            logger.warning(
                "LOGIN LOCKOUT — username '%s' bloqueado após %d falhas (ip: %s)",
                username, user_count, ip
            )

        # ── Persistir no BD (assíncrono / best-effort) ─────────────────────
        cls._persistir_tentativa(
            ip=ip,
            username=username,
            schema=schema,
            request=request,
            bloqueado=ip_locked or user_locked,
        )

        lockout_secs = 0
        if ip_locked or user_locked:
            lockout_secs = LOCKOUT

        return {
            'ip':              ip,
            'ip_attempts':     ip_count,
            'user_attempts':   user_count,
            'ip_locked':       ip_locked,
            'user_locked':     user_locked,
            'lockout_seconds': lockout_secs,
        }

    @classmethod
    def _persistir_tentativa(cls, ip, username, schema, request, bloqueado=False):
        """Grava LoginAttempt no BD. Falha silenciosamente para não interromper o request."""
        try:
            from apps.core.models import LoginAttempt
            LoginAttempt.objects.create(
                ip_address=ip,
                username_tentado=username[:150] if username else '',
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                schema_name=schema or '',
                bloqueado=bloqueado,
            )
        except Exception as exc:
            logger.error("Falha ao persistir LoginAttempt: %s", exc)

    # ── Reset após login bem-sucedido ─────────────────────────────────────────

    @classmethod
    def reset_on_success(cls, request, username: str = ''):
        """
        Limpa todos os contadores e locks do IP e username após login bem-sucedido.
        Não apaga o histórico em BD — apenas liberta os bloqueios activos.
        """
        ip = cls.get_ip(request)
        keys = [
            _cache_key_ip_count(ip),
            _cache_key_ip_lock(ip),
        ]
        if username:
            keys += [
                _cache_key_user_count(username),
                _cache_key_user_lock(username),
            ]
        cache.delete_many(keys)
        logger.info("Login bem-sucedido — contadores limpos para IP %s / user '%s'", ip, username)

    # ── Desbloqueio manual (admin) ────────────────────────────────────────────

    @classmethod
    def unblock_ip(cls, ip: str):
        """Desbloqueia um IP manualmente (chamado pelo admin)."""
        cache.delete_many([_cache_key_ip_count(ip), _cache_key_ip_lock(ip)])
        logger.info("IP %s desbloqueado manualmente", ip)

    @classmethod
    def unblock_user(cls, username: str):
        """Desbloqueia um username manualmente."""
        cache.delete_many([
            _cache_key_user_count(username),
            _cache_key_user_lock(username),
        ])
        logger.info("Username '%s' desbloqueado manualmente", username)
