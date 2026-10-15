# apps/fiscal/views.py
import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Any
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods
from apps.empresas.models import Empresa
from django.http import FileResponse
from django.contrib.admin.views.decorators import staff_member_required

from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required, user_passes_test

from apps.fiscal.services.assinatura_service import AssinaturaDigitalService
from apps.fiscal.services.pdf_agt_service import PDFDeclaracaoService
from apps.fiscal.services.utils import FiscalServiceError, RetencaoFonteService, SAFTExportService, TaxaIVAService, validar_documentos_fiscais
from .models import AssinaturaDigital, DocumentoFiscal
from django.shortcuts import get_object_or_404
from apps.fiscal.services.audit_service import AuditLogService
from apps.fiscal.services.relatorio_service import gerar_backup_fiscal, gerar_relatorio_retencoes, gerar_relatorio_taxas
from apps.fiscal.utility.pdf import gerar_pdf_submissao_agt
from .models import SAFTExport, TaxaIVAAGT, AssinaturaDigital, RetencaoFonte
from .serializers import (
    TaxaIVAAGTSerializer, AssinaturaDigitalSerializer, RetencaoFonteSerializer
)
from apps.empresas.models import Empresa
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

logger = logging.getLogger(__name__)




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
                return redirect(reverse_lazy('core_tenants:dashboard')) # Redirecionamento para a Home ou Dashboard

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
                return redirect(reverse_lazy('core_tenants:dashboard'))

            if acao_requerida:
                if not funcionario.pode_realizar_acao(acao_requerida):
                    messages.error(
                        request,
                        f"Acesso negado. O seu cargo não permite realizar a ação de '{acao_requerida}'."
                    )
                    return redirect(reverse_lazy('core_tenants:dashboard'))

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator



logger = logging.getLogger(__name__)


# Configuração de logging
logger = logging.getLogger('fiscais.views')




class SAFTExportView(LoginRequiredMixin, PermissaoAcaoMixin, APIView):
    acao_requerida = 'exportar_saft'
    module_name = 'fiscal'
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
    module_name = 'fiscal'
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
            # FiscalDashboardService não existe — agregação directa enquanto
            # esse serviço não for implementado em utils.py.
            from django.db.models import Sum, Count
            metricas = {
                'total_retencoes': RetencaoFonte.objects.aggregate(
                    total=Sum('valor_retido'))['total'] or 0,
                'total_taxas_ativas': TaxaIVAAGT.objects.filter(ativo=True).count(),
            }
            
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




class AssinaturaDigitalViewSet(viewsets.ViewSet):
    """
    ViewSet para gestão da chave do contribuinte (singleton por tenant).
    Não é mais um ModelViewSet de listagem — só faz sentido um registo.
    """
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        assinatura = AssinaturaDigital.obter_configuracao()
        if not assinatura:
            return Response({'configurada': False})
        return Response(AssinaturaDigitalSerializer(assinatura).data)

    @action(detail=False, methods=['post'])
    def configurar_chave(self, request):
        """Regista a chave do contribuinte, tal como recebida do Portal do Contribuinte AGT."""
        nif = request.data.get('nif_contribuinte', '').strip()
        chave_privada = request.data.get('chave_privada', '').strip()
        chave_publica = request.data.get('chave_publica', '').strip() or None

        if not nif or not chave_privada:
            return Response({'error': 'NIF e chave privada são obrigatórios.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            config = AssinaturaDigitalService.configurar_chave_contribuinte(
                nif=nif, chave_privada_pem=chave_privada,
                chave_publica_pem=chave_publica, usuario=request.user,
            )
            return Response(AssinaturaDigitalSerializer(config).data)
        except FiscalServiceError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def assinar_documento(self, request):
        dados_documento = request.data.get('documento', {})
        try:
            jws = AssinaturaDigitalService.assinar_documento(dados_documento)
            return Response({'jwsDocumentSignature': jws})
        except FiscalServiceError as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def status_cadeia(self, request):
        config = AssinaturaDigital.obter_configuracao()
        if not config:
            return Response({'configurada': False, 'message': 'Assinatura digital não configurada'})
        return Response({
            'configurada': config.esta_configurada,
            'nif_contribuinte': config.nif_contribuinte,
            'ultimo_hash': config.ultimo_hash,
            'series_fiscais': config.dados_series_fiscais,
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
            assinatura = AssinaturaDigital.objects.filter().first()
            
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
    Verifica a integridade da cadeia de hash dos documentos.
    Isolamento físico: usa AssinaturaDigital.obter_configuracao() — sem filtro por empresa.
    """
    try:
        assinatura = AssinaturaDigital.obter_configuracao()
        if not assinatura:
            return JsonResponse({
                'error': 'Assinatura digital não configurada',
                'configurada': False
            }, status=404)

        # Verificar cada série fiscal
        resultados = {}
        for serie, dados in (assinatura.dados_series_fiscais or {}).items():
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
                'series_verificadas': len(resultados)
            }
        )

        return JsonResponse({
            'nif_contribuinte': assinatura.nif_contribuinte,
            'series_fiscais': resultados,
            'integridade_geral': all(s['hash_valido'] for s in resultados.values()),
            'verificado_em': timezone.now().isoformat()
        })

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
    module_name = 'fiscal'
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
        context["total_taxas_ativas"] = TaxaIVAAGT.objects.filter(ativo=True).count()
        context["total_isencoes"] = TaxaIVAAGT.objects.filter(tax_type="IS").count()
        context["total_nao_sujeitas"] = TaxaIVAAGT.objects.filter(tax_type="NS").count()
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
        queryset = TaxaIVAAGT.objects.filter()
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
    template_name = "fiscal/assinatura_digital.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assinatura"] = AssinaturaDigital.obter_configuracao()
        return context


class AssinaturaConfigurarChaveContribuinteView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """
    Substitui a antiga AssinaturaGerarChavesView: não GERA nada — apenas
    regista a chave do contribuinte que o admin colou, tal como recebida
    do Portal do Contribuinte AGT.
    """
    acao_requerida = 'configurar_assinatura_digital'
    template_name = "fiscal/assinatura_configurar.html"

    def get(self, request, *args, **kwargs):
        from apps.fiscal.models import AssinaturaDigital
        assinatura = AssinaturaDigital.obter_configuracao()
        return render(request, self.template_name, {
            'assinatura': assinatura,
            'ja_configurada': assinatura.esta_configurada,
        })

    def post(self, request, *args, **kwargs):
        from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, FiscalServiceError
        from apps.fiscal.utility.crypto import AESService

        nif = request.POST.get('nif_contribuinte', '').strip()
        chave_privada = request.POST.get('chave_privada', '').strip()
        chave_publica = request.POST.get('chave_publica', '').strip() or None
        api_username = request.POST.get('api_username', '').strip()
        api_password = request.POST.get('api_password', '').strip()

        if not nif or not chave_privada:
            messages.error(request, "NIF e chave privada do contribuinte são obrigatórios.")
            return redirect("fiscal:assinatura-configurar")

        try:
            config = AssinaturaDigitalService.configurar_chave_contribuinte(
                nif=nif,
                chave_privada_pem=chave_privada,
                chave_publica_pem=chave_publica,
                usuario=request.user,
            )
            # Guardar credenciais API AGT se fornecidas
            if api_username:
                config.api_username = api_username
            if api_password:
                config.api_password = AESService.encrypt(api_password)
            if api_username or api_password:
                config.save(update_fields=['api_username', 'api_password'])

            messages.success(request, "Chave do contribuinte configurada com sucesso. "
                                       "O sistema já pode assinar documentos fiscais.")
        except FiscalServiceError as e:
            messages.error(request, str(e))
            return redirect("fiscal:assinatura-configurar")

        return redirect("fiscal:assinatura-digital")


class AssinaturaGerarChavesView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'configurar_assinatura_digital'
    """
    Redireciona para a view correcta de configuração.
    Esta classe existe apenas para compatibilidade com rotas antigas —
    a lógica real está em AssinaturaConfigurarChaveContribuinteView.
    A geração de chaves pelo sistema foi eliminada: a chave do contribuinte
    é sempre emitida pela AGT e colada manualmente pelo admin.
    """

    def get(self, request, *args, **kwargs):
        return redirect("fiscal:assinatura-digital")

    def post(self, request, *args, **kwargs):
        return AssinaturaConfigurarChaveContribuinteView.as_view()(request, *args, **kwargs)
    

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
        search = self.request.GET.get("q", "")
        queryset = RetencaoFonte.objects.filter()
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
        retencao = get_object_or_404(RetencaoFonte, pk=kwargs["pk"], )
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
        context["total_retencoes"] = RetencaoFonte.objects.filter().count()
        context["total_taxas_iva"] = TaxaIVAAGT.objects.filter(ativo=True).count()
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
        queryset = RetencaoFonte.objects.filter()
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
        queryset = TaxaIVAAGT.objects.filter()
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


class SAFTExportWebView(PermissaoAcaoMixin, View):
    """
    Exporta o SAF-T AO 1.01_01 para o período solicitado.
    Usa SaftXmlGeneratorService (novo gerador) e valida o XML contra o XSD
    antes de devolvê-lo — os erros XSD são incluídos nos headers HTTP para
    diagnóstico sem bloquear o download (a AGT valida do seu lado também).
    """
    acao_requerida = 'exportar_saft'

    def post(self, request, *args, **kwargs):
        from apps.fiscal.services.saft_xml_generator_service import SaftXmlGeneratorService
        from apps.fiscal.services.saft_validacao_service import SaftValidacaoService

        try:
            empresa = request.user.empresa
            data = json.loads(request.body)

            data_inicio_str = data.get('dataInicio')
            data_fim_str = data.get('dataFim')

            if not data_inicio_str or not data_fim_str:
                return JsonResponse(
                    {'success': False, 'error': 'dataInicio e dataFim são obrigatórios (YYYY-MM-DD).'},
                    status=400,
                )

            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()

            logger.info(
                "Exportação SAF-T iniciada",
                extra={'empresa': empresa.nif, 'inicio': data_inicio_str, 'fim': data_fim_str},
            )

            # Gerar XML com o novo gerador (SaftXmlGeneratorService)
            gerador = SaftXmlGeneratorService(empresa, data_inicio, data_fim)
            xml_bytes = gerador.generate_xml()

            # Validar contra XSD — não bloqueia o download, mas anota o resultado
            valido, erros_xsd = SaftValidacaoService.validar(xml_bytes)
            if not valido:
                logger.warning(
                    "SAF-T gerado mas com erros XSD: %d erro(s). Primeiro: %s",
                    len(erros_xsd), erros_xsd[0] if erros_xsd else '',
                )

            nome_ficheiro = f"SAFT_{empresa.nif}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xml"
            response = HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
            response['Content-Disposition'] = f'attachment; filename="{nome_ficheiro}"'
            # Informa o cliente sobre a validade XSD via header (não bloqueia)
            response['X-SAFT-XSD-Valid'] = 'true' if valido else 'false'
            response['X-SAFT-XSD-Errors'] = str(len(erros_xsd))
            return response

        except (ValueError, KeyError) as e:
            return JsonResponse({'success': False, 'error': f'Parâmetros inválidos: {e}'}, status=400)
        except Exception as e:
            logger.exception("Erro na exportação SAF-T")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class SAFTValidarXSDView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """
    Endpoint de validação XSD: gera o SAF-T do período e devolve JSON com
    o resultado da validação contra o schema SAFTAO1.01_01.xsd.

    Útil para diagnosticar erros antes de submeter à AGT ou fazer o download.

    POST body: {"dataInicio": "YYYY-MM-DD", "dataFim": "YYYY-MM-DD"}
    Resposta: {"valido": bool, "total_erros": int, "erros": ["...", ...]}
    """
    acao_requerida = 'exportar_saft'

    def post(self, request, *args, **kwargs):
        from apps.fiscal.services.saft_xml_generator_service import SaftXmlGeneratorService
        from apps.fiscal.services.saft_validacao_service import SaftValidacaoService

        try:
            empresa = request.user.empresa
            data = json.loads(request.body)
            data_inicio_str = data.get('dataInicio', '')
            data_fim_str = data.get('dataFim', '')

            if not data_inicio_str or not data_fim_str:
                return JsonResponse(
                    {'error': 'dataInicio e dataFim obrigatórios (YYYY-MM-DD).'},
                    status=400,
                )

            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()

            xml_bytes = SaftXmlGeneratorService(empresa, data_inicio, data_fim).generate_xml()
            resultado = SaftValidacaoService.resumo(xml_bytes)
            return JsonResponse(resultado)

        except (ValueError, KeyError) as e:
            return JsonResponse({'error': f'Parâmetros inválidos: {e}'}, status=400)
        except Exception as e:
            logger.exception("Erro na validação XSD do SAF-T")
            return JsonResponse({'error': str(e)}, status=500)


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
        context["ultima_validacao"] = timezone.now().strftime("%d/%m/%Y %H:%M")
        context["assinatura"] = getattr("assinatura_fiscal")
        context["total_retencoes"] = RetencaoFonte.objects.filter().count()
        context["total_taxas"] = TaxaIVAAGT.objects.filter(ativo=True).count()
        return context


class ValidarDocumentosView(LoginRequiredMixin, View):
    acao_requerida = 'validar_documentos_fiscais'
    """
    Executa validações em documentos fiscais emitidos (faturas, notas de crédito, etc.).
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        empresa = getattr(connection, 'tenant', None)
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
        empresa = getattr(connection, 'tenant', None)
        context["empresa"] = empresa
        context["assinatura_digital"] = getattr(empresa, "assinatura_fiscal", None)
        context["total_taxas"] = TaxaIVAAGT.objects.filter().count()
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
        empresa = getattr(connection, 'tenant', None)
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

        existe = Fornecedor.objects.filter(nif=nif).exists()
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
        total_retencoes = RetencaoFonte.objects.filter().aggregate(total=Sum('valor_retido'))['total'] or Decimal('0')
        total_iva = TaxaIVAAGT.objects.filter(ativo=True).count()

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

        qs = RetencaoFonte.objects.filter()
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
                 .filter()
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

@require_POST
def ajax_verificar_documento(request):
    """Valida integridade de documento via hash e assinatura digital."""
    try:
        documento_hash = request.POST.get('hash', '')

        # ✅ Padrão django-tenants: O schema ativo já isola os dados da empresa.
        # Não precisa passar nenhum filtro de empresa.
        assinatura = AssinaturaDigital.objects.get() 

        if assinatura.ultimo_hash == documento_hash:
            return JsonResponse({"success": True, "valid": True, "message": "Documento íntegro."})
            
        return JsonResponse({"success": True, "valid": False, "message": "Documento alterado ou corrompido."})

    except AssinaturaDigital.DoesNotExist:
        return JsonResponse({"success": False, "message": "Assinatura digital não configurada."}, status=404)
    except AssinaturaDigital.MultipleObjectsReturned:
        logger.error("Mais de uma assinatura digital configurada no schema do tenant.")
        return JsonResponse({"success": False, "message": "Erro de configuração da assinatura."}, status=500)
    except Exception as e:
        logger.exception("Erro ao verificar documento.")
        return JsonResponse({"success": False, "message": "Erro ao verificar documento.", "error": str(e)}, status=500)

# -------------------------
# 🔹 AJAX: Status da Assinatura Digital
# -------------------------
@login_required
@require_GET
def ajax_status_assinatura(request):
    """Retorna o status da assinatura digital do tenant activo."""
    try:
        assinatura = AssinaturaDigital.obter_configuracao()
        if not assinatura:
            return JsonResponse({"success": False, "message": "Assinatura digital não configurada."}, status=404)

        return JsonResponse({
            "success": True,
            "data": {
                "nif_contribuinte": assinatura.nif_contribuinte,
                "configurada": assinatura.esta_configurada,
                "data_configuracao_chave": (
                    assinatura.data_configuracao_chave.strftime('%Y-%m-%d %H:%M')
                    if assinatura.data_configuracao_chave else None
                ),
                "tem_chave_publica": bool(assinatura.chave_contribuinte_publica),
                "ultimo_hash": assinatura.ultimo_hash or None
            }
        })
    except Exception as e:
        logger.exception("Erro ao obter status da assinatura digital.")
        return JsonResponse({"success": False, "message": "Erro ao carregar status.", "error": str(e)}, status=500)


@login_required
@require_POST
def ajax_testar_assinatura(request):
    """
    S10 — Testa a assinatura digital do contribuinte com um documento de teste.
    Recebe { "documento": "texto" } e tenta gerar uma assinatura JWS.
    Não persiste nada na BD.
    """
    from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, FiscalServiceError
    try:
        import json as _json
        body = _json.loads(request.body)
        texto_doc = body.get('documento', 'teste')
    except Exception:
        texto_doc = 'teste'

    try:
        # Montar um payload de teste com os campos obrigatórios AGT
        dados_teste = {
            "documentNo": "FT TESTE/0001",
            "taxRegistrationNumber": "000000001",
            "documentType": "FT",
            "documentDate": "2026-01-01",
            "customerTaxID": "000000000",
            "customerCountry": "AO",
            "companyName": "Empresa Teste",
            "documentTotals": {
                "grossTotal": "100.00",
                "netTotal": "86.21",
                "taxPayable": "13.79",
            },
            "_conteudo_teste": texto_doc[:200],
        }
        assinatura_jws = AssinaturaDigitalService.assinar_documento(dados_teste)
        return JsonResponse({
            'success': True,
            'titulo': 'Assinatura JWS gerada com sucesso',
            'mensagem': 'O sistema assinou um documento de teste com a chave do contribuinte.',
            'hash': assinatura_jws[:80] + '...' if len(assinatura_jws) > 80 else assinatura_jws,
        })
    except FiscalServiceError as e:
        return JsonResponse({'success': False, 'mensagem': str(e)}, status=400)
    except Exception as e:
        logger.exception("Erro ao testar assinatura digital.")
        return JsonResponse({'success': False, 'mensagem': f'Erro interno: {e}'}, status=500)




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
        p.drawString(120, 720, f"- Total Retenções: {RetencaoFonte.objects.filter().count()}")
        p.drawString(120, 700, f"- Total Taxas IVA: {TaxaIVAAGT.objects.filter().count()}")
        p.drawString(120, 680, f"- Última Exportação SAF-T: {SAFTExport.objects.filter().order_by('-created_at').first()}")
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
        exportacao = get_object_or_404(SAFTExportService, pk=export_id, )
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
    Permite o download da chave pública do contribuinte deste tenant.
    Isolamento físico: usa AssinaturaDigital.obter_configuracao() — sem FK empresa.
    """
    permission_classes = [MultiplePermissions]
    multiple_permissions = {'AND': [EmpresaPermission, FiscalPermission]}

    def get(self, request, *args, **kwargs):
        assinatura = AssinaturaDigital.obter_configuracao()
        if not assinatura or not assinatura.chave_contribuinte_publica:
            messages.error(request, "Chave pública do contribuinte não configurada para este tenant.")
            raise Http404("Chave pública não disponível.")
        nif = assinatura.nif_contribuinte or 'contribuinte'
        logger.info(f"Chave pública baixada — NIF {nif}")
        response = HttpResponse(assinatura.chave_contribuinte_publica, content_type="application/x-pem-file")
        response['Content-Disposition'] = f'attachment; filename="chave_publica_{nif}.pem"'
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


# webhook_agt_notification foi movido para views_integracoes.py com HMAC. Esta cópia foi removida.


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
@login_required
@user_passes_test(has_permission_agt)
def baixar_chave_publica(request):
    assinatura = AssinaturaDigital.obter_configuracao()
    if not assinatura or not assinatura.chave_contribuinte_publica:
        raise Http404("Chave pública não configurada.")
    formato = request.GET.get('formato', 'pem').lower()

    AuditLogService.registrar(
        user=request.user,
        acao=f"DOWNLOAD_CHAVE_PUBLICA_{formato.upper()}",
        empresa_id=connection.tenant.id,
        ip=request.META.get('REMOTE_ADDR')
    )

    if formato == 'pdf':
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        p.setFont("Helvetica-Bold", 14)
        p.drawString(50, 800, f"Chave Pública do Contribuinte — NIF {assinatura.nif_contribuinte}")
        p.setFont("Courier", 9)
        text_object = p.beginText(50, 740)
        for line in assinatura.chave_contribuinte_publica.split('\n'):
            text_object.textLine(line)
        p.drawText(text_object)
        p.showPage()
        p.save()
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename="chave_publica_do_contribuinte.pdf")

    response = HttpResponse(assinatura.chave_contribuinte_publica, content_type='application/x-pem-file')
    response['Content-Disposition'] = 'attachment; filename=chave_publica_do_contribuinte.pem'
    return response




@login_required
@user_passes_test(has_permission_agt)  # Só ADMIN MASTER
def baixar_pdf_submissao(request):
    """
    Gera e devolve o PDF de submissão à AGT para o tenant activo.
    Isolamento físico: usa AssinaturaDigital.obter_configuracao() — sem FK empresa nem empresa_id na URL.
    """
    assinatura = AssinaturaDigital.obter_configuracao()
    if not assinatura or not assinatura.esta_configurada:
        raise Http404("Assinatura do contribuinte não configurada para este tenant.")
    empresa = request.user.empresa
    buf = gerar_pdf_submissao_agt(empresa, assinatura)
    return FileResponse(buf, as_attachment=True, filename=f"submissao_agt_{empresa.nif or 'tenant'}.pdf")




@login_required
@user_passes_test(has_permission_agt)  # Só ADMIN MASTER
def download_pdf_agt(request):
    """
    Gera PDF de declaração AGT para o tenant activo.
    Isolamento físico: usa AssinaturaDigital.obter_configuracao() — sem FK empresa nem empresa_id na URL.
    """
    assinatura = AssinaturaDigital.obter_configuracao()
    if not assinatura or not assinatura.esta_configurada:
        raise Http404("Assinatura do contribuinte não configurada para este tenant.")
    empresa = request.user.empresa
    return PDFDeclaracaoService.gerar_pdf_declaracao(empresa, assinatura)




# ──────────────────────────────────────────────────────────────────────────────
# DocumentoFiscalViewSet — Secção 3 (Imutabilidade + Máquina de estados)
# ──────────────────────────────────────────────────────────────────────────────

from rest_framework import viewsets
from apps.fiscal.serializers import DocumentoFiscalSerializer
from apps.fiscal.services.documento_fiscal_service import DocumentoFiscalService
from apps.fiscal.services.utils import FiscalServiceError


class DocumentoFiscalViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestão de DocumentoFiscal com protecção de imutabilidade.

    Endpoints de leitura e criação (draft) estão disponíveis normalmente.
    Edição (PUT/PATCH) só é permitida em documentos no estado 'draft'.
    DELETE é bloqueado — documentos fiscais nunca são apagados.

    Endpoints adicionais de transição de estado:
        POST  /api/documentos-fiscais/{id}/emitir/
        POST  /api/documentos-fiscais/{id}/lancar/
        POST  /api/documentos-fiscais/{id}/pagar/
        POST  /api/documentos-fiscais/{id}/cancelar/
        POST  /api/documentos-fiscais/{id}/rectificar/
        PATCH /api/documentos-fiscais/{id}/comentarios/
    """
    serializer_class   = DocumentoFiscalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return DocumentoFiscal.objects.select_related(
            'cliente', 'empresa', 'usuario_criacao', 'documento_original'
        ).order_by('-data_emissao', '-numero')

    def perform_create(self, serializer):
        serializer.save(
            usuario_criacao=self.request.user,
            status='draft',
        )

    def update(self, request, *args, **kwargs):
        """PUT/PATCH — bloqueado para campos fiscais após emissão."""
        instance = self.get_object()
        if instance.status != 'draft':
            campos_fiscais = DocumentoFiscalService.CAMPOS_FISCAIS_READONLY
            tentativa = set(request.data.keys()) & campos_fiscais
            if tentativa:
                return Response(
                    {
                        'detail': (
                            f"O documento '{instance.numero_documento}' está emitido "
                            f"(status='{instance.status}'). "
                            f"Campos fiscais não podem ser alterados: {', '.join(tentativa)}. "
                            f"Emita um documento rectificativo (NC/ND) para corrigir."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """DELETE — sempre bloqueado. Documentos fiscais nunca são apagados."""
        instance = self.get_object()
        return Response(
            {
                'detail': (
                    f"O documento fiscal '{instance.numero_documento}' não pode ser apagado. "
                    f"Para invalidar, use o endpoint /cancelar/ ou /rectificar/."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── Endpoints de transição de estado ─────────────────────────────────────

    @action(detail=True, methods=['post'])
    def emitir(self, request, pk=None):
        """DRAFT → CONFIRMED. Gera hash, assina e bloqueia campos fiscais."""
        doc = self.get_object()
        try:
            DocumentoFiscalService.emitir(doc, request.user)
            return Response(DocumentoFiscalSerializer(doc).data)
        except (FiscalServiceError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def lancar(self, request, pk=None):
        """CONFIRMED → POSTED."""
        doc = self.get_object()
        try:
            DocumentoFiscalService.lancar(doc, request.user)
            return Response(DocumentoFiscalSerializer(doc).data)
        except (FiscalServiceError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def pagar(self, request, pk=None):
        """CONFIRMED/POSTED → PAID."""
        doc = self.get_object()
        try:
            DocumentoFiscalService.registar_pagamento(
                doc, request.user, dados_pagamento=request.data or None
            )
            return Response(DocumentoFiscalSerializer(doc).data)
        except (FiscalServiceError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        """
        Cancela o documento. Body: {"motivo_codigo": "N", "motivo_texto": "..."}
        motivo_codigo: 'I' ou 'N' (obrigatório para docs já emitidos).
        """
        doc = self.get_object()
        motivo_codigo = request.data.get('motivo_codigo', 'N')
        motivo_texto  = request.data.get('motivo_texto', '')
        try:
            DocumentoFiscalService.cancelar(
                doc, request.user,
                motivo_codigo=motivo_codigo,
                motivo_texto=motivo_texto,
            )
            return Response(DocumentoFiscalSerializer(doc).data)
        except (FiscalServiceError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def rectificar(self, request, pk=None):
        """
        Marca o doc como RECTIFIED e cria NC/ND em draft.
        Body: {"tipo_rectificativo": "NC", "motivo": "..."}
        """
        doc = self.get_object()
        tipo = request.data.get('tipo_rectificativo', 'NC')
        motivo = request.data.get('motivo', '')
        try:
            correctivo = DocumentoFiscalService.rectificar(
                doc, request.user, tipo_rectificativo=tipo, motivo=motivo
            )
            return Response(
                DocumentoFiscalSerializer(correctivo).data,
                status=status.HTTP_201_CREATED,
            )
        except (FiscalServiceError, Exception) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['patch'], url_path='comentarios')
    def actualizar_comentarios(self, request, pk=None):
        """
        Actualiza o campo 'comentarios' — único campo editável após emissão.
        Body: {"comentarios": "texto livre..."}
        """
        doc = self.get_object()
        comentarios = request.data.get('comentarios', '')
        try:
            DocumentoFiscalService.actualizar_comentarios(doc, request.user, comentarios)
            return Response({'comentarios': doc.comentarios})
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ============================================================
# === HOMOLOGAÇÃO AGT — Dashboard 17 Pontos (S11) ===
# ============================================================

PONTOS_HOMOLOGACAO = [
    {'numero': 1,    'descricao': 'Factura com NIF do cliente',                        'tipo_doc': 'FT', 'saft_campo': 'CustomerTaxID',         'notas': ''},
    {'numero': 2,    'descricao': 'Factura anulada',                                   'tipo_doc': 'FT', 'saft_campo': 'DocumentStatus = "A"',  'notas': 'PDF com marca visual "ANULADO"'},
    {'numero': 3,    'descricao': 'Documento pró-forma',                               'tipo_doc': 'FP', 'saft_campo': 'WorkingDocuments',       'notas': ''},
    {'numero': '4a', 'descricao': 'Factura a partir da pró-forma',                     'tipo_doc': 'FT', 'saft_campo': 'OrderReferences',        'notas': ''},
    {'numero': '4b', 'descricao': 'Nota de Crédito com referência à factura',          'tipo_doc': 'NC', 'saft_campo': 'OrderReference',         'notas': ''},
    {'numero': 5,    'descricao': 'Factura com 2 linhas: IVA 14% + Isenção M11',       'tipo_doc': 'FT', 'saft_campo': 'TaxExemptionReason',     'notas': ''},
    {'numero': 6,    'descricao': 'Desconto global (SettlementAmount, UniPrice 4 dec)', 'tipo_doc': 'FT', 'saft_campo': 'SettlementAmount',       'notas': 'Qty=100, UniPrice=0.5500, IVA=8.8%'},
    {'numero': 7,    'descricao': 'Documento em moeda estrangeira',                    'tipo_doc': 'FT', 'saft_campo': 'Currency/ExchangeRate',  'notas': 'USD'},
    {'numero': 8,    'descricao': 'Sem NIF, total < 50 AOA, hora ≤ 10h',              'tipo_doc': 'FR', 'saft_campo': 'SystemEntryDate',        'notas': ''},
    {'numero': 9,    'descricao': 'Outro cliente sem NIF (distinto do ponto 8)',        'tipo_doc': 'FR', 'saft_campo': '',                       'notas': ''},
    {'numero': 10,   'descricao': 'Duas guias de remessa (DT)',                         'tipo_doc': 'GT', 'saft_campo': 'MovementOfGoods',        'notas': 'Dois documentos'},
    {'numero': 11,   'descricao': 'Segundo orçamento / pró-forma adicional',            'tipo_doc': 'OR', 'saft_campo': 'WorkingDocuments',       'notas': ''},
    {'numero': 12,   'descricao': 'Factura genérica (GF) + Auto-facturação (AF)',       'tipo_doc': 'GF+AF', 'saft_campo': 'InvoiceType',         'notas': ''},
    {'numero': 13,   'descricao': 'Factura global (FG)',                                'tipo_doc': 'FG', 'saft_campo': 'InvoiceType',            'notas': ''},
    {'numero': 14,   'descricao': 'Outros documentos (Nota de Débito, Recibo)',         'tipo_doc': 'ND+RC', 'saft_campo': '',                    'notas': ''},
    {'numero': 15,   'descricao': 'Índice de correspondência',                          'tipo_doc': None, 'saft_campo': '',                       'notas': 'Documento de submissão'},
    {'numero': 16,   'descricao': 'Documentos não aplicáveis',                          'tipo_doc': None, 'saft_campo': '',                       'notas': 'TV, LD — não aplicáveis'},
    {'numero': 17,   'descricao': 'Ficheiro SAF-T XML único (todos os documentos)',     'tipo_doc': 'XML', 'saft_campo': 'HashControl + XSD',     'notas': 'Validar contra XSD AO 1.01_01'},
]


class HomologacaoDashboardView(LoginRequiredMixin, PermissaoAcaoMixin, TemplateView):
    """Dashboard de acompanhamento dos 17 pontos de homologação AGT."""
    acao_requerida = 'ver_status_atual_assinatura_digital'
    template_name = 'fiscal/homologacao_dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Verificar quais documentos HOM- já foram gerados
        from apps.fiscal.models import DocumentoFiscal, AssinaturaDigital
        docs_hom = set(
            DocumentoFiscal.objects.filter(numero_documento__startswith='HOM-')
            .values_list('numero_documento', flat=True)
        )

        pontos_status = []
        for ponto in PONTOS_HOMOLOGACAO:
            num = ponto['numero']
            # Verificar se existe documento para este ponto
            numero_doc = None
            tipo = ponto['tipo_doc'] or ''
            nao_aplicavel = str(num) in ('15', '16')
            gerado = nao_aplicavel  # 15 e 16 não precisam de doc

            if not nao_aplicavel and tipo not in ('XML',):
                from django.utils import timezone
                ano = timezone.now().year
                tipo_simples = tipo.split('+')[0] if '+' in tipo else tipo
                candidatos = [
                    f'HOM-{tipo_simples}{ano}/{n:04d}'
                    for n in range(1, 20)
                ]
                for cand in candidatos:
                    if cand in docs_hom:
                        numero_doc = cand
                        gerado = True
                        break

            if str(num) == '17':
                import os
                from django.conf import settings as dj_settings
                pasta_saft = os.path.join(
                    getattr(dj_settings, 'BASE_DIR', '.'), 'media', 'homologacao'
                )
                gerado = os.path.isdir(pasta_saft) and bool(os.listdir(pasta_saft))

            pontos_status.append({
                **ponto,
                'gerado': gerado,
                'nao_aplicavel': nao_aplicavel,
                'numero_doc': numero_doc,
            })

        # Info do último SAF-T
        import os
        from django.conf import settings as dj_settings
        from django.utils import timezone
        pasta_saft = os.path.join(
            getattr(dj_settings, 'BASE_DIR', '.'), 'media', 'homologacao'
        )
        ultimo_saft = None
        if os.path.isdir(pasta_saft):
            ficheiros = sorted(
                [f for f in os.listdir(pasta_saft) if f.endswith('.xml')],
                reverse=True
            )
            if ficheiros:
                caminho = os.path.join(pasta_saft, ficheiros[0])
                tamanho = os.path.getsize(caminho)
                mtime = os.path.getmtime(caminho)
                import datetime
                ultimo_saft = {
                    'nome': ficheiros[0],
                    'tamanho': f'{tamanho / 1024:.1f} KB',
                    'data': datetime.datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M'),
                }

        assinatura = AssinaturaDigital.obter_configuracao()
        ctx.update({
            'pontos': pontos_status,
            'documentos_gerados': sum(1 for p in pontos_status if p['gerado']),
            'ultimo_saft': ultimo_saft,
            'assinatura_configurada': assinatura.esta_configurada if assinatura else False,
        })
        return ctx


class HomologacaoGerarView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """POST — Gera todos os documentos de homologação via management command inline."""
    acao_requerida = 'configurar_assinatura_digital'

    def post(self, request):
        from django.db import connection
        from io import StringIO
        from django.core.management import call_command

        schema = connection.schema_name
        out = StringIO()
        erros = []
        try:
            call_command(
                'gerar_documentos_homologacao',
                schema=schema,
                stdout=out,
                stderr=out,
            )
            messages.success(request, 'Documentos de homologação gerados com sucesso!')
        except Exception as exc:
            messages.error(request, f'Erro ao gerar documentos: {exc}')

        return redirect('fiscal:homologacao-dashboard')


class HomologacaoGerarPontoView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """POST — Gera apenas um ponto específico."""
    acao_requerida = 'configurar_assinatura_digital'

    def post(self, request, ponto):
        from django.db import connection
        from io import StringIO
        from django.core.management import call_command

        schema = connection.schema_name
        out = StringIO()
        try:
            call_command(
                'gerar_documentos_homologacao',
                schema=schema,
                ponto=str(ponto),
                stdout=out,
            )
            messages.success(request, f'Ponto {ponto} gerado com sucesso!')
        except Exception as exc:
            messages.error(request, f'Erro no ponto {ponto}: {exc}')

        return redirect('fiscal:homologacao-dashboard')


class HomologacaoGerarSaftView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """POST — Gera só o SAF-T XML (ponto 17)."""
    acao_requerida = 'ver_status_atual_assinatura_digital'

    def get(self, request):
        from django.db import connection
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        try:
            call_command(
                'gerar_documentos_homologacao',
                schema=connection.schema_name,
                apenas_saft=True,
                stdout=out,
            )
            messages.success(request, 'SAF-T XML gerado com sucesso!')
        except Exception as exc:
            messages.error(request, f'Erro ao gerar SAF-T: {exc}')

        return redirect('fiscal:homologacao-dashboard')


class HomologacaoDownloadSaftView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """GET — Download do último SAF-T de homologação."""
    acao_requerida = 'ver_status_atual_assinatura_digital'

    def get(self, request):
        import os
        from django.http import FileResponse, Http404
        from django.conf import settings as dj_settings
        from django.db import connection

        pasta = os.path.join(
            getattr(dj_settings, 'BASE_DIR', '.'), 'media', 'homologacao'
        )
        if not os.path.isdir(pasta):
            raise Http404('Nenhum SAF-T gerado ainda.')

        ficheiros = sorted(
            [f for f in os.listdir(pasta) if f.endswith('.xml')],
            reverse=True
        )
        if not ficheiros:
            raise Http404('Nenhum SAF-T encontrado.')

        caminho = os.path.join(pasta, ficheiros[0])
        return FileResponse(
            open(caminho, 'rb'),
            as_attachment=True,
            filename=ficheiros[0],
            content_type='application/xml',
        )


class HomologacaoPdfView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    """GET — Gera o PDF de um documento de homologação específico."""
    acao_requerida = 'ver_status_atual_assinatura_digital'

    def get(self, request, numero_documento):
        from apps.fiscal.models import DocumentoFiscal
        from django.http import Http404
        try:
            doc = DocumentoFiscal.objects.get(numero_documento=numero_documento)
        except DocumentoFiscal.DoesNotExist:
            raise Http404(f'Documento {numero_documento} não encontrado.')

        try:
            from apps.fiscal.services.pdf_agt_service import PDFDocumentoService
            pdf_bytes = PDFDocumentoService.gerar_pdf(doc)
            from django.http import HttpResponse
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = (
                f'inline; filename="{numero_documento.replace("/", "_")}.pdf"'
            )
            return response
        except Exception as exc:
            messages.error(request, f'Erro ao gerar PDF: {exc}')
            return redirect('fiscal:homologacao-dashboard')
