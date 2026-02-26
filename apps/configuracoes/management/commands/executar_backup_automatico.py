# apps/configuracoes/management/commands/executar_backup_automatico.py
from django.core.management.base import BaseCommand
from apps.empresas.models import Empresa
from apps.configuracoes.services.backup_service import executar_backup, limpar_backups_antigos

class Command(BaseCommand):
    help = 'Executa backup automático diário e remove backups antigos'

    def handle(self, *args, **options):
        empresas = Empresa.objects.all()
        for empresa in empresas:
            executar_backup(empresa, tipo='automático', user=None)
        limpar_backups_antigos(dias=30)
        self.stdout.write(self.style.SUCCESS("Backups automáticos concluídos e limpos com sucesso."))

