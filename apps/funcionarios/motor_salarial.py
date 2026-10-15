# apps/funcionarios/motor_salarial.py
"""Motor de cálculo salarial (Angola) — IRT Grupo A, INSS, rubricas configuráveis."""
import ast
import calendar
import operator
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from .models_recibo import (
    NATUREZAS_AUTORIZACAO, AuditoriaSalarial, ConfiguracaoRecibo, LinhaRecibo, ParametroFiscal,
    ReciboVencimento, Rubrica, RubricaFuncionario, TabelaIRT, q2,
)

ZERO = Decimal('0')
CEM = Decimal('100')


# ══════════════════════════════════════════════════════════════════════════════
# Avaliador seguro de fórmulas (sem eval)
# ══════════════════════════════════════════════════════════════════════════════
class FormulaInvalida(ValueError):
    pass


VARIAVEIS_FORMULA = ('SALARIO_BASE', 'BASE_ACUMULADA', 'ILIQUIDO', 'BASE_INSS', 'BASE_IRT',
                     'QTD', 'VALOR', 'HORAS_MES', 'DIAS_MES')
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_FUN = {'min': min, 'max': max, 'abs': abs}


def _avaliar(no, v):
    if isinstance(no, ast.Expression):
        return _avaliar(no.body, v)
    if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)) and not isinstance(no.value, bool):
        return Decimal(str(no.value))
    if isinstance(no, ast.Name):
        if no.id not in VARIAVEIS_FORMULA:
            raise FormulaInvalida(f"Variável desconhecida: {no.id}")
        return Decimal(v.get(no.id, 0))
    if isinstance(no, ast.UnaryOp) and isinstance(no.op, (ast.USub, ast.UAdd)):
        x = _avaliar(no.operand, v)
        return -x if isinstance(no.op, ast.USub) else x
    if isinstance(no, ast.BinOp) and type(no.op) in _BIN:
        a, b = _avaliar(no.left, v), _avaliar(no.right, v)
        if isinstance(no.op, ast.Div) and b == 0:
            raise FormulaInvalida("Divisão por zero")
        return _BIN[type(no.op)](a, b)
    if isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in _FUN \
            and not no.keywords and no.args:
        return Decimal(_FUN[no.func.id](*[_avaliar(a, v) for a in no.args]))
    raise FormulaInvalida("Expressão não permitida na fórmula")


def avaliar_formula(formula, variaveis):
    if len(formula) > 300:
        raise FormulaInvalida("Fórmula demasiado longa")
    try:
        arvore = ast.parse(formula.strip(), mode='eval')
    except SyntaxError:
        raise FormulaInvalida("Sintaxe inválida")
    return _avaliar(arvore, variaveis)


def validar_formula(formula):
    avaliar_formula(formula, {n: 1 for n in VARIAVEIS_FORMULA})


# ══════════════════════════════════════════════════════════════════════════════
# Resultado do cálculo
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class LinhaCalculada:
    tipo: str
    codigo: str
    designacao: str
    ordem: int
    natureza: str = ''
    rubrica_id: int = None
    quantidade: Decimal = None
    base_calculo: Decimal = ZERO
    taxa: Decimal = None
    valor_calculado: Decimal = ZERO
    valor_final: Decimal = ZERO
    sujeita_irt: bool = True
    sujeita_inss: bool = True
    integra_iliquido: bool = True
    participa_base: bool = True
    limite_isencao_irt: Decimal = None
    limite_isencao_inss: Decimal = None
    observacao: str = ''


@dataclass
class ResultadoCalculo:
    linhas: list = field(default_factory=list)
    salario_base: Decimal = ZERO
    total_remuneracoes_adicionais: Decimal = ZERO
    salario_iliquido: Decimal = ZERO
    base_inss: Decimal = ZERO
    base_irt: Decimal = ZERO
    materia_coletavel: Decimal = ZERO
    inss_trabalhador: Decimal = ZERO
    irt: Decimal = ZERO
    inss_patronal: Decimal = ZERO
    total_descontos: Decimal = ZERO
    salario_liquido: Decimal = ZERO
    custo_total_empresa: Decimal = ZERO
    avisos: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    parametros: dict = field(default_factory=dict)

    @property
    def ok(self):
        return not self.erros


SISTEMA = {
    'SALARIO_BASE': ('SAL_BASE', 'Salário-base', 'REMUNERACAO', 10),
    'INSS_TRABALHADOR': ('INSS_TRAB', 'Segurança Social (INSS) — trabalhador', 'DESCONTO', 900),
    'IRT': ('IRT', 'Imposto sobre o Rendimento do Trabalho (IRT)', 'DESCONTO', 910),
    'INSS_PATRONAL': ('INSS_PAT', 'Segurança Social (INSS) — entidade empregadora', 'ENCARGO', 950),
}
LIMITADAS = ('LIMITADO_ART248', 'OUTRO_AUTORIZADO')   # n.ºs 4–6 do art. 248.º


def _dec(v):
    if v in (None, ''):
        return None
    return Decimal(str(v))


# ══════════════════════════════════════════════════════════════════════════════
# Motor
# ══════════════════════════════════════════════════════════════════════════════
class MotorSalarial:
    VERSAO = '1.0'

    def __init__(self, mes, ano):
        self.mes, self.ano = mes, ano
        self.inicio = date(ano, mes, 1)
        self.data_ref = date(ano, mes, calendar.monthrange(ano, mes)[1])
        obter = ParametroFiscal.obter
        self.taxa_inss_trab = obter('INSS_TRABALHADOR', self.data_ref)
        self.taxa_inss_pat = obter('INSS_PATRONAL', self.data_ref)
        self.limite_248 = obter('LIMITE_ART248', self.data_ref, Decimal('25'))
        self.teto_inss = obter('TETO_BASE_INSS', self.data_ref, ZERO)
        self.tabela_irt = TabelaIRT.vigente('A', self.data_ref)
        todas = Rubrica.objects.filter(vigencia_inicio__lte=self.data_ref).filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=self.data_ref)
        ).prefetch_related('departamentos', 'cargos', 'funcionarios')
        self.sistema = {r.codigo_sistema: r for r in todas if r.codigo_sistema}
        self.rubricas = [r for r in todas if not r.codigo_sistema and r.ativa]

    def parametros(self):
        return {
            'versao_motor': self.VERSAO, 'data_referencia': self.data_ref.isoformat(),
            'inss_trabalhador_pct': str(self.taxa_inss_trab), 'inss_patronal_pct': str(self.taxa_inss_pat),
            'limite_art248_pct': str(self.limite_248), 'teto_base_inss': str(self.teto_inss),
            'tabela_irt': self.tabela_irt.snapshot() if self.tabela_irt else None,
        }

    # ── seleção de rubricas aplicáveis ──────────────────────────────────────
    def _aplicaveis(self, func, avisos):
        atribs = {a.rubrica_id: a for a in RubricaFuncionario.objects.filter(
            funcionario=func, vigencia_inicio__lte=self.data_ref
        ).filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=self.data_ref))}
        candidatas = []
        for r in self.rubricas:
            if not r.aplica_a(func):
                continue
            a = atribs.get(r.pk)
            if a and a.modo == 'EXCLUIR':
                if r.obrigatoria_por_lei:
                    avisos.append(f"A rubrica '{r.nome}' é legalmente obrigatória: a exclusão foi ignorada.")
                else:
                    continue
                a = None
            if r.natureza in NATUREZAS_AUTORIZACAO and not (a and a.autorizacao_referencia):
                avisos.append(f"Desconto '{r.nome}' ignorado: falta a referência da autorização escrita ou da decisão (art. 248.º LGT).")
                continue
            candidatas.append((r, a))

        finais, familias = [], defaultdict(list)
        for r, a in candidatas:
            if r.comportamento == 'SUBSTITUI' and r.chave_substituicao:
                familias[r.chave_substituicao].append((r, a))
            else:
                finais.append((r, a))
        for lista in familias.values():     # individual > selecionados > grupo > global; depois prioridade
            lista.sort(key=lambda x: (x[0].especificidade, x[0].prioridade), reverse=True)
            finais.append(lista[0])
        vistos, unicas = set(), []
        for r, a in sorted(finais, key=lambda x: (x[0].ordem_calculo, x[0].pk)):
            if r.codigo not in vistos:      # evita duplicação
                vistos.add(r.codigo)
                unicas.append((r, a))
        return unicas

    # ── cálculo de uma rubrica ──────────────────────────────────────────────
    @staticmethod
    def _base(nome, ctx):
        return ctx.get(nome, ZERO) if nome != 'NENHUMA' else ZERO

    def _calc_rubrica(self, rub, atr, lanc, ctx, avisos):
        lanc = lanc or {}
        qtd = _dec(lanc.get('quantidade'))
        if qtd is None and atr and atr.quantidade is not None:
            qtd = atr.quantidade
        valor_lanc = _dec(lanc.get('valor'))
        taxa = atr.percentagem if atr and atr.percentagem is not None else rub.percentagem
        unit_fixo = atr.valor_fixo if atr and atr.valor_fixo is not None else rub.valor_fixo
        base, calc, m = ZERO, ZERO, rub.metodo_calculo
        if m == 'VALOR_FIXO':
            calc = (valor_lanc if valor_lanc is not None else (unit_fixo or ZERO)) * (qtd if qtd is not None else 1)
        elif m == 'VARIAVEL':
            unit = valor_lanc if valor_lanc is not None else (unit_fixo or ZERO)
            calc = unit * (qtd if qtd is not None else 1)
        elif m == 'PERCENTUAL':
            base = self._base(rub.base_incidencia, ctx)
            calc = valor_lanc if valor_lanc is not None else base * (taxa or ZERO) / CEM
        elif m == 'FORMULA':
            variaveis = {k: ctx.get(k, ZERO) for k in VARIAVEIS_FORMULA}
            variaveis.update(QTD=qtd or ZERO, VALOR=valor_lanc or ZERO)
            try:
                calc = avaliar_formula(rub.formula, variaveis)
            except FormulaInvalida as exc:
                avisos.append(f"Rubrica {rub.codigo}: {exc}")
                return None
            base = ctx.get('SALARIO_BASE', ZERO) if 'SALARIO_BASE' in rub.formula else ZERO
        valor = q2(calc)
        if valor < 0:
            avisos.append(f"Rubrica {rub.codigo}: valor negativo ignorado.")
            valor = Decimal('0.00')
        if valor == 0 and not rub.mostrar_se_zero:
            return None
        return LinhaCalculada(
            tipo='DESCONTO' if rub.tipo == 'DESCONTO' else ('ENCARGO' if rub.tipo == 'ENCARGO_PATRONAL' else 'REMUNERACAO'),
            codigo=rub.codigo, designacao=rub.nome, ordem=rub.ordem_calculo, natureza=rub.natureza, rubrica_id=rub.pk,
            quantidade=qtd, base_calculo=q2(base), taxa=taxa if m == 'PERCENTUAL' else None,
            valor_calculado=valor, valor_final=valor, sujeita_irt=rub.sujeita_irt, sujeita_inss=rub.sujeita_inss,
            integra_iliquido=rub.integra_iliquido, participa_base=rub.participa_base_calculo,
            limite_isencao_irt=rub.limite_isencao_irt, limite_isencao_inss=rub.limite_isencao_inss)

    def _linha_sistema(self, chave, valor, base=ZERO, taxa=None, observacao=''):
        codigo, nome, tipo, ordem = SISTEMA[chave]
        row = self.sistema.get(chave)
        return LinhaCalculada(tipo=tipo, codigo=row.codigo if row else codigo, designacao=row.nome if row else nome,
                              ordem=row.ordem_calculo if row else ordem, natureza='LEGAL' if tipo != 'REMUNERACAO' else 'REMUNERATORIA',
                              base_calculo=q2(base), taxa=taxa, valor_calculado=q2(valor), valor_final=q2(valor),
                              observacao=observacao)

    # ── cálculo completo ────────────────────────────────────────────────────
    def calcular(self, func, lancamentos=None, ajuste_salario_base=None):
        lanc = lancamentos or {}
        res = ResultadoCalculo(parametros=self.parametros())
        avisos, erros = res.avisos, res.erros
        sal_base = q2(ajuste_salario_base if ajuste_salario_base is not None else func.salario_atual)
        res.salario_base = sal_base
        if self.taxa_inss_trab is None or self.taxa_inss_pat is None:
            erros.append("Taxas de INSS não configuradas para este período (Parâmetros fiscais).")
        if self.tabela_irt is None:
            erros.append(f"Não existe tabela de IRT vigente em {self.data_ref:%d/%m/%Y}.")
        if sal_base <= 0:
            erros.append("Salário-base inválido (zero ou negativo).")
        if erros:
            return res
        try:
            dados = func.dados_salariais
        except Exception:
            dados = None
        suj_inss = dados.sujeito_inss if dados else True
        suj_irt = dados.sujeito_irt if dados else True

        aplicaveis = self._aplicaveis(func, avisos)
        ctx = {'SALARIO_BASE': sal_base, 'DIAS_MES': Decimal('30'),
               'HORAS_MES': Decimal(func.carga_horaria_semanal or 44) * 52 / 12}

        # A) remunerações
        sb = self._linha_sistema('SALARIO_BASE', sal_base, base=sal_base)
        sb.natureza = 'REMUNERATORIA'
        rem = [sb]
        for rub, atr in aplicaveis:
            if rub.tipo != 'REMUNERACAO':
                continue
            ctx['BASE_ACUMULADA'] = sum((l.valor_final for l in rem if l.participa_base), ZERO)
            linha = self._calc_rubrica(rub, atr, lanc.get(rub.codigo), ctx, avisos)
            if linha:
                rem.append(linha)
        iliquido = sum((l.valor_final for l in rem if l.integra_iliquido), ZERO)
        res.total_remuneracoes_adicionais = sum((l.valor_final for l in rem if l.codigo != sb.codigo), ZERO)
        ctx['ILIQUIDO'] = iliquido

        # B) faltas (reduzem as bases fiscais)
        faltas = []
        for rub, atr in aplicaveis:
            if rub.tipo == 'DESCONTO' and rub.natureza == 'FALTA':
                linha = self._calc_rubrica(rub, atr, lanc.get(rub.codigo), ctx, avisos)
                if linha:
                    faltas.append(linha)
        total_faltas = sum((l.valor_final for l in faltas), ZERO)

        # C) bases, INSS e IRT
        def parte(l, lim):
            return l.valor_final - (min(l.valor_final, lim) if lim is not None else ZERO)
        base_inss = sum((parte(l, l.limite_isencao_inss) for l in rem if l.sujeita_inss), ZERO)
        base_irt = sum((parte(l, l.limite_isencao_irt) for l in rem if l.sujeita_irt), ZERO)
        base_inss = max(base_inss - total_faltas, ZERO) if suj_inss else ZERO
        base_irt = max(base_irt - total_faltas, ZERO)
        if self.teto_inss and self.teto_inss > 0:
            base_inss = min(base_inss, self.teto_inss)
        inss_t = q2(base_inss * self.taxa_inss_trab / CEM)
        inss_p = q2(base_inss * self.taxa_inss_pat / CEM)
        materia = max(q2(base_irt) - inss_t, ZERO) if suj_irt else ZERO
        irt, escala = self.tabela_irt.calcular(materia)
        ctx.update(BASE_INSS=base_inss, BASE_IRT=materia)

        obs_irt = (f"{escala.ordem}.º escalão: parcela fixa {escala.parcela_fixa:,.2f} + {escala.taxa}% sobre o excesso de "
                   f"{escala.excesso_de:,.2f}") if escala and irt > 0 else ("Isento" if suj_irt else "Não sujeito")
        l_inss_t = self._linha_sistema('INSS_TRABALHADOR', inss_t, base=base_inss, taxa=self.taxa_inss_trab)
        l_irt = self._linha_sistema('IRT', irt, base=materia, taxa=escala.taxa if escala else None, observacao=obs_irt)
        l_inss_p = self._linha_sistema('INSS_PATRONAL', inss_p, base=base_inss, taxa=self.taxa_inss_pat,
                                       observacao="Encargo da entidade empregadora — não descontado ao trabalhador")

        # D) outros descontos e encargos
        outros, encargos = [], [l_inss_p]
        for rub, atr in aplicaveis:
            if rub.tipo == 'DESCONTO' and rub.natureza != 'FALTA':
                linha = self._calc_rubrica(rub, atr, lanc.get(rub.codigo), ctx, avisos)
                if linha:
                    outros.append(linha)
            elif rub.tipo == 'ENCARGO_PATRONAL':
                linha = self._calc_rubrica(rub, atr, lanc.get(rub.codigo), ctx, avisos)
                if linha:
                    encargos.append(linha)

        # E) limite do art. 248.º (n.ºs 4 a 6) sobre o salário líquido
        limitadas = [l for l in outros if l.natureza in LIMITADAS]
        if limitadas:
            nao_limitados = inss_t + irt + total_faltas + sum((l.valor_final for l in outros if l.natureza not in LIMITADAS), ZERO)
            cap = q2(max(iliquido - nao_limitados, ZERO) * self.limite_248 / CEM)
            total_lim = sum((l.valor_final for l in limitadas), ZERO)
            if total_lim > cap:
                acumulado = ZERO
                for i, l in enumerate(limitadas):
                    novo = q2(l.valor_final * cap / total_lim) if i < len(limitadas) - 1 else q2(cap - acumulado)
                    novo = max(novo, Decimal('0.00'))
                    l.observacao = (l.observacao + ' ' if l.observacao else '') + 'Limitado nos termos do art. 248.º da LGT.'
                    l.valor_final, acumulado = novo, acumulado + novo
                avisos.append(f"Descontos limitados a {self.limite_248}% do salário líquido (art. 248.º LGT): "
                              f"pedido {total_lim:,.2f}, aplicado {cap:,.2f}.")

        descontos = faltas + [l_inss_t, l_irt] + outros
        total_desc = sum((l.valor_final for l in descontos), ZERO)
        liquido = iliquido - total_desc
        if liquido < 0:
            erros.append("O total de descontos excede o salário ilíquido.")

        res.linhas = sorted(rem, key=lambda l: l.ordem) + sorted(descontos, key=lambda l: l.ordem) + sorted(encargos, key=lambda l: l.ordem)
        res.salario_iliquido, res.base_inss, res.base_irt = q2(iliquido), q2(base_inss), q2(base_irt)
        res.materia_coletavel, res.inss_trabalhador, res.irt, res.inss_patronal = q2(materia), inss_t, irt, inss_p
        res.total_descontos, res.salario_liquido = q2(total_desc), q2(liquido)
        res.custo_total_empresa = q2(iliquido + sum((l.valor_final for l in encargos), ZERO))
        return res


# ══════════════════════════════════════════════════════════════════════════════
# Serviços: persistência de recibos
# ══════════════════════════════════════════════════════════════════════════════
def _snapshot_empresa():
    t = connection.tenant
    cfg = ConfiguracaoRecibo.get_solo()
    endereco = ', '.join(x for x in [getattr(t, 'endereco', ''), getattr(t, 'numero', ''),
                                      getattr(t, 'bairro', ''), getattr(t, 'cidade', '')] if x)
    contactos = ' | '.join(x for x in [f"Tel: {t.telefone}" if getattr(t, 'telefone', '') else '', getattr(t, 'email', '')] if x)
    return dict(empresa_nome=getattr(t, 'nome', ''), empresa_nif=getattr(t, 'nif', ''), empresa_endereco=endereco,
                empresa_contactos=contactos, empresa_inss=cfg.numero_inss_empregador)


def _snapshot_funcionario(f):
    try:
        d = f.dados_salariais
    except Exception:
        d = None
    iban = (d.iban if d and d.iban else f"{f.banco} {f.conta_corrente}".strip())
    return dict(func_nome=f.nome_completo, func_matricula=f.matricula, func_nif=(d.nif if d else ''),
                func_inss=(d.numero_inss if d else ''), func_cargo=f.cargo.nome if f.cargo_id else '',
                func_categoria=(d.categoria_profissional if d and d.categoria_profissional
                                else (f.cargo.get_categoria_display() if f.cargo_id else '')),
                func_departamento=f.departamento.nome, func_unidade=(d.unidade if d else ''),
                func_tipo_contrato=f.get_tipo_contrato_display(), func_data_admissao=f.data_admissao, func_iban=iban)


def preencher_recibo(recibo, func, res):
    for k, v in {**_snapshot_empresa(), **_snapshot_funcionario(func)}.items():
        setattr(recibo, k, v)
    for c in ReciboVencimento.CAMPOS_VALORES:
        setattr(recibo, c, getattr(res, c, ZERO))
    recibo.parametros_calculo = res.parametros
    recibo.avisos, recibo.erros = res.avisos, res.erros
    recibo.nome_responsavel = recibo.nome_responsavel or ''


def pre_visualizar(func, mes, ano, lancamentos=None, ajuste=None):
    res = MotorSalarial(mes, ano).calcular(func, lancamentos, ajuste)
    recibo = ReciboVencimento(funcionario=func, mes=mes, ano=ano, estado='RASCUNHO', moeda='AOA',
                              numero='PRÉ-VISUALIZAÇÃO', data_emissao=timezone.localdate())
    preencher_recibo(recibo, func, res)
    return recibo, res


@transaction.atomic
def processar_recibo(processamento, func, usuario, lancamentos=None, ajuste='__manter__', motor=None):
    recibo = (ReciboVencimento.objects.select_for_update()
              .filter(processamento=processamento, funcionario=func, estado__in=('RASCUNHO', 'CALCULADO')).first())
    if recibo is None:
        if ReciboVencimento.objects.filter(processamento=processamento, funcionario=func, estado__in=('EMITIDO', 'PAGO')).exists():
            raise ValidationError(f"{func.nome_completo} já tem recibo emitido neste processamento. Use a retificação.")
        recibo = ReciboVencimento(processamento=processamento, funcionario=func, mes=processamento.mes,
                                  ano=processamento.ano, moeda=processamento.moeda)
    lanc = lancamentos if lancamentos is not None else (recibo.lancamentos or {})
    aj = recibo.ajuste_salario_base if ajuste == '__manter__' else ajuste
    motor = motor or MotorSalarial(processamento.mes, processamento.ano)
    res = motor.calcular(func, lanc, aj)
    preencher_recibo(recibo, func, res)
    recibo.lancamentos, recibo.ajuste_salario_base = lanc, aj
    recibo.estado = 'CALCULADO' if res.ok else 'RASCUNHO'
    recibo.calculado_por, recibo.calculado_em = usuario, timezone.now()
    recibo.save()
    recibo.linhas.all().delete()
    LinhaRecibo.objects.bulk_create([
        LinhaRecibo(recibo=recibo, rubrica_id=l.rubrica_id, tipo=l.tipo, codigo=l.codigo, designacao=l.designacao,
                    natureza=l.natureza, ordem=l.ordem, quantidade=l.quantidade, base_calculo=l.base_calculo,
                    taxa=l.taxa, valor_calculado=l.valor_calculado, valor_final=l.valor_final,
                    sujeita_irt=l.sujeita_irt, sujeita_inss=l.sujeita_inss, integra_iliquido=l.integra_iliquido,
                    observacao=l.observacao[:250]) for l in res.linhas])
    AuditoriaSalarial.registar(usuario, 'RECIBO_CALCULADO', recibo,
                               depois={'liquido': str(recibo.salario_liquido), 'erros': res.erros, 'avisos': res.avisos})
    return recibo


def recalcular_recibo(recibo, usuario):
    return processar_recibo(recibo.processamento, recibo.funcionario, usuario)


def processar_todos(processamento, usuario):
    """Gera/recalcula os recibos de todos os funcionários activos no período."""
    from .models import Funcionario
    motor = MotorSalarial(processamento.mes, processamento.ano)
    qs = (Funcionario.objects.filter(ativo=True, data_admissao__lte=motor.data_ref)
          .filter(Q(data_demissao__isnull=True) | Q(data_demissao__gte=motor.inicio))
          .select_related('cargo', 'departamento', 'dados_salariais'))
    ok, com_erros, falhas = 0, 0, []
    for f in qs:
        try:
            r = processar_recibo(processamento, f, usuario, motor=motor)
            ok += 1
            if r.erros:
                com_erros += 1
                falhas.append(f"{f.nome_completo}: {'; '.join(r.erros)}")
        except ValidationError as exc:
            falhas.append(f"{f.nome_completo}: {'; '.join(exc.messages)}")
    if processamento.estado == 'RASCUNHO' and ok:
        processamento.estado = 'CALCULADO'
        processamento.save(update_fields=['estado', 'updated_at'])
    return {'processados': ok, 'com_erros': com_erros, 'falhas': falhas}
