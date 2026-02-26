from django.core.management.base import BaseCommand
from apps.licenca.models import Modulo
from django.utils.text import slugify

class Command(BaseCommand):
    help = 'Cria os módulos do sistema baseados nas apps disponíveis'

    def handle(self, *args, **options):
        # Lista extraída do seu TENANT_APPS no settings.py
        apps_sistema = [
            ('Produtos e Inventário', 'produtos'),
            ('Business Intelligence | Auditoria', 'analytics'),
            ('Gestão de Fornecedores', 'fornecedores'),
            ('Controle de Estoque', 'estoque'),
            ('Gestão de Clientes', 'clientes'),
            ('Vendas e Faturamento', 'vendas'),
            ('Recursos Humanos', 'funcionarios'),
            ('Prestação de Serviços', 'servicos'),
            ('Gestão de Comandas', 'comandas'),
            ('Financeiro e Fluxo de Caixa', 'financeiro'),
            ('Relatórios Gerenciais', 'relatorios'),
            ('Configurações do Sistema', 'configuracoes'),
            ('Fiscal e Impostos', 'fiscal'),
            ('Exportação SAF-T', 'saft'),
            ('Gestão de Compras', 'compras'),
            ('Site institucional', 'site'),
        ]

        self.stdout.write(self.style.MIGRATE_HEADING('Iniciando criação de módulos...'))

        for nome, slug in apps_sistema:
            modulo, created = Modulo.objects.get_or_create(
                slug=slug,
                defaults={'nome': nome, 'descricao': f'Acesso ao módulo de {nome}', 'ativo': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Módulo "{nome}" criado.'))
            else:
                self.stdout.write(f'Módulo "{nome}" já existe.')

        self.stdout.write(self.style.SUCCESS('Configuração de módulos concluída.'))