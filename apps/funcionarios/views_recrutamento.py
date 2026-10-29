# apps/funcionarios/views_recrutamento.py
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from apps.funcionarios.views import PermissaoAcaoMixin
from apps.site.models import Candidatura
from .models import Funcionario, Cargo, Departamento
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .forms import AdmissaoCandidatoForm




class PainelCandidaturaView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    """
    🏢 PAINEL DE CONTROLO DE TALENTOS: Gestão de candidatos do site.
    """
    acao_requerida = 'gerenciar_funcionarios'
    model = Candidatura
    template_name = "funcionarios/painel_candidatura.html"
    context_object_name = "candidatos"


    def get_queryset(self):
        # Filtra candidaturas vinculadas à empresa do usuário logado
        return Candidatura.objects.select_related('concurso').all().order_by('-created_at')


class AdmitirCandidatoView(
    LoginRequiredMixin,
    PermissaoAcaoMixin,
    View,
):
    """
    Admite um candidato após recolher e validar todos os dados
    obrigatórios do funcionário.

    A criação do funcionário e a atualização da candidatura
    são realizadas na mesma transação.
    """

    acao_requerida = 'gerenciar_funcionarios'
    template_name = 'funcionarios/admitir_candidato.html'

    def _obter_tenant(self, request):
        tenant = getattr(request, 'tenant', None)

        if (
            not tenant
            or getattr(tenant, 'schema_name', 'public') == 'public'
        ):
            return None

        return tenant

    def get(self, request, candidato_id):
        tenant = self._obter_tenant(request)

        if tenant is None:
            messages.error(
                request,
                'Empresa não encontrada para esta requisição.',
            )
            return redirect('funcionarios:painel_candidatura')

        candidato = get_object_or_404(
            Candidatura,
            pk=candidato_id,
        )

        if candidato.status == 'aceita':
            messages.info(
                request,
                'Esta candidatura já foi aceite.',
            )
            return redirect('funcionarios:painel_candidatura')

        form = AdmissaoCandidatoForm(
            candidatura=candidato,
        )

        return render(
            request,
            self.template_name,
            {
                'form': form,
                'candidato': candidato,
            },
        )

    def post(self, request, candidato_id):
        tenant = self._obter_tenant(request)

        if tenant is None:
            messages.error(
                request,
                'Empresa não encontrada para esta requisição.',
            )
            return redirect('funcionarios:painel_candidatura')

        candidato = get_object_or_404(
            Candidatura,
            pk=candidato_id,
        )

        if candidato.status == 'aceita':
            messages.info(
                request,
                'Esta candidatura já foi aceite.',
            )
            return redirect('funcionarios:painel_candidatura')

        form = AdmissaoCandidatoForm(
            request.POST,
            candidatura=candidato,
        )

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'candidato': candidato,
                },
            )

        try:
            with transaction.atomic():
                # Impede duas admissões simultâneas da mesma candidatura.
                candidato = get_object_or_404(
                    Candidatura.objects.select_for_update(),
                    pk=candidato_id,
                )

                if candidato.status == 'aceita':
                    messages.info(
                        request,
                        'Esta candidatura já foi aceite.',
                    )
                    return redirect(
                        'funcionarios:painel_candidatura'
                    )

                # Os campos obrigatórios já foram validados pelo formulário.
                novo_funcionario = form.save(commit=False)
                novo_funcionario.save()

                # Só aceitar a candidatura depois de criar o funcionário.
                candidato.status = 'aceita'
                candidato.save()

        except ValidationError as exc:
            form.add_error(None, exc)

            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'candidato': candidato,
                },
            )

        except IntegrityError:
            form.add_error(
                None,
                (
                    'Não foi possível concluir a admissão devido '
                    'a um conflito com um registo existente. '
                    'Confirme o BI e tente novamente.'
                ),
            )

            return render(
                request,
                self.template_name,
                {
                    'form': form,
                    'candidato': candidato,
                },
            )

        # O envio do email ocorre depois da transação.
        # Uma falha no email não deve desfazer a admissão.
        if novo_funcionario.email_pessoal:
            self.enviar_email_boas_vindas(
                novo_funcionario,
                tenant,
            )

        messages.success(
            request,
            (
                f'Admissão de {novo_funcionario.nome_completo} '
                f'concluída. Matrícula: {novo_funcionario.matricula}.'
            ),
        )

        return redirect(
            'funcionarios:editar_funcionario',
            pk=novo_funcionario.pk,
        )

    def enviar_email_boas_vindas(self, funcionario, empresa):
        """Envia o email de boas-vindas após a admissão."""

        nome_empresa = (
            getattr(empresa, 'name', None)
            or getattr(empresa, 'nome', None)
            or getattr(empresa, 'schema_name', None)
            or 'Empresa'
        )

        assunto = (
            f'Bem-vindo à equipa, '
            f'{funcionario.nome_completo}! | {nome_empresa}'
        )

        contexto = {
            'nome': funcionario.nome_completo,
            'empresa_nome': nome_empresa,
            'matricula': funcionario.matricula,
        }

        try:
            html_message = render_to_string(
                'emails/boas_vindas_funcionario.html',
                contexto,
            )

            plain_message = strip_tags(html_message)

            send_mail(
                subject=assunto,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[funcionario.email_pessoal],
                html_message=html_message,
                fail_silently=True,
            )

        except Exception:
            # Uma falha no serviço de email não deve anular a admissão.
            import logging

            logging.getLogger(__name__).exception(
                'Falha no email de boas-vindas do funcionário %s.',
                funcionario.pk,
            )

            

class RejeitarCandidatoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """
    🛡️ RIGOR DE FEEDBACK: Altera status da candidatura e notifica o candidato.
    """
    acao_requerida = 'gerenciar_funcionarios'

    def post(self, request, candidato_id):
        candidato = get_object_or_404(Candidatura, id=candidato_id)
        
        try:
            # 1. Atualizar Status para Rejeitada
            candidato.status = 'rejeitada'
            candidato.save()

            # 2. Enviar E-mail de Feedback (Employer Branding)
            self.enviar_email_rejeicao(candidato)

            messages.info(request, f"Candidato {candidato.nome} rejeitado. E-mail de feedback enviado.")
            return redirect('funcionarios:painel_candidatura')

        except Exception as e:
            messages.error(request, f"Erro ao processar rejeição: {str(e)}")
            return redirect('funcionarios:painel_candidatura')

    def enviar_email_rejeicao(self, candidato):
        assunto = f"Atualização sobre a sua candidatura | {self.request.tenant.nome}"
        contexto = {
            'nome': candidato.nome,
            'empresa_nome': self.request.tenant.nome,
            'vaga': candidato.concurso.titulo,
        }
        
        html_message = render_to_string('emails/candidatura_rejeitada.html', contexto)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=assunto,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[candidato.email],
            html_message=html_message,
            fail_silently=True,
        )


