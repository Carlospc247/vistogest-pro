from django.core.management.base import BaseCommand, CommandError

from django_tenants.utils import (
    get_public_schema_name,
    get_tenant_model,
    schema_context,
)

from apps.fiscal.services.payload_reconciliation_service import (
    PayloadReconciliationService,
)


class Command(BaseCommand):
    help = (
        "Reconcilia DocumentoFiscal e PayloadAGT num tenant. "
        "Por defeito, executa apenas uma simulação, sem persistir alterações."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            required=True,
            help="Schema do tenant que será analisado.",
        )

        parser.add_argument(
            "--grace-minutes",
            type=int,
            default=10,
            help=(
                "Tempo de tolerância, em minutos, antes de sinalizar "
                "documentos sem payload. Valor padrão: 10."
            ),
        )

        parser.add_argument(
            "--aplicar",
            action="store_true",
            help=(
                "Aplica as associações recuperáveis e regista os eventos "
                "de reconciliação."
            ),
        )

    def _validar_schema(self, schema):
        """
        Confirma que o schema corresponde a um tenant registado.

        A consulta ao modelo de tenants é feita no schema público,
        antes de entrar no schema do tenant.
        """
        if not schema:
            raise CommandError(
                "O nome do schema não pode estar vazio."
            )

        if schema.lower() == get_public_schema_name().lower():
            raise CommandError(
                "O schema público não pode ser utilizado nesta operação."
            )

        TenantModel = get_tenant_model()

        with schema_context(get_public_schema_name()):
            existe = TenantModel.objects.filter(
                schema_name=schema
            ).exists()

        if not existe:
            raise CommandError(
                f"Não foi encontrado nenhum tenant registado "
                f"com o schema '{schema}'."
            )

    @staticmethod
    def _contar(resultado, chave):
        """
        Devolve a quantidade de ocorrências de uma chave do relatório.
        """
        valor = resultado.get(chave, [])

        if isinstance(valor, (list, tuple, set)):
            return len(valor)

        try:
            return int(valor or 0)
        except (TypeError, ValueError):
            return 0

    def _apresentar_resultado(self, resultado):
        self.stdout.write("")
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "RELATÓRIO DA RECONCILIAÇÃO AGT"
            )
        )
        self.stdout.write("-" * 48)

        self.stdout.write(
            f"Documentos analisados: "
            f"{resultado.get('documentos_analisados', 0)}"
        )

        indicadores = [
            (
                "documentos_sem_payload",
                "Documentos sem payload",
            ),
            (
                "documentos_reconciliados",
                "Associações recuperáveis/recuperadas",
            ),
            (
                "documentos_com_multiplos_payloads",
                "Documentos com vários payloads",
            ),
            (
                "payloads_orfaos",
                "Envelopes sem associação única",
            ),
            (
                "associacoes_incorrectas",
                "Associações incorrectas",
            ),
            (
                "payloads_preparados_nao_enviados",
                "Payloads preparados ou não enviados",
            ),
            (
                "payloads_resultado_indeterminado",
                "Payloads com resultado indeterminado",
            ),
            (
                "documentos_duplicados_no_payload",
                "Documentos duplicados nos envelopes",
            ),
        ]

        for chave, descricao in indicadores:
            quantidade = self._contar(resultado, chave)

            self.stdout.write(
                f"{descricao}: {quantidade}"
            )

        self.stdout.write("-" * 48)

    def handle(self, *args, **options):
        schema = (options.get("schema") or "").strip()
        grace_minutes = options["grace_minutes"]
        aplicar = options["aplicar"]

        if grace_minutes < 0:
            raise CommandError(
                "--grace-minutes não pode ter um valor negativo."
            )

        # Confirma que o schema pertence a um tenant registado.
        self._validar_schema(schema)

        modo = "APLICAÇÃO" if aplicar else "SIMULAÇÃO"

        self.stdout.write(
            self.style.WARNING(
                f"Modo de execução: {modo}"
            )
        )

        self.stdout.write(
            f"Tenant: {schema}"
        )
        self.stdout.write(
            f"Tempo de tolerância: {grace_minutes} minuto(s)"
        )

        # Toda a reconciliação é executada no schema do tenant.
        with schema_context(schema):
            resultado = PayloadReconciliationService.reconciliar(
                dry_run=not aplicar,
                grace_minutes=grace_minutes,
            )

        self._apresentar_resultado(resultado)

        if aplicar:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reconciliação aplicada com sucesso no tenant '{schema}'."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULAÇÃO CONCLUÍDA: nenhuma alteração foi persistida. "
                    "Use --aplicar para executar as reparações recuperáveis "
                    "e registar os respectivos eventos."
                )
            )

        self.stdout.write("")