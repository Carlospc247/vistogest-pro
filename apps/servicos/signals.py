from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import AgendamentoServico
from apps.analytics.models import NotificacaoAlerta, AlertaInteligente

@receiver(post_save, sender=AgendamentoServico)
def notificar_novo_agendamento(sender, instance, created, **kwargs):
    """
    🔔 RIGOR SOTARQ: Alerta de Operatividade.
    Notifica a equipa sempre que um novo serviço é agendado (Site ou Balcão).
    """
    if created:
        # 1. Criar um Alerta Inteligente para a Empresa
        alerta = AlertaInteligente.objects.create(
            empresa=instance.empresa,
            tipo='sistema',
            prioridade='media',
            titulo="📅 Novo Agendamento Recebido",
            mensagem=(
                f"O cliente {instance.cliente.nome_completo} agendou o serviço "
                f"'{instance.servico.nome}' para o dia {instance.data_hora.strftime('%d/%m/%Y às %H:%M')}."
            ),
            dados_contexto={
                'agendamento_id': instance.id,
                'cliente_id': instance.cliente.id,
                'origem': 'site' if not instance.funcionario else 'interno'
            }
        )

        # 2. Vincular a notificação aos administradores da empresa
        # Buscamos todos os usuários daquela empresa que são staff ou administradores
        usuarios_notificar = instance.empresa.usuarios.filter(
            is_active=True, 
            e_administrador_empresa=True
        )

        for usuario in usuarios_notificar:
            NotificacaoAlerta.objects.create(
                alerta=alerta,
                usuario=usuario,
                via_sistema=True,
                enviada=True,
                enviada_em=timezone.now()
            )

        if settings.DEBUG:
            print(f"📢 [SOTARQ] Alerta de agendamento criado para {usuarios_notificar.count()} administradores.")