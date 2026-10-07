from django.db import transaction
from django_tenants.utils import schema_context

from apps.core.provisionamento import campos_permissao
from .models import Cargo

# Permissões da área interna SOTARQ (portal de parceiros).
# Os admins das empresas-cliente NÃO devem recebê-las por defeito.
PERMISSOES_PARCEIROS = {
    "pode_gerir_parceiros",
    "pode_ver_parceiros",
    "pode_aprovar_solicitacoes_parceiros",
    "pode_ver_faturamento_parceiros",
}

# Sensíveis: o Gerente não as recebe por defeito.
_SENSIVEIS_GERENTE = {
    "pode_gerir_assinatura_digital", "pode_configurar_assinatura_digital",
    "pode_gerar_par_chave_publica_ou_privada", "pode_baixar_chave_publica",
    "pode_fazer_backup_manual", "pode_atualizar_backups",
    "pode_alterar_dados_fiscais", "pode_eliminar_detalhes_fiscal",
}

CARGOS_PADRAO = [
    {
        "codigo": "ADMIN", "nome": "Administrador", "categoria": "diretoria",
        "nivel": 1, "limite_desconto": 100, "selecionar_todos": True,
        "permissoes": lambda todas: todas - PERMISSOES_PARCEIROS,
    },
    {
        "codigo": "GERENTE", "nome": "Gerente", "categoria": "gerencia",
        "nivel": 2, "limite_desconto": 20,
        "permissoes": lambda todas: todas - PERMISSOES_PARCEIROS - _SENSIVEIS_GERENTE,
    },
    {
        "codigo": "CONTABILISTA", "nome": "Contabilista", "categoria": "financeiro",
        "nivel": 3,
        "permissoes": lambda todas: {
            "pode_acessar_financeiro", "pode_acessar_documentos", "pode_ver_vendas",
            "pode_acessar_fornecedores", "pode_acessar_detalhes_fiscal",
            "pode_acessar_dashboard_fiscal", "pode_acessar_painel_principal_fiscal",
            "pode_exportar_saft", "pode_ver_historico_saft", "pode_baixar_saft",
            "pode_validar_saft", "pode_visualizar_saft", "pode_ver_status_saft",
            "pode_acessar_dashboard_saft", "pode_baixar_saft_backup_fiscal",
            "pode_ver_taxaiva_agt", "pode_ver_taxas_iva", "pode_ver_relatorio_fiscal",
            "pode_ver_relatorio_retencoes", "pode_ver_relatorio_taxas_iva",
            "pode_baixar_retencoes", "pode_baixar_relatorio_retencoes",
            "pode_validar_documentos_fiscais", "pode_verificar_integridade_hash",
            "pode_verificar_integridade_cadeia_hash_fiscal",
        },
    },
    {
        "codigo": "VENDEDOR", "nome": "Vendedor", "categoria": "vendas",
        "nivel": 4,
        "permissoes": lambda todas: {
            "pode_vender", "pode_ver_vendas", "pode_emitir_proforma",
            "pode_emitir_recibo", "pode_confirmar_entrega",
        },
    },
    {
        "codigo": "CAIXA", "nome": "Caixa", "categoria": "vendas",
        "nivel": 4,
        "permissoes": lambda todas: {
            "pode_vender", "pode_ver_vendas", "pode_emitir_recibo",
            "pode_liquidar_faturacredito",
        },
    },
    {
        "codigo": "ESTOQUISTA", "nome": "Estoquista", "categoria": "operacional",
        "nivel": 4,
        "permissoes": lambda todas: {
            "pode_gerenciar_estoque", "pode_editar_produtos",
            "pode_fazer_compras", "pode_acessar_fornecedores",
        },
    },
    {
        "codigo": "RH", "nome": "Recursos Humanos", "categoria": "rh",
        "nivel": 3,
        "permissoes": lambda todas: {
            "pode_acessar_rh", "pode_gerenciar_funcionarios", "pode_pagar_salario",
        },
    },
        {
        "codigo": "GESTOR_SITE", "nome": "Gestor do Site", "categoria": "outros",
        "nivel": 4,
        "permissoes": lambda todas: {
            "pode_gerir_site", "pode_editar_produtos", "pode_ver_vendas",
        },
    },
]


def garantir_cargo(definicao, sincronizar=False, incluir_parceiros=False):
    """
    Cria o cargo se não existir. Chamar SEMPRE dentro de schema_context.
    Devolve (cargo, estado) com estado em 'criado' | 'sincronizado' | 'existente'.
    """
    todas = set(campos_permissao())
    permitidas = set(definicao["permissoes"](todas))
    if incluir_parceiros and definicao["codigo"] == "ADMIN":
        permitidas |= PERMISSOES_PARCEIROS

    desconhecidas = permitidas - todas
    if desconhecidas:
        raise ValueError(
            f"Cargo {definicao['codigo']}: permissões inexistentes no model: {sorted(desconhecidas)}"
        )

    # Tem de ser explícito para TODOS os campos: o model tem defaults True
    # (ex.: pode_vender, pode_pagar_salario) que se aplicariam sem isto.
    valores = {campo: (campo in permitidas) for campo in todas}
    valores["limite_desconto_percentual"] = definicao.get("limite_desconto", 0)
    valores["selecionar_todos"] = definicao.get("selecionar_todos", False)

    cargo = Cargo.objects.filter(codigo=definicao["codigo"]).first()
    if cargo is None:
        cargo = Cargo.objects.create(
            codigo=definicao["codigo"],
            nome=definicao["nome"],
            categoria=definicao["categoria"],
            nivel_hierarquico=definicao["nivel"],
            descricao="Cargo padrão criado automaticamente.",
            **valores,
        )
        return cargo, "criado"

    if sincronizar:
        for campo, valor in valores.items():
            setattr(cargo, campo, valor)
        cargo.save()
        return cargo, "sincronizado"

    return cargo, "existente"


def garantir_cargo_por_codigo(codigo, sincronizar=False, incluir_parceiros=False):
    for definicao in CARGOS_PADRAO:
        if definicao["codigo"] == codigo:
            return garantir_cargo(definicao, sincronizar, incluir_parceiros)
    raise KeyError(f"Cargo padrão desconhecido: {codigo}")


def garantir_cargos_padrao(sincronizar=False, incluir_parceiros=False):
    """Dentro de schema_context. Devolve {codigo: estado}."""
    return {
        d["codigo"]: garantir_cargo(d, sincronizar, incluir_parceiros)[1]
        for d in CARGOS_PADRAO
    }


def aplicar_no_schema(schema_name, sincronizar=False, incluir_parceiros=False, dry_run=False):
    """Entra no schema do tenant, aplica tudo numa transação e devolve o resultado."""
    with schema_context(schema_name):
        with transaction.atomic():
            resultado = garantir_cargos_padrao(sincronizar, incluir_parceiros)
            if dry_run:
                transaction.set_rollback(True)
            return resultado