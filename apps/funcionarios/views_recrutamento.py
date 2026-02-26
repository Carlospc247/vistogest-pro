# apps/funcionarios/views_recrutamento.py
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from apps.site.models import Candidatura
from .models import Funcionario, Cargo, Departamento
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from django.db import transaction




class PainelCandidaturaView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    🏢 PAINEL DE CONTROLO DE TALENTOS: Gestão de candidatos do site.
    """
    model = Candidatura
    template_name = "funcionarios/painel_candidatura.html"
    context_object_name = "candidatos"
    permission_required = 'funcionarios.pode_gerenciar_funcionarios'

    def get_queryset(self):
        # Filtra candidaturas vinculadas à empresa do usuário logado
        return Candidatura.objects.filter(concurso__pagina__empresa=self.request.user.empresa).order_by('-created_at')

class AdmitirCandidatoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    🚀 CONVERSÃO SOTARQ: Transforma um Candidato em Funcionário Ativo.
    """
    permission_required = 'funcionarios.pode_gerenciar_funcionarios'

    def post(self, request, candidato_id):
        candidato = get_object_or_404(Candidatura, id=candidato_id, concurso__pagina__empresa=request.user.empresa)
        empresa = request.user.empresa

        try:
            # 1. Criar o Funcionário com dados da candidatura
            # Nota: Campos como 'cargo' e 'departamento' devem ser preenchidos no form de admissão.
            # Aqui fazemos um provisionamento básico.
            novo_funcionario = Funcionario.objects.create(
                empresa=empresa,
                nome_completo=candidato.nome,
                email_pessoal=candidato.email,
                telefone=candidato.telefone,
                data_admissao=timezone.now().date(),
                salario_atual=0, # Deve ser editado após a admissão
                departamento=Departamento.objects.filter(loja__empresa=empresa).first(),
                loja_principal=request.user.loja or empresa.lojas.first(),
                ativo=True
            )

            # 2. Atualizar status da candidatura
            candidato.status = 'aceita'
            candidato.save()

            messages.success(request, f"Rigor de Admissão: {candidato.nome} agora é um funcionário oficial!")
            return redirect('funcionarios:editar_funcionario', pk=novo_funcionario.id)

        except Exception as e:
            messages.error(request, f"Erro ao admitir: {str(e)}")
            return redirect('funcionarios:painel_candidatura')



class AdmitirCandidatoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    🚀 CONVERSÃO E BOAS-VINDAS SOTARQ: 
    Admite o candidato e dispara notificação oficial.
    """
    permission_required = 'funcionarios.pode_gerenciar_funcionarios'

    def post(self, request, candidato_id):
        candidato = get_object_or_404(Candidatura, id=candidato_id, concurso__pagina__empresa=request.user.empresa)
        empresa = request.user.empresa

        try:
            with transaction.atomic():
                # 1. Criar o Funcionário (A matrícula é gerada no save() do modelo)
                novo_funcionario = Funcionario.objects.create(
                    empresa=empresa,
                    nome_completo=candidato.nome,
                    email_pessoal=candidato.email,
                    telefone=candidato.telefone,
                    data_admissao=timezone.now().date(),
                    salario_atual=0, 
                    departamento=Departamento.objects.filter(loja__empresa=empresa).first(),
                    loja_principal=request.user.loja or empresa.lojas.first(),
                    ativo=True
                )

                # 2. Atualizar candidatura
                candidato.status = 'aceita'
                candidato.save()

                # 3. Disparar E-mail de Boas-Vindas (Rigor de Comunicação)
                self.enviar_email_boas_vindas(novo_funcionario)

            messages.success(request, f"Admissão de {candidato.nome} concluída com e-mail de boas-vindas.")
            return redirect('funcionarios:editar_funcionario', pk=novo_funcionario.id)

        except Exception as e:
            messages.error(request, f"Erro no rigor de admissão: {str(e)}")
            return redirect('funcionarios:painel_candidatura')

    def enviar_email_boas_vindas(self, funcionario):
        """Serviço de e-mail integrado ao padrão VistoGEST"""
        assunto = f"Bem-vindo à equipe, {funcionario.nome_completo}! | {funcionario.empresa.nome}"
        contexto = {
            'nome': funcionario.nome_completo,
            'empresa_nome': funcionario.empresa.nome,
            'matricula': funcionario.matricula,
        }
        
        html_message = render_to_string('emails/boas_vindas_funcionario.html', contexto)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=assunto,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[funcionario.email_pessoal],
            html_message=html_message,
            fail_silently=True, # Evita travar a admissão se o servidor de e-mail falhar
        )


class RejeitarCandidatoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    🛡️ RIGOR DE FEEDBACK: Altera status da candidatura e notifica o candidato.
    """
    permission_required = 'funcionarios.pode_gerenciar_funcionarios'

    def post(self, request, candidato_id):
        candidato = get_object_or_404(Candidatura, id=candidato_id, concurso__pagina__empresa=request.user.empresa)
        
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
        assunto = f"Atualização sobre a sua candidatura | {candidato.concurso.pagina.empresa.nome}"
        contexto = {
            'nome': candidato.nome,
            'empresa_nome': candidato.concurso.pagina.empresa.nome,
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


