# apps/integracoes/forms.py
from urllib.parse import urlparse

from django import forms
from django.conf import settings

from .models import ConfiguracaoIntegracao

CAMPOS_URL = ('base_url', 'url_destino')


class ConfiguracaoForm(forms.Form):
    """Formulário dinâmico: os campos vêm de TipoIntegracao.esquema_credenciais / esquema_configuracoes."""
    ambiente = forms.ChoiceField(choices=ConfiguracaoIntegracao.AMBIENTE_CHOICES, label='Ambiente')
    limite_requests_dia = forms.IntegerField(min_value=1, max_value=1_000_000, initial=1000, label='Limite de pedidos por dia')
    timeout_segundos = forms.IntegerField(min_value=1, max_value=120, initial=15, label='Timeout (segundos)')
    tentativas_max = forms.IntegerField(min_value=1, max_value=5, initial=2, label='Tentativas máximas')

    def __init__(self, *args, tipo, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo, self.config, self._cred_atual = tipo, config, {}
        if config:
            for nome in ('ambiente', 'limite_requests_dia', 'timeout_segundos', 'tentativas_max'):
                self.fields[nome].initial = getattr(config, nome)
            try:
                self._cred_atual = config.get_credenciais()
            except Exception:
                self._cred_atual = {}

        for c in tipo.esquema_credenciais:
            segredo = c.get('segredo')
            ajuda = c.get('ajuda', '')
            if segredo and self._cred_atual.get(c['chave']):
                ajuda = (ajuda + ' ' if ajuda else '') + 'Deixe em branco para manter o valor actual.'
            self.fields['cred_' + c['chave']] = forms.CharField(
                label=c.get('label', c['chave']), required=False, help_text=ajuda,
                widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}) if segredo
                else forms.TextInput(),
                initial=None if segredo else self._cred_atual.get(c['chave'], ''))

        atuais = (config.configuracoes if config else {}) or {}
        for c in tipo.esquema_configuracoes:
            inicial = atuais.get(c['chave'], c.get('padrao'))
            t = c.get('tipo', 'text')
            if t == 'bool':
                campo = forms.BooleanField(required=False, initial=bool(inicial))
            elif t == 'number':
                campo = forms.IntegerField(required=False, initial=inicial)
            elif t == 'choice':
                campo = forms.ChoiceField(choices=[(o, o) for o in c.get('opcoes', [])], initial=inicial)
            else:
                campo = forms.CharField(required=False, initial=inicial)
            campo.label = c.get('label', c['chave'])
            self.fields['cfg_' + c['chave']] = campo

    def clean(self):
        dados = super().clean()
        cred = {}
        for c in self.tipo.esquema_credenciais:
            chave, nome = c['chave'], 'cred_' + c['chave']
            valor = (dados.get(nome) or '').strip()
            if not valor and c.get('segredo'):
                valor = self._cred_atual.get(chave, '')
            if not valor and c.get('obrigatorio', True):
                self.add_error(nome, 'Campo obrigatório.')
            if valor and chave in CAMPOS_URL:
                p = urlparse(valor)
                if not p.hostname or (p.scheme != 'https' and not (settings.DEBUG and p.scheme == 'http')):
                    self.add_error(nome, 'Indique um URL https válido.')
            cred[chave] = valor
        self._cred_nova = cred
        return dados

    def salvar(self, usuario):
        d = self.cleaned_data
        config = self.config or ConfiguracaoIntegracao(tipo_integracao=self.tipo, criada_por=usuario)
        config.ambiente = d['ambiente']
        config.limite_requests_dia = d['limite_requests_dia']
        config.timeout_segundos = d['timeout_segundos']
        config.tentativas_max = d['tentativas_max']
        config.configuracoes = {c['chave']: d.get('cfg_' + c['chave']) for c in self.tipo.esquema_configuracoes}
        if self._cred_nova != self._cred_atual:
            config.ultimo_teste_ok = config.ultimo_teste_em = None
        config.set_credenciais(self._cred_nova)
        config.save()
        return config


class EnvioTesteForm(forms.Form):
    destino = forms.CharField(max_length=254, label='Destino (telefone ou e-mail)')
    texto = forms.CharField(max_length=500, widget=forms.Textarea(attrs={'rows': 2}), initial='Mensagem de teste do VistoGest.')
    assunto = forms.CharField(max_length=150, required=False, label='Assunto (só e-mail)')
