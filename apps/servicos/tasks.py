from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from .models import AgendamentoServico

def disparar_lembretes_agendamento():
    """
    🤖 AUTOMAÇÃO SOTARQ: O "Guardião da Agenda".
    Verifica agendamentos nas próximas horas e notifica o cliente.
    """
    agora = timezone.now()
    janela_inicio = agora + timedelta(hours=2)
    janela_fim = agora + timedelta(hours=3)

    # Buscar agendamentos que acontecem na janela de 2 a 3 horas a partir de agora
    agendamentos_proximos = AgendamentoServico.objects.filter(
        data_hora__range=(janela_inicio, janela_fim),
        status='agendado'
    ).select_related('cliente', 'servico', 'empresa')

    for agendamento in agendamentos_proximos:
        try:
            # Construção do E-mail
            assunto = f"🔔 Lembrete de Agendamento - {agendamento.empresa.nome}"
            mensagem = (
                f"Olá {agendamento.cliente.nome_completo},\n\n"
                f"Lembramos que o seu serviço de '{agendamento.servico.nome}' está marcado "
                f"para hoje às {agendamento.data_hora.strftime('%H:%M')}.\n\n"
                f"Até breve!"
            )
            
            send_mail(
                assunto,
                mensagem,
                'no-reply@vistogest.com',
                [agendamento.cliente.email],
                fail_silently=False,
            )
            
            # Registar no log do agendamento que o lembrete foi enviado
            agendamento.observacoes += f"\n[SISTEMA] Lembrete enviado às {agora.strftime('%H:%M')}."
            agendamento.save()
            
        except Exception as e:
            print(f"❌ Erro ao enviar lembrete para {agendamento.cliente.email}: {e}")