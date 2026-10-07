// static/js/printer.js
class PrinterManager {
    constructor() {
        this.impressoras = [];
        this.loadImpressoras();
    }
    
    async loadImpressoras() {
        try {
            const response = await fetch('/documentos/listar-impressoras/');
            this.impressoras = await response.json();
        } catch (error) {
            console.error('Erro ao carregar impressoras:', error);
        }
    }
    
    async imprimirDocumento(documentoId, impressoraId = null) {
        try {
            const response = await fetch('/documentos/imprimir/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    documento_id: documentoId,
                    impressora_id: impressoraId
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification('Documento impresso com sucesso!', 'success');
                return true;
            } else {
                this.showNotification(`Erro na impressão: ${result.error}`, 'error');
                return false;
            }
            
        } catch (error) {
            this.showNotification('Erro de comunicação com a impressora', 'error');
            return false;
        }
    }
    
    async abrirGaveta(impressoraId) {
        try {
            const response = await fetch('/documentos/abrir-gaveta/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    impressora_id: impressoraId
                })
            });
            
            const result = await response.json();
            return result.success;
            
        } catch (error) {
            console.error('Erro ao abrir gaveta:', error);
            return false;
        }
    }
    
    showNotification(message, type) {
        // Implementar sistema de notificações
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
}

// Instância global
const printerManager = new PrinterManager();

// Funções de conveniência
function imprimirVenda(vendaId) {
    // Gerar documento e imprimir
    fetch('/documentos/gerar/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            venda_id: vendaId,
            tipo_documento_id: 1 // NFC-e
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            printerManager.imprimirDocumento(result.documento_id);
        }
    });
}

function imprimirRecibo(vendaId) {
    // Gerar recibo e imprimir
    fetch('/documentos/gerar/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            venda_id: vendaId,
            tipo_documento_id: 3 // Recibo
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            printerManager.imprimirDocumento(result.documento_id);
        }
    });
}