#pharmassys/urls.py
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect


# Função para redirecionar /accounts/profile/ para dashboard
def redirect_to_dashboard(request):
    return redirect('dashboard')


# redireciona para a view namespaced
#Criar um alias sem namespace no urls.py global
#Para que qualquer reverse('suporte') funcione, mesmo que venha do admin:
def redirect_to_suporte(request):
    from django.urls import reverse
    return redirect(reverse('configuracoes:suporte'))



urlpatterns = [
    # Admin
    path('erp-admin-2901-super/', admin.site.urls),
    
    
    # Autenticação
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change.html'), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),
    
    # *** SOLUÇÃO PARA O ERRO 404 DE ACCOUNTS/PROFILE/ ***
    path('accounts/profile/', redirect_to_dashboard, name='profile'),
    path('suporte/', redirect_to_suporte),

    # Apps
    path('', include('apps.core.urls')),
    path('produtos/', include('apps.produtos.urls')),
    path('clientes/', include('apps.clientes.urls', namespace='clientes')), #Tenho que usar namespace='clientes' para possibilitar chamar qualquer url da app clientes no javascript. Ex: {% url 'clientes:api_buscar_clientes' %}

    path('estoque/', include('apps.estoque.urls')),
    path('fornecedores/', include('apps.fornecedores.urls')),
    path('funcionarios/', include('apps.funcionarios.urls')),
    path('financeiro/', include('apps.financeiro.urls')),
    path('servicos/', include('apps.servicos.urls')),
    path('comandas/', include('apps.comandas.urls')),
    path('configuracoes/', include('apps.configuracoes.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('relatorios/', include('apps.relatorios.urls')),
    path('fiscal/', include('apps.fiscal.urls')),
    path('saft/', include('apps.saft.urls')),
    path('compras/', include('apps.compras.urls')),

    path('vendas/', include('apps.vendas.urls')),
    path('vendas-documentos/', include('apps.vendas.urls_documentos', namespace='vendas_documentos')),
    path('api/v1/vendas/', include('apps.vendas.urls', namespace='vendas_api')),
]


def robots_txt(request):
    content = "User-agent: *\nDisallow: /"
    return HttpResponse(content, content_type="text/plain")

urlpatterns += [
    path("robots.txt", robots_txt, name="robots_txt"),
]


