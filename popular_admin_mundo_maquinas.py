# popular_cliente.py
import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from apps.funcionarios.models import Cargo, Departamento

def popular(schema_name):
    print(f"--- 🛠 SOTARQ: Populando Dados Iniciais no Schema: {schema_name} ---")
    connection.set_schema(schema_name)
    
    # Criar Departamentos Básicos
    Departamento.objects.get_or_create(nome="Administração", codigo="ADM")
    Departamento.objects.get_or_create(nome="Operacional", codigo="OPS")
    
    # Criar Cargos Iniciais
    Cargo.objects.get_or_create(nome="Diretor Geral", nivel_hierarquico=1)
    Cargo.objects.get_or_create(nome="Gerente", nivel_hierarquico=2)
    
    print("✔ Dados populados com sucesso.")

if __name__ == "__main__":
    popular('mundo_maquinas')