from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Modulo, PlanoLicenca, Licenca, HistoricoLicenca
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import ComissaoBypass



@admin.register(ComissaoBypass)
class ComissaoBypassAdmin(admin.ModelAdmin):
    """
    🛡️ RIGOR SOTARQ: Painel de Controle de Royalties do Plano Elite.
    Gerencia os 2% de comissão de forma auditável.
    """
    list_display = (
        'empresa', 'get_periodo', 'get_faturamento_formatado', 
        'get_comissao_badge', 'get_status_badge', 'pago_em'
    )
    list_filter = ('status', 'periodo_inicio', 'empresa')
    search_fields = ('empresa__nome', 'empresa__nif')
    readonly_fields = ('valor_comissao', 'pago_em')
    
    actions = ['marcar_como_pago']

    # 🎨 Visualização de Rigor: Badges de Status
    def get_status_badge(self, obj):
        colors = {'pendente': '#dc3545', 'parcial': '#ffc107', 'pago': '#28a745'}
        return format_html(
            '<span style="background: {}; color: white; padding: 5px 12px; '
            'border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#6c757d'), obj.get_status_display().upper()
        )
    get_status_badge.short_description = "Situação"

    def get_comissao_badge(self, obj):
        return format_html('<strong style="color: #28a745;">{} Kz</strong>', f"{obj.valor_comissao:,.2f}")
    get_comissao_badge.short_description = "Nossa Parte (2%)"

    def get_faturamento_formatado(self, obj):
        return f"{obj.valor_faturado:,.2f} Kz"
    get_faturamento_formatado.short_description = "Faturado pelo Cliente"

    def get_periodo(self, obj):
        return f"{obj.periodo_inicio.strftime('%d/%m')} à {obj.periodo_fim.strftime('%d/%m/%y')}"
    get_periodo.short_description = "Período"

    # 🚀 Ação de Engenharia: Liquidação em Massa
    def marcar_como_pago(self, request, queryset):
        rows_updated = queryset.update(status='pago', pago_em=timezone.now())
        self.message_user(request, f"✔ {rows_updated} faturas de comissão foram liquidadas com sucesso.")
    marcar_como_pago.short_description = "Liquidar comissões selecionadas"



@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ('nome', 'slug', 'ativo', 'created_at')
    search_fields = ('nome', 'slug')
    list_filter = ('ativo',)
    prepopulated_fields = {'slug': ('nome',)} # Facilita a criação manual

@admin.register(PlanoLicenca)
class PlanoLicencaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco_mensal', 'limite_usuarios', 'limite_produtos', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    filter_horizontal = ('modulos',) # Interface amigável para selecionar ManyToMany

class HistoricoLicencaInline(admin.TabularInline):
    """Permite visualizar o histórico diretamente dentro da página da Licença"""
    model = HistoricoLicenca
    extra = 0
    readonly_fields = ('acao', 'data_anterior', 'data_nova', 'observacoes', 'created_at')
    can_delete = False

@admin.register(Licenca)
class LicencaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'plano', 'status_vencimento', 'data_vencimento', 'status_badge')
    list_filter = ('status', 'plano', 'data_vencimento')
    search_fields = ('empresa__nome', 'chave_licenca')
    readonly_fields = ('chave_licenca', 'created_at', 'updated_at')
    inlines = [HistoricoLicencaInline]
    
    fieldsets = (
        ('Identificação', {
            'fields': ('chave_licenca', 'empresa', 'plano', 'status')
        }),
        ('Prazos e Datas', {
            'fields': ('data_inicio', 'data_vencimento', 'data_cancelamento')
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',) # Esconde por padrão para limpar a tela
        }),
    )

    def status_badge(self, obj):
        """Cria um indicador visual colorido para o status no grid"""
        colors = {
            'ativa': '#059669',   # Verde
            'expirada': '#dc2626', # Vermelho
            'suspensa': '#d97706', # Laranja
            'cancelada': '#4b5563', # Cinza
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 10px; border-radius: 10px; font-weight: bold;">{}</span>',
            colors.get(obj.status, '#000'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def status_vencimento(self, obj):
        """Exibe o rastro de dias restantes com cor de alerta"""
        dias = obj.dias_para_vencer
        if obj.esta_vencida:
            return format_html('<b style="color: #dc2626;">VENCIDA</b>')
        if dias <= 7:
            return format_html('<b style="color: #d97706;">Vence em {} dias</b>', dias)
        return f"{dias} dias restantes"
    status_vencimento.short_description = 'Prazo'

@admin.register(HistoricoLicenca)
class HistoricoLicencaAdmin(admin.ModelAdmin):
    list_display = ('licenca', 'acao', 'data_nova', 'created_at')
    list_filter = ('acao', 'created_at')
    readonly_fields = ('licenca', 'acao', 'data_anterior', 'data_nova', 'observacoes', 'created_at', 'updated_at')
