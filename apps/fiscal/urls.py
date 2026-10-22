# apps/fiscal/urls.py
"""URLs fiscais.

As páginas com isolamento por tenant apontam para web_views; API DRF usa os
ViewSets tenant-aware. Os endpoints legados de homologação, downloads e AJAX
continuam disponíveis para compatibilidade.
"""
from django.conf import settings
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.fiscal import views_erro_agt
from . import api_viewsets, views, views_integracoes, web_views

app_name = "fiscal"

router = DefaultRouter()
router.register(r"taxas-iva", api_viewsets.TaxaIVAAGTViewSet, basename="taxas-iva")
router.register(r"assinatura-digital", api_viewsets.AssinaturaDigitalViewSet, basename="assinatura-digital")
router.register(r"retencoes-fonte", api_viewsets.RetencaoFonteViewSet, basename="retencoes-fonte")
router.register(r"documentos-fiscais", api_viewsets.DocumentoFiscalViewSet, basename="documentos-fiscais")

# API endpoints específicos precedem o router para tornar os nomes inequívocos.
api_urlpatterns = [
    path("api/saft/export/", views.SAFTExportView.as_view(), name="saft-export"),
    path("api/dashboard/", api_viewsets.FiscalDashboardAPIView.as_view(), name="fiscal-dashboard"),
    path("api/validar-documento/", views.ValidarDocumentoView.as_view(), name="validar-documento"),
    path("api/verificar-integridade/", views.verificar_integridade_hash, name="verificar-integridade"),
    path("api/taxas-iva/ativas/", api_viewsets.TaxaIVAAGTViewSet.as_view({"get": "ativas"}), name="taxas-iva-ativas"),
    path("api/taxas-iva/export-saft/", api_viewsets.TaxaIVAAGTViewSet.as_view({"get": "export_saft"}), name="taxas-iva-export-saft"),
    path("api/taxas-iva/<int:pk>/calcular/", api_viewsets.TaxaIVAAGTViewSet.as_view({"post": "calcular_iva"}), name="taxas-iva-calcular"),
    path("api/assinatura/configurar-chave/", api_viewsets.AssinaturaDigitalViewSet.as_view({"post": "configurar_chave"}), name="assinatura-configurar-chave"),
    path("api/assinatura/assinar-documento/", api_viewsets.AssinaturaDigitalViewSet.as_view({"post": "assinar_documento"}), name="assinatura-assinar"),
    path("api/assinatura/status-cadeia/", api_viewsets.AssinaturaDigitalViewSet.as_view({"get": "status_cadeia"}), name="assinatura-status"),
    path("api/retencoes/relatorio-mensal/", api_viewsets.RetencaoFonteViewSet.as_view({"get": "relatorio_mensal"}), name="retencoes-relatorio-mensal"),
    path("api/retencoes/<int:pk>/marcar-paga/", api_viewsets.RetencaoFonteViewSet.as_view({"post": "marcar_paga"}), name="retencoes-marcar-paga"),
    # Mantém os endpoints padrão do router efectivamente montados.
    path("api/", include(router.urls)),
]

web_urlpatterns = [
    # Dashboard e documentos fiscais: implementação tenant-aware.
    path("", web_views.FiscalDashboardView.as_view(), name="dashboard"),
    path("documentos/", web_views.DocumentoFiscalListView.as_view(), name="documentos"),
    path("documentos/novo/", web_views.DocumentoFiscalCreateView.as_view(), name="documento_novo"),
    path("documentos/<int:pk>/", web_views.DocumentoFiscalDetailView.as_view(), name="documento_detalhe"),
    path("documentos/<int:pk>/editar/", web_views.DocumentoFiscalUpdateView.as_view(), name="documento_editar"),

    # Homologação AGT; os subfluxos legados continuam em views.py.
    path("homologacao/", web_views.HomologacaoDashboardView.as_view(), name="homologacao"),
    path("homologacao/", web_views.HomologacaoDashboardView.as_view(), name="homologacao-dashboard"),
    path("homologacao/gerar/", views.HomologacaoGerarView.as_view(), name="homologacao-gerar"),
    path("homologacao/gerar/<str:ponto>/", views.HomologacaoGerarPontoView.as_view(), name="homologacao-gerar-ponto"),
    path("homologacao/saft/", views.HomologacaoGerarSaftView.as_view(), name="homologacao-saft"),
    path("homologacao/download-saft/", views.HomologacaoDownloadSaftView.as_view(), name="homologacao-download-saft"),
    path("homologacao/pdf/<str:numero_documento>/", views.HomologacaoPdfView.as_view(), name="homologacao-pdf"),

    # Taxas de imposto. Os aliases preservam reverse() de versões anteriores.
    path("taxas-iva/", web_views.TaxaIVAListView.as_view(), name="taxas_iva"),
    path("taxas-iva/", web_views.TaxaIVAListView.as_view(), name="taxas-iva-list"),
    path("taxas-iva/nova/", web_views.TaxaIVACreateView.as_view(), name="taxa_iva_nova"),
    path("taxas-iva/nova/", web_views.TaxaIVACreateView.as_view(), name="taxas-iva-create"),
    path("taxas-iva/<int:pk>/editar/", web_views.TaxaIVAUpdateView.as_view(), name="taxa_iva_editar"),
    path("taxas-iva/<int:pk>/editar/", web_views.TaxaIVAUpdateView.as_view(), name="taxas-iva-update"),
    path("taxas-iva/<int:pk>/", web_views.TaxaIVADetailView.as_view(), name="taxas-iva-detail"),
    path("taxas-iva/<int:pk>/deletar/", web_views.TaxaIVADeleteView.as_view(), name="taxas-iva-delete"),

    # Assinatura digital. A configuração dos dados AGT não gera chaves novas.
    path("assinatura/", web_views.AssinaturaDigitalConfigView.as_view(), name="assinatura-digital"),
    path("assinatura-digital/", web_views.AssinaturaDigitalConfigView.as_view(), name="assinatura_digital"),
    path("assinatura/configurar/", views.AssinaturaConfigurarChaveContribuinteView.as_view(), name="assinatura-configurar"),
    # Rota antiga preservada apenas para compatibilidade com clientes existentes.
    path("assinatura/gerar-chaves/", views.AssinaturaGerarChavesView.as_view(), name="assinatura-gerar-chaves-web"),

    # Retenções. As vistas principais usam campos reais e respeitam o tenant.
    path("retencoes/", web_views.RetencaoFonteListView.as_view(), name="retencoes"),
    path("retencoes/", web_views.RetencaoFonteListView.as_view(), name="retencoes-list"),
    path("retencoes/nova/", web_views.RetencaoFonteCreateView.as_view(), name="retencao_nova"),
    path("retencoes/nova/", web_views.RetencaoFonteCreateView.as_view(), name="retencoes-create"),
    path("retencoes/<int:pk>/editar/", web_views.RetencaoFonteUpdateView.as_view(), name="retencao_editar"),
    path("retencoes/<int:pk>/editar/", web_views.RetencaoFonteUpdateView.as_view(), name="retencoes-update"),
    path("retencoes/<int:pk>/", web_views.RetencaoFonteDetailView.as_view(), name="retencoes-detail"),
    path("retencoes/<int:pk>/deletar/", web_views.RetencaoFonteDeleteView.as_view(), name="retencoes-delete"),
    path("retencoes/<int:pk>/pagar/", web_views.RetencaoMarcarPagaView.as_view(), name="retencoes-pagar"),

    # Relatórios e exportação fiscal.
    path("relatorios/", web_views.RelatoriosFiscaisView.as_view(), name="relatorios"),
    path("relatorios/retencoes/", views.RelatorioRetencoesView.as_view(), name="relatorio-retencoes"),
    path("relatorios/taxas-iva/", views.RelatorioTaxasIVAView.as_view(), name="relatorio-taxas-iva"),
    path("saft/", views.SAFTView.as_view(), name="saft"),
    path("saft/exportar/", web_views.SAFTExportWebView.as_view(), name="saft_exportar"),
    path("saft/exportar/", web_views.SAFTExportWebView.as_view(), name="saft-export-web"),
    path("saft/validar/", views.SAFTValidarXSDView.as_view(), name="saft-validar-xsd"),
    path("saft/historico/", views.SAFTHistoricoView.as_view(), name="saft-historico"),

    # Validação e integridade.
    path("validacao/", web_views.ValidacaoFiscalView.as_view(), name="validacao"),
    path("validacoes/", views.ValidacoesView.as_view(), name="validacoes"),
    path("validacoes/documentos/", views.ValidarDocumentosView.as_view(), name="validar-documentos-web"),
    path("validacoes/integridade/", web_views.VerificarIntegridadeView.as_view(), name="verificar-integridade-web"),
    path("integridade/", web_views.VerificarIntegridadeView.as_view(), name="integridade"),

    # Configurações legadas específicas mantidas, página principal protegida.
    path("configuracoes/", web_views.ConfiguracoesFiscalView.as_view(), name="configuracoes"),
    path("configuracoes/empresa/", views.ConfiguracaoEmpresaView.as_view(), name="configuracao-empresa"),
    path("configuracoes/backup/", views.BackupFiscalView.as_view(), name="backup-fiscal"),

    # Downloads de chave pública/PDFs para submissão à AGT.
    path("assinatura/baixar-publica/", views.baixar_chave_publica, name="baixar_chave_publica"),
    path("assinatura/pdf-submissao/", views.baixar_pdf_submissao, name="baixar_pdf_submissao"),
    path("assinatura/download-pdf-agt/", views.download_pdf_agt, name="download_pdf_agt"),
]

ajax_urlpatterns = [
    path("ajax/calcular-iva/", views.ajax_calcular_iva, name="ajax-calcular-iva"),
    path("ajax/buscar-fornecedores/", views.ajax_buscar_fornecedores, name="ajax-buscar-fornecedores"),
    path("ajax/validar-nif/", views.ajax_validar_nif, name="ajax-validar-nif"),
    path("ajax/gerar-hash/", views.ajax_gerar_hash, name="ajax-gerar-hash"),
    path("ajax/venda/<int:venda_id>/erros/", views_erro_agt.detalhe_erro_venda, name="ajax-venda-erros"),
    path("ajax/dados-dashboard/", views.ajax_dados_dashboard, name="ajax-dados-dashboard"),
    path("ajax/metricas-periodo/", views.ajax_metricas_periodo, name="ajax-metricas-periodo"),
    path("ajax/graf-retencoes/", views.ajax_grafico_retencoes, name="ajax-graf-retencoes"),
    path("ajax/verificar-documento/", views.ajax_verificar_documento, name="ajax-verificar-documento"),
    path("ajax/status-assinatura/", views.ajax_status_assinatura, name="ajax-status-assinatura"),
    path("ajax/testar-assinatura/", views.ajax_testar_assinatura, name="ajax-testar-assinatura"),
]

download_urlpatterns = [
    path("download/relatorio-retencoes/<str:formato>/", views.DownloadRelatorioRetencoesView.as_view(), name="download-relatorio-retencoes"),
    path("download/relatorio-taxas/<str:formato>/", views.DownloadRelatorioTaxasView.as_view(), name="download-relatorio-taxas"),
    path("download/dashboard-pdf/", views.DownloadDashboardPDFView.as_view(), name="download-dashboard-pdf"),
    path("download/saft/<int:export_id>/", views.DownloadSAFTFileView.as_view(), name="download-saft-file"),
    path("download/saft-backup/", views.DownloadSAFTBackupView.as_view(), name="download-saft-backup"),
    path("download/template-retencoes/", views.DownloadTemplateRetencoesView.as_view(), name="download-template-retencoes"),
    path("download/exemplo-saft/", views.DownloadExemploSAFTView.as_view(), name="download-exemplo-saft"),
    path("download/chave-publica/", views.DownloadChavePublicaView.as_view(), name="download-chave-publica"),
]

webhook_urlpatterns = [
    path("webhook/agt-notification/", views_integracoes.webhook_agt_notification, name="webhook-agt"),
]

urlpatterns = [*api_urlpatterns, *web_urlpatterns, *ajax_urlpatterns, *download_urlpatterns, *webhook_urlpatterns]

if settings.DEBUG:
    urlpatterns += [
        path("debug/limpar-cache/", views.debug_limpar_cache, name="debug-limpar-cache"),
        path("debug/info-sistema/", views.debug_info_sistema, name="debug-info-sistema"),
    ]
