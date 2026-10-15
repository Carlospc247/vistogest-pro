# apps/integracoes/services/providers.py
import hashlib
import hmac
import json
import re

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.utils import timezone

from .cliente import chamar

REGISTRO = {}


def registrar(*codigos):
    def deco(cls):
        for c in codigos:
            REGISTRO[c] = cls
        return cls
    return deco


def obter_provider(config):
    cls = REGISTRO.get(config.tipo_integracao.codigo)
    return cls(config) if cls else None


def assinar(segredo: str, corpo: bytes) -> str:
    return 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def _assinatura_valida(segredo: str, corpo: bytes, recebida: str) -> bool:
    return bool(segredo) and hmac.compare_digest(recebida or '', assinar(segredo, corpo))


def _erro_http(r) -> str:
    try:
        msg = r.json().get('error', {})
        msg = msg.get('message') if isinstance(msg, dict) else msg
    except ValueError:
        msg = None
    return f"HTTP {r.status_code}: {(msg or r.text)[:200]}"


class ProviderBase:
    suporta_mensagens = False

    def __init__(self, config):
        self.config = config
        self.cred = config.get_credenciais()
        self.cfg = config.configuracoes or {}

    def testar_conexao(self):
        raise NotImplementedError

    def enviar_mensagem(self, destino, texto, assunto=''):
        raise NotImplementedError

    # webhooks de entrada ------------------------------------------------------
    def verificar_webhook(self, request) -> bool:
        """Por defeito: HMAC-SHA256 do corpo com o segredo do webhook, em X-Webhook-Signature."""
        return _assinatura_valida(self.config.get_webhook_segredo(), request.body,
                                  request.headers.get('X-Webhook-Signature', ''))

    def responder_verificacao(self, request):
        return None

    def extrair_evento(self, payload) -> str:
        if isinstance(payload, dict):
            return str(payload.get('evento') or payload.get('event') or payload.get('type') or '')[:100]
        return ''

    def extrair_identificador(self, request, payload) -> str:
        return request.headers.get('X-Webhook-Id', '')[:255] or hashlib.sha256(request.body).hexdigest()

    def processar_webhook(self, webhook):
        """PONTO DE EXTENSÃO: aqui entra a lógica de negócio (ex.: confirmar pagamento, marcar mensagem lida).
        Levante uma excepção para marcar o webhook como falhado (pode reprocessar na UI)."""


@registrar('whatsapp_cloud')
class WhatsAppCloud(ProviderBase):
    suporta_mensagens = True

    def _base(self):
        return f"https://graph.facebook.com/{self.cfg.get('api_version') or 'v21.0'}"

    def _h(self):
        return {'Authorization': f"Bearer {self.cred['access_token']}"}

    def testar_conexao(self):
        r = chamar(self.config, 'GET', f"{self._base()}/{self.cred['phone_number_id']}", headers=self._h(),
                   params={'fields': 'display_phone_number,verified_name'}, exigir_ativa=False)
        if r.status_code == 200:
            d = r.json()
            return True, f"Ligado: {d.get('verified_name', '')} {d.get('display_phone_number', '')}".strip()
        return False, _erro_http(r)

    def enviar_mensagem(self, destino, texto, assunto=''):
        numero = re.sub(r'\D', '', destino)
        r = chamar(self.config, 'POST', f"{self._base()}/{self.cred['phone_number_id']}/messages",
                   headers=self._h(),
                   json_body={'messaging_product': 'whatsapp', 'to': numero, 'type': 'text',
                              'text': {'body': texto}},
                   contexto={'destino_final': numero[-4:]})
        return r.status_code in (200, 201), ('Mensagem enviada.' if r.status_code in (200, 201) else _erro_http(r))

    def verificar_webhook(self, request):
        return _assinatura_valida(self.cred.get('app_secret', ''), request.body,
                                  request.headers.get('X-Hub-Signature-256', ''))

    def responder_verificacao(self, request):
        esperado = self.cred.get('verify_token', '')
        recebido = request.GET.get('hub.verify_token', '')
        if esperado and request.GET.get('hub.mode') == 'subscribe' and hmac.compare_digest(recebido, esperado):
            return HttpResponse(request.GET.get('hub.challenge', ''), content_type='text/plain')
        return HttpResponse(status=403)

    def _valor(self, payload):
        try:
            return payload['entry'][0]['changes'][0]['value']
        except (KeyError, IndexError, TypeError):
            return {}

    def extrair_evento(self, payload):
        v = self._valor(payload)
        return 'messages' if v.get('messages') else 'statuses' if v.get('statuses') else ''

    def extrair_identificador(self, request, payload):
        v = self._valor(payload)
        try:
            return (v.get('messages') or v.get('statuses'))[0]['id'][:255]
        except (TypeError, IndexError, KeyError):
            return hashlib.sha256(request.body).hexdigest()


@registrar('twilio')
class Twilio(ProviderBase):
    suporta_mensagens = True

    def _auth(self):
        return self.cred['account_sid'], self.cred['auth_token']

    def _base(self):
        return f"https://api.twilio.com/2010-04-01/Accounts/{self.cred['account_sid']}"

    def testar_conexao(self):
        r = chamar(self.config, 'GET', self._base() + '.json', auth=self._auth(), exigir_ativa=False)
        return (True, 'Conta Twilio válida.') if r.status_code == 200 else (False, _erro_http(r))

    def enviar_mensagem(self, destino, texto, assunto=''):
        wa = self.cfg.get('canal') == 'whatsapp'
        para = ('whatsapp:' if wa else '') + '+' + re.sub(r'\D', '', destino)
        de = self.cred.get('remetente', '')
        if wa and not de.startswith('whatsapp:'):
            de = 'whatsapp:' + de
        r = chamar(self.config, 'POST', self._base() + '/Messages.json', auth=self._auth(),
                   data={'To': para, 'From': de, 'Body': texto})
        ok = r.status_code in (200, 201)
        return ok, ('Mensagem enviada.' if ok else _erro_http(r))

    def verificar_webhook(self, request):
        # A Twilio assina de outra forma (X-Twilio-Signature); aqui confia-se no token longo do URL.
        return True


@registrar('sendgrid')
class SendGrid(ProviderBase):
    suporta_mensagens = True

    def _h(self):
        return {'Authorization': f"Bearer {self.cred['api_key']}"}

    def testar_conexao(self):
        r = chamar(self.config, 'GET', 'https://api.sendgrid.com/v3/scopes', headers=self._h(), exigir_ativa=False)
        return (True, 'Chave SendGrid válida.') if r.status_code == 200 else (False, _erro_http(r))

    def enviar_mensagem(self, destino, texto, assunto=''):
        remetente = self.cfg.get('remetente')
        if not remetente:
            return False, 'Defina o remetente verificado nas configurações.'
        corpo = {'personalizations': [{'to': [{'email': destino}]}],
                 'from': {'email': remetente, 'name': self.cfg.get('nome_remetente') or remetente},
                 'subject': assunto or 'Mensagem de teste',
                 'content': [{'type': 'text/plain', 'value': texto}]}
        r = chamar(self.config, 'POST', 'https://api.sendgrid.com/v3/mail/send', headers=self._h(), json_body=corpo)
        return r.status_code == 202, ('E-mail aceite para envio.' if r.status_code == 202 else _erro_http(r))


@registrar('webhook_saida')
class WebhookSaida(ProviderBase):
    """Envia eventos do VistoGest para um URL vosso, assinados com HMAC-SHA256."""

    def emitir(self, evento, dados, forcar=False):
        permitidos = [e.strip() for e in (self.cfg.get('eventos') or '*').split(',') if e.strip()]
        if not forcar and '*' not in permitidos and evento not in permitidos:
            return False, 'Evento não subscrito.'
        corpo = json.dumps({'evento': evento, 'enviado_em': timezone.now().isoformat(), 'dados': dados},
                           ensure_ascii=False, cls=DjangoJSONEncoder).encode()
        headers = {'Content-Type': 'application/json', 'X-Webhook-Event': evento,
                   'X-Webhook-Signature': assinar(self.cred['segredo_hmac'], corpo)}
        r = chamar(self.config, 'POST', self.cred['url_destino'], headers=headers, data=corpo,
                   exigir_ativa=not forcar, contexto={'evento': evento})
        return r.status_code < 400, f"HTTP {r.status_code}"

    def testar_conexao(self):
        return self.emitir('ping', {'mensagem': 'teste de ligação'}, forcar=True)


@registrar('api_personalizada', 'gateway_pagamento')
class ApiPersonalizada(ProviderBase):
    """Cliente REST genérico: base_url + chave no cabeçalho configurado."""

    def _url(self, caminho):
        return self.cred['base_url'].rstrip('/') + '/' + caminho.lstrip('/')

    def _h(self):
        nome = self.cfg.get('cabecalho_auth') or 'Authorization'
        prefixo = self.cfg.get('prefixo_auth', 'Bearer ')
        return {nome: f"{prefixo}{self.cred.get('api_key', '')}"}

    def requisicao(self, metodo, caminho, json_body=None, params=None, usuario=None, exigir_ativa=True):
        return chamar(self.config, metodo, self._url(caminho), headers=self._h(), json_body=json_body,
                      params=params, usuario=usuario, exigir_ativa=exigir_ativa)

    def testar_conexao(self):
        r = self.requisicao('GET', self.cfg.get('endpoint_teste') or '/', exigir_ativa=False)
        return r.status_code < 400, f"HTTP {r.status_code}"
