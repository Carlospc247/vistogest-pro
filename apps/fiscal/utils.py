#apps/fiscal/utils.py
import logging
from django.utils import timezone
from decimal import Decimal
import hashlib
from django.utils.encoding import force_bytes

from apps.fiscal.models import DocumentoFiscal

logger = logging.getLogger(__name__)

def validar_documentos_fiscais(empresa):
    """
    Executa validações em todos os documentos fiscais emitidos pela empresa.

    Retorna um dicionário com contagem de erros e avisos.
    """
    erros = []
    avisos = []

    documentos = DocumentoFiscal.objects.filter(empresa=empresa).order_by('-data_emissao')

    if not documentos.exists():
        avisos.append("Nenhum documento fiscal encontrado para validação.")
        logger.warning(f"Nenhum documento fiscal encontrado para {empresa.nome}")
        return {
            "status": "ok",
            "mensagem": "Nenhum documento encontrado.",
            "erros": len(erros),
            "avisos": len(avisos),
            "detalhes": {"erros": erros, "avisos": avisos},
        }

    for doc in documentos:
        # 🔹 1. Validação de NIF
        if not doc.nif_cliente or len(str(doc.nif_cliente)) < 5:
            erros.append(f"Documento {doc.numero} - NIF inválido ou ausente.")

        # 🔹 2. Validação de valores
        if doc.total < Decimal("0.00"):
            erros.append(f"Documento {doc.numero} - Valor total negativo ({doc.total}).")

        # 🔹 3. Verificação de data futura
        if doc.data_emissao > timezone.now().date():
            avisos.append(f"Documento {doc.numero} - Data de emissão está no futuro ({doc.data_emissao}).")

        # 🔹 4. Verificação de assinatura digital
        if not doc.hash_assinatura:
            avisos.append(f"Documento {doc.numero} - Assinatura digital ausente.")

        # 🔹 5. Verificação de estado
        if not doc.estado or doc.estado not in ["emitido", "cancelado", "pago"]:
            avisos.append(f"Documento {doc.numero} - Estado desconhecido: {doc.estado}.")

    logger.info(f"Validação concluída para {empresa.nome}: {len(erros)} erros, {len(avisos)} avisos.")

    return {
        "status": "ok",
        "empresa": empresa.nome,
        "total_documentos": documentos.count(),
        "erros": len(erros),
        "avisos": len(avisos),
        "detalhes": {
            "erros": erros,
            "avisos": avisos,
        },
        "timestamp": timezone.now().isoformat(),
    }




def gerar_hash_documento(documento):
    """
    Gera hash encadeado SAF-T AO com base no documento anterior.
    """
    from apps.fiscal.models import DocumentoFiscal

    ultimo_doc = (
        DocumentoFiscal.objects
        .filter(empresa=documento.empresa)
        .exclude(hash_documento=None)
        .order_by("-id")
        .first()
    )

    hash_anterior = ultimo_doc.hash_documento if ultimo_doc else ""
    base_str = f"{hash_anterior}{documento.numero}{documento.data_emissao}{documento.valor_total or ''}"

    return hashlib.sha1(force_bytes(base_str)).hexdigest().upper()

import hashlib
from apps.fiscal.models import DocumentoFiscal

def gerar_hash_anterior(documento):
    # Pega o último documento da mesma série e tipo
    anterior = (
        DocumentoFiscal.objects
        .filter(empresa=documento.empresa, serie=documento.serie, tipo_documento=documento.tipo_documento)
        .exclude(pk=documento.pk)
        .order_by('-numero')
        .first()
    )
    return anterior.hash_documento if anterior else ''

def gerar_hash_documento(documento, hash_anterior=''):
    base_str = f"{hash_anterior}{documento.numero}{documento.data_emissao}{getattr(documento, 'total_geral', '')}"
    hash_result = hashlib.sha1(base_str.encode('utf-8')).hexdigest().upper()
    return hash_result


# apps/fiscal/utils.py
def gerar_atcud(documento):
    """
    Gera o ATCUD para um documento fiscal.

    ATCUD = <codigo_validacao_empresa>-<numero_documento>
    """
    if not hasattr(documento.empresa, 'codigo_validacao'):
        raise ValueError("Empresa não possui 'codigo_validacao' definido para ATCUD.")
    
    codigo_validacao = documento.empresa.codigo_validacao
    numero_documento = documento.numero_documento or documento.id

    return f"{codigo_validacao}-{numero_documento}"



