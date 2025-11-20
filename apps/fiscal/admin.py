# apps/fiscal/admin.py
# apps/fiscal/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.core.exceptions import ValidationError

from .models import AssinaturaDigital
from apps.fiscal.services import AssinaturaDigitalService


# FORM COM VALIDAÇÃO DE DUPLICAÇÃO
class AssinaturaDigitalForm(forms.ModelForm):
    class Meta:
        model = AssinaturaDigital
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        empresa = cleaned_data.get('empresa')

        # Bloqueia se já existir outra assinatura para esta empresa
        if empresa and AssinaturaDigital.objects.filter(empresa=empresa).exists() and not self.instance.pk:
            raise ValidationError("⚠️ Já existe uma assinatura para esta empresa. Não é permitido duplicar.")

        return cleaned_data

    def clean_dados_series_fiscais(self):
        return self.cleaned_data.get('dados_series_fiscais') or {}


@admin.register(AssinaturaDigital)
class AssinaturaDigitalAdmin(admin.ModelAdmin):
    form = AssinaturaDigitalForm
    list_display = ['empresa', 'data_geracao', 'acoes', 'acoes_download']
    readonly_fields = ['chave_publica', 'data_geracao', 'ultimo_hash']

    # Salva e delega geração de chaves ao serviço
    def save_model(self, request, obj, form, change):
        if not obj.pk:
            assinatura = AssinaturaDigitalService.gerar_chaves_rsa(obj.empresa)
            obj.chave_publica = assinatura.chave_publica
            obj.chave_privada = assinatura.chave_privada
            obj.data_geracao = assinatura.data_geracao
            obj.ultimo_hash = assinatura.ultimo_hash
            obj.dados_series_fiscais = assinatura.dados_series_fiscais

        super().save_model(request, obj, form, change)

    # Botões de ações no admin
    def acoes(self, obj):
        url = reverse('fiscal:baixar_chave_publica', args=[obj.empresa.id])
        return format_html('<a class="button" href="{}">Baixar Chave Pública</a>', url)
    acoes.short_description = "Ações"

    def acoes_download(self, obj):
        botoes = [
            f'<a class="button" href="{reverse("fiscal:baixar_chave_publica", args=[obj.empresa.id])}">🔑 Chave Pública</a>',
            f'<a class="button" href="{reverse("fiscal:baixar_pdf_submissao", args=[obj.empresa.id])}">📄 PDF AGT</a>',
            f'<a class="button" href="{reverse("fiscal:download_pdf_agt", args=[obj.empresa.id])}">⚙️ Fluxo ATCUD</a>',
        ]
        return format_html(" &nbsp; ".join(botoes))
    acoes_download.short_description = "Downloads & Fluxo Fiscal"
