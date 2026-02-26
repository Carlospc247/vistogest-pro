# provisionar_cliente.py
import os
import django
from django.db import connection

# 1. Configuração de Ambiente
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.empresas.models import Empresa, Domain
from apps.core.models import Usuario

def criar_cliente(schema_name, nome_empresa, nif, dominio, email_admin):
    print(f"--- 🚀 SOTARQ: Provisionando Cliente: {nome_empresa} ---")
    
    # Garantir que estamos no schema public para criar o registro do Tenant
    connection.set_schema_to_public()

    # 2. Criar a Empresa (Tenant)
    # O save() desta classe dispara automaticamente o 'create_schema' no Postgres
    try:
        tenant = Empresa.objects.create(
            schema_name=schema_name,
            nome=nome_empresa,
            nif=nif,
            endereco="Endereço Padrão",
            bairro="Bairro Padrão",
            cidade="Luanda",
            provincia="LUA",
            email=email_admin,
            telefone="900000000",
            postal="0000",
            ativa=True
        )
        print(f"✔ Schema '{schema_name}' criado e migrado com sucesso.")

        # 3. Criar o Domínio para este Cliente
        # Ex: escola1.localhost ou cliente.sotarq.com
        Domain.objects.create(
            domain=dominio,
            tenant=tenant,
            is_primary=True
        )
        print(f"✔ Domínio '{dominio}' vinculado ao cliente.")

        # 4. Criar o Administrador da Empresa (No Schema do Cliente)
        # O rigor SOTARQ exige que o admin do cliente seja criado dentro do seu próprio schema
        connection.set_schema(schema_name)
        
        username_admin = f"admin_{schema_name}"
        if not Usuario.objects.filter(username=username_admin).exists():
            Usuario.objects.create_superuser(
                username=username_admin,
                email=email_admin,
                password='88PiY~PJzKTen38i2026!',
                empresa=tenant,
                e_administrador_empresa=True
            )
            print(f"✔ Administrador do Cliente criado: {username_admin}")

        print(f"\n✅ PROVISIONAMENTO CONCLUÍDO COM SUCESSO!")
        print(f"Acesse em: http://{dominio}:8080/admin")

    except Exception as e:
        print(f"❌ ERRO CRÍTICO NO PROVISIONAMENTO: {e}")

if __name__ == "__main__":
    # Exemplo de uso para o SOTARQ SCHOOL
    criar_cliente(
        schema_name='mundo_maquinas', 
        nome_empresa='Mundo e Máquinas', 
        nif='500012345', 
        dominio='mundoemaquinas.localhost', # Use .localhost para testar localmente
        email_admin='direcao@mundoemaquinas.ao'
    )