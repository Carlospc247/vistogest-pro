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


def _validar_empresa_no_schema(empresa=None) -> None:
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise FiscalServiceError(
            "Operações de documentos fiscais devem decorrer no schema do tenant, não em public."
        )
    if empresa is not None:
        schema_empresa = getattr(empresa, "schema_name", None)
        if schema_empresa != schema_actual:
            raise FiscalServiceError(
                f"A empresa pertence ao schema '{schema_empresa}', "
                f"mas o schema activo é '{schema_actual}'."
            )

"""Serviço central para o ciclo de vida dos documentos fiscais SOTARQ.

Este módulo deve ser usado no schema do tenant activo. A criação de um
DocumentoFiscal produz sempre um rascunho; a confirmação fiscal é uma operação
explícita através de ``emitir``. A confirmação local não significa, por si só,
que a AGT recebeu ou aceitou o documento.
"""

import logging
from decimal import Decimal
from typing import Any, Optional

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal, DocumentoFiscalLinha, TaxaIVAAGT
from apps.fiscal.services.utils import FiscalServiceError

logger = logging.getLogger("fiscal.documento_service")
_ZERO = Decimal("0.00")


# Campos que não podem ser fornecidos pelo chamador durante a criação.
# A numeração, ATCUD, hash e assinatura devem ser preparados pelo modelo e/ou
# pelo fluxo fiscal central, e nunca aceites arbitrariamente em dados_extra.
_CAMPOS_CONTROLADOS_NA_CRIACAO = frozenset(
    {
        "empresa",
        "empresa_id",
        "tipo_documento",
        "serie",
        "cliente",
        "cliente_id",
        "usuario_criacao",
        "usuario_criacao_id",
        "status",
        "origem",
        "id",
        "pk",
        "numero",
        "numero_documento",
        "atcud",
        "hash_documento",
        "hash_anterior",
        "assinatura_digital",
        "eac_code",
        "periodo_tributacao",
    }
)


def _nome_usuario(usuario: Any) -> str:
    """Obtém um identificador de utilizador sem assumir um tipo concreto."""
    if usuario is None:
        return "sistema"

    get_username = getattr(usuario, "get_username", None)
    if callable(get_username):
        nome = get_username()
        if nome:
            return str(nome)

    return str(getattr(usuario, "username", None) or getattr(usuario, "pk", "utilizador"))


def _validar_empresa_no_schema(empresa: Any = None) -> None:
    """Impede operações fiscais em public ou com uma empresa de outro tenant."""
    schema_actual = getattr(connection, "schema_name", "public")
    if schema_actual == "public":
        raise FiscalServiceError(
            "As operações de documentos fiscais têm de decorrer no schema do tenant, não em 'public'."
        )

    if empresa is not None:
        schema_empresa = getattr(empresa, "schema_name", None)
        if not schema_empresa:
            raise FiscalServiceError(
                "Não foi possível validar o schema da empresa associada ao documento fiscal."
            )
        if schema_empresa != schema_actual:
            raise FiscalServiceError(
                f"A empresa pertence ao schema '{schema_empresa}', mas o schema activo é '{schema_actual}'."
            )


def _validar_campo_concreto(modelo, nome: str):
    """Resolve um campo concreto Django, aceitando também o seu attname (*_id)."""
    try:
        campo = modelo._meta.get_field(nome)
    except FieldDoesNotExist:
        campo = next(
            (item for item in modelo._meta.concrete_fields if item.attname == nome),
            None,
        )

    if campo is None:
        raise FiscalServiceError(f"Campo inválido para {modelo.__name__}: '{nome}'.")

    if (
        not campo.concrete
        or campo.auto_created
        or campo.primary_key
        or not campo.editable
    ):
        raise FiscalServiceError(
            f"O campo '{nome}' de {modelo.__name__} não pode ser definido manualmente."
        )

    return campo


def _registar_log_apos_commit(mensagem: str, *args: Any) -> None:
    """Evita registar uma operação como concluída se a transação for revertida."""
    transaction.on_commit(lambda: logger.info(mensagem, *args))


class DocumentoFiscalService:
    """Operações transacionais para criar e gerir documentos fiscais."""

    CAMPOS_FISCAIS_READONLY = frozenset(
        {
            "tipo_documento",
            "serie",
            "numero",
            "numero_documento",
            "atcud",
            "data_emissao",
            "hora_emissao",
            "data_operacao",
            "cliente",
            "cliente_id",
            "cliente_nif",
            "cliente_nome",
            "cliente_endereco",
            "cliente_email",
            "cliente_telefone",
            "tipo_cliente",
            "valor_base",
            "valor_iva",
            "valor_desconto",
            "valor_retencao",
            "valor_total",
            "moeda",
            "taxa_cambio",
            "hash_documento",
            "hash_anterior",
            "assinatura_digital",
            "eac_code",
            "periodo_tributacao",
        }
    )

    CAMPOS_OPERACIONAIS_EDITAVEIS = frozenset(
        {"comentarios", "metadados", "usuario_modificacao"}
    )

    @staticmethod
    def _obter_documento_bloqueado(documento: DocumentoFiscal) -> DocumentoFiscal:
        """Volta a obter o registo no schema activo, bloqueando-o para escrita."""
        _validar_empresa_no_schema()
        pk = getattr(documento, "pk", None)
        if pk is None:
            raise FiscalServiceError("É necessário indicar um documento fiscal já persistido.")

        try:
            documento_db = DocumentoFiscal.objects.select_for_update().get(pk=pk)
        except DocumentoFiscal.DoesNotExist as exc:
            raise FiscalServiceError(
                f"O documento fiscal '{pk}' não existe no schema activo."
            ) from exc

        empresa = getattr(documento_db, "empresa", None)
        if empresa is not None:
            _validar_empresa_no_schema(empresa)

        return documento_db

    @staticmethod
    @transaction.atomic
    def emitir(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        """Confirma localmente um documento que ainda está em rascunho."""
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        if documento_db.status != "draft":
            raise FiscalServiceError(
                "Apenas documentos em rascunho podem ser emitidos. "
                f"Estado actual: '{documento_db.status}'."
            )

        documento_db.confirmar_documento(usuario)
        _registar_log_apos_commit(
            "Documento fiscal %s confirmado localmente por %s.",
            documento_db.numero_documento,
            _nome_usuario(usuario),
        )
        return documento_db

    @staticmethod
    @transaction.atomic
    def lancar(documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        """Lança um documento previamente confirmado."""
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        if documento_db.status != "confirmed":
            raise FiscalServiceError(
                "Apenas documentos confirmados podem ser lançados. "
                f"Estado actual: '{documento_db.status}'."
            )

        documento_db.lancar_documento(usuario)
        _registar_log_apos_commit(
            "Documento fiscal %s lançado por %s.",
            documento_db.numero_documento,
            _nome_usuario(usuario),
        )
        return documento_db

    @staticmethod
    @transaction.atomic
    def registar_pagamento(
        documento: DocumentoFiscal,
        usuario,
        dados_pagamento: Optional[dict] = None,
    ) -> DocumentoFiscal:
        """Marca o documento fiscal como pago após o pagamento ser confirmado."""
        if dados_pagamento is not None and not isinstance(dados_pagamento, dict):
            raise FiscalServiceError("'dados_pagamento' tem de ser um dicionário ou None.")

        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        if documento_db.status not in {"confirmed", "posted"}:
            raise FiscalServiceError(
                "Apenas documentos confirmados ou lançados podem ser marcados como pagos. "
                f"Estado actual: '{documento_db.status}'."
            )

        documento_db.registar_pagamento(usuario, dados_pagamento)
        _registar_log_apos_commit(
            "Pagamento registado no documento fiscal %s por %s.",
            documento_db.numero_documento,
            _nome_usuario(usuario),
        )
        return documento_db

    @staticmethod
    @transaction.atomic
    def cancelar(
        documento: DocumentoFiscal,
        usuario,
        motivo_codigo: str = "N",
        motivo_texto: str = "",
    ) -> DocumentoFiscal:
        """Cancela o documento através das regras de negócio do próprio modelo."""
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        documento_db.cancelar_documento(
            usuario,
            motivo_codigo=motivo_codigo,
            motivo_texto=motivo_texto,
        )
        _registar_log_apos_commit(
            "Documento fiscal %s cancelado por %s. Código do motivo: %s.",
            documento_db.numero_documento,
            _nome_usuario(usuario),
            motivo_codigo,
        )
        return documento_db

    @staticmethod
    @transaction.atomic
    def rectificar(
        documento: DocumentoFiscal,
        usuario,
        tipo_rectificativo: str = "NC",
        motivo: str = "",
    ) -> DocumentoFiscal:
        """Cria o documento rectificativo através do modelo fiscal."""
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        rectificativo = documento_db.rectificar_documento(
            usuario,
            tipo_rectificativo=tipo_rectificativo,
            motivo=motivo,
        )
        _registar_log_apos_commit(
            "Documento rectificativo %s criado a partir de %s por %s.",
            rectificativo.pk,
            documento_db.numero_documento,
            _nome_usuario(usuario),
        )
        return rectificativo

    @staticmethod
    @transaction.atomic
    def actualizar_comentarios(
        documento: DocumentoFiscal,
        usuario,
        comentarios: str,
    ) -> DocumentoFiscal:
        """Actualiza apenas o comentário operacional, sem alterar dados fiscais."""
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        if comentarios is not None and not isinstance(comentarios, str):
            raise FiscalServiceError("O comentário tem de ser texto.")

        documento_db.comentarios = comentarios or ""
        documento_db.usuario_modificacao = usuario
        documento_db.save(
            _skip_immutability_check=True,
            update_fields=["comentarios", "usuario_modificacao", "updated_at"],
        )
        _registar_log_apos_commit(
            "Comentário do documento fiscal %s actualizado por %s.",
            documento_db.numero_documento,
            _nome_usuario(usuario),
        )
        return documento_db

    @classmethod
    def verificar_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> bool:
        return getattr(documento, "status", None) == "draft"

    @classmethod
    def garantir_pode_editar_campos_fiscais(cls, documento: DocumentoFiscal) -> None:
        if not cls.verificar_pode_editar_campos_fiscais(documento):
            numero = getattr(documento, "numero_documento", None) or getattr(documento, "pk", "desconhecido")
            estado = getattr(documento, "status", "desconhecido")
            raise FiscalServiceError(
                f"O documento '{numero}' está no estado '{estado}' e não pode ter os seus dados "
                "fiscais alterados. Para corrigir um documento confirmado, siga o processo fiscal "
                "de rectificação aplicável."
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
        """Cria um documento em rascunho e, opcionalmente, as suas linhas.

        ``dados_extra`` só aceita campos concretos e editáveis do modelo. Não pode
        substituir a empresa, o tipo, a série, o cliente, o estado, a origem, o
        criador, a numeração, o ATCUD, o hash ou a assinatura do documento.
        Cada linha deve usar nomes reais do modelo ``DocumentoFiscalLinha``.
        """
        _validar_empresa_no_schema(empresa)
        if empresa is None:
            raise FiscalServiceError("É obrigatório indicar a empresa do documento fiscal.")
        if not tipo_documento or not isinstance(tipo_documento, str):
            raise FiscalServiceError("É obrigatório indicar um tipo de documento fiscal válido.")
        if not isinstance(serie, str) or not serie.strip():
            raise FiscalServiceError("A série do documento fiscal tem de ser um texto não vazio.")

        if dados_extra is not None and not isinstance(dados_extra, dict):
            raise FiscalServiceError("'dados_extra' tem de ser um dicionário ou None.")
        if linhas is not None and not isinstance(linhas, (list, tuple)):
            raise FiscalServiceError("'linhas' tem de ser uma lista, uma tupla ou None.")

        dados_extra = dict(dados_extra or {})
        linhas = list(linhas or [])

        conflitos = _CAMPOS_CONTROLADOS_NA_CRIACAO.intersection(dados_extra)
        if conflitos:
            raise FiscalServiceError(
                "Não envie campos controlados pelo serviço dentro de 'dados_extra': "
                + ", ".join(sorted(conflitos))
            )

        for nome in dados_extra:
            _validar_campo_concreto(DocumentoFiscal, nome)

        # Quando são fornecidas linhas, os valores totais devem ser calculados a
        # partir delas; não aceitamos totais fornecidos pelo chamador como fonte.
        if linhas:
            for campo in (
                "valor_base",
                "valor_iva",
                "valor_desconto",
                "valor_retencao",
                "valor_total",
            ):
                dados_extra.pop(campo, None)
            dados_extra.update(
                {
                    "valor_base": _ZERO,
                    "valor_iva": _ZERO,
                    "valor_desconto": _ZERO,
                    "valor_retencao": _ZERO,
                    "valor_total": _ZERO,
                }
            )

        documento = DocumentoFiscal(
            tipo_documento=tipo_documento,
            serie=serie.strip(),
            cliente=cliente,
            usuario_criacao=usuario,
            origem="sistema",
            status="confirmed",
            **dados_extra,
        )

        if not documento.data_emissao:
            documento.data_emissao = timezone.now().date()

        if cliente is not None:
            documento.cliente_nome = (
                getattr(cliente, "nome_exibicao", None)
                or getattr(cliente, "nome_completo", None)
                or getattr(cliente, "razao_social", None)
                or getattr(cliente, "nome", None)
                or str(cliente)
            )
            documento.cliente_nif = getattr(cliente, "nif", "") or ""
            documento.cliente_email = getattr(cliente, "email", "") or ""
            documento.cliente_telefone = getattr(cliente, "telefone", "") or ""
            if hasattr(cliente, "endereco"):
                documento.cliente_endereco = str(getattr(cliente, "endereco", "") or "")

        # O método save() do modelo é o responsável pelos preparativos fiscais
        # existentes no projecto (snapshot, numeração e ATCUD, conforme aplicável).
        documento.save()

        for indice, dados_linha in enumerate(linhas, start=1):
            if not isinstance(dados_linha, dict):
                raise FiscalServiceError(f"A linha {indice} tem de ser um dicionário de campos.")

            dados_linha = dict(dados_linha)
            # A relação com o documento é sempre fixada aqui, nunca pelo chamador.
            dados_linha.pop("documento", None)
            dados_linha.pop("documento_id", None)
            dados_linha.setdefault("numero_linha", indice)

            obrigatorios = {"codigo_produto", "descricao", "quantidade", "preco_unitario"}
            em_falta = obrigatorios.difference(dados_linha)
            if em_falta:
                raise FiscalServiceError(
                    f"A linha {indice} não contém os campos obrigatórios: "
                    + ", ".join(sorted(em_falta))
                    + "."
                )

            tem_taxa = "taxa_iva" in dados_linha
            tem_taxa_id = "taxa_iva_id" in dados_linha
            if tem_taxa == tem_taxa_id:
                raise FiscalServiceError(
                    f"A linha {indice} deve indicar exactamente um dos campos 'taxa_iva' ou 'taxa_iva_id'."
                )

            if tem_taxa:
                taxa = dados_linha["taxa_iva"]
                if taxa is None:
                    raise FiscalServiceError(f"A linha {indice} tem uma taxa de IVA nula.")
                if not isinstance(taxa, TaxaIVAAGT):
                    dados_linha["taxa_iva_id"] = dados_linha.pop("taxa_iva")
            elif dados_linha["taxa_iva_id"] in (None, ""):
                raise FiscalServiceError(f"A linha {indice} tem um identificador de taxa de IVA inválido.")

            if "produto" in dados_linha and "produto_id" in dados_linha:
                raise FiscalServiceError(
                    f"A linha {indice} não pode definir 'produto' e 'produto_id' ao mesmo tempo."
                )
            if "produto" in dados_linha and dados_linha["produto"] is not None:
                produto = dados_linha["produto"]
                if not hasattr(produto, "_meta"):
                    dados_linha["produto_id"] = dados_linha.pop("produto")

            try:
                linha = DocumentoFiscalLinha(documento=documento, **dados_linha)
                linha.full_clean()
                linha.save()
            except (ValidationError, TypeError, ValueError, IntegrityError) as exc:
                raise FiscalServiceError(
                    f"Erro ao validar ou guardar a linha {indice} do documento fiscal: {exc}"
                ) from exc

        if linhas:
            documento.refresh_from_db()

        _registar_log_apos_commit(
            "Documento fiscal %s criado como rascunho por %s.",
            documento.pk,
            _nome_usuario(usuario),
        )
        return documento

    @staticmethod
    @transaction.atomic
    def recalcular_totais(documento: DocumentoFiscal) -> DocumentoFiscal:
        """Recalcula os totais pelas linhas; só é permitido em rascunhos.

        Mantém a funcionalidade da implementação antiga, mas reutiliza o mesmo
        bloqueio transaccional e impede alterar os totais após a confirmação.
        """
        documento_db = DocumentoFiscalService._obter_documento_bloqueado(documento)
        DocumentoFiscalService.garantir_pode_editar_campos_fiscais(documento_db)

        valor_base = _ZERO
        valor_iva = _ZERO
        valor_total = _ZERO
        for linha in documento_db.linhas.all():
            valor_base += getattr(linha, "valor_liquido", _ZERO) or _ZERO
            valor_iva += getattr(linha, "valor_iva_linha", _ZERO) or _ZERO
            valor_total += getattr(linha, "valor_total_linha", _ZERO) or _ZERO

        documento_db.valor_base = valor_base
        documento_db.valor_iva = valor_iva
        documento_db.valor_total = valor_total
        documento_db.save(update_fields=["valor_base", "valor_iva", "valor_total"])
        return documento_db

    # Wrappers de compatibilidade: mantêm chamadas antigas a funcionar sem
    # duplicar a lógica das transições. Podem ser removidos após auditar os usos.
    @classmethod
    def confirmar_documento(cls, documento: DocumentoFiscal, usuario) -> DocumentoFiscal:
        return cls.emitir(documento, usuario)

    @classmethod
    def cancelar_documento(
        cls,
        documento: DocumentoFiscal,
        usuario,
        motivo: str = "",
    ) -> DocumentoFiscal:
        return cls.cancelar(documento, usuario, motivo_texto=motivo)

