"""Fluxo novo de cadastro sem quota/licença paga para o parceiro.

Pode ligar esta classe à rota actual `portal-cliente-criar` depois de configurar
PARTNER_TENANT_PROVISIONER com o provisionador existente da SOTARQ.
"""
import logging
from decimal import InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.views import View
from django.db import transaction

from apps.licenca.models import PlanoLicenca
from apps.parceiros.models import Partner
from apps.parceiros.commercial_services import registar_cliente_ilimitado
from apps.parceiros.provisioning import provisionar_tenant_para_parceiro

logger = logging.getLogger("parceiros.views_unlimited")


def _partner(request):
    try:
        return request.user.partner_profile
    except (Partner.DoesNotExist, AttributeError):
        return None


def _require_active_partner(request):
    partner = _partner(request)
    if not partner:
        raise PermissionDenied("Só parceiros registados podem usar esta funcionalidade.")
    if partner.status == "inactivo":
        return None, redirect("parceiros:portal-reativacao")
    if partner.status != "activo":
        raise PermissionDenied("A conta de parceiro está suspensa ou cancelada.")
    return partner, None


class PartnerClientCreateUnlimitedView(LoginRequiredMixin, View):
    template_name = "parceiros/portal/cliente_create_unlimited.html"

    def get(self, request):
        partner, resposta = _require_active_partner(request)
        if resposta:
            return resposta
        return render(request, self.template_name, {
            "partner": partner,
            "planos_cliente": PlanoLicenca.objects.filter(ativo=True).order_by("preco_mensal"),
        })

    def post(self, request):
        partner, resposta = _require_active_partner(request)
        if resposta:
            return resposta
        try:
            plano_id = int(request.POST.get("plano_cliente_id", ""))
            meses = int(request.POST.get("meses", "1"))
            dados = {
                "nome": request.POST.get("nome", "").strip(),
                "nif": request.POST.get("nif", "").strip(),
                "email": request.POST.get("email", "").strip(),
                "telefone": request.POST.get("telefone", "").strip(),
                "dominio": request.POST.get("dominio", "").strip(),
                "observacoes": request.POST.get("observacoes", "").strip(),
            }
            if not dados["nome"] or not dados["email"]:
                raise ValidationError("Nome da empresa e email são obrigatórios.")
            # O provisionador real é obrigatório: não inventamos campos para Empresa/Domain.
            with transaction.atomic():
                empresa = provisionar_tenant_para_parceiro(dados=dados, partner=partner, request=request)
                associado = registar_cliente_ilimitado(
                    partner_id=partner.pk,
                    empresa_id=empresa.pk,
                    plano_cliente_id=plano_id,
                    criado_por=request.user,
                    ip=request.META.get("REMOTE_ADDR"),
                    meses_iniciais=meses,
                )
            messages.success(request, f"Tenant {empresa.nome} registado. A licença ficará pendente e só será activada após confirmação do pagamento pela SOTARQ.")
            return redirect("parceiros:portal-cliente-detalhe", pk=associado.pk)
        except (ImproperlyConfigured, ValidationError, ValueError, InvalidOperation, PlanoLicenca.DoesNotExist) as exc:
            logger.warning("Falha de cadastro de tenant pelo parceiro %s: %s", partner.pk, exc)
            messages.error(request, str(exc))
            return redirect(request.path)
