# apps/fiscal/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.http import HttpResponseRedirect
from django.contrib import messages
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from .models import AssinaturaDigital


# FORM SIMPLIFICADO
class AssinaturaDigitalForm(forms.ModelForm):
    class Meta:
        model = AssinaturaDigital
        # No django_tenants, o registro reside no schema do Tenant.
        # Não existe o campo 'empresa'.
        fields = []

    def clean(self):
        cleaned_data = super().clean()

        # Garante a regra de 1 Assinatura Digital por Tenant/Schema
        if AssinaturaDigital.objects.exists() and not self.instance.pk:
            raise ValidationError("⚠️ Já existe uma assinatura digital configurada para este Tenant.")

        return cleaned_data


@admin.register(AssinaturaDigital)
class AssinaturaDigitalAdmin(admin.ModelAdmin):
    form = AssinaturaDigitalForm
    
    # Lista de visibilidade (Removida referência a 'empresa')
    list_display = ['status_chave', 'data_geracao', 'acoes_download', 'acoes_rapidas']
    
    # Campos no formulário de edição
    fields = ['gerar_chaves_btn', 'acoes_download', 'ver_chave_publica', 'data_geracao']
    readonly_fields = ['gerar_chaves_btn', 'acoes_download', 'ver_chave_publica', 'data_geracao']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:pk>/gerar-chaves/',
                self.admin_site.admin_view(self.gerar_chaves_view),
                name='fiscal_assinaturadigital_gerar_chaves',
            ),
        ]
        return custom_urls + urls

    def gerar_chaves_view(self, request, pk):
        """
        View exclusiva para gerar par de chaves RSA (Privada/Pública).
        """
        obj = self.get_object(request, pk)
        if not obj:
            messages.error(request, "Assinatura não encontrada.")
            return HttpResponseRedirect(reverse('admin:fiscal_assinaturadigital_changelist'))

        try:
            # 1. Gerar Chave Privada RSA 2048 bits
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # 2. Serializar Chave Privada (PEM)
            pem_private = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )

            # 3. Serializar Chave Pública (PEM)
            pem_public = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )

            # 4. Atualizar Objeto
            obj.chave_privada = pem_private.decode('utf-8')
            obj.chave_publica = pem_public.decode('utf-8')
            obj.data_geracao = timezone.now()
            
            obj.save()

            messages.success(request, "✅ Chaves RSA geradas com sucesso para o Tenant!")
            
        except Exception as e:
            messages.error(request, f"Erro ao gerar chaves: {str(e)}")

        return HttpResponseRedirect(reverse('admin:fiscal_assinaturadigital_change', args=[pk]))

    def acoes_download(self, obj):
        if not obj.chave_publica:
            return "-"
            
        # As URLs no contexto do tenant não necessitam receber o id da empresa
        url_base = reverse("fiscal:baixar_chave_publica")
        
        botoes = [
            '<div style="margin-bottom: 5px;"><strong>Chave Pública:</strong></div>',
            f'<a class="button" href="{url_base}?formato=pem" title="Formato PEM (Padrão)">PEM</a>',
            f'<a class="button" href="{url_base}?formato=txt" title="Formato Texto">TXT</a>',
            f'<a class="button" href="{url_base}?formato=pdf" title="Documento PDF">PDF</a>',
            '<br><div style="margin-top: 8px; margin-bottom: 5px;"><strong>Documentos Fiscais:</strong></div>',
            f'<a class="button" href="{reverse("fiscal:baixar_pdf_submissao")}">📄 PDF AGT</a>',
            f'<a class="button" href="{reverse("fiscal:download_pdf_agt")}">⚙️ Fluxo ATCUD</a>',
        ]
        return format_html(" ".join(botoes))
    acoes_download.short_description = "Downloads & Fluxo Fiscal"

    def gerar_chaves_btn(self, obj):
        if not obj.pk:
            return "Grave a configuração primeiro para gerar as chaves."
        
        url = reverse('admin:fiscal_assinaturadigital_gerar_chaves', args=[obj.pk])
        return format_html(
            '''
            <a class="button" href="{}" style="background-color: #28a745; color: white; padding: 10px 20px; border-radius: 5px; font-weight: bold; text-decoration: none;">
                🔑 CRIAR CHAVE PÚBLICA (Gerar Par RSA)
            </a>
            <p style="margin-top:10px; color:#666;">
                <i>Ao clicar, uma nova chave privada e pública serão geradas e salvas automaticamente.</i>
            </p>
            ''',
            url
        )
    gerar_chaves_btn.short_description = "Ação Necessária"

    def ver_chave_publica(self, obj):
        if not obj.chave_publica:
            return "-"
        return format_html(
            '<textarea readonly style="width: 100%; height: 150px; font-family: monospace;">{}</textarea>',
            obj.chave_publica
        )
    ver_chave_publica.short_description = "Chave Pública (PEM)"

    def status_chave(self, obj):
        if obj.chave_publica and obj.chave_privada:
            return format_html('<span style="color: green;">✅ Ativa</span>')
        return format_html('<span style="color: red;">❌ Pendente</span>')
    status_chave.short_description = "Status"

    def acoes_rapidas(self, obj):
        # Atalho para o botão na listagem
        return self.gerar_chaves_btn(obj)
    acoes_rapidas.short_description = "Gerar Chaves"