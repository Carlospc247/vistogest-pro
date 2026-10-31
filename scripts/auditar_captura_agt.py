"""Audita possíveis caminhos HTTP AGT fora do transporte central.

Executar a partir da raiz do projecto:
    python scripts/auditar_captura_agt.py
O script só lê ficheiros .py; não importa a aplicação nem faz pedidos de rede.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "migrations", "node_modules"}
PATTERNS = {
    "POST HTTP": re.compile(r"\brequests\.(?:post|request)\s*\(|\bsession\.post\s*\(|\bhttpx\.(?:post|request)\s*\(", re.I),
    "AGT registarFactura": re.compile(r"registarFactura|registar_factura|registar_documento_fiscal", re.I),
    "Payload inspector": re.compile(r"PayloadInspectorService|submeter_documento_agt", re.I),
    "AGTClient": re.compile(r"AGTClient|\.\_chamar\s*\(", re.I),
}


def main() -> int:
    matches = 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            found = [name for name, pattern in PATTERNS.items() if pattern.search(line)]
            if found:
                matches += 1
                print(f"{path}:{number}: [{', '.join(found)}] {line.strip()}")
    if not matches:
        print("Nenhum ponto de transporte/submissão reconhecido. Confirme a pasta actual.")
    print("\nRevisão manual necessária: cada POST para registarFactura deve passar pelo AGTClient._chamar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
