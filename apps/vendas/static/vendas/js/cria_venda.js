// apps/vendas/static/vendas/js/cria_venda.js

// Variável global para rastrear os IDs dos itens do produto (simplificação)
let itemIdCounter = 0;

// URL base da sua API
const API_URL = '/api/v1/vendas/'; 

// Assumimos que o token CSRF está disponível globalmente (padrão Django)
const CSRF_TOKEN = document.querySelector('[name=csrfmiddlewaretoken]').value; 

// --- 1. Funções de Suporte do DOM ---

function adicionarItem() {
    itemIdCounter++;
    const container = document.getElementById('itens-container');
    const novoItem = document.createElement('div');
    novoItem.id = `item-${itemIdCounter}`;
    novoItem.innerHTML = `
        <hr>
        <label>Produto ID:</label>
        <input type="number" class="item-produto-id" value="1" required style="width: 50px;">
        
        <label>Qtd:</label>
        <input type="number" class="item-quantidade" value="1" min="1" required style="width: 50px;">
        
        <label>Preço Unitário:</label>
        <input type="number" class="item-preco" value="100.00" step="0.01" required style="width: 80px;">
        
        <label>Desc.:</label>
        <input type="number" class="item-desconto" value="0.00" step="0.01" style="width: 50px;">
        
        <button type="button" onclick="removerItem(${itemIdCounter})">X</button>
    `;
    container.appendChild(novoItem);
}

function removerItem(id) {
    document.getElementById(`item-${id}`).remove();
}

function getItensVenda() {
    const itens = [];
    // Itera sobre todos os contentores de itens para construir a lista
    document.querySelectorAll('#itens-container > div').forEach(itemDiv => {
        const id = itemDiv.querySelector('.item-produto-id').value;
        const qtd = itemDiv.querySelector('.item-quantidade').value;
        const preco = itemDiv.querySelector('.item-preco').value;
        const desconto = itemDiv.querySelector('.item-desconto').value;

        if (id && qtd && preco) {
            itens.push({
                produto_id: parseInt(id),
                quantidade: parseFloat(qtd),
                preco_unitario: parseFloat(preco),
                desconto_item: parseFloat(desconto)
            });
        }
    });
    return itens;
}

// --- 2. Lógica de Submissão e Comunicação com a API ---

async function submeterVenda(event) {
    event.preventDefault();
    document.getElementById('feedback-erro').textContent = '';
    document.getElementById('btn-finalizar').disabled = true;

    // 1. Coletar Dados
    const itens = getItensVenda();
    
    if (itens.length === 0) {
        alert("Adicione pelo menos um item à venda.");
        document.getElementById('btn-finalizar').disabled = false;
        return;
    }
    
    const vendaData = {
        empresa: document.getElementById('empresa_id').value || null,
        cliente: document.getElementById('cliente_id').value || null,
        forma_pagamento: document.getElementById('forma_pagamento_id').value,
        tipo_venda: 'FR', // Fatura Recibo, o código AGT
        itens: itens
        // O restante dos totais (total, iva_valor, hash, atcud) é calculado e gerado pelo Backend.
    };

    // 2. Chamar a API (Fetch Assíncrono)
    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN // Segurança Django
            },
            body: JSON.stringify(vendaData)
        });

        // 3. Tratar a Resposta
        const data = await response.json();

        if (response.ok) {
            // SUCESSO: Documento assinado e salvo!
            
            // Apresentar os dados CRÍTICOS ao operador:
            document.getElementById('display-numero').textContent = data.documento.numero_documento;
            document.getElementById('display-atcud').textContent = data.documento.atcud;
            document.getElementById('display-hash').textContent = data.documento.hash_documento;
            
            document.getElementById('resultado-fiscal').style.display = 'block';
            document.getElementById('venda-form').reset(); // Limpa o formulário após o sucesso
            document.getElementById('itens-container').innerHTML = ''; // Limpa os itens

            // Ação de Logística: Imprimir o documento (chamada a outra função)
            console.log(`Documento ${data.documento.numero_documento} pronto para impressão.`);

        } else {
            // ERRO: Erro de validação do Serializer ou Erro CRÍTICO do Service Fiscal
            const errorMessage = data.message || JSON.stringify(data.itens || data);
            document.getElementById('feedback-erro').textContent = `Falha na Emissão: ${errorMessage}`;
            console.error("Erro da API:", data);
        }

    } catch (error) {
        document.getElementById('feedback-erro').textContent = `Erro de Conexão: O servidor não respondeu. ${error.message}`;
        console.error("Erro de Rede ou Conexão:", error);
    } finally {
        document.getElementById('btn-finalizar').disabled = false;
    }
}

// Inicialização: Anexar o listener ao formulário
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('venda-form').addEventListener('submit', submeterVenda);
    // Adiciona um item inicial para começar
    adicionarItem(); 
});
