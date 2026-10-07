"""
setup_departamento — cria os departamentos padrão em todos os tenants.

- Idempotente. `codigo` é o identificador estável; sem código, procura pelo nome.
- Por defeito só CRIA os que faltam e preserva os existentes.
- --sincronizar repõe nome/descrição/centro de custo/ativo dos existentes.
- Nunca altera `responsavel`.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model

from apps.funcionarios.departamentos_padrao import DEPARTAMENTOS_PADRAO, aplicar_no_schema


class Command(BaseCommand):
    help = "Cria os departamentos padrão em todos os tenants (ou nos indicados)."

    def add_arguments(self, parser):
        parser.add_argument("--schema", action="append", dest="schemas",
                            help="Limita a um schema (pode repetir a opção).")
        parser.add_argument("--sincronizar", action="store_true",
                            help="Atualiza também os existentes (apaga personalizações).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Simula sem gravar nada.")
        parser.add_argument("--only", action="append", dest="only", metavar="CODIGO",
                            help="Só estes códigos. Ex.: --only DEP-ADM --only DEP-FIN.")

    def handle(self, *args, **opts):
        only = {c.strip().upper() for c in (opts["only"] or []) if c.strip()}
        desconhecidos = only - {d["codigo"].upper() for d in DEPARTAMENTOS_PADRAO}
        if desconhecidos:
            raise CommandError("Código(s) desconhecido(s): " + ", ".join(sorted(desconhecidos)))

        Empresa = get_tenant_model()
        tenants = Empresa.objects.exclude(schema_name=get_public_schema_name())
        if opts["schemas"]:
            tenants = tenants.filter(schema_name__in=opts["schemas"])
            em_falta = set(opts["schemas"]) - set(tenants.values_list("schema_name", flat=True))
            if em_falta:
                raise CommandError(f"Schemas não encontrados: {sorted(em_falta)}")

        if not tenants.exists():
            self.stdout.write(self.style.WARNING("Nenhum tenant encontrado."))
            return

        prefixo = "[dry-run] " if opts["dry_run"] else ""
        estilos = {"criado": self.style.SUCCESS, "atualizado": self.style.WARNING,
                   "erro": self.style.ERROR}
        simbolos = {"criado": "+", "atualizado": "~", "erro": "!"}
        totais, falhas = Counter(), []

        for empresa in tenants.order_by("schema_name"):
            self.stdout.write(self.style.NOTICE(f"\n{prefixo}[{empresa.schema_name}]"))
            try:
                linhas = aplicar_no_schema(
                    empresa.schema_name,
                    sincronizar=opts["sincronizar"],
                    codigos=only or None,
                    dry_run=opts["dry_run"],
                )
            except Exception as e:
                falhas.append(empresa.schema_name)
                self.stderr.write(self.style.ERROR(f"  ERRO — {e}"))
                continue

            for codigo, nome, estado, alteracoes in linhas:
                totais[estado] += 1
                estilo = estilos.get(estado, lambda s: s)
                self.stdout.write(estilo(
                    f"  {simbolos.get(estado, '=')} {estado.upper():<10} | {codigo:<12} | {nome}"
                ))
                for campo, atual, novo in alteracoes:
                    self.stdout.write(f"      {campo}: {atual!r} -> {novo!r}")

        self.stdout.write(
            f"\n{prefixo}Criados: {totais['criado']} | Atualizados: {totais['atualizado']} | "
            f"Inalterados: {totais['inalterado']} | Preservados: {totais['existente']} | "
            f"Erros: {totais['erro']}"
        )
        if falhas:
            raise CommandError(
                f"Falhou em: {', '.join(falhas)}. "
                "Se for 'relation does not exist', corra primeiro: python manage.py migrate_schemas"
            )