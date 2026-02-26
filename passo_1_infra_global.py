# passo_1_infra_global.py
import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.empresas.models import Empresa, Domain

def criar_infra():
    print("--- 🚀 SOTARQ: Iniciando Infraestrutura Global ---")
    connection.set_schema_to_public()

    # Criar Empresa Mestre (Public) - Sem foto para evitar erro de API Cloudinary
    tenant, created = Empresa.objects.get_or_create(
        schema_name='public',
        defaults={
            'nome': 'SOTARQ GESTAO GLOBAL',
            'nif': '0000000000',
            'endereco': 'Sede Central SOTARQ',
            'bairro': 'Centro',
            'cidade': 'Malanje',
            'provincia': 'MAL',
            'email': 'admin@sotarq.com',
            'telefone': '900000000',
            'postal': '0000',
            'ativa': True
        }
    )

    if created:
        print(f"✔ Empresa 'public' criada.")
    else:
        print(f"i Empresa 'public' já existe.")

    # Criar Domínio Localhost
    domain, d_created = Domain.objects.get_or_create(
        domain='localhost',
        defaults={
            'tenant': tenant,
            'is_primary': True
        }
    )

    if d_created:
        print(f"✔ Domínio 'localhost' configurado.")
    else:
        print(f"i Domínio 'localhost' já existe.")

if __name__ == "__main__":
    criar_infra()