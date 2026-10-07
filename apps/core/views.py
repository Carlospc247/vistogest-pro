# apps/core/views.py
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
import json
import logging
from decimal import Decimal
from django.urls import reverse_lazy

logger = logging.getLogger('core.security')
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth.views import LoginView
from apps.core.models import AuditoriaAcesso
from apps.core.signals import get_client_ip
from apps.produtos.models import Categoria, Produto
from apps.empresas.models import Empresa
from apps.analytics.models import AuditoriaInvestimento
from django.core.mail import send_mail
from django.template.loader import render_to_string
from .models import IPConhecido, AuditoriaAcesso, VerificacaoSeguranca
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.contrib import messages
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from calendar import monthrange
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from apps.analytics.models import AuditoriaInvestimento, EventoAnalytics, NotificacaoAlerta
from apps.empresas.models import Empresa
from apps.produtos.models import Produto
from apps.vendas.models import Venda, FaturaCredito, NotaCredito
from datetime import date, timedelta
import traceback
from django.core.exceptions import PermissionDenied
from django.contrib.auth import logout
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db import connection
from django.db import connection
from django_tenants.utils import schema_context
from apps.licenca.models import ComissaoBypass




# ============================================================
# BASE VIEW COM CONTEXTO EMPRESARIAL
# ============================================================

class BaseMPAView(TemplateView):
    """
    RIGOR SOTARQ: base para todas as views MPA de tenant.
    Alinhada ao padrão django_tenants (isolamento físico via schema PostgreSQL).
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        context.update({
            'user': self.request.user,
            'current_module': getattr(self, 'module_name', 'dashboard'),
            'empresa_atual': empresa,
        })
        return context

    def get_empresa(self):
        """Retorna o Tenant (Empresa) activo associado ao schema da requisição actual."""
        tenant = getattr(self.request, 'tenant', None) or getattr(connection, 'tenant', None)

        if not tenant or getattr(tenant, 'schema_name', 'public') == 'public':
            if getattr(self, 'exigir_empresa', False):
                raise PermissionDenied("Acção permitida apenas no contexto de uma empresa/tenant activo.")
            return None

        return tenant






from django.views.generic import TemplateView
from django.core.exceptions import PermissionDenied
from django.db import connection





class PlanoBypassView(LoginRequiredMixin, BaseMPAView):
    template_name = 'core/plano_bypass.html'
    module_name = 'plano_bypass' # 👈 Importante para o CSS do botão | Para garantir que ninguém descubra a URL e tente acessá-la (mesmo sem o botão)
    
    def dispatch(self, request, *args, **kwargs):
        # RIGOR SOTARQ: Só o Admin Supremo ou quem tem permissão explícita entra
        if not request.user.is_superuser and not request.user.has_perm('core.pode_ver_bypass'):
            raise PermissionDenied("Acesso restrito ao Administrador do Ecossistema.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresas_elite = Empresa.objects.filter(plano__nome__iexact='Elite Bypass')
        relatorio_geral = []
        total_global_comissao = Decimal('0.00')
        total_faturado_geral = Decimal('0.00')

        for emp in empresas_elite:
            with schema_context(emp.schema_name):
                # 🛡️ RIGOR SOTARQ: Soma faturamento real e subtrai Notas de Crédito (Devoluções)
                vendas = Venda.objects.filter(status='finalizada').aggregate(t=Sum('total'))['t'] or Decimal('0')
                faturas = FaturaCredito.objects.filter(status='liquidada').aggregate(t=Sum('total'))['t'] or Decimal('0')
                devolucoes = NotaCredito.objects.filter(status='emitida').aggregate(t=Sum('total'))['t'] or Decimal('0')
                
                faturamento_liquido = (vendas + faturas) - devolucoes
                comissao = faturamento_liquido * Decimal('0.02')
                
                relatorio_geral.append({
                    'faturamento': faturamento_liquido,
                    'nossa_parte': comissao,
                })
                total_global_comissao += comissao
                total_faturado_geral += faturamento_liquido

        context.update({
            'relatorio': relatorio_geral,
            'total_global': total_global_comissao,
            'total_faturado_geral': total_faturado_geral,
        })
        return context

# ============================================================
# DASHBOARD
# ============================================================


class CustomLoginView(LoginView):
    """
    View de login com protecção completa contra brute-force e DDoS:

    ┌─────────────────────────────────────────────────────────────────┐
    │  CAMADAS DE PROTECÇÃO                                           │
    │  1. Rate limit por IP  — MAX_ATTEMPTS_IP em WINDOW segundos    │
    │  2. Rate limit por username — MAX_ATTEMPTS_USER em WINDOW s    │
    │  3. Lockout progressivo — bloqueia LOCKOUT_DURATION segundos   │
    │  4. hCaptcha — aparece após CAPTCHA_THRESHOLD falhas           │
    │  5. Reset automático — contadores limpos após login correcto   │
    │  6. Log persistente — LoginAttempt gravado em BD               │
    └─────────────────────────────────────────────────────────────────┘
    """
    template_name = 'registration/login.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Ponto de entrada: verificar lockout ANTES de processar qualquer formulário.
        Bloqueia tanto GET como POST quando em lockout — impede enumeração de usernames.
        """
        from apps.core.services.rate_limit_service import LoginRateLimitService
        username = request.POST.get('username', '').strip()

        if LoginRateLimitService.is_locked(request, username):
            ttl = LoginRateLimitService.lockout_ttl(request, username)
            return self._render_lockout(request, ttl)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.services.rate_limit_service import LoginRateLimitService
        from django.conf import settings as dj_settings
        username = self.request.POST.get('username', '').strip()
        attempts = LoginRateLimitService.get_attempts(self.request, username)
        ctx.update({
            'show_captcha':        attempts >= getattr(dj_settings, 'LOGIN_CAPTCHA_THRESHOLD', 3),
            'hcaptcha_site_key':   getattr(dj_settings, 'HCAPTCHA_SITE_KEY', ''),
            'login_attempts':      attempts,
            'captcha_threshold':   getattr(dj_settings, 'LOGIN_CAPTCHA_THRESHOLD', 3),
        })
        return ctx

    def form_valid(self, form):
        """Login bem-sucedido: limpar contadores e continuar o fluxo normal."""
        from apps.core.services.rate_limit_service import LoginRateLimitService
        username = form.cleaned_data.get('username', '')

        # Limpar contadores antes de chamar super() (que faz login e redireciona)
        LoginRateLimitService.reset_on_success(self.request, username)

        response = super().form_valid(form)
        user = self.request.user

        # Superutilizadores podem aceder ao schema public
        if user.is_superuser:
            return response

        schema_atual = getattr(connection, 'schema_name', 'public')
        if schema_atual == 'public':
            logout(self.request)
            messages.error(
                self.request,
                "Acesso negado: o login deve ser feito através do subdomínio da sua empresa."
            )
            return redirect('core:login')

        return response

    def form_invalid(self, form):
        """
        Login falhado: registar tentativa e aplicar rate limit.
        Verificar CAPTCHA se acima do limiar.
        """
        from apps.core.services.rate_limit_service import LoginRateLimitService
        from apps.core.services.captcha_service import CaptchaService
        from django.conf import settings as dj_settings

        username = self.request.POST.get('username', '').strip()
        schema   = getattr(connection, 'schema_name', 'public')
        attempts_before = LoginRateLimitService.get_attempts(self.request, username)

        # ── 1. Verificar CAPTCHA se acima do limiar ────────────────────────
        captcha_threshold = getattr(dj_settings, 'LOGIN_CAPTCHA_THRESHOLD', 3)
        if attempts_before >= captcha_threshold:
            captcha_ok, captcha_err = CaptchaService.verificar(self.request)
            if not captcha_ok:
                messages.error(self.request, captcha_err)
                # Não incrementa contador por falha de CAPTCHA (evita penalizar
                # utilizadores que só erraram o puzzle visual, não a password)
                return super().form_invalid(form)

        # ── 2. Registar falha e verificar lockout resultante ───────────────
        estado = LoginRateLimitService.record_failure(
            request=self.request,
            username=username,
            schema=schema,
        )

        if estado['ip_locked'] or estado['user_locked']:
            return self._render_lockout(self.request, estado['lockout_seconds'])

        # ── 3. Aviso progressivo de tentativas restantes ───────────────────
        from apps.core.services.rate_limit_service import MAX_USER
        restantes_user = MAX_USER - estado['user_attempts']
        if 0 < restantes_user <= 2 and username:
            messages.warning(
                self.request,
                f"Atenção: ainda tem {restantes_user} tentativa(s) antes de a conta ficar bloqueada."
            )

        return super().form_invalid(form)

    def _render_lockout(self, request, ttl_segundos: int):
        """Renderiza a página de lockout com o tempo restante."""
        minutos   = ttl_segundos // 60
        segundos  = ttl_segundos % 60

        if minutos > 0:
            tempo_msg = f"{minutos} minuto(s) e {segundos} segundo(s)"
        else:
            tempo_msg = f"{ttl_segundos} segundo(s)"

        return render(request, 'registration/login.html', {
            'locked_out':          True,
            'lockout_seconds':     ttl_segundos,
            'lockout_tempo_legivel': tempo_msg,
            'hcaptcha_site_key':   getattr(settings, 'HCAPTCHA_SITE_KEY', ''),
            'show_captcha':        False,
            'login_attempts':      0,
        }, status=429)


    def get_success_url(self):
        from django.urls import reverse
        from django.conf import settings

        schema_atual = getattr(connection, 'schema_name', 'public')
        if schema_atual == 'public':
            return '/admin/'

        # Passa urlconf explicitamente — não depende do thread-local de
        # get_urlconf() estar correctamente propagado neste ponto do ciclo
        # de pedido. Mesmo padrão já usado em TwoFactorIPMiddleware.
        return reverse('core_tenants:dashboard', urlconf=settings.TENANT_URLCONF)
        

def logout_view(request):
    """Lógica de encerramento de sessão com limpeza de logs."""
    logout(request)
    messages.success(request, "Sessão encerrada com sucesso. Até breve!")
    return redirect('core:login')





@receiver(user_logged_in)
def verificar_seguranca_ip(sender, request, user, **kwargs):
    ip_atual = get_client_ip(request)
    
    # 1. Registrar a auditoria (já existente)
    AuditoriaAcesso.objects.create(
        usuario=user,
        acao='LOGIN',
        ip_address=ip_atual,
        user_agent=request.META.get('HTTP_USER_AGENT')
    )

    # 2. Verificar se o IP é novo
    ip_existe = IPConhecido.objects.filter(usuario=user, ip_address=ip_atual).exists()

    if not ip_existe:
        # Registrar como novo IP conhecido para o futuro
        IPConhecido.objects.create(usuario=user, ip_address=ip_atual)
        
        # Enviar e-mail de alerta (Apenas se não for o primeiro login da história do user)
        if AuditoriaAcesso.objects.filter(usuario=user, acao='LOGIN').count() > 1:
            enviar_alerta_ip_novo(user, ip_atual, request.META.get('HTTP_USER_AGENT'))

def enviar_alerta_ip_novo(user, ip, ua):
    context = {
        'user': user,
        'ip': ip,
        'ua': ua,
        'sistema': 'VistoGEST'
    }
    html_content = render_to_string('emails/alerta_seguranca_ip.html', context)
    
    send_mail(
        subject="Alerta de Segurança: Novo acesso detectado",
        message=f"Um novo acesso foi realizado na sua conta VistoGEST a partir do IP {ip}.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_content
    )


# ============================================================
# SEGURANÇA: VERIFICAÇÃO DE DISPOSITIVO (2FA POR IP)
# ============================================================

from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import logout
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.db import connection
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import VerificacaoSeguranca, IPConhecido  # Ajuste os imports conforme os seus apps



# ============================================================
# SEGURANÇA — Endpoint AJAX de status do lockout (S13)
# ============================================================

class LoginStatusView(View):
    """
    AJAX GET — devolve o estado de rate limit para o IP do pedido.

    Usado pelo frontend para:
      - Polling periódico (a cada 5 s) enquanto o utilizador está
        perto do limiar, para detectar lockout sem reload de página.
      - Mostrar contagem de tentativas restantes em tempo real.
      - Fornecer ao script de debounce o TTL exacto do lockout.

    Não requer autenticação — actua antes do login ser feito.
    Retorna apenas informação de segurança (nunca dados pessoais).

    Resposta:
        {
            "locked":          bool,
            "lockout_seconds": int,    # 0 se não bloqueado
            "attempts":        int,    # total de falhas recentes
            "needs_captcha":   bool,
            "ip_locked":       bool,
            "user_locked":     bool,
        }
    """

    def get(self, request):
        from apps.core.services.rate_limit_service import LoginRateLimitService

        username = request.GET.get('u', '').strip()  # username opcional (GET param)

        ip_locked   = LoginRateLimitService.is_ip_locked(
            LoginRateLimitService.get_ip(request)
        )
        user_locked = LoginRateLimitService.is_user_locked(username) if username else False
        locked      = ip_locked or user_locked
        ttl         = LoginRateLimitService.lockout_ttl(request, username) if locked else 0
        attempts    = LoginRateLimitService.get_attempts(request, username)

        return JsonResponse({
            'locked':          locked,
            'lockout_seconds': ttl,
            'attempts':        attempts,
            'needs_captcha':   LoginRateLimitService.needs_captcha(request, username),
            'ip_locked':       ip_locked,
            'user_locked':     user_locked,
        })


class LoginUnblockView(LoginRequiredMixin, View):
    """
    POST — Desbloqueia um IP ou username (apenas superutilizadores).
    Útil para administradores desbloquear utilizadores legítimos bloqueados
    pelo rate limiter após demasiadas tentativas.
    """

    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

        from apps.core.services.rate_limit_service import LoginRateLimitService
        try:
            data     = json.loads(request.body)
            ip       = data.get('ip', '').strip()
            username = data.get('username', '').strip()

            if ip:
                LoginRateLimitService.unblock_ip(ip)
            if username:
                LoginRateLimitService.unblock_user(username)

            if not ip and not username:
                return JsonResponse({'ok': False, 'error': 'ip ou username obrigatório'}, status=400)

            logger.info(
                "Desbloqueio manual: ip=%s username=%s por %s",
                ip, username, request.user.username
            )
            return JsonResponse({'ok': True, 'ip': ip, 'username': username})

        except Exception as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)


@csrf_exempt
def error_report(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            logger.error(f"FRONTEND ERROR: {json.dumps(data, indent=2)}")
            return JsonResponse({'status': 'success'})
        except:
            return JsonResponse({'status': 'error'}, status=400)
    return JsonResponse({'status': 'error'}, status=405)


# ============================================================
# PWA — Manifest + Offline + Sync (S9 · PLANO_IMPLEMENTACAO v7)
# ============================================================

class PWAManifestView(View):
    """
    Serve o manifest.json dinamicamente para incluir o nome do tenant.
    Registado em /manifest.json (sem autenticação, sem CSRF).
    """

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        nome_empresa = getattr(tenant, 'nome', None) or 'VistoGEST Pro'
        schema = getattr(tenant, 'schema_name', 'public')

        manifest = {
            "name": nome_empresa,
            "short_name": nome_empresa[:12],
            "description": f"Sistema de Gestão — {nome_empresa}",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#ffffff",
            "theme_color": "#2563eb",
            "lang": "pt",
            "icons": [
                {
                    "src": "/static/images/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable"
                },
                {
                    "src": "/static/images/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable"
                }
            ],
            "categories": ["business", "productivity"],
            "screenshots": [],
            "shortcuts": [
                {
                    "name": "Nova Venda",
                    "short_name": "PDV",
                    "description": "Abrir o Ponto de Venda",
                    "url": "/vendas/pdv/",
                    "icons": [{"src": "/static/images/icon-192.png", "sizes": "192x192"}]
                },
                {
                    "name": "Dashboard",
                    "short_name": "Dashboard",
                    "description": "Ver o painel principal",
                    "url": "/",
                    "icons": [{"src": "/static/images/icon-192.png", "sizes": "192x192"}]
                }
            ]
        }

        return JsonResponse(
            manifest,
            content_type='application/manifest+json',
            headers={'Cache-Control': 'public, max-age=3600'},
        )


class PWAOfflineView(TemplateView):
    """Página offline — servida pelo Service Worker quando não há rede."""
    template_name = "core/offline.html"


class PWASyncOfflineView(LoginRequiredMixin, View):
    """
    Endpoint para Background Sync do Service Worker.
    Recebe vendas criadas offline e as regista na base de dados.
    """

    def post(self, request):
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

        # Por agora, registar e confirmar — a lógica de criação de venda
        # está no endpoint /ajax/vendas/nova/ que o SW usará com retry.
        # Este endpoint serve para confirmar que o sync foi recebido.
        logger.info(f"PWA Background Sync recebido: {len(payload.get('vendas', []))} venda(s) de {request.user}")

        return JsonResponse({
            'ok': True,
            'received': len(payload.get('vendas', [])),
            'message': 'Sincronização recebida com sucesso',
        })


class PWAServiceWorkerView(View):
    """
    Serve o service-worker.js a partir da raiz (/) para que o scope seja '/'.
    O SW em /static/js/ não pode ter scope global — tem de ser servido da raiz.
    """

    def get(self, request):
        import os
        from django.conf import settings as dj_settings
        from django.http import HttpResponse

        # Tentar localizar o ficheiro estático
        sw_paths = [
            os.path.join(dj_settings.BASE_DIR, 'apps', 'core', 'static', 'js', 'service-worker.js'),
            os.path.join(dj_settings.BASE_DIR, 'static', 'js', 'service-worker.js'),
            os.path.join(dj_settings.BASE_DIR, 'staticfiles', 'js', 'service-worker.js'),
        ]
        for path in sw_paths:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                response = HttpResponse(content, content_type='application/javascript')
                response['Service-Worker-Allowed'] = '/'
                response['Cache-Control'] = 'no-cache'
                return response

        # Fallback mínimo se o ficheiro não for encontrado
        minimal_sw = "self.addEventListener('fetch', function(e) {});"
        response = HttpResponse(minimal_sw, content_type='application/javascript')
        response['Service-Worker-Allowed'] = '/'
        return response
