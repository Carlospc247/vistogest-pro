"""Painel de consulta dos payloads AGT (apenas leitura e download)."""
import json

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils.html import escape
from django.views.generic import DetailView, ListView, View
from django.db import connection
from django_tenants.utils import get_public_schema_name

from apps.fiscal.models_payload_agt import PayloadAGT


class PayloadAGTAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "core:login"

    def test_func(self):
        user = self.request.user
        return bool(
            user.is_authenticated
            and (
                user.is_superuser
                or user.is_staff
                or user.has_perm("fiscal.inspect_payloadagt")
                or user.has_perm("fiscal.view_payloadagt")
            )
        )

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Não tens permissão para consultar payloads fiscais AGT.")
        return super().handle_no_permission()

    def _proteger_schema_publico(self):
        schema = getattr(connection, "schema_name", get_public_schema_name())
        if schema == get_public_schema_name():
            raise PermissionDenied("O Inspector de Payloads AGT só está disponível dentro de um tenant.")


class PayloadAGTListView(PayloadAGTAccessMixin, ListView):
    model = PayloadAGT
    template_name = "fiscal/payload_inspector/lista.html"
    context_object_name = "payloads"
    paginate_by = 25

    def get_queryset(self):
        self._proteger_schema_publico()
        qs = PayloadAGT.objects.all().order_by("-created_at", "-pk")
        q = (self.request.GET.get("q") or "").strip()
        tipo = (self.request.GET.get("tipo") or "").strip().upper()
        status = (self.request.GET.get("status") or "").strip()
        ambiente = (self.request.GET.get("ambiente") or "").strip().upper()
        if q:
            qs = qs.filter(
                models_q_numero_documento(q)
            )
        if tipo:
            qs = qs.filter(tipo_documento=tipo)
        if status and status in dict(PayloadAGT.STATUS_CHOICES):
            qs = qs.filter(status=status)
        if ambiente and ambiente in dict(PayloadAGT.AMBIENTE_CHOICES):
            qs = qs.filter(ambiente=ambiente)
        self.filtros = {"q": q, "tipo": tipo, "status": status, "ambiente": ambiente}
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filtros"] = getattr(self, "filtros", {})
        context["status_choices"] = PayloadAGT.STATUS_CHOICES
        context["ambiente_choices"] = PayloadAGT.AMBIENTE_CHOICES
        context["total_payloads"] = PayloadAGT.objects.count()
        return context


def models_q_numero_documento(q):
    """Pesquisa sem importação global de Q no módulo de views."""
    from django.db.models import Q
    return Q(numero_documento__icontains=q) | Q(submission_uuid__icontains=q) | Q(request_id__icontains=q)


class PayloadAGTDetailView(PayloadAGTAccessMixin, DetailView):
    model = PayloadAGT
    template_name = "fiscal/payload_inspector/detalhe.html"
    context_object_name = "payload_registo"

    def get_queryset(self):
        self._proteger_schema_publico()
        return PayloadAGT.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        registo = self.object
        context["payload_pretty"] = json.dumps(registo.payload or {}, ensure_ascii=False, indent=2)
        context["resposta_pretty"] = json.dumps(registo.resposta or {}, ensure_ascii=False, indent=2)
        context["documentos_associados"] = registo.documentos.all().order_by("data_emissao", "numero")
        return context


class PayloadAGTDownloadView(PayloadAGTAccessMixin, View):
    def get(self, request, pk):
        self._proteger_schema_publico()
        registo = PayloadAGT.objects.filter(pk=pk).first()
        if registo is None:
            from django.http import Http404
            raise Http404("Payload AGT não encontrado.")
        conteudo = json.dumps(registo.payload or {}, ensure_ascii=False, indent=2).encode("utf-8")
        nome = f"payload_agt_{registo.pk}_{registo.tipo_documento or 'documento'}.json"
        response = HttpResponse(conteudo, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{nome}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
