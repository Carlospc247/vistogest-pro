# apps/parceiros/admin.py
"""
Admin Global do Portal de Parceiros.
Secção 6.3 do PLANO_IMPLEMENTACAO.md.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Partner, PartnerLicensePlan, PartnerLicense, PartnerToken,
    PartnerClient, PartnerQuotaUsage, PartnerLicenseRequest,
    PartnerBilling, PartnerNotification, PartnerAudit,
)


# ── PartnerLicensePlan ────────────────────────────────────────────────────────

@admin.register(PartnerLicensePlan)
class PartnerLicensePlanAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'preco', 'moeda', 'duracao_display', 'max_empresas_total', 'max_empresas_mes', 'ativo')
    list_filter   = ('ativo', 'unidade_duracao')
    search_fields = ('nome',)
    filter_horizontal = ('planos_cliente_autorizados',)
    fieldsets = (
        ('Identificação', {'fields': ('nome', 'descricao', 'ativo')}),
        ('Preço e Duração', {'fields': ('preco', 'moeda', 'duracao', 'unidade_duracao', 'renovacao_automatica')}),
        ('Quotas', {'fields': ('max_empresas_total', 'max_empresas_mes')}),
        ('Permissões', {'fields': ('permite_renovacao', 'permite_upgrade', 'permite_downgrade')}),
        ('Planos de Cliente Autorizados', {
            'fields': ('planos_cliente_autorizados',),
            'description': (
                'Seleccione os planos de licença de cliente que parceiros com este plano '
                'estão autorizados a oferecer. O parceiro NÃO cria estes planos.'
            ),
        }),
    )

    def duracao_display(self, obj):
        return f"{obj.duracao} {obj.get_unidade_duracao_display()}"
    duracao_display.short_description = 'Duração'


# ── Partner ───────────────────────────────────────────────────────────────────

class PartnerLicenseInline(admin.TabularInline):
    model  = PartnerLicense
    extra  = 0
    fields = ('plano', 'status', 'data_inicio', 'data_expiracao', 'valor_pago')
    readonly_fields = ('data_inicio', 'data_expiracao')
    show_change_link = True


class PartnerClientInline(admin.TabularInline):
    model    = PartnerClient
    fk_name  = 'partner'   # PartnerClient tem 2 FKs para Partner; especificar qual usar
    extra    = 0
    fields   = ('empresa', 'status', 'licenca_cliente', 'created_at')
    readonly_fields = ('created_at',)
    show_change_link = True


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'tipo', 'nif', 'email', 'status_badge', 'licenca_activa_display', 'quota_display', 'created_at')
    list_filter   = ('status', 'tipo')
    search_fields = ('nome', 'nif', 'email', 'usuario__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PartnerLicenseInline, PartnerClientInline]
    fieldsets = (
        ('Dados do Parceiro', {'fields': ('usuario', 'nome', 'tipo', 'nif', 'telefone', 'email', 'endereco')}),
        ('Estado', {'fields': ('status', 'registado_por', 'observacoes')}),
        ('Auditoria', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def status_badge(self, obj):
        cores = {'activo': 'green', 'suspenso': 'orange', 'inactivo': 'gray', 'cancelado': 'red'}
        cor = cores.get(obj.status, 'gray')
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', cor, obj.get_status_display())
    status_badge.short_description = 'Estado'

    def licenca_activa_display(self, obj):
        lic = obj.licenca_activa
        if lic:
            return format_html('<span style="color:green;">✔ {}</span>', lic.plano.nome)
        return format_html('<span style="color:red;">{}</span>', '✘ Sem licença',)
    licenca_activa_display.short_description = 'Licença'

    def quota_display(self, obj):
        lic = obj.licenca_activa
        if not lic:
            return '—'
        s = lic.saldo()
        total = f"{s['total_usado']}/{'∞' if s['ilimitado_total'] else s['total_limite']}"
        return total
    quota_display.short_description = 'Quota'


# ── PartnerLicense ────────────────────────────────────────────────────────────

@admin.register(PartnerLicense)
class PartnerLicenseAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'plano', 'status_badge', 'data_inicio', 'data_expiracao', 'quota_display', 'valor_pago')
    list_filter   = ('status', 'plano', 'metodo_pagamento')
    search_fields = ('partner__nome', 'plano__nome')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['activar_licencas', 'suspender_licencas', 'expirar_licencas']

    def status_badge(self, obj):
        cores = {'activa': 'green', 'pendente': 'orange', 'expirada': 'red', 'suspensa': 'gray', 'cancelada': 'darkred'}
        cor = cores.get(obj.status, 'gray')
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', cor, obj.get_status_display())
    status_badge.short_description = 'Estado'

    def quota_display(self, obj):
        s = obj.saldo()
        t = f"{s['total_usado']}/{'∞' if s['ilimitado_total'] else s['total_limite']}"
        m = f"{s['mes_usado']}/{'∞' if s['ilimitado_mes'] else s['mes_limite']} (mês)"
        return f"{t} | {m}"
    quota_display.short_description = 'Quota (total | mês)'

    @admin.action(description='Activar licenças seleccionadas')
    def activar_licencas(self, request, queryset):
        hoje = timezone.now().date()
        for lic in queryset.filter(status='pendente'):
            lic.status = 'activa'
            lic.data_inicio = hoje
            lic.save(update_fields=['status', 'data_inicio'])
        self.message_user(request, f"{queryset.count()} licença(s) activada(s).")

    @admin.action(description='Suspender licenças seleccionadas')
    def suspender_licencas(self, request, queryset):
        queryset.update(status='suspensa')
        self.message_user(request, f"{queryset.count()} licença(s) suspensa(s).")

    @admin.action(description='Marcar como expiradas')
    def expirar_licencas(self, request, queryset):
        queryset.update(status='expirada')
        self.message_user(request, f"{queryset.count()} licença(s) marcada(s) como expiradas.")


# ── PartnerClient ─────────────────────────────────────────────────────────────

@admin.register(PartnerClient)
class PartnerClientAdmin(admin.ModelAdmin):
    list_display  = ('empresa', 'partner', 'status', 'licenca_cliente', 'created_at')
    list_filter   = ('status', 'partner')
    search_fields = ('empresa__nome', 'partner__nome')
    readonly_fields = ('created_at', 'data_transferencia', 'parceiro_anterior')


# ── PartnerLicenseRequest ─────────────────────────────────────────────────────

@admin.register(PartnerLicenseRequest)
class PartnerLicenseRequestAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'tipo', 'plano_solicitado', 'status_badge', 'created_at', 'respondido_por')
    list_filter   = ('status', 'tipo')
    search_fields = ('partner__nome',)
    readonly_fields = ('created_at', 'respondido_em')
    actions = ['aprovar_solicitacoes', 'rejeitar_solicitacoes']

    def status_badge(self, obj):
        cores = {'pendente': 'orange', 'aprovado': 'green', 'rejeitado': 'red', 'em_analise': 'blue', 'concluido': 'gray', 'cancelado': 'gray'}
        cor = cores.get(obj.status, 'gray')
        return format_html('<span style="color:{};">{}</span>', cor, obj.get_status_display())
    status_badge.short_description = 'Estado'

    @admin.action(description='Aprovar solicitações seleccionadas')
    def aprovar_solicitacoes(self, request, queryset):
        for req in queryset.filter(status__in=['pendente', 'em_analise']):
            req.status = 'aprovado'
            req.respondido_por = request.user
            req.respondido_em = timezone.now()
            req.save()
        self.message_user(request, f"{queryset.count()} solicitação(ões) aprovada(s).")

    @admin.action(description='Rejeitar solicitações seleccionadas')
    def rejeitar_solicitacoes(self, request, queryset):
        for req in queryset.filter(status__in=['pendente', 'em_analise']):
            req.status = 'rejeitado'
            req.respondido_por = request.user
            req.respondido_em = timezone.now()
            req.save()
        self.message_user(request, f"{queryset.count()} solicitação(ões) rejeitada(s).")


# ── PartnerBilling ────────────────────────────────────────────────────────────

@admin.register(PartnerBilling)
class PartnerBillingAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'valor', 'moeda', 'metodo', 'status', 'data_pagamento', 'registado_por')
    list_filter   = ('status', 'metodo', 'moeda')
    search_fields = ('partner__nome', 'referencia')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)


# ── PartnerToken ──────────────────────────────────────────────────────────────

@admin.register(PartnerToken)
class PartnerTokenAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'tipo', 'status', 'plano_destino', 'expira_em', 'utilizado_em', 'criado_por')
    list_filter   = ('tipo', 'status')
    search_fields = ('partner__nome',)
    readonly_fields = ('token_hash', 'utilizado_em', 'created_at')

    def has_add_permission(self, request):
        # Tokens são gerados via service — nunca directamente pelo admin
        return False


# ── PartnerAudit ──────────────────────────────────────────────────────────────

@admin.register(PartnerAudit)
class PartnerAuditAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'acao', 'objeto_tipo', 'executado_por', 'origem', 'created_at')
    list_filter   = ('acao', 'origem')
    search_fields = ('partner__nome', 'acao', 'executado_por__username')
    date_hierarchy = 'created_at'
    readonly_fields = tuple(f.name for f in PartnerAudit._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── PartnerNotification ───────────────────────────────────────────────────────

@admin.register(PartnerNotification)
class PartnerNotificationAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'tipo', 'titulo', 'lida', 'created_at')
    list_filter   = ('tipo', 'lida')
    search_fields = ('partner__nome', 'titulo')
    readonly_fields = ('created_at',)
