# apps/empresas/urls.py
from django.urls import path
from . import views_public

app_name = 'empresas'

urlpatterns = [
    path('registo/', views_public.CadastroEmpresaView.as_view(), name='cadastro'),
    path('registo/sucesso/', views_public.CadastroSucessoView.as_view(), name='cadastro_sucesso'),
]