# apps/servicos/tracking_views.py
"""Staff-side tracking pages and operations; all lookups are tenant-scoped."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST
from django.db import connection

from apps.servicos.models import AgendamentoServico
from apps.servicos.tracking_models import EventoAgendamento
from apps.servicos.views import empresa_da_requisicao

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".txt"}


def _agendamento_empresa(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        return None, None
    agendamento = get_object_or_404(
        AgendamentoServico.objects.select_related("cliente", "servico", "funcionario"),
        pk=pk,
    )
    return empresa, agendamento


def _criar_evento(request, agendamento, tipo, titulo, descricao="", *, visivel=True, anexo=None, autor_cliente=None):
    from apps.servicos.tracking_services import registar_evento_agendamento
    return registar_evento_agendamento(
        agendamento=agendamento,
        tipo=tipo,
        titulo=titulo,
        descricao=descricao,
        visivel_cliente=visivel,
        autor_usuario=request.user if request.user.is_authenticated and not autor_cliente else None,
        autor_cliente_site=autor_cliente,
        anexo=anexo,
        schema_name=connection.schema_name,
    )


def _segundos_decorridos(agendamento, eventos, agora=None):
    if not agendamento.data_inicio_real:
        return 0
    agora = agora or timezone.now()
    fim = agendamento.data_fim_real or agora
    total = max(0, (fim - agendamento.data_inicio_real).total_seconds())
    pausa_aberta = None
    total_pausado = 0.0
    for evento in eventos:
        if evento.tipo == "pausado" and pausa_aberta is None:
            pausa_aberta = evento.created_at
        elif evento.tipo == "retomado" and pausa_aberta is not None:
            total_pausado += max(0, (evento.created_at - pausa_aberta).total_seconds())
            pausa_aberta = None
    if pausa_aberta is not None:
        total_pausado += max(0, (fim - pausa_aberta).total_seconds())
    return int(max(0, total - total_pausado))


def _evento_dict(evento):
    anexo_url = ""
    try:
        if evento.anexo:
            anexo_url = evento.anexo.url
    except Exception:
        logger.warning("Anexo de evento %s não tem URL disponível", evento.pk)
    return {
        "id": evento.pk,
        "tipo": evento.tipo,
        "tipo_display": evento.get_tipo_display(),
        "titulo": evento.titulo,
        "descricao": evento.descricao,
        "created_at": timezone.localtime(evento.created_at).isoformat(),
        "anexo_url": anexo_url,
        "autor": (getattr(evento.autor_cliente_site, "nome", None)
                  or (str(evento.autor_usuario) if evento.autor_usuario else "Sistema")),
    }


@login_required
def acompanhamento_agendamento(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    eventos = list(agendamento.eventos_acompanhamento.select_related("autor_usuario", "autor_cliente_site"))
    return render(request, "servicos/agendamento_acompanhamento.html", {
        "agendamento": agendamento,
        "eventos": eventos,
        "tempo_decorrido": _segundos_decorridos(agendamento, eventos),
    })


@login_required
@require_GET
def acompanhamento_eventos_api(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return JsonResponse({"success": False, "message": "Empresa não encontrada."}, status=400)
    eventos = list(agendamento.eventos_acompanhamento.select_related("autor_usuario", "autor_cliente_site"))
    return JsonResponse({
        "success": True,
        "status": agendamento.status,
        "status_display": agendamento.get_status_display(),
        "data_hora": timezone.localtime(agendamento.data_hora).isoformat(),
        "tempo_decorrido": _segundos_decorridos(agendamento, eventos),
        "eventos": [_evento_dict(evento) for evento in eventos],
    })


@login_required
@require_POST
def acompanhamento_enviar_mensagem(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    texto = request.POST.get("mensagem", "").strip()
    ficheiro = request.FILES.get("anexo")
    if not texto and not ficheiro:
        messages.error(request, "Escreva uma mensagem ou anexe um ficheiro.")
        return redirect("servicos:acompanhamento_agendamento", pk=pk)
    if ficheiro:
        name = (ficheiro.name or "").lower()
        import os
        if os.path.splitext(name)[1] not in ALLOWED_EXTENSIONS:
            messages.error(request, "Tipo de ficheiro não permitido.")
            return redirect("servicos:acompanhamento_agendamento", pk=pk)
        if ficheiro.size > MAX_UPLOAD_BYTES:
            messages.error(request, "O anexo excede o limite de 15 MB.")
            return redirect("servicos:acompanhamento_agendamento", pk=pk)
    _criar_evento(request, agendamento, "mensagem_empresa", "Mensagem da empresa", texto, anexo=ficheiro)
    messages.success(request, "Mensagem enviada ao cliente.")
    return redirect("servicos:acompanhamento_agendamento", pk=pk)


@login_required
@require_POST
def pausar_agendamento(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if agendamento.status != "em_andamento":
        messages.error(request, "Só é possível pausar um serviço em execução.")
    else:
        agendamento.status = "pausado"
        agendamento.save(update_fields=["status", "updated_at"])
        _criar_evento(request, agendamento, "pausado", "Serviço pausado", request.POST.get("motivo", "").strip())
        messages.success(request, "Serviço pausado; o cronómetro ficará suspenso.")
    return redirect("servicos:acompanhamento_agendamento", pk=pk)


@login_required
@require_POST
def retomar_agendamento(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if agendamento.status != "pausado":
        messages.error(request, "Só é possível retomar um serviço pausado.")
    else:
        agendamento.status = "em_andamento"
        agendamento.save(update_fields=["status", "updated_at"])
        _criar_evento(request, agendamento, "retomado", "Serviço retomado", request.POST.get("motivo", "").strip())
        messages.success(request, "Serviço retomado.")
    return redirect("servicos:acompanhamento_agendamento", pk=pk)


@login_required
@require_POST
def adiar_agendamento(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if agendamento.status != "agendado":
        messages.error(request, "Só é possível adiar serviços ainda agendados.")
        return redirect("servicos:acompanhamento_agendamento", pk=pk)
    nova_data = parse_datetime(request.POST.get("nova_data_hora", ""))
    if not nova_data:
        messages.error(request, "Informe uma data e hora válidas.")
        return redirect("servicos:acompanhamento_agendamento", pk=pk)
    if timezone.is_naive(nova_data):
        nova_data = timezone.make_aware(nova_data, timezone.get_current_timezone())
    if nova_data <= timezone.now():
        messages.error(request, "A nova data tem de estar no futuro.")
        return redirect("servicos:acompanhamento_agendamento", pk=pk)
    antiga = timezone.localtime(agendamento.data_hora).strftime("%d/%m/%Y %H:%M")
    agendamento.data_hora = nova_data
    agendamento.save(update_fields=["data_hora", "updated_at"])
    nova = timezone.localtime(nova_data).strftime("%d/%m/%Y %H:%M")
    _criar_evento(request, agendamento, "adiado", "Serviço adiado", f"Data anterior: {antiga}. Nova data: {nova}.")
    messages.success(request, "Agendamento adiado; o cliente será notificado por email quando o Celery estiver operacional.")
    return redirect("servicos:acompanhamento_agendamento", pk=pk)


@login_required
@require_POST
def cancelar_agendamento(request, pk):
    empresa, agendamento = _agendamento_empresa(request, pk)
    if empresa is None:
        return HttpResponseBadRequest("Empresa não encontrada.")
    if agendamento.status in {"finalizado", "cancelado", "faltou"}:
        messages.error(request, "Este agendamento já não pode ser cancelado neste estado.")
    else:
        motivo = request.POST.get("motivo", "").strip()
        agendamento.status = "cancelado"
        if hasattr(agendamento, "data_fim_real") and agendamento.data_inicio_real and not agendamento.data_fim_real:
            agendamento.data_fim_real = timezone.now()
            agendamento.save(update_fields=["status", "data_fim_real", "updated_at"])
        else:
            agendamento.save(update_fields=["status", "updated_at"])
        _criar_evento(request, agendamento, "cancelado", "Serviço cancelado", motivo or "O agendamento foi cancelado.")
        messages.success(request, "Agendamento cancelado.")
    return redirect("servicos:acompanhamento_agendamento", pk=pk)
