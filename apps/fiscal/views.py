import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from apps.core.models import Empresa
from django.http import FileResponse
from django.contrib.admin.views.decorators import staff_member_required

from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import AssinaturaDigital
from django.shortcuts import get_object_or_404
from apps.fiscal.servicos.audit_service import AuditLogService
from apps.fiscal.signals import gerar_backup_fiscal, gerar_relatorio_retencoes, gerar_relatorio_taxas
from apps.fiscal.utility.pdf import gerar_pdf_submissao_agt
from apps.fiscal.utility.pdf_agt_service import PDFAGTService
from apps.fiscal.utils import validar_documentos_fiscais
from .models import SAFTExport, TaxaIVAAGT, AssinaturaDigital, RetencaoFonte
from .services import (
    TaxaIVAService, AssinaturaDigitalService, RetencaoFonteService,
    FiscalDashboardService, FiscalServiceError
)
from .serializers import (
    TaxaIVAAGTSerializer, AssinaturaDigitalSerializer, RetencaoFonteSerializer
)
from apps.core.models import Empresa
from apps.core.permissions import EmpresaPermission
import io
from datetime import datetime
from django.views.generic import TemplateView, ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from django.db.models import Sum, Count
import logging
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
import hashlib
import logging
from decimal import Decimal
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.core.exceptions import ObjectDoesNotExist

from apps.core.permissions import empresa_required, FiscalPermission, ContabilidadePermission
from apps.fiscal.models import TaxaIVAAGT, RetencaoFonte, AssinaturaDigital
from apps.fornecedores.models import Fornecedor
from apps.financeiro.models import ContaPagar
from apps.core.permissions import MultiplePermissions, EmpresaPermission, FiscalPermission
from .models import AssinaturaDigital, TaxaIVAAGT, RetencaoFonte
from apps.core.permissions import MultiplePermissions, EmpresaPermission, FiscalPermission
from .models import RetencaoFonte, TaxaIVAAGT
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import (
    TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView, View
)
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Q
import secrets
import base64
from django.contrib.auth.mixins import AccessMixin
from apps.core.permissions import (
    MultiplePermissions,
    EmpresaPermission,
    FiscalPermission
)

from .models import TaxaIVAAGT, AssinaturaDigital, RetencaoFonte
#from .utils import gerar_chaves_assinatura  # função auxiliar opcional
import logging
import io
import zipfile
from django.http import HttpResponse, FileResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views import View
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.core.permissions import MultiplePermissions, EmpresaPermission, FiscalPermission
from .models import RetencaoFonte, TaxaIVAAGT, AssinaturaDigital
import logging
import platform
import socket
import psutil
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction

from apps.core.permissions import empresa_required
from apps.fiscal.models import TaxaIVAAGT, RetencaoFonte, AssinaturaDigital
from apps.fornecedores.models import Fornecedor
import io
import logging
from django.http import HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from apps.core.permissions import MultiplePermissions, EmpresaPermission, FiscalPermission  # ajusta o import conforme teu projeto
from django.contrib.auth.mixins import AccessMixin
from apps.fiscal.services import SAFTExportService





class PermissaoAcaoMixin(AccessMixin):
    # CRÍTICO: Definir esta variável na View
    acao_requerida = None 

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            # Tenta obter o Funcionario (ligação fundamental)
            funcionario = request.user.funcionario 
        except Exception:
            messages.error(request, "Acesso negado. O seu usuário não está ligado a um registro de funcionário.")
            return self.handle_no_permission()

        if self.acao_requerida:
            # Usa a lógica dinâmica do modelo Funcionario (que já criámos)
            if not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(request, f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.")
                return redirect(reverse_lazy('core:dashboard')) # Redirecionamento para a Home ou Dashboard

        return super().dispatch(request, *args, **kwargs)
 
from functools import wraps
 
def permissao_acao_required(acao_requerida=None):
    """
    Decorator para function-based views que verifica:
    1. Usuário autenticado
    2. Usuário ligado a um registro Funcionario
    3. Permissão de ação específica
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Acesso negado. Usuário não autenticado.")
                return redirect(reverse_lazy('core:login'))  # ou handle customizado

            try:
                funcionario = request.user.funcionario
            except Exception:
                messages.error(
                    request,
                    "Acesso negado. O seu usuário não está ligado a um registro de funcionário."
                )
                return redirect(reverse_lazy('core:dashboard'))

            if acao_requerida:
                if not funcionario.pode_realizar_acao(acao_requerida):
                    messages.error(
                        request,
                        f"Acesso negado. O seu cargo não permite realizar a ação de '{acao_requerida}'."
                    )
                    return redirect(reverse_lazy('core:dashboard'))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator



logger = logging.getLogger(__name__)


# Configuração de logging
logger = logging.getLogger('fiscais.views')




class SAFTExportView(LoginRequiredMixin, PermissaoAcaoMixin, APIView):
    acao_requerida = 'exportar_saft'
    """
    View para exportação completa de dados SAF-T AO
    """
    #permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Gera arquivo SAF-T AO para período especificado"""
        empresa = request.user.empresa
        data_inicio_str = request.data.get('data_inicio')
        data_fim_str = request.data.get('data_fim')
        
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            
            logger.info(
                f"Iniciando exportação SAF-T via API",
                extra={
                    'user_id': request.user.id,
                    'empresa_id': empresa.id,
                    'data_inicio': data_inicio.isoformat(),
                    'data_fim': data_fim.isoformat()
                }
            )
            
            xml_saft = SAFTExportService.gerar_saft_ao(empresa, data_inicio, data_fim)
            
            # Preparar resposta HTTP
            response = HttpResponse(xml_saft, content_type='application/xml')
            response['Content-Disposition'] = f'attachment; filename="SAFT_AO_{empresa.nif}_{data_inicio}_{data_fim}.xml"'
            
            logger.info(
                f"SAF-T exportado com sucesso",
                extra={
                    'empresa_id': empresa.id,
                    'tamanho_arquivo': len(xml_saft)
                }
            )
            
            return response
            
        except ValueError as e:
            logger.warning(f"Datas inválidas para exportação SAF-T: {e}")
            return Response(
                {'error': 'Formato de data inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except FiscalServiceError as e:
            logger.error(f"Erro na exportação SAF-T: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FiscalDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, APIView):
    acao_requerida = 'acessar_dashboard_fiscal'
    """
    View para dashboard fiscal com métricas principais
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Retorna métricas fiscais para dashboard"""
        empresa = request.user.empresa
        
        # Período padrão: mês atual
        hoje = date.today()
        data_inicio = date(hoje.year, hoje.month, 1)
        data_fim = hoje
        
        # Permitir customização do período
        if request.query_params.get('data_inicio'):
            data_inicio = datetime.strptime(
                request.query_params['data_inicio'], '%Y-%m-%d'
            ).date()
        
        if request.query_params.get('data_fim'):
            data_fim = datetime.strptime(
                request.query_params['data_fim'], '%Y-%m-%d'
            ).date()
        
        try:
            metricas = FiscalDashboardService.obter_metricas_fiscais(
                empresa, (data_inicio, data_fim)
            )
            
            logger.debug(
                f"Métricas fiscais solicitadas via API",
                extra={
                    'user_id': request.user.id,
                    'empresa_id': empresa.id,
                    'periodo': f"{data_inicio} - {data_fim}"
                }
            )
            
            return Response({
                'periodo': {
                    'data_inicio': data_inicio.isoformat(),
                    'data_fim': data_fim.isoformat()
                },
                'metricas': metricas,
                'empresa': {
                    'id': empresa.id,
                    'nome': empresa.nome,
                    'nif': empresa.nif
                },
                'gerado_em': timezone.now().isoformat()
            })
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao obter métricas fiscais: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =====================================
# ViewSets para API REST
# =====================================

class TaxaIVAAGTViewSet(viewsets.ModelViewSet):
    
    """
    ViewSet para gestão de Taxas de IVA com funcionalidades SAF-T
    """
    serializer_class = TaxaIVAAGTSerializer
    permission_classes = [permissions.IsAuthenticated, EmpresaPermission]
    filterset_fields = ['tax_type', 'tax_code', 'ativo']
    search_fields = ['nome', 'tax_code']
    ordering_fields = ['tax_percentage', 'created_at']
    ordering = ['-tax_percentage']
    
    def get_queryset(self):
        empresa_id = self.request.user.empresa.id
        return TaxaIVAAGT.objects.filter(empresa_id=empresa_id)
    
    def perform_create(self, serializer):
        """Criação com logging e validações SAF-T"""
        empresa = self.request.user.empresa
        
        try:
            taxa = TaxaIVAService.criar_taxa_iva(
                empresa=empresa,
                dados=serializer.validated_data
            )
            
            logger.info(
                f"Taxa IVA criada via API",
                extra={
                    'user_id': self.request.user.id,
                    'empresa_id': empresa.id,
                    'taxa_id': taxa.id,
                    'tax_type': taxa.tax_type
                }
            )
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao criar taxa via API: {e}")
            raise
    
    @action(detail=False, methods=['get'])
    def ativas(self, request):
        """Endpoint para obter apenas taxas ativas"""
        empresa = request.user.empresa
        taxas = TaxaIVAService.obter_taxas_ativas(empresa)
        serializer = self.get_serializer(taxas, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def calcular_iva(self, request, pk=None):
        """Endpoint para calcular IVA baseado em valor base"""
        taxa = self.get_object()
        
        try:
            valor_base = Decimal(request.data.get('valor_base', '0.00'))
            calculo = TaxaIVAService.calcular_iva(valor_base, taxa)
            
            logger.debug(
                f"IVA calculado via API",
                extra={
                    'taxa_id': taxa.id,
                    'valor_base': float(valor_base),
                    'valor_iva': float(calculo['valor_iva'])
                }
            )
            
            return Response(calculo)
            
        except (ValueError, TypeError) as e:
            logger.warning(f"Valor base inválido para cálculo IVA: {e}")
            return Response(
                {'error': 'Valor base inválido'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def export_saft(self, request):
        """Exporta tabela de impostos no formato SAF-T"""
        empresa = request.user.empresa
        taxas = self.get_queryset()
        
        # Converter para formato SAF-T
        saft_data = []
        for taxa in taxas:
            saft_entry = {
                'TaxType': taxa.tax_type,
                'TaxCode': taxa.tax_code,
                'Description': taxa.nome,
                'TaxCountryRegion': 'AO'
            }
            
            if taxa.tax_type == 'IVA':
                saft_entry['TaxPercentage'] = float(taxa.tax_percentage)
            else:
                saft_entry['TaxExemptionCode'] = taxa.exemption_reason
            
            saft_data.append(saft_entry)
        
        return Response({
            'TaxTable': saft_data,
            'GeneratedAt': timezone.now().isoformat(),
            'Company': empresa.nome
        })




class AssinaturaDigitalViewSet(viewsets.ModelViewSet):
    
    """
    ViewSet para gestão de Assinatura Digital
    """
    serializer_class = AssinaturaDigitalSerializer
    permission_classes = [permissions.IsAuthenticated, EmpresaPermission]
    
    def get_queryset(self):
        empresa_id = self.request.user.empresa.id
        return AssinaturaDigital.objects.filter(empresa_id=empresa_id)
    
    @action(detail=False, methods=['post'])
    def gerar_chaves(self, request):
        """Gera novas chaves RSA para a empresa"""
        empresa = request.user.empresa
        tamanho_chave = int(request.data.get('tamanho_chave', 2048))
        
        try:
            assinatura = AssinaturaDigitalService.gerar_chaves_rsa(empresa, tamanho_chave)
            
            logger.info(
                f"Chaves RSA geradas via API",
                extra={
                    'user_id': request.user.id,
                    'empresa_id': empresa.id,
                    'tamanho_chave': tamanho_chave
                }
            )
            
            return Response({
                'message': 'Chaves geradas com sucesso',
                'chave_publica': assinatura.chave_publica,
                'data_geracao': assinatura.data_geracao
            })
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao gerar chaves via API: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def assinar_documento(self, request):
        """Assina um documento digitalmente"""
        empresa = request.user.empresa
        dados_documento = request.data.get('documento', {})
        
        try:
            resultado = AssinaturaDigitalService.assinar_documento(empresa, dados_documento)
            
            logger.info(
                f"Documento assinado via API",
                extra={
                    'user_id': request.user.id,
                    'empresa_id': empresa.id,
                    'tipo_documento': dados_documento.get('tipo_documento'),
                    'numero': dados_documento.get('numero')
                }
            )
            
            return Response(resultado)
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao assinar documento via API: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def status_cadeia(self, request):
        """Retorna status da cadeia de integridade"""
        empresa = request.user.empresa
        
        try:
            assinatura = AssinaturaDigital.objects.get(empresa=empresa)
            
            return Response({
                'configurada': True,
                'ultimo_hash': assinatura.ultimo_hash,
                'series_fiscais': assinatura.dados_series_fiscais,
                'data_geracao': assinatura.data_geracao
            })
            
        except AssinaturaDigital.DoesNotExist:
            return Response({
                'configurada': False,
                'message': 'Assinatura digital não configurada'
            })

class RetencaoFonteViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestão de Retenções na Fonte
    """
    serializer_class = RetencaoFonteSerializer
    permission_classes = [permissions.IsAuthenticated, EmpresaPermission]
    filterset_fields = ['tipo_retencao', 'paga_ao_estado', 'data_retencao']
    search_fields = ['referencia_documento', 'fornecedor__razao_social']
    ordering_fields = ['data_retencao', 'valor_retido']
    ordering = ['-data_retencao']
    
    def get_queryset(self):
        empresa_id = self.request.user.empresa.id
        return RetencaoFonte.objects.filter(empresa_id=empresa_id).select_related('fornecedor')
    
    def perform_create(self, serializer):
        """Criação com geração automática de lançamentos contábeis"""
        empresa = self.request.user.empresa
        dados = serializer.validated_data
        dados['empresa'] = empresa
        
        try:
            retencao = RetencaoFonteService.criar_retencao(dados)
            
            logger.info(
                f"Retenção criada via API",
                extra={
                    'user_id': self.request.user.id,
                    'empresa_id': empresa.id,
                    'retencao_id': retencao.id,
                    'tipo_retencao': retencao.tipo_retencao,
                    'valor_retido': float(retencao.valor_retido)
                }
            )
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao criar retenção via API: {e}")
            raise
    
    @action(detail=True, methods=['post'])
    def marcar_paga(self, request, pk=None):
        """Marca retenção como paga ao Estado"""
        retencao = self.get_object()
        data_pagamento = request.data.get('data_pagamento')
        
        if not data_pagamento:
            data_pagamento = date.today()
        else:
            data_pagamento = datetime.strptime(data_pagamento, '%Y-%m-%d').date()
        
        try:
            retencao_atualizada = RetencaoFonteService.processar_pagamento_estado(
                retencao.id, data_pagamento
            )
            
            logger.info(
                f"Retenção marcada como paga via API",
                extra={
                    'user_id': request.user.id,
                    'retencao_id': retencao.id,
                    'data_pagamento': data_pagamento.isoformat()
                }
            )
            
            serializer = self.get_serializer(retencao_atualizada)
            return Response(serializer.data)
            
        except FiscalServiceError as e:
            logger.error(f"Erro ao marcar retenção como paga: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def relatorio_mensal(self, request):
        """Relatório mensal de retenções"""
        ano = int(request.query_params.get('ano', date.today().year))
        mes = int(request.query_params.get('mes', date.today().month))
        
        retencoes = self.get_queryset().filter(
            data_retencao__year=ano,
            data_retencao__month=mes
        )
        
        # Agrupar por tipo de retenção
        relatorio = {}
        for retencao in retencoes:
            tipo = retencao.tipo_retencao
            if tipo not in relatorio:
                relatorio[tipo] = {
                    'total_valor': Decimal('0.00'),
                    'total_count': 0,
                    'pagas_count': 0,
                    'pendentes_count': 0
                }
            
            relatorio[tipo]['total_valor'] += retencao.valor_retido
            relatorio[tipo]['total_count'] += 1
            
            if retencao.paga_ao_estado:
                relatorio[tipo]['pagas_count'] += 1
            else:
                relatorio[tipo]['pendentes_count'] += 1
        
        # Converter Decimal para float para JSON
        for tipo_data in relatorio.values():
            tipo_data['total_valor'] = float(tipo_data['total_valor'])
        
        return Response({
            'periodo': f"{mes:02d}/{ano}",
            'relatorio': relatorio,
            'gerado_em': timezone.now().isoformat()
        })



@method_decorator([login_required, csrf_exempt], name='dispatch')
class ValidarDocumentoView(View, PermissaoAcaoMixin):
    acao_requerida = 'validar_documentos_fiscais'
    """
    View para validação de documentos fiscais
    """
    
    def post(self, request):
        """Valida documento fiscal e retorna conformidade SAF-T"""
        empresa = request.user.empresa
        
        try:
            dados_documento = json.loads(request.body)
            
            # Validações básicas SAF-T
            erros = []
            avisos = []
            
            # Validar campos obrigatórios
            campos_obrigatorios = ['tipo_documento', 'numero', 'data', 'valor_total']
            for campo in campos_obrigatorios:
                if not dados_documento.get(campo):
                    erros.append(f"Campo obrigatório ausente: {campo}")
            
            # Validar formato de data
            try:
                data_doc = datetime.strptime(dados_documento.get('data', ''), '%Y-%m-%d')
            except ValueError:
                erros.append("Formato de data inválido")
            
            # Validar valor total
            try:
                valor_total = Decimal(str(dados_documento.get('valor_total', '0')))
                if valor_total <= 0:
                    erros.append("Valor total deve ser maior que zero")
            except (ValueError, TypeError):
                erros.append("Valor total inválido")
            
            # Verificar se série fiscal existe
            serie = dados_documento.get('serie', 'DEFAULT')
            assinatura = AssinaturaDigital.objects.filter(empresa=empresa).first()
            
            if not assinatura:
                avisos.append("Assinatura digital não configurada")
            
            resultado = {
                'valido': len(erros) == 0,
                'erros': erros,
                'avisos': avisos,
                'conformidade_saft': len(erros) == 0 and len(avisos) == 0,
                'validado_em': timezone.now().isoformat()
            }
            
            logger.info(
                f"Documento validado",
                extra={
                    'user_id': request.user.id,
                    'empresa_id': empresa.id,
                    'valido': resultado['valido'],
                    'total_erros': len(erros)
                }
            )
            
            return JsonResponse(resultado)
            
        except json.JSONDecodeError:
            logger.warning("JSON inválido na validação de documento")
            return JsonResponse(
                {'error': 'JSON inválido'},
                status=400
            )
        except Exception as e:
            logger.error(f"Erro na validação de documento: {e}")
            return JsonResponse(
                {'error': 'Erro interno na validação'},
                status=500
            )

@require_http_methods(["GET"])
@login_required
@permissao_acao_required(acao_requerida='verificar_integridade_hash')
def verificar_integridade_hash(request):
    """
    Verifica a integridade da cadeia de hash dos documentos
    """
    empresa = request.user.empresa
    
    try:
        assinatura = AssinaturaDigital.objects.get(empresa=empresa)
        
        # Verificar cada série fiscal
        resultados = {}
        
        for serie, dados in assinatura.dados_series_fiscais.items():
            ultimo_hash = dados.get('ultimo_hash')
            ultimo_documento = dados.get('ultimo_documento')
            
            resultados[serie] = {
                'ultimo_hash': ultimo_hash,
                'ultimo_documento': ultimo_documento,
                'hash_valido': bool(ultimo_hash),
                'data_ultima_assinatura': dados.get('data_ultima_assinatura')
            }
        
        logger.info(
            f"Integridade de hash verificada",
            extra={
                'user_id': request.user.id,
                'empresa_id': empresa.id,
                'series_verificadas': len(resultados)
            }
        )
        
        return JsonResponse({
            'empresa': empresa.nome,
            'series_fiscais': resultados,
            'integridade_geral': all(s['hash_valido'] for s in resultados.values()),
            'verificado_em': timezone.now().isoformat()
        })
        
    except AssinaturaDigital.DoesNotExist:
        return JsonResponse({
            'error': 'Assinatura digital não configurada',
            'configurada': False
        }, status=404)
    except Exception as e:
        logger.error(f"Erro na verificação de integridade: {e}")
        return JsonResponse({
            'error': 'Erro interno na verificação'
        }, status=500)


# apps/fiscal/views.py
from django.urls import reverse_lazy
from django.contrib import messages
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.permissions import IsAuthenticated
from apps.core.permissions import (
    MultiplePermissions,
    EmpresaPermission,
    FiscalPermission
)
from .models import TaxaIVAAGT
from django.db.models import Q


# ===============================
# DASHBOARD FISCAL
# ===============================
class FiscalDashboardTemplateView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_painel_principal_fiscal'
    """
    Painel principal da área fiscal — apresenta resumo de taxas, retenções e status SAF-T.
    """
    template_name = "fiscal/dashboard.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["total_taxas_ativas"] = TaxaIVAAGT.objects.filter(empresa=empresa, ativo=True).count()
        context["total_isencoes"] = TaxaIVAAGT.objects.filter(empresa=empresa, tax_type="IS").count()
        context["total_nao_sujeitas"] = TaxaIVAAGT.objects.filter(empresa=empresa, tax_type="NS").count()
        return context


# ===============================
# LISTAGEM DE TAXAS DE IVA
# ===============================
class TaxaIVAListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'ver_taxas_iva'
    """
    Lista todas as Taxas de IVA (AGT) registradas pela empresa.
    """
    model = TaxaIVAAGT
    template_name = "fiscal/taxaiva_list.html"
    context_object_name = "taxas_iva"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_queryset(self):
        empresa = self.request.user.empresa
        search = self.request.GET.get("q", "")
        queryset = TaxaIVAAGT.objects.filter(empresa=empresa)
        if search:
            queryset = queryset.filter(Q(nome__icontains=search) | Q(tax_code__icontains=search))
        return queryset.order_by("-tax_percentage")


# ===============================
# DETALHE
# ===============================
class TaxaIVADetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'ver_taxas_iva'
    """
    Exibe detalhes de uma taxa de IVA específica.
    """
    model = TaxaIVAAGT
    template_name = "fiscal/taxaiva_detail.html"
    context_object_name = "taxa"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não tem acesso a esta taxa de outra empresa.")
        return obj


# ===============================
# CRIAÇÃO
# ===============================
class TaxaIVACreateView(LoginRequiredMixin, PermissaoAcaoMixin, CreateView):
    acao_requerida = 'criar_taxas_iva'
    """
    Criação de nova taxa de IVA.
    """
    model = TaxaIVAAGT
    fields = [
        "nome", "tax_type", "tax_code", "tax_percentage",
        "exemption_reason", "legislacao_referencia", "ativo"
    ]
    template_name = "fiscal/taxaiva_form.html"
    success_url = reverse_lazy("fiscal:taxas-iva-list")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def form_valid(self, form):
        form.instance.empresa = self.request.user.empresa
        messages.success(self.request, "Taxa de IVA criada com sucesso.")
        return super().form_valid(form)


# ===============================
# EDIÇÃO
# ===============================
class TaxaIVAUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'criar_taxas_iva'
    """
    Edição de taxa de IVA existente.
    """
    model = TaxaIVAAGT
    fields = [
        "nome", "tax_type", "tax_code", "tax_percentage",
        "exemption_reason", "legislacao_referencia", "ativo"
    ]
    template_name = "fiscal/taxaiva_form.html"
    success_url = reverse_lazy("fiscal:taxas-iva-list")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não pode editar taxas de outra empresa.")
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Taxa de IVA atualizada com sucesso.")
        return super().form_valid(form)


# ===============================
# EXCLUSÃO
# ===============================
class TaxaIVADeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'apagar_taxas_iva'
    """
    Exclusão lógica ou física de uma taxa.
    """
    model = TaxaIVAAGT
    template_name = "fiscal/taxaiva_confirm_delete.html"
    success_url = reverse_lazy("fiscal:taxas-iva-list")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não pode excluir taxas de outra empresa.")
        return obj

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Taxa de IVA excluída com sucesso.")
        return super().delete(request, *args, **kwargs)



# ============================================================
# === GESTÃO DE ASSINATURA DIGITAL ===
# ============================================================

class AssinaturaDigitalView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'ver_status_atual_assinatura_digital'
    """
    Exibe o status atual da assinatura digital da empresa.
    """
    template_name = "fiscal/assinatura_digital.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        assinatura = AssinaturaDigital.objects.filter(empresa=empresa).first()
        context["empresa"] = empresa
        context["assinatura"] = assinatura
        return context


class AssinaturaConfigurarView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'configurar_assinatura_digital'
    """
    Permite ao usuário configurar ou atualizar informações da assinatura digital.
    """
    model = AssinaturaDigital
    fields = ["certificado_digital", "senha_certificado", "validade_certificado"]
    template_name = "fiscal/assinatura_configurar.html"
    success_url = reverse_lazy("fiscal:assinatura-digital")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        empresa = self.request.user.empresa
        obj, _ = AssinaturaDigital.objects.get_or_create(empresa=empresa)
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Assinatura digital configurada com sucesso.")
        return super().form_valid(form)


class AssinaturaGerarChavesView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'gerar_par_chave_publica_ou_privada'
    """
    Gera par de chaves pública/privada para assinatura digital e salva no modelo.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        assinatura, _ = AssinaturaDigital.objects.get_or_create(empresa=empresa)

        # gera par de chaves (substitua por RSA real em produção)
        private_key = base64.b64encode(secrets.token_bytes(32)).decode()
        public_key = base64.b64encode(secrets.token_bytes(32)).decode()

        assinatura.chave_privada = private_key
        assinatura.chave_publica = public_key
        assinatura.data_geracao = timezone.now()
        assinatura.save()

        messages.success(request, "Par de chaves gerado com sucesso.")
        return redirect("fiscal:assinatura-digital")
    

# ============================================================
# === GESTÃO DE RETENÇÕES NA FONTE ===
# ============================================================

class RetencaoFonteListView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'gerir_retencoes_na_fonte'
    """
    Lista de retenções na fonte da empresa.
    """
    model = RetencaoFonte
    template_name = "fiscal/retencao_list.html"
    context_object_name = "retencoes"

    def get_queryset(self):
        empresa = self.request.user.empresa
        search = self.request.GET.get("q", "")
        queryset = RetencaoFonte.objects.filter(empresa=empresa)
        if search:
            queryset = queryset.filter(
                Q(fornecedor__nome__icontains=search) |
                Q(documento_referencia__icontains=search)
            )
        return queryset.order_by("-data_retencao")


class RetencaoFonteDetailView(LoginRequiredMixin, PermissaoAcaoMixin, DetailView):
    acao_requerida = 'gerir_retencoes_na_fonte'
    """
    Exibe detalhes de uma retenção na fonte específica.
    """
    model = RetencaoFonte
    template_name = "fiscal/retencao_detail.html"
    context_object_name = "retencao"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Acesso negado: retenção pertence a outra empresa.")
        return obj


from django.urls import reverse_lazy
from django.contrib import messages
from django.views.generic import CreateView
from .models import RetencaoFonte
from .forms import RetencaoFonteForm

class RetencaoFonteCreateView(PermissaoAcaoMixin, CreateView):
    acao_requerida = 'criar_retencoes_na_fonte'
    model = RetencaoFonte
    form_class = RetencaoFonteForm
    template_name = "fiscal/retencao_form.html"
    success_url = reverse_lazy("fiscal:retencoes-list")

    def form_valid(self, form):
        # Define empresa automaticamente
        form.instance.empresa = self.request.user.empresa
        messages.success(self.request, "Retenção criada com sucesso.")
        return super().form_valid(form)



class RetencaoFonteUpdateView(LoginRequiredMixin, PermissaoAcaoMixin, UpdateView):
    acao_requerida = 'criar_retencoes_na_fonte'
    """
    Edição de uma retenção existente.
    """
    model = RetencaoFonte
    fields = ["fornecedor", "documento_referencia", "valor_bruto", "percentual", "descricao"]
    template_name = "fiscal/retencao_form.html"
    success_url = reverse_lazy("fiscal:retencoes-list")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não pode editar retenções de outra empresa.")
        return obj

    def form_valid(self, form):
        form.instance.valor_retido = (form.instance.valor_bruto * form.instance.percentual) / 100
        messages.success(self.request, "Retenção atualizada com sucesso.")
        return super().form_valid(form)


class RetencaoFonteDeleteView(LoginRequiredMixin, PermissaoAcaoMixin, DeleteView):
    acao_requerida = 'apagar_retencoes_na_fonte'
    """
    Exclusão de retenção.
    """
    model = RetencaoFonte
    template_name = "fiscal/retencao_confirm_delete.html"
    success_url = reverse_lazy("fiscal:retencoes-list")
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.empresa != self.request.user.empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Você não pode excluir retenções de outra empresa.")
        return obj

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Retenção excluída com sucesso.")
        return super().delete(request, *args, **kwargs)


class RetencaoMarcarPagaView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'marcar_retencoes_como_pago'
    """
    Marca uma retenção como paga.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission]
    }

    def post(self, request, *args, **kwargs):
        empresa = request.user.empresa
        retencao = get_object_or_404(RetencaoFonte, pk=kwargs["pk"], empresa=empresa)
        retencao.status = "paga"
        retencao.data_pagamento = timezone.now()
        retencao.save()
        messages.success(request, "Retenção marcada como paga com sucesso.")
        return redirect("fiscal:retencoes-list")





# ============================================================
# === RELATÓRIOS FISCAIS ===
# ============================================================

class RelatoriosView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'ver_relatorio_fiscal'
    """
    Dashboard geral dos relatórios fiscais disponíveis.
    """
    template_name = "fiscal/relatorios_dashboard.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["total_retencoes"] = RetencaoFonte.objects.filter(empresa=empresa).count()
        context["total_taxas_iva"] = TaxaIVAAGT.objects.filter(empresa=empresa, ativo=True).count()
        context["ultimo_relatorio"] = timezone.now().strftime("%d/%m/%Y %H:%M")
        return context


class RelatorioRetencoesView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'ver_relatorio_retencoes'
    
    """
    Relatório de Retenções na Fonte (IRT, IRPC, etc).
    """
    model = RetencaoFonte
    template_name = "fiscal/relatorio_retencoes.html"
    context_object_name = "retencoes"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_queryset(self):
        empresa = self.request.user.empresa
        queryset = RetencaoFonte.objects.filter(empresa=empresa)
        mes = self.request.GET.get("mes")
        ano = self.request.GET.get("ano")
        if mes and ano:
            queryset = queryset.filter(data_retencao__month=mes, data_retencao__year=ano)
        return queryset.order_by("-data_retencao")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        queryset = self.get_queryset()
        context["empresa"] = empresa
        context["total_retido"] = queryset.aggregate(total=Sum("valor_retido"))["total"] or 0
        context["retencoes_pagas"] = queryset.filter(paga_ao_estado=True).count()
        context["retencoes_pendentes"] = queryset.filter(paga_ao_estado=False).count()
        return context


class RelatorioTaxasIVAView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'ver_relatorio_taxas_iva'

    """
    Relatório de Taxas de IVA em vigor e histórico.
    """
    model = TaxaIVAAGT
    template_name = "fiscal/relatorio_taxas_iva.html"
    context_object_name = "taxas"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_queryset(self):
        empresa = self.request.user.empresa
        ativos = self.request.GET.get("ativos", "true")
        queryset = TaxaIVAAGT.objects.filter(empresa=empresa)
        if ativos == "true":
            queryset = queryset.filter(ativo=True)
        return queryset.order_by("-tax_percentage")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["total_taxas"] = self.get_queryset().count()
        context["media_percentual"] = (
            self.get_queryset().aggregate(media=Sum("tax_percentage"))["media"] or 0
        )
        return context


# ============================================================
# === EXPORTAÇÕES SAF-T AGT ===
# ============================================================

class SAFTView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    acao_requerida = 'acessar_dashboard_saft'
    """
    Painel principal de exportação SAF-T (AGT Angola).
    """
    template_name = "fiscal/saft_dashboard.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["historico_count"] = empresa.saft_geracoes.count() if hasattr(empresa, "saft_geracoes") else 0
        context["ultimo_export"] = (
            empresa.saft_geracoes.order_by("-data_criacao").first()
            if hasattr(empresa, "saft_geracoes") else None
        )
        return context


from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from datetime import datetime
import json, traceback
from apps.fiscal.services import SAFTExportService


class SAFTExportWebView(PermissaoAcaoMixin, View):
    acao_requerida = 'exportar_saft'

    def post(self, request, *args, **kwargs):
        print("===== DEBUG SAF-T =====")

        try:
            empresa = request.user.empresa
            data = json.loads(request.body)

            data_inicio_str = data.get('dataInicio')
            data_fim_str = data.get('dataFim')

            # Converter para objetos date
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else None
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else None

            incluir_stock = data.get('incluirMovimentosStock', True)
            incluir_clientes = data.get('incluirDadosClientes', True)

            print("Empresa:", empresa)
            print("Período:", data_inicio, "->", data_fim)
            print("Incluir stock:", incluir_stock, "| Incluir clientes:", incluir_clientes)

            # Gera o XML SAF-T
            xml_saft = SAFTExportService.gerar_saft_ao(empresa, data_inicio, data_fim)

            # Cria nome do ficheiro
            nome_ficheiro = f"SAFT_{empresa.nif}_{timezone.now().strftime('%Y%m%d')}.xml"

            # Retorna o ficheiro XML como anexo (download)
            response = HttpResponse(xml_saft, content_type="application/xml")
            response['Content-Disposition'] = f'attachment; filename="{nome_ficheiro}"'
            return response

        except Exception as e:
            print("===== ERRO NO PROCESSO SAF-T =====")
            traceback.print_exc()
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class SAFTHistoricoView(LoginRequiredMixin, PermissaoAcaoMixin, ListView):
    acao_requerida = 'ver_historico_saft'
    """
    Exibe histórico de ficheiros SAF-T gerados.
    """
    template_name = "fiscal/saft_historico.html"
    context_object_name = "historicos"

    def get_queryset(self):
        empresa = self.request.user.empresa
        if hasattr(empresa, "saft_geracoes"):
            return empresa.saft_geracoes.all().order_by("-data_criacao")
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa

        # Obter o funcionario (já está garantido pelo PermissaoAcaoMixin)
        funcionario = self.request.user.funcionario
        context["funcionario"] = funcionario

        return context






logger = logging.getLogger(__name__)

# ============================================================
# === VALIDAÇÕES FISCAIS ===
# ============================================================

class ValidacoesView(LoginRequiredMixin, TemplateView):
    acao_requerida = 'validar_documentos_fiscais'
    """
    Painel de Validações Fiscais - visão geral.
    """
    template_name = "fiscal/validacoes_dashboard.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["ultima_validacao"] = timezone.now().strftime("%d/%m/%Y %H:%M")
        context["assinatura"] = getattr(empresa, "assinatura_fiscal", None)
        context["total_retencoes"] = RetencaoFonte.objects.filter(empresa=empresa).count()
        context["total_taxas"] = TaxaIVAAGT.objects.filter(empresa=empresa, ativo=True).count()
        return context


class ValidarDocumentosView(LoginRequiredMixin, View):
    acao_requerida = 'validar_documentos_fiscais'
    """
    Executa validações em documentos fiscais emitidos (faturas, notas de crédito, etc.).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        try:
            resultado = validar_documentos_fiscais(empresa)
            messages.success(request, f"Validação concluída com {resultado['erros']} erros e {resultado['avisos']} avisos.")
            logger.info(f"Validação fiscal executada para {empresa.nome} ({empresa.id})")
            return JsonResponse(resultado)
        except Exception as e:
            logger.exception(f"Erro ao validar documentos fiscais: {e}")
            messages.error(request, f"Erro ao validar documentos: {e}")
            return JsonResponse({'status': 'erro', 'detalhe': str(e)}, status=500)


class VerificarIntegridadeView(LoginRequiredMixin, View):
    acao_requerida = 'verificar_integridade_cadeia_hash_fiscal'
    """
    Verifica integridade da cadeia de hash fiscal (assinaturas digitais e hash em cadeia).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        try:
            resultado = verificar_integridade_hash(empresa)
            if resultado["ok"]:
                messages.success(request, "Integridade fiscal confirmada — sem alterações detectadas.")
            else:
                messages.warning(request, f"Atenção: {resultado['mensagem']}")
            return JsonResponse(resultado)
        except Exception as e:
            logger.exception(f"Erro ao verificar integridade fiscal: {e}")
            messages.error(request, f"Erro na verificação: {e}")
            return JsonResponse({'status': 'erro', 'detalhe': str(e)}, status=500)


# ============================================================
# === CONFIGURAÇÕES FISCAIS ===
# ============================================================

class ConfiguracoesFiscaisView(LoginRequiredMixin, TemplateView):
    acao_requerida = 'acessar_configuracao_fiscal'
    """
    Painel central de configurações fiscais da empresa.
    """
    template_name = "fiscal/configuracoes_dashboard.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["assinatura_digital"] = getattr(empresa, "assinatura_fiscal", None)
        context["total_taxas"] = TaxaIVAAGT.objects.filter(empresa=empresa).count()
        context["ultima_actualizacao"] = timezone.now().strftime("%d/%m/%Y %H:%M")
        return context


class ConfiguracaoEmpresaView(LoginRequiredMixin, TemplateView):
    acao_requerida = 'acessar_configuracao_fiscal'
    """
    Exibe e permite ajustar parâmetros fiscais específicos da empresa (NIF, Série, Assinatura, etc.).
    """
    template_name = "fiscal/configuracao_empresa.html"
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def post(self, request, *args, **kwargs):
        empresa = request.user.empresa
        try:
            empresa.nif = request.POST.get("nif", empresa.nif)
            empresa.save()
            messages.success(request, "Configurações fiscais da empresa atualizadas com sucesso.")
        except Exception as e:
            logger.exception(f"Erro ao atualizar configuração fiscal da empresa {empresa.id}: {e}")
            messages.error(request, f"Erro ao salvar configuração: {e}")
        return redirect("fiscal:configuracao-empresa")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.request.user.empresa
        context["empresa"] = empresa
        context["assinatura"] = getattr(empresa, "assinatura_fiscal", None)
        return context


class BackupFiscalView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_saft_backup_fiscal'
    """
    Gera um backup completo dos dados fiscais (Taxas, Retenções, Assinaturas, Configurações).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        try:
            ficheiro, nome_ficheiro = gerar_backup_fiscal(empresa)
            response = HttpResponse(ficheiro, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{nome_ficheiro}"'
            messages.success(request, "Backup fiscal gerado com sucesso.")
            logger.info(f"Backup fiscal criado para empresa {empresa.nome} ({empresa.id})")
            return response
        except Exception as e:
            logger.exception(f"Erro ao gerar backup fiscal: {e}")
            messages.error(request, f"Erro ao gerar backup: {e}")
            return redirect("fiscal:configuracoes")







logger = logging.getLogger('fiscal.ajax')


# -------------------------
# 🔹 AJAX: Calcular IVA
# -------------------------
@login_required
#@empresa_required
@require_POST
def ajax_calcular_iva(request):
    """Calcula o valor do IVA com base na taxa ativa e no valor informado."""
    try:
        data = request.POST
        valor_base = Decimal(data.get('valor_base', '0'))
        taxa_id = data.get('taxa_id')

        taxa = TaxaIVAAGT.objects.get(id=taxa_id, empresa=request.user.empresa, ativo=True)
        valor_iva = valor_base * (taxa.tax_percentage / Decimal('100'))

        return JsonResponse({
            "success": True,
            "message": "Cálculo de IVA realizado com sucesso.",
            "data": {
                "valor_base": str(valor_base),
                "taxa": str(taxa.tax_percentage),
                "valor_iva": str(round(valor_iva, 2))
            }
        }, status=200)
    except ObjectDoesNotExist:
        return JsonResponse({"success": False, "message": "Taxa de IVA não encontrada."}, status=404)
    except Exception as e:
        logger.exception("Erro ao calcular IVA.")
        return JsonResponse({"success": False, "message": "Erro interno ao calcular IVA.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Buscar Fornecedores
# -------------------------
@login_required
#@empresa_required
@require_GET
def ajax_buscar_fornecedores(request):
    """Busca fornecedores pelo nome ou NIF para autocomplete."""
    try:
        termo = request.GET.get('q', '').strip()
        fornecedores = Fornecedor.objects.filter(
            empresa=request.user.empresa,
            nome__icontains=termo
        ).values('id', 'nome', 'nif')[:20]

        return JsonResponse({"success": True, "results": list(fornecedores)}, status=200)
    except Exception as e:
        logger.exception("Erro ao buscar fornecedores.")
        return JsonResponse({"success": False, "message": "Erro ao buscar fornecedores.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Validar NIF
# -------------------------
@login_required
#@empresa_required
@require_POST
def ajax_validar_nif(request):
    """Valida formato e duplicidade de NIF."""
    try:
        nif = request.POST.get('nif', '').strip()

        if not nif or len(nif) < 9:
            return JsonResponse({"success": False, "message": "NIF inválido."}, status=400)

        existe = Fornecedor.objects.filter(nif=nif, empresa=request.user.empresa).exists()
        return JsonResponse({
            "success": True,
            "valid": not existe,
            "message": "NIF válido e disponível." if not existe else "NIF já cadastrado."
        })
    except Exception as e:
        logger.exception("Erro ao validar NIF.")
        return JsonResponse({"success": False, "message": "Erro ao validar NIF.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Gerar Hash
# -------------------------
@login_required
#@empresa_required
@require_POST
def ajax_gerar_hash(request):
    """Gera hash SHA256 a partir de dados fiscais ou documento."""
    try:
        dados = request.POST.get('dados', '')
        if not dados:
            return JsonResponse({"success": False, "message": "Nenhum dado informado para hash."}, status=400)

        base_string = f"{dados}-{datetime.now().isoformat()}"
        hash_code = hashlib.sha256(base_string.encode('utf-8')).hexdigest()

        return JsonResponse({
            "success": True,
            "message": "Hash gerado com sucesso.",
            "hash": hash_code
        })
    except Exception as e:
        logger.exception("Erro ao gerar hash.")
        return JsonResponse({"success": False, "message": "Erro ao gerar hash.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Dados Dashboard
# -------------------------
@login_required
#@empresa_required
@require_GET
def ajax_dados_dashboard(request):
    """Retorna dados consolidados para o dashboard fiscal."""
    try:
        empresa = request.user.empresa
        total_retencoes = RetencaoFonte.objects.filter(empresa=empresa).aggregate(total=Sum('valor_retido'))['total'] or Decimal('0')
        total_iva = TaxaIVAAGT.objects.filter(empresa=empresa, ativo=True).count()

        return JsonResponse({
            "success": True,
            "data": {
                "total_retencoes": str(total_retencoes),
                "total_taxas_ativas": total_iva
            }
        })
    except Exception as e:
        logger.exception("Erro ao carregar dados do dashboard.")
        return JsonResponse({"success": False, "message": "Erro ao carregar dados do dashboard.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Métricas por Período
# -------------------------
@login_required
#@empresa_required
@require_GET
def ajax_metricas_periodo(request):
    """Retorna métricas fiscais e financeiras por período (mês/ano)."""
    try:
        periodo = request.GET.get('periodo', 'mensal')
        empresa = request.user.empresa

        qs = RetencaoFonte.objects.filter(empresa=empresa)
        metricas = qs.values('data_retencao__month').annotate(total=Sum('valor_retido')).order_by('data_retencao__month')

        return JsonResponse({
            "success": True,
            "periodo": periodo,
            "data": list(metricas)
        })
    except Exception as e:
        logger.exception("Erro ao carregar métricas por período.")
        return JsonResponse({"success": False, "message": "Erro ao carregar métricas.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Gráfico de Retenções
# -------------------------
@login_required
#@empresa_required
@require_GET
def ajax_grafico_retencoes(request):
    """Gera dados de gráfico para retenções mensais."""
    try:
        empresa = request.user.empresa
        dados = (RetencaoFonte.objects
                 .filter(empresa=empresa)
                 .values('data_retencao__month')
                 .annotate(total=Sum('valor_retido'))
                 .order_by('data_retencao__month'))

        return JsonResponse({"success": True, "data": list(dados)}, status=200)
    except Exception as e:
        logger.exception("Erro ao gerar gráfico de retenções.")
        return JsonResponse({"success": False, "message": "Erro ao gerar gráfico.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Verificar Documento
# -------------------------
@login_required
#@empresa_required
@require_POST
def ajax_verificar_documento(request):
    """Valida integridade de documento via hash e assinatura digital."""
    try:
        documento_hash = request.POST.get('hash', '')
        assinatura = AssinaturaDigital.objects.get(empresa=request.user.empresa)

        if assinatura.ultimo_hash == documento_hash:
            return JsonResponse({"success": True, "valid": True, "message": "Documento íntegro."})
        return JsonResponse({"success": True, "valid": False, "message": "Documento alterado ou corrompido."})
    except ObjectDoesNotExist:
        return JsonResponse({"success": False, "message": "Assinatura digital não configurada."}, status=404)
    except Exception as e:
        logger.exception("Erro ao verificar documento.")
        return JsonResponse({"success": False, "message": "Erro ao verificar documento.", "error": str(e)}, status=500)


# -------------------------
# 🔹 AJAX: Status da Assinatura Digital
# -------------------------
@login_required
#@empresa_required
@require_GET
def ajax_status_assinatura(request):
    acao_requerida = 'ver_status_atual_assinatura_digital'
    """Retorna o status da assinatura digital da empresa."""
    try:
        assinatura = AssinaturaDigital.objects.filter(empresa=request.user.empresa).first()
        if not assinatura:
            return JsonResponse({"success": False, "message": "Assinatura digital não configurada."}, status=404)

        return JsonResponse({
            "success": True,
            "data": {
                "empresa": assinatura.empresa.nome,
                "data_geracao": assinatura.data_geracao.strftime('%Y-%m-%d %H:%M'),
                "tem_chave_publica": bool(assinatura.chave_publica),
                "tem_chave_privada": bool(assinatura.chave_privada),
                "ultimo_hash": assinatura.ultimo_hash or None
            }
        })
    except Exception as e:
        logger.exception("Erro ao obter status da assinatura digital.")
        return JsonResponse({"success": False, "message": "Erro ao carregar status.", "error": str(e)}, status=500)


logger = logging.getLogger(__name__)


class DownloadRelatorioRetencoesView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_relatorio_retencoes'
    """
    Gera e faz o download do relatório de retenções na fonte (PDF, XLSX, CSV).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, formato, *args, **kwargs):
        empresa = request.user.empresa
        try:
            ficheiro, nome_arquivo, content_type = gerar_relatorio_retencoes(empresa, formato)
            logger.info(f"Relatório de retenções ({formato}) gerado para {empresa.nome}")
            response = HttpResponse(ficheiro, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
            return response
        except Exception as e:
            logger.exception(f"Erro ao gerar relatório de retenções: {e}")
            messages.error(request, f"Erro ao gerar relatório de retenções: {e}")
            raise Http404("Erro ao gerar o relatório.")


class DownloadRelatorioTaxasView(LoginRequiredMixin, View):
    acao_requerida = 'ver_relatorio_taxas_iva'
    """
    Gera e faz o download do relatório de taxas de IVA (PDF, XLSX, CSV).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, formato, *args, **kwargs):
        empresa = request.user.empresa
        try:
            ficheiro, nome_arquivo, content_type = gerar_relatorio_taxas(empresa, formato)
            logger.info(f"Relatório de taxas de IVA ({formato}) gerado para {empresa.nome}")
            response = HttpResponse(ficheiro, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
            return response
        except Exception as e:
            logger.exception(f"Erro ao gerar relatório de taxas IVA: {e}")
            messages.error(request, f"Erro ao gerar relatório: {e}")
            raise Http404("Erro ao gerar o relatório.")


class DownloadDashboardPDFView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_saft_backup_fiscal'
    """
    Gera um PDF resumido do dashboard fiscal (retencões, taxas, SAFT, assinatura).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setTitle(f"Dashboard Fiscal - {empresa.nome}")
        p.drawString(100, 800, f"Relatório Fiscal - {empresa.nome}")
        p.drawString(100, 780, f"NIF: {empresa.nif}")
        p.drawString(100, 760, f"Data: {timezone.now().strftime('%d/%m/%Y %H:%M')}")
        p.drawString(100, 740, "Resumo:")
        p.drawString(120, 720, f"- Total Retenções: {RetencaoFonte.objects.filter(empresa=empresa).count()}")
        p.drawString(120, 700, f"- Total Taxas IVA: {TaxaIVAAGT.objects.filter(empresa=empresa).count()}")
        p.drawString(120, 680, f"- Última Exportação SAF-T: {SAFTExport.objects.filter(empresa=empresa).order_by('-created_at').first()}")
        p.showPage()
        p.save()
        buffer.seek(0)
        logger.info(f"Dashboard fiscal exportado em PDF para {empresa.nome}")
        return FileResponse(buffer, as_attachment=True, filename=f"Dashboard_Fiscal_{empresa.nif}.pdf")

class DownloadSAFTFileView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_saft'
    """
    Permite o download de um ficheiro SAF-T específico.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, export_id, *args, **kwargs):
        empresa = request.user.empresa
        exportacao = get_object_or_404(SAFTExportService, pk=export_id, empresa=empresa)
        if not exportacao.arquivo or not exportacao.arquivo.path:
            raise Http404("Arquivo SAF-T não encontrado.")
        logger.info(f"Download SAF-T {exportacao.id} ({empresa.nome}) realizado.")
        return FileResponse(open(exportacao.arquivo.path, "rb"), as_attachment=True, filename=exportacao.nome_arquivo)


class DownloadSAFTBackupView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_saft_backup_fiscal'
    """
    Gera um backup fiscal completo (SAF-T + configuração + chaves).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        try:
            ficheiro, nome_ficheiro = gerar_backup_fiscal(empresa)
            response = HttpResponse(ficheiro, content_type="application/zip")
            response['Content-Disposition'] = f'attachment; filename="{nome_ficheiro}"'
            messages.success(request, "Backup SAF-T gerado com sucesso.")
            logger.info(f"Backup SAF-T criado para {empresa.nome}")
            return response
        except Exception as e:
            logger.exception(f"Erro ao gerar backup SAF-T: {e}")
            messages.error(request, "Erro ao gerar backup fiscal.")
            raise Http404("Erro ao gerar backup SAF-T.")




class DownloadTemplateRetencoesView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_retencoes'
    """
    Faz download do template CSV de importação de retenções.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        buffer = io.BytesIO()

        # ✅ Cria o conteúdo em string normal e depois converte para bytes UTF-8
        conteudo = "nif_cliente;valor;descricao;data\n500000000;10000;Serviços;2025-10-14"
        buffer.write(conteudo.encode('utf-8'))  # encode corrige o erro
        buffer.seek(0)

        logger.info("Template de retenções exportado com sucesso.")

        response = HttpResponse(buffer, content_type="text/csv; charset=utf-8")
        response['Content-Disposition'] = 'attachment; filename="template_retencoes.csv"'
        return response



class DownloadExemploSAFTView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_saft'
    """
    Fornece um exemplo de arquivo SAF-T (XML fictício para teste).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        exemplo = b'<?xml version="1.0" encoding="UTF-8"?><AuditFile><Header><CompanyName>Exemplo SAFT</CompanyName></Header></AuditFile>'
        logger.info("Arquivo exemplo SAF-T disponibilizado para download.")
        response = HttpResponse(exemplo, content_type="application/xml")
        response['Content-Disposition'] = 'attachment; filename="exemplo_saft.xml"'
        return response



class DownloadChavePublicaView(LoginRequiredMixin, View):
    acao_requerida = 'baixar_chave_publica'
    """
    Permite o download da chave pública da assinatura digital da empresa.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = request.user.empresa
        assinatura = getattr(empresa, "assinatura_fiscal", None)
        if not assinatura or not assinatura.chave_publica:
            messages.error(request, "Chave pública não encontrada.")
            raise Http404("Chave pública não disponível.")
        logger.info(f"Chave pública baixada para {empresa.nome}")
        response = HttpResponse(assinatura.chave_publica, content_type="application/x-pem-file")
        response['Content-Disposition'] = f'attachment; filename="chave_publica_{empresa.nif}.pem"'
        return response


# apps/fiscal/views_integracoes.py

import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# 🔹 WEBHOOKS – Notificações externas
# ---------------------------------------------------------

@csrf_exempt
def webhook_agt_notification(request):
    """
    Recebe notificações da AGT (Autoridade Geral Tributária) – 
    como validação de facturas, status de submissões, etc.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("Método não permitido")

    try:
        data = json.loads(request.body.decode('utf-8'))
        nif = data.get('nif')
        status = data.get('status')
        mensagem = data.get('mensagem')

        logger.info(f"[AGT Webhook] Recebido: NIF={nif}, STATUS={status}, MSG={mensagem}")

        # Aqui podes atualizar o status da factura no teu modelo FiscalDocumento
        # Exemplo:
        # FiscalDocumento.objects.filter(nif_cliente=nif).update(status_validacao=status)

        return JsonResponse({"success": True, "message": "Notificação da AGT processada"})
    except Exception as e:
        logger.exception("Erro ao processar webhook AGT")
        return JsonResponse({"success": False, "error": str(e)}, status=400)





# -------------------------
# 🔹 DEBUG: Limpar Cache
# -------------------------
@login_required
#@empresa_required
@require_POST
def debug_limpar_cache(request):
    """Limpa completamente o cache do sistema em ambiente de debug."""
    if not settings.DEBUG:
        return JsonResponse({"success": False, "message": "Acesso restrito ao modo de debug."}, status=403)

    try:
        cache.clear()
        return JsonResponse({"success": True, "message": "Cache limpo com sucesso."})
    except Exception as e:
        logger.exception("Erro ao limpar cache.")
        return JsonResponse({"success": False, "message": "Erro ao limpar cache.", "error": str(e)}, status=500)


# -------------------------
# 🔹 DEBUG: Info do Sistema
# -------------------------
@login_required
@require_GET
def debug_info_sistema(request):
    """Retorna informações detalhadas do sistema para diagnóstico."""
    if not settings.DEBUG:
        return JsonResponse({"success": False, "message": "Acesso restrito ao modo de debug."}, status=403)

    try:
        info = {
            "sistema": platform.system(),
            "versao": platform.version(),
            "python": platform.python_version(),
            "host": socket.gethostname(),
            "memoria_total": f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB",
            "memoria_usada": f"{round(psutil.virtual_memory().used / (1024**3), 2)} GB",
            "disco_total": f"{round(psutil.disk_usage('/').total / (1024**3), 2)} GB",
            "disco_usado": f"{round(psutil.disk_usage('/').used / (1024**3), 2)} GB",
            "hora_servidor": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "debug_mode": settings.DEBUG,
        }

        return JsonResponse({"success": True, "data": info}, status=200)
    except Exception as e:
        logger.exception("Erro ao coletar informações do sistema.")
        return JsonResponse({"success": False, "message": "Erro ao obter informações do sistema.", "error": str(e)}, status=500)




def has_permission_agt(user):
    return user.has_perm('fiscal.can_download_agt_keys')





@login_required
@user_passes_test(has_permission_agt)
def baixar_chave_publica(request, empresa_id):
    assinatura = get_object_or_404(AssinaturaDigital, empresa__id=empresa_id)
    formato = request.GET.get('formato', 'pem').lower()
    
    # LOG da tentativa
    AuditLogService.registrar(
        user=request.user,
        acao=f"DOWNLOAD_CHAVE_PUBLICA_{formato.upper()}",
        empresa_id=empresa_id,
        ip=request.META.get('REMOTE_ADDR')
    )

    if formato == 'pdf':
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setTitle(f"Chave Pública - {assinatura.empresa.nome}")
        
        # Cabeçalho
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, 800, f"Chave Pública RSA - {assinatura.empresa.nome}")
        p.setFont("Helvetica", 10)
        p.drawString(50, 785, f"Gerada em: {assinatura.data_geracao.strftime('%d/%m/%Y %H:%M:%S')}")
        p.drawString(50, 770, f"NIF: {assinatura.empresa.nif}")

        # Corpo da Chave
        p.setFont("Courier", 9)
        text_object = p.beginText(50, 740)
        
        # Quebrar linhas para caber na página
        chave_lines = assinatura.chave_publica.split('\n')
        for line in chave_lines:
            text_object.textLine(line)
            
        p.drawText(text_object)
        p.showPage()
        p.save()
        
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"chave_publica_{empresa_id}.pdf")

    elif formato == 'txt':
        response = HttpResponse(assinatura.chave_publica, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename=chave_publica_{empresa_id}.txt'
        return response

    else:
        # Default PEM
        response = HttpResponse(assinatura.chave_publica, content_type='application/x-pem-file')
        response['Content-Disposition'] = f'attachment; filename=chave_publica_{empresa_id}.pem'
        return response


@login_required
@user_passes_test(has_permission_agt)  # Só ADMIN MASTER
def baixar_pdf_submissao(request, empresa_id):
    empresa = get_object_or_404(Empresa, pk=empresa_id)
    assinatura = getattr(empresa, 'assinatura_fiscal', None)
    if not assinatura:
        raise Http404("Assinatura não encontrada.")
    buf = gerar_pdf_submissao_agt(empresa, assinatura)
    return FileResponse(buf, as_attachment=True, filename=f"submissao_agt_{empresa.nif or empresa.id}.pdf")




@login_required
@user_passes_test(has_permission_agt)  # Só ADMIN MASTER
def download_pdf_agt(request, empresa_id):
    empresa = get_object_or_404(Empresa, id=empresa_id)
    assinatura = get_object_or_404(AssinaturaDigital, empresa=empresa)

    return PDFAGTService.gerar_pdf_declaracao(empresa, assinatura)


