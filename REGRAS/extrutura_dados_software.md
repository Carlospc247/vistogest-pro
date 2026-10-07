# Estrutura de Dados do Software — Facturação Electrónica

> Reescrita técnica do **Decreto Executivo n.º 683/25, de 22 de Agosto**, publicado no *Diário da República*, I Série, n.º 159. O conteúdo abaixo reorganiza a informação do PDF em Markdown, mantendo os nomes dos campos JSON, serviços, códigos e tabelas de referência.

## Escopo do documento

O diploma define a estrutura de dados de software, o modelo de facturação electrónica e as respectivas especificações técnicas e procedimentais, nos termos do artigo 36.º do Decreto Presidencial n.º 71/25, de 20 de Março, bem como a competência para gerar as séries de facturas.

**Nota sobre o PDF de origem:** o ficheiro enviado contém, depois do Decreto Executivo n.º 683/25, um aviso autónomo do Banco Nacional de Angola a partir da página 66. Essa parte não integra a estrutura de dados do software e, por isso, não foi incluída nesta reescrita.

## Índice

1. [Decreto Executivo n.º 683/25](#decreto-executivo-n-68325)
2. [Anexo I — Estrutura de Dados do Software](#anexo-i--estrutura-de-dados-do-software)
3. [Anexo II — Modelo de Facturação Electrónica](#anexo-ii--modelo-de-facturação-electrónica)
4. [Anexo III — Especificações Técnicas](#anexo-iii--especificações-técnicas)
5. [Tabela 1 — CAE](#tabela-1--códigos-de-actividade-económica--cae)
6. [Tabela 2 — IEC](#tabela-2--taxas-do-imposto-especial-de-consumo-iec)
7. [Tabela 3 — Imposto do Selo](#tabela-3--verbas-e-taxas-de-imposto-de-selo-is)
8. [Tabela 4 — Isenções de IVA](#tabela-4--isenções-de-imposto-sobre-o-valor-acrescentado-iva)
9. [Tabela 5 — Isenções de IS](#tabela-5--isenções-de-imposto-de-selo-is)
10. [Tabela 6 — Isenções de IEC](#tabela-6--isenções-de-imposto-especial-de-consumo-iec)

---

# Decreto Executivo n.º 683/25

## Artigo 1.º — Objecto

O diploma define:

- a estrutura de dados de software;
- o modelo de facturação electrónica;
- as especificações técnicas e procedimentais do sistema de facturação electrónica; e
- a competência para gerar as séries de facturas.

## Artigo 2.º — Estrutura de dados e especificações técnicas

A estrutura de dados do software, o modelo de facturação electrónica e as especificações técnicas e procedimentais correspondem aos **Anexos I, II e III**, que são parte integrante do Decreto Executivo.

## Artigo 3.º — Actualizações

A Administração Geral Tributária (AGT) disponibiliza aos contribuintes e aos produtores de software de facturação, sempre que necessário, as actualizações das especificações técnicas e procedimentais.

## Artigo 4.º — Séries de facturas

As séries utilizadas pelos contribuintes que emitem facturas em software de facturação electrónica são geradas pela **AGT**.

## Artigo 5.º — Dúvidas e omissões

As dúvidas e omissões resultantes da interpretação e aplicação do diploma são resolvidas pela Ministra das Finanças.

## Artigo 6.º — Entrada em vigor

O Decreto Executivo entra em vigor **30 dias após a data da sua publicação**.

**Luanda, 15 de Agosto de 2025** — A Ministra, **Vera Esperança dos Santos Daves de Sousa**.

---

# Anexo I — Estrutura de Dados do Software

## 1. Serviço `registarFactura` — Solicitar Registo de Factura Electrónica

Serviço destinado a receber pedidos de registo de facturas electrónicas. A resposta devolve o identificador único do pedido, necessário para acompanhar a validação posterior. Quando o pedido não é aceite, são devolvidos os problemas que conduziram à rejeição.

### Parâmetros de entrada

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema do serviço. Exemplo indicado: `1.0`. |
| submissionGUID | string | Sim | GUID/UUID da solicitação, em formato standard; deve ser único por contribuinte emissor. Exemplo: `55088400-e29b-41d4-a716-446655440000`. |
| taxRegistrationNumber | string; max 15 | Sim | Número fiscal de contribuinte. |
| submissionTimeStamp | string; ISO 8601 | Sim | Data/hora da submissão. Pode usar UTC (`Z`) ou indicar o timezone. |
| softwareInfo | object | Sim | Objecto com os dados do software de facturação. |
| numberOfEntries | integer | Sim | Número de facturas que constam na chamada. |
| documents | array | Sim | Lista de documentos. O serviço prevê um máximo de **30 facturas por pedido**. |

### Objecto `softwareInfo`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| softwareInfoDetail | object | Sim | Detalhes do software de facturação. |
| jwsSoftwareSignature | string; min 256 / max 256 | Sim | Assinatura do software de facturação, usando a chave privada do produtor e todos os campos do objecto `softwareInfo`. |

### Objecto `softwareInfoDetail`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| productId | string | Sim | Nome do software de facturação. |
| productVersion | string | Sim | Versão do software de facturação. |
| softwareValidationNumber | string | Sim | Número de certificação do software de facturação. |

### Array `documents`

Cada item é um objecto `document`. O máximo previsto é de 30 documentos.

### Objecto `document`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| documentNo | string; min 8 / max 60 | Sim | Identificação única do documento, gerada pelo software em conformidade com o SAF-T (AO). É constituída por um código interno do documento, espaço, número de série, `/` e número sequencial. |
| documentStatus | string; 1 caractere | Sim | Estado do documento: `N` Normal; `S` Autofacturação; `A` Anulado; `R` Documento de resumo de outros documentos criados noutras aplicações e gerado nesta aplicação; `C` Documento gerado para correcção de documento anteriormente gerado e rejeitado pela AGT. |
| documentCancelReason | string; 1 caractere | Não | Motivo da anulação. `I` = anulada por incorrecta identificação do adquirente; `N` = anulada por não ter sido enviada ao adquirente. Obrigatório quando `documentStatus = A`. |
| rejectedDocumentNo | string; min 8 / max 60 | Não | Número do documento anteriormente submetido à AGT e rejeitado. Obrigatório quando `documentStatus = C`. |
| jwsDocumentSignature | string; min 256 / max 256 | Sim | Assinatura da factura com a chave privada do emissor sobre `documentNo`, `taxRegistrationNumber`, `documentType`, `documentDate`, `customerTaxID`, `customerCountry`, `companyName` e `documentTotals`. |
| documentDate | string; date | Sim | Data de emissão do documento. |
| documentType | string; 2 caracteres | Sim | Tipo de documento de facturação electrónica. |
| eacCode | string; min 5 | Sim | Código de actividade relacionado com a actividade constante da Tabela 1. |
| systemEntryDate | string; date-time ISO 8601 | Sim | Timestamp de gravação do registo, no momento da assinatura. |
| customerCountry | string; ISO 3166-1 alpha-2 | Sim | Código do país do comprador. Para compradores domésticos utiliza-se `AO`. |
| customerTaxID | string | Sim | NIF do comprador. Para documentos domésticos sem identificação do comprador pode ser usado `999999999`. |
| companyName | string; max 100 | Sim | Nome/denominação do contribuinte ou comprador. |
| lines | array | Condicional | Linhas dos artigos/serviços. Não é preenchido para `AR`, `RC` e `RG`; é obrigatório para os demais tipos. |
| paymentReceipt | object | Condicional | Dados do recibo. Obrigatório para `AR`, `RC` e `RG`; não é preenchido nos restantes tipos. |
| documentTotals | object | Sim | Totais do documento. |
| withholdingTaxList | array | Não | Lista de retenções na fonte do documento. |

### Valores de `documentType`

| Código | Significado |
| --- | --- |
| FA | Factura de Adiantamento |
| FT | Factura |
| FR | Factura/Recibo |
| FG | Factura Global |
| AC | Aviso de Cobrança |
| AR | Aviso de Cobrança/Recibo |
| TV | Talão de Venda |
| RC | Recibo Emitido |
| RG | Outros Recibos Emitidos |
| RE | Estorno ou Recibo de Estorno |
| ND | Nota de Débito |
| NC | Nota de Crédito |
| AF | Factura/Recibo de Autofacturação |
| RP | Prémio ou Recibo de Prémio |
| RA | Resseguro Aceite |
| CS | Imputação a Co-seguradoras |
| LD | Imputação a Co-seguradora Líder |

### Array `lines` e objecto `line`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| lineNumber | integer | Sim | Número sequencial da linha, começando em 1 e incrementando 1. |
| productCode | string; min 1 / max 60 | Sim | Código do produto ou serviço. |
| productDescription | string; min 1 / max 200 | Sim | Descrição do produto ou serviço. |
| quantity | number; min 0 | Sim | Quantidade inteira ou decimal. |
| unitOfMeasure | string; min 7 / max 20 | Sim | Unidade de medida. |
| unitPrice | number; min 0 | Sim | Preço unitário sem descontos e sem impostos. |
| unitPriceBase | number; min 0 | Sim | Preço unitário já deduzido de descontos. |
| referenceInfo | object | Condicional | Referência do documento de origem. Obrigatório para `NC` para indicar a factura base da devolução. |
| debitAmount | number; min 0 | Condicional | Montante da linha, sem impostos e já deduzidos os descontos. |
| creditAmount | number; min 0 | Condicional | Montante da linha, sem impostos e já deduzidos os descontos. |
| taxes | array | Não | Impostos aplicados à linha. |
| settlementAmount | number; min 0 | Sim | Valor total dos descontos atribuídos à linha, incluindo a proporção do desconto global e o desconto específico da linha. |

Apenas um dos campos `debitAmount` e `creditAmount` poderá estar preenchido.

### Objecto `referenceInfo`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| reference | string; min 1 | Sim | Referência do documento de facturação de origem. |
| reason | string; max 60 | Não | Motivo da intervenção no documento de origem. |

### Array `taxes`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| taxType | string; 2–3 | Sim | Sistema de imposto: `IVA`, `IS`, `IEC` ou `NS` (não sujeito a IVA, IS ou IEC). |
| taxCountryRegion | string; 2–6 | Sim | Código do país segundo ISO 3166-1 alpha-2; para a região de Cabinda utiliza-se `AO-CAB`. |
| taxCode | string; 2–10 | Sim | Código dependente de `taxType`. Para IVA: `NOR`, `INT`, `RED`, `ISE`, `OUT`; para IS pode conter a verba de IS ou `ISE`; para IEC pode conter o código pautal ou `ISE`; para `NS`, usa-se `ISE`. |
| taxBase | number | Não | Valor tributável unitário quando a quantia da linha se refere apenas ao imposto e a respectiva base não constitui receita do sujeito passivo. |
| taxPercentage | number; min 0 | Não | Percentagem da taxa a aplicar. Ex.: `14` representa 14%. Deve ser `0` em caso de isenção ou não sujeição. |
| taxAmount | number | Não | Valor fixo da verba de IS, aplicado em função da quantidade. |
| taxContribution | number | Não | Valor calculado do imposto para a linha, com máximo de duas casas decimais e arredondamento por excesso ao cêntimo seguinte. |
| taxExemptionCode | string; min 3 | Condicional | Código do motivo de isenção. Preenchido para imposto isento e, no caso de `taxType = NS`, também obrigatoriamente. O código é obtido das Tabelas 4, 5 ou 6. |

#### Regras do campo `taxCode`

- **IVA:** `NOR` (taxa normal), `INT` (taxa intermédia), `RED` (taxa reduzida), `ISE` (isento), `OUT` (outra).
- **IS:** pode ser preenchido com a verba de IS constante da Tabela 3 ou `ISE`.
- **IEC:** pode ser preenchido com o código pautal da Tabela 2 ou `ISE`.
- **NS:** `taxCode = ISE`.

### Objecto `paymentReceipt`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| sourceDocuments | array | Sim | Dados dos documentos de facturação pagos. |

#### Item do array `sourceDocuments`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| lineNo | integer | Sim | Número da linha do documento incluída no recibo, iniciando em 1. |
| sourceDocumentID | object | Sim | Identificação do documento de facturação pago. |
| debitAmount | number | Condicional | Valor do recibo do documento rectificativo, sem impostos e eventuais descontos. |
| creditAmount | number | Condicional | Valor do recibo da factura ou documento rectificativo, sem impostos e eventuais descontos. |

Apenas um dos campos `debitAmount` e `creditAmount` poderá estar preenchido.

#### Objecto `sourceDocumentID`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| originatingNo | string; min 1 | Sim | Número do documento de facturação de origem. |
| documentDate | string; date | Não | Data de emissão da factura ou documento de origem. |

### Objecto `documentTotals`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| taxPayable | number | Sim | Valor total do imposto devido. Para `AR`, `RC` e `RG`, resulta da soma dos `taxPayable` dos documentos de origem regularizados; as NC entram com sinal negativo. |
| netTotal | number | Sim | Valor total do documento sem imposto. Para `AR`, `RC` e `RG`, soma os `netTotal` dos documentos de origem regularizados; as NC entram com sinal negativo. |
| grossTotal | number | Sim | Soma do total sem imposto e do total do imposto. |
| currency | object | Condicional | Informação da moeda do pagamento. Não é preenchido para AOA; torna-se obrigatório quando a moeda é diferente de AOA. |

#### Objecto `currency`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| currencyCode | string; 3 | Sim | Código ISO 4217 da moeda, excluindo AOA. |
| currencyAmount | number | Sim | Valor total na moeda estrangeira. |
| exchangeRate | number | Sim | Taxa de câmbio para AOA. |

### Array `withholdingTaxList`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| withholdingTaxType | string; max 3 | Sim | Tipo de retenção: `IRT`, `II`, `IS`, `IVA`, `IP`, `IAC`, `OU`, `IRPC`, `IRPS`. |
| withholdingTaxDescription | string; max 120 | Não | Motivo da retenção, incluindo a disposição legal ou a percentagem aplicável. |
| withholdingTaxAmount | number | Sim | Valor da retenção. Para `AR`, `RC` e `RG`, é agrupado por tipo de imposto; NC entra com sinal negativo. |

### Resposta do `registarFactura`

| HTTP | Resposta | Situação | Descrição |
| --- | --- | --- | --- |
| 200 | string `requestID` | Sucesso | O pedido foi registado; a validação será feita de forma diferida. `requestID` tem máximo de 15 caracteres. |
| 400 | array `errorList` | Erro | Pedido rejeitado na recepção devido a erros nos dados. |

Cada erro contém `idError`, `descriptionError` e, quando o erro ocorre dentro de `documents`, `documentNo`.

## 2. Serviço `obterEstado` — Obter Estado de Validação da Factura

Consulta o estado das facturas previamente transmitidas por `registarFactura`.

### Entrada

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador da solicitação fornecido pelo barramento, no formato `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF do contribuinte. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp da submissão. |
| softwareInfo | object | Sim | Dados do software de facturação. |
| jwsSignature | string; 256 | Sim | Assinatura do contribuinte. |
| requestID | string; max 15 | Sim | Identificador devolvido pelo `registarFactura`. |

### Resultado `statusResult`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| requestID | string; max 15 | Sim | Identificador do pedido consultado. |
| resultCode | integer | Sim | `0` concluído sem facturas inválidas; `1` concluído com facturas válidas (com ou sem penalização) e inválidas; `2` concluído sem facturas válidas; `7` solicitação prematura/repetitiva; `8` processamento em curso; `9` processamento cancelado. |
| documentStatusList | array | Condicional | Resultados por factura; é obrigatório quando `resultCode` indicar que há resultados de documentos. |

Cada item de `documentStatusList` possui `documentNo`, `documentStatus` e, quando aplicável, `errorList`.

Valores de `documentStatus`: `V` factura válida; `I` factura inválida; `P` factura válida com penalização por envio com mais de 24 horas de atraso e sem contingência.

### Erros relevantes

| Código | Significado |
| --- | --- |
| 422 / E96 | Solicitação ainda em processamento / chamada prematura, conforme a situação descrita pelo serviço. |
| 422 / E97 | Solicitação prematura. |
| 422 / E95 | NIF do emissor diferente. |
| 429 / E98 | Demasiadas solicitações repetidas. |
| 400 / E96 | Solicitação mal efectuada — erro de estrutura. |

## 3. Serviço `listarFacturas` — Listar Facturas Electrónicas

Obtém a lista de facturas registadas em nome de um contribuinte durante determinado período.

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador da solicitação `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF do contribuinte. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp da submissão. |
| softwareInfo | object | Sim | Dados do software. |
| jwsSignature | string; 256 | Sim | Assinatura com os campos `taxRegistrationNumber`, `queryStartDate` e `queryEndDate`. |
| queryStartDate | string; date | Sim | Data inicial da pesquisa. |
| queryEndDate | string; date | Sim | Data final da pesquisa. |

### Resultado `documentListResult`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| documentResultCount | integer | Sim | Número de facturas encontradas. |
| documentResultList | array | Sim | Lista de identificação e data das facturas. |

Cada item possui `documentNo` (máx. 60) e `documentDate`.

Erros: `E94` (NIF diferente), `E98` (demasiadas solicitações repetidas) e `E96` (erro de estrutura).

## 4. Serviço `consultarFactura` — Consultar Factura Electrónica

Obtém os dados detalhados de uma factura electrónica emitida em nome do contribuinte.

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador da solicitação `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF do contribuinte. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp da submissão. |
| softwareInfo | object | Sim | Dados do software. |
| jwsSignature | string; 256 | Sim | Assinatura sobre `taxRegistrationNumber` e `documentNo`. |
| documentNo | string; max 60 | Sim | Factura electrónica a consultar. |

### Resultado `statusFEResult`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| documentNo | string; max 60 | Sim | Identificação da factura consultada. |
| validationStatus | string; 1 | Condicional | `V` factura válida; `P` factura válida com penalização (mais de 24 h de atraso e sem contingência aprovada pela AGT). |
| documents | array | Não | Dados da factura. Pode existir mais de um resultado quando a factura foi anulada depois de emitida. |

## 5. Serviço `solicitarSerie` — Criar Série de Facturas Electrónicas

Cria uma nova série de numeração de facturas electrónicas.

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF do contribuinte. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp da submissão. |
| softwareInfo | object | Sim | Dados do software. |
| jwsSignature | string; 256 | Sim | Assinatura sobre `taxRegistrationNumber`, `seriesCode`, `seriesYear`, `documentType` e `firstDocumentNumber`. |
| seriesCode | string; min 3 | Sim | Código alfanumérico da série; deve conter na sua composição o ano de emissão com 2 ou 4 dígitos. |
| seriesYear | integer | Sim | Ano de emissão da série. De 1 de Janeiro a 15 de Dezembro apenas se pode criar para o ano do sistema; depois dessa data pode ser criada para o ano do sistema e para o ano imediatamente posterior. |
| documentType | string; 2 | Sim | Tipo de documento electrónico, usando os mesmos códigos da facturação. |
| firstDocumentNumber | integer | Sim | Primeiro número de factura a gerar na série, normalmente `1`. |

### Resultado

`200` devolve um inteiro: `1 = sucesso`, `0 = insucesso`. Em caso de erro, é devolvido `errorList` com `idError` e `descriptionError`.

## 6. Serviço `listarSeries` — Listar Séries de Numeração

Obtém a lista de séries de numeração registadas em nome do contribuinte.

### Filtros de entrada

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp. |
| softwareInfo | object | Sim | Dados do software. |
| jwsSignature | string; 256 | Sim | Assinatura do contribuinte. |
| seriesCode | string; 3–60 | Não | Código de série. |
| seriesYear | integer | Não | Ano da série. |
| documentType | string; 2 | Não | Tipo de documento. |
| seriesStatus | string; 2 | Não | Estado da série. |

`seriesStatus`: `A` = série aberta; `U` = série em utilização; `F` = série fechada após expirar o ano de emissão.

### Resultado `seriesListResult`

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| seriesResultCount | integer | Sim | Número de séries encontradas. |
| seriesInfo | array | Sim | Lista das séries. |

Cada `seriesInfo` contém:

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| seriesCode | string; max 60 | Sim | Código da série. |
| seriesYear | integer | Sim | Ano da série. |
| documentType | string; 2 | Sim | Tipo de documento. |
| seriesStatus | string; 2 | Sim | Estado `A`, `U` ou `F`. |
| seriesCreationDate | string; date | Sim | Data de criação. |
| firstDocumentCreated | string | Sim | Número do primeiro documento criado na série. |
| lastDocumentCreated | string | Não | Última factura criada, quando a série já foi utilizada. |
| invoicingMethod | string; 4 | Sim | Método: `FEPC` (Portal do Contribuinte), `FESF` (Software de Facturação) ou `SF` (facturação não electrónica via software). |

Erros: `E94` (NIF diferente), `E98` (demasiadas solicitações repetidas) e `E96` (erro de estrutura).

## 7. Serviço `ValidarDocumento` — Confirmar/Rejeitar Documento

Permite ao adquirente confirmar ou rejeitar uma factura/documento equivalente emitido em seu nome e definir a percentagem de IVA dedutível quando aplicável.

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| schemaVersion | string | Sim | Versão do schema. |
| submissionId | string | Sim | Identificador `xxxxx-99999999-9999`. |
| taxRegistrationNumber | string; max 15 | Sim | NIF do adquirente. |
| submissionTimeStamp | string; ISO 8601 | Sim | Timestamp. |
| softwareInfo | object | Sim | Dados do software. |
| jwsSignature | string; 256 | Sim | Assinatura sobre `taxRegistrationNumber` e `documentNo`. |
| documentNo | string; max 60 | Sim | Documento a confirmar/rejeitar. |
| action | string; 1 | Sim | `C` = confirmação; `R` = rejeição. |
| deductibleVATPercentage | number; 0–100 | Não | Percentagem de IVA dedutível. Aplicável quando `action = C` e o documento não é recibo nem nota de crédito. Quando omitido, considera-se que não existe direito a dedução. |

### Resultado `confirmRejectResult`

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| actionResultCode | string; 4–5 | Sim | `COK`/`C OK` = confirmação com sucesso; `ROK`/`R OK` = rejeição com sucesso; `CNOK`/`C NOK` = confirmação não possível; `RNOK`/`R NOK` = rejeição não possível. |
| documentStatusCode | string; 3–4 | Sim | Estado anterior à tentativa: `SA` anulado; `SC` confirmado; `SI` inválido; `SRG` registado; `SRJ` rejeitado; `SV` válido. |
| errorList | array | Condicional | Erros que impediram a execução com sucesso; obrigatório quando a acção resulta em `C NOK` ou `R NOK`. |

### Objecto de erro

| Campo | Tipo / atributos | Obrigatório | Descrição |
| --- | --- | --- | --- |
| errorCode | string; 3 | Sim | Código do erro. |
| errorDescription | string; max 100 | Sim | Descrição do erro. |

---

# Anexo II — Modelo de Facturação Electrónica

O modelo adoptado é de **validação a posteriori**: os documentos electrónicos são emitidos e entregues ao adquirente sem necessidade de validação prévia pela AGT, sendo a validação realizada posteriormente com base em regras de controlo pré-estabelecidas. O modelo assenta essencialmente na troca de informações por serviços.

## Aspectos funcionais do modelo

- Apenas contribuintes que aderiram à facturação electrónica podem utilizar os webservices previstos para o respectivo módulo.
- Os softwares de facturação devem comunicar as séries de numeração das facturas electrónicas para os diferentes tipos de documentos.
- As facturas electrónicas podem ser registadas individualmente ou em lotes até ao limite previamente definido.
- O serviço de registo responde de imediato se a solicitação foi registada ou se existe erro estrutural na chamada.
- A validação do conteúdo é feita posteriormente à aceitação do pedido, mediante serviço que permite consultar o resultado da validação.
- A validação deve ocorrer num intervalo de tempo razoável, compatível com a infraestrutura tecnológica do sistema.
- Quando uma solicitação é rejeitada ou considerada inválida, a factura ou conjunto de facturas, para efeitos fiscais, não existe.
- Cada contribuinte deve poder consultar as facturas electrónicas emitidas em seu nome e respectivo detalhe, podendo, num período de 2 meses, validar um documento em que foi identificado como adquirente.

---

# Anexo III — Especificações Técnicas

## Serviços REST

| Método | Serviço | Tipo de comunicação | Descrição |
| --- | --- | --- | --- |
| POST | `registarFactura` | Síncrono | Solicitar registo de factura electrónica e registar os dados para emissão. |
| POST | `obterEstado` | Síncrono | Obter o estado de validação da factura electrónica. |
| POST | `listarFacturas` | Síncrono | Obter a lista de facturas electrónicas emitidas num período em nome de determinado contribuinte. |
| POST | `consultarFactura` | Síncrono | Obter os dados de uma factura electrónica emitida em nome de determinado contribuinte. |
| POST | `solicitarSerie` | Síncrono | Solicitar a criação de nova série de numeração de facturas electrónicas. |
| POST | `listarSeries` | Síncrono | Obter a lista de séries de numeração utilizadas por um emissor. |
| POST | `ValidarDocumento` | Síncrono | Validar (confirmar/rejeitar) um documento de facturação emitido em nome do adquirente. |

## Requisitos técnicos

- Os serviços Web devem respeitar a arquitectura **REST**.
- Os dados devem ser transmitidos em **JSON**.
- Devem ser suportados os caracteres e formatos numéricos portugueses.
- Ao nível de auditoria, todos os eventos, erros e alterações devem ser registados.
- Campos não obrigatórios podem ser omitidos na chamada/resposta ou apresentados como `null` em JSON, significando que não têm valor atribuído.

## QR Code nos documentos impressos

| Especificação | Valor |
| --- | --- |
| Padrão | QR Code Model 2 |
| Versão | 4 (33 × 33 módulos) |
| Nível de correcção de erros | M (15%) |
| Modo de dados | Byte |
| Codificação | UTF-8 |
| URL codificada | `https://portaldocontribuinte.minfin.gov.ao/consultar-fe?documentNo` |
| Formato do ficheiro | PNG, 350 × 350 px |
| Espaços em `documentNo` | Cada espaço deve ser substituído pela sequência `%20`. |

O logotipo da AGT deve ser incluído no QR Code/documento conforme indicado no modelo, ocupando **menos de 20% da imagem total**.

---

# Tabelas de referência

As tabelas seguintes são as tabelas às quais o Anexo I remete para preenchimento dos campos de actividade económica e de tributação.

# Tabela 1 — Códigos de Actividade Económica — CAE

A lista de CAE é baseada na lista publicada pelo INE.

| Código | Descrição |
| --- | --- |
| 01111 | Cerealicultura (excepto arroz) |
| 01112 | Leguminosas secas e sementes oleaginosas |
| 01120 | Cultura de arroz |
| 01131 | Cultura de mandioca |
| 01132 | Cultura de produtos hortícolas e de outras raízes e tubérculos |
| 01140 | Cultura de cana-de-açúcar |
| 01150 | Cultura de tabaco |
| 01161 | Cultura de algodão |
| 01162 | Cultura de sisal |
| 01163 | Outras culturas de plantas têxteis |
| 01191 | Cultura de flores e de plantas ornamentais |
| 01192 | Outras culturas temporárias, n. e |
| 01210 | Viticultura |
| 01220 | Culturas de frutos tropicais e subtropicais |
| 01230 | Cultura de citrinos |
| 01240 | Cultura de pomóideas e prunóideas |
| 01250 | Cultura de outros frutos (inclui casca rija) em árvores e arbustos |
| 01260 | Cultura de frutos oleaginosos |
| 01271 | Cafeicultura |
| 01272 | Outras culturas de plantas destinadas à preparação de bebidas |
| 01280 | Cultura de especiarias, plantas aromáticas, medicinais e farmacêuticas |
| 01290 | Outras culturas permanentes |
| 01300 | Cultura de materiais de propagação vegetativa |
| 01410 | Bovinicultura |
| 01420 | Criação de gado cavalar, asinino e muar |
| 01430 | Criação de gado ovino e caprino |
| 01440 | Suinicultura |
| 01450 | Avicultura |
| 01491 | Apicultura |
| 01492 | Criação de animais de companhia |
| 01493 | Outra produção animal, n.e |
| 01500 | Agricultura e produção animal combinadas |
| 01610 | Actividades dos serviços relacionados com a agricultura |
| 01620 | Actividades dos serviços relacionados com a produção animal, excepto serviços veterinários |
| 01630 | Preparação de produtos agricolas para a venda |
| 01640 | Preparação e tratamento de sementes para propagação |
| 01700 | Caça, repovoamento cinegético e actividades dos serviços relacionados |
| 02100 | Silvicultura e outras actividades florestais |
| 02200 | Exploração florestal |
| 02300 | Extracção de cortiça, resina e apanha de outros produtos florestais, excepto madeira |
| 02400 | Actividades dos serviços relacionados com a silvicultura e exploração florestal |
| 03111 | Pesca marítima |
| 03112 | Apanha de algas e de outros produtos do mar |
| 03120 | Pesca e apanha de produtos em águas interiores |
| 03210 | Aquacultura em águas salgadas e salobras |
| 03220 | Aquacultura em águas doces |
| 05100 | Extracção de hulha |
| 05200 | Extracção de lenhite |
| 06100 | Extracção de petróleo bruto |
| 06200 | Extracção de gás natural |
| 07100 | Extracção e preparação de minérios de ferro |
| 07210 | Extracção e preparação de minérios de urânio e de tório |
| 07291 | Extracção e preparação de minérios de cobre |
| 07292 | Extracção e preparação de minérios de metais preciosos |
| 07293 | Extracção e preparação de outros minérios metálicos não ferrosos (excepto minérios de urânio e de tório), n.e |
| 08101 | Extracção de mármore e rochas similares |
| 08102 | Extracção de calcário, gesso e cré |
| 08103 | Extracção de saibro, areia e pedra britada |
| 08104 | Extracção de argila e caulino |
| 08910 | Extracção de minerais para a indústria química e para a fabricação de adubos |
| 08920 | Extracção de sal |
| 08991 | Extracção de diamantes |
| 08992 | Extracção de outros minerais não metálicos, n.e |
| 09100 | Actividades dos serviços relacionados com a extracção de petróleo e gás, excepto a prospecção |
| 09900 | Outras actividades dos serviços relacionados com as indústrias extractivas |
| 10101 | Abate de gado (produção de carne) |
| 10102 | Abate de aves (produção de carne) |
| 10103 | Fabricação de produtos à base de carne |
| 10201 | Preparação de produtos da pesca e da aquacultura |
| 10202 | Congelação de produtos da pesca e da aquacultura |
| 10203 | Conservação de produtos da pesca e da aquacultura em azeite e outros óleos vegetais e outros molhos |
| 10204 | Secagem, salgas e outras actividades de transformação de produtos da pesca e da aquacultura |
| 10301 | Fabricação de sumos de frutos e de produtos hortícolas |
| 10302 | Congelação de frutos e de produtos hortícolas |
| 10303 | Fabricação de doces, compotas, geleias e marmelada |
| 10304 | Secagem e desidratação de frutos e produtos hortícolas |
| 10305 | Preparação e conservação de batatas |
| 10306 | Preparação e conservação de frutos e de produtos hortícolas, por outros processos |
| 10401 | Produção e refinação de óleos gorduras vegetais |
| 10402 | Produção e refinação de óleos e gorduras animais |
| 10403 | Fabricação de margarinas e de gorduras alimentares similares |
| 10501 | Indústrias do leite e derivados |
| 10502 | Fabricação de gelados e sorvetes |
| 10611 | Moagem de cereais |
| 10612 | Descasque, branqueamento e glaciagem do arroz |
| 10613 | Transformação de cereais e leguminosas, n.e |
| 10620 | Fabricação de amidos, féculas e produtos afins |
| 10711 | Panificação |
| 10712 | Pastelaria |
| 10713 | Fabricação de bolachas, biscoitos, tostas e pastelaria de conservação |
| 10720 | Indústria do açúcar |
| 10730 | Indústria do cacau, do chocolate e dos produtos de confeitaria |
| 10740 | Fabricação de massas alimentícias, cuscuz e similares |
| 10750 | Fabricação de refeições e pratos pré-cozinhados |
| 10791 | Refinação do sal |
| 10792 | Indústria do café e do chá |
| 10793 | Fabricação de outros produtos alimentares diversos, n.e. |
| 10800 | Fabricação de alimentos para animais |
| 11010 | Fabricação de bebidas alcoólicas destiladas |
| 11020 | Produção de vinho e de bebidas fermentadas de frutos |
| 11030 | Fabricação de cerveja e malte |
| 11041 | Engarrafamento de águas minerais naturais e de nascente |
| 11042 | Fabricação de refrigerantes e de outras bebidas não alcoólicas, n.e |
| 12000 | Indústria do Tabaco |
| 13111 | Preparação, fiação e tecelagem de algodão, de fibras artificiais, sintéticas e mistas |
| 13112 | Fabricação de linhas de costura |
| 13113 | Preparação, fiação e tecelagem de outras fibras têxteis |
| 13120 | Acabamento de têxteis |
| 13910 | Fabricação de artigos têxteis confeccionados, excepto vestuário |
| 13920 | Fabricação de tapetes e carpetes |
| 13930 | Fabricação de cordoaria e redes |
| 13991 | Fabricação de bordados e rendas |
| 13992 | Fabricação de outros artigos têxteis diversos, n.e |
| 14101 | Confecção de vestuário de trabalho e de uniformes |
| 14102 | Confecção de outro vestuário exterior em série |
| 14103 | Confecção de outro vestuário exterior por medida |
| 14104 | Confecção de outros artigos e acessórios de vestuário |
| 14200 | Fabricação de artigos de peles com pêlo |
| 14300 | Fabricação de artigos de malha |
| 15110 | Curtimenta e acabamento de peles, sem pêlo e com pêlo |
| 15120 | Fabricação de artigos de viagem e de uso pessoal, de marroquinaria, de correeiro e de seleiro |
| 15200 | Indústria do calçado e seus componentes |
| 16100 | Serração, aplainamento e impregnação da madeira |
| 16210 | Fabricação de folheados, contraplacados, painéis lamelados, de partículas, de fibras e de outros painéis |
| 16220 | Fabricação de obras de carpintaria para a construção |
| 16230 | Fabricação de embalagens de madeira |
| 16291 | Fabricação de obras de cestaria, de espartaria e similares |
| 16292 | Indústria da cortiça e de outras obras de madeira, n.e. |
| 17010 | Fabricação de pasta, de papel e cartão (excepto canelado) |
| 17020 | Fabricação de papel e de cartão canelados e de embalagens de papel e cartão |
| 17030 | Fabricação de artigos de papel para uso doméstico e sanitário |
| 17090 | Fabricação de artigos de pasta de papel, de papel e de cartão, n.e |
| 18110 | Impressão |
| 18120 | Actividades relacionadas com a impressão |
| 18200 | Reprodução de suportes gravados |
| 19100 | Fabricação de produtos de coqueria |
| 19200 | Fabricação de produtos petrolíferos refinados e de aglomerados de combustíveis |
| 20111 | Fabricação de gases industriais |
| 20112 | Fabricação de álcool etílico de fermentação |
| 20113 | Fabricação de outros produtos químicos de base |
| 20120 | Fabricação de adubos e de compostos azotados |
| 20130 | Fabricação de matérias plásticas e de borracha sintética sob formas primárias |
| 20210 | Fabricação de pesticidas e de outros produtos agroquímicos |
| 20220 | Fabricação de tintas, vernizes e produtos similares; mastiques; tintas de impressão |
| 20231 | Fabricação de sabões e detergentes, produtos de limpeza e de polimento |
| 20232 | Fabricação de perfumes, cosméticos e de produtos de higiene |
| 20291 | Fabricação de explosivos e artigos de pirotecnia |
| 20292 | Fabricação de outros produtos químicos, diversos, n.e. |
| 20300 | Fabricação de fibras sintéticas ou artificiais |
| 21000 | Fabricação de produtos farmacêuticos de base e de preparações farmacêuticas |
| 22111 | Fabricação de pneus e câmaras-de-ar |
| 22112 | Reconstrução de pneus |
| 22190 | Fabricação de produtos de borracha, n.e. |
| 22201 | Fabricação de chapas, folhas, tubos e perfis de plástico |
| 22202 | Fabricação de embalagens de plástico |
| 22203 | Fabricação de artigos de plástico, n.e. |
| 23100 | Fabricação de vidro e artigos de vidro |
| 23910 | Fabricação de produtos cerâmicos refractários |
| 23921 | Fabricação de azulejos, ladrilhos, mosaicos e placas de cerâmica |
| 23922 | Fabricação de tijolos, telhas e de outros produtos de barro para a construção |
| 23930 | Fabricação de outros produtos de porcelana e cerâmicos não refractários |
| 23941 | Fabricação de cimento |
| 23942 | Fabricação de cal e gesso |
| 23951 | Fabricação de betão pronto e produtos de betão para a construção (excepto blocos) |
| 23952 | Fabricação de produtos de fibrocimento |
| 23953 | Fabricação de blocos de cimento para construção |
| 23954 | Fabricação de outros produtos de betão, gesso e cimento |
| 23960 | Serragem, corte e acabamento de rochas omamentais e de outras pedras de construção |
| 23990 | Fabricação de outros produtos minerais não metálicos, n.e. |
| 24100 | Indústrias metalúrgicas de base do ferro e do aço |
| 24201 | Obtenção e primeira transformação de metais preciosos |
| 24202 | Obtenção e primeira transformação do zinco |
| 24203 | Obtenção e primeira transformação de outros metais não ferrosos |
| 24310 | Fundição de ferro fundido e de aço |
| 24320 | Fundição de metais não ferrosos |
| 25111 | Fabricação de estruturas de construções metálicas |
| 25112 | Fabricação de portas, janelas e elementos similares em metal |
| 25120 | Fabricação de reservatórios, recipientes, caldeiras e radiadores metálicos para aquecimento central |
| 25130 | Fabricação de geradores de vapor (excepto caldeiras para aquecimento central) |
| 25200 | Fabricação de armas e munições |
| 25910 | Fabricação de produtos forjados, estampados e laminados; metalurgia dos pós |
| 25920 | Tratamento e revestimento de metais; actividades de mecânica geral |
| 25931 | Fabricação de cutelaria |
| 25932 | Fabricação de fechaduras, dobradiças e de outras ferragens |
| 25933 | Fabricação de ferramentas e de moldes metálicos |
| 25991 | Fabricação de embalagens metálicas |
| 25992 | Fabricação de produtos de arame, rebites, parafusos, molas e correntes metálicas |
| 25993 | Fabricação de outros produtos metálicos, n.e. |
| 26100 | Fabricação de componentes e de placas, electrónicos |
| 26200 | Fabricação de computadores e equipamento periférico |
| 26300 | Fabricação de equipamentos de comunicação |
| 26400 | Fabricação de receptores de rádio e de televisão e bens de consumo similares |
| 26510 | Fabricação de instrumentos e aparelhos de medida, verificação, controlo, navegação e outros fins |
| 26520 | Fabricação de relógios e material de relojoaria |
| 26600 | Fabricação de equipamentos de radiação, electromedicina e electroterapêutico |
| 26700 | Fabricação de material e equipamento óptico |
| 26800 | Fabricação de suportes de informação magnéticos e ópticos |
| 27101 | Fabricação de motores, geradores e transformadores eléctricos |
| 27102 | fabricação de material de distribuição e de controlo para instalações eléctricas |
| 27200 | Fabricação de acumuladores e de pilhas eléctricas |
| 27300 | Fabricação de fios e cabos isolados e seus acessórios |
| 27400 | Fabricação de lâmpadas eléctricas e de outro material de iluminação |
| 27501 | Fabricação de electrodomésticos |
| 27502 | Fabricação de aparelhos não eléctricos para o uso doméstico |
| 27900 | Fabricação de outro equipamento eléctrico |
| 28110 | Fabricação de motores e turbinas, excepto motores para aeronaves, automóveis e motociclos |
| 28120 | Fabricação de equipamento hidráulico e pneumatico, bombas, compressores, tomeiras, e válvulas |
| 28130 | Fabricação de rolamentos, de engrenagens e de outros órgãos de transmissão |
| 28140 | Fabricação de fornos e queimadores |
| 28150 | Fabricação de equipamento de elevação e de movimentação |
| 28160 | Fabricação de máquinas e equipamento de escritório, excepto computadores e equipamento periférico |
| 28170 | Fabricação de máquinas-ferramentas portáteis com motor |
| 28190 | Fabricação de outras máquinas de uso geral |
| 28210 | Fabricação de máquinas e de tractores para a agricultura, pecuária e silvicultura |
| 28220 | Fabricação de outras máquinas-ferramentas para metais, excepto portáteis |
| 28230 | Fabricação de máquinas para a metalurgia |
| 28250 | Fabricação de máquinas para as indústrias alimentares, das bebidas e do tabaco |
| 28260 | Fabricação de máquinas para as indústrias têxtil, do vestuário e do couro |
| 28290 | Fabricação de outras máquinas e equipamentos para uso específico, n.e |
| 29100 | Fabricação de veículos automóveis |
| 29200 | Fabricação de carroçarias, reboques e semi-reboques |
| 35302 | Produção de gelo |
| 36000 | Captação, tratamento e distribuição de água |
| 37000 | Recolha, Drenagem e Tratamento de Águas Residuais |
| 38110 | Recolha de resíduos não perigosos |
| 38120 | Recolha de resíduos perigosos |
| 38210 | Tratamento e eliminação de resíduos não perigosos |
| 38220 | Tratamento e eliminação de resíduos perigosos |
| 38301 | Valorização de sucatas e de resíduos metálicos |
| 38302 | Valorização de resíduos não metálicos |
| 39000 | Descontaminação e Actividades Similares |
| 41001 | Promoção imobiliária |
| 41002 | Construção de edifícios (residenciais e não residenciais) |
| 42100 | Construção de auto-estradas, estradas, pontes, túneis, aeroportos e vias-férreas |
| 42200 | Construção de redes de transporte de água, de esgotos e de outros fluidos, de distribuição de energia, de telecomunicação e de outras redes |
| 42900 | Construção de outras obras de engenharia civil |
| 43100 | Demolição e preparação dos locais de construção |
| 43210 | Instalação eléctrica |
| 43220 | Instalação de canalizações e de climatização |
| 43290 | Outras instalações em construções |
| 43301 | Montagem de trabalhos de carpintaria e de caixilharia |
| 43302 | Estucagem, revestimento de pavimentos e de paredes |
| 43303 | Outras actividades de acabamento |
| 43901 | Aluguer de equipamento de construção e de demolição, com operador |
| 43902 | Outras obras especializadas de construção, n.e. |
| 45100 | Comércio de veículos automóveis |
| 45200 | Manutenção e reparação de veículos automóveis |
| 45300 | Comércio de peças e acessórios para veículos automóveis |
| 45401 | Comércio por grosso e a retalho de motociclos, de suas peças e acessórios |
| 45402 | Manutenção e reparação de motociclos, de suas peças e acessórios |
| 46101 | Agentes do comércio por grosso de matérias-primas agrícolas e têxteis, animais vivos e produtos semi-acabados |
| 46102 | Agentes do comércio por grosso de combustíveis, minérios, metais, produtos químicos para a indústria, máquinas, equipamentos industriais, embarcações e aeronaves |
| 46103 | Agentes do comércio por grosso de madeira, materiais de construção, mobiliário, artigos para uso doméstico e ferragens |
| 46104 | Agentes do comércio por grosso de produtos alimentares, bebidas e tabaco |
| 46105 | Agentes do comércio por grosso misto sem predominância |
| 46106 | Agentes especializados do comércio por grosso de produtos, n.e |
| 46201 | Comércio por grosso de cereais, sementes, leguminosas, oleaginosas e alimentos para animais |
| 46202 | Comércio por grosso de flores e plantas |
| 46203 | Comércio por grosso de animais vivos, de peles e couro |
| 46204 | Comércio por grosso de tabaco em bruto |
| 46301 | Comércio por grosso de frutas e de produtos hortícolas |
| 46302 | Comércio por grosso de carne e de produtos à base de carne |
| 46303 | Comércio por grosso de leite e derivados, ovos, azeite, óleo e gorduras alimentares |
| 46304 | Comércio por grosso de bebidas |
| 46305 | Comércio por grosso de tabaco |
| 46306 | Comércio por grosso de café, açúcar, chá, cacau, produtos de confeitaria e de especiarias |
| 46307 | Comércio por grosso de peixe, crustáceos e moluscos |
| 46308 | Comércio por grosso de outros produtos alimentares |
| 46411 | Comércio por grosso de têxteis, vestuário e acessórios |
| 46412 | Comércio por grosso de calçado |
| 46491 | Comércio por grosso de electrodomésticos, aparelhos de rádio e de televisão |
| 46492 | Comércio por grosso de louças em cerâmica e em vidro, de papel de parede e de produtos de limpeza |
| 46493 | Comércio por grosso de perfumes, de produtos de higiene e de produtos farmacêuticos |
| 46494 | Comércio por grosso de artigos de papelaria, livros, revistas e jornais |
| 46495 | Comércio por grosso de outros bens de consumo, excepto alimentares, bebidas e tabaco |
| 46510 | Comércio por grosso de computadores, equipamentos periféricos e programas informáticos, excepto outras máquinas e equipamento de escritório |
| 46520 | Comércio por grosso de outros componentes e equipamentos electrónicos e de telecomunicações |
| 46530 | Comércio por grosso de máquinas e equipamentos agricolas |
| 46591 | Comércio por grosso de máquinas-ferramentas, de máquinas para construção e de engenharia civil |
| 46592 | Comércio por grosso de mobiliário de escritório, de máquinas e equipamento de escritório, excepto computadores |
| 46593 | Comércio por grosso de máquinas e equipamentos para a indústria, comércio, navegação e para outros fins, n.e. |
| 46610 | Comércio por grosso de combustíveis sólidos, líquidos, gasosos e produtos derivados |
| 46620 | Comércio por grosso de minérios e de metais |
| 46631 | Comércio por grosso de madeira em bruto e de produtos derivados |
| 46632 | Comércio por grosso de materiais de construção (excepto madeira) e equipamento sanitário |
| 46633 | Comércio por grosso de ferragens, ferramentas manuais e artigos para canalização e aquecimento |
| 46691 | Comércio por grosso de produtos químicos |
| 46692 | Comércio por grosso de bens intermédios não agricolas, n.e., de desperdícios e de sucatas |
| 46900 | Comércio por grosso, n.e. |
| 47111 | Comércio a retalho em supermercados e hipermercados |
| 47112 | Comércio a retalho em outros estabelecimentos não especializados, com predominância de produtos alimentares, bebidas ou tabaco |
| 47190 | Comércio a retalho em estabelecimentos não especializados, sem predominância de produtos alimentares, bebidas ou tabaco |
| 47211 | Comércio a retalho de frutas e de produtos hortícolas, em estabelecimentos especializados |
| 47212 | Comércio a retalho de carne e de produtos à base de carne, em estabelecimentos especializados |
| 47213 | Comércio a retalho de peixe, crustaceos e moluscos, em estabelecimentos especializados |
| 47214 | Comércio a retalho de pão, de produtos de pastelaria e de confeitaria, em estabelecimentos especializados |
| 47215 | Comércio a retalho de outros produtos alimentares, em estabelecimentos especializados |
| 47220 | Comércio a retalho de bebidas, em estabelecimentos especializados |
| 47230 | Comércio a retalho de tabaco, em estabelecimentos especializados |
| 47300 | Comércio a retalho de combustível para veículos a motor, em estabelecimentos especializados |
| 47411 | Comércio a retalho de computadores, equipamentos periféricos e programas informáticos (software), em estabelecimentos especializados |
| 47412 | Comércio a retalho de equipamento de telecomunicações, em estabelecimentos especializados |
| 47420 | Comércio a retalho de equipamento audiovisual, em estabelecimentos especializados |
| 47510 | Comércio a retalho de têxteis, em estabelecimentos especializados |
| 47520 | Comércio a retalho de ferragens, tintas, vidros, equipamento sanitário, ladrilhos e similares, em estabelecimentos especializados |
| 47530 | Comércio a retalho de carpetes, tapetes, cortinados e outros revestimentos para paredes e pavimentos, em estabelecimentos especializados |
| 47591 | Comércio a retalho de electrodomésticos, em estabelecimentos especializados |
| 47592 | Comércio a retalho de mobiliário e artigos de iluminação, em estabelecimentos especializados |
| 47593 | Comércio a retalho de louças, cutelaria e de outros artigos similares para uso doméstico, em estabelecimentos especializados |
| 47594 | Comércio a retalho de outros artigos para o lar, n.e., em estabelecimentos especializados |
| 47610 | Comércio a retalho de livros, jornais e artigos de papelaria, em estabelecimentos especializados |
| 47620 | Comércio a retalho de discos, CD, DVD, cassetes e produtos similares, em estabelecimentos especializados |
| 47630 | Comércio a retalho de artigos de desporto, de campismo e lazer, em estabelecimentos especializados |
| 47640 | Comércio a retalho de brinquedos e jogos, em estabelecimentos especializados |
| 47711 | Comércio a retalho de vestuário, em estabelecimentos especializados |
| 47712 | Comércio a retalho de marroquinaria e artigos de viagem e de calçado, em estabelecimentos especializados |
| 47720 | Comércio a retalho de produtos farmacêuticos, médicos e ortopédicos, cosméticos e de higiene, em estabelecimentos especializados |
| 47731 | Comércio a retalho de relógios e de artigos de ourivesaria e joalharia, em estabelecimentos especializados |
| 47732 | Comércio a retalho de fiores, plantas, sementes e fertilizantes, em estabelecimentos especializados |
| 47733 | Comércio a retalho de combustíveis para uso doméstico, em estabelecimentos especializados |
| 47734 | Comércio a retalho de material óptico, fotográfico, cinematográfico e de instrumentos de precisão, em estabelecimentos especializados |
| 47735 | Comércio a retalho de animais de estimação e respectivos alimentos, em estabelecimentos especializados |
| 47736 | Comércio a retalho de máquinas e de outro material de escritório, em estabelecimentos especializados 4TT3T Comércio a retalho de outros produtos novos, n.e., em estabelecimentos especializados |
| 47740 | Comércio a retalho de artigos em segunda mão, em estabelecimentos especializados |
| 47810 | Comércio a retalho em bancas, feiras e unidades móveis de venda de produtos alimentares, bebidas e tabaco |
| 47820 | Comércio a retalho em bancas, feiras e unidades móveis de venda de têxteis, vestuário, calçado, malas e similares |
| 47890 | Comércio a retalho em bancas, feiras e unidades móveis de venda de outros produtos, n.e |
| 47910 | Comércio a retalho por correspondência ou via Intemet |
| 47990 | Comércio a retalho por outros métodos, não efectuado em estabelecimentos, em bancas, feiras ou unidades móveis |
| 49110 | Transporte interurbano de passageiros por caminho-de-ferro |
| 49120 | Transporte de mercadorias por caminho-de-ferro |
| 49210 | Transportes terrestres, urbanos e suburbanos, regulares de passageiros |
| 49220 | Outros transportes terrestres não regulares de passageiros |
| 49230 | Transportes rodoviários de mercadorias |
| 49300 | Transportes por oleodutos e gasodutos |
| 50110 | Transportes marítimos de passageiros |
| 50120 | Transportes marítimos de mercadorias |
| 50210 | Transportes de passageiros por vias navegáveis interiores |
| 50220 | Transportes de mercadorias por vias navegáveis interiores |
| 51100 | Transportes aéreos de passageiros |
| 51200 | Transportes aéreos de mercadorias |
| 52100 | Armazenagem |
| 52210 | Actividades auxiliares dos transportes terrestres |
| 52220 | Actividades auxiliares dos transportes por água |
| 52230 | Actividades auxiliares dos transportes aéreos |
| 52240 | Manuseamento de carga |
| 52290 | Actividades de agentes transitários, aduaneiros e de outras actividades de apoio ao transporte |
| 53100 | Actividades dos correios nacionais |
| 53200 | Actividades postais independentes dos correios nacionais |
| 55111 | Hotéis com restaurante |
| 55112 | Complexos turísticos com restaurante |
| 55113 | Pensões com restaurante |
| 55114 | Estabelecimento hoteleiros com restaurante, n.e |
| 55121 | Hotéis sem restaurante |
| 55122 | Pensões sem restaurante |
| 55123 | Estabelecimentos hoteleiros sem restaurante, n.e |
| 55200 | Parques de campismo e de caravanismo |
| 55900 | Outros locais de alojamento |
| 56101 | Restaurantes do tipo tradicional |
| 56102 | Restaurantes com lugares ao balcão (Snack bares) |
| 56103 | Restaurantes sem serviço de mesa |
| 56104 | Restaurantes, n.e |
| 56210 | Fornecimento de refeições para eventos |
| 56220 | Outras actividades de serviços de refeições |
| 56301 | Cafés e pastelarias |
| 56302 | Cervejarias e bares |
| 56303 | Outros estabelecimentos de bebidas |
| 58110 | Edição de livros |
| 58120 | Edição de listas destinadas a consulta |
| 58130 | Edição de jornais, revistas e de outras publicações periódicas |
| 58190 | Outras actividades de edição |
| 58200 | Edição de programas informáticos |
| 59110 | Produção de filmes, vídeos e de programas de televisão |
| 59120 | Actividades técnicas de pos-produção de filmes, vídeos e programas de televisão |
| 59130 | Distribuição de filmes, vídeos e programas de televisão |
| 59140 | Projecção de filmes e de vídeos |
| 59200 | Actividades de gravação de som e de edição de música |
| 60100 | Actividades de rádio |
| 60200 | Actividades de televisão |
| 61100 | Actividades de telecomunicações por fio |
| 61200 | Actividades de telecomunicações sem fio |
| 61300 | Actividades de telecomunicações por satélite |
| 61900 | Outras actividades de telecomunicações |
| 62010 | Actividades de programação informática |
| 62021 | Actividades de consultoria em informática |
| 62022 | Gestão e exploração de equipamento informático |
| 62090 | Outras actividades dos serviços relacionadas com as tecnologias de informação e informática |
| 63110 | Actividades de processamento de dados, domiciliação de informação e actividades relacionadas |
| 63120 | Portais Web |
| 63910 | Actividades de agências de notícias |
| 63990 | Outras actividades dos serviços de informação, n.e. |
| 64110 | Banco Central |
| 64191 | Instituições bancárias |
| 64192 | Outra intermediação monetária, n.e. |
| 64200 | Actividades das sociedades gestoras de participações sociais |
| 64300 | Trusts, fundos e entidades financeiras similares |
| 64910 | Actividade de locação financeira |
| 64920 | Outras actividades de crédito |
| 64990 | Outras actividades de serviços financeiros, n.e. (excepto seguros e fundos de pensões ) |
| 65110 | Seguros de vida e outras actividades complementares de segurança social |
| 65120 | Seguros não vida |
| 65200 | Resseguros |
| 65300 | Fundos de pensões |
| 66110 | Administração de mercados financeiros |
| 66120 | Actividades de negociação por conta de terceiros em valores mobiliários e outros instrumentos financeiros |
| 66190 | Outras actividades auxiliares dos serviços financeiros, excepto seguros e fundos de pensões |
| 66210 | Actividades de avaliação do risco e danos |
| 66220 | Actividade de mediadores de seguros |
| 66290 | Outras actividades auxiliares de seguros e de fundos de pensões |
| 66300 | Actividades de gestão de fundos |
| 68100 | Actividades imobiliárias por conta própria |
| 68200 | Actividades imobiliárias por conta de outrem |
| 69100 | Actividades jurídicas |
| 69200 | Actividades de contabilidade e auditoria; consultoria fiscal |
| 70100 | Actividades das sedes sociais |
| 70200 | Actividades de consultoria para os negócios e a gestão |
| 71101 | Actividades de arquitectura |
| 71102 | Actividades de engenharia e técnicas afins |
| 71200 | Actividades de ensaios e análises técnicas |
| 72100 | Investigação científica e desenvolvimento das ciências físicas e naturais |
| 72200 | Investigação científica e desenvolvimento das ciências sociais e humanas |
| 73100 | Publicidade |
| 73200 | Estudos de mercado e sondagens de opinião |
| 74100 | Actividades de design |
| 74200 | Actividades fotográficas |
| 74900 | Outras actividades de consultoria, científicas, técnicas e similares, n.e. |
| 75000 | Actividades veterinárias |
| 77100 | Aluguer de veículos automóveis |
| 77210 | Aluguer de bens recreativos e desportivos |
| 77220 | Aluguer de videocassetes e discos |
| 77290 | Aluguer de outros bens de uso pessoal e doméstico |
| 77301 | Aluguer de máquinas e equipamentos agrícolas |
| 77302 | Aluguer de máquinas e equipamentos para construção e engenharia civil |
| 77303 | Aluguer de máquinas e equipamentos de escritório (inclui computadores ) |
| 77304 | Aluguer de meios de transporte marítimo e fluvial |
| 77305 | Aluguer de meios de transporte aéreo |
| 77306 | Aluguer de meios de transporte terrestre, excepto veículos automóveis |
| 77307 | Aluguer de outras máquinas e equipamentos, n.e |
| 77400 | Locação de propriedade intelectual e produtos similares, excepto direitos de autor |
| 78100 | Actividades das empresas de selecção e colocação de pessoal |
| 78200 | Actividades das empresas de trabalho temporário |
| 78300 | Outro fomecimento de recursos humanos |
| 79110 | Actividades das agências de viagem |
| 79120 | Actividade dos operadores turísticos |
| 79900 | Outras actividades de reservas |
| 80100 | Actividades de segurança privada |
| 80200 | Actividades relacionadas com sistemas de segurança |
| 80300 | Actividades de investigação |
| 81100 | Actividades combinadas de apoio à gestão de edifícios |
| 85492 | Formação profissional |
| 85493 | Outras actividades educativas, n.e |
| 85500 | Actividades de serviços de apoio à educação |
| 86100 | Actividades dos estabelecimentos de saúde com internamento |
| 86201 | Actividades de prática médica de clínica geral, em ambulatório |
| 86202 | Actividades de prática médica de clínica especializada, em ambulatório |
| 86203 | Actividades de medicina dentária e odontologia |
| 86901 | Laboratórios de análises clínicas |
| 86902 | Actividades de enfermagem |
| 86903 | Outras actividades de saúde humana, n.e |
| 87100 | Actividades de enfermagem com alojamento |
| 87200 | Actividades dos estabelecimentos para pessoas com doenças do foro mental e toxicodependência, com alojamento |
| 87301 | Actividades de acção social para pessoas idosas, com alojamento |
| 87302 | Acção social para pessoas com deficiência, com alojamento |
| 87901 | Actividades de acção social para crianças e jovens, com alojamento |
| 87902 | Outras actividades de acção social, com alojamento, n.e |
| 88101 | Actividades de acção social para pessoas idosas, sem alojamento |
| 88102 | Actividades de acção social para pessoas com deficiência, sem alojamento |
| 88901 | Actividades de cuidados para crianças, sem alojamento |
| 88902 | Outras actividades de acção social, sem alojamento, n.e |
| 90001 | Actividades das artes do espectáculo |
| 90002 | Actividades de apoio às artes do espectáculo |
| 90003 | Criação artística e literária |
| 90004 | Exploração de salas de espectáculos e actividades conexas |
| 91010 | Actividades das bibliotecas e arquivos |
| 91020 | Actividades dos museus e de gestão dos locais e monumentos históricos |
| 91030 | Actividades dos jardins botânicos e zoológicos, dos parques e reservas naturais |
| 92000 | Lotarias e Outros Jogos de Aposta |
| 93110 | Gestão de instalações desportivas |
| 93120 | Actividades dos clubes desportivos |
| 93190 | Outras actividades desportivas |
| 93210 | Actividades de parques de diversão e temáticos |
| 93290 | Outras actividades de diversão e recreativas, n.e |
| 94110 | Actividades de organizações económicas e patronais |
| 94120 | Actividades de organizações profissionais |
| 94200 | Actividades de organizações sindicais |
| 94910 | Actividades de organizações religiosas |
| 94920 | Actividades de organizações políticas |
| 94990 | Outras actividades associativas, n.e |
| 95110 | Reparação de computadores e de equipamento periférico |
| 95120 | Reparação de equipamento de comunicação |
| 95210 | Reparação de televisores e de outros bens de consumo similares |
| 95220 | Reparação de electrodomésticos e de outros equipamentos de uso doméstico e para jardim |
| 95230 | Reparação de calçado e de artigos de couro |
| 95240 | Reparação de mobiliário e similares de uso doméstico |
| 95291 | Reparação de relógios e de artigos de joalharia |
| 95292 | Reparação de outros bens de uso pessoal e doméstico, n.e |
| 96010 | Lavagem e limpeza a seco de têxteis e peles |
| 96020 | Actividades de salões de cabeleireiro e institutos de beleza |
| 96030 | Actividades funerárias e conexas |
| 96090 | Outras actividades de serviços pessoais, n.e |
| 97000 | Actividades das Famílias Empregadoras de Pessoal Doméstico |
| 98100 | Actividades de produção de bens pelas famílias para uso próprio |
| 98200 | Actividades de produção de serviços pelas famílias para uso próprio |
| 99000 | Actividades dos organismos internacionais e outras instituições extra-territoriais |

# Tabela 2 — Taxas do Imposto Especial de Consumo (IEC)

| Classificação Pautal | Designação | Unidade de Medida | IEC (%) |
| --- | --- | --- | --- |
| 2202.10.00 | Águas, incluídas as águas minerais e as águas gaseificadas, adicionadas de açúcar ou de outros edulcorantes ou aromatizadas | LITRO (Lt) | 3 |
| 2202.91.00 | Cerveja sem álcool | LITRO (Lt) | 4 |
| 2202.99.00 | Outras | LITRO (Lt) | 4 |
| 2203.00.00 | Cerveja de malte | LITRO (Lt) | 4 |
| 2204.10.10 | Champanhe | LITRO (Lt) | 8 |
| 2204.10.90 | Outras | LITRO (Lt) | 8 |
| 2204.21.00 | Em recipientes de capacidade não superior a 2 l | LITRO (Lt) | 8 |
| 2204.22.00 | Em recipientes de capacidade superior a 2 l, mas não superior a 10 l | LITRO (Lt) | 8 |
| 2204.29.00 | Outros | LITRO (Lt) | 8 |
| 2205.10.00 | Em recipientes de capacidade não superior a 2 l | LITRO (Lt) | 8 |
| 2205.90.00 | Outros | LITRO (Lt) | 8 |
| 2206.00.00 | Outras bebidas fermentadas (por exemplo, sidra, perada, hidromel); misturas de bebidas fermentadas e misturas de bebidas fermentadas com bebidas não alcoólicas | LITRO (Lt) | 8 |
| 2207.10.00 | Álcool etílico não desnaturado, com um teor alcoólico, em volume, igual ou superior a 80% vol. | LITRO (Lt) | 15 |
| 2207.20.10 | Álcool etílico | LITRO (Lt) | 15 |
| 2207.20.19 | Outros | LITRO (Lt) | 15 |
| 2208.20.00 | Aguardentes de vinho ou de bagaço de uvas | LITRO (Lt) | 8 |
| 2208.30.00 | Uísques | LITRO (Lt) | 8 |
| 2208.40.00 | Rum e outras aguardentes provenientes da destilação, após fermentação, de produtos da cana-de-açúcar | LITRO (Lt) | 8 |
| 2208.50.00 | Gin e genebra | LITRO (Lt) | 8 |
| 2208.60.00 | Vodca | LITRO (Lt) | 8 |
| 2208.70.00 | Licores | LITRO (Lt) | 8 |
| 2208.90.00 | Outros | LITRO (Lt) | 8 |
| 2401.10.00 | Tabaco não destalado | KILOGRAMA (Kg) | 25 |
| 2401.20.00 | Tabaco total ou parcialmente destalado | KILOGRAMA (Kg) | 25 |
| 2401.30.00 | Desperdícios de tabaco | KILOGRAMA (Kg) | 25 |
| 2402.10.00 | Charutos e cigarrilhas, que contenham tabaco | KILOGRAMA (Kg) | 25 |
| 2402.20.00 | Cigarros que contenham tabaco | KILOGRAMA (Kg) | 25 |
| 2402.90.00 | Outros | KILOGRAMA (Kg) | 25 |
| 2403.11.00 | Tabaco para cachimbo de água (narguilé) mencionado na Nota 1 de subposição | KILOGRAMA (Kg) | 25 |
| 2403.19.00 | Outros | KILOGRAMA (Kg) | 25 |
| 2403.91.00 | Tabaco “homogeneizado” ou “reconstituído” | KILOGRAMA (Kg) | 25 |
| 2403.99.00 | Outros | KILOGRAMA (Kg) | 25 |
| 3604.10.00 | Fogo de Artifício | KILOGRAMA (Kg) | 19 |
| 3923.21.10 | Sacos de quaisquer dimensões destinados exclusivamente para embalar produtos, excepto os de transporte | KILOGRAMA (Kg) | 2 |
| 3923.21.90 | Outros | KILOGRAMA (Kg) | 19 |
| 3923.29.10 | Sacos de quaisquer dimensões destinados exclusivamente para embalar produtos, excepto os de transporte | KILOGRAMA (Kg) | 2 |
| 3923.29.90 | Outros | KILOGRAMA (Kg) | 19 |
| 3926.90.90 | Outras (palhinhas de plástico) | KILOGRAMA (Kg) | 19 |
| 4012.11.00 | Do tipo utilizado em automóveis de passageiros (incluindo os veículos de uso misto e os automóveis de corrida) | UNIDADE/QUANTIDADE (U ou Qtd) | 19 |
| 4012.12.00 | Do tipo utilizado em autocarros ou camiões | UNIDADE/QUANTIDADE (U ou Qtd) | 19 |
| 4012.13.00 | Do tipo utilizado em veículos aéreos | UNIDADE/QUANTIDADE (U ou Qtd) | 19 |
| 4012.19.00 | Outros | UNIDADE/QUANTIDADE (U ou Qtd) | 19 |
| 4012.20.00 | Pneumáticos usados | UNIDADE/QUANTIDADE (U ou Qtd) | 19 |
| 4012.90.00 | Outros | KILOGRAMA (Kg) | 19 |
| 7113.11.00 | De prata, mesmo revestida, folheada ou chapeada, de outros metais preciosos | KILOGRAMA (Kg) | 15 |
| 7113.19.00 | De outros metais preciosos, mesmo revestidos, folheados ou chapeados, de metais preciosos | KILOGRAMA (Kg) | 15 |
| 7113.20.00 | De metais comuns, folheados ou chapeados de metais preciosos | KILOGRAMA (Kg) | 15 |
| 7114.11.00 | De prata, mesmo revestida, folheada ou chapeada de outros metais preciosos | KILOGRAMA (Kg) | 15 |
| 7114.19.00 | De outros metais preciosos, mesmo revestidos, folheados ou chapeados, de metais preciosos | KILOGRAMA (Kg) | 15 |
| 7114.20.00 | De metais comuns, folheados ou chapeados de metais preciosos | KILOGRAMA (Kg) | 15 |
| 8703.24.49 | Outros — Novos | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8703.24.59 | Outros — Usados | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8703.33.59 | Outros — Novos | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8703.33.69 | Outros — Usados | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8704.21.10 | Do tipo Pickup e Furgão, de cilindrada não superior a 5000 cm3 — Novos | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8704.21.11 | Do tipo Pickup e Furgão, de cilindrada superior a 5000 cm3 — Novos | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8704.21.15 | Do tipo Pickup e Furgão, de cilindrada não superior a 5000 cm3 — Usados | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8704.21.16 | Do tipo Pickup e Furgão, de cilindrada superior a 5000 cm3 — Usados | UNIDADE/QUANTIDADE (U ou Qtd) | 5 |
| 8801.00.00 | Balões e dirigíveis; planadores, asas voadoras e outros veículos aéreos, não concebidos para propulsão a motor | KILOGRAMA (Kg) | 20 |
| 8802.11.00 | De peso não superior a 2.000 kg, sem carga (vazios) | UNIDADE (U) | 20 |
| 8802.20.00 | Aviões e outros veículos aéreos, de peso não superior a 2.000 kg, sem carga (vazios) | UNIDADE (U) | 20 |
| 8903.91.00 | Barcos a vela, mesmo com motor auxiliar | UNIDADE/QUANTIDADE (U ou Qtd) | 20 |
| 8903.92.00 | Barcos a motor, excepto com motor fora-de-borda | UNIDADE/QUANTIDADE (U ou Qtd) | 20 |
| 8903.99.90 | Outros | UNIDADE/QUANTIDADE (U ou Qtd) | 20 |
| 9303.20.00 | Outras espingardas e carabinas de caça ou de tiro ao alvo, com pelo menos um cano liso | UNIDADE/QUANTIDADE (U ou Qtd) | 50 |
| 9303.30.00 | Outras espingardas e carabinas de caça ou de tiro ao alvo | UNIDADE/QUANTIDADE (U ou Qtd) | 50 |
| 9701.10.00 | Quadros, pinturas e desenhos | UNIDADE (U) | 5 |
| 9701.90.00 | Outros | KILOGRAMA (Kg) | 5 |
| 9702.00.00 | Gravuras, estampas e litografias, originais | UNIDADE (U) | 5 |
| 9703.00.00 | Produções originais de arte estatutária ou de escultura, de quaisquer matérias | UNIDADE (U) | 5 |
| 9704.00.00 | Selos postais, selos fiscais, marcas postais, envelope de primeiro dia (First Day Covers), inteiros postais e semelhantes, obliterados ou não obliterados, excepto os artigos da posição 49.07 | KILOGRAMA (Kg) | 5 |
| 9705.00.00 | Colecções e espécimes para colecções, de zoologia, botânica, mineralogia, anatomia, ou apresentando interesse histórico, arqueológico, paleontológico, etnográfico ou numismático | KILOGRAMA (Kg) | 5 |
| 9706.00.00 | Antiguidades com mais de 100 anos | KILOGRAMA (Kg) | 5 |
| 2701.11.00 | Antracite | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2701.12.00 | Hulha betuminosa | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2701.19.00 | Outras hulhas | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2701.20.00 | Briquetes, bolas em aglomerados e combustíveis sólidos semelhantes, obtidos a partir da hulha | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2702.10.00 | Linhites, mesmo em pó, mas não aglomeradas | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2702.20.00 | Linhites aglomeradas | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2704.00.00 | Coques e semicoques, de hulha, de linhite ou de turfa, mesmo aglomerados; carvão de retorta | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2705.00.00 | Gás de hulha, gás de água, gás pobre (gás de ar) e gases semelhantes, excepto gases de petróleo e outros hidrocarbonetos gasosos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2706.00.00 | Alcatrões de hulha, de linhite ou de turfa e outros alcatrões minerais, mesmo desidratados ou parcialmente destilados, incluindo os alcatrões reconstituídos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.10.00 | Benzol (benzeno) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.20.00 | Toluol (tolueno) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.30.00 | Xilol (xilenos) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.40.00 | Naftaleno | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.50.00 | Outras misturas de hidrocarbonetos aromáticos que destilem uma fracção igual ou superior a 65 %, em volume, a 250 ºC, segundo o método ISO 3405 (equivalente ao método ASTM D 86) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.91.00 | Óleos de creosoto | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2707.99.00 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2708.10.00 | Breu | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2708.20.00 | Coque de breu | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.12.11 | Gasolina para aviões | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.12.12 | Outras Gasolinas | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 5 |
| 2710.12.13 | Querosene | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 0 |
| 2710.12.14 | Gasóleo | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 5 |
| 2710.12.15 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.19.21 | Óleo base | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.19.23 | Óleos lubrificantes | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.19.29 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.20.00 | Óleos de petróleo ou de minerais betuminosos (excepto óleos brutos) e preparações não especificadas nem compreendidas noutras posições, que contenham, como constituintes básicos, 70 % ou mais, em peso, de óleos de petróleo ou de minerais betuminosos; que contenham biodiesel, excepto os resíduos de óleos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.91.00 | Que contenham difenilos policlorados (PCB), terfenilos policlorados (PCT) ou difenilos polibromados (PBB) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2710.99.00 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2711.12.00 | Propano | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2711.13.00 | Butano | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 0 |
| 2711.14.00 | Etileno, propileno, butileno e butadieno | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2711.19.00 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2712.10.00 | Vaselina | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2712.20.00 | Parafina que contenha, em peso, menos de 0,75 % de óleo | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2712.90.00 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2713.11.00 | Não calcinado | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2713.12.00 | Calcinado | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2713.20.00 | Betume de petróleo | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2713.90.00 | Outros resíduos dos óleos de petróleo ou de minerais betuminosos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2714.10.00 | Xistos e areias betuminosos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2714.90.10 | Aditivos de xistos e areias betuminosos | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2714.90.90 | Outros | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |
| 2715.00.00 | Misturas betuminosas à base de asfalto ou de betumes naturais, de betume de petróleo, de alcatrão mineral ou de breu de alcatrão mineral (por exemplo, mastiques betuminosos e cut-backs) | TONELADAS MÉTRICAS (TM); KILOGRAMA (Kg); METROS CÚBICOS (m3); LITRO (Lt ou Lts) | 2 |

# Tabela 3 — Verbas e Taxas de Imposto de Selo (IS)

| N.º / verba | Actos / documentos / contratos / operações / títulos | Taxa |
| --- | --- | --- |
| 1 | Aquisição onerosa ou gratuita do direito de propriedade ou de figuras parcelares desse direito, sobre imóveis; resolução, invalidade ou extinção por mútuo consenso — sobre o valor. | 0,3% |
| 2.1 | Arrendamento/subarrendamento para fins habitacionais — sobre o valor, aumento da renda ou prorrogação. | 0,1% |
| 2.2 | Arrendamento/subarrendamento para estabelecimento comercial, industrial ou profissão independente. | 0,4% |
| 3 | Autos e termos perante tribunais e serviços/organismos do Estado, incluindo os actos enumerados na tabela — por cada um. | 1.000,00 Kz |
| 4 | Cheques de qualquer natureza — por cada dez. | 100,00 Kz |
| 5 | Depósito civil — sobre o respectivo valor. | 0,1% |
| 6 | Depósito, em serviço público, dos estatutos de associações e outras instituições cuja constituição dele dependa — por cada. | 4.400,00 Kz |
| 7.1 | Constituição de sociedade — sobre o valor real dos bens entregues ou a entregar pelos sócios, após deduções previstas. | 0,1% |
| 7.2 | Transformação em sociedade, associação ou pessoa colectiva não sociedade de capitais. | 0,1% |
| 7.3 | Aumento do capital social mediante entrada de bens de qualquer espécie. | 0,1% |
| 7.4 | Aumento do activo mediante entrada de bens remunerada por direitos equivalentes aos dos sócios. | 0,1% |
| 8 | Outros contratos não especialmente previstos na tabela, incluindo os efectuados perante entidades públicas — por cada um. | 1.000,00 Kz |
| 9 | Exploração, pesquisa e prospecção de recursos geológicos do domínio público do Estado — por contrato administrativo. | 3.000,00 Kz |
| 10.1 | Garantias de prazo inferior a um ano. | 0,3% |
| 10.2 | Garantias de prazo igual ou superior a um ano. | 0,2% |
| 10.3 | Garantias sem prazo ou de prazo igual ou superior a cinco anos. | 0,1% |
| 11 | Cada aposta de jogos, incluindo bilhetes, boletins, cartões, matrizes, rifas ou tômbolas. | 100,00 Kz |
| 11.1 | Ingressos em salas de jogo de fortuna ou azar ou equivalentes. | 100,00 Kz |
| 12.1 | Licenças para instalação/exploração de máquinas electrónicas de diversão. | 1.300,00 Kz |
| 12.2 | Licenças para quaisquer outros jogos legais — por cada um. | 1.300,00 Kz |
| 12.3.1.1 | Clubes nocturnos e outros estabelecimentos com espaço reservado para dança — Luanda. | 53.000,00 Kz |
| 12.3.1.2 | Os mesmos estabelecimentos — restantes capitais de província e Lobito. | 27.000,00 Kz |
| 12.3.1.3 | Os mesmos estabelecimentos — outras localidades. | 14.000,00 Kz |
| 12.3.2.1 | Restaurantes — Luanda. | 6.000,00 Kz |
| 12.3.2.2 | Restaurantes — restantes capitais de província e Lobito. | 3.000,00 Kz |
| 12.3.2.3 | Restaurantes — outras localidades. | 1.500,00 Kz |
| 12.3.3.1 | Outros estabelecimentos de restauração e bebidas — Luanda. | 1.500,00 Kz |
| 12.3.3.2 | Outros estabelecimentos — restantes capitais de província e Lobito. | 1.000,00 Kz |
| 12.3.3.3 | Outros estabelecimentos — outras localidades. | 500,00 Kz |
| 12.4.1 | Hotelaria e similares — 1.ª categoria/luxo (pelo menos 4 estrelas). | 100.000,00 Kz |
| 12.4.2 | Hotelaria e similares — 2.ª categoria (3 estrelas). | 60.000,00 Kz |
| 12.4.3.1 | Restantes estabelecimentos hoteleiros — Luanda. | 53.000,00 Kz |
| 12.4.3.2 | Restantes — capitais de província e Lobito. | 30.000,00 Kz |
| 12.4.3.3 | Restantes — outras localidades. | 15.000,00 Kz |
| 12.5 | Máquinas automáticas de venda de bens/serviços em locais públicos — por máquina. | 3.000,00 Kz |
| 12.6 | Outras licenças designadas nesta tabela — por cada uma. | 2.000,00 Kz |
| 13 | Marcas e patentes — sobre o registo unitário. | 3.000,00 Kz |
| 14.1 | Escrituras, excluindo as referentes aos actos da verba 8. | 2.000,00 Kz |
| 14.2 | Habilitação de herdeiros e de legatários — por cada acto. | 1.000,00 Kz |
| 14.3 | Testamento público ou cerrado. | 1.000,00 Kz |
| 14.4.1.1 | Procurações e outros instrumentos para gerência comercial. | 1.000,00 Kz |
| 14.4.1.2 | Procurações e outros poderes. | 500,00 Kz |
| 14.4.1.3 | Substabelecimento. | 500,00 Kz |
| 14.5 | Registo de documentos apresentados aos notários para arquivo — por cada registo. | 100,00 Kz |
| 14.6 | Outros instrumentos notariais avulsos não especialmente previstos. | 100,00 Kz |
| 15.1 | Operações aduaneiras — sobre o valor aduaneiro da importação. | 1% |
| 15.2 | Operações aduaneiras — sobre o valor aduaneiro das exportações. | 0,5% |
| 15.2.2 | Exportações de marfim e outras matérias/produtos animais especificados na tabela. | 0,5% |
| 16.1.1 | Crédito de prazo igual ou inferior a um ano. | 0,5% |
| 16.1.2 | Crédito de prazo superior a um ano. | 0,4% |
| 16.1.3 | Crédito de prazo igual ou superior a cinco anos. | 0,3% |
| 16.1.4 | Conta corrente, descoberto bancário ou outra forma sem prazo determinado/determinável. | 0,1% |
| 16.1.5 | Crédito habitação — sobre o valor. | 0,1% |
| 16.2.1 | Juros por desconto de letras e empréstimos/créditos. | 0,2% |
| 16.2.2 | Prémios e juros por letras tomadas, letras a receber, saques ou transferências. | 0,5% |
| 16.2.3 | Comissões por garantias prestadas. | 0,5% |
| 16.2.4 | Outras comissões/contraprestações por serviços financeiros. | 0,7% |
| 16.3.1 | Saque sobre o estrangeiro, guias, ouro e fundos/títulos negociáveis vendidos. | 1% |
| 16.3.2 | Títulos de dívida pública emitidos por governos estrangeiros e postos à venda no País. | 0,5% |
| 16.3.3 | Câmbio de notas em moeda estrangeira/conversão de moeda nacional em moeda estrangeira a favor de pessoas singulares. | 0,1% |
| 17.1 | Locação financeira de bens imóveis. | 0,3% |
| 17.2 | Locação financeira/operacional de bens móveis corpóreos, incluindo manutenção e assistência técnica. | 0,4% |
| 18 | Precatórios ou mandados para levantamento/entrega de dinheiro ou valores existentes — sobre a importância. | 0,1% |
| 19.1 | Cartazes/anúncios em suportes fixos ou móveis na via pública — por m² ou fracção e por ano civil. | 1.000,00 Kz |
| 19.2 | Publicidade em revistas, jornais, catálogos, rádio/televisão e impressos públicos — por edição de 1000 exemplares ou fracção. | 25.000,00 Kz |
| 20.1 | Registos e averbamentos de aeronaves. | 45.000,00 Kz |
| 20.2 | Registos e averbamentos de barcos. | 23.000,00 Kz |
| 20.3 | Registos e averbamentos de motas de água. | 18.000,00 Kz |
| 20.4.1 | Motociclos e veículos abrangidos, novos e até 3 anos. | 7.000,00 Kz |
| 20.4.2 | Motociclos e veículos abrangidos, usados com mais de 3 anos. | 0,5% |
| 21 | Reporte — sobre o valor do contrato. | — |
| 22.1.1 | Seguro do ramo caução. | 0,3% |
| 22.1.2 | Seguro marítimo e fluvial, incluindo transporte, embarcações e responsabilidade civil. | 0,3% |
| 22.1.3 | Seguro do ramo aéreo, incluindo aeronave, responsabilidade civil, mercadorias e pessoas transportadas. | 0,2% |
| 22.1.4 | Seguro de mercadorias transportadas fora dos ramos marítimo, fluvial e aéreo. | 0,1% |
| 22.1.5 | Seguros de quaisquer outros ramos. | 0,3% |
| 22.2 | Comissões cobradas pela actividade de mediação. | 0,4% |
| 23.1 | Letras e livranças — sobre o valor, mínimo de 100 Kz. | 0,1% |
| 23.2 | Ordens e escritos de qualquer natureza, excepto cheques, que determinem pagamento/entrega de dinheiro — mínimo 100 Kz. | 0,1% |
| 23.3 | Recibo de quitação pelo efectivo recebimento de créditos de actividade comercial/industrial, exceptuando os derivados exclusivamente de arrendamento habitacional de pessoas singulares. | 1% |
| 23.4 | Abertura de crédito por escrito particular ou instrumento público. | 0,1% |
| 24.1 | Trespasse ou cessão para exploração de estabelecimento comercial, industrial ou agrícola. | 0,2% |
| 24.2 | Subcomissões e trespasses de concessões feitas pelo Estado e províncias. | 0,2% |

# Tabela 4 — Isenções de Imposto sobre o Valor Acrescentado (IVA)

| Código | Menção a constar no documento | Descrição |
| --- | --- | --- |
| M10 | Isento nos termos da alínea a) do n.º 1 do artigo 12.º do CIVA | Transmissão dos bens alimentares conforme o Anexo I do CIVA. |
| M11 | Isento nos termos da alínea b) do n.º 1 do artigo 12.º do CIVA | Transmissão de medicamentos destinados exclusivamente a fins terapêuticos e profilácticos. |
| M12 | Isento nos termos da alínea c) do n.º 1 do artigo 12.º do CIVA | Cadeiras de rodas e veículos semelhantes para pessoas com deficiência, dispositivos Braille, impressoras Braille e artefactos destinados a invisuais ou correcção auditiva. |
| M13 | Isento nos termos da alínea d) do n.º 1 do artigo 12.º do CIVA | Transmissão de livros, inclusive em formato digital. |
| M14 | Isento nos termos da alínea e) do n.º 1 do artigo 12.º do CIVA | Locação de bens imóveis destinados a habitação, exceptuando prestações de alojamento hoteleiro ou análogas. |
| M15 | Isento nos termos da alínea f) do n.º 1 do artigo 12.º do CIVA | Operações sujeitas a SISA, ainda que dela isentas. |
| M16 | Isento nos termos da alínea g) do n.º 1 do artigo 12.º do CIVA | Exploração e prática de jogos de fortuna ou azar/diversão social e operações relacionadas, quando sujeitas a Imposto Especial sobre Jogos. |
| M17 | Isento nos termos da alínea h) do n.º 1 do artigo 12.º do CIVA | Transporte colectivo de passageiros. |
| M18B | Isento nos termos da alínea i) do n.º 1 do artigo 12.º do CIVA | Operações de intermediação financeira, incluindo locação financeira, excepto quando é cobrada taxa ou contraprestação específica e predeterminada. |
| M19 | Isento nos termos da alínea j) do n.º 1 do artigo 12.º do CIVA | Seguro de saúde e seguros/resseguros do ramo vida. |
| M20 | Isento nos termos da alínea k) do n.º 1 do artigo 12.º do CIVA | Transmissões de produtos petrolíferos conforme Anexo II do CIVA. |
| M21 | Isento nos termos da alínea l) do n.º 1 do artigo 12.º do CIVA | Ensino prestado por estabelecimentos abrangidos pela Lei de Bases do Sistema de Educação e Ensino e por instituições de ensino superior reconhecidas. |
| M22 | Isento nos termos da alínea m) do artigo 12.º do CIVA | Prestação de serviços médico-sanitários por hospitais, clínicas, dispensários e similares. |
| M23 | Isento nos termos da alínea n) do artigo 12.º do CIVA | Transporte de doentes ou feridos em ambulâncias/veículos apropriados por organismos autorizados. |
| M24 | Isento nos termos da alínea o) do artigo 12.º do CIVA | Equipamentos médicos para a actividade dos estabelecimentos de saúde. |
| M80 | Isento nos termos da alínea a) do n.º 1 do artigo 14.º | Importações definitivas de bens cuja transmissão no território nacional seja isenta. |
| M81 | Isento nos termos da alínea b) do n.º 1 do artigo 14.º | Importações de ouro, moedas ou notas de banco efectuadas pelo Banco Nacional de Angola. |
| M82 | Isento nos termos da alínea c) do n.º 1 do artigo 14.º | Importação de bens destinados a ofertas para atenuar efeitos de calamidades naturais, mediante autorização competente. |
| M83 | Isento nos termos da alínea d) do n.º 1 do artigo 14.º | Mercadorias/equipamentos destinados exclusivamente à execução de operações petrolíferas e mineiras, nos termos dos regimes aplicáveis. |
| M84 | Isento nos termos da alínea e) do n.º 1 do artigo 14.º | Importação de moeda estrangeira por instituições financeiras bancárias nos termos definidos pelo BNA. |
| M85 | Isento nos termos da alínea a) do n.º 2 do artigo 14.º | Importações enquadradas em tratados e acordos internacionais de que Angola seja parte. |
| M86 | Isento nos termos da alínea b) do n.º 2 do artigo 14.º | Operações no âmbito das relações diplomáticas e consulares quando a isenção resulta de tratados/acordos internacionais. |
| M30 | Isento nos termos da alínea a) do artigo 15.º do CIVA | Transmissões de bens expedidos/transportados com destino ao estrangeiro. |
| M31 | Isento nos termos da alínea b) do artigo 15.º do CIVA | Bens de abastecimento colocados a bordo de embarcações que naveguem em alto mar e satisfaçam as condições previstas. |
| M32 | Isento nos termos da alínea c) do artigo 15.º do CIVA | Bens de abastecimento colocados a bordo de aeronaves afectas principalmente ao tráfego internacional. |
| M33 | Isento nos termos da alínea d) do artigo 15.º do CIVA | Bens de abastecimento destinados a embarcações de salvamento, assistência marítima, pesca costeira e embarcações de guerra com destino a porto estrangeiro. |
| M34 | Isento nos termos da alínea e) do artigo 15.º do CIVA | Transmissão, transformação, reparação, manutenção, frete e aluguer, incluindo locação financeira, de determinadas embarcações e aeronaves e serviços directos conexos. |
| M35 | Isento nos termos da alínea f) do artigo 15.º do CIVA | Transmissões no âmbito de relações diplomáticas e consulares quando previstas em acordos/convénios. |
| M36 | Isento nos termos da alínea g) do artigo 15.º do CIVA | Transmissões para organismos internacionais reconhecidos por Angola e respectivos membros dentro dos limites dos acordos aplicáveis. |
| M37 | Isento nos termos da alínea h) do artigo 15.º do CIVA | Transmissões abrangidas por tratados e acordos internacionais de que Angola seja parte. |
| M38 | Isento nos termos da alínea i) do artigo 15.º do CIVA | Transporte de pessoas provenientes ou com destino ao estrangeiro. |
| M90 | Isento nos termos da alínea a) do n.º 1 do artigo 16.º | Importações em zona franca, armazéns sob regimes aduaneiros ou lojas francas enquanto permanecerem nesses regimes. |
| M91 | Isento nos termos da alínea b) do n.º 1 do artigo 16.º | Transmissões para as zonas/depósitos referidos e serviços directamente conexos. |
| M92 | Isento nos termos da alínea c) do n.º 1 do artigo 16.º | Transmissões efectuadas nos regimes da alínea anterior e serviços directamente conexos enquanto os bens permanecerem nesses regimes. |
| M93 | Isento nos termos da alínea d) do n.º 1 do artigo 16.º | Bens em trânsito, draubaque ou importação temporária e serviços directamente conexos enquanto abrangidos por esses regimes. |
| M00 | IVA — Regime Simplificado | Regime simplificado. |
| M02 | Transmissão de bens e serviços não sujeita | Operações não sujeitas a IVA. |
| M04 | IVA — Regime de Exclusão | Regime de exclusão. |

# Tabela 5 — Isenções de Imposto de Selo (IS)

| Código | Menção a constar no documento | Descrição |
| --- | --- | --- |
| S01 | Isento nos termos do CIS | Isenção no âmbito do Código do Imposto do Selo. |
| S02 | Isento nos termos do Artigo 28.º do CBF | Isenção de Imposto do Selo nos aumentos de capital constantes do Código dos Benefícios Fiscais. |
| S03 | Isento nos termos do Artigo 40.º do CBF | Isenção do imposto do selo sobre o recibo de quitação para microempresas, relativa a pagamentos recebidos de vendas. |

# Tabela 6 — Isenções de Imposto Especial de Consumo (IEC)

| Código | Menção a constar no documento | Descrição |
| --- | --- | --- |
| I01 | Isento nos termos da alínea h) e i) do n.º 1 do artigo 6.º da LIEC | Importação e exportação de produtos beneficiando de regime suspensivo de direitos aduaneiros (taxa fixa de UCF 240). |
| I02 | Isenção nos termos da alínea a) do n.º 1 do artigo 6.º do LIEC | Exportação feita pelo próprio produtor ou entidade reconhecida por lei. |
| I03 | Isenção nos termos da alínea b) do n.º 1 do artigo 6.º da LIEC | Bens importados por representações diplomáticas/consulares com reciprocidade e por organizações internacionais. |
| I04 | Isenção nos termos da alínea c) do n.º 1 do artigo 6.º da LIEC | Matérias-primas para a indústria nacional e bens para fins medicinais ou de ensino, devidamente certificados. |
| I05 | Isenção nos termos da alínea d) do n.º 1 do artigo 6.º da LIEC | Bens destinados a fins laboratoriais e investigação científica. |
| I06 | Isenção nos termos da alínea e) do n.º 1 do artigo 6.º da LIEC | Bens de uso pessoal conforme legislação aduaneira. |
| I07 | Isenção nos termos da alínea f) do n.º 1 do artigo 6.º da LIEC | Bens destinados a provisões de bordo de meios de transporte colectivo de passageiros em tráfego internacional. |
| I08 | Isenção nos termos da alínea g) do n.º 1 do artigo 6.º da LIEC | Produtos vendidos a bordo de meios de transporte colectivo de passageiros em tráfego internacional. |
| I09 | Isenção nos termos da alínea h) do n.º 1 do artigo 6.º da LIEC | Produtos que beneficiem de regime suspensivo de direitos aduaneiros. |
| I10 | Isenção nos termos da alínea i) do n.º 1 do artigo 6.º da LIEC | Produtos vendidos em lojas francas. |
| I11 | Isenção nos termos da alínea b) do artigo 98.º do IPP e artigo 15.º do CIVA | Isenção de direitos aduaneiros e IEC e taxas aduaneiras reduzidas para importação/exportação relativa a abastecimento de provisões de bordo para funcionamento/manutenção do meio de transporte. |
| I12 | Isenção nos termos da alínea c) do artigo 98.º do IPP e artigo 15.º do CIVA | Mesmo regime da referência anterior, com taxa fixa de UCF 240. |
| I13 | Isenção nos termos das alíneas h) e i) do artigo 98.º do IPP e artigo 15.º do CIVA | Produtos que beneficiem de regime suspensivo de direitos aduaneiros. |
| I14 | Isenção nos termos do anexo I da LIEC | Isenção de IEC na importação de produtos com código pautal 3926.90.90, excepto as palhinhas de plástico. |
| I15 | Isenção nos termos do artigo 70.º do IPP e artigo 11.º da LIEC | Isenção de direitos aduaneiros e IEC na importação de mercadorias para utilização em eventos. |
| I16 | Isenção nos termos da Resolução n.º 6/91, de 23 de Março, e das alíneas a) e b) do n.º 2 do artigo 14.º do CIVA | Isenção de direitos aduaneiros, IEC e IVA na importação/exportação de mercadorias por agências especializadas das Nações Unidas. |

---

## Observações de transcrição

- Os nomes dos campos JSON foram preservados tanto quanto legíveis no PDF e, quando a digitalização introduziu artefactos tipográficos, foi adoptada a grafia coerente com o restante schema.
- Os anexos e tabelas foram reorganizados para facilitar implementação, pesquisa e consulta em código, sem alterar deliberadamente o conteúdo funcional.
- O documento original permanece a referência jurídica primária para qualquer interpretação normativa.

**Fonte:** Decreto Executivo n.º 683/25, de 22 de Agosto, *Diário da República*, I Série, n.º 159, páginas 19164–19227.