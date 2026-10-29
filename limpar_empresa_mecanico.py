"""
Remove as linhas triviais que ainda referem o FK `empresa` já apagado dos modelos
fiscais. Só apaga linhas que são, sozinhas, uma instrução completa:

    _validar_empresa_no_schema(documento.empresa)
    form.instance.empresa = self.request.user.empresa
    obj.empresa = empresa

Por omissão NÃO grava nada (dry-run). Com --apply faz backup (.bak_empresa),
grava e compila o ficheiro; se a compilação falhar (por exemplo, a linha era a
única instrução de um bloco), repõe o backup e diz qual foi.

Uso, na raiz do projecto (onde está o manage.py):
    python limpar_empresa_mecanico.py            # só mostra
    python limpar_empresa_mecanico.py --apply    # aplica
"""
import argparse
import py_compile
import re
import shutil
from pathlib import Path

ALVOS = (
    "apps/fiscal/services/documento_fiscal_service.py",
    "apps/fiscal/views.py",
    "apps/fiscal/web_views.py",
)
PADROES = (
    re.compile(r"^\s*_validar_empresa_no_schema\(documento\.empresa\)\s*$"),
    re.compile(r"^\s*form\.instance\.empresa\s*=\s*self\.request\.user\.empresa\s*$"),
    re.compile(r"^\s*obj\.empresa\s*=\s*empresa\s*$"),
)


def processar(caminho: Path, aplicar: bool) -> int:
    linhas = caminho.read_text(encoding="utf-8").splitlines(keepends=True)
    removidas = [(n, l) for n, l in enumerate(linhas, 1) if any(p.match(l) for p in PADROES)]
    for n, l in removidas:
        print(f"  {caminho}:{n}: {l.strip()}")
    if not removidas or not aplicar:
        return len(removidas)

    backup = caminho.with_suffix(caminho.suffix + ".bak_empresa")
    shutil.copy2(caminho, backup)
    numeros = {n for n, _ in removidas}
    caminho.write_text("".join(l for n, l in enumerate(linhas, 1) if n not in numeros), encoding="utf-8")
    try:
        py_compile.compile(str(caminho), doraise=True)
    except py_compile.PyCompileError as exc:
        shutil.copy2(backup, caminho)
        print(f"  ✘ {caminho}: ficou inválido sem essas linhas, REPOSTO. {exc.msg.strip()}")
        return 0
    print(f"  ✔ {caminho}: {len(removidas)} linha(s) removida(s); backup em {backup.name}")
    return len(removidas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="grava as alterações")
    args = ap.parse_args()

    total = 0
    for alvo in ALVOS:
        caminho = Path(alvo)
        if not caminho.exists():
            print(f"  (não encontrado: {alvo})")
            continue
        total += processar(caminho, args.apply)
    print(f"\n{total} linha(s) {'removida(s)' if args.apply else 'a remover (dry-run; use --apply)'}.")


if __name__ == "__main__":
    main()