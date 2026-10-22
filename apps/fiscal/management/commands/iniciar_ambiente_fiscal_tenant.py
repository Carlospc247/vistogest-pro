"""Inicializa os catálogos fiscais legais num schema tenant.

Uso:
    python manage.py iniciar_ambiente_fiscal_tenant --schema=mundoemaquinas
    python manage.py iniciar_ambiente_fiscal_tenant --schema=mundoemaquinas --atualizar-referencias

Seguro para reexecução: por defeito cria apenas registos em falta e preserva edições manuais.
"""
import logging
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q

logger = logging.getLogger("fiscal.ambiente_tenant")


class Command(BaseCommand):
    help = "Cria os catálogos fiscais de referência AGT para um tenant específico."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema", required=True, type=str,
            help="Schema exacto do tenant (ex.: mundoemaquinas).",
        )
        parser.add_argument(
            "--atualizar-referencias", action="store_true",
            help="Sincroniza descrições/taxas de referência existentes com as tabelas incluídas no pacote. "
                 "Use apenas quando quiser descartar alterações manuais aos catálogos legais.",
        )

    def handle(self, *args, **options):
        schema = options["schema"].strip()
        if not schema or not re.fullmatch(r"[A-Za-z0-9_]+", schema):
            raise CommandError("Nome de schema inválido. Use apenas letras, números e underscore.")

        try:
            from django_tenants.utils import get_tenant_model, schema_context
        except ImportError as exc:
            raise CommandError("django-tenants não está instalado ou configurado.") from exc

        # A tabela de tenants normalmente vive no schema public.
        TenantModel = get_tenant_model()
        try:
            if hasattr(connection, "set_schema_to_public"):
                connection.set_schema_to_public()
            tenant = TenantModel.objects.get(schema_name=schema)
        except TenantModel.DoesNotExist as exc:
            raise CommandError(f"Não existe tenant com schema '{schema}'.") from exc
        except Exception as exc:
            raise CommandError(f"Não foi possível validar o tenant/schema '{schema}': {exc}") from exc

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nInicialização fiscal AGT\nTenant: {getattr(tenant, 'name', schema)}\nSchema: {schema}\n"
        ))

        try:
            with schema_context(schema), transaction.atomic():
                report = self._initializar(bool(options["atualizar_referencias"]))
        except Exception as exc:
            logger.exception("Falha a inicializar ambiente fiscal para schema %s", schema)
            raise CommandError(
                "A inicialização foi cancelada. Confirme que as migrações da app fiscal foram aplicadas "
                f"neste schema e verifique a mensagem: {exc}"
            ) from exc

        self.stdout.write("")
        for label, counts in report.items():
            self.stdout.write(f"  {label}: {counts['criados']} criados; {counts['existentes']} existentes; {counts['atualizados']} actualizados")
        self.stdout.write(self.style.SUCCESS("\nAmbiente fiscal de referência preparado com sucesso."))
        self.stdout.write(
            self.style.WARNING(
                "Não foram criadas chaves, credenciais, NIF, nem séries autorizadas pela AGT: "
                "estes dados são específicos do contribuinte e têm de ser fornecidos/emitidos legitimamente."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "A taxa especial de Cabinda não foi semeada: a Lei n.º 14/23 consultada indica 1%, mas o portal actual da AGT indica 2%, "
                "e o modelo não representa a região taxCountryRegion='AO-CAB'. Confirmar com a AGT antes de implementar."
            )
        )

    def _initializar(self, atualizar):
        from apps.fiscal.models import TaxaIVAAGT, AssinaturaDigital
        from apps.fiscal.models_referencia import CAE, ImpostoSelo, ImpostoEspecialConsumo
        from apps.fiscal.data.referencias_agt import (
            CAE_DADOS, IEC_DADOS, IMPOSTO_SELO_DADOS, ISENCOES_DADOS, IVA_TAXAS_DADOS,
        )

        report = {}
        report["CAE (Tabela 1)"] = self._seed_simple(
            CAE, CAE_DADOS, lookup_index=0,
            build=lambda r: ({"codigo": r[0]}, {
                "descricao": r[1],
                "referencia_legal": "Decreto Executivo n.º 683/25 — Tabela 1; CAE-Rev.2 (INE)",
                "ativo": True,
            }), atualizar=atualizar,
        )

        report["IEC (Tabela 2)"] = self._seed_simple(
            ImpostoEspecialConsumo, IEC_DADOS, lookup_index=0,
            build=lambda r: ({"codigo_pautal": r[0]}, {
                "designacao": r[1], "unidade_medida": r[2],
                "taxa_percentual": Decimal(str(r[3]).replace(",", ".")),
                "referencia_legal": "Decreto Executivo n.º 683/25 — Tabela 2 (IEC)", "ativo": True,
            }), atualizar=atualizar,
        )

        report["Imposto do Selo (Tabela 3)"] = self._seed_selo(ImpostoSelo, IMPOSTO_SELO_DADOS, atualizar)

        report["Taxas de IVA legais"] = self._seed_taxas_iva(TaxaIVAAGT, IVA_TAXAS_DADOS, atualizar)
        report["Isenções IVA/IS/IEC e não sujeição (Tabelas 4–6)"] = self._seed_isencoes(TaxaIVAAGT, ISENCOES_DADOS, atualizar)

        # Configuração singleton sem credenciais/chaves fictícias. A empresa completa-a depois.
        antes = AssinaturaDigital.objects.filter(pk=1).exists()
        AssinaturaDigital.get_solo()
        report["Assinatura fiscal (base vazia)"] = {
            "criados": 0 if antes else 1, "existentes": 1 if antes else 0, "atualizados": 0,
        }
        return report

    def _seed_simple(self, model, rows, lookup_index, build, atualizar):
        counts = {"criados": 0, "existentes": 0, "atualizados": 0}
        for row in rows:
            lookup, defaults = build(row)
            obj = model.objects.filter(**lookup).first()
            if obj is None:
                model.objects.create(**lookup, **defaults)
                counts["criados"] += 1
            elif atualizar:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value); changed = True
                if changed:
                    obj.save(update_fields=list(defaults.keys()) + ["updated_at"] if hasattr(obj, "updated_at") else list(defaults.keys()))
                    counts["atualizados"] += 1
                else:
                    counts["existentes"] += 1
            else:
                counts["existentes"] += 1
        return counts

    @staticmethod
    def _parse_taxa_selo(raw):
        """Transforma texto de tabela (por ex. 0,3% ou 1.000,00 Kz) em dados auxiliares."""
        raw = str(raw).strip()
        if "%" in raw:
            number = raw.split("%", 1)[0].strip().replace(" ", "").replace(",", ".")
            try:
                return "percentual", Decimal(number), None, "AOA"
            except InvalidOperation:
                return "nao_definido", None, None, "AOA"
        if re.search(r"\bKz\b", raw, flags=re.I):
            number = re.sub(r"\s*Kz\s*$", "", raw, flags=re.I).strip()
            number = number.replace(".", "").replace(",", ".").replace(" ", "")
            try:
                return "fixo", None, Decimal(number), "AOA"
            except InvalidOperation:
                return "nao_definido", None, None, "AOA"
        return "nao_definido", None, None, "AOA"

    def _seed_selo(self, model, rows, atualizar):
        counts = {"criados": 0, "existentes": 0, "atualizados": 0}
        for verba, descricao, taxa_original in rows:
            tipo, percentual, valor_fixo, moeda = self._parse_taxa_selo(taxa_original)
            lookup = {"verba": verba}
            defaults = {
                "descricao": descricao, "taxa_original": taxa_original, "tipo_taxa": tipo,
                "taxa_percentual": percentual, "valor_fixo": valor_fixo, "moeda": moeda,
                "referencia_legal": "Decreto Executivo n.º 683/25 — Tabela 3 (Imposto do Selo)",
                "ativo": True,
            }
            obj = model.objects.filter(**lookup).first()
            if obj is None:
                model.objects.create(**lookup, **defaults); counts["criados"] += 1
            elif atualizar:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value); changed = True
                if changed:
                    update_fields = list(defaults.keys())
                    if hasattr(obj, "updated_at"): update_fields.append("updated_at")
                    obj.save(update_fields=update_fields); counts["atualizados"] += 1
                else: counts["existentes"] += 1
            else: counts["existentes"] += 1
        return counts

    def _seed_taxas_iva(self, model, rows, atualizar):
        counts = {"criados": 0, "existentes": 0, "atualizados": 0}
        for row in rows:
            lookup = {
                "tax_type": row["tax_type"], "tax_code": row["tax_code"],
                "tax_percentage": Decimal(row["tax_percentage"]),
                "nome": row["nome"],
            }
            reason = row.get("exemption_reason")
            query = model.objects.filter(**lookup)
            query = query.filter((Q(exemption_reason__isnull=True) | Q(exemption_reason="")) if reason is None else Q(exemption_reason=reason))
            # `nome` faz parte da identidade do registo para permitir duas
            # regras legais com a mesma percentagem/código, mas âmbitos diferentes.
            # Não o repetir em defaults: isso causaria TypeError por keyword duplicada.
            defaults = {
                "codigo_pais": "AO",
                "legislacao_referencia": row["legislacao_referencia"],
                "ativo": True,
            }
            obj = query.order_by("pk").first()
            if obj is None:
                model.objects.create(**lookup, exemption_reason=reason, **defaults); counts["criados"] += 1
            elif atualizar:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value); changed = True
                if changed:
                    update_fields = list(defaults.keys())
                    if hasattr(obj, "updated_at"): update_fields.append("updated_at")
                    obj.save(update_fields=update_fields); counts["atualizados"] += 1
                else: counts["existentes"] += 1
            else: counts["existentes"] += 1
        return counts

    def _seed_isencoes(self, model, rows, atualizar):
        counts = {"criados": 0, "existentes": 0, "atualizados": 0}
        for item in rows:
            codigo = item["codigo"]
            categoria = item["categoria"]
            if codigo == "M18B":  # compatibilidade de 3 caracteres definida pelo projecto/notificação
                codigo = "M18"
            if codigo == "M00":
                tax_type, tax_code, percent = "IVA", "OUT", Decimal("7.00")
            elif codigo in ("M02", "M04"):
                # O catálogo interno/SAF-T mantém NS; o gerador da API converte TaxCode para ISE.
                tax_type, tax_code, percent = "NS", "NS", Decimal("0.00")
            elif categoria == "IVA":
                tax_type, tax_code, percent = "IVA", "ISE", Decimal("0.00")
            elif categoria == "IS":
                tax_type, tax_code, percent = "IS", "ISE", Decimal("0.00")
            else:
                tax_type, tax_code, percent = "IEC", "ISE", Decimal("0.00")

            # Taxa de M00 já é incluída no bloco IVA_TAXAS_DADOS, evita duplicação.
            if codigo == "M00":
                continue
            nome_curto = re.sub(r"\s+", " ", item["descricao"]).strip()
            nome = (f"{codigo} — {nome_curto}")[:100]
            lookup = {
                "tax_type": tax_type, "tax_code": tax_code,
                "tax_percentage": percent, "exemption_reason": codigo,
            }
            defaults = {
                "nome": nome, "codigo_pais": "AO", "legislacao_referencia": item["menção"][:255], "ativo": True,
            }
            obj = model.objects.filter(**lookup).order_by("pk").first()
            if obj is None:
                model.objects.create(**lookup, **defaults); counts["criados"] += 1
            elif atualizar:
                changed = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value); changed = True
                if changed:
                    update_fields = list(defaults.keys())
                    if hasattr(obj, "updated_at"): update_fields.append("updated_at")
                    obj.save(update_fields=update_fields); counts["atualizados"] += 1
                else: counts["existentes"] += 1
            else: counts["existentes"] += 1
        return counts
