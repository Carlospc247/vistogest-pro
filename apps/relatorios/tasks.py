# apps/relatorios/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta, date
import logging
from celery import shared_task, chain
from django.utils import timezone
from datetime import timedelta, date
import logging
from django.core.mail import EmailMessage
from django.conf import settings 
from .models import RelatorioGerado, AgendamentoRelatorio, MetricaKPI, AlertaGerencial
from .utils import (
    processar_relatorio_assincrono, criar_kpi_automatico,
    detectar_alertas_automaticos
)
from apps.empresas.models import Empresa

logger = logging.getLogger(__name__)


@shared_task
def processar_relatorio_task(relatorio_id):
    """
    Task para processar relatório de forma assíncrona
    """
    try:
        processar_relatorio_assincrono(relatorio_id)
        logger.info(f'Relatório {relatorio_id} processado com sucesso')
    except Exception as e:
        logger.error(f'Erro ao processar relatório {relatorio_id}: {e}')


@shared_task
def executar_agendamentos_relatorios():
    """
    Task para executar agendamentos de relatórios
    """
    try:
        agora = timezone.now()
        hora_atual = agora.time()
        
        # Buscar agendamentos ativos para a hora atual
        agendamentos = AgendamentoRelatorio.objects.filter(
            ativo=True,
            horario=hora_atual.replace(second=0, microsecond=0)
        )
        
        for agendamento in agendamentos:
            # Verificar se deve executar baseado na frequência
            deve_executar = False
            
            if agendamento.frequencia == 'diario':
                deve_executar = True
            elif agendamento.frequencia == 'semanal':
                # Executar apenas às segundas-feiras
                deve_executar = agora.weekday() == 0
            elif agendamento.frequencia == 'mensal':
                # Executar apenas no primeiro dia do mês
                deve_executar = agora.day == 1
            
            if deve_executar:
                # Gerar relatório
                relatorio = RelatorioGerado.objects.create(
                    tipo_relatorio=agendamento.template,
                    formato='pdf',  # Formato padrão para agendamentos
                    empresa=agendamento.template.empresa,
                    solicitante=agendamento.template.empresa.usuario_set.first(),  # Usuário padrão
                    data_inicio=date.today() - timedelta(days=30),
                    data_fim=date.today()
                )
                
                # Processar assincronamente
                processar_relatorio_task.delay(relatorio.id)
                
                logger.info(f'Agendamento {agendamento.id} executado - Relatório {relatorio.id} criado')
        
    except Exception as e:
        logger.error(f'Erro ao executar agendamentos: {e}')


@shared_task
def gerar_kpis_automaticos():
    """
    Task para gerar KPIs automáticos diários
    """
    try:
        hoje = date.today()
        
        for empresa in Empresa.objects.filter(ativa=True):
            # KPI de vendas diárias
            criar_kpi_automatico(
                empresa=empresa,
                codigo='VENDAS_DIA',
                nome='Vendas do Dia',
                tipo_metrica='vendas',
                periodo='diario',
                data_referencia=hoje
            )
            
            # KPI de vendas por loja
            for loja in empresa.lojas.filter(ativa=True):
                criar_kpi_automatico(
                    empresa=empresa,
                    codigo=f'VENDAS_DIA_LOJA_{loja.id}',
                    nome=f'Vendas do Dia - {loja.nome}',
                    tipo_metrica='vendas',
                    periodo='diario',
                    data_referencia=hoje,
                    loja=loja
                )
        
        logger.info('KPIs automáticos gerados com sucesso')
        
    except Exception as e:
        logger.error(f'Erro ao gerar KPIs automáticos: {e}')


@shared_task
def detectar_alertas_task():
    """
    Task para detectar alertas automáticos
    """
    try:
        for empresa in Empresa.objects.filter(ativa=True):
            alertas = detectar_alertas_automaticos(empresa)
            
            if alertas:
                logger.info(f'Criados {len(alertas)} alertas para empresa {empresa.nome}')
        
    except Exception as e:
        logger.error(f'Erro ao detectar alertas: {e}')


@shared_task
def limpar_relatorios_antigos():
    """
    Task para limpar relatórios antigos
    """
    try:
        # Remover relatórios com mais de 90 dias
        data_limite = timezone.now() - timedelta(days=90)
        
        relatorios_antigos = RelatorioGerado.objects.filter(
            data_solicitacao__lt=data_limite
        )
        
        count = relatorios_antigos.count()
        
        # Remover arquivos físicos
        for relatorio in relatorios_antigos:
            if relatorio.arquivo_resultado:
                try:
                    relatorio.arquivo_resultado.delete()
                except:
                    pass
        
        # Remover registros
        relatorios_antigos.delete()
        
        logger.info(f'Removidos {count} relatórios antigos')
        
    except Exception as e:
        logger.error(f'Erro ao limpar relatórios antigos: {e}')


@shared_task
def gerar_relatorio_mensal():
    """
    Task para gerar relatórios mensais automáticos
    """
    try:
        hoje = date.today()
        
        # Executar apenas no primeiro dia do mês
        if hoje.day != 1:
            return
        
        # Calcular período do mês anterior
        primeiro_dia_mes_anterior = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
        ultimo_dia_mes_anterior = hoje.replace(day=1) - timedelta(days=1)
        
        for empresa in Empresa.objects.filter(ativa=True):
            # Relatório de vendas mensais
            relatorio = RelatorioGerado.objects.create(
                tipo_relatorio=empresa.tipos_relatorio.filter(codigo='VENDAS_MENSAL').first(),
                formato='pdf',
                empresa=empresa,
                solicitante=empresa.usuario_set.first(),
                data_inicio=primeiro_dia_mes_anterior,
                data_fim=ultimo_dia_mes_anterior
            )
            
            if relatorio.tipo_relatorio:
                processar_relatorio_task.delay(relatorio.id)
                logger.info(f'Relatório mensal criado para empresa {empresa.nome}')
        
    except Exception as e:
        logger.error(f'Erro ao gerar relatórios mensais: {e}')


@shared_task
def enviar_relatorio_email_task(resultado_processamento, relatorio_id: int, destinatarios: list):
    """
    Task para enviar um relatório gerado por e-mail com o ficheiro em anexo.
    Recebe o resultado da task anterior na chain.
    """
    try:
        relatorio = RelatorioGerado.objects.get(id=relatorio_id)

        # Verificar se o relatório foi concluído com sucesso e tem um ficheiro
        if relatorio.status != 'concluido' or not relatorio.arquivo_resultado:
            logger.warning(f"Envio de e-mail para relatório {relatorio_id} cancelado: relatório não está concluído ou não tem ficheiro.")
            return

        # Construir o e-mail
        assunto = f"Relatório Gerado: {relatorio.tipo_relatorio.nome}"
        corpo_email = f"""
        Olá,

        O relatório '{relatorio.tipo_relatorio.nome}' solicitado foi gerado com sucesso e encontra-se em anexo.

        Período de Análise: {relatorio.data_inicio} a {relatorio.data_fim}

        Atenciosamente,
        Sistema de Relatórios Pharmassys
        """
        
        from_email = settings.DEFAULT_FROM_EMAIL
        
        email = EmailMessage(
            assunto,
            corpo_email,
            from_email,
            destinatarios
        )

        # Anexar o ficheiro
        nome_arquivo = relatorio.arquivo_resultado.name.split('/')[-1]
        mime_type = 'application/pdf' # Ajuste se usar outros formatos
        if '.xlsx' in nome_arquivo:
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif '.csv' in nome_arquivo:
            mime_type = 'text/csv'

        email.attach(
            nome_arquivo, 
            relatorio.arquivo_resultado.read(), 
            mime_type
        )
        
        # Enviar
        email.send()
        
        logger.info(f"Relatório {relatorio.id} enviado com sucesso para: {', '.join(destinatarios)}")

    except RelatorioGerado.DoesNotExist:
        logger.error(f"Não foi possível enviar e-mail: Relatório com ID {relatorio_id} não encontrado.")
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail para relatório {relatorio_id}: {e}")

