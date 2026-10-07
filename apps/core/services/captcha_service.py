# apps/core/services/captcha_service.py
"""
Verificação hCaptcha server-side.

hCaptcha é um substituto ético do reCAPTCHA:
  - Funciona sem Google, compatível com GDPR/LGPD.
  - Chaves de teste oficiais disponíveis para desenvolvimento:
      site_key:   10000000-ffff-ffff-ffff-000000000001
      secret_key: 0x0000000000000000000000000000000000000000
  - Em produção, criar conta em hcaptcha.com e definir as chaves no .env.

Uso:
    ok, err = CaptchaService.verificar(request)
    if not ok:
        form.add_error(None, err)
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger('core.security')

VERIFY_URL   = getattr(settings, 'HCAPTCHA_VERIFY_URL',   'https://hcaptcha.com/siteverify')
SECRET_KEY   = getattr(settings, 'HCAPTCHA_SECRET_KEY',   '0x0000000000000000000000000000000000000000')
SITE_KEY     = getattr(settings, 'HCAPTCHA_SITE_KEY',     '10000000-ffff-ffff-ffff-000000000001')
TIMEOUT_SECS = 5


class CaptchaService:

    @staticmethod
    def verificar(request) -> tuple[bool, str]:
        """
        Verifica o token hCaptcha enviado no POST.

        Retorna (True, '') se válido, (False, mensagem_de_erro) se inválido.
        Falha silenciosa em caso de timeout/erro de rede — permite login
        para não bloquear utilizadores legítimos quando o serviço externo
        estiver indisponível (fail-open intencional para UX; o rate limit
        continua a proteger contra brute-force mesmo sem CAPTCHA).
        """
        token = request.POST.get('h-captcha-response', '').strip()

        if not token:
            return False, "Por favor complete o desafio de segurança (CAPTCHA)."

        # Chaves de teste oficiais hCaptcha — sempre válidas em dev
        if SECRET_KEY == '0x0000000000000000000000000000000000000000':
            # Em modo de teste, qualquer token não vazio é aceite
            logger.debug("hCaptcha: modo de teste — token aceite automaticamente")
            return True, ''

        try:
            resp = requests.post(
                VERIFY_URL,
                data={
                    'secret':   SECRET_KEY,
                    'response': token,
                    'remoteip': _get_ip(request),
                },
                timeout=TIMEOUT_SECS,
            )
            data = resp.json()
            if data.get('success'):
                return True, ''

            # Mapear códigos de erro hCaptcha para mensagens legíveis
            erros = data.get('error-codes', [])
            if 'expired-or-duplicated-secret-key' in erros:
                logger.error("hCaptcha: chave secreta expirada ou duplicada")
                return True, ''  # fail-open: não punir o utilizador por erro de config

            logger.warning("hCaptcha falhou: %s", erros)
            return False, "Desafio de segurança inválido. Tente novamente."

        except requests.Timeout:
            logger.warning("hCaptcha: timeout na verificação — fail-open")
            return True, ''   # fail-open em timeout de rede
        except Exception as exc:
            logger.error("hCaptcha: erro inesperado — %s", exc)
            return True, ''   # fail-open em erros inesperados


def _get_ip(request) -> str:
    x_fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return x_fwd.split(',')[0].strip() if x_fwd else request.META.get('REMOTE_ADDR', '')
