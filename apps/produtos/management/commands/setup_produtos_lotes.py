# apps/produtos/management/commands/setup_produtos_lotes.py
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from apps.core_tenants.tenant_commands import TenantCommand
from apps.fornecedores.models import Fornecedor
from apps.produtos.models import Categoria, Fabricante, Lote, Produto

D2 = Decimal('0.01')


def q(v):
    return Decimal(v).quantize(D2, rounding=ROUND_HALF_UP)


MARCAS = ['Kianda', 'Mussulo', 'Baobá', 'Palanca', 'Imbondeiro', 'Calulu',
          'Welwitschia', 'Maiombe', 'Kwanza', 'Okavango', 'Namib', 'Sumbe']

FABRICANTES = ['Kianda Industrial', 'Mussulo Labs', 'Baobá Manufacturas', 'Palanca Foods',
               'Imbondeiro Tools', 'Calulu Tech', 'Maiombe Cosmética', 'Kwanza Químicos']

# categoria: (preço mín. custo, preço máx. custo, artigos, variantes)  — valores em Kz
CATALOGO = {
    'Medicamentos': (500, 8000,
        ['Paracetamol', 'Ibuprofeno', 'Amoxicilina', 'Omeprazol', 'Loratadina', 'Vitamina C',
         'Diclofenac', 'Metformina', 'Azitromicina', 'Cetirizina', 'Ácido Fólico', 'Soro Oral'],
        ['500mg 20 comp', '250mg 30 comp', '1g 10 comp', 'Xarope 120ml', 'Gotas 20ml', '10mg 30 comp']),
    'Cosmética e Higiene': (800, 25000,
        ['Creme Hidratante', 'Protetor Solar', 'Shampoo', 'Condicionador', 'Sabonete Líquido',
         'Desodorizante', 'Pasta de Dentes', 'Loção Corporal', 'Gel de Banho', 'Perfume',
         'Batom', 'Base Facial'],
        ['50ml', '100ml', '200ml', '400ml', '500ml', '1L']),
    'Bebidas': (150, 3500,
        ['Água Mineral', 'Sumo de Laranja', 'Refrigerante Cola', 'Cerveja', 'Vinho Tinto',
         'Bebida Energética', 'Chá Gelado', 'Sumo de Manga', 'Água Tónica', 'Leite UHT'],
        ['33cl', '50cl', '1L', '1.5L', 'Pack 6', 'Pack 12']),
    'Mercearia': (300, 9000,
        ['Arroz', 'Feijão', 'Açúcar', 'Óleo Alimentar', 'Massa Esparguete', 'Farinha de Trigo',
         'Sal', 'Fuba de Milho', 'Atum em Lata', 'Leite em Pó', 'Café', 'Molho de Tomate'],
        ['500g', '1kg', '2kg', '5kg', '1L', 'Pack 6']),
    'Limpeza': (400, 12000,
        ['Detergente', 'Lixívia', 'Desinfetante', 'Sabão em Pó', 'Amaciador', 'Limpa Vidros',
         'Esponja', 'Sacos do Lixo', 'Papel Higiénico', 'Toalhitas'],
        ['500ml', '1L', '2L', '5L', 'Pack 4', 'Pack 12']),
    'Ferramentas': (2000, 120000,
        ['Chave de Fendas', 'Martelo', 'Alicate', 'Berbequim', 'Serra Manual', 'Fita Métrica',
         'Chave Inglesa', 'Rebarbadora', 'Nível de Bolha', 'Jogo de Chaves', 'Lanterna',
         'Extensão Elétrica'],
        ['Pro', 'Standard', 'Compacto', 'Industrial', 'Kit', 'Profissional']),
    'Eletrónica e Acessórios': (3000, 450000,
        ['Carregador USB', 'Cabo HDMI', 'Auscultadores', 'Powerbank', 'Rato Sem Fios', 'Teclado',
         'Pen Drive', 'Disco Externo', 'Candeeiro LED', 'Adaptador'],
        ['Preto', 'Branco', 'Pro', 'Mini', 'Plus', 'Max']),
    'Papelaria': (100, 15000,
        ['Caderno A4', 'Esferográfica', 'Marcador', 'Resma de Papel A4', 'Agrafador',
         'Pasta de Arquivo', 'Cola', 'Tesoura', 'Calculadora', 'Mochila Escolar'],
        ['Pack 10', 'Pack 50', 'Azul', 'Preto', 'Grande', 'Pequeno']),
    'Peças e Lubrificantes': (1500, 90000,
        ['Óleo de Motor', 'Filtro de Óleo', 'Filtro de Ar', 'Velas de Ignição', 'Pastilhas de Travão',
         'Bateria 12V', 'Correia de Distribuição', 'Líquido de Refrigeração', 'Lâmpada Automóvel',
         'Escovas Limpa-Vidros'],
        ['Universal', 'Premium', 'Standard', '1L', '4L', 'Heavy Duty']),
}


class Command(TenantCommand):
    help = "Cria produtos de teste (prefixo TST-) com lotes, no tenant indicado."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--quantidade', type=int, default=1200, help="Nº de produtos (default 1200)")
        parser.add_argument('--lotes-max', type=int, default=3, help="Máx. de lotes por produto (default 3)")
        parser.add_argument('--com-vencidos', action='store_true',
                            help="Inclui ~3%% de lotes já vencidos (testar bloqueios/alertas)")
        parser.add_argument('--com-movimentacoes', action='store_true',
                            help="Cria também MovimentacaoEstoque de entrada por lote (requer --usuario)")
        parser.add_argument('--usuario', help="username que fica como autor das movimentações")

    def handle_tenant(self, *args, **options):
        rng = self.rng
        qtd = options['quantidade']
        hoje = timezone.localdate()

        user = None
        if options['com_movimentacoes']:
            if not options['usuario']:
                raise CommandError("--com-movimentacoes requer --usuario <username>.")
            try:
                user = get_user_model().objects.get(username=options['usuario'])
            except get_user_model().DoesNotExist:
                raise CommandError(f"Utilizador '{options['usuario']}' não existe.")

        # IVA: id 1 (o default do modelo) ou a primeira taxa existente
        Taxa = apps.get_model('fiscal', 'TaxaIVAAGT')
        taxa = Taxa.objects.filter(pk=1).first() or Taxa.objects.first()
        if taxa is None:
            self.stdout.write(self.style.WARNING(
                "Sem TaxaIVAAGT no tenant: produtos ficam sem taxa de IVA (rever antes de faturar)."))

        fornecedores = list(Fornecedor.objects.filter(ativo=True, bloqueado=False))
        if not fornecedores:
            self.stdout.write(self.style.WARNING(
                "Sem fornecedores: corra setup_fornecedores primeiro para ligar os produtos."))

        fabricantes = [Fabricante.objects.get_or_create(nome=n, defaults={'origem': 'Angola'})[0]
                       for n in FABRICANTES]
        categorias = {n: Categoria.objects.get_or_create(nome=n, defaults={'codigo': n[:3].upper()})[0]
                      for n in CATALOGO}
        nomes_cat = list(CATALOGO)

        internos = set(Produto.objects.filter(codigo_interno__startswith='TST-')
                       .values_list('codigo_interno', flat=True))
        barras = set(Produto.objects.filter(codigo_barras__startswith='600')
                     .values_list('codigo_barras', flat=True))

        specs = []  # (produto, [dados de lotes])
        for i in range(1, qtd + 1):
            interno, barra = f'TST-{i:05d}', f'600{i:010d}'
            if interno in internos or barra in barras:
                continue

            cat_nome = nomes_cat[(i - 1) % len(nomes_cat)]
            lo, hi, artigos, variantes = CATALOGO[cat_nome]
            nome = f"{rng.choice(artigos)} {rng.choice(MARCAS)} {rng.choice(variantes)}"

            custo = q(max(lo, round(rng.uniform(lo, hi) / 50) * 50))
            venda = q(custo * (Decimal('1') + q(rng.uniform(15, 60)) / Decimal('100')))
            margem = q((venda - custo) / custo * Decimal('100'))
            minimo = rng.randint(5, 20)

            # Cenário de stock: 3% zerado, 7% abaixo do mínimo, resto normal
            roll = rng.random()
            lotes = []
            for n in range(rng.randint(1, options['lotes_max'])):
                if roll < 0.03:
                    atual = 0
                elif roll < 0.10:
                    atual = rng.randint(1, max(1, minimo - 1))
                else:
                    atual = rng.randint(20, 400)

                r = rng.random()
                if options['com_vencidos'] and r < 0.03:
                    validade = hoje - timedelta(days=rng.randint(1, 180))
                elif r < 0.12:
                    validade = hoje + timedelta(days=rng.randint(3, 30))     # a vencer
                else:
                    validade = hoje + timedelta(days=rng.randint(60, 1000))

                lotes.append(dict(
                    numero_lote=f"LT{hoje:%y%m}-{i:05d}-{n + 1}",
                    data_validade=validade,
                    quantidade_inicial=atual + rng.randint(0, 100) if atual else rng.randint(50, 100),
                    quantidade_atual=atual,
                    preco_custo_lote=q(custo * Decimal(str(rng.uniform(0.95, 1.05)))),
                ))

            produto = Produto(
                categoria=categorias[cat_nome],
                fornecedor=rng.choice(fornecedores) if fornecedores else None,
                fabricante=rng.choice(fabricantes),
                codigo_interno=interno,
                codigo_barras=barra,
                nome_produto=nome,
                nome_comercial=nome,
                taxa_iva=taxa,
                desconto_percentual=Decimal(rng.choice([0, 0, 0, 0, 5, 10])),
                estoque_atual=sum(l['quantidade_atual'] for l in lotes),
                estoque_minimo=minimo,
                estoque_maximo=rng.randint(200, 1000),
                preco_custo=custo,
                preco_venda=venda,
                margem_lucro=margem,
                ativo=True,
            )
            specs.append((produto, lotes))

        if not specs:
            self.stdout.write("Nada a criar: todos os produtos TST-* pedidos já existem.")
            return

        with transaction.atomic():
            Produto.objects.bulk_create([p for p, _ in specs], batch_size=500)

            lotes_objs = [Lote(produto=p, **l) for p, ls in specs for l in ls]
            Lote.objects.bulk_create(lotes_objs, batch_size=1000)

            if user:
                from apps.estoque.models import MovimentacaoEstoque
                MovimentacaoEstoque.objects.bulk_create([
                    MovimentacaoEstoque(produto=l.produto, usuario=user, tipo='entrada',
                                        quantidade=l.quantidade_atual,
                                        motivo='Carga inicial (dados de teste)')
                    for l in lotes_objs if l.quantidade_atual > 0
                ], batch_size=1000)

        self.stdout.write(self.style.SUCCESS(
            f"Produtos: {len(specs)} criados | Lotes: {len(lotes_objs)} criados."))