# apps/fiscal/admin.py
"""Admin da assinatura fiscal com suporte ao schema public e aos tenants.

A aplicação fiscal é tenant-local. Por isso o admin global não consulta a tabela
fiscal_assinaturadigital em public; selecciona primeiro uma Empresa e só depois
entra no respectivo schema através de schema_context.
"""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.db import connection
from django_tenants.utils import schema_context

from apps.empresas.models import Empresa
from .models import AssinaturaDigital


class AssinaturaTenantForm(forms.Form):
    nif_contribuinte = forms.CharField(
        label="NIF do contribuinte", max_length=20,
        widget=forms.TextInput(attrs={"class": "vTextField", "autocomplete": "off"}),
    )
    chave_privada = forms.CharField(
        label="Chave privada emitida pela AGT (PEM)",
        widget=forms.Textarea(attrs={"rows": 8, "class": "vLargeTextField", "autocomplete": "off"}),
        help_text="A chave é cifrada antes de ser guardada. Nunca será devolvida pela interface.",
    )
    chave_publica = forms.CharField(
        label="Chave pública emitida pela AGT (PEM)",
        widget=forms.Textarea(attrs={"rows": 8, "class": "vLargeTextField", "autocomplete": "off"}),
    )

    def clean_nif_contribuinte(self):
        value = self.cleaned_data["nif_contribuinte"].strip()
        if not value:
            raise forms.ValidationError("O NIF é obrigatório.")
        return value

    def clean_chave_privada(self):
        value = self.cleaned_data["chave_privada"].strip()
        if "PRIVATE KEY" not in value:
            raise forms.ValidationError("A chave privada deve estar no formato PEM.")
        return value

    def clean_chave_publica(self):
        value = self.cleaned_data["chave_publica"].strip()
        if "PUBLIC KEY" not in value and "CERTIFICATE" not in value:
            raise forms.ValidationError("A chave pública/certificado deve estar no formato PEM.")
        return value


@admin.register(AssinaturaDigital)
class AssinaturaDigitalAdmin(admin.ModelAdmin):
    list_display = ("nif_contribuinte", "status_chave", "data_configuracao_chave", "configurada_por")
    fields = ("nif_contribuinte", "estado_configuracao", "data_configuracao_chave", "configurada_por")
    readonly_fields = fields
    ordering = ("nif_contribuinte",)

    def get_urls(self):
        custom = [
            path(
                "gestao-tenants/",
                self.admin_site.admin_view(self.gestao_tenants_view),
                name="fiscal_assinaturadigital_global",
            ),
            path(
                "gestao-tenants/<int:empresa_id>/configurar/",
                self.admin_site.admin_view(self.configurar_tenant_view),
                name="fiscal_assinaturadigital_configurar_tenant",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        # A tabela fiscal_assinaturadigital não existe em public: o admin global
        # deve listar tenants, nunca executar o ChangeList sobre a tabela tenant-local.
        if getattr(connection, "schema_name", "public") == "public":
            return self.gestao_tenants_view(request)
        return super().changelist_view(request, extra_context=extra_context)

    def has_add_permission(self, request):
        # A linha singleton é criada automaticamente pelo get_solo() no schema alvo.
        return False

    def has_change_permission(self, request, obj=None):
        # A configuração global passa pela view que activa o schema do tenant.
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def status_chave(self, obj):
        return "Configurada" if getattr(obj, "esta_configurada", False) else "Pendente"
    status_chave.short_description = "Estado da assinatura"

    def estado_configuracao(self, obj):
        return self.status_chave(obj)
    estado_configuracao.short_description = "Estado"

    def gestao_tenants_view(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied("Só o superuser pode configurar chaves fiscais de tenants.")
        if getattr(connection, "schema_name", "public") != "public":
            raise PermissionDenied("A gestão global das chaves deve ser aberta no admin do schema public.")

        empresas = Empresa.objects.all().order_by("nome")
        context = {
            **self.admin_site.each_context(request),
            "title": "Configuração fiscal por tenant",
            "opts": self.model._meta,
            "empresas": empresas,
            "configurar_url_name": "admin:fiscal_assinaturadigital_configurar_tenant",
        }
        return TemplateResponse(
            request,
            "admin/fiscal/assinaturadigital/global_changelist.html",
            context,
        )

    def configurar_tenant_view(self, request, empresa_id):
        if not request.user.is_superuser:
            raise PermissionDenied("Só o superuser pode configurar chaves fiscais de tenants.")
        if getattr(connection, "schema_name", "public") != "public":
            raise PermissionDenied("Abra esta página a partir do admin global em public.")

        empresa = get_object_or_404(Empresa, pk=empresa_id)
        if not getattr(empresa, "schema_name", None) or empresa.schema_name == "public":
            messages.error(request, "A empresa seleccionada não possui um schema de tenant válido.")
            return redirect("admin:fiscal_assinaturadigital_global")

        if request.method == "POST":
            form = AssinaturaTenantForm(request.POST)
            if form.is_valid():
                try:
                    with schema_context(empresa.schema_name):
                        configuracao = AssinaturaDigital.get_solo()
                        configuracao.definir_chaves(
                            nif=form.cleaned_data["nif_contribuinte"],
                            chave_privada_pem=form.cleaned_data["chave_privada"],
                            chave_publica_pem=form.cleaned_data["chave_publica"],
                            usuario=request.user,
                        )
                        estado = configuracao.esta_configurada
                        data_configuracao = configuracao.data_configuracao_chave
                    if not estado:
                        messages.warning(request, f"A configuração de {empresa.nome} foi guardada, mas não ficou completa.")
                    else:
                        messages.success(request, f"Chaves fiscais guardadas com sucesso para {empresa.nome}.")
                    return redirect("admin:fiscal_assinaturadigital_global")
                except Exception as exc:
                    messages.error(request, f"Não foi possível configurar o tenant {empresa.nome}: {exc}")
        else:
            form = AssinaturaTenantForm()
            data_configuracao = None
            try:
                with schema_context(empresa.schema_name):
                    configuracao = AssinaturaDigital.objects.filter(pk=1).first()
                    if configuracao:
                        form = AssinaturaTenantForm(initial={"nif_contribuinte": configuracao.nif_contribuinte})
                        data_configuracao = configuracao.data_configuracao_chave
            except Exception as exc:
                messages.warning(request, f"Ainda não foi possível ler a configuração fiscal deste tenant: {exc}")

        context = {
            **self.admin_site.each_context(request),
            "title": f"Configurar assinatura fiscal — {empresa.nome}",
            "opts": self.model._meta,
            "empresa": empresa,
            "form": form,
            "data_configuracao": data_configuracao,
            "voltar_url": reverse("admin:fiscal_assinaturadigital_global"),
        }
        return TemplateResponse(
            request,
            "admin/fiscal/assinaturadigital/tenant_config.html",
            context,
        )


# Preserva o registo dos catálogos fiscais adicionais já definidos na aplicação.
from . import admin_referencia  # noqa: F401,E402
