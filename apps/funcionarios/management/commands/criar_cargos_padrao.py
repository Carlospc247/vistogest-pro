from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_public_schema_name, get_tenant_model

from apps.funcionarios.cargos_padrao import aplicar_no_schema


class Command(BaseCommand):
    help = "Cria os cargos padrão (Administrador, Gerente, ...) em todos os tenants existentes."

    def add_arguments(self, parser):
        parser.add_argument("--schema", action="append", dest="schemas",
                            help="Limita a um schema (pode repetir a opção).")
        parser.add_argument("--sincronizar", action="store_true",
                            help="Repõe as permissões dos cargos JÁ existentes (apaga personalizações).")
        parser.add_argument("--incluir-parceiros", action="store_true",
                            help="Dá as permissões de parceiros ao ADMIN (só para o tenant interno SOTARQ).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Mostra o que faria, sem gravar nada.")

    def handle(self, *args, **opts):
        Empresa = get_tenant_model()
        tenants = Empresa.objects.exclude(schema_name=get_public_schema_name())

        if opts["schemas"]:
            tenants = tenants.filter(schema_name__in=opts["schemas"])
            em_falta = set(opts["schemas"]) - set(tenants.values_list("schema_name", flat=True))
            if em_falta:
                raise CommandError(f"Schemas não encontrados: {sorted(em_falta)}")

        prefixo = "[dry-run] " if opts["dry_run"] else ""
        erros = []

        for empresa in tenants.order_by("schema_name"):
            try:
                resultado = aplicar_no_schema(
                    empresa.schema_name,
                    sincronizar=opts["sincronizar"],
                    incluir_parceiros=opts["incluir_parceiros"],
                    dry_run=opts["dry_run"],
                )
            except Exception as e:
                erros.append(empresa.schema_name)
                self.stderr.write(self.style.ERROR(f"{prefixo}{empresa.schema_name}: ERRO — {e}"))
                continue

            detalhe = ", ".join(f"{cod}={estado}" for cod, estado in resultado.items())
            self.stdout.write(self.style.SUCCESS(f"{prefixo}{empresa.schema_name}: {detalhe}"))

        total = tenants.count()
        self.stdout.write(f"\n{prefixo}Processados: {total - len(erros)}/{total}")
        if erros:
            raise CommandError(
                f"Falhou em: {', '.join(erros)}. "
                "Se for 'relation does not exist', corra primeiro: python manage.py migrate_schemas"
            )