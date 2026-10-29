from django.core.management.base import BaseCommand

from apps.licenca.models import Modulo

# FONTE ÚNICA dos módulos. O setup_plano importa esta lista.
# (slug, nome)
MODULOS = [
    ("core_tenants", "Dashboard profissional"),
    ("produtos", "Produtos e Inventário"),
    ("analytics", "Business Intelligence | Auditoria"),
    ("fornecedores", "Gestão de Fornecedores"),
    ("estoque", "Controle de Estoque"),
    ("clientes", "Gestão de Clientes"),
    ("vendas", "Vendas e Faturamento"),
    ("funcionarios", "Recursos Humanos"),
    ("servicos", "Prestação de Serviços"),
    ("financeiro", "Financeiro e Fluxo de Caixa"),
    ("relatorios", "Relatórios Gerenciais"),
    ("configuracoes", "Configurações do Sistema"),
    ("fiscal", "Fiscal e Impostos"),
    ("saft", "Exportação SAF-T"),
    ("compras", "Gestão de Compras"),
    ("comunicacao", "Bate-papos e Interações"),
    ("integracoes", "Integrações"),
    ("site", "Site institucional"),
]
SLUGS_TODOS = [s for s, _ in MODULOS]


class Command(BaseCommand):
    help = "Sincroniza os módulos do sistema (lista MODULOS neste ficheiro é a fonte única)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Sincronizando módulos..."))
        for slug, nome in MODULOS:
            modulo, criado = Modulo.objects.get_or_create(
                slug=slug,
                defaults={"nome": nome, "descricao": f"Acesso ao módulo de {nome}", "ativo": True},
            )
            if criado:
                self.stdout.write(self.style.SUCCESS(f'Módulo "{nome}" criado.'))
            elif modulo.nome != nome:
                antigo, modulo.nome = modulo.nome, nome
                modulo.save(update_fields=["nome"])
                self.stdout.write(self.style.WARNING(f'Módulo "{slug}": nome "{antigo}" -> "{nome}".'))
            else:
                self.stdout.write(f'Módulo "{nome}" já existe.')

        # Módulos na base que já não estão no catálogo: só avisar (nunca apagar).
        orfaos = Modulo.objects.exclude(slug__in=SLUGS_TODOS).values_list("slug", flat=True)
        for slug in orfaos:
            self.stdout.write(self.style.WARNING(
                f'Módulo "{slug}" existe na base mas não está no catálogo — '
                "verifique se algum plano ainda o usa."
            ))
        self.stdout.write(self.style.SUCCESS("Configuração de módulos concluída."))