# apps/fiscal/models.py
from django.db import models
from decimal import Decimal
from apps.core.models import TimeStampedModel
from apps.core.choices import TIPO_RETENCAO_CHOICES
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.conf import settings
import hashlib
import json
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime
from apps.core.models import TimeStampedModel
from apps.clientes.models import Cliente
#from apps.fiscal.services.utils import gerar_numero_documento
from apps.produtos.models import Produto
from django.contrib.postgres.fields import JSONField
import base64
import logging
from typing import Dict, Optional, Tuple
from apps.empresas.models import Empresa
from django.db import transaction
from django.utils import timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend

from decimal import Decimal




logger = logging.getLogger(__name__)



class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    acao = models.CharField(max_length=50)
    empresa_id = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()


class TaxaIVAAGT(TimeStampedModel):
    """
    Tabela Mestra de Impostos (Tax Table) conforme Requisitos AGT/SAF-T AO.
    Define as taxas e códigos legais para o IVA, Isenções (IS) e Não Sujeição (NS).

    NOTA (pendente para a próxima fase de correções, já registada e combinada
    com o utilizador): TAX_EXEMPTION_REASON_CHOICES abaixo ainda só tem os
    3 códigos genéricos antigos (M99, M01, M02) — nenhum dos quais existe de
    facto na lista oficial (Tabela 4 do Decreto Executivo 683/25: M10-M24,
    M80-M86, M30-M38, M90-M93, M00, M02, M04). Isto será substituído numa
    fase posterior, junto com a Tabela 5 (Imposto de Selo: S01-S03) e
    Tabela 6 (IEC: I01-I16). Também o campo `empresa` abaixo foi removido (isolamento 
    físico via django-tenants) se trata da arquitetura de chaves.
    """
    TAX_TYPE_CHOICES = [
        ('IVA', 'Imposto sobre o Valor Acrescentado (IVA)'),
        ('IS', 'Isenção'),
        ('NS', 'Não Sujeição'),
    ]
    
    TAX_CODE_CHOICES = [
        # Códigos IVA conforme XSD SAF-T AO 1.01_01 (TaxTableEntryTaxCode)
        ('NOR', 'NOR — Taxa Normal'),
        ('INT', 'INT — Taxa Intermédia'),
        ('RED', 'RED — Taxa Reduzida'),
        ('ISE', 'ISE — Isento'),
        ('OUT', 'OUT — Outros (regimes especiais de IVA)'),
        # Não sujeição e recibos sem descrição de imposto
        ('NS',  'NS — Não Sujeito a IVA ou IS'),
        ('NA',  'NA — Recibos sem descrição de imposto'),
    ]
    
    TAX_EXEMPTION_REASON_CHOICES = [
        # --- Tabela 4 (IVA), Art. 12.º — isenções internas ---
        ('M10', 'M10 — Transmissão de bens alimentares (Anexo I)'),
        ('M11', 'M11 — Medicamentos para fins terapêuticos/profilácticos'),
        ('M12', 'M12 — Cadeiras de rodas, veículos p/ deficientes, braille'),
        ('M13', 'M13 — Transmissão de livros, incluindo digital'),
        ('M14', 'M14 — Locação de imóveis para fins habitacionais'),
        ('M15', 'M15 — Operações sujeitas a SISA, ainda que isentas'),
        ('M16', 'M16 — Jogos de fortuna/azar e diversão social'),
        ('M17', 'M17 — Transporte colectivo de passageiros'),
        ('M18', 'M18 — Intermediação financeira, incl. locação financeira'),
        ('M19', 'M19 — Seguro de saúde e seguros/resseguros do ramo vida'),
        ('M20', 'M20 — Produtos petrolíferos (Anexo II)'),
        ('M21', 'M21 — Ensino (estabelecimentos integrados/superior reconhecido)'),
        ('M22', 'M22 — Serviço médico-sanitário (hospitais, clínicas)'),
        ('M23', 'M23 — Transporte de doentes/feridos em ambulância'),
        ('M24', 'M24 — Equipamentos médicos de estabelecimentos de saúde'),

        # --- Tabela 4 (IVA), Art. 14.º — isenções na importação ---
        ('M80', 'M80 — Importação de bens cuja transmissão interna é isenta'),
        ('M81', 'M81 — Importação de ouro/moeda pelo BNA'),
        ('M82', 'M82 — Importação de bens p/ ofertas em calamidades naturais'),
        ('M83', 'M83 — Importação p/ operações petrolíferas e mineiras'),
        ('M84', 'M84 — Importação de moeda estrangeira por instituições bancárias'),
        ('M85', 'M85 — No âmbito de tratados/acordos internacionais (Angola parte)'),
        ('M86', 'M86 — No âmbito de relações diplomáticas/consulares'),

        # --- Tabela 4 (IVA), Art. 15.º — exportações e afins ---
        ('M30', 'M30 — Bens expedidos/transportados para o estrangeiro'),
        ('M31', 'M31 — Abastecimento de embarcações em alto mar (tráfego internacional)'),
        ('M32', 'M32 — Abastecimento de aeronaves de tráfego internacional'),
        ('M33', 'M33 — Abastecimento de embarcações de salvamento/guerra'),
        ('M34', 'M34 — Transmissão/reparação/aluguer de embarcações e aeronaves internacionais'),
        ('M35', 'M35 — Bens no âmbito de relações diplomáticas/consulares'),
        ('M36', 'M36 — Bens destinados a organismos internacionais'),
        ('M37', 'M37 — Bens no âmbito de tratados/acordos internacionais'),
        ('M38', 'M38 — Transporte de pessoas de/para o estrangeiro'),

        # --- Tabela 4 (IVA), Art. 16.º — zonas francas/trânsito ---
        ('M90', 'M90 — Importação sob regime de zona franca/loja franca'),
        ('M91', 'M91 — Bens expedidos para zonas francas/depósitos'),
        ('M92', 'M92 — Transmissões dentro do regime de zona franca'),
        ('M93', 'M93 — Trânsito, draubaque ou importação temporária'),

        # --- Regimes (não são bem "isenções") ---
        ('M00', 'M00 — IVA, Regime Simplificado'),
        ('M02', 'M02 — Transmissão de bens/serviço não sujeita'),
        ('M04', 'M04 — IVA, Regime de Exclusão'),

        # --- Tabela 5 (Imposto de Selo) ---
        ('S01', 'S01 — Isento nos termos do CIS'),
        ('S02', 'S02 — Isento nos termos do Art. 28.º do CBF (aumentos de capital)'),
        ('S03', 'S03 — Isento nos termos do Art. 40.º do CBF (recibo de quitação, Micro Empresas)'),

        # --- Tabela 6 (IEC) ---
        ('I01', 'I01 — Regime suspensivo de direitos aduaneiros (importação/exportação)'),
        ('I02', 'I02 — Exportação pelo próprio produtor/entidade vocacionada'),
        ('I03', 'I03 — Bens importados por representações diplomáticas/consulares'),
        ('I04', 'I04 — Matérias-primas industriais e bens para fins medicinais/ensino'),
        ('I05', 'I05 — Bens para fins laboratoriais e investigação científica'),
        ('I06', 'I06 — Bens de uso pessoal (legislação aduaneira)'),
        ('I07', 'I07 — Provisões de bordo, transporte colectivo internacional'),
        ('I08', 'I08 — Produtos vendidos a bordo (transporte internacional)'),
        ('I09', 'I09 — Produtos sob regime suspensivo de direitos aduaneiros'),
        ('I10', 'I10 — Produtos vendidos em lojas francas'),
        ('I11', 'I11 — Provisões de bordo p/ funcionamento do meio de transporte'),
        ('I12', 'I12 — Provisões de bordo p/ manutenção do meio de transporte'),
        ('I13', 'I13 — Art. 98.º IPP + Art. 15.º CIVA (regime suspensivo)'),
        ('I14', 'I14 — Anexo I LIEC (código pautal 3926.90.90, excepto palhinhas)'),
        ('I15', 'I15 — Art. 70.º IPP + Art. 11.º LIEC (mercadorias p/ eventos)'),
        ('I16', 'I16 — Resolução n.º 6/91 + Art. 14.º CIVA (agências ONU)'),
    ]

    # Vínculo com a empresa para personalização, embora as taxas sejam tipicamente globais.
    #empresa = models.ForeignKey(
     #   'empresas.Empresa', 
      #  on_delete=models.CASCADE, 
       # related_name='taxas_iva'
    #)
    #CODIGO_PAIS_CHOICES = [
     #   ('AO', 'AO - Angola'),
    #]
    
    # Detalhes Fiscais
    nome = models.CharField(max_length=100, help_text="Ex: IVA Taxa Normal 14%")
    #codigo_pais = models.CharField(max_length=2, choices=CODIGO_PAIS_CHOICES, verbose_name="Código do País", default='AO', editable=False)
    codigo_pais = models.CharField(max_length=2, default='AO')
    tax_type = models.CharField(max_length=3, choices=TAX_TYPE_CHOICES, verbose_name="Tipo de Imposto (TaxType)")
    tax_code = models.CharField(max_length=3, choices=TAX_CODE_CHOICES, verbose_name="Código da Taxa (TaxCode)")
    
    # Taxa (apenas aplicável se tax_type for 'IVA')
    tax_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Taxa em percentagem (e.g., 14.00)"
    )
    
    # Razão de Isenção (apenas aplicável se tax_type for 'IS' ou 'NS')
    exemption_reason = models.CharField(
        max_length=3, 
        choices=TAX_EXEMPTION_REASON_CHOICES, 
        blank=True, 
        null=True,
        verbose_name="Razão de Isenção (TaxExemptionCode)"
    )
    
    # Informação Legal
    legislacao_referencia = models.CharField(max_length=255, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Taxa de IVA (AGT)"
        verbose_name_plural = "Tabela de Impostos (AGT)"
        ordering = ['-tax_percentage', 'tax_type']
        
    def __str__(self):
        if self.tax_type == 'IVA':
            return f"{self.nome} ({self.tax_percentage}%)"
        return f"{self.nome} ({self.tax_type} - {self.exemption_reason})"
    
    def obter_codigo_isencao(self):
        """
        Retorna o código de isenção obrigatório para taxas 0%.
        Levanta erro se não configurado — 'M99' não existe na lista oficial.
        """
        if self.tax_percentage == Decimal('0.00'):
            if self.exemption_reason:
                return self.exemption_reason
            # M02 = "Transmissão de bens/serviço não sujeita" — fallback seguro
            return 'M02'
        return None



class ContadorDocumento(models.Model):
    """
    Motor de Sequencialidade SOTARQ.
    Garante que cada fatura tenha um número único por Empresa/Ano/Série.

    NOTA (pendente): a regra da AGT (Decreto Executivo 683/25, serviço
    solicitarSerie) exige que, de 1 de Janeiro a 15 de Dezembro, só se possa
    criar série para o ano corrente; depois disso, para o ano corrente e o
    seguinte. Esta validação ainda não está implementada aqui — fica para a
    fase de correção dos serviços de série fiscal.
    """
    tipo_documento = models.CharField(max_length=5) 
    ano = models.IntegerField()
    serie = models.CharField(max_length=10, default='A')
    ultimo_numero = models.IntegerField(default=0)

    class Meta:
        # Essencial para garantir que a combinação nunca se repita no banco
        unique_together = ('tipo_documento', 'ano', 'serie')
        verbose_name = 'Contador de Documento'
        verbose_name_plural = 'Contadores de Documentos'

    def __str__(self):
        return f"{self.empresa.nome} - {self.tipo_documento} {self.serie}/{self.ano}: {self.ultimo_numero}"




class SerieFiscalAGT(TimeStampedModel):
    """
    Espelho local das séries de numeração registadas na AGT via
    serviço solicitarSerie / listarSeries (Decreto Executivo 683/25).

    Uma série corresponde a um tipo de documento + ano + código único.
    A AGT é a fonte de verdade; este modelo é o cache local sincronizado.

    Isolamento físico: sem FK para Empresa — o schema já isola por tenant.
    """

    # ── Códigos de estado de série (seriesStatus) ──────────────────────────
    STATUS_ABERTA      = 'A'   # Série criada, ainda não usada
    STATUS_UTILIZACAO  = 'U'   # Série em uso (já tem documentos emitidos)
    STATUS_FECHADA     = 'F'   # Série expirada (ano encerrado)
    SERIES_STATUS_CHOICES = [
        (STATUS_ABERTA,     'A — Aberta'),
        (STATUS_UTILIZACAO, 'U — Em utilização'),
        (STATUS_FECHADA,    'F — Fechada'),
    ]

    # ── Métodos de facturação (invoicingMethod) ────────────────────────────
    METODO_FEPC  = 'FEPC'   # Portal do Contribuinte
    METODO_FESF  = 'FESF'   # Software de Facturação (este sistema)
    METODO_SF    = 'SF'     # Facturação não electrónica via software
    INVOICING_METHOD_CHOICES = [
        (METODO_FEPC, 'FEPC — Portal do Contribuinte'),
        (METODO_FESF, 'FESF — Software de Facturação'),
        (METODO_SF,   'SF — Software (não electrónico)'),
    ]

    # ── Campos principais ──────────────────────────────────────────────────
    series_code = models.CharField(
        max_length=60,
        verbose_name="Código da Série",
        help_text=(
            "Código alfanumérico único, contendo o ano com 2 ou 4 dígitos. "
            "Ex.: FT2025A, NC25B. Gerado localmente e confirmado pela AGT."
        ),
    )
    series_year = models.IntegerField(
        verbose_name="Ano da Série",
        help_text="Ano a que a série diz respeito. Regra: de 1/Jan a 15/Dez apenas o ano corrente; após 15/Dez também o seguinte.",
    )
    document_type = models.CharField(
        max_length=3,
        verbose_name="Tipo de Documento",
        help_text="Código do tipo de documento (FT, FR, NC, …) — mesmos códigos da API AGT.",
    )
    series_status = models.CharField(
        max_length=1,
        choices=SERIES_STATUS_CHOICES,
        default=STATUS_ABERTA,
        verbose_name="Estado da Série",
    )
    invoicing_method = models.CharField(
        max_length=4,
        choices=INVOICING_METHOD_CHOICES,
        default=METODO_FESF,
        verbose_name="Método de Facturação",
    )
    contingency_indicator = models.CharField(
        max_length=1,
        choices=[('N', 'N — Normal'), ('C', 'C — Contingência')],
        default='N',
        verbose_name="Indicador de Contingência",
    )

    # ── Numeração autorizada pela AGT ──────────────────────────────────────
    first_document_no = models.CharField(
        max_length=60, blank=True,
        verbose_name="Primeiro Número Autorizado",
    )
    last_document_no = models.CharField(
        max_length=60, blank=True,
        verbose_name="Último Número Autorizado",
    )
    authorized_quantity = models.CharField(
        max_length=30, blank=True,
        verbose_name="Quantidade Autorizada pela AGT",
    )

    # ── Rastreio de uso ────────────────────────────────────────────────────
    first_document_created = models.CharField(
        max_length=60, blank=True,
        verbose_name="Primeiro Documento Criado",
    )
    last_document_created = models.CharField(
        max_length=60, blank=True,
        verbose_name="Último Documento Criado",
    )
    series_creation_date = models.DateField(
        null=True, blank=True,
        verbose_name="Data de Criação (AGT)",
    )

    # ── Ligação com o ContadorDocumento local ──────────────────────────────
    contador = models.OneToOneField(
        ContadorDocumento,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='serie_agt',
        verbose_name="Contador Local",
        help_text="Contador de sequência local ligado a esta série AGT.",
    )

    # ── Estabelecimento emissor ────────────────────────────────────────────
    establishment_number = models.CharField(
        max_length=200,
        default='SEDE',
        verbose_name="Estabelecimento",
        help_text="Número do estabelecimento conforme registado no Portal do Contribuinte. Use 'SEDE' se único.",
    )

    class Meta:
        verbose_name = "Série Fiscal AGT"
        verbose_name_plural = "Séries Fiscais AGT"
        unique_together = ('series_code', 'series_year', 'document_type')
        ordering = ['-series_year', 'document_type', 'series_code']

    def __str__(self):
        return (
            f"{self.series_code} | {self.document_type} {self.series_year} "
            f"[{self.get_series_status_display()}]"
        )

    @property
    def esta_utilizavel(self) -> bool:
        """True se a série pode ser usada para emitir documentos."""
        return self.series_status in (self.STATUS_ABERTA, self.STATUS_UTILIZACAO)

    @classmethod
    def validar_ano_serie(cls, ano_solicitado: int) -> None:
        """
        Valida se o ano pedido respeita a regra AGT:
          - 1 Jan a 15 Dez: apenas o ano corrente.
          - Após 15 Dez: ano corrente OU ano seguinte.
        Lança ValueError se inválido.
        """
        from django.utils import timezone
        from datetime import date

        hoje = timezone.now().date()
        ano_corrente = hoje.year
        limite_dezembro = date(hoje.year, 12, 15)

        if hoje <= limite_dezembro:
            if ano_solicitado != ano_corrente:
                raise ValueError(
                    f"Até 15 de Dezembro só é possível criar série para o ano corrente ({ano_corrente}). "
                    f"Pedido: {ano_solicitado}."
                )
        else:
            if ano_solicitado not in (ano_corrente, ano_corrente + 1):
                raise ValueError(
                    f"Após 15 de Dezembro só é possível criar série para {ano_corrente} ou {ano_corrente + 1}. "
                    f"Pedido: {ano_solicitado}."
                )


class AssinaturaDigital(TimeStampedModel):
    """
    Configuração da assinatura digital do CONTRIBUINTE (a empresa deste
    tenant) para a Faturação Eletrónica da AGT.

    ARQUITETURA DE CHAVES (duas chaves distintas — não confundir):

    1) Chave do SOFTWARE (jwsSoftwareSignature): gerada LOCALMENTE pela
       SOTARQ (nunca pela AGT), uma só para TODO o sistema — igual para
       todos os tenants. Vive em `settings.AGT_SOFTWARE_PRIVATE_KEY`
       (variável de ambiente), NÃO fica guardada neste modelo nem em
       nenhuma tabela do banco. A chave pública correspondente é
       submetida manualmente no registo do produtor de software no
       Portal do Parceiro (homologação/produção).

    2) Chave do CONTRIBUINTE (jwsDocumentSignature, jwsSignature): emitida
       PELA AGT, uma por empresa/NIF, disponibilizada no portal do
       contribuinte de cada cliente. É essa que fica guardada aqui,
       inserida manualmente pelo admin da empresa ao configurar o tenant
       (ver `definir_chaves`).

    Isolamento físico (django-tenants): este modelo NÃO tem FK para
    Empresa — o schema já isola por empresa, então só pode (e deve)
    existir UMA linha por tenant. Use sempre `AssinaturaDigital.get_solo()`
    para obter/criar essa linha; nunca faça `.objects.create()` diretamente
    nem filtre por `empresa=`.
    """

    # --- NIF do contribuinte deste tenant ---
    nif_contribuinte = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="NIF do Contribuinte",
        help_text="NIF da empresa (tenant) tal como consta na chave emitida pela AGT."
    )

    # --- Chaves do CONTRIBUINTE, emitidas pela AGT ---
    # ATENÇÃO: os nomes abaixo seguem a convenção do assinatura_service.py
    # (chave_contribuinte_privada / chave_contribuinte_publica) para evitar
    # confusão com campos de outras iterações do modelo.
    chave_contribuinte_privada = models.TextField(
        blank=True, null=True,
        help_text="Chave privada RSA do CONTRIBUINTE (emitida pela AGT), armazenada cifrada via AESService. "
                   "Usada para assinar jwsDocumentSignature e jwsSignature."
    )
    chave_contribuinte_publica = models.TextField(
        blank=True, null=True,
        help_text="Chave pública RSA do CONTRIBUINTE (emitida pela AGT), em PEM."
    )
    data_configuracao_chave = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Data de Configuração das Chaves"
    )
    configurada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assinaturas_fiscais_configuradas',
        verbose_name="Configurado por"
    )

    # --- Credenciais Basic Auth para a API AGT ---
    api_username = models.CharField(
        max_length=100, blank=True,
        verbose_name="Username API AGT",
        help_text="Usuário da Basic Auth emitido pela AGT (email produtores)."
    )
    api_password = models.TextField(
        blank=True,
        verbose_name="Password API AGT (cifrada)",
        help_text="Password da Basic Auth cifrada via AESService."
    )

    # --- Cadeia de integridade (hash chain) do SAF-T, por série ---
    ultimo_hash = models.CharField(
        max_length=256,
        blank=True,
        null=True,
        verbose_name="Último Hash em Cadeia (SAF-T)"
    )
    dados_series_fiscais = models.JSONField(
        default=dict, blank=True,
        verbose_name="Dados de Hash e Código AGT por Série"
    )

    data_geracao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Assinatura Fiscal do Contribuinte"
        verbose_name_plural = "Assinatura Fiscal do Contribuinte"

    def save(self, *args, **kwargs):
        # Singleton: força sempre a mesma linha (pk=1) dentro deste schema/tenant.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Não permitir apagar a configuração singleton — só editar.
        raise ValidationError("A configuração de Assinatura Fiscal não pode ser apagada, apenas editada.")

    @classmethod
    def get_solo(cls):
        """Obtém (ou cria, vazia) a única linha de configuração deste tenant."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def obter_configuracao(cls):
        """Alias de get_solo() — compatível com chamadas no service e nas views."""
        return cls.get_solo()

    def definir_chaves(self, nif: str, chave_privada_pem: str, chave_publica_pem: str = None, usuario=None):
        """
        Recebe as chaves do CONTRIBUINTE emitidas pela AGT (coladas pelo
        admin da empresa a partir do portal do contribuinte) e guarda a
        privada cifrada (AES) e a pública em claro.
        """
        from apps.fiscal.utility.crypto import AESService

        self.nif_contribuinte = nif
        self.chave_contribuinte_privada = AESService.encrypt(chave_privada_pem)
        if chave_publica_pem:
            self.chave_contribuinte_publica = chave_publica_pem
        self.data_configuracao_chave = timezone.now()
        self.configurada_por = usuario
        self.save()

    @property
    def esta_configurada(self):
        """True se as chaves do contribuinte já foram inseridas para este tenant."""
        return bool(self.chave_contribuinte_privada and self.chave_contribuinte_publica)

    def __str__(self):
        status = "configurada" if self.esta_configurada else "NÃO configurada"
        nif = f" NIF {self.nif_contribuinte}" if self.nif_contribuinte else ""
        return f"Assinatura Fiscal do Contribuinte{nif} ({status})"


class RetencaoFonte(TimeStampedModel):
    """
    Registo das Retenções na Fonte efetuadas pela empresa (pagador).
    Essencial para o bloco <WithholdingTax> do SAF-T.

    NOTA (pendente para a próxima fase, já combinada com o utilizador):
    TIPO_RETENCAO_CHOICES é importado de apps.core.choices e ainda não foi
    alinhado com os códigos oficiais da AGT (Anexo I, withholdingTaxList:
    IRT, II, IS, IVA, IP, IAC, OU, IRPC, IRPS). Será corrigido na fase de
    ajuste dos módulos fiscal/vendas.
    """
    # Identificação
    referencia_documento = models.CharField(max_length=50, help_text="Ex: Número da Fatura do Fornecedor ou Recibo")
    data_retencao = models.DateField(help_text="Data em que a retenção foi efetuada (geralmente data de pagamento)")
    
    # Valores
    valor_base = models.DecimalField(max_digits=12, decimal_places=2, help_text="Base tributável da retenção")
    
    valor_retido = models.DecimalField(max_digits=12, decimal_places=2, help_text="Valor efetivamente retido")
    
    # Classificação Fiscal
    taxa_retencao = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentual da retenção aplicada sobre o valor base"
    )
    tipo_retencao = models.CharField(
        max_length=10, 
        choices=TIPO_RETENCAO_CHOICES, 
        help_text="Tipo de imposto retido (código SAF-T obrigatório - ex: IRPC, IRT)"
    )
    codigo_tributario = models.CharField(max_length=50, blank=True, help_text="Código da Secção/Artigo da lei fiscal (se aplicável)")
    
    # Rastreamento Contábil
    conta_pagar = models.ForeignKey(
        'financeiro.ContaPagar', 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        help_text="Conta a pagar que gerou esta retenção"
    )
    fornecedor = models.ForeignKey(
        'fornecedores.Fornecedor', 
        on_delete=models.PROTECT, 
        help_text="Fornecedor/Prestador de serviço a quem foi efetuada a retenção"
    )
    
    # Controle
    paga_ao_estado = models.BooleanField(default=False, help_text="Indica se o valor retido já foi pago ao Estado")
    
    
    class Meta:
        verbose_name = "Retenção na Fonte"
        verbose_name_plural = "Retenções na Fonte"
        ordering = ['-data_retencao']

    def save(self, *args, **kwargs):
        # 🚨 Lógica de Negócio Obrigatória: Cálculo do valor retido
        if self.valor_base and self.taxa_retencao:
            self.valor_retido = self.valor_base * (self.taxa_retencao / Decimal('100.00'))
        
        # 🚨 Hook Contábil: Deve ser gerado um LançamentoFinanceiro aqui (ex: Débito em Passivo (Impostos a Pagar), Crédito em ContaPagar)
        self.gerar_lancamento_contabil() 
        
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Retenção {self.tipo_retencao} de {self.valor_retido} em {self.data_retencao}"


class DocumentoFiscal(TimeStampedModel):
    """
    Modelo principal para documentos fiscais (Faturas, Notas de Crédito, etc.)
    Compatível com SAF-T Angola e AGT.
    Suporta assinatura digital e cadeia de integridade.

    NOTA (pendente para a próxima fase, já combinada com o utilizador): o
    campo `empresa` abaixo e os campos ainda em falta face ao Anexo I do
    Decreto Executivo 683/25 (operationType, documentCancelReason,
    settlementAmount, referenceInfo por linha, objeto currency) serão
    corrigidos numa fase posterior. Esta revisão trata apenas da
    arquitetura de chaves de assinatura — por isso a duplicação de save()
    que existia antes foi eliminada aqui (só havia uma versão realmente
    ativa em Python; a morta foi removida para evitar confusão ao mexer
    exatamente neste método).
    """
    
    # Tipos de Documento conforme SAF-T AO 1.01_01 (InvoiceType) +
    # tipos da API AGT Decreto 683/25 (documentType).
    # Os 15 tipos do XSD estão marcados com [SAF-T].
    # Os tipos exclusivos da API (FA, RC, RG) estão marcados com [API].
    TIPO_DOCUMENTO_CHOICES = [
        # --- Facturas e documentos equivalentes ---
        ('FT',  'FT — Factura'),                                    # [SAF-T + API]
        ('FR',  'FR — Factura/Recibo'),                             # [SAF-T + API]
        ('GF',  'GF — Factura Genérica'),                           # [SAF-T + API]
        ('FG',  'FG — Factura Global'),                             # [SAF-T + API]
        ('FA',  'FA — Factura de Adiantamento'),                    # [API]
        # --- Avisos de cobrança ---
        ('AC',  'AC — Aviso de Cobrança'),                          # [SAF-T + API]
        ('AR',  'AR — Aviso de Cobrança/Recibo'),                   # [SAF-T + API]
        # --- Talões e documentos comerciais ---
        ('TV',  'TV — Talão de Venda'),                             # [SAF-T + API]
        # --- Notas rectificativas ---
        ('NC',  'NC — Nota de Crédito'),                            # [SAF-T + API]
        ('ND',  'ND — Nota de Débito'),                             # [SAF-T + API]
        ('RE',  'RE — Estorno ou Recibo de Estorno'),               # [SAF-T + API]
        # --- Autofacturação ---
        ('AF',  'AF — Factura/Recibo de Autofacturação'),           # [SAF-T + API]
        # --- Recibos ---
        ('RC',  'RC — Recibo Emitido'),                             # [API]
        ('RG',  'RG — Outros Recibos Emitidos'),                    # [API]
        # --- Documentos de transporte (Guia de Remessa) ---
        ('DT',  'DT — Documento de Transporte / Guia de Remessa'),  # interno → SAF-T GT/MovementOfGoods
        # --- Documentos de conferência / pró-forma ---
        ('FP',  'FP — Fatura Pró-Forma / Orçamento'),               # [WorkingDocuments]
        # --- Sector segurador ---
        ('RP',  'RP — Prémio ou Recibo de Prémio'),                 # [SAF-T]
        ('CS',  'CS — Imputação a Co-seguradoras'),                  # [SAF-T + API]
        ('LD',  'LD — Imputação a Co-seguradora Líder'),             # [SAF-T + API]
        ('RA',  'RA — Resseguro Aceite'),                            # [SAF-T + API]
    ]
    
    # Status do Documento
    STATUS_CHOICES = [
        ('draft', 'Rascunho'),
        ('confirmed', 'Confirmado'),
        ('posted', 'Lançado'),
        ('paid', 'Pago'),
        ('cancelled', 'Cancelado'),
        ('rectified', 'Retificado'),
    ]
    
    # Origem do Documento
    ORIGEM_CHOICES = [
        ('manual', 'Manual'),
        ('sistema', 'Sistema'),
        ('importacao', 'Importação'),
        ('api', 'API Externa'),
        ('edi', 'EDI'),
    ]
    
    # Tipo de Cliente/Regime
    TIPO_CLIENTE_CHOICES = [
        ('particular', 'Particular'),
        ('isento', 'Isento de IVA'),
        ('nao_residente', 'Não Residente'),
        ('regime_especial', 'Regime Especial'),
    ]

    # ==========================================
    # IDENTIFICAÇÃO DO DOCUMENTO
    # ==========================================
    
    empresa = models.ForeignKey(
        'empresas.Empresa',
        on_delete=models.CASCADE,
        related_name='documentos_fiscais'
    )
    
    # Numeração Sequencial Obrigatória (SAF-T)
    tipo_documento = models.CharField(
        max_length=3,
        choices=TIPO_DOCUMENTO_CHOICES,
        verbose_name="Tipo de Documento"
    )
    
    serie = models.CharField(
        max_length=10,
        default='A',
        help_text="Série do documento (ex: A, B, C, 2024A)"
    )
    
    numero = models.PositiveIntegerField(
        verbose_name="Número do Documento",
        help_text="Número sequencial dentro da série"
    )
    
    numero_documento = models.CharField(
        max_length=50,
        verbose_name="Número Completo",
        help_text="Formato: TIPO SERIE/NUMERO (ex: FT A/1234)",
        editable=False
    )
    
    # ATCUD (Código Único de Documento - Obrigatório AGT)
    atcud = models.CharField(
        max_length=70,
        verbose_name="ATCUD",
        help_text="Código Único de Documento gerado pelo sistema",
        editable=False,
        db_index=True
    )

    # EACCode — Código de Actividade Económica (obrigatório na API AGT)
    eac_code = models.CharField(
        max_length=5,
        blank=True,
        verbose_name="Código CAE (EACCode)",
        help_text="Código de Actividade Económica (5 dígitos, Tabela CAE). "
                  "Obrigatório no payload registarFactura (Decreto 683/25, Anexo I)."
    )
    
    # ==========================================
    # DADOS TEMPORAIS
    # ==========================================
    
    data_emissao = models.DateField(
        verbose_name="Data de Emissão",
        help_text="Data de emissão do documento"
    )
    
    data_vencimento = models.DateField(
        blank=True,
        null=True,
        verbose_name="Data de Vencimento",
        help_text="Data de vencimento para documentos a prazo"
    )
    
    data_operacao = models.DateField(
        blank=True,
        null=True,
        verbose_name="Data da Operação",
        help_text="Data efetiva da operação (se diferente da emissão)"
    )
    
    hora_emissao = models.TimeField(
        auto_now_add=True,
        verbose_name="Hora de Emissão"
    )
    
    # ==========================================
    # PARTES ENVOLVIDAS
    # ==========================================
    
    cliente = models.ForeignKey(
        'clientes.Cliente',
        on_delete=models.PROTECT,
        related_name='documentos_fiscais',
        blank=True,
        null=True,
        verbose_name="Cliente"
    )
    
    # Dados do Cliente (snapshot no momento da emissão)
    cliente_nome = models.CharField(
        max_length=200,
        verbose_name="Nome do Cliente"
    )
    
    cliente_nif = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="NIF do Cliente"
    )
    
    cliente_endereco = models.TextField(
        blank=True,
        verbose_name="Endereço do Cliente"
    )
    
    cliente_email = models.EmailField(
        blank=True,
        verbose_name="Email do Cliente"
    )
    
    cliente_telefone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Telefone do Cliente"
    )
    
    tipo_cliente = models.CharField(
        max_length=20,
        choices=TIPO_CLIENTE_CHOICES,
        default='particular',
        verbose_name="Tipo de Cliente"
    )
    
    # ==========================================
    # VALORES E IMPOSTOS
    # ==========================================
    
    # Valores Base
    valor_base = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor Base (sem IVA)",
        help_text="Soma de todas as linhas sem IVA"
    )
    
    valor_iva = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor do IVA",
        help_text="Soma de todo o IVA aplicado"
    )
    
    valor_desconto = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor de Desconto",
        help_text="Desconto total aplicado"
    )
    
    valor_retencao = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor de Retenção na Fonte",
        help_text="Retenção aplicada (se aplicável)"
    )
    
    valor_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Valor Total",
        help_text="Valor final a pagar/receber"
    )
    
    # Moeda
    moeda = models.CharField(
        max_length=3,
        default='AOA',
        verbose_name="Moeda",
        help_text="Código ISO da moeda (ex: AOA, USD, EUR)"
    )
    
    taxa_cambio = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('1.000000'),
        validators=[MinValueValidator(Decimal('0.000001'))],
        verbose_name="Taxa de Câmbio",
        help_text="Taxa de conversão para AOA (se aplicável)"
    )
    
    # ==========================================
    # INFORMAÇÕES ADICIONAIS
    # ==========================================
    
    observacoes = models.TextField(
        blank=True,
        verbose_name="Observações",
        help_text="Observações ou notas adicionais"
    )
    
    referencia_externa = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Referência Externa",
        help_text="Número de referência do cliente ou sistema externo"
    )
    
    condicoes_pagamento = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Condições de Pagamento",
        help_text="Ex: Pronto pagamento, 30 dias, etc."
    )
    
    forma_pagamento = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Forma de Pagamento",
        help_text="Ex: Dinheiro, Transferência, Cartão"
    )
    
    # ==========================================
    # CONTROLE E STATUS
    # ==========================================
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Status"
    )
    
    origem = models.CharField(
        max_length=20,
        choices=ORIGEM_CHOICES,
        default='manual',
        verbose_name="Origem"
    )
    
    # ==========================================
    # ASSINATURA DIGITAL E INTEGRIDADE
    # ==========================================
    
    hash_documento = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash do Documento",
        help_text="SHA-256 do conteúdo do documento",
        editable=False
    )
    
    hash_anterior = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash do Documento Anterior",
        help_text="Hash do documento anterior da mesma série",
        editable=False
    )
    
    assinatura_digital = models.TextField(
        blank=True,
        verbose_name="Assinatura Digital",
        help_text="Assinatura RSA (RS256) do hash do documento, feita com a chave do CONTRIBUINTE",
        editable=False
    )
    
    # ==========================================
    # RASTREABILIDADE E AUDITORIA
    # ==========================================
    
    usuario_criacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_criados',
        verbose_name="Criado por"
    )
    
    usuario_modificacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_modificados',
        blank=True,
        null=True,
        verbose_name="Modificado por"
    )
    
    data_confirmacao = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Data de Confirmação"
    )
    
    usuario_confirmacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='documentos_confirmados',
        blank=True,
        null=True,
        verbose_name="Confirmado por"
    )
    
    # ==========================================
    # DADOS SAF-T ESPECÍFICOS
    # ==========================================
    
    # Campos específicos para exportação SAF-T
    saft_hash = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash SAF-T",
        help_text="Hash específico para SAF-T",
        editable=False
    )
    
    periodo_tributacao = models.CharField(
        max_length=7,
        verbose_name="Período de Tributação",
        help_text="Formato YYYY-MM para SAF-T",
        editable=False
    )
    
    # ==========================================
    # METADADOS
    # ==========================================
    
    metadados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadados",
        help_text="Dados adicionais em formato JSON"
    )

    # ==========================================
    # CAMPOS NOVOS (Secção 3 — Imutabilidade + Secção 4 — PDF)
    # ==========================================

    # Campo operacional — não fiscal; pode ser alterado após emissão; não entra no hash
    comentarios = models.TextField(
        blank=True,
        verbose_name="Comentários / Observações",
        help_text=(
            "Comentários adicionais do operador. Campo operacional — não fiscal. "
            "Pode ser editado após emissão. NÃO é incluído no hash do documento."
        )
    )

    # Motivo de cancelamento/anulação — obrigatório pela API AGT quando documentStatus=A
    MOTIVO_CANCELAMENTO_CHOICES = [
        ('I', 'I — Identificação incorrecta do adquirente'),
        ('N', 'N — Não enviado ao adquirente'),
    ]
    motivo_cancelamento_codigo = models.CharField(
        max_length=1,
        choices=MOTIVO_CANCELAMENTO_CHOICES,
        blank=True,
        verbose_name="Motivo de Cancelamento (documentCancelReason)",
        help_text="Obrigatório quando documentStatus='A' (anulado). Decreto 683/25, Anexo I."
    )

    # Relação com documento de origem (para NC/ND/rectificativos)
    # Auto-referência: permite rastrear a cadeia documento_original → correctivo
    documento_original = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='documentos_correctivos',
        verbose_name="Documento Original",
        help_text=(
            "Referência ao documento fiscal original que originou este rectificativo. "
            "Preenchido em NC, ND e RE que derivem de outro documento."
        )
    )

    class Meta:
        verbose_name = "Documento Fiscal"
        verbose_name_plural = "Documentos Fiscais"
        ordering = ['-data_emissao', '-numero']
        
        # Constraints para garantir unicidade
        constraints = [
            models.UniqueConstraint(
                fields=['tipo_documento', 'serie', 'numero'],
                name='unique_documento_por_empresa_serie'
            ),
            models.UniqueConstraint(
                fields=['atcud'],
                name='unique_atcud_por_empresa'
            ),
        ]
        
        # Índices para performance
        indexes = [
            models.Index(fields=['data_emissao']),
            models.Index(fields=['status']),
            models.Index(fields=['cliente', 'data_emissao']),
            models.Index(fields=['numero_documento']),
            models.Index(fields=['atcud']),
            models.Index(fields=['hash_documento']),
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # CAMPOS FISCAIS IMUTÁVEIS
    # Campos que NÃO podem ser alterados depois de status != 'draft'.
    # ──────────────────────────────────────────────────────────────────────────
    CAMPOS_FISCAIS_IMUTAVEIS = frozenset([
        'tipo_documento', 'serie', 'numero', 'numero_documento', 'atcud',
        'data_emissao', 'hora_emissao', 'data_operacao',
        'cliente', 'cliente_id', 'cliente_nif', 'cliente_nome',
        'cliente_endereco', 'cliente_email', 'cliente_telefone', 'tipo_cliente',
        'valor_base', 'valor_iva', 'valor_desconto', 'valor_retencao', 'valor_total',
        'moeda', 'taxa_cambio',
        'hash_documento', 'hash_anterior', 'assinatura_digital', 'saft_hash',
        'eac_code', 'periodo_tributacao',
    ])

    def clean(self):
        """
        Validações de integridade fiscal.
        Impede a alteração de campos fiscais imutáveis após a emissão.
        """
        super().clean()

        # Validar datas
        if self.data_vencimento and self.data_vencimento < self.data_emissao:
            raise ValidationError({
                'data_vencimento': 'Data de vencimento não pode ser anterior à data de emissão.'
            })

        # Validar valor total
        if self.valor_total < 0:
            raise ValidationError({'valor_total': 'Valor total não pode ser negativo.'})

        # Validar consistência de valores
        valor_calculado = self.valor_base + self.valor_iva - self.valor_desconto - self.valor_retencao
        if abs(valor_calculado - self.valor_total) > Decimal('0.01'):
            raise ValidationError({
                'valor_total': f'Valor total inconsistente. Esperado: {valor_calculado}'
            })

        # ── PROTECÇÃO DE IMUTABILIDADE ─────────────────────────────────────
        # Só verifica se o documento já existe na BD (pk preenchido)
        if self.pk and self.status != 'draft':
            try:
                original = DocumentoFiscal.objects.get(pk=self.pk)
            except DocumentoFiscal.DoesNotExist:
                return

            # Se o status original não era draft, bloquear campos fiscais
            if original.status != 'draft':
                for campo in self.CAMPOS_FISCAIS_IMUTAVEIS:
                    if getattr(self, campo, None) != getattr(original, campo, None):
                        raise ValidationError(
                            f"O documento '{self.numero_documento}' já foi emitido (status='{self.status}'). "
                            f"O campo '{campo}' não pode ser alterado. "
                            f"Para corrigir, emita um documento rectificativo (NC/ND)."
                        )

    def save(self, *args, _skip_immutability_check=False, **kwargs):
        """
        Pipeline de persistência fiscal SOTARQ.
        Ordem: Validação de imutabilidade → Numeração → ATCUD → Assinatura.

        O parâmetro _skip_immutability_check=True é reservado exclusivamente
        para os métodos internos de transição de estado (emitir, cancelar, etc.)
        que precisam de actualizar apenas campos operacionais de forma legítima.
        NUNCA usar externamente.
        """
        # Executar validações de imutabilidade (excepto quando chamado internamente)
        if not _skip_immutability_check:
            self.full_clean()

        # 1. Fase de Inserção (Novo Registo)
        if not self.pk:
            self._gerar_numero_documento()
            self._gerar_atcud()
            self._definir_periodo_tributacao()

        # 2. Fase de Confirmação (Criptografia)
        if self.status == 'confirmed' and not self.hash_documento:
            doc_anterior = DocumentoFiscal.objects.filter(
                tipo_documento=self.tipo_documento,
                serie=self.serie,
                numero__lt=self.numero,
                status='confirmed'
            ).order_by('-numero').first()

            if doc_anterior:
                self.hash_anterior = doc_anterior.hash_documento

            self._gerar_hash_documento()
            self._aplicar_assinatura_digital()

        # Atualizar campos calculados (dados do cliente, se vinculado)
        self._atualizar_campos_calculados()

        super().save(*args, **kwargs)

        # Atualizar hash da cadeia após salvar
        if self.status == 'confirmed':
            self._atualizar_cadeia_integridade()

    def _gerar_numero_documento(self):
        """
        Integração com o motor de sequencialidade centralizado do Core.
        Garante conformidade com a estrutura de dicionário retornada pelo service.
        """
        
        # Só gera se o número ainda não tiver sido atribuído (evita re-geração no save)
        if not self.numero:
            from apps.fiscal.services.utils import gerar_numero_documento

            dados = gerar_numero_documento(
                empresa=self.empresa,
                tipo_documento=self.tipo_documento,
                serie=self.serie
            )
            
            # Mapeamento rigoroso conforme o retorno do service unificado
            self.numero = dados['sequencial']
            self.numero_documento = dados['formatado']

    def _gerar_atcud(self):
        """Gera ATCUD conforme especificação AGT."""
        from django.utils import timezone
        
        # Formato: EMPRESA_SERIE_NUMERO_TIMESTAMP
        timestamp = int(timezone.now().timestamp())
        self.atcud = f"{self.empresa.nif}_{self.tipo_documento}_{self.serie}_{self.numero}_{timestamp}"

    def _definir_periodo_tributacao(self):
        """Define período de tributação para SAF-T."""
        self.periodo_tributacao = self.data_emissao.strftime('%Y-%m')

    def _gerar_hash_documento(self):
        """Gera hash SHA-256 do conteúdo do documento."""
        # Dados para hash (ordem importante para consistência)
        dados_hash = {
            'atcud': self.atcud,
            'numero_documento': self.numero_documento,
            'data_emissao': self.data_emissao.isoformat(),
            'cliente_nif': self.cliente_nif or '',
            'valor_total': str(self.valor_total),
            'moeda': self.moeda,
        }
        
        # Incluir hash anterior para cadeia de integridade
        if self.hash_anterior:
            dados_hash['hash_anterior'] = self.hash_anterior
        
        # Gerar hash
        dados_json = json.dumps(dados_hash, sort_keys=True, ensure_ascii=False)
        self.hash_documento = hashlib.sha256(dados_json.encode('utf-8')).hexdigest()

    def _aplicar_assinatura_digital(self):
        """
        Aplica assinatura digital RS256 ao hash do documento, usando a chave
        do CONTRIBUINTE (emitida pela AGT, guardada em AssinaturaDigital
        deste tenant — ver apps.fiscal.services.assinatura_service).

        Constrói um payload mínimo com os campos obrigatórios do Anexo I e
        chama AssinaturaDigitalService.assinar_documento().
        """
        from apps.fiscal.services.assinatura_service import AssinaturaDigitalService, FiscalServiceError

        try:
            # Payload de assinatura conforme Anexo I do Decreto 683/25
            payload = {
                "documentNo": self.numero_documento,
                "documentDate": self.data_emissao.isoformat(),
                "documentType": self.tipo_documento,
                "hash": self.hash_documento,
                "hashAnterior": self.hash_anterior or "",
            }
            self.assinatura_digital = AssinaturaDigitalService.assinar_documento(payload)
        except FiscalServiceError as e:
            # Chave do contribuinte ainda não configurada para este tenant —
            # regista o aviso mas não impede o fluxo (documento fica sem
            # assinatura até a chave ser configurada).
            logger.warning(f"Não foi possível assinar digitalmente o documento {self.numero_documento}: {e}")

    def _atualizar_campos_calculados(self):
        """Atualiza campos calculados automaticamente."""
        # Atualizar dados do cliente se vinculado
        if self.cliente:
            self.cliente_nome = self.cliente.nome_exibicao
            self.cliente_nif = self.cliente.nif or ''
            self.cliente_endereco = str(self.cliente.endereco) if hasattr(self.cliente, 'endereco') else ''
            self.cliente_email = self.cliente.email or ''
            self.cliente_telefone = self.cliente.telefone or ''

    def _atualizar_cadeia_integridade(self):
        """
        Atualiza a cadeia de integridade após confirmar um documento, delegando
        ao AssinaturaDigitalService (única fonte de lógica de cadeia).
        """
        from apps.fiscal.services.assinatura_service import AssinaturaDigitalService

        serie_key = f"{self.tipo_documento}_{self.serie}"
        AssinaturaDigitalService.atualizar_cadeia_interna(
            serie=serie_key,
            numero_documento=self.numero_documento,
            novo_hash=self.hash_documento,
        )

    def confirmar_documento(self, usuario):
        """
        Transição DRAFT → CONFIRMED.
        Gera hash, assina e torna o documento imutável nos campos fiscais.
        Única forma legítima de emitir um documento.
        """
        if self.status != 'draft':
            raise ValidationError(
                f"Apenas documentos em rascunho podem ser confirmados. "
                f"Status actual: '{self.status}'."
            )

        self.status = 'confirmed'
        self.usuario_confirmacao = usuario
        self.data_confirmacao = timezone.now()

        # Buscar hash do documento anterior na mesma série
        doc_anterior = DocumentoFiscal.objects.filter(
            tipo_documento=self.tipo_documento,
            serie=self.serie,
            numero__lt=self.numero,
            status='confirmed'
        ).order_by('-numero').first()

        if doc_anterior:
            self.hash_anterior = doc_anterior.hash_documento

        # _skip_immutability_check=True porque esta é uma transição legítima de estado
        self.save(_skip_immutability_check=True)

        # Registar auditoria
        _registar_auditoria_documento(
            documento=self, usuario=usuario,
            acao='DOCUMENT_CONFIRMED',
            estado_anterior='draft', estado_novo='confirmed'
        )

    def lancar_documento(self, usuario):
        """Transição CONFIRMED → POSTED."""
        if self.status != 'confirmed':
            raise ValidationError(
                f"Apenas documentos confirmados podem ser lançados. "
                f"Status actual: '{self.status}'."
            )
        self.status = 'posted'
        self.usuario_modificacao = usuario
        self.save(_skip_immutability_check=True)
        _registar_auditoria_documento(
            documento=self, usuario=usuario,
            acao='DOCUMENT_POSTED',
            estado_anterior='confirmed', estado_novo='posted'
        )

    def registar_pagamento(self, usuario, dados_pagamento=None):
        """Transição POSTED → PAID (ou CONFIRMED → PAID para FR/RC)."""
        if self.status not in ('confirmed', 'posted'):
            raise ValidationError(
                f"Apenas documentos confirmados ou lançados podem ser marcados como pagos. "
                f"Status actual: '{self.status}'."
            )
        estado_anterior = self.status
        self.status = 'paid'
        self.usuario_modificacao = usuario
        if dados_pagamento and isinstance(dados_pagamento, dict):
            if not self.metadados:
                self.metadados = {}
            self.metadados['pagamento'] = dados_pagamento
        self.save(_skip_immutability_check=True)
        _registar_auditoria_documento(
            documento=self, usuario=usuario,
            acao='DOCUMENT_PAID',
            estado_anterior=estado_anterior, estado_novo='paid'
        )

    def cancelar_documento(self, usuario, motivo_codigo='N', motivo_texto=''):
        """
        Cancela o documento (CONFIRMED/POSTED/DRAFT → CANCELLED).
        motivo_codigo: 'I' (identif. incorrecta adquirente) ou 'N' (não enviado).
        Nunca apaga o documento — apenas muda o status para 'cancelled'.
        """
        if self.status in ('cancelled', 'paid', 'rectified'):
            raise ValidationError(
                f"Documento não pode ser cancelado no status '{self.status}'."
            )
        if self.status not in ('draft',) and motivo_codigo not in ('I', 'N'):
            raise ValidationError(
                "Motivo de cancelamento obrigatório: 'I' (identificação incorrecta) "
                "ou 'N' (não enviado ao adquirente)."
            )

        estado_anterior = self.status
        self.status = 'cancelled'
        self.motivo_cancelamento_codigo = motivo_codigo
        self.usuario_modificacao = usuario

        if not self.metadados:
            self.metadados = {}
        self.metadados['cancelamento'] = {
            'motivo_codigo': motivo_codigo,
            'motivo_texto': motivo_texto,
            'data': datetime.now().isoformat(),
            'usuario': usuario.username
        }
        self.save(_skip_immutability_check=True)
        _registar_auditoria_documento(
            documento=self, usuario=usuario,
            acao='DOCUMENT_CANCELLED',
            estado_anterior=estado_anterior, estado_novo='cancelled',
            motivo=f"{motivo_codigo}: {motivo_texto}"
        )

    def rectificar_documento(self, usuario, tipo_rectificativo='NC', motivo=''):
        """
        Marca este documento como RECTIFIED e cria o documento correctivo vazio.
        O documento correctivo (NC/ND/RE) deverá ser preenchido e confirmado separadamente.
        Devolve o novo DocumentoFiscal rectificativo (em estado 'draft').
        """
        if self.status not in ('confirmed', 'posted', 'paid'):
            raise ValidationError(
                f"Apenas documentos emitidos podem ser rectificados. "
                f"Status actual: '{self.status}'."
            )
        if tipo_rectificativo not in ('NC', 'ND', 'RE'):
            raise ValidationError("Tipo rectificativo deve ser NC, ND ou RE.")

        estado_anterior = self.status
        self.status = 'rectified'
        self.usuario_modificacao = usuario
        if not self.metadados:
            self.metadados = {}
        self.metadados['rectificacao'] = {
            'tipo': tipo_rectificativo,
            'motivo': motivo,
            'data': datetime.now().isoformat(),
            'usuario': usuario.username,
        }
        self.save(_skip_immutability_check=True)

        # Criar documento correctivo em rascunho
        correctivo = DocumentoFiscal(
            tipo_documento=tipo_rectificativo,
            serie=self.serie,
            documento_original=self,
            empresa=self.empresa,
            cliente=self.cliente,
            cliente_nome=self.cliente_nome,
            cliente_nif=self.cliente_nif,
            cliente_endereco=self.cliente_endereco,
            cliente_email=self.cliente_email,
            cliente_telefone=self.cliente_telefone,
            tipo_cliente=self.tipo_cliente,
            moeda=self.moeda,
            taxa_cambio=self.taxa_cambio,
            data_emissao=timezone.now().date(),
            valor_base=Decimal('0.00'),
            valor_iva=Decimal('0.00'),
            valor_total=Decimal('0.00'),
            usuario_criacao=usuario,
            origem='sistema',
            observacoes=f"Rectificativo de {self.numero_documento}. Motivo: {motivo}",
            status='draft',
        )
        correctivo.save(_skip_immutability_check=True)

        _registar_auditoria_documento(
            documento=self, usuario=usuario,
            acao='DOCUMENT_RECTIFIED',
            estado_anterior=estado_anterior, estado_novo='rectified',
            motivo=motivo, documento_relacionado=correctivo
        )
        _registar_auditoria_documento(
            documento=correctivo, usuario=usuario,
            acao='DOCUMENT_CORRECTION_CREATED',
            estado_anterior=None, estado_novo='draft',
            documento_relacionado=self
        )
        return correctivo

    def gerar_pdf(self):
        """Gera PDF do documento (placeholder)."""
        # Implementar geração de PDF
        pass

    def enviar_email(self, destinatario=None):
        """Envia documento por email (placeholder)."""
        # Implementar envio por email
        pass

    @property
    def pode_editar(self):
        """Verifica se o documento pode ser editado (apenas campos não-fiscais após emissão)."""
        return self.status == 'draft'

    @property
    def pode_cancelar(self):
        """Verifica se o documento pode ser cancelado."""
        return self.status in ('draft', 'confirmed', 'posted')

    @property
    def pode_rectificar(self):
        """Verifica se o documento pode gerar um rectificativo."""
        return self.status in ('confirmed', 'posted', 'paid')

    @property
    def esta_emitido(self):
        """True quando o documento saiu do estado rascunho."""
        return self.status != 'draft'

    @property
    def campos_fiscais_imutaveis(self):
        """True — os campos fiscais são sempre imutáveis após emissão."""
        return self.esta_emitido

    @property
    def valor_liquido(self):
        """Retorna valor líquido (total - retenção)."""
        return self.valor_total - self.valor_retencao

    @property
    def taxa_iva_media(self):
        """Calcula taxa média de IVA aplicada."""
        if self.valor_base > 0:
            return (self.valor_iva / self.valor_base) * 100
        return Decimal('0.00')

    def __str__(self):
        return f"{self.numero_documento} - {self.cliente_nome} - {self.valor_total} {self.moeda}"




# ──────────────────────────────────────────────────────────────────────────────
# Função auxiliar de auditoria de ciclo de vida de documentos fiscais
# (Secção 3.4.6 do PLANO_IMPLEMENTACAO.md)
# ──────────────────────────────────────────────────────────────────────────────

def _registar_auditoria_documento(
    documento,
    usuario,
    acao: str,
    estado_anterior=None,
    estado_novo=None,
    motivo: str = '',
    documento_relacionado=None,
):
    """
    Regista um evento de auditoria no ciclo de vida de um DocumentoFiscal.

    Reutiliza o modelo AuditLog existente (apps/fiscal/models.py) quando
    disponível. Se não existir, regista apenas no logger de auditoria.

    Eventos conhecidos:
        DOCUMENT_CREATED, DOCUMENT_CONFIRMED, DOCUMENT_POSTED,
        DOCUMENT_PAID, DOCUMENT_CANCELLED, DOCUMENT_RECTIFIED,
        DOCUMENT_CORRECTION_CREATED
    """
    try:
        AuditLog.objects.create(
            user=usuario,
            acao=acao,
            empresa_id=getattr(documento, 'empresa_id', 0),
            ip_address='0.0.0.0',  # IP disponível apenas em context de request
        )
    except Exception:
        pass  # AuditLog é melhor-esforço — não deve bloquear o fluxo fiscal

    # Log estruturado para análise posterior
    import logging
    audit_logger = logging.getLogger('fiscal.auditoria')
    audit_logger.info(
        "AUDITORIA | %s | doc=%s | usuario=%s | %s→%s | motivo=%s | relacionado=%s",
        acao,
        getattr(documento, 'numero_documento', str(documento.pk)),
        getattr(usuario, 'username', str(usuario)),
        estado_anterior,
        estado_novo,
        motivo or '',
        getattr(documento_relacionado, 'numero_documento', '') if documento_relacionado else '',
    )


class DocumentoFiscalLinha(TimeStampedModel):
    """
    Linhas/itens de um documento fiscal.
    Representa cada produto/serviço no documento.
    """
    
    documento = models.ForeignKey(
        DocumentoFiscal,
        on_delete=models.CASCADE,
        related_name='linhas'
    )
    
    # Identificação do Item
    numero_linha = models.PositiveIntegerField(
        verbose_name="Número da Linha"
    )
    
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name="Produto"
    )
    
    # Dados do Produto (snapshot)
    codigo_produto = models.CharField(
        max_length=50,
        verbose_name="Código do Produto"
    )
    
    descricao = models.CharField(
        max_length=200,
        verbose_name="Descrição"
    )
    
    unidade = models.CharField(
        max_length=10,
        default='UN',
        verbose_name="Unidade de Medida"
    )
    
    # Quantidades e Valores
    quantidade = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name="Quantidade"
    )
    
    preco_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        verbose_name="Preço Unitário"
    )
    
    valor_desconto_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Desconto da Linha"
    )
    
    valor_liquido = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor Líquido",
        help_text="Quantidade × Preço - Desconto",
        editable=False
    )
    
    # IVA
    taxa_iva = models.ForeignKey(
        TaxaIVAAGT,
        on_delete=models.PROTECT,
        verbose_name="Taxa de IVA"
    )
    
    valor_iva_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor IVA da Linha",
        editable=False
    )
    
    valor_total_linha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor Total da Linha",
        editable=False
    )
    
    # Informações Adicionais
    observacoes_linha = models.TextField(
        blank=True,
        verbose_name="Observações da Linha"
    )

    class Meta:
        verbose_name = "Linha de Documento Fiscal"
        verbose_name_plural = "Linhas de Documentos Fiscais"
        ordering = ['numero_linha']
        
        constraints = [
            models.UniqueConstraint(
                fields=['documento', 'numero_linha'],
                name='unique_linha_por_documento'
            ),
        ]

    def clean(self):
        """Validações da linha."""
        super().clean()
        
        if self.quantidade <= 0:
            raise ValidationError({
                'quantidade': 'Quantidade deve ser maior que zero.'
            })
        
        if self.preco_unitario < 0:
            raise ValidationError({
                'preco_unitario': 'Preço unitário não pode ser negativo.'
            })

    def save(self, *args, **kwargs):
        """Calcula valores automaticamente."""
        
        # Calcular valor líquido
        self.valor_liquido = (self.quantidade * self.preco_unitario) - self.valor_desconto_linha
        
        # Calcular IVA
        if self.taxa_iva.tax_type == 'IVA':
            self.valor_iva_linha = self.valor_liquido * (self.taxa_iva.tax_percentage / Decimal('100'))
        else:
            self.valor_iva_linha = Decimal('0.00')
        
        # Calcular total da linha
        self.valor_total_linha = self.valor_liquido + self.valor_iva_linha
        
        super().save(*args, **kwargs)
        
        # Atualizar totais do documento
        self._atualizar_totais_documento()

    def _atualizar_totais_documento(self):
        """Atualiza os totais do documento pai."""
        from django.db.models import Sum
        
        documento = self.documento
        
        # Somar todas as linhas
        totais = documento.linhas.aggregate(
            total_base=Sum('valor_liquido'),
            total_iva=Sum('valor_iva_linha'),
            total_desconto=Sum('valor_desconto_linha'),
            total_geral=Sum('valor_total_linha')
        )
        
        documento.valor_base = totais['total_base'] or Decimal('0.00')
        documento.valor_iva = totais['total_iva'] or Decimal('0.00')
        documento.valor_desconto = totais['total_desconto'] or Decimal('0.00')
        documento.valor_total = totais['total_geral'] or Decimal('0.00')
        
        # Salvar sem triggerar signals para evitar loop
        DocumentoFiscal.objects.filter(pk=documento.pk).update(
            valor_base=documento.valor_base,
            valor_iva=documento.valor_iva,
            valor_desconto=documento.valor_desconto,
            valor_total=documento.valor_total
        )

    def __str__(self):
        return f"Linha {self.numero_linha}: {self.descricao} - {self.quantidade} × {self.preco_unitario}"


class SAFTExport(TimeStampedModel):
    """
    Registro dos arquivos SAF-T exportados.
    Serve para auditoria, rastreabilidade e reenvio.
    Compatível com SAF-T Angola / AGT.
    """

    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('gerado', 'Gerado'),
        ('enviado', 'Enviado'),
        ('falhou', 'Falhou'),
    ]

    empresa = models.ForeignKey(
        'empresas.Empresa',
        on_delete=models.CASCADE,
        related_name='saft_exports',
        verbose_name="Empresa"
    )

    # Identificação do arquivo
    periodo_tributacao = models.CharField(
        max_length=7,
        verbose_name="Período de Tributação",
        help_text="Formato YYYY-MM",
    )
    nome_arquivo = models.CharField(
        max_length=255,
        verbose_name="Nome do Arquivo SAF-T",
        help_text="Ex: SAFT_2025-10_AOA.xml"
    )
    caminho_arquivo = models.FileField(
        upload_to='saft_exports/',
        verbose_name="Arquivo SAF-T",
        help_text="Arquivo XML gerado para envio AGT/SAF-T"
    )
    hash_arquivo = models.CharField(
        max_length=256,
        blank=True,
        verbose_name="Hash SHA-256 do arquivo",
        help_text="Garantia de integridade do arquivo SAF-T"
    )

    # Status de exportação
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name="Status do Export"
    )
    
    # Logs e auditoria
    log_geracao = models.TextField(
        blank=True,
        verbose_name="Log de Geração",
        help_text="Mensagens ou erros durante a geração do SAF-T"
    )
    log_envio = models.TextField(
        blank=True,
        verbose_name="Log de Envio",
        help_text="Mensagens ou erros durante o envio para AGT"
    )

    # Controle de usuários
    usuario_geracao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='saft_gerados',
        verbose_name="Gerado por"
    )
    usuario_envio = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='saft_enviados',
        blank=True,
        null=True,
        verbose_name="Enviado por"
    )
    data_envio = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Data de Envio"
    )
    

    class Meta:
        verbose_name = "Exportação SAF-T"
        verbose_name_plural = "Exportações SAF-T"
        ordering = ['-periodo_tributacao', '-created_at']

        indexes = [
            models.Index(fields=['empresa', 'periodo_tributacao']),
            models.Index(fields=['status']),
            models.Index(fields=['hash_arquivo']),
        ]

    def __str__(self):
        return f"SAFT {self.periodo_tributacao} - {self.empresa.nome} ({self.status})"

    def marcar_gerado(self, hash_val):
        """Marca o arquivo como gerado e salva o hash."""
        self.status = 'gerado'
        self.hash_arquivo = hash_val
        self.save(update_fields=['status', 'hash_arquivo', 'updated_at'])

    def marcar_enviado(self, usuario):
        """Marca o arquivo como enviado."""
        self.status = 'enviado'
        self.usuario_envio = usuario
        self.data_envio = timezone.now()
        self.save(update_fields=['status', 'usuario_envio', 'data_envio', 'updated_at'])

    def registrar_erro(self, log_texto, envio=False):
        """Registra logs de erro na geração ou envio."""
        if envio:
            self.log_envio += f"{timezone.now().isoformat()} - {log_texto}\n"
            self.status = 'falhou'
            self.save(update_fields=['log_envio', 'status', 'updated_at'])
        else:
            self.log_geracao += f"{timezone.now().isoformat()} - {log_texto}\n"
            self.status = 'falhou'
            self.save(update_fields=['log_geracao', 'status', 'updated_at'])