# apps/integracoes/services/catalogo.py
CATALOGO = [
    dict(
        codigo='whatsapp_cloud', nome='WhatsApp Business (Cloud API)', categoria='mensageria',
        icone='fab fa-whatsapp', ordem=10, suporta_webhook=True,
        descricao='Envio de mensagens e recepção de eventos (mensagens e estados) pela API Cloud da Meta.',
        url_base='https://graph.facebook.com', metodo_autenticacao='bearer_token',
        url_documentacao='https://developers.facebook.com/docs/whatsapp/cloud-api',
        esquema_credenciais=[
            dict(chave='access_token', label='Token de acesso', segredo=True, ajuda='Token permanente de um utilizador de sistema.'),
            dict(chave='phone_number_id', label='ID do número de telefone', segredo=False),
            dict(chave='app_secret', label='App Secret', segredo=True, obrigatorio=False, ajuda='Necessário para validar a assinatura dos webhooks.'),
            dict(chave='verify_token', label='Token de verificação do webhook', segredo=True, obrigatorio=False, ajuda='Texto livre; o mesmo que indicar na Meta.'),
        ],
        esquema_configuracoes=[dict(chave='api_version', label='Versão da API', tipo='text', padrao='v21.0')],
        passos=[
            'Em developers.facebook.com crie uma App do tipo Business e adicione o produto WhatsApp.',
            'Em WhatsApp > API Setup copie o "Phone number ID". Crie um utilizador de sistema no Business Manager e gere um token permanente com a permissão whatsapp_business_messaging.',
            'Aqui, clique em Configurar, preencha o token e o ID do número, e grave.',
            'Em WhatsApp > Configuration > Webhook indique o URL de webhook (página de detalhe) e o mesmo token de verificação; subscreva o campo "messages". Copie o App Secret (Settings > Basic) para cá.',
            'Clique em Testar ligação e depois Activar. Use "Enviar mensagem de teste" para um número que já tenha falado com o vosso número.',
            'Atenção: texto livre só é entregue dentro de 24 h depois de o cliente escrever; fora dessa janela a Meta exige modelos de mensagem aprovados.',
        ]),
    dict(
        codigo='twilio', nome='Twilio (SMS / WhatsApp)', categoria='mensageria', icone='fas fa-sms', ordem=20,
        suporta_webhook=True, descricao='SMS ou WhatsApp através da Twilio.', url_base='https://api.twilio.com',
        metodo_autenticacao='basic_auth', url_documentacao='https://www.twilio.com/docs/messaging',
        esquema_credenciais=[
            dict(chave='account_sid', label='Account SID', segredo=False),
            dict(chave='auth_token', label='Auth Token', segredo=True),
            dict(chave='remetente', label='Número/ID do remetente', segredo=False, ajuda='Ex.: +14155550100. Para WhatsApp, o número do sandbox ou aprovado.'),
        ],
        esquema_configuracoes=[dict(chave='canal', label='Canal', tipo='choice', opcoes=['sms', 'whatsapp'], padrao='sms')],
        passos=[
            'Na consola da Twilio copie o Account SID e o Auth Token.',
            'Compre/active um número (ou use o sandbox de WhatsApp) e indique-o como remetente.',
            'Escolha o canal (sms ou whatsapp), grave, teste a ligação e active.',
            'Confirme que o destino é permitido na vossa conta (contas de teste só enviam para números verificados) e que o país está activado nas Geo Permissions.',
            'Para receber respostas/estados, use o URL de webhook desta página como "Status callback"/"Webhook" na Twilio.',
        ]),
    dict(
        codigo='sendgrid', nome='SendGrid (e-mail transaccional)', categoria='email', icone='fas fa-envelope', ordem=30,
        descricao='Envio de e-mails por API (facturas, avisos, notificações).', url_base='https://api.sendgrid.com',
        metodo_autenticacao='bearer_token', url_documentacao='https://docs.sendgrid.com/api-reference/mail-send/mail-send',
        esquema_credenciais=[dict(chave='api_key', label='API Key', segredo=True, ajuda='Permissão "Mail Send".')],
        esquema_configuracoes=[
            dict(chave='remetente', label='E-mail remetente (verificado)', tipo='text', padrao=''),
            dict(chave='nome_remetente', label='Nome do remetente', tipo='text', padrao=''),
        ],
        passos=[
            'Na SendGrid crie uma API Key com permissão de envio (Mail Send).',
            'Verifique o remetente (Single Sender) ou autentique o vosso domínio (SPF/DKIM).',
            'Aqui, preencha a API Key e o e-mail do remetente verificado, grave e teste.',
            'Active a integração e use "Enviar mensagem de teste" com o vosso e-mail.',
        ]),
    dict(
        codigo='webhook_saida', nome='Webhook de saída', categoria='api', icone='fas fa-share-square', ordem=40,
        descricao='Envia eventos do VistoGest (ex.: venda finalizada) para um sistema vosso, assinados com HMAC.',
        metodo_autenticacao='hmac',
        esquema_credenciais=[
            dict(chave='url_destino', label='URL de destino (https)', segredo=False),
            dict(chave='segredo_hmac', label='Segredo partilhado', segredo=True, ajuda='O vosso sistema usa-o para validar X-Webhook-Signature.'),
        ],
        esquema_configuracoes=[dict(chave='eventos', label='Eventos subscritos', tipo='text', padrao='*', )],
        passos=[
            'Crie no vosso sistema um endpoint HTTPS que aceite POST JSON.',
            'Defina um segredo partilhado (mín. 32 caracteres aleatórios) e guarde-o nos dois lados.',
            'Aqui, indique o URL e o segredo. Em "Eventos" use * (todos) ou uma lista separada por vírgulas.',
            'Teste a ligação: é enviado o evento "ping". Valide a assinatura no vosso lado (ver o guia de webhooks).',
            'No código do VistoGest emita eventos com emitir_evento("venda.finalizada", {...}).',
        ]),
    dict(
        codigo='api_personalizada', nome='API REST personalizada', categoria='api', icone='fas fa-code', ordem=50,
        suporta_webhook=True, descricao='Cliente REST para qualquer serviço com autenticação por chave/token, mais receptor de webhooks genérico.',
        metodo_autenticacao='api_key',
        esquema_credenciais=[
            dict(chave='base_url', label='URL base (https)', segredo=False),
            dict(chave='api_key', label='Chave / token', segredo=True),
        ],
        esquema_configuracoes=[
            dict(chave='cabecalho_auth', label='Cabeçalho de autenticação', tipo='text', padrao='Authorization'),
            dict(chave='prefixo_auth', label='Prefixo do valor', tipo='text', padrao='Bearer '),
            dict(chave='endpoint_teste', label='Endpoint de teste (GET)', tipo='text', padrao='/'),
        ],
        passos=[
            'Obtenha a URL base e a chave/token na documentação do serviço.',
            'Indique o cabeçalho e o prefixo exigidos (ex.: X-API-Key e prefixo vazio, ou Authorization e "Bearer ").',
            'Defina um endpoint de teste seguro (GET) e use Testar ligação.',
            'Para receber eventos, use o URL de webhook e o segredo desta página (assinatura X-Webhook-Signature).',
        ]),
    dict(
        codigo='gateway_pagamento', nome='Gateway de pagamentos (REST)', categoria='pagamento',
        icone='fas fa-credit-card', ordem=60, suporta_webhook=True,
        descricao='Para gateways/bancos que ofereçam API REST (referências de pagamento, pagamento online). Os endpoints concretos dependem do contrato com o fornecedor.',
        metodo_autenticacao='api_key',
        esquema_credenciais=[
            dict(chave='base_url', label='URL base da API (https)', segredo=False),
            dict(chave='api_key', label='Chave / token', segredo=True),
        ],
        esquema_configuracoes=[
            dict(chave='cabecalho_auth', label='Cabeçalho de autenticação', tipo='text', padrao='Authorization'),
            dict(chave='prefixo_auth', label='Prefixo do valor', tipo='text', padrao='Bearer '),
            dict(chave='endpoint_teste', label='Endpoint de teste (GET)', tipo='text', padrao='/'),
        ],
        passos=[
            'Peça ao fornecedor as credenciais de sandbox, a URL base e a documentação dos endpoints e do webhook.',
            'Configure aqui em ambiente "Teste", teste a ligação e só depois mude para "Produção" com as credenciais reais.',
            'Configure no portal do fornecedor o URL de webhook desta página; confirme com ele o método de assinatura (se não for HMAC-SHA256 em X-Webhook-Signature, é preciso um conector dedicado).',
            'A lógica de negócio (ex.: marcar a factura como paga) implementa-se em processar_webhook do provider.',
        ]),
]


def garantir_catalogo(forcar=False):
    from ..models import TipoIntegracao
    if not forcar and TipoIntegracao.objects.count() >= len(CATALOGO):
        return
    for item in CATALOGO:
        dados = dict(item)
        TipoIntegracao.objects.update_or_create(codigo=dados.pop('codigo'), defaults=dados)
