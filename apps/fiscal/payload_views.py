# apps/fiscal/payload_views.py
"""Painel de consulta dos payloads AGT — leitura, auditoria e download."""
import json

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, View

from django_tenants.utils import get_public_schema_name

from apps.fiscal.models_payload_agt import (
    PayloadAGT,
    EventoAuditoriaPayloadAGT,
    AuditoriaPayloadAGT,
    ControloSubmissaoAGT,
)


# ============================================================================
# PERMISSÕES E PROTECÇÃO MULTI-TENANT
# ============================================================================

class PermissaoAcaoMixin(AccessMixin):
    """
    Exige utilizador autenticado, funcionário associado e permissão da acção.

    O Inspector é exclusivamente tenant-local. Nunca deve consultar
    PayloadAGT ou os respectivos eventos no schema public.
    """

    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            funcionario = request.user.funcionario
        except Exception:
            messages.error(
                request,
                "Acesso negado. O utilizador não está ligado a um funcionário.",
            )
            return self.handle_no_permission()

        if self.acao_requerida:
            if (
                not funcionario
                or not funcionario.pode_realizar_acao(self.acao_requerida)
            ):
                messages.error(
                    request,
                    (
                        "Acesso negado. O seu cargo não permite realizar "
                        f"a acção '{self.acao_requerida}'."
                    ),
                )
                return redirect(reverse_lazy("core_tenants:dashboard"))

        self._proteger_schema_publico()
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _proteger_schema_publico():
        schema = getattr(
            connection,
            "schema_name",
            get_public_schema_name(),
        )

        if schema == get_public_schema_name():
            raise PermissionDenied(
                "O Inspector de Payloads AGT só está disponível dentro de um tenant."
            )


# ============================================================================
# LISTAGEM
# ============================================================================

def models_q_numero_documento(termo):
    """
    Pesquisa pelo identificador do documento, submissionUUID, requestID,
    hash e número do DocumentoFiscal associado.
    """
    return (
        Q(numero_documento__icontains=termo)
        | Q(submission_uuid__icontains=termo)
        | Q(request_id__icontains=termo)
        | Q(hash_payload__icontains=termo)
        | Q(documentos__numero_documento__icontains=termo)
    )


class PayloadAGTListView(PermissaoAcaoMixin, ListView):
    acao_requerida = "acessar_payload_agt"

    model = PayloadAGT
    template_name = "fiscal/payload_inspector/lista.html"
    context_object_name = "payloads"
    paginate_by = 25

    def get_queryset(self):
        qs = (
            PayloadAGT.objects
            .all()
            .annotate(
                documentos_total=Count("documentos", distinct=True)
            )
            .order_by("-created_at", "-pk")
        )

        q = (self.request.GET.get("q") or "").strip()
        tipo = (self.request.GET.get("tipo") or "").strip().upper()
        status = (self.request.GET.get("status") or "").strip()
        ambiente = (self.request.GET.get("ambiente") or "").strip().upper()

        if q:
            qs = qs.filter(models_q_numero_documento(q)).distinct()

        if tipo:
            qs = qs.filter(tipo_documento=tipo)

        if status and status in dict(PayloadAGT.STATUS_CHOICES):
            qs = qs.filter(status=status)

        if ambiente and ambiente in dict(PayloadAGT.AMBIENTE_CHOICES):
            qs = qs.filter(ambiente=ambiente)

        self.filtros = {
            "q": q,
            "tipo": tipo,
            "status": status,
            "ambiente": ambiente,
        }

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Primeiro, definir o queryset base do tenant.
        base = PayloadAGT.objects.all()

        # Tipos de documentos existentes, obtidos dinamicamente.
        context["tipo_choices"] = list(
            base.exclude(tipo_documento="")
            .order_by("tipo_documento")
            .values_list("tipo_documento", flat=True)
            .distinct()
        )

        context.update({
            "filtros": getattr(
                self,
                "filtros",
                {
                    "q": "",
                    "tipo": "",
                    "status": "",
                    "ambiente": "",
                },
            ),

            "status_choices": PayloadAGT.STATUS_CHOICES,
            "ambiente_choices": PayloadAGT.AMBIENTE_CHOICES,

            # Indicadores gerais do tenant.
            "total_payloads": base.count(),

            "total_indeterminados": base.filter(
                resultado_indeterminado=True
            ).count(),

            "total_preparados": base.filter(
                status=PayloadAGT.STATUS_PREPARADO
            ).count(),

            "total_respostas": base.filter(
                status=PayloadAGT.STATUS_RESPOSTA
            ).count(),

            "total_falhados": base.filter(
                status=PayloadAGT.STATUS_FALHOU
            ).count(),

            "total_erros_preparacao": base.filter(
                status=PayloadAGT.STATUS_ERRO_PREPARACAO
            ).count(),

            "schema_tenant": connection.schema_name,
        })

        return context


# ============================================================================
# DETALHE
# ============================================================================

class PayloadAGTDetailView(PermissaoAcaoMixin, DetailView):
    acao_requerida = "acessar_payload_agt"

    model = PayloadAGT
    template_name = "fiscal/payload_inspector/detalhe.html"
    context_object_name = "payload_registo"

    def get_queryset(self):
        return (
            PayloadAGT.objects
            .all()
            .prefetch_related("documentos")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        registo = self.object

        documentos = (
            registo.documentos
            .all()
            .order_by("data_emissao", "numero_documento")
        )

        # JSON formatado para leitura.
        context["payload_pretty"] = json.dumps(
            registo.payload or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        context["resposta_pretty"] = json.dumps(
            registo.resposta or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        # JSON bruto usado efectivamente no pedido HTTP.
        # Só recorremos ao payload formatado nos registos antigos.
        context["payload_raw_json"] = (
            getattr(registo, "payload_json", "")
            or context["payload_pretty"]
        )

        # Hash e reconciliação.
        context["hash_payload"] = getattr(
            registo,
            "hash_payload",
            "",
        )

        context["associacao_resultado_pretty"] = json.dumps(
            getattr(registo, "associacao_resultado", {}) or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        context["resultado_indeterminado"] = getattr(
            registo,
            "resultado_indeterminado",
            False,
        )

        context["documentos_associados"] = documentos
        context["documentos_associados_total"] = documentos.count()

        # Controlos de submissão que apontam para este envelope.
        context["controlos_submissao"] = (
            ControloSubmissaoAGT.objects
            .filter(ultimo_payload=registo)
            .select_related("documento")
            .order_by("-atualizado_em", "-pk")
        )

        # Cronologia combinada:
        # eventos ligados directamente ao payload e eventos ligados
        # aos documentos que pertencem a este envelope.
        documentos_ids = documentos.values("pk")

        context["eventos_auditoria"] = (
            EventoAuditoriaPayloadAGT.objects
            .filter(
                Q(payload=registo)
                | Q(documento_id__in=documentos_ids)
            )
            .select_related("documento", "payload")
            .distinct()
            .order_by("criado_em", "pk")
        )

        # Auditorias técnicas executadas sobre o payload.
        context["auditorias"] = (
            AuditoriaPayloadAGT.objects
            .filter(payload=registo)
            .order_by("-executado_em", "-pk")
        )

        context["schema_tenant"] = connection.schema_name

        return context


# ============================================================================
# DOWNLOAD DO JSON
# ============================================================================

class PayloadAGTDownloadView(PermissaoAcaoMixin, View):
    acao_requerida = "baixar_payload_agt"

    def get(self, request, pk):
        registo = PayloadAGT.objects.filter(pk=pk).first()

        if registo is None:
            raise Http404("Payload AGT não encontrado.")

        # Preserva exactamente o JSON enviado, quando disponível.
        conteudo_texto = (
            getattr(registo, "payload_json", "")
            or json.dumps(
                registo.payload or {},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        conteudo = conteudo_texto.encode("utf-8")

        tipo = "".join(
            caracter
            for caracter in str(registo.tipo_documento or "documento")
            if caracter.isalnum() or caracter in ("-", "_")
        )[:20] or "documento"

        nome = f"payload_agt_{registo.pk}_{tipo}.json"

        response = HttpResponse(
            conteudo,
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{nome}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "no-store"

        return response