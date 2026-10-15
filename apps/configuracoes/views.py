import os
from django.conf import settings
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin, AccessMixin
from django.core.mail import send_mail
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView, UpdateView, ListView, FormView, DetailView, DeleteView, CreateView
from django_tenants.utils import get_public_schema_name
from .models import ConfiguracaoFiscal, BackupConfiguracao, PersonalizacaoInterface, HistoricoBackup, DadosBancarios
from .forms import ConfiguracaoFiscalForm, BackupConfiguracoesForm, ContactForm, PersonalizacaoInterfaceForm, DadosBancariosForm
from .services.backup_service import executar_backup, limpar_backups_antigos, restaurar_backup

class PermissaoAcaoMixin(AccessMixin):
    acao_requerida=None
    def dispatch(self, request,*args,**kwargs):
        if not request.user.is_authenticated: return self.handle_no_permission()
        user=request.user
        # Administradores podem gerir as configurações da sua própria empresa.
        if getattr(user,"is_superuser",False) or getattr(user,"is_staff",False) or getattr(user,"e_administrador_empresa",False):
            return super().dispatch(request,*args,**kwargs)
        if self.acao_requerida:
            funcionario=getattr(user,"funcionario",None) or getattr(user,"funcionario_relacionado",None)
            pode=getattr(funcionario,"pode_realizar_acao",None) if funcionario else None
            if callable(pode):
                if not pode(self.acao_requerida):
                    messages.error(request,"O seu cargo não permite realizar esta ação.")
                    return HttpResponseForbidden("Acesso negado.")
            elif not user.has_perm(f"configuracoes.{self.acao_requerida}"):
                messages.error(request,"Não tem permissão para realizar esta ação.")
                return HttpResponseForbidden("Acesso negado.")
        return super().dispatch(request,*args,**kwargs)

class ConfiguracoesBaseView(LoginRequiredMixin, PermissaoAcaoMixin):
    acao_requerida="acessar_configuracoes"
    def get_empresa(self):
        tenant=getattr(self.request,"tenant",None)
        if tenant and getattr(tenant,"schema_name",get_public_schema_name()) != get_public_schema_name(): return tenant
        return None
    def dispatch(self,request,*args,**kwargs):
        if not self.get_empresa():
            messages.error(request,"Aceda a esta área através do domínio da sua empresa.")
            return HttpResponseForbidden("Esta área requer um tenant.")
        return super().dispatch(request,*args,**kwargs)

def _fiscal_config():
    # Não se usa empresa=...: os dados já estão isolados pelo schema do tenant.
    defaults={"razao_social":"","nome_fantasia":"","nif":"","email":"","site":"","telefone":"","endereco":"","cidade":"","provincia":"","postal":""}
    obj, _=ConfiguracaoFiscal.objects.get_or_create(defaults=defaults)
    return obj

def _backup_config():
    obj=BackupConfiguracao.objects.first()
    return obj or BackupConfiguracao()

class ConfiguracoesDashboardView(ConfiguracoesBaseView,TemplateView):
    template_name="configuracoes/dashboard.html"
    def get_context_data(self,**kwargs):
        c=super().get_context_data(**kwargs); c["title"]="Painel de Configurações"
        c["config_fiscal_exists"]=ConfiguracaoFiscal.objects.exists(); c["config_backup_exists"]=BackupConfiguracao.objects.exists()
        c["config_interface_exists"]=PersonalizacaoInterface.objects.filter().exists()
        c["ultimo_backup"]=HistoricoBackup.objects.filter(status="sucesso").order_by("-data_criacao").first()
        return c

class ConfiguracaoFiscalUpdateView(ConfiguracoesBaseView,UpdateView):
    acao_requerida="alterar_dados_fiscais"; model=ConfiguracaoFiscal; form_class=ConfiguracaoFiscalForm; template_name="configuracoes/fiscal.html"
    def get_object(self,queryset=None): return _fiscal_config()
    def get_success_url(self): messages.success(self.request,"Dados fiscais guardados com sucesso."); return reverse_lazy("configuracoes:fiscal_detail")
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Configurações Fiscais"; return c

class ConfiguracaoFiscalDetailView(ConfiguracoesBaseView,DetailView):
    acao_requerida="acessar_detalhes_fiscal"; model=ConfiguracaoFiscal; template_name="configuracoes/fiscal_detail.html"; context_object_name="object"
    def get_object(self,queryset=None): return ConfiguracaoFiscal.objects.first()
    def get_context_data(self,**kwargs):
        c=super().get_context_data(**kwargs); c["title"]="Dados Fiscais da Empresa"
        c["dados_bancarios"]=DadosBancarios.objects.filter(configuracao_fiscal=self.object).order_by("nome_banco") if self.object else DadosBancarios.objects.none()
        return c

class ConfiguracaoFiscalDeleteView(ConfiguracoesBaseView,DeleteView):
    acao_requerida="eliminar_detalhes_fiscal"; model=ConfiguracaoFiscal; template_name="configuracoes/fiscal_confirm_delete.html"; success_url=reverse_lazy("configuracoes:fiscal_detail")
    def get_object(self,queryset=None): return get_object_or_404(ConfiguracaoFiscal.objects.all().order_by("pk"),pk=self.request.POST.get("pk") or self.kwargs.get("pk")) if self.kwargs.get("pk") else get_object_or_404(ConfiguracaoFiscal.objects.all().order_by("pk"))
    def form_valid(self,form): messages.success(self.request,"Configuração fiscal removida. Os dados bancários associados também serão removidos."); return super().form_valid(form)

class PersonalizacaoInterfaceUpdateView(ConfiguracoesBaseView,UpdateView):
    acao_requerida="alterar_interface"; model=PersonalizacaoInterface; form_class=PersonalizacaoInterfaceForm; template_name="configuracoes/interface.html"
    def get_object(self,queryset=None):
        obj,_=PersonalizacaoInterface.objects.get_or_create(defaults={"tema":"auto","cor_primaria":"#5D5CDE"})
        return obj
    def form_valid(self,form):
        
        if "interface_prefs" in self.request.session: del self.request.session["interface_prefs"]
        messages.success(self.request,"Preferências da interface guardadas.")
        return super().form_valid(form)
    def get_success_url(self): return reverse_lazy("configuracoes:interface")
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Personalização da Interface"; return c

class SuporteView(LoginRequiredMixin,FormView):
    template_name="configuracoes/suporte.html"; form_class=ContactForm; success_url=reverse_lazy("configuracoes:suporte")
    def get_initial(self):
        i=super().get_initial(); i["nome"]=self.request.user.get_full_name() or self.request.user.get_username(); i["email"]=self.request.user.email; return i
    def form_valid(self,form):
        recipient=getattr(settings,"SUPPORT_EMAIL",None)
        if not recipient:
            messages.error(self.request,"O suporte ainda não está configurado. Defina SUPPORT_EMAIL no settings.py.")
            return self.form_invalid(form)
        body=(f"Nova mensagem de suporte\n\nNome: {form.cleaned_data['nome']}\nEmail: {form.cleaned_data['email']}\nAssunto: {form.cleaned_data['assunto']}\n\n{form.cleaned_data['mensagem']}")
        try:
            send_mail(f"[Suporte VistoGEST] {form.cleaned_data['assunto']}",body,settings.DEFAULT_FROM_EMAIL,[recipient],fail_silently=False)
        except Exception:
            messages.error(self.request,"Não foi possível enviar a mensagem. Tente novamente mais tarde.")
            return self.form_invalid(form)
        messages.success(self.request,"Mensagem enviada à equipa de suporte.")
        return super().form_valid(form)
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Central de Ajuda e Suporte"; return c

class BackupConfiguracaoUpdateView(ConfiguracoesBaseView,UpdateView):
    acao_requerida="atualizar_backups"; model=BackupConfiguracao; form_class=BackupConfiguracoesForm; template_name="configuracoes/backup_config.html"
    def get_object(self,queryset=None): return _backup_config()
    def form_valid(self,form): messages.success(self.request,"Política de backups guardada."); return super().form_valid(form)
    def get_success_url(self): return reverse_lazy("configuracoes:backup_config")
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Configurar Backups"; c["ultimo_backup"]=HistoricoBackup.objects.order_by("-data_criacao").first(); return c

class BackupListView(ConfiguracoesBaseView,ListView):
    acao_requerida="ver_configuracoes"; model=HistoricoBackup; template_name="configuracoes/backup_historico.html"; context_object_name="backups"; paginate_by=20
    def get_queryset(self): return HistoricoBackup.objects.order_by("-data_criacao")
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Histórico de Backups"; return c

class BackupManualCreateView(ConfiguracoesBaseView,View):
    acao_requerida="fazer_backup_manual"
    http_method_names=["post"]
    def post(self,request,*args,**kwargs):
        try:
            backup=executar_backup(tipo="manual",user=request.user,tenant=self.get_empresa())
            messages.success(request,f"Backup '{backup.nome_ficheiro}' criado com sucesso.")
        except Exception as exc:
            messages.error(request,f"Falha na criação do backup: {exc}")
        return redirect("configuracoes:backup_historico")

class BackupDownloadView(ConfiguracoesBaseView,View):
    acao_requerida="descarregar_backup"
    def get(self,request,*args,**kwargs):
        backup=get_object_or_404(HistoricoBackup,pk=kwargs["pk"],status="sucesso")
        if not backup.ficheiro_backup or not backup.ficheiro_backup.storage.exists(backup.ficheiro_backup.name): raise Http404("Ficheiro de backup não encontrado.")
        stream=backup.ficheiro_backup.open("rb")
        return FileResponse(stream,as_attachment=True,filename=os.path.basename(backup.ficheiro_backup.name))

class BackupRestoreView(ConfiguracoesBaseView,View):
    acao_requerida="restaurar_backup"
    def post(self,request,*args,**kwargs):
        # Restauração é destrutiva: exige superuser/permissão e confirmação textual explícita.
        if not (request.user.is_superuser or request.user.has_perm("configuracoes.restore_backup")):
            return HttpResponseForbidden("Só um superutilizador ou utilizador com permissão restore_backup pode restaurar backups.")
        if request.POST.get("confirmacao") != "RESTAURAR":
            messages.error(request,"Confirmação inválida. Escreva RESTAURAR para autorizar a operação."); return redirect("configuracoes:backup_historico")
        backup=get_object_or_404(HistoricoBackup,pk=kwargs["pk"],status="sucesso")
        try:
            # Cria uma cópia de segurança do estado actual antes de sobrepor dados.
            safety_backup=executar_backup(tipo="manual",user=request.user,tenant=self.get_empresa())
            safety_name=safety_backup.ficheiro_backup.name
            safety_size=safety_backup.tamanho_ficheiro
            manifest=restaurar_backup(backup,tenant=self.get_empresa())
            # O dump restaurado pode repor um histórico antigo; regista novamente a cópia pré-restauração.
            HistoricoBackup.objects.create(
                tipo="manual", status="sucesso", data_conclusao=timezone.now(),
                ficheiro_backup=safety_name, tamanho_ficheiro=safety_size, solicitado_por=None,
                detalhes_erro=f"Cópia automática criada antes da restauração de #{kwargs['pk']}."
            )
            messages.success(request,f"Restauração concluída para o schema {manifest['schema_name']}. Foi preservada uma cópia pré-restauração no histórico.")
        except Exception as exc:
            messages.error(request,f"Não foi possível restaurar o backup: {exc}")
        return redirect("configuracoes:backup_historico")

class DadosBancariosBaseMixin(ConfiguracoesBaseView):
    def get_config_fiscal(self): return _fiscal_config()
    def get_queryset(self): return DadosBancarios.objects.filter(configuracao_fiscal=self.get_config_fiscal())

class DadosBancariosCreateView(DadosBancariosBaseMixin,CreateView):
    acao_requerida="criar_dados_bancarios"; model=DadosBancarios; form_class=DadosBancariosForm; template_name="configuracoes/dados_bancarios_form.html"; success_url=reverse_lazy("configuracoes:fiscal_detail")
    def form_valid(self,form): form.instance.configuracao_fiscal=self.get_config_fiscal(); messages.success(self.request,"Dados bancários adicionados."); return super().form_valid(form)
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Adicionar Dados Bancários"; return c

class DadosBancariosUpdateView(DadosBancariosBaseMixin,UpdateView):
    acao_requerida="atualizar_dados_bancarios"; model=DadosBancarios; form_class=DadosBancariosForm; template_name="configuracoes/dados_bancarios_form.html"; success_url=reverse_lazy("configuracoes:fiscal_detail")
    def form_valid(self,form): messages.success(self.request,"Dados bancários atualizados."); return super().form_valid(form)
    def get_context_data(self,**kwargs): c=super().get_context_data(**kwargs); c["title"]="Editar Dados Bancários"; return c

class DadosBancariosDeleteView(DadosBancariosBaseMixin,DeleteView):
    acao_requerida="apagar_dados_bancarios"; model=DadosBancarios; template_name="configuracoes/dados_bancarios_confirm_delete.html"; success_url=reverse_lazy("configuracoes:fiscal_detail")
    def form_valid(self,form): messages.success(self.request,"Dados bancários removidos."); return super().form_valid(form)
