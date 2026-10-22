# apps/servicos/management/commands/setup_servicos.py
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import product as combos

from django.apps import apps
from django.core.management.base import CommandError
from django.db import transaction

from apps.core_tenants.tenant_commands import TenantCommand
from apps.produtos.models import Categoria
from apps.servicos.models import Servico

D2 = Decimal('0.01')

# categoria: (durações possíveis em min, (preço mín., preço máx.) em Kz, serviços-base)
CATALOGO = {
    'Serviços Técnicos': ([30, 60, 90, 120, 180], (5000, 150000),
        ['Manutenção Preventiva', 'Reparação', 'Instalação', 'Diagnóstico', 'Calibração',
         'Inspeção Técnica', 'Montagem', 'Configuração']),
    'Serviços de Consultoria': ([60, 90, 120], (10000, 250000),
        ['Consultoria', 'Auditoria', 'Formação', 'Avaliação', 'Aconselhamento', 'Planeamento']),
    'Serviços de Saúde e Bem-estar': ([15, 30, 45, 60], (2000, 60000),
        ['Consulta', 'Medição de Tensão', 'Teste Rápido', 'Massagem',
         'Aconselhamento Farmacêutico', 'Avaliação Nutricional']),
    'Serviços de Limpeza': ([60, 120, 240], (4000, 90000),
        ['Limpeza Geral', 'Limpeza Profunda', 'Desinfeção', 'Limpeza de Estofos', 'Limpeza de Vidros']),
    'Serviços de Entrega e Logística': ([30, 60, 120], (1500, 40000),
        ['Entrega Expresso', 'Entrega Programada', 'Recolha', 'Transporte de Carga', 'Montagem no Local']),
}

# variante: multiplicador de preço
VARIANTES = {
    'Básico': 0.8, 'Standard': 1.0, 'Premium': 1.4, 'Express': 1.3, 'Completo': 1.2,
    'ao Domicílio': 1.2, 'Urgente': 1.5, 'Empresarial': 1.3, 'Residencial': 1.0, 'Industrial': 1.5,
    'Mensal': 1.0, 'Trimestral': 2.5, 'Anual': 8.0, 'Pack 3': 2.6, 'Pack 5': 4.2,
    'Pack 10': 8.0, 'Noturno': 1.3, 'Fim de Semana': 1.2, 'VIP': 1.6, 'Económico': 0.7,
}


def q(v):
    return Decimal(v).quantize(D2, rounding=ROUND_HALF_UP)


class Command(TenantCommand):
    help = "Cria serviços de teste (catálogo) no tenant indicado."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--quantidade', type=int, default=500, help="Nº de serviços (default 500, máx. 600)")

    def handle_tenant(self, *args, **options):
        rng = self.rng
        qtd = options['quantidade']

        # taxa_iva é obrigatória (PROTECT) em Servico
        Taxa = apps.get_model('fiscal', 'TaxaIVAAGT')
        taxa = Taxa.objects.filter(pk=1).first() or Taxa.objects.first()
        if taxa is None:
            raise CommandError("Não há nenhuma TaxaIVAAGT neste tenant. Configure o módulo fiscal "
                               "(taxas de IVA) antes de criar serviços.")
        iva = q(getattr(taxa, 'tax_percentage', 0) or 0)

        categorias = {n: Categoria.objects.get_or_create(nome=n, defaults={'codigo': 'SRV'})[0]
                      for n in CATALOGO}

        todos = [(cat, base, var)
                 for cat, (_, _, bases) in CATALOGO.items()
                 for base, var in combos(bases, VARIANTES)]
        if qtd > len(todos):
            raise CommandError(f"Máximo de {len(todos)} serviços únicos; pediu {qtd}.")
        rng.shuffle(todos)

        existentes = set(Servico.objects.values_list('nome', flat=True))
        novos = []
        for cat, base, var in todos[:qtd]:
            nome = f"{base} {var}"
            if nome in existentes:
                continue
            duracoes, (lo, hi), _ = CATALOGO[cat]
            minutos = rng.choice(duracoes)
            preco = max(lo, round(rng.uniform(lo, hi) * VARIANTES[var] / 500) * 500)
            novos.append(Servico(
                nome=nome,
                categoria=categorias[cat],
                duracao_padrao_minutos=minutos,
                duracao_servico_padrao=timedelta(minutes=minutos),
                preco_padrao=q(preco),
                desconto_percentual=Decimal(rng.choice([0, 0, 0, 0, 5, 10, 15])),
                iva_percentual=iva,
                taxa_iva=taxa,
                instrucoes_padrao=f"{base} ({var}). Dados de teste.",
                instrucoes_servico=f"{base} ({var}). Dados de teste.",
                ativo=True,
            ))

        with transaction.atomic():
            Servico.objects.bulk_create(novos, batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f"Serviços: {len(novos)} criados, {qtd - len(novos)} já existiam."))