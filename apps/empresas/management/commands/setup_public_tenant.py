from django.core.management.base import BaseCommand
from apps.empresas.models import Empresa, Domain
from django.db import connection

class Command(BaseCommand):
    help = 'Cria o tenant público e o domínio inicial'

    def handle(self, *args, **options):
        # 1. Verificar se o schema public já existe
        self.stdout.write("Configurando o Tenant Público...")
        
        # Cria a Empresa 'mãe' no schema public
        public_tenant, created = Empresa.objects.get_or_create(
            nif="000000000",
            defaults={
                "nome": "SOTARQ ADMIN",
                "nome_fantasia": "SOTARQ CENTRAL",
                "endereco": "Sede Central",
                "bairro": "Centro",
                "cidade": "Malanje",
                "provincia": "MAL",
                "postal": "0000",
                "telefone": "900000000",
                "email": "admin@sotarq.com",
            }
        )

        # 2. Criar o Domínio para o schema public
        # Nota: Se estiver em desenvolvimento, use 'localhost' ou '127.0.0.1'
        domain_name = 'localhost' 
        Domain.objects.get_or_create(
            domain=domain_name,
            tenant=public_tenant,
            defaults={'is_primary': True}
        )

        self.stdout.write(self.style.SUCCESS(f"Tenant Público '{public_tenant.nome}' e Domínio '{domain_name}' configurados."))