from django.core.management.base import BaseCommand

from apps.integracoes.services.catalogo import CATALOGO, garantir_catalogo


class Command(BaseCommand):
    help = "Cria/actualiza o catálogo de integrações (correr por tenant: tenant_command / all_tenants_command)."

    def handle(self, *args, **opts):
        garantir_catalogo(forcar=True)
        self.stdout.write(self.style.SUCCESS(f"{len(CATALOGO)} tipos de integração sincronizados."))

# python manage.py all_tenants_command seed_integracoes