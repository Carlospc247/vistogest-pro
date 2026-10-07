# apps/core/choices.py
"""
Choices partilhadas entre apps/core (SHARED_APPS) e TENANT_APPS.
Importar daqui para garantir consistência em todo o sistema.
"""

FORMA_PAGAMENTO_CHOICES = [
    ('dinheiro', 'Dinheiro'),
    ('cartao_debito', 'Cartão de Débito'),
    ('cartao_credito', 'Cartão de Crédito'),
    ('transferencia', 'Transferência'),
    ('cheque', 'Cheque'),
    ('vale', 'Vale'),
    ('outros', 'Outros'),
]


TIPO_RETENCAO_CHOICES = [
    ('IRT',  'IRT — Imposto Sobre os Rendimentos do Trabalho'),
    ('II',   'II — Imposto Industrial'),
    ('IS',   'IS — Imposto de Selo'),
    ('IVA',  'IVA — Imposto sobre o Valor Acrescentado (Cativo)'),
    ('IP',   'IP — Imposto Predial'),
    ('IAC',  'IAC — Imposto sobre Aplicação de Capitais'),
    ('OU',   'OU — Outros'),
    ('IRPC', 'IRPC — Imposto sobre Rendimento de Pessoas Colectivas'),
    ('IRPS', 'IRPS — Imposto sobre Rendimento de Pessoas Singulares'),
]

# Nota: IRPC e IRPS mantêm-se como tipos válidos desde já.
# O IRPS tem data de entrada em vigor em Jan/2027, mas ao momento da
# certificação AGT esse prazo já terá passado. O bloqueio foi removido.
# Fonte: decisão do dono do sistema (PLANO_IMPLEMENTACAO.md Secção 3.4.9)


# operationType — tipo de operação por linha (Decreto Executivo 683/25, Anexo I)
# Obrigatório em cada linha do payload registarFactura e no SAF-T.
OPERATION_TYPE_CHOICES = [
    ('SE',  'SE — Serviços prestados em território nacional'),
    ('SS',  'SS — Serviços prestados no estrangeiro'),
    ('STP', 'STP — Serviços de telecomunicações e prestados por via electrónica'),
    ('SR',  'SR — Serviços relacionados com imóveis'),
    ('SIF', 'SIF — Serviços de intermediação financeira'),
    ('SHS', 'SHS — Serviços de hotelaria e similares'),
    ('ST',  'ST — Serviços de transporte'),
    ('SG',  'SG — Serviços em geral não especificados'),
    ('TB',  'TB — Transmissão de bens'),
    ('AS',  'AS — Aquisição de serviços'),
    ('QT',  'QT — Outras operações tributáveis'),
    ('RD',  'RD — Regularizações e devoluções'),
]
