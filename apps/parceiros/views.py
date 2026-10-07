# apps/parceiros/views.py
"""
Views do Portal de Parceiros — VistoGest Pro / SOTARQ Software.
Secção 6.3 do PLANO_IMPLEMENTACAO.md.

Dois grupos de views:
  A) Portal do Parceiro (/portal-parceiros/) — para o parceiro externo
  B) Área Interna SOTARQ (/admin-parceiros/) — para funcionários SOTARQ
"""
import json
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Sum, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import (
    DetailView, ListView, TemplateView, CreateView, UpdateView,
)

from .models import (
    Partner, PartnerLicense, PartnerLicensePlan, PartnerToken,
    PartnerClient, PartnerLicenseRequest, PartnerBilling, PartnerNotification,
)
from .services import PartnerService, PartnerServiceError

logger = logging.getLogger('parceiros.views')


# ─────────────────────────────────────────────────────────────────────────────
# Mixins de acesso
# ─────────────────────────────────────────────────────────────────────────────

class PartnerRequiredMixin(LoginRequiredMixin):
    """Garante que o utilizador é um parceiro activo."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        try:
            self.partner = request.user.partner_profile
        except Partner.DoesNotExist:
            messages.error(request, "Acesso negado: não é um parceiro registado.")
            return redirect('core:login')
        return super().dispatch(request, *args, **kwargs)


class SOTARQStaffRequiredMixin(LoginRequiredMixin):
    """Garante que o utilizador é staff da SOTARQ com permissões de parceiros."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            messages.error(request, "Acesso negado: área restrita a funcionários SOTARQ.")
            return redirect('core:login')
        return super().dispatch(request, *args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# A) PORTAL DO PARCEIRO
# ─────────────────────────────────────────────────────────────────────────────

class PartnerDashboardView(PartnerRequiredMixin, TemplateView):
    """Dashboard principal do parceiro com licença, quota e clientes."""
    template_name = 'parceiros/portal/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        partner = self.partner
        licenca = partner.licenca_activa
        ctx.update({
            'partner':  partner,
            'licenca':  licenca,
            'saldo':    licenca.saldo() if licenca else None,
            'clientes_activos':  partner.clientes.filter(status='activo').count(),
            'clientes_total':    partner.clientes.count(),
            'solicitacoes_pendentes': partner.solicitacoes.filter(status='pendente').count(),
            'notificacoes_nao_lidas': partner.notificacoes.filter(lida=False).count(),
            'ultimas_actividades': partner.auditorias.order_by('-created_at')[:5],
        })
        return ctx


class PartnerWalletView(PartnerRequiredMixin, TemplateView):
    """Carteira do parceiro: licença + saldo + clientes + pagamentos."""
    template_name = 'parceiros/portal/carteira.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        partner = self.partner
        licenca = partner.licenca_activa
        ctx.update({
            'partner': partner,
            'licenca': licenca,
            'saldo':   licenca.saldo() if licenca else None,
            'historico_licencas': partner.licencas.order_by('-created_at')[:10],
            'pagamentos':  partner.pagamentos.order_by('-created_at')[:10],
            'clientes_activos':  partner.clientes.filter(status='activo').count(),
            'clientes_expirados': partner.clientes.filter(status='expirado').count(),
            'clientes_pendentes': partner.clientes.filter(status='suspenso').count(),
        })
        return ctx


class PartnerClientListView(PartnerRequiredMixin, ListView):
    """Lista de clientes do parceiro."""
    template_name = 'parceiros/portal/clientes_list.html'
    context_object_name = 'clientes'
    paginate_by = 20

    def get_queryset(self):
        return self.partner.clientes.select_related(
            'empresa', 'licenca_cliente'
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['partner'] = self.partner
        return ctx


class PartnerClientDetailView(PartnerRequiredMixin, DetailView):
    """Detalhe de um cliente do parceiro."""
    template_name = 'parceiros/portal/cliente_detail.html'
    context_object_name = 'cliente'

    def get_object(self):
        return get_object_or_404(
            PartnerClient, pk=self.kwargs['pk'], partner=self.partner
        )


class PartnerClientCreateView(PartnerRequiredMixin, View):
    """Registo de novo cliente pelo parceiro."""
    template_name = 'parceiros/portal/cliente_create.html'

    def get(self, request):
        partner = self.partner
        licenca = partner.licenca_activa
        if not licenca or not licenca.esta_activa:
            messages.error(request, "Precisa de uma licença activa para registar clientes.")
            return redirect('parceiros:portal-dashboard')

        saldo = PartnerService.verificar_quota(licenca)
        if not saldo['pode_criar']:
            messages.error(request, saldo['motivo_bloqueio'])
            return redirect('parceiros:portal-clientes')

        planos_autorizados = licenca.plano.planos_cliente_autorizados.filter()
        return render(request, self.template_name, {
            'partner': partner,
            'licenca': licenca,
            'saldo': saldo,
            'planos_autorizados': planos_autorizados,
        })

    def post(self, request):
        partner = self.partner
        licenca = partner.licenca_activa
        if not licenca or not licenca.esta_activa:
            messages.error(request, "Licença inactiva.")
            return redirect('parceiros:portal-dashboard')

        plano_cliente_id = request.POST.get('plano_cliente_id')
        if not plano_cliente_id:
            messages.error(request, "Seleccione um plano de cliente.")
            return redirect(request.path)

        # Os dados da empresa já devem ter sido criados antes desta view
        # (via gerenciar_sotarq.py ou API própria) — aqui apenas vinculamos
        empresa_id = request.POST.get('empresa_id')
        if not empresa_id:
            messages.error(request, "ID da empresa é obrigatório.")
            return redirect(request.path)

        try:
            from apps.empresas.models import Empresa
            empresa = get_object_or_404(Empresa, pk=empresa_id)
            PartnerService.registar_cliente(
                partner=partner,
                empresa=empresa,
                plano_cliente_id=int(plano_cliente_id),
                criado_por=request.user,
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, f"Cliente '{empresa.nome}' registado com sucesso.")
            return redirect('parceiros:portal-clientes')
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerActivateLicenseView(PartnerRequiredMixin, View):
    """Activação da licença do parceiro com token."""
    template_name = 'parceiros/portal/activar_licenca.html'

    def get(self, request):
        return render(request, self.template_name, {'partner': self.partner})

    def post(self, request):
        token_valor = request.POST.get('token', '').strip()
        if not token_valor:
            messages.error(request, "Insira o código de activação.")
            return redirect(request.path)
        try:
            licenca = PartnerService.ativar_licenca(
                self.partner, token_valor,
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(
                request,
                f"Licença '{licenca.plano.nome}' activada. Válida até {licenca.data_expiracao}."
            )
            return redirect('parceiros:portal-dashboard')
        except (ValueError, PartnerServiceError) as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerLicenseRequestCreateView(PartnerRequiredMixin, View):
    """Pedido de plano superior / renovação."""
    template_name = 'parceiros/portal/solicitar.html'

    def get(self, request):
        planos = PartnerLicensePlan.objects.filter(ativo=True)
        return render(request, self.template_name, {
            'partner': self.partner,
            'planos': planos,
        })

    def post(self, request):
        plano_id = request.POST.get('plano_id')
        motivo   = request.POST.get('motivo', '').strip()
        tipo     = request.POST.get('tipo', 'upgrade')
        if not plano_id or not motivo:
            messages.error(request, "Plano e motivo são obrigatórios.")
            return redirect(request.path)
        try:
            req = PartnerService.solicitar_upgrade(
                partner=self.partner,
                plano_solicitado_id=int(plano_id),
                motivo=motivo,
                tipo=tipo,
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, "Solicitação enviada. Aguarde resposta da SOTARQ.")
            return redirect('parceiros:portal-solicitacoes')
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerLicenseRequestListView(PartnerRequiredMixin, ListView):
    """Histórico de solicitações do parceiro."""
    template_name = 'parceiros/portal/solicitacoes_list.html'
    context_object_name = 'solicitacoes'
    paginate_by = 20

    def get_queryset(self):
        return self.partner.solicitacoes.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['partner'] = self.partner
        return ctx


class PartnerBillingListView(PartnerRequiredMixin, ListView):
    """Histórico de pagamentos do parceiro."""
    template_name = 'parceiros/portal/pagamentos_list.html'
    context_object_name = 'pagamentos'
    paginate_by = 20

    def get_queryset(self):
        return self.partner.pagamentos.order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['partner'] = self.partner
        ctx['total_pago'] = self.partner.pagamentos.filter(
            status='pago'
        ).aggregate(t=Sum('valor'))['t'] or 0
        return ctx


class PartnerNotificationListView(PartnerRequiredMixin, View):
    """Lista e marca notificações como lidas."""
    template_name = 'parceiros/portal/notificacoes.html'

    def get(self, request):
        notifs = self.partner.notificacoes.order_by('-created_at')
        # Marcar como lidas ao visualizar
        notifs.filter(lida=False).update(lida=True, lida_em=timezone.now())
        return render(request, self.template_name, {
            'partner': self.partner,
            'notificacoes': notifs[:50],
        })


# ─────────────────────────────────────────────────────────────────────────────
# B) ÁREA INTERNA SOTARQ
# ─────────────────────────────────────────────────────────────────────────────

class PartnerAdminDashboardView(SOTARQStaffRequiredMixin, TemplateView):
    """Dashboard geral da rede de parceiros para funcionários SOTARQ."""
    template_name = 'parceiros/admin/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        ctx.update({
            'total_parceiros':      Partner.objects.count(),
            'parceiros_activos':    Partner.objects.filter(status='activo').count(),
            'parceiros_suspensos':  Partner.objects.filter(status='suspenso').count(),
            'licencas_activas':     PartnerLicense.objects.filter(status='activa').count(),
            'licencas_vencendo_30': PartnerLicense.objects.filter(
                status='activa',
                data_expiracao__lte=hoje + timezone.timedelta(days=30),
            ).count(),
            'total_clientes':       PartnerClient.objects.count(),
            'clientes_activos':     PartnerClient.objects.filter(status='activo').count(),
            'requests_pendentes':   PartnerLicenseRequest.objects.filter(status='pendente').count(),
            'faturamento_mes':      PartnerBilling.objects.filter(
                status='pago',
                data_pagamento__year=hoje.year,
                data_pagamento__month=hoje.month,
            ).aggregate(t=Sum('valor'))['t'] or 0,
        })
        return ctx


class PartnerListView(SOTARQStaffRequiredMixin, ListView):
    """Lista de parceiros para staff SOTARQ."""
    template_name   = 'parceiros/admin/parceiros_list.html'
    context_object_name = 'parceiros'
    paginate_by     = 25

    def get_queryset(self):
        qs = Partner.objects.select_related('usuario').order_by('nome')
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(nome__icontains=q) | qs.filter(nif__icontains=q)
        status_f = self.request.GET.get('status', '')
        if status_f:
            qs = qs.filter(status=status_f)
        return qs


class PartnerDetailView(SOTARQStaffRequiredMixin, DetailView):
    """Visão 360º de um parceiro: licença, quota, clientes, pagamentos, auditoria."""
    template_name = 'parceiros/admin/parceiro_detail.html'
    model         = Partner
    context_object_name = 'parceiro'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        partner = self.object
        ctx.update({
            'licenca_activa': partner.licenca_activa,
            'historico_licencas': partner.licencas.order_by('-created_at')[:10],
            'clientes': partner.clientes.select_related('empresa').order_by('-created_at')[:20],
            'solicitacoes': partner.solicitacoes.order_by('-created_at')[:10],
            'pagamentos': partner.pagamentos.order_by('-created_at')[:10],
            'auditorias': partner.auditorias.order_by('-created_at')[:20],
            'saldo': partner.licenca_activa.saldo() if partner.licenca_activa else None,
        })
        return ctx


class PartnerCreateView(SOTARQStaffRequiredMixin, View):
    """Cadastrar novo parceiro (staff SOTARQ)."""
    template_name = 'parceiros/admin/parceiro_create.html'

    def get(self, request):
        planos = PartnerLicensePlan.objects.filter(ativo=True)
        return render(request, self.template_name, {'planos': planos})

    def post(self, request):
        dados = {k: v for k, v in request.POST.items()}
        dados['password'] = dados.get('password', '')
        try:
            partner = PartnerService.criar_partner(
                dados=dados,
                criado_por=request.user,
                ip=request.META.get('REMOTE_ADDR'),
            )
            # Criar licença se plano foi seleccionado
            plano_id = request.POST.get('plano_id')
            if plano_id:
                from decimal import Decimal
                plano = PartnerLicensePlan.objects.get(pk=plano_id)
                metodo = request.POST.get('metodo_pagamento', 'numerario')
                valor  = Decimal(request.POST.get('valor_pago', str(plano.preco)))
                licenca, token_valor = PartnerService.criar_licenca(
                    partner=partner,
                    plano=plano,
                    metodo_pagamento=metodo,
                    valor_pago=valor,
                    registada_por=request.user,
                    ip=request.META.get('REMOTE_ADDR'),
                )
                messages.success(
                    request,
                    f"Parceiro criado. Token de activação: {token_valor} "
                    f"(válido 72h — entregar ao parceiro)."
                )
            else:
                messages.success(request, f"Parceiro '{partner.nome}' criado.")
            return redirect('parceiros:admin-detalhe', pk=partner.pk)
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerLicenseCreateView(SOTARQStaffRequiredMixin, View):
    """Atribuir licença a um parceiro existente."""
    template_name = 'parceiros/admin/licenca_create.html'

    def get(self, request, partner_pk):
        partner = get_object_or_404(Partner, pk=partner_pk)
        planos  = PartnerLicensePlan.objects.filter(ativo=True)
        return render(request, self.template_name, {'parceiro': partner, 'planos': planos})

    def post(self, request, partner_pk):
        partner  = get_object_or_404(Partner, pk=partner_pk)
        plano_id = request.POST.get('plano_id')
        metodo   = request.POST.get('metodo_pagamento', 'numerario')
        from decimal import Decimal
        valor = Decimal(request.POST.get('valor_pago', '0'))
        try:
            plano = PartnerLicensePlan.objects.get(pk=plano_id, ativo=True)
            licenca, token_valor = PartnerService.criar_licenca(
                partner=partner, plano=plano,
                metodo_pagamento=metodo, valor_pago=valor,
                registada_por=request.user,
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(
                request,
                f"Licença criada. Token de activação: {token_valor} (entregar ao parceiro)."
            )
            return redirect('parceiros:admin-detalhe', pk=partner.pk)
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerLicenseRequestAdminView(SOTARQStaffRequiredMixin, ListView):
    """Gerir solicitações de parceiros (staff SOTARQ)."""
    template_name = 'parceiros/admin/solicitacoes_list.html'
    context_object_name = 'solicitacoes'
    paginate_by = 25

    def get_queryset(self):
        qs = PartnerLicenseRequest.objects.select_related(
            'partner', 'plano_solicitado'
        ).order_by('-created_at')
        status_f = self.request.GET.get('status', 'pendente')
        if status_f:
            qs = qs.filter(status=status_f)
        return qs

    def post(self, request):
        """Responder a uma solicitação."""
        req_id   = request.POST.get('request_id')
        aprovado = request.POST.get('aprovado') == '1'
        resposta = request.POST.get('resposta', '').strip()
        req      = get_object_or_404(PartnerLicenseRequest, pk=req_id)
        try:
            PartnerService.responder_solicitacao(
                req, aprovado, resposta, request.user,
                ip=request.META.get('REMOTE_ADDR'),
            )
            messages.success(request, "Resposta enviada ao parceiro.")
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
        return redirect(request.path)


class PartnerBillingAdminView(SOTARQStaffRequiredMixin, TemplateView):
    """Dashboard financeiro da rede de parceiros."""
    template_name = 'parceiros/admin/faturamento.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoje = timezone.now().date()

        def total_periodo(ano, mes):
            return PartnerBilling.objects.filter(
                status='pago',
                data_pagamento__year=ano,
                data_pagamento__month=mes,
            ).aggregate(t=Sum('valor'))['t'] or 0

        ctx.update({
            'total_hoje':   PartnerBilling.objects.filter(
                status='pago', data_pagamento__date=hoje
            ).aggregate(t=Sum('valor'))['t'] or 0,
            'total_mes':    total_periodo(hoje.year, hoje.month),
            'por_metodo':   PartnerBilling.objects.filter(status='pago').values(
                'metodo'
            ).annotate(total=Sum('valor')),
            'ultimos_pagamentos': PartnerBilling.objects.filter(
                status='pago'
            ).select_related('partner').order_by('-data_pagamento')[:20],
        })
        return ctx


class PartnerTokenGenerateView(SOTARQStaffRequiredMixin, View):
    """Gerar token de activação/renovação para um parceiro."""
    template_name = 'parceiros/admin/gerar_token.html'

    def get(self, request):
        parceiros = Partner.objects.filter(status='activo')
        planos    = PartnerLicensePlan.objects.filter(ativo=True)
        return render(request, self.template_name, {'parceiros': parceiros, 'planos': planos})

    def post(self, request):
        partner_id = request.POST.get('partner_id')
        plano_id   = request.POST.get('plano_id')
        tipo       = request.POST.get('tipo', 'activacao')
        partner    = get_object_or_404(Partner, pk=partner_id)
        plano      = get_object_or_404(PartnerLicensePlan, pk=plano_id) if plano_id else None
        token_obj, token_valor = PartnerToken.gerar(
            partner=partner, tipo=tipo, plano_destino=plano, criado_por=request.user
        )
        messages.success(
            request,
            f"Token gerado: {token_valor} (válido 72h). Entregar ao parceiro de forma segura."
        )
        return redirect('parceiros:admin-parceiros')
