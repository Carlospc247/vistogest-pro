# apps/core/management/commands/verificar_categorias.py
# Criar este arquivo para debug

from django.core.management.base import BaseCommand
from django.db import connection
from apps.empresas.models import Empresa, Categoria


class Command(BaseCommand):
    help = 'Verifica e corrige problemas com categorias'
    
    def handle(self, *args, **options):
        self.stdout.write("=== VERIFICAÇÃO DE CATEGORIAS ===")
        
        # 1. Verificar empresas
        empresas = Empresa.objects.all()
        self.stdout.write(f"Empresas encontradas: {empresas.count()}")
        for empresa in empresas:
            self.stdout.write(f"  - {empresa.id}: {empresa.nome}")
        
        # 2. Verificar categorias
        categorias = Categoria.objects.all()
        self.stdout.write(f"\nCategorias encontradas: {categorias.count()}")
        for categoria in categorias:
            self.stdout.write(f"  - {categoria.id}: {categoria.nome} (Empresa: {categoria.empresa_id})")
        
        # 3. Verificar duplicatas
        # 3. Verificar duplicatas
        self.stdout.write("\n=== VERIFICANDO DUPLICATAS ===")
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT empresa_id, nome, COUNT(*) 
                FROM {Categoria._meta.db_table}
                GROUP BY empresa_id, nome 
                HAVING COUNT(*) > 1
            """)
            duplicatas = cursor.fetchall()

            
            if duplicatas:
                self.stdout.write("DUPLICATAS ENCONTRADAS:")
                for empresa_id, nome, count in duplicatas:
                    self.stdout.write(f"  - Empresa {empresa_id}, Nome '{nome}': {count} registros")
                    
                    # Remover duplicatas
                    categorias_dup = Categoria.objects.filter(empresa_id=empresa_id, nome=nome)
                    primeira = categorias_dup.first()
                    for categoria in categorias_dup[1:]:
                        self.stdout.write(f"    Removendo categoria ID {categoria.id}")
                        categoria.delete()
            else:
                self.stdout.write("Nenhuma duplicata encontrada.")
        
        # 4. Verificar constraint
        self.stdout.write("\n=== VERIFICANDO CONSTRAINT ===")
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT constraint_name, constraint_type 
                FROM information_schema.table_constraints 
                WHERE table_name = 'Categoria._meta.db_table'
            """)
            constraints = cursor.fetchall()
            
            for name, tipo in constraints:
                self.stdout.write(f"  - {name}: {tipo}")
        
        self.stdout.write("\n=== VERIFICAÇÃO CONCLUÍDA ===")
    
