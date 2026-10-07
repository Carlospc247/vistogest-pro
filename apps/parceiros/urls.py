# apps/parceiros/urls.py
from django.urls import path
from . import views

app_name = 'parceiros'

# ── A) Portal do Parceiro (/portal-parceiros/) ────────────────────────────────
portal_patterns = [
    path('',                  views.PartnerDashboardView.as_view(),          name='portal-dashboard'),
    path('carteira/',         views.PartnerWalletView.as_view(),              name='portal-carteira'),
    path('clientes/',         views.PartnerClientListView.as_view(),          name='portal-clientes'),
    path('clientes/novo/',    views.PartnerClientCreateView.as_view(),        name='portal-cliente-criar'),
    path('clientes/<int:pk>/',views.PartnerClientDetailView.as_view(),        name='portal-cliente-detalhe'),
    path('activar-licenca/',  views.PartnerActivateLicenseView.as_view(),     name='portal-activar-licenca'),
    path('solicitar/',        views.PartnerLicenseRequestCreateView.as_view(),name='portal-solicitar'),
    path('solicitacoes/',     views.PartnerLicenseRequestListView.as_view(),  name='portal-solicitacoes'),
    path('pagamentos/',       views.PartnerBillingListView.as_view(),         name='portal-pagamentos'),
    path('notificacoes/',     views.PartnerNotificationListView.as_view(),    name='portal-notificacoes'),
]

# ── B) Área Interna SOTARQ (/admin-parceiros/) ────────────────────────────────
admin_patterns = [
    path('',                              views.PartnerAdminDashboardView.as_view(), name='admin-dashboard'),
    path('parceiros/',                    views.PartnerListView.as_view(),            name='admin-parceiros'),
    path('parceiros/novo/',               views.PartnerCreateView.as_view(),          name='admin-parceiro-criar'),
    path('parceiros/<int:pk>/',           views.PartnerDetailView.as_view(),          name='admin-detalhe'),
    path('parceiros/<int:partner_pk>/licenca/', views.PartnerLicenseCreateView.as_view(), name='admin-licenca-criar'),
    path('solicitacoes/',                 views.PartnerLicenseRequestAdminView.as_view(), name='admin-solicitacoes'),
    path('faturamento/',                  views.PartnerBillingAdminView.as_view(),    name='admin-faturamento'),
    path('tokens/',                       views.PartnerTokenGenerateView.as_view(),   name='admin-gerar-token'),
]

urlpatterns = portal_patterns + admin_patterns
