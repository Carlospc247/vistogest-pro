# vistogest-pro/config/urls_public.py
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def robots_txt(request):
    content = "User-agent: *\nDisallow: /admin/"
    return HttpResponse(content, content_type="text/plain")

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core público: SÓ login/logout/reset — nada de dashboard ou módulos do ERP
    path('', include(('apps.core.urls_login', 'core'), namespace='core')),

    path('empresas/', include('apps.empresas.urls', namespace='empresas')),

    # Portal de Parceiros — área pública (schema public)
    # /portal-parceiros/ → acesso do parceiro externo
    # /admin-parceiros/  → acesso dos funcionários SOTARQ
    path('portal-parceiros/', include(('apps.parceiros.urls', 'parceiros'), namespace='parceiros')),
    path('admin-parceiros/',  include(('apps.parceiros.urls', 'parceiros_admin'), namespace='parceiros_admin')),

    path("robots.txt", robots_txt, name="robots_txt"),
]
