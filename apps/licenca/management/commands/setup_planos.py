from django.core.management.base import BaseCommand
from apps.licenca.models import PlanoLicenca, Modulo
from decimal import Decimal

class Command(BaseCommand):
    help = 'Cria os planos de licença com herança progressiva de módulos e regimes específicos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Sincronizando Módulos e Planos...'))

        # 1. Definição das listas de módulos por perfil (Base para herança)
        # ----------------------------------------------------------------
        modulos_comercio = ['vendas', 'produtos', 'clientes', 'fiscal', 'saft']
        modulos_servicos = ['servicos', 'relatorios', 'estoque', 'fornecedores', 'compras', 'site']
        
        # Herança progressiva para os planos de nível
        modulos_demo = modulos_comercio # Demo foca no básico de comércio
        modulos_basic = list(set(modulos_demo + ['financeiro', 'funcionarios']))
        modulos_pro = list(set(modulos_basic + modulos_servicos))
        
        # Misto e Enterprise
        modulos_mistos = list(set(modulos_comercio + modulos_servicos))
        modulos_enterprise = list(Modulo.objects.all().values_list('slug', flat=True))

        # 2. Estrutura de dados unificada dos planos
        # ----------------------------------------------------------------
        planos_config = [
            {
                'nome': 'Demo',
                'preco': Decimal('0.00'),
                'usuarios': 2,
                'produtos': 10,
                'desc': 'Plano de teste gratuito para avaliação.',
                'slugs': modulos_demo
            },
            {
                'nome': 'Basic',
                'preco': Decimal('5000.00'),
                'usuarios': 5,
                'produtos': 350,
                'desc': 'Essencial para pequenos negócios em crescimento.',
                'slugs': modulos_basic
            },
            {
                'nome': 'Professional',
                'preco': Decimal('35000.00'),
                'usuarios': 15,
                'produtos': 2000,
                'desc': 'Gestão completa e avançada para empresas.',
                'slugs': modulos_pro
            },
            {
                'nome': 'Enterprise',
                'preco': Decimal('0.00'), # Sob negociação
                'usuarios': 9999,
                'produtos': None, # Ilimitado
                'desc': 'Solução personalizada para grandes operações.',
                'slugs': modulos_enterprise
            },
            {
                'nome': 'Comércio',
                'preco': Decimal('10000.00'),
                'usuarios': 5,
                'produtos': 600,
                'desc': 'Plano específico para regime de Comércio.',
                'slugs': modulos_comercio
            },
            {
                'nome': 'Serviços',
                'preco': Decimal('10000.00'),
                'usuarios': 20,
                'produtos': None,
                'desc': 'Plano específico para prestadores de Serviços.',
                'slugs': modulos_servicos
            },
            {
                'nome': 'Misto',
                'preco': Decimal('20000.00'),
                'usuarios': 5,
                'produtos': 2000,
                'desc': 'Ideal para empresas com regime Misto.',
                'slugs': modulos_mistos
            },
            {
                'nome': 'Elite Bypass',
                'preco': Decimal('0.00'), # 0.00 fixo, pois a receita vem dos 2%
                'usuarios': 9999,
                'produtos': None, 
                'desc': 'Acesso Total SOTARQ. Sem mensalidade. Comissão de 2% sobre faturação.',
                'slugs': modulos_enterprise #
            },
        ]

        # 3. Execução da persistência no banco de dados
        # ----------------------------------------------------------------
        for p_data in planos_config:
            plano, created = PlanoLicenca.objects.update_or_create(
                nome=p_data['nome'],
                defaults={
                    'preco_mensal': p_data['preco'],
                    'limite_usuarios': p_data['usuarios'],
                    'limite_produtos': p_data['produtos'],
                    'descricao': p_data['desc'],
                    'ativo': True
                }
            )
            
            # Vinculação dos módulos
            modulos_qs = Modulo.objects.filter(slug__in=p_data['slugs'])
            plano.modulos.set(modulos_qs)
            
            acao = "CRIADO" if created else "ATUALIZADO"
            self.stdout.write(self.style.SUCCESS(
                f'[{acao}] Plano: {plano.nome.ljust(15)} | Módulos: {str(modulos_qs.count()).zfill(2)} | Preço: {plano.preco_mensal:>8} Kz'
            ))

        # CORREÇÃO AQUI: De MIGRATE_SUCCESS para SUCCESS
        self.stdout.write(self.style.SUCCESS('Todos os planos SOTARQ foram sincronizados com sucesso.'))