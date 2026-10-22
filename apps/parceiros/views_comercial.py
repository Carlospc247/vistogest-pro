"""Portal de chat de parceiros e métricas comerciais; modelos globais no public."""
import os
import logging
from decimal import InvalidOperation
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction

from apps.parceiros.models import Partner
from apps.parceiros.models_comercial import (
    PartnerConversation, PartnerConversationParticipant, PartnerMessage,
)
from apps.parceiros.commercial_services import metricas_dashboard_parceiro

logger = logging.getLogger("parceiros.chat")
User = get_user_model()
MAX_ANEXO_BYTES = 15 * 1024 * 1024
EXTENSOES_PERMITIDAS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".doc", ".docx", ".xls", ".xlsx", ".txt"}


def _parceiro_do_user(user):
    try:
        return user.partner_profile
    except (Partner.DoesNotExist, AttributeError):
        return None


def _staff_pode_ver_conversas(user):
    """Permite consultar a lista de conversas, sem revelar o conteúdo das mensagens."""
    return bool(
        user.is_authenticated
        and user.is_staff
        and (user.is_superuser or user.has_perm("parceiros.view_partnerconversation"))
    )


def _staff_pode_ver_mensagens(user):
    """Permissão separada para ler mensagens e abrir anexos privados."""
    return bool(
        user.is_authenticated
        and user.is_staff
        and (user.is_superuser or user.has_perm("parceiros.view_partnermessage"))
    )


def _staff_pode_enviar_mensagens(user):
    return bool(
        user.is_authenticated
        and user.is_staff
        and (user.is_superuser or user.has_perm("parceiros.add_partnermessage"))
    )


def _pode_abrir_conversa(user, conversa):
    partner = _parceiro_do_user(user)
    if partner:
        return partner.status == "activo" and conversa.participantes.filter(partner=partner).exists()
    if not user.is_authenticated:
        return False
    # A participação/listagem não substitui a permissão de leitura; a revogação
    # de permissões deve também bloquear textos e anexos de conversas antigas.
    return _staff_pode_ver_mensagens(user)


def _serializar_mensagem(msg):
    autor = msg.autor_partner.nome if msg.autor_partner_id else (str(msg.autor_usuario) if msg.autor_usuario_id else "Sistema")
    return {
        "id": msg.pk,
        "autor": autor,
        "texto": msg.texto,
        "created_at": timezone.localtime(msg.created_at).isoformat(),
        "anexo_nome": msg.nome_original_anexo or (os.path.basename(msg.anexo.name) if msg.anexo else ""),
        "anexo_download_url": reverse("parceiros:mensagem_anexo", kwargs={"pk": msg.pk}) if msg.anexo else "",
        "comissao_id": msg.comissao_id,
    }


class PartnerChatInboxView(LoginRequiredMixin, View):
    template_name = "parceiros/chat/inbox.html"

    def get(self, request):
        partner = _parceiro_do_user(request.user)
        if partner:
            if partner.status == "inactivo":
                return redirect("parceiros:portal-reativacao")
            if partner.status != "activo":
                raise PermissionDenied("A conta de parceiro está suspensa ou cancelada.")
            qs = PartnerConversation.objects.filter(participantes__partner=partner, ativa=True).distinct()
        elif _staff_pode_ver_conversas(request.user) or _staff_pode_ver_mensagens(request.user):
            # A lista mostra metadados. O detalhe/anexos continua protegido por view_partnermessage.
            qs = PartnerConversation.objects.filter(ativa=True)
        elif request.user.is_staff:
            qs = PartnerConversation.objects.filter(participantes__usuario=request.user, ativa=True).distinct()
        else:
            raise PermissionDenied
        return render(request, self.template_name, {"conversas": qs.order_by("-ultimo_evento_em")[:200], "partner": partner})


class PartnerChatCreateView(LoginRequiredMixin, View):
    template_name = "parceiros/chat/criar.html"

    def get(self, request):
        partner = _parceiro_do_user(request.user)
        if partner and partner.status == "inactivo":
            return redirect("parceiros:portal-reativacao")
        if partner and partner.status != "activo":
            raise PermissionDenied("Conta de parceiro suspensa ou cancelada.")
        if not partner and not (request.user.is_superuser or request.user.has_perm("parceiros.add_partnerconversation")):
            raise PermissionDenied("Sem permissão para iniciar conversas de parceiros.")
        return render(request, self.template_name, {
            "partner": partner,
            "outros_parceiros": Partner.objects.filter(status="activo").exclude(pk=getattr(partner, "pk", None)).order_by("nome"),
            "funcionarios": User.objects.filter(is_staff=True, is_active=True).order_by("username")[:200],
        })

    def post(self, request):
        partner = _parceiro_do_user(request.user)
        if partner and partner.status == "inactivo":
            return redirect("parceiros:portal-reativacao")
        if partner and partner.status != "activo":
            raise PermissionDenied("Conta de parceiro suspensa ou cancelada.")
        if not partner and not (request.user.is_superuser or request.user.has_perm("parceiros.add_partnerconversation")):
            raise PermissionDenied("Sem permissão para iniciar conversas de parceiros.")
        tipo = request.POST.get("tipo", "partner_staff")
        titulo = request.POST.get("titulo", "").strip()[:180]
        if not titulo:
            messages.error(request, "Indique o assunto da conversa.")
            return redirect(request.path)

        if partner:
            if tipo == "partner_partner":
                outro = get_object_or_404(Partner, pk=request.POST.get("partner_id"), status="activo")
                if outro.pk == partner.pk:
                    messages.error(request, "Escolha outro parceiro.")
                    return redirect(request.path)
            elif tipo == "partner_staff":
                outro_staff = get_object_or_404(User, pk=request.POST.get("usuario_id"), is_staff=True, is_active=True)
                tipo = "partner_staff"
            else:
                raise PermissionDenied
        else:
            outro = get_object_or_404(Partner, pk=request.POST.get("partner_id"), status="activo")
            tipo = "partner_staff"

        with transaction.atomic():
            conversa = PartnerConversation.objects.create(tipo=tipo, titulo=titulo, criada_por=request.user, ultimo_evento_em=timezone.now())
            if partner:
                PartnerConversationParticipant.objects.create(conversa=conversa, partner=partner)
                if tipo == "partner_partner":
                    PartnerConversationParticipant.objects.create(conversa=conversa, partner=outro)
                else:
                    PartnerConversationParticipant.objects.create(conversa=conversa, usuario=outro_staff)
            else:
                PartnerConversationParticipant.objects.create(conversa=conversa, usuario=request.user)
                PartnerConversationParticipant.objects.create(conversa=conversa, partner=outro)
        return redirect("parceiros:chat_detalhe", pk=conversa.pk)


class PartnerChatDetailView(LoginRequiredMixin, View):
    template_name = "parceiros/chat/detalhe.html"

    def get_conversa(self, request, pk):
        conversa = get_object_or_404(PartnerConversation, pk=pk, ativa=True)
        if not _pode_abrir_conversa(request.user, conversa):
            raise PermissionDenied
        return conversa

    def get(self, request, pk):
        conversa = self.get_conversa(request, pk)
        mensagens_qs = conversa.mensagens.select_related("autor_partner", "autor_usuario", "comissao").order_by("created_at")[:500]
        return render(request, self.template_name, {"conversa": conversa, "mensagens": [_serializar_mensagem(m) for m in mensagens_qs], "partner": _parceiro_do_user(request.user)})

    def post(self, request, pk):
        partner = _parceiro_do_user(request.user)
        conversa = get_object_or_404(PartnerConversation, pk=pk, ativa=True)
        participante_staff = conversa.participantes.filter(usuario=request.user).exists()
        # Um funcionário autorizado pode responder a um atendimento partner_staff sem
        # precisar ser previamente participante; não pode intervir em conversa privada
        # partner_partner sem convite explícito.
        resposta_staff_autorizada = bool(
            partner is None
            and _staff_pode_ver_mensagens(request.user)
            and _staff_pode_enviar_mensagens(request.user)
            and conversa.tipo == "partner_staff"
        )
        if not _pode_abrir_conversa(request.user, conversa) and not resposta_staff_autorizada:
            raise PermissionDenied
        if partner is None and not _staff_pode_enviar_mensagens(request.user):
            raise PermissionDenied("Tem acesso de leitura, mas não tem permissão para enviar mensagens.")
        ficheiro = request.FILES.get("anexo")
        texto = request.POST.get("texto", "").strip()
        if not texto and not ficheiro:
            messages.error(request, "Escreva uma mensagem ou anexe um ficheiro.")
            return redirect("parceiros:chat_detalhe", pk=pk)
        if ficheiro:
            ext = os.path.splitext((ficheiro.name or "").lower())[1]
            if ext not in EXTENSOES_PERMITIDAS or ficheiro.size > MAX_ANEXO_BYTES:
                messages.error(request, "Ficheiro não permitido ou superior a 15 MB.")
                return redirect("parceiros:chat_detalhe", pk=pk)
        if partner is None and not conversa.participantes.filter(usuario=request.user).exists():
            if conversa.tipo == "partner_partner":
                raise PermissionDenied("A equipa pode consultar conversas entre parceiros, mas não participar nelas sem convite.")
            if not resposta_staff_autorizada:
                raise PermissionDenied("Não participa nesta conversa.")
        comissao = None
        comissao_id = request.POST.get("comissao_id", "").strip()
        if comissao_id:
            from apps.parceiros.models_comercial import PartnerCommission
            qs = PartnerCommission.objects.filter(pk=comissao_id)
            if partner:
                qs = qs.filter(partner=partner)
            comissao = get_object_or_404(qs)
        with transaction.atomic():
            if partner is None and not conversa.participantes.filter(usuario=request.user).exists():
                PartnerConversationParticipant.objects.get_or_create(conversa=conversa, usuario=request.user)
            msg = PartnerMessage.objects.create(
                conversa=conversa,
                autor_partner=partner,
                autor_usuario=None if partner else request.user,
                texto=texto,
                anexo=ficheiro,
                nome_original_anexo=os.path.basename(ficheiro.name)[:255] if ficheiro else "",
                tipo_conteudo_anexo=getattr(ficheiro, "content_type", "")[:120] if ficheiro else "",
                comissao=comissao,
            )
            conversa.ultimo_evento_em = timezone.now()
            conversa.save(update_fields=["ultimo_evento_em", "updated_at"])
            # Os eventos são globais e visíveis à equipa SOTARQ, não ao parceiro no feed comercial.
            participantes_parceiros = conversa.participantes.filter(
                partner__isnull=False
            ).select_related("partner")
            owner_participante = participantes_parceiros.first()
            partner_event_owner = partner or (owner_participante.partner if owner_participante else None)
            if partner_event_owner is not None:
                from apps.parceiros.commercial_services import _criar_evento
                _criar_evento(
                    partner_event_owner,
                    "alerta_staff",
                    f"partner_chat_msg:{msg.pk}",
                    "Nova mensagem no chat de parceiros",
                    f"Nova mensagem na conversa #{conversa.pk}; anexo: {'sim' if bool(ficheiro) else 'não'}.",
                    dados={"conversa_id": conversa.pk, "mensagem_id": msg.pk, "tem_anexo": bool(ficheiro), "comissao_id": comissao.pk if comissao else None},
                    visivel=False,
                )
            else:
                logger.error("Mensagem de chat %s sem parceiro participante; verificar o tipo da conversa.", msg.pk)
            transaction.on_commit(lambda: _enfileirar_notificacao_parceiro(msg.pk))
        messages.success(request, "Mensagem enviada.")
        return redirect("parceiros:chat_detalhe", pk=pk)


def _enfileirar_notificacao_parceiro(mensagem_id):
    try:
        from apps.parceiros.tasks import notificar_mensagem_parceiro
        notificar_mensagem_parceiro.delay(mensagem_id)
    except Exception:
        logger.exception("Mensagem de parceiro guardada, mas não foi possível enfileirar alerta (%s).", mensagem_id)


class PartnerMessageAttachmentView(LoginRequiredMixin, View):
    """Entrega ficheiros apenas após autorização de participação/permissão staff."""
    def get(self, request, pk):
        msg = get_object_or_404(PartnerMessage.objects.select_related("conversa"), pk=pk)
        if not _pode_abrir_conversa(request.user, msg.conversa):
            raise PermissionDenied
        if not msg.anexo:
            raise Http404("Esta mensagem não tem anexo.")
        try:
            ficheiro = msg.anexo.open("rb")
        except Exception as exc:
            logger.exception("Não foi possível abrir anexo da mensagem %s.", pk)
            raise Http404("Anexo indisponível.") from exc
        nome = os.path.basename(msg.nome_original_anexo or msg.anexo.name or f"anexo-{pk}")
        resposta = FileResponse(ficheiro, as_attachment=True, filename=nome)
        resposta["X-Content-Type-Options"] = "nosniff"
        resposta["Cache-Control"] = "private, no-store"
        return resposta


class PartnerDashboardComercialMixin:
    """Snippet mixin: acrescenta métricas sem mudar o resto do dashboard."""
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        partner = getattr(self, "partner", None)
        if partner:
            ctx["metricas_comerciais"] = metricas_dashboard_parceiro(partner)
        return ctx


class _PartnerPortalMixin(LoginRequiredMixin):
    """Gate central: inactivo pode pedir reactivação, mas não navegar no portal."""
    def dispatch(self, request, *args, **kwargs):
        self.partner = _parceiro_do_user(request.user)
        if self.partner is None:
            # As views internas da SOTARQ têm URLConf e permissões próprios.
            # Não permitir que staff use rotas do portal externo sem perfil Partner.
            raise PermissionDenied("Esta conta não é um parceiro registado.")
        if self.partner.status == "inactivo":
            return redirect("parceiros:portal-reativacao")
        if self.partner.status != "activo":
            raise PermissionDenied("A conta de parceiro está suspensa ou cancelada.")
        return super().dispatch(request, *args, **kwargs)


class PartnerClientListComercialView(_PartnerPortalMixin, View):
    template_name = "parceiros/portal/clientes_comercial.html"

    def get(self, request):
        from datetime import timedelta
        from apps.parceiros.models import PartnerClient
        hoje = timezone.localdate()
        qs = PartnerClient.objects.filter(partner=self.partner).select_related("empresa", "licenca_cliente").order_by("-created_at")
        status = request.GET.get("status", "").strip()
        if status in {"activo", "expirado", "suspenso", "cancelado"}:
            qs = qs.filter(status=status)
        vencimento = request.GET.get("vencimento", "").strip()
        if vencimento == "30dias":
            qs = qs.filter(licenca_cliente__status="ativa", licenca_cliente__data_vencimento__gte=hoje, licenca_cliente__data_vencimento__lte=hoje + timedelta(days=30))
        elif vencimento == "expiradas":
            qs = qs.filter(licenca_cliente__data_vencimento__lt=hoje)
        query = request.GET.get("q", "").strip()
        if query:
            qs = qs.filter(empresa__nome__icontains=query)
        return render(request, self.template_name, {"partner": self.partner, "clientes": qs[:500], "status_filter": status, "vencimento_filter": vencimento, "query": query})


class PartnerDashboardComercialView(_PartnerPortalMixin, View):
    template_name = "parceiros/portal/dashboard_comercial.html"

    def get(self, request):
        from apps.parceiros.commercial_services import metricas_dashboard_parceiro
        from apps.parceiros.models import PartnerClient
        partner = self.partner
        ctx = metricas_dashboard_parceiro(partner)
        from apps.parceiros.commercial_services import tempo_status_partner, ultima_atividade_comercial
        ultima_atividade = ultima_atividade_comercial(partner)
        data_ultima = timezone.localtime(ultima_atividade).date() if ultima_atividade else partner.created_at.date()
        ctx.update({
            "partner": partner,
            "clientes_recentes": PartnerClient.objects.filter(partner=partner).select_related("empresa", "licenca_cliente").order_by("-created_at")[:10],
            "dias_sem_atividade": max(0, (timezone.localdate() - data_ultima).days),
            **tempo_status_partner(partner),
        })
        return render(request, self.template_name, ctx)


class PartnerClientRenewLicenseView(_PartnerPortalMixin, View):
    template_name = "parceiros/portal/renovar_cliente.html"

    def _cliente(self, request, pk):
        from apps.parceiros.models import PartnerClient
        return get_object_or_404(
            PartnerClient.objects.select_related("empresa", "licenca_cliente"),
            pk=pk, partner=self.partner,
        )

    def get(self, request, pk):
        cliente = self._cliente(request, pk)
        return render(request, self.template_name, {"partner": self.partner, "cliente": cliente})

    def post(self, request, pk):
        from apps.parceiros.commercial_services import renovar_licenca_cliente
        cliente = self._cliente(request, pk)
        try:
            meses = int(request.POST.get("meses", "1"))
            # A base de cálculo vem do preço oficial do plano; a SOTARQ reconcilia
            # o pagamento. O parceiro não pode definir a própria comissão por POST.
            referencia = request.POST.get("referencia_pagamento", "").strip()
            renovar_licenca_cliente(
                partner_id=self.partner.pk,
                partner_client_id=cliente.pk,
                meses=meses,
                executado_por=request.user,
                ip=request.META.get("REMOTE_ADDR"),
                referencia_pagamento=referencia,
            )
            messages.success(request, "Pedido de renovação registado. O prazo só será actualizado após confirmação do pagamento pela equipa SOTARQ.")
            return redirect("parceiros:portal-cliente-detalhe", pk=cliente.pk)
        except (ValueError, InvalidOperation, ValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(request.path)


class PartnerCommissionWalletView(_PartnerPortalMixin, View):
    template_name = "parceiros/portal/carteira_comercial.html"

    def get(self, request):
        from django.db.models import Sum
        from apps.parceiros.models_comercial import PartnerCommission
        partner = self.partner
        qs = PartnerCommission.objects.filter(partner=partner).select_related("partner_client", "licenca_cliente").order_by("-created_at")
        return render(request, self.template_name, {
            "partner": partner, "comissoes": qs[:200],
            "previsto": qs.filter(status="aguarda_confirmacao").aggregate(v=Sum("valor_comissao"))["v"] or 0,
            "confirmado": qs.filter(status="confirmada").aggregate(v=Sum("valor_comissao"))["v"] or 0,
            "pago": qs.filter(status="paga").aggregate(v=Sum("valor_comissao"))["v"] or 0,
        })


class PartnerReactivationRequestView(LoginRequiredMixin, View):
    """Única área do portal permitida ao parceiro inactivo para pedir reactivação."""
    template_name = "parceiros/portal/reativacao.html"

    def _partner(self, request):
        partner = _parceiro_do_user(request.user)
        if partner is None:
            raise PermissionDenied("Apenas um parceiro pode pedir reactivação.")
        return partner

    def get(self, request):
        from apps.parceiros.models_comercial import PartnerReactivationRequest
        partner = self._partner(request)
        pedidos = partner.pedidos_reativacao.order_by("-created_at")[:20]
        return render(request, self.template_name, {"partner": partner, "pedidos": pedidos})

    def post(self, request):
        from apps.parceiros.models_comercial import PartnerReactivationRequest, PartnerBusinessEvent
        from apps.parceiros.models import PartnerAudit
        from django.db import transaction
        partner = self._partner(request)
        motivo = request.POST.get("motivo", "").strip()
        if partner.status != "inactivo":
            raise PermissionDenied("Só parceiros inactivos podem pedir reactivação.")
        if len(motivo) < 20:
            messages.error(request, "Descreva o motivo com pelo menos 20 caracteres.")
            return redirect("parceiros:portal-reativacao")
        if partner.pedidos_reativacao.filter(status="pendente").exists():
            messages.info(request, "Já existe um pedido de reactivação pendente.")
            return redirect("parceiros:portal-reativacao")
        with transaction.atomic():
            pedido = PartnerReactivationRequest.objects.create(partner=partner, motivo=motivo)
            PartnerAudit.objects.create(
                partner=partner, acao="PARTNER_REACTIVATION_REQUESTED", objeto_tipo="PartnerReactivationRequest",
                objeto_id=str(pedido.pk), executado_por=request.user, origem="portal",
                valor_novo={"pedido_id": pedido.pk, "motivo": motivo[:300]},
            )
            evento = PartnerBusinessEvent.objects.create(
                partner=partner, tipo="alerta_staff", chave_evento=f"reativacao_pedido:{pedido.pk}",
                titulo="Pedido de reactivação recebido", descricao=f"O parceiro {partner.nome} solicitou reactivação.",
                dados={"pedido_id": pedido.pk}, visivel_parceiro=False,
            )
            transaction.on_commit(lambda: _enfileirar_notificacao_evento(evento.pk))
        messages.success(request, "Pedido enviado. Apenas o superuser SOTARQ pode aprovar a reactivação.")
        return redirect("parceiros:portal-reativacao")


def _enfileirar_notificacao_evento(evento_id):
    try:
        from apps.parceiros.tasks import notificar_evento_comercial_staff
        notificar_evento_comercial_staff.delay(evento_id)
    except Exception:
        logger.exception("Pedido de reactivação guardado; email de alerta não enfileirado (%s).", evento_id)


class PartnerStaffDashboardComercialView(LoginRequiredMixin, View):
    template_name = "parceiros/admin/dashboard_comercial.html"

    def get(self, request):
        pode_ver_financeiro = request.user.is_superuser or (
            request.user.is_staff
            and request.user.has_perm("parceiros.view_partnerbusinessevent")
            and request.user.has_perm("parceiros.view_partnercommission")
        )
        if not pode_ver_financeiro:
            raise PermissionDenied("Precisa das permissões de visualização de eventos comerciais e comissões.")
        from apps.parceiros.commercial_services import metricas_dashboard_staff
        return render(request, self.template_name, metricas_dashboard_staff())


class PartnerListComercialView(LoginRequiredMixin, View):
    """Lista interna de parceiros; métricas financeiras/clientes respeitam permissões próprias."""
    template_name = "parceiros/admin/parceiros_list_comercial.html"

    def get(self, request):
        from django.db.models import Q, Count, Sum
        from apps.parceiros.models import Partner
        from apps.parceiros.models_comercial import PartnerCommission
        if not (request.user.is_superuser or request.user.has_perm("parceiros.view_partner")):
            raise PermissionDenied("Sem permissão para consultar parceiros.")
        pode_ver_clientes = request.user.is_superuser or request.user.has_perm("parceiros.view_partnerclient")
        pode_ver_comissoes = request.user.is_superuser or request.user.has_perm("parceiros.view_partnercommission")
        qs = Partner.objects.select_related("usuario").order_by("nome")
        if pode_ver_clientes:
            qs = qs.annotate(total_clientes_db=Count("clientes", distinct=True))
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(email__icontains=q) | Q(nif__icontains=q) | Q(usuario__username__icontains=q))
        estado = request.GET.get("status", "").strip()
        if estado in {"activo", "inactivo", "suspenso", "cancelado"}:
            qs = qs.filter(status=estado)
        parceiros = list(qs[:500])
        for p in parceiros:
            p.total_clientes_db = getattr(p, "total_clientes_db", None)
            p.comissao_confirmada_total = (
                PartnerCommission.objects.filter(partner=p, status="confirmada").aggregate(v=Sum("valor_comissao"))["v"] or 0
                if pode_ver_comissoes else None
            )
        return render(request, self.template_name, {
            "parceiros": parceiros, "query": q, "status_filter": estado,
            "pode_ver_clientes": pode_ver_clientes, "pode_ver_comissoes": pode_ver_comissoes,
            "pode_criar_partner": request.user.is_superuser or request.user.has_perm("parceiros.add_partner"),
        })


class PartnerAdminDetailComercialView(LoginRequiredMixin, View):
    template_name = "parceiros/admin/parceiro_detail_comercial.html"

    def get(self, request, pk):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.view_partner")):
            raise PermissionDenied("Sem permissão para consultar parceiros.")
        from apps.parceiros.models import Partner, PartnerClient
        from apps.parceiros.models_comercial import PartnerCommission, PartnerBusinessEvent, PartnerConversation
        partner = get_object_or_404(Partner, pk=pk)
        pode_ver_clientes = request.user.is_superuser or request.user.has_perm("parceiros.view_partnerclient")
        pode_ver_comissoes = request.user.is_superuser or request.user.has_perm("parceiros.view_partnercommission")
        pode_ver_eventos = request.user.is_superuser or request.user.has_perm("parceiros.view_partnerbusinessevent")
        pode_ver_conversas = request.user.is_superuser or request.user.has_perm("parceiros.view_partnerconversation") or request.user.has_perm("parceiros.view_partnermessage")
        pode_ver_reativacao = request.user.is_superuser or request.user.has_perm("parceiros.view_partnerreactivationrequest")
        return render(request, self.template_name, {
            "parceiro": partner,
            "clientes": PartnerClient.objects.filter(partner=partner).select_related("empresa", "licenca_cliente", "criado_por").order_by("-created_at")[:500] if pode_ver_clientes else [],
            "comissoes": PartnerCommission.objects.filter(partner=partner).select_related("partner_client", "confirmado_por").order_by("-created_at")[:100] if pode_ver_comissoes else [],
            "eventos": PartnerBusinessEvent.objects.filter(partner=partner).select_related("partner_client", "licenca_cliente").order_by("-created_at")[:100] if pode_ver_eventos else [],
            "conversas": PartnerConversation.objects.filter(participantes__partner=partner).distinct().order_by("-ultimo_evento_em")[:100] if pode_ver_conversas else [],
            "pedidos_reativacao": partner.pedidos_reativacao.order_by("-created_at")[:20] if pode_ver_reativacao else [],
            "pode_ver_clientes": pode_ver_clientes,
            "pode_ver_comissoes": pode_ver_comissoes,
            "pode_ver_eventos": pode_ver_eventos,
            "pode_ver_conversas": pode_ver_conversas,
            "pode_ver_reativacao": pode_ver_reativacao,
        })


class PartnerCreateComercialView(LoginRequiredMixin, View):
    template_name = "parceiros/admin/parceiro_create_comercial.html"

    def get(self, request):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.add_partner")):
            raise PermissionDenied("Sem permissão para criar parceiros.")
        return render(request, self.template_name)

    def post(self, request):
        if not (request.user.is_superuser or request.user.has_perm("parceiros.add_partner")):
            raise PermissionDenied("Sem permissão para criar parceiros.")
        from apps.parceiros.services import PartnerService, PartnerServiceError
        dados = {
            "nome": request.POST.get("nome", "").strip(),
            "tipo": request.POST.get("tipo", "empresa"),
            "nif": request.POST.get("nif", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "telefone": request.POST.get("telefone", "").strip(),
            "endereco": request.POST.get("endereco", "").strip(),
            "username": request.POST.get("username", "").strip(),
            "password": request.POST.get("password", ""),
            "observacoes": request.POST.get("observacoes", "").strip(),
        }
        confirmar = request.POST.get("confirmar_password", "")
        if dados["password"] != confirmar:
            messages.error(request, "As passwords não coincidem.")
            return redirect(request.path)
        try:
            partner = PartnerService.criar_partner(dados=dados, criado_por=request.user, ip=request.META.get("REMOTE_ADDR"))
            messages.success(request, f"Parceiro {partner.nome} criado sem subscrição paga nem quota de tenants.")
            return redirect("parceiros_admin:admin-detalhe", pk=partner.pk)
        except PartnerServiceError as exc:
            messages.error(request, str(exc))
            return redirect(request.path)
