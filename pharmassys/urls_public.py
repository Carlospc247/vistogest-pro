from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def robots_txt(request):
    content = "User-agent: *\nDisallow: /admin/"
    return HttpResponse(content, content_type="text/plain")

urlpatterns = [
    # Admin global
    path('admin/', admin.site.urls),

    # Core público (login, dashboard básico, páginas públicas)
    path('', include(('apps.core.urls', 'core'), namespace='core')),
    #path('', include('pharmassys.urls_tenants')),
    path('empresas/', include('apps.empresas.urls', namespace='empresas')),
    
    # Proteção robots
    path("robots.txt", robots_txt, name="robots_txt"),
]