import hashlib
import base64
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

def gerar_hash_anterior(documento: Any) -> str:
    """
    Recupera o hash do documento anterior da mesma série e tipo.
    Retorna string vazia se não houver anterior.
    """
    from apps.fiscal.models import DocumentoFiscal
    
    # Evita erro circular se o modelo não estiver carregado, 
    # mas idealmente o caller passa o objeto já com acesso ao ORM.
    
    anterior = (
        DocumentoFiscal.objects
        .filter(
            empresa=documento.empresa, 
            serie=documento.serie, 
            tipo_documento=documento.tipo_documento
        )
        .exclude(pk=documento.pk)
        .order_by('-numero') # Assumindo que 'numero' é sequencial
        .first()
    )
    
    if anterior and anterior.hash_documento:
        return anterior.hash_documento
    return ""

def calcular_hash_documento(doc_data: Dict[str, Any], hash_anterior: str = "") -> str:
    """
    Calcula hash SHA256 (base64) de um documento, conforme padrão AGT.
    
    doc_data deve conter:
    - data (YYYY-MM-DD)
    - tipo_documento (FT, FR, etc)
    - serie
    - numero
    - valor_total (string ou decimal)
    """
    ordenado = {
        "data": str(doc_data.get("data", "")),
        "tipo_documento": str(doc_data.get("tipo_documento", "")),
        "serie": str(doc_data.get("serie", "")),
        "numero": str(doc_data.get("numero", "")),
        "valor_total": str(doc_data.get("valor_total", "0.00")),
        "hash_anterior": hash_anterior,
    }
    
    texto = ";".join(f"{k}:{v}" for k, v in sorted(ordenado.items()))
    digest = hashlib.sha256(texto.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("utf-8")

def gerar_hash_documento(documento: Any) -> str:
    """
    Wrapper para calcular hash diretamente de um objeto DocumentoFiscal.
    """
    hash_anterior = gerar_hash_anterior(documento)
    
    doc_data = {
        "data": documento.data_emissao, # Assumindo que é date ou datetime
        "tipo_documento": documento.tipo_documento,
        "serie": getattr(documento, 'serie', 'DEFAULT'),
        "numero": documento.numero,
        "valor_total": documento.valor_total or "0.00"
    }
    
    return calcular_hash_documento(doc_data, hash_anterior)

def gerar_atcud(nif: str, serie: str, numero: str, hash_documento: str) -> str:
    """
    Gera ATCUD conforme padrão AGT (SHA256).
    Formato base: NIF|Serie|Numero|Hash
    Retorna: Hexdigest uppercase
    """
    base = f"{nif}|{serie}|{numero}|{hash_documento}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest().upper()

def gerar_atcud_documento(documento: Any) -> str:
    """
    Wrapper para gerar ATCUD diretamente de um objeto DocumentoFiscal.
    """
    empresa = documento.empresa
    nif = empresa.nif or empresa.numero_contribuinte or ""
    serie = getattr(documento, 'serie', 'DEFAULT') # Ajustar default conforme modelo
    numero = str(documento.numero)
    hash_doc = documento.hash_documento or ""
    
    return gerar_atcud(nif, serie, numero, hash_doc)
