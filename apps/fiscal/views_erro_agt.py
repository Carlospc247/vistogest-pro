# apps/fiscal/views_erro_agt.py

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404

from apps.vendas.models import Venda



# apps/fiscal/views.py

def detalhe_erro_venda(request, venda_id):
    """
    Retorna os detalhes técnicos da rejeição da AGT.
    Substituído get_object_or_404 por tratamento manual para não quebrar o AJAX.
    """
    empresa = request.user.empresa
    
    try:
        # Filtro rigoroso por ID e Empresa (Multi-tenant)
        venda = Venda.objects.get(id=venda_id, empresa=empresa)
        
        erros = venda.metadados.get('erros_agt', [])
        request_id = venda.metadados.get('request_id_agt', 'N/A')

        if not erros and venda.status == 'cancelled':
            erros = [{
                "errorCode": "INFO", 
                "errorDescription": "O documento foi cancelado, mas a AGT não retornou detalhes específicos."
            }]

        return JsonResponse({
            "success": True,
            "numero_documento": venda.numero_documento,
            "request_id": request_id,
            "erros": erros
        })

    except Venda.DoesNotExist:
        # DECISÃO TÉCNICA: Em vez de 404 HTML, retornamos 200 com success: False
        # Isso permite que o seu JavaScript trate o erro e mostre um alerta no Modal.
        logger.warning(f"Tentativa de acesso a venda inexistente ou de outro tenant: ID {venda_id}")
        return JsonResponse({
            "success": False,
            "error": "Documento não encontrado ou acesso negado."
        }, status=200) # Mantemos 200 para o Fetch não 'estourar', tratamos no JSON

