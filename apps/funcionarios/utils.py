# apps/funcionarios/utils.pya
from django.utils import timezone
from apps.funcionarios.models import RegistroPonto

def funcionario_tem_turno_aberto(funcionario):
    """Retorna True se o funcionário tem turno aberto (entrada sem saída)."""

    ultimo = RegistroPonto.objects.filter(
        funcionario=funcionario,
        data_registro=timezone.localdate()
    ).order_by('-data_registro', '-hora_registro').first()

    if not ultimo:
        return False

    # Se o último registro for ENTRADA → turno aberto
    return ultimo.tipo_registro in ['entrada', 'volta_almoco', 'entrada_extra']
