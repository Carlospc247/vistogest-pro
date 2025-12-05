import os
import django
from django.conf import settings
from django.test import RequestFactory
from django.urls import reverse, resolve

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings')
django.setup()

from apps.vendas.views import fatura_credito_pdf_view
from apps.produtos.views import listar_categorias_api
# from apps.core.views import error_report # This might not exist yet

def test_categorias_api():
    print("Testing /produtos/api/categorias/ ...")
    factory = RequestFactory()
    request = factory.get('/produtos/api/categorias/')
    
    # Mock user/empresa if needed (views usually require login)
    from django.contrib.auth.models import User, AnonymousUser
    from apps.core.models import Empresa
    
    # Create dummy user/empresa if not exists
    empresa, _ = Empresa.objects.get_or_create(nome="Test Company", nif="999999999")
    user = User.objects.create_user(username='testuser', password='password')
    user.empresa = empresa
    user.save()
    
    request.user = user
    
    try:
        response = listar_categorias_api(request)
        print(f"Response Code: {response.status_code}")
    except Exception as e:
        print(f"CRASH: {e}")

def test_fatura_pdf():
    print("\nTesting /vendas/faturas-credito/<id>/pdf/a4/ ...")
    # Need a FaturaCredito instance
    from apps.vendas.models import FaturaCredito
    fatura = FaturaCredito.objects.first()
    if not fatura:
        print("No FaturaCredito found. Skipping.")
        return

    factory = RequestFactory()
    request = factory.get(f'/vendas/faturas-credito/{fatura.id}/pdf/a4/')
    request.user = User.objects.first() # Reuse user
    
    try:
        response = fatura_credito_pdf_view(request, fatura.id, 'a4')
        print(f"Response Code: {response.status_code}")
    except Exception as e:
        print(f"CRASH: {e}")

if __name__ == "__main__":
    try:
        test_categorias_api()
        test_fatura_pdf()
    except Exception as e:
        print(f"Setup failed: {e}")
