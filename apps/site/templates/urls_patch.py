# Acrescenta esta rota dentro de urlpatterns em apps/site/urls.py.
path(
    'admin/secao/<int:secao_id>/upload-imagem/',
    views.UploadImagemSecaoView.as_view(),
    name='upload_imagem_secao',
),
