# apps/empresas/admin.py
from django.contrib import admin
from django.db import connection
from django.utils.text import slugify

from .models import Empresa, Categoria, Domain

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
                # 🚀 EXECUÇÃO BRUTA
                obj.delete() 
                self.message_user(request, f"✔ {obj._meta.verbose_name} eliminado com Rigor Sênior.")
            else:
                # 🛡️ BLOQUEIO ATIVO: Se não validou, manda para a view de Token
                self.message_user(request, "⚠️ Validação 2FA necessária para eliminar registos globais.", level='WARNING')
                
                # Guardamos a intenção na sessão para voltar depois (opcional)
                request.session['pending_action'] = f"delete_{obj.pk}"
                
                # Redireciona para a view que será criado
                return redirect(reverse('core:verify_ip')) 
        else:
            # Comportamento padrão dentro dos inquilinos (Tenants)
            super().delete_model(request, obj)
            
    #def delete_model(self, request, obj):
    #    """🛡️ RIGOR SOTARQ: Deleção via Model customizado (SQL Direto)"""
    #    obj.delete()

    def get_deleted_objects(self, objs, request):
        """🛡️ RIGOR SOTARQ: Evita travamento por tabelas inexistentes no public"""
        if connection.schema_name == 'public':
            return [], {}, set(), []
        return super().get_deleted_objects(objs, request)

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


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "ativa",
        "created_at",
    )

    list_filter = ("ativa", "created_at")
    search_fields = ("nome", "codigo")
    #list_select_related = ("empresa",)
    ordering = ("nome",)

    fieldsets = (
        ("Identificação", {
            "fields": ("nome", "codigo")
        }),
        ("Detalhes", {
            "fields": ("descricao",)
        }),
        ("Status", {
            "fields": ("ativa",)
        }),
    )

