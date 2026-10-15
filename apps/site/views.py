# apps/site/views.py
"""
Views da app site — site institucional + loja online.
"""
import copy
import hashlib
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import connection, models, transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Max
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views import View
from django.views.generic import CreateView
from django_tenants.utils import get_public_schema_name
from rest_framework import permissions, viewsets

from apps.clientes.models import Cliente
from apps.produtos.models import Produto
from apps.servicos.models import AgendamentoServico, Servico

from .forms import CandidaturaForm
from .models import (
    Candidatura, Carrinho, ClienteSite, ComprovativoCompra, ConfiguracaoSite,
    Concurso, EventoSite, ItemCarrinho, ItemPedidoOnline, Pagina, PedidoOnline,
    ProdutoSite, Reclamacao, Secao, ServicoSite, SolicitacaoContato,
    formatar_duracao,
)
from .serializers import (
    CandidaturaSerializer, CarrinhoSerializer, ClienteSiteSerializer,
    ComprovativoCompraSerializer, ConcursoSerializer, ConfiguracaoSiteSerializer,
    PaginaSerializer, PedidoOnlineSerializer, ProdutoSiteSerializer,
    ReclamacaoSerializer, SecaoSerializer, ServicoSiteSerializer,
    SolicitacaoContatoSerializer,
)

logger = logging.getLogger('site')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _obter_config():
    return ConfiguracaoSite.obter()


def _esta_no_public():
    return getattr(connection, 'schema_name', None) == get_public_schema_name()


def _pode_gerir_site(user):
    """
    True se o utilizador pode gerir o site:
    superuser, ou funcionário ativo cujo cargo tenha pode_gerir_site.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        funcionario = user.funcionario_relacionado
    except ObjectDoesNotExist:
        return False   # utilizador sem funcionário associado
    return funcionario.pode_realizar_acao('gerir_site')


class TenantOnlyMixin:
    """
    Protege as views do gestor do site:
      1. bloqueia pedidos que chegam no schema public;
      2. bloqueia utilizadores sem a permissão 'pode_gerir_site' no cargo.
    Deve vir DEPOIS de LoginRequiredMixin e ANTES de View.
    """
    redirect_url_name = 'core_tenants:dashboard'        # confirma que este nome existe
    redirect_sem_permissao = 'core_tenants:dashboard'   # para onde mandar quem não tem permissão

    def _e_ajax(self, request):
        return (request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.content_type == 'application/json')

    def dispatch(self, request, *args, **kwargs):
        if _esta_no_public():
            if self._e_ajax(request):
                raise PermissionDenied("Operação permitida apenas no domínio da empresa.")
            messages.error(
                request,
                "O gestor do site só está disponível no domínio da sua empresa."
            )
            return redirect(self.redirect_url_name)

        if not _pode_gerir_site(request.user):
            if self._e_ajax(request):
                raise PermissionDenied("Não tem permissão para gerir o site.")
            messages.error(request, "Não tem permissão para gerir o site.")
            return redirect(self.redirect_sem_permissao)

        return super().dispatch(request, *args, **kwargs)


class PodeGerirSite(permissions.BasePermission):
    message = "Não tem permissão para gerir o site."

    def has_permission(self, request, view):
        return _pode_gerir_site(request.user)


class TenantBaseViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, PodeGerirSite]

    def get_queryset(self):
        return self.queryset
    
def _obter_carrinho(request):
    """Obtém ou cria o carrinho activo para a sessão/cliente."""
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key

    cliente_site = None
    if request.session.get('cliente_site_id'):
        try:
            cliente_site = ClienteSite.objects.get(pk=request.session['cliente_site_id'], ativo=True)
        except ClienteSite.DoesNotExist:
            pass

    return Carrinho.obter_ou_criar(session_key, cliente_site)


def _contexto_base(request):
    """Contexto partilhado por todas as páginas públicas."""
    config = _obter_config()
    carrinho = _obter_carrinho(request)
    cliente_site_id = request.session.get('cliente_site_id')
    return {
        'config':         config,
        'carrinho':       carrinho,
        'carrinho_total': carrinho.total_itens,
        'cliente_logado': ClienteSite.objects.filter(pk=cliente_site_id, ativo=True).first() if cliente_site_id else None,
    }


_BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|monitor|facebookexternalhit|curl|wget', re.I)


def registar_evento(request, tipo, referencia=''):
    """Regista interação anónima. Nunca deve partir a página."""
    try:
        ua = request.META.get('HTTP_USER_AGENT', '')
        if _BOT_RE.search(ua) or request.user.is_authenticated:   # ignora bots e equipa interna
            return
        if not request.session.session_key:
            request.session.create()
        sk = request.session.session_key or ''
        if tipo == 'visita':   # 1 visita por sessão/página/30 min
            if EventoSite.objects.filter(
                tipo='visita', session_key=sk, caminho=request.path[:300],
                created_at__gte=timezone.now() - timedelta(minutes=30),
            ).exists():
                return
        EventoSite.objects.create(
            tipo=tipo, caminho=request.path[:300], referencia=str(referencia)[:120],
            session_key=sk, dispositivo='mobile' if 'Mobi' in ua else 'desktop',
        )
    except Exception as exc:
        logger.warning("registar_evento falhou: %s", exc)


def _vitrine_produtos(limite, so_destaque=False):
    ocultos = set(ProdutoSite.objects.filter(visivel_na_loja=False).values_list('produto_id', flat=True))
    cfg = {c.produto_id: c for c in ProdutoSite.objects.filter(visivel_na_loja=True)}
    itens = []
    for p in Produto.objects.filter(ativo=True).exclude(id__in=ocultos):
        c = cfg.get(p.id)
        if so_destaque and not (c and c.destaque):
            continue
        img = ''
        try:
            img = p.imagem.url if getattr(p, 'imagem', None) else ''
        except Exception:
            pass
        itens.append({'id': p.id, 'nome': p.nome_produto, 'imagem': img,
                      'preco': c.preco_final if c else getattr(p, 'preco_venda', Decimal('0.00'))})
        if len(itens) >= limite:
            break
    return itens


def _vitrine_servicos(limite):
    ocultos = set(ServicoSite.objects.filter(visivel_na_loja=False).values_list('servico_id', flat=True))
    cfg = {c.servico_id: c for c in ServicoSite.objects.filter(visivel_na_loja=True)}
    itens = []
    for s in Servico.objects.filter(ativo=True).exclude(id__in=ocultos)[:limite]:
        c = cfg.get(s.id)
        itens.append({'id': s.id, 'nome': s.nome, 'descricao': getattr(s, 'descricao', ''),
                      'preco': c.preco_final if c else getattr(s, 'preco', Decimal('0.00'))})
    return itens



def _preparar_secoes(qs):
    """
    Prepara as secções para renderização pública.
    Normaliza os logos dos parceiros para que o template
    receba sempre as chaves esperadas.
    """
    secoes = list(qs)

    for s in secoes:
        s.templates_render = [
            f"site/sections/{s.tipo}.html",
            "site/sections/_fallback.html",
        ]

        dados = s.dados if isinstance(s.dados, dict) else {}

        # Normalizar os logos dos parceiros.
        # Aceita o formato atual (url) e o antigo (imagem_url).
        if s.tipo == 'parceiros':
            logos_originais = dados.get('logos_json') or []
            logos_normalizados = []

            if isinstance(logos_originais, list):
                for item in logos_originais:
                    if not isinstance(item, dict):
                        continue

                    logo = dict(item)

                    logo['url'] = str(
                        logo.get('url')
                        or logo.get('imagem_url')
                        or ''
                    ).strip()

                    logo['alt'] = str(
                        logo.get('alt') or 'Parceiro'
                    ).strip()

                    logo['link'] = str(
                        logo.get('link') or ''
                    ).strip()

                    logos_normalizados.append(logo)

            # Alteração apenas para esta renderização.
            # Não grava automaticamente na base de dados.
            s.dados = {
                **dados,
                'logos_json': logos_normalizados,
            }

        try:
            limite = int(dados.get('limite') or 8)
        except (TypeError, ValueError):
            limite = 8

        if s.tipo == 'produtos':
            s.itens_vitrine = _vitrine_produtos(
                limite,
                bool(dados.get('so_destaque')),
            )

        elif s.tipo == 'servicos':
            s.itens_vitrine = _vitrine_servicos(limite)

    return secoes



def _json_body(request):
    try:
        return json.loads(request.body or b'{}')
    except Exception:
        return request.POST.dict()


# ─────────────────────────────────────────────────────────────────────────────
# API ViewSets (REST)
# ─────────────────────────────────────────────────────────────────────────────



class ConfiguracaoSiteViewSet(TenantBaseViewSet):
    queryset          = ConfiguracaoSite.objects.all()
    serializer_class  = ConfiguracaoSiteSerializer

class PaginaViewSet(TenantBaseViewSet):
    queryset          = Pagina.objects.all()
    serializer_class  = PaginaSerializer

class SecaoViewSet(TenantBaseViewSet):
    queryset          = Secao.objects.all()
    serializer_class  = SecaoSerializer

class ProdutoSiteViewSet(TenantBaseViewSet):
    queryset          = ProdutoSite.objects.filter(visivel_na_loja=True)
    serializer_class  = ProdutoSiteSerializer

class ServicoSiteViewSet(TenantBaseViewSet):
    queryset          = ServicoSite.objects.filter(visivel_na_loja=True)
    serializer_class  = ServicoSiteSerializer

class ConcursoViewSet(TenantBaseViewSet):
    queryset          = Concurso.objects.filter(ativo=True)
    serializer_class  = ConcursoSerializer

class CandidaturaViewSet(TenantBaseViewSet):
    queryset          = Candidatura.objects.all()
    serializer_class  = CandidaturaSerializer

class SolicitacaoContatoViewSet(TenantBaseViewSet):
    queryset          = SolicitacaoContato.objects.all()
    serializer_class  = SolicitacaoContatoSerializer

class ReclamacaoViewSet(TenantBaseViewSet):
    queryset          = Reclamacao.objects.all()
    serializer_class  = ReclamacaoSerializer

class ComprovativoCompraViewSet(TenantBaseViewSet):
    queryset          = ComprovativoCompra.objects.all()
    serializer_class  = ComprovativoCompraSerializer

class PedidoOnlineViewSet(TenantBaseViewSet):
    queryset          = PedidoOnline.objects.all()
    serializer_class  = PedidoOnlineSerializer


# ─────────────────────────────────────────────────────────────────────────────
# Site Institucional (público)
# ─────────────────────────────────────────────────────────────────────────────

class PaginaDetailView(View):
    """Página pública. Só mostra páginas PUBLICADAS (em_rascunho=False)."""
    template_name = 'site/index.html'

    def get(self, request, slug=None):
        if slug:
            pagina = get_object_or_404(Pagina, slug=slug, ativo=True, em_rascunho=False)
        else:
            pagina = Pagina.obter_principal()
            if not pagina:
                return render(request, 'site/em_construcao.html', _contexto_base(request))

        registar_evento(request, 'visita')
        ctx = _contexto_base(request)
        ctx.update({
            'pagina':               pagina,
            'secoes':               _preparar_secoes(pagina.secoes.filter(ativo=True).order_by('ordem')),
            'concursos':            Concurso.objects.filter(ativo=True),
            'servicos_disponiveis': Servico.objects.filter(ativo=True),   # usado por agendamento.html
        })
        return render(request, self.template_name, ctx)


class SitePreviewView(LoginRequiredMixin, View):
    """Preview de rascunho (equipa interna, com token)."""
    template_name = 'site/index.html'

    def get(self, request, slug, token):
        pagina = get_object_or_404(Pagina, slug=slug, preview_token=token)
        ctx = _contexto_base(request)
        ctx.update({
            'pagina':               pagina,
            'modo_preview':         True,
            'secoes':               _preparar_secoes(pagina.secoes.all().order_by('ordem')),
            'servicos_disponiveis': Servico.objects.filter(ativo=True),
        })
        return render(request, self.template_name, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Loja Online — Catálogo
# ─────────────────────────────────────────────────────────────────────────────

class LojaView(View):
    """
    Página da loja online.
    Catálogo automático: todos os Produto e Servico activos são exibidos.
    ProdutoSite/ServicoSite permitem ocultar itens específicos ou personalizar preço.
    """
    template_name = 'site/loja/loja.html'

    def get(self, request):
        config = _obter_config()
        if not config.loja_activa:
            return render(request, 'site/loja/loja_inactiva.html', _contexto_base(request))

        # Produtos: todos os activos. Se tiver entrada em ProdutoSite com visivel=False → excluir
        ocultos_produto = ProdutoSite.objects.filter(
            visivel_na_loja=False
        ).values_list('produto_id', flat=True)

        produtos = Produto.objects.filter(ativo=True).exclude(id__in=ocultos_produto)

        # Enriquecer com configuração de site (preço customizado, destaque)
        config_produto = {p.produto_id: p for p in ProdutoSite.objects.filter(visivel_na_loja=True)}

        # Serviços: mesma lógica
        ocultos_servico = ServicoSite.objects.filter(
            visivel_na_loja=False
        ).values_list('servico_id', flat=True)

        servicos = Servico.objects.filter(ativo=True).exclude(id__in=ocultos_servico)
        config_servico = {s.servico_id: s for s in ServicoSite.objects.filter(visivel_na_loja=True)}

        registar_evento(request, 'visita')  # loja
        ctx = _contexto_base(request)
        ctx.update({
            'produtos':        produtos,
            'servicos':        servicos,
            'config_produto':  config_produto,
            'config_servico':  config_servico,
            'em_destaque_p':   [p for p in produtos if config_produto.get(p.id) and config_produto[p.id].destaque],
            'em_destaque_s':   [s for s in servicos if config_servico.get(s.id) and config_servico[s.id].destaque],
        })
        return render(request, self.template_name, ctx)


class ProdutoDetalheView(View):
    """Detalhe de um produto na loja."""
    template_name = 'site/loja/produto_detalhe.html'

    def get(self, request, pk):
        produto = get_object_or_404(Produto, pk=pk, ativo=True)
        # Verificar se está oculto
        config_p = ProdutoSite.objects.filter(produto=produto, visivel_na_loja=False).first()
        if config_p:
            return redirect('site:loja')
        try:
            preco = ProdutoSite.objects.get(produto=produto).preco_final
        except ProdutoSite.DoesNotExist:
            preco = getattr(produto, 'preco_venda', Decimal('0.00'))

        ctx = _contexto_base(request)
        registar_evento(request, 'produto', produto.nome_produto)  # track-produto
        ctx.update({'produto': produto, 'preco': preco})
        return render(request, self.template_name, ctx)


class ServicoDetalheView(View):
    """Detalhe de um serviço na loja."""
    template_name = 'site/loja/servico_detalhe.html'

    def get(self, request, pk):
        servico = get_object_or_404(Servico, pk=pk, ativo=True)
        try:
            preco = ServicoSite.objects.get(servico=servico).preco_final
        except ServicoSite.DoesNotExist:
            preco = getattr(servico, 'preco', Decimal('0.00'))
        ctx = _contexto_base(request)
        ctx.update({'servico': servico, 'preco': preco})
        return render(request, self.template_name, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Loja Online — Carrinho
# ─────────────────────────────────────────────────────────────────────────────

class CarrinhoView(View):
    """Visualizar o carrinho de compras."""
    template_name = 'site/loja/carrinho.html'

    def get(self, request):
        carrinho = _obter_carrinho(request)
        ctx = _contexto_base(request)
        ctx['carrinho_obj'] = carrinho
        ctx['itens'] = carrinho.itens.all()
        return render(request, self.template_name, ctx)


class AdicionarCarrinhoView(View):
    """Adicionar item ao carrinho (AJAX ou POST normal)."""

    def post(self, request):
        carrinho  = _obter_carrinho(request)
        tipo      = request.POST.get('tipo', 'produto')  # 'produto' ou 'servico'
        item_id   = request.POST.get('item_id')
        try:
            quantidade = max(1, int(request.POST.get('quantidade', 1)))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Quantidade inválida.'}, status=400)

        if not item_id:
            return JsonResponse({'success': False, 'error': 'item_id obrigatório'}, status=400)

        try:
            if tipo == 'produto':
                produto = get_object_or_404(Produto, pk=item_id, ativo=True)
                try:
                    preco = ProdutoSite.objects.get(produto=produto).preco_final
                except ProdutoSite.DoesNotExist:
                    preco = getattr(produto, 'preco_venda', Decimal('0.00'))
                item, created = ItemCarrinho.objects.get_or_create(
                    carrinho=carrinho, produto=produto,
                    defaults={'preco_unitario': preco, 'quantidade': quantidade}
                )
                if not created:
                    item.quantidade += quantidade
                    item.save(update_fields=['quantidade'])
            else:
                servico = get_object_or_404(Servico, pk=item_id, ativo=True)
                try:
                    preco = ServicoSite.objects.get(servico=servico).preco_final
                except ServicoSite.DoesNotExist:
                    preco = getattr(servico, 'preco', Decimal('0.00'))
                item, created = ItemCarrinho.objects.get_or_create(
                    carrinho=carrinho, servico=servico,
                    defaults={'preco_unitario': preco, 'quantidade': quantidade}
                )
                if not created:
                    item.quantidade += quantidade
                    item.save(update_fields=['quantidade'])

        except Exception as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

        registar_evento(request, "carrinho", f"{tipo}:{item_id}")  # track-carrinho
        return JsonResponse({
            'success': True,
            'total_itens': carrinho.total_itens,
            'total': str(carrinho.total),
        })


class RemoverItemCarrinhoView(View):
    """Remover item do carrinho."""

    def post(self, request):
        item_id = request.POST.get('item_id')
        carrinho = _obter_carrinho(request)
        ItemCarrinho.objects.filter(pk=item_id, carrinho=carrinho).delete()
        return JsonResponse({'success': True, 'total_itens': carrinho.total_itens})


# ─────────────────────────────────────────────────────────────────────────────
# Loja Online — Checkout e Pedido
# ─────────────────────────────────────────────────────────────────────────────

class CheckoutView(View):
    """Formulário de checkout — dados de entrega e cliente."""
    template_name = 'site/loja/checkout.html'

    def get(self, request):
        carrinho = _obter_carrinho(request)
        if not carrinho.itens.exists():
            messages.warning(request, "O seu carrinho está vazio.")
            return redirect('site:loja')
        ctx = _contexto_base(request)
        ctx.update({'carrinho_obj': carrinho, 'itens': carrinho.itens.all()})
        return render(request, self.template_name, ctx)

    @transaction.atomic
    def post(self, request):
        carrinho = _obter_carrinho(request)
        if not carrinho.itens.exists():
            return redirect('site:loja')

        nome     = request.POST.get('nome', '').strip()
        email    = request.POST.get('email', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        endereco = request.POST.get('endereco_entrega', '').strip()
        notas    = request.POST.get('notas', '').strip()

        if not nome or not email or not endereco:
            messages.error(request, "Nome, email e endereço de entrega são obrigatórios.")
            return redirect('site:checkout')

        # Obter ou criar ClienteSite
        cliente_site, _ = ClienteSite.objects.get_or_create(
            email=email,
            defaults={'nome': nome, 'telefone': telefone}
        )
        # Guardar na sessão
        request.session['cliente_site_id'] = cliente_site.pk

        # Criar PedidoOnline
        pedido = PedidoOnline.objects.create(
            cliente_site=cliente_site,
            nome_destinatario=nome,
            telefone_entrega=telefone,
            endereco_entrega=endereco,
            notas=notas,
            moeda=_obter_config().moeda,
        )

        # Criar ItemPedidoOnline a partir do carrinho
        for item in carrinho.itens.all():
            ItemPedidoOnline.objects.create(
                pedido=pedido,
                produto=item.produto,
                servico=item.servico,
                nome_item=item.nome,
                quantidade=item.quantidade,
                preco_unitario=item.preco_unitario,
            )

        pedido.recalcular_total()

        # Fechar carrinho
        carrinho.ativo = False
        carrinho.save(update_fields=['ativo'])

        return redirect('site:pedido_confirmacao', referencia=pedido.referencia)


class PedidoConfirmacaoView(View):
    """Página de confirmação após submissão do pedido."""
    template_name = 'site/loja/pedido_confirmacao.html'

    def get(self, request, referencia):
        pedido = get_object_or_404(PedidoOnline, referencia=referencia)
        ctx = _contexto_base(request)
        ctx.update({
            'pedido':         pedido,
            'itens':          pedido.itens.all(),
            'url_whatsapp':   pedido.url_whatsapp_pedido(),
        })
        return render(request, self.template_name, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Área do Cliente (autenticação pública)
# ─────────────────────────────────────────────────────────────────────────────

class ClienteRegistoView(View):
    """Registo de novo cliente no portal público."""
    template_name = 'site/cliente/registo.html'

    def get(self, request):
        return render(request, self.template_name, _contexto_base(request))

    def post(self, request):
        nome     = request.POST.get('nome', '').strip()
        email    = request.POST.get('email', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        senha    = request.POST.get('senha', '').strip()

        if not nome or not email or not senha:
            messages.error(request, "Nome, email e senha são obrigatórios.")
            return redirect('site:cliente_registo')

        if ClienteSite.objects.filter(email=email).exists():
            messages.error(request, "Este email já está registado.")
            return redirect('site:cliente_login')

        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        cliente = ClienteSite.objects.create(
            nome=nome, email=email, telefone=telefone, senha_hash=senha_hash
        )
        request.session['cliente_site_id'] = cliente.pk
        messages.success(request, f"Bem-vindo(a), {nome}!")
        return redirect('site:cliente_perfil')


class ClienteLoginView(View):
    """Login de cliente no portal público."""
    template_name = 'site/cliente/login.html'

    def get(self, request):
        return render(request, self.template_name, _contexto_base(request))

    def post(self, request):
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('senha', '').strip()

        senha_hash = hashlib.sha256(senha.encode()).hexdigest()
        try:
            cliente = ClienteSite.objects.get(email=email, senha_hash=senha_hash, ativo=True)
            request.session['cliente_site_id'] = cliente.pk
            messages.success(request, f"Bem-vindo(a) de volta, {cliente.nome}!")
            return redirect('site:cliente_perfil')
        except ClienteSite.DoesNotExist:
            messages.error(request, "Email ou senha incorrectos.")
            return redirect('site:cliente_login')


class ClienteLogoutView(View):
    def get(self, request):
        request.session.pop('cliente_site_id', None)
        return redirect('site:loja')


class ClienteRecuperarSenhaView(View):
    """
    Solicita a recuperação da senha do cliente.

    Por segurança, nunca informa ao utilizador se o email
    existe ou não no sistema.
    """

    template_name = 'site/cliente/recuperar_senha.html'

    SIGNER_SALT = 'site-cliente-recuperacao-senha'
    TOKEN_MAX_AGE = 3600  # 1 hora

    def get(self, request):
        return render(request, self.template_name, _contexto_base(request))

    def post(self, request):
        email = request.POST.get('email', '').strip().lower()

        if not email:
            messages.error(request, "Informe o seu email.")
            return redirect('site:cliente_recuperar_senha')

        cliente = ClienteSite.objects.filter(email__iexact=email, ativo=True).first()

        # Não revelar se o email está ou não registado.
        if cliente:
            signer = TimestampSigner(salt=self.SIGNER_SALT)

            # O hash actual da senha também entra no token.
            # Assim, depois que a senha for alterada,
            # tokens antigos deixam automaticamente de funcionar.
            payload = f"{cliente.pk}:{cliente.senha_hash}"
            token = signer.sign(payload)

            url_redefinicao = request.build_absolute_uri(
                reverse('site:cliente_redefinir_senha', kwargs={'token': token})
            )

            nome_empresa = _obter_config().nome_exibicao
            assunto = f"Redefinição de senha — {nome_empresa}"

            mensagem = (
                f"Olá, {cliente.nome}.\n\n"
                "Recebemos um pedido para redefinir a senha "
                "da sua conta no nosso site.\n\n"
                "Para criar uma nova senha, aceda ao link abaixo:\n\n"
                f"{url_redefinicao}\n\n"
                "Este link é válido durante 1 hora.\n"
                "Depois desse período será necessário solicitar "
                "um novo link.\n\n"
                "Se não foi você que solicitou esta alteração, "
                "ignore este email.\n\n"
                f"{nome_empresa}"
            )

            try:
                send_mail(
                    subject=assunto,
                    message=mensagem,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                    recipient_list=[cliente.email],
                    fail_silently=False,
                )
            except Exception:
                # Registar internamente sem expor detalhes ao utilizador.
                logger.exception(
                    "Falha ao enviar email de recuperação para ClienteSite id=%s",
                    cliente.pk,
                )
                messages.error(
                    request,
                    "Não foi possível enviar o email de recuperação. "
                    "Tente novamente mais tarde."
                )
                return redirect('site:cliente_recuperar_senha')

        messages.success(
            request,
            "Se o email estiver associado a uma conta activa, "
            "receberá um link para redefinir a sua senha."
        )
        return redirect('site:cliente_login')


class ClienteRedefinirSenhaView(View):
    """
    Define uma nova senha utilizando o token enviado por email.

    O token:
      - é assinado pelo SECRET_KEY do Django;
      - expira após 1 hora;
      - fica inválido depois que a senha é alterada.
    """

    template_name = 'site/cliente/redefinir_senha.html'

    SIGNER_SALT = 'site-cliente-recuperacao-senha'
    TOKEN_MAX_AGE = 3600  # 1 hora

    def _obter_cliente_do_token(self, token):
        """
        Valida o token e retorna o ClienteSite correspondente.
        Formato esperado do payload: cliente_id:senha_hash_actual
        """
        signer = TimestampSigner(salt=self.SIGNER_SALT)
        payload = signer.unsign(token, max_age=self.TOKEN_MAX_AGE)

        try:
            cliente_id, senha_hash_token = payload.split(':', 1)
        except ValueError:
            raise BadSignature("Token de recuperação malformado.")

        cliente = ClienteSite.objects.filter(pk=int(cliente_id), ativo=True).first()

        if not cliente:
            raise BadSignature("Cliente inválido ou inactivo.")

        # Se a senha já tiver sido alterada, o hash actual será diferente
        # e o token deixa de ser válido.
        if cliente.senha_hash != senha_hash_token:
            raise BadSignature("Token já utilizado ou senha já alterada.")

        return cliente

    def get(self, request, token):
        try:
            cliente = self._obter_cliente_do_token(token)
        except SignatureExpired:
            messages.error(
                request,
                "O link de redefinição de senha expirou. Solicite um novo link."
            )
            return redirect('site:cliente_recuperar_senha')
        except (BadSignature, ValueError, TypeError):
            messages.error(request, "O link de redefinição de senha é inválido.")
            return redirect('site:cliente_recuperar_senha')

        ctx = _contexto_base(request)
        ctx.update({'token': token, 'cliente': cliente})
        return render(request, self.template_name, ctx)

    def post(self, request, token):
        senha = request.POST.get('senha', '')
        confirmar_senha = request.POST.get('confirmar_senha', '')

        if not senha or not confirmar_senha:
            messages.error(request, "Preencha a nova senha e a confirmação.")
            return redirect('site:cliente_redefinir_senha', token=token)

        if len(senha) < 6:
            messages.error(request, "A nova senha deve ter pelo menos 6 caracteres.")
            return redirect('site:cliente_redefinir_senha', token=token)

        if senha != confirmar_senha:
            messages.error(request, "As senhas não coincidem.")
            return redirect('site:cliente_redefinir_senha', token=token)

        try:
            cliente = self._obter_cliente_do_token(token)
        except SignatureExpired:
            messages.error(
                request,
                "O link de redefinição de senha expirou. Solicite um novo link."
            )
            return redirect('site:cliente_recuperar_senha')
        except (BadSignature, ValueError, TypeError):
            messages.error(
                request,
                "O link de redefinição de senha é inválido ou já foi utilizado."
            )
            return redirect('site:cliente_recuperar_senha')

        # Manter compatibilidade com o sistema actual (SHA-256 para ClienteSite).
        cliente.senha_hash = hashlib.sha256(senha.encode('utf-8')).hexdigest()
        cliente.save(update_fields=['senha_hash', 'updated_at'])

        # Autenticar automaticamente o cliente após a redefinição.
        request.session['cliente_site_id'] = cliente.pk

        messages.success(request, "A sua senha foi redefinida com sucesso.")
        return redirect('site:cliente_perfil')


class ClientePerfilView(View):
    """Área pessoal do cliente — pedidos, contactos e reclamações (com feedback do gestor)."""
    template_name = 'site/cliente/perfil.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get('cliente_site_id'):
            return redirect('site:cliente_login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        cliente = get_object_or_404(
            ClienteSite,
            pk=request.session['cliente_site_id'],
            ativo=True
        )

        pedidos = PedidoOnline.objects.filter(cliente_site=cliente).order_by('-created_at')

        # Os campos atendido, atendido_em, feedback_gestor e tempo_resposta_fmt
        # (RastreioAtendimento) já vêm nos objetos — o template só os mostra.
        contactos = SolicitacaoContato.objects.filter(
            email__iexact=cliente.email
        ).order_by('-created_at')

        reclamacoes = Reclamacao.objects.filter(
            cliente_email__iexact=cliente.email
        ).order_by('-created_at')

        ctx = _contexto_base(request)
        ctx.update({
            'cliente': cliente,
            'pedidos': pedidos,
            'contactos': contactos,
            'reclamacoes': reclamacoes,
        })
        return render(request, self.template_name, ctx)


class MeusPedidosView(View):
    """Lista de pedidos do cliente autenticado no site."""
    template_name = 'site/cliente/pedidos.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get('cliente_site_id'):
            return redirect('site:cliente_login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        cliente = get_object_or_404(ClienteSite, pk=request.session['cliente_site_id'], ativo=True)
        pedidos = PedidoOnline.objects.filter(cliente_site=cliente).order_by('-created_at')
        ctx = _contexto_base(request)
        ctx.update({'cliente': cliente, 'pedidos': pedidos})
        return render(request, self.template_name, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Formulários públicos
# ─────────────────────────────────────────────────────────────────────────────

class CandidaturaCreateView(SuccessMessageMixin, CreateView):
    model          = Candidatura
    form_class     = CandidaturaForm
    template_name  = 'site/forms/candidatura_form.html'
    success_message = 'Candidatura enviada com sucesso!'

    def get_success_url(self):
        from django.urls import reverse_lazy
        return reverse_lazy('site:pagina_home')


class SolicitacaoContatoCreateView(View):
    template_name = 'site/forms/contato_form.html'

    def get(self, request):
        ctx = _contexto_base(request)
        cliente = ctx.get('cliente_logado')
        if cliente:
            ctx.update({'cliente_formulario': cliente})
        return render(request, self.template_name, ctx)

    def post(self, request):
        cliente_site_id = request.session.get('cliente_site_id')
        cliente = None
        if cliente_site_id:
            cliente = ClienteSite.objects.filter(pk=cliente_site_id, ativo=True).first()

        if cliente:
            nome = cliente.nome
            email = cliente.email
            telefone = cliente.telefone or request.POST.get('telefone', '').strip()
        else:
            nome = request.POST.get('nome', '').strip()
            email = request.POST.get('email', '').strip()
            telefone = request.POST.get('telefone', '').strip()

        mensagem = request.POST.get('mensagem', '').strip()
        tipo = request.POST.get('tipo', 'contato')

        if not nome or not email or not mensagem:
            messages.error(request, "Nome, email e mensagem são obrigatórios.")
            return redirect(request.META.get('HTTP_REFERER', '/'))

        SolicitacaoContato.objects.create(
            nome=nome,
            email=email,
            telefone=telefone,
            mensagem=mensagem,
            tipo=tipo,
        )

        messages.success(request, "Mensagem enviada com sucesso!")
        return redirect(request.META.get('HTTP_REFERER', '/'))


class ReclamacaoCreateView(View):
    template_name = 'site/forms/reclamacao_form.html'

    def get(self, request):
        ctx = _contexto_base(request)
        cliente = ctx.get('cliente_logado')
        if cliente:
            ctx.update({'cliente_formulario': cliente})
        return render(request, self.template_name, ctx)

    def post(self, request):
        cliente_site_id = request.session.get('cliente_site_id')
        cliente = None
        if cliente_site_id:
            cliente = ClienteSite.objects.filter(pk=cliente_site_id, ativo=True).first()

        if cliente:
            cliente_nome = cliente.nome
            cliente_email = cliente.email
            cliente_telefone = (
                cliente.telefone
                or request.POST.get('cliente_telefone', '').strip()
            )
        else:
            cliente_nome = request.POST.get('cliente_nome', '').strip()
            cliente_email = request.POST.get('cliente_email', '').strip()
            cliente_telefone = request.POST.get('cliente_telefone', '').strip()

        assunto = request.POST.get('assunto', '').strip()
        mensagem = request.POST.get('mensagem', '').strip()

        if not cliente_nome or not cliente_email or not assunto or not mensagem:
            messages.error(request, "Nome, email, assunto e mensagem são obrigatórios.")
            return redirect(request.META.get('HTTP_REFERER', '/'))

        Reclamacao.objects.create(
            cliente_nome=cliente_nome,
            cliente_email=cliente_email,
            cliente_telefone=cliente_telefone,
            assunto=assunto,
            mensagem=mensagem,
        )

        messages.success(request, "Reclamação registada com sucesso.")
        return redirect(request.META.get('HTTP_REFERER', '/'))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard administrativo (editor no-code interno)
# ─────────────────────────────────────────────────────────────────────────────

def _obter_pagina_principal(config):
    """Página principal do tenant: a primeira existente, ou cria uma."""
    pagina = Pagina.objects.order_by('pk').first()
    if pagina is None:
        pagina = Pagina.objects.create(
            slug=slugify(connection.schema_name) or 'home',
            titulo=f"Site — {config.nome_exibicao}",
        )
    return pagina


BLOCOS_DISPONIVEIS = [
    {'tipo': 'hero',        'nome': 'Hero / Banner',      'icone': 'image',           'cor': 'indigo'},
    {'tipo': 'imagem_fixa', 'nome': 'Imagem Fixa com Texto', 'icone': 'image', 'cor': 'blue'},
    {'tipo': 'carrossel',   'nome': 'Carrossel',          'icone': 'images',          'cor': 'yellow'},
    {'tipo': 'texto',       'nome': 'Texto Rico',         'icone': 'align-left',      'cor': 'blue'},
    {'tipo': 'card',        'nome': 'Cards',              'icone': 'th-large',        'cor': 'green'},
    {'tipo': 'produtos',    'nome': 'Vitrine Produtos',   'icone': 'store',           'cor': 'emerald'},
    {'tipo': 'servicos',    'nome': 'Vitrine Serviços',   'icone': 'concierge-bell',  'cor': 'teal'},
    {'tipo': 'agendamento', 'nome': 'Agendamento',        'icone': 'calendar-check',  'cor': 'indigo'},
    {'tipo': 'cta',         'nome': 'Call-to-Action',     'icone': 'bullhorn',        'cor': 'orange'},
    {'tipo': 'galeria',     'nome': 'Galeria',            'icone': 'photo-video',     'cor': 'pink'},
    {'tipo': 'depoimentos', 'nome': 'Depoimentos',        'icone': 'quote-right',     'cor': 'purple'},
    {'tipo': 'faq',         'nome': 'Perguntas (FAQ)',    'icone': 'question-circle', 'cor': 'cyan'},
    {'tipo': 'contador',    'nome': 'Contadores',         'icone': 'sort-numeric-up', 'cor': 'red'},
    {'tipo': 'equipa',      'nome': 'Equipa',             'icone': 'users',           'cor': 'violet'},
    {'tipo': 'parceiros',   'nome': 'Parceiros/Clientes', 'icone': 'handshake',       'cor': 'gray'},
    {'tipo': 'video',       'nome': 'Vídeo',              'icone': 'play-circle',     'cor': 'rose'},
    {'tipo': 'formulario',  'nome': 'Formulário',         'icone': 'envelope',        'cor': 'sky'},
    {'tipo': 'localizacao', 'nome': 'Mapa',               'icone': 'map-marker-alt',  'cor': 'amber'},
    {'tipo': 'whatsapp',    'nome': 'Botão WhatsApp',     'icone': 'comment-dots',    'cor': 'green'},
    {'tipo': 'divider',     'nome': 'Separador',          'icone': 'minus',           'cor': 'gray'},
]

# Chaves ALINHADAS com os templates de site/sections/
SECAO_DEFAULTS = {
    'hero':        {'titulo': 'O Seu Título Principal', 'subtitulo': 'Frase de impacto aqui', 'imagem_url': '',
                    'texto_botao': 'Saber Mais', 'link_botao': '/loja/', 'altura_px': 500},
    'carrossel':   {'slides': [{'imagem_url': '', 'titulo': 'Slide 1', 'subtitulo': '', 'texto_botao': 'Ver mais',
                                'link_botao': '', 'alinhamento': 'center'}], 'autoplay': True, 'intervalo_ms': 5000, 'altura_px': 450},
    'card':        {'titulo_secao': 'Nossos Destaques',
                    'itens': [{'icone': 'fas fa-star', 'titulo': 'Destaque', 'descricao': 'Descrição breve.', 'link': ''}]},
    'texto':       {'titulo': '', 'conteudo': '<p>Clique em editar para inserir o seu texto.</p>', 'alinhamento': 'esquerda'},
    'imagem_fixa': {'imagem_url': '', 'legenda': '', 'largura_total': True},
    'localizacao': {'titulo_mapa': 'A Nossa Localização', 'iframe_url': '', 'endereco_texto': '',
                    'mostrar_info_contato': True, 'altura_mapa': 400},
    'whatsapp':    {'numero_whatsapp': '', 'mensagem_predefinida': 'Olá! Vim do vosso site.',
                    'posicao': 'direita', 'texto_tooltip': 'Fale connosco'},
    'produtos':    {'titulo': 'Os Nossos Produtos', 'limite': 8, 'so_destaque': False},
    'servicos':    {'titulo': 'Os Nossos Serviços', 'limite': 6},
    'agendamento': {'titulo': 'Agende o seu Atendimento', 'subtitulo': 'Escolha o melhor horário para si',
                    'mostrar_preco': True, 'mensagem_sucesso': 'Agendamento realizado! Aguarde a nossa confirmação.',
                    'cor_botao': '#6366f1'},
    'depoimentos': {'titulo': 'O Que Dizem de Nós',
                    'depoimentos_json': [{'nome': 'Cliente Exemplo', 'cargo': 'CEO', 'texto': 'Excelente serviço!', 'foto': ''}]},
    'faq':         {'titulo': 'Perguntas Frequentes',
                    'faqs_json': [{'pergunta': 'Como funciona?', 'resposta': 'É muito simples...'}]},
    'cta':         {'titulo': 'Pronto para começar?', 'descricao': 'Entre em contacto connosco.',
                    'texto_botao': 'Contactar', 'link_botao': '/contato/'},
    'galeria':     {'titulo': 'Galeria', 'colunas': '3', 'imagens_json': []},
    'contador':    {'titulo': 'Números que Importam',
                    'contadores_json': [{'numero': 100, 'sufixo': '+', 'label': 'Clientes', 'icone': 'fas fa-users'}]},
    'equipa':      {'titulo': 'A Nossa Equipa',
                    'membros_json': [{'nome': 'Nome Apelido', 'cargo': 'Cargo', 'foto': '', 'linkedin': ''}]},
    'parceiros':   {'titulo': 'Os Nossos Parceiros', 'logos_json': [{'url': '', 'alt': 'Parceiro', 'link': ''}]},
    'video':       {'url_video': '', 'titulo': '', 'altura_px': 450},
    'formulario':  {'titulo': 'Contacte-nos', 'texto_botao': 'Enviar'},
    'divider':     {'espessura': 1, 'cor': '#e5e7eb', 'margem': 'md'},
}


class UploadImagemSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Recebe uma imagem do editor e guarda-a no Cloudinary para uma secção."""
    MAX_BYTES = 8 * 1024 * 1024
    CONTENT_TYPES = {
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
    }

    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        imagem = request.FILES.get('imagem')

        if imagem is None:
            return JsonResponse(
                {'ok': False, 'error': 'Selecciona uma imagem antes de carregar.'},
                status=400,
            )

        if imagem.size > self.MAX_BYTES:
            return JsonResponse(
                {'ok': False, 'error': 'A imagem não pode exceder 8 MB.'},
                status=413,
            )

        if imagem.content_type not in self.CONTENT_TYPES:
            return JsonResponse(
                {'ok': False, 'error': 'Formato inválido. Usa JPG, PNG, WEBP ou GIF.'},
                status=415,
            )

        try:
            import cloudinary.uploader

            tenant_folder = slugify(connection.schema_name) or 'tenant'
            resultado = cloudinary.uploader.upload(
                imagem,
                folder=f'vistogest/sites/{tenant_folder}/{secao.tipo}',
                resource_type='image',
                allowed_formats=['jpg', 'jpeg', 'png', 'webp', 'gif'],
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
            url = resultado.get('secure_url')
            if not url:
                raise RuntimeError('O serviço de imagens não devolveu um URL seguro.')

            return JsonResponse({
                'ok': True,
                'url': url,
                'public_id': resultado.get('public_id', ''),
            })
        except Exception:
            logger.exception(
                'Falha ao carregar imagem de secção (secao_id=%s)', secao.pk
            )
            return JsonResponse(
                {'ok': False, 'error': 'Não foi possível carregar a imagem. Verifica a configuração do Cloudinary.'},
                status=502,
            )



# ─── S12 Site Builder ───────────────────────────────────────────────────────

class SiteEditorView(LoginRequiredMixin, TenantOnlyMixin, View):
    """
    S12 — Editor visual de página com drag-and-drop.
    Permite ao gestor da empresa editar o site sem saber programação.
    """
    template_name = 'site/editor.html'

    def get(self, request, pagina_id=None):
        config = _obter_config()
        pagina = (
            get_object_or_404(Pagina, pk=pagina_id)
            if pagina_id
            else _obter_pagina_principal(config)
        )
        secoes = pagina.secoes.order_by('ordem')
        return render(request, self.template_name, {
            'config':             config,
            'pagina':             pagina,
            'secoes':             secoes,
            'blocos_disponiveis': BLOCOS_DISPONIVEIS,
        })


class AdicionarSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Adiciona secção. Aceita JSON (AJAX) ou form POST."""
    def post(self, request, pagina_id):
        pagina = get_object_or_404(Pagina, pk=pagina_id)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        body = _json_body(request) if is_ajax else request.POST
        tipo = body.get('tipo', 'texto')

        if tipo not in dict(Secao.TIPO_CHOICES):
            return JsonResponse({'ok': False, 'error': 'Tipo de bloco inválido'}, status=400)

        ordem = (pagina.secoes.aggregate(m=Max('ordem'))['m'] or 0) + 1
        nova = Secao.objects.create(
            pagina=pagina, tipo=tipo, ordem=ordem,
            dados=copy.deepcopy(SECAO_DEFAULTS.get(tipo, {})),
        )
        if is_ajax:
            return JsonResponse({'ok': True, 'id': nova.pk})
        messages.success(request, f"Bloco '{nova.get_tipo_display()}' adicionado.")
        return redirect('site:configuracao_dashboard')


class SiteConfigDashboardView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Dashboard de gestão do site (só em schema de tenant)."""
    template_name = 'site/dashboard_config.html'

    def get(self, request):
        config = _obter_config()
        pagina = _obter_pagina_principal(config)
        desde = timezone.now() - timedelta(days=7)
        ev = EventoSite.objects.filter(created_at__gte=desde)

        stats = {
            'contatos_novos':         SolicitacaoContato.objects.filter(atendido=False).count(),
            'candidaturas_pendentes': Candidatura.objects.filter(status='pendente').count(),
            'reclamacoes_abertas':    Reclamacao.objects.filter(atendido=False).count(),
            'pedidos_pendentes':      PedidoOnline.objects.filter(status='pendente').count(),
            'visitas_7d':             ev.filter(tipo='visita').values('session_key').distinct().count(),
            'whatsapp_7d':            ev.filter(tipo='whatsapp').count(),
        }
        pendentes = (stats['contatos_novos'] + stats['candidaturas_pendentes']
                     + stats['reclamacoes_abertas'] + stats['pedidos_pendentes'])

        base_int = reverse('site:interacoes')
        cards = [
            {'rotulo': 'Visitas (7 dias)', 'valor': stats['visitas_7d'],             'icone': 'fas fa-eye',          'cor': '#6366f1', 'url': base_int},
            {'rotulo': 'Cliques WhatsApp', 'valor': stats['whatsapp_7d'],            'icone': 'fab fa-whatsapp',     'cor': '#25D366', 'url': base_int + '?tipo=whatsapp'},
            {'rotulo': 'Contactos novos',  'valor': stats['contatos_novos'],         'icone': 'fas fa-envelope',     'cor': '#4f46e5', 'url': base_int + '?tipo=contato'},
            {'rotulo': 'Pedidos pendentes','valor': stats['pedidos_pendentes'],      'icone': 'fas fa-shopping-bag', 'cor': '#16a34a', 'url': base_int + '?tipo=pedido'},
            {'rotulo': 'Candidaturas',     'valor': stats['candidaturas_pendentes'], 'icone': 'fas fa-user-tie',     'cor': '#d97706', 'url': base_int + '?tipo=candidatura'},
            {'rotulo': 'Reclamações',      'valor': stats['reclamacoes_abertas'],    'icone': 'fas fa-exclamation-circle', 'cor': '#dc2626', 'url': base_int + '?tipo=reclamacao'},
        ]

        return render(request, self.template_name, {
            'config':           config,
            'pagina':           pagina,
            'secoes':           pagina.secoes.order_by('ordem'),
            'blocos':           BLOCOS_DISPONIVEIS,
            'empresa_atual':    getattr(connection, 'tenant', None),
            'cards':            cards,
            'pendentes_total':  pendentes,
            'ultima_alteracao': getattr(pagina, 'updated_at', None) or getattr(pagina, 'modified', None),
            # links públicos (absolutos, no domínio do tenant)
            'url_site':       request.build_absolute_uri(reverse('site:pagina_home')),
            'url_loja':       request.build_absolute_uri(reverse('site:loja')),
            'url_preview':    reverse('site:preview', args=[pagina.slug, pagina.preview_token]),
            'url_editor':     reverse('site:editor'),
            'url_interacoes': base_int,
        })


class PublicarSiteView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Publica ou despublica (campo POST acao=despublicar)."""
    def post(self, request, pk):
        pagina = get_object_or_404(Pagina, pk=pk)
        if request.POST.get('acao') == 'despublicar':
            pagina.em_rascunho = True
            msg = "Site passou a rascunho (já não é visível ao público)."
        else:
            pagina.em_rascunho = False
            pagina.ativo = True
            msg = "Site publicado com sucesso!"
        pagina.save(update_fields=['em_rascunho', 'ativo'])
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'em_rascunho': pagina.em_rascunho})
        messages.success(request, msg)
        return redirect('site:configuracao_dashboard')


class AtualizarSeoPaginaView(LoginRequiredMixin, TenantOnlyMixin, View):
    def post(self, request, pk):
        pagina = get_object_or_404(Pagina, pk=pk)
        titulo = request.POST.get('titulo', '').strip()
        if titulo:
            pagina.titulo = titulo[:200]
        pagina.meta_descricao = request.POST.get('meta_descricao', '').strip()[:160]
        pagina.save(update_fields=['titulo', 'meta_descricao'])
        messages.success(request, "Configurações de SEO guardadas.")
        return redirect('site:configuracao_dashboard')


class RegistarEventoView(View):
    """Endpoint público: só aceita cliques no WhatsApp."""
    def post(self, request):
        body = _json_body(request)
        if body.get('tipo') == 'whatsapp':
            registar_evento(request, 'whatsapp', body.get('referencia', ''))
        return JsonResponse({'ok': True})


# ─────────────────────────────────────────────────────────────────────────────
# PAINEL DE INTERAÇÕES DO PÚBLICO
# ─────────────────────────────────────────────────────────────────────────────

TIPOS_INTERACAO = {   # chave: (rótulo, ícone FA, cor)
    'pedido':       ('Pedidos',        'fa-shopping-bag',       '#16a34a'),
    'contato':      ('Contactos',      'fa-envelope',           '#4f46e5'),
    'agendamento':  ('Agendamentos',   'fa-calendar-check',     '#0891b2'),
    'candidatura':  ('Candidaturas',   'fa-user-tie',           '#d97706'),
    'reclamacao':   ('Reclamações',    'fa-exclamation-circle', '#dc2626'),
    'comprovativo': ('Comprovativos',  'fa-receipt',            '#7c3aed'),
    'cliente':      ('Novos clientes', 'fa-user-plus',          '#0ea5e9'),
    'carrinho':     ('Carrinhos',      'fa-shopping-cart',      '#64748b'),
    'whatsapp':     ('WhatsApp',       'fa-whatsapp',           '#25D366'),
}

LIMITE_RESUMO = 160


def _aware(dt):
    if dt is None:
        return timezone.now()
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def _resumo(texto, limite=LIMITE_RESUMO):
    """Mensagem numa só linha, truncada (a completa vai em 'mensagem_completa')."""
    plano = ' '.join(str(texto or '').split())
    return plano if len(plano) <= limite else plano[:limite].rstrip() + '…'


def _contacto(*partes):
    return ' · '.join(str(p) for p in partes if p)


def _nome_utilizador(user):
    if not user:
        return ''
    return user.get_full_name() or user.get_username()


def _item(tipo, pk, titulo, detalhe, quando, pendente=False, acao='',
          contacto='', link='', mensagem_completa='', obj=None):
    """
    Item do feed. `obj` (opcional) é o registo original: dele saem os dados
    de atendimento (quem, quando, feedback, tempo de resposta).
    """
    rotulo, icone, cor = TIPOS_INTERACAO[tipo]
    quando = _aware(quando)
    atendido_em = getattr(obj, 'atendido_em', None)
    por = getattr(obj, 'atendido_por', None)
    plano = ' '.join(str(mensagem_completa or '').split())

    return {
        'tipo': tipo, 'pk': pk, 'rotulo': rotulo, 'icone': icone, 'cor': cor,
        'titulo': titulo, 'detalhe': detalhe,
        'mensagem_completa': mensagem_completa,
        'tem_mais': len(plano) > LIMITE_RESUMO,     # mostra "… ver completa"
        'quando': quando,
        'pendente': pendente, 'acao': acao,
        'contacto': contacto, 'link': link,
        'atendido_em': atendido_em,
        'atendido_por': _nome_utilizador(por),
        'feedback': getattr(obj, 'feedback_gestor', '') or '',
        'tempo_resposta': formatar_duracao(atendido_em - quando) if atendido_em else '',
    }


def _url_ficheiro(campo):
    try:
        return campo.url if campo else ''
    except Exception:
        return ''


def _feed_interacoes(desde, filtro=''):
    quer = lambda t: not filtro or filtro == t
    L = 100
    it = []

    if quer('pedido'):
        for p in (PedidoOnline.objects.filter(created_at__gte=desde)
                  .select_related('cliente_site', 'processado_por')[:L]):
            it.append(_item(
                'pedido', p.pk, f"Pedido {p.referencia}",
                f"{p.nome_destinatario} · {p.total} {p.moeda} · {p.get_status_display()}",
                p.created_at, p.status == 'pendente', 'Confirmar',
                p.telefone_entrega or p.cliente_site.email, obj=p,
            ))

    if quer('contato'):
        for c in (SolicitacaoContato.objects.filter(created_at__gte=desde)
                  .select_related('atendido_por')[:L]):
            it.append(_item(
                'contato', c.pk, c.nome,
                f"{c.get_tipo_display()}: {_resumo(c.mensagem)}",
                c.created_at, not c.atendido, 'Marcar atendido',
                _contacto(c.telefone, c.email),
                mensagem_completa=c.mensagem, obj=c,
            ))

    if quer('candidatura'):
        for c in (Candidatura.objects.filter(created_at__gte=desde)
                  .select_related('concurso')[:L]):
            it.append(_item(
                'candidatura', c.pk, c.nome, f"Vaga: {c.concurso.titulo}",
                c.created_at, c.status == 'pendente', 'Marcar avaliada',
                c.email, _url_ficheiro(c.cv), obj=c,
            ))

    if quer('reclamacao'):
        for r in (Reclamacao.objects.filter(created_at__gte=desde)
                  .select_related('atendido_por')[:L]):
            it.append(_item(
                'reclamacao', r.pk, f"{r.cliente_nome} — {r.assunto}",
                _resumo(r.mensagem),
                r.created_at, not r.atendido, 'Marcar atendida',
                _contacto(r.cliente_telefone, r.cliente_email),
                mensagem_completa=f"Assunto: {r.assunto}\n\n{r.mensagem}", obj=r,
            ))

    if quer('comprovativo'):
        for c in (ComprovativoCompra.objects.filter(created_at__gte=desde)
                  .select_related('pedido')[:L]):
            ref = c.pedido.referencia if c.pedido else 'sem pedido'
            it.append(_item(
                'comprovativo', c.pk, f"Comprovativo — {ref}", c.descricao or c.nome,
                c.created_at, not c.verificado, 'Marcar verificado',
                '', _url_ficheiro(c.imagem), obj=c,
            ))

    if quer('cliente'):
        for c in ClienteSite.objects.filter(created_at__gte=desde)[:L]:
            it.append(_item('cliente', c.pk, c.nome, "Registou-se no site", c.created_at,
                            contacto=_contacto(c.email, c.telefone)))

    if quer('carrinho'):
        for c in (Carrinho.objects.filter(ativo=True, itens__isnull=False, created_at__gte=desde)
                  .distinct().prefetch_related('itens')[:L]):
            who = c.cliente_site.nome if c.cliente_site_id else 'Visitante anónimo'
            it.append(_item('carrinho', c.pk, who,
                            f"{c.total_itens} item(ns) · {c.total} — não finalizado",
                            c.created_at,
                            contacto=c.cliente_site.email if c.cliente_site_id else ''))

    if quer('whatsapp'):
        for e in EventoSite.objects.filter(tipo='whatsapp', created_at__gte=desde)[:L]:
            it.append(_item('whatsapp', e.pk, "Clicou no WhatsApp",
                            f"Página: {e.caminho} · {e.dispositivo}", e.created_at))

    if quer('agendamento'):
        try:
            for a in (AgendamentoServico.objects.filter(status='agendado')
                      .select_related('cliente', 'servico').order_by('-pk')[:L]):
                criado = getattr(a, 'created_at', None) or a.data_hora
                if _aware(criado) < desde:
                    continue
                it.append(_item(
                    'agendamento', a.pk,
                    getattr(a.cliente, 'nome_completo', str(a.cliente)),
                    f"{a.servico.nome} · para {a.data_hora:%d/%m/%Y %H:%M}", criado,
                    contacto=_contacto(getattr(a.cliente, 'telefone', ''),
                                       getattr(a.cliente, 'email', '')),
                ))
        except Exception as exc:
            logger.warning("Agendamentos no painel: %s", exc)

    it.sort(key=lambda i: i['quando'], reverse=True)
    return it[:150]


def _tempo_medio(qs):
    """Tempo médio entre criação e atendimento (só registos já atendidos)."""
    m = qs.filter(atendido_em__isnull=False).aggregate(
        m=Avg(ExpressionWrapper(F('atendido_em') - F('created_at'),
                                output_field=DurationField()))
    )['m']
    return formatar_duracao(m) if m else '—'


class InteracoesSiteView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Painel com todas as interações do público no site."""
    template_name = 'site/interacoes.html'

    def get(self, request):
        try:
            dias = int(request.GET.get('dias', 30))
        except ValueError:
            dias = 30
        dias = dias if dias in (7, 30, 90) else 30
        filtro = request.GET.get('tipo', '')
        if filtro not in TIPOS_INTERACAO:
            filtro = ''

        desde = timezone.now() - timedelta(days=dias)
        hoje = timezone.localdate()
        lista_dias = [hoje - timedelta(days=i) for i in range(dias - 1, -1, -1)]
        ev = EventoSite.objects.filter(created_at__date__gte=lista_dias[0])

        # gráfico de visitas únicas por dia
        por_dia = {r['d']: r['n'] for r in (
            ev.filter(tipo='visita').annotate(d=TruncDate('created_at'))
              .values('d').annotate(n=Count('session_key', distinct=True)))}
        maximo = max(por_dia.values(), default=1) or 1
        grafico = [{'dia': d, 'n': por_dia.get(d, 0),
                    'pct': max(4, round(por_dia.get(d, 0) / maximo * 100)) if por_dia.get(d) else 2}
                   for d in lista_dias]

        contagens = {
            'pedido':       PedidoOnline.objects.filter(created_at__gte=desde).count(),
            'contato':      SolicitacaoContato.objects.filter(created_at__gte=desde).count(),
            'candidatura':  Candidatura.objects.filter(created_at__gte=desde).count(),
            'reclamacao':   Reclamacao.objects.filter(created_at__gte=desde).count(),
            'comprovativo': ComprovativoCompra.objects.filter(created_at__gte=desde).count(),
            'cliente':      ClienteSite.objects.filter(created_at__gte=desde).count(),
            'carrinho':     Carrinho.objects.filter(ativo=True, itens__isnull=False, created_at__gte=desde).distinct().count(),
            'whatsapp':     ev.filter(tipo='whatsapp').count(),
            'agendamento':  len(_feed_interacoes(desde, 'agendamento')),
        }
        abas = [{'chave': k, 'rotulo': v[0], 'icone': v[1], 'cor': v[2], 'n': contagens[k]}
                for k, v in TIPOS_INTERACAO.items()]

        return render(request, self.template_name, {
            'dias': dias, 'filtro': filtro, 'abas': abas,
            'feed': _feed_interacoes(desde, filtro),
            'visitas_total': ev.filter(tipo='visita').values('session_key').distinct().count(),
            'grafico': grafico,
            'top_paginas': ev.filter(tipo='visita').values('caminho').annotate(n=Count('id')).order_by('-n')[:5],
            'top_produtos': ev.filter(tipo='produto').values('referencia').annotate(n=Count('id')).order_by('-n')[:5],
            'dispositivos': ev.filter(tipo='visita').values('dispositivo').annotate(n=Count('id')).order_by('-n'),
            # tempo médio de resposta (só registos atendidos no período)
            'tempo_medio_contato':    _tempo_medio(SolicitacaoContato.objects.filter(created_at__gte=desde)),
            'tempo_medio_reclamacao': _tempo_medio(Reclamacao.objects.filter(created_at__gte=desde)),
            'url_dashboard': reverse('site:configuracao_dashboard'),
        })


# tipo: (Model, filtro do que ainda está pendente, campos a actualizar)
ATENDER = {
    'contato':      (SolicitacaoContato, {'atendido': False},    {'atendido': True}),
    'reclamacao':   (Reclamacao,         {'atendido': False},    {'atendido': True}),
    'candidatura':  (Candidatura,        {'status': 'pendente'}, {'status': 'avaliada'}),
    'pedido':       (PedidoOnline,       {'status': 'pendente'}, {'status': 'confirmado'}),
    'comprovativo': (ComprovativoCompra, {'verificado': False},  {'verificado': True}),
}


class AtenderInteracaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """
    Marca uma interação como tratada e regista os dados de atendimento
    apenas nos modelos que possuem esses campos.
    """

    def post(self, request, tipo, pk):
        if tipo not in ATENDER:
            return JsonResponse(
                {'ok': False, 'error': 'tipo inválido'},
                status=400,
            )

        Model, pendente, novos = ATENDER[tipo]

        obj = Model.objects.filter(pk=pk, **pendente).first()

        if not obj:
            return JsonResponse(
                {'ok': False, 'error': 'já atendido ou inexistente'},
                status=404,
            )

        # Actualizar o estado específico da interação.
        for campo, valor in novos.items():
            setattr(obj, campo, valor)

        # Obter os campos reais do modelo.
        campos_modelo = {
            campo.name for campo in obj._meta.get_fields()
        }

        # PedidoOnline utiliza processado_por, não atendido_por.
        if tipo == 'pedido' and 'processado_por' in campos_modelo:
            obj.processado_por = request.user

        # Registar atendimento apenas quando os campos existem.
        if 'atendido_em' in campos_modelo:
            obj.atendido_em = timezone.now()

        if 'atendido_por' in campos_modelo:
            obj.atendido_por = request.user

        if 'feedback_gestor' in campos_modelo:
            obj.feedback_gestor = (
                request.POST.get('feedback') or ''
            ).strip()[:2000]

        obj.save()

        # Resposta compatível com os diferentes modelos.
        atendido_em = getattr(obj, 'atendido_em', None)
        responsavel = (
            getattr(obj, 'atendido_por', None)
            or getattr(obj, 'processado_por', None)
        )

        return JsonResponse({
            'ok': True,
            'atendido_em': (
                timezone.localtime(atendido_em).strftime('%d/%m/%Y %H:%M')
                if atendido_em else ''
            ),
            'atendido_por': _nome_utilizador(responsavel),
            'tempo_resposta': getattr(obj, 'tempo_resposta_fmt', ''),
        })


# ─────────────────────────────────────────────────────────────────────────────
# Restantes views do editor
# ─────────────────────────────────────────────────────────────────────────────

class AtualizarDesignGlobalView(LoginRequiredMixin, TenantOnlyMixin, View):
    """S12 — Actualiza design global: cores, fonte, tema, raio, efeitos, rodapé."""
    def post(self, request):
        config = _obter_config()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST.dict()
        else:
            data = request.POST.dict()

        campos_texto = [
            'cor_primaria', 'cor_secundaria', 'fonte', 'fonte_titulos', 'fonte_corpo',
            'tema_layout', 'raio_bordas', 'rodape_cor', 'rodape_texto_cor',
            'texto_botao_primario', 'texto_whatsapp_flutuante',
        ]
        campos_bool = ['sombras_activas', 'animacoes_activas', 'header_transparente']

        for campo in campos_texto:
            if campo in data:
                setattr(config, campo, data[campo])
        for campo in campos_bool:
            if campo in data:
                val = data[campo]
                setattr(config, campo, val is True or val == 'true' or val == 'on')

        config.salvar()
        if is_ajax:
            return JsonResponse({'ok': True})
        messages.success(request, "Aparência global actualizada.")
        return redirect('site:configuracao_dashboard')


class AtualizarConfiguracaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Actualiza ConfiguracaoSite (WhatsApp, loja, contactos, etc.)."""
    def post(self, request):
        config = _obter_config()
        campos = [
            'nome_exibicao', 'slogan', 'email_publico', 'telefone_publico',
            'endereco_publico', 'numero_whatsapp', 'mensagem_whatsapp',
            'mostrar_whatsapp', 'loja_activa', 'aceita_pedidos', 'moeda',
            'mensagem_confirmacao', 'email_notificacao_pedidos',
            'facebook', 'instagram', 'linkedin', 'youtube', 'iframe_mapa',
        ]
        campos_booleanos = {'mostrar_whatsapp', 'loja_activa', 'aceita_pedidos'}

        for campo in campos:
            if campo in campos_booleanos:
                # Checkboxes desmarcadas não chegam no POST: nesse caso ficam False.
                valor = request.POST.get(campo, '').strip().lower()
                setattr(config, campo, valor in {'on', 'true', '1', 'yes', 'sim'})
            elif campo in request.POST:
                # Preserva a possibilidade de limpar campos de texto.
                setattr(config, campo, request.POST.get(campo, '').strip())

        config.salvar()
        messages.success(request, 'Configuração actualizada.')
        return redirect('site:configuracao_dashboard')



class ReordenarSecoesView(LoginRequiredMixin, TenantOnlyMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

        with transaction.atomic():
            # Aceita tanto {'secoes': [...]} como {'ordem': [...]}
            lista = data.get('ordem') or data.get('secoes', [])
            if isinstance(lista, str):
                try:
                    lista = json.loads(lista)
                except Exception:
                    lista = []
            for item in lista:
                pk = item.get('id') or item.get('pk')
                ord_ = item.get('ordem', item.get('posicao', 0))
                if pk is not None:
                    Secao.objects.filter(pk=pk).update(ordem=ord_)
        return JsonResponse({'ok': True})


class EditarConteudoSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """S12 — Editar conteúdo e design de uma secção via AJAX."""
    def get(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        return JsonResponse({
            'status': 'success',
            'dados': secao.dados,
            'tipo': secao.tipo,
            'design': {
                'fundo':             secao.fundo,
                'cor_fundo_custom':  secao.cor_fundo_custom,
                'padding_vertical':  secao.padding_vertical,
                'largura_maxima':    secao.largura_maxima,
                'animacao_entrada':  secao.animacao_entrada,
                'classe_extra':      secao.classe_extra,
            }
        })

    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            body = json.loads(request.body) if is_ajax else request.POST.dict()
        except Exception:
            body = {}

        # Actualizar conteúdo
        if 'dados' in body:
            raw = body['dados']
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass
            secao.dados = raw if isinstance(raw, dict) else secao.dados

        # Actualizar design da secção
        if 'design' in body:
            design = body['design']
            if isinstance(design, str):
                try:
                    design = json.loads(design)
                except Exception:
                    design = {}
            campos_design = ['fundo', 'cor_fundo_custom', 'padding_vertical',
                             'largura_maxima', 'animacao_entrada', 'classe_extra']
            for campo in campos_design:
                if campo in design:
                    setattr(secao, campo, design[campo])

        # Toggle ativo
        if body.get('toggle_ativo'):
            secao.ativo = not secao.ativo

        secao.save()
        if is_ajax:
            return JsonResponse({'ok': True, 'ativo': secao.ativo})

        messages.success(request, "Secção actualizada.")
        return redirect('site:configuracao_dashboard')


class DuplicarSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """S12 — Duplica uma secção."""
    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        nova = Secao.objects.create(
            pagina=secao.pagina,
            tipo=secao.tipo,
            dados=copy.deepcopy(secao.dados),
            ordem=secao.ordem + 1,
            ativo=secao.ativo,
            fundo=secao.fundo,
            cor_fundo_custom=secao.cor_fundo_custom,
            padding_vertical=secao.padding_vertical,
            largura_maxima=secao.largura_maxima,
            animacao_entrada=secao.animacao_entrada,
            classe_extra=secao.classe_extra,
        )
        # Reordenar as que ficaram atrás
        Secao.objects.filter(
            pagina=secao.pagina, ordem__gt=secao.ordem
        ).exclude(pk=nova.pk).update(ordem=models.F('ordem') + 1)

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            return JsonResponse({'ok': True, 'id': nova.pk})
        messages.success(request, "Secção duplicada.")
        return redirect('site:configuracao_dashboard')


class EliminarSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """S12 — Elimina uma secção."""
    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        pagina_id = secao.pagina_id
        secao.delete()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            return JsonResponse({'ok': True})
        messages.success(request, "Secção eliminada.")
        return redirect('site:editor', pagina_id=pagina_id)


class ProcessarAgendamentoSiteView(View):
    """Bug 8 corrigido: sem 'empresa=' — TENANT_APP já está no schema correcto."""
    def post(self, request):
        servico_id = request.POST.get('servico_id')
        email      = request.POST.get('email', '').strip()
        nome       = request.POST.get('nome', '').strip()
        telefone   = request.POST.get('telefone', '').strip()
        data_hora  = request.POST.get('data_hora')

        if not servico_id or not email or not data_hora:
            return JsonResponse({'success': False, 'error': 'Campos obrigatórios em falta'}, status=400)

        servico = get_object_or_404(Servico, pk=servico_id, ativo=True)
        cliente, _ = Cliente.objects.get_or_create(
            email=email,
            defaults={'nome_completo': nome, 'telefone': telefone}
        )
        AgendamentoServico.objects.create(
            cliente=cliente,
            servico=servico,
            data_hora=data_hora,
            valor_cobrado=getattr(servico, 'preco', Decimal('0.00')),
            status='agendado',
        )
        return JsonResponse({'success': True, 'message': 'Agendamento registado!'})

