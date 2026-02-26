import pandas as pd
from django.core.management.base import BaseCommand
from apps.empresas.models import Categoria


class Command(BaseCommand):
    help = 'Exporta categorias para Excel'

    def handle(self, *args, **options):
        qs = Categoria.objects.all()
        exportar_categorias_excel(qs)
        self.stdout.write(self.style.SUCCESS("Categorias exportadas com sucesso!"))


import pandas as pd

def exportar_categorias_excel(qs):
    # Converte QuerySet em lista de dicionários
    data = list(qs.values("id", "nome", "codigo", "descricao", "ativa"))

    # Cria DataFrame
    df = pd.DataFrame(data)

    # Define caminho de saída
    caminho_arquivo = "categorias.xlsx"

    # Exporta para Excel
    df.to_excel(caminho_arquivo, index=False, engine="openpyxl")

    return caminho_arquivo

