import json
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, CreateView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.db import transaction
from django.contrib import messages
from django.http import JsonResponse
from rest_framework import viewsets, permissions

from apps.core.views import BaseMPAView
from apps.servicos.models import AgendamentoServico, Servico
from apps.clientes.models import Cliente
from .models import (
    Pagina, Secao, Concurso, Candidatura, ProdutoSite,
    SolicitacaoContato, Reclamacao, ClienteSite, ComprovativoCompra
)
from .serializers import (
    PaginaSerializer, SecaoSerializer, ConcursoSerializer,
    CandidaturaSerializer, ProdutoSiteSerializer,
    SolicitacaoContatoSerializer, ReclamacaoSerializer,
    ClienteSiteSerializer, ComprovativoCompraSerializer
)

# ==========================================
# API VIEWSETS (MOBILE / EXTERNO)
# ==========================================
class TenantBaseViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    def get_queryset(self):
        tenant = getattr(self.request.user, "empresa", None)
        if tenant:
            return self.queryset.filter(pagina__empresa=tenant) if hasattr(self.queryset.model, "pagina") else self.queryset.filter(empresa=tenant)
        return self.queryset.none()

class PaginaViewSet(TenantBaseViewSet): queryset = Pagina.objects.all(); serializer_class = PaginaSerializer
class SecaoViewSet(TenantBaseViewSet): queryset = Secao.objects.all(); serializer_class = SecaoSerializer
class ConcursoViewSet(TenantBaseViewSet): queryset = Concurso.objects.all(); serializer_class = ConcursoSerializer
class CandidaturaViewSet(TenantBaseViewSet): queryset = Candidatura.objects.all(); serializer_class = CandidaturaSerializer
class ProdutoSiteViewSet(TenantBaseViewSet): queryset = ProdutoSite.objects.all(); serializer_class = ProdutoSiteSerializer
class SolicitacaoContatoViewSet(TenantBaseViewSet): queryset = SolicitacaoContato.objects.all(); serializer_class = SolicitacaoContatoSerializer
class ReclamacaoViewSet(TenantBaseViewSet): queryset = Reclamacao.objects.all(); serializer_class = ReclamacaoSerializer
class ClienteSiteViewSet(TenantBaseViewSet): queryset = ClienteSite.objects.all(); serializer_class = ClienteSiteSerializer
class ComprovativoCompraViewSet(TenantBaseViewSet): queryset = ComprovativoCompra.objects.all(); serializer_class = ComprovativoCompraSerializer

# ==========================================
# VIEWS PÚBLICAS (VISITANTES)
# ==========================================
class PaginaDetailView(DetailView):
    model = Pagina
    template_name = "site/index.html"
    context_object_name = "pagina"
    def get_object(self, queryset=None): return get_object_or_404(Pagina, slug=self.kwargs.get('slug'), ativo=True)
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['secoes'] = self.object.secoes.filter(ativo=True).order_by('ordem')
        context['produtos'] = self.object.produtos_site.filter(ativo=True).select_related('produto')
        context['concursos'] = self.object.concursos.filter(ativo=True)
        return context

class SitePreviewView(LoginRequiredMixin, DetailView):
    model = Pagina
    template_name = "site/index.html"
    context_object_name = "pagina"
    def get_object(self, queryset=None): return get_object_or_404(Pagina, slug=self.kwargs.get('slug'), preview_token=self.kwargs.get('token'))
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['modo_preview'] = True
        context['secoes'] = self.object.secoes.all().order_by('ordem')
        context['produtos'] = self.object.produtos_site.all().select_related('produto')
        return context

class CandidaturaCreateView(SuccessMessageMixin, CreateView):
    model = Candidatura
    fields = ['concurso', 'nome', 'email', 'telefone', 'cv', 'observacoes']
    template_name = "site/forms/candidatura_form.html"
    success_message = "Candidatura enviada com sucesso!"
    def get_success_url(self): return reverse_lazy('site:pagina_detalhe', kwargs={'slug': self.object.concurso.pagina.slug})

class SolicitacaoContatoCreateView(SuccessMessageMixin, CreateView):
    model = SolicitacaoContato
    fields = ['pagina', 'nome', 'email', 'telefone', 'mensagem', 'tipo']
    template_name = "site/forms/contato_form.html"
    success_message = "Mensagem enviada com sucesso!"
    def get_success_url(self): return reverse_lazy('site:pagina_detalhe', kwargs={'slug': self.object.pagina.slug})

class ReclamacaoCreateView(SuccessMessageMixin, CreateView):
    model = Reclamacao
    fields = ['pagina', 'cliente_nome', 'cliente_email', 'cliente_telefone', 'assunto', 'mensagem', 'documentos', 'imagens']
    template_name = "site/forms/reclamacao_form.html"
    success_message = "Reclamação registada com rigor."
    def get_success_url(self): return reverse_lazy('site:pagina_detalhe', kwargs={'slug': self.object.pagina.slug})

# ==========================================
# DASHBOARD ADMINISTRATIVO (EDITOR NO-CODE)
# ==========================================
class SiteConfigDashboardView(LoginRequiredMixin, BaseMPAView):
    template_name = "site/dashboard_config.html"
    module_name = 'site'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        pagina, _ = Pagina.objects.get_or_create(empresa=empresa, defaults={'titulo': f"Site - {empresa.nome}", 'slug': slugify(empresa.nome)})
        context.update({
            'pagina': pagina,
            'secoes': pagina.secoes.all().order_by('ordem'),
            'stats': {
                'candidaturas_pendentes': Candidatura.objects.filter(concurso__pagina=pagina, status='pendente').count(),
                'contatos_novos': SolicitacaoContato.objects.filter(pagina=pagina, atendido=False).count(),
                'reclamacoes_abertas': Reclamacao.objects.filter(pagina=pagina, atendido=False).count(),
            }
        })
        return context

class PublicarSiteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        pagina = get_object_or_404(Pagina, id=pk, empresa=request.user.empresa)
        pagina.em_rascunho = False
        pagina.ativo = True
        pagina.save()
        messages.success(request, "Site publicado com sucesso!")
        return redirect('site:configuracao_dashboard')

class AtualizarDesignGlobalView(LoginRequiredMixin, View):
    def post(self, request):
        pagina = get_object_or_404(Pagina, empresa=request.user.empresa)
        pagina.conteudo_json.update({
            'cor_primaria': request.POST.get('cor_primaria'),
            'cor_secundaria': request.POST.get('cor_secundaria'),
            'fonte': request.POST.get('fonte'),
        })
        pagina.save()
        messages.success(request, "Aparência global atualizada.")
        return redirect('site:configuracao_dashboard')

class AdicionarSecaoView(LoginRequiredMixin, View):
    def post(self, request, pagina_id):
        pagina = get_object_or_404(Pagina, id=pagina_id, empresa=request.user.empresa)
        tipo = request.POST.get('tipo')
        esquemas = {
            'carrossel': {"slides": [{"imagem_url": "", "titulo": "Novo Slide", "subtitulo": "", "texto_botao": "Clique Aqui", "link_botao": ""}], "autoplay": True},
            'card': {"titulo_secao": "Título da Seção", "itens": [{"icone": "fas fa-star", "titulo": "Destaque", "descricao": "Breve descrição"}]},
            'texto': {"conteudo_html": "<h2>Título</h2><p>Texto...</p>", "fundo_claro": True},
            'imagem_fixa': {"imagem_url": "", "legenda": "", "largura_total": True},
            'localizacao': {"titulo_mapa": "Nossa Localização", "iframe_url": "", "endereco_texto": "Endereço...", "mostrar_info_contato": True},
            'whatsapp': {"numero_whatsapp": "244", "mensagem_predefinida": "Olá!", "texto_tooltip": "Fale connosco"}
        }
        Secao.objects.create(pagina=pagina, tipo=tipo, dados=esquemas.get(tipo, {}), ordem=pagina.secoes.count() + 1)
        messages.success(request, f"Bloco de {tipo} adicionado.")
        return redirect('site:configuracao_dashboard')

class ReordenarSecoesView(LoginRequiredMixin, View):
    def post(self, request):
        data = json.loads(request.body)
        with transaction.atomic():
            for item in data.get('secoes', []):
                Secao.objects.filter(id=item['id'], pagina__empresa=request.user.empresa).update(ordem=item['posicao'])
        return JsonResponse({'status': 'success'})

class EditarConteudoSecaoView(LoginRequiredMixin, View):
    def get(self, request, secao_id):
        secao = get_object_or_404(Secao, id=secao_id, pagina__empresa=request.user.empresa)
        return JsonResponse({'status': 'success', 'dados': secao.dados, 'tipo': secao.tipo})
    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, id=secao_id, pagina__empresa=request.user.empresa)
        novos_dados = request.POST.dict()
        novos_dados.pop('csrfmiddlewaretoken', None)
        secao.dados = novos_dados
        secao.save()
        messages.success(request, "Conteúdo atualizado.")
        return redirect('site:configuracao_dashboard')

class ProcessarAgendamentoSiteView(BaseMPAView): # Herança corrigida para ter get_empresa()
    def post(self, request):
        empresa = self.get_empresa()
        servico = get_object_or_404(Servico, id=request.POST.get('servico_id'), empresa=empresa)
        cliente, _ = Cliente.objects.get_or_create(email=request.POST.get('email'), empresa=empresa, defaults={'nome': request.POST.get('nome'), 'telefone': request.POST.get('telefone')})
        AgendamentoServico.objects.create(empresa=empresa, cliente=cliente, servico=servico, data_hora=request.POST.get('data_hora'), valor_cobrado=servico.preco, status='agendado')
        return JsonResponse({'success': True, 'message': 'Registado!'})