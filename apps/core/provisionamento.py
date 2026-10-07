# apps/core/provisionamento.py
from datetime import date

from django.db import models as dj_models, transaction
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, schema_context

from apps.funcionarios.models import Cargo, Funcionario


def campos_permissao():
    """Lê os campos pode_* pelos metadados (não toca na BD)."""
    return [
        f.name for f in Cargo._meta.get_fields()
        if isinstance(f, dj_models.BooleanField) and f.name.startswith("pode_")
    ]


def _cargo_administrador():
    """Chamar SEMPRE dentro de schema_context."""
    from apps.funcionarios.cargos_padrao import garantir_cargo_por_codigo
    cargo, _ = garantir_cargo_por_codigo("ADMIN")
    return cargo


def _departamento_administracao():
    """Chamar SEMPRE dentro de schema_context."""
    from apps.funcionarios.departamentos_padrao import garantir_departamento_por_codigo
    departamento, _, _ = garantir_departamento_por_codigo("DEP-ADM")
    return departamento


def vincular_usuario_ao_cargo(usuario, cargo_id=None):
    """
    Garante Funcionario + Cargo para o usuário, dentro do schema da empresa.
    Se cargo_id for None, usa (ou cria) o cargo 'Administrador'.
    """
    empresa = usuario.empresa
    if not empresa or empresa.schema_name == get_public_schema_name():
        raise ValueError("Usuário sem empresa (tenant) válida.")

    with schema_context(empresa.schema_name):
        with transaction.atomic():
            cargo = Cargo.objects.get(pk=cargo_id) if cargo_id else _cargo_administrador()

            funcionario = Funcionario.objects.filter(usuario_id=usuario.pk).first()
            if funcionario:
                # update() evita o save() (e o gerar_matricula); updated_at é manual
                Funcionario.objects.filter(pk=funcionario.pk).update(
                    cargo=cargo, updated_at=timezone.now()
                )
                funcionario.cargo = cargo
                return funcionario

            funcionario = Funcionario(
                usuario=usuario,
                cargo=cargo,
                departamento=_departamento_administracao(),
                nome_completo=usuario.get_full_name() or usuario.username,
                # Placeholders: o RH completa depois dentro do tenant.
                # Funciona com pk inteiro ou UUID; 14 caracteres, único.
                bi="PEND" + str(usuario.pk).replace("-", "")[-10:].zfill(10),
                data_nascimento=date(1990, 1, 1),
                sexo="O",
                endereco="A preencher",
                numero="S/N",
                bairro="A preencher",
                cidade="A preencher",
                postal="0000-000",
                data_admissao=date.today(),
                salario_atual=0,
                email_corporativo=usuario.email or "",
            )
            funcionario.save(sincronizar_grupo=False)
            return funcionario