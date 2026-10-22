quero saber porquê as notificações estão a dar Forbidden (erro 403)
 e garanta que as notificações sejam encontradas e estejam bem implementadas e sem erros e inconsistências.

[2026-10-17 09:46:12,608] WARNING django.request: Forbidden: /ajax/notifications/count/
[2026-10-17 09:46:12,608] WARNING django.request: Forbidden: /ajax/notifications/count/
[2026-10-17 09:46:12,610] WARNING django.server: "GET /ajax/notifications/count/ HTTP/1.1" 403 46
[2026-10-17 09:46:12,610] WARNING django.server: "GET /ajax/notifications/count/ HTTP/1.1" 403 46

<!-- templates/base.html -->
{% load static %}
<!DOCTYPE html>
<html lang="pt-AO" class="h-full {% if interface_prefs.tema == 'dark' or interface_prefs.tema == 'escuro' %}dark{% endif %}" data-server-theme="{% if interface_prefs.tema == 'dark' or interface_prefs.tema == 'escuro' %}dark{% elif interface_prefs.tema == 'system' or interface_prefs.tema == 'sistema' %}system{% else %}light{% endif %}" data-theme="{% if interface_prefs.tema == 'dark' or interface_prefs.tema == 'escuro' %}dark{% else %}light{% endif %}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <script>
    /* Tema essencial: corre antes do primeiro paint, sem Alpine, Tailwind ou Internet.
       É a ÚNICA fonte de verdade do tema; o Alpine só reflete o estado (evento vg-theme-change). */
    (function () {
        'use strict';
        var root = document.documentElement;
        var validThemes = ['light', 'dark', 'system'];
        var preference = root.getAttribute('data-server-theme') || 'light';

        function normalise(value) {
            value = String(value || 'light').trim().toLowerCase();
            if (value === 'dark' || value === 'escuro') return 'dark';
            if (value === 'system' || value === 'sistema') return 'system';
            return 'light';
        }
        function apply(value) {
            preference = normalise(value);
            var isDark = preference === 'dark' ||
                (preference === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
            root.classList.toggle('dark', !!isDark);
            root.setAttribute('data-theme', isDark ? 'dark' : 'light');
            root.setAttribute('data-theme-preference', preference);
        }
        function readStore() {
            try {
                var s = JSON.parse(window.localStorage.getItem('app-preferences') || '{}');
                return (s && typeof s === 'object' && !Array.isArray(s)) ? s : {};
            } catch (_) { return {}; }
        }

        var saved = readStore();
        if (validThemes.indexOf(saved.themePreference) !== -1) preference = saved.themePreference;

        window.__vistoGestSetTheme = function (value) {
            var next = normalise(value);
            apply(next);
            try {
                var s = readStore();
                s.themePreference = next;
                window.localStorage.setItem('app-preferences', JSON.stringify(s));
            } catch (_) { /* a alteração visual continua a funcionar sem armazenamento */ }
            document.dispatchEvent(new CustomEvent('vg-theme-change', { detail: { preference: next } }));
        };

        apply(preference);

        if (window.matchMedia) {
            var query = window.matchMedia('(prefers-color-scheme: dark)');
            var systemChanged = function () {
                if (root.getAttribute('data-theme-preference') === 'system') apply('system');
            };
            if (query.addEventListener) query.addEventListener('change', systemChanged);
            else if (query.addListener) query.addListener(systemChanged);
        }
        /* Botões com data-theme-choice funcionam mesmo se o Alpine falhar a carregar. */
        document.addEventListener('click', function (event) {
            var choice = event.target && event.target.closest ? event.target.closest('[data-theme-choice]') : null;
            if (choice) window.__vistoGestSetTheme(choice.getAttribute('data-theme-choice'));
        });
    })();
    </script>

    <meta name="csrf-token" content="{{ csrf_token }}">
    <meta name="description" content="vistoGEST - Vistoria e Gestão Estratégica">
    <title>{% block title %}vistoGEST{% endblock %} | Sistema de Gestão</title>

    <!-- Favicon -->
    <link rel="icon" type="image/png" href="{% static 'img/logo.png' %}?v=2">
    <link rel="apple-touch-icon" href="{% static 'img/logo.png' %}">

    <!-- PWA -->
    {% url 'core:pwa_manifest' as PWA_MANIFEST_URL %}
    {% if PWA_MANIFEST_URL %}<link rel="manifest" href="{{ PWA_MANIFEST_URL }}">{% endif %}
    <meta name="theme-color" content="{{ interface_prefs.cor_primaria|default:'#5D5CDE' }}">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="VistoGEST">

    <!-- CSS local: Tailwind compilado (build) + Font Awesome + estilos da base.
         A ordem importa: vistogest-base.css vem depois do Tailwind. -->
    <link rel="preload" href="{% static 'vendor/fontawesome/webfonts/fa-solid-900.woff2' %}" as="font" type="font/woff2" crossorigin>
    <link rel="stylesheet" href="{% static 'css/tailwind.css' %}">
    <link rel="stylesheet" href="{% static 'vendor/fontawesome/css/all.min.css' %}">
    <link rel="stylesheet" href="{% static 'css/vistogest-base.css' %}">
    <style>:root { --vg-primary: {{ interface_prefs.cor_primaria|default:'#5D5CDE' }}; }</style>

    <!-- Alpine: defer, local e com versão fixa -->
    <script defer src="{% static 'vendor/alpine/alpine.min.js' %}"></script>

    {# Bibliotecas pesadas (Chart.js, jQuery, Select2): só nas páginas que as pedem, via block vendor_libs. #}
    {% block vendor_libs %}{% endblock %}

    {% block extra_css %}{% endblock %}
</head>

<body class="app-shell h-screen overflow-hidden"
      x-data="appData('{% if interface_prefs.tema == 'dark' or interface_prefs.tema == 'escuro' %}dark{% elif interface_prefs.tema == 'system' or interface_prefs.tema == 'sistema' %}system{% else %}light{% endif %}')"
      x-init="initApp()"
      @keydown.window.ctrl.b.prevent="toggleSidebar()"
      @keydown.window.meta.b.prevent="toggleSidebar()"
      @keydown.window.ctrl.d.prevent="toggleDarkMode()"
      @keydown.window.meta.d.prevent="toggleDarkMode()"
      @keydown.window.escape="isMobile && sidebarOpen && closeSidebar()"
      :class="{ 'sidebar-open': sidebarOpen }">

    <!-- Loading Overlay (JS nativo, sem dependência de Alpine/CDN) -->
    <div id="loading-overlay" class="loading-overlay gradient-overlay-bg" role="status" aria-live="polite" aria-atomic="true" aria-hidden="true">
        <svg class="loading-overlay__spinner" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
            <circle style="opacity:.25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path style="opacity:.75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>Carregando...</span>
        <p id="loading-overlay-detail" class="loading-status-detail" hidden></p>
    </div>

    <script>
    /* Gestor de carregamento: mostra durante navegações/submissões reais, sem timeout fixo.
       Para excluir um link/formulário use data-no-loading. */
    (function () {
        'use strict';
        var overlay = document.getElementById('loading-overlay');
        var detail = document.getElementById('loading-overlay-detail');
        if (!overlay) return;
        var DOWNLOAD_RE = /\.(pdf|xlsx?|csv|zip|xml|docx?|txt|json)(\?|#|$)/i;

        function setVisible(visible, message) {
            overlay.classList.toggle('is-visible', !!visible);
            overlay.setAttribute('aria-hidden', visible ? 'false' : 'true');
            document.documentElement.setAttribute('aria-busy', visible ? 'true' : 'false');
            if (detail) {
                detail.textContent = message || '';
                detail.hidden = !message;
            }
            var app = window.__vistoGestApp;
            if (app && app.loading !== !!visible) app.loading = !!visible;
        }
        window.showLoadingOverlay = function (message) { setVisible(true, message); };
        window.hideLoadingOverlay = function () { setVisible(false, ''); };

        function sameOriginNavigation(link) {
            if (!link || link.hasAttribute('download') || link.hasAttribute('data-no-loading')) return false;
            if (link.target && link.target.toLowerCase() !== '_self') return false;
            var raw = (link.getAttribute('href') || '').trim();
            if (!raw || raw === '#' || raw.toLowerCase().indexOf('javascript:') === 0) return false;
            if (DOWNLOAD_RE.test(raw)) return false;
            try {
                var target = new URL(raw, window.location.href);
                if (target.origin !== window.location.origin) return false;
                if (target.pathname === window.location.pathname && target.search === window.location.search && target.hash) return false;
                return true;
            } catch (_) { return false; }
        }

        document.addEventListener('click', function (event) {
            if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            var element = event.target;
            var link = element && element.closest ? element.closest('a[href]') : null;
            if (link && sameOriginNavigation(link)) {
                setVisible(navigator.onLine !== false, '');
                return;
            }
            var trigger = element && element.closest ? element.closest('[data-loading-trigger]') : null;
            if (trigger && !trigger.disabled) {
                setVisible(true, trigger.getAttribute('data-loading-message') || 'A operação está a ser processada.');
            }
        }, false);

        document.addEventListener('submit', function (event) {
            if (event.defaultPrevented) return;
            var form = event.target;
            if (!form || form.hasAttribute('data-no-loading')) return;
            var target = (form.getAttribute('target') || '').toLowerCase();
            var method = (form.getAttribute('method') || 'get').toLowerCase();
            if ((target && target !== '_self') || method === 'dialog') return;
            setVisible(navigator.onLine !== false, '');
        }, false);

        window.addEventListener('pageshow', function () { setVisible(false, ''); });
        window.addEventListener('offline', function () { setVisible(false, ''); });

        /* Contrato para AJAX: show antes da operação, hide no finally. */
        window.withLoadingOverlay = async function (operation, message) {
            setVisible(true, message || 'A operação está a ser processada.');
            try { return await operation(); }
            finally { setVisible(false, ''); }
        };
    })();
    </script>

    <!-- Overlay para fechar a sidebar no mobile -->
    <div x-show="sidebarOpen && isMobile" x-cloak @click="closeSidebar()"
         x-transition:enter="ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100"
         x-transition:leave="ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0"
         class="fixed inset-0 z-40 bg-black bg-opacity-50 lg:hidden"></div>

    <div class="flex h-full min-h-0">
        <!-- ===================== Sidebar ===================== -->
        <aside x-show="sidebarOpen" x-cloak
               x-transition:enter="ease-out duration-300"
               x-transition:enter-start="transform -translate-x-full"
               x-transition:enter-end="transform translate-x-0"
               x-transition:leave="ease-in duration-300"
               x-transition:leave-start="transform translate-x-0"
               x-transition:leave-end="transform -translate-x-full"
               :class="isMobile ? 'fixed inset-y-0 left-0 z-50' : 'sidebar-desktop'"
               class="vg-bar flex w-64 shrink-0 flex-col border-r">

            <!-- Logo + título: cor por token (índigo no claro, branco no escuro) -->
            <div class="vg-bar flex h-16 shrink-0 items-center justify-between border-b px-6">
                <a href="{% url 'core_tenants:dashboard' %}" class="flex min-w-0 items-center gap-3" aria-label="vistoGEST — página inicial">
                    {% if interface_prefs.logo_principal %}
                        <img class="h-9 w-auto max-w-28 object-contain" height="36" src="{{ interface_prefs.logo_principal }}" alt="Logótipo da empresa">
                    {% else %}
                        <img class="h-9 w-auto max-w-28 object-contain" height="36" src="{% static 'img/logo.png' %}" alt="vistoGEST">
                    {% endif %}
                    <span class="vg-brand truncate text-xl font-bold tracking-tight">vistoGEST</span>
                </a>

                <button @click="closeSidebar()" x-show="isMobile" type="button"
                        class="vg-text menu-button lg:hidden -m-2.5 rounded-md p-2.5">
                    <span class="sr-only">Fechar menu</span>
                    <i class="fas fa-times"></i>
                </button>
            </div>

            <!-- Navegação: um único @click fecha a sidebar no mobile ao clicar em qualquer link -->
            <nav class="sidebar-nav custom-scrollbar flex flex-1 flex-col overflow-y-auto p-4" aria-label="Navegação principal"
                 @click="if (isMobile && $event.target.closest('a[href]')) closeSidebar()">
                <ul role="list" class="flex flex-1 flex-col gap-y-1">

                    <!-- Dashboard -->
                    <li>
                        <a href="{% url 'core_tenants:dashboard' %}"
                           class="menu-item {% if request.resolver_match.namespace == 'core_tenants' and request.resolver_match.url_name == 'dashboard' or request.resolver_match.namespace == 'core' and request.resolver_match.url_name == 'dashboard' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-tachometer-alt menu-icon"></i>
                            Dashboard
                        </a>
                    </li>

                    {% if user.is_superuser %}
                    {% url 'core:plano_bypass' as PLANO_BYPASS_URL %}
                    <li class="menu-section-label" aria-hidden="true">Administração Global – Dívidas</li>
                    <li>
                        <a href="{{ PLANO_BYPASS_URL|default:'#' }}"
                           class="menu-item menu-cta {% if current_module == 'plano_bypass' %}menu-cta--active{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-gem menu-icon"></i>
                            <span>Elite Bypass (%%)</span>
                        </a>
                    </li>
                    {% endif %}

                    <!-- Vendas e Documentos (antes: 3 menus com links repetidos) -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'vendas' or 'fatura' in request.path or 'recibo' in request.path or 'proforma' in request.path or 'documento' in request.path or 'nota' in request.path or 'pdv' in request.path %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-file-invoice-dollar menu-icon"></i>
                            <span>Vendas e Documentos</span>
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            {% if connection.schema_name != 'public' %}
                            <li><a href="{% url 'vendas:documentos_dashboard' %}" class="menu-subitem"><i class="fas fa-chart-line menu-subicon"></i>Dashboard Documentos</a></li>
                            <li class="menu-divider"></li>
                            {% endif %}

                            <li class="menu-section-label">Vendas diretas (FR)</li>
                            <li><a href="{% url 'vendas:pdv' %}" class="menu-subitem"><i class="fas fa-cash-register menu-subicon"></i>PDV – Ponto de Venda</a></li>
                            <li><a href="{% url 'vendas:lista' %}" class="menu-subitem"><i class="fas fa-list menu-subicon"></i>Vendas</a></li>
                            <li><a href="{% url 'vendas:vendas_lista' %}" class="menu-subitem"><i class="fas fa-receipt menu-subicon"></i>Vendas Realizadas (FR)</a></li>
                            <li><a href="{% url 'vendas:faturas_recibo_lista' %}" class="menu-subitem"><i class="fas fa-receipt menu-subicon"></i>Faturas Recibo (FR)</a></li>

                            <li class="menu-divider"></li>
                            <li class="menu-section-label">Crédito e cobranças</li>
                            <li><a href="{% url 'vendas:faturas_credito_lista' %}" class="menu-subitem"><i class="fas fa-file-invoice menu-subicon"></i>Faturas a Crédito (FT)</a></li>
                            <li><a href="{% url 'vendas:recibos_lista' %}" class="menu-subitem"><i class="fas fa-money-check-alt menu-subicon"></i>Recibos (REC)</a></li>
                            {% if connection.schema_name != 'public' %}
                            <li><a href="{% url 'vendas:proformas_lista' %}" class="menu-subitem"><i class="fas fa-file-contract menu-subicon"></i>Proformas</a></li>
                            <li><a href="{% url 'vendas:contas_receber' %}" class="menu-subitem"><i class="fas fa-coins menu-subicon"></i>Contas a Receber</a></li>
                            {% endif %}

                            <li class="menu-divider"></li>
                            <li class="menu-section-label">Outros documentos fiscais</li>
                            <li><a href="{% url 'vendas:nota_credito_lista' %}" class="menu-subitem menu-subitem--grow">
                                <span class="flex items-center gap-x-2.5"><i class="fas fa-minus-circle menu-subicon"></i>Notas de Crédito</span>
                                <span class="menu-badge menu-badge--red">NC</span></a></li>
                            <li><a href="{% url 'vendas:nota_debito_lista' %}" class="menu-subitem menu-subitem--grow">
                                <span class="flex items-center gap-x-2.5"><i class="fas fa-plus-circle menu-subicon"></i>Notas de Débito</span>
                                <span class="menu-badge menu-badge--indigo">ND</span></a></li>
                            <li><a href="{% url 'vendas:documento_transporte_lista' %}" class="menu-subitem menu-subitem--grow">
                                <span class="flex items-center gap-x-2.5"><i class="fas fa-truck-moving menu-subicon"></i>Guias de Transporte</span>
                                <span class="menu-badge menu-badge--purple">GT</span></a></li>

                            {% if connection.schema_name != 'public' %}
                            <li class="menu-divider"></li>
                            <li class="menu-section-label">Criar</li>
                            <li><a href="{% url 'vendas:nova_fatura_credito' %}" class="menu-subitem"><i class="fas fa-plus-circle menu-subicon"></i>Nova Fatura Crédito</a></li>
                            <li><a href="{% url 'vendas:nova_proforma' %}" class="menu-subitem"><i class="fas fa-hand-holding-usd menu-subicon"></i>Nova Proforma</a></li>
                            {% endif %}
                        </ul>
                    </li>

                    <!-- Produtos / Serviços (CORRIGIDO: regime_empresa já não existe; o campo é "regime") -->
                    {% if request.tenant.regime == 'COMERCIO' or request.tenant.regime == 'SERVICOS' or request.tenant.regime == 'MISTO' %}
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'produtos' or request.resolver_match.namespace == 'servicos' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-box menu-icon"></i>
                            Produtos/Serviços
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'produtos:produto_list' %}" class="menu-subitem"><i class="fas fa-list menu-subicon"></i>Produtos</a></li>
                            {% url 'servicos:servico_dashboard' as SERVICOS_DASHBOARD_URL %}
                            {% if SERVICOS_DASHBOARD_URL %}
                            <li><a href="{{ SERVICOS_DASHBOARD_URL }}" class="menu-subitem"><i class="fas fa-concierge-bell menu-subicon"></i>Serviços</a></li>
                            {% endif %}
                            {# <li><a href="{% url 'servicos:servico_list' %}" class="menu-subitem"><i class="fas fa-hands-helping menu-subicon"></i>Serviços</a></li> #}
                            
                            <li><a href="{% url 'produtos:categoria_list' %}" class="menu-subitem"><i class="fas fa-tags menu-subicon"></i>Categorias</a></li>
                        </ul>
                    </li>

                    <!-- Estoque -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'estoque' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-warehouse menu-icon"></i>
                            Estoque
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'estoque:dashboard' %}" class="menu-subitem"><i class="fas fa-chart-bar menu-subicon"></i>Visão Geral</a></li>
                            <li><a href="{% url 'estoque:movimentacao_lista' %}" class="menu-subitem"><i class="fas fa-exchange-alt menu-subicon"></i>Movimentações</a></li>
                            <li><a href="{% url 'estoque:inventario_lista' %}" class="menu-subitem"><i class="fas fa-clipboard-list menu-subicon"></i>Inventário</a></li>
                        </ul>
                    </li>
                    {% endif %}

                    <!-- Clientes -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'clientes' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-users menu-icon"></i>
                            Clientes
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'clientes:dashboard' %}" class="menu-subitem"><i class="fas fa-list menu-subicon"></i>Clientes</a></li>
                        </ul>
                    </li>

                    <!-- Fornecedores -->
                    <li>
                        <a href="{% url 'fornecedores:lista' %}"
                           class="menu-item {% if request.resolver_match.namespace == 'fornecedores' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-truck menu-icon"></i>
                            Fornecedores
                        </a>
                    </li>

                    <!-- Funcionários -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'funcionarios' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-user-tie menu-icon"></i>
                            Funcionários
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'funcionarios:dashboard' %}" class="menu-subitem"><i class="fas fa-tachometer-alt menu-subicon"></i>Dashboard</a></li>
                            <li><a href="{% url 'funcionarios:funcionarios' %}" class="menu-subitem"><i class="fas fa-list menu-subicon"></i>Ver Funcionários</a></li>
                            <li><a href="{% url 'funcionarios:cargo_lista' %}" class="menu-subitem"><i class="fas fa-briefcase menu-subicon"></i>Ver Cargos</a></li>
                        </ul>
                    </li>

                    <!-- Financeiro -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'financeiro' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-dollar-sign menu-icon"></i>
                            Financeiro
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'financeiro:dashboard' %}" class="menu-subitem"><i class="fas fa-chart-line menu-subicon"></i>Visão Geral</a></li>
                            <li><a href="{% url 'financeiro:conta_receber_lista' %}" class="menu-subitem"><i class="fas fa-arrow-down menu-subicon text-green-500"></i>Contas a Receber</a></li>
                            <li><a href="{% url 'financeiro:conta_pagar_lista' %}" class="menu-subitem"><i class="fas fa-arrow-up menu-subicon text-red-500"></i>Contas a Pagar</a></li>
                            <li><a href="{% url 'financeiro:fluxo_caixa' %}" class="menu-subitem"><i class="fas fa-money-bill-wave menu-subicon"></i>Fluxo de Caixa</a></li>
                        </ul>
                    </li>

                    <!-- Relatórios -->
                    {% if perms.relatorios.view_relatorio %}
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'relatorios' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-chart-bar menu-icon"></i>
                            Relatórios
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'relatorios:dashboard' %}" class="menu-subitem"><i class="fas fa-tachometer-alt menu-subicon"></i>Dashboard</a></li>
                            <li><a href="{% url 'relatorios:vendas' %}" class="menu-subitem"><i class="fas fa-shopping-cart menu-subicon"></i>Vendas</a></li>
                            <li><a href="{% url 'relatorios:estoque' %}" class="menu-subitem"><i class="fas fa-warehouse menu-subicon"></i>Estoque</a></li>
                            <li><a href="{% url 'relatorios:financeiro' %}" class="menu-subitem"><i class="fas fa-dollar-sign menu-subicon"></i>Financeiro</a></li>
                        </ul>
                    </li>
                    {% endif %}

                    {# Módulos complementares: só aparecem quando as URLs estão registadas. #}
                    {% url 'analytics:dashboard' as ANALYTICS_DASHBOARD_URL %}
                    {% url 'compras:dashboard' as COMPRAS_DASHBOARD_URL %}
                    {% if ANALYTICS_DASHBOARD_URL or COMPRAS_DASHBOARD_URL %}
                    <li class="menu-section-label" aria-hidden="true">Gestão e análise</li>
                    {% endif %}
                    {% if ANALYTICS_DASHBOARD_URL %}
                    <li>
                        <a href="{{ ANALYTICS_DASHBOARD_URL }}"
                           class="menu-item {% if request.resolver_match.namespace == 'analytics' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-chart-line menu-icon"></i><span>Analytics</span>
                        </a>
                    </li>
                    {% endif %}
                    {% if COMPRAS_DASHBOARD_URL %}
                    <li>
                        <a href="{{ COMPRAS_DASHBOARD_URL }}"
                           class="menu-item {% if request.resolver_match.namespace == 'compras' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-shopping-basket menu-icon"></i><span>Compras</span>
                        </a>
                    </li>
                    {% endif %}

                    <!-- AGT e documentos -->
                    <li x-data="{ open: {% if request.resolver_match.namespace == 'fiscal' or request.resolver_match.namespace == 'saft' %}true{% else %}false{% endif %} }">
                        <button @click="open = !open" type="button"
                                class="menu-item menu-link group flex w-full items-center gap-x-3 rounded-md p-2 text-left text-sm leading-6 font-semibold">
                            <i class="fas fa-university menu-icon"></i>
                            AGT e documentos
                            <i class="fas fa-chevron-right ml-auto h-5 w-5 shrink-0 transition-transform" :class="open ? 'rotate-90' : ''"></i>
                        </button>
                        <ul x-show="open" x-cloak x-transition class="mt-1 px-2">
                            <li><a href="{% url 'fiscal:dashboard' %}" class="menu-subitem"><i class="fas fa-file-export menu-subicon"></i>Dashboard SAF-T</a></li>
                            <li><a href="{% url 'fiscal:retencoes-list' %}" class="menu-subitem"><i class="fas fa-file-code menu-subicon"></i>Retenções na Fonte</a></li>
                            <li><a href="{% url 'fiscal:relatorios' %}" class="menu-subitem"><i class="fas fa-file-contract menu-subicon"></i>Relatórios Fiscal</a></li>
                            <li><a href="{% url 'fiscal:configuracoes' %}" class="menu-subitem"><i class="fas fa-cog menu-subicon"></i>Configurações fiscais</a></li>

                            {% url 'saft:saft_export' as SAFT_EXPORT_URL %}
                            {% url 'saft:historico' as SAFT_HISTORY_URL %}
                            {% url 'saft:validar' as SAFT_VALIDATE_URL %}
                            {% if SAFT_EXPORT_URL or SAFT_HISTORY_URL or SAFT_VALIDATE_URL %}
                            <li class="menu-divider"></li>
                            <li class="menu-section-label">SAF-T (AO)</li>
                            {% if SAFT_EXPORT_URL %}<li><a href="{{ SAFT_EXPORT_URL }}" class="menu-subitem"><i class="fas fa-file-export menu-subicon"></i>Exportar SAF-T</a></li>{% endif %}
                            {% if SAFT_HISTORY_URL %}<li><a href="{{ SAFT_HISTORY_URL }}" class="menu-subitem"><i class="fas fa-history menu-subicon"></i>Histórico SAF-T</a></li>{% endif %}
                            {% if SAFT_VALIDATE_URL %}<li><a href="{{ SAFT_VALIDATE_URL }}" class="menu-subitem"><i class="fas fa-check-circle menu-subicon"></i>Validar XML</a></li>{% endif %}
                            {% endif %}
                        </ul>
                    </li>

                    {% if 'site' in modulos_ativos and user.e_administrador_empresa %}
                    <li>
                        <a href="{% url 'site:configuracao_dashboard' %}"
                           class="menu-item {% if request.resolver_match.namespace == 'site' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-globe menu-icon"></i>
                            <span>Configurações do Site</span>
                        </a>
                    </li>
                    {% endif %}

                    {% if perms.funcionarios.pode_gerenciar_funcionarios %}
                    <li>
                        <a href="{% url 'funcionarios:painel_candidatura' %}"
                           class="menu-item {% if 'recrutamento' in request.path %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-user-tie menu-icon"></i>
                            <span>Painel de Candidaturas</span>
                        </a>
                    </li>
                    {% endif %}

                    <!-- Configurações -->
                    <li class="mt-auto">
                        <a href="{% url 'configuracoes:dashboard_configuracoes' %}"
                           class="menu-item {% if request.resolver_match.namespace == 'configuracoes' %}menu-active{% else %}menu-link{% endif %} group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold">
                            <i class="fas fa-cog menu-icon"></i>
                            Configurações
                        </a>
                    </li>
                </ul>
            </nav>
        </aside>

        <!-- ===================== Conteúdo principal ===================== -->
        <div class="page-shell content-transition flex min-w-0 flex-1 flex-col"
             :class="!isMobile && sidebarOpen ? 'main-content-with-sidebar' : 'main-content-full-width'">

            <!-- Top bar -->
            <header class="vg-bar sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b px-4 shadow-sm sm:gap-x-6 sm:px-6 lg:px-8">
                <button @click="toggleSidebar()" type="button" x-show="isMobile"
                        class="vg-text menu-button lg:hidden -m-2.5 rounded-md p-2.5">
                    <span class="sr-only" x-text="sidebarOpen ? 'Fechar menu' : 'Abrir menu'"></span>
                    <i :class="sidebarOpen ? 'fas fa-times' : 'fas fa-bars'"></i>
                </button>

                <button @click="toggleSidebar()" type="button" x-show="!isMobile"
                        class="vg-text desktop-toggle-button hidden lg:flex -m-2.5 rounded-md border border-transparent p-2.5">
                    <span class="sr-only" x-text="sidebarOpen ? 'Recolher menu' : 'Expandir menu'"></span>
                    <i :class="sidebarOpen ? 'fas fa-chevron-left' : 'fas fa-chevron-right'"></i>
                </button>

                <div class="vg-divider h-6 w-px"></div>

                <!-- Breadcrumbs -->
                <div class="flex flex-1 gap-x-4 lg:gap-x-6">
                    <nav class="flex" aria-label="Breadcrumb">
                        <ol role="list" class="flex items-center space-x-4">
                            {% block breadcrumbs %}
                            <li><a href="{% url 'core_tenants:dashboard' %}" class="vg-muted-btn" aria-label="Início"><i class="fas fa-home"></i></a></li>
                            {% endblock %}
                        </ol>
                    </nav>
                </div>

                <div class="flex items-center gap-x-4 lg:gap-x-6">
                    <!-- Notificações (renderizadas no servidor; o polling só actualiza se houver mudanças) -->
                    <div x-data="{ open: false }" class="relative">
                        <button @click="open = !open" type="button" class="vg-muted-btn menu-button relative -m-2.5 p-2.5">
                            <span class="sr-only">Ver notificações</span>
                            <i class="fas fa-bell text-lg"></i>
                            <span class="notification-badge absolute -right-1 -top-1 h-4 w-4 items-center justify-center rounded-full bg-red-500 text-xs text-white"
                                  style="display: {% if notifications_count %}flex{% else %}none{% endif %}">{{ notifications_count|default:0 }}</span>
                        </button>

                        <div x-show="open" @click.away="open = false" x-cloak
                             x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 scale-95" x-transition:enter-end="opacity-100 scale-100"
                             x-transition:leave="transition ease-in duration-75" x-transition:leave-start="opacity-100 scale-100" x-transition:leave-end="opacity-0 scale-95"
                             class="dropdown-panel absolute right-0 z-10 mt-2 w-80 origin-top-right">
                            <div class="flex items-center justify-between border-b px-4 py-2" style="border-color: var(--color-border)">
                                <h3 class="text-sm font-medium text-gray-900">Notificações</h3>
                                <button type="button" class="notification-mark-all text-xs hover:underline" style="color: var(--color-text-link)">Marcar todas como lidas</button>
                            </div>
                            <div class="notification-dropdown-list max-h-96 overflow-y-auto">
                                {% for notification in notifications|slice:":5" %}
                                <a href="{{ notification.url|default:'#' }}" {% if notification.id %}data-notif-id="{{ notification.id }}"{% endif %} class="notification-item">
                                    <div class="flex">
                                        <div class="flex-shrink-0"><i class="fas fa-{{ notification.icon|default:'info-circle' }} notif-icon notif-icon--{{ notification.type|default:'blue' }}"></i></div>
                                        <div class="ml-3 min-w-0">
                                            <p class="truncate text-sm font-medium text-gray-900">{{ notification.title }}</p>
                                            <p class="truncate text-sm text-gray-500">{{ notification.message|truncatechars:50 }}</p>
                                            <p class="text-xs text-gray-500">{{ notification.created_at|timesince }} atrás</p>
                                        </div>
                                    </div>
                                </a>
                                {% empty %}
                                <div class="px-4 py-3 text-center text-sm text-gray-500">Nenhuma notificação</div>
                                {% endfor %}
                            </div>
                            {% url 'core_tenants:notifications' as NOTIFICATIONS_URL %}
                            {% if NOTIFICATIONS_URL %}
                            <div class="border-t" style="border-color: var(--color-border)">
                                <a href="{{ NOTIFICATIONS_URL }}" class="block px-4 py-2 text-center text-sm hover:underline" style="color: var(--color-text-link)">Ver todas as notificações</a>
                            </div>
                            {% endif %}
                        </div>
                    </div>

                    <!-- Ações rápidas (CORRIGIDO: regime_empresa → regime) -->
                    <div x-data="{ open: false }" class="relative">
                        <button @click="open = !open" type="button" class="vg-muted-btn menu-button -m-2.5 p-2.5">
                            <span class="sr-only">Ações rápidas</span>
                            <i class="fas fa-plus text-lg"></i>
                        </button>
                        <div x-show="open" @click.away="open = false" x-cloak class="dropdown-panel absolute right-0 z-10 mt-2 w-56 origin-top-right">
                            <a href="{% url 'vendas:pdv' %}" class="dropdown-item"><i class="fas fa-cash-register"></i>Nova Venda (PDV)</a>
                            {% if request.tenant.regime == 'COMERCIO' or request.tenant.regime == 'SERVICOS' or request.tenant.regime == 'MISTO' %}
                            <a href="{% url 'produtos:criar' %}" class="dropdown-item"><i class="fas fa-box"></i>Cadastrar Produto</a>
                            {% endif %}
                            <a href="{% url 'clientes:novo' %}" class="dropdown-item"><i class="fas fa-user-plus"></i>Cadastrar Cliente</a>
                            {% if request.tenant.regime == 'COMERCIO' or request.tenant.regime == 'SERVICOS' or request.tenant.regime == 'MISTO' %}
                            <a href="{% url 'produtos:lote_create' %}" class="dropdown-item"><i class="fas fa-truck"></i>Entrada de Estoque</a>
                            {% endif %}
                        </div>
                    </div>

                    <div class="vg-divider hidden lg:block lg:h-6 lg:w-px"></div>

                    <!-- Menu do utilizador (user.funcionario resolvido uma só vez; avatar nunca rebenta sem foto) -->
                    {% with func=user.funcionario %}
                    <div x-data="{ open: false }" class="relative">
                        <button @click="open = !open" type="button" class="flex min-w-0 items-center rounded-lg p-1.5 transition focus:outline-none focus:ring-2 focus:ring-indigo-500 menu-button">
                            <span class="sr-only">Abrir menu do utilizador</span>
                            <img src="{% if func and func.foto %}{{ func.foto.url }}{% else %}{% static 'img/logo.png' %}{% endif %}"
                                 width="32" height="32" class="h-8 w-8 rounded-full object-cover" alt="{{ user.get_full_name|default:user.username }}">
                            <span class="hidden lg:flex lg:items-center">
                                <span class="ml-3 max-w-48 truncate text-sm font-semibold leading-6 text-gray-900">{{ user.get_full_name|default:user.username }}</span>
                                <i class="vg-muted-btn ml-2 fas fa-chevron-down"></i>
                            </span>
                        </button>

                        <div x-show="open" @click.away="open = false" x-cloak
                             x-transition:enter="transition ease-out duration-200" x-transition:enter-start="opacity-0 scale-95" x-transition:enter-end="opacity-100 scale-100"
                             x-transition:leave="transition ease-in duration-75" x-transition:leave-start="opacity-100 scale-100" x-transition:leave-end="opacity-0 scale-95"
                             class="dropdown-panel absolute right-0 z-10 mt-2 w-56 origin-top-right">

                            <div class="border-b px-4 py-2" style="border-color: var(--color-border)">
                                <p class="vg-text text-sm">{{ user.get_full_name|default:user.username }}</p>
                                <p class="text-xs text-gray-500">{{ user.email }}</p>
                                {% if func.cargo %}<p class="text-xs text-gray-500">{{ func.cargo.nome }}</p>{% endif %}
                            </div>

                            {% if func %}
                            <a href="{% url 'funcionarios:perfil' func.pk %}" class="dropdown-item"><i class="fas fa-user"></i>Meu Perfil</a>
                            {% endif %}
                            <a href="{% url 'configuracoes:interface' %}" class="dropdown-item"><i class="fas fa-palette"></i>Preferências</a>

                            <div class="dropdown-sep"></div>
                            <p class="dropdown-heading">Tema da interface</p>
                            <button type="button" data-theme-choice="light" :aria-pressed="themePreference === 'light'" class="dropdown-item">
                                <i class="fas fa-sun"></i><span class="flex-1 text-left">Claro</span>
                                <i x-show="themePreference === 'light'" x-cloak class="fas fa-check" style="color: var(--color-text-link)" aria-hidden="true"></i>
                            </button>
                            <button type="button" data-theme-choice="dark" :aria-pressed="themePreference === 'dark'" class="dropdown-item">
                                <i class="fas fa-moon"></i><span class="flex-1 text-left">Escuro</span>
                                <i x-show="themePreference === 'dark'" x-cloak class="fas fa-check" style="color: var(--color-text-link)" aria-hidden="true"></i>
                            </button>
                            <button type="button" data-theme-choice="system" :aria-pressed="themePreference === 'system'" class="dropdown-item">
                                <i class="fas fa-desktop"></i><span class="flex-1 text-left">Sistema</span>
                                <i x-show="themePreference === 'system'" x-cloak class="fas fa-check" style="color: var(--color-text-link)" aria-hidden="true"></i>
                            </button>

                            <div class="dropdown-sep"></div>
                            <form method="post" action="{% url 'core:logout' %}">
                                {% csrf_token %}
                                <button type="submit" class="dropdown-item"><i class="fas fa-sign-out-alt"></i>Sair</button>
                            </form>
                        </div>
                    </div>
                    {% endwith %}
                </div>
            </header>

            <!-- Conteúdo da página -->
            <main class="page-content min-h-0 flex-1 overflow-y-auto py-6">
                <div class="page-content mx-auto w-full px-4 sm:px-6 lg:px-8">
                    {% block page_header %}
                    <div class="mb-8">
                        <div class="md:flex md:items-center md:justify-between">
                            <div class="min-w-0 flex-1">
                                <h1 class="text-2xl font-bold leading-7 text-gray-900 sm:truncate sm:text-3xl sm:tracking-tight">
                                    {% block page_title %}{{ title|default:"Dashboard" }}{% endblock %}
                                </h1>
                                {% block page_subtitle %}{% endblock %}
                            </div>
                            <div class="mt-4 flex md:ml-4 md:mt-0">
                                {% block page_actions %}{% endblock %}
                            </div>
                        </div>
                    </div>
                    {% endblock %}

                    <!-- Mensagens -->
                    {% if messages %}
                    <div x-data="{ show: true }" x-show="show" x-init="setTimeout(() => show = false, 5000)" class="mb-6 space-y-2">
                        {% for message in messages %}
                        <div class="rounded-md p-4 {% if message.tags == 'error' %}bg-red-50 dark:bg-red-900{% elif message.tags == 'warning' %}bg-yellow-50 dark:bg-yellow-900{% elif message.tags == 'success' %}bg-green-50 dark:bg-green-900{% else %}bg-blue-50 dark:bg-blue-900{% endif %}">
                            <div class="flex">
                                <div class="flex-shrink-0">
                                    {% if message.tags == 'error' %}<i class="fas fa-exclamation-circle text-red-400"></i>
                                    {% elif message.tags == 'warning' %}<i class="fas fa-exclamation-triangle text-yellow-400"></i>
                                    {% elif message.tags == 'success' %}<i class="fas fa-check-circle text-green-400"></i>
                                    {% else %}<i class="fas fa-info-circle text-blue-400"></i>{% endif %}
                                </div>
                                <div class="ml-3">
                                    <p class="text-sm font-medium {% if message.tags == 'error' %}text-red-800 dark:text-red-200{% elif message.tags == 'warning' %}text-yellow-800 dark:text-yellow-200{% elif message.tags == 'success' %}text-green-800 dark:text-green-200{% else %}text-blue-800 dark:text-blue-200{% endif %}">{{ message }}</p>
                                </div>
                                <div class="ml-auto pl-3">
                                    <button type="button" @click="show = false" aria-label="Fechar"
                                            class="inline-flex {% if message.tags == 'error' %}text-red-400 hover:text-red-500{% elif message.tags == 'warning' %}text-yellow-400 hover:text-yellow-500{% elif message.tags == 'success' %}text-green-400 hover:text-green-500{% else %}text-blue-400 hover:text-blue-500{% endif %}">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}

                    {% block content %}{% endblock %}
                </div>
            </main>

            <!-- Rodapé -->
            <footer class="vg-bar no-print shrink-0 border-t">
                <div class="mx-auto w-full px-4 py-3 sm:px-6 lg:px-8">
                    <div class="flex flex-col gap-2 text-xs text-gray-500 sm:flex-row sm:items-center sm:justify-between">
                        <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
                            <span>© {% now "Y" %} vistoGEST. Todos os direitos reservados.</span>
                            <span>Empresa: {% if request.tenant %}{{ request.tenant.razao_social|default:request.tenant.nome|default:"vistoGEST" }}{% else %}vistoGEST{% endif %}</span>
                        </div>
                        <div class="flex items-center gap-4">
                            <span>Versão 1.0.0</span>
                            <a href="{% url 'configuracoes:suporte' %}" class="vg-text inline-flex items-center gap-1 hover:underline">
                                <i class="fas fa-question-circle"></i><span>Suporte</span>
                            </a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    </div>

    <!-- Indicador de estado de rede (antes dos scripts, para existir quando forem executados) -->
    <div id="network-status" class="hidden" role="status" aria-live="polite"></div>

    <!-- ===================== Scripts ===================== -->
    <script>
    /* Estado da aplicação (Alpine). O tema é gerido pelo script do <head>;
       aqui só se reflecte o estado, via evento vg-theme-change. */
    function appData(initialTheme) {
        var root = document.documentElement;
        return {
            loading: false,
            themePreference: ['light', 'dark', 'system'].indexOf(initialTheme) !== -1 ? initialTheme : 'light',
            darkMode: false,
            sidebarOpen: true,
            isMobile: false,

            initApp() {
                window.__vistoGestApp = this;

                var mq = window.matchMedia('(max-width: 1023px)'); // breakpoint lg
                this.isMobile = mq.matches;
                this.loadPreferences();
                if (this.isMobile) this.sidebarOpen = false;

                var onBreakpoint = (e) => {
                    var wasMobile = this.isMobile;
                    this.isMobile = e.matches;
                    if (wasMobile && !this.isMobile) this.sidebarOpen = true;
                    else if (!wasMobile && this.isMobile) this.sidebarOpen = false;
                };
                if (mq.addEventListener) mq.addEventListener('change', onBreakpoint);
                else if (mq.addListener) mq.addListener(onBreakpoint);

                this.syncTheme();
                document.addEventListener('vg-theme-change', () => this.syncTheme());

                // Compatibilidade com páginas que alteram $root.loading
                this.$watch('loading', (value) => {
                    if (value) window.showLoadingOverlay && window.showLoadingOverlay();
                    else window.hideLoadingOverlay && window.hideLoadingOverlay();
                });
            },

            syncTheme() {
                this.themePreference = root.getAttribute('data-theme-preference') || this.themePreference;
                this.darkMode = root.classList.contains('dark');
            },
            setTheme(theme) {
                if (typeof window.__vistoGestSetTheme === 'function') window.__vistoGestSetTheme(theme);
            },
            toggleDarkMode() { this.setTheme(this.darkMode ? 'light' : 'dark'); },

            toggleSidebar() { this.sidebarOpen = !this.sidebarOpen; this.savePreferences(); },
            closeSidebar()  { this.sidebarOpen = false; this.savePreferences(); },
            openSidebar()   { this.sidebarOpen = true;  this.savePreferences(); },

            // Faz merge: nunca apaga themePreference nem outras chaves de app-preferences.
            savePreferences() {
                if (this.isMobile) return; // no mobile a sidebar começa sempre fechada
                try {
                    var s = JSON.parse(localStorage.getItem('app-preferences') || '{}');
                    if (!s || typeof s !== 'object' || Array.isArray(s)) s = {};
                    s.sidebarOpen = this.sidebarOpen;
                    localStorage.setItem('app-preferences', JSON.stringify(s));
                } catch (error) { /* sem armazenamento: ignora */ }
            },
            loadPreferences() {
                try {
                    var s = JSON.parse(localStorage.getItem('app-preferences') || 'null');
                    if (s && !this.isMobile && s.sidebarOpen !== undefined) this.sidebarOpen = !!s.sidebarOpen;
                } catch (error) { /* ignora */ }
            },

            // Utilitários usados por templates filhos
            formatCurrency(value) { return new Intl.NumberFormat('pt-AO', { style: 'currency', currency: 'AOA' }).format(value); },
            formatDate(date) { return new Intl.DateTimeFormat('pt-AO').format(new Date(date)); },
            navigateTo(url) { if (this.isMobile) this.closeSidebar(); window.location.href = url; },
            showSuccess(message) { this.showToast(message, 'success'); },
            showError(message) { this.showToast(message, 'error'); },
            showToast(message, type) {
                var toast = document.createElement('div');
                var colour = type === 'success' ? 'bg-green-500' : (type === 'error' ? 'bg-red-500' : 'bg-blue-500');
                toast.className = 'fixed top-4 right-4 z-50 p-4 rounded-md shadow-lg transition-all duration-300 text-white ' + colour;
                toast.setAttribute('role', 'status');
                toast.textContent = message;
                document.body.appendChild(toast);
                setTimeout(function () {
                    toast.style.opacity = '0';
                    toast.style.transform = 'translateX(100%)';
                    setTimeout(function () { toast.remove(); }, 300);
                }, 3000);
            }
        };
    }

    // Atalhos globais mantidos por compatibilidade
    window.toggleSidebar = function () { window.__vistoGestApp && window.__vistoGestApp.toggleSidebar(); };
    window.toggleDarkMode = function () { window.__vistoGestApp && window.__vistoGestApp.toggleDarkMode(); };
    </script>

    {% block extra_js %}{% endblock %}

{% if user.is_authenticated %}
<script>
/* =====================================================================
   NOTIFICAÇÕES — polling AJAX otimizado
   - sem chamada imediata (o servidor já renderizou a lista)
   - pausa com o separador escondido; retoma ao voltar
   - backoff exponencial em caso de erro (60 s → máx. 5 min)
   - só mexe no DOM quando algo mudou; sem innerHTML (sem XSS)
   ===================================================================== */
(function () {
    'use strict';

    var POLL_URL = '{% url "core_tenants:notifications_count_ajax" %}';
    var READ_ALL_URL = '{% url "core_tenants:notifications_read_all" %}';
    var READ_ONE_TPL = '{% url "core_tenants:notification_mark_read" 0 %}';
    var CSRF_TOKEN = '{{ csrf_token }}';
    var BASE_INTERVAL = 60000, MAX_INTERVAL = 300000;

    var badge = document.querySelector('.notification-badge');
    var list = document.querySelector('.notification-dropdown-list');
    var markAllBtn = document.querySelector('.notification-mark-all');

    var ICONS = {
        'bell': 'fa-bell', 'info-circle': 'fa-info-circle', 'exclamation-triangle': 'fa-exclamation-triangle',
        'exclamation-circle': 'fa-exclamation-circle', 'boxes': 'fa-boxes', 'chart-line': 'fa-chart-line',
        'tachometer-alt': 'fa-tachometer-alt', 'shield-alt': 'fa-shield-alt', 'money-bill-wave': 'fa-money-bill-wave'
    };
    var COLOURS = ['blue', 'red', 'green', 'yellow', 'orange', 'indigo', 'purple', 'gray'];

    var timer = null, delay = BASE_INTERVAL, inFlight = false, lastPoll = Date.now(), lastSignature = null;

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }
    function safeUrl(url) {
        return (typeof url === 'string' && /^(\/(?!\/)|https?:\/\/)/.test(url)) ? url : '#';
    }
    function timeAgo(iso) {
        if (!iso) return '';
        var diff = Math.floor((Date.now() - new Date(iso)) / 1000);
        if (diff < 60) return diff + 's';
        if (diff < 3600) return Math.floor(diff / 60) + 'min';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h';
        return Math.floor(diff / 86400) + 'd';
    }

    function updateBadge(count) {
        if (!badge) return;
        badge.textContent = count;
        badge.style.display = count > 0 ? 'flex' : 'none';
        if (count > 0) {
            badge.classList.add('animate-pulse');
            setTimeout(function () { badge.classList.remove('animate-pulse'); }, 3000);
        }
    }

    function renderDropdown(items) {
        if (!list) return;
        list.textContent = '';
        if (!items || !items.length) {
            list.appendChild(el('div', 'px-4 py-3 text-center text-sm text-gray-500', 'Nenhuma notificação'));
            return;
        }
        items.forEach(function (n) {
            var a = el('a', 'notification-item');
            a.href = safeUrl(n.url);
            if (n.id) a.setAttribute('data-notif-id', n.id);

            var colour = COLOURS.indexOf(n.type) !== -1 ? n.type : 'blue';
            var icon = el('i', 'fas ' + (ICONS[n.icon] || 'fa-info-circle') + ' notif-icon notif-icon--' + colour);
            var left = el('div', 'flex-shrink-0'); left.appendChild(icon);

            var right = el('div', 'ml-3 min-w-0');
            right.appendChild(el('p', 'truncate text-sm font-medium text-gray-900', n.title));
            right.appendChild(el('p', 'truncate text-sm text-gray-500', n.message));
            right.appendChild(el('p', 'text-xs text-gray-500', timeAgo(n.created_at) + ' atrás'));

            var row = el('div', 'flex'); row.appendChild(left); row.appendChild(right);
            a.appendChild(row);
            list.appendChild(a);
        });
    }

    function applyData(data) {
        var items = data.notifications || [];
        var signature = data.count + '|' + items.map(function (n) { return n.id || n.title; }).join(',');
        if (signature === lastSignature) return;      // nada mudou: não toca no DOM
        lastSignature = signature;
        updateBadge(data.count);
        renderDropdown(items);
    }

    function schedule() {
        clearTimeout(timer);
        if (document.hidden) return;
        timer = setTimeout(poll, delay);
    }

    function poll() {
        if (inFlight || navigator.onLine === false) { schedule(); return; }
        inFlight = true;
        fetch(POLL_URL, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(function (data) { delay = BASE_INTERVAL; applyData(data); })
            .catch(function () { delay = Math.min(delay * 2, MAX_INTERVAL); })
            .then(function () { inFlight = false; lastPoll = Date.now(); schedule(); });
    }

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) { clearTimeout(timer); return; }
        if (Date.now() - lastPoll >= BASE_INTERVAL) poll(); else schedule();
    });

    // Marcar uma como lida (delegação: funciona também nos itens renderizados no servidor)
    if (list) {
        list.addEventListener('click', function (event) {
            var item = event.target.closest('[data-notif-id]');
            if (!item) return;
            fetch(READ_ONE_TPL.replace('/0/', '/' + item.getAttribute('data-notif-id') + '/'), {
                method: 'POST', credentials: 'same-origin', keepalive: true,
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'Content-Type': 'application/json' }
            });
        });
    }

    if (markAllBtn) {
        markAllBtn.addEventListener('click', function (event) {
            event.preventDefault();
            fetch(READ_ALL_URL, {
                method: 'POST', credentials: 'same-origin',
                headers: { 'X-CSRFToken': CSRF_TOKEN, 'Content-Type': 'application/json' }
            }).then(function () { lastSignature = null; poll(); });
        });
    }

    schedule();
})();
</script>
{% endif %}

<!-- PWA: Service Worker + prompt de instalação -->
<script>
(function () {
    'use strict';

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker
                .register('{% url "core:pwa_service_worker" %}', { scope: '/' })
                .then(function (reg) {
                    reg.addEventListener('updatefound', function () {
                        var worker = reg.installing;
                        if (!worker) return;
                        worker.addEventListener('statechange', function () {
                            if (worker.state === 'installed' && navigator.serviceWorker.controller) {
                                worker.postMessage({ type: 'SKIP_WAITING' });
                            }
                        });
                    });
                })
                .catch(function (err) { console.warn('[PWA] Falha ao registar Service Worker:', err); });
        });
    }

    var deferredPrompt = null;
    var ICON_URL = '{% static "images/icon-192.png" %}';

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        var installBtn = document.getElementById('pwa-install-btn');
        if (installBtn) {
            installBtn.style.display = 'flex';
            installBtn.addEventListener('click', function () {
                installBtn.style.display = 'none';
                if (!deferredPrompt) return;
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(function () { deferredPrompt = null; });
            }, { once: true });
        }
        setTimeout(showInstallBanner, 3000);
    });

    function showInstallBanner() {
        if (!deferredPrompt) return;
        if (window.matchMedia('(display-mode: standalone)').matches) return;
        if (document.getElementById('pwa-install-banner')) return;

        var banner = document.createElement('div');
        banner.id = 'pwa-install-banner';
        banner.setAttribute('role', 'dialog');
        banner.setAttribute('aria-label', 'Instalar aplicação');
        banner.className = 'dropdown-panel no-print fixed bottom-4 left-1/2 z-50 mx-4 flex w-full max-w-sm -translate-x-1/2 items-center gap-x-3 px-4 py-3 text-sm';
        banner.innerHTML =
            '<img src="' + ICON_URL + '" alt="" width="40" height="40" class="h-10 w-10 flex-shrink-0 rounded-lg" onerror="this.style.display=\'none\'">' +
            '<div class="min-w-0 flex-1"><p class="vg-text truncate font-semibold">Instalar VistoGEST</p>' +
            '<p class="truncate text-xs text-gray-500">Acesso rápido, funciona offline</p></div>' +
            '<button type="button" id="pwa-banner-install" class="flex-shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500">Instalar</button>' +
            '<button type="button" id="pwa-banner-dismiss" aria-label="Fechar" class="vg-muted-btn ml-1 flex-shrink-0 focus:outline-none"><i class="fas fa-times"></i></button>';
        document.body.appendChild(banner);

        document.getElementById('pwa-banner-install').addEventListener('click', function () {
            banner.remove();
            if (!deferredPrompt) return;
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then(function () { deferredPrompt = null; });
        });
        document.getElementById('pwa-banner-dismiss').addEventListener('click', function () { banner.remove(); });
        setTimeout(function () { if (banner.parentNode) banner.remove(); }, 10000);
    }

    function updateOnlineStatus() {
        var indicator = document.getElementById('network-status');
        if (!indicator) return;
        if (navigator.onLine) {
            indicator.textContent = '';
            indicator.className = 'hidden';
        } else {
            indicator.textContent = 'Sem conexão — modo offline';
            indicator.className = 'fixed top-0 left-0 right-0 z-50 py-1 px-4 text-xs text-center bg-yellow-500 text-white font-medium';
        }
    }
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
    updateOnlineStatus();
})();
</script>
</body>
</html>

# apps/core_tenants/urls.py
from django.urls import path

from . import views

app_name = 'core_tenants'

urlpatterns = [
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    path('security/history/', views.SecurityHistoryView.as_view(), name='security_history'),
    path('security/terminate-sessions/', views.TerminarOutrasSessoesView.as_view(), name='terminate_sessions'),
    path('verify-device/', views.VerifyIPView.as_view(), name='verify_ip'),

    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('ajax/notifications/count/', views.NotificacaoCountAjaxView.as_view(), name='notifications_count_ajax'),
    path('ajax/notifications/<int:pk>/read/', views.NotificacaoMarcarLidaView.as_view(), name='notification_mark_read'),
    path('ajax/notifications/read-all/', views.NotificacaoMarcarTodasLidasView.as_view(), name='notifications_read_all'),

    path('ajax/dashboard/stats/', views.DashboardStatsAPI.as_view(), name='dashboard_stats_api'),
]

# apps/core_tenants/views.py
"""
Views de tenant (schemas de empresa). Mapeadas 1:1 a partir de
apps/core/views.py conforme PLANO_CORE_TENANT.md, secção 3.1.

Namespace de URL: 'core_tenants' (NÃO 'core' — decisão final confirmada
pelo dono do sistema, substituindo a ideia anterior de manter app_name='core'
em core_tenants/urls.py).
"""
from datetime import timedelta
from decimal import Decimal
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import connection
from django.db.models import F, Q, Count, Sum
from django.db.models.functions import TruncWeek, TruncMonth
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags
from django.views import View
from django.views.generic import ListView, TemplateView

from apps.core.models import AuditoriaAcesso, IPConhecido, VerificacaoSeguranca
from apps.analytics.models import AuditoriaInvestimento, NotificacaoAlerta
from apps.produtos.models import Categoria, Produto
from apps.servicos.models import NotificacaoAgendamento
from apps.vendas.models import ItemVenda, Venda
from apps.vendas.dashboard_data import dados_analise_vendas, lucro_total


logger = logging.getLogger('core_tenants.security')


# ============================================================
# BASE VIEW COM CONTEXTO EMPRESARIAL (tenant)
# ============================================================

class BaseMPAView(TemplateView):
    """
    RIGOR SOTARQ: base para todas as views MPA de tenant.
    Alinhada ao padrão django_tenants (isolamento físico via schema PostgreSQL).
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        empresa = self.get_empresa()
        context.update({
            'user': self.request.user,
            'current_module': getattr(self, 'module_name', 'dashboard'),
            'empresa_atual': empresa,
        })
        return context

    def get_empresa(self):
        """Retorna o Tenant (Empresa) activo associado ao schema da requisição actual."""
        tenant = getattr(self.request, 'tenant', None) or getattr(connection, 'tenant', None)

        if not tenant or getattr(tenant, 'schema_name', 'public') == 'public':
            if getattr(self, 'exigir_empresa', False):
                raise PermissionDenied("Acção permitida apenas no contexto de uma empresa/tenant activo.")
            return None

        return tenant


# ============================================================
# DASHBOARD
# ============================================================


class DashboardView(LoginRequiredMixin, BaseMPAView):
    """
    Dashboard executivo: vendas, lucro e ativos.
    Regras de consistência:
      - Todos os valores monetários saem de `vendas_qs`, que nunca faz JOIN
        com itens (o filtro de investidor usa pk__in com subquery).
      - Lucro do cartão e do gráfico usam a mesma fórmula (dashboard_data).
      - Datas em hora local (timezone.localdate), não em UTC.
      - O contexto envia dicts Python; o template serializa com json_script.
    """
    template_name = 'core/dashboard.html'
    module_name = 'dashboard'

    # ------------------------------------------------------------------
    # Filtros de compliance (investidores)
    # ------------------------------------------------------------------

    def _vinculo_restrito(self, user):
        """Devolve o vínculo de auditoria se o utilizador estiver limitado
        aos seus ativos; None se tiver acesso total."""
        if user.is_superuser:
            return None
        from apps.analytics.models import AuditoriaInvestimento
        vinculo = AuditoriaInvestimento.objects.filter(usuario=user).first()
        if vinculo is None or vinculo.pode_auditar_tudo:
            return None
        return vinculo

    def get_vendas_filtradas(self, user, empresa=None):
        """Queryset de vendas finalizadas, SEM joins (seguro para Sum/Count)."""
        if connection.schema_name == 'public':
            return Venda.objects.none()

        base = Venda.objects.filter(status='finalizada')
        vinculo = self._vinculo_restrito(user)
        if vinculo is None:
            return base

        ids = (ItemVenda.objects
               .filter(venda__status='finalizada')
               .filter(Q(produto__lotes__in=vinculo.lotes_vinculados.all()) |
                       Q(produto__fabricante__in=vinculo.fabricantes_vinculados.all()))
               .values('venda_id'))
        return base.filter(pk__in=ids)

    def get_produtos_base(self, user):
        base = Produto.objects.filter(ativo=True)
        vinculo = self._vinculo_restrito(user)
        if vinculo is None:
            return base

        ids = (Produto.objects
               .filter(Q(lotes__in=vinculo.lotes_vinculados.all()) |
                       Q(fabricante__in=vinculo.fabricantes_vinculados.all()))
               .values('pk'))
        return base.filter(pk__in=ids)

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    def get_lucro_investidor(self, vendas_qs):
        return lucro_total(vendas_qs)

    def get_formas_pagamento(self, vendas_qs):
        inicio_mes = timezone.localdate().replace(day=1)
        qs = (vendas_qs
              .filter(data_venda__date__gte=inicio_mes)
              .values('forma_pagamento__nome')
              .annotate(total=Sum('total'))
              .order_by('-total'))

        dados = {'labels': [], 'valores': []}
        for item in qs:
            if item['total']:
                dados['labels'].append(item['forma_pagamento__nome'] or 'Outros')
                dados['valores'].append(float(item['total']))
        return dados

    def get_metas(self, vendas_qs, hoje):
        """Metas de faturamento activas hoje vs realizado (sem JOIN com itens)."""
        from apps.vendas.models import MetaVenda

        metas = (MetaVenda.objects
                 .filter(status='ativa', meta_faturamento__isnull=False,
                         data_inicio__lte=hoje, data_fim__gte=hoje)
                 .order_by('data_inicio')[:6])

        dados = {'labels': [], 'metas': [], 'realizados': []}
        for m in metas:
            qs = vendas_qs.filter(data_venda__date__gte=m.data_inicio,
                                  data_venda__date__lte=m.data_fim)
            if m.vendedor_id:
                qs = qs.filter(vendedor_id=m.vendedor_id)
            realizado = qs.aggregate(t=Sum('total'))['t'] or Decimal('0.00')

            dados['labels'].append(m.nome)
            dados['metas'].append(float(m.meta_faturamento))
            dados['realizados'].append(float(realizado))
        return dados

    def get_top_vendedores(self, vendas_qs):
        inicio_mes = timezone.localdate().replace(day=1)
        return list(
            vendas_qs
            .filter(data_venda__date__gte=inicio_mes, vendedor__isnull=False)
            .values('vendedor__nome_completo')
            .annotate(total_vendas=Count('id'), total_faturamento=Sum('total'))
            .order_by('-total_faturamento')[:5]
        )

    # ------------------------------------------------------------------
    # Contexto
    # ------------------------------------------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Schema public: tudo vazio, mas com a estrutura completa
        if connection.schema_name == 'public':
            context.update({
                'vendas_hoje': {'total': Decimal('0.00'), 'quantidade': 0},
                'lucro_total': Decimal('0.00'),
                'produtos_stats': {'total': 0, 'total_categorias': 0},
                'estoque_stats': {'estoque_baixo': 0},
                'vendas_recentes': [],
                'top_vendedores': [],
                'dados_vendas': dados_analise_vendas(Venda.objects.none()),
                'dados_formas_pagamento': {'labels': [], 'valores': []},
                'dados_metas': {'labels': [], 'metas': [], 'realizados': []},
            })
            return context

        user = self.request.user
        hoje = timezone.localdate()

        vendas_qs = self.get_vendas_filtradas(user, context.get('empresa_atual'))
        produtos_base = self.get_produtos_base(user)

        v_hoje = vendas_qs.filter(data_venda__date=hoje).aggregate(
            t=Sum('total'), q=Count('id'))

        context.update({
            'vendas_hoje': {
                'total': v_hoje['t'] or Decimal('0.00'),
                'quantidade': v_hoje['q'] or 0,
            },
            'lucro_total': self.get_lucro_investidor(vendas_qs),
            'produtos_stats': {
                'total': produtos_base.count(),
                'total_categorias': Categoria.objects.filter(ativa=True).count(),
            },
            'estoque_stats': {
                'estoque_baixo': produtos_base.filter(
                    estoque_atual__lte=F('estoque_minimo')).count(),
            },
            'vendas_recentes': (vendas_qs.select_related('cliente')
                                .order_by('-data_venda')[:10]),
            'top_vendedores': self.get_top_vendedores(vendas_qs),
            'dados_vendas': dados_analise_vendas(vendas_qs),
            'dados_formas_pagamento': self.get_formas_pagamento(vendas_qs),
            'dados_metas': self.get_metas(vendas_qs, hoje),
        })
        return context



class DashboardStatsAPI(LoginRequiredMixin, View):
    """AJAX de estatísticas do dashboard (stub — preencher quando necessário)."""

    def get(self, request):
        return JsonResponse({'success': True, 'stats': {}})


# ============================================================
# SEGURANÇA — histórico, sessões, 2FA por IP
# ============================================================

class SecurityHistoryView(LoginRequiredMixin, BaseMPAView):
    """RIGOR SOTARQ: exibe o histórico de segurança e acessos do utilizador."""
    template_name = 'core/security_history.html'
    module_name = 'security'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['logs'] = AuditoriaAcesso.objects.filter(
            usuario=self.request.user
        ).order_by('-timestamp')[:20]
        return context


class TerminarOutrasSessoesView(LoginRequiredMixin, View):
    """RIGOR SOTARQ: invalida todas as sessões do utilizador, excepto a actual."""

    def post(self, request):
        chave_sessao_atual = request.session.session_key
        sessoes = Session.objects.filter(expire_date__gte=timezone.now())

        contagem_removida = 0
        for sessao in sessoes:
            dados = sessao.get_decoded()
            if dados.get('_auth_user_id') == str(request.user.id):
                if sessao.session_key != chave_sessao_atual:
                    sessao.delete()
                    contagem_removida += 1

        messages.success(request, f"Sucesso! {contagem_removida} dispositivos remotos foram desconectados.")
        return redirect('core_tenants:security_history')


class VerifyIPView(LoginRequiredMixin, View):
    """
    RIGOR SOTARQ: desafia o utilizador com um token de 6 dígitos sempre que
    um novo IP é detectado. É uma view de TENANT — o login em si (schema
    public) continua em apps.core.views.CustomLoginView.
    """
    template_name = 'registration/verify_ip.html'

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

    def get(self, request):
        user = request.user
        ip_atual = self.get_client_ip(request)
        agora = timezone.now()

        # Blindagem de isolamento físico: utilizadores comuns não podem
        # validar 2FA no schema public (área global, sem tenant).
        if not user.is_superuser:
            if getattr(connection, 'schema_name', 'public') == 'public':
                if settings.DEBUG:
                    print(f"⚠️ BLOQUEIO DE SEGURANÇA: Utilizador {user.email} tentou aceder à validação 2FA no schema public")
                logout(request)
                messages.error(request, "Acesso negado: Esta operação deve ser realizada no domínio da sua empresa.")
                return redirect('core:login')

        if settings.DEBUG:
            print("\n" + "!" * 60)
            print("🕵️ AUDITORIA DE ACESSO 2FA")
            print(f"🏢 SCHEMA ATIVO: {connection.schema_name}")
            print(f"👤 UTILIZADOR: {user.email}")
            print(f"🌐 IP: {ip_atual}")
            print("!" * 60 + "\n")

        verificacao, created = VerificacaoSeguranca.objects.get_or_create(
            usuario=user,
            ip_address=ip_atual,
            foi_verificado=False,
            defaults={'expira_em': agora + timezone.timedelta(minutes=10)}
        )

        if request.GET.get('action') == 'resend':
            segundos_desde_ultimo = (agora - verificacao.criado_em).total_seconds()

            if segundos_desde_ultimo < 60:
                segundos_restantes = int(60 - segundos_desde_ultimo)
                messages.warning(
                    request,
                    f"Aguarde mais {segundos_restantes} segundos antes de solicitar um novo código."
                )
                return render(request, self.template_name, {'email': user.email})

            messages.info(request, "Um novo código foi gerado e enviado para o seu e-mail.")
            verificacao.criado_em = agora
            verificacao.save()

        token = verificacao.gerar_token()
        self.enviar_email_token(user, token, ip_atual)

        return render(request, self.template_name, {'email': user.email})

    def post(self, request):
        token_inserido = request.POST.get('token')
        ip_atual = self.get_client_ip(request)

        verificacao = VerificacaoSeguranca.objects.filter(
            usuario=request.user,
            ip_address=ip_atual,
            foi_verificado=False
        ).last()

        if verificacao and verificacao.esta_valido() and verificacao.token == token_inserido:
            verificacao.foi_verificado = True
            verificacao.save()

            IPConhecido.objects.get_or_create(usuario=request.user, ip_address=ip_atual)

            messages.success(request, "Dispositivo autorizado com sucesso!")
            return redirect('core_tenants:dashboard')

        messages.error(request, "Código inválido ou expirado. Um novo código foi enviado para o seu e-mail.")
        return self.get(request)

    def enviar_email_token(self, user, token, ip):
        """Envia o e-mail de 2FA."""
        if settings.DEBUG:
            print("\n" + "=" * 50)
            print(f"🛠️ [SOTARQ DEBUG] 2FA PARA: {user.email}")
            print(f"🔑 TOKEN: {token}")
            print(f"🌐 IP: {ip}")
            print("=" * 50 + "\n")

        assunto = f"Código de Verificação: {token} | VistoGEST"
        contexto = {'user': user, 'token': token, 'ip': ip, 'expire': 10}

        html_message = render_to_string('emails/token_2fa_email.html', contexto)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=assunto,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )


# ============================================================
# NOTIFICAÇÕES
# ============================================================

class NotificationListView(LoginRequiredMixin, ListView):
    """Lista todas as notificações do utilizador autenticado."""
    template_name = "core_tenants/notifications_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        return (
            NotificacaoAlerta.objects
            .filter(usuario=self.request.user)
            .select_related('alerta')
            .order_by('-alerta__created_at')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['unread_count'] = (
            NotificacaoAlerta.objects
            .filter(usuario=self.request.user, lida=False)
            .count()
        )
        return ctx


class NotificacaoMarcarLidaView(LoginRequiredMixin, View):
    """AJAX — marca uma NotificacaoAlerta como lida."""

    def post(self, request, pk):
        try:
            notif = NotificacaoAlerta.objects.get(pk=pk, usuario=request.user)
            if not notif.lida:
                notif.lida = True
                notif.lida_em = timezone.now()
                notif.save(update_fields=['lida', 'lida_em'])
            return JsonResponse({'ok': True})
        except NotificacaoAlerta.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'not found'}, status=404)


class NotificacaoMarcarTodasLidasView(LoginRequiredMixin, View):
    """AJAX — marca todas as notificações do utilizador como lidas."""

    def post(self, request):
        agora = timezone.now()
        updated = (
            NotificacaoAlerta.objects
            .filter(usuario=request.user, lida=False)
            .update(lida=True, lida_em=agora)
        )
        return JsonResponse({'ok': True, 'updated': updated})


import logging
from django.db import connection, transaction

log = logging.getLogger('core_tenants.notifications')


class NotificacaoCountAjaxView(LoginRequiredMixin, View):
    """Polling de notificações (alertas + agendamentos + expiração)."""

    def handle_no_permission(self):
        return JsonResponse({'count': 0, 'notifications': [], 'auth': False}, status=401)

    def get(self, request):
        if connection.schema_name == 'public':
            return JsonResponse({'count': 0, 'notifications': []})

        from apps.produtos.models import AlertaProdutoExpiracao

        count, notifs = 0, []

        try:
            with transaction.atomic():
                qs = (NotificacaoAlerta.objects
                      .filter(usuario=request.user, lida=False)
                      .select_related('alerta'))
                count += qs.count()
                for n in qs.order_by('-alerta__created_at')[:5]:
                    a = n.alerta
                    if a:
                        notifs.append({
                            'id': n.pk, 'title': a.titulo, 'message': a.mensagem[:80],
                            'url': f'/analytics/alertas/{a.pk}/',
                            'icon': _icon_for_alerta(a.tipo),
                            'type': _color_for_prioridade(a.prioridade),
                            'created_at': a.created_at.isoformat(), 'source': 'alerta',
                        })
        except Exception:
            log.exception('Falha na fonte: alertas')

        try:
            with transaction.atomic():
                qs = NotificacaoAgendamento.objects.filter(status='pendente')
                count += qs.count()
                for n in qs.select_related('cliente').order_by('-data_agendada_envio')[:5]:
                    notifs.append({
                        'id': None,
                        'title': f"{n.get_tipo_notificacao_display()} — {n.cliente.nome_completo}",
                        'message': (n.mensagem or '')[:80],
                        'url': f'/notificacoes/{n.id}/editar/',
                        'icon': 'bell', 'type': 'blue',
                        'created_at': n.created_at.isoformat(), 'source': 'agendamento',
                    })
        except Exception:
            log.exception('Falha na fonte: agendamentos')

        try:
            with transaction.atomic():
                qs = AlertaProdutoExpiracao.objects.filter(enviado=False)
                count += qs.count()
                hoje = timezone.localdate()
                for a in qs.select_related('lote__produto').order_by('-created_at')[:5]:
                    dias = (a.lote.data_validade - hoje).days
                    notifs.append({
                        'id': None, 'title': 'Produto prestes a expirar',
                        'message': f"{a.lote.produto.nome_comercial} vence em {dias} dias",
                        'url': f'/produtos/lotes/{a.lote.id}/',
                        'icon': 'exclamation-triangle', 'type': 'red',
                        'created_at': a.created_at.isoformat(), 'source': 'expiracao',
                    })
        except Exception:
            log.exception('Falha na fonte: expiração')

        notifs.sort(key=lambda x: x['created_at'], reverse=True)
        return JsonResponse({'count': count, 'notifications': notifs[:5]})



def _icon_for_alerta(tipo):
    return {
        'estoque_baixo': 'boxes',
        'vendas_baixas': 'chart-line',
        'erro_sistema': 'exclamation-circle',
        'performance': 'tachometer-alt',
        'seguranca': 'shield-alt',
        'financeiro': 'money-bill-wave',
    }.get(tipo, 'info-circle')


def _color_for_prioridade(prioridade):
    return {
        'baixa': 'green',
        'media': 'yellow',
        'alta': 'orange',
        'critica': 'red',
    }.get(prioridade, 'blue')


notifications_list.html:
{% extends "base.html" %}
{% load i18n %}

{% block title %}Todas as Notificações — {{ block.super }}{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

  <!-- Cabeçalho -->
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">
        <i class="fas fa-bell mr-2 text-blue-500"></i>Notificações
      </h1>
      {% if unread_count %}
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
        {{ unread_count }} não lida{{ unread_count|pluralize:"s" }}
      </p>
      {% endif %}
    </div>

    {% if unread_count %}
    <form method="post" action="{% url 'core_tenants:notifications_read_all' %}">
      {% csrf_token %}
      <button type="submit"
              class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium
                     rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none
                     focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors">
        <i class="fas fa-check-double mr-2"></i>Marcar todas como lidas
      </button>
    </form>
    {% endif %}
  </div>

  <!-- Lista -->
  <div class="bg-white dark:bg-gray-800 shadow rounded-lg divide-y divide-gray-200 dark:divide-gray-700">
    {% for notif in notifications %}
    <div class="flex items-start p-4 {% if not notif.lida %}bg-blue-50 dark:bg-blue-900/10{% endif %}">
      <div class="flex-shrink-0 mt-0.5">
        {% if notif.alerta %}
          {% with tipo=notif.alerta.tipo %}
          <i class="fas fa-{% if tipo == 'estoque_baixo' %}boxes{% elif tipo == 'financeiro' %}money-bill-wave{% elif tipo == 'seguranca' %}shield-alt{% elif tipo == 'erro_sistema' %}exclamation-circle{% else %}info-circle{% endif %}
                      text-{% if notif.alerta.prioridade == 'critica' %}red{% elif notif.alerta.prioridade == 'alta' %}orange{% elif notif.alerta.prioridade == 'media' %}yellow{% else %}blue{% endif %}-500 text-lg w-6 text-center"></i>
          {% endwith %}
        {% else %}
          <i class="fas fa-bell text-blue-500 text-lg w-6 text-center"></i>
        {% endif %}
      </div>

      <div class="ml-4 flex-1 min-w-0">
        {% if notif.alerta %}
        <p class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ notif.alerta.titulo }}</p>
        <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">{{ notif.alerta.mensagem }}</p>
        <div class="flex items-center gap-x-3 mt-2">
          <span class="text-xs text-gray-400 dark:text-gray-500">
            <i class="far fa-clock mr-1"></i>{{ notif.alerta.created_at|timesince }} atrás
          </span>
          <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
            {% if notif.alerta.prioridade == 'critica' %}bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200
            {% elif notif.alerta.prioridade == 'alta' %}bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200
            {% elif notif.alerta.prioridade == 'media' %}bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200
            {% else %}bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200{% endif %}">
            {{ notif.alerta.get_prioridade_display }}
          </span>
          {% if not notif.lida %}
          <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
            Nova
          </span>
          {% endif %}
        </div>
        {% else %}
        <p class="text-sm text-gray-500 dark:text-gray-400 italic">Notificação sem detalhes</p>
        {% endif %}
      </div>

      {% if not notif.lida %}
      <div class="ml-4 flex-shrink-0">
        <form method="post" action="{% url 'core_tenants:notification_mark_read' notif.pk %}">
          {% csrf_token %}
          <button type="submit"
                  class="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  title="Marcar como lida">
            <i class="fas fa-check"></i>
          </button>
        </form>
      </div>
      {% endif %}
    </div>
    {% empty %}
    <div class="flex flex-col items-center justify-center py-16 text-gray-400 dark:text-gray-500">
      <i class="fas fa-bell-slash text-4xl mb-3"></i>
      <p class="text-sm">Nenhuma notificação de momento</p>
    </div>
    {% endfor %}
  </div>

  <!-- Paginação (se necessário no futuro) -->
  {% if is_paginated %}
  <div class="mt-6 flex justify-center">
    {% include "partials/pagination.html" %}
  </div>
  {% endif %}

</div>
{% endblock %}

# apps/core_tenants/context_processors.py
from datetime import timedelta

from django.db import connection
from django.utils import timezone

from apps.produtos.models import AlertaProdutoExpiracao, Lote
from apps.servicos.models import NotificacaoAgendamento
from apps.vendas.models import Venda


def dashboard_data(request):
    """Context processor para dados globais do dashboard (só faz sentido em tenant)."""
    if connection.schema_name == 'public':
        return {}

    if not request.user.is_authenticated or not hasattr(request.user, 'funcionario') or not request.user.funcionario:
        return {}

    hoje = timezone.now().date()
    notificacoes = []

    vencendo_hoje = Lote.objects.filter(
        produto__ativo=True,
        data_validade=hoje,
        quantidade_atual__gt=0
    ).count()

    if vencendo_hoje > 0:
        notificacoes.append({
            'tipo': 'warning',
            'mensagem': f'{vencendo_hoje} produto(s) vencem hoje!',
            'url': '/produtos/vencimentos/'
        })

    uma_hora_atras = timezone.now() - timedelta(hours=1)
    vendas_pendentes = Venda.objects.filter(
        status='aguardando_pagamento',
        created_at__lt=uma_hora_atras
    ).count()

    if vendas_pendentes > 0:
        notificacoes.append({
            'tipo': 'info',
            'mensagem': f'{vendas_pendentes} venda(s) aguardando pagamento',
            'url': '/vendas/pendentes/'
        })

    return {
        'notificacoes_globais': notificacoes,
        'count_notificacoes': len(notificacoes)
    }


def notifications_context(request):
    """Idem — só faz sentido em tenant, onde existem NotificacaoAgendamento/AlertaProdutoExpiracao."""
    if connection.schema_name == 'public':
        return {}

    user = request.user
    notifications = []

    if hasattr(user, 'funcionario') and user.funcionario:
        agend_notifs = NotificacaoAgendamento.objects.filter(
            status='pendente'
        ).order_by('-data_agendada_envio')[:10]

        for n in agend_notifs:
            notifications.append({
                'title': f"{n.get_tipo_notificacao_display()} - {n.cliente.nome_completo}",
                'message': n.mensagem,
                'url': f"/notificacoes/{n.id}/editar/",
                'icon': 'bell',
                'type': 'blue',
                'created_at': n.created_at,
            })

        alertas = AlertaProdutoExpiracao.objects.filter(
            enviado=False
        ).order_by('-created_at')[:20]

        for a in alertas:
            dias = (a.lote.data_validade - timezone.now().date()).days
            notifications.append({
                'title': "Produto prestes a expirar",
                'message': f"{a.lote.produto.nome_comercial} - Lote {a.lote.numero_lote} vence em {dias} dias",
                'url': f"/produtos/lotes/{a.lote.id}/",
                'icon': 'exclamation-triangle',
                'type': 'red',
                'created_at': a.created_at,
            })

    return {
        'notifications': notifications,
        'notifications_count': len(notifications)
    }




def notifications(request):
    """Idem — só faz sentido em tenant, onde existem NotificacaoAgendamento/AlertaProdutoExpiracao."""
    if connection.schema_name == 'public':
        return {}

    user = request.user
    notifications = []

    if hasattr(user, 'funcionario') and user.funcionario:
        agend_notifs = NotificacaoAgendamento.objects.filter(
            status='pendente'
        ).order_by('-data_agendada_envio')[:10]

        for n in agend_notifs:
            notifications.append({
                'title': f"{n.get_tipo_notificacao_display()} - {n.cliente.nome_completo}",
                'message': n.mensagem,
                'url': f"/notificacoes/{n.id}/editar/",
                'icon': 'bell',
                'type': 'blue',
                'created_at': n.created_at,
            })

        alertas = AlertaProdutoExpiracao.objects.filter(
            enviado=False
        ).order_by('-created_at')[:20]

        for a in alertas:
            dias = (a.lote.data_validade - timezone.now().date()).days
            notifications.append({
                'title': "Produto prestes a expirar",
                'message': f"{a.lote.produto.nome_comercial} - Lote {a.lote.numero_lote} vence em {dias} dias",
                'url': f"/produtos/lotes/{a.lote.id}/",
                'icon': 'exclamation-triangle',
                'type': 'red',
                'created_at': a.created_at,
            })

    return {
        'notifications': notifications,
        'notifications_count': len(notifications)
    }





def modules_context(request):
    """Idem — módulos activos da licença do tenant."""
    if connection.schema_name == 'public':
        return {}

    if not request.user.is_authenticated or not hasattr(request.user, 'funcionario') or not request.user.funcionario:
        return {}

    empresa_atual = getattr(request, 'tenant', None)
    licenca = getattr(empresa_atual, "licenca", None)
    modulos_ativos = []

    if licenca:
        modulos_ativos = list(licenca.plano.modulos.filter(ativo=True).values_list('slug', flat=True))

    return {
        "modulos_ativos": modulos_ativos
    }

"""Views tenant-aware para catálogo, agendamentos e notificações."""
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from apps.empresas.models import Empresa
from .forms import ServicoForm, AgendamentoServicoForm, FinalizarServicoForm, NotificacaoAgendamentoForm, ConfiguracaoNotificacaoForm
from .models import Servico, AgendamentoServico, NotificacaoAgendamento, ConfiguracaoNotificacao

logger = logging.getLogger(__name__)


def empresa_da_requisicao(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return None
    return tenant


def _sem_empresa_json():
    return JsonResponse({"success": False, "message": "Empresa/tenant não encontrada para esta requisição."}, status=400)


class ServicoPermissionMixin(LoginRequiredMixin):
    """Aplica o isolamento por empresa às views genéricas."""
    def get_empresa(self):
        return empresa_da_requisicao(self.request)

    def dispatch(self, request, *args, **kwargs):
        # Deixa primeiro o LoginRequiredMixin redireccionar utilizadores anónimos.
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if self.get_empresa() is None:
            messages.error(request, "Não foi possível identificar a empresa activa.")
            return redirect("home")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        empresa = self.get_empresa()
        if empresa is None:
            return self.model.objects.none()
        fields = {field.name for field in self.model._meta.get_fields() if getattr(field, "concrete", False)}
        if "empresa" in fields:
            return self.model.objects.filter(empresa=empresa)
        # Não retorna dados de outros tenants caso o modelo seja schema-local.
        return self.model.objects.none()


class ServicoDashboard(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = "servicos/dashboard_servicos.html"
    context_object_name = "servicos"
    paginate_by = 8

    def get_queryset(self):
        return super().get_queryset().select_related("categoria").order_by("nome")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx["total_servicos"] = qs.count()
        ctx["servicos_ativos"] = qs.filter(ativo=True).count()
        ctx["servicos_inativos"] = qs.filter(ativo=False).count()
        ctx["agendamentos_pendentes"] = AgendamentoServico.objects.filter(status="agendado").count()
        ctx["agendamentos_em_andamento"] = AgendamentoServico.objects.filter(status="em_andamento").count()
        return ctx


class ServicoListView(ServicoPermissionMixin, ListView):
    model = Servico
    template_name = "servicos/servico_list.html"
    context_object_name = "servicos"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("categoria")
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "")
        if query: qs = qs.filter(Q(nome__icontains=query) | Q(instrucoes_padrao__icontains=query))
        if estado == "ativo": qs = qs.filter(ativo=True)
        elif estado == "inativo": qs = qs.filter(ativo=False)
        return qs.order_by("nome")


class ServicoCreateView(ServicoPermissionMixin, CreateView):
    model = Servico
    form_class = ServicoForm
    template_name = "servicos/servico_form.html"
    success_url = reverse_lazy("servicos:servico_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs["empresa"] = self.get_empresa(); return kwargs

    def form_valid(self, form):
        form.instance.empresa = self.get_empresa()
        response = super().form_valid(form)
        messages.success(self.request, "Serviço de catálogo criado com sucesso.")
        return response


class ServicoUpdateView(ServicoPermissionMixin, UpdateView):
    model = Servico
    form_class = ServicoForm
    template_name = "servicos/servico_form.html"
    success_url = reverse_lazy("servicos:servico_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs["empresa"] = self.get_empresa(); return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Serviço de catálogo actualizado com sucesso.")
        return response


class ServicoDeleteView(ServicoPermissionMixin, DeleteView):
    model = Servico
    template_name = "servicos/servico_confirm_delete.html"
    success_url = reverse_lazy("servicos:servico_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.agendamentos.exists():
            messages.error(request, "Este serviço já está associado a agendamentos. Desactive-o em vez de o eliminar, para preservar o histórico.")
            return redirect(self.success_url)
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "O serviço está protegido por registos relacionados e não pode ser eliminado.")
            return redirect(self.success_url)

    def form_valid(self, form):
        nome = self.object.nome
        response = super().form_valid(form)
        messages.success(self.request, f"Serviço '{nome}' eliminado com sucesso.")
        return response


class AgendamentoListView(ServicoPermissionMixin, ListView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_list.html"
    context_object_name = "agendamentos"
    paginate_by = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = AgendamentoServico.STATUS_CHOICES
        return context

    def get_queryset(self):
        qs = super().get_queryset().select_related("servico", "cliente", "funcionario")
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        if query: qs = qs.filter(Q(cliente__nome_completo__icontains=query) | Q(servico__nome__icontains=query) | Q(funcionario__nome_completo__icontains=query))
        if status in dict(AgendamentoServico.STATUS_CHOICES): qs = qs.filter(status=status)
        return qs


class AgendamentoCreateView(ServicoPermissionMixin, CreateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = "servicos/agendamento_form.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs["empresa"] = self.get_empresa(); return kwargs

    def form_valid(self, form):
        form.instance.empresa = self.get_empresa()
        if not form.instance.valor_cobrado and form.cleaned_data.get("servico"):
            form.instance.valor_cobrado = form.cleaned_data["servico"].preco_com_desconto
        response = super().form_valid(form)
        messages.success(self.request, "Agendamento criado com sucesso.")
        return response


class AgendamentoUpdateView(ServicoPermissionMixin, UpdateView):
    model = AgendamentoServico
    form_class = AgendamentoServicoForm
    template_name = "servicos/agendamento_form.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs(); kwargs["empresa"] = self.get_empresa(); return kwargs

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Agendamento actualizado com sucesso.")
        return response


class AgendamentoDeleteView(ServicoPermissionMixin, DeleteView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_confirm_delete.html"
    success_url = reverse_lazy("servicos:agendamento_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.notificacoes.exists():
            messages.error(request, "Este agendamento tem notificações associadas. Cancele o agendamento ou preserve o histórico; elimine primeiro as notificações se tiver autorização.")
            return redirect("servicos:agendamento_detail", pk=self.object.pk)
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, "O agendamento está protegido por registos relacionados.")
            return redirect("servicos:agendamento_detail", pk=self.object.pk)

    def form_valid(self, form):
        description = f"{self.object.servico} — {self.object.cliente}"
        response = super().form_valid(form)
        messages.success(self.request, f"Agendamento '{description}' eliminado.")
        return response


class AgendamentoDetailView(ServicoPermissionMixin, DetailView):
    model = AgendamentoServico
    template_name = "servicos/agendamento_detail.html"
    context_object_name = "agendamento"

    def get_queryset(self):
        return super().get_queryset().select_related("servico", "cliente", "funcionario")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["finalizar_form"] = FinalizarServicoForm()
        return context


class IniciarServicoView(ServicoPermissionMixin, View):
    http_method_names = ["post"]
    def post(self, request, pk, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoServico.objects.filter(empresa=self.get_empresa()), pk=pk)
        try:
            agendamento.iniciar()
            messages.success(request, f"O serviço '{agendamento.servico.nome}' foi iniciado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("servicos:agendamento_detail", pk=agendamento.pk)


class FinalizarServicoView(ServicoPermissionMixin, View):
    http_method_names = ["post"]
    def post(self, request, pk, *args, **kwargs):
        agendamento = get_object_or_404(AgendamentoServico.objects.filter(empresa=self.get_empresa()), pk=pk)
        form = FinalizarServicoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Preencha o resultado do serviço antes de finalizar.")
        else:
            try:
                agendamento.finalizar(form.cleaned_data["resultado_servico"], form.cleaned_data["recomendacoes"])
                messages.success(request, "Agendamento finalizado com sucesso.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        return redirect("servicos:agendamento_detail", pk=agendamento.pk)


def _api_tenant(request):
    empresa = empresa_da_requisicao(request)
    return empresa


@login_required
@require_GET
def buscar_agendamento_api(request):
    empresa = _api_tenant(request)
    if empresa is None: return _sem_empresa_json()
    qs = AgendamentoServico.objects.filter(empresa=empresa).select_related("cliente", "servico", "funcionario")
    query, status = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if status in dict(AgendamentoServico.STATUS_CHOICES): qs = qs.filter(status=status)
    if query: qs = qs.filter(Q(cliente__nome_completo__icontains=query) | Q(servico__nome__icontains=query) | Q(funcionario__nome_completo__icontains=query))
    results = [{"id": a.pk, "data_hora": a.data_hora.isoformat(), "servico": a.servico.nome, "cliente": getattr(a.cliente, "nome_completo", str(a.cliente)), "funcionario": getattr(a.funcionario, "nome_completo", "") if a.funcionario_id else "", "status": a.status, "status_display": a.get_status_display()} for a in qs.order_by("data_hora")[:100]]
    return JsonResponse({"success": True, "agendamentos": results, "total_encontrados": len(results)})


@login_required
@require_GET
def listar_servicos_api(request):
    empresa = _api_tenant(request)
    if empresa is None: return _sem_empresa_json()
    qs = Servico.objects.filter(ativo=True).select_related("categoria").order_by("nome")[:500]
    results = [{"id": s.pk, "nome": s.nome, "categoria": str(s.categoria), "categoria_id": s.categoria_id, "preco": float(s.preco_com_desconto), "preco_padrao": float(s.preco_padrao), "desconto_percentual": float(s.desconto_percentual), "iva_percentual": float(s.iva_percentual), "descricao": s.instrucoes_padrao, "disponivel": s.ativo} for s in qs]
    return JsonResponse({"success": True, "servicos": results, "total_encontrados": len(results)})


@login_required
@require_GET
def buscar_servicos_api(request):
    empresa = _api_tenant(request)
    if empresa is None: return _sem_empresa_json()
    qs = Servico.objects.filter(ativo=True).select_related("categoria")
    query, categoria = request.GET.get("q", "").strip(), request.GET.get("categoria", "").strip()
    if query: qs = qs.filter(nome__icontains=query)
    if categoria and categoria != "todos":
        if not categoria.isdigit(): return JsonResponse({"success": False, "message": "Categoria inválida."}, status=400)
        qs = qs.filter(categoria_id=int(categoria))
    rows = [{"id": s.pk, "nome": s.nome, "categoria": str(s.categoria), "categoria_id": s.categoria_id, "preco_padrao": float(s.preco_padrao), "preco_com_desconto": float(s.preco_com_desconto), "desconto_percentual": float(s.desconto_percentual), "iva_percentual": float(s.iva_percentual)} for s in qs.order_by("nome")[:100]]
    return JsonResponse({
        "success": True, 
        "servicos": rows, 
        "total_encontrados": len(rows)
        })


@login_required
def notificacao_list(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    qs = NotificacaoAgendamento.objects.filter(empresa=empresa).select_related("cliente", "agendamento", "agendamento__servico")
    query, status = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if query: qs = qs.filter(Q(titulo__icontains=query) | Q(cliente__nome_completo__icontains=query) | Q(mensagem__icontains=query))
    if status in dict(NotificacaoAgendamento.STATUS_CHOICES): qs = qs.filter(status=status)
    return render(request, "servicos/notificacao_list.html", {"notificacoes": qs.order_by("-data_agendada_envio")[:100], "status_choices": NotificacaoAgendamento.STATUS_CHOICES, "query": query, "status_filter": status})


@login_required
def notificacao_create(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None: return redirect("home")
    form = NotificacaoAgendamentoForm(request.POST or None, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        notificacao = form.save(commit=False)
        notificacao.empresa = empresa
        if notificacao.agendamento.empresa_id != empresa.pk:
            form.add_error("agendamento", "O agendamento pertence a outra empresa.")
        else:
            notificacao.save()
            messages.success(request, "Notificação criada com sucesso.")
            return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_form.html", {"form": form, "titulo": "Criar notificação"})


@login_required
def notificacao_update(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None: return redirect("home")
    notificacao = get_object_or_404(NotificacaoAgendamento, pk=pk, empresa=empresa)
    form = NotificacaoAgendamentoForm(request.POST or None, instance=notificacao, empresa=empresa)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False); updated.empresa = empresa; updated.save()
        messages.success(request, "Notificação actualizada com sucesso.")
        return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_form.html", {"form": form, "titulo": "Editar notificação", "notificacao": notificacao})


@login_required
def notificacao_delete(request, pk):
    empresa = empresa_da_requisicao(request)
    if empresa is None: return redirect("home")
    notificacao = get_object_or_404(NotificacaoAgendamento, pk=pk, empresa=empresa)
    if request.method == "POST":
        notificacao.delete(); messages.success(request, "Notificação eliminada com sucesso.")
        return redirect("servicos:notificacao_list")
    return render(request, "servicos/notificacao_confirm_delete.html", {"notificacao": notificacao})


@login_required
@require_GET
def buscar_notificacao_api(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None: return _sem_empresa_json()
    qs = NotificacaoAgendamento.objects.filter(empresa=empresa).select_related("cliente", "agendamento", "agendamento__servico")
    query, status = request.GET.get("q", "").strip(), request.GET.get("status", "").strip()
    if query: qs = qs.filter(Q(titulo__icontains=query) | Q(cliente__nome_completo__icontains=query) | Q(mensagem__icontains=query))
    if status in dict(NotificacaoAgendamento.STATUS_CHOICES): qs = qs.filter(status=status)
    rows = [{"id": n.pk, "titulo": n.titulo, "cliente": getattr(n.cliente, "nome_completo", str(n.cliente)), "tipo_notificacao": n.get_tipo_notificacao_display(), "status": n.get_status_display(), "data_agendada_envio": timezone.localtime(n.data_agendada_envio).strftime("%d/%m/%Y %H:%M")} for n in qs.order_by("-data_agendada_envio")[:50]]
    return JsonResponse({"success": True, "notificacoes": rows, "total": len(rows)})


@login_required
def configuracao_notificacao_update(request):
    empresa = empresa_da_requisicao(request)
    if empresa is None:
        messages.error(request, "Empresa activa não encontrada.")
        return redirect("home")
    config, _ = ConfiguracaoNotificacao.objects.get_or_create(empresa=empresa)
    form = ConfiguracaoNotificacaoForm(request.POST or None, instance=config)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False); saved.empresa = empresa; saved.save()
        messages.success(request, "Configurações de notificação guardadas.")
        return redirect("servicos:config_notificacao")
    return render(request, "servicos/configuracao_form.html", {"form": form, "config": config})
