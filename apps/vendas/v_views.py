# =====================================================================
# apps/vendas/views.py  —  PATCH: Proforma (FP) e Fatura a Crédito (FT)
# =====================================================================
# Como aplicar:
#   1) Acrescentar os imports da secção 0.
#   2) SUBSTITUIR no views.py as funções/blocos com o mesmo nome:
#        nova_fatura_credito, nova_proforma,
#        finalizar_proforma_api, finalizar_fatura_credito_api (agora SEM fatura_id),
#        converter_proforma_api, _converter_para_fatura_recibo,
#        _converter_para_fatura_credito, atualizar_status_proforma_api,
#        proforma_pdf_view, fatura_credito_pdf_view, recibo_pdf_view,
#        nota_debito_pdf_view, buscar_produtos_api, buscar_servicos_api
#   3) A antiga finalizar_fatura_credito_api(request, fatura_id) passa a chamar-se
#      gerar_documento_fatura_credito_api (secção 6) — ver URLs no fim do ficheiro.
#   4) Acrescentar os helpers (secção 1) antes das views.
# =====================================================================


# ---------------------------------------------------------------------
# 0) IMPORTS A ACRESCENTAR / AJUSTAR
# ---------------------------------------------------------------------
from decimal import Decimal, InvalidOperation          # (já tinhas Decimal)
from django.core.serializers.json import DjangoJSONEncoder


# ---------------------------------------------------------------------
# 1) HELPERS COMUNS (FP / FT)
# ---------------------------------------------------------------------
IVA_PADRAO = Decimal('14.00')
CENTIMO = Decimal('0.01')


def _q(valor):
    """Arredonda a 2 casas, igual ao que o DecimalField(…, decimal_places=2) grava."""
    return Decimal(valor).quantize(CENTIMO)


def _msg_erro(exc):
    if isinstance(exc, ValidationError):
        return ' '.join(exc.messages)
    return str(exc)


def _ler_json(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        raise ValidationError('Corpo da requisição inválido (JSON esperado).')
    if not isinstance(data, dict):
        raise ValidationError('Corpo da requisição inválido.')
    return data


def _dec(valor, campo, minimo=None):
    try:
        d = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(f'Valor inválido em {campo}.')
    if not d.is_finite():
        raise ValidationError(f'Valor inválido em {campo}.')
    if minimo is not None and d < minimo:
        raise ValidationError(f'Valor inválido em {campo}.')
    return d


def _parse_data(valor, campo):
    try:
        return datetime.strptime(str(valor), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValidationError(f'{campo} inválida (formato esperado: AAAA-MM-DD).')


def _regime_do_tenant(request):
    """Mesma regra do PDVView: o regime vem do tenant activo."""
    tenant = getattr(request, 'tenant', None) or getattr(connection, 'tenant', None)
    if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
        raise PermissionDenied('Este documento só está disponível no domínio de uma empresa.')
    regime = getattr(tenant, 'regime', None)
    if regime not in {'COMERCIO', 'SERVICOS', 'MISTO'}:
        raise PermissionDenied('O tipo de actividade da empresa não está configurado correctamente.')
    return regime


def _obter_cliente(data):
    cliente_id = data.get('cliente_id')
    if not cliente_id:
        raise ValidationError('Cliente é obrigatório.')
    try:
        cliente = Cliente.objects.filter(pk=cliente_id, ativo=True).first()
    except (ValueError, TypeError):
        cliente = None
    if not cliente:
        raise ValidationError('Cliente não encontrado ou inactivo.')
    return cliente


def _percentual_iva(obj):
    """% de IVA configurada no produto/serviço (taxa_iva > iva_percentual > 14%)."""
    taxa = getattr(obj, 'taxa_iva', None)
    if taxa is not None:
        return Decimal(str(taxa.tax_percentage))
    pct = getattr(obj, 'iva_percentual', None)
    return IVA_PADRAO if pct is None else Decimal(str(pct))


def _resolver_iva(obj):
    """Devolve (TaxaIVAAGT|None, percentual). O servidor é a fonte de verdade do IVA."""
    taxa = getattr(obj, 'taxa_iva', None)
    if taxa is not None:
        return taxa, Decimal(str(taxa.tax_percentage))
    pct = _percentual_iva(obj)
    return TaxaIVAAGT.objects.filter(tax_percentage=pct).first(), pct


def _json_seguro(obj):
    """JSON para injectar em <script> com |safe (escapa <, >, & e separadores unicode)."""
    texto = json.dumps(obj, cls=DjangoJSONEncoder, ensure_ascii=False)
    return (texto.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
                 .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def _nome_categoria(obj):
    cat = getattr(obj, 'categoria', None)
    if cat is None:
        return ''
    return getattr(cat, 'nome', None) or str(cat)


def _serializar_produto(p):
    foto_url = None
    foto = getattr(p, 'foto', None)
    if foto:
        try:
            foto_url = foto.url
        except ValueError:
            foto_url = None
    return {
        'id': p.id,
        'nome_produto': p.nome_produto,
        'codigo_interno': getattr(p, 'codigo_interno', '') or '',
        'preco_venda': float(p.preco_venda or 0),
        'estoque_atual': float(p.estoque_atual or 0),
        'foto_url': foto_url,
        'categoria': _nome_categoria(p),
        'categoria_id': getattr(p, 'categoria_id', None),
        'iva_percentual': float(_percentual_iva(p)),
    }


def _serializar_servico(s):
    return {
        'id': s.id,
        'nome': s.nome,
        'preco': float(s.preco_padrao or 0),            # o template lê servico.preco
        'categoria': _nome_categoria(s),
        'categoria_id': getattr(s, 'categoria_id', None),
        'descricao': getattr(s, 'descricao', '') or '',
        'iva_percentual': float(_percentual_iva(s)),
    }


def _render_documento_comercial(request, template, titulo, tipo_documento):
    """Contexto idêntico ao do PDV: regime + produtos/servicos já filtrados pelo regime."""
    try:
        regime = _regime_do_tenant(request)
    except PermissionDenied as e:
        messages.error(request, str(e))
        return redirect('core_tenants:dashboard')

    produtos, servicos = [], []
    if regime in {'COMERCIO', 'MISTO'}:
        produtos = [_serializar_produto(p)
                    for p in Produto.objects.filter(ativo=True).order_by('nome_produto')]
    if regime in {'SERVICOS', 'MISTO'}:
        servicos = [_serializar_servico(s)
                    for s in Servico.objects.filter(ativo=True).order_by('nome')]

    return render(request, template, {
        'title': titulo,
        'tipo_documento': tipo_documento,
        'regime': regime,
        'produtos': _json_seguro(produtos),   # string JSON -> {{ produtos|safe }}
        'servicos': _json_seguro(servicos),
    })


def _montar_linhas(itens, verificar_estoque=False):
    """
    Valida e calcula as linhas SEM confiar nos valores do cliente:
    preço, nome, tipo de operação e IVA vêm da BD; do cliente só vêm
    produto_id/servico_id, quantidade e desconto_item (valor absoluto da linha).
    Deve ser chamada dentro de transaction.atomic() (usa select_for_update no estoque).
    """
    if not itens or not isinstance(itens, list):
        raise ValidationError('O documento deve conter pelo menos um item.')

    validar_itens_por_regime(itens)

    linhas = []
    for idx, it in enumerate(itens, start=1):
        produto_id, servico_id = it.get('produto_id'), it.get('servico_id')
        if bool(produto_id) == bool(servico_id):
            raise ValidationError(f'Item {idx}: indique um produto OU um serviço.')

        qtd = _dec(it.get('quantidade'), f'quantidade do item {idx}')
        if qtd <= 0 or qtd != qtd.quantize(CENTIMO):
            raise ValidationError(f'Item {idx}: quantidade inválida.')

        produto = servico = None
        if produto_id:
            qs = Produto.objects.filter(pk=produto_id, ativo=True)
            if verificar_estoque:
                qs = qs.select_for_update()
            produto = qs.first()
            if not produto:
                raise ValidationError(f'Item {idx}: produto não encontrado ou inactivo.')
            if verificar_estoque and produto.estoque_atual < qtd:
                raise ValidationError(
                    f'Estoque insuficiente para "{produto.nome_produto}" '
                    f'(disponível: {produto.estoque_atual}).')
            origem, nome, preco, operacao = produto, produto.nome_produto, produto.preco_venda, 'TB'
        else:
            servico = Servico.objects.filter(pk=servico_id, ativo=True).first()
            if not servico:
                raise ValidationError(f'Item {idx}: serviço não encontrado ou inactivo.')
            origem, nome, preco, operacao = servico, servico.nome, servico.preco_padrao, 'SE'

        preco = _q(Decimal(str(preco)))
        taxa, pct = _resolver_iva(origem)

        bruto = preco * qtd
        desconto = _q(_dec(it.get('desconto_item', 0), f'desconto do item {idx}', Decimal('0')))
        if desconto > _q(bruto):
            raise ValidationError(f'Item {idx}: o desconto excede o valor da linha.')

        base = bruto - desconto
        iva_exato = base * pct / Decimal('100')

        linhas.append({
            'produto': produto, 'servico': servico, 'nome': nome,
            'quantidade': qtd, 'preco': preco, 'desconto': desconto,
            'pct': pct, 'taxa': taxa, 'operacao': operacao,
            'subtotal': _q(bruto), 'iva': _q(iva_exato), 'total': _q(base + iva_exato),
        })

    subtotal = sum((l['subtotal'] for l in linhas), Decimal('0.00'))
    desconto = sum((l['desconto'] for l in linhas), Decimal('0.00'))
    iva = sum((l['iva'] for l in linhas), Decimal('0.00'))
    totais = {'subtotal': subtotal, 'desconto': desconto, 'iva': iva,
              'total': subtotal - desconto + iva}
    if totais['total'] <= 0:
        raise ValidationError('O total do documento deve ser superior a zero.')
    return linhas, totais


def _reconciliar_totais(doc):
    """Recalcula o cabeçalho a partir dos itens PERSISTIDOS (garante coerência com os arredondamentos)."""
    ag = doc.itens.aggregate(sub=Sum('subtotal'), desc=Sum('desconto_item'), iva=Sum('iva_valor'))
    sub = ag['sub'] or Decimal('0.00')
    desc = ag['desc'] or Decimal('0.00')
    iva = ag['iva'] or Decimal('0.00')
    doc.subtotal, doc.desconto_valor, doc.iva_valor = sub, desc, iva
    doc.total = sub - desc + iva
    doc.save(update_fields=['subtotal', 'desconto_valor', 'iva_valor', 'total'])


def _baixar_estoque(linhas):
    for l in linhas:
        if l['produto']:
            qtd = l['quantidade']
            qtd = int(qtd) if qtd == qtd.to_integral_value() else qtd
            Produto.objects.filter(pk=l['produto'].pk).update(estoque_atual=F('estoque_atual') - qtd)


def _resposta_erro(exc):
    if isinstance(exc, PermissionDenied):
        return JsonResponse({'success': False, 'message': str(exc)}, status=403)
    if isinstance(exc, ValidationError):
        return JsonResponse({'success': False, 'message': _msg_erro(exc)}, status=400)
    logger.exception('Erro inesperado ao processar documento comercial')
    return JsonResponse({'success': False, 'message': 'Erro interno ao processar o documento.'}, status=500)


# ---------------------------------------------------------------------
# 2) PÁGINAS (render dos templates)  — faltava regime/produtos/servicos
# ---------------------------------------------------------------------
@login_required
@require_GET
@requer_permissao("emitir_faturacredito")
def nova_fatura_credito(request):
    return _render_documento_comercial(
        request, 'vendas/nova_fatura_credito.html', 'Nova Fatura a Crédito (FT)', 'FT')


@login_required
@require_GET
@requer_permissao("emitir_proforma")
def nova_proforma(request):
    return _render_documento_comercial(
        request, 'vendas/nova_proforma.html', 'Nova Proforma (Orçamento)', 'FP')


# ---------------------------------------------------------------------
# 3) CRIAR PROFORMA  (url name: api_finalizar_proforma)
# ---------------------------------------------------------------------
@login_required
@require_POST
@requer_permissao("emitir_proforma")
def finalizar_proforma_api(request):
    """Cria a Proforma (FP) com itens, IVA, desconto e observações. Totais calculados no servidor."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data)

        validade = _parse_data(data.get('data_validade'), 'Data de validade')
        if validade < timezone.localdate():
            raise ValidationError('A data de validade não pode estar no passado.')

        # `with atomic` DENTRO do try: se algo falhar, tudo é revertido.
        with transaction.atomic():
            linhas, t = _montar_linhas(data.get('itens'))

            proforma = FaturaProforma(
                cliente=cliente,
                vendedor=getattr(request.user, 'funcionario', None),
                data_validade=validade,
                subtotal=t['subtotal'], desconto_valor=t['desconto'],
                iva_valor=t['iva'], total=t['total'],
                observacoes=(data.get('observacoes') or '').strip() or None,
                status='emitida',
            )
            # O save() da proforma cria o DocumentoFiscal -> precisa de usuario_criacao
            # (objects.create() não aceita este kwarg, por isso instancia + save).
            proforma.save(usuario_criacao=request.user)

            for l in linhas:
                ItemProforma.objects.create(
                    proforma=proforma, produto=l['produto'], servico=l['servico'],
                    quantidade=l['quantidade'], preco_unitario=l['preco'],
                    desconto_item=l['desconto'], iva_percentual=l['pct'], taxa_iva=l['taxa'],
                )
            _reconciliar_totais(proforma)

        return JsonResponse({
            'success': True,
            'message': f'Proforma {proforma.numero_documento} criada com sucesso!',
            'proforma_id': proforma.id,
            'numero_documento': proforma.numero_documento,
            'total': float(proforma.total),
        })
    except Exception as e:
        return _resposta_erro(e)


# ---------------------------------------------------------------------
# 4) CRIAR FATURA A CRÉDITO  (url name: api_finalizar_fatura_credito — SEM pk)
# ---------------------------------------------------------------------
@login_required
@require_POST
@requer_permissao("emitir_faturacredito")
def finalizar_fatura_credito_api(request):
    """Cria a FT: itens, baixa de estoque, totais, documento fiscal (hash/ATCUD) e dívida (valor_pago=0)."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data)

        vencimento = _parse_data(data.get('data_vencimento'), 'Data de vencimento')
        if vencimento < timezone.localdate():
            raise ValidationError('A data de vencimento não pode estar no passado.')

        with transaction.atomic():
            linhas, t = _montar_linhas(data.get('itens'), verificar_estoque=True)

            fatura = FaturaCredito.objects.create(
                cliente=cliente,
                vendedor=getattr(request.user, 'funcionario', None),
                data_vencimento=vencimento,
                subtotal=t['subtotal'], desconto_valor=t['desconto'],
                iva_valor=t['iva'], total=t['total'],
                valor_pago=Decimal('0.00'),
                observacoes=(data.get('observacoes') or '').strip() or None,
                status='emitida',
            )

            for l in linhas:
                ItemFatura.objects.create(
                    fatura=fatura, produto=l['produto'], servico=l['servico'],
                    nome_item=l['nome'], quantidade=l['quantidade'],
                    preco_unitario=l['preco'], desconto_item=l['desconto'],
                    iva_percentual=l['pct'], taxa_iva=l['taxa'],
                    operation_type=l['operacao'],
                )

            _reconciliar_totais(fatura)
            _baixar_estoque(linhas)
            fatura.gerar_documento_fiscal(request.user)   # hash + ATCUD (FT)

        return JsonResponse({
            'success': True,
            'message': f'Fatura {fatura.numero_documento} criada com sucesso!',
            'fatura_id': fatura.id,
            'numero_documento': fatura.numero_documento,
            'total': float(fatura.total),
        })
    except Exception as e:
        return _resposta_erro(e)


# ---------------------------------------------------------------------
# 5) CONVERSÃO PROFORMA -> FR / FT  (corrigida)
# ---------------------------------------------------------------------
def _taxa_do_item_proforma(item):
    if item.taxa_iva_id:
        return item.taxa_iva
    return TaxaIVAAGT.objects.filter(tax_percentage=item.iva_percentual).first()


@login_required
@require_POST
@requer_permissao("liquidar_faturacredito")
def converter_proforma_api(request, proforma_id):
    """Converte Proforma (FP) em FR ou FT."""
    try:
        data = _ler_json(request)
        tipo = data.get('tipo_conversao')
        if tipo not in ('fatura_recibo', 'fatura_credito'):
            raise ValidationError('Tipo de conversão inválido.')

        with transaction.atomic():
            proforma = get_object_or_404(FaturaProforma.objects.select_for_update(), id=proforma_id)

            if proforma.status not in ('emitida', 'aceite'):
                raise ValidationError('Apenas proformas emitidas ou aceites podem ser convertidas.')
            if proforma.data_validade < timezone.localdate():
                raise ValidationError('A Proforma expirou e não pode ser convertida.')

            if tipo == 'fatura_recibo':
                forma = None
                if data.get('forma_pagamento_id'):
                    forma = FormaPagamento.objects.filter(pk=data['forma_pagamento_id'], ativa=True).first()
                forma = forma or proforma.forma_pagamento or FormaPagamento.objects.filter(ativa=True).first()
                if not forma:
                    raise ValidationError('Indique uma forma de pagamento para emitir a Fatura-Recibo.')
                documento = _converter_para_fatura_recibo(proforma, request.user, forma)
                proforma.venda_convertida = documento
                nome_tipo = 'Fatura Recibo (FR)'
            else:
                documento = _converter_para_fatura_credito(proforma, request.user)
                nome_tipo = 'Fatura a Crédito (FT)'

            proforma.status = 'convertida'
            proforma.save(criar_documento=False)

        return JsonResponse({
            'success': True,
            'message': f'Proforma convertida em {nome_tipo}: {documento.numero_documento}',
            'documento_id': documento.id,
            'numero_documento': documento.numero_documento,
            'tipo': tipo,
        })
    except Http404:
        return JsonResponse({'success': False, 'message': 'Proforma não encontrada.'}, status=404)
    except Exception as e:
        return _resposta_erro(e)


def _converter_para_fatura_recibo(proforma, user, forma_pagamento):
    """Proforma -> Venda (FR). forma_pagamento é obrigatória no model Venda (PROTECT)."""
    venda = Venda.objects.create(
        cliente=proforma.cliente,
        vendedor=getattr(user, 'funcionario', None),
        forma_pagamento=forma_pagamento,
        subtotal=proforma.subtotal, desconto_valor=proforma.desconto_valor,
        iva_valor=proforma.iva_valor, total=proforma.total,
        valor_pago=proforma.total,
        status='finalizada', tipo_venda='fatura_recibo',
        usuario_criacao=user,
        observacoes=f'Convertido da Proforma {proforma.numero_documento}',
    )

    for item in proforma.itens.select_related('produto', 'servico'):
        qtd = item.quantidade
        if qtd != qtd.to_integral_value():
            raise ValidationError('Quantidades fraccionadas não são suportadas em Fatura-Recibo (ItemVenda é inteiro).')
        qtd = int(qtd)

        if item.produto:
            p = Produto.objects.select_for_update().get(pk=item.produto_id)
            if p.estoque_atual < qtd:
                raise ValidationError(f'Estoque insuficiente para "{p.nome_produto}".')
            Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - qtd)

        ItemVenda.objects.create(
            venda=venda, produto=item.produto, servico=item.servico,
            nome_produto=item.produto.nome_produto if item.produto else None,
            nome_servico=item.servico.nome if item.servico else None,
            quantidade=qtd, preco_unitario=item.preco_unitario,
            # ItemVenda.desconto_item é POR UNIDADE; na proforma é o valor da linha.
            desconto_item=(item.desconto_item / qtd).quantize(CENTIMO),
            taxa_iva=_taxa_do_item_proforma(item),
            operation_type='TB' if item.produto else 'SE',
        )

    venda.calcular_totais()
    venda.valor_pago = venda.total
    venda.save(update_fields=['subtotal', 'iva_valor', 'total', 'valor_pago'])
    venda.gerar_documento_fiscal(user)
    return venda


def _converter_para_fatura_credito(proforma, user):
    """Proforma -> Fatura de Crédito (FT). Agora passa iva_percentual (antes o IVA ficava a 0)."""
    fatura = FaturaCredito.objects.create(
        cliente=proforma.cliente,
        vendedor=getattr(user, 'funcionario', None),
        subtotal=proforma.subtotal, desconto_valor=proforma.desconto_valor,
        iva_valor=proforma.iva_valor, total=proforma.total,
        status='emitida',
        data_vencimento=timezone.localdate() + timedelta(days=30),
        observacoes=f'Convertido da Proforma {proforma.numero_documento}',
    )

    for item in proforma.itens.select_related('produto', 'servico'):
        if item.produto:
            p = Produto.objects.select_for_update().get(pk=item.produto_id)
            if p.estoque_atual < item.quantidade:
                raise ValidationError(f'Estoque insuficiente para "{p.nome_produto}".')
            qtd = item.quantidade
            qtd = int(qtd) if qtd == qtd.to_integral_value() else qtd
            Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - qtd)

        ItemFatura.objects.create(
            fatura=fatura, produto=item.produto, servico=item.servico,
            nome_item=item.produto.nome_produto if item.produto else item.servico.nome,
            quantidade=item.quantidade, preco_unitario=item.preco_unitario,
            desconto_item=item.desconto_item,
            iva_percentual=item.iva_percentual,
            taxa_iva=_taxa_do_item_proforma(item),
            operation_type='TB' if item.produto else 'SE',
        )

    _reconciliar_totais(fatura)
    fatura.gerar_documento_fiscal(user)
    return fatura


# ---------------------------------------------------------------------
# 6) FT já existente sem documento fiscal (antiga finalizar_fatura_credito_api(fatura_id))
# ---------------------------------------------------------------------
@login_required
@require_POST
@requer_permissao("emitir_faturacredito")
def gerar_documento_fatura_credito_api(request, fatura_id):
    try:
        with transaction.atomic():
            fatura = get_object_or_404(FaturaCredito.objects.select_for_update(), id=fatura_id)
            if fatura.status != 'emitida':
                raise ValidationError('Fatura já processada.')
            if fatura.documento_fiscal_id:
                raise ValidationError('Esta fatura já tem documento fiscal.')
            fatura.gerar_documento_fiscal(request.user)
        return JsonResponse({'success': True, 'numero': fatura.numero_documento})
    except Http404:
        return JsonResponse({'success': False, 'message': 'Fatura não encontrada.'}, status=404)
    except Exception as e:
        return _resposta_erro(e)


# ---------------------------------------------------------------------
# 7) STATUS DA PROFORMA (corrigido: 'expirada'/'cancelada' conforme o model)
# ---------------------------------------------------------------------
@login_required
@require_POST
@requer_permissao("aprovar_proforma")
def atualizar_status_proforma_api(request, proforma_id):
    try:
        data = _ler_json(request)
        novo = data.get('status')
        validos = {'emitida', 'aceite', 'rejeitada', 'expirada', 'cancelada'}   # 'convertida' só via conversão
        if novo not in validos:
            raise ValidationError('Status inválido.')

        with transaction.atomic():
            proforma = get_object_or_404(FaturaProforma.objects.select_for_update(), id=proforma_id)
            if proforma.status == 'convertida':
                raise ValidationError('Proformas convertidas não podem mudar de estado.')
            anterior = proforma.status
            proforma.status = novo
            proforma.save(criar_documento=False)

        nomes = dict(FaturaProforma.STATUS_CHOICES)
        return JsonResponse({
            'success': True,
            'message': f'Status alterado de {nomes.get(anterior, anterior)} para {nomes.get(novo, novo)}',
            'status_anterior': anterior, 'status_novo': novo,
        })
    except Http404:
        return JsonResponse({'success': False, 'message': 'Proforma não encontrada.'}, status=404)
    except Exception as e:
        return _resposta_erro(e)


# ---------------------------------------------------------------------
# 8) PDFs — faltava @login_required; nota_debito_pdf_view estava como POST
# ---------------------------------------------------------------------
@login_required
@require_GET
@requer_permissao("emitir_proforma")
def proforma_pdf_view(request, proforma_id):
    proforma = get_object_or_404(FaturaProforma, id=proforma_id)
    return _gerar_response_pdf(proforma, "FP")


@login_required
@require_GET
@requer_permissao("emitir_faturacredito")
def fatura_credito_pdf_view(request, fatura_id, tipo='a4'):
    fatura = get_object_or_404(FaturaCredito, id=fatura_id)
    return _gerar_response_pdf(fatura, "FT")


@login_required
@require_GET
@requer_permissao("emitir_recibos")
def recibo_pdf_view(request, recibo_id):
    recibo = get_object_or_404(Recibo, id=recibo_id)
    return _gerar_response_pdf(recibo, "REC")


@login_required
@require_GET                       # era require_http_methods(["POST"]) -> o PDF nunca abria num <a>/window.open
@requer_permissao("aplicar_notacredito")
def nota_debito_pdf_view(request, nota_id):
    nota = get_object_or_404(NotaDebito, id=nota_id)
    return _gerar_response_pdf(nota, "ND")


# ---------------------------------------------------------------------
# 9) APIs de busca do módulo vendas — usavam campos inexistentes (p.nome, p.codigo, s.preco)
# ---------------------------------------------------------------------
@login_required
def buscar_produtos_api(request):
    try:
        termo = request.GET.get('termo', '')
        produtos = Produto.objects.filter(ativo=True)
        if termo:
            produtos = produtos.filter(
                Q(nome_produto__icontains=termo) | Q(codigo_interno__icontains=termo))
        return JsonResponse({'success': True,
                             'produtos': [_serializar_produto(p) for p in produtos[:20]]})
    except Exception as e:
        logger.exception('Erro em buscar_produtos_api')
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def buscar_servicos_api(request):
    try:
        termo = request.GET.get('termo', '')
        servicos = Servico.objects.filter(ativo=True)
        if termo:
            servicos = servicos.filter(nome__icontains=termo)
        return JsonResponse({'success': True,
                             'servicos': [_serializar_servico(s) for s in servicos[:20]]})
    except Exception as e:
        logger.exception('Erro em buscar_servicos_api')
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


# =====================================================================
# URLS (apps/vendas/urls.py) — os names têm de bater com os templates
# =====================================================================
# path('proforma/nova/',                          views.nova_proforma,                       name='nova_proforma'),
# path('fatura-credito/nova/',                    views.nova_fatura_credito,                 name='nova_fatura_credito'),
# path('api/proforma/finalizar/',                 views.finalizar_proforma_api,              name='api_finalizar_proforma'),
# path('api/fatura-credito/finalizar/',           views.finalizar_fatura_credito_api,        name='api_finalizar_fatura_credito'),
# path('api/fatura-credito/<int:fatura_id>/gerar-documento/',
#                                                 views.gerar_documento_fatura_credito_api,  name='api_gerar_documento_fatura_credito'),
# path('proforma/<int:proforma_id>/pdf/',         views.proforma_pdf_view,                   name='proforma_pdf'),
# path('api/fatura-credito/<int:fatura_id>/a4/',  views.fatura_credito_pdf_view,             name='fatura_credito_pdf'),