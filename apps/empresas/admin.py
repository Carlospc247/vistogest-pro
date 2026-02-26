from django.contrib import admin
from django.db import connection
from django.utils.text import slugify

from .models import Empresa, Loja, Categoria, Domain


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
    list_filter = ('regime', 'ativa')

    list_filter = ("ativa", "regime", "provincia", "data_cadastro")
    search_fields = ("nome", "nome_fantasia", "nif", "schema_name")
    readonly_fields = ("data_cadastro",)
    inlines = [DomainInline]

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
                # 🚀 EXECUÇÃO BRUTA (O comando que o senhor guardou)
                obj.delete() 
                self.message_user(request, f"✔ {obj._meta.verbose_name} eliminado com Rigor Sênior.")
            else:
                # 🛡️ BLOQUEIO ATIVO: Se não validou, manda para a view de Token
                self.message_user(request, "⚠️ Validação 2FA necessária para eliminar registos globais.", level='WARNING')
                
                # Guardamos a intenção na sessão para voltar depois (opcional)
                request.session['pending_action'] = f"delete_{obj.pk}"
                
                # Redireciona para a view que o senhor já criou anteriormente
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
# LOJA ADMIN
# =========================

@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "empresa",
        "codigo",
        "cidade",
        "ativa",
        "eh_matriz",
    )

    list_filter = ("ativa", "eh_matriz", "provincia", "empresa")
    search_fields = ("nome", "codigo", "empresa__nome")
    list_select_related = ("empresa",)

    fieldsets = (
        ("Identificação", {
            "fields": ("empresa", "nome", "codigo", "eh_matriz")
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
            "fields": ("telefone", "email", "foto")
        }),
        ("Status", {
            "fields": ("ativa",)
        }),
    )

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
                # 🚀 EXECUÇÃO BRUTA (O comando que o senhor guardou)
                obj.delete() 
                self.message_user(request, f"✔ {obj._meta.verbose_name} eliminado com Rigor Sênior.")
            else:
                # 🛡️ BLOQUEIO ATIVO: Se não validou, manda para a view de Token
                self.message_user(request, "⚠️ Validação 2FA necessária para eliminar registos globais.", level='WARNING')
                
                # Guardamos a intenção na sessão para voltar depois (opcional)
                request.session['pending_action'] = f"delete_{obj.pk}"
                
                # Redireciona para a view que o senhor já criou anteriormente
                return redirect(reverse('core:verify_ip')) 
        else:
            # Comportamento padrão dentro dos inquilinos (Tenants)
            super().delete_model(request, obj)

    #def delete_model(self, request, obj):
    #    obj.delete()

    def get_deleted_objects(self, objs, request):
        if connection.schema_name == 'public':
            return [], {}, set(), []
        return super().get_deleted_objects(objs, request)


# =========================
# CATEGORIA ADMIN
# =========================

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "empresa",
        "ativa",
        "created_at",
    )

    list_filter = ("ativa", "empresa")
    search_fields = ("nome", "codigo", "empresa__nome")
    list_select_related = ("empresa",)
    ordering = ("nome",)

    fieldsets = (
        ("Identificação", {
            "fields": ("empresa", "nome", "codigo")
        }),
        ("Detalhes", {
            "fields": ("descricao",)
        }),
        ("Status", {
            "fields": ("ativa",)
        }),
    )


# =========================
# DOMAIN ADMIN (opcional)
# =========================

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__nome")
    list_select_related = ("tenant",)