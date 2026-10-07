from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

# Import obrigatório do django_tenants para garantir gravação no Schema Public
from django_tenants.utils import schema_context

from apps.empresas.models import Empresa
from apps.licenca.models import Licenca
from .models import LogAuditoriaPublica


@receiver(post_save, sender=Empresa)
def rastro_empresa_publica(sender, instance, created, **kwargs):
    operacao = "CRIADA" if created else "ATUALIZADA"

    def gravar_log():
        # Garante que a escrita ocorra explicitamente no schema 'public'
        with schema_context('public'):
            LogAuditoriaPublica.objects.create(
                tipo_evento='TENANT_CRUD',
                nivel='INFO',
                empresa_relacionada=instance,
                acao=f"Empresa {instance.nome} foi {operacao}.",
                dados_contexto={
                    'nif': getattr(instance, 'nif', None),
                    'status': getattr(instance, 'ativa', False)
                }
            )

    # Executa o log somente após a transação ser commitada no banco
    transaction.on_commit(gravar_log)


@receiver(post_save, sender=Licenca)
def rastro_licenciamento(sender, instance, created, **kwargs):
    operacao = "CRIADA" if created else "ALTERADA"

    def gravar_log():
        # Proteção contra NoneType
        nome_empresa = instance.empresa.nome if instance.empresa else "Sem Empresa"
        nome_plano = instance.plano.nome if instance.plano else "Sem Plano"
        esta_vencida = getattr(instance, 'esta_vencida', False)

        with schema_context('public'):
            LogAuditoriaPublica.objects.create(
                tipo_evento='LICENCA',
                nivel='AVISO' if esta_vencida else 'INFO',
                empresa_relacionada=instance.empresa,
                acao=f"Licença da empresa '{nome_empresa}' foi {operacao.lower()} (Plano: {nome_plano}).",
                dados_contexto={
                    'vencimento': str(instance.data_vencimento) if instance.data_vencimento else None,
                    'status': getattr(instance, 'status', None)
                }
            )

    transaction.on_commit(gravar_log)