import os
import django
from django.db import connection

# Rigor SOTARQ: Configuração correta do módulo de settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

from django_tenants.utils import schema_context
from apps.empresas.models import Empresa
from apps.financeiro.models import CategoriaFinanceira, ContaBancaria

def seed_mundo_maquinas():
    schema_name = 'mundo_maquinas'
    
    try:
        with schema_context(schema_name):
            print(f"--- Iniciando Seed no Schema: {schema_name} ---")
            
            # 1. Garantir que a Empresa existe (Ajustado para o campo 'nome')
            empresa, created_emp = Empresa.objects.get_or_create(
                schema_name=schema_name, # Importante para Tenants
                defaults={
                    'nome': "Mundo e Máquinas Lda",
                    'nome_fantasia': "Mundo Máquinas",
                    'nif': '5000123456', 
                    'ativa': True
                }
            )
            if created_emp: 
                print(f"Empresa '{empresa.nome}' criada com sucesso.")
            else:
                print(f"Empresa '{empresa.nome}' já existia.")

            # 2. Criar Categorias Financeiras (Rigor Vistogest Pro)
            categorias = [
                ('Venda de Produtos', 'receita'),
                ('Prestação de Serviços', 'receita'),
                ('Pagamento Fornecedores', 'despesa'),
                ('Despesas Operacionais', 'despesa'),
            ]
            
            for nome_cat, tipo_cat in categorias:
                cat, created = CategoriaFinanceira.objects.get_or_create(
                    nome=nome_cat,
                    empresa=empresa,
                    tipo=tipo_cat,
                    defaults={'ativa': True}
                )
                if created: print(f"Categoria criada: {nome_cat}")

            # 3. Conta Bancária Principal (Motor de Fluxo de Caixa)
            conta, created_bank = ContaBancaria.objects.get_or_create(
                nome="Caixa Geral",
                empresa=empresa,
                defaults={
                    'banco': 'BANCO BIC',
                    'agencia': '0001',
                    'conta': '12345097658',
                    'tipo_conta': 'caixa',
                    'conta_principal': True,
                    'ativa': True
                }
            )
            if created_bank: print(f"Conta principal criada: {conta.nome}")

            print("--- Seed Finalizado com Sucesso ---")
            
    except Exception as e:
        print(f"ERRO DE RIGOR TÉCNICO: {e}")

if __name__ == "__main__":
    seed_mundo_maquinas()

#python manage.py migrate_schemas --schema=public --settings=pharmassys.settings.development
#python manage.py migrate_schemas --schema=mundo_maquinas --settings=pharmassys.settings.development