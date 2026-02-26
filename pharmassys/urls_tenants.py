print(">>> CARREGANDO URLS DO TENANT")
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.generic import RedirectView

# Registrar core com namespace para que login/dashboard funcione
urlpatterns = [
    # Redireciona '' para login por padrão
    path('', RedirectView.as_view(pattern_name='core:login', permanent=False)),

    # Apps Core (Dashboard, login, logout, etc.)
    path('', include(('apps.core.urls', 'core'), namespace='core')),

    # Módulos do ERP/Vistogest
    path('vendas/', include(('apps.vendas.urls', 'vendas'), namespace='vendas')),
    path('produtos/', include('apps.produtos.urls', namespace='produtos')),
    path('clientes/', include('apps.clientes.urls', namespace='clientes')),
    path('estoque/', include('apps.estoque.urls', namespace='estoque')),
    path('fornecedores/', include('apps.fornecedores.urls', namespace='fornecedores')),
    path('funcionarios/', include('apps.funcionarios.urls', namespace='funcionarios')),
    path('financeiro/', include('apps.financeiro.urls', namespace='financeiro')),
    path('servicos/', include('apps.servicos.urls', namespace='servicos')),
    path('configuracoes/', include('apps.configuracoes.urls', namespace='configuracoes')),
    path('analytics/', include('apps.analytics.urls', namespace='analytics')),
    path('relatorios/', include('apps.relatorios.urls', namespace='relatorios')),
    path('fiscal/', include('apps.fiscal.urls', namespace='fiscal')),
    path('saft/', include('apps.saft.urls', namespace='saft')),
    path('compras/', include('apps.compras.urls', namespace='compras')),
    path('site/', include('apps.site.urls', namespace='site')),
    
    path('vendas/', include(('apps.vendas.urls', 'vendas'), namespace='vendas')),
    # Documentos (FT, REC, NC, ND, GT)
    #path('vendas-documentos/', include(('apps.vendas.urls_documentos', 'vendas_documentos'), namespace='vendas_documentos')),

    #path('api/v1/vendas/', include(('apps.vendas.urls', 'vendas_api'), namespace='vendas_api')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)