# apps/produtos/api_views.py
from django.http import JsonResponse
from apps.empresas.models import Categoria

def categorias_api(request):
    user_empresa = request.user.empresa
    if not user_empresa:
        return JsonResponse({'error': 'Usuário sem empresa associada.'}, status=400)
    
    categorias = Categoria.objects.filter(empresa=user_empresa, ativa=True).order_by('nome')
    data = [{'id': c.id, 'nome': c.nome} for c in categorias]
    return JsonResponse(data, safe=False)#
