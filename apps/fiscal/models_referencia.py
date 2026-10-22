# apps/fiscal/models_referencia.py
"""Modelos de tabelas legais de referência AGT.

Importados no final de apps.fiscal.models para que o Django os descubra como modelos da app fiscal.
As tabelas são catálogos por schema tenant e podem ser geridas pelos administradores.
"""
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.db import models
from decimal import Decimal
from apps.core.models import TimeStampedModel


class CAE(TimeStampedModel):
    """Código de Actividade Económica da Tabela 1 do Decreto Executivo 683/25 / CAE-Rev.2."""
    codigo = models.CharField(
        max_length=5,
        unique=True,
        db_index=True,
        validators=[RegexValidator(r"^\d{5}$", "O código CAE deve conter exactamente 5 dígitos.")],
        verbose_name="Código CAE",
    )
    descricao = models.TextField(verbose_name="Descrição da actividade")
    ativo = models.BooleanField(default=True, db_index=True)
    referencia_legal = models.CharField(
        max_length=255,
        default="Decreto Executivo n.º 683/25 — Tabela 1; CAE-Rev.2 (INE)",
        verbose_name="Referência legal",
    )

    class Meta:
        verbose_name = "Código CAE"
        verbose_name_plural = "Códigos CAE"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.descricao[:100]}"


class ImpostoSelo(TimeStampedModel):
    """Verbas e taxas do Imposto do Selo (Tabela 3 do Decreto Executivo 683/25).

    `taxa_original` preserva exactamente o texto da tabela. Os campos numéricos são
    interpretados para permitir pesquisa/relatórios, mas a descrição legal prevalece.
    """
    TIPO_PERCENTUAL = "percentual"
    TIPO_FIXO = "fixo"
    TIPO_NAO_DEFINIDO = "nao_definido"
    TIPO_TAXA_CHOICES = [
        (TIPO_PERCENTUAL, "Percentual"),
        (TIPO_FIXO, "Valor fixo"),
        (TIPO_NAO_DEFINIDO, "Sem taxa numérica na tabela"),
    ]

    verba = models.CharField(max_length=24, unique=True, verbose_name="N.º / verba")
    descricao = models.TextField(verbose_name="Acto, documento, contrato, operação ou título")
    taxa_original = models.CharField(max_length=80, verbose_name="Taxa conforme tabela legal")
    tipo_taxa = models.CharField(max_length=20, choices=TIPO_TAXA_CHOICES, default=TIPO_NAO_DEFINIDO)
    taxa_percentual = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))], verbose_name="Taxa percentual (%)",
    )
    valor_fixo = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))], verbose_name="Valor fixo",
    )
    moeda = models.CharField(max_length=3, default="AOA", verbose_name="Moeda do valor fixo")
    ativo = models.BooleanField(default=True, db_index=True)
    referencia_legal = models.CharField(
        max_length=255,
        default="Decreto Executivo n.º 683/25 — Tabela 3 (Imposto do Selo)",
        verbose_name="Referência legal",
    )

    class Meta:
        verbose_name = "Verba de Imposto do Selo"
        verbose_name_plural = "Verbas e taxas de Imposto do Selo"
        ordering = ["verba"]

    def __str__(self):
        return f"Verba {self.verba} — {self.taxa_original}"


class ImpostoEspecialConsumo(TimeStampedModel):
    """Classificações pautais e taxas IEC da Tabela 2 do Decreto Executivo 683/25."""
    codigo_pautal = models.CharField(max_length=20, unique=True, db_index=True, verbose_name="Classificação pautal")
    designacao = models.TextField(verbose_name="Designação")
    unidade_medida = models.TextField(verbose_name="Unidade de medida legal")
    taxa_percentual = models.DecimalField(
        max_digits=7, decimal_places=3,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="IEC (%)",
    )
    ativo = models.BooleanField(default=True, db_index=True)
    referencia_legal = models.CharField(
        max_length=255,
        default="Decreto Executivo n.º 683/25 — Tabela 2 (IEC)",
        verbose_name="Referência legal",
    )

    class Meta:
        verbose_name = "Classificação / taxa IEC"
        verbose_name_plural = "Classificações e taxas IEC"
        ordering = ["codigo_pautal"]

    def __str__(self):
        return f"{self.codigo_pautal} — {self.taxa_percentual}%"
