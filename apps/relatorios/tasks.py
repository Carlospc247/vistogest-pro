# apps/relatorios/tasks.py
"""Tarefas Celery com troca explícita de schema e validação de models."""
import logging
import os
from datetime import timedelta
from email.utils import getaddresses

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import connection
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.models import Usuario
from .models import AgendamentoRelatorio, Relatorio, RelatorioGerado, TemplateRelatorio
from .utils import (
    criar_kpi_automatico,
    detectar_alertas_automaticos,
    gerar_relatorio_csv,
    gerar_relatorio_excel,
    gerar_relatorio_pdf,
    processar_relatorio_assincrono,
)

logger = logging.getLogger(__name__)


def _tenants():
    Tenant = get_tenant_model()
    with schema_context("public"):
        qs = Tenant.objects.all()
        try:
            qs = qs.exclude(schema_name="public")
        except Exception:
            pass
        if any(field.name == "ativo" for field in Tenant._meta.fields):
            qs = qs.filter(ativo=True)
        elif any(field.name == "is_active" for field in Tenant._meta.fields):
            qs = qs.filter(is_active=True)
        return list(qs)


def _field_exists(model, name):
    try:
        model._meta.get_field(name)
        return True
    except Exception:
        return False


def _tenant_schema(schema_name=None):
    schema = schema_name or getattr(connection, "schema_name", None)
    if not schema or schema == "public":
        raise ValueError("schema_name do tenant é obrigatório para processar relatórios em Celery.")
    return schema


def _parse_recipients(value):
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        candidates = [str(x).strip() for x in value]
    else:
        candidates = [email for _, email in getaddresses([str(value)]) if email]
        if not candidates:
            candidates = [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]
    return [email for email in candidates if "@" in email]


def _run_template_report(template, user, recipients=None):
    """Executa um TemplateRelatorio sobre o model declarado no ContentType."""
    content_type = getattr(template, "modelo_base", None)
    model = content_type.model_class() if content_type and hasattr(content_type, "model_class") else None
    if model is None:
        raise ValueError(f'O template "{template.nome}" não tem um modelo-base válido.')

    declared_fields = getattr(template, "campos", None) or []
    if isinstance(declared_fields, dict):
        declared_fields = declared_fields.get("campos", []) or declared_fields.get("fields", [])
    if isinstance(declared_fields, str):
        declared_fields = [part.strip() for part in declared_fields.split(",") if part.strip()]
    available = {field.name for field in model._meta.fields}
    fields = [str(field) for field in declared_fields if str(field) in available]
    if not fields:
        fields = [field.name for field in model._meta.fields if field.concrete and not field.is_relation][:12]
    if not fields:
        fields = [model._meta.pk.name]

    objects = list(model.objects.all().order_by("pk")[:5000])
    rows = []
    for obj in objects:
        rows.append({field: getattr(obj, field, None) for field in fields})
    clean_rows = [{key: (value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else "") for key, value in row.items()} for row in rows]
    formato = "pdf"
    if _field_exists(Relatorio, "formato"):
        # Mantém o formato predefinido do model se houver uma configuração de distribuição.
        formato = "pdf"
    if formato == "excel": payload, ext = gerar_relatorio_excel(clean_rows), "xlsx"
    elif formato == "csv": payload, ext = gerar_relatorio_csv(clean_rows).encode("utf-8-sig"), "csv"
    else: payload, ext = gerar_relatorio_pdf(clean_rows, template.nome), "pdf"

    create_kwargs = {}
    if _field_exists(Relatorio, "template"): create_kwargs["template"] = template
    if _field_exists(Relatorio, "formato"): create_kwargs["formato"] = formato
    if _field_exists(Relatorio, "filtros"): create_kwargs["filtros"] = {"fonte": f"{model._meta.app_label}.{model._meta.model_name}"}
    if _field_exists(Relatorio, "gerado_por"): create_kwargs["gerado_por"] = user
    report = Relatorio.objects.create(**create_kwargs)
    filename = f"{slugify(template.nome) or 'relatorio'}-{report.pk}.{ext}"
    if _field_exists(Relatorio, "arquivo_gerado"):
        report.arquivo_gerado.save(filename, ContentFile(payload), save=False)
    if _field_exists(Relatorio, "status"):
        report.status = "concluido"
    report.save()

    valid_recipients = _parse_recipients(recipients)
    if valid_recipients and _field_exists(Relatorio, "arquivo_gerado") and report.arquivo_gerado:
        report.arquivo_gerado.open("rb")
        try: contents = report.arquivo_gerado.read()
        finally: report.arquivo_gerado.close()
        email = EmailMessage(
            subject=f"Relatório agendado: {template.nome}",
            body=f"Segue o relatório gerado a partir do template {template.nome}.",
            to=valid_recipients,
        )
        email.attach(os.path.basename(report.arquivo_gerado.name), contents, "application/pdf" if ext == "pdf" else "application/octet-stream")
        email.send(fail_silently=False)
    return report


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def processar_relatorio_task(self, relatorio_id, schema_name=None):
    """Processa RelatorioGerado dentro do schema correcto do tenant.

    Sempre passar o schema como segundo argumento: os IDs de tabelas tenant-scoped
    podem repetir-se entre schemas e não identificam o tenant por si só.
    """
    schema = _tenant_schema(schema_name)
    try:
        with schema_context(schema):
            report = processar_relatorio_assincrono(relatorio_id, schema_name=schema)
            return {"relatorio_id": report.pk, "codigo": report.codigo_relatorio, "status": report.status, "schema": schema}
    except Exception as exc:
        logger.exception("Erro ao processar relatório %s no schema %s", relatorio_id, schema)
        raise self.retry(exc=exc)


@shared_task
def executar_agendamentos_relatorios():
    """Executa os agendamentos cujo horário coincide com o minuto actual."""
    now = timezone.localtime()
    executados = []
    for tenant in _tenants():
        schema = getattr(tenant, "schema_name", None)
        if not schema or schema == "public":
            continue
        with schema_context(schema):
            schedules = AgendamentoRelatorio.objects.filter(ativo=True)
            for schedule in schedules.select_related("template") if _field_exists(AgendamentoRelatorio, "template") else schedules:
                horario = getattr(schedule, "horario", None)
                if horario and (horario.hour, horario.minute) != (now.hour, now.minute):
                    continue
                frequency = str(getattr(schedule, "frequencia", "diaria")).lower()
                if frequency in {"semanal", "weekly"} and now.weekday() != 0:
                    continue
                if frequency in {"mensal", "monthly"} and now.day != 1:
                    continue
                template = getattr(schedule, "template", None)
                if template is None:
                    logger.warning("Agendamento %s no schema %s sem template associado.", schedule.pk, schema)
                    continue
                user = None
                if _field_exists(AgendamentoRelatorio, "usuario"):
                    user = getattr(schedule, "usuario", None)
                if user is None:
                    user = Usuario.objects.filter(is_active=True).first() if _field_exists(Usuario, "is_active") else Usuario.objects.first()
                if user is None:
                    logger.warning("Não há utilizador activo no schema %s para executar o agendamento %s.", schema, schedule.pk)
                    continue
                try:
                    report = _run_template_report(template, user, getattr(schedule, "destinatarios", None))
                    executados.append({"schema": schema, "agendamento_id": schedule.pk, "relatorio_id": report.pk})
                except Exception:
                    logger.exception("Erro no agendamento %s do schema %s", schedule.pk, schema)
    return executados


@shared_task
def gerar_kpis_automaticos():
    hoje = timezone.localdate()
    resultado = []
    for tenant in _tenants():
        schema = getattr(tenant, "schema_name", None)
        if not schema or schema == "public": continue
        with schema_context(schema):
            for codigo, nome in (("VENDAS_DIA", "Vendas do Dia"), ("VENDAS_MES", "Vendas do Mês")):
                try:
                    kpi = criar_kpi_automatico(codigo=codigo, nome=nome, tipo_metrica="monetario", periodo="diario" if codigo.endswith("DIA") else "mensal", data_referencia=hoje)
                    resultado.append({"schema": schema, "kpi_id": kpi.pk, "codigo": codigo})
                except Exception:
                    logger.exception("Falha ao gerar KPI %s no schema %s", codigo, schema)
    return resultado


@shared_task
def detectar_alertas_task():
    detections = []
    for tenant in _tenants():
        schema = getattr(tenant, "schema_name", None)
        if not schema or schema == "public": continue
        with schema_context(schema):
            try:
                alerts = detectar_alertas_automaticos()
                detections.append({"schema": schema, "total": len(alerts)})
            except Exception:
                logger.exception("Falha ao detectar alertas no schema %s", schema)
    return detections


@shared_task
def limpar_relatorios_antigos(dias=90):
    cutoff = timezone.now() - timedelta(days=dias)
    apagados = 0
    for tenant in _tenants():
        schema = getattr(tenant, "schema_name", None)
        if not schema or schema == "public": continue
        with schema_context(schema):
            qs = RelatorioGerado.objects.filter(data_solicitacao__lt=cutoff)
            for report in qs.iterator():
                try:
                    if report.arquivo_resultado:
                        report.arquivo_resultado.delete(save=False)
                except Exception:
                    logger.exception("Falha ao remover o ficheiro de relatório %s no schema %s", report.pk, schema)
                report.delete(); apagados += 1
    return {"apagados": apagados, "antes_de": cutoff.isoformat()}


@shared_task
def gerar_relatorio_mensal():
    """Executa templates com frequência mensal no primeiro dia do mês."""
    now = timezone.localtime()
    if now.day != 1:
        return {"executados": 0, "motivo": "A tarefa mensal só corre no primeiro dia do mês."}
    result = executar_agendamentos_relatorios()
    return {"executados": len(result), "detalhes": result}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enviar_relatorio_email_task(self, relatorio_id, schema_name=None, recipient=None):
    schema = _tenant_schema(schema_name)
    try:
        with schema_context(schema):
            report = RelatorioGerado.objects.get(pk=relatorio_id)
            if not report.arquivo_resultado:
                raise ValueError("O relatório ainda não possui ficheiro de resultado.")
            recipients = _parse_recipients(recipient)
            if not recipients:
                raise ValueError("É necessário indicar pelo menos um destinatário válido.")
            report.arquivo_resultado.open("rb")
            try: contents = report.arquivo_resultado.read()
            finally: report.arquivo_resultado.close()
            filename = os.path.basename(report.arquivo_resultado.name)
            email = EmailMessage(
                subject=f"Relatório {report.codigo_relatorio}",
                body="Segue em anexo o relatório solicitado.",
                to=recipients,
            )
            email.attach(filename, contents, "application/octet-stream")
            email.send(fail_silently=False)
            return {"relatorio_id": report.pk, "enviado_para": recipients, "schema": schema}
    except Exception as exc:
        logger.exception("Falha ao enviar relatório %s no schema %s", relatorio_id, schema)
        raise self.retry(exc=exc)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def executar_agendamento_individual_task(self, agendamento_id, schema_name=None):
    """Executa manualmente um único agendamento pelo seu ID no schema informado."""
    schema = _tenant_schema(schema_name)
    try:
        with schema_context(schema):
            schedule = AgendamentoRelatorio.objects.select_related("template").get(pk=agendamento_id)
            template = getattr(schedule, "template", None)
            if template is None:
                raise ValueError("O agendamento não tem template associado.")
            user = getattr(schedule, "usuario", None) if _field_exists(AgendamentoRelatorio, "usuario") else None
            if user is None:
                user = Usuario.objects.filter(is_active=True).first() if _field_exists(Usuario, "is_active") else Usuario.objects.first()
            if user is None:
                raise ValueError("Não existe utilizador para registar a execução do relatório.")
            report = _run_template_report(template, user, getattr(schedule, "destinatarios", None))
            return {"schema": schema, "agendamento_id": schedule.pk, "relatorio_id": report.pk, "status": getattr(report, "status", "concluido")}
    except Exception as exc:
        logger.exception("Erro na execução manual do agendamento %s no schema %s", agendamento_id, schema)
        raise self.retry(exc=exc)
