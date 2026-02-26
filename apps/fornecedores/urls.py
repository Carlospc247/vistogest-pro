# apps/fornecedores/urls.py
from django.urls import path, include
from . import views



app_name = 'fornecedores'

urlpatterns = [
    # =====================================
    # LISTAGENS PRINCIPAIS
    # =====================================
    path('', views.FornecedorListView.as_view(), name='lista'),
    path('pedidos/', views.PedidoCompraListView.as_view(), name='pedido_lista'),
    path('contratos/', views.ContratoListView.as_view(), name='contrato_lista'),
    
    # =====================================
    # GESTÃO DE FORNECEDORES
    # =====================================
    path('novo/', views.FornecedorCreateView.as_view(), name='create'),
    path('<int:pk>/', views.FornecedorDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.FornecedorUpdateView.as_view(), name='update'),
    path('<int:pk>/deletar/', views.FornecedorDeleteView.as_view(), name='delete'),
    
    # Ações especiais
    path('<int:pk>/ativar/', views.AtivarFornecedorView.as_view(), name='ativar'),
    path('<int:pk>/bloquear/', views.BloquearFornecedorView.as_view(), name='bloquear'),
    path('<int:pk>/avaliar/', views.AvaliarFornecedorView.as_view(), name='avaliar'),
    path('<int:pk>/historico/', views.HistoricoFornecedorView.as_view(), name='historico'),
    
    # =====================================
    # GESTÃO DE CONTATOS
    # =====================================
    path('<int:fornecedor_pk>/contatos/', views.ContatoListView.as_view(), name='contato_lista'),
    path('<int:fornecedor_pk>/contatos/novo/', views.ContatoCreateView.as_view(), name='contato_create'),
    path('contatos/<int:pk>/editar/', views.ContatoUpdateView.as_view(), name='contato_update'),
    path('contatos/<int:pk>/deletar/', views.ContatoDeleteView.as_view(), name='contato_delete'),
    
    # =====================================
    # PEDIDOS DE COMPRA
    # =====================================
    path('pedidos/novo/', views.PedidoCompraCreateView.as_view(), name='pedido_create'),
    path('pedidos/<int:pk>/', views.PedidoCompraDetailView.as_view(), name='pedido_detail'),
    path('pedidos/<int:pk>/editar/', views.PedidoCompraUpdateView.as_view(), name='pedido_update'),
    path('pedidos/<int:pk>/deletar/', views.PedidoCompraDeleteView.as_view(), name='pedido_delete'),
    
    # Status do pedido
    path('pedidos/<int:pk>/aprovar/', views.AprovarPedidoView.as_view(), name='pedido_aprovar'),
    path('pedidos/<int:pk>/enviar/', views.EnviarPedidoView.as_view(), name='pedido_enviar'),
    path('pedidos/<int:pk>/cancelar/', views.CancelarPedidoView.as_view(), name='pedido_cancelar'),
    path('pedidos/<int:pk>/receber/', views.ReceberPedidoView.as_view(), name='pedido_receber'),
    
    # Documentos do pedido
    path('pedidos/<int:pk>/imprimir/', views.ImprimirPedidoView.as_view(), name='pedido_imprimir'),
    path('pedidos/<int:pk>/pdf/', views.PedidoPDFView.as_view(), name='pedido_pdf'),
    path('pedidos/<int:pk>/xml/', views.PedidoXMLView.as_view(), name='pedido_xml'),
    
    # =====================================
    # CONTRATOS
    # =====================================
    path('contratos/novo/', views.ContratoCreateView.as_view(), name='contrato_create'),
    path('contratos/<int:pk>/', views.ContratoDetailView.as_view(), name='contrato_detail'),
    path('contratos/<int:pk>/editar/', views.ContratoUpdateView.as_view(), name='contrato_update'),
    path('contratos/<int:pk>/renovar/', views.RenovarContratoView.as_view(), name='contrato_renovar'),
    path('contratos/<int:pk>/encerrar/', views.EncerrarContratoView.as_view(), name='contrato_encerrar'),
    
    # =====================================
    # AVALIAÇÕES E QUALIFICAÇÃO
    # =====================================
    path('avaliacoes/', views.AvaliacaoListView.as_view(), name='avaliacao_lista'),
    path('<int:fornecedor_pk>/nova-avaliacao/', views.AvaliacaoCreateView.as_view(), name='avaliacao_create'),
    path('qualificacao/', views.QualificacaoFornecedorView.as_view(), name='qualificacao'),
    path('ranking/', views.RankingFornecedorView.as_view(), name='ranking'),
    
    # =====================================
    # COTAÇÕES
    # =====================================
    path('cotacoes/', views.CotacaoListView.as_view(), name='cotacao_lista'),
    path('cotacoes/nova/', views.CotacaoCreateView.as_view(), name='cotacao_create'),
    path('cotacoes/<int:pk>/', views.CotacaoDetailView.as_view(), name='cotacao_detail'),
    path('cotacoes/<int:pk>/comparar/', views.CompararCotacaoView.as_view(), name='cotacao_comparar'),
    
    # =====================================
    # RELATÓRIOS
    # =====================================
    path('relatorios/', views.FornecedorRelatoriosView.as_view(), name='relatorios'),
    path('relatorios/compras/', views.RelatorioComprasView.as_view(), name='relatorio_compras'),
    path('relatorios/performance/', views.RelatorioPerformanceView.as_view(), name='relatorio_performance'),
    path('relatorios/pagamentos/', views.RelatorioPagamentosView.as_view(), name='relatorio_pagamentos'),
    
    # =====================================
    # IMPORTAÇÃO E EXPORTAÇÃO
    # =====================================
    path('importar/', views.ImportarFornecedoresView.as_view(), name='importar'),
    path('exportar/', views.ExportarFornecedoresView.as_view(), name='exportar'),
    
    # =====================================
    # AJAX E UTILITÁRIOS
    # =====================================
    path('ajax/buscar/', views.BuscarFornecedorAjaxView.as_view(), name='buscar_ajax'),
    path('ajax/validar-nif/', views.ValidarNifView.as_view(), name='validar_nif'),
    path('ajax/calcular-prazo/', views.CalcularPrazoEntregaView.as_view(), name='calcular_prazo'),
    
    # =====================================
    # COMUNICAÇÃO
    # =====================================
    path('<int:pk>/enviar-email/', views.EnviarEmailView.as_view(), name='enviar_email'),
    path('<int:pk>/whatsapp/', views.EnviarWhatsAppView.as_view(), name='enviar_whatsapp'),
    path('comunicacoes/', views.ComunicacaoListView.as_view(), name='comunicacao_lista'),
    
    # =====================================
    # API REST
    # =====================================
    
    # API Personalizada
    path('api/buscar-produtos/', views.BuscarProdutosFornecedorAPIView.as_view(), name='api_buscar_produtos'),
    path('api/calcular-frete/', views.CalcularFreteAPIView.as_view(), name='api_calcular_frete'),
]