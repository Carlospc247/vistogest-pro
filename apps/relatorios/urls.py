# apps/relatorios/urls.py
from django.urls import path, include
from apps.relatorios.relatorios import gerar_relatorio_corporativo
from . import views


app_name = 'relatorios'

urlpatterns = [
    # =====================================
    # DASHBOARD RELATÓRIOS
    # =====================================
    path('', views.RelatoriosDashboardView.as_view(), name='dashboard'),
    path('central/', views.CentralRelatoriosView.as_view(), name='central'),
    path('favoritos/', views.RelatoriosFavoritosView.as_view(), name='favoritos'),
    path('recentes/', views.RelatoriosRecentesView.as_view(), name='recentes'),
    
    # =====================================
    # CONSTRUTOR DE RELATÓRIOS
    # =====================================
    path('construtor/', views.ConstrutorRelatorioView.as_view(), name='construtor'),
    path('construtor/novo/', views.NovoRelatorioView.as_view(), name='novo_relatorio'),
    path('construtor/<int:pk>/editar/', views.EditarRelatorioView.as_view(), name='editar_relatorio'),
    path('construtor/campos/', views.CamposDisponiveisView.as_view(), name='campos_disponiveis'),
    
    # =====================================
    # TEMPLATES DE RELATÓRIOS
    # =====================================
    path('templates/', views.TemplateRelatorioListView.as_view(), name='template_lista'),
    path('templates/novo/', views.TemplateRelatorioCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/', views.TemplateRelatorioDetailView.as_view(), name='template_detail'),
    path('templates/<int:pk>/duplicar/', views.DuplicarTemplateView.as_view(), name='template_duplicar'),
    path('templates/<int:pk>/compartilhar/', views.CompartilharTemplateView.as_view(), name='template_compartilhar'),
    
    # =====================================
    # RELATÓRIOS DE VENDAS
    # =====================================
    path('vendas/', views.RelatoriosVendasView.as_view(), name='vendas'),
    path('vendas/diario/', views.RelatorioVendasDiarioView.as_view(), name='vendas_diario'),
    path('vendas/mensal/', views.RelatorioVendasMensalView.as_view(), name='vendas_mensal'),
    path('vendas/anual/', views.RelatorioVendasAnualView.as_view(), name='vendas_anual'),
    path('vendas/produto/', views.RelatorioVendasProdutoView.as_view(), name='vendas_produto'),
    path('vendas/categoria/', views.RelatorioVendasCategoriaView.as_view(), name='vendas_categoria'),
    path('vendas/vendedor/', views.RelatorioVendasVendedorView.as_view(), name='vendas_vendedor'),
    path('vendas/cliente/', views.RelatorioVendasClienteView.as_view(), name='vendas_cliente'),
    path('vendas/forma-pagamento/', views.RelatorioVendasFormaPagamentoView.as_view(), name='vendas_forma_pagamento'),
    
    # =====================================
    # RELATÓRIOS DE ESTOQUE
    # =====================================
    path('estoque/', views.RelatoriosEstoqueView.as_view(), name='estoque'),
    path('estoque/posicao/', views.RelatorioPosicaoEstoqueView.as_view(), name='estoque_posicao'),
    path('estoque/movimentacao/', views.RelatorioMovimentacaoEstoqueView.as_view(), name='estoque_movimentacao'),
    path('estoque/vencimentos/', views.RelatorioVencimentosView.as_view(), name='estoque_vencimentos'),
    path('estoque/ruptura/', views.RelatorioRupturaEstoqueView.as_view(), name='estoque_ruptura'),
    path('estoque/giro/', views.RelatorioGiroEstoqueView.as_view(), name='estoque_giro'),
    path('estoque/abc/', views.RelatorioABCView.as_view(), name='estoque_abc'),
    path('estoque/inventario/', views.RelatorioInventarioView.as_view(), name='estoque_inventario'),
    
    # =====================================
    # RELATÓRIOS FINANCEIROS
    # =====================================
    path('financeiro/', views.RelatoriosFinanceiroView.as_view(), name='financeiro'),
    path('financeiro/fluxo-caixa/', views.RelatorioFluxoCaixaView.as_view(), name='financeiro_fluxo_caixa'),
    path('financeiro/contas-receber/', views.RelatorioContasReceberView.as_view(), name='financeiro_contas_receber'),
    path('financeiro/contas-pagar/', views.RelatorioContasPagarView.as_view(), name='financeiro_contas_pagar'),
    path('financeiro/dre/', views.RelatorioDREView.as_view(), name='financeiro_dre'),
    path('financeiro/inadimplencia/', views.RelatorioInadimplenciaView.as_view(), name='financeiro_inadimplencia'),
    
    # =====================================
    # RELATÓRIOS DE CLIENTES
    # =====================================
    path('clientes/', views.RelatoriosClientesView.as_view(), name='clientes'),
    path('clientes/cadastros/', views.RelatorioCadastrosClientesView.as_view(), name='clientes_cadastros'),
    path('clientes/aniversariantes/', views.RelatorioAniversariantesView.as_view(), name='clientes_aniversariantes'),
    path('clientes/compras/', views.RelatorioComprasClientesView.as_view(), name='clientes_compras'),
    path('clientes/fidelidade/', views.RelatorioFidelidadeView.as_view(), name='clientes_fidelidade'),
    path('clientes/segmentacao/', views.RelatorioSegmentacaoView.as_view(), name='clientes_segmentacao'),
    
    # =====================================
    # RELATÓRIOS DE FUNCIONÁRIOS
    # =====================================
    path('funcionarios/', views.RelatoriosFuncionariosView.as_view(), name='funcionarios'),
    path('funcionarios/ponto/', views.RelatorioPontoView.as_view(), name='funcionarios_ponto'),
    path('funcionarios/folha/', views.RelatorioFolhaView.as_view(), name='funcionarios_folha'),
    path('funcionarios/ferias/', views.RelatorioFeriasView.as_view(), name='funcionarios_ferias'),
    path('funcionarios/treinamentos/', views.RelatorioTreinamentosView.as_view(), name='funcionarios_treinamentos'),
    path('funcionarios/performance/', views.RelatorioPerformanceView.as_view(), name='funcionarios_performance'),
    
    
    # =====================================
    # RELATÓRIOS DE FORNECEDORES
    # =====================================
    path('fornecedores/', views.RelatoriosFornecedoresView.as_view(), name='fornecedores'),
    path('fornecedores/compras/', views.RelatorioComprasView.as_view(), name='fornecedores_compras'),
    path('fornecedores/performance/', views.RelatorioPerformanceFornecedorView.as_view(), name='fornecedores_performance'),
    path('fornecedores/prazos/', views.RelatorioPrazosEntregaView.as_view(), name='fornecedores_prazos'),
    path('fornecedores/qualidade/', views.RelatorioQualidadeFornecedorView.as_view(), name='fornecedores_qualidade'),
    
    # =====================================
    # ANÁLISES E DASHBOARDS
    # =====================================
    path('analises/', views.AnalisesDashboardView.as_view(), name='analises'),
    path('analises/vendas/', views.AnaliseVendasView.as_view(), name='analises_vendas'),
    path('analises/lucratividade/', views.AnaliseLucratividadeView.as_view(), name='analises_lucratividade'),

    
    # =====================================
    # KPIs E INDICADORES
    # =====================================
    path('kpis/', views.KPIsDashboardView.as_view(), name='kpis'),
    path('kpis/vendas/', views.KPIsVendasView.as_view(), name='kpis_vendas'),
    path('kpis/financeiros/', views.KPIsFinanceirosView.as_view(), name='kpis_financeiros'),
    path('kpis/operacionais/', views.KPIsOperacionaisView.as_view(), name='kpis_operacionais'),
    path('kpis/personalizados/', views.KPIsPersonalizadosView.as_view(), name='kpis_personalizados'),
    
    # =====================================
    # RELATÓRIOS AGENDADOS
    # =====================================
    path('agendamentos/', views.AgendamentoListView.as_view(), name='agendamento_lista'),
    path('agendamentos/novo/', views.AgendamentoCreateView.as_view(), name='agendamento_create'),
    path('agendamentos/<int:pk>/', views.AgendamentoDetailView.as_view(), name='agendamento_detail'),
    path('agendamentos/<int:pk>/executar/', views.ExecutarAgendamentoView.as_view(), name='agendamento_executar'),
    path('agendamentos/<int:pk>/ativar/', views.AtivarAgendamentoView.as_view(), name='agendamento_ativar'),
    path('agendamentos/<int:pk>/desativar/', views.DesativarAgendamentoView.as_view(), name='agendamento_desativar'),
    
    # =====================================
    # DISTRIBUIÇÃO DE RELATÓRIOS
    # =====================================
    path('distribuicao/', views.DistribuicaoRelatoriosView.as_view(), name='distribuicao'),
    path('email/', views.EnvioEmailView.as_view(), name='envio_email'),
    path('impressao/', views.ImpressaoRelatoriosView.as_view(), name='impressao'),
    path('compartilhamento/', views.CompartilhamentoView.as_view(), name='compartilhamento'),
    
    # =====================================
    # HISTÓRICO E AUDITORIA
    # =====================================
    path('historico/', views.HistoricoRelatoriosView.as_view(), name='historico'),
    path('auditoria/', views.AuditoriaRelatoriosView.as_view(), name='auditoria'),
    path('logs/', views.LogsRelatoriosView.as_view(), name='logs'),
    path('acesso/', views.LogAcessoRelatoriosView.as_view(), name='log_acesso'),
    
    # =====================================
    # EXPORTAÇÃO EM DIVERSOS FORMATOS
    # =====================================
    path('<int:pk>/pdf/', views.ExportarPDFView.as_view(), name='exportar_pdf'),
    path('<int:pk>/excel/', views.ExportarExcelView.as_view(), name='exportar_excel'),
    path('<int:pk>/csv/', views.ExportarCSVView.as_view(), name='exportar_csv'),
    path('<int:pk>/xml/', views.ExportarXMLView.as_view(), name='exportar_xml'),
    path('<int:pk>/json/', views.ExportarJSONView.as_view(), name='exportar_json'),
    


    
    # =====================================
    # BUSINESS INTELLIGENCE
    # =====================================
    path('bi/', views.BusinessIntelligenceView.as_view(), name='bi'),
    path('bi/cubos/', views.CubosOLAPView.as_view(), name='bi_cubos'),
    path('bi/data-mining/', views.DataMiningView.as_view(), name='bi_data_mining'),
    path('bi/previsoes/', views.PrevisoesView.as_view(), name='bi_previsoes'),
    
    # =====================================
    # AJAX E UTILITÁRIOS
    # =====================================
    path('ajax/gerar/', views.GerarRelatorioAjaxView.as_view(), name='gerar_ajax'),
    path('ajax/preview/', views.PreviewRelatorioView.as_view(), name='preview'),
    path('ajax/validar-campos/', views.ValidarCamposView.as_view(), name='validar_campos'),
    path('ajax/buscar-dados/', views.BuscarDadosView.as_view(), name='buscar_dados'),
    
    # =====================================
    # CONFIGURAÇÕES
    # =====================================
    path('configuracoes/', views.ConfiguracoesRelatoriosView.as_view(), name='configuracoes'),
    path('configuracoes/formatos/', views.ConfiguracoesFormatosView.as_view(), name='configuracoes_formatos'),
    path('configuracoes/permissoes/', views.ConfiguracoesPermissoesView.as_view(), name='configuracoes_permissoes'),
    
    # =====================================
    # API REST
    # =====================================
    
    # API Personalizada
    path('api/gerar-relatorio/', views.GerarRelatorioAPIView.as_view(), name='api_gerar_relatorio'),
    path('api/dados-grafico/', views.DadosGraficoAPIView.as_view(), name='api_dados_grafico'),
    path('api/estatisticas/', views.EstatisticasAPIView.as_view(), name='api_estatisticas'),

    path("relatorio-corporativo/", gerar_relatorio_corporativo, name="relatorio_corporativo"),
]