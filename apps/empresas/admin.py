# apps/empresas/admin.py
from django.contrib import admin
from django.db import connection
from django.utils.text import slugify

from .models import Empresa, Domain

from django.utils.html import format_html


# =========================
# DOMAIN INLINE
# =========================

class DomainInline(admin.TabularInline):
    model = Domain
    extra = 1
    fields = ("domain", "is_primary")
    verbose_name = "Domínio"
    verbose_name_plural = "Domínios"


# =========================
# EMPRESA ADMIN
# =========================

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "nif",
        "regime",
        "schema_name",
        "ativa",
        "data_cadastro",
    )

    list_filter = ("ativa", "regime", "provincia", "data_cadastro")
    search_fields = ("nome", "nome_fantasia", "nif", "schema_name")
    readonly_fields = ("data_cadastro",)
    #inlines = [DomainInline]

    fieldsets = (
        ("Identificação Técnica (Multi-Tenant)", {
            "fields": ("schema_name",)
        }),
        ("Dados da Empresa", {
            "fields": (
                "nome",
                "nome_fantasia",
                "nif",
                "regime",
                "codigo_validacao",
                "foto",
            )
        }),
        ("Endereço", {
            "fields": (
                "endereco",
                "numero",
                "bairro",
                "cidade",
                "provincia",
                "postal",
            )
        }),
        ("Contato", {
            "fields": ("telefone", "email")
        }),
        ("Status", {
            "fields": ("ativa", "data_cadastro")
        }),
    )

    def save_model(self, request, obj, form, change):
        # Gera schema automaticamente se não for informado
        if not obj.schema_name:
            from django.utils.text import slugify
            obj.schema_name = slugify(obj.nome).replace("-", "_")
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        """
        🛡️ RIGOR SOTARQ: Interceptação de Segurança com Redirecionamento.
        Cobre a eliminação de UM único objeto (via página de detalhe).
        """
        from apps.core.models import IPConhecido
        from django.shortcuts import redirect
        from django.urls import reverse

        # 1. Pega o IP real (considerando proxies como o Render)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_atual = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

        # 2. Verifica se o vínculo IP+User já foi autenticado via 2FA
        foi_validado = IPConhecido.objects.filter(usuario=request.user, ip_address=ip_atual).exists()

        if connection.schema_name == 'public':
            if foi_validado:
                if obj.schema_name == 'public':
                    self.message_user(request, "❌ Não é permitido apagar o schema 'public'.", level='ERROR')
                    return
                # 🚀 EXECUÇÃO SEGURA: apaga o schema físico e a linha, sem o Collector
                # padrão do Django (que tentaria ler tabelas de TENANT_APPS inexistentes
                # no schema 'public' — ver nota em delete_queryset() abaixo).
                obj._drop_schema(force_drop=True)
                Empresa.objects.filter(pk=obj.pk)._raw_delete(Empresa.objects.db)
                self.message_user(request, f"✔ {obj._meta.verbose_name} eliminado com Rigor Sênior.")
            else:
                # 🛡️ BLOQUEIO ATIVO: Se não validou, manda para a view de Token
                self.message_user(request, "⚠️ Validação 2FA necessária para eliminar registos globais.", level='WARNING')
                request.session['pending_action'] = f"delete_{obj.pk}"
                return redirect(reverse('core:verify_ip'))
        else:
            # Comportamento padrão dentro dos inquilinos (Tenants)
            super().delete_model(request, obj)

    def get_deleted_objects(self, objs, request):
        """
        🛡️ RIGOR SOTARQ: Evita travamento por tabelas inexistentes no public.
        Protege a PÁGINA DE CONFIRMAÇÃO da ação "Delete selected".
        """
        if connection.schema_name == 'public':
            return [], {}, set(), []
        return super().get_deleted_objects(objs, request)

    def delete_queryset(self, request, queryset):
        """
        🛡️ RIGOR SOTARQ: A ação "Delete selected" do Django, depois de o
        utilizador confirmar na página protegida por get_deleted_objects(),
        chama diretamente delete_queryset() -> queryset.delete(). Isso NÃO
        passa pelo get_deleted_objects() acima e aciona o Collector padrão
        do Django, que percorre TODAS as relações reversas de Empresa em
        TODAS as apps instaladas — incluindo models de TENANT_APPS como
        vendas.FormaPagamento, vendas.Convenio, funcionarios.Cargo, etc.
        Essas tabelas não existem no schema 'public', causando
        ProgrammingError: relation "..." does not exist.

        Aqui replicamos a mesma lógica segura usada no reset do
        gerenciar_sotarq.py: apagamos o schema físico de cada tenant e
        removemos a linha via SQL direto (_raw_delete), sem o Collector.
        """
        if connection.schema_name == 'public':
            for empresa in queryset:
                if empresa.schema_name == 'public':
                    continue  # nunca apaga o próprio public
                empresa._drop_schema(force_drop=True)
                Empresa.objects.filter(pk=empresa.pk)._raw_delete(Empresa.objects.db)
        else:
            super().delete_queryset(request, queryset)


# =========================
# CATEGORIA ADMIN
# =========================


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    """
    Configuração do Admin para gestão individual de Domínios.
    """
    list_display = [
        'domain',
        'tenant',
        'is_primary',
        'acessar_dominio',
    ]

    list_filter = [
        'is_primary',
    ]

    search_fields = [
        'domain',
        'tenant__nome',
        'tenant__schema_name',
    ]

    list_editable = [
        'is_primary',
    ]

    autocomplete_fields = ['tenant']
    ordering = ['domain']
    list_per_page = 25

    fieldsets = (
        ('Configuração do Domínio', {
            'fields': ('domain', 'is_primary')
        }),
        ('Tenant Vinculado', {
            'fields': ('tenant',)
        }),
    )

    @admin.display(description="Acesso Rápido")
    def acessar_dominio(self, obj):
        if not obj.domain:
            return "-"
        protocolo = "http" if ("localhost" in obj.domain or "127.0.0.1" in obj.domain) else "https"
        url = f"{protocolo}://{obj.domain}"
        return format_html(
            '<a href="{url}" target="_blank" style="font-weight: bold; color: #28a745;">Abrir site ↗</a>',
            url=url
        )

