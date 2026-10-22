# apps/core/tenant_commands.py
import random

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import get_tenant_model, schema_context


class TenantCommand(BaseCommand):
    """Base: corre o command dentro do schema de um tenant (nunca no public)."""

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True,
                            help="schema_name do tenant (ex.: mundoemaquinas)")
        parser.add_argument('--forcar', action='store_true',
                            help="Permite correr com DEBUG=False (dados de teste!)")
        parser.add_argument('--seed', type=int, default=42,
                            help="Semente do gerador aleatório (resultados reprodutíveis)")

    def handle(self, *args, **options):
        schema = options['schema']
        if schema == 'public':
            raise CommandError("Indique o schema de um tenant, não o 'public'.")
        if not get_tenant_model().objects.filter(schema_name=schema).exists():
            raise CommandError(f"Não existe nenhum tenant com schema_name='{schema}'.")
        if not settings.DEBUG and not options['forcar']:
            raise CommandError("DEBUG=False: estes commands criam dados de teste. "
                               "Use --forcar se tem a certeza.")
        self.rng = random.Random(options['seed'])
        with schema_context(schema):
            self.handle_tenant(*args, **options)

    def handle_tenant(self, *args, **options):
        raise NotImplementedError