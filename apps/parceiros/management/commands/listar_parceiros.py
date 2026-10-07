# apps/parceiros/management/commands/listar_parceiros.py
from django.core.management.base import BaseCommand
from apps.parceiros.models import Partner


class Command(BaseCommand):
    help = 'Lista todos os parceiros com estado e quota'

    def handle(self, *args, **options):
        partners = Partner.objects.select_related('usuario').order_by('nome')
        if not partners.exists():
            self.stdout.write('Nenhum parceiro cadastrado.')
            return

        self.stdout.write(f'\n{"ID":<5} {"Nome":<30} {"Estado":<12} {"Licença":<25} {"Quota"}')
        self.stdout.write('-' * 90)
        for p in partners:
            lic = p.licenca_activa
            lic_label = lic.plano.nome[:24] if lic else '(sem licença)'
            quota = ''
            if lic:
                s = lic.saldo()
                t_lim = '∞' if s['ilimitado_total'] else str(s['total_limite'])
                quota = f"{s['total_usado']}/{t_lim}"
            self.stdout.write(
                f"{p.pk:<5} {p.nome[:30]:<30} {p.status:<12} {lic_label:<25} {quota}"
            )
        self.stdout.write('')
