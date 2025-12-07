# apps/vendas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .api import viewsets

# API Router (DRF) - Configuração para ViewSets
router = DefaultRouter()
router.register(r'vendas', views.VendaViewSet, basename='vendas')
router.register(r'itens', viewsets.ItemVendaViewSet)
router.register(r'pagamentos', viewsets.PagamentoViewSet)


app_name = 'vendas'

urlpatterns = [
    # =====================================
    # 1. GESTÃO DE VENDAS (VISTAS HTML)
    # =====================================
    
    path('vendas/', views.VendasView.as_view(), name='lista'),
    path('pdv/', views.PDVView.as_view(), name='pdv'),
    path('nova/', views.VendaCreateView.as_view(), name='create'),
    path('<int:pk>/', views.VendaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.VendaUpdateView.as_view(), name='update'),
    path('<int:pk>/cancelar/', views.CancelarVendaView.as_view(), name='cancelar'),
    
    # =====================================
    # 2. PAGAMENTOS E ESTORNOS
    # =====================================
    path('<int:venda_pk>/pagamentos/', views.PagamentoListView.as_view(), name='pagamento_lista'),
    path('<int:venda_pk>/pagamentos/novo/', views.PagamentoCreateView.as_view(), name='pagamento_create'),
    path('pagamentos/<int:pk>/', views.PagamentoDetailView.as_view(), name='pagamento_detail'),
    path('pagamentos/<int:pk>/estornar/', views.EstornarPagamentoView.as_view(), name='pagamento_estornar'),
    # Tipos específicos de pagamento
    path('pagamentos/cartao/', views.PagamentoCartaoView.as_view(), name='pagamento_cartao'),
    path('pagamentos/convenio/', views.PagamentoConvenioView.as_view(), name='pagamento_convenio'),
    path('pagamentos/crediario/', views.PagamentoCrediarioView.as_view(), name='pagamento_crediario'),
    
    # =====================================
    # 3. ORÇAMENTOS
    # =====================================
    path('orcamentos/', views.OrcamentoListView.as_view(), name='orcamento_lista'),
    path('orcamentos/novo/', views.OrcamentoCreateView.as_view(), name='orcamento_create'),
    path('orcamentos/<int:pk>/', views.OrcamentoDetailView.as_view(), name='orcamento_detail'),
    path('orcamentos/<int:pk>/editar/', views.OrcamentoUpdateView.as_view(), name='orcamento_update'),
    path('orcamentos/<int:pk>/excluir/', views.OrcamentoDeleteView.as_view(), name='orcamento_delete'),
    path("orcamentos/<int:pk>/converter/", views.OrcamentoConverterView.as_view(), name="orcamento_converter"),
    
    # =====================================
    # 4. DEVOLUÇÕES
    # =====================================
    path('devolucoes/', views.DevolucaoListView.as_view(), name='devolucao_lista'),
    path('<int:pk>/devolver/', views.DevolucaoVendaView.as_view(), name='devolucao'),
    path('devolucoes/<int:pk>/', views.DevolucaoDetailView.as_view(), name='devolucao_detail'),

    # =====================================
    # 5. DELIVERY E ENTREGAS
    # =====================================
    path('delivery/', views.DeliveryListView.as_view(), name='delivery_lista'),
    path('<int:pk>/agendar-entrega/', views.AgendarEntregaView.as_view(), name='agendar_entrega'),
    path('entregas/', views.EntregaListView.as_view(), name='entrega_lista'),
    path('entregas/<int:pk>/confirmar/', views.ConfirmarEntregaView.as_view(), name='confirmar_entrega'),
    path('rotas/', views.RotaEntregaView.as_view(), name='rota_entrega'),
    
    # =====================================
    # 6. CONVÊNIOS E GESTÃO FINANCEIRA
    # =====================================
    path('convenios/', views.ConvenioListView.as_view(), name='convenio_lista'),
    path('convenios/novo/', views.ConvenioCreateView.as_view(), name='convenio_create'),
    path('convenios/<int:pk>/', views.ConvenioDetailView.as_view(), name='convenio_detail'),
    path('convenios/<int:pk>/faturar/', views.FaturarConvenioView.as_view(), name='convenio_faturar'),
    path('contas-receber/', views.contas_receber, name='contas_receber'),
    
    # =====================================
    # 7. ANÁLISES E DASHBOARDS
    # =====================================
    path('dashboard/', views.VendaDashboardView.as_view(), name='dashboard'),
    path('analytics/', views.VendaAnalyticsView.as_view(), name='analytics'),
    path('kpis/', views.VendaKPIsView.as_view(), name='kpis'),
    path('metas/', views.MetasVendaView.as_view(), name='metas'),
    path('comissoes/', views.ComissaoListView.as_view(), name='comissao_lista'),
    path('comissoes/calcular/', views.CalcularComissaoView.as_view(), name='calcular_comissao'),
    path('comissoes/pagar/', views.PagarComissaoView.as_view(), name='pagar_comissao'),
    
    # API de B.I. (NOVA)
    path('v1/relatorios/rentabilidade/', views.RentabilidadeAPIView.as_view(), name='rentabilidade-api'),
    
    # =====================================
    # 8. GESTÃO DE DOCUMENTOS (LISTAS)
    # =====================================
    path('documentos/dashboard/', views.documentos_dashboard_view, name='documentos_dashboard'),
    path('vendas/lista/', views.vendas_lista, name='vendas_lista'),
    path('faturas-recibo/', views.faturas_recibo_lista, name='faturas_recibo_lista'),
    path('faturas-credito/', views.faturas_credito_lista, name='faturas_credito_lista'),
    path('recibos/', views.recibos_lista, name='recibos_lista'),
    path('proformas/', views.proformas_lista, name='proformas_lista'),
    
    # =====================================
    # 9. ROTAS ESPECÍFICAS DE DOCUMENTOS (CRIAÇÃO)
    # =====================================
    path('fatura-credito/nova/', views.nova_fatura_credito, name='nova_fatura_credito'),
    path('proforma/nova/', views.nova_proforma, name='nova_proforma'),
    
    # =====================================
    # 10. APIs PERSONALIZADAS (AÇÕES E UTILITÁRIOS)
    # =====================================
    # APIs de Ação
    path('api/vendas/finalizar/', views.finalizar_venda_api, name='api_finalizar_venda'),
    path('api/cancelar-venda/', views.CancelarVendaAPIView.as_view(), name='api_cancelar_venda'),
    path('api/finalizar-fatura-credito/', views.finalizar_fatura_credito_api, name='api_finalizar_fatura_credito'),
    path('api/finalizar-proforma/', views.finalizar_proforma_api, name='api_finalizar_proforma'),
    path('api/abrir-gaveta/', views.AbrirGavetaApiView.as_view(), name='api_abrir_gaveta'),
    
    # APIs de Consulta/Utilidade
    path('api/consultar-preco/', views.ConsultarPrecoAPIView.as_view(), name='api_consultar_preco'),
    path('api/aplicar-desconto/', views.AplicarDescontoAPIView.as_view(), name='api_aplicar_desconto'),
    path('api/formas-pagamento/', views.formas_pagamento_api, name='api_formas_pagamento'),
    path('api/atualizar-observacoes/<int:venda_id>/', views.atualizar_observacoes_venda, name='atualizar_observacoes'),
    
    # APIs/Views de Cálculo AJAX
    path('ajax/calcular-desconto/', views.CalcularDescontoView.as_view(), name='calcular_desconto'),
    path('ajax/verificar-estoque/', views.VerificarEstoqueVendaView.as_view(), name='verificar_estoque'),
    path('ajax/calcular-troco/', views.CalcularTrocoView.as_view(), name='calcular_troco'),
    
    # =====================================
    # 11. APIs DE DOCUMENTOS (PDF)
    # =====================================
    path('api/fatura/<int:venda_id>/<str:tipo>/', views.fatura_pdf_view, name='fatura_pdf_view'),
    path('api/fatura-credito/<int:fatura_id>/<str:tipo>/', views.fatura_credito_pdf_view, name='fatura_credito_pdf_view'),
    path('fatura/<int:venda_id>/pdf/', views.fatura_pdf_view, {'tipo': 'a4'}, name='fatura_pdf'),
    path('recibo/<int:recibo_id>/pdf/', views.recibo_pdf_view, name='recibo_pdf'),
    path('proforma/<int:proforma_id>/pdf/', views.proforma_pdf_view, name='proforma_pdf'),
    path('api/liquidar-fatura/<int:fatura_id>/', views.liquidar_fatura_api, name='liquidar_fatura_api'),
    
    path('api/converter-proforma/<int:proforma_id>/', views.converter_proforma_api, name='converter_proforma'),
    path('api/atualizar-status-proforma/<int:proforma_id>/', views.atualizar_status_proforma_api, name='atualizar_status_proforma'),

    # =====================================
    # 12. API REST ROUTER (DRF)
    # Esta rota deve ser a ÚLTIMA API para evitar conflitos
    # =====================================
    path('api/', include(router.urls)),
    #path('', include('apps.vendas.urls_documentos')),
    path('', include('apps.vendas.urls_documentos', namespace='vendas_documentos')),

    path('notas-credito/', views.NotaCreditoListView.as_view(), name='nota_credito_lista'),
    path('notas-credito/nova/', views.NotaCreditoCreateView.as_view(), name='nota_credito_create'),
    path('notas-credito/<int:pk>/', views.NotaCreditoDetailView.as_view(), name='nota_credito_detail'),
    path('notas-credito/<int:pk>/editar/', views.NotaCreditoUpdateView.as_view(), name='nota_credito_update'),
    path('notas-credito/<int:pk>/aplicar/', views.AplicarNotaCreditoView.as_view(), name='aplicar_nota_credito'),
    path('notas-credito/<int:pk>/aprovar/', views.AprovarNotaCreditoView.as_view(), name='aprovar_nota_credito'),
    path('notas-credito/<int:nota_id>/pdf/', views.nota_credito_pdf_view, name='nota_credito_pdf'),
    
    # =====================================
    # NOTAS DE DÉBITO
    # =====================================
    path('notas-debito/', views.NotaDebitoListView.as_view(), name='nota_debito_lista'),
    path('notas-debito/nova/', views.NotaDebitoCreateView.as_view(), name='nota_debito_create'),
    path('notas-debito/<int:pk>/', views.NotaDebitoDetailView.as_view(), name='nota_debito_detail'),
    path('notas-debito/<int:pk>/editar/', views.NotaDebitoUpdateView.as_view(), name='nota_debito_update'),
    path('notas-debito/<int:pk>/aplicar/', views.AplicarNotaDebitoView.as_view(), name='aplicar_nota_debito'),
    path('notas-debito/<int:pk>/aprovar/', views.AprovarNotaDebitoView.as_view(), name='aprovar_nota_debito'),
    path('notas-debito/<int:nota_id>/pdf/', views.nota_debito_pdf_view, name='nota_debito_pdf'),
    
    # =====================================
    # DOCUMENTOS DE TRANSPORTE
    # =====================================
    path('documentos-transporte/', views.DocumentoTransporteListView.as_view(), name='documento_transporte_lista'),
    path('documentos-transporte/novo/', views.DocumentoTransporteCreateView.as_view(), name='documento_transporte_create'),
    path('documentos-transporte/<int:pk>/', views.DocumentoTransporteDetailView.as_view(), name='documento_transporte_detail'),
    path('documentos-transporte/<int:pk>/editar/', views.DocumentoTransporteUpdateView.as_view(), name='documento_transporte_update'),
    path('documentos-transporte/<int:pk>/iniciar/', views.IniciarTransporteView.as_view(), name='iniciar_transporte'),
    path('documentos-transporte/<int:pk>/confirmar-entrega/', views.ConfirmarEntregaView.as_view(), name='confirmar_entrega'),
    path('documentos-transporte/<int:documento_id>/pdf/', views.documento_transporte_pdf_view, name='documento_transporte_pdf'),
    
    # =====================================
    # DASHBOARDS E RELATÓRIOS
    # =====================================
    path('analytics/documentos-fiscais/', views.DocumentosFiscaisAnalyticsView.as_view(), name='documentos_fiscais_analytics'),
    path('relatorios/notas-credito/', views.RelatorioNotasCreditoView.as_view(), name='relatorio_notas_credito'),
    path('relatorios/transportes/', views.RelatorioTransportesView.as_view(), name='relatorio_transportes'),
    
    # =====================================
    # APIs
    # =====================================
    path('api/finalizar-nota-credito/', views.finalizar_nota_credito_api, name='finalizar_nota_credito_api'),
    path('api/finalizar-nota-debito/', views.finalizar_nota_debito_api, name='finalizar_nota_debito_api'),
    path('api/finalizar-documento-transporte/', views.finalizar_documento_transporte_api, name='finalizar_documento_transporte_api'),
    path('api/buscar-documentos-origem/', views.buscar_documentos_origem_api, name='buscar_documentos_origem_api'),

    # Adicionar no final do arquivo apps/vendas/urls_documentos.py:

    # APIs para gestão de itens
    path('api/adicionar-item-nc/', views.adicionar_item_nota_credito_api, name='adicionar_item_nota_credito_api'),
    path('api/adicionar-item-nd/', views.adicionar_item_nota_debito_api, name='adicionar_item_nota_debito_api'),
    path('api/adicionar-item-gt/', views.adicionar_item_documento_transporte_api, name='adicionar_item_documento_transporte_api'),
    path('api/remover-item-nc/<int:item_id>/', views.remover_item_nota_credito_api, name='remover_item_nota_credito_api'),
    path('api/remover-item-nd/<int:item_id>/', views.remover_item_nota_debito_api, name='remover_item_nota_debito_api'),
    path('api/remover-item-gt/<int:item_id>/', views.remover_item_documento_transporte_api, name='remover_item_documento_transporte_api'),
    
    # APIs de busca
    path('api/buscar-produtos/', views.buscar_produtos_api, name='buscar_produtos_api'),
    path('api/buscar-servicos/', views.buscar_servicos_api, name='buscar_servicos_api'),
    path('api/buscar-clientes/', views.buscar_clientes_api, name='buscar_clientes_api'),
    path('api/estatisticas-rapidas/', views.estatisticas_rapidas_api, name='estatisticas_rapidas_api'),
]

    
