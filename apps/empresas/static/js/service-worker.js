// Service Worker para funcionalidades offline - vistoGEST
const CACHE_NAME = 'visto-gest-v1.2.0';
const OFFLINE_URL = '/offline/';

// Recursos essenciais para cache
const ESSENTIAL_RESOURCES = [
    '/',
    '/dashboard/',
    '/static/css/dashboard.css',
    '/static/js/dashboard.js',
    '/static/js/pdv-avancado.js',
    '/offline/',
    // Adicionar mais recursos essenciais
];

// Recursos do PDV para funcionamento offline
const PDV_RESOURCES = [
    '/pdv/',
    '/static/js/pdv-offline.js',
    '/ajax/produtos/search/',
    '/ajax/formas-pagamento/',
];

// APIs que devem ser interceptadas para funcionamento offline
const API_ROUTES = [
    '/ajax/produtos/search/',
    '/ajax/vendas/nova/',
    '/ajax/dashboard/',
    '/relatorios/vendas/dados/',
];

// Instalar Service Worker
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('Cacheando recursos essenciais...');
            return cache.addAll(ESSENTIAL_RESOURCES);
        }).then(() => {
            return self.skipWaiting();
        })
    );
});

// Ativar Service Worker
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Removendo cache antigo:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});

// Interceptar requisições
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);
    
    // Estratégia: Cache First para recursos estáticos
    if (isStaticResource(event.request)) {
        event.respondWith(cacheFirst(event.request));
        return;
    }
    
    // Estratégia: Network First para APIs
    if (isApiRoute(url.pathname)) {
        event.respondWith(networkFirstWithOfflineSupport(event.request));
        return;
    }
    
    // Estratégia: Stale While Revalidate para páginas
    if (isPageRequest(event.request)) {
        event.respondWith(staleWhileRevalidate(event.request));
        return;
    }
    
    // Estratégia padrão: Network First
    event.respondWith(networkFirst(event.request));
});

// Estratégias de cache
async function cacheFirst(request) {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const networkResponse = await fetch(request);
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, networkResponse.clone());
        return networkResponse;
    } catch (error) {
        console.log('Falha na rede para recurso estático:', request.url);
        return new Response('Recurso não disponível offline', { status: 503 });
    }
}

async function networkFirst(request) {
    try {
        const networkResponse = await fetch(request);
        
        // Cachear resposta se for bem-sucedida
        if (networkResponse.ok) {
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
            return cachedResponse;
        }
        
        // Retornar página offline para navegação
        if (isPageRequest(request)) {
            return caches.match(OFFLINE_URL);
        }
        
        return new Response('Não disponível offline', { status: 503 });
    }
}

async function networkFirstWithOfflineSupport(request) {
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            // Armazenar dados para uso offline
            const data = await networkResponse.clone().json();
            await storeOfflineData(request.url, data);
            
            const cache = await caches.open(CACHE_NAME);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('Requisição offline para:', request.url);
        
        // Tentar dados offline
        const offlineData = await getOfflineData(request.url);
        if (offlineData) {
            return new Response(JSON.stringify(offlineData), {
                headers: { 'Content-Type': 'application/json' }
            });
        }
        
        // Retornar resposta de erro estruturada
        return new Response(JSON.stringify({
            success: false,
            error: 'Dados não disponíveis offline',
            offline: true
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

async function staleWhileRevalidate(request) {
    const cachedResponse = await caches.match(request);
    
    const fetchPromise = fetch(request).then(networkResponse => {
        if (networkResponse.ok) {
            const cache = caches.open(CACHE_NAME);
            cache.then(c => c.put(request, networkResponse.clone()));
        }
        return networkResponse;
    }).catch(() => cachedResponse);
    
    return cachedResponse || fetchPromise;
}

// Funções auxiliares
function isStaticResource(request) {
    const url = new URL(request.url);
    return url.pathname.includes('/static/') || 
           url.pathname.includes('/media/') ||
           url.pathname.endsWith('.css') ||
           url.pathname.endsWith('.js') ||
           url.pathname.endsWith('.png') ||
           url.pathname.endsWith('.jpg') ||
           url.pathname.endsWith('.svg');
}

function isApiRoute(pathname) {
    return API_ROUTES.some(route => pathname.includes(route));
}

function isPageRequest(request) {
    return request.mode === 'navigate' ||
           (request.method === 'GET' && request.headers.get('accept').includes('text/html'));
}

// Armazenamento offline usando IndexedDB
async function storeOfflineData(url, data) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['data'], 'readwrite');
            const store = transaction.objectStore('data');
            
            store.put({
                url: url,
                data: data,
                timestamp: Date.now()
            });
            
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
        };
        
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains('data')) {
                const store = db.createObjectStore('data', { keyPath: 'url' });
                store.createIndex('timestamp', 'timestamp', { unique: false });
            }
            
            if (!db.objectStoreNames.contains('vendas_offline')) {
                const store = db.createObjectStore('vendas_offline', { keyPath: 'id', autoIncrement: true });
                store.createIndex('timestamp', 'timestamp', { unique: false });
                store.createIndex('synced', 'synced', { unique: false });
            }
            
            if (!db.objectStoreNames.contains('produtos_cache')) {
                const store = db.createObjectStore('produtos_cache', { keyPath: 'id' });
                store.createIndex('codigo_barras', 'codigo_barras', { unique: false });
                store.createIndex('nome', 'nome_comercial', { unique: false });
            }
        };
    });
}

async function getOfflineData(url) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['data'], 'readonly');
            const store = transaction.objectStore('data');
            const getRequest = store.get(url);
            
            getRequest.onsuccess = () => {
                const result = getRequest.result;
                if (result && (Date.now() - result.timestamp) < 24 * 60 * 60 * 1000) { // 24 horas
                    resolve(result.data);
                } else {
                    resolve(null);
                }
            };
            
            getRequest.onerror = () => resolve(null);
        };
    });
}

// Sincronização em background
self.addEventListener('sync', event => {
    if (event.tag === 'sync-vendas-offline') {
        event.waitUntil(syncOfflineSales());
    } else if (event.tag === 'sync-data-cache') {
        event.waitUntil(syncDataCache());
    }
});

async function syncOfflineSales() {
    console.log('Sincronizando vendas offline...');
    
    const vendas = await getOfflineSales();
    
    for (const venda of vendas) {
        try {
            const response = await fetch('/ajax/vendas/sync-offline/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': await getCSRFToken(),
                },
                body: JSON.stringify(venda.data)
            });
            
            if (response.ok) {
                await markSaleAsSynced(venda.id);
                console.log('Venda sincronizada:', venda.id);
            }
        } catch (error) {
            console.error('Erro ao sincronizar venda:', error);
        }
    }
}

async function syncDataCache() {
    console.log('Sincronizando cache de dados...');
    
    try {
        // Atualizar cache de produtos
        const response = await fetch('/ajax/produtos/cache-offline/');
        if (response.ok) {
            const produtos = await response.json();
            await updateProductsCache(produtos);
        }
        
        // Atualizar outras caches necessárias
        await updateFormasPagamentoCache();
        await updateClientesCache();
        
    } catch (error) {
        console.error('Erro ao sincronizar cache:', error);
    }
}

// Funções auxiliares para IndexedDB
async function getOfflineSales() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['vendas_offline'], 'readonly');
            const store = transaction.objectStore('vendas_offline');
            const index = store.index('synced');
            const getRequest = index.getAll(false);
            
            getRequest.onsuccess = () => resolve(getRequest.result);
            getRequest.onerror = () => reject(getRequest.error);
        };
    });
}

async function markSaleAsSynced(saleId) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['vendas_offline'], 'readwrite');
            const store = transaction.objectStore('vendas_offline');
            const getRequest = store.get(saleId);
            
            getRequest.onsuccess = () => {
                const venda = getRequest.result;
                if (venda) {
                    venda.synced = true;
                    store.put(venda);
                }
                resolve();
            };
        };
    });
}

async function updateProductsCache(produtos) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['produtos_cache'], 'readwrite');
            const store = transaction.objectStore('produtos_cache');
            
            // Limpar cache antigo
            store.clear();
            
            // Adicionar novos produtos
            produtos.forEach(produto => {
                store.put(produto);
            });
            
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
        };
    });
}

async function getCSRFToken() {
    try {
        const response = await fetch('/ajax/csrf-token/');
        const data = await response.json();
        return data.token;
    } catch (error) {
        console.error('Erro ao obter CSRF token:', error);
        return '';
    }
}

// Mensagens para a aplicação principal
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    } else if (event.data && event.data.type === 'STORE_OFFLINE_SALE') {
        storeOfflineSale(event.data.sale);
    } else if (event.data && event.data.type === 'REQUEST_SYNC') {
        // Solicitar sincronização
        self.registration.sync.register('sync-vendas-offline');
    }
});

async function storeOfflineSale(saleData) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VistoGestOffline', 1);
        
        request.onsuccess = () => {
            const db = request.result;
            const transaction = db.transaction(['vendas_offline'], 'readwrite');
            const store = transaction.objectStore('vendas_offline');
            
            store.add({
                data: saleData,
                timestamp: Date.now(),
                synced: false
            });
            
            transaction.oncomplete = () => {
                console.log('Venda armazenada offline');
                resolve();
            };
            transaction.onerror = () => reject(transaction.error);
        };
    });
}

// Notificações para o usuário
function notifyUser(message, type = 'info') {
    self.registration.showNotification('vistoGEST', {
        body: message,
        icon: '/static/icons/icon-192.png',
        badge: '/static/icons/badge-72.png',
        tag: `notification-${type}`,
        actions: [
            {
                action: 'view',
                title: 'Ver Detalhes'
            }
        ]
    });
}

// Manter conexão viva
setInterval(() => {
    fetch('/ajax/ping/', { method: 'HEAD' }).catch(() => {
        // Conexão perdida - modo offline ativo
    });
}, 30000); // Check a cada 30 segundos