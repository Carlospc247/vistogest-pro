"""Consolida as rotas de Vendas e corrige criação/emissão fiscal.

Executar na raiz do projecto: python scripts/patch_vendas_views.py
Cria backup .pre_fiscal_patch.bak antes de gravar.
"""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

TARGET = Path("apps/vendas/views.py")

DUPLICATES_KEEP_FIRST = {
    "finalizar_proforma_api",
    "converter_proforma_api",
    "_converter_para_fatura_recibo",
    "_converter_para_fatura_credito",
    "finalizar_fatura_credito_api",
    "fatura_credito_pdf_view",
    "recibo_pdf_view",
    "proforma_pdf_view",
    "nota_debito_pdf_view",
    "buscar_servicos_api",
}

FINALIZAR_VENDA = '''@login_required
@require_http_methods(["POST"])
@requer_permissao("vender")
def finalizar_venda_api(request):
    """Finaliza a venda usando preços/impostos da BD e stock bloqueado."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data) if data.get("cliente_id") else None
        forma_id = data.get("forma_pagamento_id")
        forma = FormaPagamento.objects.filter(pk=forma_id, ativa=True).first() if forma_id else None
        if forma is None:
            raise ValidationError("Seleccione uma forma de pagamento activa.")

        with transaction.atomic():
            linhas, totais = _montar_linhas(data.get("itens"), verificar_estoque=True)
            for idx, linha in enumerate(linhas, start=1):
                if linha["quantidade"] != linha["quantidade"].to_integral_value():
                    raise ValidationError(f"Item {idx}: a quantidade fraccionada não é suportada numa venda.")
                if linha["taxa"] is None:
                    raise ValidationError(
                        f"Item {idx}: falta configurar a taxa fiscal de IVA de {linha['pct']}%."
                    )

            # Revalidar stock agregado por produto para evitar vender duas vezes
            # a mesma unidade quando o produto aparece em várias linhas.
            por_produto = {}
            for linha in linhas:
                produto = linha["produto"]
                if produto:
                    por_produto[produto.pk] = por_produto.get(produto.pk, Decimal("0")) + linha["quantidade"]
            bloqueados = {
                p.pk: p for p in Produto.objects.select_for_update().filter(pk__in=list(por_produto))
            }
            for pid, qtd in por_produto.items():
                produto = bloqueados.get(pid)
                if produto is None or produto.estoque_atual < qtd:
                    disponivel = getattr(produto, "estoque_atual", 0) if produto else 0
                    nome = getattr(produto, "nome_produto", f"#{pid}") if produto else f"#{pid}"
                    raise ValidationError(
                        f'Estoque insuficiente para "{nome}" (disponível: {disponivel}, solicitado: {qtd}).'
                    )

            tipo_venda = data.get("tipo_venda", "fatura_recibo")
            escolhas = {v for v, _ in Venda._meta.get_field("tipo_venda").choices}
            if escolhas and tipo_venda not in escolhas:
                raise ValidationError("Tipo de venda inválido.")

            venda = Venda.objects.create(
                cliente=cliente,
                vendedor=getattr(request.user, "funcionario", None),
                forma_pagamento=forma,
                subtotal=totais["subtotal"],
                desconto_valor=totais["desconto"],
                iva_valor=totais["iva"],
                total=totais["total"],
                status="finalizada",
                tipo_venda=tipo_venda,
                usuario_criacao=request.user,
                observacoes=(data.get("observacoes") or "").strip(),
            )

            for linha in linhas:
                quantidade = int(linha["quantidade"])
                cents = int((linha["desconto"] * 100).to_integral_value())
                por_unidade, resto = divmod(cents, quantidade)
                grupos = []
                if quantidade - resto:
                    grupos.append((quantidade - resto, Decimal(por_unidade) / Decimal("100")))
                if resto:
                    grupos.append((resto, Decimal(por_unidade + 1) / Decimal("100")))

                for qtd_grupo, desconto_unidade in grupos:
                    ItemVenda.objects.create(
                        venda=venda,
                        produto=linha["produto"],
                        servico=linha["servico"],
                        nome_produto=linha["produto"].nome_produto if linha["produto"] else None,
                        nome_servico=linha["servico"].nome if linha["servico"] else None,
                        quantidade=qtd_grupo,
                        preco_unitario=linha["preco"],
                        desconto_item=desconto_unidade,
                        taxa_iva=linha["taxa"],
                        operation_type=linha["operacao"],
                    )

            _baixar_estoque(linhas)
            venda.calcular_totais()
            venda.gerar_documento_fiscal(request.user)
            venda.refresh_from_db()

        try:
            from apps.vendas.servicos.notificacao_service import NotificacaoVendaService
            NotificacaoVendaService.disparar_todas(
                venda,
                email_avulso=data.get("email_cliente_avulso"),
                whats_avulso=data.get("whatsapp_cliente_avulso"),
            )
        except Exception:
            logger.exception("Venda %s criada fiscalmente, mas a notificação falhou.", venda.pk)

        return JsonResponse({
            "success": True, "venda_id": venda.pk,
            "numero": venda.numero_documento, "total": float(venda.total),
        })
    except Exception as exc:
        return _resposta_erro(exc)
'''

FINALIZAR_PROFORMA = '''@login_required
@require_POST
@requer_permissao("emitir_proforma")
def finalizar_proforma_api(request):
    """Cria pró-forma, grava itens e só depois emite o documento fiscal oficial."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data)
        validade = _parse_data(data.get("data_validade"), "Data de validade")
        if validade < timezone.localdate():
            raise ValidationError("A data de validade não pode estar no passado.")

        with transaction.atomic():
            linhas, totais = _montar_linhas(data.get("itens"))
            proforma = FaturaProforma(
                cliente=cliente,
                vendedor=getattr(request.user, "funcionario", None),
                data_validade=validade,
                subtotal=totais["subtotal"],
                desconto_valor=totais["desconto"],
                iva_valor=totais["iva"],
                total=totais["total"],
                observacoes=(data.get("observacoes") or "").strip(),
                status="emitida",
            )
            # numero_documento fica NULL temporariamente; a migração adicionada
            # com este patch permite persistir o cabeçalho antes dos seus itens.
            proforma.save(criar_documento=False)

            for linha in linhas:
                ItemProforma.objects.create(
                    proforma=proforma,
                    produto=linha["produto"],
                    servico=linha["servico"],
                    quantidade=linha["quantidade"],
                    preco_unitario=linha["preco"],
                    desconto_item=linha["desconto"],
                    iva_percentual=linha["pct"],
                    taxa_iva=linha["taxa"],
                )

            _reconciliar_totais(proforma)
            proforma.gerar_documento_fiscal(request.user)
            proforma.refresh_from_db()

        return JsonResponse({
            "success": True,
            "message": f"Pró-forma {proforma.numero_documento} criada e emitida com sucesso.",
            "proforma_id": proforma.pk,
            "numero_documento": proforma.numero_documento,
            "atcud": proforma.atcud,
            "total": float(proforma.total),
        }, status=201)
    except Exception as exc:
        return _resposta_erro(exc)
'''

FINALIZAR_NOTA_CREDITO = '''@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("aplicar_notacredito")
def finalizar_nota_credito_api(request):
    """Cria NC e emite o documento fiscal após persistir todas as linhas."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        validar_itens_por_regime(data.get("itens", []))

        with transaction.atomic():
            nota = NotaCredito.objects.create(
                cliente_id=data.get("cliente_id"),
                emitida_por=request.user,
                vendedor=getattr(request.user, "funcionario", None),
                motivo=data.get("motivo", "outros"),
                venda_origem_id=data.get("venda_origem_id"),
                fatura_credito_origem_id=data.get("fatura_credito_origem_id"),
                total=_dec(data.get("total", 0), "total", Decimal("0")),
                status="emitida",
            )
            itens = data.get("itens") or []
            if not itens:
                raise ValidationError("A nota de crédito deve conter pelo menos um item.")
            for item in itens:
                ItemNotaCredito.objects.create(
                    nota_credito=nota,
                    produto_id=item.get("produto_id"),
                    servico_id=item.get("servico_id"),
                    descricao_item=item.get("descricao") or "Item de crédito",
                    quantidade_creditada=_dec(item.get("quantidade"), "quantidade", Decimal("0.001")),
                    valor_unitario_credito=_dec(item.get("preco_unitario"), "preço unitário", Decimal("0")),
                    iva_percentual=_dec(item.get("iva_percentual", 0), "IVA", Decimal("0")),
                    taxa_iva_id=item.get("taxa_iva_id") or None,
                )
            nota.recalcular_total()
            nota.gerar_documento_fiscal(request.user)
            nota.refresh_from_db()

        return JsonResponse({
            "success": True, "nota_id": nota.pk,
            "numero_nota": nota.numero_nota, "atcud": nota.atcud,
            "total": float(nota.total),
        }, status=201)
    except Exception as exc:
        return _resposta_erro(exc)
'''

FINALIZAR_NOTA_DEBITO = '''@login_required
@require_POST
@requer_permissao("aplicar_notadebito")
def finalizar_nota_debito_api(request, nota_id):
    """Emite fiscalmente uma Nota de Débito existente após validar os seus itens."""
    try:
        with transaction.atomic():
            nota = get_object_or_404(NotaDebito.objects.select_for_update(), pk=nota_id)
            nota.gerar_documento_fiscal(request.user)
            nota.refresh_from_db()
        return JsonResponse({"success": True, "numero": nota.numero_nota, "atcud": nota.atcud})
    except Http404:
        return JsonResponse({"success": False, "message": "Nota de débito não encontrada."}, status=404)
    except Exception as exc:
        return _resposta_erro(exc)
'''

FINALIZAR_TRANSPORTE = '''@transaction.atomic
@login_required
@require_http_methods(["POST"])
@requer_permissao("emitir_documentotransporte")
def finalizar_documento_transporte_api(request):
    """Cria GT, grava os itens e depois associa o registo fiscal DT."""
    try:
        data = _ler_json(request)
        tenant = getattr(request, "tenant", None) or getattr(connection, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            raise ValidationError("Não foi possível determinar o tenant da empresa.")
        if getattr(tenant, "regime", None) == "SERVICOS":
            raise ValidationError("Empresas em regime de serviços não emitem Guias de Transporte de mercadorias.")

        with transaction.atomic():
            itens = data.get("itens") or []
            if not itens:
                raise ValidationError("O documento de transporte deve conter pelo menos um item.")
            gt = DocumentoTransporte.objects.create(
                emitido_por=request.user,
                destinatario_nome=data["destinatario_nome"],
                destinatario_endereco=data["destinatario_endereco"],
                data_inicio_transporte=_parse_data(data["data_inicio"], "Data de início"),
                data_previsao_entrega=data.get("data_previsao_entrega") or timezone.now(),
                veiculo_matricula=data["veiculo_matricula"],
                status="preparando",
            )
            for item in itens:
                ItemDocumentoTransporte.objects.create(
                    documento=gt,
                    produto_id=item["produto_id"],
                    quantidade_enviada=_dec(item["quantidade"], "quantidade", Decimal("0.001")),
                )
            gt.gerar_documento_fiscal(request.user)
            gt.refresh_from_db()

        return JsonResponse({"success": True, "documento_id": gt.pk, "numero_documento": gt.numero_documento}, status=201)
    except Exception as exc:
        return _resposta_erro(exc)
'''

FINALIZAR_RECIBO = '''@login_required
@require_POST
@requer_permissao("liquidar_faturacredito")
def finalizar_recibo_api(request):
    """Regista um pagamento parcial/total, gera REC fiscal e actualiza a dívida atomicamente."""
    try:
        data = _ler_json(request)
        with transaction.atomic():
            fatura = get_object_or_404(FaturaCredito.objects.select_for_update(), pk=data.get("fatura_id"))
            if fatura.status in {"liquidada", "cancelada"}:
                raise ValidationError("Esta factura não aceita novos pagamentos.")
            valor = _dec(data.get("valor_pago"), "valor pago", Decimal("0.01"))
            pendente = fatura.valor_pendente()
            if valor > pendente:
                raise ValidationError(f"O pagamento excede o saldo pendente ({pendente}).")

            forma = None
            if data.get("forma_pagamento_id"):
                forma = FormaPagamento.objects.filter(pk=data["forma_pagamento_id"], ativa=True).first()
                if forma is None:
                    raise ValidationError("Forma de pagamento inválida ou inactiva.")

            recibo = Recibo.objects.create(
                fatura=fatura,
                cliente=fatura.cliente,
                vendedor=getattr(request.user, "funcionario", None),
                forma_pagamento=forma,
                valor_pago=valor,
                status="emitido",
            )
            recibo.gerar_documento_fiscal(request.user)
            fatura.valor_pago = fatura.valor_pago + valor
            fatura.status = "liquidada" if fatura.valor_pago >= fatura.total else "parcial"
            fatura.save(update_fields=["valor_pago", "status", "updated_at"])

        return JsonResponse({
            "success": True, "recibo_id": recibo.pk,
            "numero_recibo": recibo.numero_recibo, "atcud": recibo.atcud,
            "valor_pago": float(valor), "saldo_pendente": float(fatura.valor_pendente()),
        }, status=201)
    except Http404:
        return JsonResponse({"success": False, "message": "Factura não encontrada."}, status=404)
    except Exception as exc:
        return _resposta_erro(exc)
'''


ERROR_RESPONSE = '''def _resposta_erro(exc):
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"success": False, "message": str(exc)}, status=403)
    if isinstance(exc, (ValidationError, FiscalServiceError)):
        mensagem = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        return JsonResponse({"success": False, "message": mensagem}, status=400)
    logger.exception("Erro inesperado ao processar documento comercial")
    return JsonResponse({"success": False, "message": "Erro interno ao processar o documento."}, status=500)
'''

PDF_RESPONSE = '''def _gerar_response_pdf(obj_documento, prefixo):
    """Gera PDF sem presumir que todos os documentos usam o mesmo campo de número."""
    try:
        pdf_service = PDFDocumentoService(obj_documento)
        pdf_buffer = pdf_service.gerar()
        numero = (
            getattr(obj_documento, "numero_documento", None)
            or getattr(obj_documento, "numero_nota", None)
            or getattr(obj_documento, "numero_recibo", None)
            or f"ID_{obj_documento.pk}"
        )
        safe_number = str(numero).replace("/", "_").replace("\\\\", "_").replace(" ", "_")
        return FileResponse(
            pdf_buffer, as_attachment=False, content_type="application/pdf",
            filename=f"{prefixo}_{safe_number}.pdf",
        )
    except Exception as exc:
        logger.exception("Falha ao gerar PDF %s do objecto %s: %s", prefixo, getattr(obj_documento, "pk", "?"), exc)
        raise Http404("Não foi possível gerar o PDF deste documento.") from exc
'''


def parse(source: str):
    return ast.parse(source)


def node_start(node: ast.AST) -> int:
    decorators = [d.lineno for d in getattr(node, "decorator_list", [])]
    return min([node.lineno, *decorators])


def remove_duplicate_defs(source: str) -> str:
    tree = parse(source)
    lines = source.splitlines(keepends=True)
    seen = set()
    removals = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in DUPLICATES_KEEP_FIRST:
            continue
        if node.name not in seen:
            seen.add(node.name)
            continue
        removals.append((node_start(node), node.end_lineno))
    for start, end in sorted(removals, reverse=True):
        del lines[start - 1:end]
    return "".join(lines)


def replace_function(source: str, name: str, replacement: str) -> str:
    tree = parse(source)
    matches = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Esperava uma definição única de {name}; encontrei {len(matches)}.")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start, end = node_start(node), node.end_lineno
    new_lines = replacement.strip("\n").splitlines(keepends=True)
    new_lines = [line if line.endswith("\n") else line + "\n" for line in new_lines]
    lines[start - 1:end] = new_lines
    patched = "".join(lines)
    parse(patched)
    return patched


def patch_pdf_decorators(source: str) -> str:
    tree = parse(source)
    lines = source.splitlines(keepends=True)
    edits = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in {"fatura_pdf_view", "nota_debito_pdf_view"}:
            continue
        start, end = node_start(node), node.end_lineno
        block = "".join(lines[start - 1:end])
        if node.name == "fatura_pdf_view" and not any(
            isinstance(d, ast.Name) and d.id == "login_required" for d in node.decorator_list
        ):
            block = "@login_required\n" + block
        if node.name == "nota_debito_pdf_view":
            block = block.replace('requer_permissao("aplicar_notacredito")', 'requer_permissao("aplicar_notadebito")')
            block = block.replace("requer_permissao('aplicar_notacredito')", "requer_permissao('aplicar_notadebito')")
        edits.append((start, end, block))
    for start, end, block in sorted(edits, reverse=True):
        new_lines = block.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        lines[start - 1:end] = new_lines
    result = "".join(lines)
    parse(result)
    return result


def main():
    if not TARGET.exists():
        raise SystemExit(f"Ficheiro não encontrado: {TARGET.resolve()}. Execute na raiz do projecto.")
    original = TARGET.read_text(encoding="utf-8")
    parse(original)
    backup = TARGET.with_suffix(TARGET.suffix + ".pre_fiscal_patch.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    patched = remove_duplicate_defs(original)
    if "from apps.fiscal.services.utils import FiscalServiceError" not in patched:
        anchor = "from apps.fiscal.services.pdf_agt_service import PDFDocumentoService"
        if anchor in patched:
            patched = patched.replace(anchor, anchor + "\nfrom apps.fiscal.services.utils import FiscalServiceError", 1)
    patched = replace_function(patched, "_resposta_erro", ERROR_RESPONSE)
    patched = replace_function(patched, "finalizar_venda_api", FINALIZAR_VENDA)
    patched = replace_function(patched, "finalizar_proforma_api", FINALIZAR_PROFORMA)
    patched = replace_function(patched, "finalizar_nota_credito_api", FINALIZAR_NOTA_CREDITO)
    patched = replace_function(patched, "finalizar_nota_debito_api", FINALIZAR_NOTA_DEBITO)
    patched = replace_function(patched, "finalizar_documento_transporte_api", FINALIZAR_TRANSPORTE)
    patched = replace_function(patched, "finalizar_recibo_api", FINALIZAR_RECIBO)
    patched = replace_function(patched, "_gerar_response_pdf", PDF_RESPONSE)
    patched = patch_pdf_decorators(patched)
    parse(patched)
    TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: {TARGET} actualizado. Backup: {backup}")
    print("Definições duplicadas consolidadas; emissão fiscal ocorre depois de gravar os itens.")


if __name__ == "__main__":
    main()
