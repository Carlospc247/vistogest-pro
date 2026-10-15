# apps/site/urls.py
from django.urls import path
from . import views

app_name = 'site'

urlpatterns = [
    path(
        'admin/secao/<int:secao_id>/upload-imagem/',
        views.UploadImagemSecaoView.as_view(),
        name='upload_imagem_secao',
    ),
    # ── Site Institucional ────────────────────────────────────────────────────
    path('', views.PaginaDetailView.as_view(), name='pagina_home'),
    path('p/<slug:slug>/', views.PaginaDetailView.as_view(), name='pagina_detalhe'),
    path('p/<slug:slug>/preview/<uuid:token>/', views.SitePreviewView.as_view(), name='preview'),

    # Painel de interações do público (S12)
    path('admin/interacoes/', views.InteracoesSiteView.as_view(), name='interacoes'),
    path('admin/interacoes/<str:tipo>/<int:pk>/atender/', views.AtenderInteracaoView.as_view(), name='atender_interacao'),
 
    # SEO da página (título + meta descrição)
    path('admin/pagina/<int:pk>/seo/', views.AtualizarSeoPaginaView.as_view(), name='seo_pagina'),
 
    # Tracking público (cliques no WhatsApp)
    path('track/', views.RegistarEventoView.as_view(), name='registar_evento'),


    
    # ── Loja Online — Catálogo ────────────────────────────────────────────────
    path('loja/', views.LojaView.as_view(), name='loja'),
    path('loja/produto/<int:pk>/', views.ProdutoDetalheView.as_view(), name='produto_detalhe'),
    path('loja/servico/<int:pk>/', views.ServicoDetalheView.as_view(), name='servico_detalhe'),

    # ── Loja Online — Carrinho ────────────────────────────────────────────────
    path('loja/carrinho/', views.CarrinhoView.as_view(), name='carrinho'),
    path('loja/carrinho/adicionar/', views.AdicionarCarrinhoView.as_view(), name='adicionar_carrinho'),
    path('loja/carrinho/remover/', views.RemoverItemCarrinhoView.as_view(), name='remover_carrinho'),

    # ── Loja Online — Checkout e Pedido ───────────────────────────────────────
    path('loja/checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('loja/pedido/<str:referencia>/', views.PedidoConfirmacaoView.as_view(), name='pedido_confirmacao'),

    # ── Área do Cliente (autenticação pública) ────────────────────────────────
    path('cliente/registo/', views.ClienteRegistoView.as_view(), name='cliente_registo'),
    path('cliente/login/', views.ClienteLoginView.as_view(), name='cliente_login'),
    path('cliente/logout/', views.ClienteLogoutView.as_view(), name='cliente_logout'),
    path('cliente/recuperar-senha/', views.ClienteRecuperarSenhaView.as_view(), name='cliente_recuperar_senha'),
    path('cliente/redefinir-senha/<str:token>/', views.ClienteRedefinirSenhaView.as_view(), name='cliente_redefinir_senha'),
    path('cliente/perfil/', views.ClientePerfilView.as_view(), name='cliente_perfil'),
    path('cliente/pedidos/', views.MeusPedidosView.as_view(), name='cliente_pedidos'),

    # ── Formulários públicos ──────────────────────────────────────────────────
    path('candidatura/', views.CandidaturaCreateView.as_view(), name='candidatura'),
    path('contato/', views.SolicitacaoContatoCreateView.as_view(), name='contato'),
    path('reclamacao/', views.ReclamacaoCreateView.as_view(), name='reclamacao'),
    path('agendamento/', views.ProcessarAgendamentoSiteView.as_view(), name='agendamento'),

    # ══════════════════════════════════════════════════════════════════════════
    # S12 — SITE BUILDER (Área de Gestão Interna)
    # Estas rotas são acedidas pelo gestor da empresa logado no sistema ERP.
    # Não são páginas públicas.
    # ══════════════════════════════════════════════════════════════════════════

    # Dashboard de administração do site
    path('admin/dashboard/', views.SiteConfigDashboardView.as_view(), name='configuracao_dashboard'),

    # Editor visual drag-and-drop (S12)
    path('admin/editor/', views.SiteEditorView.as_view(), name='editor'),
    path('admin/editor/<int:pagina_id>/', views.SiteEditorView.as_view(), name='editor'),

    # Publicação
    path('admin/publicar/<int:pk>/', views.PublicarSiteView.as_view(), name='publicar'),

    # Design Global (cores, fontes, tema)
    path('admin/design/', views.AtualizarDesignGlobalView.as_view(), name='design_global'),

    # Configuração geral (WhatsApp, loja, contactos)
    path('admin/configuracao/', views.AtualizarConfiguracaoView.as_view(), name='configuracao'),

    # ── CRUD de Secções ───────────────────────────────────────────────────────
    path('admin/pagina/<int:pagina_id>/adicionar-secao/', views.AdicionarSecaoView.as_view(), name='adicionar_secao'),
    path('admin/reordenar-secoes/', views.ReordenarSecoesView.as_view(), name='reordenar_secoes'),
    path('admin/secao/<int:secao_id>/dados/', views.EditarConteudoSecaoView.as_view(), name='get_secao_dados'),
    path('admin/secao/<int:secao_id>/editar/', views.EditarConteudoSecaoView.as_view(), name='editar_secao'),
    path('admin/secao/<int:secao_id>/duplicar/', views.DuplicarSecaoView.as_view(), name='duplicar_secao'),
    path('admin/secao/<int:secao_id>/eliminar/', views.EliminarSecaoView.as_view(), name='eliminar_secao'),
]
