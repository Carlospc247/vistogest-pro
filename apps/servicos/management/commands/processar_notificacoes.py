# apps/servicos/management/commands/processar_notificacoes.py
"""Manual entry point. Actual network sends are still delegated to Celery workers."""
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = "Cria notificações de agendamentos e enfileira as pendentes no Celery."

    def add_arguments(self, parser):
        parser.add_argument("--criar-notificacoes", action="store_true")
        parser.add_argument("--enviar-pendentes", action="store_true")

    def handle(self, *args, **options):
        criar = options["criar_notificacoes"]
        enviar = options["enviar_pendentes"]
        if not criar and not enviar:
            raise CommandError("Indique --criar-notificacoes, --enviar-pendentes ou ambos.")

        from apps.empresas.models import Empresa
        from apps.servicos.tasks import _criar_notificacoes_do_tenant, _enfileirar_notificacoes_vencidas

        with schema_context("public"):
            schemas = list(Empresa.objects.exclude(schema_name="public").values_list("schema_name", flat=True))

        criadas = enfileiradas = erros = 0
        for schema_name in schemas:
            try:
                with schema_context(schema_name):
                    if criar:
                        criadas += _criar_notificacoes_do_tenant(schema_name)
                    if enviar:
                        enfileiradas += _enfileirar_notificacoes_vencidas(schema_name)
            except Exception as exc:
                erros += 1
                self.stderr.write(self.style.ERROR(f"{schema_name}: {exc}"))

        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {criadas} criadas; {enfileiradas} enviadas para o worker; {erros} tenants com erro."
        ))
