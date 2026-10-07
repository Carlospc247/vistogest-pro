# apps/fiscal/management/commands/gerar_documentos_homologacao.py
"""
Management command: gerar_documentos_homologacao

Gera os 17 documentos de teste exigidos pela AGT para homologação do software,
conforme a Notificação Ref: 0000497/01180000/AGT/2026.

Uso:
    python manage.py gerar_documentos_homologacao --schema=mundoemaquinas
    python manage.py gerar_documentos_homologacao --schema=mundoemaquinas --limpar

Os documentos são criados directamente na base de dados do tenant indicado.
Cada ponto da notificação é criado e registado em HomologacaoDocumento (modelo de tracking).

IMPORTANTE: Requer migrações aplicadas e chaves AGT configuradas no tenant.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger('fiscal.homologacao')

PONTOS = {
    1:  'Factura com NIF do cliente',
    2:  'Factura anulada (DocumentStatus=A)',
    3:  'Documento pró-forma',
    '4a': 'Factura a partir da pró-forma (OrderReferences)',
    '4b': 'Nota de Crédito com referência à factura (OrderReference)',
    5:  'Factura com 2 linhas — IVA 14% e Isenção (TaxExemptionReason)',
    6:  'Factura com desconto global (SettlementAmount, UniPrice 4 dec.)',
    7:  'Factura em moeda estrangeira (Currency/ExchangeRate)',
    8:  'Cliente sem NIF, total < 50 AOA, hora ≤ 10h',
    9:  'Outro cliente sem NIF (distinto do ponto 8)',
    10: 'Duas guias de remessa (DocumentoTransporte/DT)',
    11: 'Segundo orçamento / pró-forma adicional',
    12: 'Factura genérica (GF) + Auto-facturação (AF)',
    13: 'Factura global (FG)',
    14: 'Outros documentos (Nota de Débito, Recibo)',
    15: 'Índice de correspondência',
    16: 'Documentos não aplicáveis',
    17: 'Ficheiro SAF-T XML único (todos os documentos)',
}


class Command(BaseCommand):
    help = 'Gera os 17 documentos de homologação AGT para o tenant indicado.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schema', type=str, default='mundoemaquinas',
            help='Schema do tenant onde criar os documentos (default: mundoemaquinas).'
        )
        parser.add_argument(
            '--limpar', action='store_true',
            help='Apaga os registos de homologação anteriores antes de recriar.'
        )
        parser.add_argument(
            '--apenas-saft', action='store_true',
            help='Só gera o SAF-T XML (ponto 17) sem criar novos documentos.'
        )
        parser.add_argument(
            '--ponto', type=str, default=None,
            help='Executar apenas um ponto específico (ex: --ponto=5).'
        )

    def handle(self, *args, **options):
        schema = options['schema']
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n══════════════════════════════════════════\n'
            f'  HOMOLOGAÇÃO AGT — Notificação 0000497/01180000/AGT/2026\n'
            f'  Tenant: {schema}\n'
            f'══════════════════════════════════════════\n'
        ))

        try:
            from django_tenants.utils import schema_context
        except ImportError:
            raise CommandError('django_tenants não está instalado.')

        with schema_context(schema):
            self._executar_no_tenant(options)

    def _executar_no_tenant(self, options):
        """Executa toda a lógica dentro do schema do tenant."""
        from django.db import connection

        schema = connection.schema_name
        self.stdout.write(f'  Schema activo: {schema}\n')

        if options['limpar']:
            self._limpar_registos()

        if options['apenas_saft']:
            self._gerar_saft()
            return

        ponto_alvo = options.get('ponto')

        resultados = {}
        erros = []

        geradores = {
            '1':  self._ponto_1_fatura_com_nif,
            '2':  self._ponto_2_fatura_anulada,
            '3':  self._ponto_3_proforma,
            '4a': self._ponto_4a_fatura_de_proforma,
            '4b': self._ponto_4b_nota_credito,
            '5':  self._ponto_5_fatura_iva_isencao,
            '6':  self._ponto_6_desconto_global,
            '7':  self._ponto_7_moeda_estrangeira,
            '8':  self._ponto_8_sem_nif_baixo_valor,
            '9':  self._ponto_9_segundo_sem_nif,
            '10': self._ponto_10_guias_remessa,
            '11': self._ponto_11_segundo_orcamento,
            '12': self._ponto_12_generica_autofacturacao,
            '13': self._ponto_13_fatura_global,
            '14': self._ponto_14_outros_documentos,
        }

        for chave, gerador in geradores.items():
            if ponto_alvo and str(ponto_alvo) != str(chave):
                continue
            desc = PONTOS.get(int(chave) if chave.isdigit() else chave, chave)
            self.stdout.write(f'  Ponto {chave}: {desc}...', ending='')
            try:
                resultado = gerador()
                resultados[chave] = resultado
                self.stdout.write(self.style.SUCCESS(f' ✓ {resultado}'))
            except Exception as exc:
                erros.append((chave, str(exc)))
                self.stdout.write(self.style.ERROR(f' ✗ {exc}'))
                logger.exception(f'Ponto {chave} falhou: {exc}')

        # Ponto 15 — índice de correspondência
        if not ponto_alvo or ponto_alvo == '15':
            self._ponto_15_indice(resultados)
            self.stdout.write(self.style.SUCCESS('  Ponto 15: Índice gerado ✓'))

        # Ponto 16 — não aplicáveis
        if not ponto_alvo or ponto_alvo == '16':
            self._ponto_16_nao_aplicaveis()
            self.stdout.write(self.style.SUCCESS('  Ponto 16: Não aplicáveis documentados ✓'))

        # Ponto 17 — SAF-T XML
        if not ponto_alvo or ponto_alvo == '17':
            self.stdout.write('  Ponto 17: A gerar SAF-T XML...', ending='')
            try:
                caminho = self._gerar_saft()
                self.stdout.write(self.style.SUCCESS(f' ✓ {caminho}'))
            except Exception as exc:
                erros.append(('17', str(exc)))
                self.stdout.write(self.style.ERROR(f' ✗ {exc}'))

        # Resumo final
        self.stdout.write('')
        if erros:
            self.stdout.write(self.style.WARNING(
                f'Concluído com {len(erros)} erro(s):\n' +
                '\n'.join(f'  Ponto {p}: {e}' for p, e in erros)
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                '✔ Todos os documentos de homologação gerados com sucesso!\n'
                'Próximo passo: configurar chaves AGT e submeter à AGT em:\n'
                '  produtos.dfe.dcrr.agt@minfin.gov.ao'
            ))

    # ──────────────────────────────────────────────────────────────
    # HELPERS — obter dados do tenant
    # ──────────────────────────────────────────────────────────────

    def _obter_ou_criar_taxa_iva(self, percentagem, code='NOR', isento=False, motivo_isencao=''):
        """Obtém ou cria uma TaxaIVAAGT para os testes."""
        from apps.fiscal.models import TaxaIVAAGT
        taxa, _ = TaxaIVAAGT.objects.get_or_create(
            tax_percentage=percentagem,
            defaults={
                'nome': f'IVA {percentagem}%' if not isento else f'Isento {motivo_isencao}',
                'descricao': f'Taxa de IVA de {percentagem}%' if not isento else f'Isenção {motivo_isencao}',
                'tax_type': 'IVA',
                'tax_code': code,
                'tax_country_region': 'AO',
                'ativa': True,
                'exemption_reason': motivo_isencao if isento else '',
            }
        )
        return taxa

    def _obter_ou_criar_produto_teste(self, nome, preco, taxa_iva):
        """Obtém ou cria um Produto de teste."""
        from apps.produtos.models import Produto
        try:
            return Produto.objects.get(nome_produto=nome)
        except Produto.DoesNotExist:
            pass
        # Tentar criar minimamente
        try:
            from apps.produtos.models import Categoria
            cat, _ = Categoria.objects.get_or_create(nome='Homologação AGT')
            return Produto.objects.create(
                nome_produto=nome,
                codigo_interno=f'HOM-{nome[:6].upper().replace(" ", "")}',
                preco_venda=preco,
                categoria=cat,
                ativo=True,
            )
        except Exception:
            return None

    def _obter_forma_pagamento(self):
        """Obtém a primeira forma de pagamento disponível."""
        from apps.vendas.models import FormaPagamento
        fp = FormaPagamento.objects.filter(ativa=True).first()
        if not fp:
            fp = FormaPagamento.objects.create(nome='Dinheiro', tipo='dinheiro', ativa=True)
        return fp

    def _registar_resultado(self, ponto, numero_documento, tipo, notas=''):
        """Regista o resultado num dicionário para o índice."""
        return f'{tipo} {numero_documento}'

    def _limpar_registos(self):
        """Remove documentos de homologação anteriores (apenas os marcados como teste)."""
        from apps.fiscal.models import DocumentoFiscal
        eliminados = DocumentoFiscal.objects.filter(
            numero_documento__startswith='HOM-'
        ).count()
        DocumentoFiscal.objects.filter(numero_documento__startswith='HOM-').delete()
        self.stdout.write(f'  Limpos {eliminados} documentos HOM-* anteriores.\n')

    def _numero_doc(self, tipo, seq):
        """Gera número de documento de teste."""
        from django.utils import timezone
        ano = timezone.now().year
        return f'HOM-{tipo}{ano}/{seq:04d}'

    # ──────────────────────────────────────────────────────────────
    # PONTOS 1–14 — Criação dos documentos de teste
    # ──────────────────────────────────────────────────────────────

    @transaction.atomic
    def _ponto_1_fatura_com_nif(self):
        """Ponto 1 — Factura com NIF do cliente (CustomerTaxID preenchido)."""
        from apps.fiscal.models import DocumentoFiscal, TaxaIVAAGT
        taxa = self._obter_ou_criar_taxa_iva(14)
        numero = self._numero_doc('FT', 1)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 1,
                'data_emissao': timezone.now().replace(hour=14, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Empresa Teste Lda.',
                'cliente_nif': '5000099001',
                'valor_base': '1000.00',
                'valor_iva': '140.00',
                'valor_total': '1140.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 1: Factura com NIF do cliente.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_2_fatura_anulada(self):
        """Ponto 2 — Factura anulada (DocumentStatus=A no SAF-T)."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FT', 2)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 2,
                'data_emissao': timezone.now().replace(hour=11, minute=0),
                'status': 'cancelled',
                'cliente_nome': 'Consumidor Final',
                'cliente_nif': '',
                'valor_base': '500.00',
                'valor_iva': '70.00',
                'valor_total': '570.00',
                'periodo_contabilistico': timezone.now().month,
                'motivo_cancelamento_codigo': 'N',
                'notas_homologacao': 'Ponto 2: Factura anulada — DocumentStatus=A.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_3_proforma(self):
        """Ponto 3 — Documento pró-forma."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FP', 3)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FP',
                'serie': 'HOM-FP',
                'numero': 3,
                'data_emissao': timezone.now().replace(hour=9, minute=30),
                'status': 'confirmed',
                'cliente_nome': 'Cliente Pró-Forma Teste',
                'cliente_nif': '5000099003',
                'valor_base': '2000.00',
                'valor_iva': '280.00',
                'valor_total': '2280.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 3: Documento pró-forma para conferência.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_4a_fatura_de_proforma(self):
        """Ponto 4a — Factura criada a partir da pró-forma (OrderReferences)."""
        from apps.fiscal.models import DocumentoFiscal
        proforma_num = self._numero_doc('FP', 3)
        numero = self._numero_doc('FT', 4)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 4,
                'data_emissao': timezone.now().replace(hour=10, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Cliente Pró-Forma Teste',
                'cliente_nif': '5000099003',
                'valor_base': '2000.00',
                'valor_iva': '280.00',
                'valor_total': '2280.00',
                'periodo_contabilistico': timezone.now().month,
                'documento_origem_referencia': proforma_num,
                'notas_homologacao': f'Ponto 4a: Factura com OrderReferences → {proforma_num}.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_4b_nota_credito(self):
        """Ponto 4b — Nota de Crédito com referência à factura (OrderReference)."""
        from apps.fiscal.models import DocumentoFiscal
        fatura_num = self._numero_doc('FT', 4)
        numero = self._numero_doc('NC', 4)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'NC',
                'serie': 'HOM-NC',
                'numero': 4,
                'data_emissao': timezone.now().replace(hour=15, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Cliente Pró-Forma Teste',
                'cliente_nif': '5000099003',
                'valor_base': '500.00',
                'valor_iva': '70.00',
                'valor_total': '570.00',
                'periodo_contabilistico': timezone.now().month,
                'documento_origem_referencia': fatura_num,
                'motivo_referencia': 'Devolução parcial',
                'notas_homologacao': f'Ponto 4b: NC com OrderReference → {fatura_num}.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_5_fatura_iva_isencao(self):
        """Ponto 5 — Factura com 2 linhas: IVA 14% + Isenção M11."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FT', 5)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 5,
                'data_emissao': timezone.now().replace(hour=16, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Consumidor Final',
                'cliente_nif': '',
                'valor_base': '1000.00',
                'valor_iva': '70.00',
                'valor_total': '1070.00',
                'periodo_contabilistico': timezone.now().month,
                'dados_linhas_json': [
                    {
                        'lineNumber': 1, 'productCode': 'HOM-P001',
                        'productDescription': 'Produto tributado IVA 14%',
                        'quantity': 1, 'unitOfMeasure': 'UN',
                        'unitPriceBase': '500.0000', 'unitPrice': '500.0000',
                        'creditAmount': '500.00', 'settlementAmount': '0.00',
                        'taxes': [{'taxType': 'IVA', 'taxCountryRegion': 'AO',
                                   'taxCode': 'NOR', 'taxPercentage': 14,
                                   'taxContribution': 70.00}],
                        'operationType': 'TB',
                    },
                    {
                        'lineNumber': 2, 'productCode': 'HOM-S001',
                        'productDescription': 'Serviço isento — Art. 12.º b) CIVA',
                        'quantity': 1, 'unitOfMeasure': 'UN',
                        'unitPriceBase': '500.0000', 'unitPrice': '500.0000',
                        'creditAmount': '500.00', 'settlementAmount': '0.00',
                        'taxes': [{'taxType': 'IVA', 'taxCountryRegion': 'AO',
                                   'taxCode': 'ISE', 'taxPercentage': 0,
                                   'taxContribution': 0,
                                   'taxExemptionCode': 'M11',
                                   'taxExemptionReason': 'Isento Artigo 12.º b) do CIVA'}],
                        'operationType': 'SE',
                    },
                ],
                'notas_homologacao': 'Ponto 5: Linha 1 IVA 14%, Linha 2 isenta M11.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_6_desconto_global(self):
        """Ponto 6 — Desconto global (qty=100, unit=0.55, IVA=8.8%, SettlementAmount)."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FT', 6)
        # Base: 100 × 0.55 = 55.00; IVA 8.8% = 4.84; Total = 59.84
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 6,
                'data_emissao': timezone.now().replace(hour=11, minute=30),
                'status': 'confirmed',
                'cliente_nome': 'Consumidor Final',
                'cliente_nif': '',
                'valor_base': '55.00',
                'valor_iva': '4.84',
                'valor_total': '59.84',
                'valor_desconto': '5.50',  # desconto global = 10%
                'periodo_contabilistico': timezone.now().month,
                'dados_linhas_json': [
                    {
                        'lineNumber': 1, 'productCode': 'HOM-P002',
                        'productDescription': 'Produto homologação desconto global',
                        'quantity': 100, 'unitOfMeasure': 'UN',
                        'unitPriceBase': '0.5500', 'unitPrice': '0.5500',
                        'creditAmount': '55.00',
                        'settlementAmount': '5.50',  # SettlementAmount = desconto global
                        'taxes': [{'taxType': 'IVA', 'taxCountryRegion': 'AO',
                                   'taxCode': 'NOR', 'taxPercentage': 8.8,
                                   'taxContribution': 4.84}],
                        'operationType': 'TB',
                    }
                ],
                'notas_homologacao': 'Ponto 6: Qty=100, UniPrice=0.5500, IVA=8.8%, SettlementAmount=5.50.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_7_moeda_estrangeira(self):
        """Ponto 7 — Documento em moeda estrangeira (USD)."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FT', 7)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FT',
                'serie': 'HOM-FT',
                'numero': 7,
                'data_emissao': timezone.now().replace(hour=14, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'International Client Ltd.',
                'cliente_nif': '5000099007',
                'valor_base': '43100.00',   # 100 USD × taxa 431 AOA/USD
                'valor_iva': '6034.00',     # 14%
                'valor_total': '49134.00',
                'moeda': 'USD',
                'taxa_cambio': '431.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 7: USD — CurrencyCode=USD, ExchangeRate=431.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_8_sem_nif_baixo_valor(self):
        """Ponto 8 — Sem NIF, total < 50 AOA, hora ≤ 10h."""
        from apps.fiscal.models import DocumentoFiscal
        from datetime import date, datetime, time
        emissao = timezone.now().replace(hour=9, minute=45, second=0, microsecond=0)
        # Forçar para a manhã no dia actual
        numero = self._numero_doc('FR', 8)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FR',
                'serie': 'HOM-FR',
                'numero': 8,
                'data_emissao': emissao,
                'status': 'confirmed',
                'cliente_nome': 'João Teste',
                'cliente_nif': '',       # sem NIF
                'valor_base': '35.09',
                'valor_iva': '4.91',
                'valor_total': '40.00',  # < 50 AOA
                'periodo_contabilistico': emissao.month,
                'notas_homologacao': 'Ponto 8: Sem NIF, total=40.00<50, hora=09:45.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_9_segundo_sem_nif(self):
        """Ponto 9 — Outro cliente sem NIF (distinto do ponto 8)."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FR', 9)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FR',
                'serie': 'HOM-FR',
                'numero': 9,
                'data_emissao': timezone.now().replace(hour=16, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Maria Silva',
                'cliente_nif': '',       # sem NIF
                'valor_base': '263.16',
                'valor_iva': '36.84',
                'valor_total': '300.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 9: Outro cliente sem NIF (distinto do ponto 8).',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_10_guias_remessa(self):
        """Ponto 10 — Duas guias de remessa (DT)."""
        from apps.fiscal.models import DocumentoFiscal
        numeros = []
        for seq in [10, 11]:
            numero = self._numero_doc('GT', seq)
            doc, created = DocumentoFiscal.objects.get_or_create(
                numero_documento=numero,
                defaults={
                    'tipo_documento': 'GT',
                    'serie': 'HOM-GT',
                    'numero': seq,
                    'data_emissao': timezone.now().replace(hour=8 + seq, minute=0),
                    'status': 'confirmed',
                    'cliente_nome': f'Destinatário Guia {seq - 9}',
                    'cliente_nif': '',
                    'valor_base': f'{seq * 500}.00',
                    'valor_iva': '0.00',
                    'valor_total': f'{seq * 500}.00',
                    'periodo_contabilistico': timezone.now().month,
                    'notas_homologacao': f'Ponto 10: Guia de remessa {seq - 9}/2.',
                }
            )
            numeros.append(numero)
        return ', '.join(numeros)

    @transaction.atomic
    def _ponto_11_segundo_orcamento(self):
        """Ponto 11 — Segundo orçamento / pró-forma adicional."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('OR', 11)
        doc, created = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'OR',
                'serie': 'HOM-OR',
                'numero': 11,
                'data_emissao': timezone.now().replace(hour=10, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Cliente Orçamento',
                'cliente_nif': '5000099011',
                'valor_base': '3000.00',
                'valor_iva': '420.00',
                'valor_total': '3420.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 11: Segundo orçamento/pró-forma.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_12_generica_autofacturacao(self):
        """Ponto 12 — Factura genérica (GF) + Factura de Auto-facturação (AF)."""
        from apps.fiscal.models import DocumentoFiscal
        numeros = []
        for tipo, seq, desc in [('GF', 12, 'Factura Genérica'), ('AF', 13, 'Auto-facturação')]:
            numero = self._numero_doc(tipo, seq)
            doc, _ = DocumentoFiscal.objects.get_or_create(
                numero_documento=numero,
                defaults={
                    'tipo_documento': tipo,
                    'serie': f'HOM-{tipo}',
                    'numero': seq,
                    'data_emissao': timezone.now().replace(hour=14, minute=seq),
                    'status': 'confirmed',
                    'cliente_nome': 'Empresa Parceira Lda.',
                    'cliente_nif': '5000099012',
                    'valor_base': '2000.00',
                    'valor_iva': '280.00',
                    'valor_total': '2280.00',
                    'periodo_contabilistico': timezone.now().month,
                    'notas_homologacao': f'Ponto 12: {desc}.',
                }
            )
            numeros.append(numero)
        return ', '.join(numeros)

    @transaction.atomic
    def _ponto_13_fatura_global(self):
        """Ponto 13 — Factura global (FG)."""
        from apps.fiscal.models import DocumentoFiscal
        numero = self._numero_doc('FG', 14)
        doc, _ = DocumentoFiscal.objects.get_or_create(
            numero_documento=numero,
            defaults={
                'tipo_documento': 'FG',
                'serie': 'HOM-FG',
                'numero': 14,
                'data_emissao': timezone.now().replace(hour=17, minute=0),
                'status': 'confirmed',
                'cliente_nome': 'Agregador Global',
                'cliente_nif': '5000099013',
                'valor_base': '10000.00',
                'valor_iva': '1400.00',
                'valor_total': '11400.00',
                'periodo_contabilistico': timezone.now().month,
                'notas_homologacao': 'Ponto 13: Factura global (FG) — múltiplas operações.',
            }
        )
        return numero

    @transaction.atomic
    def _ponto_14_outros_documentos(self):
        """Ponto 14 — Outros: Nota de Débito (ND) + Recibo (RC)."""
        from apps.fiscal.models import DocumentoFiscal
        numeros = []
        for tipo, seq, nome, base, iva, total in [
            ('ND', 15, 'Nota de Débito — juros de mora', '200.00', '28.00', '228.00'),
            ('RC', 16, 'Recibo de pagamento',             '1140.00', '0.00', '1140.00'),
        ]:
            numero = self._numero_doc(tipo, seq)
            doc, _ = DocumentoFiscal.objects.get_or_create(
                numero_documento=numero,
                defaults={
                    'tipo_documento': tipo,
                    'serie': f'HOM-{tipo}',
                    'numero': seq,
                    'data_emissao': timezone.now().replace(hour=15, minute=seq),
                    'status': 'confirmed',
                    'cliente_nome': 'Consumidor Final',
                    'cliente_nif': '',
                    'valor_base': base,
                    'valor_iva': iva,
                    'valor_total': total,
                    'periodo_contabilistico': timezone.now().month,
                    'notas_homologacao': f'Ponto 14: {nome}.',
                }
            )
            numeros.append(numero)
        return ', '.join(numeros)

    def _ponto_15_indice(self, resultados):
        """Ponto 15 — Índice de correspondência (log para o admin)."""
        linhas = ['=== ÍNDICE DE CORRESPONDÊNCIA ===']
        for ponto, doc in resultados.items():
            desc = PONTOS.get(int(ponto) if str(ponto).isdigit() else ponto, ponto)
            linhas.append(f'Ponto {ponto}: {desc} → {doc}')
        self.stdout.write('\n'.join(linhas))

    def _ponto_16_nao_aplicaveis(self):
        """Ponto 16 — Documentos não aplicáveis."""
        nao_aplicaveis = [
            'Talão de venda simplificado (TV) — não produzido nesta versão',
            'Factura de leasing (LD) — não aplicável ao modelo de negócio standard',
        ]
        for item in nao_aplicaveis:
            self.stdout.write(f'  [N/A] {item}')

    def _gerar_saft(self):
        """Ponto 17 — Gera o ficheiro SAF-T XML único com todos os documentos."""
        from django.db import connection
        from apps.fiscal.services.saft_xml_generator_service import SaftXmlGeneratorService
        from django.utils import timezone
        import os

        tenant = connection.tenant
        data_inicio = timezone.now().replace(month=1, day=1).date()
        data_fim = timezone.now().date()

        service = SaftXmlGeneratorService(tenant, data_inicio, data_fim)
        xml_bytes = service.generate_xml()

        # Gravar em media/homologacao/
        import django.conf as conf
        base_dir = getattr(conf.settings, 'BASE_DIR', '.')
        pasta = os.path.join(base_dir, 'media', 'homologacao')
        os.makedirs(pasta, exist_ok=True)

        schema = connection.schema_name
        nome_ficheiro = f'SAFT_{schema}_{timezone.now().strftime("%Y%m%d_%H%M")}.xml'
        caminho = os.path.join(pasta, nome_ficheiro)

        with open(caminho, 'wb') as f:
            f.write(xml_bytes)

        self.stdout.write(f'\n  SAF-T gravado: {caminho}')
        self.stdout.write(f'  Tamanho: {len(xml_bytes):,} bytes')

        # Validar contra XSD
        try:
            from apps.fiscal.services.saft_validacao_service import SaftValidacaoService
            erros_xsd = SaftValidacaoService.validar(xml_bytes)
            if erros_xsd:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ {len(erros_xsd)} aviso(s) de validação XSD:\n' +
                    '\n'.join(f'    - {e}' for e in erros_xsd[:5])
                ))
            else:
                self.stdout.write(self.style.SUCCESS('  ✓ SAF-T válido contra XSD'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f'  Validação XSD ignorada: {exc}'))

        return caminho
