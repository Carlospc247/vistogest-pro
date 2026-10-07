# vistogest-pro/config/urls_tenants.py

from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # Redireciona raiz para login (usa o namespace core do login)
    path('', RedirectView.as_view(pattern_name='core:login', permanent=False)),

    path(
        '',
        include(
            ('apps.core.urls_login', 'core'),
            namespace='core'
        )
    ),

    # ── URLs do core_tenants (dashboard, notificações, 2FA, etc.) ────────────
    path(
        '',
        include(
            ('apps.core_tenants.urls', 'core_tenants'),
            namespace='core_tenants'
        )
    ),
    # ── Módulos ERP (TENANT_APPS) ─────────────────────────────────────────────
    path('vendas/',        include(('apps.vendas.urls',        'vendas'),        namespace='vendas')),
    path('produtos/',      include(('apps.produtos.urls',      'produtos'),      namespace='produtos')),
    path('clientes/',      include(('apps.clientes.urls',      'clientes'),      namespace='clientes')),
    path('estoque/',       include(('apps.estoque.urls',       'estoque'),       namespace='estoque')),
    path('fornecedores/',  include(('apps.fornecedores.urls',  'fornecedores'),  namespace='fornecedores')),
    path('funcionarios/',  include(('apps.funcionarios.urls',  'funcionarios'),  namespace='funcionarios')),
    path('financeiro/',    include(('apps.financeiro.urls',    'financeiro'),    namespace='financeiro')),
    path('servicos/',      include(('apps.servicos.urls',      'servicos'),      namespace='servicos')),
    path('configuracoes/', include(('apps.configuracoes.urls', 'configuracoes'), namespace='configuracoes')),
    path('analytics/',     include(('apps.analytics.urls',    'analytics'),     namespace='analytics')),
    path('relatorios/',    include(('apps.relatorios.urls',   'relatorios'),    namespace='relatorios')),
    path('fiscal/',        include(('apps.fiscal.urls',       'fiscal'),        namespace='fiscal')),
    path('saft/',          include(('apps.saft.urls',         'saft'),          namespace='saft')),
    path('compras/',       include(('apps.compras.urls',      'compras'),       namespace='compras')),
    path('site/',          include(('apps.site.urls',         'site'),          namespace='site')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,  document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)