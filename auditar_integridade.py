#!/usr/bin/env python
"""
auditar_integridade.py — VistoGest Pro / SOTARQ Software

Auditoria completa da infraestrutura de tenants e estado fiscal.
Verifica:
  1. Schemas físicos no PostgreSQL vs registos na tabela Empresa.
  2. Schemas órfãos (existem no DB mas sem registo).
  3. Conexão funcional dentro de cada schema.
  4. Migrações pendentes por schema.
  5. Configuração de AssinaturaDigital por tenant.
  6. Licença activa por tenant.
  7. SerieFiscalAGT configurada por tenant.

Uso:
    python auditar_integridade.py          # todos os tenants
    python auditar_integridade.py --schema=mundoemaquinas   # tenant específico
    python auditar_integridade.py --output=auditorias/     # exportar relatório

Também disponível como management command:
    python manage.py auditar_integridade --settings=config.settings.development
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Cores ANSI (sem dependências externas)
# ──────────────────────────────────────────────────────────────────────────────
GREEN  = '\033[32m'
RED    = '\033[31m'
YELLOW = '\033[33m'
CYAN   = '\033[36m'
RESET  = '\033[0m'
BOLD   = '\033[1m'
DIM    = '\033[2m'

def _ok(msg):     return f"  {GREEN}[OK]{RESET}    {msg}"
def _err(msg):    return f"  {RED}[ERRO]{RESET}  {msg}"
def _warn(msg):   return f"  {YELLOW}[AVISO]{RESET} {msg}"
def _info(msg):   return f"  {CYAN}[INFO]{RESET}  {msg}"
def _section(t):  return f"\n{BOLD}{CYAN}{'─'*60}\n  {t}\n{'─'*60}{RESET}"


# ──────────────────────────────────────────────────────────────────────────────
# Setup Django
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if os.environ.get('RENDER') or os.environ.get('ENV_MODE', '').lower() == 'production':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
else:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from django.db import connection
from django.utils import timezone
from django_tenants.utils import (
    get_tenant_model,
    get_public_schema_name,
    schema_exists,
    schema_context,
)


# ──────────────────────────────────────────────────────────────────────────────
# Núcleo da auditoria
# ──────────────────────────────────────────────────────────────────────────────

def executar_auditoria_integridade(schema_filtro=None):
    """
    Executa a auditoria completa. Devolve (linhas_output, contadores_problema).
    """
    Empresa   = get_tenant_model()
    public_schema = get_public_schema_name()
    linhas    = []
    problemas = {
        'schemas_ausentes':   [],
        'schemas_orfaos':     [],
        'schemas_com_falha':  [],
        'migrations_pendentes': [],
        'assinatura_incompleta': [],
        'licenca_inexistente':   [],
        'series_ausentes':       [],
    }

    ts = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    linhas.append(f"\n{'='*60}")
    linhas.append(f"  AUDITORIA DE INTEGRIDADE — VistoGest Pro")
    linhas.append(f"  {ts}")
    linhas.append(f"  Settings: {os.environ.get('DJANGO_SETTINGS_MODULE','?')}")
    linhas.append(f"{'='*60}\n")

    # ── 1. Schemas físicos vs registos BD ────────────────────────────────────
    linhas.append(_section("PASSO 1 — Schemas físicos vs registos Empresa"))

    empresas_qs = Empresa.objects.exclude(schema_name=public_schema)
    if schema_filtro:
        empresas_qs = empresas_qs.filter(schema_name=schema_filtro)
    empresas = list(empresas_qs)

    for emp in empresas:
        if not schema_exists(emp.schema_name):
            msg = f"Empresa '{emp.nome}' (ID:{emp.id}) → schema '{emp.schema_name}' NÃO existe no PostgreSQL"
            linhas.append(_err(msg))
            problemas['schemas_ausentes'].append(emp.schema_name)
        else:
            linhas.append(_ok(f"Schema '{emp.schema_name}' — existe no PostgreSQL"))

    if not empresas:
        linhas.append(_info("Nenhum tenant encontrado (além do public)."))

    # ── 2. Schemas órfãos ─────────────────────────────────────────────────────
    linhas.append(_section("PASSO 2 — Schemas físicos sem registo (órfãos)"))

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_catalog.pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%%' "
            "AND nspname NOT IN ('information_schema', %s)",
            [public_schema],
        )
        schemas_no_db = {row[0] for row in cursor.fetchall()}

    schemas_registados = set(Empresa.objects.values_list('schema_name', flat=True))
    orfaos = schemas_no_db - schemas_registados

    if orfaos:
        for sch in sorted(orfaos):
            linhas.append(_warn(f"Schema físico '{sch}' existe no DB mas não tem registo em Empresa"))
            problemas['schemas_orfaos'].append(sch)
    else:
        linhas.append(_ok("Nenhum schema órfão encontrado."))

    # ── 3. Conexão funcional por schema ───────────────────────────────────────
    linhas.append(_section("PASSO 3 — Teste de conexão por schema"))

    for emp in empresas:
        if emp.schema_name in problemas['schemas_ausentes']:
            continue
        try:
            with schema_context(emp.schema_name):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1;")
            linhas.append(_ok(f"'{emp.schema_name}' — conexão funcional"))
        except Exception as exc:
            linhas.append(_err(f"'{emp.schema_name}' — FALHA de conexão: {exc}"))
            problemas['schemas_com_falha'].append(emp.schema_name)

    # ── 4. Migrações pendentes por schema ─────────────────────────────────────
    linhas.append(_section("PASSO 4 — Migrações pendentes por schema"))

    try:
        from django.db.migrations.executor import MigrationExecutor

        for emp in empresas:
            if emp.schema_name in problemas['schemas_ausentes'] + problemas['schemas_com_falha']:
                continue
            with schema_context(emp.schema_name):
                executor = MigrationExecutor(connection)
                plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
                if plano:
                    pendentes = [str(m) for m, _ in plano[:5]]
                    extra = f"... e mais {len(plano)-5}" if len(plano) > 5 else ""
                    linhas.append(_warn(
                        f"'{emp.schema_name}' — {len(plano)} migração(ões) pendente(s): "
                        f"{', '.join(pendentes)}{extra}"
                    ))
                    problemas['migrations_pendentes'].append(emp.schema_name)
                else:
                    linhas.append(_ok(f"'{emp.schema_name}' — migrações em dia"))
    except Exception as exc:
        linhas.append(_warn(f"Não foi possível verificar migrações: {exc}"))

    # ── 5. AssinaturaDigital por tenant ───────────────────────────────────────
    linhas.append(_section("PASSO 5 — Configuração de AssinaturaDigital por tenant"))

    for emp in empresas:
        if emp.schema_name in problemas['schemas_ausentes'] + problemas['schemas_com_falha']:
            continue
        try:
            with schema_context(emp.schema_name):
                from apps.fiscal.models import AssinaturaDigital
                config = AssinaturaDigital.obter_configuracao()
                if not config:
                    linhas.append(_warn(f"'{emp.schema_name}' — AssinaturaDigital não existe"))
                    problemas['assinatura_incompleta'].append(emp.schema_name)
                elif not config.nif_contribuinte:
                    linhas.append(_warn(f"'{emp.schema_name}' — nif_contribuinte não preenchido"))
                    problemas['assinatura_incompleta'].append(emp.schema_name)
                elif not config.esta_configurada:
                    linhas.append(_warn(f"'{emp.schema_name}' — chaves do contribuinte não configuradas"))
                    problemas['assinatura_incompleta'].append(emp.schema_name)
                elif not config.api_username:
                    linhas.append(_warn(f"'{emp.schema_name}' — api_username AGT não preenchido"))
                    problemas['assinatura_incompleta'].append(emp.schema_name)
                else:
                    linhas.append(_ok(f"'{emp.schema_name}' — NIF={config.nif_contribuinte}, chaves OK, api_username OK"))
        except Exception as exc:
            linhas.append(_warn(f"'{emp.schema_name}' — erro ao verificar AssinaturaDigital: {exc}"))

    # ── 6. Licença activa por tenant ──────────────────────────────────────────
    linhas.append(_section("PASSO 6 — Licença activa por tenant"))

    for emp in empresas:
        if emp.schema_name in problemas['schemas_ausentes'] + problemas['schemas_com_falha']:
            continue
        try:
            from apps.licenca.models import Licenca
            with schema_context(public_schema):
                try:
                    lic = Licenca.objects.get(empresa=emp)
                    if lic.status == 'ativa' and not lic.esta_vencida:
                        linhas.append(_ok(
                            f"'{emp.schema_name}' — Licença '{lic.plano.nome}' activa "
                            f"(vence em {lic.data_vencimento})"
                        ))
                    else:
                        linhas.append(_warn(
                            f"'{emp.schema_name}' — Licença status='{lic.status}', "
                            f"vencimento={lic.data_vencimento}"
                        ))
                        problemas['licenca_inexistente'].append(emp.schema_name)
                except Licenca.DoesNotExist:
                    linhas.append(_warn(f"'{emp.schema_name}' — sem licença registada"))
                    problemas['licenca_inexistente'].append(emp.schema_name)
        except Exception as exc:
            linhas.append(_warn(f"'{emp.schema_name}' — erro ao verificar licença: {exc}"))

    # ── 7. SerieFiscalAGT por tenant ──────────────────────────────────────────
    linhas.append(_section("PASSO 7 — Séries Fiscais AGT por tenant"))

    for emp in empresas:
        if emp.schema_name in problemas['schemas_ausentes'] + problemas['schemas_com_falha']:
            continue
        try:
            with schema_context(emp.schema_name):
                from apps.fiscal.models import SerieFiscalAGT
                series = SerieFiscalAGT.objects.filter(
                    series_status__in=['A', 'U']
                ).count()
                if series > 0:
                    linhas.append(_ok(f"'{emp.schema_name}' — {series} série(s) activa(s)/em uso"))
                else:
                    linhas.append(_warn(f"'{emp.schema_name}' — nenhuma série fiscal AGT activa"))
                    problemas['series_ausentes'].append(emp.schema_name)
        except Exception as exc:
            linhas.append(_warn(f"'{emp.schema_name}' — erro ao verificar séries: {exc}"))

    # ── Resumo ────────────────────────────────────────────────────────────────
    linhas.append(f"\n{'='*60}")
    linhas.append(f"  RESUMO DA AUDITORIA")
    linhas.append(f"{'='*60}")
    linhas.append(f"  Tenants verificados:          {len(empresas)}")
    linhas.append(f"  Schemas ausentes:             {len(problemas['schemas_ausentes'])}")
    linhas.append(f"  Schemas órfãos:               {len(problemas['schemas_orfaos'])}")
    linhas.append(f"  Falhas de conexão:            {len(problemas['schemas_com_falha'])}")
    linhas.append(f"  Migrações pendentes:          {len(problemas['migrations_pendentes'])}")
    linhas.append(f"  AssinaturaDigital incompleta: {len(problemas['assinatura_incompleta'])}")
    linhas.append(f"  Sem licença activa:           {len(problemas['licenca_inexistente'])}")
    linhas.append(f"  Sem séries AGT activas:       {len(problemas['series_ausentes'])}")

    total_problemas = sum(len(v) for v in problemas.values())
    if total_problemas == 0:
        linhas.append(f"\n{GREEN}  ✔ CONCLUSÃO: Infraestrutura 100% íntegra.{RESET}")
    else:
        linhas.append(f"\n{RED}  ✘ CONCLUSÃO: {total_problemas} problema(s) encontrado(s).{RESET}")
    linhas.append(f"{'='*60}\n")

    return linhas, problemas


def main():
    parser = argparse.ArgumentParser(description='Auditoria de integridade do VistoGest Pro')
    parser.add_argument('--schema', help='Auditar apenas um schema específico', default=None)
    parser.add_argument('--output', help='Directório onde guardar o relatório .txt', default=None)
    args = parser.parse_args()

    linhas, problemas = executar_auditoria_integridade(schema_filtro=args.schema)

    # Imprimir no terminal com cores
    for linha in linhas:
        print(linha)

    # Exportar para ficheiro se --output foi especificado
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        ficheiro = output_dir / f"integridade_{ts}.txt"

        # Remover códigos de cor para o ficheiro de texto
        import re
        ansi_escape = re.compile(r'\033\[[0-9;]*m')
        with open(ficheiro, 'w', encoding='utf-8') as f:
            for linha in linhas:
                f.write(ansi_escape.sub('', linha) + '\n')
        print(f"\n  Relatório exportado: {ficheiro}")

    total = sum(len(v) for v in problemas.values())
    sys.exit(1 if total > 0 else 0)


if __name__ == '__main__':
    main()
