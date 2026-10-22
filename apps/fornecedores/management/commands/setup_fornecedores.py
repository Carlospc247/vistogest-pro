# apps/fornecedores/management/commands/setup_fornecedores.py
from apps.core_tenants.tenant_commands import TenantCommand
from apps.fornecedores.models import CondicaoPagamento, Fornecedor

CONDICOES = [
    dict(nome='À vista', prazo_dias=0, parcelas=1, intervalo_parcelas=0, desconto_a_vista=3),
    dict(nome='30 dias', prazo_dias=30, parcelas=1, intervalo_parcelas=30),
    dict(nome='60 dias', prazo_dias=60, parcelas=1, intervalo_parcelas=30),
    dict(nome='3x de 30 dias', prazo_dias=90, parcelas=3, intervalo_parcelas=30),
]

# (razão social, categoria, porte, bairro, município)
FORNECEDORES = [
    ('Angola Distribuição e Comércio, Lda', 'distribuidor', 'grande', 'Maianga', 'Luanda'),
    ('Luanda Importações, SA', 'importador', 'grande', 'Talatona', 'Luanda'),
    ('Kianda Atacadista, Lda', 'atacadista', 'medio', 'Viana', 'Viana'),
    ('Mussulo Representações, Lda', 'representante', 'pequeno', 'Ingombota', 'Luanda'),
    ('Baobá Farma Distribuidora, SA', 'laboratorio', 'grande', 'Kilamba', 'Luanda'),
    ('Imbondeiro Materiais Técnicos, Lda', 'distribuidor', 'medio', 'Cazenga', 'Cazenga'),
    ('Palanca Logística e Serviços, Lda', 'prestador_servico', 'medio', 'Benfica', 'Luanda'),
    ('Calulu Eletrónica e Acessórios, Lda', 'importador', 'pequeno', 'Rangel', 'Luanda'),
    ('Cabinda Ferramentas Industriais, SA', 'atacadista', 'grande', 'Cabassango', 'Cabinda'),
    ('Huambo Cooperativa Agrícola, CRL', 'cooperativa', 'micro', 'Calilongue', 'Huambo'),
]


class Command(TenantCommand):
    help = "Cria 10 fornecedores de teste (e condições de pagamento) no tenant indicado."

    def handle_tenant(self, *args, **options):
        condicoes = []
        for c in CONDICOES:
            obj, _ = CondicaoPagamento.objects.get_or_create(nome=c['nome'], defaults=c)
            condicoes.append(obj)

        criados = 0
        for i, (razao, cat, porte, bairro, cidade) in enumerate(FORNECEDORES, start=1):
            slug = razao.split(',')[0].lower().split()[0]
            _, created = Fornecedor.objects.get_or_create(
                nif_bi=f'5400000{i:03d}',            # 10 dígitos (NIF fictício)
                defaults=dict(
                    razao_social=razao,
                    nome_fantasia=razao.split(',')[0],
                    tipo_pessoa='juridica',
                    categoria=cat,
                    porte=porte,
                    endereco=f'Rua {i + 10}',
                    numero=str(i * 7),
                    bairro=bairro,
                    cidade=cidade,
                    provincia='LUA',
                    postal='10000-001',
                    telefone_principal=f'+24492300{i:04d}',
                    whatsapp=f'+24492300{i:04d}',
                    email_principal=f'comercial@{slug}.exemplo.ao',
                    email_financeiro=f'financeiro@{slug}.exemplo.ao',
                    condicao_pagamento_padrao=condicoes[i % len(condicoes)],
                    prazo_entrega_dias=3 + (i % 8),
                    valor_minimo_pedido=50000 * (1 + i % 4),
                    banco_principal='BAI',
                    permite_devolucao=True,
                    ativo=True,
                ),
            )
            criados += created

        self.stdout.write(self.style.SUCCESS(
            f"Fornecedores: {criados} criados, {len(FORNECEDORES) - criados} já existiam."))