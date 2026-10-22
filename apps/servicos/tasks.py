"""Asynchronous service-reminder and service-event tasks.

Assumptions to verify in the real project:
- Empresa is available in the public schema and has schema_name.
- Appointment/notification tables are tenant-schema-local; only ConfiguracaoNotificacao points to Empresa.
- TimeStampedModel exposes created_at/updated_at.
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class _SafeFormat(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _formatar(template, dados):
    try:
        return (template or "").format_map(_SafeFormat(dados))
    except (ValueError, TypeError):
        logger.exception("Template de notificação inválido; será usado texto sem formatação.")
        return template or ""


def _dados_agendamento(agendamento, empresa):
    cliente = agendamento.cliente
    funcionario = getattr(agendamento, "funcionario", None)
    nome_cliente = getattr(cliente, "nome_exibicao", None) or getattr(cliente, "nome_completo", str(cliente))
    nome_funcionario = (
        getattr(funcionario, "nome_completo", None) or str(funcionario)
        if funcionario else "A confirmar"
    )
    return {
        "nome_paciente": nome_cliente,
        "nome_cliente": nome_cliente,
        "data_consulta": timezone.localtime(agendamento.data_hora).strftime("%d/%m/%Y"),
        "hora_consulta": timezone.localtime(agendamento.data_hora).strftime("%H:%M"),
        "farmaceutico": nome_funcionario,
        "funcionario": nome_funcionario,
        "servico": agendamento.servico.nome,
        "nome_empresa": getattr(empresa, "nome", str(empresa)),
    }


def _criar_notificacoes_do_tenant(schema_name):
    """Create one notification per appointment/day/channel without confusing channels."""
    from apps.servicos.models import AgendamentoServico, ConfiguracaoNotificacao, NotificacaoAgendamento

    criadas = 0
    agora = timezone.now()
    hoje = timezone.localdate()
    configs = ConfiguracaoNotificacao.objects.select_related("empresa").all()

    for config in configs:
        canais = []
        if config.email_ativo:
            canais.append("email")
        if config.sms_ativo:
            canais.append("sms")
        if config.whatsapp_ativo:
            canais.append("whatsapp")
        if not canais:
            continue

        # The appointment table is tenant-schema-local. Do not require an empresa FK:
        # this prevents accidentally mixing schema isolation with logical multi-company filters.
        if getattr(config.empresa, "schema_name", schema_name) != schema_name:
            continue
        agendamentos = AgendamentoServico.objects.filter(
            status="agendado",
            data_hora__gt=agora,
        ).select_related("cliente", "servico", "funcionario")

        for agendamento in agendamentos:
            dados = _dados_agendamento(agendamento, config.empresa)
            for dias in config.get_dias_notificacao_lista():
                data_envio = timezone.localtime(agendamento.data_hora).date() - timedelta(days=dias)
                if data_envio < hoje:
                    continue
                try:
                    momento = datetime.combine(data_envio, config.horario_inicio_envio)
                    data_agendada = timezone.make_aware(momento, timezone.get_current_timezone())
                except (TypeError, ValueError):
                    logger.exception("Hora de envio inválida para ConfiguracaoNotificacao %s", config.pk)
                    continue

                for canal in canais:
                    titulo = (
                        _formatar(config.template_email_titulo, dados)
                        if canal == "email"
                        else f"Lembrete de serviço — {dados['nome_cliente']}"
                    )
                    corpo_template = config.template_email_mensagem if canal == "email" else config.template_sms_mensagem
                    mensagem = _formatar(corpo_template, dados)
                    _, created = NotificacaoAgendamento.objects.get_or_create(
                        agendamento=agendamento,
                        dias_antecedencia=dias,
                        tipo_notificacao=canal,
                        defaults={
                            "cliente": agendamento.cliente,
                            "titulo": titulo,
                            "mensagem": mensagem,
                            "data_agendada_envio": data_agendada,
                            "status": "pendente",
                        },
                    )
                    criadas += int(created)

    return criadas


def _proximo_horario_envio(config, agora):
    """Return the next allowed send time if `agora` is outside the configured window."""
    if config is None:
        return None
    local = timezone.localtime(agora)
    inicio = config.horario_inicio_envio
    fim = config.horario_fim_envio
    hora = local.timetz().replace(tzinfo=None)
    dentro = (inicio <= hora <= fim) if inicio <= fim else (hora >= inicio or hora <= fim)
    if dentro:
        return None
    if inicio <= fim:
        data = local.date() if hora < inicio else local.date() + timedelta(days=1)
    else:
        # For an overnight window, the closed interval between end and start leads to start today.
        data = local.date()
    instante = datetime.combine(data, inicio)
    return timezone.make_aware(instante, timezone.get_current_timezone())


def _enfileirar_notificacoes_vencidas(schema_name):
    """Claim due notifications before enqueueing so Beat ticks do not resend them."""
    from apps.servicos.models import ConfiguracaoNotificacao, NotificacaoAgendamento

    agora = timezone.now()
    with schema_context(schema_name):
        config = ConfiguracaoNotificacao.objects.select_related("empresa").filter(
            empresa__schema_name=schema_name
        ).first()
    # Recover rows left in "processando" after a worker crash. A single Beat instance
    # plus the row lock below prevents routine duplicate dispatches.
    NotificacaoAgendamento.objects.filter(
        status="processando", updated_at__lt=agora - timedelta(minutes=15),
        data_agendada_envio__lte=agora,
    ).update(status="pendente")
    ids = list(
        NotificacaoAgendamento.objects.filter(
            status="pendente", data_agendada_envio__lte=agora
        ).order_by("data_agendada_envio").values_list("pk", flat=True)[:500]
    )
    enfileiradas = 0
    for pk in ids:
        try:
            with transaction.atomic():
                notificacao = (
                    NotificacaoAgendamento.objects.select_for_update()
                    .filter(pk=pk, status="pendente", data_agendada_envio__lte=agora)
                    .first()
                )
                if notificacao is None:
                    continue
                proximo = _proximo_horario_envio(config, agora)
                if proximo is not None:
                    notificacao.data_agendada_envio = proximo
                    notificacao.save(update_fields=["data_agendada_envio", "updated_at"])
                    continue
                notificacao.status = "processando"
                notificacao.save(update_fields=["status", "updated_at"])
            enviar_notificacao_agendamento.apply_async(args=[schema_name, pk], expires=300)
            enfileiradas += 1
        except Exception as exc:
            logger.exception("Não foi possível enfileirar a notificação %s", pk)
            NotificacaoAgendamento.objects.filter(pk=pk, status="processando").update(
                status="pendente",
                data_agendada_envio=timezone.now() + timedelta(minutes=1),
                erro_envio=f"Falha ao enfileirar no Celery; será tentado novamente: {exc}"[:4000],
            )
    return enfileiradas


@shared_task(name="servicos.processar_notificacoes_global", ignore_result=True)
def processar_notificacoes_global():
    """Beat entry point: process all physical tenant schemas."""
    from apps.empresas.models import Empresa

    with schema_context("public"):
        schemas = list(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))

    totals = {"tenants": len(schemas), "criadas": 0, "enfileiradas": 0, "erros": 0}
    for schema_name in schemas:
        try:
            totals["criadas"] += processar_notificacoes_tenant.run(schema_name)
            with schema_context(schema_name):
                totals["enfileiradas"] += _enfileirar_notificacoes_vencidas(schema_name)
        except Exception:
            totals["erros"] += 1
            logger.exception("Falha ao processar notificações no schema %s", schema_name)
    return totals


@shared_task(name="servicos.processar_notificacoes_tenant", ignore_result=True)
def processar_notificacoes_tenant(schema_name):
    with schema_context(schema_name):
        return _criar_notificacoes_do_tenant(schema_name)


@shared_task(name="servicos.enviar_notificacao_agendamento", acks_late=True)
def enviar_notificacao_agendamento(schema_name, notificacao_id):
    """Send one claimed notification. Unsupported channels fail explicitly, never fake success."""
    from apps.servicos.models import ConfiguracaoNotificacao, NotificacaoAgendamento

    with schema_context(schema_name):
        notificacao = NotificacaoAgendamento.objects.select_related("cliente", "agendamento").filter(
            pk=notificacao_id, status="processando"
        ).first()
        if notificacao is None:
            return {"status": "ignorada", "id": notificacao_id}

        notificacao.tentativas_envio += 1
        notificacao.save(update_fields=["tentativas_envio", "updated_at"])
        try:
            if notificacao.tipo_notificacao == "email":
                email = getattr(notificacao.cliente, "email", "")
                if not email:
                    raise ValueError("O cliente não possui email cadastrado.")
                notificacao.email_enviado = email
                send_mail(
                    subject=notificacao.titulo,
                    message=notificacao.mensagem,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=[email],
                    fail_silently=False,
                )
            elif notificacao.tipo_notificacao == "sms":
                raise NotImplementedError("Canal SMS sem provedor/API configurado.")
            elif notificacao.tipo_notificacao == "whatsapp":
                raise NotImplementedError("Canal WhatsApp sem provedor/API configurado.")
            else:
                raise ValueError(f"Canal de notificação desconhecido: {notificacao.tipo_notificacao}")

            notificacao.status = "enviada"
            notificacao.data_envio = timezone.now()
            notificacao.erro_envio = ""
            notificacao.save(update_fields=["status", "data_envio", "erro_envio", "email_enviado", "updated_at"])
            return {"status": "enviada", "id": notificacao.pk}
        except Exception as exc:
            logger.exception("Falha a enviar NotificacaoAgendamento id=%s", notificacao_id)
            config = ConfiguracaoNotificacao.objects.select_related("empresa").filter(
                empresa__schema_name=schema_name
            ).first()
            max_tentativas = max(1, int(getattr(config, "max_tentativas_envio", 3) or 3))
            intervalo_horas = max(1, int(getattr(config, "intervalo_tentativas_horas", 2) or 2))
            notificacao.erro_envio = str(exc)[:4000]
            if notificacao.tentativas_envio < max_tentativas:
                notificacao.status = "pendente"
                notificacao.data_agendada_envio = timezone.now() + timedelta(hours=intervalo_horas)
                notificacao.save(update_fields=["status", "data_agendada_envio", "erro_envio", "updated_at"])
                return {"status": "reagendada", "id": notificacao.pk, "tentativas": notificacao.tentativas_envio}
            notificacao.status = "erro"
            notificacao.save(update_fields=["status", "erro_envio", "updated_at"])
            return {"status": "erro", "id": notificacao.pk, "erro": str(exc)}


@shared_task(name="servicos.notificar_evento_agendamento", ignore_result=True)
def notificar_evento_agendamento(schema_name, evento_id):
    """Notify the customer of staff events, or staff of a customer reply."""
    from apps.servicos.tracking_models import EventoAgendamento

    with schema_context(schema_name):
        evento = EventoAgendamento.objects.select_related(
            "agendamento", "agendamento__cliente", "agendamento__servico",
            "agendamento__funcionario", "agendamento__funcionario__usuario",
        ).filter(pk=evento_id, visivel_cliente=True).first()
        if not evento:
            return {"status": "ignorado", "evento": evento_id}

        agendamento = evento.agendamento
        cliente = agendamento.cliente
        if evento.tipo == "mensagem_cliente":
            # A customer reply must notify the responsible employee (or a configured
            # service-alert address), not send the message back to the same customer.
            funcionario = getattr(agendamento, "funcionario", None)
            usuario = getattr(funcionario, "usuario", None) if funcionario else None
            destinatarios = [getattr(usuario, "email", "")] if usuario else []
            fallback = getattr(settings, "SERVICOS_EMAIL_ALERTAS", "") or ""
            if isinstance(fallback, str):
                destinatarios.extend(e.strip() for e in fallback.split(","))
            else:
                destinatarios.extend(fallback)
            destinatarios = sorted({email.strip() for email in destinatarios if email and email.strip()})
            if not destinatarios:
                logger.warning("Evento de cliente %s guardado sem destinatário de equipa para schema %s", evento_id, schema_name)
                return {"status": "sem_destinatario_equipa", "evento": evento_id}
            saudacao = "Nova mensagem do cliente"
            body = (
                f"{saudacao} sobre o serviço '{agendamento.servico.nome}'.\n\n"
                f"Cliente: {getattr(cliente, 'nome_exibicao', None) or getattr(cliente, 'nome_completo', str(cliente))}\n"
                f"{evento.titulo}\n\n{evento.descricao}\n\n"
                "Abra o VistoGest para responder ao cliente."
            )
        else:
            email = getattr(cliente, "email", "")
            if not email:
                return {"status": "sem_email_cliente", "evento": evento_id}
            destinatarios = [email]
            body = (
                f"Olá {getattr(cliente, 'nome_exibicao', None) or getattr(cliente, 'nome_completo', str(cliente))},\n\n"
                f"{evento.titulo}\n\n{evento.descricao}\n\n"
                "Consulte o seu perfil no site para acompanhar o histórico e responder."
            )

        subject = f"Actualização do serviço: {agendamento.servico.nome}"
        try:
            send_mail(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), destinatarios, fail_silently=False)
            return {"status": "enviada", "evento": evento_id, "destinatarios": len(destinatarios)}
        except Exception:
            logger.exception("Falha ao enviar alerta do evento %s (schema %s)", evento_id, schema_name)
            return {"status": "erro", "evento": evento_id}
