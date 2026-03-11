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



"""
#urls_tenants.py
print("!!! CARREGANDO URLS DO TENANT !!!")
from django.urls import path
from apps.billing.views import billing_webhook
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.views.generic import RedirectView


# Título do Admin (Para ficar profissional)
admin.site.site_header = "Sotarq School | Administração"
admin.site.site_title = "Portal Admin"
admin.site.index_title = "Gestão do Sistema"

urlpatterns = [
    # 1. Administração (Acesso ao Cofre de Chaves, Utilizadores, etc.)
    path('', RedirectView.as_view(pattern_name='core:login', permanent=False)),
    path('', include('apps.core.urls')), 
    
    #path('admin/', admin.site.urls), # REMOVI PORQUE, CADA ESCOLA NÃO DEVE TER SEU PRÓPRIO DJANGO-ADMIN
    # e também para evitar avisos de erros de duas rotas admin no sistema.

    # Agrupamento de módulos por funcionalidade
    path('academic/', include('apps.academic.urls', namespace='academic')),
    path('teachers/', include('apps.teachers.urls', namespace='teachers')),
    path('students/', include('apps.students.urls', namespace='students')),
    path('transport/', include('apps.transport.urls', namespace='transport')),
    path('portal/', include('apps.portal.urls', namespace='portal')),
    path('finance/', include('apps.finance.urls')),
    path('saft/', include('apps.saft.urls')),
    path('library/', include('apps.library.urls')),
    path('cafeteria/', include('apps.cafeteria.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('reports/', include('apps.reports.urls')),
    path('audit/', include('apps.audit.urls')),
    path('fiscal/', include('apps.fiscal.urls')),
    path('compras/', include('apps.compras.urls')),
    path('documents/', include('apps.documents.urls')),
    path('accounts/', include('apps.accounts.urls')),

    path('billing/webhook-gateway-secret-123/', billing_webhook, name='billing_webhook'),

    #path('', include('apps.core.urls', namespace='core')), # ATENÇÃO: Mantenha sempre no final da lista porque contém a rota vazia ''.
    #path('', include('apps.core.urls')),
]

if settings.DEBUG:
    # Desenvolvimento: Django serve tudo
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # Produção: O Nginx ou WhiteNoise cuidam disso. 
    # Deixamos as URLs limpas para performance.
    pass
"""