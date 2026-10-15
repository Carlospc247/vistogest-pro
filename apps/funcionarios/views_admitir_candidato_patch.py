"""Vista para admissão de uma candidatura do app site."""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.views import View

from apps.site.models import Candidatura
from .forms import AdmissaoCandidatoForm

logger = logging.getLogger(__name__)


class AdmitirCandidatoView(LoginRequiredMixin, View):
    """Converte uma candidatura em funcionário dentro do tenant actual."""

    template_name = "funcionarios/admitir_candidato.html"
    @staticmethod
    def _tenant_actual(request):
        tenant = getattr(request, "tenant", None)
        if not tenant or getattr(tenant, "schema_name", "public") in {"", "public"}:
            return None
        return tenant

    def dispatch(self, request, *args, **kwargs):
        # Deixa o LoginRequiredMixin redireccionar utilizadores anónimos.
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        # Funcionario.usuario define related_name='funcionario_relacionado'.
        perfil = getattr(request.user, "funcionario_relacionado", None)
        # Compatibilidade com código legado que tenha related_name='funcionario'.
        if perfil is None:
            perfil = getattr(request.user, "funcionario", None)

        if perfil is None or not perfil.pode_realizar_acao("gerenciar_funcionarios"):
            raise PermissionDenied("Não tem permissão para admitir funcionários.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, candidato_id):
        if self._tenant_actual(request) is None:
            messages.error(request, "Empresa não encontrada para esta requisição.")
            return redirect("funcionarios:painel_candidatura")

        candidato = get_object_or_404(Candidatura, pk=candidato_id)
        if candidato.status == "aceita":
            messages.warning(request, "Esta candidatura já se encontra aceite.")
            return redirect("funcionarios:painel_candidatura")

        form = AdmissaoCandidatoForm(candidatura=candidato)
        return render(request, self.template_name, {"form": form, "candidato": candidato})

    def post(self, request, candidato_id):
        empresa = self._tenant_actual(request)
        if empresa is None:
            messages.error(request, "Empresa não encontrada para esta requisição.")
            return redirect("funcionarios:painel_candidatura")

        candidato = get_object_or_404(Candidatura, pk=candidato_id)
        if candidato.status == "aceita":
            messages.warning(request, "Esta candidatura já se encontra aceite; não foi criado outro funcionário.")
            return redirect("funcionarios:painel_candidatura")

        form = AdmissaoCandidatoForm(request.POST, candidatura=candidato)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "candidato": candidato})

        funcionario = None
        try:
            with transaction.atomic():
                # Bloqueia a candidatura para impedir admissões duplicadas concorrentes.
                candidato = get_object_or_404(
                    Candidatura.objects.select_for_update(),
                    pk=candidato_id,
                )
                if candidato.status == "aceita":
                    messages.warning(request, "Esta candidatura já foi aceite por outro utilizador.")
                    return redirect("funcionarios:painel_candidatura")

                funcionario = form.save(commit=False)
                funcionario.ativo = True
                funcionario.save()  # gera a matrícula e valida que cargo está definido
                form.save_m2m()

                candidato.status = "aceita"
                candidato.save()

        except IntegrityError:
            logger.exception("Conflito de integridade durante a admissão da candidatura %s", candidato_id)
            form.add_error(
                None,
                "Não foi possível concluir a admissão. Confirme se o BI já está registado e reveja os dados.",
            )
            return render(request, self.template_name, {"form": form, "candidato": candidato})
        except Exception:
            logger.exception("Erro inesperado durante a admissão da candidatura %s", candidato_id)
            messages.error(request, "Ocorreu um erro ao concluir a admissão. Nenhuma alteração parcial foi guardada.")
            return redirect("funcionarios:painel_candidatura")

        email_enviado = self.enviar_email_boas_vindas(funcionario, empresa)
        if email_enviado:
            messages.success(
                request,
                f"Admissão de {funcionario.nome_completo} concluída. O e-mail de boas-vindas foi enviado.",
            )
        else:
            messages.warning(
                request,
                f"Admissão de {funcionario.nome_completo} concluída, mas não foi possível enviar o e-mail de boas-vindas.",
            )

        return redirect("funcionarios:editar_funcionario", pk=funcionario.pk)

    @staticmethod
    def enviar_email_boas_vindas(funcionario, empresa):
        """Envia o e-mail após a transacção; uma falha de e-mail não desfaz a admissão."""
        if not funcionario.email_pessoal:
            return False

        nome_empresa = (
            getattr(empresa, "nome", None)
            or getattr(empresa, "name", None)
            or getattr(empresa, "schema_name", None)
            or "Empresa"
        )
        assunto = f"Bem-vindo à equipa, {funcionario.nome_completo}! | {nome_empresa}"
        contexto = {
            "nome": funcionario.nome_completo,
            "empresa_nome": nome_empresa,
            "matricula": funcionario.matricula,
        }

        try:
            html_message = render_to_string("emails/boas_vindas_funcionario.html", contexto)
            resultado = send_mail(
                subject=assunto,
                message=strip_tags(html_message),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=[funcionario.email_pessoal],
                html_message=html_message,
                fail_silently=False,
            )
            return resultado == 1
        except Exception:
            logger.exception("Falha ao enviar o e-mail de boas-vindas ao funcionário %s", funcionario.pk)
            return False
