#!/usr/bin/env python3
"""Aplica as correcções S12 em apps/site/views.py e apps/site/urls.py.

Uso, na raiz do projecto VistoGest:
    python apply_site_views_fixes.py

Cria cópias .bak antes de modificar os ficheiros. É idempotente: pode ser
executado novamente sem duplicar a classe nem a rota.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

UPLOAD_CLASS = '''class UploadImagemSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Recebe uma imagem do editor e guarda-a no Cloudinary para uma secção."""
    MAX_BYTES = 8 * 1024 * 1024
    CONTENT_TYPES = {
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
    }

    def post(self, request, secao_id):
        secao = get_object_or_404(Secao, pk=secao_id)
        imagem = request.FILES.get('imagem')

        if imagem is None:
            return JsonResponse(
                {'ok': False, 'error': 'Selecciona uma imagem antes de carregar.'},
                status=400,
            )

        if imagem.size > self.MAX_BYTES:
            return JsonResponse(
                {'ok': False, 'error': 'A imagem não pode exceder 8 MB.'},
                status=413,
            )

        if imagem.content_type not in self.CONTENT_TYPES:
            return JsonResponse(
                {'ok': False, 'error': 'Formato inválido. Usa JPG, PNG, WEBP ou GIF.'},
                status=415,
            )

        try:
            import cloudinary.uploader

            tenant_folder = slugify(connection.schema_name) or 'tenant'
            resultado = cloudinary.uploader.upload(
                imagem,
                folder=f'vistogest/sites/{tenant_folder}/{secao.tipo}',
                resource_type='image',
                allowed_formats=['jpg', 'jpeg', 'png', 'webp', 'gif'],
                use_filename=True,
                unique_filename=True,
                overwrite=False,
            )
            url = resultado.get('secure_url')
            if not url:
                raise RuntimeError('O serviço de imagens não devolveu um URL seguro.')

            return JsonResponse({
                'ok': True,
                'url': url,
                'public_id': resultado.get('public_id', ''),
            })
        except Exception:
            logger.exception(
                'Falha ao carregar imagem de secção (secao_id=%s)', secao.pk
            )
            return JsonResponse(
                {'ok': False, 'error': 'Não foi possível carregar a imagem. Verifica a configuração do Cloudinary.'},
                status=502,
            )
'''

UPDATED_CONFIG_CLASS = '''class AtualizarConfiguracaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Actualiza ConfiguracaoSite (WhatsApp, loja, contactos, etc.)."""
    def post(self, request):
        config = _obter_config()
        campos = [
            'nome_exibicao', 'slogan', 'email_publico', 'telefone_publico',
            'endereco_publico', 'numero_whatsapp', 'mensagem_whatsapp',
            'mostrar_whatsapp', 'loja_activa', 'aceita_pedidos', 'moeda',
            'mensagem_confirmacao', 'email_notificacao_pedidos',
            'facebook', 'instagram', 'linkedin', 'youtube', 'iframe_mapa',
        ]
        campos_booleanos = {'mostrar_whatsapp', 'loja_activa', 'aceita_pedidos'}

        for campo in campos:
            if campo in campos_booleanos:
                # Checkboxes desmarcadas não chegam no POST: nesse caso ficam False.
                valor = request.POST.get(campo, '').strip().lower()
                setattr(config, campo, valor in {'on', 'true', '1', 'yes', 'sim'})
            elif campo in request.POST:
                # Preserva a possibilidade de limpar campos de texto.
                setattr(config, campo, request.POST.get(campo, '').strip())

        config.salvar()
        messages.success(request, 'Configuração actualizada.')
        return redirect('site:configuracao_dashboard')
'''


def patch_views(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    # 1. Remove a declaração duplicada, mais permissiva, sem PodeGerirSite.
    duplicate = re.compile(
        r"\nclass TenantBaseViewSet\(viewsets\.ModelViewSet\):\n"
        r"[ \t]+permission_classes = \[permissions\.IsAuthenticated\]\n"
        r"(?:[ \t]*\n)?[ \t]+def get_queryset\(self\):\n"
        r"[ \t]+return self\.queryset\n?"
    )
    text, n_duplicate = duplicate.subn("\n", text, count=1)
    if n_duplicate:
        changes.append('Removida a declaração permissiva duplicada de TenantBaseViewSet.')

    secure_class = re.search(
        r"class TenantBaseViewSet\(viewsets\.ModelViewSet\):\s*"
        r"permission_classes\s*=\s*\[permissions\.IsAuthenticated,\s*PodeGerirSite\]",
        text,
    )
    count_base_classes = len(re.findall(r"^class TenantBaseViewSet\(", text, flags=re.M))
    if not secure_class or count_base_classes != 1:
        raise ValueError(
            'Não foi possível confirmar que TenantBaseViewSet tem exactamente uma '
            'declaração com IsAuthenticated e PodeGerirSite. Nenhuma alteração foi escrita.'
        )

    # 2. Adiciona imagem_fixa ao catálogo do editor.
    block_list = re.search(r"BLOCOS_DISPONIVEIS\s*=\s*\[(.*?)\n\]", text, flags=re.S)
    if not block_list:
        raise ValueError('Não encontrei a lista BLOCOS_DISPONIVEIS.')
    if "'tipo': 'imagem_fixa'" not in block_list.group(1):
        hero_line = re.search(r"(?m)^([ \t]*\{'tipo': 'hero'.*\n)", block_list.group(1))
        if hero_line:
            insert_at = block_list.start(1) + hero_line.end(1)
            image_entry = "    {'tipo': 'imagem_fixa', 'nome': 'Imagem Fixa com Texto', 'icone': 'image', 'cor': 'blue'},\n"
            text = text[:insert_at] + image_entry + text[insert_at:]
        else:
            # Sem depender da existência de hero, insere no início da lista.
            insert_at = block_list.start(1)
            text = text[:insert_at] + "\n    {'tipo': 'imagem_fixa', 'nome': 'Imagem Fixa com Texto', 'icone': 'image', 'cor': 'blue'}," + text[insert_at:]
        changes.append('Adicionado imagem_fixa a BLOCOS_DISPONIVEIS.')

    # 3. Acrescenta intervalo_ms ao default específico do carrossel.
    defaults_start = text.find('SECAO_DEFAULTS = {')
    if defaults_start < 0:
        raise ValueError('Não encontrei SECAO_DEFAULTS.')
    next_section = text.find("\n    'card':", defaults_start)
    if next_section < 0:
        raise ValueError('Não encontrei a secção card depois do default do carrossel.')
    carousel_region = text[defaults_start:next_section]
    if "'intervalo_ms'" not in carousel_region:
        new_region, n_interval = re.subn(
            r"('autoplay'\s*:\s*True\s*,\s*)('altura_px'\s*:\s*450)",
            r"\1'intervalo_ms': 5000, \2",
            carousel_region,
            count=1,
        )
        if not n_interval:
            raise ValueError('Não consegui acrescentar intervalo_ms ao default do carrossel.')
        text = text[:defaults_start] + new_region + text[next_section:]
        changes.append('Adicionado intervalo_ms=5000 aos defaults do carrossel.')

    # 4. Corrige a actualização da configuração por tipo explícito de campo.
    config_pattern = re.compile(
        r"class AtualizarConfiguracaoView\(LoginRequiredMixin, TenantOnlyMixin, View\):.*?(?=\nclass ReordenarSecoesView\()",
        flags=re.S,
    )
    match = config_pattern.search(text)
    if not match:
        raise ValueError('Não encontrei AtualizarConfiguracaoView antes de ReordenarSecoesView.')
    old_class = match.group(0).rstrip()
    if 'campos_booleanos = {\'mostrar_whatsapp\', \'loja_activa\', \'aceita_pedidos\'}' not in old_class:
        text = text[:match.start()] + UPDATED_CONFIG_CLASS + '\n\n' + text[match.end():]
        changes.append('Corrigido AtualizarConfiguracaoView para tratar booleanos explicitamente.')

    # 5. Insere a view de upload antes da secção/editor.
    if 'class UploadImagemSecaoView(' not in text:
        marker = '# ─── S12 Site Builder'
        pos = text.find(marker)
        if pos < 0:
            marker = 'class SiteEditorView('
            pos = text.find(marker)
        if pos < 0:
            raise ValueError('Não encontrei o ponto de inserção para UploadImagemSecaoView.')
        text = text[:pos] + UPLOAD_CLASS + '\n\n\n' + text[pos:]
        changes.append('Adicionada UploadImagemSecaoView com validação básica e upload para Cloudinary.')

    # Sanity checks against accidental duplicates / missed changes.
    if text.count('class UploadImagemSecaoView(') != 1:
        raise ValueError('A classe UploadImagemSecaoView ficou duplicada.')
    if "'tipo': 'imagem_fixa'" not in re.search(
        r"BLOCOS_DISPONIVEIS\s*=\s*\[(.*?)\n\]", text, flags=re.S
    ).group(1):
        raise ValueError('imagem_fixa não ficou na lista BLOCOS_DISPONIVEIS.')
    defaults_region = text[text.find('SECAO_DEFAULTS = {'):text.find("\n    'card':", text.find('SECAO_DEFAULTS = {'))]
    if "'intervalo_ms': 5000" not in defaults_region:
        raise ValueError('intervalo_ms não ficou nos defaults do carrossel.')
    return text, changes


def patch_urls(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    if "name='upload_imagem_secao'" in text or 'name="upload_imagem_secao"' in text:
        return text, changes

    marker = re.search(r"(?m)^urlpatterns\s*=\s*\[", text)
    if not marker:
        raise ValueError('Não encontrei urlpatterns = [ em apps/site/urls.py.')

    # Coloca os imports junto aos restantes, imediatamente antes de urlpatterns.
    imports_to_add = []
    if not re.search(r"(?m)^from\s+django\.urls\s+import\s+[^\n]*\bpath\b", text):
        if not re.search(r"(?m)^import\s+[^\n]*django\.urls", text):
            imports_to_add.append('from django.urls import path')
    has_views_module = bool(re.search(
        r"(?m)^(?:from\s+\.\s+import\s+views\b|from\s+apps\.site\s+import\s+views\b|import\s+apps\.site\.views\s+as\s+views\b)",
        text,
    ))
    if not has_views_module:
        imports_to_add.append('from . import views')

    if imports_to_add:
        text = text[:marker.start()] + '\n'.join(imports_to_add) + '\n\n' + text[marker.start():]
        marker = re.search(r"(?m)^urlpatterns\s*=\s*\[", text)
        changes.append('Garantidos os imports de path e views em apps/site/urls.py.')

    route = "\n    path(\n        'admin/secao/<int:secao_id>/upload-imagem/',\n        views.UploadImagemSecaoView.as_view(),\n        name='upload_imagem_secao',\n    ),"
    insert_pos = marker.end()
    text = text[:insert_pos] + route + text[insert_pos:]
    changes.append('Adicionada a rota nomeada site:upload_imagem_secao.')
    return text, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', default='.', help='Raiz do projecto Django (por omissão: directório actual).')
    parser.add_argument('--dry-run', action='store_true', help='Só valida e mostra alterações; não escreve ficheiros.')
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    views_path = root / 'apps' / 'site' / 'views.py'
    urls_path = root / 'apps' / 'site' / 'urls.py'
    missing = [str(p) for p in (views_path, urls_path) if not p.is_file()]
    if missing:
        print('ERRO: não encontrei todos os ficheiros necessários:', file=sys.stderr)
        for item in missing:
            print(f'  - {item}', file=sys.stderr)
        print('Executa o script na raiz do projecto ou usa --project-root "C:\\caminho\\vistogest-pro".', file=sys.stderr)
        return 2

    try:
        raw_views = views_path.read_bytes().decode('utf-8')
        raw_urls = urls_path.read_bytes().decode('utf-8')
        views_newline = '\r\n' if '\r\n' in raw_views else '\n'
        urls_newline = '\r\n' if '\r\n' in raw_urls else '\n'
        original_views = raw_views.replace('\r\n', '\n').replace('\r', '\n')
        original_urls = raw_urls.replace('\r\n', '\n').replace('\r', '\n')
        updated_views, view_changes = patch_views(original_views)
        updated_urls, url_changes = patch_urls(original_urls)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        print('Nenhum ficheiro foi escrito.', file=sys.stderr)
        return 1

    changes = view_changes + url_changes
    if not changes:
        print('OK: as correcções solicitadas já parecem estar aplicadas; nada a alterar.')
        return 0

    print('Alterações propostas:')
    for item in changes:
        print(f'  - {item}')
    if args.dry_run:
        print('DRY-RUN: validação concluída; ficheiros não modificados.')
        return 0

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for path in (views_path, urls_path):
        backup = path.with_name(path.name + f'.bak_{stamp}')
        shutil.copy2(path, backup)
        print(f'Backup: {backup}')

    views_path.write_text(updated_views.replace('\n', views_newline), encoding='utf-8', newline='')
    urls_path.write_text(updated_urls.replace('\n', urls_newline), encoding='utf-8', newline='')
    print('SUCESSO: views.py e urls.py foram actualizados.')
    print('Próximo passo: executar `python manage.py check` no ambiente virtual do projecto.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
