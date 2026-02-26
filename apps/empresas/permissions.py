from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from django.core.exceptions import ObjectDoesNotExist
import logging

logger = logging.getLogger('core.permissions')

class EmpresaPermission(permissions.BasePermission):
    """
    Permissão personalizada que garante que usuários só acessem dados da sua empresa ativa.
    Aplicável a ViewSets e Views que manipulam dados específicos de empresa.
    """
    
    message = "Você não tem permissão para acessar dados desta empresa."
    
    def has_permission(self, request, view):
        """
        Verifica se o usuário tem permissão geral para acessar a view.
        Garante que o usuário está autenticado e tem uma empresa ativa.
        """
        # Usuário deve estar autenticado
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Usuário deve ter uma empresa ativa
        if not hasattr(request.user, 'empresa_ativa') or not request.user.empresa_ativa:
            logger.warning(
                f"Usuário {request.user.id} tentou acessar sem empresa ativa",
                extra={'user_id': request.user.id, 'view': view.__class__.__name__}
            )
            return False
        
        return True
    
    def has_object_permission(self, request, view, obj):
        """
        Verifica se o usuário tem permissão para acessar um objeto específico.
        Garante que o objeto pertence à empresa ativa do usuário.
        """
        # Primeiro, verificar permissão geral
        if not self.has_permission(request, view):
            return False
        
        # Obter empresa ativa do usuário
        empresa_ativa = request.user.empresa_ativa
        
        # Verificar se o objeto possui campo 'empresa'
        if hasattr(obj, 'empresa'):
            objeto_empresa = obj.empresa
        elif hasattr(obj, 'empresa_id'):
            objeto_empresa_id = obj.empresa_id
            # Comparar IDs diretamente para evitar queries desnecessárias
            if objeto_empresa_id != empresa_ativa.id:
                logger.warning(
                    f"Usuário {request.user.id} tentou acessar objeto de outra empresa",
                    extra={
                        'user_id': request.user.id,
                        'user_empresa_id': empresa_ativa.id,
                        'objeto_empresa_id': objeto_empresa_id,
                        'objeto_type': obj.__class__.__name__,
                        'objeto_id': getattr(obj, 'id', 'N/A')
                    }
                )
                return False
            return True
        else:
            # Se o objeto não tem empresa, permitir acesso (pode ser um modelo global)
            logger.debug(
                f"Objeto {obj.__class__.__name__} não possui campo empresa, permitindo acesso",
                extra={'objeto_type': obj.__class__.__name__, 'user_id': request.user.id}
            )
            return True
        
        # Verificar se o objeto pertence à empresa ativa
        if objeto_empresa.id != empresa_ativa.id:
            logger.warning(
                f"Usuário {request.user.id} tentou acessar objeto de outra empresa",
                extra={
                    'user_id': request.user.id,
                    'user_empresa_id': empresa_ativa.id,
                    'objeto_empresa_id': objeto_empresa.id,
                    'objeto_type': obj.__class__.__name__,
                    'objeto_id': getattr(obj, 'id', 'N/A')
                }
            )
            return False
        
        return True


class SuperUserPermission(permissions.BasePermission):
    """
    Permissão que permite acesso apenas a superusuários.
    Útil para views administrativas que devem ser acessíveis apenas por administradores do sistema.
    """
    
    message = "Apenas superusuários podem acessar este recurso."
    
    def has_permission(self, request, view):
        """Verifica se o usuário é superusuário"""
        return request.user and request.user.is_authenticated and request.user.is_superuser
    
    def has_object_permission(self, request, view, obj):
        """Verifica se o usuário é superusuário para objetos específicos"""
        return self.has_permission(request, view)


class ReadOnlyPermission(permissions.BasePermission):
    """
    Permissão que permite apenas leitura (GET, HEAD, OPTIONS).
    Útil para APIs que devem ser somente leitura para determinados usuários.
    """
    
    message = "Você tem permissão apenas para leitura deste recurso."
    
    def has_permission(self, request, view):
        """Permite apenas métodos seguros (leitura)"""
        return request.method in permissions.SAFE_METHODS


class EmpresaAdminPermission(permissions.BasePermission):
    """
    Permissão para administradores de empresa.
    Permite acesso completo a usuários que são administradores da empresa ativa.
    """
    
    message = "Apenas administradores da empresa podem acessar este recurso."
    
    def has_permission(self, request, view):
        """
        Verifica se o usuário é administrador da empresa ativa.
        """
        # Usuário deve estar autenticado
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Usuário deve ter uma empresa ativa
        if not hasattr(request.user, 'empresa_ativa') or not request.user.empresa_ativa:
            return False
        
        # Verificar se o usuário é administrador da empresa
        # Assumindo que existe um campo is_admin no modelo de usuário ou relacionamento
        if hasattr(request.user, 'is_empresa_admin'):
            return request.user.is_empresa_admin
        
        # Alternativa: verificar através de relacionamento com empresa
        try:
            # Assumindo que existe um relacionamento funcionarios na empresa
            funcionario = request.user.empresa_ativa.funcionarios.filter(
                usuario=request.user,
                is_admin=True
            ).first()
            return funcionario is not None
        except (ObjectDoesNotExist, AttributeError):
            logger.warning(
                f"Não foi possível verificar status de admin para usuário {request.user.id}",
                extra={'user_id': request.user.id}
            )
            return False
    
    def has_object_permission(self, request, view, obj):
        """Verifica permissão em nível de objeto"""
        return self.has_permission(request, view)


class FiscalPermission(permissions.BasePermission):
    """
    Permissão específica para operações fiscais.
    Permite acesso a usuários com permissões fiscais na empresa.
    """
    
    message = "Você não tem permissão para acessar recursos fiscais."
    
    def has_permission(self, request, view):
        """
        Verifica se o usuário tem permissões fiscais.
        """
        # Primeiro, verificar permissão básica de empresa
        empresa_permission = EmpresaPermission()
        if not empresa_permission.has_permission(request, view):
            return False
        
        # Verificar permissões específicas fiscais
        user = request.user
        
        # Se for superusuário, permitir
        if user.is_superuser:
            return True
        
        # Verificar se o usuário tem permissão fiscal específica
        # Isso pode ser implementado através de grupos, permissões específicas, etc.
        
        # Exemplo usando grupos do Django
        if user.groups.filter(name__in=['Fiscal', 'Contabilidade', 'Administrador']).exists():
            return True
        
        # Exemplo usando permissões específicas
        fiscal_permissions = [
            'fiscal.add_taxaivaagt',
            'fiscal.change_taxaivaagt',
            'fiscal.view_taxaivaagt',
            'fiscal.add_retencaofonte',
            'fiscal.change_retencaofonte',
            'fiscal.view_retencaofonte',
        ]
        
        if user.has_perms(fiscal_permissions):
            return True
        
        # Verificar através de relacionamento com empresa (se houver campo específico)
        try:
            funcionario = user.empresa_ativa.funcionarios.filter(
                usuario=user
            ).first()
            
            if funcionario and hasattr(funcionario, 'pode_acessar_fiscal'):
                return funcionario.pode_acessar_fiscal
                
        except (ObjectDoesNotExist, AttributeError):
            pass
        
        logger.warning(
            f"Usuário {user.id} sem permissão fiscal tentou acessar recurso",
            extra={
                'user_id': user.id,
                'empresa_id': user.empresa_ativa.id,
                'view': view.__class__.__name__
            }
        )
        
        return False
    
    def has_object_permission(self, request, view, obj):
        """Verifica permissão em nível de objeto"""
        # Primeiro verificar permissão geral
        if not self.has_permission(request, view):
            return False
        
        # Depois verificar se o objeto pertence à empresa (usando EmpresaPermission)
        empresa_permission = EmpresaPermission()
        return empresa_permission.has_object_permission(request, view, obj)


class ContabilidadePermission(permissions.BasePermission):
    """
    Permissão específica para operações contábeis.
    Similar à FiscalPermission, mas para funcionalidades contábeis.
    """
    
    message = "Você não tem permissão para acessar recursos contábeis."
    
    def has_permission(self, request, view):
        """Verifica se o usuário tem permissões contábeis"""
        # Verificar permissão básica de empresa
        empresa_permission = EmpresaPermission()
        if not empresa_permission.has_permission(request, view):
            return False
        
        user = request.user
        
        # Superusuário sempre pode
        if user.is_superuser:
            return True
        
        # Verificar grupos específicos
        if user.groups.filter(name__in=['Contabilidade', 'Financeiro', 'Administrador']).exists():
            return True
        
        # Verificar permissões específicas de contabilidade
        contabil_permissions = [
            
        ]
        
        if user.has_perms(contabil_permissions):
            return True
        
        return False


# Decorador de conveniência para views baseadas em função
def empresa_required(view_func):
    """
    Decorador que aplica EmpresaPermission a views baseadas em função.
    
    Uso:
    @empresa_required
    def minha_view(request):
        # Código da view
        pass
    """
    def wrapper(request, *args, **kwargs):
        permission = EmpresaPermission()
        if not permission.has_permission(request, None):
            raise PermissionDenied(permission.message)
        return view_func(request, *args, **kwargs)
    
    return wrapper


def fiscal_required(view_func):
    """
    Decorador que aplica FiscalPermission a views baseadas em função.
    """
    def wrapper(request, *args, **kwargs):
        permission = FiscalPermission()
        if not permission.has_permission(request, None):
            raise PermissionDenied(permission.message)
        return view_func(request, *args, **kwargs)
    
    return wrapper


# Classe de conveniência para combinar múltiplas permissões
class MultiplePermissions(permissions.BasePermission):
    """
    Permite combinar múltiplas permissões com operadores AND ou OR.
    
    Exemplo de uso:
    permission_classes = [MultiplePermissions]
    multiple_permissions = {
        'AND': [EmpresaPermission, FiscalPermission],
        'OR': [SuperUserPermission]
    }
    """
    
    def has_permission(self, request, view):
        """
        Verifica permissões combinadas baseadas na configuração da view.
        """
        # Obter configuração de permissões da view
        permissions_config = getattr(view, 'multiple_permissions', {})
        
        # Verificar permissões AND (todas devem passar)
        and_permissions = permissions_config.get('AND', [])
        if and_permissions:
            for permission_class in and_permissions:
                permission = permission_class()
                if not permission.has_permission(request, view):
                    return False
        
        # Verificar permissões OR (pelo menos uma deve passar)
        or_permissions = permissions_config.get('OR', [])
        if or_permissions:
            for permission_class in or_permissions:
                permission = permission_class()
                if permission.has_permission(request, view):
                    return True
            # Se nenhuma permissão OR passou, negar acesso
            return False
        
        # Se chegou até aqui, todas as permissões AND passaram
        return True
    
    def has_object_permission(self, request, view, obj):
        """Verifica permissões de objeto combinadas"""
        permissions_config = getattr(view, 'multiple_permissions', {})
        
        # Verificar permissões AND
        and_permissions = permissions_config.get('AND', [])
        if and_permissions:
            for permission_class in and_permissions:
                permission = permission_class()
                if hasattr(permission, 'has_object_permission'):
                    if not permission.has_object_permission(request, view, obj):
                        return False
        
        # Verificar permissões OR
        or_permissions = permissions_config.get('OR', [])
        if or_permissions:
            for permission_class in or_permissions:
                permission = permission_class()
                if hasattr(permission, 'has_object_permission'):
                    if permission.has_object_permission(request, view, obj):
                        return True
            return False
        
        return True
