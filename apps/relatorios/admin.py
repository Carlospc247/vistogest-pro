# apps/relatorios/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.http import HttpResponse
import json

from .models import (
    TipoRelatorio, RelatorioGerado, MetricaKPI, DashboardConfig,
    AnaliseVendas, AnaliseEstoque, AnaliseClientes, AlertaGerencial,
    TemplateRelatorio, Relatorio, AgendamentoRelatorio
)


@admin.register(TipoRelatorio)
class TipoRelatorioAdmin(admin.ModelAdmin):
    list_display = [
        'codigo', 'nome', 'categoria', 'periodicidade', 'publico',
        'requer_aprovacao', 'ativo', 'ordem_exibicao', 'total_execucoes'
    ]
    list_filter = [
        'categoria', 'periodicidade', 'publico', 'requer_aprovacao', 'ativo'
    ]
    search_fields = ['codigo', 'nome', 'descricao']
    readonly_fields = ['created_at', 'updated_at', 'parametros_schema_json']
    list_editable = ['ordem_exibicao', 'ativo']
    ordering = ['categoria', 'ordem_exibicao', 'nome']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('codigo', 'nome', 'descricao', 'categoria')
        }),
        ('Configurações', {
            'fields': ('periodicidade', 'publico', 'requer_aprovacao', 'ativo', 'ordem_exibicao')
        }),
        ('Parâmetros e Template', {
            'fields': ('parametros_schema_json', 'query_sql', 'template_html'),
            'classes': ('collapse',)
        }),
        ('Permissões', {
            'fields': ('cargos_permitidos',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['cargos_permitidos']
    
    def parametros_schema_json(self, obj):
        if obj.parametros_schema:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.parametros_schema, indent=2, ensure_ascii=False)
            )
        return '-'
    parametros_schema_json.short_description = 'Parâmetros Schema (JSON)'
    
    def total_execucoes(self, obj):
        return obj.execucoes.count()
    total_execucoes.short_description = 'Total Execuções'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('execucoes')


@admin.register(RelatorioGerado)
class RelatorioGeradoAdmin(admin.ModelAdmin):
    list_display = [
        'codigo_relatorio', 'tipo_relatorio', 'formato', 'status',
        'solicitante', 'data_solicitacao', 'tempo_processamento_display',
        'total_registros', 'acoes_relatorio'
    ]
    list_filter = [
        'status', 'formato', 'tipo_relatorio__categoria',
        'data_solicitacao', 'empresa'
    ]
    search_fields = [
        'codigo_relatorio', 'tipo_relatorio__nome', 'solicitante__username'
    ]
    readonly_fields = [
        'codigo_relatorio', 'data_solicitacao', 'data_inicio_processamento',
        'data_conclusao', 'tempo_processamento', 'parametros_json',
        'dados_resultado_json'
    ]
    date_hierarchy = 'data_solicitacao'
    list_per_page = 50
    
    fieldsets = (
        ('Identificação', {
            'fields': ('codigo_relatorio', 'tipo_relatorio', 'formato', 'status')
        }),
        ('Solicitação', {
            'fields': ('solicitante', 'data_solicitacao', 'empresa')
        }),
        ('Parâmetros', {
            'fields': ('parametros_json', 'data_inicio', 'data_fim'),
            'classes': ('collapse',)
        }),
        ('Filtros', {
            'fields': ('lojas', 'categorias', 'funcionarios'),
            'classes': ('collapse',)
        }),
        ('Processamento', {
            'fields': (
                'data_inicio_processamento', 'data_conclusao',
                'tempo_processamento', 'mensagem_erro'
            )
        }),
        ('Resultado', {
            'fields': ('arquivo_resultado', 'dados_resultado_json', 'total_registros')
        }),
        ('Aprovação', {
            'fields': ('aprovador', 'data_aprovacao'),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ['lojas', 'categorias', 'funcionarios']
    
    def parametros_json(self, obj):
        if obj.parametros:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.parametros, indent=2, ensure_ascii=False)
            )
        return '-'
    parametros_json.short_description = 'Parâmetros (JSON)'
    
    def dados_resultado_json(self, obj):
        if obj.dados_resultado:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_resultado, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_resultado_json.short_description = 'Dados Resultado (JSON)'
    
    def tempo_processamento_display(self, obj):
        if obj.tempo_processamento:
            total_seconds = obj.tempo_processamento.total_seconds()
            if total_seconds < 60:
                return f"{total_seconds:.1f}s"
            elif total_seconds < 3600:
                return f"{total_seconds/60:.1f}min"
            else:
                return f"{total_seconds/3600:.1f}h"
        return '-'
    tempo_processamento_display.short_description = 'Tempo Processamento'
    
    def acoes_relatorio(self, obj):
        actions = []
        
        if obj.status == 'concluido' and obj.arquivo_resultado:
            download_url = obj.arquivo_resultado.url
            actions.append(
                f'<a href="{download_url}" class="button" target="_blank">Download</a>'
            )
        
        if obj.status == 'erro':
            actions.append(
                '<span style="color: red;">❌ Erro</span>'
            )
        elif obj.status == 'processando':
            actions.append(
                '<span style="color: orange;">⏳ Processando</span>'
            )
        elif obj.status == 'concluido':
            actions.append(
                '<span style="color: green;">✅ Concluído</span>'
            )
        
        return format_html(' '.join(actions))
    acoes_relatorio.short_description = 'Ações'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MetricaKPI)
class MetricaKPIAdmin(admin.ModelAdmin):
    list_display = [
        'codigo', 'nome', 'tipo_metrica', 'periodo', 'data_referencia',
        'valor_atual_formatted', 'variacao_display', 'status_meta_display'
    ]
    list_filter = [
        'tipo_metrica', 'periodo', 'formato_exibicao', 'data_referencia', 'empresa'
    ]
    search_fields = ['codigo', 'nome', 'descricao']
    readonly_fields = [
        'created_at', 'updated_at', 'variacao_absoluta', 'variacao_percentual',
        'detalhes_calculo_json', 'percentual_meta_display'
    ]
    date_hierarchy = 'data_referencia'
    list_per_page = 50
    
    fieldsets = (
        ('Identificação', {
            'fields': ('codigo', 'nome', 'descricao', 'tipo_metrica')
        }),
        ('Período', {
            'fields': ('periodo', 'data_referencia')
        }),
        ('Valores', {
            'fields': (
                'valor_atual', 'valor_anterior', 'valor_meta',
                'variacao_absoluta', 'variacao_percentual'
            )
        }),
        ('Formatação', {
            'fields': ('unidade_medida', 'formato_exibicao')
        }),
        ('Filtros', {
            'fields': ('loja', 'categoria', 'empresa')
        }),
        ('Detalhes', {
            'fields': ('detalhes_calculo_json',),
            'classes': ('collapse',)
        }),
        ('Meta', {
            'fields': ('percentual_meta_display',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def valor_atual_formatted(self, obj):
        if obj.formato_exibicao == 'moeda':
            return f"R$ {obj.valor_atual:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        elif obj.formato_exibicao == 'percentual':
            return f"{obj.valor_atual:.2f}%"
        else:
            return f"{obj.valor_atual} {obj.unidade_medida}"
    valor_atual_formatted.short_description = 'Valor Atual'
    
    def variacao_display(self, obj):
        if obj.variacao_percentual > 0:
            color = 'green'
            arrow = '↗'
        elif obj.variacao_percentual < 0:
            color = 'red'
            arrow = '↘'
        else:
            color = 'gray'
            arrow = '→'
        
        return format_html(
            '<span style="color: {};">{} {:.2f}%</span>',
            color, arrow, obj.variacao_percentual
        )
    variacao_display.short_description = 'Variação'
    
    def status_meta_display(self, obj):
        status = obj.status_meta
        if status == 'atingida':
            return format_html('<span style="color: green;">✅ Atingida</span>')
        elif status == 'proximo':
            return format_html('<span style="color: orange;">⚠️ Próximo</span>')
        elif status == 'distante':
            return format_html('<span style="color: red;">❌ Distante</span>')
        else:
            return format_html('<span style="color: gray;">➖ Sem Meta</span>')
    status_meta_display.short_description = 'Status Meta'
    
    def percentual_meta_display(self, obj):
        percentual = obj.percentual_meta
        if percentual is not None:
            return f"{percentual:.1f}%"
        return 'Sem meta definida'
    percentual_meta_display.short_description = 'Percentual da Meta'
    
    def detalhes_calculo_json(self, obj):
        if obj.detalhes_calculo:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.detalhes_calculo, indent=2, ensure_ascii=False)
            )
        return '-'
    detalhes_calculo_json.short_description = 'Detalhes do Cálculo'


@admin.register(DashboardConfig)
class DashboardConfigAdmin(admin.ModelAdmin):
    list_display = [
        'nome', 'usuario', 'publico', 'dashboard_padrao', 'auto_refresh',
        'ativo', 'total_widgets', 'empresa'
    ]
    list_filter = ['publico', 'dashboard_padrao', 'auto_refresh', 'ativo', 'empresa']
    search_fields = ['nome', 'descricao', 'codigo', 'usuario__username']
    readonly_fields = [
        'created_at', 'updated_at', 'configuracao_layout_json', 'widgets_incluidos_json'
    ]
    
    fieldsets = (
        ('Identificação', {
            'fields': ('nome', 'descricao', 'codigo', 'usuario', 'empresa')
        }),
        ('Configurações', {
            'fields': ('publico', 'dashboard_padrao', 'ativo')
        }),
        ('Atualização', {
            'fields': ('auto_refresh', 'intervalo_refresh')
        }),
        ('Layout', {
            'fields': ('configuracao_layout_json',),
            'classes': ('collapse',)
        }),
        ('Widgets', {
            'fields': ('widgets_incluidos_json',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_widgets(self, obj):
        return len(obj.widgets_incluidos) if obj.widgets_incluidos else 0
    total_widgets.short_description = 'Total Widgets'
    
    def configuracao_layout_json(self, obj):
        if obj.configuracao_layout:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.configuracao_layout, indent=2, ensure_ascii=False)
            )
        return '-'
    configuracao_layout_json.short_description = 'Configuração Layout'
    
    def widgets_incluidos_json(self, obj):
        if obj.widgets_incluidos:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.widgets_incluidos, indent=2, ensure_ascii=False)
            )
        return '-'
    widgets_incluidos_json.short_description = 'Widgets Incluídos'


@admin.register(AnaliseVendas)
class AnaliseVendasAdmin(admin.ModelAdmin):
    list_display = [
        'dimensao', 'data_inicio', 'data_fim', 'total_vendas',
        'faturamento_formatted', 'ticket_medio_formatted',
        'data_processamento', 'usuario_solicitante'
    ]
    list_filter = [
        'dimensao', 'data_processamento', 'loja', 'categoria', 'empresa'
    ]
    search_fields = ['usuario_solicitante__username']
    readonly_fields = [
        'data_processamento', 'top_produtos_json', 'top_clientes_json',
        'top_vendedores_json', 'vendas_por_dia_json', 'dados_detalhados_json'
    ]
    date_hierarchy = 'data_processamento'
    
    fieldsets = (
        ('Configuração', {
            'fields': ('dimensao', 'data_inicio', 'data_fim', 'usuario_solicitante')
        }),
        ('Filtros', {
            'fields': ('loja', 'categoria', 'empresa')
        }),
        ('Resultados Gerais', {
            'fields': (
                'total_vendas', 'total_itens', 'faturamento_total',
                'ticket_medio', 'margem_bruta_total', 'margem_bruta_percentual'
            )
        }),
        ('Top Performers', {
            'fields': ('top_produtos_json', 'top_clientes_json', 'top_vendedores_json'),
            'classes': ('collapse',)
        }),
        ('Análises Temporais', {
            'fields': ('vendas_por_dia_json',),
            'classes': ('collapse',)
        }),
        ('Dados Detalhados', {
            'fields': ('dados_detalhados_json',),
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('data_processamento',)
        }),
    )
    
    def faturamento_formatted(self, obj):
        return f"R$ {obj.faturamento_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    faturamento_formatted.short_description = 'Faturamento'
    
    def ticket_medio_formatted(self, obj):
        return f"R$ {obj.ticket_medio:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    ticket_medio_formatted.short_description = 'Ticket Médio'
    
    def top_produtos_json(self, obj):
        if obj.top_produtos:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.top_produtos, indent=2, ensure_ascii=False)
            )
        return '-'
    top_produtos_json.short_description = 'Top Produtos'
    
    def top_clientes_json(self, obj):
        if obj.top_clientes:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.top_clientes, indent=2, ensure_ascii=False)
            )
        return '-'
    top_clientes_json.short_description = 'Top Clientes'
    
    def top_vendedores_json(self, obj):
        if obj.top_vendedores:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.top_vendedores, indent=2, ensure_ascii=False)
            )
        return '-'
    top_vendedores_json.short_description = 'Top Vendedores'
    
    def vendas_por_dia_json(self, obj):
        if obj.vendas_por_dia:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.vendas_por_dia, indent=2, ensure_ascii=False)
            )
        return '-'
    vendas_por_dia_json.short_description = 'Vendas por Dia'
    
    def dados_detalhados_json(self, obj):
        if obj.dados_detalhados:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_detalhados, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_detalhados_json.short_description = 'Dados Detalhados'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnaliseEstoque)
class AnaliseEstoqueAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_analise', 'data_referencia', 'periodo_analise_dias',
        'total_produtos_analisados', 'valor_estoque_formatted',
        'giro_medio', 'data_processamento', 'usuario_solicitante'
    ]
    list_filter = [
        'tipo_analise', 'data_processamento', 'loja', 'categoria', 'empresa'
    ]
    search_fields = ['usuario_solicitante__username']
    readonly_fields = [
        'data_processamento', 'produtos_classe_a_json', 'produtos_criticos_json',
        'dados_completos_json', 'recomendacoes_json'
    ]
    date_hierarchy = 'data_processamento'
    
    fieldsets = (
        ('Configuração', {
            'fields': (
                'tipo_analise', 'data_referencia', 'periodo_analise_dias',
                'usuario_solicitante'
            )
        }),
        ('Filtros', {
            'fields': ('loja', 'categoria', 'empresa')
        }),
        ('Resultados Gerais', {
            'fields': (
                'total_produtos_analisados', 'valor_estoque_total', 'giro_medio'
            )
        }),
        ('Classificação ABC', {
            'fields': ('produtos_classe_a_json',),
            'classes': ('collapse',)
        }),
        ('Produtos Críticos', {
            'fields': ('produtos_criticos_json',),
            'classes': ('collapse',)
        }),
        ('Recomendações', {
            'fields': ('recomendacoes_json',),
            'classes': ('collapse',)
        }),
        ('Dados Completos', {
            'fields': ('dados_completos_json',),
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('data_processamento',)
        }),
    )
    
    def valor_estoque_formatted(self, obj):
        return f"R$ {obj.valor_estoque_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    valor_estoque_formatted.short_description = 'Valor Estoque'
    
    def produtos_classe_a_json(self, obj):
        if obj.produtos_classe_a:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.produtos_classe_a, indent=2, ensure_ascii=False)
            )
        return '-'
    produtos_classe_a_json.short_description = 'Produtos Classe A'
    
    def produtos_criticos_json(self, obj):
        dados_criticos = {
            'ruptura': obj.produtos_ruptura,
            'excesso': obj.produtos_excesso,
            'vencendo': obj.produtos_vencendo,
            'sem_giro': obj.produtos_sem_giro
        }
        if any(dados_criticos.values()):
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(dados_criticos, indent=2, ensure_ascii=False)
            )
        return '-'
    produtos_criticos_json.short_description = 'Produtos Críticos'
    
    def recomendacoes_json(self, obj):
        recomendacoes = {
            'compra': obj.recomendacoes_compra,
            'promocao': obj.recomendacoes_promocao
        }
        if any(recomendacoes.values()):
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(recomendacoes, indent=2, ensure_ascii=False)
            )
        return '-'
    recomendacoes_json.short_description = 'Recomendações'
    
    def dados_completos_json(self, obj):
        if obj.dados_completos:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_completos, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_completos_json.short_description = 'Dados Completos'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AnaliseClientes)
class AnaliseClientesAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_segmentacao', 'data_inicio', 'data_fim',
        'total_clientes_analisados', 'total_clientes_ativos',
        'valor_medio_formatted', 'data_processamento', 'usuario_solicitante'
    ]
    list_filter = [
        'tipo_segmentacao', 'data_processamento', 'loja', 'empresa'
    ]
    search_fields = ['usuario_solicitante__username']
    readonly_fields = [
        'data_processamento', 'segmentacao_rfm_json', 'analise_produtos_json',
        'analise_temporal_json', 'recomendacoes_json', 'dados_detalhados_json'
    ]
    date_hierarchy = 'data_processamento'
    
    fieldsets = (
        ('Configuração', {
            'fields': (
                'tipo_segmentacao', 'data_inicio', 'data_fim', 'usuario_solicitante'
            )
        }),
        ('Filtros', {
            'fields': ('loja', 'empresa')
        }),
        ('Resultados Gerais', {
            'fields': (
                'total_clientes_analisados', 'total_clientes_ativos',
                'valor_medio_compra', 'frequencia_media_compra'
            )
        }),
        ('Segmentação RFM', {
            'fields': ('segmentacao_rfm_json',),
            'classes': ('collapse',)
        }),
        ('Análise de Produtos', {
            'fields': ('analise_produtos_json',),
            'classes': ('collapse',)
        }),
        ('Análise Temporal', {
            'fields': ('analise_temporal_json',),
            'classes': ('collapse',)
        }),
        ('Recomendações', {
            'fields': ('recomendacoes_json',),
            'classes': ('collapse',)
        }),
        ('Dados Detalhados', {
            'fields': ('dados_detalhados_json',),
            'classes': ('collapse',)
        }),
        ('Metadados', {
            'fields': ('data_processamento',)
        }),
    )
    
    def valor_medio_formatted(self, obj):
        return f"R$ {obj.valor_medio_compra:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    valor_medio_formatted.short_description = 'Valor Médio'
    
    def segmentacao_rfm_json(self, obj):
        segmentacao = {
            'vip': obj.clientes_vip,
            'frequentes': obj.clientes_frequentes,
            'ocasionais': obj.clientes_ocasionais,
            'inativos': obj.clientes_inativos,
            'em_risco': obj.clientes_em_risco
        }
        return format_html(
            '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
            json.dumps(segmentacao, indent=2, ensure_ascii=False)
        )
    segmentacao_rfm_json.short_description = 'Segmentação RFM'
    
    def analise_produtos_json(self, obj):
        analise = {
            'produtos_mais_vendidos': obj.produtos_mais_vendidos,
            'categorias_preferidas': obj.categorias_preferidas
        }
        if any(analise.values()):
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(analise, indent=2, ensure_ascii=False)
            )
        return '-'
    analise_produtos_json.short_description = 'Análise de Produtos'
    
    def analise_temporal_json(self, obj):
        temporal = {
            'por_mes': obj.distribuicao_compras_mes,
            'por_dia_semana': obj.distribuicao_compras_dia_semana,
            'por_hora': obj.distribuicao_compras_hora
        }
        if any(temporal.values()):
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(temporal, indent=2, ensure_ascii=False)
            )
        return '-'
    analise_temporal_json.short_description = 'Análise Temporal'
    
    def recomendacoes_json(self, obj):
        recomendacoes = {
            'retencao': obj.recomendacoes_retencao,
            'reativacao': obj.recomendacoes_reativacao
        }
        if any(recomendacoes.values()):
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(recomendacoes, indent=2, ensure_ascii=False)
            )
        return '-'
    recomendacoes_json.short_description = 'Recomendações'
    
    def dados_detalhados_json(self, obj):
        if obj.dados_detalhados:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 300px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.dados_detalhados, indent=2, ensure_ascii=False)
            )
        return '-'
    dados_detalhados_json.short_description = 'Dados Detalhados'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AlertaGerencial)
class AlertaGerencialAdmin(admin.ModelAdmin):
    list_display = [
        'tipo_alerta', 'prioridade', 'titulo', 'data_referencia',
        'ativo', 'valor_atual_formatted', 'status_display',
        'empresa'
    ]
    list_filter = [
        'tipo_alerta', 'prioridade', 'ativo', 'data_referencia', 'empresa'
    ]
    search_fields = ['titulo', 'descricao']
    readonly_fields = [
        'created_at', 'updated_at', 'acoes_recomendadas_json'
    ]
    list_editable = ['ativo']
    date_hierarchy = 'data_referencia'
    
    fieldsets = (
        ('Configuração', {
            'fields': ('tipo_alerta', 'prioridade', 'titulo', 'descricao')
        }),
        ('Valores', {
            'fields': ('valor_atual', 'valor_esperado', 'data_referencia')
        }),
        ('Contexto', {
            'fields': ('loja', 'produto', 'cliente', 'funcionario', 'empresa')
        }),
        ('Ações', {
            'fields': ('acoes_recomendadas_json',)
        }),
        ('Status', {
            'fields': ('ativo', 'data_resolucao', 'resolvido_por', 'observacoes_resolucao')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['resolver_alertas', 'reativar_alertas']
    
    def valor_atual_formatted(self, obj):
        if obj.valor_atual:
            return f"R$ {obj.valor_atual:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return '-'
    valor_atual_formatted.short_description = 'Valor Atual'
    
    def status_display(self, obj):
        if obj.ativo:
            if obj.prioridade == 'critica':
                return format_html('<span style="color: red;">🔴 Ativo - Crítico</span>')
            elif obj.prioridade == 'alta':
                return format_html('<span style="color: orange;">🟠 Ativo - Alto</span>')
            else:
                return format_html('<span style="color: yellow;">🟡 Ativo</span>')
        else:
            return format_html('<span style="color: green;">✅ Resolvido</span>')
    status_display.short_description = 'Status'
    
    def acoes_recomendadas_json(self, obj):
        if obj.acoes_recomendadas:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.acoes_recomendadas, indent=2, ensure_ascii=False)
            )
        return '-'
    acoes_recomendadas_json.short_description = 'Ações Recomendadas'
    
    def resolver_alertas(self, request, queryset):
        count = 0
        for alerta in queryset.filter(ativo=True):
            alerta.resolver_alerta(request.user, "Resolvido via admin")
            count += 1
        
        self.message_user(
            request,
            f'{count} alerta(s) resolvido(s) com sucesso.',
            messages.SUCCESS
        )
    resolver_alertas.short_description = "Resolver alertas selecionados"
    
    def reativar_alertas(self, request, queryset):
        count = queryset.filter(ativo=False).update(
            ativo=True,
            data_resolucao=None,
            resolvido_por=None,
            observacoes_resolucao=''
        )
        
        self.message_user(
            request,
            f'{count} alerta(s) reativado(s) com sucesso.',
            messages.SUCCESS
        )
    reativar_alertas.short_description = "Reativar alertas selecionados"


@admin.register(TemplateRelatorio)
class TemplateRelatorioAdmin(admin.ModelAdmin):
    list_display = [
        'nome', 'modelo_base', 'empresa', 'ativo', 'total_relatorios'
    ]
    list_filter = ['modelo_base', 'ativo', 'empresa']
    search_fields = ['nome', 'descricao']
    readonly_fields = [
        'created_at', 'updated_at', 'campos_json', 'filtros_disponiveis_json'
    ]
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('nome', 'descricao', 'empresa', 'modelo_base', 'ativo')
        }),
        ('Configuração', {
            'fields': ('campos_json', 'filtros_disponiveis_json')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def campos_json(self, obj):
        if obj.campos:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.campos, indent=2, ensure_ascii=False)
            )
        return '-'
    campos_json.short_description = 'Campos (JSON)'
    
    def filtros_disponiveis_json(self, obj):
        if obj.filtros_disponiveis:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.filtros_disponiveis, indent=2, ensure_ascii=False)
            )
        return '-'
    filtros_disponiveis_json.short_description = 'Filtros Disponíveis (JSON)'
    
    def total_relatorios(self, obj):
        return obj.relatorio_set.count()
    total_relatorios.short_description = 'Total Relatórios'


@admin.register(Relatorio)
class RelatorioAdmin(admin.ModelAdmin):
    list_display = [
        'template', 'formato', 'status', 'gerado_por',
        'data_geracao', 'arquivo_link'
    ]
    list_filter = ['formato', 'status', 'data_geracao']
    search_fields = ['template__nome', 'gerado_por__username']
    readonly_fields = [
        'data_geracao', 'filtros_aplicados_json'
    ]
    date_hierarchy = 'data_geracao'
    
    fieldsets = (
        ('Configuração', {
            'fields': ('template', 'formato', 'gerado_por')
        }),
        ('Filtros', {
            'fields': ('filtros_aplicados_json',)
        }),
        ('Resultado', {
            'fields': ('status', 'arquivo_gerado', 'data_geracao')
        }),
    )
    
    def filtros_aplicados_json(self, obj):
        if obj.filtros_aplicados:
            return format_html(
                '<pre style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{}</pre>',
                json.dumps(obj.filtros_aplicados, indent=2, ensure_ascii=False)
            )
        return '-'
    filtros_aplicados_json.short_description = 'Filtros Aplicados (JSON)'
    
    def arquivo_link(self, obj):
        if obj.arquivo_gerado:
            return format_html(
                '<a href="{}" target="_blank">Download</a>',
                obj.arquivo_gerado.url
            )
        return '-'
    arquivo_link.short_description = 'Arquivo'
    
    def has_add_permission(self, request):
        return False


@admin.register(AgendamentoRelatorio)
class AgendamentoRelatorioAdmin(admin.ModelAdmin):
    list_display = [
        'template', 'frequencia', 'horario', 'ativo',
        'total_destinatarios'
    ]
    list_filter = ['frequencia', 'ativo']
    search_fields = ['template__nome', 'destinatarios']
    
    fieldsets = (
        ('Configuração', {
            'fields': ('template', 'frequencia', 'horario', 'ativo')
        }),
        ('Destinatários', {
            'fields': ('destinatarios',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def total_destinatarios(self, obj):
        if obj.destinatarios:
            emails = [email.strip() for email in obj.destinatarios.split(',')]
            return len([email for email in emails if email])
        return 0
    total_destinatarios.short_description = 'Total Destinatários'


# Configurações do admin
admin.site.site_header = 'VistoGEST - Administração'
admin.site.site_title = 'Administração'
admin.site.index_title = 'Administração do Sistema'