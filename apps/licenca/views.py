# apps/licenca/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.http import JsonResponse
from datetime import timedelta
from django.utils import timezone
from .models import Licenca, PlanoLicenca, HistoricoLicenca
from apps.empresas.models import Empresa
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
                return redirect(reverse_lazy('core:dashboard'))

        return super().dispatch(request, *args, **kwargs)




@staff_member_required
def gerar_licenca(request):
    """Gerar nova licença para empresa"""
    if request.method == 'POST':
        empresa_id = request.POST.get('empresa_id')
        plano_id = request.POST.get('plano_id')
        meses = int(request.POST.get('meses', 1))
        
        empresa = get_object_or_404(Empresa, id=empresa_id)
        plano = get_object_or_404(PlanoLicenca, id=plano_id)
        
        # Verificar se já tem licença
        if hasattr(empresa, 'licenca'):
            messages.error(request, 'Empresa já possui licença!')
            return redirect('admin:licenciamento_licenca_changelist')
        
        # Criar licença
        data_vencimento = timezone.now().date() + timedelta(days=30 * meses)
        
        licenca = Licenca.objects.create(
            empresa=empresa,
            plano=plano,
            data_vencimento=data_vencimento
        )
        
        # Registrar histórico
        HistoricoLicenca.objects.create(
            licenca=licenca,
            acao='criada',
            data_nova=data_vencimento,
            observacoes=f'Licença criada para {meses} mês(es)'
        )
        
        messages.success(request, f'Licença gerada para {empresa.nome}!')
        return redirect('admin:licenciamento_licenca_change', licenca.id)
    
    # GET - mostrar formulário
    empresas_sem_licenca = Empresa.objects.filter(licenca__isnull=True)
    planos = PlanoLicenca.objects.filter(ativo=True)
    
    return render(request, 'admin/gerar_licenca.html', {
        'empresas': empresas_sem_licenca,
        'planos': planos
    })

@staff_member_required
def renovar_licenca(request, licenca_id):
    """Renovar licença existente"""
    licenca = get_object_or_404(Licenca, id=licenca_id)
    
    if request.method == 'POST':
        meses = int(request.POST.get('meses', 1))
        
        data_anterior = licenca.data_vencimento
        licenca.renovar(meses=meses)
        
        # Registrar histórico
        HistoricoLicenca.objects.create(
            licenca=licenca,
            acao='renovada',
            data_anterior=data_anterior,
            data_nova=licenca.data_vencimento,
            observacoes=f'Renovada por {meses} mês(es)'
        )
        
        messages.success(request, f'Licença renovada até {licenca.data_vencimento}!')
        return redirect('admin:licenciamento_licenca_change', licenca.id)
    
    return render(request, 'admin/renovar_licenca.html', {'licenca': licenca})

def verificar_licenca_api(request):
    """API para verificar se licença está válida"""
    if not hasattr(request.user, 'perfilusuario'):
        return JsonResponse({'valida': False, 'motivo': 'Usuário sem perfil'})
    
    empresa = request.user.perfilusuario.empresa
    
    if not hasattr(empresa, 'licenca'):
        return JsonResponse({'valida': False, 'motivo': 'Empresa sem licença'})
    
    licenca = empresa.licenca
    
    if licenca.esta_vencida:
        return JsonResponse({'valida': False, 'motivo': 'Licença vencida'})
    
    if licenca.status != 'ativa':
        return JsonResponse({'valida': False, 'motivo': 'Licença inativa'})
    
    return JsonResponse({
        'valida': True,
        'dias_restantes': licenca.dias_para_vencer,
        'plano': licenca.plano.nome
    })


from django.views import View
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from .models import Licenca, HistoricoLicenca, PlanoLicenca
from .forms import LicencaForm, RenovacaoForm
from django.utils import timezone

class LicencaDashboardView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/dashboard.html')

class LicencaListView(View):
    def get(self, request, *args, **kwargs):
        licencas = Licenca.objects.all()
        return render(request, 'licencas/lista.html', {'licencas': licencas})

class VencimentosView(View):
    def get(self, request, *args, **kwargs):
        licencas_vencidas = Licenca.objects.filter(data_vencimento__lt=timezone.now().date())
        return render(request, 'licencas/vencimentos.html', {'licencas': licencas_vencidas})

class LicencaCreateView(View):
    def get(self, request, *args, **kwargs):
        form = LicencaForm()
        return render(request, 'licencas/form.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = LicencaForm(request.POST)
        if form.is_valid():
            licencia = form.save()
            messages.success(request, 'Licença criada com sucesso!')
            return redirect(reverse('licencas:detail', args=[licencia.pk]))
        return render(request, 'licencas/form.html', {'form': form})

class LicencaDetailView(View):
    def get(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        historico = licenca.historico.all()
        return render(request, 'licencas/detail.html', {'licenca': licenca, 'historico': historico})

class LicencaUpdateView(View):
    def get(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        form = LicencaForm(instance=licenca)
        return render(request, 'licencas/form.html', {'form': form})

    def post(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        form = LicencaForm(request.POST, instance=licenca)
        if form.is_valid():
            form.save()
            messages.success(request, 'Licença atualizada com sucesso!')
            return redirect(reverse('licencas:detail', args=[licenca.pk]))
        return render(request, 'licencas/form.html', {'form': form})

class LicencaDeleteView(View):
    def post(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        licenca.delete()
        messages.success(request, 'Licença deletada com sucesso!')
        return redirect(reverse('licencas:lista'))

class RenovarLicencaView(View):
    def get(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        form = RenovacaoForm()
        return render(request, 'licencas/renovar.html', {'form': form, 'licenca': licenca})

    def post(self, request, pk, *args, **kwargs):
        licenca = get_object_or_404(Licenca, pk=pk)
        form = RenovacaoForm(request.POST)
        if form.is_valid():
            meses = form.cleaned_data['meses']
            licenca.renovar(meses)
            HistoricoLicenca.objects.create(
                licenca=licenca,
                acao='Renovação',
                data_anterior=licenca.data_vencimento,
                data_nova=licenca.data_vencimento,
                observacoes=f'Renovação por {meses} meses'
            )
            messages.success(request, 'Licença renovada com sucesso!')
            return redirect(reverse('licencas:detail', args=[licenca.pk]))
        return render(request, 'licencas/renovar.html', {'form': form, 'licenca': licenca})

class RenovacaoListView(View):
    def get(self, request, *args, **kwargs):
        renovacoes = HistoricoLicenca.objects.all()
        return render(request, 'licencas/renovacao_lista.html', {'renovacoes': renovacoes})

class RenovacaoDetailView(View):
    def get(self, request, pk, *args, **kwargs):
        renovacao = get_object_or_404(HistoricoLicenca, pk=pk)
        return render(request, 'licencas/renovacao_detail.html', {'renovacao': renovacao})

class FinalizarRenovacaoView(View):
    def post(self, request, pk, *args, **kwargs):
        renovacao = get_object_or_404(HistoricoLicenca, pk=pk)
        # Lógica para finalizar a renovação se necessário
        messages.success(request, 'Renovação finalizada com sucesso!')
        return redirect(reverse('licencas:renovacao_lista'))

class AlertasView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/alertas.html')

class ConfigurarAlertasView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/configurar_alertas.html')

class NotificacoesView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/notificacoes.html')

class LicencaRelatoriosView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/relatorios.html')

class RelatorioComplianceView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/relatorio_compliance.html')

class RelatorioVencimentosView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/relatorio_vencimentos.html')

class RelatorioCustosView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/relatorio_custos.html')



class HistoricoLicencasView(View):
    def get(self, request, *args, **kwargs):
        historicos = HistoricoLicenca.objects.all()
        return render(request, 'licencas/historico.html', {'historicos': historicos})

class AuditoriaLicencasView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/auditoria.html')

class LogsLicencasView(View):
    def get(self, request, *args, **kwargs):
        return render(request, 'licencas/logs.html')

class VerificarStatusAPIView(View):
    def get(self, request, *args, **kwargs):
        # Implementar lógica de verificação de status
        return JsonResponse({"status": "success"})  # Exemplo de resposta

class ProximosVencimentosAPIView(View):
    def get(self, request, *args, **kwargs):
        # Implementar lógica de próximos vencimentos
        return JsonResponse({"vencimentos": []})  # Exemplo de resposta

