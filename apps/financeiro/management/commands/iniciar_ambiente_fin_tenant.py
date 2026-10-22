"""Inicializa os dados-base financeiros de um tenant, sem criar movimentos fictícios.

Uso:
    python manage.py iniciar_ambiente_fin_tenant --schema=mundoemaquinas

O comando é idempotente: repeti-lo não duplica as categorias, centros de custo,
contas do PGC, conta de caixa nem configuração fiscal que já existam.
"""
from __future__ import annotations

import re
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.financeiro.data.plano_contas_pgc import (
    CATEGORIAS_FINANCEIRAS,
    CENTROS_CUSTO,
    CLASSES_PGC,
    CONTAS_PGC,
)


SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _DryRunRollback(Exception):
    """Força rollback limpo para simular a inicialização sem persistir dados."""


class Command(BaseCommand):
    help = "Cria configurações e dados-base financeiros para um tenant específico."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema", required=True,
            help="Nome exacto do schema/tenant, por exemplo --schema=mundoemaquinas.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Executa os passos dentro de uma transacção que será revertida.",
        )

    def handle(self, *args, **options):
        schema = (options.get("schema") or "").strip()
        if not schema or not SCHEMA_RE.fullmatch(schema):
            raise CommandError("Schema inválido. Use --schema=<nome_do_schema>.")
        if schema.lower() == "public":
            raise CommandError("Por segurança, este comando não pode inicializar o schema 'public'.")

        try:
            from django_tenants.utils import get_tenant_model, schema_context
        except ImportError as exc:
            raise CommandError("django-tenants não está instalado ou configurado.") from exc

        # Confirma o tenant no schema público antes de mudar de schema.
        try:
            tenant_model = get_tenant_model()
        except Exception as exc:
            raise CommandError(f"Não foi possível obter o modelo de tenant: {exc}") from exc
        try:
            tenant_model.objects.get(schema_name=schema)
        except tenant_model.DoesNotExist as exc:
            raise CommandError(f"Não existe tenant registado com schema '{schema}'.") from exc
        except Exception as exc:
            raise CommandError(f"Não foi possível validar o tenant '{schema}': {exc}") from exc

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nInicialização financeira do tenant: {schema}\n"
        ))

        with schema_context(schema):
            if connection.schema_name != schema:
                raise CommandError(
                    f"O schema activo ({connection.schema_name}) não corresponde a '{schema}'."
                )
            try:
                with transaction.atomic():
                    self.stats = defaultdict(lambda: {"criados": 0, "existentes": 0})
                    self._inicializar_tenant()
                    self._mostrar_resumo()
                    if options.get("dry_run"):
                        raise _DryRunRollback
            except _DryRunRollback:
                self.stdout.write(self.style.WARNING(
                    "DRY RUN: transacção revertida; nenhuma alteração foi persistida."
                ))

        if not options.get("dry_run"):
            self.stdout.write(self.style.SUCCESS(
                "\nAmbiente financeiro inicializado. Pode agora editar/adicionar contas e categorias no Admin."
            ))

    def _contabilizar(self, secao, criado):
        self.stats[secao]["criados" if criado else "existentes"] += 1

    def _criar_plano_contas(self):
        from apps.financeiro.models import PlanoConta

        dados = list(CLASSES_PGC) + list(CONTAS_PGC)
        codigos = {codigo for codigo, _ in dados}
        codigos_com_filhos = set()
        for codigo in codigos:
            if "." in codigo:
                codigos_com_filhos.add(codigo.rsplit(".", 1)[0])
            elif len(codigo) > 1:
                codigos_com_filhos.add(codigo[0])

        # Primeiro classes e contas superiores, depois as subcontas.
        dados.sort(key=lambda item: (item[0].count("."), len(item[0]), item[0]))
        for codigo, nome in dados:
            conta_pai = None
            if "." in codigo:
                codigo_pai = codigo.rsplit(".", 1)[0]
                conta_pai = PlanoConta.objects.filter(codigo=codigo_pai).first()
            elif len(codigo) == 2:
                conta_pai = PlanoConta.objects.filter(codigo=codigo[0]).first()

            natureza = self._natureza_pgc(codigo)
            if len(codigo) == 1:
                agrupamento = "GR"
            elif codigo in codigos_com_filhos:
                agrupamento = "GA"
            else:
                agrupamento = "GM"

            _, criado = PlanoConta.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "nome": nome,
                    "classe": codigo[0],
                    "natureza": natureza,
                    "conta_pai": conta_pai,
                    "agrupamento_saft": agrupamento,
                    "ativa": True,
                    "aceita_lancamentos": codigo not in codigos_com_filhos,
                    "origem": "PGC Angola — Decreto n.º 82/01",
                },
            )
            self._contabilizar("Plano de contas PGC", criado)

    @staticmethod
    def _natureza_pgc(codigo):
        if len(codigo) == 1:
            return {
                "1": "ativo", "2": "ativo", "3": "mista", "4": "ativo",
                "5": "patrimonio_liquido", "6": "receita", "7": "custo", "8": "resultado",
            }.get(codigo, "mista")
        if codigo.startswith("21") or codigo.startswith("71") or codigo.startswith("72") \
                or codigo.startswith("73") or codigo.startswith("75") or codigo.startswith("76") \
                or codigo.startswith("78") or codigo.startswith("79"):
            return "custo"
        if codigo.startswith("31"):
            return "ativo"
        if codigo.startswith("32") or codigo.startswith("33") or codigo.startswith("39"):
            return "passivo"
        if codigo.startswith("34") or codigo.startswith("35") or codigo.startswith("36") \
                or codigo.startswith("37"):
            return "mista"
        if codigo.startswith("51") or codigo.startswith("52") or codigo.startswith("53") \
                or codigo.startswith("54") or codigo.startswith("55") or codigo.startswith("56") \
                or codigo.startswith("57") or codigo.startswith("58"):
            return "patrimonio_liquido"
        if codigo.startswith("61") or codigo.startswith("62") or codigo.startswith("63") \
                or codigo.startswith("64") or codigo.startswith("65") or codigo.startswith("66") \
                or codigo.startswith("67") or codigo.startswith("68") or codigo.startswith("69"):
            return "receita"
        if codigo.startswith("8"):
            return "resultado"
        return "ativo"

    def _criar_categorias(self):
        from apps.financeiro.models import CategoriaFinanceira, PlanoConta

        for nome, tipo, codigo_conta in CATEGORIAS_FINANCEIRAS:
            conta = PlanoConta.objects.filter(codigo=codigo_conta).first()
            defaults = {"ativa": True}
            # Só define o mapeamento inicial na criação; não substitui escolhas manuais já feitas.
            if conta is not None:
                defaults["plano_contas"] = conta
            _, criado = CategoriaFinanceira.objects.get_or_create(
                nome=nome,
                tipo=tipo,
                defaults=defaults,
            )
            self._contabilizar("Categorias financeiras", criado)

    def _criar_centros_custo(self):
        from apps.financeiro.models import CentroCusto

        for codigo, nome, descricao in CENTROS_CUSTO:
            _, criado = CentroCusto.objects.get_or_create(
                codigo=codigo,
                defaults={"nome": nome, "descricao": descricao, "ativo": True},
            )
            self._contabilizar("Centros de custo", criado)

    def _criar_caixa_principal(self):
        from apps.financeiro.models import ContaBancaria

        caixa = ContaBancaria.objects.filter(nome="Caixa Principal", tipo_conta="caixa").first()
        if caixa:
            criado = False
        else:
            ja_existe_principal = ContaBancaria.objects.filter(conta_principal=True).exists()
            caixa = ContaBancaria.objects.create(
                nome="Caixa Principal",
                banco="Caixa físico",
                agencia="N/A",
                conta="CAIXA-PRINCIPAL",
                digito="",
                tipo_conta="caixa",
                saldo_inicial=0,
                saldo_atual=0,
                limite_credito=0,
                ativa=True,
                conta_principal=not ja_existe_principal,
                permite_saldo_negativo=False,
                observacoes=(
                    "Conta interna de caixa criada pelo comando de inicialização. "
                    "Saldo inicial zero; registe o saldo real de abertura antes de operar."
                ),
            )
            criado = True

        # Não desactiva a conta principal bancária que o tenant já possa ter.
        self._contabilizar("Caixa principal", criado)

    def _criar_configuracao_imposto(self):
        try:
            from apps.fiscal.models import ConfiguracaoImposto
        except (ImportError, RuntimeError) as exc:
            self.stdout.write(self.style.WARNING(
                f"Configuração fiscal omitida: modelo ConfiguracaoImposto indisponível ({exc})."
            ))
            return

        config = ConfiguracaoImposto.objects.first()
        criado = False
        if config is None:
            # Deixa o modelo aplicar os seus próprios defaults; não cria impostos,
            # valores a pagar nem taxas diferentes das que o projecto já definiu.
            config = ConfiguracaoImposto.objects.create()
            criado = True

        centro_fiscal = None
        try:
            from apps.financeiro.models import CentroCusto
            centro_fiscal = CentroCusto.objects.filter(codigo="FIS").first()
        except Exception:
            pass

        if centro_fiscal and not config.centro_custo_impostos_id:
            config.centro_custo_impostos = centro_fiscal
            config.save(update_fields=["centro_custo_impostos"])

        self._contabilizar("Configuração fiscal", criado)

    def _inicializar_tenant(self):
        # A ordem respeita as FKs e permite que as categorias apontem para contas PGC.
        self._criar_plano_contas()
        self._criar_centros_custo()
        self._criar_categorias()
        self._criar_caixa_principal()
        self._criar_configuracao_imposto()

        # Verificação adicional: contas financeiras não devem ficar sem categoria PGC
        # por falha no seed. As linhas são opcionais até à escolha do utilizador.
        from apps.financeiro.models import PlanoConta
        if not PlanoConta.objects.filter(codigo="45.1.1").exists():
            raise CommandError("A conta PGC 45.1.1 (Caixa principal) não foi criada.")

    def _mostrar_resumo(self):
        self.stdout.write("\nResumo do ambiente financeiro:")
        for secao in (
            "Plano de contas PGC", "Centros de custo", "Categorias financeiras",
            "Caixa principal", "Configuração fiscal",
        ):
            dados = self.stats.get(secao, {"criados": 0, "existentes": 0})
            self.stdout.write(
                f"  {secao}: {dados['criados']} criados; {dados['existentes']} já existentes"
            )

        self.stdout.write(
            "\nNão foram criados saldos contabilísticos, vendas, movimentos, contas a pagar/receber "
            "ou obrigações fiscais fictícias."
        )
