import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger('core.permissions')


class EmpresaPermission(permissions.BasePermission):
    """
    Permissão personalizada que garante que usuários só acessem dados da sua empresa ativa.
    Aplicável a ViewSets e Views que manipulam dados específicos de empresa.

    No ecossistema django_tenants, o isolamento entre empresas é FÍSICO (por Schema do
    PostgreSQL). Por isso a verificação é feita pelo schema ativo na conexão/request,
    não por um campo 'empresa_ativa' no model de Usuario (que não existe).
    """

    message = "Você não tem permissão para acessar dados desta empresa."

    def has_permission(self, request, view):
        """
        Verifica se o usuário está autenticado e se a requisição está a rodar
        dentro de um schema de tenant válido (não 'public').
        """
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = getattr(request, 'tenant', None) or getattr(connection, 'tenant', None)
        schema_atual = getattr(tenant, 'schema_name', 'public')

        if not tenant or schema_atual == 'public':
            logger.warning(
                f"Usuário {request.user.id} tentou acessar sem estar num tenant ativo",
                extra={'user_id': request.user.id, 'view': view.__class__.__name__, 'schema': schema_atual}
            )
            return False

        return True

    def has_object_permission(self, request, view, obj):
        """
        Verifica se o utilizador tem permissão de nível de objeto.

        Se o objeto foi carregado do banco, ele JÁ PERTENCE nativamente ao schema
        da empresa ativa — o isolamento físico do django_tenants garante isso.
        """
        if not self.has_permission(request, view):
            return False

        schema_atual = getattr(connection, 'schema_name', 'public')

        if schema_atual == 'public':
            logger.warning(
                f"Tentativa negada: Acesso ao objeto {obj.__class__.__name__} (ID: {getattr(obj, 'pk', 'N/A')}) no Schema Público.",
                extra={
                    'user_id': getattr(request.user, 'id', 'N/A'),
                    'objeto_type': obj.__class__.__name__
                }
            )
            return False

        # Regras de Nível de Objeto (Exemplo: Dono do registo / Usuário responsável)
        if hasattr(view, 'exigir_dono') and view.exigir_dono:
            usuario_dono_id = getattr(obj, 'usuario_id', None) or getattr(obj, 'usuario_responsavel_id', None)

            if usuario_dono_id and usuario_dono_id != request.user.id and not request.user.is_superuser:
                logger.warning(
                    f"Acesso negado: Utilizador {request.user.id} tentou aceder a registo privado do utilizador {usuario_dono_id}",
                    extra={
                        'user_id': request.user.id,
                        'objeto_type': obj.__class__.__name__,
                        'objeto_id': getattr(obj, 'pk', 'N/A')
                    }
                )
                return False

        return True


class SuperUserPermission(permissions.BasePermission):
    """
    Permissão que permite acesso apenas a superusuários.
    """

    message = "Apenas superusuários podem acessar este recurso."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_superuser

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class ReadOnlyPermission(permissions.BasePermission):
    """
    Permissão que permite apenas leitura (GET, HEAD, OPTIONS).
    """

    message = "Você tem permissão apenas para leitura deste recurso."

    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class EmpresaAdminPermission(permissions.BasePermission):
    """
    Permissão para administradores de empresa.
    Permite acesso completo a usuários cujo Funcionario tem um Cargo com
    privilégios administrativos totais (cargo.selecionar_todos = True).

    NOTA: 'selecionar_todos' é o campo usado no script gerenciar_sotarq.py para
    marcar o "Administrador Supremo". Confirma se é este o campo correto no teu
    model Cargo — se usares outro nome/lógica para marcar admins, ajusta aqui.
    """

    message = "Apenas administradores da empresa podem acessar este recurso."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        funcionario = getattr(request.user, 'funcionario', None)
        if not funcionario:
            return False

        try:
            cargo = getattr(funcionario, 'cargo', None)
            return bool(getattr(cargo, 'selecionar_todos', False))
        except (ObjectDoesNotExist, AttributeError):
            logger.warning(
                f"Não foi possível verificar status de admin para usuário {request.user.id}",
                extra={'user_id': request.user.id}
            )
            return False

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)


class FiscalPermission(permissions.BasePermission):
    """
    Permissão específica para operações fiscais.
    Permite acesso a usuários com permissões fiscais na empresa: superusuário,
    grupos específicos, permissões Django explícitas, ou Funcionario cujo Cargo
    tem 'pode_exportar_saft' (proxy para acesso fiscal — confirma se é este o
    campo correto no teu model Cargo).
    """

    message = "Você não tem permissão para acessar recursos fiscais."

    def has_permission(self, request, view):
        empresa_permission = EmpresaPermission()
        if not empresa_permission.has_permission(request, view):
            return False

        user = request.user

        if user.is_superuser:
            return True

        if user.groups.filter(name__in=['Fiscal', 'Contabilidade', 'Administrador']).exists():
            return True

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

        funcionario = getattr(user, 'funcionario', None)
        if funcionario:
            cargo = getattr(funcionario, 'cargo', None)
            if getattr(cargo, 'pode_exportar_saft', False):
                return True

        logger.warning(
            f"Usuário {user.id} sem permissão fiscal tentou acessar recurso",
            extra={
                'user_id': user.id,
                'view': view.__class__.__name__
            }
        )

        return False

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False

        empresa_permission = EmpresaPermission()
        return empresa_permission.has_object_permission(request, view, obj)


class ContabilidadePermission(permissions.BasePermission):
    """
    Permissão específica para operações contábeis.
    Similar à FiscalPermission, mas para funcionalidades contábeis.
    """

    message = "Você não tem permissão para acessar recursos contábeis."

    def has_permission(self, request, view):
        empresa_permission = EmpresaPermission()
        if not empresa_permission.has_permission(request, view):
            return False

        user = request.user

        if user.is_superuser:
            return True

        if user.groups.filter(name__in=['Contabilidade', 'Financeiro', 'Administrador']).exists():
            return True

        contabil_permissions = [
            'financeiro.add_configuracaoimposto',
            'financeiro.change_configuracaoimposto',
            'financeiro.view_configuracaoimposto',
            'financeiro.add_impostotributo',
            'financeiro.change_impostotributo',
            'financeiro.view_impostotributo',
            'financeiro.add_movimentocaixa',
            'financeiro.change_movimentocaixa',
            'financeiro.view_movimentocaixa',
            'financeiro.add_conciliacaobancaria',
            'financeiro.change_conciliacaobancaria',
            'financeiro.view_conciliacaobancaria',
            'financeiro.add_fluxocaixa',
            'financeiro.change_fluxocaixa',
            'financeiro.view_fluxocaixa',
        ]

        if user.has_perms(contabil_permissions):
            return True

        funcionario = getattr(user, 'funcionario', None)
        if funcionario:
            cargo = getattr(funcionario, 'cargo', None)
            if getattr(cargo, 'pode_acessar_financeiro', False):
                return True

        return False


# Decorador de conveniência para views baseadas em função
def empresa_required(view_func):
    """
    Decorador que aplica EmpresaPermission a views baseadas em função.
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
        permissions_config = getattr(view, 'multiple_permissions', {})

        and_permissions = permissions_config.get('AND', [])
        if and_permissions:
            for permission_class in and_permissions:
                permission = permission_class()
                if not permission.has_permission(request, view):
                    return False

        or_permissions = permissions_config.get('OR', [])
        if or_permissions:
            for permission_class in or_permissions:
                permission = permission_class()
                if permission.has_permission(request, view):
                    return True
            return False

        return True

    def has_object_permission(self, request, view, obj):
        permissions_config = getattr(view, 'multiple_permissions', {})

        and_permissions = permissions_config.get('AND', [])
        if and_permissions:
            for permission_class in and_permissions:
                permission = permission_class()
                if hasattr(permission, 'has_object_permission'):
                    if not permission.has_object_permission(request, view, obj):
                        return False

        or_permissions = permissions_config.get('OR', [])
        if or_permissions:
            for permission_class in or_permissions:
                permission = permission_class()
                if hasattr(permission, 'has_object_permission'):
                    if permission.has_object_permission(request, view, obj):
                        return True
            return False

        return True