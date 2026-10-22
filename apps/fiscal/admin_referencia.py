"""Admin dos catálogos fiscais tenant-local; ocultos no admin global public."""
from django.contrib import admin
from django.db import connection
from .models_referencia import CAE, ImpostoSelo, ImpostoEspecialConsumo


class TenantSchemaAdminMixin:
    def has_module_permission(self, request):
        return getattr(connection, "schema_name", "public") != "public" and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return getattr(connection, "schema_name", "public") != "public" and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return getattr(connection, "schema_name", "public") != "public" and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return getattr(connection, "schema_name", "public") != "public" and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return getattr(connection, "schema_name", "public") != "public" and super().has_delete_permission(request, obj)


class CAEAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("codigo", "descricao", "ativo")
    list_filter = ("ativo",)
    search_fields = ("codigo", "descricao")
    ordering = ("codigo",)
    list_per_page = 50


class ImpostoSeloAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("verba", "taxa_original", "tipo_taxa", "taxa_percentual", "valor_fixo", "ativo")
    list_filter = ("tipo_taxa", "ativo")
    search_fields = ("verba", "descricao", "taxa_original")
    ordering = ("verba",)
    list_per_page = 50


class ImpostoEspecialConsumoAdmin(TenantSchemaAdminMixin, admin.ModelAdmin):
    list_display = ("codigo_pautal", "designacao", "taxa_percentual", "ativo")
    list_filter = ("taxa_percentual", "ativo")
    search_fields = ("codigo_pautal", "designacao", "unidade_medida")
    ordering = ("codigo_pautal",)
    list_per_page = 50


for model, model_admin in (
    (CAE, CAEAdmin),
    (ImpostoSelo, ImpostoSeloAdmin),
    (ImpostoEspecialConsumo, ImpostoEspecialConsumoAdmin),
):
    if not admin.site.is_registered(model):
        admin.site.register(model, model_admin)
