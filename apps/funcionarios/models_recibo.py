# apps/funcionarios/models_recibo.py
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel



"""
Recibo de Vencimento — modelos (isolamento físico django-tenants: sem FK para Empresa).
"""

__all__ = [
    'q2', 'NATUREZAS_AUTORIZACAO', 'ParametroFiscal', 'TabelaIRT', 'EscalaIRT', 'ConfiguracaoRecibo',
    'DadosSalariaisFuncionario', 'Rubrica', 'RubricaFuncionario', 'ProcessamentoSalarial',
    'ReciboVencimento', 'LinhaRecibo', 'AuditoriaSalarial',
]

CENT = Decimal('0.01')
USER = settings.AUTH_USER_MODEL
# Descontos que exigem autorização escrita do trabalhador ou decisão/acordo (art. 248.º LGT)
NATUREZAS_AUTORIZACAO = ('SINDICAL', 'LIMITADO_ART248', 'OUTRO_AUTORIZADO', 'JUDICIAL')


def q2(valor):
    return Decimal(str(valor or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


# ══════════════════════════════════════════════════════════════════════════════
# PARÂMETROS FISCAIS COM VIGÊNCIA
# ══════════════════════════════════════════════════════════════════════════════
class ParametroFiscal(TimeStampedModel):
    CHAVES = [
        ('INSS_TRABALHADOR', 'Taxa INSS — trabalhador (%)'),
        ('INSS_PATRONAL', 'Taxa INSS — entidade empregadora (%)'),
        ('LIMITE_ART248', 'Limite dos descontos do art. 248.º n.ºs 4 a 6 (% do salário líquido)'),
        ('TETO_BASE_INSS', 'Teto da base de incidência INSS (Kz; 0 = sem teto)'),
    ]
    chave = models.CharField(max_length=30, choices=CHAVES)
    valor = models.DecimalField(max_digits=14, decimal_places=4)
    vigencia_inicio = models.DateField()
    vigencia_fim = models.DateField(null=True, blank=True)
    diploma = models.CharField("Diploma legal", max_length=200, blank=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Parâmetro fiscal"
        verbose_name_plural = "Parâmetros fiscais"
        ordering = ['chave', '-vigencia_inicio']

    def __str__(self):
        return f"{self.get_chave_display()} = {self.valor} (desde {self.vigencia_inicio:%d/%m/%Y})"

    def clean(self):
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            raise ValidationError({'vigencia_fim': "A vigência final não pode ser anterior à inicial."})
        outros = type(self).objects.filter(chave=self.chave).exclude(pk=self.pk).filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=self.vigencia_inicio))
        if self.vigencia_fim:
            outros = outros.filter(vigencia_inicio__lte=self.vigencia_fim)
        if outros.exists():
            raise ValidationError("Já existe um valor deste parâmetro com vigência sobreposta.")

    @classmethod
    def obter(cls, chave, data, default=None):
        p = (cls.objects.filter(chave=chave, vigencia_inicio__lte=data)
             .filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=data))
             .order_by('-vigencia_inicio').first())
        return p.valor if p else default


class TabelaIRT(TimeStampedModel):
    """Tabela de retenção na fonte do IRT, com vigência (nunca alterar retroactivamente: criar nova)."""
    GRUPOS = [('A', 'Grupo A — trabalho por conta de outrem')]
    nome = models.CharField(max_length=120)
    grupo = models.CharField(max_length=1, choices=GRUPOS, default='A')
    diploma = models.CharField("Diploma legal", max_length=200, blank=True)
    vigencia_inicio = models.DateField()
    vigencia_fim = models.DateField(null=True, blank=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tabela de IRT"
        verbose_name_plural = "Tabelas de IRT"
        ordering = ['-vigencia_inicio']

    def __str__(self):
        return f"{self.nome} (desde {self.vigencia_inicio:%d/%m/%Y})"

    def clean(self):
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            raise ValidationError({'vigencia_fim': "A vigência final não pode ser anterior à inicial."})
        outros = type(self).objects.filter(grupo=self.grupo, ativa=True).exclude(pk=self.pk).filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=self.vigencia_inicio))
        if self.vigencia_fim:
            outros = outros.filter(vigencia_inicio__lte=self.vigencia_fim)
        if self.ativa and outros.exists():
            raise ValidationError("Já existe uma tabela activa com vigência sobreposta.")

    @classmethod
    def vigente(cls, grupo, data):
        return (cls.objects.filter(grupo=grupo, ativa=True, vigencia_inicio__lte=data)
                .filter(Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=data))
                .order_by('-vigencia_inicio').first())

    def calcular(self, materia):
        """IRT = parcela fixa + (matéria colectável − excesso de) × taxa. Devolve (imposto, escalão)."""
        materia = q2(materia)
        if materia <= 0:
            return Decimal('0.00'), None
        for e in self.escalas.all():
            if materia > e.limite_inferior and (e.limite_superior is None or materia <= e.limite_superior):
                imposto = e.parcela_fixa + (materia - e.excesso_de) * e.taxa / Decimal('100')
                return q2(max(imposto, Decimal('0'))), e
        return Decimal('0.00'), None

    def snapshot(self):
        return {'id': self.pk, 'nome': self.nome, 'diploma': self.diploma,
                'vigencia_inicio': self.vigencia_inicio.isoformat(),
                'escalas': [[e.ordem, str(e.limite_inferior), str(e.limite_superior) if e.limite_superior is not None else None,
                             str(e.parcela_fixa), str(e.taxa), str(e.excesso_de)] for e in self.escalas.all()]}


class EscalaIRT(models.Model):
    tabela = models.ForeignKey(TabelaIRT, on_delete=models.CASCADE, related_name='escalas')
    ordem = models.PositiveSmallIntegerField()
    limite_inferior = models.DecimalField("Acima de", max_digits=14, decimal_places=2)
    limite_superior = models.DecimalField("Até", max_digits=14, decimal_places=2, null=True, blank=True)
    parcela_fixa = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxa = models.DecimalField("Taxa (%)", max_digits=6, decimal_places=2, default=0)
    excesso_de = models.DecimalField("Excesso de", max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['ordem']
        unique_together = [('tabela', 'ordem')]

    def __str__(self):
        return f"{self.ordem}.º escalão"


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO E DADOS SALARIAIS
# ══════════════════════════════════════════════════════════════════════════════
class ConfiguracaoRecibo(TimeStampedModel):
    """Singleton por tenant (pk=1). Use sempre ConfiguracaoRecibo.get_solo()."""
    numero_inss_empregador = models.CharField("N.º de inscrição da entidade empregadora no INSS", max_length=30, blank=True)
    prefixo_numeracao = models.CharField(max_length=6, default='RV')
    exigir_assinatura_trabalhador = models.BooleanField(default=True)
    mostrar_assinatura_contabilista = models.BooleanField("Mostrar área de assinatura do contabilista", default=False)
    contabilista_nome = models.CharField(max_length=150, blank=True)
    contabilista_numero_ordem = models.CharField("N.º de inscrição profissional", max_length=40, blank=True)
    mostrar_iban_completo = models.BooleanField("Mostrar IBAN completo no PDF", default=False)
    texto_rodape = models.CharField(max_length=250, blank=True)

    class Meta:
        verbose_name = "Configuração do Recibo de Vencimento"
        verbose_name_plural = "Configuração do Recibo de Vencimento"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("A configuração não pode ser apagada, apenas editada.")

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class DadosSalariaisFuncionario(TimeStampedModel):
    """Dados fiscais/bancários que não existem no cadastro base do funcionário."""
    funcionario = models.OneToOneField('funcionarios.Funcionario', on_delete=models.CASCADE, related_name='dados_salariais')
    nif = models.CharField("NIF", max_length=20, blank=True)
    numero_inss = models.CharField("N.º de beneficiário do INSS", max_length=30, blank=True)
    iban = models.CharField("IBAN", max_length=34, blank=True)
    unidade = models.CharField("Unidade / estabelecimento", max_length=100, blank=True)
    categoria_profissional = models.CharField(max_length=100, blank=True,
                                               help_text="Se vazio, usa a categoria do cargo.")
    sujeito_inss = models.BooleanField(default=True)
    sujeito_irt = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Dados salariais do funcionário"
        verbose_name_plural = "Dados salariais dos funcionários"

    def __str__(self):
        return f"Dados salariais — {self.funcionario}"

    def clean(self):
        if self.iban:
            self.iban = re.sub(r'\s+', '', self.iban).upper()
            if not re.fullmatch(r'AO\d{23}', self.iban):
                raise ValidationError({'iban': "IBAN angolano inválido (AO + 23 dígitos)."})


# ══════════════════════════════════════════════════════════════════════════════
# RUBRICAS CONFIGURÁVEIS
# ══════════════════════════════════════════════════════════════════════════════
class Rubrica(TimeStampedModel):
    TIPOS = [('REMUNERACAO', 'Remuneração / abono'), ('DESCONTO', 'Desconto / dedução'),
             ('ENCARGO_PATRONAL', 'Encargo da entidade empregadora')]
    NATUREZAS = [
        ('REMUNERATORIA', 'Remuneratória'),
        ('LEGAL', 'Desconto legal (Estado / segurança social)'),
        ('SINDICAL', 'Quotização sindical (a pedido escrito)'),
        ('LIMITADO_ART248', 'Adiantamento / empréstimo / fornecimento a crédito (art. 248.º, n.ºs 4–6)'),
        ('JUDICIAL', 'Decisão judicial / acordo homologado'),
        ('FALTA', 'Desconto por faltas (tempo de falta)'),
        ('OUTRO_AUTORIZADO', 'Outro desconto autorizado por escrito'),
        ('ENCARGO', 'Encargo patronal'),
    ]
    NATUREZAS_POR_TIPO = {
        'REMUNERACAO': {'REMUNERATORIA'},
        'DESCONTO': {'LEGAL', 'SINDICAL', 'LIMITADO_ART248', 'JUDICIAL', 'FALTA', 'OUTRO_AUTORIZADO'},
        'ENCARGO_PATRONAL': {'ENCARGO'},
    }
    METODOS = [('PERCENTUAL', 'Percentagem'), ('VALOR_FIXO', 'Valor fixo'), ('FORMULA', 'Fórmula'),
               ('TABELA_IRT', 'Tabela fiscal (IRT)'), ('VARIAVEL', 'Variável (lançado em cada mês)')]
    BASES = [('SALARIO_BASE', 'Salário-base'), ('BASE_ACUMULADA', 'Remunerações anteriores (que participam na base)'),
             ('ILIQUIDO', 'Salário ilíquido'), ('BASE_INSS', 'Base de incidência INSS'),
             ('BASE_IRT', 'Matéria colectável IRT'), ('NENHUMA', 'Sem base')]
    AMBITOS = [('GLOBAL', 'Global — todos os funcionários'), ('GRUPO', 'Grupo (departamento, cargo, categoria, contrato)'),
               ('SELECIONADOS', 'Funcionários selecionados'), ('INDIVIDUAL', 'Individual')]
    SISTEMA = [('SALARIO_BASE', 'Salário-base'), ('INSS_TRABALHADOR', 'INSS trabalhador'), ('IRT', 'IRT'),
               ('INSS_PATRONAL', 'INSS patronal')]

    codigo = models.CharField(max_length=20, unique=True)
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    natureza = models.CharField(max_length=20, choices=NATUREZAS, default='REMUNERATORIA')
    descricao = models.TextField(blank=True)
    codigo_sistema = models.CharField(max_length=20, choices=SISTEMA, null=True, blank=True, unique=True, editable=False)

    metodo_calculo = models.CharField(max_length=12, choices=METODOS, default='VARIAVEL')
    percentagem = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True,
                                       validators=[MinValueValidator(0), MaxValueValidator(100)])
    valor_fixo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    formula = models.CharField(max_length=300, blank=True,
                               help_text="Variáveis: SALARIO_BASE, BASE_ACUMULADA, ILIQUIDO, BASE_INSS, BASE_IRT, QTD, VALOR, HORAS_MES, DIAS_MES. "
                                         "Operadores + - * / ( ) e funções min, max, abs.")
    base_incidencia = models.CharField(max_length=15, choices=BASES, default='SALARIO_BASE')

    integra_iliquido = models.BooleanField("Integra o salário ilíquido", default=True)
    sujeita_irt = models.BooleanField("Sujeita a IRT", default=True)
    sujeita_inss = models.BooleanField("Sujeita a INSS", default=True)
    participa_base_calculo = models.BooleanField("Participa na base de cálculo de outras rubricas", default=True)
    limite_isencao_irt = models.DecimalField("Parte isenta de IRT (Kz)", max_digits=14, decimal_places=2, null=True, blank=True)
    limite_isencao_inss = models.DecimalField("Parte isenta de INSS (Kz)", max_digits=14, decimal_places=2, null=True, blank=True)
    mostrar_se_zero = models.BooleanField(default=False)

    ordem_calculo = models.PositiveIntegerField(default=100)
    ambito = models.CharField(max_length=14, choices=AMBITOS, default='GLOBAL')
    departamentos = models.ManyToManyField('funcionarios.Departamento', blank=True, related_name='rubricas_recibo')
    cargos = models.ManyToManyField('funcionarios.Cargo', blank=True, related_name='rubricas_recibo')
    categorias = models.JSONField("Categorias de cargo", default=list, blank=True)
    tipos_contrato = models.JSONField("Tipos de contrato", default=list, blank=True)
    funcionarios = models.ManyToManyField('funcionarios.Funcionario', blank=True, related_name='rubricas_recibo')

    comportamento = models.CharField(max_length=9, default='ACUMULA',
                                      choices=[('ACUMULA', 'Acumula com outras rubricas'),
                                               ('SUBSTITUI', 'Substitui outra rubrica da mesma família')])
    chave_substituicao = models.CharField("Família (para substituição)", max_length=30, blank=True)
    prioridade = models.PositiveSmallIntegerField(default=0)

    obrigatoria_por_lei = models.BooleanField(default=False)
    ativa = models.BooleanField(default=True)
    vigencia_inicio = models.DateField(default=date.today)
    vigencia_fim = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Rubrica"
        verbose_name_plural = "Rubricas"
        ordering = ['tipo', 'ordem_calculo', 'codigo']

    def __str__(self):
        return f"{self.codigo} — {self.nome}"

    @property
    def eh_sistema(self):
        return bool(self.codigo_sistema)

    @property
    def especificidade(self):
        return {'GLOBAL': 0, 'GRUPO': 1, 'SELECIONADOS': 2, 'INDIVIDUAL': 3}[self.ambito]

    @property
    def exige_autorizacao(self):
        return self.natureza in NATUREZAS_AUTORIZACAO

    def vigente_em(self, d):
        return self.vigencia_inicio <= d and (self.vigencia_fim is None or self.vigencia_fim >= d)

    def aplica_a(self, f):
        if self.ambito == 'GLOBAL':
            return True
        if self.ambito == 'GRUPO':
            testes = []
            deps = {d.pk for d in self.departamentos.all()}
            if deps:
                testes.append(f.departamento_id in deps)
            cargos = {c.pk for c in self.cargos.all()}
            if cargos:
                testes.append(f.cargo_id in cargos)
            if self.categorias:
                testes.append(bool(f.cargo_id) and f.cargo.categoria in self.categorias)
            if self.tipos_contrato:
                testes.append(f.tipo_contrato in self.tipos_contrato)
            return bool(testes) and all(testes)
        return f.pk in {x.pk for x in self.funcionarios.all()}

    def clean(self):
        if self.codigo_sistema:
            return
        erros = {}
        if self.natureza not in self.NATUREZAS_POR_TIPO.get(self.tipo, set()):
            erros['natureza'] = "Natureza incompatível com o tipo de rubrica (descontos fora do art. 248.º LGT não são permitidos)."
        if self.exige_autorizacao and self.ambito == 'GLOBAL':
            erros['ambito'] = "Este desconto exige autorização individual: não pode ser global."
        if self.metodo_calculo == 'TABELA_IRT':
            erros['metodo_calculo'] = "A tabela de IRT só é usada pela rubrica de sistema."
        if self.metodo_calculo == 'PERCENTUAL' and self.percentagem is None:
            erros['percentagem'] = "Indique a percentagem."
        if self.metodo_calculo == 'VALOR_FIXO' and self.valor_fixo is None:
            erros['valor_fixo'] = "Indique o valor fixo."
        if self.metodo_calculo == 'FORMULA':
            if not self.formula:
                erros['formula'] = "Indique a fórmula."
            else:
                from .motor_salarial import FormulaInvalida, validar_formula
                try:
                    validar_formula(self.formula)
                except FormulaInvalida as exc:
                    erros['formula'] = str(exc)
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            erros['vigencia_fim'] = "A vigência final não pode ser anterior à inicial."
        if self.obrigatoria_por_lei and not self.ativa:
            erros['ativa'] = "Uma rubrica legalmente obrigatória não pode ser desactivada."
        if self.comportamento == 'SUBSTITUI' and not self.chave_substituicao:
            erros['chave_substituicao'] = "Indique a família para a regra de substituição."
        if erros:
            raise ValidationError(erros)

    def delete(self, *args, **kwargs):
        raise ValidationError("Rubricas não são apagadas (preservam o histórico): desactive-a.")


class RubricaFuncionario(TimeStampedModel):
    """Atribuição individual: valores próprios, exclusão ou referência de autorização."""
    MODOS = [('SUBSTITUIR', 'Valores individuais / autorização'), ('EXCLUIR', 'Excluir este funcionário da rubrica')]
    rubrica = models.ForeignKey(Rubrica, on_delete=models.CASCADE, related_name='atribuicoes')
    funcionario = models.ForeignKey('funcionarios.Funcionario', on_delete=models.CASCADE, related_name='atribuicoes_rubrica')
    modo = models.CharField(max_length=10, choices=MODOS, default='SUBSTITUIR')
    valor_fixo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    percentagem = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    vigencia_inicio = models.DateField(default=date.today)
    vigencia_fim = models.DateField(null=True, blank=True)
    autorizacao_referencia = models.CharField("Referência da autorização / decisão", max_length=150, blank=True)
    observacoes = models.TextField(blank=True)
    criado_por = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = "Atribuição individual de rubrica"
        verbose_name_plural = "Atribuições individuais de rubricas"
        ordering = ['rubrica', 'funcionario']

    def __str__(self):
        return f"{self.rubrica.codigo} → {self.funcionario}"

    def clean(self):
        r = getattr(self, 'rubrica', None)
        if r is None:
            return
        erros = {}
        if self.modo == 'EXCLUIR' and r.obrigatoria_por_lei:
            erros['modo'] = "Não é possível excluir um funcionário de uma rubrica legalmente obrigatória."
        if self.modo == 'SUBSTITUIR' and r.exige_autorizacao and not self.autorizacao_referencia:
            erros['autorizacao_referencia'] = "Indique a referência da autorização escrita ou da decisão."
        if self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            erros['vigencia_fim'] = "A vigência final não pode ser anterior à inicial."
        if erros:
            raise ValidationError(erros)


# ══════════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO SALARIAL E RECIBO
# ══════════════════════════════════════════════════════════════════════════════
class ProcessamentoSalarial(TimeStampedModel):
    ESTADOS = [('RASCUNHO', 'Em elaboração'), ('CALCULADO', 'Calculado'), ('FECHADO', 'Fechado (recibos emitidos)'),
               ('PAGO', 'Pago'), ('CANCELADO', 'Cancelado')]
    MESES = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro',
             'Outubro', 'Novembro', 'Dezembro']
    mes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    ano = models.PositiveSmallIntegerField(validators=[MinValueValidator(2020), MaxValueValidator(2100)])
    descricao = models.CharField(max_length=150, blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default='RASCUNHO')
    moeda = models.CharField(max_length=3, default='AOA')
    data_pagamento = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_por = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fechado_por = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    fechado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Processamento salarial"
        verbose_name_plural = "Processamentos salariais"
        unique_together = [('mes', 'ano')]
        ordering = ['-ano', '-mes']

    def __str__(self):
        return f"Processamento {self.mes:02d}/{self.ano}"

    @property
    def mes_nome(self):
        return self.MESES[self.mes]

    @property
    def aberto(self):
        return self.estado in ('RASCUNHO', 'CALCULADO')

    def totais(self):
        qs = self.recibos.exclude(estado__in=('RETIFICADO', 'ANULADO'))
        agg = qs.aggregate(n=models.Count('id'), iliq=models.Sum('salario_iliquido'), desc=models.Sum('total_descontos'),
                           liq=models.Sum('salario_liquido'), pat=models.Sum('inss_patronal'))
        return {k: (v or 0) for k, v in agg.items()}


class ReciboVencimento(TimeStampedModel):
    ESTADOS = [('RASCUNHO', 'Rascunho / com erros'), ('CALCULADO', 'Calculado'), ('EMITIDO', 'Emitido'),
               ('PAGO', 'Pago'), ('RETIFICADO', 'Retificado'), ('ANULADO', 'Anulado')]
    FECHADOS = ('EMITIDO', 'PAGO', 'RETIFICADO', 'ANULADO')
    ATIVOS = ('RASCUNHO', 'CALCULADO', 'EMITIDO', 'PAGO')
    CAMPOS_VALORES = ('salario_base', 'total_remuneracoes_adicionais', 'salario_iliquido', 'base_inss', 'base_irt',
                      'materia_coletavel', 'inss_trabalhador', 'irt', 'inss_patronal', 'total_descontos',
                      'salario_liquido', 'custo_total_empresa')
    CAMPOS_SNAPSHOT = ('empresa_nome', 'empresa_nif', 'empresa_endereco', 'empresa_contactos', 'empresa_inss',
                       'func_nome', 'func_matricula', 'func_nif', 'func_inss', 'func_cargo', 'func_categoria',
                       'func_departamento', 'func_unidade', 'func_tipo_contrato', 'func_data_admissao', 'func_iban')
    # Imutáveis depois de emitido (alterações só por retificação)
    CAMPOS_FECHADOS = CAMPOS_VALORES + CAMPOS_SNAPSHOT + (
        'funcionario_id', 'processamento_id', 'numero', 'sequencial', 'mes', 'ano', 'moeda', 'ajuste_salario_base',
        'lancamentos', 'parametros_calculo', 'data_emissao')

    processamento = models.ForeignKey(ProcessamentoSalarial, on_delete=models.PROTECT, related_name='recibos')
    funcionario = models.ForeignKey('funcionarios.Funcionario', on_delete=models.PROTECT, related_name='recibos_vencimento')
    sequencial = models.PositiveIntegerField(editable=False)
    numero = models.CharField(max_length=40, unique=True, editable=False)
    mes = models.PositiveSmallIntegerField()
    ano = models.PositiveSmallIntegerField()
    data_emissao = models.DateField(null=True, blank=True)
    data_pagamento = models.DateField(null=True, blank=True)
    moeda = models.CharField(max_length=3, default='AOA')
    estado = models.CharField(max_length=10, choices=ESTADOS, default='RASCUNHO')

    # Snapshot da empresa e do funcionário
    empresa_nome = models.CharField(max_length=200, blank=True)
    empresa_nif = models.CharField(max_length=20, blank=True)
    empresa_endereco = models.CharField(max_length=300, blank=True)
    empresa_contactos = models.CharField(max_length=200, blank=True)
    empresa_inss = models.CharField(max_length=30, blank=True)
    func_nome = models.CharField(max_length=255, blank=True)
    func_matricula = models.CharField(max_length=20, blank=True)
    func_nif = models.CharField(max_length=20, blank=True)
    func_inss = models.CharField(max_length=30, blank=True)
    func_cargo = models.CharField(max_length=100, blank=True)
    func_categoria = models.CharField(max_length=100, blank=True)
    func_departamento = models.CharField(max_length=100, blank=True)
    func_unidade = models.CharField(max_length=100, blank=True)
    func_tipo_contrato = models.CharField(max_length=40, blank=True)
    func_data_admissao = models.DateField(null=True, blank=True)
    func_iban = models.CharField(max_length=60, blank=True)

    # Valores
    salario_base = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_remuneracoes_adicionais = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    salario_iliquido = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    base_inss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    base_irt = models.DecimalField("Rendimento sujeito a IRT", max_digits=14, decimal_places=2, default=0)
    materia_coletavel = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    inss_trabalhador = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    irt = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    inss_patronal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_descontos = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    salario_liquido = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    custo_total_empresa = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    ajuste_salario_base = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    lancamentos = models.JSONField(default=dict, blank=True)
    parametros_calculo = models.JSONField(default=dict, blank=True)
    avisos = models.JSONField(default=list, blank=True)
    erros = models.JSONField(default=list, blank=True)

    # Assinaturas e confirmação (operacionais — editáveis após emissão)
    nome_responsavel = models.CharField("Responsável pelo processamento", max_length=150, blank=True)
    contabilista_nome = models.CharField(max_length=150, blank=True)
    contabilista_numero_ordem = models.CharField(max_length=40, blank=True)
    data_assinatura = models.DateField(null=True, blank=True)
    referencia_pagamento = models.CharField("Referência do pagamento bancário", max_length=100, blank=True)
    observacoes = models.TextField(blank=True)

    # Auditoria
    calculado_por = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    calculado_em = models.DateTimeField(null=True, blank=True)
    emitido_por = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    emitido_em = models.DateTimeField(null=True, blank=True)
    hash_integridade = models.CharField(max_length=64, blank=True, editable=False)
    recibo_original = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='retificacoes')
    motivo = models.TextField("Motivo de retificação/anulação", blank=True)

    class Meta:
        verbose_name = "Recibo de Vencimento"
        verbose_name_plural = "Recibos de Vencimento"
        ordering = ['-ano', '-mes', 'func_nome']
        constraints = [
            models.UniqueConstraint(fields=['processamento', 'funcionario'],
                                    condition=Q(estado__in=['RASCUNHO', 'CALCULADO', 'EMITIDO', 'PAGO']),
                                    name='uniq_recibo_ativo_por_processamento'),
            models.UniqueConstraint(fields=['ano', 'sequencial'], name='uniq_recibo_sequencial_ano'),
        ]
        indexes = [models.Index(fields=['funcionario', 'ano', 'mes']), models.Index(fields=['estado'])]

    def __str__(self):
        return f"{self.numero} — {self.func_nome or self.funcionario_id}"

    # ── propriedades ────────────────────────────────────────────────────────
    @property
    def editavel(self):
        return self.estado in ('RASCUNHO', 'CALCULADO')

    @property
    def periodo(self):
        return f"{self.mes:02d}/{self.ano}"

    @property
    def func_iban_mascarado(self):
        i = self.func_iban or ''
        return i if len(i) <= 8 else i[:4] + '*' * (len(i) - 8) + i[-4:]

    @property
    def integridade_ok(self):
        return bool(self.hash_integridade) and self.hash_integridade == self.calcular_hash()

    # ── persistência ────────────────────────────────────────────────────────
    def _atribuir_numero(self):
        cfg = ConfiguracaoRecibo.objects.select_for_update().get_or_create(pk=1)[0]
        ultimo = type(self).objects.filter(ano=self.ano).aggregate(m=Max('sequencial'))['m'] or 0
        self.sequencial = ultimo + 1
        self.numero = f"{cfg.prefixo_numeracao} {self.ano}/{self.sequencial:05d}"

    def save(self, *args, _transicao=False, **kwargs):
        with transaction.atomic():
            if self.pk and not _transicao:
                orig = type(self).objects.filter(pk=self.pk).values('estado', *self.CAMPOS_FECHADOS).first()
                if orig and orig['estado'] in self.FECHADOS:
                    for campo in self.CAMPOS_FECHADOS:
                        if orig[campo] != getattr(self, campo):
                            raise ValidationError(
                                f"O recibo {self.numero} já foi emitido: o campo '{campo}' não pode ser alterado. "
                                f"Use a retificação.")
            if not self.pk and not self.numero:
                self._atribuir_numero()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.estado in self.FECHADOS:
            raise ValidationError("Recibos emitidos não podem ser apagados.")
        return super().delete(*args, **kwargs)

    # ── integridade ─────────────────────────────────────────────────────────
    def calcular_hash(self):
        base = {
            'n': self.numero, 'f': self.funcionario_id, 'p': f"{self.ano}-{self.mes:02d}",
            'v': [str(getattr(self, c)) for c in self.CAMPOS_VALORES],
            'l': [[l.tipo, l.codigo, str(l.valor_final)] for l in self.linhas.order_by('tipo', 'ordem', 'id')],
        }
        return hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest()

    # ── transições de estado ────────────────────────────────────────────────
    def emitir(self, usuario):
        if self.estado != 'CALCULADO':
            raise ValidationError("Só recibos calculados e sem erros podem ser emitidos.")
        with transaction.atomic():
            self.estado = 'EMITIDO'
            self.data_emissao = timezone.localdate()
            self.emitido_por, self.emitido_em = usuario, timezone.now()
            self.hash_integridade = self.calcular_hash()
            self.save(_transicao=True)
            AuditoriaSalarial.registar(usuario, 'RECIBO_EMITIDO', self, depois={'numero': self.numero, 'liquido': str(self.salario_liquido)})

    def marcar_pago(self, usuario, data_pagamento, referencia=''):
        if self.estado != 'EMITIDO':
            raise ValidationError("Só recibos emitidos podem ser marcados como pagos.")
        self.estado, self.data_pagamento = 'PAGO', data_pagamento
        if referencia:
            self.referencia_pagamento = referencia
        self.save(_transicao=True)
        AuditoriaSalarial.registar(usuario, 'RECIBO_PAGO', self, depois={'data': str(data_pagamento), 'referencia': referencia})

    def anular(self, usuario, motivo):
        if self.estado not in ('EMITIDO', 'PAGO'):
            raise ValidationError("Só recibos emitidos ou pagos podem ser anulados.")
        self.estado, self.motivo = 'ANULADO', motivo
        self.save(_transicao=True)
        AuditoriaSalarial.registar(usuario, 'RECIBO_ANULADO', self, depois={'motivo': motivo})

    def retificar(self, usuario, motivo):
        """Marca este recibo como RETIFICADO e cria um novo em rascunho (a recalcular)."""
        if self.estado not in ('EMITIDO', 'PAGO'):
            raise ValidationError("Só recibos emitidos ou pagos podem ser retificados.")
        with transaction.atomic():
            self.estado, self.motivo = 'RETIFICADO', motivo
            self.save(_transicao=True)
            novo = ReciboVencimento(processamento=self.processamento, funcionario=self.funcionario, mes=self.mes,
                                    ano=self.ano, moeda=self.moeda, estado='RASCUNHO', recibo_original=self,
                                    motivo=motivo, lancamentos=self.lancamentos,
                                    ajuste_salario_base=self.ajuste_salario_base)
            novo.save()
            AuditoriaSalarial.registar(usuario, 'RECIBO_RETIFICADO', self, depois={'motivo': motivo, 'novo': novo.numero})
        return novo


class LinhaRecibo(models.Model):
    TIPOS = [('REMUNERACAO', 'Remuneração'), ('DESCONTO', 'Desconto'), ('ENCARGO', 'Encargo patronal')]
    recibo = models.ForeignKey(ReciboVencimento, on_delete=models.CASCADE, related_name='linhas')
    rubrica = models.ForeignKey(Rubrica, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    tipo = models.CharField(max_length=12, choices=TIPOS)
    codigo = models.CharField(max_length=20)
    designacao = models.CharField(max_length=160)
    natureza = models.CharField(max_length=20, blank=True)
    ordem = models.PositiveIntegerField(default=100)
    quantidade = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    base_calculo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    taxa = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    valor_calculado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_final = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sujeita_irt = models.BooleanField(default=True)
    sujeita_inss = models.BooleanField(default=True)
    integra_iliquido = models.BooleanField(default=True)
    observacao = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ['tipo', 'ordem', 'id']

    def __str__(self):
        return f"{self.codigo} {self.valor_final}"

    def save(self, *args, **kwargs):
        if self.recibo.estado in ReciboVencimento.FECHADOS:
            raise ValidationError("Linhas de recibos emitidos não podem ser alteradas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.recibo.estado in ReciboVencimento.FECHADOS:
            raise ValidationError("Linhas de recibos emitidos não podem ser apagadas.")
        return super().delete(*args, **kwargs)


class AuditoriaSalarial(models.Model):
    utilizador = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    acao = models.CharField(max_length=40)
    modelo = models.CharField(max_length=60)
    objeto_id = models.CharField(max_length=40)
    objeto_repr = models.CharField(max_length=250, blank=True)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auditoria salarial"
        verbose_name_plural = "Auditoria salarial"
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['modelo', 'objeto_id'])]

    @classmethod
    def registar(cls, utilizador, acao, objeto, antes=None, depois=None, ip=None):
        def ser(d):
            return None if d is None else json.loads(json.dumps(d, default=str))
        cls.objects.create(utilizador=utilizador if getattr(utilizador, 'pk', None) else None, acao=acao,
                           modelo=type(objeto).__name__, objeto_id=str(objeto.pk), objeto_repr=str(objeto)[:250],
                           antes=ser(antes), depois=ser(depois), ip=ip)
        

