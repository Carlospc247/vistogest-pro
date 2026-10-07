# apps/fiscal/services/documento_fiscal_service.py
"""
DocumentoFiscalService — Secção 3 do PLANO_IMPLEMENTACAO.md.

Camada de service centralizada para todas as transições de estado de
DocumentoFiscal. É o único ponto legítimo para emitir, lançar, pagar,
cancelar e rectificar documentos fiscais.

REGRA FUNDAMENTAL:
    Um documento fiscal emitido (status != 'draft') NUNCA deve ter os seus
    campos fiscais essenciais sobrescritos directamente.
    Todas as correcções passam por documentos rectificativos (NC/ND/RE).

NUNCA chamar document.save() directamente com campos fiscais alterados
fora deste service. Sempre usar os métodos abaixo.
"""
import logging
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.fiscal.models import DocumentoFiscal
from .utils import FiscalServiceError

logger = logging.getLogger('fiscal.documento_service')


class DocumentoFiscalService:
    """
    Service central para transições de estado de DocumentoFiscal.
    Todos os métodos são @staticmethod — não é necessário instanciar.
    """

    # ── Campos fiscais — NUNCA alterar após emissão ────────────────────────
    CAMPOS_FISCAIS_READONLY = frozenset([
        'tipo_documento', 'serie', 'numero', 'numero_documento', 'atcud',
        'data_emissao', 'hora_emissao', 'data_operacao',
        'cliente', 'cliente_id', 'cliente_nif', 'cliente_nome',
        'valor_base', 'valor_iva', 'valor_desconto', 'valor_retencao', 'valor_total',
        'moeda', 'taxa_cambio',
        'hash_documento', 'hash_anterior', 'assinatura_digital',
        'eac_code', 'periodo_tributacao',
    ])

    # ── Campos operacionais — permitidos editar após emissão ───────────────
    CAMPOS_OPERACIONAIS_EDITAVEIS = frozenset([
        'comentarios',       # observações do operador
        'metadados',         # dados internos do sistema (não fiscais)
        'usuario_modificacao',
    ])

    # ─────────────────────────────────────────────────────────────────────────
    # Transições de estado
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def emitir(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        """
        DRAFT → CONFIRMED.
        Gera hash, assina o documento e torna-o imutável nos campos fiscais.
        """
        if documento.status != 'draft':
            raise FiscalServiceError(
                f"Apenas rascunhos podem ser emitidos. "
                f"Status actual: '{documento.status}'."
            )
        documento.confirmar_documento(usuario)
        logger.info("Documento %s emitido por %s.", documento.numero_documento, usuario.username)
        return documento

    @staticmethod
    @transaction.atomic
    def lancar(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        """CONFIRMED → POSTED."""
        if documento.status != 'confirmed':
            raise FiscalServiceError(
                f"Apenas documentos confirmados podem ser lançados. "
                f"Status actual: '{documento.status}'."
            )
        documento.lancar_documento(usuario)
        logger.info("Documento %s lançado por %s.", documento.numero_documento, usuario.username)
        return documento

    @staticmethod
    @transaction.atomic
    def registar_pagamento(
        documento: DocumentoFiscal,
        usuario,
        dados_pagamento: Optional[dict] = None,
    ) -> DocumentoFiscal:
        """CONFIRMED/POSTED → PAID."""
        if documento.status not in ('confirmed', 'posted'):
            raise FiscalServiceError(
                f"Apenas documentos confirmados ou lançados podem ser marcados como pagos. "
                f"Status actual: '{documento.status}'."
            )
        documento.registar_pagamento(usuario, dados_pagamento)
        logger.info("Pagamento registado em %s por %s.", documento.numero_documento, usuario.username)
        return documento

    @staticmethod
    @transaction.atomic
    def cancelar(
        documento: DocumentoFiscal,
        usuario,
        motivo_codigo: str = 'N',
        motivo_texto: str = '',
    ) -> DocumentoFiscal:
        """
        Cancela o documento (CONFIRMED/POSTED/DRAFT → CANCELLED).
        motivo_codigo: 'I' ou 'N' (obrigatório para documentos já emitidos).
        """
        documento.cancelar_documento(usuario, motivo_codigo=motivo_codigo, motivo_texto=motivo_texto)
        logger.info(
            "Documento %s cancelado por %s. Motivo: %s.",
            documento.numero_documento, usuario.username, motivo_codigo
        )
        return documento

    @staticmethod
    @transaction.atomic
    def rectificar(
        documento: DocumentoFiscal,
        usuario,
        tipo_rectificativo: str = 'NC',
        motivo: str = '',
    ) -> DocumentoFiscal:
        """
        Marca o documento como RECTIFIED e cria o rectificativo em 'draft'.
        Devolve o novo DocumentoFiscal rectificativo.
        """
        correctivo = documento.rectificar_documento(
            usuario, tipo_rectificativo=tipo_rectificativo, motivo=motivo
        )
        logger.info(
            "Rectificativo %s criado a partir de %s por %s.",
            correctivo.pk, documento.numero_documento, usuario.username
        )
        return correctivo

    # ─────────────────────────────────────────────────────────────────────────
    # Actualização de campos operacionais (permitida após emissão)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def actualizar_comentarios(
        documento: DocumentoFiscal,
        usuario,
        comentarios: str,
    ) -> DocumentoFiscal:
        """
        Actualiza o campo 'comentarios' (operacional — não fiscal).
        É o único campo que pode ser editado após a emissão.
        """
        documento.comentarios = comentarios
        documento.usuario_modificacao = usuario
        # _skip_immutability_check=True porque comentarios é campo operacional
        documento.save(
            _skip_immutability_check=True,
            update_fields=['comentarios', 'usuario_modificacao', 'updated_at'],
        )
        return documento

    # ─────────────────────────────────────────────────────────────────────────
    # Protecção explícita contra edições directas
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def verificar_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> bool:
        """
        Devolve True apenas se o documento está em 'draft'.
        Usar antes de qualquer edição manual a campos fiscais.
        """
        return documento.status == 'draft'

    @classmethod
    def garantir_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> None:
        """
        Levanta FiscalServiceError se o documento não está em rascunho.
        Usar no início de qualquer view/endpoint de edição fiscal.
        """
        if not cls.verificar_pode_editar_campos_fiscais(documento):
            raise FiscalServiceError(
                f"O documento '{documento.numero_documento}' está no status "
                f"'{documento.status}' e não pode ter os seus dados fiscais alterados. "
                f"Para corrigir, emita um documento rectificativo (NC/ND)."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Criar documento (wrapper que garante estado inicial correcto)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def criar_documento(
        empresa,
        tipo_documento: str,
        usuario,
        cliente=None,
        serie: str = 'A',
        dados_extra: Optional[dict] = None,
        linhas: Optional[list] = None,
    ) -> DocumentoFiscal:
        """
        Cria um DocumentoFiscal em estado 'draft'.
        Não emite — emitir requer chamada explícita a DocumentoFiscalService.emitir().
        """
        dados_extra = dados_extra or {}
        doc = DocumentoFiscal(
            empresa=empresa,
            tipo_documento=tipo_documento,
            serie=serie,
            cliente=cliente,
            usuario_criacao=usuario,
            origem='sistema',
            status='draft',
            **dados_extra,
        )
        # Garantir campos obrigatórios mínimos
        if not doc.cliente_nome and cliente:
            doc.cliente_nome = getattr(cliente, 'nome_completo', str(cliente))
        if not doc.cliente_nif and cliente:
            doc.cliente_nif = getattr(cliente, 'nif', '') or ''
        if not doc.data_emissao:
            from django.utils import timezone
            doc.data_emissao = timezone.now().date()

        doc.save(_skip_immutability_check=True)
        logger.info(
            "DocumentoFiscal %s criado (draft) por %s.",
            doc.pk, usuario.username
        )
        return doc
