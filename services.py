# apps/core/services.py
from django.db import transaction
from django.utils import timezone
from apps.fiscal.models import ContadorDocumento

def gerar_numero_documento(empresa, tipo_documento, serie='A'):
    """
    Gera o número oficial conforme o modelo DocumentoFiscal.
    Formato exigido: TIPO SERIE/NUMERO
    Exemplo: FR A/1, FT A/2, REC A/1
    """
    ano_atual = timezone.now().year

    with transaction.atomic():
        # select_for_update() bloqueia a linha para evitar duplicidade no PDV
        contador, created = ContadorDocumento.objects.select_for_update().get_or_create(
            empresa=empresa,
            tipo_documento=tipo_documento,
            ano=ano_atual,
            serie=serie,
            defaults={'ultimo_numero': 0}
        )

        contador.ultimo_numero += 1
        contador.save()

        # Montagem rigorosa conforme o campo 'numero_documento' do seu modelo fiscal
        # Formato: TIPO SERIE/NUMERO (Ex: FR A/1)
        numero_final = f"{tipo_documento} {contador.serie}/{contador.ultimo_numero}"

        # Retornamos um dicionário para que o model fiscal preencha os campos 'numero' e 'numero_documento'
        return {
            'sequencial': contador.ultimo_numero,
            'formatado': numero_final
        }

