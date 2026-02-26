from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
from django.db import models
from django.contrib.auth.mixins import LoginRequiredMixin


class BaseViewMixin(LoginRequiredMixin):
    """
    Mixin base para todas as views do sistema.
    Garante que o usuário esteja autenticado e permite centralizar comportamentos comuns.
    """
    login_url = '/conta/login/'
    redirect_field_name = 'next'

    # Exemplo: podes adicionar métodos comuns aqui
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['app_name'] = _("Pharmassys")
        return context


# --- Mixins para DRF Views ---
class SuccessMessageMixin:
    """
    Adiciona mensagem de sucesso nas respostas de create/update/delete.
    """
    success_message = None

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if self.success_message:
            response.data['detail'] = self.success_message
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if self.success_message:
            response.data['detail'] = self.success_message
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        if self.success_message:
            return Response({'detail': self.success_message}, status=status.HTTP_204_NO_CONTENT)
        return response


class IsAuthenticatedMixin:
    """
    Garante que todas as views herdem autenticação por padrão.
    """
    permission_classes = [IsAuthenticated]


# --- Mixins para Models ---
class TimeStampedModel(models.Model):
    """
    Modelo abstrato que adiciona campos created_at e updated_at.
    """
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        abstract = True


class AtivoInativoModel(models.Model):
    """
    Modelo abstrato para ativar/inativar registros.
    """
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        abstract = True
