# apps/core_tenants/middleware.py
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from apps.core.models import IPConhecido
from apps.core.utils import get_user_empresa

logger = logging.getLogger('core_tenants.middleware')


# ==============================================================
# 🔹 1. LOG DE DOCUMENTOS
# ==============================================================
class DocumentLogMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if 'documentos/gerar' in request.path and response.status_code == 200:
            doc_logger = logging.getLogger('documentos')
            doc_logger.info(
                f'Documento gerado: {request.path} - '
                f'Usuário: {request.user.username if request.user.is_authenticated else "Anônimo"}'
            )
        return response


# ==============================================================
# 🔹 2. ACESSO A MÓDULOS (blindado contra schema public)
# ==============================================================
class ModuloAcessMiddleware:
    """
    Middleware responsável por:
    1. Garantir que o usuário pertence ao Tenant (Schema) actual.
    2. Garantir que o Tenant possui licença para aceder ao módulo da URL.

    100% aderente ao isolamento físico do django-tenants.
    """

    EXEMPT_PREFIXES = {
        'admin',
        'static',
        'media',
        'login',
        'logout',
        'perfil',
        'dashboard',
        'auth',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if connection.schema_name == 'public':
            return self.get_response(request)

        if hasattr(request.user, 'tenants'):
            if not request.user.tenants.filter(pk=request.tenant.pk).exists():
                raise PermissionDenied("Você não tem permissão a esta empresa/tenant.")

        path_segments = [seg for seg in request.path.strip("/").split("/") if seg]
        path_module = path_segments[0] if path_segments else ""

        if path_module in self.EXEMPT_PREFIXES:
            return self.get_response(request)

        licenca = getattr(request.tenant, "licenca", None)

        if licenca and hasattr(licenca, "plano"):
            modulos_ativos = set(licenca.plano.modulos.values_list("slug", flat=True))
        else:
            modulos_ativos = set()

        if path_module and path_module not in modulos_ativos:
            return HttpResponseForbidden("O seu plano não possui acesso a este módulo.")

        return self.get_response(request)


# ==============================================================
# 🔹 3. LICENÇA VENCIDA (blindado contra schema public)
# ==============================================================
class LicencaVencidaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if connection.schema_name == 'public' or not request.user.is_authenticated or request.path.startswith('/admin/'):
            return self.get_response(request)

        empresa = get_user_empresa(request.user)
        if not empresa:
            return self.get_response(request)

        licenca = getattr(empresa, 'licenca', None)

        if request.path != '/licenca-expirada/':
            if licenca and (licenca.esta_vencida or licenca.status != 'ativa'):
                return render(request, 'errors/licenca_expirada.html', {'licenca': licenca})

        return self.get_response(request)


# ==============================================================
# 🔹 4. TWO-FACTOR POR IP (2FA — blindado contra schema public)
# ==============================================================
class TwoFactorIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if connection.schema_name == 'public':
            return self.get_response(request)

        if request.user.is_authenticated:
            path = request.path
            tenant_urlconf = settings.TENANT_URLCONF

            exempt_urls = [
                # CORRIGIDO: VerifyIPView agora vive em core_tenants, não em core.
                reverse('core_tenants:verify_ip', urlconf=tenant_urlconf),
                # logout continua a resolver por 'core' porque urls_login.py
                # (namespace 'core') é incluído também no TENANT_URLCONF.
                reverse('core:logout', urlconf=tenant_urlconf),
                settings.STATIC_URL,
                settings.MEDIA_URL,
                '/admin/',
            ]

            if any(path.startswith(url) for url in exempt_urls):
                return self.get_response(request)

            ip_atual = self.get_client_ip(request)
            ip_autorizado = IPConhecido.objects.filter(
                usuario=request.user,
                ip_address=ip_atual
            ).exists()

            if not ip_autorizado:
                return redirect(reverse('core_tenants:verify_ip', urlconf=tenant_urlconf))

        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')