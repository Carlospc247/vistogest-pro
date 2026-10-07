# apps/parceiros/management/commands/expirar_licencas_parceiros.py
from django.core.management.base import BaseCommand
from apps.parceiros.services import PartnerService


class Command(BaseCommand):
    help = 'Verifica e expira licenças de parceiros vencidas'

    def handle(self, *args, **options):
        count = PartnerService.expirar_licencas_vencidas()
        self.stdout.write(self.style.SUCCESS(f'✔ {count} licença(s) expirada(s).'))
