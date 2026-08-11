# apps/relatorios/utils.py
import logging
import json
import os
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, List, Any, Optional
from django.db.models import Q, Sum, Count, Avg, Max, Min, F
from django.utils import timezone
from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.http import HttpResponse
import numpy as np
import pandas as pd
import openpyxl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import csv
import io

from .models import (
    RelatorioGerado, MetricaKPI, AnaliseVendas, AnaliseEstoque, 
    AnaliseClientes, AlertaGerencial
)
from apps.vendas.models import Venda, ItemVenda
from apps.produtos.models import Produto
from apps.clientes.models import Cliente
from apps.funcionarios.models import Funcionario
from statsmodels.tsa.api import Holt
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from django.db.models.functions import TruncMonth







logger = logging.getLogger(__name__)


def calcular_metricas_vendas(empresa, data_inicio: date, data_fim: date) -> Dict[str, Any]:
    """
    Calcular métricas de vendas para o período especificado
    """
    try:
        # Query base
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        )
        
        
        # Métricas básicas
        total_vendas = vendas.count()
        faturamento_total = vendas.aggregate(Sum('total'))['total__sum'] or 0
        ticket_medio = vendas.aggregate(Avg('total'))['total__avg'] or 0
        
        # Itens vendidos
        total_itens = ItemVenda.objects.filter(
            venda__in=vendas
        ).aggregate(Sum('quantidade'))['quantidade__sum'] or 0
        
        # Vendas por dia
        vendas_por_dia = {}
        current_date = data_inicio
        while current_date <= data_fim:
            vendas_dia = vendas.filter(data_venda=current_date)
            vendas_por_dia[current_date.isoformat()] = {
                'quantidade': vendas_dia.count(),
                'valor': float(vendas_dia.aggregate(Sum('total'))['total__sum'] or 0)
            }
            current_date += timedelta(days=1)
        
        # Top produtos
        top_produtos = ItemVenda.objects.filter(
            venda__in=vendas
        ).values(
            'produto__nome_comercial'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            total=Sum(F('quantidade') * F('preco_unitario'))
        ).order_by('-quantidade_vendida')[:10]
        
        # Top clientes
        top_clientes = vendas.values(
            'cliente__nome',
            'cliente__cpf_cnpj'
        ).annotate(
            total_compras=Count('id'),
            total=Sum('total')
        ).order_by('-total')[:10]
        
        # Comparar com período anterior
        dias_periodo = (data_fim - data_inicio).days + 1
        data_inicio_anterior = data_inicio - timedelta(days=dias_periodo)
        data_fim_anterior = data_inicio - timedelta(days=1)
        
        vendas_anterior = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio_anterior,
            data_venda__lte=data_fim_anterior,
            status='finalizada'
        )
        
        
        faturamento_anterior = vendas_anterior.aggregate(Sum('total'))['total__sum'] or 0
        
        variacao_faturamento = 0
        if faturamento_anterior > 0:
            variacao_faturamento = ((faturamento_total - faturamento_anterior) / faturamento_anterior) * 100
        
        return {
            'total_vendas': total_vendas,
            'faturamento_total': float(faturamento_total),
            'ticket_medio': float(ticket_medio),
            'total_itens': total_itens,
            'vendas_por_dia': vendas_por_dia,
            'top_produtos': list(top_produtos),
            'top_clientes': list(top_clientes),
            'faturamento_anterior': float(faturamento_anterior),
            'variacao_faturamento': variacao_faturamento,
            'periodo': {
                'inicio': data_inicio.isoformat(),
                'fim': data_fim.isoformat(),
                'dias': dias_periodo
            }
        }
        
    except Exception as e:
        logger.error(f'Erro ao calcular métricas de vendas: {e}')
        return {}


def calcular_analise_abc_produtos(empresa, data_inicio: date, data_fim: date) -> Dict[str, Any]:
    """
    Calcular análise ABC de produtos baseada em faturamento
    """
    try:
        # Query base
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        )
        
        
        # Faturamento por produto
        produtos_faturamento = ItemVenda.objects.filter(
            venda__in=vendas
        ).values(
            'produto__id',
            'produto__nome_comercial',
            'produto__codigo'
        ).annotate(
            quantidade_vendida=Sum('quantidade'),
            faturamento=Sum(F('quantidade') * F('preco_unitario'))
        ).order_by('-faturamento')
        
        # Calcular participação percentual
        faturamento_total = sum(item['faturamento'] for item in produtos_faturamento)
        
        produtos_com_participacao = []
        faturamento_acumulado = 0
        
        for produto in produtos_faturamento:
            faturamento_acumulado += produto['faturamento']
            participacao = (produto['faturamento'] / faturamento_total) * 100 if faturamento_total > 0 else 0
            participacao_acumulada = (faturamento_acumulado / faturamento_total) * 100 if faturamento_total > 0 else 0
            
            # Classificação ABC
            if participacao_acumulada <= 80:
                classe = 'A'
            elif participacao_acumulada <= 95:
                classe = 'B'
            else:
                classe = 'C'
            
            produtos_com_participacao.append({
                'produto_id': produto['produto__id'],
                'nome': produto['produto__nome_comercial'],
                'codigo': produto['produto__codigo'],
                'quantidade_vendida': produto['quantidade_vendida'],
                'faturamento': float(produto['faturamento']),
                'participacao': participacao,
                'participacao_acumulada': participacao_acumulada,
                'classe': classe
            })
        
        # Separar por classe
        classe_a = [p for p in produtos_com_participacao if p['classe'] == 'A']
        classe_b = [p for p in produtos_com_participacao if p['classe'] == 'B']
        classe_c = [p for p in produtos_com_participacao if p['classe'] == 'C']
        
        return {
            'faturamento_total': float(faturamento_total),
            'total_produtos': len(produtos_com_participacao),
            'classe_a': {
                'produtos': classe_a,
                'quantidade': len(classe_a),
                'faturamento': sum(p['faturamento'] for p in classe_a)
            },
            'classe_b': {
                'produtos': classe_b,
                'quantidade': len(classe_b),
                'faturamento': sum(p['faturamento'] for p in classe_b)
            },
            'classe_c': {
                'produtos': classe_c,
                'quantidade': len(classe_c),
                'faturamento': sum(p['faturamento'] for p in classe_c)
            },
            'periodo': {
                'inicio': data_inicio.isoformat(),
                'fim': data_fim.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f'Erro ao calcular análise ABC: {e}')
        return {}


def calcular_segmentacao_rfm_clientes(empresa, data_inicio: date, data_fim: date) -> Dict[str, Any]:
    """
    Calcular segmentação RFM (Recência, Frequência, Valor Monetário) de clientes
    """
    try:
        # Query base
        vendas = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada',
            cliente__isnull=False
        )
        
        
        # Calcular métricas RFM por cliente
        clientes_rfm = []
        
        for cliente in Cliente.objects.filter(empresa=empresa, ativo=True):
            vendas_cliente = vendas.filter(cliente=cliente)
            
            if not vendas_cliente.exists():
                continue
            
            # Recência (dias desde a última compra)
            ultima_compra = vendas_cliente.order_by('-data_venda').first()
            recencia = (data_fim - ultima_compra.data_venda).days
            
            # Frequência (número de compras)
            frequencia = vendas_cliente.count()
            
            # Valor Monetário (total gasto)
            valor_monetario = vendas_cliente.aggregate(Sum('total'))['total__sum'] or 0
            
            clientes_rfm.append({
                'cliente_id': cliente.id,
                'nome': cliente.nome,
                'cpf_cnpj': cliente.cpf_cnpj,
                'recencia': recencia,
                'frequencia': frequencia,
                'valor_monetario': float(valor_monetario)
            })
        
        if not clientes_rfm:
            return {'erro': 'Nenhum cliente com vendas no período'}
        
        # Calcular quintis para cada métrica
        clientes_rfm.sort(key=lambda x: x['recencia'])
        quintil_size = len(clientes_rfm) // 5
        
        for i, cliente in enumerate(clientes_rfm):
            # Score de Recência (inverso - menor recência = maior score)
            if i < quintil_size:
                cliente['r_score'] = 5
            elif i < quintil_size * 2:
                cliente['r_score'] = 4
            elif i < quintil_size * 3:
                cliente['r_score'] = 3
            elif i < quintil_size * 4:
                cliente['r_score'] = 2
            else:
                cliente['r_score'] = 1
        
        # Frequência
        clientes_rfm.sort(key=lambda x: x['frequencia'], reverse=True)
        for i, cliente in enumerate(clientes_rfm):
            if i < quintil_size:
                cliente['f_score'] = 5
            elif i < quintil_size * 2:
                cliente['f_score'] = 4
            elif i < quintil_size * 3:
                cliente['f_score'] = 3
            elif i < quintil_size * 4:
                cliente['f_score'] = 2
            else:
                cliente['f_score'] = 1
        
        # Valor Monetário
        clientes_rfm.sort(key=lambda x: x['valor_monetario'], reverse=True)
        for i, cliente in enumerate(clientes_rfm):
            if i < quintil_size:
                cliente['m_score'] = 5
            elif i < quintil_size * 2:
                cliente['m_score'] = 4
            elif i < quintil_size * 3:
                cliente['m_score'] = 3
            elif i < quintil_size * 4:
                cliente['m_score'] = 2
            else:
                cliente['m_score'] = 1
        
        # Segmentação baseada nos scores
        for cliente in clientes_rfm:
            r, f, m = cliente['r_score'], cliente['f_score'], cliente['m_score']
            
            if r >= 4 and f >= 4 and m >= 4:
                cliente['segmento'] = 'Champions'
            elif r >= 3 and f >= 3 and m >= 3:
                cliente['segmento'] = 'Cliente Leal'
            elif r >= 4 and f <= 2:
                cliente['segmento'] = 'Novo Cliente'
            elif r <= 2 and f >= 3 and m >= 3:
                cliente['segmento'] = 'Em Risco'
            elif r <= 2 and f <= 2:
                cliente['segmento'] = 'Perdido'
            else:
                cliente['segmento'] = 'Outros'
        
        # Agrupar por segmento
        segmentos = {}
        for cliente in clientes_rfm:
            segmento = cliente['segmento']
            if segmento not in segmentos:
                segmentos[segmento] = []
            segmentos[segmento].append(cliente)
        
        return {
            'total_clientes': len(clientes_rfm),
            'segmentos': segmentos,
            'clientes_detalhados': clientes_rfm,
            'periodo': {
                'inicio': data_inicio.isoformat(),
                'fim': data_fim.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f'Erro ao calcular segmentação RFM: {e}')
        return {}


def gerar_relatorio_pdf(dados: Dict[str, Any], titulo: str, template_name: str = None) -> bytes:
    """
    Gerar relatório em formato PDF
    """
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        heading_style = styles['Heading2']
        normal_style = styles['Normal']
        
        # Título
        story.append(Paragraph(titulo, title_style))
        story.append(Paragraph("<br/><br/>", normal_style))
        
        # Dados gerais
        if 'resumo' in dados:
            story.append(Paragraph("Resumo Executivo", heading_style))
            for key, value in dados['resumo'].items():
                story.append(Paragraph(f"<b>{key}:</b> {value}", normal_style))
            story.append(Paragraph("<br/>", normal_style))
        
        # Tabelas de dados
        if 'tabelas' in dados:
            for tabela_nome, tabela_dados in dados['tabelas'].items():
                story.append(Paragraph(tabela_nome, heading_style))
                
                if tabela_dados:
                    # Cabeçalhos
                    headers = list(tabela_dados[0].keys())
                    table_data = [headers]
                    
                    # Dados
                    for row in tabela_dados[:20]:  # Limitar a 20 linhas
                        table_data.append([str(row.get(header, '')) for header in headers])
                    
                    # Criar tabela
                    table = Table(table_data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    
                    story.append(table)
                    story.append(Paragraph("<br/>", normal_style))
        
        # Construir PDF
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f'Erro ao gerar PDF: {e}')
        return b''


def gerar_relatorio_excel(dados: Dict[str, Any], titulo: str) -> bytes:
    """
    Gerar relatório em formato Excel
    """
    try:
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Resumo
            if 'resumo' in dados:
                resumo_df = pd.DataFrame(list(dados['resumo'].items()), 
                                       columns=['Métrica', 'Valor'])
                resumo_df.to_excel(writer, sheet_name='Resumo', index=False)
            
            # Tabelas de dados
            if 'tabelas' in dados:
                for nome, tabela_dados in dados['tabelas'].items():
                    if tabela_dados:
                        df = pd.DataFrame(tabela_dados)
                        # Limitar nome da aba (Excel tem limite de 31 caracteres)
                        sheet_name = nome[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Dados detalhados
            if 'dados_detalhados' in dados and isinstance(dados['dados_detalhados'], list):
                df_detalhes = pd.DataFrame(dados['dados_detalhados'])
                df_detalhes.to_excel(writer, sheet_name='Dados Detalhados', index=False)
        
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f'Erro ao gerar Excel: {e}')
        return b''


def gerar_relatorio_csv(dados: Dict[str, Any], titulo: str) -> str:
    """
    Gerar relatório em formato CSV
    """
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Título
        writer.writerow([titulo])
        writer.writerow([])  # Linha vazia
        
        # Resumo
        if 'resumo' in dados:
            writer.writerow(['RESUMO'])
            for key, value in dados['resumo'].items():
                writer.writerow([key, value])
            writer.writerow([])  # Linha vazia
        
        # Dados principais
        if 'dados_principais' in dados and isinstance(dados['dados_principais'], list):
            if dados['dados_principais']:
                # Cabeçalhos
                headers = list(dados['dados_principais'][0].keys())
                writer.writerow(headers)
                
                # Dados
                for row in dados['dados_principais']:
                    writer.writerow([row.get(header, '') for header in headers])
        
        return output.getvalue()
        
    except Exception as e:
        logger.error(f'Erro ao gerar CSV: {e}')
        return ''


def processar_relatorio_assincrono(relatorio_id: int):
    """
    Processar relatório de forma assíncrona
    """
    try:
        relatorio = RelatorioGerado.objects.get(id=relatorio_id)
        relatorio.status = 'processando'
        relatorio.data_inicio_processamento = timezone.now()
        relatorio.save()
        
        # Determinar tipo de processamento baseado no tipo de relatório
        tipo_codigo = relatorio.tipo_relatorio.codigo
        
        if tipo_codigo == 'VENDAS_GERAL':
            dados = processar_relatorio_vendas(relatorio)
        elif tipo_codigo == 'ANALISE_ABC':
            dados = processar_relatorio_abc(relatorio)
        elif tipo_codigo == 'SEGMENTACAO_RFM':
            dados = processar_relatorio_rfm(relatorio)
        else:
            # Processamento genérico
            dados = processar_relatorio_generico(relatorio)
        
        if dados:
            # Gerar arquivo no formato solicitado
            if relatorio.formato == 'pdf':
                conteudo = gerar_relatorio_pdf(dados, relatorio.tipo_relatorio.nome)
                nome_arquivo = f'{relatorio.codigo_relatorio}.pdf'
            elif relatorio.formato == 'excel':
                conteudo = gerar_relatorio_excel(dados, relatorio.tipo_relatorio.nome)
                nome_arquivo = f'{relatorio.codigo_relatorio}.xlsx'
            elif relatorio.formato == 'csv':
                conteudo = gerar_relatorio_csv(dados, relatorio.tipo_relatorio.nome)
                nome_arquivo = f'{relatorio.codigo_relatorio}.csv'
            elif relatorio.formato == 'json':
                conteudo = json.dumps(dados, indent=2, ensure_ascii=False, default=str).encode('utf-8')
                nome_arquivo = f'{relatorio.codigo_relatorio}.json'
            else:
                raise ValueError(f'Formato não suportado: {relatorio.formato}')
            
            # Salvar arquivo
            if isinstance(conteudo, str):
                conteudo = conteudo.encode('utf-8')
            
            relatorio.arquivo_resultado.save(
                nome_arquivo,
                ContentFile(conteudo),
                save=False
            )
            
            # Salvar dados do resultado
            relatorio.dados_resultado = dados
            relatorio.total_registros = dados.get('total_registros', 0)
            relatorio.status = 'concluido'
        else:
            relatorio.status = 'erro'
            relatorio.mensagem_erro = 'Erro ao processar dados do relatório'
        
        # Finalizar
        relatorio.data_conclusao = timezone.now()
        relatorio.tempo_processamento = relatorio.data_conclusao - relatorio.data_inicio_processamento
        relatorio.save()
        
        logger.info(f'Relatório {relatorio.codigo_relatorio} processado com sucesso')
        
    except Exception as e:
        logger.error(f'Erro ao processar relatório {relatorio_id}: {e}')
        try:
            relatorio = RelatorioGerado.objects.get(id=relatorio_id)
            relatorio.status = 'erro'
            relatorio.mensagem_erro = str(e)
            relatorio.data_conclusao = timezone.now()
            if relatorio.data_inicio_processamento:
                relatorio.tempo_processamento = relatorio.data_conclusao - relatorio.data_inicio_processamento
            relatorio.save()
        except:
            pass


def processar_relatorio_vendas(relatorio: RelatorioGerado) -> Dict[str, Any]:
    """
    Processar relatório específico de vendas
    """
    dados = calcular_metricas_vendas(
        empresa=relatorio.empresa,
        data_inicio=relatorio.data_inicio,
        data_fim=relatorio.data_fim,
       )
    
    # Estruturar dados para o relatório
    return {
        'titulo': 'Relatório de Vendas',
        'periodo': dados.get('periodo', {}),
        'resumo': {
            'Total de Vendas': dados.get('total_vendas', 0),
            'Faturamento Total': f"AO {dados.get('faturamento_total', 0):,.2f}",
            'Ticket Médio': f"AO {dados.get('ticket_medio', 0):,.2f}",
            'Total de Itens': dados.get('total_itens', 0),
            'Variação vs Período Anterior': f"{dados.get('variacao_faturamento', 0):.1f}%"
        },
        'tabelas': {
            'Top Produtos': dados.get('top_produtos', []),
            'Top Clientes': dados.get('top_clientes', [])
        },
        'dados_detalhados': dados,
        'total_registros': dados.get('total_vendas', 0)
    }


def processar_relatorio_abc(relatorio: RelatorioGerado) -> Dict[str, Any]:
    """
    Processar relatório de análise ABC
    """
    dados = calcular_analise_abc_produtos(
        empresa=relatorio.empresa,
        data_inicio=relatorio.data_inicio,
        data_fim=relatorio.data_fim,
    )
    
    return {
        'titulo': 'Análise ABC de Produtos',
        'periodo': dados.get('periodo', {}),
        'resumo': {
            'Faturamento Total': f"AO {dados.get('faturamento_total', 0):,.2f}",
            'Total de Produtos': dados.get('total_produtos', 0),
            'Produtos Classe A': dados.get('classe_a', {}).get('quantidade', 0),
            'Produtos Classe B': dados.get('classe_b', {}).get('quantidade', 0),
            'Produtos Classe C': dados.get('classe_c', {}).get('quantidade', 0)
        },
        'tabelas': {
            'Produtos Classe A': dados.get('classe_a', {}).get('produtos', []),
            'Produtos Classe B': dados.get('classe_b', {}).get('produtos', []),
            'Produtos Classe C': dados.get('classe_c', {}).get('produtos', [])
        },
        'dados_detalhados': dados,
        'total_registros': dados.get('total_produtos', 0)
    }


def processar_relatorio_rfm(relatorio: RelatorioGerado) -> Dict[str, Any]:
    """
    Processar relatório de segmentação RFM
    """
    dados = calcular_segmentacao_rfm_clientes(
        empresa=relatorio.empresa,
        data_inicio=relatorio.data_inicio,
        data_fim=relatorio.data_fim,
    )
    
    # Preparar resumo por segmento
    resumo_segmentos = {}
    for segmento, clientes in dados.get('segmentos', {}).items():
        resumo_segmentos[f'Clientes {segmento}'] = len(clientes)
    
    return {
        'titulo': 'Segmentação RFM de Clientes',
        'periodo': dados.get('periodo', {}),
        'resumo': {
            'Total de Clientes': dados.get('total_clientes', 0),
            **resumo_segmentos
        },
        'tabelas': {
            segmento: clientes for segmento, clientes in dados.get('segmentos', {}).items()
        },
        'dados_detalhados': dados,
        'total_registros': dados.get('total_clientes', 0)
    }


def processar_relatorio_generico(relatorio: RelatorioGerado) -> Dict[str, Any]:
    """
    Processamento genérico para outros tipos de relatório
    """
    return {
        'titulo': relatorio.tipo_relatorio.nome,
        'periodo': {
            'inicio': relatorio.data_inicio.isoformat() if relatorio.data_inicio else None,
            'fim': relatorio.data_fim.isoformat() if relatorio.data_fim else None
        },
        'resumo': {
            'Status': 'Processado com sucesso',
            'Formato': relatorio.formato.upper()
        },
        'dados_detalhados': {
            'parametros': relatorio.parametros,
            'filtros_aplicados': {
                'categorias': [cat.nome for cat in relatorio.categorias.all()],
                'funcionarios': [func.user.get_full_name() for func in relatorio.funcionarios.all()]
            }
        },
        'total_registros': 1
    }


def criar_kpi_automatico(empresa, codigo: str, nome: str, tipo_metrica: str, 
                        periodo: str, data_referencia: date) -> Optional[MetricaKPI]:
    """
    Criar KPI automaticamente baseado em regras de negócio
    """
    try:
        # Verificar se já existe
        existing = MetricaKPI.objects.filter(
            empresa=empresa,
            codigo=codigo,
            data_referencia=data_referencia
        ).first()
        
        if existing:
            return existing
        
        # Calcular valor baseado no tipo
        valor_atual = 0
        valor_anterior = 0
        detalhes_calculo = {}
        
        if codigo == 'VENDAS_DIA':
            vendas_dia = Venda.objects.filter(
                empresa=empresa,
                data_venda=data_referencia,
                status='finalizada'
            )
            
            valor_atual = vendas_dia.aggregate(Sum('total'))['total__sum'] or 0
            
            # Valor do dia anterior
            data_anterior = data_referencia - timedelta(days=1)
            vendas_anterior = Venda.objects.filter(
                empresa=empresa,
                data_venda=data_anterior,
                status='finalizada'
            )
            
            valor_anterior = vendas_anterior.aggregate(Sum('total'))['total__sum'] or 0
            
            detalhes_calculo = {
                'total_vendas': vendas_dia.count(),
                'ticket_medio': vendas_dia.aggregate(Avg('total'))['total__avg'] or 0
            }
        
        # Criar KPI
        kpi = MetricaKPI.objects.create(
            empresa=empresa,
            codigo=codigo,
            nome=nome,
            tipo_metrica=tipo_metrica,
            periodo=periodo,
            data_referencia=data_referencia,
            valor_atual=valor_atual,
            valor_anterior=valor_anterior,
            detalhes_calculo=detalhes_calculo,
            formato_exibicao='moeda' if 'vendas' in codigo.lower() else 'numero'
        )
        
        return kpi
        
    except Exception as e:
        logger.error(f'Erro ao criar KPI automático: {e}')
        return None


def detectar_alertas_automaticos(empresa):
    """
    Detectar e criar alertas automáticos baseados em métricas
    """
    try:
        alertas_criados = []
        hoje = date.today()
        
        # 1. Verificar vendas baixas
        vendas_hoje = Venda.objects.filter(
            empresa=empresa,
            data_venda=hoje,
            status='finalizada'
        ).aggregate(Sum('total'))['total__sum'] or 0
        
        # Média dos últimos 7 dias
        data_inicio_semana = hoje - timedelta(days=7)
        vendas_semana = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio_semana,
            data_venda__lt=hoje,
            status='finalizada'
        ).aggregate(Sum('total'))['total__sum'] or 0
        
        media_diaria = vendas_semana / 7 if vendas_semana > 0 else 0
        
        # Se vendas de hoje estão 30% abaixo da média
        if media_diaria > 0 and vendas_hoje < (media_diaria * 0.7):
            alerta = AlertaGerencial.objects.create(
                empresa=empresa,
                tipo_alerta='queda_vendas',
                prioridade='alta',
                titulo=f'Vendas baixas detectadas',
                descricao=f'Vendas de hoje (AO {vendas_hoje:,.2f}) estão 30% abaixo da média semanal (AO {media_diaria:,.2f})',
                valor_atual=vendas_hoje,
                valor_esperado=media_diaria,
                data_referencia=hoje,
                acoes_recomendadas=[
                    'Verificar problemas operacionais',
                    'Analisar concorrência',
                    'Revisar estratégias de marketing',
                    'Verificar satisfação dos clientes'
                ]
            )
            alertas_criados.append(alerta)
        
        # 2. Verificar produtos sem estoque
        produtos_sem_estoque = Produto.objects.filter(
            empresa=empresa,
            ativo=True,
            estoque_atual=0
        ).count()
        
        if produtos_sem_estoque > 0:
            alerta = AlertaGerencial.objects.create(
                empresa=empresa,
                tipo_alerta='estoque_baixo',
                prioridade='media',
                titulo=f'{produtos_sem_estoque} produto(s) sem estoque',
                descricao=f'Foram detectados {produtos_sem_estoque} produtos com estoque zerado',
                valor_atual=produtos_sem_estoque,
                data_referencia=hoje,
                acoes_recomendadas=[
                    'Verificar produtos em falta',
                    'Contactar fornecedores',
                    'Atualizar previsão de entrega',
                    'Comunicar clientes se necessário'
                ]
            )
            alertas_criados.append(alerta)
        
        return alertas_criados
        
    except Exception as e:
        logger.error(f'Erro ao detectar alertas automáticos: {e}')
        return []


def gerar_dashboard_dados(dashboard_config, periodo_dias: int = 30) -> Dict[str, Any]:
    """
    Gerar dados para dashboard personalizado
    """
    try:
        empresa = dashboard_config.empresa
        data_inicio = date.today() - timedelta(days=periodo_dias)
        data_fim = date.today()
        
        dados_widgets = {}
        
        for widget in dashboard_config.widgets_incluidos:
            widget_id = widget.get('id')
            widget_type = widget.get('type')
            
            if widget_type == 'vendas_resumo':
                dados_widgets[widget_id] = calcular_metricas_vendas(
                    empresa, data_inicio, data_fim
                )
            
            elif widget_type == 'top_produtos':
                # Top 10 produtos por faturamento
                vendas = Venda.objects.filter(
                    empresa=empresa,
                    data_venda__gte=data_inicio,
                    data_venda__lte=data_fim,
                    status='finalizada'
                )
                
                top_produtos = ItemVenda.objects.filter(
                    venda__in=vendas
                ).values(
                    'produto__nome_comercial'
                ).annotate(
                    faturamento=Sum(F('quantidade') * F('preco_unitario'))
                ).order_by('-faturamento')[:10]
                
                dados_widgets[widget_id] = list(top_produtos)
            
            elif widget_type == 'alertas_ativos':
                alertas = AlertaGerencial.objects.filter(
                    empresa=empresa,
                    ativo=True
                ).order_by('-prioridade')[:5]
                
                dados_widgets[widget_id] = [
                    {
                        'titulo': alerta.titulo,
                        'prioridade': alerta.prioridade,
                        'tipo': alerta.tipo_alerta,
                        'data': alerta.data_referencia.isoformat()
                    }
                    for alerta in alertas
                ]
            
            elif widget_type == 'kpis_principais':
                kpis = MetricaKPI.objects.filter(
                    empresa=empresa,
                    data_referencia=data_fim
                ).order_by('tipo_metrica')[:6]
                
                dados_widgets[widget_id] = [
                    {
                        'nome': kpi.nome,
                        'valor_atual': float(kpi.valor_atual),
                        'formato': kpi.formato_exibicao,
                        'variacao': float(kpi.variacao_percentual),
                        'status_meta': kpi.status_meta
                    }
                    for kpi in kpis
                ]
        
        return {
            'dashboard_id': dashboard_config.id,
            'nome': dashboard_config.nome,
            'periodo': {
                'inicio': data_inicio.isoformat(),
                'fim': data_fim.isoformat(),
                'dias': periodo_dias
            },
            'widgets': dados_widgets,
            'ultima_atualizacao': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f'Erro ao gerar dados do dashboard: {e}')
        return {}


def exportar_dashboard_pdf(dashboard_config, dados_dashboard: Dict[str, Any]) -> bytes:
    """
    Exportar dashboard como PDF
    """
    try:
        # Usar template HTML para renderizar o dashboard
        html_content = render_to_string('relatorios/dashboard_pdf.html', {
            'dashboard': dashboard_config,
            'dados': dados_dashboard
        })
        
        # Converter HTML para PDF usando alguma biblioteca como WeasyPrint
        # Por enquanto, retornar PDF simples
        return gerar_relatorio_pdf(dados_dashboard, f'Dashboard: {dashboard_config.nome}')
        
    except Exception as e:
        logger.error(f'Erro ao exportar dashboard PDF: {e}')
        return b''



def calcular_previsao_vendas(empresa, data_inicio: date, data_fim: date, periodos_previsao: int = 3) -> Dict[str, Any]:
    """
    Calcular previsão de vendas para os próximos períodos usando Holt's Linear Trend Model.
    """
    try:
        # Agrupar vendas por mês para a série temporal
        vendas_mensais = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        ).annotate(
            mes=TruncMonth('data_venda')
        ).values('mes').annotate(
            faturamento=Sum('total')
        ).order_by('mes')
        
        if len(vendas_mensais) < 4: # Requer um mínimo de dados para prever
            return {'erro': 'Dados insuficientes para gerar previsão.'}
        
        # Preparar dados para o pandas
        df = pd.DataFrame(list(vendas_mensais))
        df['mes'] = pd.to_datetime(df['mes'])
        df = df.set_index('mes')
        
        # Treinar o modelo de previsão (Holt's)
        modelo = Holt(df['faturamento'], initialization_method="estimated").fit()
        previsao = modelo.forecast(periodos_previsao)
        
        return {
            'historico': df.reset_index().to_dict('records'),
            'previsao': {
                'periodos': periodos_previsao,
                'valores': previsao.to_dict()
            },
            'modelo': 'Holt Linear Trend'
        }
        
    except Exception as e:
        logger.error(f'Erro ao calcular previsão de vendas: {e}')
        return {}


def analisar_sazonalidade(empresa, data_inicio: date, data_fim: date, periodo: int = 12) -> Dict[str, Any]:
    """
    Analisar a sazonalidade das vendas, decompondo a série temporal.
    """
    try:
        vendas_mensais = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        ).annotate(
            mes=TruncMonth('data_venda')
        ).values('mes').annotate(
            faturamento=Sum('total')
        ).order_by('mes')

        if len(vendas_mensais) < periodo * 2: # Requer pelo menos 2 ciclos completos
            return {'erro': 'Dados insuficientes para análise de sazonalidade.'}

        df = pd.DataFrame(list(vendas_mensais), columns=['mes', 'faturamento']).set_index('mes')
        
        # Decompor a série
        decomposicao = seasonal_decompose(df['faturamento'], model='additive', period=periodo)
        
        sazonalidade = decomposicao.seasonal.reset_index().to_dict('records')
        tendencia = decomposicao.trend.dropna().reset_index().to_dict('records')
        
        # Encontrar picos de sazonalidade
        pico = max(sazonalidade, key=lambda x: x['seasonal'])
        vale = min(sazonalidade, key=lambda x: x['seasonal'])

        return {
            'sazonalidade': sazonalidade,
            'tendencia': tendencia,
            'pico_sazonal': pico,
            'vale_sazonal': vale
        }

    except Exception as e:
        logger.error(f'Erro ao analisar sazonalidade: {e}')
        return {}


def calcular_tendencias(empresa, data_inicio: date, data_fim: date) -> Dict[str, Any]:
    """
    Calcular a tendência geral de uma métrica (ex: faturamento) usando regressão linear.
    """
    try:
        vendas_mensais = Venda.objects.filter(
            empresa=empresa,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
            status='finalizada'
        ).annotate(
            mes=TruncMonth('data_venda')
        ).values('mes').annotate(
            faturamento=Sum('total')
        ).order_by('mes')

        if len(vendas_mensais) < 2:
            return {'erro': 'Dados insuficientes para calcular tendência.'}

        df = pd.DataFrame(list(vendas_mensais))
        df['periodo'] = range(len(df)) # Eixo X (tempo)

        # Regressão Linear com numpy
        coeficientes = np.polyfit(df['periodo'], df['faturamento'], 1)
        inclinacao = coeficientes[0]

        if inclinacao > 5: # Threshold para considerar crescimento
            tendencia = 'Crescimento'
        elif inclinacao < -5:
            tendencia = 'Declínio'
        else:
            tendencia = 'Estável'
            
        return {
            'dados': df.to_dict('records'),
            'inclinacao': inclinacao,
            'tendencia': tendencia
        }

    except Exception as e:
        logger.error(f'Erro ao calcular tendências: {e}')
        return {}


def gerar_cubo_olap(empresa, data_inicio: date, data_fim: date, dimensoes: List[str], metrica: str) -> Dict[str, Any]:
    """
    Gerar um cubo de dados (pivot table) para análise multidimensional.
    Ex: dimensoes=['categoria__nome'], metrica='total'
    """
    try:
        dados_flat = Venda.objects.filter(
            empresa=empresa, data_venda__range=(data_inicio, data_fim), status='finalizada'
        ).values(*dimensoes, metrica)
        
        if not dados_flat:
            return {'erro': 'Nenhum dado encontrado para os filtros selecionados.'}

        df = pd.DataFrame(list(dados_flat))
        
        # Cria a pivot table (o cubo)
        cubo = pd.pivot_table(
            df, 
            index=dimensoes[0], 
            columns=dimensoes[1] if len(dimensoes) > 1 else None, 
            values=metrica, 
            aggfunc='sum', 
            fill_value=0
        )
        
        return {
            'dimensoes': dimensoes,
            'metrica': metrica,
            'cubo_html': cubo.to_html(classes='table table-bordered table-striped')
        }
        
    except Exception as e:
        logger.error(f'Erro ao gerar cubo OLAP: {e}')
        return {}


def executar_data_mining(empresa, data_inicio: date, data_fim: date, n_clusters: int = 4) -> Dict[str, Any]:
    """
    Executar data mining para segmentação de clientes usando K-Means.
    """
    try:
        dados_clientes = Cliente.objects.filter(
            empresa=empresa,
            venda__data_venda__range=(data_inicio, data_fim)
        ).annotate(
            faturamento_total=Sum('venda__total'),
            frequencia=Count('venda__id'),
            ticket_medio=Avg('venda__total')
        ).values('id', 'nome', 'faturamento_total', 'frequencia', 'ticket_medio')

        if len(dados_clientes) < n_clusters:
            return {'erro': 'Dados insuficientes para clusterização.'}

        df = pd.DataFrame(list(dados_clientes)).dropna()
        
        # Preparar dados para o modelo
        features = df[['faturamento_total', 'frequencia', 'ticket_medio']]
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        # Treinar modelo K-Means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        df['segmento'] = kmeans.fit_predict(features_scaled)
        
        # Agrupar resultados
        segmentos = {}
        for i in range(n_clusters):
            cluster_data = df[df['segmento'] == i]
            segmentos[f'Segmento {i+1}'] = {
                'total_clientes': len(cluster_data),
                'faturamento_medio': cluster_data['faturamento_total'].mean(),
                'frequencia_media': cluster_data['frequencia'].mean(),
                'clientes': cluster_data.to_dict('records')
            }
            
        return {
            'total_clientes_analisados': len(df),
            'numero_segmentos': n_clusters,
            'segmentos': segmentos
        }

    except Exception as e:
        logger.error(f'Erro ao executar data mining: {e}')
        return {}


def calcular_correlacoes(empresa, data_inicio: date, data_fim: date) -> Dict[str, Any]:
    """
    Calcular a matriz de correlação entre métricas de vendas.
    """
    try:
        dados_vendas = Venda.objects.filter(
            empresa=empresa, data_venda__range=(data_inicio, data_fim), status='finalizada'
        ).annotate(
            num_itens=Sum('itens_venda__quantidade')
        ).values('total', 'desconto', 'num_itens')

        if len(dados_vendas) < 2:
            return {'erro': 'Dados insuficientes para calcular correlações.'}

        df = pd.DataFrame(list(dados_vendas))
        matriz_correlacao = df.corr()
        
        return {
            'matriz_html': matriz_correlacao.to_html(classes='table table-bordered', float_format='{:,.2f}'.format),
            'dados_brutos': matriz_correlacao.to_dict()
        }

    except Exception as e:
        logger.error(f'Erro ao calcular correlações: {e}')
        return {}
    

