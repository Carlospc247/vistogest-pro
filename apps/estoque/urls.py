# apps/estoque/urls.py
from django.urls import path, include
from . import views
from .views import EntradaDiretaProdutoView, EntradaEstoqueView, SaidaEstoqueView, AjusteEstoqueView, PerdaEstoqueView

# API Router

app_name = 'estoque'

urlpatterns = [
    # =====================================
    # DASHBOARD E VISÃO GERAL
    # =====================================
    path('', views.EstoqueDashboardView.as_view(), name='dashboard'),
    path('lista/', views.EstoqueListView.as_view(), name='lista'),
    
    
    # =====================================
    # MOVIMENTAÇÕES
    # =====================================
    path('movimentacoes/', views.MovimentacaoListView.as_view(), name='movimentacao_lista'),
    path('movimentacoes/nova/', views.MovimentacaoCreateView.as_view(), name='movimentacao_create'),
    path('movimentacoes/<int:pk>/', views.MovimentacaoUpdateView.as_view(), name='movimentacao_update'),
    path('movimentacoes/<int:pk>/', views.MovimentacaoDetailView.as_view(), name='movimentacao_detail'),
    path('movimentacoes/<int:pk>/estornar/', views.EstornarMovimentacaoView.as_view(), name='movimentacao_estornar'),
    
    # Tipos específicos de movimentação
    path('entrada/', views.EntradaEstoqueView.as_view(), name='entrada'),
    path('saida/', views.SaidaEstoqueView.as_view(), name='saida'),
    path('ajuste/', views.AjusteEstoqueView.as_view(), name='ajuste'),
    path('perda/', views.PerdaEstoqueView.as_view(), name='perda'),


    path('entrada/<int:pk>/', EntradaDiretaProdutoView.as_view(), name='entrada_produto'),
    path('entrada/', EntradaEstoqueView.as_view(), name='entrada'),
    path('saida/', SaidaEstoqueView.as_view(), name='saida'),
    path('ajuste/', AjusteEstoqueView.as_view(), name='ajuste'),
    path('perda/', views.PerdaEstoqueView.as_view(), name='perda'),
    
    # =====================================
    # TRANSFERÊNCIAS ENTRE LOJAS
    # =====================================
    path('transferencias/', views.TransferenciaListView.as_view(), name='transferencia_lista'),
    path('transferencias/nova/', views.TransferenciaCreateView.as_view(), name='transferencia_create'),
    path('transferencias/<int:pk>/', views.TransferenciaDetailView.as_view(), name='transferencia_detail'),
    path('transferencias/<int:pk>/aprovar/', views.AprovarTransferenciaView.as_view(), name='transferencia_aprovar'),
    path('transferencias/<int:pk>/enviar/', views.EnviarTransferenciaView.as_view(), name='transferencia_enviar'),
    path('transferencias/<int:pk>/receber/', views.ReceberTransferenciaView.as_view(), name='transferencia_receber'),
    path('transferencias/<int:pk>/cancelar/', views.CancelarTransferenciaView.as_view(), name='transferencia_cancelar'),
    
    # =====================================
    # INVENTÁRIOS
    # =====================================
    path('inventarios/', views.InventarioListView.as_view(), name='inventario_lista'),
    path('inventarios/novo/', views.InventarioCreateView.as_view(), name='inventario_create'),
    path('inventarios/<int:pk>/', views.InventarioDetailView.as_view(), name='inventario_detail'),
    path('inventarios/<int:pk>/finalizar/', views.FinalizarInventarioView.as_view(), name='inventario_finalizar'),
    path('inventarios/<int:pk>/gerar-ajustes/', views.GerarAjustesInventarioView.as_view(), name='inventario_gerar_ajustes'),

    path('inventarios/<int:pk>/iniciar/', views.IniciarInventarioView.as_view(), name='inventario_iniciar'),
    
    # =====================================
    # CONTROLE DE VENCIMENTOS
    # =====================================
    path('vencimentos/', views.VencimentosView.as_view(), name='vencimentos'),
    path('vencimentos/proximos/', views.ProximosVencimentosView.as_view(), name='proximos_vencimentos'),
    path('vencimentos/vencidos/', views.VencidosView.as_view(), name='vencidos'),
    path('vencimentos/descarte/', views.DescarteView.as_view(), name='descarte'),
    
    # =====================================
    # ALERTAS E REPOSIÇÃO
    # =====================================
    path('alertas/', views.AlertasEstoqueView.as_view(), name='alertas'),
    path('estoque-minimo/', views.EstoqueMinimoView.as_view(), name='estoque_minimo'),
    path('sugestao-compra/', views.SugestaoCompraView.as_view(), name='sugestao_compra'),
    path('ruptura/', views.RupturaEstoqueView.as_view(), name='ruptura'),
    
    # =====================================
    # LOCALIZAÇÃO E ENDEREÇAMENTO
    # =====================================
    path('localizacoes/', views.LocalizacaoListView.as_view(), name='localizacao_lista'),
    path('localizacoes/nova/', views.LocalizacaoCreateView.as_view(), name='localizacao_create'),
    path('localizacoes/<int:pk>/editar/', views.LocalizacaoUpdateView.as_view(), name='localizacao_update'),
    path('enderecamento/', views.EnderecamentoView.as_view(), name='enderecamento'),
    
    # =====================================
    # RELATÓRIOS
    # =====================================
    path('relatorios/', views.EstoqueRelatoriosView.as_view(), name='relatorios'),
    path('relatorios/posicao/', views.RelatorioPosicaoEstoqueView.as_view(), name='relatorio_posicao'),
    path('relatorios/movimentacao/', views.RelatorioMovimentacaoView.as_view(), name='relatorio_movimentacao'),
    path('relatorios/abc/', views.RelatorioABCView.as_view(), name='relatorio_abc'),
    path('relatorios/giro/', views.RelatorioGiroView.as_view(), name='relatorio_giro'),
    
    # =====================================
    # CÓDIGO DE BARRAS E ETIQUETAS
    # =====================================
    path('codigo-barras/', views.CodigoBarrasView.as_view(), name='codigo_barras'),
    path('etiquetas/', views.EtiquetasView.as_view(), name='etiquetas'),
    path('imprimir-etiquetas/', views.ImprimirEtiquetasView.as_view(), name='imprimir_etiquetas'),
    
    # =====================================
    # LEITURA POR SCANNER
    # =====================================
    path('scanner/', views.ScannerView.as_view(), name='scanner'),
    path('conferencia/', views.ConferenciaView.as_view(), name='conferencia'),
    path('coleta/', views.ColetaView.as_view(), name='coleta'),
    
    # =====================================
    # IMPORTAÇÃO E EXPORTAÇÃO
    # =====================================
    path('importar/', views.ImportarEstoqueView.as_view(), name='importar'),
    path('exportar/', views.ExportarEstoqueView.as_view(), name='exportar'),
    
    # =====================================
    # AJAX E UTILITÁRIOS
    # =====================================
    path('ajax/consultar-estoque/', views.ConsultarEstoqueAjaxView.as_view(), name='consultar_estoque_ajax'),
    path('ajax/reservar/', views.ReservarEstoqueView.as_view(), name='reservar_estoque'),
    path('ajax/liberar-reserva/', views.LiberarReservaView.as_view(), name='liberar_reserva'),
    path('ajax/sugerir-localizacao/', views.SugerirLocalizacaoView.as_view(), name='sugerir_localizacao'),
    
    # =====================================
    # CONFIGURAÇÕES
    # =====================================
    path('configuracoes/', views.ConfiguracoesEstoqueView.as_view(), name='configuracoes'),
    path('parametros/', views.ParametrosEstoqueView.as_view(), name='parametros'),
    
    # =====================================
    # API REST
    # =====================================
   
    # API Personalizada
    path('api/saldo-atual/', views.SaldoAtualAPIView.as_view(), name='api_saldo_atual'),
    path('api/historico-movimentacao/', views.HistoricoMovimentacaoAPIView.as_view(), name='api_historico_movimentacao'),
    path('api/validar-lote/', views.ValidarLoteAPIView.as_view(), name='api_validar_lote'),



    
    path('entrada/<int:pk>/', views.EntradaDiretaProdutoView.as_view(), name='entrada_produto'),

   

]
