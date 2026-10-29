#!/usr/bin/env python3
"""Prepara um tenant Django com um único comando.

Executa, nesta ordem:
  1. setup_formas_pagamento (cria todas as formas; não activa nenhuma por --ativar)
  2. iniciar_ambiente_fin_tenant
  3. iniciar_ambiente_fiscal_tenant
  4. scripts/criar_consumidor_final.py

Uso na raiz do projecto:
    python scripts/preparar_tenant_producao.py mundoemaquinas

Se o schema for omitido, será solicitado interactivamente. O script confirma o
schema antes de executar e pára no primeiro comando que falhar. Cada etapa é um
processo Django separado; etapas já concluídas não são revertidas automaticamente.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_SETTINGS = "config.settings.production"
SCHEMA_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
TOTAL_ETAPAS = 4


def encontrar_raiz(explicita: str | None) -> Path:
    """Localiza o directório que contém manage.py."""
    if explicita:
        raiz = Path(explicita).expanduser().resolve()
        if not (raiz / "manage.py").is_file():
            raise FileNotFoundError(f"Não foi encontrado manage.py em: {raiz}")
        return raiz

    actual = Path.cwd().resolve()
    if (actual / "manage.py").is_file():
        return actual

    # Permite executar o script directamente a partir de <projecto>/scripts/.
    for candidato in Path(__file__).resolve().parents:
        if (candidato / "manage.py").is_file():
            return candidato

    raise FileNotFoundError(
        "Não foi possível localizar manage.py. Coloque o script em scripts/ "
        "do projecto ou indique --root CAMINHO_DO_PROJECTO."
    )


def validar_schema(schema: str) -> str:
    schema = (schema or "").strip()
    if not SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError(
            "Schema inválido. Use até 63 caracteres, começando por uma letra "
            "e utilizando apenas letras, números e underscore."
        )
    if schema.lower() == "public":
        raise ValueError("Por segurança, a preparação não pode ser executada no schema public.")
    return schema


def construir_comandos(
    raiz: Path,
    schema: str,
    settings_django: str,
    settings_financeiro: str,
) -> list[list[str]]:
    """Constrói os quatro comandos com schema/settings explícitos."""
    script_consumidor = raiz / "scripts" / "criar_consumidor_final.py"
    if not script_consumidor.is_file():
        raise FileNotFoundError(
            f"Não foi encontrado {script_consumidor}. Coloque criar_consumidor_final.py "
            "na mesma pasta scripts/ deste script."
        )

    manage = [sys.executable, "manage.py"]
    return [
        [
            *manage,
            "setup_formas_pagamento",
            f"--schema={schema}",
            "--forcar",
            f"--settings={settings_django}",
        ],
        [
            *manage,
            "iniciar_ambiente_fin_tenant",
            f"--schema={schema}",
            f"--settings={settings_financeiro}",
        ],
        [
            *manage,
            "iniciar_ambiente_fiscal_tenant",
            f"--schema={schema}",
            f"--settings={settings_django}",
        ],
        [
            sys.executable,
            str(script_consumidor.relative_to(raiz)),
            schema,
            f"--settings={settings_django}",
            "--forcar",
        ],
    ]


def executar(comando: list[str], raiz: Path, numero: int, total: int) -> None:
    print(
        f"\n{'=' * 76}\nETAPA {numero}/{total}\n{' '.join(comando)}\n{'=' * 76}",
        flush=True,
    )
    resultado = subprocess.run(comando, cwd=raiz, check=False)
    if resultado.returncode != 0:
        raise subprocess.CalledProcessError(resultado.returncode, comando)
    print(f"Etapa {numero}/{total} concluída com sucesso.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepara o tenant: formas de pagamento, ambiente financeiro, "
            "ambiente fiscal e Consumidor Final."
        )
    )
    parser.add_argument(
        "schema",
        nargs="?",
        help="Schema do tenant (ex.: mundoemaquinas). Se omitido, será solicitado.",
    )
    parser.add_argument(
        "--root",
        help="Caminho da raiz do projecto Django (directório onde está manage.py).",
    )
    parser.add_argument(
        "--django-settings",
        default=os.environ.get("DJANGO_SETTINGS_MODULE", DEFAULT_SETTINGS),
        help=(
            "Módulo settings para as etapas de formas de pagamento, fiscal e Consumidor Final. "
            f"Padrão: DJANGO_SETTINGS_MODULE ou {DEFAULT_SETTINGS}."
        ),
    )
    parser.add_argument(
        "--finance-settings",
        default=None,
        help=(
            "Módulo settings específico para iniciar_ambiente_fin_tenant. "
            "Por omissão, utiliza --django-settings."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Executa sem pedir confirmação interactiva do schema.",
    )
    args = parser.parse_args()

    try:
        raiz = encontrar_raiz(args.root)
        schema = validar_schema(args.schema or input("Introduza o schema do tenant: "))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.", file=sys.stderr)
        return 130

    settings_django = (args.django_settings or "").strip()
    settings_financeiro = (args.finance_settings or settings_django).strip()
    if not settings_django or not settings_financeiro:
        print("ERRO: indique os módulos de configurações Django.", file=sys.stderr)
        return 2

    try:
        comandos = construir_comandos(
            raiz=raiz,
            schema=schema,
            settings_django=settings_django,
            settings_financeiro=settings_financeiro,
        )
    except FileNotFoundError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print("\nPreparação automática do tenant VistoGest Pro")
    print(f"Projecto:                  {raiz}")
    print(f"Schema:                    {schema}")
    print(f"Settings gerais:           {settings_django}")
    print(f"Settings financeiros:      {settings_financeiro}")
    print("Formas de pagamento:       todas serão criadas; nenhuma é activada por --ativar")
    print("Etapas:                    formas → financeiro → fiscal → Consumidor Final")
    print("O processo pára no primeiro erro. As etapas concluídas não são revertidas automaticamente.")
    print("A primeira etapa usa --forcar, conforme o comando de preparação original.")

    if not args.yes:
        try:
            confirmacao = input(
                f"\nPara continuar, escreva exactamente o schema '{schema}': "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperação cancelada.")
            return 130
        if confirmacao != schema:
            print("Confirmação não corresponde ao schema. Nenhum comando foi executado.")
            return 1

    try:
        for indice, comando in enumerate(comandos, start=1):
            executar(comando, raiz, indice, TOTAL_ETAPAS)
    except KeyboardInterrupt:
        print(
            "\nExecução interrompida. Verifique quais etapas terminaram; "
            "as etapas concluídas não são revertidas automaticamente.",
            file=sys.stderr,
        )
        return 130
    except subprocess.CalledProcessError as exc:
        print(
            f"\nERRO: a etapa falhou com código {exc.returncode}. "
            "As etapas seguintes não foram executadas. Verifique a saída acima.",
            file=sys.stderr,
        )
        return exc.returncode or 1

    print(f"\nSUCESSO: as quatro etapas foram concluídas para o schema '{schema}'.")
    print("As formas de pagamento foram criadas; a activação fica a cargo dos utilizadores autorizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
