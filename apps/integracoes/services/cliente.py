# apps/integracoes/services/cliente.py
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone

from ..models import LogIntegracao

logger = logging.getLogger('integracoes')

LIMITE_TEXTO = 10_000
SENSIVEIS = ('authorization', 'token', 'secret', 'password', 'senha', 'api_key', 'apikey', 'x-api-key', 'auth')


class ErroIntegracao(Exception):
    pass


class LimiteExcedido(ErroIntegracao):
    pass


class UrlNaoPermitida(ErroIntegracao):
    pass


def validar_url_externa(url: str):
    """Só https e só destinos públicos (anti-SSRF). Em DEBUG permite http/endereços locais.
    Nota: não elimina DNS rebinding; para isso use um proxy de saída."""
    p = urlparse(url)
    if not p.hostname or (p.scheme != 'https' and not (settings.DEBUG and p.scheme == 'http')):
        raise UrlNaoPermitida("Apenas URLs https são permitidas.")
    if settings.DEBUG:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443)
    except socket.gaierror:
        raise UrlNaoPermitida("Não foi possível resolver o endereço.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UrlNaoPermitida("Endereços internos não são permitidos.")


def _mascarar(obj):
    if isinstance(obj, dict):
        return {k: ('***' if any(s in str(k).lower() for s in SENSIVEIS) else _mascarar(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mascarar(i) for i in obj]
    return obj


def _texto_log(json_body, data) -> str:
    try:
        if json_body is not None:
            return json.dumps(_mascarar(json_body), ensure_ascii=False)[:LIMITE_TEXTO]
        if isinstance(data, (bytes, bytearray)):
            return json.dumps(_mascarar(json.loads(data)), ensure_ascii=False)[:LIMITE_TEXTO]
        if isinstance(data, dict):
            return json.dumps(_mascarar(data), ensure_ascii=False)[:LIMITE_TEXTO]
    except (ValueError, TypeError):
        return '[corpo não registado]'
    return ''


def _registar(config, status, metodo, url, headers, payload, status_code, resposta, duracao, tentativas,
              usuario, contexto):
    LogIntegracao.objects.create(
        configuracao=config, direcao='saida', status=status, metodo=metodo, url=url[:2000],
        headers=_mascarar(dict(headers or {})), payload=payload, status_code=status_code,
        response_data=(resposta or '')[:LIMITE_TEXTO], tempo_resposta=duracao, tentativas=tentativas,
        usuario=usuario if getattr(usuario, 'pk', None) else None, contexto=contexto or {})


def _marcar_erro(config, msg):
    config.erro_ultima_sincronizacao = msg[:500]
    config.save(update_fields=['erro_ultima_sincronizacao'])


def chamar(config, metodo, url, *, headers=None, json_body=None, data=None, params=None, auth=None,
           usuario=None, contexto=None, exigir_ativa=True):
    """Chamada HTTP de saída com quota, retries (timeout/5xx), log mascarado e anti-SSRF.
    Devolve a Response (mesmo com 4xx/5xx — quem chama decide). Levanta ErroIntegracao em falhas de rede."""
    if exigir_ativa and not config.ativa:
        raise ErroIntegracao("A integração está desactivada.")
    validar_url_externa(url)
    payload = _texto_log(json_body, data)

    if not config.consumir_quota():
        _registar(config, 'limite_excedido', metodo, url, headers, payload, None, '', None, 0, usuario, contexto)
        raise LimiteExcedido("Limite diário de pedidos excedido.")

    tentativas = max(1, config.tentativas_max)
    inicio = time.monotonic()
    resp, erro, status_erro, n = None, None, 'erro', 0
    for n in range(1, tentativas + 1):
        try:
            resp = requests.request(metodo, url, headers=headers, json=json_body, data=data, params=params,
                                    auth=auth, timeout=config.timeout_segundos, allow_redirects=False)
            if resp.status_code >= 500 and n < tentativas:
                time.sleep(0.5 * 2 ** (n - 1))
                continue
            break
        except requests.Timeout as exc:
            resp, erro, status_erro = None, exc, 'timeout'
        except requests.RequestException as exc:
            resp, erro, status_erro = None, exc, 'erro'
        if n < tentativas:
            time.sleep(0.5 * 2 ** (n - 1))
    duracao = time.monotonic() - inicio

    if resp is None:
        _registar(config, status_erro, metodo, url, headers, payload, None, str(erro), duracao, n, usuario, contexto)
        _marcar_erro(config, f"{status_erro}: {erro}")
        raise ErroIntegracao(f"Falha de ligação ({status_erro}).")

    ok = resp.status_code < 400
    _registar(config, 'sucesso' if ok else 'erro', metodo, url, headers, payload, resp.status_code,
              resp.text, duracao, n, usuario, contexto)
    if ok:
        config.ultima_sincronizacao = timezone.now()
        config.erro_ultima_sincronizacao = ''
        config.save(update_fields=['ultima_sincronizacao', 'erro_ultima_sincronizacao'])
    else:
        _marcar_erro(config, f"HTTP {resp.status_code}")
    return resp