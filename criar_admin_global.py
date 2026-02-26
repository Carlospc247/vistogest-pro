# create_global_superuser.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.core.models import Usuario
from apps.empresas.models import Empresa
from django.db import connection

def create_admin():
    print("--- CRIANDO SUPERUSUÁRIO GLOBAL ---")
    
    connection.set_schema_to_public()
    
    try:
        public_tenant = Empresa.objects.get(schema_name='public')
    except Empresa.DoesNotExist:
        print("❌ ERRO: Execute primeiro o script 'init_public_tenant.py'.")
        return

    username = "admin_sotarq"
    email = "admin@sotarq.com"
    password = "88PiY~PJzKTen38i2026!"

    if not Usuario.objects.filter(username=username).exists():
        user = Usuario.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            empresa=public_tenant,
            e_administrador_empresa=True # Campo customizado SOTARQ
        )
        print(f"✔ Superusuário '{username}' criado com sucesso!")
        print(f"🔑 Password: {password}")
    else:
        print(f"i O usuário '{username}' já existe.")

if __name__ == "__main__":
    create_admin()