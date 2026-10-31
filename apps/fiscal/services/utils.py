# apps/fiscal/services/utils.py
from __future__ import annotations

import logging
import hashlib
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Any

from django.db import connection, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.conf import settings
from lxml import etree

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Importações apenas para Type Hinting (evita Circular Import em Runtime)
if TYPE_CHECKING:
    from apps.empresas.models import Empresa
    from apps.fiscal.models import (
        AssinaturaDigital,
        ContadorDocumento,
        DocumentoFiscal,
        DocumentoFiscalLinha,
        RetencaoFonte,
        TaxaIVAAGT,
    )


import logging
import hashlib
import json
import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Any

from django.db import connection, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.conf import settings
from lxml import etree

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Importações apenas para Type Hinting (evita Circular Import em Runtime)
if TYPE_CHECKING:
    from apps.empresas.models import Empresa
    from apps.fiscal.models import (
        AssinaturaDigital,
        ContadorDocumento,
        DocumentoFiscal,
        DocumentoFiscalLinha,
        RetencaoFonte,
        TaxaIVAAGT,
    )

import importlib
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

logger = logging.getLogger("fiscal.services.utils")




class FiscalServiceError(Exception):
    """Erro controlado de negócio da área Fiscal."""




def gerar_rsa_local() -> Tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem




def _validar_contexto_tenant(empresa=None):
    schema = getattr(connection, "schema_name", "public")
    tenant = getattr(connection, "tenant", None)
    if schema == "public" or tenant is None or getattr(tenant, "schema_name", None) != schema:
        raise FiscalServiceError("Esta operação deve ser executada no schema de um tenant válido.")
    if empresa is not None:
        empresa_schema = getattr(empresa, "schema_name", None)
        if empresa_schema != schema or getattr(tenant, "pk", None) != getattr(empresa, "pk", None):
            raise FiscalServiceError(
                f"A empresa indicada não corresponde ao tenant activo (schema '{schema}')."
            )
    return tenant


def gerar_numero_documento(*, empresa, tipo_documento: str, serie: str = "A") -> dict:
    """Reserva, de forma atómica, o próximo número de um tipo/série/ano.

    Devolve as chaves consumidas por DocumentoFiscal: ``sequencial`` e
    ``formatado``. O contador pertence ao schema do tenant; o bloqueio da linha
    evita atribuir o mesmo número a duas transacções concorrentes.
    """
    tenant = _validar_contexto_tenant(empresa)
    tipo = (tipo_documento or "").strip().upper()
    serie = (serie or "A").strip()
    if not tipo or not serie:
        raise FiscalServiceError("Tipo de documento e série são obrigatórios para a numeração.")

    # Importação tardia para evitar ciclo models -> services -> models.
    from apps.fiscal.models import ContadorDocumento

    ano = timezone.localdate().year
    from django.db.models import Max
    from apps.fiscal.models import DocumentoFiscal

    with transaction.atomic():
        # O schema/serie do documento não inclui necessariamente o ano na chave
        # única (tipo, série, número). Por isso a sequência não pode voltar a 1
        # em Janeiro se a mesma série for reutilizada. Bloqueamos os contadores
        # existentes e também respeitamos documentos antigos sem contador.
        contadores = ContadorDocumento.objects.select_for_update().filter(
            tipo_documento=tipo, serie=serie
        )
        maior_contador = max(contadores.values_list("ultimo_numero", flat=True), default=0)
        maior_documento = DocumentoFiscal.objects.filter(
            tipo_documento=tipo, serie=serie
        ).aggregate(maior=Max("numero"))["maior"] or 0
        maior_existente = max(maior_contador, int(maior_documento or 0))

        try:
            contador = (
                ContadorDocumento.objects.select_for_update()
                .get(tipo_documento=tipo, ano=ano, serie=serie)
            )
        except ContadorDocumento.DoesNotExist:
            # O savepoint interno permite recuperar de uma criação concorrente
            # sem deixar a transacção externa marcada como rollback-only.
            try:
                with transaction.atomic():
                    contador = ContadorDocumento.objects.create(
                        tipo_documento=tipo, ano=ano, serie=serie,
                        ultimo_numero=maior_existente,
                    )
            except IntegrityError:
                contador = (
                    ContadorDocumento.objects.select_for_update()
                    .get(tipo_documento=tipo, ano=ano, serie=serie)
                )

        if contador.ultimo_numero < maior_existente:
            contador.ultimo_numero = maior_existente
        contador.ultimo_numero += 1
        contador.save(update_fields=["ultimo_numero"])
        numero = contador.ultimo_numero

    # Este formato é determinístico e compatível com DocumentoFiscal.numero_documento.
    formatado = f"{tipo} {serie}/{numero}"
    logger.info(
        "Número fiscal reservado: schema=%s tipo=%s série=%s ano=%s número=%s",
        tenant.schema_name, tipo, serie, ano, numero,
    )
    return {"sequencial": numero, "formatado": formatado, "ano": ano, "serie": serie}



class TaxaIVAService:
    """Operações tenant-local sobre a tabela de taxas, que não tem FK Empresa."""

    @staticmethod
    def criar_taxa_iva(dados: dict):
        from apps.fiscal.models import TaxaIVAAGT

        payload = dict(dados or {})
        empresa = payload.pop("empresa", None)
        _validar_contexto_tenant(empresa)
        try:
            obj = TaxaIVAAGT(**payload)
            obj.full_clean()
            obj.save()
            return obj
        except (ValidationError, TypeError, ValueError) as exc:
            raise FiscalServiceError(f"Não foi possível criar a taxa de IVA: {exc}") from exc

    @staticmethod
    def obter_taxas_ativas(empresa=None):
        _validar_contexto_tenant(empresa)
        from apps.fiscal.models import TaxaIVAAGT
        return TaxaIVAAGT.objects.filter(ativo=True).order_by("-tax_percentage", "nome")

    @staticmethod
    def calcular_iva(valor_base, taxa):
        try:
            base = Decimal(str(valor_base))
        except Exception as exc:
            raise FiscalServiceError("Valor base inválido.") from exc
        if not base.is_finite() or base < 0:
            raise FiscalServiceError("Valor base deve ser um número não negativo.")
        percentagem = taxa.tax_percentage if taxa.tax_type == "IVA" else Decimal("0.00")
        iva = (base * percentagem / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "valor_base": str(base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "taxa_percentagem": str(percentagem),
            "valor_iva": str(iva),
            "valor_total": str((base + iva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }




class RetencaoFonteService:
    """Operações controladas de criação e confirmação de retenções."""

    @staticmethod
    @transaction.atomic
    def criar_retencao(dados: dict):
        from apps.fiscal.models import RetencaoFonte

        payload = dict(dados or {})
        empresa = payload.pop("empresa", None)  # não existe FK empresa no modelo
        _validar_contexto_tenant(empresa)
        permitidos = {f.name for f in RetencaoFonte._meta.concrete_fields} - {"id", "created_at", "updated_at"}
        desconhecidos = set(payload) - permitidos
        if desconhecidos:
            raise FiscalServiceError(
                "Campos não reconhecidos para RetencaoFonte: " + ", ".join(sorted(desconhecidos))
            )
        try:
            obj = RetencaoFonte(**payload)
            obj.full_clean()
            obj.save()
            return obj
        except (ValidationError, TypeError, ValueError) as exc:
            raise FiscalServiceError(f"Não foi possível criar a retenção: {exc}") from exc

    @staticmethod
    @transaction.atomic
    def processar_pagamento_estado(retencao_id: int, data_pagamento: date | None = None):
        from apps.fiscal.models import RetencaoFonte

        _validar_contexto_tenant()
        try:
            obj = RetencaoFonte.objects.select_for_update().get(pk=retencao_id)
        except RetencaoFonte.DoesNotExist as exc:
            raise FiscalServiceError("Retenção não encontrada neste tenant.") from exc
        if obj.paga_ao_estado:
            return obj
        if data_pagamento and data_pagamento > timezone.localdate():
            raise FiscalServiceError("A data de pagamento ao Estado não pode estar no futuro.")
        obj.paga_ao_estado = True
        obj.save(update_fields=["paga_ao_estado", "updated_at"])
        return obj



class SAFTExportService:
    """Adaptador para o gerador SAF-T oficial existente, sem fabricar XML parcial.

    Procura os nomes de módulos de serviço usados habitualmente pelo projecto.
    Se nenhum estiver instalado, falha explicitamente: não deve ser entregue um
    XML incompleto como se fosse uma exportação fiscal válida.
    """
    @staticmethod
    def gerar_saft_ao(empresa, data_inicio, data_fim):
        _validar_contexto_tenant(empresa)
        if not isinstance(data_inicio, date) or not isinstance(data_fim, date) or data_inicio > data_fim:
            raise FiscalServiceError("Intervalo de datas SAF-T inválido.")
        candidatos = (
            ("apps.fiscal.services.saft_export_service", "gerar_saft_ao"),
            ("apps.fiscal.services.saft_service", "gerar_saft_ao"),
            ("apps.fiscal.services.saft_service", "gerar_saft"),
        )
        for modulo_nome, funcao_nome in candidatos:
            try:
                modulo = importlib.import_module(modulo_nome)
                funcao = getattr(modulo, funcao_nome, None)
                if callable(funcao):
                    return funcao(empresa, data_inicio, data_fim)
            except ModuleNotFoundError as exc:
                if exc.name != modulo_nome:
                    raise
        raise FiscalServiceError(
            "O gerador SAF-T completo não foi disponibilizado no código analisado; "
            "a exportação foi interrompida para não produzir um ficheiro fiscal incompleto."
        )


def validar_documentos_fiscais(empresa=None) -> dict:
    """Validação estrutural, de números e da cadeia de hash dos documentos do tenant."""
    tenant = _validar_contexto_tenant(empresa)
    from apps.fiscal.models import DocumentoFiscal

    docs = DocumentoFiscal.objects.order_by("tipo_documento", "serie", "numero", "pk")
    erros: list[str] = []
    avisos: list[str] = []
    anterior_por_serie: dict[tuple[str, str], str] = {}
    vistos: set[tuple[str, str, int]] = set()

    for doc in docs.iterator():
        if not (doc.numero_documento or "").strip():
            erros.append(f"Documento #{doc.pk}: numero_documento vazio.")
        chave = (doc.tipo_documento, doc.serie, int(doc.numero or 0))
        if chave in vistos:
            erros.append(f"Número duplicado: {doc.tipo_documento} {doc.serie}/{doc.numero}.")
        vistos.add(chave)
        serie_key = (doc.tipo_documento, doc.serie)
        if doc.status != "draft":
            esperado = anterior_por_serie.get(serie_key, "")
            if (doc.hash_anterior or "") != esperado:
                erros.append(f"Cadeia de hash inconsistente em {doc.numero_documento}.")
            if not doc.hash_documento:
                avisos.append(f"Documento emitido sem hash: {doc.numero_documento}.")
            anterior_por_serie[serie_key] = doc.hash_documento or ""

    return {
        "schema": tenant.schema_name,
        "total_documentos": docs.count(),
        "erros": len(erros),
        "avisos": len(avisos),
        "detalhes_erros": erros[:500],
        "detalhes_avisos": avisos[:500],
    }




def gerar_numero_documento(tipo_documento: str, serie: str = 'A') -> Dict[str, Any]:
    """
    Gera o número oficial conforme o modelo DocumentoFiscal.
    Formato exigido: TIPO SERIE/NUMERO
    Exemplo: FR A/1, FT A/2, REC A/1
    """
    from apps.fiscal.models import ContadorDocumento

    ano_atual = timezone.now().year

    with transaction.atomic():
        # select_for_update() bloqueia a linha para evitar duplicidade no PDV
        contador, created = ContadorDocumento.objects.select_for_update().get_or_create(
            tipo_documento=tipo_documento,
            ano=ano_atual,
            serie=serie,
            defaults={'ultimo_numero': 0}
        )

        contador.ultimo_numero += 1
        contador.save()

        # Montagem rigorosa conforme o campo 'numero_documento' do modelo fiscal
        numero_final = f"{tipo_documento} {contador.serie}/{contador.ultimo_numero}"

        return {
            'sequencial': contador.ultimo_numero,
            'formatado': numero_final
        }

