# apps/core_tenants/permissions.py
import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger('core_tenants.permissions')


class EmpresaPermission(permissions.BasePermission):
    """
    Garante que o utilizador só acede a dados dentro de um schema de tenant
    válido (não 'public'). No django_tenants o isolamento é FÍSICO (schema
    PostgreSQL) — por isso a verificação é pelo schema activo, não por um
    campo 'empresa_ativa' inexistente no model Usuario.
    """

    message = "Você não tem permissão para acessar dados desta empresa."

    def has_permission(self, request, view):
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
        if not self.has_permission(request, view):
            return False

        schema_atual = getattr(connection, 'schema_name', 'public')

        if schema_atual == 'public':
            logger.warning(
                f"Tentativa negada: Acesso ao objeto {obj.__class__.__name__} (ID: {getattr(obj, 'pk', 'N/A')}) no Schema Público.",
                extra={'user_id': getattr(request.user, 'id', 'N/A'), 'objeto_type': obj.__class__.__name__}
            )
            return False

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


class EmpresaAdminPermission(permissions.BasePermission):
    """
    Permissão para administradores de empresa. Acesso completo a
    utilizadores cujo Funcionario tem um Cargo com cargo.selecionar_todos=True.
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
    """Permissão específica para operações fiscais (depende de EmpresaPermission)."""

    message = "Você não tem permissão para acessar recursos fiscais."

    def has_permission(self, request, view):
        if not EmpresaPermission().has_permission(request, view):
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
            extra={'user_id': user.id, 'view': view.__class__.__name__}
        )

        return False

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False
        return EmpresaPermission().has_object_permission(request, view, obj)


class ContabilidadePermission(permissions.BasePermission):
    """Permissão específica para operações contábeis (depende de EmpresaPermission)."""

    message = "Você não tem permissão para acessar recursos contábeis."

    def has_permission(self, request, view):
        if not EmpresaPermission().has_permission(request, view):
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


def empresa_required(view_func):
    """Decorador que aplica EmpresaPermission a views baseadas em função."""
    def wrapper(request, *args, **kwargs):
        permission = EmpresaPermission()
        if not permission.has_permission(request, None):
            raise PermissionDenied(permission.message)
        return view_func(request, *args, **kwargs)
    return wrapper


def fiscal_required(view_func):
    """Decorador que aplica FiscalPermission a views baseadas em função."""
    def wrapper(request, *args, **kwargs):
        permission = FiscalPermission()
        if not permission.has_permission(request, None):
            raise PermissionDenied(permission.message)
        return view_func(request, *args, **kwargs)
    return wrapper