from django.core.management.base import CommandError

from apps.core_tenants.tenant_commands import TenantCommand
from apps.financeiro.views import _garantir_formas_padrao
from apps.vendas.models import FormaPagamento


class Command(TenantCommand):
    help = "Cria as formas de pagamento padrão (inativas) no tenant. Use --ativar para ligar algumas."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--ativar", default="",
                            help="Tipos a ativar, separados por vírgula (ex.: dinheiro,transferencia)")

    def handle_tenant(self, *args, **options):
        _garantir_formas_padrao()
        tipos = [t.strip() for t in options["ativar"].split(",") if t.strip()]
        validos = dict(FormaPagamento.FORMA_PAGAMENTO_CHOICES)
        invalidos = [t for t in tipos if t not in validos]
        if invalidos:
            raise CommandError(f"Tipos inválidos: {', '.join(invalidos)}. Válidos: {', '.join(validos)}")
        if tipos:
            FormaPagamento.objects.filter(tipo__in=tipos).update(ativa=True)
        ativas = FormaPagamento.objects.filter(ativa=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"{len(validos)} tipos garantidos; {ativas} ativas."))