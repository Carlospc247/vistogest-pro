# apps/vendas/views.py
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.cache import caches
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.generic import (
    CreateView, DetailView, ListView, TemplateView, UpdateView,
)

from rest_framework import generics, mixins, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clientes.models import Cliente
from apps.core.views import BaseMPAView
from apps.fiscal.models import TaxaIVAAGT
from apps.fiscal.services.pdf_agt_service import PDFDocumentoService
from apps.funcionarios.models import Funcionario
from apps.produtos.models import Produto
from apps.servicos.models import Servico
from apps.vendas.serializers import ItemVendaSerializer, VendaSerializer

from .forms import (
    AgendarEntregaForm, ConvenioForm, DevolucaoForm, DocumentoTransporteForm,
    NotaCreditoForm, NotaDebitoForm, PagamentoVendaForm, VendaForm,
)
from .models import (
    Comissao, Convenio, DevolucaoVenda, DocumentoTransporte, Entrega,
    FaturaCredito, FaturaProforma, FormaPagamento, ItemDocumentoTransporte,
    ItemFatura, ItemNotaCredito, ItemNotaDebito, ItemProforma, ItemVenda,
    MetaVenda, NotaCredito, NotaDebito, PagamentoVenda, Recibo, Venda,
)
from .services import validar_itens_por_regime
from .tasks import verificar_margem_critica

logger = logging.getLogger(__name__)


# =====================================================================
# 0) CONFIGURAÇÃO: AÇÕES DE PERMISSÃO E NOMES DE CAMPOS
# =====================================================================
# Todas as ações têm de existir em Funcionario.pode_realizar_acao().
ACAO_VENDER = 'vender'
ACAO_ENTREGAS = 'vender'
ACAO_RELATORIOS = 'acessar_documentos'   # dashboards, KPIs, analytics, metas
ACAO_CONVENIOS = 'acessar_documentos'    # TODO: criar acção própria 'gerir_convenios'
ACAO_COMISSOES = 'acessar_documentos'    # TODO: criar acção própria 'gerir_comissoes'

# Nomes dos campos de data dos documentos fiscais. As versões anteriores
# misturavam `data_nota`/`data_documento` com `data_emissao`. Se o teu model
# usa outro nome, altera AQUI (um único sítio).
CAMPO_DATA_NC = 'data_nota'
CAMPO_DATA_ND = 'data_nota'
CAMPO_DATA_GT = 'data_documento'

IVA_PADRAO = Decimal('14.00')
CENTIMO = Decimal('0.01')
TIPOS_VENDA_PDV = {'fatura_recibo', 'balcao', 'online'}


# =====================================================================
# 1) PERMISSÕES
# =====================================================================

def requer_permissao(acao_requerida):
    """Decorator para FBVs, usando exclusivamente a lógica do modelo Funcionario."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            funcionario = getattr(request.user, "funcionario", None)
            if not funcionario:
                return JsonResponse(
                    {"success": False, "message": "Usuário não está vinculado a um funcionário."},
                    status=403,
                )
            if not funcionario.pode_realizar_acao(acao_requerida):
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"Você não tem permissão para realizar a ação '{acao_requerida}'.",
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


class PermissaoAcaoMixin(AccessMixin):
    acao_requerida = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        try:
            funcionario = request.user.funcionario
        except Exception:
            messages.error(
                request,
                "Acesso negado. O seu usuário não está ligado a um registro de funcionário.",
            )
            return self.handle_no_permission()

        if self.acao_requerida:
            if not funcionario or not funcionario.pode_realizar_acao(self.acao_requerida):
                messages.error(
                    request,
                    f"Acesso negado. O seu cargo não permite realizar a ação de '{self.acao_requerida}'.",
                )
                return redirect(reverse_lazy('core_tenants:dashboard'))

        return super().dispatch(request, *args, **kwargs)


class BaseVendaView(LoginRequiredMixin):
    """
    View base do módulo. NÃO filtra por empresa: o isolamento é o schema.
    `get_empresa()` serve só para exibir dados da empresa.
    """

    def get_empresa(self):
        return getattr(self.request.user, 'empresa', None)


# =====================================================================
# 2) HELPERS COMUNS
# =====================================================================

def _q(valor):
    """Arredonda a 2 casas, igual ao DecimalField(decimal_places=2)."""
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


def to_decimal(value):
    """Converte string/número para Decimal de forma tolerante (vírgula decimal)."""
    if value is None or value == '':
        return Decimal('0.00')
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    value_str = str(value).strip()
    try:
        if ',' in value_str and '.' in value_str:
            if value_str.index('.') < value_str.index(','):
                value_str = value_str.replace('.', '')
        return Decimal(value_str.replace(',', '.'))
    except (ValueError, TypeError, InvalidOperation):
        logger.error('Erro de conversão para Decimal no valor: %s', value)
        return Decimal('0.00')


def _int_param(request, nome, padrao, minimo=1, maximo=3650):
    """Lê um inteiro da query string sem rebentar com 500."""
    try:
        valor = int(request.GET.get(nome, padrao))
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(valor, maximo))


def _parse_data(valor, campo):
    try:
        return datetime.strptime(str(valor), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValidationError(f'{campo} inválida (formato esperado: AAAA-MM-DD).')


def _regime_do_tenant(request):
    """O regime vem do tenant activo (COMERCIO / SERVICOS / MISTO)."""
    tenant = getattr(request, 'tenant', None) or getattr(connection, 'tenant', None)
    if tenant is None or getattr(tenant, 'schema_name', 'public') == 'public':
        raise PermissionDenied('Este documento só está disponível no domínio de uma empresa.')
    regime = getattr(tenant, 'regime', None)
    if regime not in {'COMERCIO', 'SERVICOS', 'MISTO'}:
        raise PermissionDenied('O tipo de actividade da empresa não está configurado correctamente.')
    return regime


def _obter_cliente(data, obrigatorio=True):
    cliente_id = data.get('cliente_id')
    if not cliente_id:
        if obrigatorio:
            raise ValidationError('Cliente é obrigatório.')
        return None
    try:
        cliente = Cliente.objects.filter(pk=cliente_id, ativo=True).first()
    except (ValueError, TypeError):
        cliente = None
    if not cliente:
        raise ValidationError('Cliente não encontrado ou inactivo.')
    return cliente


def _percentual_iva(obj):
    """% de IVA do produto/serviço (taxa_iva > iva_percentual > 14%)."""
    taxa = getattr(obj, 'taxa_iva', None)
    if taxa is not None:
        return Decimal(str(taxa.tax_percentage))
    pct = getattr(obj, 'iva_percentual', None)
    return IVA_PADRAO if pct is None else Decimal(str(pct))


def _resolver_iva(obj):
    """(TaxaIVAAGT|None, percentual). O servidor é a fonte de verdade do IVA."""
    taxa = getattr(obj, 'taxa_iva', None)
    if taxa is not None:
        return taxa, Decimal(str(taxa.tax_percentage))
    pct = _percentual_iva(obj)
    return TaxaIVAAGT.objects.filter(tax_percentage=pct).first(), pct


def _json_seguro(obj):
    """JSON para injectar em <script> com |safe."""
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
        'preco': float(s.preco_padrao or 0),
        'categoria': _nome_categoria(s),
        'categoria_id': getattr(s, 'categoria_id', None),
        'descricao': getattr(s, 'descricao', '') or '',
        'iva_percentual': float(_percentual_iva(s)),
    }


def _render_documento_comercial(request, template, titulo, tipo_documento):
    """Contexto idêntico ao do PDV: regime + produtos/serviços filtrados pelo regime."""
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

    produtos_json = _json_seguro(produtos)
    servicos_json = _json_seguro(servicos)
    return render(request, template, {
        'title': titulo,
        'tipo_documento': tipo_documento,
        'regime': regime,
        # Mantêm-se os nomes antigos para não quebrar templates legados.
        'produtos': produtos_json,
        'servicos': servicos_json,
        # Os novos templates partilhados usam explicitamente JSON seguro.
        'produtos_json': produtos_json,
        'servicos_json': servicos_json,
    })


def _montar_linhas(itens, verificar_estoque=False):
    """
    Valida e calcula as linhas SEM confiar nos valores do cliente: preço, nome,
    operação e IVA vêm da BD; do cliente só vêm produto_id/servico_id,
    quantidade e desconto_item (valor absoluto da linha).
    Chamar dentro de transaction.atomic() (usa select_for_update no estoque).
    """
    if not itens or not isinstance(itens, list):
        raise ValidationError('O documento deve conter pelo menos um item.')

    validar_itens_por_regime(itens)

    linhas = []
    reservado = {}   # produto_id -> quantidade já pedida noutras linhas do mesmo documento
    for idx, it in enumerate(itens, start=1):
        if not isinstance(it, dict):
            raise ValidationError(f'Item {idx}: formato inválido.')
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
            if verificar_estoque:
                ja_pedido = reservado.get(produto.pk, Decimal('0'))
                if produto.estoque_atual < ja_pedido + qtd:
                    raise ValidationError(
                        f'Estoque insuficiente para "{produto.nome_produto}" '
                        f'(disponível: {produto.estoque_atual}).')
                reservado[produto.pk] = ja_pedido + qtd
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
    """Recalcula o cabeçalho a partir dos itens PERSISTIDOS."""
    ag = doc.itens.aggregate(sub=Sum('subtotal'), desc=Sum('desconto_item'), iva=Sum('iva_valor'))
    sub = ag['sub'] or Decimal('0.00')
    desc = ag['desc'] or Decimal('0.00')
    iva = ag['iva'] or Decimal('0.00')
    doc.subtotal, doc.desconto_valor, doc.iva_valor = sub, desc, iva
    doc.total = sub - desc + iva
    doc.save(update_fields=['subtotal', 'desconto_valor', 'iva_valor', 'total'])


def _qtd_inteira(quantidade):
    """ItemVenda.quantidade é inteiro: rejeita fracções em vez de truncar em silêncio."""
    q = Decimal(str(quantidade))
    if q != q.to_integral_value():
        raise ValidationError('Quantidades fraccionadas não são suportadas neste documento.')
    return int(q)


def _baixar_estoque(linhas):
    for l in linhas:
        if l['produto']:
            qtd = l['quantidade']
            qtd = int(qtd) if qtd == qtd.to_integral_value() else qtd
            Produto.objects.filter(pk=l['produto'].pk).update(estoque_atual=F('estoque_atual') - qtd)


def _reservar_estoque(produto_id, quantidade):
    """Bloqueia a linha do produto, valida e baixa o estoque. Dentro de atomic()."""
    p = Produto.objects.select_for_update().get(pk=produto_id)
    if p.estoque_atual < quantidade:
        raise ValidationError(f'Estoque insuficiente para "{p.nome_produto}".')
    Produto.objects.filter(pk=p.pk).update(estoque_atual=F('estoque_atual') - quantidade)


def _repor_estoque(produto_id, quantidade):
    Produto.objects.filter(pk=produto_id).update(estoque_atual=F('estoque_atual') + quantidade)


def _criar_item_venda(venda, *, produto, servico, quantidade, preco_unitario, desconto_linha, taxa):
    """
    Cria ItemVenda. ATENÇÃO: ItemVenda.desconto_item é POR UNIDADE; os outros
    documentos guardam o valor da linha. Divide-se aqui (arredondado a 2 casas).
    """
    qtd = _qtd_inteira(quantidade)
    desconto_unit = (_q(desconto_linha) / qtd).quantize(CENTIMO) if qtd else Decimal('0.00')
    return ItemVenda.objects.create(
        venda=venda, produto=produto, servico=servico,
        nome_produto=produto.nome_produto if produto else None,
        nome_servico=servico.nome if servico else None,
        quantidade=qtd, preco_unitario=preco_unitario, desconto_item=desconto_unit,
        taxa_iva=taxa, operation_type='TB' if produto else 'SE',
    )


def _resposta_erro(exc):
    if isinstance(exc, PermissionDenied):
        return JsonResponse({'success': False, 'message': str(exc) or 'Acesso negado.'}, status=403)
    if isinstance(exc, ValidationError):
        return JsonResponse({'success': False, 'message': _msg_erro(exc)}, status=400)
    if isinstance(exc, Http404):
        return JsonResponse({'success': False, 'message': 'Registo não encontrado.'}, status=404)
    if isinstance(exc, KeyError):
        return JsonResponse(
            {'success': False, 'message': f'Campo obrigatório em falta: {exc.args[0]}.'}, status=400)
    logger.exception('Erro inesperado ao processar documento comercial')
    return JsonResponse({'success': False, 'message': 'Erro interno ao processar o documento.'}, status=500)


def _invalidar_cache_bi():
    """
    Invalida a cache de BI SÓ do tenant actual, incrementando uma versão que
    faz parte da chave (cache.clear() apagaria a cache de todas as empresas).
    Nunca propaga erros: um problema de cache não pode falhar a venda.
    """
    try:
        c = caches['B_I']
        chave = f'bi_versao:{connection.schema_name}'
        try:
            c.incr(chave)
        except ValueError:
            c.set(chave, 2, None)
    except Exception:
        logger.warning(
            "Falha ao invalidar o cache BI (ignorada; a venda não é afectada).",
            exc_info=True,
        )
        

def _data_q(campo, lookup, valor):
    """Constrói {'<campo>__<lookup>': valor} para os campos configuráveis."""
    return {f'{campo}__{lookup}': valor}


# =====================================================================
# 3) PÁGINAS DE EMISSÃO (FT / FP)
# =====================================================================

@login_required
@require_GET
@requer_permissao('emitir_faturacredito')
def nova_fatura_credito(request):
    return _render_documento_comercial(
        request, 'vendas/nova_fatura_credito.html', 'Nova Fatura a Crédito (FT)', 'FT')


@login_required
@require_GET
@requer_permissao('emitir_proforma')
def nova_proforma(request):
    return _render_documento_comercial(
        request, 'vendas/nova_proforma.html', 'Nova Proforma (Orçamento)', 'FP')


# =====================================================================
# Opções comuns de partilha/notificação de documentos comerciais
# =====================================================================

def _opcoes_notificacao(data):
    """Só envia notificações quando o utilizador as activa explicitamente."""
    ativada = data.get('enviar_notificacao') is True or str(data.get('enviar_notificacao', '')).lower() in {'1', 'true', 'sim', 'on'}
    if not ativada:
        return False, None, None

    email = (data.get('email_cliente_avulso') or '').strip() or None
    whatsapp = (data.get('whatsapp_cliente_avulso') or '').strip() or None
    if not email and not whatsapp:
        raise ValidationError('Para enviar o documento, indique um e-mail e/ou WhatsApp.')
    if email:
        from django.core.validators import validate_email
        validate_email(email)
    if whatsapp and len(''.join(ch for ch in whatsapp if ch.isdigit())) < 9:
        raise ValidationError('O número de WhatsApp parece inválido. Inclua o indicativo do país.')
    return True, email, whatsapp


def _publicar_documento_no_perfil(cliente, tipo_documento, documento, utilizador, solicitado):
    """Publica o documento apenas na conta activa com e-mail igual ao do Cliente interno.

    A ligação é opt-in e tenant-local. Uma falha na funcionalidade opcional não deve
    cancelar a emissão contabilística do documento; o resultado é devolvido à UI.
    """
    resultado = {'solicitado': bool(solicitado), 'partilhado': False, 'mensagem': ''}
    if not solicitado:
        return resultado
    if cliente is None:
        resultado['mensagem'] = 'Selecione um cliente para disponibilizar o documento no perfil.'
        return resultado
    email_cliente = (getattr(cliente, 'email', '') or '').strip()
    if not email_cliente:
        resultado['mensagem'] = 'O cliente interno não tem e-mail registado.'
        return resultado

    try:
        from apps.site.models import ClienteSite, DocumentoPartilhado
        with transaction.atomic():
            conta = ClienteSite.objects.filter(email__iexact=email_cliente, ativo=True).first()
            if not conta:
                resultado['mensagem'] = 'Não foi encontrada uma conta ativa no site com o mesmo e-mail do cliente.'
                return resultado

            numero = getattr(documento, 'numero_documento', '') or f'{tipo_documento.upper()}-{documento.pk}'
            DocumentoPartilhado.objects.update_or_create(
                cliente_site=conta,
                tipo_documento=tipo_documento,
                documento_id=documento.pk,
                defaults={
                    'numero_documento': str(numero),
                    'titulo': str(numero),
                    'total': getattr(documento, 'total', Decimal('0.00')) or Decimal('0.00'),
                    'compartilhado_por': utilizador,
                    'ativo': True,
                },
            )
        resultado['partilhado'] = True
        resultado['mensagem'] = 'Documento disponibilizado no perfil da conta do cliente.'
        return resultado
    except Exception:
        # A partilha é opcional. O savepoint acima isola erros de tabela/migração
        # e impede que uma falha na área do site desfaça a emissão fiscal.
        logger.exception('Não foi possível publicar %s #%s no perfil do cliente.', tipo_documento, getattr(documento, 'pk', '?'))
        resultado['mensagem'] = 'Documento criado, mas a partilha falhou. Confirme a migração do modelo DocumentoPartilhado e a conta do cliente.'
        return resultado


def _notificar_documento_comercial(tipo_documento, documento_id, email, whatsapp):
    """Despacha e-mail/PDF e WhatsApp via adaptador configurável, depois do commit."""
    try:
        from apps.vendas.docs.servicos.notificacao_service import NotificacaoDocumentoService
        resultado = NotificacaoDocumentoService.disparar(
            tipo_documento=tipo_documento,
            documento_id=documento_id,
            email_destino=email,
            whatsapp_destino=whatsapp,
        )
        logger.info('Notificação de %s #%s concluída: %s', tipo_documento, documento_id, resultado)
    except Exception:
        logger.exception('Falha ao notificar %s #%s.', tipo_documento, documento_id)


# =====================================================================
# 4) CRIAR PROFORMA / FATURA A CRÉDITO
# =====================================================================

@login_required
@require_POST
@requer_permissao('emitir_proforma')
def finalizar_proforma_api(request):
    """Cria a Proforma (FP); partilha/notifica apenas se o utilizador o pedir."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data)
        validade = _parse_data(data.get('data_validade'), 'Data de validade')
        if validade < timezone.localdate():
            raise ValidationError('A data de validade não pode estar no passado.')
        notificar, email_avulso, whats_avulso = _opcoes_notificacao(data)
        publicar_perfil = data.get('publicar_no_perfil') is True or str(data.get('publicar_no_perfil', '')).lower() in {'1', 'true', 'sim', 'on'}

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
            proforma.save(usuario_criacao=request.user)
            for l in linhas:
                ItemProforma.objects.create(
                    proforma=proforma, produto=l['produto'], servico=l['servico'],
                    quantidade=l['quantidade'], preco_unitario=l['preco'],
                    desconto_item=l['desconto'], iva_percentual=l['pct'], taxa_iva=l['taxa'],
                )
            _reconciliar_totais(proforma)
            perfil = _publicar_documento_no_perfil(cliente, 'proforma', proforma, request.user, publicar_perfil)
            proforma_id = proforma.pk
            transaction.on_commit(_invalidar_cache_bi)
            if notificar:
                transaction.on_commit(lambda: _notificar_documento_comercial('proforma', proforma_id, email_avulso, whats_avulso))

        return JsonResponse({
            'success': True,
            'message': f'Proforma {proforma.numero_documento} criada com sucesso!',
            'proforma_id': proforma.pk,
            'numero_documento': proforma.numero_documento,
            'total': float(proforma.total),
            'perfil_cliente': perfil,
            'notificacao_solicitada': notificar,
        })
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_faturacredito')
def finalizar_fatura_credito_api(request):
    """Cria a FT, baixa stock e regista partilha/notificação opcionais."""
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)
        cliente = _obter_cliente(data)
        vencimento = _parse_data(data.get('data_vencimento'), 'Data de vencimento')
        if vencimento < timezone.localdate():
            raise ValidationError('A data de vencimento não pode estar no passado.')
        notificar, email_avulso, whats_avulso = _opcoes_notificacao(data)
        publicar_perfil = data.get('publicar_no_perfil') is True or str(data.get('publicar_no_perfil', '')).lower() in {'1', 'true', 'sim', 'on'}

        with transaction.atomic():
            linhas, t = _montar_linhas(data.get('itens'), verificar_estoque=True)
            fatura = FaturaCredito.objects.create(
                cliente=cliente,
                vendedor=getattr(request.user, 'funcionario', None),
                data_vencimento=vencimento,
                subtotal=t['subtotal'], desconto_valor=t['desconto'],
                iva_valor=t['iva'], total=t['total'], valor_pago=Decimal('0.00'),
                observacoes=(data.get('observacoes') or '').strip() or None,
                status='emitida',
            )
            for l in linhas:
                ItemFatura.objects.create(
                    fatura=fatura, produto=l['produto'], servico=l['servico'],
                    nome_item=l['nome'], quantidade=l['quantidade'],
                    preco_unitario=l['preco'], desconto_item=l['desconto'],
                    iva_percentual=l['pct'], taxa_iva=l['taxa'], operation_type=l['operacao'],
                )
            _reconciliar_totais(fatura)
            _baixar_estoque(linhas)
            fatura.gerar_documento_fiscal(request.user)
            perfil = _publicar_documento_no_perfil(cliente, 'fatura_credito', fatura, request.user, publicar_perfil)
            fatura_id = fatura.pk
            transaction.on_commit(_invalidar_cache_bi)
            if notificar:
                transaction.on_commit(lambda: _notificar_documento_comercial('fatura_credito', fatura_id, email_avulso, whats_avulso))

        return JsonResponse({
            'success': True,
            'message': f'Fatura {fatura.numero_documento} criada com sucesso!',
            'fatura_id': fatura.pk,
            'numero_documento': fatura.numero_documento,
            'total': float(fatura.total),
            'perfil_cliente': perfil,
            'notificacao_solicitada': notificar,
        })
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_faturacredito')
def gerar_documento_fatura_credito_api(request, fatura_id):
    """FT já existente sem documento fiscal."""
    try:
        with transaction.atomic():
            fatura = get_object_or_404(FaturaCredito.objects.select_for_update(), id=fatura_id)
            if fatura.status != 'emitida':
                raise ValidationError('Fatura já processada.')
            if fatura.documento_fiscal_id:
                raise ValidationError('Esta fatura já tem documento fiscal.')
            fatura.gerar_documento_fiscal(request.user)
        return JsonResponse({'success': True, 'numero': fatura.numero_documento})
    except Exception as e:
        return _resposta_erro(e)


# =====================================================================
# 5) CONVERSÃO PROFORMA -> FR / FT
# =====================================================================

def _taxa_do_item_proforma(item):
    if item.taxa_iva_id:
        return item.taxa_iva
    return TaxaIVAAGT.objects.filter(tax_percentage=item.iva_percentual).first()


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
        qtd = _qtd_inteira(item.quantidade)
        if item.produto_id:
            _reservar_estoque(item.produto_id, qtd)
        _criar_item_venda(
            venda, produto=item.produto, servico=item.servico, quantidade=qtd,
            preco_unitario=item.preco_unitario, desconto_linha=item.desconto_item,
            taxa=_taxa_do_item_proforma(item))

    venda.calcular_totais()
    venda.valor_pago = venda.total
    venda.save(update_fields=['subtotal', 'iva_valor', 'total', 'valor_pago'])
    venda.gerar_documento_fiscal(user)
    return venda


def _converter_para_fatura_credito(proforma, user):
    """Proforma -> Fatura de Crédito (FT)."""
    fatura = FaturaCredito.objects.create(
        cliente=proforma.cliente,
        vendedor=getattr(user, 'funcionario', None),
        subtotal=proforma.subtotal, desconto_valor=proforma.desconto_valor,
        iva_valor=proforma.iva_valor, total=proforma.total,
        valor_pago=Decimal('0.00'),
        status='emitida',
        data_vencimento=timezone.localdate() + timedelta(days=30),
        observacoes=f'Convertido da Proforma {proforma.numero_documento}',
    )

    for item in proforma.itens.select_related('produto', 'servico'):
        if item.produto_id:
            qtd = item.quantidade
            qtd = int(qtd) if qtd == qtd.to_integral_value() else qtd
            _reservar_estoque(item.produto_id, qtd)

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


@login_required
@require_POST
@requer_permissao('liquidar_faturacredito')
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
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('aprovar_proforma')
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
    except Exception as e:
        return _resposta_erro(e)


# =====================================================================
# 6) PDFs
# =====================================================================

def _gerar_response_pdf(obj_documento, prefixo, tamanho='a4'):
    """Centraliza a chamada ao PDFDocumentoService."""
    try:
        pdf_service = PDFDocumentoService(
            documento_fiscal=getattr(obj_documento, 'documento_fiscal', None),
            venda_obj=obj_documento,
            tamanho=tamanho,
        )
        pdf_buffer = pdf_service.gerar()

        numero_documento = str(getattr(obj_documento, 'numero_documento', '') or obj_documento.pk)
        safe_number = numero_documento.replace('/', '_').replace(' ', '_')
        filename = f'{prefixo}_{safe_number}.pdf'

        return FileResponse(pdf_buffer, as_attachment=False, content_type='application/pdf', filename=filename)
    except Exception as e:
        logger.error('Erro ao gerar PDF %s ID %s: %s', prefixo, obj_documento.id, e, exc_info=True)
        raise Http404('Erro interno ao gerar o documento PDF.')


@login_required
@require_GET
@requer_permissao('vender')
def fatura_pdf_view(request, venda_id, tipo='a4'):
    """PDF da Fatura-Recibo (FR). tipo: 'a4' ou '80mm'."""
    tamanho = '80mm' if tipo == '80mm' else 'a4'
    return _gerar_response_pdf(get_object_or_404(Venda, id=venda_id), 'FR', tamanho)


@login_required
@require_GET
@requer_permissao('emitir_faturacredito')
def fatura_credito_pdf_view(request, fatura_id, tipo='a4'):
    """PDF da Fatura de Crédito (FT)."""
    tamanho = '80mm' if tipo == '80mm' else 'a4'
    return _gerar_response_pdf(get_object_or_404(FaturaCredito, id=fatura_id), 'FT', tamanho)


@login_required
@require_GET
@requer_permissao('emitir_recibos')
def recibo_pdf_view(request, recibo_id):
    """PDF do Recibo (REC)."""
    return _gerar_response_pdf(get_object_or_404(Recibo, id=recibo_id), 'REC')


@login_required
@require_GET
@requer_permissao('emitir_proforma')
def proforma_pdf_view(request, proforma_id):
    """PDF da Proforma (FP)."""
    return _gerar_response_pdf(get_object_or_404(FaturaProforma, id=proforma_id), 'FP')


@login_required
@require_GET
@requer_permissao('aplicar_notacredito')
def nota_credito_pdf_view(request, nota_id):
    """PDF da Nota de Crédito (NC)."""
    return _gerar_response_pdf(get_object_or_404(NotaCredito, id=nota_id), 'NC')


@login_required
@require_GET   # era POST: o PDF nunca abria num <a>/window.open
@requer_permissao('aplicar_notacredito')
def nota_debito_pdf_view(request, nota_id):
    """PDF da Nota de Débito (ND)."""
    return _gerar_response_pdf(get_object_or_404(NotaDebito, id=nota_id), 'ND')


@login_required
@require_GET
@requer_permissao('emitir_documentotransporte')
def documento_transporte_pdf_view(request, documento_id):
    """PDF da Guia de Transporte (GT)."""
    return _gerar_response_pdf(get_object_or_404(DocumentoTransporte, id=documento_id), 'GT')


# =====================================================================
# 7) APIs DE BUSCA
# =====================================================================

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
    except Exception:
        logger.exception('Erro em buscar_produtos_api')
        return JsonResponse({'success': False, 'message': 'Erro interno.'}, status=500)


@login_required
def buscar_servicos_api(request):
    try:
        termo = request.GET.get('termo', '')
        servicos = Servico.objects.filter(ativo=True)
        if termo:
            servicos = servicos.filter(nome__icontains=termo)
        return JsonResponse({'success': True,
                             'servicos': [_serializar_servico(s) for s in servicos[:20]]})
    except Exception:
        logger.exception('Erro em buscar_servicos_api')
        return JsonResponse({'success': False, 'message': 'Erro interno.'}, status=500)


@login_required
def buscar_clientes_api(request):
    try:
        termo = request.GET.get('termo', '')
        clientes = Cliente.objects.filter(ativo=True)
        if termo:
            clientes = clientes.filter(
                Q(nome_completo__icontains=termo) | Q(nif__icontains=termo) | Q(email__icontains=termo))

        resultados = [{
            'id': c.id, 'nome_completo': c.nome_completo, 'nif': c.nif, 'email': c.email,
            'telefone': getattr(c, 'telefone', ''), 'endereco': getattr(c, 'endereco', ''),
        } for c in clientes[:20]]
        return JsonResponse({'success': True, 'clientes': resultados})
    except Exception:
        logger.exception('Erro em buscar_clientes_api')
        return JsonResponse({'success': False, 'message': 'Erro interno.'}, status=500)


@login_required
@require_GET
def formas_pagamento_api(request):
    formas = FormaPagamento.objects.filter(ativa=True).order_by('ordem_exibicao')
    return JsonResponse({'success': True,
                         'formas_pagamento': [{'id': f.id, 'nome': f.nome} for f in formas]})


@login_required
@require_GET
@requer_permissao('acessar_documentos')  # consulta de documentos de origem
def buscar_documentos_origem_api(request):
    """Documentos de origem para notas de crédito/débito."""
    try:
        tipo = request.GET.get('tipo')
        termo = request.GET.get('termo', '')
        resultados = []

        if tipo == 'venda':
            vendas = Venda.objects.filter(status='finalizada').select_related('cliente')
            if termo:
                vendas = vendas.filter(
                    Q(numero_documento__icontains=termo) | Q(cliente__nome_completo__icontains=termo))
            for venda in vendas[:20]:
                resultados.append({
                    'id': venda.id, 'numero': venda.numero_documento,
                    'cliente': venda.cliente.nome_completo if venda.cliente else 'N/A',
                    'data': venda.data_venda.strftime('%d/%m/%Y'), 'total': float(venda.total),
                })
        elif tipo == 'fatura_credito':
            faturas = FaturaCredito.objects.select_related('cliente')
            if termo:
                faturas = faturas.filter(
                    Q(numero_documento__icontains=termo) | Q(cliente__nome_completo__icontains=termo))
            for fatura in faturas[:20]:
                resultados.append({
                    'id': fatura.id, 'numero': fatura.numero_documento,
                    'cliente': fatura.cliente.nome_completo if fatura.cliente else 'N/A',
                    'data': fatura.data_fatura.strftime('%d/%m/%Y'), 'total': float(fatura.total),
                })

        return JsonResponse({'success': True, 'documentos': resultados})
    except Exception:
        logger.exception('Erro em buscar_documentos_origem_api')
        return JsonResponse({'success': False, 'message': 'Erro interno.'}, status=500)


# =====================================================================
# 8) VENDAS (FR / VD / TV)
# =====================================================================

class VendasView(BaseMPAView):
    template_name = 'vendas/vendas.html'
    module_name = 'vendas'
    paginate_by = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()

        periodo = self.request.GET.get('periodo', 'mes')
        status_filtro = self.request.GET.get('status', '')
        vendedor_id = self.request.GET.get('vendedor', '')
        cliente_nome = self.request.GET.get('cliente', '')
        valor_min = self.request.GET.get('valor_min', '')
        sort = self.request.GET.get('sort', '-data_venda')
        if sort.lstrip('-') not in {'data_venda', 'total', 'status', 'numero_documento', 'cliente'}:
            sort = '-data_venda'

        vendas = Venda.objects.all()

        if periodo == 'hoje':
            vendas = vendas.filter(data_venda__date=hoje)
        elif periodo == 'semana':
            inicio_semana = hoje - timedelta(days=hoje.weekday())
            vendas = vendas.filter(data_venda__date__gte=inicio_semana)
        elif periodo == 'mes':
            vendas = vendas.filter(data_venda__year=hoje.year, data_venda__month=hoje.month)
        elif periodo == 'trimestre':
            inicio_trimestre = hoje.replace(month=((hoje.month - 1) // 3) * 3 + 1, day=1)
            vendas = vendas.filter(data_venda__date__gte=inicio_trimestre)

        if status_filtro:
            vendas = vendas.filter(status=status_filtro)
        if vendedor_id:
            vendas = vendas.filter(vendedor_id=vendedor_id)
        if cliente_nome:
            vendas = vendas.filter(
                Q(cliente__nome_completo__icontains=cliente_nome) |
                Q(cliente__nif__icontains=cliente_nome))
        if valor_min:
            try:
                vendas = vendas.filter(total__gte=Decimal(valor_min))
            except (InvalidOperation, ValueError):
                pass

        vendas = vendas.order_by(sort)

        paginator = Paginator(vendas, self.paginate_by)
        vendas_page = paginator.get_page(self.request.GET.get('page'))

        vendas_mes = Venda.objects.filter(
            data_venda__year=hoje.year, data_venda__month=hoje.month, status='finalizada'
        ).aggregate(total=Sum('total'), quantidade=Count('id'))

        vendas_hoje_qs = Venda.objects.filter(data_venda__date=hoje)
        vendas_hoje_fin = vendas_hoje_qs.filter(status='finalizada')
        vendas_hoje_total = vendas_hoje_fin.aggregate(total=Sum('total'))['total'] or 0

        context.update({
            'vendas': vendas_page,
            'vendas_total': vendas.aggregate(total=Sum('total'))['total'] or 0,
            'vendas_stats': {
                'vendas_mes': float(vendas_mes['total'] or 0),
                'quantidade_mes': vendas_mes['quantidade'] or 0,
                'ticket_medio': float(vendas_mes['total'] or 0) / max(vendas_mes['quantidade'] or 1, 1),
                'clientes_mes': vendas.filter(
                    data_venda__year=hoje.year, data_venda__month=hoje.month
                ).values('cliente').distinct().count(),
                'vendas_hoje': vendas_hoje_fin.count(),
                'vendas_hoje_total': float(vendas_hoje_total),
                'vendas_pendentes': vendas_hoje_qs.filter(status='pendente').count(),
                'vendas_canceladas': vendas_hoje_qs.filter(status='cancelada').count(),
            },
            'vendedores': Funcionario.objects.filter(ativo=True).values('id', 'nome_completo'),
            'paginator': paginator,
            'is_paginated': vendas_page.has_other_pages(),
            'page_obj': vendas_page,
        })
        return context


@login_required
@require_GET
@requer_permissao(ACAO_VENDER)
def vendas_lista(request):
    vendas = Venda.objects.select_related('cliente', 'forma_pagamento').order_by('-data_venda')[:50]
    return render(request, 'vendas/vendas_lista.html', {'vendas': vendas, 'title': 'Vendas Realizadas'})


class VendaDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    """Detalhes de uma venda: itens, pagamentos e orçamento de origem."""
    acao_requerida = ACAO_VENDER
    model = Venda
    template_name = 'vendas/venda_detail.html'
    context_object_name = 'venda'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = self.object
        context.update({
            'title': f'Venda {venda.numero_documento}',
            'itens': venda.itens.select_related('produto'),
            'pagamentos': venda.pagamentos.all(),
            'orcamento_origem': getattr(venda, 'orcamento_origem', None),
            'pode_editar': venda.status in ['rascunho', 'pendente'],
            'pode_cancelar': venda.status in ['pendente', 'finalizada'],
            'resumo': {
                'subtotal': venda.subtotal,
                'desconto_total': venda.desconto_valor,
                'criada_em': venda.data_venda,
                'status': venda.status,
            },
        })
        return context


class VendaCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = ACAO_VENDER

    model = Venda
    form_class = VendaForm
    template_name = 'vendas/venda_form.html'
    success_url = reverse_lazy('vendas:lista')

    def form_valid(self, form):
        form.instance.vendedor = getattr(self.request.user, 'funcionario', None)
        form.instance.usuario_criacao = self.request.user

        with transaction.atomic():
            response = super().form_valid(form)

            if not form.instance.numero_documento:
                form.instance.numero_documento = f'V{form.instance.id:06d}'
                form.instance.save(update_fields=['numero_documento'])

            messages.success(self.request, f'Venda {form.instance.numero_documento} criada com sucesso!')
            return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': 'Nova Venda',
            'clientes': Cliente.objects.filter(ativo=True),
            'produtos': Produto.objects.filter(ativo=True),
            'formas_pagamento': FormaPagamento.objects.filter(ativa=True),
        })
        return context


class VendaUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = ACAO_VENDER

    model = Venda
    form_class = VendaForm
    template_name = 'vendas/venda_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'pendente']:
            messages.error(self.request, 'Não é possível editar esta venda.')
            return redirect(self.get_success_url())

        form.instance.usuario_modificacao = self.request.user
        messages.success(self.request, 'Venda atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': f'Editar Venda {self.object.numero_documento}',
            'clientes': Cliente.objects.filter(ativo=True),
            'produtos': Produto.objects.filter(ativo=True),
            'formas_pagamento': FormaPagamento.objects.filter(ativa=True),
        })
        return context


def _cancelar_venda(venda_id, user, motivo):
    """
    Lógica única de cancelamento (view HTML e API). Levanta ValidationError /
    PermissionDenied. NOTA fiscal: um documento já emitido à AGT deveria ser
    anulado por Nota de Crédito; aqui só se altera o estado e repõe o estoque.
    """
    with transaction.atomic():
        venda = get_object_or_404(Venda.objects.select_for_update(), pk=venda_id)

        if venda.status == 'cancelada':
            raise ValidationError('Venda já está cancelada.')
        if venda.status not in ['pendente', 'finalizada']:
            raise ValidationError('Não é possível cancelar esta venda.')

        if venda.total > Decimal('1000'):
            funcionario = getattr(user, 'funcionario', None)
            if not (funcionario and funcionario.pode_realizar_acao('cancelar_venda_alto_valor')):
                raise PermissionDenied('Cancelações de alto valor requerem autorização superior.')

        for item in venda.itens.filter(produto__isnull=False):
            _repor_estoque(item.produto_id, item.quantidade)

        venda.status = 'cancelada'
        venda.data_cancelamento = timezone.now()
        venda.motivo_cancelamento = motivo
        venda.usuario_cancelamento = user
        venda.save()
    return venda


class CancelarVendaView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'cancelar_venda'

    def post(self, request, pk):
        try:
            venda = _cancelar_venda(pk, request.user, request.POST.get('motivo', 'Cancelamento solicitado'))
            messages.success(request, f'Venda {venda.numero_documento} cancelada com sucesso!')
        except (ValidationError, PermissionDenied) as e:
            messages.error(request, _msg_erro(e))
        return redirect('vendas:detail', pk=pk)


class CancelarVendaAPIView(PermissaoAcaoMixin, BaseVendaView, View):
    """Sem csrf_exempt: o front-end deve enviar o header X-CSRFToken."""
    acao_requerida = 'cancelar_venda'

    def post(self, request):
        try:
            data = _ler_json(request)
            if not data.get('venda_id'):
                raise ValidationError('venda_id é obrigatório.')
            venda = _cancelar_venda(data['venda_id'], request.user, data.get('motivo', 'Cancelamento via API'))
            return JsonResponse({'success': True, 'message': f'Venda {venda.numero_documento} cancelada com sucesso'})
        except Exception as e:
            return _resposta_erro(e)


# ---- Dashboards / KPIs -------------------------------------------------

class VendaDashboardView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_RELATORIOS
    template_name = 'vendas/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)

        vendas_hoje = Venda.objects.filter(data_venda__date=hoje, status='finalizada').aggregate(
            total=Sum('total'), quantidade=Count('id'))
        vendas_mes = Venda.objects.filter(data_venda__date__gte=mes_atual, status='finalizada').aggregate(
            total=Sum('total'), quantidade=Count('id'))

        top_produtos = ItemVenda.objects.filter(
            venda__data_venda__date__gte=mes_atual, venda__status='finalizada', produto__isnull=False
        ).values('produto__nome_produto').annotate(
            quantidade_vendida=Sum('quantidade'), total=Sum('total')
        ).order_by('-quantidade_vendida')[:10]

        vendas_por_pagamento = Venda.objects.filter(
            data_venda__date__gte=mes_atual, status='finalizada'
        ).values('forma_pagamento__nome').annotate(total=Sum('total'), quantidade=Count('id'))

        context.update({
            'title': 'Dashboard de Vendas',
            'vendas_hoje': vendas_hoje,
            'vendas_mes': vendas_mes,
            'top_produtos': top_produtos,
            'vendas_por_pagamento': vendas_por_pagamento,
        })
        return context


class VendaAnalyticsView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_RELATORIOS
    template_name = 'vendas/analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = _int_param(self.request, 'periodo', 30)
        data_inicio = timezone.now().date() - timedelta(days=periodo)
        base = Venda.objects.filter(data_venda__date__gte=data_inicio, status='finalizada')

        vendas_por_dia = (base.annotate(dia=TruncDate('data_venda')).values('dia')
                              .annotate(total=Sum('total'), quantidade=Count('id')).order_by('dia'))
        vendas_por_vendedor = (base.values('vendedor__nome_completo')
                                   .annotate(total=Sum('total'), quantidade=Count('id')).order_by('-total'))
        ticket_medio = base.aggregate(Avg('total'))['total__avg'] or 0

        context.update({
            'title': 'Analytics de Vendas',
            'vendas_por_dia': vendas_por_dia,
            'vendas_por_vendedor': vendas_por_vendedor,
            'ticket_medio': ticket_medio,
            'periodo': str(periodo),
        })
        return context


class VendaKPIsView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_RELATORIOS
    template_name = 'vendas/kpis.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)
        mes_anterior = (mes_atual - timedelta(days=1)).replace(day=1)

        kpis_atual = Venda.objects.filter(data_venda__date__gte=mes_atual, status='finalizada').aggregate(
            faturamento=Sum('total'), quantidade_vendas=Count('id'), ticket_medio=Avg('total'))
        kpis_anterior = Venda.objects.filter(
            data_venda__date__gte=mes_anterior, data_venda__date__lt=mes_atual, status='finalizada'
        ).aggregate(faturamento=Sum('total'), quantidade_vendas=Count('id'), ticket_medio=Avg('total'))

        def crescimento(atual, anterior):
            if anterior and anterior > 0:
                return ((atual - anterior) / anterior) * 100
            return 0 if atual == 0 else 100

        context.update({
            'title': 'KPIs de Vendas',
            'kpis_atual': kpis_atual,
            'kpis_anterior': kpis_anterior,
            'crescimento_faturamento': crescimento(kpis_atual['faturamento'] or 0, kpis_anterior['faturamento'] or 0),
            'crescimento_vendas': crescimento(kpis_atual['quantidade_vendas'] or 0, kpis_anterior['quantidade_vendas'] or 0),
        })
        return context


class MetasVendaView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_RELATORIOS
    template_name = 'vendas/metas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        mes_atual = hoje.replace(day=1)

        meta_mes = MetaVenda.objects.filter(mes=mes_atual.month, ano=mes_atual.year, vendedor__isnull=True).first()
        vendas_mes = Venda.objects.filter(data_venda__date__gte=mes_atual, status='finalizada').aggregate(
            total_vendido=Sum('total'), quantidade_vendas=Count('id'))

        percentual_faturamento = 0
        percentual_quantidade = 0
        if meta_mes:
            if meta_mes.meta_faturamento:
                percentual_faturamento = float(vendas_mes['total_vendido'] or 0) / float(meta_mes.meta_faturamento) * 100
            if meta_mes.meta_quantidade_vendas:
                percentual_quantidade = (vendas_mes['quantidade_vendas'] or 0) / meta_mes.meta_quantidade_vendas * 100

        context.update({
            'title': 'Metas de Vendas',
            'meta_mes': meta_mes,
            'vendas_mes': vendas_mes,
            'percentual_faturamento': percentual_faturamento,
            'percentual_quantidade': percentual_quantidade,
        })
        return context


# =====================================================================
# 10) PAGAMENTOS
# =====================================================================

class PagamentoListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = ACAO_VENDER
    model = PagamentoVenda
    template_name = 'vendas/pagamento_lista.html'
    context_object_name = 'pagamentos'

    def get_queryset(self):
        return PagamentoVenda.objects.filter(venda__pk=self.kwargs.get('venda_pk')).order_by('-data_pagamento')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        context.update({'venda': venda, 'title': f'Pagamentos - Venda {venda.numero_documento}'})
        return context


class PagamentoCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = ACAO_VENDER
    model = PagamentoVenda
    form_class = PagamentoVendaForm
    template_name = 'vendas/pagamento_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:pagamento_lista', kwargs={'venda_pk': self.kwargs.get('venda_pk')})

    def form_valid(self, form):
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        form.instance.venda = venda
        with transaction.atomic():
            response = super().form_valid(form)
            # O estorno já recalculava o saldo; o registo de pagamento não.
            venda.calcular_saldo_e_atualizar_status()
        messages.success(self.request, 'Pagamento registrado com sucesso!')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venda = get_object_or_404(Venda, pk=self.kwargs.get('venda_pk'))
        context.update({'venda': venda, 'title': f'Novo Pagamento - Venda {venda.numero_documento}'})
        return context


class PagamentoDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = ACAO_VENDER
    model = PagamentoVenda
    template_name = 'vendas/pagamento_detail.html'
    context_object_name = 'pagamento'


class EstornarPagamentoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'estornar_pagamento'

    def post(self, request, pk):
        try:
            with transaction.atomic():
                pagamento = get_object_or_404(PagamentoVenda.objects.select_for_update(), pk=pk)
                if pagamento.status == 'estornado':
                    messages.warning(request, 'O pagamento já está marcado como estornado. Nenhuma ação foi executada.')
                else:
                    pagamento.status = 'estornado'
                    pagamento.data_estorno = timezone.now()
                    pagamento.usuario_estorno = request.user
                    pagamento.motivo_estorno = request.POST.get('motivo', 'Estorno via sistema (motivo não especificado)')
                    pagamento.save()
                    pagamento.venda.calcular_saldo_e_atualizar_status()
                    messages.success(request, f'Pagamento de AO {pagamento.valor_pago} estornado com sucesso.')
        except Http404:
            raise
        except Exception:
            logger.exception('Erro no estorno de PagamentoVenda %s', pk)
            messages.error(request, 'Falha ao estornar o pagamento. A operação foi revertida.')

        return redirect('vendas:pagamento_detail', pk=pk)


class _PagamentoTemplateView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_VENDER
    titulo = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = self.titulo
        return context


class PagamentoCartaoView(_PagamentoTemplateView):
    template_name = 'vendas/pagamento_cartao.html'
    titulo = 'Pagamento Cartão'


class PagamentoConvenioView(_PagamentoTemplateView):
    template_name = 'vendas/pagamento_convenio.html'
    titulo = 'Pagamento Convênio'


class PagamentoCrediarioView(_PagamentoTemplateView):
    template_name = 'vendas/pagamento_crediario.html'
    titulo = 'Pagamento Crediário'


# =====================================================================
# 11) DEVOLUÇÕES
# =====================================================================

class DevolucaoListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = 'fazer_devolucao'
    model = DevolucaoVenda
    template_name = 'vendas/devolucao_lista.html'
    context_object_name = 'devolucoes'
    paginate_by = 20

    def get_queryset(self):
        return DevolucaoVenda.objects.select_related('venda_original', 'cliente').order_by('-data_devolucao')


class DevolucaoVendaView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'fazer_devolucao'

    model = DevolucaoVenda
    form_class = DevolucaoForm
    template_name = 'vendas/devolucao_form.html'
    success_url = reverse_lazy('vendas:devolucao_lista')

    def get_initial(self):
        initial = super().get_initial()
        venda = get_object_or_404(Venda, pk=self.kwargs.get('pk'))
        initial['venda_original'] = venda
        initial['cliente'] = venda.cliente
        return initial

    def form_valid(self, form):
        form.instance.solicitante = self.request.user

        with transaction.atomic():
            response = super().form_valid(form)
            for item_dev in form.instance.itens.select_related('item_venda_original__produto'):
                produto = item_dev.item_venda_original.produto
                if produto:
                    _repor_estoque(produto.pk, item_dev.quantidade_devolvida)

        messages.success(self.request, 'Devolução registrada com sucesso!')
        return response


class DevolucaoDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = 'fazer_devolucao'
    model = DevolucaoVenda
    template_name = 'vendas/devolucao_detail.html'
    context_object_name = 'devolucao'


# =====================================================================
# 12) ENTREGAS
# =====================================================================

class DeliveryListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = ACAO_ENTREGAS
    model = Venda
    template_name = 'vendas/delivery_lista.html'
    context_object_name = 'vendas'
    paginate_by = 20

    def get_queryset(self):
        return Venda.objects.filter(tipo_venda='entrega').select_related('cliente').order_by('-data_venda')


class AgendarEntregaView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = ACAO_ENTREGAS
    model = Venda
    form_class = AgendarEntregaForm
    template_name = 'vendas/agendar_entrega.html'

    def get_success_url(self):
        return reverse_lazy('vendas:detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.status_entrega = 'agendada'
        messages.success(self.request, 'Entrega agendada com sucesso!')
        return super().form_valid(form)


class EntregaListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = ACAO_ENTREGAS
    model = Entrega
    template_name = 'vendas/entrega_lista.html'
    context_object_name = 'entregas'
    paginate_by = 20

    def get_queryset(self):
        return Entrega.objects.select_related('venda', 'entregador').order_by('-data_agendada')


class ConfirmarEntregaDeliveryView(PermissaoAcaoMixin, BaseVendaView, View):
    """Confirma a entrega de uma Venda do tipo 'entrega' (ver ConfirmarEntregaView para GT)."""
    acao_requerida = 'confirmar_entrega'

    def post(self, request, pk):
        with transaction.atomic():
            entrega = get_object_or_404(Entrega.objects.select_for_update(), pk=pk)
            entrega.status = 'entregue'
            entrega.data_entrega = timezone.now()
            entrega.confirmado_por = request.user
            entrega.observacoes_entrega = request.POST.get('observacoes', '')
            entrega.save()

            entrega.venda.status_entrega = 'entregue'
            entrega.venda.save(update_fields=['status_entrega'])

        messages.success(request, 'Entrega confirmada com sucesso!')
        return redirect('vendas:entrega_lista')


class RotaEntregaView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_ENTREGAS
    template_name = 'vendas/rota_entrega.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        entregas_hoje = Entrega.objects.filter(
            data_agendada__date=hoje, status__in=['agendada', 'saiu_entrega']
        ).select_related('venda', 'entregador')
        context.update({'title': 'Rota de Entrega', 'entregas_hoje': entregas_hoje})
        return context


# =====================================================================
# 13) CONVÊNIOS
# =====================================================================

class ConvenioListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = ACAO_CONVENIOS
    model = Convenio
    template_name = 'vendas/convenio_lista.html'
    context_object_name = 'convenios'
    paginate_by = 20

    def get_queryset(self):
        return Convenio.objects.order_by('nome')


class ConvenioCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = ACAO_CONVENIOS
    model = Convenio
    form_class = ConvenioForm
    template_name = 'vendas/convenio_form.html'
    success_url = reverse_lazy('vendas:convenio_lista')

    def form_valid(self, form):
        messages.success(self.request, 'Convênio cadastrado com sucesso!')
        return super().form_valid(form)


class ConvenioDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = ACAO_CONVENIOS
    model = Convenio
    template_name = 'vendas/convenio_detail.html'
    context_object_name = 'convenio'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Venda não tem FK para Convenio: relatório vazio até a relação existir.
        context.update({'vendas_recentes': Venda.objects.none()})
        return context


class FaturarConvenioView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_CONVENIOS
    template_name = 'vendas/faturar_convenio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        convenio = get_object_or_404(Convenio, pk=self.kwargs.get('pk'))
        # Sem FK Venda->Convenio nem status_faturamento: vazio até a modelagem existir.
        context.update({'convenio': convenio, 'vendas_pendentes': Venda.objects.none(), 'total_faturar': 0})
        return context


# =====================================================================
# 14) COMISSÕES
# =====================================================================

class ComissaoListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = ACAO_COMISSOES
    model = Comissao
    template_name = 'vendas/comissao_lista.html'
    context_object_name = 'comissoes'
    paginate_by = 20

    def get_queryset(self):
        return Comissao.objects.select_related('vendedor', 'venda').order_by('-created_at')


class CalcularComissaoView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = ACAO_COMISSOES
    template_name = 'vendas/calcular_comissao.html'

    def post(self, request):
        try:
            mes = int(request.POST.get('mes'))
            ano = int(request.POST.get('ano'))
            if not 1 <= mes <= 12:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Mês/ano inválidos.')
            return redirect('vendas:comissao_lista')

        vendedor_id = request.POST.get('vendedor_id')
        vendas = Venda.objects.filter(data_venda__month=mes, data_venda__year=ano, status='finalizada')
        if vendedor_id:
            vendas = vendas.filter(vendedor_id=vendedor_id)

        with transaction.atomic():
            for venda in vendas:
                Comissao.calcular_comissao(venda)

        messages.success(request, 'Comissões calculadas com sucesso!')
        return redirect('vendas:comissao_lista')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Calcular Comissões', 'vendedores': Funcionario.objects.filter(ativo=True)})
        return context


class PagarComissaoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = ACAO_COMISSOES

    def post(self, request):
        comissao_ids = request.POST.getlist('comissao_ids')
        pagas = 0
        with transaction.atomic():
            for comissao in Comissao.objects.select_for_update().filter(id__in=comissao_ids, status='calculada'):
                comissao.status = 'paga'
                comissao.data_pagamento = timezone.now().date()
                comissao.save()
                pagas += 1

        messages.success(request, f'{pagas} comissões pagas com sucesso!')
        return redirect('vendas:comissao_lista')


# =====================================================================
# 15) AJAX E UTILITÁRIOS (login + permissão; sem csrf_exempt)
# =====================================================================

class _AjaxVendaView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = ACAO_VENDER


class CalcularDescontoView(_AjaxVendaView):
    def post(self, request):
        try:
            data = _ler_json(request)
            subtotal = _dec(data.get('subtotal', 0), 'subtotal', Decimal('0'))
            desconto_valor = _dec(data.get('desconto_valor', 0), 'desconto', Decimal('0'))
            if data.get('desconto_tipo', 'valor') == 'percentual':
                valor_desconto = subtotal * (desconto_valor / 100)
            else:
                valor_desconto = desconto_valor
            return JsonResponse({'success': True, 'valor_desconto': float(valor_desconto),
                                 'total': float(subtotal - valor_desconto)})
        except Exception as e:
            return _resposta_erro(e)


class VerificarEstoqueVendaView(_AjaxVendaView):
    def get(self, request):
        try:
            quantidade = int(request.GET.get('quantidade', 1))
            produto = Produto.objects.get(id=request.GET.get('produto_id'))
        except (TypeError, ValueError):
            return JsonResponse({'disponivel': False, 'error': 'Parâmetros inválidos'}, status=400)
        except Produto.DoesNotExist:
            return JsonResponse({'disponivel': False, 'error': 'Produto não encontrado'}, status=404)

        return JsonResponse({
            'disponivel': produto.estoque_atual >= quantidade,
            'estoque_atual': produto.estoque_atual,
            'quantidade_solicitada': quantidade,
        })


class CalcularTrocoView(_AjaxVendaView):
    def post(self, request):
        try:
            data = _ler_json(request)
            total = _dec(data.get('total', 0), 'total', Decimal('0'))
            recebido = _dec(data.get('valor_recebido', 0), 'valor recebido', Decimal('0'))
            return JsonResponse({'success': True, 'troco': float(recebido - total)})
        except Exception as e:
            return _resposta_erro(e)


class ConsultarPrecoAPIView(_AjaxVendaView):
    def get(self, request):
        try:
            quantidade = int(request.GET.get('quantidade', 1))
            produto = Produto.objects.get(id=request.GET.get('produto_id'))
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Parâmetros inválidos'}, status=400)
        except Produto.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Produto não encontrado'}, status=404)

        preco = produto.preco_venda
        subtotal = preco * quantidade
        return JsonResponse({
            'success': True,
            'produto': {
                'id': produto.id,
                'nome': produto.nome_produto,
                'preco_unitario': float(preco),
                'quantidade': quantidade,
                'subtotal': float(subtotal),
                'desconto': 0.0,
                'total': float(subtotal),
            },
        })


class AplicarDescontoAPIView(_AjaxVendaView):
    acao_requerida = 'fazer_desconto'

    def post(self, request):
        try:
            data = _ler_json(request)
            desconto_valor = _dec(data.get('desconto_valor', 0), 'desconto', Decimal('0'))
            tipo = data.get('desconto_tipo', 'valor')

            with transaction.atomic():
                venda = get_object_or_404(Venda.objects.select_for_update(), id=data.get('venda_id'))
                if venda.status not in ['rascunho', 'pendente']:
                    raise ValidationError('Não é possível aplicar desconto nesta venda.')

                if tipo == 'percentual':
                    if desconto_valor > 100:
                        raise ValidationError('O desconto percentual não pode exceder 100%.')
                    venda.desconto_valor = _q(venda.subtotal * (desconto_valor / 100))
                else:
                    if desconto_valor > venda.subtotal:
                        raise ValidationError('O desconto não pode exceder o subtotal.')
                    venda.desconto_valor = _q(desconto_valor)

                venda.calcular_totais()
                venda.save()

            return JsonResponse({
                'success': True, 'message': 'Desconto aplicado com sucesso',
                'venda': {'subtotal': float(venda.subtotal), 'desconto': float(venda.desconto_valor),
                          'total': float(venda.total)},
            })
        except Exception as e:
            return _resposta_erro(e)


# =====================================================================
# 16) PDV
# =====================================================================

class PDVView(PermissaoAcaoMixin, LoginRequiredMixin, TemplateView):
    """PDV com catálogo serializado como JSON seguro e isolado pelo schema."""
    acao_requerida = ACAO_VENDER
    template_name = 'vendas/pdv.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        regime = _regime_do_tenant(self.request)
        context['clientes'] = list(Cliente.objects.filter(ativo=True).values('id', 'nome_completo'))
        context['formas_pagamento'] = list(FormaPagamento.objects.filter(ativa=True).values('id', 'nome'))
        produtos_qs = (
            Produto.objects.filter(ativo=True).order_by('nome_produto')
            if regime in {'COMERCIO', 'MISTO'} else Produto.objects.none()
        )
        servicos_qs = (
            Servico.objects.filter(ativo=True).order_by('nome')
            if regime in {'SERVICOS', 'MISTO'} else Servico.objects.none()
        )
        produtos = [_serializar_produto(item) for item in produtos_qs]
        servicos = [_serializar_servico(item) for item in servicos_qs]
        context.update({
            'produtos': _json_seguro(produtos),
            'servicos': _json_seguro(servicos),
            'produtos_json': _json_seguro(produtos),
            'servicos_json': _json_seguro(servicos),
            'regime': regime,
        })
        return context


@login_required
@require_POST
@requer_permissao("vender")
def finalizar_venda_api(request):
    """
    Finaliza Venda (FR / VD) no PDV. Preços, IVA e totais são calculados no
    servidor a partir dos ids e quantidades; subtotal/iva_valor/total/
    preco_unitario enviados pelo cliente são IGNORADOS.
    """
    try:
        data = _ler_json(request)
        _regime_do_tenant(request)

        cliente = _obter_cliente(data, obrigatorio=False)   # PDV permite consumidor final
        forma = FormaPagamento.objects.filter(pk=data.get('forma_pagamento_id'), ativa=True).first() \
            if data.get('forma_pagamento_id') else None
        if not forma:
            raise ValidationError('Forma de pagamento inválida ou não informada.')

        tipo_venda = data.get('tipo_venda', 'fatura_recibo')
        if tipo_venda not in TIPOS_VENDA_PDV:
            raise ValidationError('Tipo de venda inválido.')

        notificar, email_avulso, whats_avulso = _opcoes_notificacao(data)
        publicar_perfil = data.get('publicar_no_perfil') is True or str(data.get('publicar_no_perfil', '')).lower() in {'1', 'true', 'sim', 'on'}

        with transaction.atomic():
            linhas, t = _montar_linhas(data.get('itens'), verificar_estoque=True)

            venda = Venda.objects.create(
                cliente=cliente,
                vendedor=getattr(request.user, 'funcionario', None),
                forma_pagamento=forma,
                subtotal=t['subtotal'], desconto_valor=t['desconto'],
                iva_valor=t['iva'], total=t['total'], valor_pago=t['total'],
                status='finalizada', tipo_venda=tipo_venda,
                usuario_criacao=request.user,
            )

            for l in linhas:
                _criar_item_venda(
                    venda, produto=l['produto'], servico=l['servico'], quantidade=l['quantidade'],
                    preco_unitario=l['preco'], desconto_linha=l['desconto'], taxa=l['taxa'])

            venda.calcular_totais()
            venda.valor_pago = venda.total
            venda.save(update_fields=['subtotal', 'iva_valor', 'total', 'valor_pago'])
            _baixar_estoque(linhas)
            venda.gerar_documento_fiscal(request.user)
            perfil = _publicar_documento_no_perfil(cliente, 'venda', venda, request.user, publicar_perfil)

            venda_id = venda.id
            transaction.on_commit(_invalidar_cache_bi)
            if notificar:
                transaction.on_commit(lambda: _notificar_venda(venda_id, email_avulso, whats_avulso))

        return JsonResponse({
            'success': True, 'venda_id': venda.id, 'numero': venda.numero_documento,
            'perfil_cliente': perfil, 'notificacao_solicitada': notificar,
        })
    except Exception as e:
        return _resposta_erro(e)


def _notificar_venda(venda_id, email_avulso, whats_avulso):
    """Corre DEPOIS do commit; uma falha de notificação não pode afectar a venda."""
    try:
        from apps.vendas.docs.servicos.notificacao_service import NotificacaoVendaService
        NotificacaoVendaService.disparar_todas(
            Venda.objects.get(pk=venda_id), email_avulso=email_avulso, whats_avulso=whats_avulso)
    except Exception:
        logger.exception('Falha ao notificar a venda %s', venda_id)


class PDVCreateAPIView(PermissaoAcaoMixin, APIView):
    """Criação atómica de venda via serializers (PDV)."""
    acao_requerida = ACAO_VENDER

    def post(self, request, *args, **kwargs):
        venda_data = request.data.get('venda')
        itens_data = request.data.get('itens')

        if not itens_data:
            return Response({'detail': 'A venda deve conter pelo menos um item.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Excepções DRF dentro do atomic fazem rollback e viram 400.
        with transaction.atomic():
            venda_serializer = VendaSerializer(data=venda_data)
            venda_serializer.is_valid(raise_exception=True)
            venda = venda_serializer.save(status='finalizada')

            for item_data in itens_data:
                item_serializer = ItemVendaSerializer(data=dict(item_data, venda=venda.id))
                if not item_serializer.is_valid():
                    raise serializers.ValidationError({'itens': item_serializer.errors})
                item_serializer.save()

                produto = item_serializer.validated_data.get('produto')
                if produto:
                    _reservar_estoque(produto.pk, item_serializer.validated_data['quantidade'])

            transaction.on_commit(_invalidar_cache_bi)

        return Response(VendaSerializer(venda).data, status=status.HTTP_201_CREATED)


class SalvarRascunhoApiView(_AjaxVendaView):
    def post(self, request):
        try:
            data = _ler_json(request)
            forma = None
            if data.get('forma_pagamento_id'):
                forma = FormaPagamento.objects.filter(pk=data['forma_pagamento_id']).first()
            cliente = _obter_cliente(data, obrigatorio=False)

            with transaction.atomic():
                venda = Venda.objects.create(
                    cliente=cliente,
                    vendedor=getattr(request.user, 'funcionario', None),
                    forma_pagamento=forma,
                    desconto_valor=to_decimal(data.get('desconto', 0)),
                    observacoes=data.get('observacoes', ''),
                    status='rascunho',
                    usuario_criacao=request.user,
                )

                total = Decimal('0.00')
                for item_data in data.get('itens', []):
                    produto = get_object_or_404(Produto, id=item_data['produto_id'], ativo=True)
                    item = ItemVenda.objects.create(
                        venda=venda, produto=produto,
                        quantidade=_qtd_inteira(item_data['quantidade']),
                        preco_unitario=produto.preco_venda,   # preço do servidor
                    )
                    total += item.total

                venda.total = total - venda.desconto_valor
                venda.save(update_fields=['total'])

            return JsonResponse({'success': True, 'message': 'Rascunho salvo com sucesso', 'venda_id': venda.id})
        except Exception as e:
            return _resposta_erro(e)


class AbrirGavetaApiView(_AjaxVendaView):
    def post(self, request):
        logger.info('Gaveta aberta por: %s', request.user.get_username())
        return JsonResponse({'success': True, 'message': 'Gaveta aberta com sucesso'})


# =====================================================================
# 17) DOCUMENTOS: LISTAS, DASHBOARD, CONTAS A RECEBER
# =====================================================================

@login_required
@requer_permissao('liquidar_faturacredito')
def contas_receber(request):
    hoje = timezone.localdate()   # data_vencimento é DateField

    faturas_ativas = FaturaCredito.objects.filter(status__in=['emitida', 'parcial']).select_related('cliente')
    faturas_vencidas = faturas_ativas.filter(data_vencimento__lt=hoje)
    faturas_vencendo = faturas_ativas.filter(data_vencimento__range=[hoje, hoje + timedelta(days=7)])

    context = {
        'title': 'Gestão de Contas a Receber',
        'total_a_receber': sum((f.valor_pendente() for f in faturas_ativas), Decimal('0.00')),
        'faturas_pendentes': faturas_ativas,
        'qtd_vencidas': faturas_vencidas.count(),
        'qtd_vencendo': faturas_vencendo.count(),
        'valor_vencido': sum((f.valor_pendente() for f in faturas_vencidas), Decimal('0.00')),
    }
    return render(request, 'vendas/contas_receber.html', context)


@login_required
@requer_permissao('acessar_documentos')
def documentos_dashboard_view(request):
    """Dashboard consolidado de todos os tipos de documentos emitidos."""
    data_inicio = timezone.now().date() - timedelta(days=30)

    vendas_qs = Venda.objects.filter(data_venda__date__gte=data_inicio)
    vendas_stats = vendas_qs.aggregate(
        total_faturamento=Sum('total'),
        qtd_fr=Count('id', filter=Q(tipo_venda='fatura_recibo')),
        qtd_vd=Count('id', filter=Q(tipo_venda='balcao')),
        qtd_tv=Count('id', filter=Q(tipo_venda='online')),
    )
    faturas_stats = FaturaCredito.objects.filter(data_fatura__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('total'),
        pendentes=Count('id', filter=Q(status__in=['emitida', 'parcial'])))
    recibos_stats = Recibo.objects.filter(data_recibo__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('valor_pago'))
    proformas_stats = FaturaProforma.objects.filter(data_proforma__gte=data_inicio).aggregate(
        qtd=Count('id'), valor=Sum('total'))

    notas_stats = {
        'nc': NotaCredito.objects.filter(**_data_q(CAMPO_DATA_NC, 'gte', data_inicio)).count(),
        'nd': NotaDebito.objects.filter(**_data_q(CAMPO_DATA_ND, 'gte', data_inicio)).count(),
    }
    logistica_stats = {
        'gt': DocumentoTransporte.objects.filter(**_data_q(CAMPO_DATA_GT, 'gte', data_inicio)).count(),
        'td': DevolucaoVenda.objects.filter(data_devolucao__gte=data_inicio).count(),
    }

    context = {
        'title': 'Painel de Gestão Documental',
        'vendas_stats': vendas_stats,
        'faturas_stats': faturas_stats,
        'recibos_stats': recibos_stats,
        'proformas_stats': proformas_stats,
        'notas_stats': notas_stats,
        'logistica_stats': logistica_stats,
        'vendas_recentes': vendas_qs.select_related('cliente').order_by('-data_venda')[:15],
    }
    return render(request, 'vendas/documentos_dashboard.html', context)


@login_required
@requer_permissao('acessar_documentos')
def faturas_recibo_lista(request):
    vendas = Venda.objects.select_related('cliente', 'forma_pagamento').order_by('-data_venda')
    return render(request, 'vendas/faturas_recibo_lista.html', {'vendas': vendas, 'title': 'Faturas Recibo (FR)'})


@login_required
@requer_permissao('acessar_documentos')
def faturas_credito_lista(request):
    faturas = FaturaCredito.objects.select_related('cliente').order_by('-data_fatura')
    return render(request, 'vendas/faturas_credito_lista.html', {'faturas': faturas, 'title': 'Faturas a Crédito (FT)'})


@login_required
@requer_permissao('acessar_documentos')
def recibos_lista(request):
    recibos = Recibo.objects.select_related('cliente', 'vendedor', 'forma_pagamento').order_by('-data_recibo')
    return render(request, 'vendas/recibos_lista.html', {'recibos': recibos, 'title': 'Recibos (REC)'})


@login_required
@requer_permissao('acessar_documentos')
def proformas_lista(request):
    proformas = FaturaProforma.objects.select_related('cliente').order_by('-data_proforma')
    return render(request, 'vendas/proformas_lista.html', {'proformas': proformas, 'title': 'Proformas'})


@login_required
@require_POST
@requer_permissao(ACAO_VENDER)
def atualizar_observacoes_venda(request, venda_id):
    try:
        data = _ler_json(request)
        venda = get_object_or_404(Venda, id=venda_id)
        venda.observacoes = data.get('observacoes', '')
        venda.save(update_fields=['observacoes'])
        return JsonResponse({'success': True})
    except Exception as e:
        return _resposta_erro(e)


# =====================================================================
# 18) LIQUIDAÇÃO / RECIBOS
# =====================================================================

@login_required
@require_POST
@requer_permissao('liquidar_faturacredito')
def liquidar_fatura_api(request, fatura_id):
    """Liquida a FT, gera o REC e a movimentação no Caixa/Banco, tudo atómico."""
    try:
        funcionario = getattr(request.user, 'funcionario', None)

        with transaction.atomic():
            fatura = get_object_or_404(FaturaCredito.objects.select_for_update(), pk=fatura_id)

            if fatura.status == 'liquidada':
                raise ValidationError('Esta fatura já se encontra liquidada.')
            if fatura.status not in ('emitida', 'parcial'):
                raise ValidationError('Esta fatura não pode ser liquidada no estado actual.')

            valor_pendente = fatura.valor_pendente()
            if valor_pendente <= 0:
                raise ValidationError('Não há valor pendente nesta fatura.')

            forma_id = request.POST.get('forma_pagamento_id')
            if forma_id:
                forma = get_object_or_404(FormaPagamento, id=forma_id, ativa=True)
            else:
                forma = FormaPagamento.objects.filter(ativa=True).first()

            recibo = Recibo.objects.create(
                fatura=fatura, cliente=fatura.cliente, vendedor=funcionario,
                forma_pagamento=forma, valor_pago=valor_pendente, status='emitido',
            )
            recibo.gerar_documento_fiscal()

            conta_destino = forma.conta_destino if forma else None
            if conta_destino:
                from apps.financeiro.models import MovimentacaoFinanceira
                MovimentacaoFinanceira.objects.create(
                    tipo_movimentacao='entrada', tipo_documento='recibo',
                    data_movimentacao=timezone.now().date(), valor=valor_pendente,
                    descricao=f'Liquidação da Fatura {fatura.numero_documento} - REC {recibo.numero_recibo}',
                    conta_bancaria=conta_destino, usuario_responsavel=request.user,
                    confirmada=True, recibo=recibo,
                )

            fatura.valor_pago += valor_pendente
            fatura.status = 'liquidada'
            fatura.save()

        return JsonResponse({
            'success': True,
            'message': f'Fatura liquidada. Recibo {recibo.numero_recibo} gerado.',
            'recibo_id': recibo.id,
        })
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_recibos')
def finalizar_recibo_api(request):
    """Recibo (pagamento total ou parcial) de uma fatura. Para liquidação total + caixa use liquidar_fatura_api."""
    try:
        data = _ler_json(request)
        with transaction.atomic():
            fatura = get_object_or_404(FaturaCredito.objects.select_for_update(), id=data.get('fatura_id'))
            valor = _q(_dec(data.get('valor_pago'), 'valor pago', Decimal('0.01')))

            if fatura.status not in ('emitida', 'parcial'):
                raise ValidationError('Esta fatura não aceita recibos no estado actual.')
            if valor > fatura.valor_pendente():
                raise ValidationError('O valor do recibo excede o valor pendente da fatura.')

            recibo = Recibo.objects.create(
                fatura=fatura, cliente=fatura.cliente,
                vendedor=getattr(request.user, 'funcionario', None), valor_pago=valor,
            )

            # Antes o valor_pago da fatura nunca era actualizado, logo nunca liquidava.
            fatura.valor_pago += valor
            fatura.status = 'liquidada' if fatura.valor_pendente() <= 0 else 'parcial'
            fatura.save()

        return JsonResponse({'success': True, 'recibo_id': recibo.id})
    except Exception as e:
        return _resposta_erro(e)


# =====================================================================
# 19) NOTAS DE CRÉDITO / DÉBITO / GT — APIs
# =====================================================================

@login_required
@require_POST
@requer_permissao('aplicar_notacredito')
def finalizar_nota_credito_api(request):
    """Finaliza Nota de Crédito (NC). O total é recalculado a partir dos itens."""
    try:
        data = _ler_json(request)
        itens = data.get('itens')
        if not itens or not isinstance(itens, list):
            raise ValidationError('A nota deve conter pelo menos um item.')
        validar_itens_por_regime(itens)
        cliente = _obter_cliente(data)

        with transaction.atomic():
            nota = NotaCredito.objects.create(
                cliente=cliente,
                emitida_por=request.user,
                motivo=data.get('motivo', 'outros'),
                venda_origem_id=data.get('venda_origem_id'),
                total=Decimal('0.00'),
                status='emitida',
            )
            for idx, item in enumerate(itens, start=1):
                ItemNotaCredito.objects.create(
                    nota_credito=nota,
                    produto_id=item.get('produto_id'),
                    servico_id=item.get('servico_id'),
                    quantidade_creditada=_dec(item.get('quantidade'), f'quantidade do item {idx}', Decimal('0.01')),
                    valor_unitario_credito=_dec(item.get('preco_unitario'), f'preço do item {idx}', Decimal('0')),
                )
            nota.recalcular_total()
            nota.save()

        return JsonResponse({'success': True, 'nota_id': nota.id})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('aplicar_notadebito')
def finalizar_nota_debito_api(request, nota_id):
    """Finaliza Nota de Débito (ND) e gera rastro AGT."""
    try:
        with transaction.atomic():
            nota = get_object_or_404(NotaDebito.objects.select_for_update(), id=nota_id)
            nota.save()
        return JsonResponse({'success': True, 'numero': nota.numero_nota})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_documentotransporte')
def finalizar_documento_transporte_api(request):
    """Finaliza Guia de Transporte (GT)."""
    try:
        data = _ler_json(request)
        if _regime_do_tenant(request) == 'SERVICOS':
            raise ValidationError('Empresas em regime de serviços não emitem Guias de Transporte de mercadorias.')

        itens = data.get('itens')
        if not itens or not isinstance(itens, list):
            raise ValidationError('A guia deve conter pelo menos um item.')

        with transaction.atomic():
            gt = DocumentoTransporte.objects.create(
                emitido_por=request.user,
                destinatario_nome=data['destinatario_nome'],
                destinatario_endereco=data['destinatario_endereco'],
                data_inicio_transporte=data['data_inicio'],
                data_previsao_entrega=data.get('data_previsao_entrega') or timezone.now(),
                veiculo_matricula=data['veiculo_matricula'],
                status='preparando',
            )
            for idx, item in enumerate(itens, start=1):
                ItemDocumentoTransporte.objects.create(
                    documento=gt,
                    produto_id=item['produto_id'],
                    quantidade_enviada=_dec(item.get('quantidade'), f'quantidade do item {idx}', Decimal('0.01')),
                )

        return JsonResponse({'success': True, 'documento_id': gt.id})
    except Exception as e:
        return _resposta_erro(e)


# ---- Itens: adicionar / remover ----------------------------------------

@login_required
@require_POST
@requer_permissao('emitir_notacredito')
def adicionar_item_nota_credito_api(request):
    try:
        data = _ler_json(request)
        with transaction.atomic():
            nota = get_object_or_404(NotaCredito.objects.select_for_update(), id=data.get('nota_id'))
            if nota.status not in ['rascunho', 'emitida']:
                raise ValidationError('Não é possível adicionar itens a esta nota.')
            item = ItemNotaCredito.objects.create(
                nota_credito=nota,
                produto_id=data.get('produto_id'),
                servico_id=data.get('servico_id'),
                descricao_item=data['descricao'],
                quantidade_creditada=_dec(data.get('quantidade'), 'quantidade', Decimal('0.01')),
                valor_unitario_credito=_dec(data.get('preco_unitario'), 'preço', Decimal('0')),
                iva_percentual=_dec(data.get('iva_percentual', 0), 'IVA', Decimal('0')),
            )
            nota.recalcular_total()
        return JsonResponse({'success': True, 'item_id': item.id, 'total': float(item.total_item_credito),
                             'novo_total': float(nota.total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_notadebito')
def adicionar_item_nota_debito_api(request):
    try:
        data = _ler_json(request)
        with transaction.atomic():
            nota = get_object_or_404(NotaDebito.objects.select_for_update(), id=data.get('nota_id'))
            if nota.status not in ['rascunho', 'emitida']:
                raise ValidationError('Não é possível adicionar itens a esta nota.')
            item = ItemNotaDebito.objects.create(
                nota_debito=nota,
                produto_id=data.get('produto_id'),
                servico_id=data.get('servico_id'),
                descricao_item=data['descricao'],
                quantidade=_dec(data.get('quantidade'), 'quantidade', Decimal('0.01')),
                valor_unitario=_dec(data.get('preco_unitario'), 'preço', Decimal('0')),
                iva_percentual=_dec(data.get('iva_percentual', 0), 'IVA', Decimal('0')),
            )
            nota.recalcular_total()
        return JsonResponse({'success': True, 'item_id': item.id, 'total': float(item.total_item),
                             'novo_total': float(nota.total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_POST
@requer_permissao('emitir_documentotransporte')
def adicionar_item_documento_transporte_api(request):
    try:
        data = _ler_json(request)
        with transaction.atomic():
            doc = get_object_or_404(DocumentoTransporte.objects.select_for_update(), id=data.get('documento_id'))
            if doc.status != 'preparando':
                raise ValidationError('Não é possível adicionar itens a este documento.')
            item = ItemDocumentoTransporte.objects.create(
                documento=doc,
                produto_id=data['produto_id'],
                quantidade_enviada=_dec(data.get('quantidade'), 'quantidade', Decimal('0.01')),
                peso_unitario=_dec(data.get('peso_unitario', 0), 'peso', Decimal('0')),
                valor_unitario=_dec(data.get('preco_unitario', 0), 'preço', Decimal('0')),
            )
            doc.peso_total = sum((i.peso_total for i in doc.itens.all()), Decimal('0.000'))
            doc.save()
        return JsonResponse({'success': True, 'item_id': item.id, 'novo_peso_total': float(doc.peso_total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_http_methods(['DELETE'])
@requer_permissao('aplicar_notacredito')
def remover_item_nota_credito_api(request, item_id):
    try:
        with transaction.atomic():
            item = get_object_or_404(ItemNotaCredito, pk=item_id)
            nota = NotaCredito.objects.select_for_update().get(pk=item.nota_credito_id)
            if nota.status not in ['rascunho', 'emitida']:
                raise ValidationError('Não é possível remover itens desta nota.')
            item.delete()
            nota.recalcular_total()
        return JsonResponse({'success': True, 'message': 'Item removido com sucesso!', 'novo_total': float(nota.total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_http_methods(['DELETE'])
@requer_permissao('aplicar_notadebito')
def remover_item_nota_debito_api(request, item_id):
    try:
        with transaction.atomic():
            item = get_object_or_404(ItemNotaDebito, pk=item_id)
            nota = NotaDebito.objects.select_for_update().get(pk=item.nota_debito_id)
            if nota.status not in ['rascunho', 'emitida']:
                raise ValidationError('Não é possível remover itens desta nota.')
            item.delete()
            nota.recalcular_total()
        return JsonResponse({'success': True, 'message': 'Item removido com sucesso!', 'novo_total': float(nota.total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_http_methods(['DELETE'])
@requer_permissao('emitir_documentotransporte')
def remover_item_documento_transporte_api(request, item_id):
    try:
        with transaction.atomic():
            item = get_object_or_404(ItemDocumentoTransporte, pk=item_id)
            documento = DocumentoTransporte.objects.select_for_update().get(pk=item.documento_id)
            if documento.status != 'preparando':
                raise ValidationError('Não é possível remover itens deste documento.')
            item.delete()
            documento.peso_total = sum((i.peso_total for i in documento.itens.all()), Decimal('0.000'))
            documento.save()
        return JsonResponse({'success': True, 'message': 'Item removido com sucesso!',
                             'novo_peso_total': float(documento.peso_total)})
    except Exception as e:
        return _resposta_erro(e)


@login_required
@require_GET
@requer_permissao('acessar_documentos')
def estatisticas_rapidas_api(request):
    try:
        hoje = timezone.now().date()
        agora = timezone.now()

        nc_hoje = NotaCredito.objects.filter(**_data_q(CAMPO_DATA_NC, 'date', hoje)).aggregate(
            quantidade=Count('id'), valor_total=Sum('total'))
        nd_hoje = NotaDebito.objects.filter(**_data_q(CAMPO_DATA_ND, 'date', hoje)).aggregate(
            quantidade=Count('id'), valor_total=Sum('total'))
        gt_hoje = DocumentoTransporte.objects.filter(**_data_q(CAMPO_DATA_GT, 'date', hoje)).aggregate(
            quantidade=Count('id'), em_transito=Count('id', filter=Q(status='em_transito')))

        pendencias = {
            'nc_pendentes_aprovacao': NotaCredito.objects.filter(
                requer_aprovacao=True, aprovada_por__isnull=True).count(),
            'nd_vencidas': NotaDebito.objects.filter(
                data_vencimento__lt=hoje, status__in=['emitida', 'aplicada']).count(),
            'transportes_atrasados': DocumentoTransporte.objects.filter(
                data_previsao_entrega__lt=agora, status__in=['preparando', 'em_transito']).count(),
        }
        return JsonResponse({'success': True, 'nc_hoje': nc_hoje, 'nd_hoje': nd_hoje,
                             'gt_hoje': gt_hoje, 'pendencias': pendencias})
    except Exception:
        logger.exception('Erro em estatisticas_rapidas_api')
        return JsonResponse({'success': False, 'message': 'Erro interno.'}, status=500)


# =====================================================================
# 20) NOTAS DE CRÉDITO (CBVs)
# =====================================================================

class NotaCreditoListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = 'emitir_notacredito'
    model = NotaCredito
    template_name = 'vendas/nota_credito_lista.html'
    context_object_name = 'notas_credito'
    paginate_by = 100

    def get_queryset(self):
        qs = NotaCredito.objects.all()

        if self.request.GET.get('status'):
            qs = qs.filter(status=self.request.GET['status'])
        if self.request.GET.get('motivo'):
            qs = qs.filter(motivo=self.request.GET['motivo'])
        cliente_nome = self.request.GET.get('cliente')
        if cliente_nome:
            qs = qs.filter(Q(cliente__nome_completo__icontains=cliente_nome) | Q(cliente__nif__icontains=cliente_nome))
        if self.request.GET.get('data_inicio'):
            qs = qs.filter(**_data_q(CAMPO_DATA_NC, 'date__gte', self.request.GET['data_inicio']))
        if self.request.GET.get('data_fim'):
            qs = qs.filter(**_data_q(CAMPO_DATA_NC, 'date__lte', self.request.GET['data_fim']))

        return qs.select_related('cliente', 'vendedor').order_by(f'-{CAMPO_DATA_NC}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = NotaCredito.objects.aggregate(
            total_creditos=Sum('total'),
            quantidade_total=Count('id'),
            pendentes_aprovacao=Count('id', filter=Q(requer_aprovacao=True, aprovada_por__isnull=True)),
            aplicadas=Count('id', filter=Q(status='aplicada')))
        context.update({
            'title': 'Notas de Crédito', 'stats': stats,
            'status': NotaCredito.STATUS_CHOICES, 'tipo_nota': NotaCredito.MOTIVO_CHOICES,
        })
        return context


class NotaCreditoDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = 'emitir_notacredito'
    model = NotaCredito
    template_name = 'vendas/nota_credito_detail.html'
    context_object_name = 'nota_credito'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nota = self.object
        pode, motivo = nota.pode_ser_aplicada()
        context.update({
            'title': f'Nota de Crédito {nota.numero_nota}',
            'itens': nota.itens.select_related('produto', 'servico'),
            'pode_aplicar': pode,
            'motivo_nao_aplicar': motivo,
        })
        return context


class NotaCreditoCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_notacredito'
    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'vendas/nota_credito_form.html'
    success_url = reverse_lazy('vendas:nota_credito_lista')

    def form_valid(self, form):
        form.instance.emitida_por = self.request.user
        form.instance.vendedor = getattr(self.request.user, 'funcionario', None)
        response = super().form_valid(form)
        messages.success(self.request, f'Nota de Crédito {form.instance.numero_nota} criada com sucesso!')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Nova Nota de Crédito',
                        'subtitle': 'Emitir documento de crédito para reduzir valor de fatura'})
        return context


class NotaCreditoUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_notacredito'
    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'vendas/nota_credito_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:nota_credito_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'emitida']:
            messages.error(self.request, 'Não é possível editar esta nota de crédito.')
            return redirect(self.get_success_url())
        messages.success(self.request, 'Nota de Crédito atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Nota de Crédito {self.object.numero_nota}',
                        'subtitle': 'Modificar dados da nota de crédito'})
        return context


class AplicarNotaCreditoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aplicar_notacredito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaCredito, pk=pk)
        try:
            with transaction.atomic():
                nota.aplicar_credito(request.user)
            messages.success(request, f'Nota de Crédito {nota.numero_nota} aplicada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao aplicar nota de crédito: {_msg_erro(e)}')
        except Exception:
            logger.exception('Erro ao aplicar NC %s', pk)
            messages.error(request, 'Erro inesperado ao aplicar a nota de crédito.')
        return redirect('vendas:nota_credito_detail', pk=pk)


class AprovarNotaCreditoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aprovar_notacredito'

    def post(self, request, pk):
        with transaction.atomic():
            nota = get_object_or_404(NotaCredito.objects.select_for_update(), pk=pk)
            if not nota.requer_aprovacao:
                messages.warning(request, 'Esta nota de crédito não requer aprovação.')
            elif nota.aprovada_por:
                messages.warning(request, 'Esta nota de crédito já foi aprovada.')
            else:
                nota.aprovada_por = request.user
                nota.data_aprovacao = timezone.now()
                nota.save()
                messages.success(request, f'Nota de Crédito {nota.numero_nota} aprovada com sucesso!')
        return redirect('vendas:nota_credito_detail', pk=pk)


# =====================================================================
# 21) NOTAS DE DÉBITO (CBVs)
# =====================================================================

class NotaDebitoListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    template_name = 'vendas/nota_debito_lista.html'
    context_object_name = 'notas_debito'
    paginate_by = 100

    def get_queryset(self):
        qs = NotaDebito.objects.all()

        if self.request.GET.get('status'):
            qs = qs.filter(status=self.request.GET['status'])
        if self.request.GET.get('motivo'):
            qs = qs.filter(motivo=self.request.GET['motivo'])
        cliente_nome = self.request.GET.get('cliente')
        if cliente_nome:
            qs = qs.filter(Q(cliente__nome_completo__icontains=cliente_nome) | Q(cliente__nif__icontains=cliente_nome))
        if self.request.GET.get('vencidas') == '1':
            qs = qs.filter(data_vencimento__lt=timezone.now().date(), status__in=['emitida', 'aplicada'])

        return qs.select_related('cliente', 'vendedor').order_by(f'-{CAMPO_DATA_ND}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hoje = timezone.now().date()
        stats = NotaDebito.objects.aggregate(
            total_debitos=Sum('total'),
            quantidade_total=Count('id'),
            vencidas=Count('id', filter=Q(data_vencimento__lt=hoje, status__in=['emitida', 'aplicada'])),
            aplicadas=Count('id', filter=Q(status='aplicada')))
        context.update({
            'title': 'Notas de Débito', 'stats': stats,
            'status': NotaDebito.STATUS_CHOICES, 'tipo_nota': NotaDebito.TIPO_NOTA_CHOICES,
        })
        return context


class NotaDebitoDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    template_name = 'vendas/nota_debito_detail.html'
    context_object_name = 'nota_debito'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        nota = self.object
        pode, motivo = nota.pode_ser_aplicada()
        hoje = timezone.now().date()
        context.update({
            'title': f'Nota de Débito {nota.numero_nota}',
            'itens': nota.itens.select_related('produto', 'servico'),
            'pode_aplicar': pode,
            'motivo_nao_aplicar': motivo,
            'esta_vencida': nota.data_vencimento < hoje,
            'dias_vencimento': (nota.data_vencimento - hoje).days,
        })
        return context


class NotaDebitoCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'vendas/nota_debito_form.html'
    success_url = reverse_lazy('vendas:nota_debito_lista')

    def form_valid(self, form):
        form.instance.emitida_por = self.request.user
        form.instance.vendedor = getattr(self.request.user, 'funcionario', None)
        response = super().form_valid(form)
        messages.success(self.request, f'Nota de Débito {form.instance.numero_nota} criada com sucesso!')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Nova Nota de Débito',
                        'subtitle': 'Emitir documento de débito para cobrança adicional'})
        return context


class NotaDebitoUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_notadebito'
    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'vendas/nota_debito_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:nota_debito_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status not in ['rascunho', 'emitida']:
            messages.error(self.request, 'Não é possível editar esta nota de débito.')
            return redirect(self.get_success_url())
        messages.success(self.request, 'Nota de Débito atualizada com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Nota de Débito {self.object.numero_nota}',
                        'subtitle': 'Modificar dados da nota de débito'})
        return context


class AplicarNotaDebitoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aplicar_notadebito'

    def post(self, request, pk):
        nota = get_object_or_404(NotaDebito, pk=pk)
        try:
            with transaction.atomic():
                nota.aplicar_debito(request.user)
            messages.success(request, f'Nota de Débito {nota.numero_nota} aplicada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao aplicar nota de débito: {_msg_erro(e)}')
        except Exception:
            logger.exception('Erro ao aplicar ND %s', pk)
            messages.error(request, 'Erro inesperado ao aplicar a nota de débito.')
        return redirect('vendas:nota_debito_detail', pk=pk)


class AprovarNotaDebitoView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'aprovar_notadebito'

    def post(self, request, pk):
        with transaction.atomic():
            nota = get_object_or_404(NotaDebito.objects.select_for_update(), pk=pk)
            if not nota.requer_aprovacao:
                messages.warning(request, 'Esta nota de débito não requer aprovação.')
            elif nota.aprovada_por:
                messages.warning(request, 'Esta nota de débito já foi aprovada.')
            else:
                nota.aprovada_por = request.user
                nota.data_aprovacao = timezone.now()
                nota.save()
                messages.success(request, f'Nota de Débito {nota.numero_nota} aprovada com sucesso!')
        return redirect('vendas:nota_debito_detail', pk=pk)


# =====================================================================
# 22) DOCUMENTOS DE TRANSPORTE (CBVs)
# =====================================================================

class DocumentoTransporteListView(PermissaoAcaoMixin, BaseVendaView, ListView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    template_name = 'vendas/documento_transporte_lista.html'
    context_object_name = 'documentos_transporte'
    paginate_by = 100

    def get_queryset(self):
        qs = DocumentoTransporte.objects.all()

        if self.request.GET.get('status'):
            qs = qs.filter(status=self.request.GET['status'])
        if self.request.GET.get('tipo_operacao'):
            qs = qs.filter(tipo_operacao=self.request.GET['tipo_operacao'])
        destinatario = self.request.GET.get('destinatario')
        if destinatario:
            qs = qs.filter(Q(destinatario_nome__icontains=destinatario) | Q(destinatario_nif__icontains=destinatario))
        if self.request.GET.get('atrasados') == '1':
            qs = qs.filter(data_previsao_entrega__lt=timezone.now(), status__in=['preparando', 'em_transito'])

        return qs.select_related('destinatario_cliente').order_by(f'-{CAMPO_DATA_GT}')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stats = DocumentoTransporte.objects.aggregate(
            total_documentos=Count('id'),
            em_transito=Count('id', filter=Q(status='em_transito')),
            entregues=Count('id', filter=Q(status='entregue')),
            atrasados=Count('id', filter=Q(data_previsao_entrega__lt=timezone.now(),
                                           status__in=['preparando', 'em_transito'])),
            peso_total=Sum('peso_total'),
            valor_total_transportes=Sum('valor_transporte'))
        context.update({
            'title': 'Documentos de Transporte', 'stats': stats,
            'status': DocumentoTransporte.STATUS_CHOICES,
            'tipo_operacao': DocumentoTransporte.TIPO_OPERACAO_CHOICES,
        })
        return context


class DocumentoTransporteDetailView(PermissaoAcaoMixin, BaseVendaView, DetailView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    template_name = 'vendas/documento_transporte_detail.html'
    context_object_name = 'documento'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        documento = self.object
        itens = documento.itens.all()

        tempo_transporte = None
        if documento.data_inicio_transporte:
            fim = documento.data_entrega_real or timezone.now()
            tempo_transporte = fim - documento.data_inicio_transporte

        context.update({
            'title': f'Documento de Transporte {documento.numero_documento}',
            'itens': itens,
            'total_peso_calculado': sum((i.peso_total for i in itens), Decimal('0.000')),
            'total_valor_calculado': sum((i.valor_total for i in itens), Decimal('0.00')),
            'pode_iniciar': documento.status == 'preparando',
            'pode_confirmar': documento.status == 'em_transito',
            'tempo_transporte': tempo_transporte,
        })
        return context


class DocumentoTransporteCreateView(PermissaoAcaoMixin, BaseVendaView, CreateView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    form_class = DocumentoTransporteForm
    template_name = 'vendas/documento_transporte_form.html'
    success_url = reverse_lazy('vendas:documento_transporte_lista')

    def form_valid(self, form):
        form.instance.emitido_por = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Documento de Transporte {form.instance.numero_documento} criado com sucesso!')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': 'Novo Documento de Transporte',
                        'subtitle': 'Criar guia de transporte para mercadorias'})
        return context


class DocumentoTransporteUpdateView(PermissaoAcaoMixin, BaseVendaView, UpdateView):
    acao_requerida = 'emitir_documentotransporte'
    model = DocumentoTransporte
    form_class = DocumentoTransporteForm
    template_name = 'vendas/documento_transporte_form.html'

    def get_success_url(self):
        return reverse_lazy('vendas:documento_transporte_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        if self.object.status != 'preparando':
            messages.error(self.request, 'Só é possível editar documentos em preparação.')
            return redirect(self.get_success_url())
        messages.success(self.request, 'Documento de Transporte atualizado com sucesso!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({'title': f'Editar Documento {self.object.numero_documento}',
                        'subtitle': 'Modificar dados do documento de transporte'})
        return context


class IniciarTransporteView(PermissaoAcaoMixin, BaseVendaView, View):
    acao_requerida = 'emitir_documentotransporte'

    def post(self, request, pk):
        documento = get_object_or_404(DocumentoTransporte, pk=pk)
        try:
            with transaction.atomic():
                documento.iniciar_transporte()
            messages.success(request, f'Transporte {documento.numero_documento} iniciado com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao iniciar transporte: {_msg_erro(e)}')
        except Exception:
            logger.exception('Erro ao iniciar transporte %s', pk)
            messages.error(request, 'Erro inesperado ao iniciar o transporte.')
        return redirect('vendas:documento_transporte_detail', pk=pk)


class ConfirmarEntregaView(PermissaoAcaoMixin, BaseVendaView, View):
    """Confirma a entrega de um DocumentoTransporte (GT). Ver ConfirmarEntregaDeliveryView p/ Venda."""
    acao_requerida = 'confirmar_entrega'

    def post(self, request, pk):
        documento = get_object_or_404(DocumentoTransporte, pk=pk)
        assinatura = request.POST.get('assinatura_destinatario', '')
        try:
            with transaction.atomic():
                documento.confirmar_entrega(request.user, assinatura)
            messages.success(request, f'Entrega do documento {documento.numero_documento} confirmada com sucesso!')
        except ValidationError as e:
            messages.error(request, f'Erro ao confirmar entrega: {_msg_erro(e)}')
        except Exception:
            logger.exception('Erro ao confirmar entrega do GT %s', pk)
            messages.error(request, 'Erro inesperado ao confirmar a entrega.')
        return redirect('vendas:documento_transporte_detail', pk=pk)


# =====================================================================
# 23) DASHBOARDS E RELATÓRIOS FISCAIS
# =====================================================================

class DocumentosFiscaisAnalyticsView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = 'emitir_documentotransporte'
    template_name = 'vendas/documentos_fiscais_analytics.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        periodo = _int_param(self.request, 'periodo', 30)
        data_inicio = timezone.now().date() - timedelta(days=periodo)
        agora = timezone.now()

        nc_qs = NotaCredito.objects.filter(**_data_q(CAMPO_DATA_NC, 'gte', data_inicio))
        nd_qs = NotaDebito.objects.filter(**_data_q(CAMPO_DATA_ND, 'gte', data_inicio))
        gt_qs = DocumentoTransporte.objects.filter(**_data_q(CAMPO_DATA_GT, 'gte', data_inicio))

        nc_stats = nc_qs.aggregate(
            total_nc=Count('id'), valor_total_nc=Sum('total'),
            aplicadas=Count('id', filter=Q(status='aplicada')),
            pendentes_aprovacao=Count('id', filter=Q(requer_aprovacao=True, aprovada_por__isnull=True)))
        nd_stats = nd_qs.aggregate(
            total_nd=Count('id'), valor_total_nd=Sum('total'), valor_pago_nd=Sum('valor_pago'),
            aplicadas=Count('id', filter=Q(status='aplicada')),
            vencidas=Count('id', filter=Q(data_vencimento__lt=agora.date())))
        gt_stats = gt_qs.aggregate(
            total_gt=Count('id'),
            em_transito=Count('id', filter=Q(status='em_transito')),
            entregues=Count('id', filter=Q(status='entregue')),
            atrasados=Count('id', filter=Q(data_previsao_entrega__lt=agora,
                                           status__in=['preparando', 'em_transito'])),
            peso_total=Sum('peso_total'), valor_transportes=Sum('valor_transporte'))

        context.update({
            'title': 'Analytics de Documentos Fiscais',
            'periodo': str(periodo),
            'data_inicio': data_inicio,
            'nc_stats': nc_stats, 'nd_stats': nd_stats, 'gt_stats': gt_stats,
            'nc_por_motivo': nc_qs.values('motivo').annotate(
                quantidade=Count('id'), valor_total=Sum('total')).order_by('-valor_total'),
            'gt_por_status': gt_qs.values('status').annotate(quantidade=Count('id')),
        })
        return context


class RelatorioNotasCreditoView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = 'aprovar_notacredito'
    template_name = 'vendas/relatorio_notas_credito.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        g = self.request.GET

        qs = NotaCredito.objects.all()
        if g.get('data_inicio'):
            qs = qs.filter(**_data_q(CAMPO_DATA_NC, 'date__gte', g['data_inicio']))
        if g.get('data_fim'):
            qs = qs.filter(**_data_q(CAMPO_DATA_NC, 'date__lte', g['data_fim']))
        if g.get('cliente_id'):
            qs = qs.filter(cliente_id=g['cliente_id'])
        if g.get('motivo'):
            qs = qs.filter(motivo=g['motivo'])

        context.update({
            'title': 'Relatório de Notas de Crédito',
            'notas_credito': qs.select_related('cliente')[:100],
            'totais': qs.aggregate(total_creditos=Sum('total'), quantidade=Count('id'), credito_medio=Avg('total')),
            'por_cliente': qs.values('cliente__nome_completo').annotate(
                total=Sum('total'), quantidade=Count('id')).order_by('-total')[:10],
            'por_motivo': qs.values('motivo').annotate(total=Sum('total'), quantidade=Count('id')).order_by('-total'),
            'clientes': Cliente.objects.filter(ativo=True),
            'motivo_choices': NotaCredito.MOTIVO_CHOICES,
        })
        return context


class RelatorioTransportesView(PermissaoAcaoMixin, BaseVendaView, TemplateView):
    acao_requerida = 'emitir_documentotransporte'
    template_name = 'vendas/relatorio_transportes.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        g = self.request.GET

        qs = DocumentoTransporte.objects.all()
        if g.get('data_inicio'):
            qs = qs.filter(**_data_q(CAMPO_DATA_GT, 'date__gte', g['data_inicio']))
        if g.get('data_fim'):
            qs = qs.filter(**_data_q(CAMPO_DATA_GT, 'date__lte', g['data_fim']))
        if g.get('status'):
            qs = qs.filter(status=g['status'])
        if g.get('provincia'):
            qs = qs.filter(destinatario_provincia=g['provincia'])

        no_prazo = atrasadas = 0
        for doc in qs.filter(status='entregue', data_entrega_real__isnull=False):
            if doc.data_entrega_real.date() <= doc.data_previsao_entrega.date():
                no_prazo += 1
            else:
                atrasadas += 1

        context.update({
            'title': 'Relatório de Transportes',
            'documentos': qs.select_related('destinatario_cliente')[:100],
            'totais': qs.aggregate(
                total_documentos=Count('id'), peso_total=Sum('peso_total'),
                valor_total=Sum('valor_transporte'), valor_medio=Avg('valor_transporte')),
            'entregas_no_prazo': no_prazo,
            'entregas_atrasadas': atrasadas,
            'por_provincia': qs.values('destinatario_provincia').annotate(
                total=Count('id'), peso=Sum('peso_total'), valor=Sum('valor_transporte')).order_by('-total'),
            'status_choices': DocumentoTransporte.STATUS_CHOICES,
        })
        return context


# =====================================================================
# 24) APIs REST (DRF)
# =====================================================================

class VendaViewSet(PermissaoAcaoMixin, mixins.CreateModelMixin, mixins.ListModelMixin,
                   mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Vendas/Documentos Fiscais: criar, listar e consultar.
    Antes era ModelViewSet (PUT/PATCH/DELETE de documentos fiscais emitidos);
    alterações passam por cancelamento/Nota de Crédito.
    """
    acao_requerida = ACAO_VENDER
    queryset = Venda.objects.all().order_by('-data_venda')
    serializer_class = VendaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        transaction.on_commit(_invalidar_cache_bi)

        headers = self.get_success_headers(serializer.data)
        return Response({
            'message': 'Venda registrada e assinada fiscalmente com sucesso.',
            'documento': serializer.data,
        }, status=status.HTTP_201_CREATED, headers=headers)


class VendaCreateAPIView(PermissaoAcaoMixin, generics.CreateAPIView):
    """Cria uma venda e gera o documento fiscal (HASH, ATCUD)."""
    acao_requerida = ACAO_VENDER
    serializer_class = VendaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                serializer.save()
                transaction.on_commit(verificar_margem_critica.delay)
                transaction.on_commit(_invalidar_cache_bi)

            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception:
            logger.exception('ALERTA DE FALHA ao criar venda via API')
            return Response(
                {'message': 'Erro de processamento interno. O administrador foi alertado.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RentabilidadeItemSerializer(serializers.Serializer):
    produto_id = serializers.IntegerField(read_only=True)
    produto_nome = serializers.CharField(read_only=True)
    total_vendido = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    custo_total = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    margem_bruta = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    percentual_margem_bruta = serializers.DecimalField(
        max_digits=7, decimal_places=2, read_only=True, coerce_to_string=False)


class RentabilidadeAPIView(PermissaoAcaoMixin, APIView):
    """Rentabilidade por produto, com cache por tenant (schema + versão) na cache 'B_I'."""
    acao_requerida = 'acessar_documentos'   # TODO: acção própria 'ver_rentabilidade' (expõe custos)
    CACHE_TTL = 60 * 60

    def get(self, request, *args, **kwargs):
        data_inicio = request.query_params.get('data_inicio', 'all')
        data_fim = request.query_params.get('data_fim', 'all')

        filtros = {'venda__status': 'finalizada'}
        try:
            if data_inicio != 'all':
                filtros['venda__data_venda__date__gte'] = _parse_data(data_inicio, 'data_inicio')
            if data_fim != 'all':
                filtros['venda__data_venda__date__lte'] = _parse_data(data_fim, 'data_fim')
        except ValidationError as e:
            return Response({'detail': _msg_erro(e)}, status=status.HTTP_400_BAD_REQUEST)

        cache = caches['B_I']
        schema = connection.schema_name
        versao = cache.get(f'bi_versao:{schema}', 1)
        cache_key = f'bi_rentabilidade:{schema}:v{versao}:{data_inicio}:{data_fim}'

        dados_cache = cache.get(cache_key)
        if dados_cache:
            return Response(dados_cache)

        linhas = (ItemVenda.objects.filter(**filtros, produto__isnull=False)
                  .values('produto_id', 'produto__nome_produto')
                  .annotate(total_vendido=Sum(F('quantidade') * F('preco_unitario')),
                            custo_total=Sum(F('quantidade') * F('produto__preco_custo')))
                  .order_by())

        resultados = []
        for r in linhas:
            vendido = r['total_vendido'] or Decimal('0')
            custo = r['custo_total'] or Decimal('0')
            margem = vendido - custo
            resultados.append({
                'produto_id': r['produto_id'],
                'produto_nome': r['produto__nome_produto'],
                'total_vendido': vendido,
                'custo_total': custo,
                'margem_bruta': margem,
                'percentual_margem_bruta': (margem * 100 / vendido).quantize(CENTIMO) if vendido else Decimal('0.00'),
            })
        resultados.sort(key=lambda x: x['margem_bruta'], reverse=True)

        response_data = {
            'relatorio_de_rentabilidade': RentabilidadeItemSerializer(resultados, many=True).data,
            'filtros_aplicados': {'data_inicio': data_inicio, 'data_fim': data_fim},
            'origem_dados': 'Base de Dados (Cache Miss)',
        }
        cache.set(cache_key, response_data, timeout=self.CACHE_TTL)
        return Response(response_data)


# =====================================================================
# URLS (apps/vendas/urls.py) — os names têm de bater com os templates
# =====================================================================
# path('proforma/nova/',                       views.nova_proforma,                      name='nova_proforma'),
# path('fatura-credito/nova/',                 views.nova_fatura_credito,                name='nova_fatura_credito'),
# path('api/proforma/finalizar/',              views.finalizar_proforma_api,             name='api_finalizar_proforma'),
# path('api/fatura-credito/finalizar/',        views.finalizar_fatura_credito_api,       name='api_finalizar_fatura_credito'),
# path('api/fatura-credito/<int:fatura_id>/gerar-documento/',
#                                              views.gerar_documento_fatura_credito_api, name='api_gerar_documento_fatura_credito'),
# path('api/proforma/<int:proforma_id>/converter/', views.converter_proforma_api,        name='api_converter_proforma'),
# path('api/proforma/<int:proforma_id>/status/',    views.atualizar_status_proforma_api, name='api_atualizar_status_proforma'),
# path('proforma/<int:proforma_id>/pdf/',      views.proforma_pdf_view,                  name='proforma_pdf'),
# path('api/fatura-credito/<int:fatura_id>/a4/', views.fatura_credito_pdf_view,          name='fatura_credito_pdf'),

