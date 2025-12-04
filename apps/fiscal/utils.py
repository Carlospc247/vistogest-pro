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







