TIPO_IMPOSTO_CHOICES = [
        # I - IMPOSTO SOBRE O VALOR ACRESCENTADO (IVA)
        ('01I', '01I - IVA - Regime Geral'),
        ('02I', '02I - IVA - Importação'),
        ('03I', '03I - IVA - Regime Geral'),
        ('04I', '04I - IVA - Regime Simplificado'),
        ('05I', '05I - IVA - Regime Transitório'),
        ('06I', '06I - IVA - Outros'),
        
        # A - IMPOSTO SOBRE APLICAÇÃO DE CAPITAIS
        ('01A', '01A - IAC - Títulos do Banco Central'),
        ('02A', '02A - IAC - Bilhetes e Obrigações do Tesouro'),
        ('03A', '03A - IAC - Depósito à Ordem'),
        ('04A', '04A - IAC - Depósito a Prazo'),
        ('05A', '05A - IAC - Dividendos/Lucros'),
        ('06A', '06A - IAC - Juros de Suprimentos'),
        ('07A', '07A - IAC - Mais Valias'),
        ('08A', '08A - IAC - Operações do Mercado Monetário'),
        ('09A', '09A - IAC - Royalties'),
        ('10A', '10A - IAC - Outros'),
        
        # B - IMPOSTO SOBRE RENDIMENTO DO TRABALHO
        ('01B', '01B - IRT - Grupo A - Conta de Outrem'),
        ('02B', '02B - IRT - Grupo B - Conta Própria'),
        ('03B', '03B - IRT - Grupo C - Atividades Comerciais e Industriais'),
        
        # C - IMPOSTO INDUSTRIAL
        ('01C', '01C - II - Regime Geral'),
        ('02C', '02C - II - Regime Simplificado'),
        ('03C', '03C - II - Retenção na Fonte - Residentes'),
        ('04C', '04C - II - Retenção na Fonte - Não Residentes'),
        ('05C', '05C - II - Diamantes'),
        ('06C', '06C - II - Ouro'),
        ('07C', '07C - II - Outros Minerais'),
        
        # D - IMPOSTOS ESPECIAIS DE JOGOS
        ('01D', '01D - IEJ - Casino'),
        ('02D', '02D - IEJ - Totobola'),
        ('03D', '03D - IEJ - Totoloto'),
        ('04D', '04D - IEJ - Angomilhões'),
        ('05D', '05D - IEJ - Outros Tipos de Jogos Sociais'),
        ('06D', '06D - IEJ - Apostas Hípicas'),
        ('07D', '07D - IEJ - Rifas e Concursos'),
        ('08D', '08D - IEJ - Combinações Aleatórias'),
        ('09D', '09D - IEJ - Lotarias'),
        ('10D', '10D - IEJ - Outros Jogos Presenciais'),
        ('11D', '11D - IEJ - Prémios - Casino'),
        ('12D', '12D - IEJ - Online - Receita Bruta'),
        ('13D', '13D - IEJ - Online - Prémios'),
        ('14D', '14D - IEJ - Prémios - Totobola'),
        ('15D', '15D - IEJ - Prémios - Totoloto'),
        ('16D', '16D - IEJ - Prémios - Angomilhões'),
        ('17D', '17D - IEJ - Prémios Online'),
        ('18D', '18D - IEJ - Prémios - Apostas Hípicas'),
        ('19D', '19D - IEJ - Prémios - Apostas Hípicas'),
        ('20D', '20D - IEJ - Prémios - Lotarias'),
        
        # E - IMPOSTOS PETROLÍFEROS
        ('01E', '01E - IP - Rendimentos do Petróleo'),
        ('02E', '02E - ITP - Transações de Petróleo'),
        
        # F - IMPOSTOS SOBRE BENS IMÓVEIS (PREDIAIS)
        ('01F', '01F - IP - Predial sobre a Detenção'),
        ('02F', '02F - IP - Predial sobre Transmissões Onerosas'),
        ('03F', '03F - IP - Predial sobre Transmissões Gratuitas'),
        ('04F', '04F - IP - Predial sobre a Renda'),
        
        # G - IMPOSTOS SOBRE BENS MÓVEIS
        ('01G', '01G - IBM - Veículos Automotores - Ligeiros'),
        ('02G', '02G - IBM - Veículos Automotores - Pesados'),
        ('03G', '03G - IBM - Motociclos, Ciclomotores, Triciclos e Quadriciclos'),
        ('04G', '04G - IBM - Veículos Automotores - Aeronaves'),
        ('05G', '05G - IBM - Veículos Automotores - Embarcações'),
        ('06G', '06G - IBM - Sucessões'),
        ('07G', '07G - IBM - Doações'),
        
        # H - IMPOSTOS SOBRE A PRODUÇÃO
        ('01H', '01H - IPD - Produção de Petróleo'),
        ('02H', '02H - IPD - Produção de Diamantes - Royalty'),
        ('03H', '03H - IPD - Produção de Ouro - Royalty'),
        ('04H', '04H - IPD - Produção de Outros Minerais - Royalty'),
        
        # J - IMPOSTO ESPECIAL DE CONSUMO
        ('01J', '01J - IEC - Aeronaves e Embarcações de Recreio'),
        ('02J', '02J - IEC - Álcool e Outras Bebidas Alcoólicas'),
        ('03J', '03J - IEC - Armas de Fogo'),
        ('04J', '04J - IEC - Artefatos de Joalharia, Ourivesaria e Outros'),
        ('05J', '05J - IEC - Bebidas Açucaradas'),
        ('06J', '06J - IEC - Bebidas Energéticas'),
        ('07J', '07J - IEC - Cerveja'),
        ('08J', '08J - IEC - Fogo-de-artifício'),
        ('09J', '09J - IEC - Objetos de Arte, Coleção e Antiguidades'),
        ('10J', '10J - IEC - Produtos Derivados do Petróleo: Gasolina e Gasóleo'),
        ('11J', '11J - IEC - Tabaco e seus Derivados'),
        ('12J', '12J - IEC - Veículos Automóveis'),
        ('13J', '13J - IEC - Produtos Derivados do Petróleo: Gás Natural, Butano, Propano'),
        ('14J', '14J - IEC - Produtos Derivados do Petróleo - Outros'),
        
        # K - IMPOSTOS SOBRE O COMÉRCIO EXTERNO
        ('01K', '01K - ICE - Exportação'),
        ('02K', '02K - ICE - Importação'),
        
        # L - IMPOSTOS DE SELO
        ('01L', '01L - IS - Contrato de Arrendamento'),
        ('02L', '02L - IS - Operações Bancárias'),
        ('03L', '03L - IS - Recibo de Quitação'),
        ('04L', '04L - IS - Operações Isentas (Regime Geral)'),
        ('05L', '05L - IS - Operações Isentas (Regime Simplificado)'),
        ('06L', '06L - IS - Outros'),
        
        # P - MULTAS E JUROS
        ('01P', '01P - Multas Fiscais pela não Entrega da Declaração'),
        ('02P', '02P - Multas Fiscais pelo não Pagamento da Prestação da Dívida Tributária'),
        ('03P', '03P - Multa Substitutiva de Confisco Aduaneiro'),
        ('04P', '04P - Multas Fiscais'),
        ('05P', '05P - Multas Aduaneiras'),
        ('06P', '06P - Multas Institucionais'),
        ('07P', '07P - Adicional de 10% sobre as Multas Fiscais'),
        ('08P', '08P - Juros de Mora'),
        ('09P', '09P - Juros Compensatórios'),
        
        # Q - CONTRIBUIÇÕES
        ('01Q', '01Q - Contribuições para o Fundo de Desenvolvimento Mineiro'),
        ('02Q', '02Q - Contribuições para Formação de Quadros Angolanos'),
    ]
    