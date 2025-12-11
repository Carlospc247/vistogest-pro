# apps/analytics/admin.py
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count, Q
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
import json

from .models import (
    EventoAnalytics, 
    AuditoriaAlteracao, 
    AlertaInteligente, 
    NotificacaoAlerta, 
    DashboardPersonalizado
)


@admin.register(EventoAnalytics)
class EventoAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'empresa', 'usuario', 'categoria', 'acao', 
        'label', 'valor', 'pais', 'cidade'
    ]
    list_filter = [
        'categoria', 'empresa', 'pais', 'timestamp'
    ]
    search_fields = [
        'acao', 'label', 'usuario__username', 'usuario__first_name', 
        'usuario__last_name', 'url', 'ip_address'
    ]
    readonly_fields = [
        'timestamp', 'ip_address', 'user_agent', 'propriedades_json'
    ]
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('empresa', 'usuario', 'categoria', 'acao', 'label')
        }),
        ('Dados do Evento', {
            'fields': ('valor', 'propriedades_json')
        }),
        ('Informações Técnicas', {
            'fields': ('url', 'referrer', 'ip_address', 'user_agent')
        }),
        ('Localização', {
            'fields': ('pais', 'cidade')
        }),
        ('Timestamp', {
            'fields': ('timestamp',)
        }),
    )
    
    def propriedades_json(self, obj):
        if obj.propriedades:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.propriedades, indent=2, ensure_ascii=False)
            )
        return '-'
    propriedades_json.short_description = 'Propriedades (JSON)'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AuditoriaAlteracao)
class AuditoriaAlteracaoAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'empresa', 'usuario', 'content_type', 
        'object_id', 'tipo_operacao', 'campos_alterados_count'
    ]
    list_filter = [
        'tipo_operacao', 'content_type', 'empresa', 'timestamp'
    ]
    search_fields = [
        'usuario__username', 'usuario__first_name', 'usuario__last_name',
        'motivo', 'object_id'
    ]
    readonly_fields = [
        'timestamp', 'dados_anteriores_json', 'dados_posteriores_json',
        'campos_alterados_json', 'content_object_link'
    ]
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('empresa', 'usuario', 'tipo_operacao', 'timestamp')
        }),
        ('Objeto Auditado', {
            'fields': ('content_type', 'object_id', 'content_object_link')
        }),
        ('Dados da Alteração', {
            'fields': ('dados_anteriores_json', 'dados_posteriores_json', 'campos_alterados_json')
        }),
        ('Contexto', {
            'fields': ('motivo', 'ip_address', 'user_agent')
        }),
    )
    
    def campos_alterados_count(self, obj):
        return len(obj.campos_alterados) if obj.campos_alterados else 0
    campos_alterados_count.short_description = 'Campos Alterados'
    
    def dados_anteriores_json(self, obj):
        if obj.dados_anteriores:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_anteriores, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_anteriores_json.short_description = 'Dados Anteriores'
    
    def dados_posteriores_json(self, obj):
        if obj.dados_posteriores:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_posteriores, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_posteriores_json.short_description = 'Dados Posteriores'
    
    def campos_alterados_json(self, obj):
        if obj.campos_alterados:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.campos_alterados, indent=2, ensure_ascii=False)
            )
        return '-'
    campos_alterados_json.short_description = 'Campos Alterados'
    
    def content_object_link(self, obj):
        if obj.content_object:
            try:
                url = reverse(
                    f'admin:{obj.content_type.app_label}_{obj.content_type.model}_change',
                    args=[obj.object_id]
                )
                return format_html(
                    '<a href="{}" target="_blank">{}</a>',
                    url, str(obj.content_object)
                )
            except:
                return str(obj.content_object)
        return '-'
    content_object_link.short_description = 'Objeto'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class NotificacaoAlertaInline(admin.TabularInline):
    model = NotificacaoAlerta
    extra = 0
    readonly_fields = ['enviada_em', 'lida_em']
    fields = [
        'usuario', 'enviada', 'lida', 'via_email', 
        'via_sistema', 'via_whatsapp', 'enviada_em', 'lida_em'
    ]


@admin.register(AlertaInteligente)
class AlertaInteligenteAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'empresa', 'tipo', 'prioridade', 'status',
        'titulo', 'usuarios_notificados_count', 'acoes_resolver'
    ]
    list_filter = [
        'tipo', 'prioridade', 'status', 'empresa', 'created_at'
    ]
    search_fields = [
        'titulo', 'mensagem', 'resolvido_por__username'
    ]
    readonly_fields = [
        'created_at', 'dados_contexto_json', 'acoes_sugeridas_json'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25
    inlines = [NotificacaoAlertaInline]
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('empresa', 'tipo', 'prioridade', 'status')
        }),
        ('Conteúdo', {
            'fields': ('titulo', 'mensagem')
        }),
        ('Dados Contextuais', {
            'fields': ('dados_contexto_json', 'acoes_sugeridas_json')
        }),
        ('Resolução', {
            'fields': ('resolvido_em', 'resolvido_por')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
    
    def usuarios_notificados_count(self, obj):
        return obj.usuarios_notificados.count()
    usuarios_notificados_count.short_description = 'Usuários Notificados'
    
    def dados_contexto_json(self, obj):
        if obj.dados_contexto:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_contexto, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_contexto_json.short_description = 'Dados de Contexto'
    
    def acoes_sugeridas_json(self, obj):
        if obj.acoes_sugeridas:
            return format_html(
                '<pre style="white-space: pre-wrap;">{}</pre>',
                json.dumps(obj.acoes_sugeridas, indent=2, ensure_ascii=False)
            )
        return '-'
    acoes_sugeridas_json.short_description = 'Ações Sugeridas'
    
    def acoes_resolver(self, obj):
        if obj.status == 'ativo':
            url = reverse('admin:analytics_alertainteligente_resolver', args=[obj.pk])
            return format_html(
                '<a href="{}" class="button">Resolver</a>',
                url
            )
        return '-'
    acoes_resolver.short_description = 'Ações'
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:alerta_id>/resolver/',
                self.admin_site.admin_view(self.resolver_alerta),
                name='analytics_alertainteligente_resolver',
            ),
        ]
        return custom_urls + urls
    
    def resolver_alerta(self, request, alerta_id):
        alerta = AlertaInteligente.objects.get(pk=alerta_id)
        if alerta.status == 'ativo':
            alerta.status = 'resolvido'
            alerta.resolvido_em = timezone.now()
            alerta.resolvido_por = request.user
            alerta.save()
            messages.success(request, f'Alerta "{alerta.titulo}" foi resolvido.')
        return redirect('admin:analytics_alertainteligente_change', alerta_id)


@admin.register(NotificacaoAlerta)
class NotificacaoAlertaAdmin(admin.ModelAdmin):
    list_display = [
        'alerta', 'usuario', 'enviada', 'lida', 'via_email',
        'via_sistema', 'via_whatsapp', 'enviada_em', 'lida_em'
    ]
    list_filter = [
        'enviada', 'lida', 'via_email', 'via_sistema', 'via_whatsapp',
        'alerta__tipo', 'alerta__prioridade'
    ]
    search_fields = [
        'usuario__username', 'usuario__first_name', 'usuario__last_name',
        'alerta__titulo'
    ]
    readonly_fields = ['enviada_em', 'lida_em']
    date_hierarchy = 'enviada_em'
    
    def has_add_permission(self, request):
        return False


@admin.register(DashboardPersonalizado)
class DashboardPersonalizadoAdmin(admin.ModelAdmin):
    list_display = [
        'nome', 'usuario', 'empresa', 'padrao', 'publico',
        'created_at', 'updated_at', 'acoes_dashboard'
    ]
    list_filter = [
        'padrao', 'publico', 'empresa', 'created_at'
    ]
    search_fields = [
        'nome', 'descricao', 'usuario__username', 
        'usuario__first_name', 'usuario__last_name'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'layout_json', 
        'widgets_json', 'filtros_padrao_json'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('usuario', 'empresa', 'nome', 'descricao')
        }),
        ('Configurações', {
            'fields': ('padrao', 'publico')
        }),
        ('Layout e Widgets', {
            'fields': ('layout_json', 'widgets_json', 'filtros_padrao_json')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def layout_json(self, obj):
        if obj.layout:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.layout, indent=2, ensure_ascii=False)
            )
        return '-'
    layout_json.short_description = 'Layout (JSON)'
    
    def widgets_json(self, obj):
        if obj.widgets:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.widgets, indent=2, ensure_ascii=False)
            )
        return '-'
    widgets_json.short_description = 'Widgets (JSON)'
    
    def filtros_padrao_json(self, obj):
        if obj.filtros_padrao:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.filtros_padrao, indent=2, ensure_ascii=False)
            )
        return '-'
    filtros_padrao_json.short_description = 'Filtros Padrão (JSON)'
    
    def acoes_dashboard(self, obj):
        url = reverse('analytics:dashboard_personalizado_preview', args=[obj.pk])
        return format_html(
            '<a href="{}" class="button" target="_blank">Visualizar</a>',
            url
        )
    acoes_dashboard.short_description = 'Ações'
    
    def save_model(self, request, obj, form, change):
        if not change:  # Novo objeto
            obj.usuario = request.user
        super().save_model(request, obj, form, change)


# Configurações gerais do admin
admin.site.site_header = 'VistoGEST Analytics'
admin.site.site_title = 'Analytics'
admin.site.index_title = 'Painel de Analytics'

