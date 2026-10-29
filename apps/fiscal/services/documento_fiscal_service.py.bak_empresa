# apps/fiscal/services/documento_fiscal_service.py
"""Serviços centrais para o ciclo de vida dos documentos fiscais SOTARQ.

Os documentos são tenant-local. A FK Empresa aponta para o registo partilhado
em public e tem de corresponder ao schema activo antes de qualquer gravação.
"""
import logging
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal, DocumentoFiscalLinha, TaxaIVAAGT
from apps.fiscal.services.utils import FiscalServiceError

logger = logging.getLogger("fiscal.documento_service")


def _validar_empresa_no_schema(empresa) -> None:
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise FiscalServiceError(
            "Operações de documentos fiscais devem decorrer no schema do tenant, não em public."
        )
    if empresa is None:
        raise FiscalServiceError("A empresa do tenant é obrigatória para criar o documento fiscal.")
    schema_empresa = getattr(empresa, "schema_name", None)
    if schema_empresa != schema_actual:
        raise FiscalServiceError(
            f"A empresa '{getattr(empresa, 'nome', empresa.pk)}' pertence ao schema "
            f"'{schema_empresa}', mas o schema activo é '{schema_actual}'."
        )


class DocumentoFiscalService:
    """Transições controladas de estado e criação de documentos fiscais."""

    CAMPOS_FISCAIS_READONLY = frozenset({
        "tipo_documento", "serie", "numero", "numero_documento", "atcud",
        "data_emissao", "hora_emissao", "data_operacao", "cliente", "cliente_id",
        "cliente_nif", "cliente_nome", "cliente_endereco", "cliente_email",
        "cliente_telefone", "tipo_cliente", "valor_base", "valor_iva",
        "valor_desconto", "valor_retencao", "valor_total", "moeda", "taxa_cambio",
        "hash_documento", "hash_anterior", "assinatura_digital", "eac_code",
        "periodo_tributacao",
    })

    CAMPOS_OPERACIONAIS_EDITAVEIS = frozenset({
        "comentarios", "metadados", "usuario_modificacao",
    })

    @staticmethod
    @transaction.atomic
    def emitir(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        if documento.status != "draft":
            raise FiscalServiceError(
                f"Apenas rascunhos podem ser emitidos. Status actual: '{documento.status}'."
            )
        documento.confirmar_documento(usuario)
        logger.info("Documento %s emitido por %s.", documento.numero_documento, usuario.username)
        return documento

    @staticmethod
    @transaction.atomic
    def lancar(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        if documento.status != "confirmed":
            raise FiscalServiceError(
                f"Apenas documentos confirmados podem ser lançados. Status actual: '{documento.status}'."
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
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        if documento.status not in ("confirmed", "posted"):
            raise FiscalServiceError(
                "Apenas documentos confirmados ou lançados podem ser marcados como pagos. "
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
        motivo_codigo: str = "N",
        motivo_texto: str = "",
    ) -> DocumentoFiscal:
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        documento.cancelar_documento(usuario, motivo_codigo=motivo_codigo, motivo_texto=motivo_texto)
        logger.info(
            "Documento %s cancelado por %s. Motivo: %s.",
            documento.numero_documento, usuario.username, motivo_codigo,
        )
        return documento

    @staticmethod
    @transaction.atomic
    def rectificar(
        documento: DocumentoFiscal,
        usuario,
        tipo_rectificativo: str = "NC",
        motivo: str = "",
    ) -> DocumentoFiscal:
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        correctivo = documento.rectificar_documento(
            usuario, tipo_rectificativo=tipo_rectificativo, motivo=motivo
        )
        logger.info(
            "Rectificativo %s criado a partir de %s por %s.",
            correctivo.pk, documento.numero_documento, usuario.username,
        )
        return correctivo

    @staticmethod
    @transaction.atomic
    def actualizar_comentarios(
        documento: DocumentoFiscal,
        usuario,
        comentarios: str,
    ) -> DocumentoFiscal:
        _validar_empresa_no_schema(documento.empresa)
        documento = DocumentoFiscal.objects.select_for_update().get(pk=documento.pk)
        _validar_empresa_no_schema(documento.empresa)
        documento.comentarios = comentarios or ""
        documento.usuario_modificacao = usuario
        documento.save(
            _skip_immutability_check=True,
            update_fields=["comentarios", "usuario_modificacao", "updated_at"],
        )
        return documento

    @classmethod
    def verificar_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> bool:
        return documento.status == "draft"

    @classmethod
    def garantir_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> None:
        if not cls.verificar_pode_editar_campos_fiscais(documento):
            raise FiscalServiceError(
                f"O documento '{documento.numero_documento}' está no status '{documento.status}' "
                "e não pode ter os seus dados fiscais alterados. Para corrigir, emita um "
                "documento rectificativo (NC/ND)."
            )

    @staticmethod
    @transaction.atomic
    def criar_documento(
        empresa,
        tipo_documento: str,
        usuario,
        cliente=None,
        serie: str = "A",
        dados_extra: Optional[dict] = None,
        linhas: Optional[list] = None,
    ) -> DocumentoFiscal:
        """Cria um rascunho e, opcionalmente, as respectivas linhas.

        `dados_extra` aceita campos concretos de DocumentoFiscal, mas não pode
        substituir campos de controlo (empresa, tipo, série, estado ou criador).
        Cada linha deve usar os nomes reais do modelo DocumentoFiscalLinha.
        """
        _validar_empresa_no_schema(empresa)
        dados_extra = dict(dados_extra or {})
        linhas = list(linhas or [])

        reservados = {
            "empresa", "empresa_id", "tipo_documento", "serie", "cliente", "cliente_id",
            "usuario_criacao", "status", "origem", "id", "pk",
        }
        conflitos = reservados.intersection(dados_extra)
        if conflitos:
            raise FiscalServiceError(
                "Não envie campos de controlo dentro de dados_extra: "
                + ", ".join(sorted(conflitos))
            )

        # Detecta previamente nomes errados para não ocultar erros de integração.
        for nome in dados_extra:
            try:
                campo = DocumentoFiscal._meta.get_field(nome)
            except Exception as exc:
                raise FiscalServiceError(f"Campo inválido em dados_extra: '{nome}'.") from exc
            if not campo.concrete or campo.auto_created or campo.primary_key:
                raise FiscalServiceError(f"Campo não editável em dados_extra: '{nome}'.")

        # Quando as linhas são a fonte dos totais, começa-se com os totais a zero.
        if linhas:
            for campo in ("valor_base", "valor_iva", "valor_desconto", "valor_retencao", "valor_total"):
                dados_extra.pop(campo, None)
            dados_extra.update({
                "valor_base": 0,
                "valor_iva": 0,
                "valor_desconto": 0,
                "valor_retencao": 0,
                "valor_total": 0,
            })

        doc = DocumentoFiscal(
            empresa=empresa,
            tipo_documento=tipo_documento,
            serie=serie,
            cliente=cliente,
            usuario_criacao=usuario,
            origem="sistema",
            status="draft",
            **dados_extra,
        )

        if not doc.data_emissao:
            doc.data_emissao = timezone.now().date()
        if cliente:
            doc.cliente_nome = (
                getattr(cliente, "nome_exibicao", None)
                or getattr(cliente, "nome_completo", None)
                or getattr(cliente, "razao_social", None)
                or getattr(cliente, "nome", None)
                or str(cliente)
            )
            doc.cliente_nif = getattr(cliente, "nif", "") or ""
            doc.cliente_email = getattr(cliente, "email", "") or ""
            doc.cliente_telefone = getattr(cliente, "telefone", "") or ""
            if hasattr(cliente, "endereco"):
                doc.cliente_endereco = str(getattr(cliente, "endereco", "") or "")

        # DocumentoFiscal.save prepara o snapshot, número, ATCUD e período antes de validar.
        doc.save()

        for idx, dados_linha in enumerate(linhas, start=1):
            if not isinstance(dados_linha, dict):
                raise FiscalServiceError(f"A linha {idx} deve ser um dicionário de campos.")
            dados_linha = dict(dados_linha)
            dados_linha.pop("documento", None)
            dados_linha.pop("documento_id", None)
            dados_linha.setdefault("numero_linha", idx)

            required = {"codigo_produto", "descricao", "quantidade", "preco_unitario"}
            missing = required.difference(dados_linha)
            if missing:
                raise FiscalServiceError(
                    f"A linha {idx} não contém os campos obrigatórios: {', '.join(sorted(missing))}."
                )
            if "taxa_iva" not in dados_linha and "taxa_iva_id" not in dados_linha:
                raise FiscalServiceError(f"A linha {idx} precisa de taxa_iva ou taxa_iva_id.")

            # Permite passar IDs nas chaves sem sufixo e converte para *_id do Django.
            if "taxa_iva" in dados_linha and not isinstance(dados_linha["taxa_iva"], TaxaIVAAGT):
                dados_linha["taxa_iva_id"] = dados_linha.pop("taxa_iva")
            if "produto" in dados_linha and dados_linha["produto"] is not None:
                produto = dados_linha["produto"]
                if not hasattr(produto, "_meta"):
                    dados_linha["produto_id"] = dados_linha.pop("produto")
            try:
                linha = DocumentoFiscalLinha(documento=doc, **dados_linha)
                linha.save()
            except (ValidationError, TypeError, ValueError) as exc:
                raise FiscalServiceError(f"Erro na linha {idx} do documento: {exc}") from exc

        if linhas:
            doc.refresh_from_db()
        logger.info("DocumentoFiscal %s criado como draft por %s.", doc.pk, usuario.username)
        return doc
