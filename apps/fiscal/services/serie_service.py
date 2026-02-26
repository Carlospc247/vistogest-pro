# apps/fiscal/services/serie_service.py
from django.utils import timezone
from apps.core.models import ContadorDocumento
from django.core.exceptions import ValidationError

class SerieFiscalService:
    """
    Controlador de Séries Fiscais SOTARQ.
    Garante que cada ano fiscal tenha sua numeração independente.
    Referência: Decreto Executivo n.º 149/19 (Regras de Faturação).
    """

    @staticmethod
    def obter_proximo_numero(empresa, tipo_documento):
        """
        Retorna o próximo número sequencial garantindo o reset anual.
        Ex: FR 2026/1, FR 2026/2...
        """
        ano_atual = timezone.now().year
        
        # 1. Busca o contador para o ano vigente e tipo de documento
        contador, created = ContadorDocumento.objects.get_or_create(
            empresa=empresa,
            tipo_documento=tipo_documento,
            ano=ano_atual,
            defaults={'sequencia': 0, 'serie': f'S{ano_atual}'}
        )

        # 2. Incremento Atómico via F() expression para evitar race conditions
        # Ref: Documentação Django "Avoiding race conditions using F()"
        from django.db.models import F
        ContadorDocumento.objects.filter(id=contador.id).update(sequencia=F('sequencia') + 1)
        
        # 3. Recupera valor atualizado
        contador.refresh_from_db()
        
        # 4. Formata conforme padrão AGT: TIPO SERIE/ANO/NUMERO
        # Exemplo: FR S2026/2026/1
        return {
            "numero": f"{tipo_documento} {contador.serie}/{contador.ano}/{contador.sequencia}",
            "sequencia": contador.sequencia,
            "serie": contador.serie
        }

    @staticmethod
    def validar_transicao_ano(empresa):
        """
        Verifica se há contadores do ano anterior que não foram fechados
        ou se o sistema precisa de novas séries AGT.
        """
        ano_anterior = timezone.now().year - 1
        pendentes = ContadorDocumento.objects.filter(
            empresa=empresa, 
            ano=ano_anterior
        ).exists()
        
        if pendentes:
            # Lógica para auditoria de fecho de ano
            pass