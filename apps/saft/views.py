# apps/saft/views.py
from django.shortcuts import render
from django.views import View
from django.http import HttpResponse
from datetime import datetime, date
from django.contrib.auth.mixins import LoginRequiredMixin
import os
import json
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from django.db import models
from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import HttpResponse, JsonResponse, Http404
from django.core.paginator import Paginator
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from apps.fiscal.models import TaxaIVAAGT
from apps.empresas.models import Empresa
from apps.fiscal.models import TaxaIVAAGT
from django.contrib.auth.mixins import AccessMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.urls import reverse
from apps.fiscal.services.utils import SAFTExportService
from apps.saft.services.saft_xml_generator_service import SaftXmlGeneratorService




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
                return redirect(reverse_lazy('home')) # Redirecionamento para a Home ou Dashboard

        return super().dispatch(request, *args, **kwargs)




class SaftExportView(LoginRequiredMixin, View, PermissaoAcaoMixin, AccessMixin):
    acao_requerida = 'exportar_saft'
    """
    View para solicitar e servir o ficheiro SAF-T (AO) XML.
    Garante que apenas utilizadores logados podem aceder.
    """ 

    template_name = 'saft/saft_export_form.html'

    def test_func(self):
        """ Verifica se o utilizador tem a permissão 'saft.export_saft'. """
        # O UserPassesTestMixin irá redirecionar o utilizador sem permissão para 403 (Forbidden)
        return self.request.user.has_perm('saft.export_saft')
    
    def test_func(self):
        """ Verifica se o utilizador tem a permissão 'saft.export_saft'. """
        # O UserPassesTestMixin irá redirecionar o utilizador sem permissão para 403 (Forbidden)
        return self.request.user.has_perm('saft.export_saft')
    
    def get(self, request):
        """ Renderiza o formulário de seleção de datas. """
        # Poderia pré-preencher com o mês anterior
        return render(request, self.template_name)

    def post(self, request):
        """ Processa o formulário e gera o ficheiro XML. """
        
        # 1. Validação de Acesso (RBAC Implícito)
        # 🚨 AQUI DEVE ENTRAR A VALIDAÇÃO DE PERMISSÃO (Ex: é gestor fiscal?)
        if not request.user.has_perm('saft.export_saft'):
            return HttpResponse("Acesso negado. Requer permissão de Gestor Fiscal.", status=403)

        # 2. Captura e Conversão das Datas
        try:
            # As datas vêm como strings do formulário HTML
            data_inicio_str = request.POST.get('data_inicio')
            data_fim_str = request.POST.get('data_fim')
            
            # Conversão para objetos datetime.date para precisão fiscal
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date()
            
            # Ajustar para o fuso horário (necessário para consultas DateTimeField)
            data_inicio_dt = datetime.combine(data_inicio, datetime.min.time(), tzinfo=request.user.empresa.timezone) 
            data_fim_dt = datetime.combine(data_fim, datetime.max.time(), tzinfo=request.user.empresa.timezone)
            

        except (ValueError, TypeError):
            # Retorna um erro amigável se o formato da data estiver incorreto
            return render(request, self.template_name, {'error': 'Formato de data inválido. Use AAAA-MM-DD.'})
        
        # 3. Execução do Serviço de Geração de XML
        
        # A empresa logada é extraída do utilizador (Assumindo request.user.empresa existe)
        empresa_ativa = request.user.empresa 
        
        try:
            generator = SaftXmlGeneratorService(
                empresa=empresa_ativa,
                data_inicio=data_inicio_dt,
                data_fim=data_fim_dt
            )
            
            
            # A geração exige a Tabela de Impostos (TaxaIVAAGT)
            xml_content = generator.generate_xml(TaxaIVAAGT) 
            # 🚨 LOGGING CRÍTICO
            print(f"SAF-T EXPORTADO: Utilizador '{request.user.username}' exportou dados de {data_inicio_str} a {data_fim_str} para a Empresa '{empresa_ativa.nome}'.")

            

        except Exception as e:
            # Logar o erro (CRÍTICO em produção)
            print(f"ERRO CRÍTICO NA GERAÇÃO SAF-T: {e}") 
            return render(request, self.template_name, {'error': f'Falha ao gerar o SAF-T: {e}'})
        
        # 4. Resposta de Download (HTTP Response)
        
        # Nome do Ficheiro (Padrão SAF-T: NIF_DATAINICIO_DATAFIM.xml)
        filename = f"{empresa_ativa.nif}_{data_inicio.strftime('%Y%m%d')}_{data_fim.strftime('%Y%m%d')}.xml"
        
        response = HttpResponse(xml_content, content_type='application/xml')
        
        # Este cabeçalho força o browser a descarregar o ficheiro em vez de o exibir
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response


logger = logging.getLogger('saft')

class SaftHistoricoView(LoginRequiredMixin, PermissaoAcaoMixin, PermissionRequiredMixin, View):
    acao_requerida = 'ver_historico_saft'
    """
    View para exibir histórico de exportações SAF-T realizadas.
    Inclui filtros, paginação e opções de download/visualização.
    """
    
    template_name = 'saft/saft_historico.html'
    permission_required = 'saft.view_saftexportlog'
    paginate_by = 20
    
    def test_func(self):
        """Verifica se o utilizador tem permissão para ver histórico SAF-T."""
        return self.request.user.has_perm('saft.view_saftexportlog')
    
    def get(self, request):
        """Renderiza página do histórico com filtros e paginação."""
        
        try:
            # 1. Obter empresa ativa do utilizador
            empresa_ativa = request.user.empresa
            
            # 2. Query base - apenas exportações da empresa do utilizador
            exports_queryset = SAFTExportService.objects.filter(
                empresa=empresa_ativa
            ).select_related('usuario', 'empresa').order_by('-data_exportacao')
            
            # 3. Aplicar filtros
            exports_queryset = self._aplicar_filtros(request, exports_queryset)
            
            # 4. Paginação
            paginator = Paginator(exports_queryset, self.paginate_by)
            page_number = request.GET.get('page', 1)
            page_obj = paginator.get_page(page_number)
            
            # 5. Estatísticas para o dashboard
            stats = self._calcular_estatisticas(empresa_ativa)
            
            # 6. Preparar contexto
            context = {
                'page_obj': page_obj,
                'exports': page_obj.object_list,
                'stats': stats,
                'filtros_ativos': self._obter_filtros_ativos(request),
                'total_exports': paginator.count,
                'empresa': empresa_ativa,
            }
            
            logger.info(
                f"Histórico SAF-T consultado por {request.user.username} - "
                f"Empresa: {empresa_ativa.nome} - Total: {paginator.count} registros"
            )
            
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Erro ao carregar histórico SAF-T: {e}")
            messages.error(request, f"Erro ao carregar histórico: {e}")
            return render(request, self.template_name, {'error': str(e)})
    
    def _aplicar_filtros(self, request, queryset):
        """Aplica filtros baseados nos parâmetros GET."""
        
        # Filtro por período
        periodo = request.GET.get('periodo')
        if periodo:
            try:
                dias = int(periodo)
                data_limite = timezone.now() - timedelta(days=dias)
                queryset = queryset.filter(data_exportacao__gte=data_limite)
            except ValueError:
                pass
        
        # Filtro por status
        status = request.GET.get('status')
        if status in ['sucesso', 'erro']:
            sucesso = status == 'sucesso'
            queryset = queryset.filter(sucesso=sucesso)
        
        # Filtro por data específica
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        
        if data_inicio:
            try:
                data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                queryset = queryset.filter(data_exportacao__date__gte=data_inicio_dt)
            except ValueError:
                pass
        
        if data_fim:
            try:
                data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d').date()
                queryset = queryset.filter(data_exportacao__date__lte=data_fim_dt)
            except ValueError:
                pass
        
        # Filtro por utilizador (apenas para admins)
        if request.user.has_perm('saft.view_all_exports'):
            usuario = request.GET.get('usuario')
            if usuario:
                queryset = queryset.filter(usuario__username__icontains=usuario)
        
        return queryset
    
    def _calcular_estatisticas(self, empresa: Empresa) -> Dict:
        """Calcula estatísticas básicas para o dashboard."""
        
        try:
            total_exports = SAFTExportService.objects.filter(empresa=empresa).count()
            exports_sucesso = SAFTExportService.objects.filter(empresa=empresa, sucesso=True).count()
            exports_erro = total_exports - exports_sucesso
            
            # Últimos 30 dias
            data_limite = timezone.now() - timedelta(days=30)
            exports_recentes = SAFTExportService.objects.filter(
                empresa=empresa,
                data_exportacao__gte=data_limite
            ).count()
            
            # Tamanho total aproximado (se disponível)
            total_size = SAFTExportService.objects.filter(
                empresa=empresa,
                sucesso=True
            ).aggregate(
                total=models.Sum('tamanho_arquivo')
            )['total'] or 0
            
            return {
                'total_exports': total_exports,
                'exports_sucesso': exports_sucesso,
                'exports_erro': exports_erro,
                'exports_recentes': exports_recentes,
                'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
                'taxa_sucesso': round((exports_sucesso / total_exports) * 100, 1) if total_exports > 0 else 0
            }
            
        except Exception as e:
            logger.warning(f"Erro ao calcular estatísticas: {e}")
            return {
                'total_exports': 0,
                'exports_sucesso': 0,
                'exports_erro': 0,
                'exports_recentes': 0,
                'total_size_mb': 0,
                'taxa_sucesso': 0
            }
    
    def _obter_filtros_ativos(self, request) -> Dict:
        """Retorna dicionário com filtros atualmente ativos."""
        return {
            'periodo': request.GET.get('periodo', ''),
            'status': request.GET.get('status', ''),
            'data_inicio': request.GET.get('data_inicio', ''),
            'data_fim': request.GET.get('data_fim', ''),
            'usuario': request.GET.get('usuario', ''),
        }


class SaftDownloadView(LoginRequiredMixin, PermissaoAcaoMixin, PermissionRequiredMixin, View):
    acao_requerida = 'baixar_saft'
    """
    View para download de arquivos SAF-T do histórico.
    """
    
    permission_required = 'saft.download_saftfile'
    
    def get(self, request, export_id):
        """Serve arquivo SAF-T para download."""
        
        try:
            # Buscar registro de exportação
            export_log = get_object_or_404(
                SAFTExportService,
                id=export_id,
                empresa=request.user.empresa,
                sucesso=True
            )
            
            # Verificar se arquivo existe
            if not export_log.caminho_arquivo or not default_storage.exists(export_log.caminho_arquivo):
                raise Http404("Arquivo não encontrado")
            
            # Ler arquivo
            with default_storage.open(export_log.caminho_arquivo, 'rb') as f:
                xml_content = f.read()
            
            # Preparar resposta
            filename = f"{export_log.empresa.nif}_{export_log.data_inicio.strftime('%Y%m%d')}_{export_log.data_fim.strftime('%Y%m%d')}.xml"
            
            response = HttpResponse(xml_content, content_type='application/xml')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Log do download
            logger.info(
                f"Download SAF-T: {filename} por {request.user.username} - "
                f"Export ID: {export_id}"
            )
            
            # Atualizar contador de downloads
            export_log.downloads += 1
            export_log.save(update_fields=['downloads'])
            
            return response
            
        except Exception as e:
            logger.error(f"Erro no download SAF-T {export_id}: {e}")
            messages.error(request, f"Erro ao baixar arquivo: {e}")
            return redirect('saft:historico')


class SaftValidarView(LoginRequiredMixin, PermissaoAcaoMixin, PermissionRequiredMixin, View):
    acao_requerida = 'validar_saft'
    """
    View para validação de arquivos SAF-T XML.
    Verifica conformidade com schema SAF-T AO v1.01.
    """
    
    template_name = 'saft/saft_validar.html'
    permission_required = 'saft.validate_saftfile'
    max_file_size = 50 * 1024 * 1024  # 50MB
    
    def get(self, request):
        """Renderiza formulário de validação."""
        
        context = {
            'max_file_size_mb': self.max_file_size // (1024 * 1024),
            'supported_formats': ['XML'],
            'saft_version': 'SAF-T AO v1.01',
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Processa upload e validação do arquivo XML."""
        
        try:
            # 1. Validar upload
            if 'saft_file' not in request.FILES:
                return JsonResponse({
                    'success': False,
                    'error': 'Nenhum arquivo foi enviado.'
                })
            
            uploaded_file = request.FILES['saft_file']
            
            # 2. Validações básicas
            validation_result = self._validar_arquivo_basico(uploaded_file)
            if not validation_result['valid']:
                return JsonResponse({
                    'success': False,
                    'error': validation_result['error']
                })
            
            # 3. Ler e validar conteúdo XML
            try:
                xml_content = uploaded_file.read().decode('utf-8')
                validation_result = self._validar_xml_saft(xml_content)
                
            except UnicodeDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Arquivo deve estar codificado em UTF-8.'
                })
            
            # 4. Log da validação
            logger.info(
                f"Validação SAF-T por {request.user.username} - "
                f"Arquivo: {uploaded_file.name} - "
                f"Resultado: {'Válido' if validation_result['valid'] else 'Inválido'}"
            )
            
            # 5. Salvar histórico de validação (opcional)
            self._salvar_historico_validacao(
                request.user,
                uploaded_file.name,
                validation_result
            )
            
            return JsonResponse(validation_result)
            
        except Exception as e:
            logger.error(f"Erro na validação SAF-T: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Erro interno na validação: {str(e)}'
            })
    
    def _validar_arquivo_basico(self, uploaded_file) -> Dict:
        """Validações básicas do arquivo (tamanho, extensão, etc.)."""
        
        # Validar tamanho
        if uploaded_file.size > self.max_file_size:
            return {
                'valid': False,
                'error': f'Arquivo muito grande. Máximo permitido: {self.max_file_size // (1024 * 1024)}MB'
            }
        
        # Validar extensão
        if not uploaded_file.name.lower().endswith('.xml'):
            return {
                'valid': False,
                'error': 'Apenas arquivos XML são permitidos.'
            }
        
        # Validar se não está vazio
        if uploaded_file.size == 0:
            return {
                'valid': False,
                'error': 'Arquivo está vazio.'
            }
        
        return {'valid': True}
    
    def _validar_xml_saft(self, xml_content: str) -> Dict:
        """Validação específica do XML SAF-T."""
        
        errors = []
        warnings = []
        
        try:
            # 1. Verificar se é XML válido
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                return {
                    'success': False,
                    'valid': False,
                    'error': f'XML malformado: {str(e)}',
                    'errors': [f'Erro de parsing XML: {str(e)}']
                }
            
            # 2. Verificar namespace SAF-T
            expected_namespace = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"
            if root.tag != f"{{{expected_namespace}}}AuditFile":
                errors.append(f"Namespace inválido. Esperado: {expected_namespace}")
            
            # 3. Validar estrutura básica SAF-T
            required_sections = ['Header', 'MasterFiles']
            for section in required_sections:
                if root.find(f'.//{{{expected_namespace}}}{section}') is None:
                    errors.append(f"Seção obrigatória ausente: {section}")
            
            # 4. Validar Header
            header_errors = self._validar_header_saft(root, expected_namespace)
            errors.extend(header_errors)
            
            # 5. Validar MasterFiles
            masterfiles_errors = self._validar_masterfiles_saft(root, expected_namespace)
            errors.extend(masterfiles_errors)
            
            # 6. Validações específicas de Angola
            angola_errors = self._validar_especificidades_angola(root, expected_namespace)
            errors.extend(angola_errors)
            
            # 7. Determinar se é válido
            is_valid = len(errors) == 0
            
            # 8. Preparar resultado
            result = {
                'success': True,
                'valid': is_valid,
                'title': 'Arquivo SAF-T Válido' if is_valid else 'Arquivo SAF-T Inválido',
                'message': self._gerar_mensagem_resultado(is_valid, len(errors), len(warnings)),
                'errors': errors,
                'warnings': warnings,
                'details': {
                    'total_errors': len(errors),
                    'total_warnings': len(warnings),
                    'file_size': len(xml_content),
                    'validation_date': timezone.now().isoformat()
                }
            }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'valid': False,
                'error': f'Erro na validação: {str(e)}',
                'errors': [f'Erro interno: {str(e)}']
            }
    
    def _validar_header_saft(self, root: ET.Element, namespace: str) -> List[str]:
        """Valida seção Header do SAF-T."""
        
        errors = []
        header = root.find(f'.//{{{namespace}}}Header')
        
        if header is None:
            return ['Header ausente']
        
        # Campos obrigatórios no Header
        required_fields = [
            'AuditFileVersion',
            'CompanyID',
            'TaxRegistrationNumber',
            'TaxAccountingBasis',
            'CompanyName',
            'FiscalYear',
            'StartDate',
            'EndDate',
            'CurrencyCode',
            'DateCreated',
            'TimeCreated',
            'ProductID',
            'ProductVersion'
        ]
        
        for field in required_fields:
            element = header.find(f'.//{{{namespace}}}{field}')
            if element is None or not element.text:
                errors.append(f'Campo obrigatório ausente no Header: {field}')
        
        # Validações específicas
        version = header.find(f'.//{{{namespace}}}AuditFileVersion')
        if version is not None and version.text != '1.01_01':
            errors.append(f'Versão SAF-T inválida: {version.text}. Esperado: 1.01_01')
        
        currency = header.find(f'.//{{{namespace}}}CurrencyCode')
        if currency is not None and currency.text != 'AOA':
            errors.append(f'Moeda inválida: {currency.text}. Esperado: AOA (Kwanza Angolano)')
        
        return errors
    
    def _validar_masterfiles_saft(self, root: ET.Element, namespace: str) -> List[str]:
        """Valida seção MasterFiles do SAF-T."""
        
        errors = []
        masterfiles = root.find(f'.//{{{namespace}}}MasterFiles')
        
        if masterfiles is None:
            return ['MasterFiles ausente']
        
        # Verificar presença de pelo menos uma tabela
        tables = ['GeneralLedgerAccounts', 'Customers', 'Suppliers', 'TaxTable', 'Products']
        has_any_table = False
        
        for table in tables:
            if masterfiles.find(f'.//{{{namespace}}}{table}') is not None:
                has_any_table = True
                break
        
        if not has_any_table:
            errors.append('MasterFiles deve conter pelo menos uma das tabelas: ' + ', '.join(tables))
        
        # Validar TaxTable se presente
        tax_table = masterfiles.find(f'.//{{{namespace}}}TaxTable')
        if tax_table is not None:
            tax_entries = tax_table.findall(f'.//{{{namespace}}}TaxTableEntry')
            if len(tax_entries) == 0:
                errors.append('TaxTable presente mas sem entradas')
        
        return errors
    
    def _validar_especificidades_angola(self, root: ET.Element, namespace: str) -> List[str]:
        """Validações específicas para Angola."""
        
        errors = []
        
        # Verificar se CompanyAddress contém Country = AO
        header = root.find(f'.//{{{namespace}}}Header')
        if header is not None:
            country = header.find(f'.//{{{namespace}}}Country')
            if country is not None and country.text != 'AO':
                errors.append(f'País deve ser AO (Angola). Encontrado: {country.text}')
        
        return errors
    
    def _gerar_mensagem_resultado(self, is_valid: bool, num_errors: int, num_warnings: int) -> str:
        """Gera mensagem descritiva do resultado da validação."""
        
        if is_valid:
            if num_warnings > 0:
                return f'Arquivo válido com {num_warnings} aviso(s). Pode ser usado para submissão.'
            else:
                return 'Arquivo totalmente válido. Pronto para submissão à AGT.'
        else:
            return f'Arquivo inválido com {num_errors} erro(s). Corrija os erros antes de submeter.'
    
    def _salvar_historico_validacao(self, usuario, filename: str, result: Dict) -> None:
        """Salva histórico de validação (opcional)."""
        
        try:
            # Implementar modelo SaftValidationLog se necessário
            # SaftValidationLog.objects.create(
            #     usuario=usuario,
            #     filename=filename,
            #     is_valid=result['valid'],
            #     errors_count=len(result.get('errors', [])),
            #     data_validacao=timezone.now()
            # )
            pass
            
        except Exception as e:
            logger.warning(f"Erro ao salvar histórico de validação: {e}")


class SaftVisualizarView(LoginRequiredMixin, PermissaoAcaoMixin, PermissionRequiredMixin, View):
    acao_requerida = 'visualizar_saft'
    """
    View para visualizar conteúdo de arquivos SAF-T em formato amigável.
    """
    
    template_name = 'saft/saft_visualizar.html'
    permission_required = 'saft.view_saftfile'
    
    def get(self, request, export_id):
        """Renderiza visualização do arquivo SAF-T."""
        
        try:
            # Buscar registro de exportação
            export_log = get_object_or_404(
                SAFTExportService,
                id=export_id,
                empresa=request.user.empresa,
                sucesso=True
            )
            
            # Verificar se arquivo existe
            if not export_log.caminho_arquivo or not default_storage.exists(export_log.caminho_arquivo):
                raise Http404("Arquivo não encontrado")
            
            # Ler e processar arquivo
            with default_storage.open(export_log.caminho_arquivo, 'rb') as f:
                xml_content = f.read().decode('utf-8')
            
            # Parsear XML para visualização
            parsed_data = self._processar_xml_para_visualizacao(xml_content)
            
            context = {
                'export_log': export_log,
                'parsed_data': parsed_data,
                'xml_preview': self._gerar_preview_xml(xml_content),
            }
            
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Erro ao visualizar SAF-T {export_id}: {e}")
            messages.error(request, f"Erro ao visualizar arquivo: {e}")
            return redirect('saft:historico')
    
    def _processar_xml_para_visualizacao(self, xml_content: str) -> Dict:
        """Processa XML para criar resumo visualizável."""
        
        try:
            root = ET.fromstring(xml_content)
            namespace = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"
            
            # Extrair informações do Header
            header = root.find(f'.//{{{namespace}}}Header')
            header_data = {}
            
            if header is not None:
                for child in header:
                    tag_name = child.tag.replace(f'{{{namespace}}}', '')
                    header_data[tag_name] = child.text
            
            # Contar elementos nas diferentes seções
            counts = {
                'customers': len(root.findall(f'.//{{{namespace}}}Customer')),
                'suppliers': len(root.findall(f'.//{{{namespace}}}Supplier')),
                'products': len(root.findall(f'.//{{{namespace}}}Product')),
                'invoices': len(root.findall(f'.//{{{namespace}}}Invoice')),
                'tax_entries': len(root.findall(f'.//{{{namespace}}}TaxTableEntry')),
            }
            
            return {
                'header': header_data,
                'counts': counts,
                'file_size': len(xml_content),
                'total_elements': len(root.findall('.//*')),
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar XML: {e}")
            return {'error': str(e)}
    
    def _gerar_preview_xml(self, xml_content: str, max_lines: int = 50) -> str:
        """Gera preview formatado do XML (primeiras linhas)."""
        
        try:
            # Formatar XML
            dom = minidom.parseString(xml_content)
            pretty_xml = dom.toprettyxml(indent="  ")
            
            # Pegar apenas as primeiras linhas
            lines = pretty_xml.split('\n')
            preview_lines = lines[:max_lines]
            
            if len(lines) > max_lines:
                preview_lines.append(f"... ({len(lines) - max_lines} linhas restantes)")
            
            return '\n'.join(preview_lines)
            
        except Exception:
            # Se falhar, retornar texto bruto limitado
            lines = xml_content.split('\n')[:max_lines]
            return '\n'.join(lines)



# Views auxiliares para AJAX
class SaftStatusAjaxView(LoginRequiredMixin, PermissaoAcaoMixin, View):
    acao_requerida = 'ver_status_saft'
    """View AJAX para verificar status de exportações em andamento."""
    
    def get(self, request):
        """Retorna status de exportações recentes."""
        
        try:
            empresa = request.user.empresa
            
            # Exportações recentes (últimas 24h)
            data_limite = timezone.now() - timedelta(hours=24)
            exports_recentes = SAFTExportService.objects.filter(
                empresa=empresa,
                data_exportacao__gte=data_limite
            ).order_by('-data_exportacao')[:5]
            
            exports_data = []
            for export in exports_recentes:
                exports_data.append({
                    'id': export.id,
                    'data_exportacao': export.data_exportacao.strftime('%d/%m/%Y %H:%M'),
                    'periodo': f"{export.data_inicio.strftime('%d/%m/%Y')} - {export.data_fim.strftime('%d/%m/%Y')}",
                    'sucesso': export.sucesso,
                    'erro_message': export.erro_message if not export.sucesso else None,
                    'tamanho_mb': round(export.tamanho_arquivo / (1024 * 1024), 2) if export.tamanho_arquivo else 0,
                })
            
            return JsonResponse({
                'success': True,
                'exports': exports_data,
                'timestamp': timezone.now().isoformat()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

