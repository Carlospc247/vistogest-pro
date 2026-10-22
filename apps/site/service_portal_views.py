"""Customer-facing service timeline for the existing ClienteSite session login.

Add these views to apps/site/urls.py. They intentionally use the existing
session key instead of Django staff authentication and only return appointments
belonging to the internal Cliente matched to the logged-in ClienteSite email.
"""
import logging
import os

from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.utils.decorators import method_decorator
from django.db import connection

from apps.clientes.models import Cliente
from apps.servicos.models import AgendamentoServico
from apps.servicos.tracking_models import EventoAgendamento
from apps.servicos.tracking_views import _segundos_decorridos, _evento_dict, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS
from .models import ClienteSite

logger = logging.getLogger(__name__)


def _cliente_site_da_sessao(request):
    pk = request.session.get("cliente_site_id")
    if not pk:
        return None, None
    cliente_site = ClienteSite.objects.filter(pk=pk, ativo=True).first()
    if cliente_site is None:
        request.session.pop("cliente_site_id", None)
        return None, None
    cliente = Cliente.objects.filter(email__iexact=cliente_site.email, ativo=True, bloqueado=False).order_by("pk").first()
    return cliente_site, cliente


def _exigir_cliente(request):
    cliente_site, cliente = _cliente_site_da_sessao(request)
    if not cliente_site:
        return None, None, redirect("site:cliente_login")
    if not cliente:
        # Never use a query parameter or a submitted client id to select a client.
        return cliente_site, None, None
    return cliente_site, cliente, None


class MeusServicosView(View):
    template_name = "site/cliente/servicos.html"

    def get(self, request):
        cliente_site, cliente, response = _exigir_cliente(request)
        if response:
            return response
        agendamentos = (
            AgendamentoServico.objects.filter(cliente=cliente).select_related("servico", "funcionario").order_by("-data_hora")
            if cliente else AgendamentoServico.objects.none()
        )
        ctx = {"cliente": cliente_site, "agendamentos": agendamentos}
        return render(request, self.template_name, ctx)


class MeuServicoDetalheView(View):
    template_name = "site/cliente/servico_detalhe.html"

    def get(self, request, pk):
        cliente_site, cliente, response = _exigir_cliente(request)
        if response:
            return response
        if cliente is None:
            messages.error(request, "Não foi encontrado um registo interno associado à sua conta. Contacte a empresa.")
            return redirect("site:cliente_perfil")
        agendamento = get_object_or_404(
            AgendamentoServico.objects.select_related("servico", "cliente", "funcionario").filter(cliente=cliente),
            pk=pk,
        )
        eventos = list(agendamento.eventos_acompanhamento.filter(visivel_cliente=True).select_related("autor_usuario", "autor_cliente_site"))
        return render(request, self.template_name, {
            "cliente": cliente_site,
            "agendamento": agendamento,
            "eventos": eventos,
            "tempo_decorrido": _segundos_decorridos(agendamento, eventos),
        })


@require_GET
def meu_servico_eventos_api(request, pk):
    cliente_site, cliente, response = _exigir_cliente(request)
    if response:
        return JsonResponse({"success": False, "message": "Autenticação necessária."}, status=401)
    if cliente is None:
        return JsonResponse({"success": False, "message": "Conta sem cliente interno associado."}, status=403)
    agendamento = get_object_or_404(AgendamentoServico.objects.filter(cliente=cliente), pk=pk)
    eventos = list(agendamento.eventos_acompanhamento.filter(visivel_cliente=True).select_related("autor_usuario", "autor_cliente_site"))
    return JsonResponse({"success": True, "status": agendamento.status,
                         "status_display": agendamento.get_status_display(),
                         "data_hora": timezone.localtime(agendamento.data_hora).isoformat(),
                         "tempo_decorrido": _segundos_decorridos(agendamento, eventos),
                         "eventos": [_evento_dict(e) for e in eventos]})


@require_POST
def meu_servico_enviar_mensagem(request, pk):
    cliente_site, cliente, response = _exigir_cliente(request)
    if response:
        return response
    if cliente is None:
        messages.error(request, "A sua conta não está associada a um cliente interno.")
        return redirect("site:cliente_perfil")
    agendamento = get_object_or_404(AgendamentoServico.objects.filter(cliente=cliente), pk=pk)
    texto = request.POST.get("mensagem", "").strip()
    ficheiro = request.FILES.get("anexo")
    if not texto and not ficheiro:
        messages.error(request, "Escreva uma mensagem ou anexe um ficheiro.")
        return redirect("site:cliente_servico_detalhe", pk=pk)
    if ficheiro:
        if os.path.splitext((ficheiro.name or "").lower())[1] not in ALLOWED_EXTENSIONS:
            messages.error(request, "Tipo de ficheiro não permitido.")
            return redirect("site:cliente_servico_detalhe", pk=pk)
        if ficheiro.size > MAX_UPLOAD_BYTES:
            messages.error(request, "O anexo excede o limite de 15 MB.")
            return redirect("site:cliente_servico_detalhe", pk=pk)
    from apps.servicos.tracking_services import registar_evento_agendamento
    registar_evento_agendamento(
        agendamento=agendamento,
        tipo="mensagem_cliente",
        titulo=f"Mensagem de {cliente_site.nome}",
        descricao=texto,
        visivel_cliente=True,
        autor_cliente_site=cliente_site,
        anexo=ficheiro,
        schema_name=connection.schema_name,
    )
    messages.success(request, "Mensagem enviada à empresa.")
    return redirect("site:cliente_servico_detalhe", pk=pk)
