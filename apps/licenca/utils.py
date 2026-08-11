# apps/licenca/utils.py
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import Licenca, LogValidacaoLicenca
from datetime import date

User = get_user_model()

class LicenseValidator:
    """Classe para validação de licenças"""
    
    @staticmethod
    def validar_licenca(license_key, empresa=None, user=None, acao="validacao_geral", request=None):
        """
        Valida uma licença específica
        
        Args:
            license_key (str): Chave da licença
            empresa (Empresa, optional): Empresa para validar
            user (User, optional): Usuário que está fazendo a validação
            acao (str): Ação que triggered a validação
            request (HttpRequest, optional): Request para logging
        
        Returns:
            dict: Resultado da validação com sucesso/falha e detalhes
        """
        resultado = {
            'sucesso': False,
            'licenca': None,
            'motivo_falha': '',
            'detalhes': {}
        }
        
        try:
            # Busca a licença
            licenca = Licenca.objects.get(license_key=license_key)
            resultado['licenca'] = licenca
            
            # Validação 1: Licença ativa
            if not licenca.ativa:
                resultado['motivo_falha'] = 'Licença inativa'
                LicenseValidator._log_validacao(licenca, False, resultado['motivo_falha'], acao, user, request)
                return resultado
            
            # Validação 2: Empresa corresponde (se especificada)
            if empresa and licenca.empresa != empresa:
                resultado['motivo_falha'] = 'Licença não pertence à empresa especificada'
                LicenseValidator._log_validacao(licenca, False, resultado['motivo_falha'], acao, user, request)
                return resultado
            
            # Validação 3: Não expirada
            if licenca.esta_expirada:
                resultado['motivo_falha'] = f'Licença expirada em {licenca.data_expiracao}'
                LicenseValidator._log_validacao(licenca, False, resultado['motivo_falha'], acao, user, request)
                return resultado
            
            # Validação 4: Empresa ativa
            if not licenca.empresa.ativa:
                resultado['motivo_falha'] = 'Empresa inativa no sistema'
                LicenseValidator._log_validacao(licenca, False, resultado['motivo_falha'], acao, user, request)
                return resultado
            
            # Se chegou até aqui, licença é válida
            resultado['sucesso'] = True
            resultado['detalhes'] = {
                'empresa': licenca.empresa.nome,
                'tipo': licenca.tipo,
                'max_usuarios': licenca.max_usuarios,
                'dias_restantes': licenca.dias_para_expiracao,
                'status': licenca.status_licenca
            }
            
            # Log de sucesso
            LicenseValidator._log_validacao(licenca, True, '', acao, user, request)
            
        except Licenca.DoesNotExist:
            resultado['motivo_falha'] = 'Licença não encontrada'
            # Não faz log se licença não existe
        
        except Exception as e:
            resultado['motivo_falha'] = f'Erro interno: {str(e)}'
        
        return resultado
    
    @staticmethod
    def validar_empresa(empresa, acao="validacao_empresa", user=None, request=None):
        """
        Valida se uma empresa tem licenças válidas
        
        Args:
            empresa (Empresa): Empresa para validar
            acao (str): Ação que triggered a validação
            user (User, optional): Usuário fazendo a validação
            request (HttpRequest, optional): Request para logging
        
        Returns:
            dict: Resultado da validação
        """
        resultado = {
            'sucesso': False,
            'licencas_validas': [],
            'motivo_falha': '',
            'detalhes': {}
        }
        
        try:
            # Empresa ativa
            if not empresa.ativa:
                resultado['motivo_falha'] = 'Empresa inativa no sistema'
                return resultado
            
            # Busca licenças válidas
            licencas_ativas = empresa.licencas.filter(ativa=True)
            licencas_validas = []
            
            for licenca in licencas_ativas:
                if not licenca.esta_expirada:
                    licencas_validas.append(licenca)
            
            if not licencas_validas:
                resultado['motivo_falha'] = 'Nenhuma licença válida encontrada'
                return resultado
            
            # Sucesso
            resultado['sucesso'] = True
            resultado['licencas_validas'] = licencas_validas
            resultado['detalhes'] = {
                'total_licencas': len(licencas_validas),
                'max_usuarios_total': sum(l.max_usuarios for l in licencas_validas),
                }
            
            # Log para a primeira licença válida (representativo)
            if licencas_validas:
                LicenseValidator._log_validacao(
                    licencas_validas[0], True, '', acao, user, request
                )
        
        except Exception as e:
            resultado['motivo_falha'] = f'Erro interno: {str(e)}'
        
        return resultado
    
    @staticmethod
    def _log_validacao(licenca, sucesso, motivo_falha, acao, user, request):
        """Registra log de validação"""
        try:
            ip_origem = None
            user_agent = ''
            
            if request:
                # Obtém IP real considerando proxies
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_origem = x_forwarded_for.split(',')[0]
                else:
                    ip_origem = request.META.get('REMOTE_ADDR')
                
                user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            LogValidacaoLicenca.objects.create(
                licenca=licenca,
                sucesso=sucesso,
                motivo_falha=motivo_falha,
                acao=acao,
                usuario=user,
                ip_origem=ip_origem,
                user_agent=user_agent,
                detalhes={
                    'timestamp': str(date.today()),
                    'acao_detalhada': acao
                }
            )
        except Exception:
            # Falha no log não deve quebrar a validação
            pass

def validar_licenca_empresa(empresa, raise_exception=True):
    """
    Função utilitária para validar licença de uma empresa
    Pode ser usada em views, middleware, etc.
    
    Args:
        empresa (Empresa): Empresa para validar
        raise_exception (bool): Se deve levantar exceção em caso de falha
    
    Returns:
        bool: True se licença válida
    
    Raises:
        ValidationError: Se licença inválida e raise_exception=True
    """
    resultado = LicenseValidator.validar_empresa(empresa)
    
    if not resultado['sucesso']:
        if raise_exception:
            raise ValidationError(f"Licença inválida: {resultado['motivo_falha']}")
        return False
    
    return True

def obter_info_licenca(license_key):
    """
    Obtém informações de uma licença sem fazer log de validação
    
    Args:
        license_key (str): Chave da licença
    
    Returns:
        dict: Informações da licença ou None se não encontrada
    """
    try:
        licenca = Licenca.objects.get(license_key=license_key)
        return {
            'license_key': licenca.license_key,
            'empresa': licenca.empresa.nome,
            'tipo': licenca.get_tipo_display(),
            'ativa': licenca.ativa,
            'status': licenca.status_licenca,
            'data_expiracao': licenca.data_expiracao,
            'max_usuarios': licenca.max_usuarios,
            'esta_expirada': licenca.esta_expirada,
            'dias_restantes': licenca.dias_para_expiracao
        }
    except Licenca.DoesNotExist:
        return None

# Decorator para views que precisam de licença válida
def licenca_requerida(view_func):
    """
    Decorator para views que requerem licença válida
    Assume que request.user.empresa existe
    """
    def wrapper(request, *args, **kwargs):
        try:
            if hasattr(request.user, 'empresa'):
                if not validar_licenca_empresa(request.user.empresa, raise_exception=False):
                    from django.http import JsonResponse
                    return JsonResponse({
                        'error': 'Licença inválida ou expirada',
                        'code': 'LICENSE_INVALID'
                    }, status=403)
            
            return view_func(request, *args, **kwargs)
        
        except Exception as e:
            from django.http import JsonResponse
            return JsonResponse({
                'error': 'Erro na validação de licença',
                'code': 'LICENSE_ERROR'
            }, status=500)
    
    return wrapper