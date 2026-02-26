from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.empresas.models import Empresa, Domain
from apps.licenca.models import Licenca, PlanoLicenca
from .models import LogAuditoriaPublica

@receiver(post_save, sender=Empresa)
def rastro_empresa_publica(sender, instance, created, **kwargs):
    operacao = "CRIADA" if created else "ATUALIZADA"
    LogAuditoriaPublica.objects.create(
        tipo_evento='TENANT_CRUD',
        nivel='INFO',
        empresa_relacionada=instance,
        acao=f"Empresa {instance.nome} foi {operacao}.",
        dados_contexto={'nif': instance.nif, 'status': instance.ativa}
    )

@receiver(post_save, sender=Licenca)
def rastro_licenciamento(sender, instance, created, **kwargs):
    LogAuditoriaPublica.objects.create(
        tipo_evento='LICENCA',
        nivel='AVISO' if instance.esta_vencida else 'INFO',
        empresa_relacionada=instance.empresa,
        acao=f"Licença da empresa {instance.empresa.nome} alterada para plano {instance.plano.nome}.",
        dados_contexto={'vencimento': str(instance.data_vencimento), 'status': instance.status}
    )