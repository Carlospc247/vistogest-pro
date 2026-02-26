#apps/core/middleware.py
import threading
from django.conf import settings
from django.shortcuts import redirect, render
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.db import connection # RIGOR: Essencial para detectar o schema
import logging
from django.utils.deprecation import MiddlewareMixin
from apps.core.utils import get_user_empresa
from django.shortcuts import redirect
from django.urls import reverse
from .models import IPConhecido, VerificacaoSeguranca



# ==============================================================
# 🔹 1. REDIRECIONAMENTO DE PERFIL (Protegido)
# ==============================================================
class AccountsProfileRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/accounts/profile'):
            if request.user.is_authenticated:
                return HttpResponseRedirect('/')
            else:
                return HttpResponseRedirect('/accounts/login/')
        
        return self.get_response(request)

# ==============================================================
# 🔹 2. LOG DE DOCUMENTOS
# ==============================================================
class DocumentLogMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if 'documentos/gerar' in request.path and response.status_code == 200:
            logger = logging.getLogger('documentos')
            logger.info(f'Documento gerado: {request.path} - Usuário: {request.user.username if request.user.is_authenticated else "Anônimo"}')
        return response

# ==============================================================
# 🔹 3. ACESSO A MÓDULOS (Blindado contra Public)
# ==============================================================

class ModuloAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if connection.schema_name == 'public':
            return self.get_response(request)

        if not request.user.is_authenticated:
            return self.get_response(request)

        empresa = get_user_empresa(request.user)
        if not empresa:
            return self.get_response(request)

        licenca = getattr(empresa, "licenca", None)
        modulos_ativos = (
            licenca.plano.modulos.values_list("slug", flat=True)
            if licenca else []
        )

        # Em vez de usar in, também pode-se udar set(). É mais eficiente:
        # Busca O(1) | Evita consultas repetidas
        #modulos_ativos = set(
        #    licenca.plano.modulos.values_list("slug", flat=True)
        #) if licenca else set()

        # ✅ EXTRAÇÃO DO MÓDULO DA URL
        path_module = request.path.strip("/").split("/")[0]

        # Rotas que nunca devem ser bloqueadas
        if path_module in ["admin", "static", "media", "login", "logout"]:
            return self.get_response(request)

        if path_module and path_module not in modulos_ativos:
            return HttpResponseForbidden("Módulo não ativo.")

        return self.get_response(request)
   
# ==============================================================
# 🔹 4. LICENÇA VENCIDA (Blindado contra Public)
# ==============================================================
class LicencaVencidaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # RIGOR: Administrador Global (Public) ou Admin do Django não sofrem bloqueio de licença
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
# 🔹 5. THREAD LOCAL USER (O Cérebro)
# ==============================================================



_thread_locals = threading.local()

class ThreadLocalUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. BLINDAGEM: Se for public, limpamos o cache de relações de tenant
        # Isso impede que o Django tente carregar o funcionário no login global
        if connection.schema_name == 'public' and request.user.is_authenticated:
            # Limpa o cache interno do Django para relações OneToOne/ForeignKey
            # O Django costuma usar o nome do campo ou o related_name no cache interno
            for attr in ['_funcionario_cache', 'funcionario']:
                if hasattr(request.user, attr):
                    try:
                        delattr(request.user, attr)
                    except AttributeError:
                        pass

        # 2. PERSISTÊNCIA: Armazena o usuário na thread
        _thread_locals.user = getattr(request, 'user', None)
        
        response = self.get_response(request)
        
        # 3. SEGURANÇA: Limpa a thread após a resposta para evitar vazamento de dados
        if hasattr(_thread_locals, 'user'):
            del _thread_locals.user
            
        return response

def get_current_authenticated_user():
    """Retorna o usuário armazenado na thread atual."""
    return getattr(_thread_locals, 'user', None)



class TwoFactorIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # RIGOR SOTARQ: Lista de exceções expandida
            path = request.path
            exempt_urls = [
                reverse('core:verify_ip'), 
                reverse('core:logout'),
                settings.STATIC_URL, # Libera CSS/JS
                settings.MEDIA_URL,  # Libera Imagens
                '/admin/',           # Evita trancar o admin
            ]

            # Se o caminho atual começar com qualquer uma das exceções, deixa passar
            if any(path.startswith(url) for url in exempt_urls):
                return self.get_response(request)

            # Verificação de IP
            ip_atual = self.get_client_ip(request)
            ip_autorizado = IPConhecido.objects.filter(
                usuario=request.user, 
                ip_address=ip_atual
            ).exists()

            if not ip_autorizado:
                return redirect('core:verify_ip')

        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
    
