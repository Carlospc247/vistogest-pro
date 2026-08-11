# apps/analytics/services.py
import json
from datetime import datetime, timedelta
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from apps.analytics.utils import get_geolocation_data, parse_user_agent_string
from .models import EventoAnalytics, AuditoriaAlteracao, AlertaInteligente

class AnalyticsService:
    """Serviço para coleta e análise de eventos"""
    
    def __init__(self, usuario=None):
        self.usuario = usuario
    
    def track_event(self, categoria, acao, label=None, valor=None, propriedades=None, request=None):
        """Registrar evento de analytics"""
        
        evento_data = {
            'usuario': self.usuario,
            'categoria': categoria,
            'acao': acao,
            'label': label or '',
            'valor': valor,
            'propriedades': propriedades or {}
        }
        
        # Se um objeto 'request' for passado, enriquece o evento com mais dados
        if request:
            ip_address = self.get_client_ip(request)
            
            # 2. CHAMA A FUNÇÃO PARA OBTER OS DADOS DE GEOLOCALIZAÇÃO
            pais, cidade = get_geolocation_data(ip_address)
            
            # (Opcional) Analisa também o user agent
            user_agent_info = parse_user_agent_string(request.META.get('HTTP_USER_AGENT', ''))
            
            evento_data.update({
                'ip_address': ip_address,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'url': request.build_absolute_uri(),
                'referrer': request.META.get('HTTP_REFERER', ''),
                'pais': pais or '',       # 3. GUARDA OS RESULTADOS
                'cidade': cidade or '',   # 4. GUARDA OS RESULTADOS
            })
            
            # Adiciona as informações do user agent às propriedades
            evento_data['propriedades']['user_agent_details'] = user_agent_info
        
        EventoAnalytics.objects.create(**evento_data)

    def track_page_view(self, page_name, request=None):
        """Registrar visualização de página"""
        self.track_event(
            categoria='navegacao',
            acao='page_view',
            label=page_name,
            request=request
        )
    
    def track_sale(self, venda, request=None):
        """Registrar venda"""
        self.track_event(
            categoria='vendas',
            acao='venda_finalizada',
            valor=venda.total,
            propriedades={
                'numero_documento': venda.numero_documento,
                'forma_pagamento': venda.forma_pagamento.nome,
                'itens_count': venda.itens.count(),
                'vendedor_id': venda.vendedor.id if venda.vendedor else None
            },
            request=request
        )
    
    def track_product_search(self, query, results_count=0, request=None):
        """Registrar busca de produto"""
        self.track_event(
            categoria='estoque',
            acao='produto_pesquisado',
            label=query,
            propriedades={
                'results_count': results_count,
                'query_length': len(query)
            },
            request=request
        )
    
    def get_client_ip(self, request):
        """Extrair IP do cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_eventos_dashboard(self, periodo_dias=30):
        """Obter eventos para dashboard"""
        data_inicio = timezone.now() - timedelta(days=periodo_dias)
        
        eventos = EventoAnalytics.objects.filter(
            timestamp__gte=data_inicio
        )
        
        # Agrupar por categoria
        por_categoria = eventos.values('categoria').annotate(
            total=models.Count('id')
        ).order_by('-total')
        
        # Eventos por dia
        por_dia = eventos.extra(
            select={'dia': 'DATE(timestamp)'}
        ).values('dia').annotate(
            total=models.Count('id')
        ).order_by('dia')
        
        # Páginas mais acessadas
        paginas_populares = eventos.filter(
            categoria='navegacao',
            acao='page_view'
        ).values('label').annotate(
            total=models.Count('id')
        ).order_by('-total')[:10]
        
        return {
            'total_eventos': eventos.count(),
            'por_categoria': list(por_categoria),
            'por_dia': list(por_dia),
            'paginas_populares': list(paginas_populares)
        }
    #Exibir todos os logins em lista para a tela do super administrador
    def track_login(self, request):
        """Registra um evento de login bem-sucedido."""
        self.track_event(
            categoria='usuario',
            acao='login_sucesso',
            label=self.usuario.username,
            propriedades={
                'email': self.usuario.email,
                'full_name': self.usuario.get_full_name()
            },
            request=request
        )

class AuditoriaService:
    """Serviço para auditoria de alterações"""
    
    def __init__(self, usuario, request=None):
        self.usuario = usuario
        self.request = request
    
    def log_alteracao(self, instance, tipo_operacao, dados_anteriores=None, campos_alterados=None, motivo=''):
        """Registrar alteração para auditoria"""
        
        
        content_type = ContentType.objects.get_for_model(instance)
        
        dados_atuais = self.serializar_objeto(instance)
        
        auditoria_data = {
            'usuario': self.usuario,
            'content_type': content_type,
            'object_id': instance.pk,
            'tipo_operacao': tipo_operacao,
            'dados_posteriores': dados_atuais,
            'dados_anteriores': dados_anteriores,
            'campos_alterados': campos_alterados or [],
            'motivo': motivo
        }
        
        if self.request:
            auditoria_data.update({
                'ip_address': self.get_client_ip(self.request),
                'user_agent': self.request.META.get('HTTP_USER_AGENT', '')
            })
        
        AuditoriaAlteracao.objects.create(**auditoria_data)
    
    def serializar_objeto(self, instance):
        """Serializar objeto para JSON"""
        dados = {}
        
        for field in instance._meta.fields:
            valor = getattr(instance, field.name)
            
            # Converter tipos não JSON serializáveis
            if isinstance(valor, datetime):
                valor = valor.isoformat()
            elif hasattr(valor, 'pk'):  # ForeignKey
                valor = valor.pk
            elif valor is None:
                valor = None
            else:
                valor = str(valor)
            
            dados[field.name] = valor
        
        return dados
    
    def get_client_ip(self, request):
        """Extrair IP do cliente"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_historico_objeto(self, instance):
        """Obter histórico de alterações de um objeto"""
        content_type = ContentType.objects.get_for_model(instance)
        
        return AuditoriaAlteracao.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).order_by('-timestamp')

class AlertasService:
    """Serviço para alertas inteligentes"""
    
    def __init__(self, empresa):
        self.empresa = empresa
    
    def verificar_alertas(self):
        """Verificar e criar alertas baseado nas condições do sistema"""
        
        alertas_criados = []
        
        # Verificar estoque baixo
        alertas_criados.extend(self.verificar_estoque_baixo())
        
        # Verificar vendas baixas
        alertas_criados.extend(self.verificar_vendas_baixas())
        
        # Verificar produtos vencendo
        alertas_criados.extend(self.verificar_produtos_vencendo())
        
        # Verificar métricas de performance
        alertas_criados.extend(self.verificar_performance())
        
        return alertas_criados
    
    def verificar_estoque_baixo(self):
        """Verificar produtos com estoque baixo"""
        from apps.produtos.models import Produto
        
        produtos_baixo_estoque = Produto.objects.filter(
            estoque_atual__lte=models.F('estoque_minimo'),
            ativo=True
        )
        
        if produtos_baixo_estoque.exists():
            # Verificar se alerta já existe e está ativo
            alerta_existente = AlertaInteligente.objects.filter(
                tipo='estoque_baixo',
                status='ativo'
            ).first()
            
            if not alerta_existente:
                alerta = AlertaInteligente.objects.create(
                    tipo='estoque_baixo',
                    prioridade='alta',
                    titulo='Produtos com Estoque Baixo',
                    mensagem=f'{produtos_baixo_estoque.count()} produtos estão com estoque abaixo do mínimo.',
                    dados_contexto={
                        'produtos_count': produtos_baixo_estoque.count(),
                        'produtos_ids': list(produtos_baixo_estoque.values_list('id', flat=True))
                    },
                    acoes_sugeridas=[
                        'Verificar produtos em estoque',
                        'Fazer pedido de reposição',
                        'Ajustar estoque mínimo'
                    ]
                )
                return [alerta]
        
        return []
    
    def verificar_vendas_baixas(self):
        """Verificar se vendas estão abaixo da média"""
        from apps.vendas.models import Venda
        
        # Últimos 7 dias
        data_inicio = timezone.now() - timedelta(days=7)
        vendas_semana = Venda.objects.filter(
            data_venda__gte=data_inicio
        ).count()
        
        # Média dos últimos 30 dias
        data_30_dias = timezone.now() - timedelta(days=30)
        vendas_30_dias = Venda.objects.filter(
            data_venda__gte=data_30_dias,
            data_venda__lt=data_inicio
        ).count()
        
        media_semanal = vendas_30_dias / 4  # Aproximadamente 4 semanas
        
        if vendas_semana < media_semanal * 0.7:  # 30% abaixo da média
            alerta_existente = AlertaInteligente.objects.filter(
                tipo='vendas_baixas',
                status='ativo',
                created_at__gte=timezone.now() - timedelta(days=7)
            ).first()
            
            if not alerta_existente:
                alerta = AlertaInteligente.objects.create(
                    tipo='vendas_baixas',
                    prioridade='media',
                    titulo='Vendas Abaixo da Média',
                    mensagem=f'Vendas desta semana ({vendas_semana}) estão abaixo da média ({media_semanal:.1f}).',
                    dados_contexto={
                        'vendas_semana': vendas_semana,
                        'media_semanal': media_semanal,
                        'percentual_reducao': ((media_semanal - vendas_semana) / media_semanal) * 100
                    },
                    acoes_sugeridas=[
                        'Analisar causas da redução',
                        'Verificar campanhas promocionais',
                        'Revisar estratégia de vendas'
                    ]
                )
                return [alerta]
        
        return []
    
    def verificar_produtos_vencendo(self):
        """Verificar produtos próximos do vencimento"""
        from apps.produtos.models import Produto
        
        data_limite = timezone.now().date() + timedelta(days=30)
        
        produtos_vencendo = Produto.objects.filter(
            data_validade__lte=data_limite,
            data_validade__gte=timezone.now().date(),
            estoque_atual__gt=0
        )
        
        if produtos_vencendo.exists():
            alerta_existente = AlertaInteligente.objects.filter(
                tipo='estoque_baixo',  # Usar mesmo tipo para não duplicar
                status='ativo',
                titulo__icontains='vencimento'
            ).first()
            
            if not alerta_existente:
                alerta = AlertaInteligente.objects.create(
                    tipo='estoque_baixo',
                    prioridade='alta',
                    titulo='Produtos Próximos do Vencimento',
                    mensagem=f'{produtos_vencendo.count()} produtos vencem nos próximos 30 dias.',
                    dados_contexto={
                        'produtos_count': produtos_vencendo.count(),
                        'produtos_ids': list(produtos_vencendo.values_list('id', flat=True))
                    },
                    acoes_sugeridas=[
                        'Promover produtos próximos do vencimento',
                        'Verificar possibilidade de devolução',
                        'Ajustar política de compras'
                    ]
                )
                return [alerta]
        
        return []
    

class MetricasService:
    """Serviço para coleta de métricas de performance"""
    
    def __init__(self, empresa):
        self.empresa = empresa
    

    def medir_tempo_execucao(self, categoria, nome):
        """Decorator para medir tempo de execução"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                import time
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    tempo_execucao = (time.time() - start_time) * 1000  # em ms
                    
                    self.registrar_metrica(
                        categoria=categoria,
                        nome=nome,
                        valor=tempo_execucao,
                        unidade='ms',
                        tags={'status': 'success'}
                    )
                    
                    return result
                    
                except Exception as e:
                    tempo_execucao = (time.time() - start_time) * 1000
                    
                    self.registrar_metrica(
                        categoria=categoria,
                        nome=nome,
                        valor=tempo_execucao,
                        unidade='ms',
                        tags={'status': 'error', 'error_type': type(e).__name__}
                    )
                    
                    raise e
            
            return wrapper
        return decorator

