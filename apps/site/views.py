# apps/site/views.py
"""
Views da app site — site institucional + loja online.
"""
import json
import hashlib
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views import View
from django.views.generic import DetailView, TemplateView, CreateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin

from rest_framework import viewsets, permissions

from apps.produtos.models import Produto
from apps.servicos.models import Servico, AgendamentoServico
from apps.clientes.models import Cliente

from .models import (
    ConfiguracaoSite, Pagina, Secao,
    ProdutoSite, ServicoSite, ClienteSite,
    Carrinho, ItemCarrinho,
    PedidoOnline, ItemPedidoOnline,
    Concurso, Candidatura,
    SolicitacaoContato, Reclamacao, ComprovativoCompra,
)
from .serializers import (
    ConfiguracaoSiteSerializer, PaginaSerializer, SecaoSerializer,
    ProdutoSiteSerializer, ServicoSiteSerializer, ClienteSiteSerializer,
    CarrinhoSerializer, PedidoOnlineSerializer,
    ConcursoSerializer, CandidaturaSerializer,
    SolicitacaoContatoSerializer, ReclamacaoSerializer,
    ComprovativoCompraSerializer,
)
from .forms import CandidaturaForm


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _obter_config():
    return ConfiguracaoSite.obter()


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


# ─────────────────────────────────────────────────────────────────────────────
# API ViewSets (REST)
# ─────────────────────────────────────────────────────────────────────────────

class TenantBaseViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.queryset


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
    """Página pública do site institucional."""
    template_name = 'site/index.html'

    def get(self, request, slug=None):
        if slug:
            pagina = get_object_or_404(Pagina, slug=slug, ativo=True)
        else:
            pagina = Pagina.obter_principal()
            if not pagina:
                return render(request, 'site/em_construcao.html', _contexto_base(request))

        config = _obter_config()
        ctx = _contexto_base(request)
        ctx.update({
            'pagina':    pagina,
            'secoes':    pagina.secoes.filter(ativo=True).order_by('ordem'),
            'concursos': Concurso.objects.filter(ativo=True),
        })
        return render(request, self.template_name, ctx)


class SitePreviewView(LoginRequiredMixin, View):
    """Preview de rascunho (só para utilizadores autenticados internos)."""
    template_name = 'site/index.html'

    def get(self, request, slug, token):
        pagina = get_object_or_404(Pagina, slug=slug, preview_token=token)
        ctx = _contexto_base(request)
        ctx.update({
            'pagina':       pagina,
            'modo_preview': True,
            'secoes':       pagina.secoes.all().order_by('ordem'),
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
        quantidade = int(request.POST.get('quantidade', 1))

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

        import hashlib
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

        import hashlib
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


class ClientePerfilView(View):
    """Área pessoal do cliente — pedidos e dados."""
    template_name = 'site/cliente/perfil.html'

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
        return reverse_lazy('site:pagina_detalhe', kwargs={'slug': 'home'})


class SolicitacaoContatoCreateView(View):
    template_name = 'site/forms/contato_form.html'

    def get(self, request):
        return render(request, self.template_name, _contexto_base(request))

    def post(self, request):
        SolicitacaoContato.objects.create(
            nome=request.POST.get('nome', ''),
            email=request.POST.get('email', ''),
            telefone=request.POST.get('telefone', ''),
            mensagem=request.POST.get('mensagem', ''),
            tipo=request.POST.get('tipo', 'contato'),
        )
        messages.success(request, "Mensagem enviada com sucesso!")
        return redirect(request.META.get('HTTP_REFERER', '/'))


class ReclamacaoCreateView(View):
    template_name = 'site/forms/reclamacao_form.html'

    def get(self, request):
        return render(request, self.template_name, _contexto_base(request))

    def post(self, request):
        Reclamacao.objects.create(
            cliente_nome=request.POST.get('cliente_nome', ''),
            cliente_email=request.POST.get('cliente_email', ''),
            cliente_telefone=request.POST.get('cliente_telefone', ''),
            assunto=request.POST.get('assunto', ''),
            mensagem=request.POST.get('mensagem', ''),
        )
        messages.success(request, "Reclamação registada com sucesso.")
        return redirect(request.META.get('HTTP_REFERER', '/'))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard administrativo (editor no-code interno)
# ─────────────────────────────────────────────────────────────────────────────

class SiteConfigDashboardView(LoginRequiredMixin, View):
    """Dashboard de gestão do site para o operador interno."""
    template_name = 'site/dashboard_config.html'

    def get(self, request):
        config = _obter_config()
        try:
            from django.db import connection
            schema = connection.schema_name
            slug_default = slugify(schema)
        except Exception:
            slug_default = 'home'

        pagina, _ = Pagina.objects.get_or_create(
            slug=slug_default,
            defaults={'titulo': f"Site — {config.nome_exibicao}"}
        )

        pedidos_pendentes = PedidoOnline.objects.filter(status='pendente').count()

        return render(request, self.template_name, {
            'config':  config,
            'pagina':  pagina,
            'secoes':  pagina.secoes.all().order_by('ordem'),
            'stats': {
                'candidaturas_pendentes': Candidatura.objects.filter(status='pendente').count(),
                'contatos_novos':         SolicitacaoContato.objects.filter(atendido=False).count(),
                'reclamacoes_abertas':    Reclamacao.objects.filter(atendido=False).count(),
                'pedidos_pendentes':      pedidos_pendentes,
            },
        })


# ─── S12 Site Builder ───────────────────────────────────────────────────────

class SiteEditorView(LoginRequiredMixin, View):
    """
    S12 — Editor visual de página com drag-and-drop.
    Permite ao gestor da empresa editar o site sem saber programação.
    """
    template_name = 'site/editor.html'

    # Definição dos blocos disponíveis na barra lateral
    BLOCOS = [
        {'tipo': 'hero',        'nome': 'Hero / Banner',     'icone': 'image',          'cor': 'indigo'},
        {'tipo': 'carrossel',   'nome': 'Carrossel',         'icone': 'images',          'cor': 'yellow'},
        {'tipo': 'texto',       'nome': 'Texto Rico',        'icone': 'align-left',      'cor': 'blue'},
        {'tipo': 'card',        'nome': 'Cards',             'icone': 'th-large',        'cor': 'green'},
        {'tipo': 'produtos',    'nome': 'Vitrine Produtos',  'icone': 'store',           'cor': 'emerald'},
        {'tipo': 'servicos',    'nome': 'Vitrine Serviços',  'icone': 'concierge-bell',  'cor': 'teal'},
        {'tipo': 'cta',         'nome': 'Call-to-Action',    'icone': 'bullhorn',        'cor': 'orange'},
        {'tipo': 'galeria',     'nome': 'Galeria',           'icone': 'photo-video',     'cor': 'pink'},
        {'tipo': 'depoimentos', 'nome': 'Depoimentos',       'icone': 'quote-right',     'cor': 'purple'},
        {'tipo': 'faq',         'nome': 'Perguntas (FAQ)',   'icone': 'question-circle', 'cor': 'cyan'},
        {'tipo': 'contador',    'nome': 'Contadores',        'icone': 'sort-numeric-up', 'cor': 'red'},
        {'tipo': 'equipa',      'nome': 'Equipa',            'icone': 'users',           'cor': 'violet'},
        {'tipo': 'parceiros',   'nome': 'Parceiros/Clientes','icone': 'handshake',       'cor': 'gray'},
        {'tipo': 'video',       'nome': 'Vídeo',             'icone': 'play-circle',     'cor': 'rose'},
        {'tipo': 'formulario',  'nome': 'Formulário',        'icone': 'envelope',        'cor': 'sky'},
        {'tipo': 'localizacao', 'nome': 'Mapa',              'icone': 'map-marker-alt',  'cor': 'amber'},
        {'tipo': 'whatsapp',    'nome': 'Botão WhatsApp',    'icone': 'whatsapp fab',    'cor': 'green'},
        {'tipo': 'divider',     'nome': 'Separador',         'icone': 'minus',           'cor': 'gray'},
    ]

    def get(self, request, pagina_id=None):
        config = _obter_config()
        if pagina_id:
            pagina = get_object_or_404(Pagina, pk=pagina_id)
        else:
            slug_default = slugify(request.tenant.schema_name if hasattr(request, 'tenant') else 'home')
            pagina, _ = Pagina.objects.get_or_create(
                slug=slug_default,
                defaults={'titulo': f"Site — {config.nome_exibicao}"}
            )
        secoes = pagina.secoes.all().order_by('ordem')
        return render(request, self.template_name, {
            'config':             config,
            'pagina':             pagina,
            'secoes':             secoes,
            'blocos_disponiveis': self.BLOCOS,
        })


class AdicionarSecaoView(LoginRequiredMixin, View):
    """AJAX POST — adiciona uma nova secção à página."""
    def post(self, request, pagina_id):
        pagina = get_object_or_404(Pagina, pk=pagina_id)

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            try:
                body = json.loads(request.body)
                tipo = body.get('tipo', 'texto')
            except Exception:
                tipo = request.POST.get('tipo', 'texto')
        else:
            tipo = request.POST.get('tipo', 'texto')

        defaults_por_tipo = {
            'hero':        {'titulo': 'O Seu Título Principal', 'subtitulo': 'Frase de impacto aqui', 'texto_botao': 'Saber Mais', 'link_botao': '/loja/', 'altura_px': 500},
            'carrossel':   {'slides': [{'imagem_url': '', 'titulo': 'Slide 1', 'subtitulo': '', 'texto_botao': 'Ver mais', 'link_botao': ''}], 'autoplay': True, 'intervalo_ms': 4000, 'altura_px': 450},
            'card':        {'titulo': 'Nossos Destaques', 'colunas': '3', 'cards_json': [{'icone': 'fas fa-star', 'titulo': 'Destaque', 'texto': 'Descrição breve.', 'link': ''}]},
            'texto':       {'titulo': '', 'conteudo': '<p>Clique no botão editar para inserir o seu texto.</p>', 'alinhamento': 'esquerda'},
            'imagem_fixa': {'imagem_url': '', 'legenda': '', 'largura_total': True},
            'localizacao': {'titulo_mapa': 'A Nossa Localização', 'endereco_texto': ''},
            'whatsapp':    {'numero': '', 'mensagem': 'Olá! Vim do vosso site.', 'tooltip': 'Fale connosco'},
            'produtos':    {'titulo': 'Os Nossos Produtos', 'limite': 8, 'so_destaque': False},
            'servicos':    {'titulo': 'Os Nossos Serviços', 'limite': 6},
            'depoimentos': {'titulo': 'O Que Dizem de Nós', 'depoimentos_json': [{'nome': 'Cliente Exemplo', 'cargo': 'CEO', 'texto': 'Excelente serviço!', 'foto': ''}]},
            'faq':         {'titulo': 'Perguntas Frequentes', 'faqs_json': [{'pergunta': 'Como funciona?', 'resposta': 'É muito simples...'}]},
            'cta':         {'titulo': 'Pronto para começar?', 'descricao': 'Entre em contacto connosco.', 'texto_botao': 'Contactar', 'link_botao': '/contato/'},
            'galeria':     {'titulo': 'Galeria', 'colunas': '3', 'imagens_json': []},
            'contador':    {'titulo': 'Números que Importam', 'contadores_json': [{'numero': 100, 'sufixo': '+', 'label': 'Clientes', 'icone': 'fas fa-users'}]},
            'equipa':      {'titulo': 'A Nossa Equipa', 'membros_json': [{'nome': 'Nome Apelido', 'cargo': 'Cargo', 'foto': '', 'linkedin': ''}]},
            'parceiros':   {'titulo': 'Os Nossos Parceiros', 'logos_json': [{'url': '', 'alt': 'Parceiro', 'link': ''}]},
            'video':       {'url_video': '', 'titulo': '', 'altura_px': 450},
            'formulario':  {'titulo': 'Contacte-nos', 'campos': ['nome', 'email', 'mensagem'], 'texto_botao': 'Enviar'},
            'divider':     {'espessura': 1, 'cor': '#e5e7eb', 'margem': 'md'},
        }

        nova_secao = Secao.objects.create(
            pagina=pagina,
            tipo=tipo,
            dados=defaults_por_tipo.get(tipo, {}),
            ordem=pagina.secoes.count() + 1
        )

        if is_ajax:
            return JsonResponse({'ok': True, 'id': nova_secao.pk})

        messages.success(request, f"Secção '{nova_secao.get_tipo_display()}' adicionada.")
        return redirect('site:editor', pagina_id=pagina_id)


class PublicarSiteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pagina = get_object_or_404(Pagina, pk=pk)
        pagina.em_rascunho = False
        pagina.ativo = True
        pagina.save(update_fields=['em_rascunho', 'ativo'])
        messages.success(request, "Site publicado com sucesso!")
        return redirect('site:configuracao_dashboard')


class AtualizarDesignGlobalView(LoginRequiredMixin, View):
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


class AtualizarConfiguracaoView(LoginRequiredMixin, View):
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
        for campo in campos:
            val = request.POST.get(campo)
            if val is not None:
                # BooleanFields chegam como 'on' ou ausentes
                if hasattr(getattr(config, campo, None), '__bool__'):
                    setattr(config, campo, campo in request.POST)
                else:
                    setattr(config, campo, val)
        config.salvar()
        messages.success(request, "Configuração actualizada.")
        return redirect('site:configuracao_dashboard')


class AdicionarSecaoView(LoginRequiredMixin, View):
    def post(self, request, pagina_id):
        pagina = get_object_or_404(Pagina, pk=pagina_id)
        tipo   = request.POST.get('tipo', 'texto')
        esquemas = {
            'carrossel':   {'slides': [{'imagem_url': '', 'titulo': 'Novo Slide', 'subtitulo': '', 'texto_botao': 'Clique Aqui', 'link_botao': ''}], 'autoplay': True},
            'card':        {'titulo_secao': 'Título', 'itens': [{'icone': 'fas fa-star', 'titulo': 'Destaque', 'descricao': '...'}]},
            'texto':       {'conteudo_html': '<h2>Título</h2><p>Texto...</p>', 'fundo_claro': True},
            'imagem_fixa': {'imagem_url': '', 'legenda': '', 'largura_total': True},
            'localizacao': {'titulo_mapa': 'A Nossa Localização', 'iframe_url': '', 'endereco_texto': 'Endereço...'},
            'whatsapp':    {'numero': '', 'mensagem': 'Olá!', 'tooltip': 'Fale connosco'},
            'produtos':    {'titulo_secao': 'Os Nossos Produtos', 'mostrar_preco': True},
            'servicos':    {'titulo_secao': 'Os Nossos Serviços', 'mostrar_preco': True},
        }
        Secao.objects.create(pagina=pagina, tipo=tipo, dados=esquemas.get(tipo, {}), ordem=pagina.secoes.count() + 1)
        messages.success(request, f"Secção '{tipo}' adicionada.")
        return redirect('site:configuracao_dashboard')


class ReordenarSecoesView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'invalid json'}, status=400)

        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            # Aceita tanto {'secoes': [...]} como {'ordem': [...]}
            lista = data.get('ordem') or data.get('secoes', [])
            for item in lista:
                pk  = item.get('id') or item.get('pk')
                ord_ = item.get('ordem', item.get('posicao', 0))
                if pk is not None:
                    Secao.objects.filter(pk=pk).update(ordem=ord_)
        return JsonResponse({'ok': True})


class EditarConteudoSecaoView(LoginRequiredMixin, View):
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


class DuplicarSecaoView(LoginRequiredMixin, View):
    """S12 — Duplica uma secção."""
    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        nova = Secao.objects.create(
            pagina=secao.pagina,
            tipo=secao.tipo,
            dados=secao.dados.copy() if isinstance(secao.dados, dict) else secao.dados,
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


class EliminarSecaoView(LoginRequiredMixin, View):
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

        # Bug 8 corrigido: sem empresa= no filtro
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
