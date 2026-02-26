# apps/core/management/commands/criar_clientes_exemplo.py

from django.core.management.base import BaseCommand
from apps.empresas.models import Empresa
from apps.clientes.models import Cliente



class Command(BaseCommand):
    help = 'Cria clientes de exemplo'
    
    def handle(self, *args, **options):
        empresa = Empresa.objects.first()
        if not empresa:
            self.stdout.write(self.style.ERROR('Nenhuma empresa encontrada'))
            return
        
        clientes_exemplo = [
            {
                'nome_completo': 'João Silva Santos',
                'documento': '123456789',
                'telefone': '923456789',
                'email': 'joao.silva@email.com',
                'endereco': 'Rua das Flores, 123',
                'cidade': 'Luanda',
                'provincia': 'Luanda'
            },
            {
                'nome_completo': 'Maria dos Santos',
                'documento': '987654321',
                'telefone': '924567890',
                'email': 'maria.santos@email.com',
                'endereco': 'Avenida Principal, 456',
                'cidade': 'Luanda',
                'provincia': 'Luanda'
            },
            {
                'nome_completo': 'António Manuel',
                'documento': '456789123',
                'telefone': '925678901',
                'email': 'antonio.manuel@email.com',
                'endereco': 'Travessa Central, 789',
                'cidade': 'Benguela',
                'provincia': 'Benguela'
            }
        ]
        
        for cliente_data in clientes_exemplo:
            cliente, created = Cliente.objects.get_or_create(
                empresa=empresa,
                documento=cliente_data['documento'],
                defaults=cliente_data
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'Cliente "{cliente.nome_completo}" criado com sucesso')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Cliente "{cliente.nome_completo}" já existe')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Processo concluído. Total de clientes: {Cliente.objects.filter(empresa=empresa).count()}')
        )

