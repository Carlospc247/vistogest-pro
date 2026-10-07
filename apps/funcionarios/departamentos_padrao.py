from django.db import IntegrityError, transaction
from django_tenants.utils import schema_context

from .models import Departamento

DEPARTAMENTOS_PADRAO = [
    {"codigo": "DEP-ADM", "nome": "Administração Geral",
     "descricao": "Gestão administrativa geral da empresa.", "centro_custo": "ADM", "ativo": True},
    {"codigo": "DEP-FIN", "nome": "Financeiro",
     "descricao": "Gestão financeira, tesouraria e controlo financeiro.", "centro_custo": "FIN", "ativo": True},
    {"codigo": "DEP-RH", "nome": "Recursos Humanos",
     "descricao": "Gestão de pessoas, pessoal, recrutamento e administração de RH.", "centro_custo": "RH", "ativo": True},
    {"codigo": "DEP-COM", "nome": "Comercial e Vendas",
     "descricao": "Gestão comercial, vendas, clientes e actividade comercial.", "centro_custo": "COM", "ativo": True},
    {"codigo": "DEP-OPS", "nome": "Operações",
     "descricao": "Gestão das operações e execução das actividades da empresa.", "centro_custo": "OPS", "ativo": True},
    {"codigo": "DEP-COMPRAS", "nome": "Compras",
     "descricao": "Gestão de compras, pedidos e relacionamento operacional com fornecedores.", "centro_custo": "CMP", "ativo": True},
    {"codigo": "DEP-EST", "nome": "Estoque e Logística",
     "descricao": "Gestão de estoque, movimentação e logística.", "centro_custo": "EST", "ativo": True},
    {"codigo": "DEP-FISCAL", "nome": "Fiscal e Contabilidade",
     "descricao": "Gestão fiscal, documentos fiscais, impostos e processos contabilísticos.", "centro_custo": "FIS", "ativo": True},
    {"codigo": "DEP-TI", "nome": "Tecnologia da Informação",
     "descricao": "Gestão de tecnologia, sistemas, infraestrutura e suporte informático.", "centro_custo": "TI", "ativo": True},
    {"codigo": "DEP-MKT", "nome": "Marketing",
     "descricao": "Marketing, comunicação e divulgação comercial.", "centro_custo": "MKT", "ativo": True},
]

_CAMPOS = ("codigo", "nome", "descricao", "centro_custo", "ativo")
_DEFAULTS = {"descricao": "", "centro_custo": "", "ativo": True}


def garantir_departamento(dados, sincronizar=False):
    """
    Chamar SEMPRE dentro de schema_context.
    Procura pelo código; se não achar, pelo nome (evita duplicados).
    Nunca mexe no `responsavel`.
    Devolve (departamento, estado, alteracoes) com estado em
    'criado' | 'atualizado' | 'inalterado' | 'existente'.
    """
    dep = Departamento.objects.filter(codigo=dados["codigo"]).first()
    if dep is None:
        dep = Departamento.objects.filter(nome=dados["nome"]).order_by("id").first()

    if dep is None:
        dep = Departamento.objects.create(
            codigo=dados["codigo"],
            nome=dados["nome"],
            descricao=dados.get("descricao", ""),
            centro_custo=dados.get("centro_custo", ""),
            ativo=dados.get("ativo", True),
        )
        return dep, "criado", []

    if not sincronizar:
        return dep, "existente", []

    alteracoes = []
    for campo in _CAMPOS:
        novo = dados.get(campo, _DEFAULTS.get(campo))
        atual = getattr(dep, campo)
        if atual != novo:
            alteracoes.append((campo, atual, novo))
            setattr(dep, campo, novo)

    if alteracoes:
        dep.save()
        return dep, "atualizado", alteracoes
    return dep, "inalterado", []


def garantir_departamento_por_codigo(codigo, sincronizar=False):
    for dados in DEPARTAMENTOS_PADRAO:
        if dados["codigo"].upper() == codigo.upper():
            return garantir_departamento(dados, sincronizar)
    raise KeyError(f"Departamento padrão desconhecido: {codigo}")


def garantir_departamentos_padrao(sincronizar=False, codigos=None):
    """
    Dentro de schema_context. Cada item tem o seu savepoint, para que um
    choque de nome único não reverta os restantes.
    Devolve lista de (codigo, nome, estado, alteracoes).
    """
    resultado = []
    for dados in DEPARTAMENTOS_PADRAO:
        if codigos and dados["codigo"].upper() not in codigos:
            continue
        try:
            with transaction.atomic():
                _, estado, alteracoes = garantir_departamento(dados, sincronizar)
        except IntegrityError as e:
            estado = "erro"
            alteracoes = [("erro", "", str(e).splitlines()[0])]
        resultado.append((dados["codigo"], dados["nome"], estado, alteracoes))
    return resultado


def aplicar_no_schema(schema_name, sincronizar=False, codigos=None, dry_run=False):
    with schema_context(schema_name):
        with transaction.atomic():
            resultado = garantir_departamentos_padrao(sincronizar, codigos)
            if dry_run:
                transaction.set_rollback(True)
            return resultado