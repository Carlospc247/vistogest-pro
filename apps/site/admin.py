# apps/site/admin.py
"""Admin da app site — Bug 6 corrigido: admin.py estava vazio."""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ConfiguracaoSite, Pagina, Secao,
    ProdutoSite, ServicoSite,
    ClienteSite, Carrinho, ItemCarrinho,
    PedidoOnline, ItemPedidoOnline,
    Concurso, Candidatura,
    SolicitacaoContato, Reclamacao, ComprovativoCompra,
)


@admin.register(ConfiguracaoSite)
class ConfiguracaoSiteAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Identidade', {'fields': ('nome_exibicao', 'logo', 'favicon', 'slogan')}),
        ('Aparência', {'fields': ('cor_primaria', 'cor_secundaria', 'fonte')}),
        ('Contactos Públicos', {'fields': ('email_publico', 'telefone_publico', 'endereco_publico')}),
        ('WhatsApp', {'fields': ('numero_whatsapp', 'mensagem_whatsapp', 'mostrar_whatsapp')}),
        ('Loja Online', {'fields': ('loja_activa', 'aceita_pedidos', 'moeda', 'mensagem_confirmacao', 'email_notificacao_pedidos')}),
        ('Redes Sociais', {'fields': ('facebook', 'instagram', 'linkedin', 'youtube')}),
        ('Localização', {'fields': ('iframe_mapa',)}),
    )


class SecaoInline(admin.TabularInline):
    model = Secao
    extra = 0
    fields = ('tipo', 'ordem', 'ativo')


@admin.register(Pagina)
class PaginaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'slug', 'ativo', 'em_rascunho', 'created_at')
    list_filter  = ('ativo', 'em_rascunho')
    search_fields = ('titulo', 'slug')
    prepopulated_fields = {'slug': ('titulo',)}
    inlines = [SecaoInline]
    actions = ['publicar_paginas']

    @admin.action(description='Publicar páginas seleccionadas')
    def publicar_paginas(self, request, queryset):
        queryset.update(ativo=True, em_rascunho=False)
        self.message_user(request, f"{queryset.count()} página(s) publicada(s).")


@admin.register(ProdutoSite)
class ProdutoSiteAdmin(admin.ModelAdmin):
    list_display = ('produto', 'visivel_na_loja', 'destaque', 'preco_final', 'ordem_exibicao')
    list_filter  = ('visivel_na_loja', 'destaque')
    list_editable = ('visivel_na_loja', 'destaque', 'ordem_exibicao')
    search_fields = ('produto__nome_produto',)


@admin.register(ServicoSite)
class ServicoSiteAdmin(admin.ModelAdmin):
    list_display = ('servico', 'visivel_na_loja', 'destaque', 'preco_final', 'ordem_exibicao')
    list_filter  = ('visivel_na_loja', 'destaque')
    list_editable = ('visivel_na_loja', 'destaque', 'ordem_exibicao')
    search_fields = ('servico__nome',)


@admin.register(ClienteSite)
class ClienteSiteAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'email', 'telefone', 'registrado_no_sistema', 'ativo', 'created_at')
    list_filter   = ('ativo', 'registrado_no_sistema', 'pessoa_juridica')
    search_fields = ('nome', 'email')
    readonly_fields = ('registrado_no_sistema',)
    actions = ['sincronizar_com_sistema']

    @admin.action(description='Sincronizar com sistema interno')
    def sincronizar_com_sistema(self, request, queryset):
        count = 0
        for cli in queryset.filter(registrado_no_sistema=False):
            cli.sincronizar_com_sistema()
            count += 1
        self.message_user(request, f"{count} cliente(s) sincronizado(s).")


class ItemPedidoInline(admin.TabularInline):
    model  = ItemPedidoOnline
    extra  = 0
    fields = ('nome_item', 'quantidade', 'preco_unitario', 'total_linha')
    readonly_fields = ('total_linha',)


class ComprovativoInline(admin.TabularInline):
    model  = ComprovativoCompra
    extra  = 0
    fields = ('descricao', 'imagem', 'verificado')


@admin.register(PedidoOnline)
class PedidoOnlineAdmin(admin.ModelAdmin):
    list_display  = ('referencia', 'cliente_site', 'status_badge', 'total', 'moeda', 'venda_id', 'created_at')
    list_filter   = ('status', 'moeda')
    search_fields = ('referencia', 'cliente_site__nome', 'cliente_site__email')
    readonly_fields = ('referencia', 'created_at')
    inlines = [ItemPedidoInline, ComprovativoInline]
    actions = ['confirmar_pedidos', 'marcar_entregues']

    def status_badge(self, obj):
        cores = {
            'pendente': 'orange', 'confirmado': 'blue',
            'em_preparacao': 'purple', 'enviado': 'teal',
            'entregue': 'green', 'cancelado': 'red',
        }
        cor = cores.get(obj.status, 'gray')
        return format_html('<span style="color:{};font-weight:bold;">{}</span>', cor, obj.get_status_display())
    status_badge.short_description = 'Estado'

    @admin.action(description='Confirmar pedidos seleccionados')
    def confirmar_pedidos(self, request, queryset):
        queryset.filter(status='pendente').update(status='confirmado', processado_por=request.user)
        self.message_user(request, "Pedidos confirmados.")

    @admin.action(description='Marcar como entregues')
    def marcar_entregues(self, request, queryset):
        queryset.update(status='entregue')
        self.message_user(request, "Pedidos marcados como entregues.")


@admin.register(Concurso)
class ConcursoAdmin(admin.ModelAdmin):
    list_display  = ('titulo', 'ativo', 'data_inicio', 'data_fim')
    list_filter   = ('ativo',)
    search_fields = ('titulo',)


@admin.register(Candidatura)
class CandidaturaAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'email', 'concurso', 'status', 'created_at')
    list_filter   = ('status', 'concurso')
    search_fields = ('nome', 'email')


@admin.register(SolicitacaoContato)
class SolicitacaoContatoAdmin(admin.ModelAdmin):
    list_display  = ('nome', 'email', 'tipo', 'atendido', 'created_at')
    list_filter   = ('tipo', 'atendido')
    search_fields = ('nome', 'email')
    list_editable = ('atendido',)


@admin.register(Reclamacao)
class ReclamacaoAdmin(admin.ModelAdmin):
    list_display  = ('cliente_nome', 'assunto', 'status', 'atendido', 'created_at')
    list_filter   = ('status', 'atendido')
    search_fields = ('cliente_nome', 'cliente_email', 'assunto')
    list_editable = ('status', 'atendido')
