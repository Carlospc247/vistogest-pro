"""Aplica a parte de modelo da correcção Fiscal/Vendas, com backup.

Executar na raiz do projecto Django: python scripts/patch_vendas_models.py
Não executa migrações. Depois, executar makemigrations vendas e inspeccionar a migração.
"""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

TARGET = Path("apps/vendas/models.py")

NULLABLE_NUMBER_FIELDS = {
    "Venda": {"numero_documento"},
    "FaturaCredito": {"numero_documento"},
    "Recibo": {"numero_recibo"},
    "FaturaProforma": {"numero_documento"},
    "NotaCredito": {"numero_nota"},
    "NotaDebito": {"numero_nota"},
    "DocumentoTransporte": {"numero_documento"},
}

GENERATOR_METHODS = {
    "Venda": "FR",
    "FaturaCredito": "FT",
    "FaturaGenerica": "GF",
    "FaturaAutofacturacao": "AF",
    "FaturaProforma": "FP",
    "Recibo": "RC",
    "NotaCredito": "NC",
    "NotaDebito": "ND",
    "DocumentoTransporte": "DT",
}


def parse(source: str):
    return ast.parse(source)


def node_start(node: ast.AST) -> int:
    decorators = [d.lineno for d in getattr(node, "decorator_list", [])]
    return min([node.lineno, *decorators])


def class_nodes(tree):
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def method_node(class_node: ast.ClassDef, method_name: str):
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            return node
    return None


def apply_edits(source: str, edits: list[tuple[int, int, str]]) -> str:
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(edits, reverse=True):
        replacement_lines = replacement.splitlines(keepends=True)
        replacement_lines = [ln if ln.endswith("\n") else ln + "\n" for ln in replacement_lines]
        lines[start - 1:end] = replacement_lines
    return "".join(lines)


def nullable_number_fields(source: str) -> str:
    tree = parse(source)
    classes = class_nodes(tree)
    edits = []
    lines = source.splitlines(keepends=True)
    for class_name, fields in NULLABLE_NUMBER_FIELDS.items():
        cls = classes.get(class_name)
        if cls is None:
            raise RuntimeError(f"Classe obrigatória não encontrada em {TARGET}: {class_name}")
        for node in cls.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [n.id for n in node.targets if isinstance(n, ast.Name)]
            field_name = next((n for n in names if n in fields), None)
            if not field_name:
                continue
            segment = "".join(lines[node.lineno - 1:node.end_lineno])
            if "null=True" in segment and "blank=True" in segment:
                continue
            if "unique=True" not in segment:
                raise RuntimeError(f"Esperava unique=True em {class_name}.{field_name}; nada foi alterado nesse campo.")
            segment = segment.replace("unique=True", "unique=True, null=True, blank=True", 1)
            edits.append((node.lineno, node.end_lineno, segment))
        # Confirma se cada campo foi encontrado.
        present = set()
        for node in cls.body:
            if isinstance(node, ast.Assign):
                present.update(n.id for n in node.targets if isinstance(n, ast.Name))
        missing = fields - present
        if missing:
            raise RuntimeError(f"Campos não encontrados em {class_name}: {', '.join(sorted(missing))}")
    return apply_edits(source, edits)


def replacement_for_method(class_name: str, method_name: str) -> str | None:
    if method_name == "save" and class_name == "FaturaProforma":
        return '''    def save(self, *args, criar_documento=False, usuario_criacao=None, **kwargs):
        """Persiste a pró-forma; a emissão fiscal é explícita após gravar os itens.

        `numero_documento` fica temporariamente NULL até gerar_documento_fiscal()
        atribuir o número do DocumentoFiscal. A coluna necessita migração.
        Os argumentos antigos são mantidos para compatibilidade com chamadas existentes.
        """
        return super().save(*args, **kwargs)
'''
    if method_name == "gerar_documento_fiscal" and class_name in GENERATOR_METHODS:
        tipo = GENERATOR_METHODS[class_name]
        return f'''    def gerar_documento_fiscal(self, usuario=None):
        """Gera, numera, assina e associa o DocumentoFiscal oficial."""
        from apps.vendas.fiscal_bridge import emitir_documento_fiscal
        return emitir_documento_fiscal(self, usuario=usuario, tipo_documento={tipo!r})
'''
    return None


def replace_class_method(source: str, class_name: str, method_name: str, replacement: str,
                         allow_insert: bool = False) -> str:
    tree = parse(source)
    classes = class_nodes(tree)
    cls = classes.get(class_name)
    if cls is None:
        raise RuntimeError(f"Classe não encontrada: {class_name}")
    node = method_node(cls, method_name)
    if node is None:
        if not allow_insert:
            raise RuntimeError(f"Método não encontrado: {class_name}.{method_name}")
        lines = source.splitlines(keepends=True)
        insert_at = cls.end_lineno
        method = replacement.rstrip() + "\n"
        lines[insert_at:insert_at] = ["\n", *[ln + "\n" for ln in method.rstrip("\n").splitlines()]]
        result = "".join(lines)
        parse(result)
        return result
    source = apply_edits(source, [(node_start(node), node.end_lineno, replacement)])
    parse(source)
    return source


def disable_automatic_document_creation(source: str, class_name: str) -> str:
    tree = parse(source)
    cls = class_nodes(tree).get(class_name)
    if cls is None:
        raise RuntimeError(f"Classe não encontrada: {class_name}")
    node = method_node(cls, "save")
    if node is None:
        return source
    lines = source.splitlines(keepends=True)
    block = "".join(lines[node_start(node) - 1:node.end_lineno])
    block = block.replace("criar_documento=True", "criar_documento=False", 1)
    if block == "".join(lines[node_start(node) - 1:node.end_lineno]):
        # Idempotente: o parâmetro já pode estar no valor novo.
        if "criar_documento=False" in block:
            return source
        raise RuntimeError(f"Não encontrei o argumento criar_documento em {class_name}.save")
    return apply_edits(source, [(node_start(node), node.end_lineno, block)])


def main():
    if not TARGET.exists():
        raise SystemExit(f"Ficheiro não encontrado: {TARGET.resolve()}. Execute na raiz do projecto.")
    source = TARGET.read_text(encoding="utf-8")
    parse(source)
    backup = TARGET.with_suffix(TARGET.suffix + ".pre_fiscal_patch.bak")
    if not backup.exists():
        shutil.copy2(TARGET, backup)

    patched = nullable_number_fields(source)

    # Remover a criação automática prematura em modelos que ainda não têm itens.
    patched = replace_class_method(
        patched, "FaturaProforma", "save",
        replacement_for_method("FaturaProforma", "save"),
    )
    for cls in ("NotaCredito", "NotaDebito", "DocumentoTransporte"):
        patched = disable_automatic_document_creation(patched, cls)

    # Geração fiscal explícita para todos os tipos que partilham o serviço bridge.
    for cls in GENERATOR_METHODS:
        if cls == "FaturaProforma":
            allow_insert = True
        else:
            allow_insert = cls in {"NotaCredito", "NotaDebito", "DocumentoTransporte"}
        replacement = replacement_for_method(cls, "gerar_documento_fiscal")
        patched = replace_class_method(patched, cls, "gerar_documento_fiscal", replacement, allow_insert=allow_insert)

    parse(patched)
    TARGET.write_text(patched, encoding="utf-8")
    print(f"OK: {TARGET} corrigido. Backup: {backup}")
    print("Campos de número tornados temporariamente nulos e métodos fiscais ligados ao bridge.")
    print("A migração de vendas NÃO foi executada; gere-a e inspeccione-a antes de migrar a BD.")


if __name__ == "__main__":
    main()
