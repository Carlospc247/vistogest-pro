# apps/configuracoes/management/commands/executar_backup_automatico.py
from django.core.management.base import BaseCommand
from django_tenants.utils import get_tenant_model, get_public_schema_name, schema_context
from apps.configuracoes.services.backup_service import executar_backup, limpar_backups_antigos


class Command(BaseCommand):
    help = 'Executa backup automático diário e remove backups antigos para todos os tenants'

    def handle(self, *args, **options):
        TenantModel = get_tenant_model()
        # Obtém todos os tenants cadastrados ignorando o schema público
        tenants = TenantModel.objects.exclude(schema_name=get_public_schema_name())

        for tenant in tenants:
            # Alterna a execução do banco para o schema do tenant atual
            with schema_context(tenant.schema_name):
                self.stdout.write(f"Processando backup para o tenant: {tenant.schema_name}")
                executar_backup(tipo='automático', user=None)
                limpar_backups_antigos(dias=30)

        self.stdout.write(
            self.style.SUCCESS("Backups automáticos concluídos e limpos com sucesso para todos os tenants.")
        )
