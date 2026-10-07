
class CustomLoginView(LoginView):
    """
    RIGOR SOTARQ: Camada de Segurança no Login (Isolamento Físico).
    Impede que utilizadores comuns façam login diretamente no schema 'public'.
    """
    template_name = 'registration/login.html'

    def form_valid(self, form):
        # 1. Executa o login padrão do Django
        response = super().form_valid(form)
        user = self.request.user

        # 2. Superusuários do ecossistema têm acesso total em qualquer schema
        if user.is_superuser:
            return response

        # 3. Blindagem de Isolamento Físico:
        # Utilizadores comuns NÃO podem autenticar-se no schema 'public'
        schema_atual = getattr(connection, 'schema_name', 'public')
        if schema_atual == 'public':
            logout(self.request)
            messages.error(
                self.request,
                "Acesso negado: O login deve ser efetuado através do subdomínio da sua empresa."
            )
            return redirect('core:login')

        return response



#######


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
    #path('', include('config.urls_tenants')),
    path('empresas/', include('apps.empresas.urls', namespace='empresas')),
    
    # Proteção robots
    path("robots.txt", robots_txt, name="robots_txt"),
]


# vistogest-pro/config/urls_public.py
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def robots_txt(request):
    content = "User-agent: *\nDisallow: /admin/"
    return HttpResponse(content, content_type="text/plain")

urlpatterns = [
    path('admin/', admin.site.urls),

    # Core público: SÓ login/logout, nada de dashboard/módulos do ERP
    path('', include(('apps.core.urls_public', 'core'), namespace='core')),

    path('empresas/', include('apps.empresas.urls', namespace='empresas')),  # onde vai viver o auto-registo
    path("robots.txt", robots_txt, name="robots_txt"),
]