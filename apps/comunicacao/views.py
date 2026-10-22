"""Two-way chat with strict membership/tenant checks and an allowlist for @mentions."""
import logging
import os
import re
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.db import connection

from apps.clientes.models import Cliente
from apps.funcionarios.models import Funcionario
from apps.site.models import ClienteSite
from apps.servicos.models import AgendamentoServico
from apps.contrato_clientes.models import ContratoCliente, EventoContrato
from apps.servicos.views import empresa_da_requisicao
from .models import Conversa, ParticipanteConversa, MensagemChat

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
MENTION_RE = re.compile(r"@(contrato|servico):(\d+)", re.IGNORECASE)


def _funcionario(request):
    try:
        item = getattr(request.user, "funcionario", None)
    except Exception:
        item = None
    if item:
        return item
    return Funcionario.objects.filter(usuario=request.user, ativo=True).select_related("cargo").first()


def _tem_perm_funcionarios(request):
    if request.user.is_superuser:
        return True
    func = _funcionario(request)
    cargo = getattr(func, "cargo", None) if func else None
    return bool(func and (getattr(func, "pode_gerir_funcionarios", False) or getattr(cargo, "pode_gerir_funcionarios", False)))


def _cliente_site(request):
    pk = request.session.get("cliente_site_id")
    if not pk:
        return None
    return ClienteSite.objects.filter(pk=pk, ativo=True).first()


def _urls_mencoes(texto, conversa, request, cliente_site=None):
    """Only resolve supported, tenant-scoped references; reject arbitrary URLs/routes."""
    resultado = []
    empresa = empresa_da_requisicao(request) if request.user.is_authenticated else None
    cliente = None
    if cliente_site:
        cliente = Cliente.objects.filter(email__iexact=cliente_site.email).order_by("pk").first()
    for tipo, raw_id in MENTION_RE.findall(texto or ""):
        pk = int(raw_id)
        if tipo.lower() == "contrato":
            # Tenant-local table: schema already scopes staff queries.
            qs = ContratoCliente.objects.filter(pk=pk)
            if empresa is None and cliente:
                qs = qs.filter(cliente=cliente)
            elif empresa is None:
                continue
            contrato = qs.first()
            if contrato:
                url = (reverse("clientes:cliente_detalhe", kwargs={"pk": pk}) if cliente_site
                       else reverse("clientes:detalhe_interno", kwargs={"pk": pk}))
                resultado.append({"tipo": "contrato", "id": pk, "rotulo": f"Contrato #{pk}", "url": url})
        elif tipo.lower() == "servico":
            qs = AgendamentoServico.objects.filter(pk=pk)
            if empresa is None:
                if cliente:
                    qs = qs.filter(cliente=cliente)
                else:
                    continue
            if qs.exists():
                url = (reverse("site:cliente_servico_detalhe", kwargs={"pk": pk}) if cliente_site
                       else reverse("servicos:acompanhamento_agendamento", kwargs={"pk": pk}))
                resultado.append({"tipo": "servico", "id": pk, "rotulo": f"Serviço #{pk}", "url": url})
    return resultado


def _tem_acesso(conversa, request, cliente_site=None):
    if cliente_site:
        return (conversa.tipo == "cliente" and conversa.cliente_id is not None and
                (conversa.cliente.email or "").lower() == (cliente_site.email or "").lower())
    if not request.user.is_authenticated:
        return False
    return conversa.participantes.filter(usuario=request.user).exists()


def _msg_json(m, request, cliente_site=None):
    anexo_url = ""
    try:
        if m.anexo:
            anexo_url = m.anexo.url
    except Exception:
        pass
    return {
        "id": m.pk,
        "texto": m.texto,
        "autor": (m.autor_cliente_site.nome if m.autor_cliente_site_id else str(m.autor_usuario or "Sistema")),
        "created_at": timezone.localtime(m.created_at).isoformat(),
        "anexo_url": anexo_url,
        "mencoes": _urls_mencoes(m.texto, m.conversa, request, cliente_site),
    }


class CaixaEntradaView(View):
    template_name = "comunicacao/caixa_entrada.html"

    def get(self, request):
        cliente_site = _cliente_site(request)
        if cliente_site:
            cliente = Cliente.objects.filter(email__iexact=cliente_site.email).order_by("pk").first()
            convs = Conversa.objects.filter(tipo="cliente", cliente=cliente, ativa=True) if cliente else Conversa.objects.none()
        elif request.user.is_authenticated:
            convs = Conversa.objects.filter(participantes__usuario=request.user, ativa=True).distinct()
        else:
            return redirect("site:cliente_login")
        return render(request, self.template_name, {"conversas": convs.select_related("cliente")})


class ConversaDetalheView(View):
    template_name = "comunicacao/conversa.html"

    def _resolver(self, request, pk):
        cliente_site = _cliente_site(request)
        conversa = get_object_or_404(Conversa.objects.select_related("cliente"), pk=pk, ativa=True)
        if not _tem_acesso(conversa, request, cliente_site):
            raise PermissionDenied
        return conversa, cliente_site

    def get(self, request, pk):
        conversa, cliente_site = self._resolver(request, pk)
        mensagens_qs = conversa.mensagens.select_related("autor_usuario", "autor_cliente_site")
        mensagens = [_msg_json(m, request, cliente_site) for m in mensagens_qs]
        return render(request, self.template_name, {"conversa": conversa, "mensagens_json": mensagens, "cliente_site": cliente_site, "base_template": "site/base.html" if cliente_site else "base.html"})

    def post(self, request, pk):
        conversa, cliente_site = self._resolver(request, pk)
        texto = request.POST.get("texto", "").strip()
        ficheiro = request.FILES.get("anexo")
        if not texto and not ficheiro:
            messages.error(request, "Escreva uma mensagem ou seleccione um anexo.")
            return redirect("clientes:conversa", pk=pk)
        if ficheiro:
            if os.path.splitext((ficheiro.name or "").lower())[1] not in ALLOWED_EXTENSIONS or ficheiro.size > MAX_UPLOAD_BYTES:
                messages.error(request, "Anexo não permitido ou superior a 15 MB.")
                return redirect("clientes:conversa", pk=pk)
        with transaction.atomic():
            msg = MensagemChat.objects.create(
                conversa=conversa,
                autor_usuario=request.user if not cliente_site else None,
                autor_cliente_site=cliente_site,
                texto=texto,
                anexo=ficheiro,
                mencoes=_urls_mencoes(texto, conversa, request, cliente_site),
            )
            conversa.save(update_fields=["updated_at"])
            schema_name = connection.schema_name
            transaction.on_commit(lambda: _enfileirar_alerta_chat(schema_name, msg.pk))
        return redirect("clientes:conversa", pk=pk)


def _enfileirar_alerta_chat(schema_name, mensagem_id):
    try:
        from apps.clientes.tasks import notificar_mensagem_chat
        notificar_mensagem_chat.delay(schema_name, mensagem_id)
    except Exception:
        logger.exception("Mensagem gravada, mas não foi possível colocar o alerta na fila (mensagem=%s)", mensagem_id)


@require_GET
def mensagens_api(request, pk):
    """Polling endpoint; returns only new messages and still enforces conversation access."""
    view = ConversaDetalheView()
    conversa, cliente_site = view._resolver(request, pk)
    try:
        after_id = max(0, int(request.GET.get("after_id", "0")))
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "message": "after_id inválido."}, status=400)
    qs = conversa.mensagens.filter(pk__gt=after_id).select_related(
        "autor_usuario", "autor_cliente_site"
    ).order_by("pk")[:100]
    return JsonResponse({"success": True, "mensagens": [_msg_json(m, request, cliente_site) for m in qs]})


@login_required
@require_POST
def iniciar_conversa_cliente(request, cliente_id):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    if not (request.user.is_superuser or _funcionario(request)):
        raise PermissionDenied
    cliente = get_object_or_404(Cliente.objects.filter(ativo=True), pk=cliente_id)
    cliente_site = ClienteSite.objects.filter(email__iexact=cliente.email, ativo=True).first()
    if not cliente_site:
        messages.error(request, "Este cliente ainda não tem uma conta activa no portal do site.")
        return redirect("clientes:detalhe", pk=cliente.pk)
    conversa = Conversa.objects.filter(tipo="cliente", cliente=cliente, ativa=True).order_by("pk").first()
    if conversa is None:
        conversa = Conversa.objects.create(tipo="cliente", cliente=cliente, titulo=f"Atendimento — {cliente.nome_exibicao}", criada_por=request.user)
    ParticipanteConversa.objects.get_or_create(conversa=conversa, usuario=request.user)
    ParticipanteConversa.objects.get_or_create(conversa=conversa, cliente_site=cliente_site)
    return redirect("clientes:conversa", pk=conversa.pk)


@login_required
def criar_grupo_funcionarios(request):
    if not _tem_perm_funcionarios(request):
        raise PermissionDenied
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    if request.method == "POST":
        titulo = request.POST.get("titulo", "").strip()
        ids = request.POST.getlist("funcionarios")
        if not titulo or not ids:
            messages.error(request, "Indique um nome e pelo menos um funcionário.")
            return redirect("clientes:criar_grupo")
        # Resolve only tenant-local active employees; arbitrary user ids are never accepted.
        funcionarios = Funcionario.objects.filter(pk__in=ids, ativo=True, usuario__isnull=False)
        if not funcionarios.exists():
            messages.error(request, "Nenhum funcionário válido foi seleccionado.")
            return redirect("clientes:criar_grupo")
        conversa = Conversa.objects.create(tipo="funcionarios", titulo=titulo, criada_por=request.user)
        ParticipanteConversa.objects.get_or_create(conversa=conversa, usuario=request.user)
        for funcionario in funcionarios:
            ParticipanteConversa.objects.get_or_create(conversa=conversa, usuario=funcionario.usuario)
        messages.success(request, "Grupo de funcionários criado.")
        return redirect("clientes:conversa", pk=conversa.pk)
    funcionarios = Funcionario.objects.filter(ativo=True, usuario__isnull=False).select_related("usuario").order_by("pk")
    return render(request, "comunicacao/criar_grupo.html", {"funcionarios": funcionarios})

