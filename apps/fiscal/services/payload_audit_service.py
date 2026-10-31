# apps/fiscal/services/payload_audit_service.py
"""
Auditoria estrutural e comparação de payloads AGT v2.0.

Não afirma validar criptograficamente JWS. Verifica presença, estrutura,
correspondência documental e consistência dos valores que consegue recalcular.
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from datetime import date, datetime

from django.db import connection, transaction
from django.utils import timezone

from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.models_payload_agt import PayloadAGT, AuditoriaPayloadAGT

logger = logging.getLogger("fiscal.payload_audit")
VERSAO_REGRAS = "agt-v2.0-inspector-1"
CENTAVO = Decimal("0.01")
RECEIPT_TYPES = {"AR", "RG"}

def _dec(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None

def _iso(value):
    if isinstance(value, datetime):
        return timezone.localtime(value).date().isoformat() if timezone.is_aware(value) else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None

class PayloadAuditService:
    @staticmethod
    def _tenant():
        schema = getattr(connection, "schema_name", "public")
        if not schema or schema == "public":
            raise RuntimeError("A auditoria de payload só pode correr num schema tenant.")
        return schema

    @staticmethod
    def _find(items, severity, code, path, message, expected=None, actual=None):
        items.append({
            "severidade": severity,
            "codigo": code,
            "campo": path,
            "mensagem": message,
            "esperado": expected,
            "encontrado": actual,
        })

    @classmethod
    def _compare(cls, findings, code, path, expected, actual, tolerance=None):
        if expected is None:
            cls._find(
                findings, "NAO_VERIFICAVEL", code, path,
                "Não existe valor local suficiente para comparar.",
                actual=actual,
            )
            return
        if tolerance is not None:
            e, a = _dec(expected), _dec(actual)
            if e is None or a is None:
                cls._find(findings, "ERRO", code, path, "Um dos valores não é numérico.", expected, actual)
            elif abs(e - a) > tolerance:
                cls._find(findings, "ERRO", code, path, "Divergência entre DocumentoFiscal e payload.", str(e), str(a))
            else:
                cls._find(findings, "CONFORME", code, path, "Valores coincidem dentro da tolerância.", str(e), str(a))
            return
        if str(expected) != str(actual):
            cls._find(findings, "ERRO", code, path, "Divergência entre DocumentoFiscal e payload.", expected, actual)
        else:
            cls._find(findings, "CONFORME", code, path, "Valor coincidente.", expected, actual)

    @classmethod
    def _totais_documento_local(cls, doc):
        """
        Replica os valores de linha usados pelo AGTPayloadBuilder:
        net = soma de valor_liquido; imposto = taxContribution por linha.
        """
        net = Decimal("0.00")
        tax = Decimal("0.00")
        linhas = list(doc.linhas.select_related("taxa_iva").all().order_by("numero_linha", "pk"))
        if not linhas:
            return None, None, None, "Documento sem linhas fiscais locais."

        for linha in linhas:
            liquido = _dec(linha.valor_liquido)
            if liquido is None:
                return None, None, None, f"Linha {linha.pk}: valor_liquido inválido."
            net += liquido

            taxa = getattr(linha, "taxa_iva", None)
            tax_type = str(getattr(taxa, "tax_type", "") or "").upper()
            if tax_type == "NS":
                imposto = Decimal("0.00")
            elif tax_type == "IVA":
                imposto = _dec(getattr(linha, "valor_iva_linha", None))
            elif tax_type in {"IS", "IEC"}:
                aliases = (
                    "valor_imposto_linha", "valor_selo_linha",
                    "valor_iec_linha", "valor_ceoc_linha", "valor_imposto",
                )
                raw = next(
                    (getattr(linha, name) for name in aliases
                     if getattr(linha, name, None) is not None),
                    None,
                )
                imposto = _dec(raw)
                if imposto is None and str(getattr(taxa, "tax_code", "")).upper() == "ISE":
                    imposto = Decimal("0.00")
            else:
                return None, None, None, f"Linha {linha.pk}: taxType {tax_type!r} não verificável."

            if imposto is None:
                return None, None, None, f"Linha {linha.pk}: montante fiscal não persistido."
            tax += imposto.quantize(CENTAVO, rounding=ROUND_CEILING)

        net = net.quantize(CENTAVO)
        tax = tax.quantize(CENTAVO)
        gross = (net + tax).quantize(CENTAVO)
        return net, tax, gross, None

    @classmethod
    def _totais_recibo(cls, doc):
        metadata = doc.metadados if isinstance(doc.metadados, dict) else {}
        receipt = metadata.get("paymentReceipt") or {}
        sources = receipt.get("sourceDocuments") if isinstance(receipt, dict) else None
        if not isinstance(sources, list) or not sources:
            return None, None, None, "paymentReceipt.sourceDocuments não está disponível."

        net = Decimal("0.00")
        tax = Decimal("0.00")
        for item in sources:
            if not isinstance(item, dict):
                return None, None, None, "Fonte de recibo com formato inválido."
            origin = None
            origin_id = item.get("documento_id", item.get("documento_origem_id"))
            if origin_id:
                origin = DocumentoFiscal.objects.filter(pk=origin_id).first()
            else:
                origin_no = str(item.get("OriginatingON") or "").strip()
                matches = list(DocumentoFiscal.objects.filter(numero_documento=origin_no)[:2]) if origin_no else []
                if len(matches) == 1:
                    origin = matches[0]
                elif len(matches) > 1:
                    return None, None, None, f"Origem {origin_no!r} ambígua."
            if origin is None:
                return None, None, None, "Documento de origem do recibo não localizado."
            onet, otax, _ogross, error = cls._totais_documento_local(origin)
            if error:
                return None, None, None, f"Origem {origin.numero_documento}: {error}"
            sign = Decimal("-1") if origin.tipo_documento == "NC" else Decimal("1")
            net += sign * onet
            tax += sign * otax
        net, tax = net.quantize(CENTAVO), tax.quantize(CENTAVO)
        return net, tax, (net + tax).quantize(CENTAVO), None

    @classmethod
    def _comparar_documento(cls, findings, node, doc, index):
        prefix = f"documents[{index}]"
        cls._compare(findings, "DOC_NO", f"{prefix}.documentNo", doc.numero_documento, node.get("documentNo"))
        cls._compare(findings, "DOC_TYPE", f"{prefix}.documentType", doc.tipo_documento, node.get("documentType"))
        cls._compare(findings, "DOC_DATE", f"{prefix}.documentDate", _iso(doc.data_emissao), node.get("documentDate"))
        cls._compare(findings, "CUSTOMER_NAME", f"{prefix}.companyName", doc.cliente_nome, node.get("companyName"))

        metadata = doc.metadados if isinstance(doc.metadados, dict) else {}
        country = (
            metadata.get("customerCountry")
            or metadata.get("customer_country")
        )
        if not country and doc.tipo_cliente != "nao_residente":
            country = "AO"
        cls._compare(findings, "CUSTOMER_COUNTRY", f"{prefix}.customerCountry", country, node.get("customerCountry"))

        customer_nif = doc.cliente_nif or metadata.get("customerTaxID")
        if not customer_nif and country == "AO":
            customer_nif = "999999999"
        cls._compare(findings, "CUSTOMER_TAX_ID", f"{prefix}.customerTaxID", customer_nif, node.get("customerTaxID"))

        totals = node.get("documentTotals")
        if not isinstance(totals, dict):
            cls._find(findings, "ERRO", "TOTALS_OBJECT", f"{prefix}.documentTotals", "documentTotals tem de ser um objecto.")
            return
        for key in ("netTotal", "taxPayable", "grossTotal"):
            if key not in totals:
                cls._find(findings, "ERRO", "TOTAL_REQUIRED", f"{prefix}.documentTotals.{key}", "Campo obrigatório ausente.")

        if doc.tipo_documento in RECEIPT_TYPES:
            net, tax, gross, error = cls._totais_recibo(doc)
        else:
            net, tax, gross, error = cls._totais_documento_local(doc)

        if error:
            cls._find(findings, "NAO_VERIFICAVEL", "LOCAL_TOTALS", f"{prefix}.documentTotals", error)
        else:
            cls._compare(findings, "NET_TOTAL", f"{prefix}.documentTotals.netTotal", net, totals.get("netTotal"), CENTAVO)
            cls._compare(findings, "TAX_PAYABLE", f"{prefix}.documentTotals.taxPayable", tax, totals.get("taxPayable"), CENTAVO)
            cls._compare(findings, "GROSS_TOTAL", f"{prefix}.documentTotals.grossTotal", gross, totals.get("grossTotal"), CENTAVO)

        local_gross = _dec(doc.valor_total)
        if local_gross is not None:
            cls._compare(
                findings, "LOCAL_GROSS", f"{prefix}.documentTotals.grossTotal",
                local_gross, totals.get("grossTotal"), CENTAVO,
            )

        if doc.tipo_documento in RECEIPT_TYPES:
            receipt = node.get("paymentReceipt")
            if not isinstance(receipt, dict) or not isinstance(receipt.get("sourceDocuments"), list):
                cls._find(findings, "ERRO", "RECEIPT_SOURCE", f"{prefix}.paymentReceipt", "Recibo AR/RG exige paymentReceipt.sourceDocuments.")
        else:
            payload_lines = node.get("lines")
            local_lines = list(doc.linhas.all().order_by("numero_linha", "pk"))
            if not isinstance(payload_lines, list):
                cls._find(findings, "ERRO", "LINES_REQUIRED", f"{prefix}.lines", "Documento exige lista lines.")
            elif len(payload_lines) != len(local_lines):
                cls._find(findings, "ERRO", "LINES_COUNT", f"{prefix}.lines", "Quantidade de linhas diferente do DocumentoFiscal.", len(local_lines), len(payload_lines))
            else:
                for line_idx, (pline, lline) in enumerate(zip(payload_lines, local_lines)):
                    pfx = f"{prefix}.lines[{line_idx}]"
                    cls._compare(findings, "LINE_CODE", f"{pfx}.productCode", lline.codigo_produto, pline.get("productCode"))
                    cls._compare(findings, "LINE_DESC", f"{pfx}.productDescription", lline.descricao, pline.get("productDescription"))
                    cls._compare(findings, "LINE_QTY", f"{pfx}.quantity", lline.quantidade, pline.get("quantity"), CENTAVO)
                    cls._compare(findings, "LINE_UNIT", f"{pfx}.unitOfMeasure", lline.unidade, pline.get("unitOfMeasure"))
                    if doc.tipo_documento == "NC":
                        original = getattr(doc, "documento_original", None)
                        reference = getattr(original, "numero_documento", None) if original else None
                        p_ref = (pline.get("referenceInfo") or {}).get("reference") if isinstance(pline.get("referenceInfo"), dict) else None
                        cls._compare(findings, "NC_REFERENCE", f"{pfx}.referenceInfo.reference", reference, p_ref)

    @classmethod
    @transaction.atomic
    def auditar_payload(cls, payload_or_id):
        cls._tenant()
        payload = (
            payload_or_id if isinstance(payload_or_id, PayloadAGT)
            else PayloadAGT.objects.get(pk=payload_or_id)
        )
        findings = []
        snapshot = payload.payload if isinstance(payload.payload, dict) else {}
        raw = getattr(payload, "payload_json", "") or ""
        if raw:
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if payload.hash_payload and digest != payload.hash_payload:
                cls._find(findings, "ERRO", "HASH_MISMATCH", "payload_json", "O hash SHA-256 não coincide com o conteúdo persistido.")
            try:
                parsed = json.loads(raw)
                if parsed != snapshot:
                    cls._find(findings, "ERRO", "SNAPSHOT_MISMATCH", "payload", "payload_json e o JSONField não representam o mesmo objecto.")
            except Exception:
                cls._find(findings, "ERRO", "JSON_INVALID", "payload_json", "O texto persistido não é JSON válido.")
        elif snapshot:
            cls._find(findings, "AVISO", "RAW_JSON_MISSING", "payload_json", "Registo legado sem texto JSON original; hash de bytes não verificável.")
        else:
            cls._find(findings, "ERRO", "EMPTY_PAYLOAD", "payload", "Não existe envelope JSON capturado.")

        required = (
            "schemaVersion", "submissionUUID", "taxRegistrationNumber",
            "submissionTimeStamp", "softwareInfo", "numberOfEntries",
            "documents", "jwsSignature",
        )
        for name in required:
            if snapshot.get(name) in (None, ""):
                cls._find(findings, "ERRO", "ENVELOPE_REQUIRED", name, f"Campo obrigatório ausente: {name}.")

        documents = snapshot.get("documents")
        if not isinstance(documents, list):
            documents = []
            cls._find(findings, "ERRO", "DOCUMENTS_ARRAY", "documents", "documents tem de ser uma lista.")
        if isinstance(snapshot.get("numberOfEntries"), bool) or snapshot.get("numberOfEntries") != len(documents):
            cls._find(findings, "ERRO", "ENTRY_COUNT", "numberOfEntries", "numberOfEntries não coincide com documents.", len(documents), snapshot.get("numberOfEntries"))
        if len(documents) > 30:
            cls._find(findings, "ERRO", "ENTRY_LIMIT", "documents", "Envelope excede 30 documentos.", 30, len(documents))

        software = snapshot.get("softwareInfo")
        if not isinstance(software, dict):
            software = {}
            cls._find(findings, "ERRO", "SOFTWARE_OBJECT", "softwareInfo", "softwareInfo tem de ser um objecto.")
        detail = software.get("softwareInfoDetail")
        if not isinstance(detail, dict):
            detail = {}
            cls._find(findings, "ERRO", "SOFTWARE_DETAIL", "softwareInfo.softwareInfoDetail", "softwareInfoDetail tem de ser um objecto.")
        for name in ("productId", "productVersion", "softwareValidationNumber", "signatureVersion"):
            if detail.get(name) in (None, ""):
                cls._find(findings, "ERRO", "SOFTWARE_REQUIRED", f"softwareInfo.softwareInfoDetail.{name}", f"Campo obrigatório ausente: {name}.")

        if not str(snapshot.get("jwsSignature") or "").strip():
            cls._find(findings, "ERRO", "REQUEST_SIGNATURE", "jwsSignature", "Assinatura do pedido ausente.")
        if not str(software.get("jwsSoftwareSignature") or "").strip():
            cls._find(findings, "ERRO", "SOFTWARE_SIGNATURE", "softwareInfo.jwsSoftwareSignature", "Assinatura do software ausente.")

        # Presença não significa validade criptográfica. Esta versão não executa
        # verificação RS256 por chave pública/cadeia de certificados.
        cls._find(
            findings, "NAO_VERIFICAVEL", "JWS_CRYPTO",
            "jwsSignature/jwsSoftwareSignature/jwsDocumentSignature",
            "Foi verificada a presença textual das assinaturas; a validade criptográfica JWS não foi verificada.",
        )

        from apps.fiscal.services.agt_payload_builder import AGT_DOCUMENT_TYPES
        associados = list(payload.documentos.all())
        por_par = {}
        for doc in associados:
            por_par.setdefault((doc.tipo_documento, doc.numero_documento), []).append(doc)

        vistos = set()
        for index, node in enumerate(documents):
            if not isinstance(node, dict):
                cls._find(findings, "ERRO", "DOCUMENT_NODE", f"documents[{index}]", "Cada documento tem de ser um objecto.")
                continue
            tipo = str(node.get("documentType") or "").strip()
            numero = str(node.get("documentNo") or "").strip()
            par = (tipo, numero)
            if not tipo or not numero:
                cls._find(findings, "ERRO", "DOCUMENT_ID", f"documents[{index}]", "documentType/documentNo são obrigatórios.")
                continue
            if tipo not in AGT_DOCUMENT_TYPES:
                cls._find(findings, "ERRO", "DOCUMENT_TYPE", f"documents[{index}].documentType", "Tipo não incluído na lista do Builder.", sorted(AGT_DOCUMENT_TYPES), tipo)
            required_doc = (
                "documentStatus", "documentDate", "systemEntryDate",
                "customerCountry", "customerTaxID", "companyName",
                "documentTotals", "jwsDocumentSignature",
            )
            for field in required_doc:
                if node.get(field) in (None, ""):
                    cls._find(findings, "ERRO", "DOCUMENT_REQUIRED", f"documents[{index}].{field}", f"Campo obrigatório ausente: {field}.")
            if node.get("documentStatus") not in {"N", "C"}:
                cls._find(findings, "ERRO", "DOCUMENT_STATUS", f"documents[{index}].documentStatus", "documentStatus tem de ser N ou C.")
            if node.get("documentStatus") == "C" and not node.get("rejectedDocumentNo"):
                cls._find(findings, "ERRO", "REJECTED_DOC_NO", f"documents[{index}].rejectedDocumentNo", "documentStatus=C exige rejectedDocumentNo.")
            if not str(node.get("jwsDocumentSignature") or "").strip():
                cls._find(findings, "ERRO", "DOCUMENT_SIGNATURE", f"documents[{index}].jwsDocumentSignature", "Assinatura documental ausente.")

            matches = por_par.get(par, [])
            if len(matches) == 1:
                vistos.add(par)
                cls._comparar_documento(findings, node, matches[0], index)
            elif len(matches) == 0:
                local = list(DocumentoFiscal.objects.filter(tipo_documento=tipo, numero_documento=numero)[:2])
                if len(local) == 1:
                    cls._find(findings, "AVISO", "M2M_MISSING", f"documents[{index}]", "Documento local encontrado, mas a relação M2M do payload está em falta.")
                    cls._comparar_documento(findings, node, local[0], index)
                else:
                    cls._find(findings, "ERRO", "LOCAL_DOCUMENT_MISSING", f"documents[{index}]", "Não existe correspondência local única para o documento.")
            else:
                cls._find(findings, "ERRO", "LOCAL_DOCUMENT_AMBIGUOUS", f"documents[{index}]", "Mais de um documento local corresponde ao mesmo tipo e número.")

        for par, docs in por_par.items():
            if par not in vistos and not any(
                isinstance(n, dict)
                and (str(n.get("documentType") or "").strip(), str(n.get("documentNo") or "").strip()) == par
                for n in documents
            ):
                cls._find(findings, "ERRO", "EXTRA_M2M_DOCUMENT", "documentos_associados", "A relação M2M contém documento que não está no envelope.", actual=par)

        counts = {
            sev: sum(1 for item in findings if item["severidade"] == sev)
            for sev in ("CONFORME", "AVISO", "ERRO", "NAO_VERIFICAVEL")
        }
        # JWS_CRYPTO é deliberadamente não verificável nesta versão, mas isso
        # não invalida a conformidade estrutural do envelope. Fica destacado
        # separadamente no resumo para não confundir presença com validade.
        nao_verificaveis_funcionais = sum(
            1 for item in findings
            if item["severidade"] == "NAO_VERIFICAVEL"
            and item["codigo"] != "JWS_CRYPTO"
        )
        if counts["ERRO"]:
            estado = "ERRO"
        elif counts["AVISO"] or nao_verificaveis_funcionais:
            estado = "AVISO"
        else:
            estado = "CONFORME"
        counts["validacao_criptografica"] = "NAO_VERIFICAVEL"

        auditoria = AuditoriaPayloadAGT.objects.create(
            payload=payload,
            versao_regras=VERSAO_REGRAS,
            estado=estado,
            resumo=counts,
            resultados=findings,
        )

        from apps.fiscal.payload_listener import PayloadListenerService
        for doc in associados:
            PayloadListenerService.registar_evento(
                doc,
                "AUDITORIA_EXECUTADA",
                f"payload:{payload.pk}:documento:{doc.pk}:auditoria:{auditoria.pk}",
                f"Auditoria do payload concluída: {estado}.",
                payload=payload,
                dados={"auditoria_id": auditoria.pk, "estado": estado, "resumo": counts},
            )

        return auditoria
