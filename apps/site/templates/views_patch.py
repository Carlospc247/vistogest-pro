# INTEGRA ESTE CÓDIGO EM apps/site/views.py.
# Os imports de logging, connection, slugify, JsonResponse, get_object_or_404,
# LoginRequiredMixin, TenantOnlyMixin, View, Secao e logger já existem no código enviado.

class UploadImagemSecaoView(LoginRequiredMixin, TenantOnlyMixin, View):
    """Recebe uma imagem do editor e guarda-a no Cloudinary para uma secção."""
    MAX_BYTES = 8 * 1024 * 1024
    CONTENT_TYPES = {
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/gif',
    }

    def post(self, request, secao_id):
        # O endpoint também serve imagens de galerias, equipa, parceiros e hero.
        # A permissão continua protegida por TenantOnlyMixin.
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
            # Cloudinary já é utilizado pelo modelo ConfiguracaoSite/Secao no projecto.
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


# SUBSTITUI a implementação de AtualizarConfiguracaoView.post por esta versão.
# Mantém a classe ActualizarConfiguracaoView existente e substitui só o método.
def atualizar_configuracao_site_post(self, request):
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
            valor = request.POST.get(campo, '').strip().lower()
            setattr(config, campo, valor in {'on', 'true', '1', 'yes', 'sim'})
        elif campo in request.POST:
            setattr(config, campo, request.POST.get(campo, '').strip())

    config.salvar()
    messages.success(request, 'Configuração actualizada.')
    return redirect('site:configuracao_dashboard')


# Para usar a função acima sem manter código duplicado:
# dentro de AtualizarConfiguracaoView, substitui post(...) por:
#     post = atualizar_configuracao_site_post

# FRAGMENTO PARA BLOCOS_DISPONIVEIS: acrescenta esta entrada, sem remover as restantes.
# {'tipo': 'imagem_fixa', 'nome': 'Imagem Fixa com Texto', 'icone': 'image', 'cor': 'blue'},

# FRAGMENTO PARA SECAO_DEFAULTS['carrossel']: mantém os campos existentes e acrescenta:
# 'intervalo_ms': 5000,


# SUBSTITUI o método ReordenarSecoesView.post por esta versão quando passares
# pagina_id no JSON. Assim, IDs de outra página do mesmo tenant não são reordenados.
def reordenar_secoes_post(self, request):
    try:
        data = json.loads(request.body or b'{}')
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

    pagina_id = data.get('pagina_id')
    if not pagina_id:
        return JsonResponse({'ok': False, 'error': 'pagina_id é obrigatório.'}, status=400)

    pagina = get_object_or_404(Pagina, pk=pagina_id)
    lista = data.get('ordem') or data.get('secoes') or []
    if not isinstance(lista, list):
        return JsonResponse({'ok': False, 'error': 'A ordem deve ser uma lista.'}, status=400)

    ids_validos = set(pagina.secoes.values_list('pk', flat=True))
    with transaction.atomic():
        for indice, item in enumerate(lista, start=1):
            if not isinstance(item, dict):
                continue
            try:
                pk = int(item.get('id') or item.get('pk'))
            except (TypeError, ValueError):
                continue
            if pk in ids_validos:
                Secao.objects.filter(pk=pk, pagina=pagina).update(ordem=indice)

    return JsonResponse({'ok': True})
