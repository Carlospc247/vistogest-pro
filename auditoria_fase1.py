#!/usr/bin/env 
"""Fase 1 - Auditoria do codigo: mapa de emissao e submissao AGT.

Uso (na raiz do projecto VistoGest):
    python auditoria_fase1.py            # analisa ./apps
    python auditoria_fase1.py caminho    # analisa outro directorio

Apenas le ficheiros .py. Nao altera nada. Gera AUDITORIA_FASE1.md.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

IGNORAR = {"migrations", "__pycache__", ".venv", "venv", "node_modules", "tests"}

# categoria -> (descricao, padroes)
CATEGORIAS: dict[str, tuple[str, list[str]]] = {
    "A1_transporte_directo": (
        "Chamadas HTTP directas (candidatas a contornar o AGTClient)",
        [r"\brequests\.(post|get|request)\(", r"\bhttpx\.", r"\bsession\.post\(",
         r"\burllib\.request"],
    ),
    "A2_registarFactura": (
        "Referencias a registarFactura",
        [r"registarFactura", r"registar_factura", r"registar_fatura"],
    ),
    "A3_agtclient": (
        "AGTClient e o seu ponto central _chamar",
        [r"\bAGTClient\b", r"\b_chamar\s*\(", r"\.enviar_lote\(", r"\.submeter\("],
    ),
    "A4_inspector_actual": (
        "Uso actual do Inspector (PayloadInspectorService / PayloadAGT)",
        [r"PayloadInspector", r"\bPayloadAGT\b", r"registar_payload\(",
         r"marcar_enviado\(", r"registar_resposta\("],
    ),
    "B1_emissao_documento": (
        "Criacao/emissao de DocumentoFiscal",
        [r"DocumentoFiscal\.objects\.(create|get_or_create|update_or_create|bulk_create)",
         r"DocumentoFiscalService\.criar_documento", r"criar_documento\("],
    ),
    "B2_transicoes_estado": (
        "Transicoes de estado (draft/confirmed/posted/paid)",
        [r"estado\s*=\s*['\"](draft|confirmed|posted|paid|emitido)['\"]",
         r"status\s*=\s*['\"](draft|confirmed|posted|paid|emitido)['\"]",
         r"\.update\(\s*(estado|status)\s*="],
    ),
    "B3_signals": (
        "Signals (pre_save/post_save/receiver)",
        [r"\b(pre_save|post_save)\b", r"@receiver", r"\.connect\("],
    ),
    "B4_bypass_do_save": (
        "Escritas que nao disparam signals (.update / bulk_update / bulk_create)",
        [r"\.bulk_update\(", r"\.bulk_create\(", r"\.objects\.filter\(.*\)\.update\("],
    ),
    "C1_celery": (
        "Tarefas Celery e disparos",
        [r"@(shared_task|app\.task|task)\b", r"\.delay\(", r"\.apply_async\(",
         r"transaction\.on_commit"],
    ),
    "C2_polling": (
        "Polling / obterEstado",
        [r"obterEstado", r"obter_estado", r"polling", r"consultar_estado"],
    ),
    "C3_comandos": (
        "Management commands relacionados",
        [r"BaseCommand"],
    ),
    "D1_credenciais_risco": (
        "Locais onde cabecalhos/credenciais podem ser persistidos (rever manualmente)",
        [r"Authorization", r"HTTPBasicAuth", r"\bauth\s*=", r"headers\s*="],
    ),
}

COMPILADOS = {
    cat: (desc, [re.compile(p) for p in pats]) for cat, (desc, pats) in CATEGORIAS.items()
}


@dataclass(frozen=True)
class Ocorrencia:
    ficheiro: Path
    linha: int
    texto: str


def ficheiros_py(raiz: Path):
    for caminho in sorted(raiz.rglob("*.py")):
        if not IGNORAR.intersection(caminho.parts):
            yield caminho


def analisar(raiz: Path) -> dict[str, list[Ocorrencia]]:
    achados: dict[str, list[Ocorrencia]] = defaultdict(list)
    for caminho in ficheiros_py(raiz):
        try:
            linhas = caminho.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, linha in enumerate(linhas, start=1):
            if linha.lstrip().startswith("#"):
                continue
            for cat, (_, padroes) in COMPILADOS.items():
                if any(p.search(linha) for p in padroes):
                    achados[cat].append(Ocorrencia(caminho, n, linha.strip()[:140]))
    return achados


def sinalizar_riscos(achados: dict[str, list[Ocorrencia]]) -> list[str]:
    """Cruza categorias para destacar caminhos que podem perder payloads."""
    riscos = []
    permitido = ("agt_client", "agtclient")

    for o in achados.get("A1_transporte_directo", []):
        if not any(p in str(o.ficheiro).lower() for p in permitido):
            riscos.append(
                f"HTTP directo fora do AGTClient: {o.ficheiro}:{o.linha} -> {o.texto}"
            )

    ficheiros_registar = {o.ficheiro for o in achados.get("A2_registarFactura", [])}
    ficheiros_inspector = {o.ficheiro for o in achados.get("A4_inspector_actual", [])}
    for f in sorted(ficheiros_registar - ficheiros_inspector):
        if not any(p in str(f).lower() for p in permitido):
            riscos.append(f"registarFactura sem Inspector no mesmo ficheiro: {f}")

    for o in achados.get("B4_bypass_do_save", []):
        riscos.append(
            f"Escrita sem signals (pode escapar ao listener): {o.ficheiro}:{o.linha}"
        )

    if not achados.get("B3_signals"):
        riscos.append("Nenhum signal encontrado: o listener nao tem onde se ligar hoje.")
    return riscos


def escrever_relatorio(raiz: Path, achados, riscos, destino: Path) -> None:
    out = [f"# Auditoria Fase 1 - Inspector AGT\n\nRaiz analisada: `{raiz}`\n"]
    out.append("## Resumo\n")
    out.append("| Categoria | Ocorrencias | Ficheiros |\n|---|---|---|")
    for cat, (desc, _) in CATEGORIAS.items():
        occ = achados.get(cat, [])
        out.append(f"| {cat}: {desc} | {len(occ)} | {len({o.ficheiro for o in occ})} |")

    out.append("\n## Riscos sinalizados (rever primeiro)\n")
    out.extend(f"- {r}" for r in (riscos or ["Nenhum risco automatico detectado."]))

    out.append("\n## Detalhe por categoria\n")
    for cat, (desc, _) in CATEGORIAS.items():
        out.append(f"### {cat} - {desc}\n")
        por_ficheiro = defaultdict(list)
        for o in achados.get(cat, []):
            por_ficheiro[o.ficheiro].append(o)
        if not por_ficheiro:
            out.append("_sem ocorrencias_\n")
            continue
        for f, lista in por_ficheiro.items():
            out.append(f"**{f}**")
            out.extend(f"- L{o.linha}: `{o.texto}`" for o in lista)
            out.append("")
    destino.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "apps")
    if not raiz.is_dir():
        print(f"Directorio nao encontrado: {raiz}")
        return 1
    achados = analisar(raiz)
    riscos = sinalizar_riscos(achados)
    destino = Path("AUDITORIA_FASE1.md")
    escrever_relatorio(raiz, achados, riscos, destino)
    print(f"Relatorio: {destino} | riscos sinalizados: {len(riscos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())