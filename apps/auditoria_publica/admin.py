from django.contrib import admin
from django.utils.html import format_html
from .models import LogAuditoriaPublica

@admin.register(LogAuditoriaPublica)
class LogAuditoriaPublicaAdmin(admin.ModelAdmin):
    """
    🛡️ RIGOR SOTARQ: Painel de Monitorização de Infraestrutura.
    Focado em leitura e auditoria de eventos globais do ecossistema.
    """
    
    # 1. Configurações de Listagem
    list_display = (
        'get_nivel_badge', 
        'tipo_evento', 
        'acao', 
        'usuario', 
        'empresa_relacionada', 
        'ip_address', 
        'created_at'
    )
    
    list_filter = ('nivel', 'tipo_evento', 'created_at', 'empresa_relacionada')
    search_fields = ('acao', 'usuario__username', 'usuario__email', 'ip_address')
    ordering = ('-created_at',)
    
    # 2. Organização do Formulário (Apenas Leitura)
    fieldsets = (
        ('Classificação do Evento', {
            'fields': ('tipo_evento', 'nivel', 'acao')
        }),
        ('Origem e Contexto', {
            'fields': ('usuario', 'empresa_relacionada', 'ip_address', 'user_agent')
        }),
        ('Dados Técnicos (JSON)', {
            'fields': ('dados_contexto',),
            'classes': ('collapse',), # Escondido por padrão para não poluir
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    # 🛡️ RIGOR SOTARQ: Bloqueio de Alterações
    # Logs são evidências imutáveis. O Admin não pode criar, editar ou apagar.
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # Tornar todos os campos visíveis como readonly
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields] + ['updated_at']

    # 🎨 Visualização de Rigor para o Nível
    def get_nivel_badge(self, obj):
        colors = {
            'INFO': '#28a745',    # Verde
            'AVISO': '#ffc107',   # Amarelo
            'CRITICO': '#dc3545', # Vermelho
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 10px; '
            'border-radius: 10px; font-weight: bold; font-size: 10px;">{}</span>',
            colors.get(obj.nivel, '#6c757d'),
            obj.nivel
        )
    get_nivel_badge.short_description = "Nível"