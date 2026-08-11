import os
import django

# 1. Configuração do ambiente Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from django_tenants.utils import (
    get_tenant_model,
    get_public_schema_name,
    schema_context
)

# Resolução dinâmica dos modelos
Usuario = get_user_model()
Empresa = get_tenant_model()

def create_admin():
    print("--- CRIANDO SUPERUSUÁRIO GLOBAL SOTARQ ---")
    
    public_schema = get_public_schema_name()
    
    # 2. Verifica se o tenant 'public' existe no banco
    if not Empresa.objects.filter(schema_name=public_schema).exists():
        print("❌ ERRO: Execute primeiro o script 'init_public_tenant.py'.")
        return

    username = "admin_sotarq"
    email = "admin@sotarq.com"
    password = "88PiY~PJzKTen38i2026!"

    # 3. Garante que a criação ocorrerá estritamente dentro do schema 'public'
    with schema_context(public_schema):
        if not Usuario.objects.filter(username=username).exists():
            user = Usuario.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                e_administrador_empresa=True  # Campo booleano do Custom User Model
            )
            print(f"✔ Superusuário '{username}' criado com sucesso no schema '{public_schema}'!")
            print(f"🔑 Password: {password}")
        else:
            print(f"ℹ O usuário '{username}' já existe no schema '{public_schema}'.")

if __name__ == "__main__":
    create_admin()