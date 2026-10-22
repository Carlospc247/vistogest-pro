"""Gera documentos de ensaio para pré-validação da homologação AGT.

IMPORTANTE
----------
* Não inventa NIF de cliente: usa um cliente real existente ou --cliente-id.
* Usa apenas tipos existentes em DocumentoFiscal.TIPO_DOCUMENTO_CHOICES.
* A numeração/ATCUD são produzidos pelo save() do modelo, nunca atribuídos
  pelo command.
* Cria primeiro em draft, cria linhas reais em DocumentoFiscalLinha e só
  confirma se o operador passar --confirmar-documentos.
* --limpar elimina apenas documentos DRAFT marcados por este command; nunca
  apaga documentos emitidos/confirmados/lançados/pagos.
* O ponto 7 é deliberadamente bloqueado até a AGT esclarecer a semântica de
  CurrencyAmount/GrossTotal/ExchangeRate para o cenário requerido.
* O ponto 8 só é criado se a hora local real da execução for <= 10:00. Não
  falsifica created_at/SystemEntryDate nem hora_emissao (auto_now_add).

Executar, por exemplo:
    python manage.py gerar_documentos_homologacao --schema=mundoemaquinas
    python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --confirmar-documentos --usar-dois-meses
    python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --ponto=5 --confirmar-documentos

Os documentos com a série HOM26 são amostras de homologação. Executar apenas
num tenant/schema de ensaio dedicado; não misturar com a facturação normal.
"""
from __future__ import annotations

import json
import logging
from datetime import date, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("fiscal.homologacao")
LOTE = "AGT-0000497-01180000-2026"
SERIE_TESTE = "HOM26"  # série interna de ensaio; não representa série autorizada pela AGT
CENTAVO = Decimal("0.01")

PONTOS = {
    "1": "Factura com NIF de cliente real",
    "2": "Factura anulada (DocumentStatus=A)",
    "3": "Factura pró-forma (FP)",
    "4a": "Factura derivada da pró-forma (referência à FP)",
    "4b": "Nota de crédito com referência à factura",
    "5": "Factura com linha IVA 14% e serviço isento M17",
    "6": "Factura com desconto aplicado à linha e SettlementAmount",
    "7": "Moeda estrangeira — BLOQUEADO até esclarecimento AGT",
    "8": "Cliente sem NIF, total inferior a 50 AOA, emissão até 10h",
    "9": "Segundo cliente sem NIF",
    "10a": "Guia de remessa (DT) 1/2",
    "10b": "Guia de remessa (DT) 2/2",
    "11": "Segundo orçamento/pró-forma adicional (FP)",
    "12a": "Factura genérica (GF)",
    "12b": "Factura de autofacturação (AF)",
    "13": "Factura global (FG)",
    "14a": "Nota de débito (ND)",
    "14b": "Recibo (RC)",
    "15": "Índice de correspondência",
    "16": "Registo de documentos não aplicáveis",
    "17": "Ficheiro SAF-T XML único e validação XSD",
}

TAXA_NORMAL = ("IVA", "NOR", Decimal("14.00"), "")
TAXA_M17 = ("IVA", "ISE", Decimal("0.00"), "M17")


class HomologacaoBloqueada(Exception):
    """O requisito não pode ser criado sem uma premissa externa confirmada."""


class Command(BaseCommand):
    help = "Prepara amostras de documentos para pré-validação da homologação AGT."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, help="Schema do tenant a utilizar.")
        parser.add_argument("--empresa-id", type=int, help="PK da Empresa emissora; obrigatório se houver várias.")
        parser.add_argument("--cliente-id", type=int, help="PK de Cliente real com NIF, para os pontos que o exigem.")
        parser.add_argument("--limpar", action="store_true", help="Apaga apenas amostras antigas ainda em draft.")
        parser.add_argument("--apenas-saft", action="store_true", help="Gera/valida SAF-T sem criar documentos.")
        parser.add_argument("--ponto", help="Executa apenas um ponto/subponto (ex.: 5, 4a, 10b).")
        parser.add_argument(
            "--confirmar-documentos", action="store_true",
            help="Confirma os drafts após criar as linhas; só usar em schema de ensaio dedicado.",
        )
        parser.add_argument(
            "--usar-dois-meses", action="store_true",
            help="Coloca o ponto 1 no último dia do mês anterior para testar períodos distintos.",
        )

    def handle(self, *args, **options):
        schema = (options.get("schema") or "").strip()
        if not schema or not schema.replace("_", "").isalnum():
            raise CommandError("Schema inválido. Indique --schema=<nome_do_schema>.")
        if options.get("ponto") and options["ponto"] not in PONTOS:
            raise CommandError(f"Ponto inválido: {options['ponto']}. Valores: {', '.join(PONTOS)}")

        try:
            from django_tenants.utils import schema_context, get_tenant_model
        except ImportError as exc:
            raise CommandError("django-tenants não está instalado ou configurado.") from exc

        # Confirma que o schema existe antes de entrar nele.
        try:
            tenant_model = get_tenant_model()
            tenant_model.objects.get(schema_name=schema)
        except Exception as exc:
            raise CommandError(f"Não foi possível confirmar o tenant/schema '{schema}': {exc}") from exc

        self.stdout.write(self.style.MIGRATE_HEADING(f"\nHOMOLOGAÇÃO AGT — schema {schema}\nLote: {LOTE}\n"))
        with schema_context(schema):
            if connection.schema_name != schema:
                raise CommandError(f"O schema activo ({connection.schema_name}) não corresponde a {schema}.")
            self._run_tenant(options)

    def _run_tenant(self, options):
        from apps.fiscal.models import DocumentoFiscal
        from django.contrib.auth import get_user_model

        self.Doc = DocumentoFiscal
        self.Linha = self._obter_modelo_linha()
        self.confirmar = bool(options.get("confirmar_documentos"))
        self.usar_dois_meses = bool(options.get("usar_dois_meses"))
        self.resultados = {}
        self.bloqueados = []
        self.erros = []
        self.aviso_operation_type = "operation_type" not in {f.name for f in self.Linha._meta.get_fields()}

        if options.get("apenas_saft"):
            caminho = self._gerar_saft()
            self.stdout.write(self.style.SUCCESS(f"SAF-T criado: {caminho}"))
            return

        self.empresa = self._obter_empresa(options.get("empresa_id"))
        self.usuario = self._obter_usuario(get_user_model())
        self.cliente_com_nif = self._obter_cliente_com_nif(options.get("cliente_id"))

        if options.get("limpar"):
            self._limpar_amostras_draft()

        geradores = {
            "1": self._ponto_1,
            "2": self._ponto_2,
            "3": self._ponto_3,
            "4a": self._ponto_4a,
            "4b": self._ponto_4b,
            "5": self._ponto_5,
            "6": self._ponto_6,
            "8": self._ponto_8,
            "9": self._ponto_9,
            "10a": lambda: self._ponto_10("10a", 1),
            "10b": lambda: self._ponto_10("10b", 2),
            "11": self._ponto_11,
            "12a": self._ponto_12a,
            "12b": self._ponto_12b,
            "13": self._ponto_13,
            "14a": self._ponto_14a,
            "14b": self._ponto_14b,
        }

        for ponto, gerador in geradores.items():
            if options.get("ponto") and options["ponto"] != ponto:
                continue
            self.stdout.write(f"Ponto {ponto}: {PONTOS[ponto]} ... ", ending="")
            try:
                doc = gerador()
                self.resultados[ponto] = doc.numero_documento
                self.stdout.write(self.style.SUCCESS(doc.numero_documento + (f" [{doc.status}]")))
            except HomologacaoBloqueada as exc:
                self.bloqueados.append((ponto, str(exc)))
                self.stdout.write(self.style.WARNING(f"PENDENTE — {exc}"))
            except Exception as exc:
                self.erros.append((ponto, str(exc)))
                logger.exception("Falha no ponto %s: %s", ponto, exc)
                self.stdout.write(self.style.ERROR(str(exc)))

        # Ponto 7: não gerar números de câmbio arbitrários enquanto a premissa não for esclarecida.
        if not options.get("ponto") or options["ponto"] == "7":
            self.bloqueados.append(("7", "Não gerar até a AGT esclarecer CurrencyAmount/GrossTotal/ExchangeRate."))
            self.stdout.write(self.style.WARNING("Ponto 7: BLOQUEADO — requer esclarecimento da AGT."))

        if self.usar_dois_meses:
            hoje = timezone.localdate()
            ponto1 = self.Doc.objects.filter(
                metadados__homologacao__lote=LOTE, metadados__homologacao__ponto="1"
            ).first()
            if not ponto1 or (ponto1.data_emissao.year, ponto1.data_emissao.month) == (hoje.year, hoje.month):
                self.bloqueados.append(("meses", "O ponto 1 não ficou num mês anterior; o critério de dois meses não está satisfeito."))
        elif not options.get("ponto"):
            self.bloqueados.append(("meses", "Para provar documentos em dois meses, execute com --usar-dois-meses num schema de ensaio dedicado."))

        if not options.get("ponto") or options["ponto"] == "15":
            caminho = self._gravar_indice()
            self.stdout.write(self.style.SUCCESS(f"Ponto 15: índice gravado em {caminho}"))
        if not options.get("ponto") or options["ponto"] == "16":
            caminho = self._gravar_nao_aplicaveis()
            self.stdout.write(self.style.SUCCESS(f"Ponto 16: notas gravadas em {caminho}"))

        # Não exportar drafts como se fossem uma submissão pronta para homologação.
        if self.confirmar and (not options.get("ponto") or options.get("ponto") == "17"):
            try:
                caminho = self._gerar_saft()
                self.stdout.write(self.style.SUCCESS(f"Ponto 17: SAF-T gerado e validado: {caminho}"))
            except Exception as exc:
                self.erros.append(("17", str(exc)))
                logger.exception("Falha ao gerar SAF-T de homologação: %s", exc)
                self.stdout.write(self.style.ERROR(f"Ponto 17: {exc}"))
        elif options.get("ponto") == "17":
            self.stdout.write(self.style.WARNING("Ponto 17 pendente: passe --confirmar-documentos para exportar documentos confirmados."))

        if self.aviso_operation_type:
            self.stdout.write(self.style.WARNING(
                "Aviso: DocumentoFiscalLinha não contém operation_type. Aplique patches/PATCH_models_e_servicos.md "
                "antes de testar o payload da API AGT."
            ))

        self.stdout.write("")
        if self.erros:
            self.stdout.write(self.style.ERROR(f"Concluído com {len(self.erros)} erro(s)."))
        if self.bloqueados:
            self.stdout.write(self.style.WARNING("Existem pontos pendentes; este lote NÃO deve ser considerado completo para submissão:"))
            for ponto, motivo in self.bloqueados:
                self.stdout.write(f"  - {ponto}: {motivo}")
        if not self.erros and not self.bloqueados:
            self.stdout.write(self.style.SUCCESS("Pré-validação técnica concluída. Ainda confirme o XSD e o payload no ambiente AGT."))
        if not self.confirmar:
            self.stdout.write(self.style.WARNING(
                "Os documentos novos permanecem em draft. Para gerar assinaturas/hash e SAF-T de ensaio, "
                "reexecute num schema dedicado com --confirmar-documentos."
            ))

    def _obter_modelo_linha(self):
        from apps.fiscal.models import DocumentoFiscalLinha
        return DocumentoFiscalLinha

    def _obter_empresa(self, empresa_id=None):
        model = self.Doc._meta.get_field("empresa").remote_field.model
        qs = model.objects.all().order_by("pk")
        if empresa_id:
            try:
                return qs.get(pk=empresa_id)
            except model.DoesNotExist as exc:
                raise CommandError(f"Empresa id={empresa_id} não existe neste schema.") from exc
        items = list(qs[:2])
        if not items:
            raise CommandError("Não existe Empresa neste schema. Crie/configure a entidade emissora primeiro.")
        if len(items) > 1:
            raise CommandError("Há várias Empresas. Especifique --empresa-id para não usar a empresa errada.")
        return items[0]

    def _obter_usuario(self, User):
        qs = User.objects.filter(is_active=True).order_by("-is_superuser", "-is_staff", "pk")
        user = qs.first()
        if not user:
            raise CommandError("Não existe utilizador activo para registar a criação/confirmação dos documentos.")
        return user

    def _obter_cliente_com_nif(self, cliente_id=None):
        from apps.clientes.models import Cliente
        qs = Cliente.objects.exclude(nif__isnull=True).exclude(nif__exact="").order_by("pk")
        if cliente_id:
            cliente = qs.filter(pk=cliente_id).first()
            if not cliente:
                raise CommandError(f"Cliente id={cliente_id} não existe ou não tem NIF preenchido.")
            return cliente
        return qs.first()

    def _obter_taxa(self, spec):
        from apps.fiscal.models import TaxaIVAAGT
        tax_type, tax_code, percentage, exemption = spec
        qs = TaxaIVAAGT.objects.filter(
            codigo_pais="AO", tax_type=tax_type, tax_code=tax_code,
            tax_percentage=percentage, ativo=True,
        )
        if exemption:
            taxa = qs.filter(exemption_reason=exemption).first()
        else:
            taxa = qs.filter(Q(exemption_reason="") | Q(exemption_reason__isnull=True)).first()
        if taxa:
            return taxa

        labels = dict(TaxaIVAAGT.TAX_CODE_CHOICES)
        if tax_type == "IVA" and percentage == Decimal("14.00"):
            nome = "IVA — Taxa Normal 14%"
            base_legal = "CIVA — taxa normal de IVA de Angola; confirmar vigência antes de uso fiscal real."
        elif exemption == "M17":
            nome = "IVA — Isenção M17 (transporte colectivo de passageiros)"
            base_legal = "Decreto Executivo 683/25 — Tabela 4; usar apenas quando a operação corresponder à descrição legal."
        elif tax_type == "NS":
            nome = "Não sujeição — NS / M02"
            base_legal = "Decreto Executivo 683/25 — M02; validar enquadramento da operação."
        else:
            nome = f"{tax_type} — {labels.get(tax_code, tax_code)}"
            base_legal = "Referência de homologação; validar enquadramento legal da operação."

        return TaxaIVAAGT.objects.create(
            nome=nome[:100], codigo_pais="AO", tax_type=tax_type,
            tax_code=tax_code, tax_percentage=percentage,
            exemption_reason=exemption or None,
            legislacao_referencia=base_legal[:255], ativo=True,
        )

    def _cliente_dados(self, nif_required=False, nome_fallback="Consumidor de teste"):
        cliente = self.cliente_com_nif if nif_required else None
        if nif_required and not cliente:
            raise HomologacaoBloqueada(
                "não há Cliente real com NIF no schema; crie/seleccione um cliente real ou passe --cliente-id."
            )
        if cliente:
            nome = getattr(cliente, "nome_exibicao", None) or getattr(cliente, "nome_completo", None) or str(cliente)
            return cliente, nome[:200], (getattr(cliente, "nif", "") or "").strip()
        return None, nome_fallback[:200], ""

    def _data_emissao(self, usar_mes_anterior=False):
        hoje = timezone.localdate()
        if not usar_mes_anterior:
            return hoje
        if hoje.month == 1:
            raise HomologacaoBloqueada(
                "para testar dois meses em Janeiro, escolha datas dentro do mesmo exercício; "
                "o command não mistura exercícios fiscais num único SAF-T."
            )
        return hoje.replace(day=1) - timedelta(days=1)

    @transaction.atomic
    def _obter_ou_criar_documento(self, ponto, tipo, descricao, linhas, *, nif_required=False,
                                  nome_cliente=None, data_emissao=None, referencia=None,
                                  motivo_referencia="", totals_sem_linhas=None):
        from apps.fiscal.models import DocumentoFiscal

        hom = ("metadados__homologacao__lote", LOTE)
        existente = DocumentoFiscal.objects.filter(**{hom[0]: hom[1], "metadados__homologacao__ponto": ponto}).first()
        if existente:
            if existente.status != "draft":
                # Documento emitido é imutável: é reutilizado, nunca reescrito.
                if self.confirmar and existente.status == "confirmed":
                    return existente
                if existente.status in ("cancelled", "posted", "paid", "rectified") and ponto != "2":
                    return existente
                if ponto == "2" and existente.status == "cancelled":
                    return existente
                raise HomologacaoBloqueada(
                    f"já existe um documento de homologação {existente.numero_documento} em status {existente.status}; "
                    "não será alterado nem apagado automaticamente."
                )
            doc = existente
            if ponto == "1" and self.usar_dois_meses and doc.status == "draft" and data_emissao and doc.data_emissao != data_emissao:
                # Draft não emitido pode ser ajustado para a data de teste; nunca se altera um emitido.
                doc.data_emissao = data_emissao
                doc.periodo_tributacao = data_emissao.strftime("%Y-%m")
                doc.save(_skip_immutability_check=True)
            elif ponto == "1" and self.usar_dois_meses and doc.data_emissao.month == timezone.localdate().month and doc.status != "draft":
                raise HomologacaoBloqueada(
                    "o documento do ponto 1 já foi emitido neste mês. Não será retrodatado; utilize um schema de ensaio novo."
                )
            doc_linhas = list(doc.linhas.all().order_by("numero_linha"))
            if doc_linhas and len(doc_linhas) != len(linhas):
                raise HomologacaoBloqueada(
                    f"o draft {doc.numero_documento} já tem {len(doc_linhas)} linha(s), mas a definição actual exige {len(linhas)}; "
                    "use --limpar apenas antes de confirmar o documento."
                )
        else:
            cliente, nome, nif = self._cliente_dados(nif_required, nome_cliente or f"Consumidor teste AGT {ponto}")
            meta = {
                "homologacao": {
                    "lote": LOTE,
                    "ponto": ponto,
                    "descricao": descricao,
                    "referencia_documento_origem": getattr(referencia, "numero_documento", "") if referencia else "",
                    "data_referencia_origem": getattr(getattr(referencia, "data_emissao", None), "isoformat", lambda: "")() if referencia else "",
                    "motivo_referencia": motivo_referencia,
                    "dados_sinteticos_de_ensaio": True,
                }
            }
            doc = DocumentoFiscal(
                empresa=self.empresa,
                tipo_documento=tipo,
                serie=SERIE_TESTE,
                data_emissao=data_emissao or timezone.localdate(),
                cliente=cliente,
                cliente_nome=nome,
                cliente_nif=nif,
                moeda="AOA",
                taxa_cambio=Decimal("1.000000"),
                valor_base=Decimal("0.00"),
                valor_iva=Decimal("0.00"),
                valor_desconto=Decimal("0.00"),
                valor_retencao=Decimal("0.00"),
                valor_total=Decimal("0.00"),
                status="draft",
                origem="sistema",
                usuario_criacao=self.usuario,
                observacoes=f"Amostra de homologação técnica: {descricao}.",
                metadados=meta,
            )
            # O save() do modelo atribui numero_documento, ATCUD e período através do motor real.
            doc.save()
            doc_linhas = []

        if not doc_linhas and linhas:
            for index, spec in enumerate(linhas, start=1):
                taxa = self._obter_taxa(spec["taxa"]) if spec.get("taxa") else None
                kwargs = {
                    "documento": doc,
                    "numero_linha": index,
                    "produto": None,
                    "codigo_produto": spec["codigo"][:50],
                    "descricao": spec["descricao"][:200],
                    "unidade": spec.get("unidade", "UN")[:10],
                    "quantidade": Decimal(str(spec["quantidade"])),
                    "preco_unitario": Decimal(str(spec["preco_unitario"])),
                    "valor_desconto_linha": Decimal(str(spec.get("desconto", "0.00"))),
                    "taxa_iva": taxa,
                    "observacoes_linha": spec.get("observacoes", ""),
                }
                if "operation_type" in {f.name for f in self.Linha._meta.get_fields()}:
                    kwargs["operation_type"] = spec.get("operation_type", "TB")
                self.Linha.objects.create(**kwargs)

        # Referências ficam nos metadados porque os campos fiscais equivalentes ainda
        # não existem como campos independentes no modelo actual. Só actualizar draft.
        if doc.status == "draft" and referencia:
            meta = dict(doc.metadados or {})
            hom_data = dict(meta.get("homologacao") or {})
            hom_data["referencia_documento_origem"] = referencia.numero_documento
            hom_data["data_referencia_origem"] = referencia.data_emissao.isoformat()
            hom_data["motivo_referencia"] = motivo_referencia or hom_data.get("motivo_referencia", "")
            meta["homologacao"] = hom_data
            DocumentoFiscal.objects.filter(pk=doc.pk).update(metadados=meta)
            doc.metadados = meta

        # A linha recalcula valores automaticamente. Recalcular o pai de forma coerente
        # com clean(): valor_base antes do desconto, valor_total = base + IVA - desconto.
        doc.refresh_from_db()
        stored_lines = list(doc.linhas.all().order_by("numero_linha"))
        if stored_lines:
            base_bruta = sum((Decimal(str(l.quantidade)) * Decimal(str(l.preco_unitario)) for l in stored_lines), Decimal("0.00"))
            desconto = sum((Decimal(str(l.valor_desconto_linha or 0)) for l in stored_lines), Decimal("0.00"))
            iva = sum((Decimal(str(l.valor_iva_linha or 0)) for l in stored_lines), Decimal("0.00"))
            base_bruta = base_bruta.quantize(CENTAVO, rounding=ROUND_HALF_UP)
            desconto = desconto.quantize(CENTAVO, rounding=ROUND_HALF_UP)
            iva = iva.quantize(CENTAVO, rounding=ROUND_HALF_UP)
            total = (base_bruta + iva - desconto).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            DocumentoFiscal.objects.filter(pk=doc.pk).update(
                valor_base=base_bruta, valor_desconto=desconto, valor_iva=iva, valor_total=total,
            )
        elif totals_sem_linhas:
            base, desconto, iva, total = [Decimal(str(x)).quantize(CENTAVO) for x in totals_sem_linhas]
            DocumentoFiscal.objects.filter(pk=doc.pk).update(
                valor_base=base, valor_desconto=desconto, valor_iva=iva, valor_total=total,
            )

        # Persistir metadata de referência sem tocar nos campos fiscais de um documento emitido.
        doc.refresh_from_db()
        return doc

    def _emitir_se_pedido(self, doc, cancelar=False):
        if not self.confirmar or doc.status != "draft":
            return doc
        from apps.fiscal.services.documento_fiscal_service import DocumentoFiscalService
        DocumentoFiscalService.emitir(doc, self.usuario)
        doc.refresh_from_db()
        if cancelar:
            DocumentoFiscalService.cancelar(
                doc, self.usuario, motivo_codigo="N",
                motivo_texto="Documento de ensaio emitido para demonstrar o estado anulado no SAF-T.",
            )
            doc.refresh_from_db()
        return doc

    def _criar(self, ponto, tipo, descricao, linhas, **kwargs):
        doc = self._obter_ou_criar_documento(ponto, tipo, descricao, linhas, **kwargs)
        return self._emitir_se_pedido(doc, cancelar=(ponto == "2"))

    def _linha(self, codigo, descricao, quantidade, preco, taxa=TAXA_NORMAL, *, desconto="0.00", operation_type="TB"):
        return {
            "codigo": codigo,
            "descricao": descricao,
            "quantidade": quantidade,
            "preco_unitario": preco,
            "desconto": desconto,
            "taxa": taxa,
            "operation_type": operation_type,
        }

    def _ponto_1(self):
        return self._criar(
            "1", "FT", PONTOS["1"],
            [self._linha("HOM-P001", "Mercadoria de teste, IVA taxa normal", "1", "1000.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real",
            data_emissao=self._data_emissao(usar_mes_anterior=self.usar_dois_meses),
        )

    def _ponto_2(self):
        return self._criar(
            "2", "FT", PONTOS["2"],
            [self._linha("HOM-P002", "Mercadoria para demonstração de anulação", "1", "500.0000")],
            nome_cliente="Consumidor de ensaio — documento anulado",
            data_emissao=timezone.localdate(),
        )

    def _ponto_3(self):
        return self._criar(
            "3", "FP", PONTOS["3"],
            [self._linha("HOM-P003", "Item de orçamento/pró-forma", "1", "2000.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real",
            data_emissao=timezone.localdate(),
        )

    def _ponto_4a(self):
        proforma = self._ponto_3()
        return self._criar(
            "4a", "FT", PONTOS["4a"],
            [self._linha("HOM-P004", "Item convertido de pró-forma", "1", "2000.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real", referencia=proforma,
            data_emissao=timezone.localdate(),
        )

    def _ponto_4b(self):
        origem = self._ponto_4a()
        return self._criar(
            "4b", "NC", PONTOS["4b"],
            [self._linha("HOM-P005", "Devolução parcial para nota de crédito", "1", "500.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real", referencia=origem,
            motivo_referencia="Devolução parcial — amostra para teste de referências.",
            data_emissao=timezone.localdate(),
        )

    def _ponto_5(self):
        return self._criar(
            "5", "FT", PONTOS["5"],
            [
                self._linha("HOM-P006", "Mercadoria tributada à taxa normal de IVA", "1", "500.0000"),
                self._linha(
                    "HOM-S017", "Serviço de transporte colectivo de passageiros — hipótese M17",
                    "1", "500.0000", TAXA_M17, operation_type="ST",
                    observacoes="M17 só é aplicável se o serviço corresponder efectivamente à descrição legal.",
                ),
            ],
            nome_cliente="Consumidor de ensaio — linha tributada e linha isenta",
            data_emissao=timezone.localdate(),
        )

    def _ponto_6(self):
        # 100 × 0,55 = 55,00; desconto 5,50; base tributável 49,50; IVA 14% = 6,93; total 56,43.
        return self._criar(
            "6", "FT", PONTOS["6"],
            [self._linha(
                "HOM-P007", "Mercadoria com desconto de ensaio", "100", "0.5500",
                TAXA_NORMAL, desconto="5.50", operation_type="TB",
            )],
            nome_cliente="Consumidor de ensaio — desconto",
            data_emissao=timezone.localdate(),
        )

    def _ponto_8(self):
        # Não altera auto_now_add para falsificar a hora: tem de correr antes/de até às 10h locais.
        hora_real = timezone.localtime().time().replace(tzinfo=None)
        if hora_real > time(10, 0):
            raise HomologacaoBloqueada(
                f"agora são {hora_real:%H:%M:%S} no fuso do servidor; execute este ponto até às 10:00 locais. "
                "O command não falsifica hora_emissao/created_at/SystemEntryDate."
            )
        return self._criar(
            "8", "FR", PONTOS["8"],
            [self._linha("HOM-P008", "Item de baixo valor para consumidor sem NIF", "1", "35.0900")],
            nome_cliente="Consumidor de ensaio sem NIF — ponto 8",
            data_emissao=timezone.localdate(),
        )

    def _ponto_9(self):
        return self._criar(
            "9", "FR", PONTOS["9"],
            [self._linha("HOM-P009", "Item para segundo consumidor sem NIF", "1", "263.1600")],
            nome_cliente="Consumidor de ensaio sem NIF — ponto 9",
            data_emissao=timezone.localdate(),
        )

    def _ponto_10(self, ponto, indice):
        return self._criar(
            ponto, "DT", PONTOS[ponto],
            [self._linha(
                f"HOM-DT{indice:02d}", f"Mercadoria para guia de remessa {indice}",
                "1", "500.0000", None, operation_type="TB",
            )],
            nome_cliente=f"Destinatário de ensaio da guia {indice}",
            data_emissao=timezone.localdate(),
        )

    def _ponto_11(self):
        return self._criar(
            "11", "FP", PONTOS["11"],
            [self._linha("HOM-P011", "Segundo item de orçamento/pró-forma", "1", "3000.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real",
            data_emissao=timezone.localdate(),
        )

    def _ponto_12a(self):
        return self._criar(
            "12a", "GF", PONTOS["12a"],
            [self._linha("HOM-GF01", "Item de factura genérica", "1", "2000.0000")],
            nif_required=True, nome_cliente="Cliente com NIF real", data_emissao=timezone.localdate(),
        )

    def _ponto_12b(self):
        return self._criar(
            "12b", "AF", PONTOS["12b"],
            [self._linha("HOM-AF01", "Item de autofacturação para ensaio", "1", "2000.0000")],
            nif_required=True, nome_cliente="Cliente/parceiro com NIF real", data_emissao=timezone.localdate(),
        )

    def _ponto_13(self):
        return self._criar(
            "13", "FG", PONTOS["13"],
            [self._linha("HOM-FG01", "Item de factura global para ensaio", "1", "10000.0000")],
            nif_required=True, nome_cliente="Cliente/agregador com NIF real", data_emissao=timezone.localdate(),
        )

    def _ponto_14a(self):
        return self._criar(
            "14a", "ND", PONTOS["14a"],
            [self._linha("HOM-ND01", "Juros de mora — amostra para nota de débito", "1", "200.0000")],
            nome_cliente="Cliente de ensaio para nota de débito", data_emissao=timezone.localdate(),
        )

    def _ponto_14b(self):
        # O recibo é exportado na secção Payments; o service constrói SourceDocumentID.
        origem = self._ponto_1()
        doc = self._criar(
            "14b", "RC", PONTOS["14b"], [],
            nif_required=True, nome_cliente="Cliente com NIF real", referencia=origem,
            data_emissao=timezone.localdate(),
            totals_sem_linhas=(Decimal("1140.00"), Decimal("0.00"), Decimal("0.00"), Decimal("1140.00")),
        )
        return doc

    def _limpar_amostras_draft(self):
        qs = self.Doc.objects.filter(metadados__homologacao__lote=LOTE)
        emitidos = qs.exclude(status="draft")
        if emitidos.exists():
            exemplos = ", ".join(emitidos.values_list("numero_documento", flat=True)[:5])
            raise CommandError(
                "--limpar foi recusado: existem amostras já emitidas/confirmadas. "
                f"Não serão apagadas. Exemplos: {exemplos}. Use um schema de ensaio novo se precisar recomeçar."
            )
        total, _ = qs.filter(status="draft").delete()
        self.stdout.write(self.style.WARNING(f"Eliminados {total} registos draft marcados como amostras deste lote."))

    def _pasta_saida(self):
        pasta = Path(getattr(settings, "MEDIA_ROOT", "") or (Path(settings.BASE_DIR) / "media")) / "homologacao"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _gravar_indice(self):
        from apps.fiscal.models import DocumentoFiscal
        qs = DocumentoFiscal.objects.filter(metadados__homologacao__lote=LOTE).order_by("data_emissao", "tipo_documento", "numero")
        dados = {
            "lote": LOTE,
            "schema": connection.schema_name,
            "gerado_em": timezone.now().isoformat(),
            "documentos": [
                {
                    "ponto": (doc.metadados or {}).get("homologacao", {}).get("ponto", ""),
                    "descricao": (doc.metadados or {}).get("homologacao", {}).get("descricao", ""),
                    "tipo": doc.tipo_documento,
                    "numero_documento": doc.numero_documento,
                    "serie": doc.serie,
                    "data_emissao": doc.data_emissao.isoformat(),
                    "estado": doc.status,
                    "valor_total": str(doc.valor_total),
                    "referencia": (doc.metadados or {}).get("homologacao", {}).get("referencia_documento_origem", ""),
                }
                for doc in qs
            ],
            "pendencias": [{"ponto": p, "motivo": motivo} for p, motivo in self.bloqueados],
        }
        caminho = self._pasta_saida() / f"indice_homologacao_{connection.schema_name}.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(caminho)

    def _gravar_nao_aplicaveis(self):
        dados = {
            "lote": LOTE,
            "schema": connection.schema_name,
            "notas": [
                {
                    "item": "Talão de venda simplificado (TV)",
                    "estado": "não gerado automaticamente",
                    "motivo": "A aplicabilidade deve ser confirmada com base no âmbito exacto da notificação e nas operações do contribuinte.",
                },
                {
                    "item": "Documentos do sector segurador (RP/CS/LD/RA)",
                    "estado": "não gerado automaticamente",
                    "motivo": "Dependem de operações reais do sector segurador; não criar dados fictícios para simular aplicabilidade.",
                },
            ],
        }
        caminho = self._pasta_saida() / f"nao_aplicaveis_homologacao_{connection.schema_name}.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(caminho)

    def _gerar_saft(self):
        from apps.fiscal.services.saft_xml_generator_service import SaftXmlGeneratorService
        from apps.fiscal.services.saft_validacao_service import SaftValidacaoService

        hoje = timezone.localdate()
        inicio = date(hoje.year, 1, 1)
        # O ponto de teste no mês anterior pode estar no exercício anterior (Janeiro); não misturar anos fiscais.
        if self.Doc.objects.filter(metadados__homologacao__lote=LOTE, data_emissao__lt=inicio).exists():
            raise CommandError("Há documentos de ensaio fora do exercício actual. Gere um SAF-T separado por exercício fiscal.")
        tenant = getattr(connection, "tenant", None)
        if tenant is None:
            raise CommandError("connection.tenant indisponível; não é possível montar o cabeçalho do SAF-T.")

        xml_bytes = SaftXmlGeneratorService(tenant, inicio, hoje).generate_xml()
        caminho = self._pasta_saida() / f"SAFT_homologacao_{connection.schema_name}_{timezone.now():%Y%m%d_%H%M%S}.xml"
        caminho.write_bytes(xml_bytes)
        valido, erros = SaftValidacaoService.validar(xml_bytes)
        if not valido:
            resumo = "\n".join(erros[:15])
            raise CommandError(f"SAF-T foi gravado mas NÃO passou a validação XSD ({len(erros)} erro(s)):\n{resumo}")
        return str(caminho)
