#!/usr/bin/env python
"""Cria (ou confirma) o cliente padrão Consumidor Final num tenant Django.

Uso, a partir da raiz do projecto:
    python scripts/criar_consumidor_final.py mundoemaquinas
    python scripts/criar_consumidor_final.py  # pede o schema

Por padrão, usa config.settings.production. Pode ser alterado com --settings.
O script é idempotente: identifica o registo por um marcador interno e não cria
um segundo Consumidor Final se for executado novamente.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MARCADOR = "[VISTOGEST:SISTEMA:CONSUMIDOR_FINAL]"
NIF_SENTINELA = "999999999"  # Convenção já reconhecida pelo PDF fiscal fornecido.
NOME_CONSUMIDOR = "Consumidor Final"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria o cliente padrão Consumidor Final no schema indicado."
    )
    parser.add_argument(
        "schema",
        nargs="?",
        help="Schema do tenant. Se omitido, será solicitado interactivamente.",
    )
    parser.add_argument(
        "--settings",
        dest="settings_module",
        default=os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.production"),
        help="Módulo Django settings (padrão: config.settings.production ou DJANGO_SETTINGS_MODULE).",
    )
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="Não pedir confirmação antes de criar/actualizar o registo.",
    )
    return parser.parse_args()


def validar_schema(schema: str, public_schema: str) -> str:
    schema = (schema or "").strip()
    if not schema:
        raise ValueError("O schema não pode estar vazio.")
    if schema == public_schema:
        raise ValueError("Por segurança, este script não cria o Consumidor Final no schema public.")
    if len(schema) > 63 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError(
            "Nome de schema inválido. Use até 63 caracteres: letras, números e underscore; "
            "o primeiro carácter deve ser letra ou underscore."
        )
    return schema


def codigo_cliente_disponivel(Cliente) -> str:
    """Gera CLI#### usando o maior código existente, não apenas o último ID."""
    codigos = Cliente.objects.filter(codigo_cliente__startswith="CLI").values_list(
        "codigo_cliente", flat=True
    )
    maior = 0
    for codigo in codigos:
        match = re.fullmatch(r"CLI(\d+)", codigo or "")
        if match:
            maior = max(maior, int(match.group(1)))

    numero = maior + 1
    while True:
        candidato = f"CLI{numero:04d}"
        if not Cliente.objects.filter(codigo_cliente=candidato).exists():
            return candidato
        numero += 1


def main() -> int:
    args = parse_args()
    schema = args.schema or input("Introduza o schema do tenant: ").strip()
    os.environ["DJANGO_SETTINGS_MODULE"] = args.settings_module

    try:
        import django
        django.setup()

        from django.db import connection, transaction, IntegrityError
        from django_tenants.utils import get_public_schema_name, schema_context
        from apps.empresas.models import Empresa
        from apps.clientes.models import Cliente

        schema = validar_schema(schema, get_public_schema_name())

        # Confirma no registo público que o schema pertence a um tenant existente.
        with schema_context(get_public_schema_name()):
            empresa_tenant = Empresa.objects.filter(schema_name=schema).first()
        if empresa_tenant is None:
            raise ValueError(
                f"Não foi encontrado um registo Empresa/tenant com schema_name='{schema}'."
            )

        print(f"Tenant: {getattr(empresa_tenant, 'nome', '') or empresa_tenant.pk} (schema={schema})")
        if not args.forcar:
            confirmacao = input(
                f"Escreva exactamente '{schema}' para criar/verificar o Consumidor Final: "
            ).strip()
            if confirmacao != schema:
                print("Operação cancelada; nenhum registo foi alterado.")
                return 1

        with schema_context(schema):
            with transaction.atomic():
                # Em PostgreSQL, impede duas execuções deste script para o mesmo schema
                # de calcularem simultaneamente o mesmo código interno.
                if connection.vendor == "postgresql":
                    lock_bytes = hashlib.sha256(
                        f"vistogest:consumidor-final:{schema}".encode("utf-8")
                    ).digest()[:8]
                    lock_id = int.from_bytes(lock_bytes, "big", signed=True)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])

                marcados = Cliente.objects.select_for_update().filter(
                    observacoes_internas__contains=MARCADOR
                )
                quantidade_marcados = marcados.count()
                if quantidade_marcados > 1:
                    raise RuntimeError(
                        f"Existem {quantidade_marcados} clientes com o marcador {MARCADOR}. "
                        "Corrija os duplicados manualmente; o script não escolherá um registo arbitrariamente."
                    )

                cliente = marcados.first()
                criado = False

                if cliente is None:
                    # Compatibilidade com um registo manual já criado segundo a convenção
                    # conhecida pelo PDF, antes de este script ter sido usado.
                    candidatos = Cliente.objects.select_for_update().filter(
                        tipo_cliente="pessoa_juridica",
                        razao_social__iexact=NOME_CONSUMIDOR,
                        nif=NIF_SENTINELA,
                    )
                    total_candidatos = candidatos.count()
                    if total_candidatos > 1:
                        raise RuntimeError(
                            "Foram encontrados vários clientes com razão social 'Consumidor Final' "
                            f"e NIF sentinela {NIF_SENTINELA}. Resolva a duplicação manualmente."
                        )
                    cliente = candidatos.first()

                if cliente is None:
                    # O modelo Cliente.clean() exige razão social e NIF para pessoa jurídica.
                    # A aplicação PDF fornecida já trata 999999999 como NIF sentinela de
                    # consumidor final, evitando apresentá-lo como NIF real no documento.
                    cliente = Cliente(
                        codigo_cliente=codigo_cliente_disponivel(Cliente),
                        tipo_cliente="pessoa_juridica",
                        nome_completo="",
                        razao_social=NOME_CONSUMIDOR,
                        nome_fantasia=NOME_CONSUMIDOR,
                        nif=NIF_SENTINELA,
                        bi="",
                        ativo=True,
                        bloqueado=False,
                        vip=False,
                        limite_credito=Decimal("0.00"),
                        desconto_padrao=Decimal("0.00"),
                        observacoes=(
                            "Registo padrão usado quando uma venda/documento é emitido "
                            "sem identificação do adquirente."
                        ),
                        observacoes_internas=MARCADOR,
                    )
                    try:
                        cliente.save(force_insert=True)
                    except IntegrityError as exc:
                        raise RuntimeError(
                            "Não foi possível criar o Consumidor Final devido a uma colisão de código. "
                            "Volte a executar o script para recalcular o próximo código disponível."
                        ) from exc
                    criado = True
                else:
                    # Marca um registo previamente existente e normaliza somente os campos
                    # essenciais; não apaga observações internas já registadas.
                    cliente.ativo = True
                    cliente.bloqueado = False
                    cliente.limite_credito = Decimal("0.00")
                    cliente.desconto_padrao = Decimal("0.00")
                    notas = (cliente.observacoes_internas or "").strip()
                    if MARCADOR not in notas:
                        cliente.observacoes_internas = f"{notas}\n{MARCADOR}".strip()
                    cliente.save(update_fields=[
                        "ativo", "bloqueado", "limite_credito", "desconto_padrao",
                        "observacoes_internas", "updated_at",
                    ] if hasattr(cliente, "updated_at") else [
                        "ativo", "bloqueado", "limite_credito", "desconto_padrao",
                        "observacoes_internas",
                    ])

                print("\nConsumidor Final verificado com sucesso.")
                print(f"Acção: {'criado' if criado else 'registo existente reutilizado'}")
                print(f"Schema: {schema}")
                print(f"ID: {cliente.pk}")
                print(f"Código: {cliente.codigo_cliente}")
                print(f"Nome de exibição: {cliente.nome_exibicao}")
                print(f"Activo: {'sim' if cliente.ativo else 'não'}")
                print(
                    "NIF sentinela interno: 999999999 "
                    "(o gerador PDF indicado trata-o como consumidor final, não como NIF real)."
                )

        return 0

    except KeyboardInterrupt:
        print("\nOperação interrompida pelo utilizador.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
