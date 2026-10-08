# apps/core/management/commands/auditar_empresa.py
"""
Apanha QUALQUER ocorrência da sequência "empresa" (sem excepções, sem
distinguir maiúsculas): empresa, empresa_atual, empresa_id, empresas,
Empresa, EmpresaForm, request.tenant.empresa, etc.

Gera `analise.md` com, para cada ocorrência:
  - o local exacto (ficheiro:linha e app, marcada como TENANT/SHARED);
  - o código INTEIRO onde está: em .py a função/método (ou o campo/statement
    da classe) completo, via AST; em .html/.js/etc. uma janela de contexto.
  - as linhas com ocorrência marcadas com ">>".

Uso:
    python manage.py auditar_empresa --settings=config.settings.development
    python manage.py auditar_empresa --ext .py .html .js --sem-migrations
    python manage.py auditar_empresa --app vendas fiscal
"""
import ast
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

DIRS_IGNORADOS = {
    '.git', '.venv', 'venv', 'env', 'node_modules', '__pycache__',
    'staticfiles', 'media', 'site-packages', 'dist', 'build', '.idea', '.vscode',
}
LANG = {
    '.py': 'python', '.html': 'html', '.js': 'javascript', '.css': 'css',
    '.json': 'json', '.md': 'markdown', '.txt': 'text', '.sql': 'sql',
}
PADRAO = re.compile(r'empresa', re.IGNORECASE)
RE_BLOCK_TPL = re.compile(r'\{%\s*block\s+(\w+)')
TAM_MAX_FICHEIRO = 2_000_000  # ignora ficheiros enormes (dumps, fixtures)


class Command(BaseCommand):
    help = 'Gera analise.md com TODAS as ocorrências de "empresa" e o código completo.'

    def add_arguments(self, parser):
        parser.add_argument('--raiz', default=None, help='Pasta raiz (omissão: BASE_DIR).')
        parser.add_argument('--ext', nargs='+',
                            default=['.py', '.html', '.js', '.css', '.json', '.txt', '.md'])
        parser.add_argument('--saida', default='analise.md')
        parser.add_argument('--sem-migrations', action='store_true')
        parser.add_argument('--app', nargs='+', default=None)
        parser.add_argument('--contexto', type=int, default=12,
                            help='Linhas de contexto (ficheiros não-Python).')
        parser.add_argument('--max-bloco', type=int, default=150,
                            help='Blocos Python maiores são cortados em janelas à volta das ocorrências.')

    # ------------------------------------------------------------------
    def handle(self, *args, **o):
        raiz = Path(o['raiz'] or settings.BASE_DIR).resolve()
        saida = Path(o['saida']).resolve()
        exts = {e if e.startswith('.') else f'.{e}' for e in o['ext']}
        self.opts = o

        ficheiros_res = []   # (rel, app, estado, blocos, n_linhas_hit)
        ignorados = []
        for p in sorted(raiz.rglob('*')):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            if any(parte in DIRS_IGNORADOS for parte in p.parts):
                continue
            if p.resolve() in (saida, Path(__file__).resolve()):
                continue
            rel = p.relative_to(raiz)
            if o['sem_migrations'] and 'migrations' in rel.parts:
                continue
            app = self._app_de(rel)
            if o['app'] and app not in o['app']:
                continue
            if p.stat().st_size > TAM_MAX_FICHEIRO:
                ignorados.append(str(rel))
                continue

            texto = p.read_text(encoding='utf-8', errors='replace')
            linhas = texto.splitlines()
            hits = [i for i, l in enumerate(linhas, 1) if PADRAO.search(l)]
            if not hits:
                continue

            if p.suffix.lower() == '.py':
                blocos = self._blocos_python(texto, linhas, hits)
            else:
                blocos = self._blocos_contexto(p.suffix.lower(), linhas, hits)
            ficheiros_res.append((rel, app, self._estado(app), blocos, len(hits)))

        self._escrever(saida, ficheiros_res, ignorados)

    # ------------------------------------------------------------------
    # Python: bloco completo via AST
    # ------------------------------------------------------------------
    @staticmethod
    def _inicio(no):
        decs = [d.lineno for d in getattr(no, 'decorator_list', [])]
        return min([no.lineno] + decs)

    @staticmethod
    def _filhos(no):
        filhos = []
        for attr in ('body', 'orelse', 'finalbody'):
            filhos.extend(getattr(no, attr, []) or [])
        filhos.extend(getattr(no, 'handlers', []) or [])
        for caso in getattr(no, 'cases', []) or []:  # match/case
            filhos.append(caso)
        return [f for f in filhos if hasattr(f, 'lineno') and hasattr(f, 'end_lineno')]

    def _localizar(self, tree, linha):
        """Devolve (breadcrumb, inicio, fim) do bloco que contém `linha`."""
        crumbs, corpo = [], tree.body
        while True:
            alvo = next((n for n in corpo
                         if hasattr(n, 'end_lineno')
                         and self._inicio(n) <= linha <= n.end_lineno), None)
            if alvo is None:
                return crumbs, linha, linha
            ini, fim = self._inicio(alvo), alvo.end_lineno

            if isinstance(alvo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                crumbs.append(alvo.name + '()')
                return crumbs, ini, fim
            if isinstance(alvo, ast.ClassDef):
                crumbs.append(f'class {alvo.name}')
            filhos = self._filhos(alvo)
            if not filhos:
                return crumbs, ini, fim            # statement simples
            if any(self._inicio(f) <= linha <= f.end_lineno for f in filhos):
                corpo = filhos                       # desce
                continue
            # ocorrência no cabeçalho (class X(...), if cond:, etc.)
            return crumbs, ini, min(self._inicio(f) for f in filhos) - 1

    def _blocos_python(self, texto, linhas, hits):
        try:
            tree = ast.parse(texto)
        except SyntaxError:
            return self._blocos_contexto('.py', linhas, hits, aviso='(erro de sintaxe: sem AST)')
        agrup = defaultdict(lambda: {'hits': [], 'crumbs': []})
        for h in hits:
            crumbs, ini, fim = self._localizar(tree, h)
            g = agrup[(ini, fim)]
            g['hits'].append(h)
            g['crumbs'] = crumbs
        blocos = []
        for (ini, fim), g in sorted(agrup.items()):
            blocos.append({
                'titulo': ' › '.join(g['crumbs']) or 'nível do módulo',
                'ini': ini, 'fim': fim, 'hits': g['hits'],
            })
        return blocos

    # ------------------------------------------------------------------
    # Outros ficheiros: janelas de contexto fundidas
    # ------------------------------------------------------------------
    def _blocos_contexto(self, ext, linhas, hits, aviso=''):
        c, total = self.opts['contexto'], len(linhas)
        janelas = []
        for h in hits:
            a, b = max(1, h - c), min(total, h + c)
            if janelas and a <= janelas[-1][1] + 1:
                janelas[-1][1] = max(janelas[-1][1], b)
                janelas[-1][2].append(h)
            else:
                janelas.append([a, b, [h]])
        blocos = []
        for a, b, hs in janelas:
            titulo = aviso or 'contexto'
            if ext == '.html':
                for i in range(hs[0], 0, -1):
                    m = RE_BLOCK_TPL.search(linhas[i - 1])
                    if m:
                        titulo = f'{{% block {m.group(1)} %}}'
                        break
            blocos.append({'titulo': titulo, 'ini': a, 'fim': b, 'hits': hs})
        return blocos

    # ------------------------------------------------------------------
    @staticmethod
    def _app_de(rel):
        p = rel.parts
        if 'apps' in p:
            i = p.index('apps')
            if i + 1 < len(p) - 1:
                return p[i + 1]
        return None

    @staticmethod
    def _estado(app):
        if not app:
            return 'FORA_DE_APPS'
        label = f'apps.{app}'
        m = lambda lst: any(a == label or a.startswith(label + '.') for a in lst)
        t, s = m(getattr(settings, 'TENANT_APPS', [])), m(getattr(settings, 'SHARED_APPS', []))
        return 'AMBOS' if t and s else 'TENANT' if t else 'SHARED' if s else 'NAO_REGISTADA'

    # ------------------------------------------------------------------
    def _renderizar_bloco(self, linhas, b, ext):
        ini, fim, hits = b['ini'], b['fim'], set(b['hits'])
        max_b, janela = self.opts['max_bloco'], 8
        if fim - ini + 1 <= max_b:
            intervalos = [(ini, fim)]
        else:  # bloco gigante: cabeçalho + janelas à volta das ocorrências
            iv = [(ini, min(fim, ini + 2))]
            for h in sorted(hits):
                iv.append((max(ini, h - janela), min(fim, h + janela)))
            iv.sort()
            intervalos = []
            for a, z in iv:
                if intervalos and a <= intervalos[-1][1] + 1:
                    intervalos[-1] = (intervalos[-1][0], max(intervalos[-1][1], z))
                else:
                    intervalos.append((a, z))
        out, ult = [], None
        for a, z in intervalos:
            if ult is not None and a > ult + 1:
                out.append(f'      ·  ... ({a - ult - 1} linhas omitidas) ...')
            for n in range(a, z + 1):
                marca = '>>' if n in hits else '  '
                out.append(f'{marca} {n:>5} | {linhas[n - 1]}')
            ult = z
        lang = LANG.get(ext, '')
        return f'````{lang}\n' + '\n'.join(out) + '\n````'

    def _escrever(self, saida, resultados, ignorados):
        ordem = {'TENANT': 0, 'AMBOS': 1, 'NAO_REGISTADA': 2, 'FORA_DE_APPS': 3, 'SHARED': 4}
        resultados.sort(key=lambda r: (ordem.get(r[2], 9), r[1] or '', str(r[0])))

        total_hits = sum(r[4] for r in resultados)
        por_app = Counter()
        for rel, app, estado, _, n in resultados:
            por_app[(estado, app or '-')] += n

        md = ['# Análise — ocorrências de "empresa"', '',
              f'- **Linhas com ocorrência:** {total_hits}',
              f'- **Ficheiros afectados:** {len(resultados)}',
              '- Critério: qualquer sequência `empresa` (sem distinguir maiúsculas), incluindo '
              '`empresa_atual`, `empresa_id`, `empresas`, `Empresa*`.',
              '- `>>` marca a linha exacta da ocorrência; o resto é o código completo do bloco '
              '(função/método/campo em Python; janela de contexto nos restantes tipos).', '',
              '## Resumo por app', '', '| Estado | App | Linhas |', '|---|---|---:|']
        for (estado, app), n in sorted(por_app.items(), key=lambda kv: (ordem.get(kv[0][0], 9), kv[0][1])):
            md.append(f'| {estado} | {app} | {n} |')

        md += ['', '## Índice de ficheiros', '', '| Estado | Ficheiro | Linhas |', '|---|---|---:|']
        for rel, app, estado, _, n in resultados:
            md.append(f'| {estado} | `{str(rel).replace(chr(92), "/")}` | {n} |')

        if ignorados:
            md += ['', '> Ignorados por tamanho (>2 MB): ' + ', '.join(f'`{i}`' for i in ignorados)]

        md += ['', '---', '']
        for rel, app, estado, blocos, n in resultados:
            rel_s = str(rel).replace('\\', '/')
            ext = rel.suffix.lower()
            texto = (Path(self.opts['raiz'] or settings.BASE_DIR) / rel).read_text(
                encoding='utf-8', errors='replace')
            linhas = texto.splitlines()
            md += [f'## `{rel_s}`', '',
                   f'**App:** `{app or "-"}` · **Estado:** {estado} · **Linhas com ocorrência:** {n}', '']
            for b in blocos:
                hs = ', '.join(str(h) for h in b['hits'])
                md += [f"### {rel_s}:{b['ini']}-{b['fim']} — {b['titulo']}",
                       f'Ocorrências nas linhas: **{hs}**', '',
                       self._renderizar_bloco(linhas, b, ext), '']

        saida.write_text('\n'.join(md), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'{total_hits} linhas em {len(resultados)} ficheiros → {saida}'))
        for (estado, app), n in sorted(por_app.items(), key=lambda kv: (ordem.get(kv[0][0], 9), kv[0][1])):
            estilo = self.style.ERROR if estado == 'TENANT' else self.style.HTTP_INFO
            self.stdout.write(estilo(f'  {estado:<14}{app:<22}{n}'))