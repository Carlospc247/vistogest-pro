# script para sincronizar o banco
# fix_content_types.py
import os
import django
from django.contrib.contenttypes.models import ContentType

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pharmassys.settings.development')
django.setup()

def fix_types():
    print("Limpando ContentTypes órfãos...")
    ContentType.objects.filter(app_label='core', model__in=['empresa', 'domain', 'loja']).delete()
    print("Rigor aplicado. ContentTypes sincronizados.")

if __name__ == "__main__":
    fix_types()