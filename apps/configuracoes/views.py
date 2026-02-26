import json
import os
import subprocess
import zipfile
from datetime import datetime
from django.views.generic.edit import FormView
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import HttpResponse, Http404, FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import TemplateView, UpdateView, ListView, View
from django.contrib.auth.decorators import login_required
from .models import ConfiguracaoFiscal, BackupConfiguracao, PersonalizacaoInterface, HistoricoBackup
from .forms import ConfiguracaoFiscalForm, BackupConfiguracoesForm, ContactForm, PersonalizacaoInterfaceForm
from apps.empresas.models import Empresa
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView, DeleteView
from .models import DadosBancarios
from .forms import DadosBancariosForm
from django.contrib.auth.mixins import AccessMixin



class PermissaoAcaoMixin(AccessMixin):
    # CRÍTICO: Definir esta variável na View
    acao_requerida = None 

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Tenta obter o Funcionario (ligação fundamental)
            funcionario = request.user.funcionario 
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            # Usa a lógica dinâmica do modelo Funcionario (que já criámos)
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('configuracoes:dashboard')) # Redirecionamento para a Home ou Dashboard

        return super().dispatch(request, *args, **kwargs)
 


class ConfiguracoesBaseView(LoginRequiredMixin, PermissaoAcaoMixin):
    acao_requerida = 'acessar_configuracoes'
    """
    Mixin base para as views de configurações, garantindo que o utilizador
    tem uma empresa associada.
    """

    def get_empresa(self):
        user = self.request.user

        # (1) Se for um funcionário vinculado a uma empresa
        if hasattr(user, 'funcionario') and user.funcionario.empresa:
            return user.funcionario.empresa

        # (2) Se for um usuário administrador (do modelo Usuario)
        if getattr(user, 'e_administrador_empresa', False) and user.empresa:
            return user.empresa

        # (3) Se tiver empresa direta no user.empresa
        if user.empresa:
            return user.empresa

        # (4) Se não houver nenhum vínculo → None
        return None

    def dispatch(self, request, *args, **kwargs):
        if not self.get_empresa():
            messages.error(request, "Nenhuma empresa associada ao seu utilizador.")
            return redirect('core:dashboard')  # Redireciona se não houver empresa
        return super().dispatch(request, *args, **kwargs)


class ConfiguracoesDashboardView(ConfiguracoesBaseView, TemplateView):
    acao_requerida = 'acessar_configuracoes'

    template_name = 'configuracoes/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        
        context['title'] = "Painel de Configurações"
        context['config_fiscal_exists'] = ConfiguracaoFiscal.objects.filter(empresa=empresa).exists()
        context['config_backup_exists'] = BackupConfiguracao.objects.filter(empresa=empresa).exists()
        context['config_interface_exists'] = PersonalizacaoInterface.objects.filter(empresa=empresa).exists()
        context['ultimo_backup'] = HistoricoBackup.objects.filter(
            empresa=empresa, status='sucesso'
        ).order_by('-data_criacao').first()
        
        return context


class ConfiguracaoFiscalUpdateView(ConfiguracoesBaseView, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'alterar_dados_fiscais'
    model = ConfiguracaoFiscal
    form_class = ConfiguracaoFiscalForm
    template_name = 'configuracoes/fiscal.html'
    
    def get_object(self, queryset=None):
        # Usa get_or_create para garantir que a configuração sempre exista para a empresa
        obj, created = ConfiguracaoFiscal.objects.get_or_create(empresa=self.get_empresa())
        return obj

    def get_success_url(self):
        messages.success(self.request, "Configurações fiscais atualizadas com sucesso!")
        return reverse_lazy('configuracoes:fiscal_update')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Configurações Fiscais"
        return context




class PersonalizacaoInterfaceUpdateView(ConfiguracoesBaseView, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'alterar_interface'

    model = PersonalizacaoInterface
    form_class = PersonalizacaoInterfaceForm
    template_name = 'configuracoes/interface.html'

    def get_object(self, queryset=None):
        # Prioriza a configuração do utilizador; se não existir, usa/cria a da empresa
        obj, created = PersonalizacaoInterface.objects.get_or_create(
            usuario=self.request.user, 
            defaults={'empresa': self.get_empresa()}
        )
        return obj

    
    def form_valid(self, form):
        # Quando o formulário é guardado com sucesso, removemos a preferência da sessão.
        # Isto força o context_processor a ler o novo valor da BD no próximo pedido.
        if 'interface_prefs' in self.request.session:
            del self.request.session['interface_prefs']
        
        messages.success(self.request, "Preferências de interface salvas com sucesso!")
        return super().form_valid(form)

    def get_success_url(self):
        # A mensagem de sucesso foi movida para form_valid
        return reverse_lazy('configuracoes:interface')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Personalização da Interface"
        return context


class SuporteView(LoginRequiredMixin, FormView):
    template_name = 'configuracoes/suporte.html'
    form_class = ContactForm
    success_url = reverse_lazy('configuracoes:suporte')

    def get_initial(self):
        """ Pré-preenche o formulário com os dados do utilizador logado. """
        initial = super().get_initial()
        initial['nome'] = self.request.user.get_full_name()
        initial['email'] = self.request.user.email
        return initial

    def form_valid(self, form):
        """
        Esta função é executada quando o formulário é válido.
        Aqui é onde enviamos o email.
        """
        nome = form.cleaned_data['nome']
        email = form.cleaned_data['email']
        assunto = form.cleaned_data['assunto']
        mensagem = form.cleaned_data['mensagem']

        # Prepara o conteúdo do email
        corpo_email = f"""
        Nova mensagem de suporte recebida:
        -----------------------------------
        De: {nome} <{email}>
        Assunto: {assunto}
        -----------------------------------
        Mensagem:
        {mensagem}
        """

        # Envia o email
        send_mail(
            subject=f"[Suporte VistoGEST] - {assunto}",
            message=corpo_email,
            from_email=settings.DEFAULT_FROM_EMAIL, # Email remetente (configurado em settings.py)
            recipient_list=[settings.SUPPORT_EMAIL], # Email destinatário (a configurar)
            fail_silently=False,
        )

        messages.success(self.request, "A sua mensagem foi enviada com sucesso! A nossa equipa entrará em contacto em breve.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Central de Ajuda e Suporte"
        return context


class BackupConfiguracaoUpdateView(ConfiguracoesBaseView, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'atualizar_backups'

    model = BackupConfiguracao
    form_class = BackupConfiguracoesForm
    template_name = 'configuracoes/backup_config.html'

    def get_object(self, queryset=None):
        obj, created = BackupConfiguracao.objects.get_or_create(empresa=self.get_empresa())
        return obj

    def get_success_url(self):
        messages.success(self.request, "Configurações de backup atualizadas com sucesso!")
        return reverse_lazy('configuracoes:backup_config')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Configurar Backups"
        return context


class BackupListView(ConfiguracoesBaseView, PermissaoAcaoMixin, ListView):
    acao_requerida = 'ver_configuracoes'
    model = HistoricoBackup
    template_name = 'configuracoes/backup_historico.html'
    context_object_name = 'backups'
    paginate_by = 15

    def get_queryset(self):
        return HistoricoBackup.objects.filter(empresa=self.get_empresa()).order_by('-data_criacao')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Histórico de Backups"
        return context


from apps.configuracoes.services.backup_service import executar_backup

class BackupManualCreateView(ConfiguracoesBaseView, PermissaoAcaoMixin, View):
    acao_requerida = 'fazer_backup_manual'
    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        try:
            backup = executar_backup(empresa, tipo='manual', user=request.user)
            messages.success(request, f"Backup '{backup.nome_ficheiro}' criado com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao criar o backup: {e}")
        return redirect('configuracoes:backup_historico')



class BackupDownloadView(ConfiguracoesBaseView, PermissaoAcaoMixin, View):
    def get(self, request, *args, **kwargs):
        backup = get_object_or_404(HistoricoBackup, pk=kwargs['pk'], empresa=self.get_empresa())
        
        if not backup.ficheiro_backup or not os.path.exists(backup.ficheiro_backup.path):
            raise Http404("Ficheiro de backup não encontrado no servidor.")
            
        return FileResponse(open(backup.ficheiro_backup.path, 'rb'), as_attachment=True)


class BackupRestoreView(ConfiguracoesBaseView, PermissaoAcaoMixin, View):
    def post(self, request, *args, **kwargs):
        messages.warning(request, "A funcionalidade de restauração automática não está implementada por motivos de segurança. Por favor, contacte o suporte técnico para restaurar um backup.")
        return redirect('configuracoes:backup_historico')



from django.views.generic import DetailView, DeleteView
from django.urls import reverse_lazy


class ConfiguracaoFiscalDetailView(ConfiguracoesBaseView, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'acessar_detalhes_fiscal'
    """
    Exibe os detalhes da configuração fiscal da empresa logada.
    """
    model = ConfiguracaoFiscal
    template_name = 'configuracoes/fiscal_detail.html'

    def get_object(self, queryset=None):
        empresa = self.get_empresa()
        obj, created = ConfiguracaoFiscal.objects.get_or_create(empresa=empresa)
        return obj


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Detalhes Fiscais da Empresa"
        return context
    

# E a nova view para eliminar a configuração
class ConfiguracaoFiscalDeleteView(ConfiguracoesBaseView, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'eliminar_detalhes_fiscal'
    """
    Exibe a página de confirmação para eliminar as configurações fiscais.
    """
    model = ConfiguracaoFiscal
    template_name = 'configuracoes/fiscal_confirm_delete.html'
    
    def get_object(self, queryset=None):
        # Garante que só pode eliminar a sua própria configuração
        return ConfiguracaoFiscal.objects.get(empresa=self.get_empresa())
    
    def get_success_url(self):
        messages.success(self.request, "Configurações fiscais eliminadas com sucesso!")
        return reverse_lazy('configuracoes:fiscal_detail') # Redireciona de volta para a página de detalhes, que agora estará vazia.
 





class DadosBancariosCreateView(CreateView, PermissaoAcaoMixin):
    acao_requerida ='criar_dados_bancarios'
    model = DadosBancarios
    form_class = DadosBancariosForm
    template_name = 'configuracoes/dados_bancarios_form.html'
    success_url = reverse_lazy('configuracoes:fiscal_detail')

    def form_valid(self, form):
        # Associa a conta bancária à configuração fiscal da empresa logada
        config_fiscal = self.request.user.empresa.config_fiscal
        form.instance.configuracao_fiscal = config_fiscal
        return super().form_valid(form)

class DadosBancariosUpdateView(UpdateView, PermissaoAcaoMixin):
    acao_requerida ='atualizar_dados_bancarios'
    model = DadosBancarios
    form_class = DadosBancariosForm
    template_name = 'configuracoes/dados_bancarios_form.html'
    success_url = reverse_lazy('configuracoes:fiscal')

class DadosBancariosDeleteView(DeleteView, PermissaoAcaoMixin):
    acao_requerida ='apagar_dados_bancarios'
    model = DadosBancarios
    template_name = 'configuracoes/dados_bancarios_confirm_delete.html'
    success_url = reverse_lazy('configuracoes:fiscal_detail')


