# Regras do SAFT-AO 1.01_01

> **Fonte normativa:** `SAFTAO1.01_01.xsd` fornecido para esta análise. Esta documentação reescreve as regras que estão efetivamente declaradas no XSD: estrutura, ordem, cardinalidade, tipos, restrições, enumerações, documentação semântica, unicidade e referências.

## 1. Identificação do schema

- **Título:** Standard Audit File - Angola
- **Versão:** `1.01_01`
- **ID:** `SAF-T_AO`
- **Namespace:** `urn:OECD:StandardAuditFile-Tax:AO_1.01_01`
- **elementFormDefault:** `qualified`
- **attributeFormDefault:** `unqualified`
- **Autor:** AGT - Administração Geral Tributária
- **Estado no XSD:** `Development`
- **Data de modificação:** `2024-10-16`
- **Repositório indicado:** `https://github.com/assoft-portugal/SAF-T-AO/`

### Contribuidores declarados no XSD
- ASSOFT - Associação Portuguesa de Software — https://www.assoft.org/
- Nelson Lopes — https://github.com/cryptolopes/
- PRIMAVERA - Business Software Solutions, S.A. — http://www.primaverabss.com/
- Softpack - Software, Lda — https://www.softpack.pt/
- Cacimbo Angola — https://www.cacimboangola.com/
- Infodelivery S.A. — http://www.infodelivery.pt/
- Eticadata Software Lda — http://www.eticadata.pt/
- SOFTSTORE, S.A. — http://www.softstore.pt/
- SAP PORTUGAL - Sistemas, Aplicações e Produtos Informáticos, Sociedade Unipessoal Lda. — http://www.sap.com/
- Texto Editores (SU) LDA — https://www.textoeditores.ao
- Paulo Matos — https://github.com/batalhadematos
- ITGest — https://itgest.co.ao/
- Newtec Tecnologias LDA — http://www.newtec.co.ao/
- Infodelivery S.A. — http://www.infodelivery.pt
- Arquiconsult S.A. — https://www.arquiconsult.com

## 2. Regra estrutural raiz

`AuditFile` é o elemento raiz. O XSD exige a seguinte ordem:

```text
AuditFile
├── Header                     [1..1]
├── MasterFiles                [1..1]
│   ├── GeneralLedgerAccounts  [0..unbounded]
│   ├── Customer                [0..unbounded]
│   ├── Supplier                [0..unbounded]
│   ├── Product                 [0..unbounded]
│   └── TaxTable                [0..1]
├── GeneralLedgerEntries       [0..1]
└── SourceDocuments            [0..1]
```

`xs:sequence` significa que a ordem dos elementos no XML faz parte da validação do schema.

## 3. Regras estruturais completas por caminho

Cada subseção abaixo representa uma estrutura `complexType` efectiva do XSD. A cardinalidade é relativa ao elemento pai imediato. `*` significa `unbounded`.
### AuditFile

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `Header` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `MasterFiles` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `GeneralLedgerEntries` | `0..1` | Opcional | `(complexType inline)` | — | Movimentos contabilísticos Neste elemento registam-se os movimentos contabilísticos correspondentes ao periodo de exportação a que diz respeito o SAF-T (AO), não devendo os movimentos de abertura ser objeto de exportação, na medida em que estes são apenas refletidos ao nível do elemento GeneralLedgerAccounts. |
| `SourceDocuments` | `0..1` | Opcional | `(complexType inline)` | — | Documentos comerciais |

### AuditFile/Header

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `AuditFileVersion` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=1.01_01 | Versão a utilizar do esquema XML |
| `CompanyID` | `1..1` | Obrigatório | `(simpleType inline)` | minLength=1; maxLength=50 | Registo comercial. |
| `TaxRegistrationNumber` | `1..1` | Obrigatório | `SAFAOAngolaVatNumber` | minLength=10; maxLength=15 | Número de identificação fiscal da empresa Preencher com o NIF Angolano sem espaços e sem qualquer prefixo do país. |
| `TaxAccountingBasis` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `A`, `C`, `F`, `I`, `P`, `Q`, `R`, `S`, `E` | Deve ser preenchido com o tipo de programa fornecendo os dados aplicáveis (incluindo os documentos de conferência e os recibos emitidos, quando existam): “I” - Contabilidade integrada com a facturação; “C” - Contabilidade; “F” - Facturação; “P” - Facturação parcial; “R” - Recibos; “A” - Aquisição de bens e serviços; ”Q” - Aquisição de bens e serviços integrada com a facturação: “S” - Autofacturação; "E" - Faturação para o Estado. (a) Deve ser indicado este tipo de programa se este emitir só este tipo de documento. Caso contrário, deverá ser utilizado o tipo “C”, “F” |
| `CompanyName` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Denominação social da empresa ou nome do sujeito passivo. |
| `BusinessName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Designação social do sujeito passivo. |
| `CompanyAddress` | `1..1` | Obrigatório | `AddressStructureAO` | — | Endereço da empresa |
| `FiscalYear` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=2000; maxInclusive=9999 | Ano fiscal. Utilizar as regras do Código do II, no caso de períodos contabilísticos coincidentes com o ano civíl. |
| `StartDate` | `1..1` | Obrigatório | `SAFAODateSpan` | minInclusive=2000-01-01; maxInclusive=9999-12-31 | Data de início do período do ficheiro |
| `EndDate` | `1..1` | Obrigatório | `SAFAODateSpan` | minInclusive=2000-01-01; maxInclusive=9999-12-31 | Data do fim do período do ficheiro |
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `AOA`, `USD` | Código da moeda. Identifica a moeda padrão a utilizar nos campos do tipo monetário existentes no ficheiro. Preencher com "AOA". |
| `DateCreated` | `1..1` | Obrigatório | `SAFAODateSpan` | minInclusive=2000-01-01; maxInclusive=9999-12-31 | Data de criação do ficheiro XML do SAF-T (AO). |
| `TaxEntity` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | No caso do ficheiro de faturação, deve ser especificado a que estabelecimento (posto de venda) diz respeito o ficheiro produzido, se aplicável. Caso contrário, deve ser preenchido com a especificação "Global". No caso do ficheiro de contabilidade ou integrado, este campo deve ser preenchido com a especificação "Sede". Identificação do estabelecimento |
| `ProductCompanyTaxID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Preencher com o NIF da entidade produtora do software. Identificação fiscal da entidade produtora do software |
| `SoftwareValidationNumber` | `1..1` | Obrigatório | `ns:SAFAOtextValidationNumber` | minLength=1; maxLength=70; pattern=\d+/AGT/\d{4}\|[0] | Número de validação atribuído ao software Número da validação. atribuído à entidade produtora do software. Deve ser preenchido com: NNN/AGT/AAAA. Se não aplicável, deve ser preenchido com «0» (zero). |
| `ProductID` | `1..1` | Obrigatório | `SAFAOProductID` | pattern=[^/]+/[^/]+; minLength=3; maxLength=255 | Nome da aplicação Nome da aplicação que gera o SAF-T(AO). Deve ser indicado o nome comercial do software e da empresa empresa produtora no formato «Nome da aplicação/Nome da empresa produtora do software». |
| `ProductVersion` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Versão da aplicação |
| `HeaderComment` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Comentários adicionais |
| `Telephone` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Telefone |
| `Fax` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Fax |
| `Email` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Email |
| `Website` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Endereço do sítio Web |

### AuditFile/Header/CompanyAddress
> Endereço da empresa

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `PostalCodeAO` | minLength=0; maxLength=10 | — |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `—` | — | — |

### AuditFile/MasterFiles

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `GeneralLedgerAccounts` | `0..unbounded` | Opcional | `(complexType inline)` | — | — |
| `Customer` | `0..unbounded` | Opcional | `(complexType inline)` | — | Tabela de clientes |
| `Supplier` | `0..unbounded` | Opcional | `(complexType inline)` | — | Tabela de fornecedores |
| `Product` | `0..unbounded` | Opcional | `(complexType inline)` | — | Tabela de produtos/serviços |
| `TaxTable` | `0..1` | Opcional | `(complexType inline)` | — | Tabela de impostos |

### AuditFile/MasterFiles/GeneralLedgerAccounts

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `Account` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | — |

### AuditFile/MasterFiles/GeneralLedgerAccounts/Account

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `AccountID` | `1..1` | Obrigatório | `SAFAOGLAccountID` | pattern=(([0-9a-zA-Z\-/._+*]*)); minLength=1; maxLength=30 | Devem constar no ficheiro todas as contas, incluindo as respetivas contas integradoras, até às contas do Razão. Código da conta |
| `AccountDescription` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | Descrição da conta |
| `OpeningDebitBalance` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Saldo de abertura a débito da conta do plano de contas. O saldo de abertura a débito será sempre o do início do período de tributação. |
| `OpeningCreditBalance` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Saldo de abertura a crédito da conta do plano de contas. O saldo de abertura a crédito será sempre o do início do período de tributação. |
| `ClosingDebitBalance` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Saldo de encerramento da conta a débito do plano de contas. O saldo de encerramento a débito será o do fim do período de tributação ou a data de geração, se anterior. |
| `ClosingCreditBalance` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Saldo de encerramento da conta a crédito do plano de contas. O saldo de encerramento a crédito será o do fim do período de tributação ou a data de geração, se anterior. |
| `GroupingCategory` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `GR`, `GA`, `GM`, `AR`, `AA`, `AM` | Categoria do tipo de conta. Deve ser indicado o tipo e a categoria da conta: “GR” – Conta de 1.º grau da contabilidade geral; “GA” – Conta agregadora ou integradora da contabilidade geral; “GM” – Conta de movimento da contabilidade geral; “AR” – Conta de 1.º grau da contabilidade analítica; “AA” – Conta agregadora ou integradora da contabilidade analítica; e “AM” – Conta de movimento da contabilidade analítica. |
| `GroupingCode` | `0..1` | Opcional | `SAFAOGLAccountID` | pattern=(([0-9a-zA-Z\-/._+*]*)); minLength=1; maxLength=30 | Excepto para as contas do 1.º grau, deve ser indicada a contaagregadora respectiva, do grau imediatamente superior, utilizando para este efeito a exacta estrutura que consta no correspondente campo 2.1.2.1. - Código da conta (Account ID). Código da conta |

### AuditFile/MasterFiles/Customer
> Tabela de clientes

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CustomerID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final". |
| `AccountID` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=(([0-9a-zA-Z\-/._+*]*)\|Desconhecido); minLength=1; maxLength=30 | Código da conta Deve ser indicada a respectiva conta-corrente do cliente no plano de contas da contabilidade, caso esteja definida. Caso contrário deve ser preenchido com a designação "Desconhecido". |
| `CustomerTaxID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Número de identificação fiscal do cliente Deve ser indicado sem o prefixo do país. O cliente genérico, correspondente ao designado ""Consumidor final"", deve ser identificado com o NIF "999999999". |
| `CompanyName` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Denominação social da empresa ou nome do sujeito passivo. |
| `Contact` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Nome do contacto na empresa |
| `BillingAddress` | `1..1` | Obrigatório | `AddressStructure` | — | Endereço de faturação Corresponde ao endereço da sede ou do estabelecimento estável em território nacional. Endereço |
| `ShipToAddress` | `0..unbounded` | Opcional | `AddressStructure` | — | Endereço de expedição Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. Endereço |
| `Telephone` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Telefone |
| `Fax` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Fax |
| `Email` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Email |
| `Website` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Endereço do sítio Web |
| `SelfBillingIndicator` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário. |

### AuditFile/MasterFiles/Customer/BillingAddress
> Endereço de faturação Corresponde ao endereço da sede ou do estabelecimento estável em território nacional.
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/MasterFiles/Customer/ShipToAddress
> Endereço de expedição Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/MasterFiles/Supplier
> Tabela de fornecedores

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SupplierID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do fornecedor |
| `AccountID` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=(([0-9a-zA-Z\-/._+*]*)\|Desconhecido); minLength=1; maxLength=30 | Código da conta Deve ser indicada a respectiva conta-corrente do cliente no plano de contas da contabilidade, caso esteja definida. Caso contrário deve ser preenchido com a designação "Desconhecido". |
| `SupplierTaxID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Número de identificação fiscal do fornecedor. Deve ser indicado sem o prefixo do país. |
| `CompanyName` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Denominação social da empresa ou nome do sujeito passivo. |
| `Contact` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Nome do contacto na empresa |
| `BillingAddress` | `1..1` | Obrigatório | `SupplierAddressStructure` | — | — |
| `ShipFromAddress` | `0..unbounded` | Opcional | `SupplierAddressStructure` | — | — |
| `Telephone` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Telefone |
| `Fax` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Fax |
| `Email` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Email |
| `Website` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Endereço do sítio Web |
| `SelfBillingIndicator` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário. |

### AuditFile/MasterFiles/Supplier/BillingAddress

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `SupplierCountry` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW; length=2 | — |

### AuditFile/MasterFiles/Supplier/ShipFromAddress

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `SupplierCountry` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW; length=2 | — |

### AuditFile/MasterFiles/Product
> Tabela de produtos/serviços

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `ProductType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `P`, `S`, `O`, `E`, `I` | Deve ser preenchido com: “P” – Produtos; “S” – Serviços; “O” – Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); “E” – Impostos Especiais de Consumo – (ex.:IEC); “I” – Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos na tabela 2.5 – Tabela de impostos (Tax Table) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código “E”. |
| `ProductCode` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E". |
| `ProductGroup` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Família do produto ou serviço |
| `ProductDescription` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do produto ou serviço |
| `ProductNumberCode` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Código do produto. Deve ser usado o código EAN do produto. Quando este não existir, preencher com o valor do elemento ProductCode. |
| `CustomsDetails` | `0..1` | Opcional | `CustomsDetails` | — | Caracterização aduaneira |

### AuditFile/MasterFiles/Product/CustomsDetails
> Caracterização aduaneira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `UNNumber` | `0..unbounded` | Opcional | `SAFAOUNNumber` | pattern=[0-9]{4}; length=4 | Preencher com o nº ONU para produtos perigosos |

### AuditFile/MasterFiles/TaxTable
> Tabela de impostos

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxTableEntry` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | Registo na tabela de impostos |

### AuditFile/MasterFiles/TaxTable/TaxTableEntry
> Registo na tabela de impostos

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | Opcional | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | Obrigatório | `TaxTableEntryTaxCode` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA; minLength=1; maxLength=10 | Código do imposto. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa Intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". Nos recibos emitidos sem a descriçao de imposto deve usar-se "NA". |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Descrição do imposto |
| `TaxExpirationDate` | `0..1` | Opcional | `SAFdateType` | — | Data de fim de vigência |
| **CHOICE** | — | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### AuditFile/GeneralLedgerEntries
> Movimentos contabilísticos Neste elemento registam-se os movimentos contabilísticos correspondentes ao periodo de exportação a que diz respeito o SAF-T (AO), não devendo os movimentos de abertura ser objeto de exportação, na medida em que estes são apenas refletidos ao nível do elemento GeneralLedgerAccounts.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfEntries` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `TotalDebit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount. |
| `TotalCredit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount. |
| `Journal` | `0..unbounded` | Opcional | `(complexType inline)` | — | Diários |

### AuditFile/GeneralLedgerEntries/Journal
> Diários

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `JournalID` | `1..1` | Obrigatório | `SAFAOJournalID` | pattern=[^ ]{1,30}; minLength=1; maxLength=30 | Identificador do diário |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do diário |
| `Transaction` | `0..unbounded` | Opcional | `(complexType inline)` | — | Identificador da transação |

### AuditFile/GeneralLedgerEntries/Journal/Transaction
> Identificador da transação

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TransactionID` | `1..1` | Obrigatório | `SAFAOTransactionID` | pattern=[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}; minLength=1; maxLength=70 | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| `Period` | `1..1` | Obrigatório | `SAFAOAccountingPeriod` | minInclusive=1; maxInclusive=16 | Período contabilístico |
| `TransactionDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do documento. Para recibos de pagamento corresponde à data do recibo. |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do movimento |
| `DocArchivalNumber` | `1..1` | Obrigatório | `SAFTAODocArchivalNumber` | pattern=[^ ]{1,20}; minLength=1; maxLength=20 | Número de arquivo do documento |
| `TransactionType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `N`, `R`, `A`, `J` | Deve ser preenchido com: “N” – Normal; “R” – Regularizações do período de tributação; “A” – Apuramento de resultados; “J” – Movimentos de ajustamento. |
| `GLPostingDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do movimento contabilístico |
| **CHOICE** | — | — | — | — | `CustomerID` [0..1] ou `SupplierID` [0..1] |
| `Lines` | `1..1` | Obrigatório | `(complexType inline)` | — | Estrutura agregadora das linhas de movimentos, que tem que incluir, pelo menos, uma linha de débito e uma linha de crédito. Tem de ser tida em consideração a ordem dos elementos: - Primeiro os de DebitLine - Depois os de CreditLine |

### AuditFile/GeneralLedgerEntries/Journal/Transaction/Lines
> Estrutura agregadora das linhas de movimentos, que tem que incluir, pelo menos, uma linha de débito e uma linha de crédito. Tem de ser tida em consideração a ordem dos elementos: - Primeiro os de DebitLine - Depois os de CreditLine

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|

### AuditFile/SourceDocuments
> Documentos comerciais

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SalesInvoices` | `0..1` | Opcional | `(complexType inline)` | — | Documentos comerciais a clientes |
| `MovementOfGoods` | `0..1` | Opcional | `(complexType inline)` | — | — |
| `WorkingDocuments` | `0..1` | Opcional | `(complexType inline)` | — | — |
| `Payments` | `0..1` | Opcional | `(complexType inline)` | — | — |
| `PurchaseInvoices` | `0..1` | Opcional | `(complexType inline)` | — | Documentos comerciais de Fornecedores |

### AuditFile/SourceDocuments/SalesInvoices
> Documentos comerciais a clientes

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfEntries` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `TotalDebit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount. |
| `TotalCredit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount. |
| `Invoice` | `0..unbounded` | Opcional | `(complexType inline)` | — | Documento de venda |

### AuditFile/SourceDocuments/SalesInvoices/Invoice
> Documento de venda

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `InvoiceNo` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=[^ ]+ [^/^ ]+/[0-9]+; minLength=1; maxLength=60 | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (InvoiceType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. Exemplos: InvoiceType: FT InvoiceNo: FT S001/1 InvoiceType: NC InvoiceNo: NC S001/1 |
| `DocumentStatus` | `1..1` | Obrigatório | `(complexType inline)` | — | Situação do documento |
| `Hash` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax172Car` | minLength=1; maxLength=172 | Chave do documento |
| `HashControl` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax70Car` | minLength=1; maxLength=70 | O campo deve ser preenchido com “0” (zero), caso o documento seja gerado por um programa não validado. |
| `Period` | `0..1` | Opcional | `(simpleType inline)` | minInclusive=1; maxInclusive=12 | Período contabilístico |
| `InvoiceDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do documento de venda |
| `InvoiceType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `FT`, `FR`, `GF`, `FG`, `AC`, `AR`, `ND`, `NC`, `AF`, `TV`, `RP`, `RE`, `CS`, `LD`, `RA` | Deve ser preenchido com: “FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “ND” - Nota de débito; “NC” - Nota de crédito “AF” - Factura/recibo (autofacturação) “TV” - Talão de venda Para o sector Segurador quando não deva constar da tabela 4.3. - Documentos de conferência de mercadorias ou de prestação de serviços (WorkingDocuments), pode ainda ser preenchido com: “RP” - Prémio ou recibo de prémio; “RE” - Estorno ou recibo de estorno; “CS” - Imputação a co-seguradoras; “LD” - Imputação a co-seguradora líder; “RA” - Resseguro aceite. |
| `SpecialRegimes` | `1..1` | Obrigatório | `SpecialRegimes` | — | Regimes especiais |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `EACCode` | `0..1` | Opcional | `(simpleType inline)` | pattern=(([0-9]*)); length=5 | Código CAE |
| `SystemEntryDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Timestamp a que corresponde a data de registo do documento |
| `TransactionID` | `0..1` | Opcional | `SAFAOTransactionID` | pattern=[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}; minLength=1; maxLength=70 | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| `CustomerID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final". |
| `ShipTo` | `0..1` | Opcional | `ShippingPointStructure` | — | Local de descarga |
| `ShipFrom` | `0..1` | Opcional | `ShippingPointStructure` | — | Local de carga |
| `MovementEndTime` | `0..1` | Opcional | `SAFdateTimeType` | — | Data e hora de fim de transporte |
| `MovementStartTime` | `0..1` | Opcional | `SAFdateTimeType` | — | Data e hora de início de transporte |
| `Line` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | Linha do documento |
| `DocumentTotals` | `1..1` | Obrigatório | `(complexType inline)` | — | Totais do documento |
| `WithholdingTax` | `0..unbounded` | Opcional | `WithholdingTax` | — | Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentStatus
> Situação do documento

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `InvoiceStatus` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `N`, `S`, `A`, `R` | Deve ser preenchido com: “N” - Normal; “S” - Autofacturação; “A” - Documento anulado; “R” - Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação; |
| `InvoiceStatusDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Data e hora do estado actual do documento |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `SourceBilling` | `1..1` | Obrigatório | `SAFTAOSourceBilling` | valores: `P`, `I`, `M` | P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/SpecialRegimes
> Regimes especiais

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SelfBillingIndicator` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário. |
| `CashVATSchemeIndicator` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de regime de IVA de Caixa |
| `ThirdPartiesBillingIndicator` | `1..1` | Obrigatório | `(simpleType inline)` | minInclusive=0; maxInclusive=3 | Indicador de regime de IVA de Caixa Deve ser preenchido com: "0" - Se não cumprir com nenhuma condição; "1" - se o documento for emitido em nome e por conta de terceiros; "2" - se respeitar ao regime de IVA Cativo; "3" - se cumprir com as condições 1 e 2 em simultâneo. |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/ShipTo
> Local de descarga

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DeliveryID` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Identificador da entrega |
| `DeliveryDate` | `0..1` | Opcional | `SAFdateType` | — | Data da entrega |
| **SEQUENCE** | — | — | — | — | Sequência aninhada definida pelo XSD. |
| `Address` | `0..1` | Opcional | `AddressStructure` | — | Endereço |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/ShipTo/Address
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/ShipFrom
> Local de carga

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DeliveryID` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Identificador da entrega |
| `DeliveryDate` | `0..1` | Opcional | `SAFdateType` | — | Data da entrega |
| **SEQUENCE** | — | — | — | — | Sequência aninhada definida pelo XSD. |
| `Address` | `0..1` | Opcional | `AddressStructure` | — | Endereço |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/ShipFrom/Address
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line
> Linha do documento

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `LineNumber` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original. |
| `OrderReferences` | `0..unbounded` | Opcional | `OrderReferences` | — | Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior. |
| `ProductCode` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E". |
| `ProductDescription` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do produto ou serviço |
| `Quantity` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Quantidade |
| `UnitOfMeasure` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Unidade de medida |
| `UnitPrice` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Preço unitário deduzido dos descontos de linha e de cabeçalho, sem incluir impostos. |
| `TaxBase` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Valor tributável unitário. Valor tributável unitário que não concorre para o Total do documento sem impostos (NetTotal). Este valor é o que serve de base de cálculo dos impostos da linha. O sinal (debito ou crédito) com que o imposto assim calculado concorre para o TaxPayable, resulta da existência na linha do DebitAmount ou do CreditAmount. |
| `TaxPointDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data de envio da mercadoria ou prestação do serviço. Deve coincidir com a data precisa do envio da mercadoria ou da prestação do serviço, o que por vezes pode não coincidir com a data do documento. |
| `References` | `0..unbounded` | Opcional | `References` | — | Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchido com “NC” – Nota de crédito |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição da linha. Deve coincidir com aquela que consta do documento entregue ao cliente. |
| `ProductSerialNumber` | `0..1` | Opcional | `ProductSerialNumber` | — | Número de série |
| **CHOICE** | — | — | — | — | `DebitAmount` [1..1] ou `CreditAmount` [1..1] |
| `Tax` | `1..1` | Obrigatório | `Tax` | — | Impostos |
| `SettlementAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |
| `CustomsInformation` | `0..1` | Opcional | `CustomsInformation` | — | Informação aduaneira |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/OrderReferences
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `OriginatingON` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o tipo, a série e o número do documento que suporta a emissão deste. Se o documento estiver contido no SAF-T AO deve ser utilizada a estrutura de numeração do campo de origem. |
| `OrderDate` | `0..1` | Opcional | `SAFdateType` | — | — |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/References
> Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchido com “NC” – Nota de crédito

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `Reference` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Referência à factura, através de identificação única da mesma, nos sistemas em que exista. Deve ser utilizada a estrutura de numeração do campo de origem. |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/ProductSerialNumber
> Número de série

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SerialNumber` | `1..unbounded` | Obrigatório | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | — |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/Tax
> Impostos

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | Opcional | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA; minLength=1; maxLength=10 | Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". |
| **CHOICE** | — | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/CustomsInformation
> Informação aduaneira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `ARCNo` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax21Car` | minLength=1; maxLength=20 | Código de referência administrativo ou D.U |
| `IECAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Montante do imposto especial de consumo da linha |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals
> Totais do documento

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxPayable` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Valor do imposto a pagar |
| `NetTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento sem impostos |
| `GrossTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento com impostos |
| `Currency` | `0..1` | Opcional | `Currency` | — | Moeda estrangeira |
| `Settlement` | `0..unbounded` | Opcional | `Settlement` | — | Acordos ou formas de pagamento. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. |
| `Payment` | `0..unbounded` | Opcional | `PaymentMethod` | — | Relativo à forma e ao método de pagamento. Havendo mais que um, pode ser repetido quantas vezes forem necessárias. |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Currency
> Moeda estrangeira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement
> Acordos ou formas de pagamento. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SettlementDiscount` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Deve ser preenchido com os acordos de descontos a aplicar no futuro sobre o valor presente. |
| `SettlementAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Representa o valor acordado para desconto futuro, mas que não concorre para o GrossTotal do documento. |
| `SettlementDate` | `0..1` | Opcional | `SAFdateType` | — | Data acordada para o pagamento com desconto. |
| `PaymentTerms` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | Descrição dos acordos estabelecidos ou a data limite de pagamento. |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Payment
> Relativo à forma e ao método de pagamento. Havendo mais que um, pode ser repetido quantas vezes forem necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `PaymentMechanism` | `0..1` | Opcional | `(simpleType inline)` | valores: `CC`, `CD`, `CH`, `CI`, `CO`, `CS`, `DE`, `MB`, `NU`, `OU`, `PR`, `TB` | Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc. |
| `PaymentAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Montante por meio de pagamento. |
| `PaymentDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do pagamento. |

### AuditFile/SourceDocuments/SalesInvoices/Invoice/WithholdingTax
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `WithholdingTaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IRT`, `II`, `IS`, `IVA`, `IPU`, `IAC`, `OU` | Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos |
| `WithholdingTaxDescription` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o normativo legal aplicável ou a percentagem de imposto aplicável. |
| `WithholdingTaxAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve ser indicado o montante retido de imposto. |

### AuditFile/SourceDocuments/MovementOfGoods

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfMovementLines` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | — |
| `TotalQuantityIssued` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | — |
| `StockMovement` | `0..unbounded` | Opcional | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DocumentNumber` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=[^ ]+ [^/^ ]+/[0-9]+; minLength=1; maxLength=60 | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (MovementType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. |
| `DocumentStatus` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `Hash` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax172Car` | minLength=1; maxLength=172 | Chave do documento |
| `HashControl` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax70Car` | minLength=1; maxLength=70 | O campo deve ser preenchido com “0” (zero), caso o documento seja gerado por um programa não validado. |
| `Period` | `0..1` | Opcional | `(simpleType inline)` | minInclusive=1; maxInclusive=12 | Período contabilístico |
| `MovementDate` | `1..1` | Obrigatório | `SAFdateType` | — | — |
| `MovementType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `GR`, `GT`, `GA`, `GD` | Deve ser preenchido com: “GR” – Guia de remessa; “GT” – Guia de transporte (incluir aqui as guias globais); “GA” – Guia de movimentação de activos fixos próprios; “GD” – Guia ou nota de devolução. |
| `SystemEntryDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Timestamp a que corresponde a data de registo do documento |
| `TransactionID` | `0..1` | Opcional | `SAFAOTransactionID` | pattern=[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}; minLength=1; maxLength=70 | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| **CHOICE** | — | — | — | — | `CustomerID` [1..1] ou `SupplierID` [1..1] |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `EACCode` | `0..1` | Opcional | `(simpleType inline)` | pattern=(([0-9]*)); length=5 | Código CAE |
| `MovementComments` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | — |
| `ShipTo` | `0..1` | Opcional | `ShippingPointStructure` | — | Local de descarga |
| `ShipFrom` | `0..1` | Opcional | `ShippingPointStructure` | — | Local de carga |
| `MovementEndTime` | `0..1` | Opcional | `SAFdateTimeType` | — | Data e hora de fim de transporte |
| `MovementStartTime` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Data e hora de início de transporte |
| `AGTDocCodeID` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | — |
| `Line` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | — |
| `DocumentTotals` | `1..1` | Obrigatório | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/DocumentStatus

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `MovementStatus` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `N`, `T`, `A`, `F`, `R` | Deve ser preenchido com: “N” – Normal; “T” – Por conta de terceiros; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos comerciais a clientes (SalesInvoices) o correspondente do tipo factura. “R” – Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação. |
| `MovementStatusDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | — |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `SourceBilling` | `1..1` | Obrigatório | `SAFTAOSourceBilling` | valores: `P`, `I`, `M` | P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/ShipTo
> Local de descarga

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DeliveryID` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Identificador da entrega |
| `DeliveryDate` | `0..1` | Opcional | `SAFdateType` | — | Data da entrega |
| **SEQUENCE** | — | — | — | — | Sequência aninhada definida pelo XSD. |
| `Address` | `0..1` | Opcional | `AddressStructure` | — | Endereço |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/ShipTo/Address
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/ShipFrom
> Local de carga

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DeliveryID` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Identificador da entrega |
| `DeliveryDate` | `0..1` | Opcional | `SAFdateType` | — | Data da entrega |
| **SEQUENCE** | — | — | — | — | Sequência aninhada definida pelo XSD. |
| `Address` | `0..1` | Opcional | `AddressStructure` | — | Endereço |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/ShipFrom/Address
> Endereço

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `BuildingNumber` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `LineNumber` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original. |
| `OrderReferences` | `0..unbounded` | Opcional | `OrderReferences` | — | Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior. |
| `ProductCode` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E". |
| `ProductDescription` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do produto ou serviço |
| `Quantity` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Quantidade |
| `UnitOfMeasure` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Unidade de medida |
| `UnitPrice` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Preço unitário deduzido dos descontos de linha e de cabeçalho, sem incluir impostos. |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | — |
| `ProductSerialNumber` | `0..1` | Opcional | `ProductSerialNumber` | — | Número de série |
| **CHOICE** | — | — | — | — | `DebitAmount` [1..1] ou `CreditAmount` [1..1] |
| `Tax` | `0..1` | Opcional | `MovementTax` | — | Impostos |
| `SettlementAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |
| `CustomsInformation` | `0..1` | Opcional | `CustomsInformation` | — | Informação aduaneira |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/OrderReferences
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `OriginatingON` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o tipo, a série e o número do documento que suporta a emissão deste. Se o documento estiver contido no SAF-T AO deve ser utilizada a estrutura de numeração do campo de origem. |
| `OrderDate` | `0..1` | Opcional | `SAFdateType` | — | — |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/ProductSerialNumber
> Número de série

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SerialNumber` | `1..unbounded` | Obrigatório | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | — |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/Tax
> Impostos

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxType` | `1..1` | Obrigatório | `SAFTAOMovementTaxType` | valores: `IVA`, `NS` | — |
| `TaxCountryRegion` | `0..1` | Opcional | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | Obrigatório | `SAFTAOMovementTaxCode` | pattern=RED\|INT\|NOR\|ISE\|OUT\|NS\|NA; minLength=1; maxLength=3 | Código da taxa na tabela de impostos. Deve ser preenchido com: “RED” – Taxa reduzida; "INT" - Taxa intermédia; “NOR” – Taxa normal; “ISE” – Isenta; “OUT” – Outros, aplicável para os regimes especiais de IVA. No caso de não sujeição deve ser preenchido com «NS». |
| `TaxPercentage` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Percentagem da taxa de imposto |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/CustomsInformation
> Informação aduaneira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `ARCNo` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax21Car` | minLength=1; maxLength=20 | Código de referência administrativo ou D.U |
| `IECAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Montante do imposto especial de consumo da linha |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/DocumentTotals

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxPayable` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Valor do imposto a pagar |
| `NetTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento sem impostos |
| `GrossTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento com impostos |
| `Currency` | `0..1` | Opcional | `Currency` | — | Moeda estrangeira |

### AuditFile/SourceDocuments/MovementOfGoods/StockMovement/DocumentTotals/Currency
> Moeda estrangeira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### AuditFile/SourceDocuments/WorkingDocuments

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfEntries` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `TotalDebit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount. |
| `TotalCredit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount. |
| `WorkDocument` | `0..unbounded` | Opcional | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `DocumentNumber` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=[^ ]+ [^/^ ]+/[0-9]+; minLength=1; maxLength=60 | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (MovementType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. |
| `DocumentStatus` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `Hash` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax172Car` | minLength=1; maxLength=172 | Chave do documento |
| `HashControl` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax70Car` | minLength=1; maxLength=70 | O campo deve ser preenchido com “0” (zero), caso o documento seja gerado por um programa não validado. |
| `Period` | `0..1` | Opcional | `(simpleType inline)` | minInclusive=1; maxInclusive=12 | Período contabilístico |
| `WorkDate` | `1..1` | Obrigatório | `SAFdateType` | — | — |
| `WorkType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `CM`, `CC`, `GR`, `NR`, `FO`, `NE`, `OU`, `OR`, `PF`, `DC`, `RP`, `RE`, `CS`, `LD`, `RA`, `PP`, `GC` | Deve ser preenchido com: “CM” – Consultas de mesa; “CC” – Credito de consignação; “GR” – Guia de remessa; “NR” – Nota de remessa; “FO” – Folhas de obra; “NE” – Nota de Encomenda; “OU” – Outros; “OR” – Orçamentos; “PF” – Pró-forma; “DC” – Documentos emitidos que sejam susceptíveis de apresentação ao cliente para conferência de mercadorias ou de prestação de serviços. Para o sector Segurador quando para os tipos de documentos a seguir identificados também deva existir na tabela 4.1 - Documentos comerciais a clientes (SalesInvoices) a correspondente factura ou documento rectificativo de factura, ainda pode ser preenchido com: “RP” – Prémio ou recibo de prémio; “RE” – Estorno ou recibo de estorno; “CS” – Imputação a co-seguradoras; “LD” – Imputação a co-seguradora líder; “RA” – Resseguro aceite; “GC” – Guia de consignação; |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `EACCode` | `0..1` | Opcional | `(simpleType inline)` | pattern=(([0-9]*)); length=5 | Código CAE |
| `SystemEntryDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Timestamp a que corresponde a data de registo do documento |
| `TransactionID` | `0..1` | Opcional | `SAFAOTransactionID` | pattern=[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}; minLength=1; maxLength=70 | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| `CustomerID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final". |
| `Line` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | — |
| `DocumentTotals` | `1..1` | Obrigatório | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/DocumentStatus

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `WorkStatus` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `N`, `A`, `F` | Deve ser preenchido com: “N” – Normal; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos Comerciais a clientes (SalesInvoices) o correspondente do tipo factura. |
| `WorkStatusDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | — |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `SourceBilling` | `1..1` | Obrigatório | `SAFTAOSourceBilling` | valores: `P`, `I`, `M` | P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `LineNumber` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original. |
| `OrderReferences` | `0..unbounded` | Opcional | `OrderReferences` | — | Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior. |
| `ProductCode` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E". |
| `ProductDescription` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Descrição do produto ou serviço |
| `Quantity` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Quantidade |
| `UnitOfMeasure` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Unidade de medida |
| `UnitPrice` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Preço unitário deduzido dos descontos de linha e de cabeçalho, sem incluir impostos. |
| `TaxBase` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Valor tributável unitário. Valor tributável unitário que não concorre para o Total do documento sem impostos (NetTotal). Este valor é o que serve de base de cálculo dos impostos da linha. O sinal (debito ou crédito) com que o imposto assim calculado concorre para o TaxPayable, resulta da existência na linha do DebitAmount ou do CreditAmount. |
| `TaxPointDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data de envio da mercadoria ou prestação do serviço. Deve coincidir com a data precisa do envio da mercadoria ou da prestação do serviço, o que por vezes pode não coincidir com a data do documento. |
| `Description` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | — |
| `References` | `0..unbounded` | Opcional | `References` | — | Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchido com “NC” – Nota de crédito |
| `ProductSerialNumber` | `0..1` | Opcional | `ProductSerialNumber` | — | Número de série |
| **CHOICE** | — | — | — | — | `DebitAmount` [1..1] ou `CreditAmount` [1..1] |
| `Tax` | `0..1` | Opcional | `Tax` | — | Impostos |
| `SettlementAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |
| `CustomsInformation` | `0..1` | Opcional | `CustomsInformation` | — | Informação aduaneira |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/OrderReferences
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `OriginatingON` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o tipo, a série e o número do documento que suporta a emissão deste. Se o documento estiver contido no SAF-T AO deve ser utilizada a estrutura de numeração do campo de origem. |
| `OrderDate` | `0..1` | Opcional | `SAFdateType` | — | — |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/References
> Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchido com “NC” – Nota de crédito

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `Reference` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Referência à factura, através de identificação única da mesma, nos sistemas em que exista. Deve ser utilizada a estrutura de numeração do campo de origem. |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/ProductSerialNumber
> Número de série

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SerialNumber` | `1..unbounded` | Obrigatório | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | — |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/Tax
> Impostos

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | Opcional | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA; minLength=1; maxLength=10 | Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". |
| **CHOICE** | — | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/CustomsInformation
> Informação aduaneira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `ARCNo` | `0..unbounded` | Opcional | `SAFAOtextTypeMandatoryMax21Car` | minLength=1; maxLength=20 | Código de referência administrativo ou D.U |
| `IECAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Montante do imposto especial de consumo da linha |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/DocumentTotals

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxPayable` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Valor do imposto a pagar |
| `NetTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento sem impostos |
| `GrossTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento com impostos |
| `Currency` | `0..1` | Opcional | `Currency` | — | Moeda estrangeira |

### AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/DocumentTotals/Currency
> Moeda estrangeira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### AuditFile/SourceDocuments/Payments

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfEntries` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `TotalDebit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount. |
| `TotalCredit` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount. |
| `Payment` | `0..unbounded` | Opcional | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/Payments/Payment

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `PaymentRefNo` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=[^ ]+ [^/^ ]+/[0-9]+; minLength=1; maxLength=60 | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (PaymentType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador e a série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. |
| `Period` | `0..1` | Opcional | `(simpleType inline)` | minInclusive=1; maxInclusive=12 | Período contabilístico |
| `TransactionID` | `0..1` | Opcional | `SAFAOTransactionID` | pattern=[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}; minLength=1; maxLength=70 | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| `TransactionDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do documento. Para recibos de pagamento corresponde à data do recibo. |
| `PaymentType` | `1..1` | Obrigatório | `SAFTAOPaymentType` | valores: `RC`, `RG`, `AR` | Deve ser preenchido com: “RC” – Recibo emitido “AR” – Aviso de cobrança/recibo “RG” – Outros recibos emitidos. |
| `Description` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | — |
| `SystemID` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax35Car` | minLength=1; maxLength=35 | — |
| `DocumentStatus` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `PaymentMethod` | `0..unbounded` | Opcional | `PaymentMethod` | — | Relativo à forma e ao método de pagamento. Havendo mais que um, pode ser repetido quantas vezes forem necessárias. |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `SystemEntryDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | Timestamp a que corresponde a data de registo do documento |
| `CustomerID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final". |
| `Line` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | — |
| `DocumentTotals` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `WithholdingTax` | `0..unbounded` | Opcional | `WithholdingTax` | — | Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. |

### AuditFile/SourceDocuments/Payments/Payment/DocumentStatus

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `PaymentStatus` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `N`, `A` | N para normal, A para Anulado |
| `PaymentStatusDate` | `1..1` | Obrigatório | `SAFdateTimeType` | — | — |
| `Reason` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `SourcePayment` | `1..1` | Obrigatório | `SAFTAOSourcePayment` | valores: `P`, `I`, `M` | P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual |

### AuditFile/SourceDocuments/Payments/Payment/PaymentMethod
> Relativo à forma e ao método de pagamento. Havendo mais que um, pode ser repetido quantas vezes forem necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `PaymentMechanism` | `0..1` | Opcional | `(simpleType inline)` | valores: `CC`, `CD`, `CH`, `CI`, `CO`, `CS`, `DE`, `MB`, `NU`, `OU`, `PR`, `TB` | Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc. |
| `PaymentAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Montante por meio de pagamento. |
| `PaymentDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do pagamento. |

### AuditFile/SourceDocuments/Payments/Payment/Line

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `LineNumber` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original. |
| `SourceDocumentID` | `1..unbounded` | Obrigatório | `(complexType inline)` | — | — |
| `SettlementAmount` | `0..1` | Opcional | `SAFmonetaryType` | minInclusive=0.00 | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |
| **CHOICE** | — | — | — | — | `DebitAmount` [1..1] ou `CreditAmount` [1..1] |
| `Tax` | `0..1` | Opcional | `PaymentTax` | — | — |

### AuditFile/SourceDocuments/Payments/Payment/Line/SourceDocumentID

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `OriginatingON` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | — |
| `InvoiceDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do documento de venda |
| `Description` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | — |

### AuditFile/SourceDocuments/Payments/Payment/Line/Tax

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | Opcional | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | Obrigatório | `PaymentTaxCode` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NA\|NS; minLength=1; maxLength=10 | "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. |
| **CHOICE** | — | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### AuditFile/SourceDocuments/Payments/Payment/DocumentTotals

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxPayable` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Valor do imposto a pagar |
| `NetTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento sem impostos |
| `GrossTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento com impostos |
| `Settlement` | `0..1` | Opcional | `(complexType inline)` | — | — |
| `Currency` | `0..1` | Opcional | `Currency` | — | Moeda estrangeira |

### AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `SettlementAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |

### AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Currency
> Moeda estrangeira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### AuditFile/SourceDocuments/Payments/Payment/WithholdingTax
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `WithholdingTaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IRT`, `II`, `IS`, `IVA`, `IPU`, `IAC`, `OU` | Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos |
| `WithholdingTaxDescription` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o normativo legal aplicável ou a percentagem de imposto aplicável. |
| `WithholdingTaxAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve ser indicado o montante retido de imposto. |

### AuditFile/SourceDocuments/PurchaseInvoices
> Documentos comerciais de Fornecedores

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `NumberOfEntries` | `1..1` | Obrigatório | `xs:nonNegativeInteger` | — | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `Invoice` | `0..unbounded` | Opcional | `(complexType inline)` | — | — |

### AuditFile/SourceDocuments/PurchaseInvoices/Invoice

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `InvoiceNo` | `1..1` | Obrigatório | `ns:SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | — |
| `References` | `0..unbounded` | Opcional | `PurchaseReferences` | — | Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. |
| `Hash` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax172Car` | minLength=1; maxLength=172 | Preencher com os 4 valores correspondentes ao Hash constantes no documento impresso. O campo deve ser preenchido com “0” (zero), caso não haja obrigatoriedade de validação. Chave do documento |
| `SourceID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Código do utilizador |
| `Period` | `0..1` | Opcional | `(simpleType inline)` | minInclusive=1; maxInclusive=12 | Período contabilístico |
| `InvoiceDate` | `1..1` | Obrigatório | `SAFdateType` | — | Data do documento de venda |
| `PurchaseType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `FT`, `FR`, `GF`, `FG`, `AC`, `AR`, `AF`, `TV`, `NL`, `NC`, `RC` | Deve ser preenchido com: "FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global; “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “AF” - Factura/recibo (autofacturação); “TV” - Talão de venda; “NL” - Nota de liquidação; "NC" - Nota de crédito; O recibo somente deve ser preenchido por contribuintes enquadrado no regime de caixa “RC” - Recibo; |
| `SupplierID` | `1..1` | Obrigatório | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Identificador único do fornecedor |
| `DocumentTotals` | `1..1` | Obrigatório | `(complexType inline)` | — | — |
| `WithholdingTax` | `0..unbounded` | Opcional | `WithholdingTax` | — | Informação relativa a impostos retidos pelo fornecedor. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. |

### AuditFile/SourceDocuments/PurchaseInvoices/Invoice/References
> Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `Reference` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Referência à factura, através de identificação única da mesma, nos sistemas em que exista. Deve ser utilizada a estrutura de numeração do campo de origem. |
| `InvoiceDate` | `0..1` | Opcional | `SAFdateType` | — | Data do documento de venda |

### AuditFile/SourceDocuments/PurchaseInvoices/Invoice/DocumentTotals

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `TaxPayable` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Valor do imposto a pagar |
| `NetTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento sem impostos |
| `GrossTotal` | `1..1` | Obrigatório | `SAFMonetaryType2DecimalPlaces` | pattern=\d+(\.\d{2}); minInclusive=0.00 | Total do documento com impostos |
| `Currency` | `0..1` | Opcional | `Currency` | — | Moeda estrangeira |

### AuditFile/SourceDocuments/PurchaseInvoices/Invoice/DocumentTotals/Currency
> Moeda estrangeira

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `CurrencyCode` | `1..1` | Obrigatório | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | Obrigatório | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### AuditFile/SourceDocuments/PurchaseInvoices/Invoice/WithholdingTax
> Informação relativa a impostos retidos pelo fornecedor.
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Presença | Tipo efectivo | Restrições | Regra/descrição |
|---|---:|---|---|---|---|
| `WithholdingTaxType` | `1..1` | Obrigatório | `(simpleType inline)` | valores: `IRT`, `II`, `IS`, `IVA`, `IPU`, `IAC`, `OU` | Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos |
| `WithholdingTaxDescription` | `0..1` | Opcional | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o normativo legal aplicável ou a percentagem de imposto aplicável. |
| `WithholdingTaxAmount` | `1..1` | Obrigatório | `SAFmonetaryType` | minInclusive=0.00 | Deve ser indicado o montante retido de imposto. |

## 4. Tipos complexos reutilizáveis declarados

O XSD declara 18 `xs:complexType` nomeados. As estruturas abaixo são as definições reutilizáveis; a secção anterior mostra como são aplicadas nos caminhos concretos.

### `AddressStructure`
> Endereço

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `BuildingNumber` | `0..1` | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido; minLength=2 | País |

### `AddressStructureAO`

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `BuildingNumber` | `0..1` | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | `PostalCodeAO` | minLength=0; maxLength=10 | — |
| `Province` | `0..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | `—` | — | — |

### `Currency`
> Moeda estrangeira

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `CurrencyCode` | `1..1` | `(simpleType inline)` | pattern=AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL; length=3 | Código ISO 4217 de moeda |
| `CurrencyAmount` | `1..1` | `SAFmonetaryType` | minInclusive=0.00 | Valor total em moeda estrangeira |
| `ExchangeRate` | `1..1` | `SAFdecimalType` | minInclusive=0.00 | Taxa de câmbio |

### `CustomsDetails`
> Caracterização aduaneira

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `UNNumber` | `0..unbounded` | `SAFAOUNNumber` | pattern=[0-9]{4}; length=4 | Preencher com o nº ONU para produtos perigosos |

### `CustomsInformation`
> Informação aduaneira

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `ARCNo` | `0..unbounded` | `SAFAOtextTypeMandatoryMax21Car` | minLength=1; maxLength=20 | Código de referência administrativo ou D.U |
| `IECAmount` | `0..1` | `SAFmonetaryType` | minInclusive=0.00 | Montante do imposto especial de consumo da linha |

### `ProductSerialNumber`
> Número de série

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `SerialNumber` | `1..unbounded` | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | — |

### `MovementTax`
> Impostos

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `TaxType` | `1..1` | `SAFTAOMovementTaxType` | valores: `IVA`, `NS` | — |
| `TaxCountryRegion` | `0..1` | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | `SAFTAOMovementTaxCode` | pattern=RED\|INT\|NOR\|ISE\|OUT\|NS\|NA; minLength=1; maxLength=3 | Código da taxa na tabela de impostos. Deve ser preenchido com: “RED” – Taxa reduzida; "INT" - Taxa intermédia; “NOR” – Taxa normal; “ISE” – Isenta; “OUT” – Outros, aplicável para os regimes especiais de IVA. No caso de não sujeição deve ser preenchido com «NS». |
| `TaxPercentage` | `1..1` | `SAFdecimalType` | minInclusive=0.00 | Percentagem da taxa de imposto |

### `OrderReferences`
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchendo com “NC” – Nota de crédito para um documento de ano económico anterior.

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `OriginatingON` | `0..1` | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o tipo, a série e o número do documento que suporta a emissão deste. Se o documento estiver contido no SAF-T AO deve ser utilizada a estrutura de numeração do campo de origem. |
| `OrderDate` | `0..1` | `SAFdateType` | — | — |

### `PaymentMethod`
> Relativo à forma e ao método de pagamento. Havendo mais que um, pode ser repetido quantas vezes forem necessárias.

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `PaymentMechanism` | `0..1` | `(simpleType inline)` | valores: `CC`, `CD`, `CH`, `CI`, `CO`, `CS`, `DE`, `MB`, `NU`, `OU`, `PR`, `TB` | Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc. |
| `PaymentAmount` | `1..1` | `SAFmonetaryType` | minInclusive=0.00 | Montante por meio de pagamento. |
| `PaymentDate` | `1..1` | `SAFdateType` | — | Data do pagamento. |

### `PaymentTax`

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `TaxType` | `1..1` | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | `PaymentTaxCode` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NA\|NS; minLength=1; maxLength=10 | "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. |
| **CHOICE** | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### `References`
> Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. O preenchimento é obrigatório, quando o campo 4.1.4.8. for preenchido com “NC” – Nota de crédito

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `Reference` | `0..1` | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Referência à factura, através de identificação única da mesma, nos sistemas em que exista. Deve ser utilizada a estrutura de numeração do campo de origem. |
| `Reason` | `0..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Motivo |

### `PurchaseReferences`
> Referências a facturas nos documentos rectificativos destas. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `Reference` | `0..1` | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Referência à factura, através de identificação única da mesma, nos sistemas em que exista. Deve ser utilizada a estrutura de numeração do campo de origem. |
| `InvoiceDate` | `0..1` | `SAFdateType` | — | Data do documento de venda |

### `Settlement`
> Acordos ou formas de pagamento. Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `SettlementDiscount` | `0..1` | `SAFAOtextTypeMandatoryMax30Car` | minLength=1; maxLength=30 | Deve ser preenchido com os acordos de descontos a aplicar no futuro sobre o valor presente. |
| `SettlementAmount` | `0..1` | `SAFmonetaryType` | minInclusive=0.00 | Representa o valor acordado para desconto futuro, mas que não concorre para o GrossTotal do documento. |
| `SettlementDate` | `0..1` | `SAFdateType` | — | Data acordada para o pagamento com desconto. |
| `PaymentTerms` | `0..1` | `SAFAOtextTypeMandatoryMax100Car` | minLength=1; maxLength=100 | Descrição dos acordos estabelecidos ou a data limite de pagamento. |

### `ShippingPointStructure`

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `DeliveryID` | `0..unbounded` | `SAFAOtextTypeMandatoryMax255Car` | minLength=1; maxLength=255 | Identificador da entrega |
| `DeliveryDate` | `0..1` | `SAFdateType` | — | Data da entrega |
| `Address` | `0..1` | `AddressStructure` | — | Endereço |

### `SpecialRegimes`
> Regimes especiais

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `SelfBillingIndicator` | `1..1` | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário. |
| `CashVATSchemeIndicator` | `1..1` | `(simpleType inline)` | minInclusive=0; maxInclusive=1 | Indicador de regime de IVA de Caixa |
| `ThirdPartiesBillingIndicator` | `1..1` | `(simpleType inline)` | minInclusive=0; maxInclusive=3 | Indicador de regime de IVA de Caixa Deve ser preenchido com: "0" - Se não cumprir com nenhuma condição; "1" - se o documento for emitido em nome e por conta de terceiros; "2" - se respeitar ao regime de IVA Cativo; "3" - se cumprir com as condições 1 e 2 em simultâneo. |

### `SupplierAddressStructure`

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `BuildingNumber` | `0..1` | `SAFAOtextTypeMandatoryMax15Car` | minLength=1; maxLength=15 | Número da porta |
| `StreetName` | `0..1` | `SAFAOtextTypeMandatoryMax200Car` | minLength=1; maxLength=200 | Nome da rua |
| `AddressDetail` | `1..1` | `SAFAOtextTypeMandatoryMax250Car` | minLength=1; maxLength=250 | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `City` | `1..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Cidade |
| `PostalCode` | `0..1` | `SAFAOtextTypeMandatoryMax20Car` | minLength=1; maxLength=20 | Código Postal |
| `Province` | `0..1` | `SAFAOtextTypeMandatoryMax50Car` | minLength=1; maxLength=50 | Província |
| `Country` | `1..1` | `SupplierCountry` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW; length=2 | — |

### `Tax`
> Impostos

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `TaxType` | `1..1` | `(simpleType inline)` | valores: `IVA`, `IS`, `NS` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `TaxCountryRegion` | `0..1` | `(simpleType inline)` | pattern=AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA; minLength=2; maxLength=6 | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxCode` | `1..1` | `(simpleType inline)` | pattern=RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA; minLength=1; maxLength=10 | Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". |
| **CHOICE** | — | — | — | `TaxPercentage` [1..1] ou `TaxAmount` [1..1] |

### `WithholdingTax`
> Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.

| Campo | Cardinalidade | Tipo | Restrições | Regra/descrição |
|---|---:|---|---|---|
| `WithholdingTaxType` | `1..1` | `(simpleType inline)` | valores: `IRT`, `II`, `IS`, `IVA`, `IPU`, `IAC`, `OU` | Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos |
| `WithholdingTaxDescription` | `0..1` | `SAFAOtextTypeMandatoryMax60Car` | minLength=1; maxLength=60 | Deve ser indicado o normativo legal aplicável ou a percentagem de imposto aplicável. |
| `WithholdingTaxAmount` | `1..1` | `SAFmonetaryType` | minInclusive=0.00 | Deve ser indicado o montante retido de imposto. |

## 5. Tipos simples e restrições formais

Todas as restrições abaixo vêm de `xs:restriction` no XSD.
### `PaymentTaxCode`
> "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA.
- **Base:** `xs:string`
- **pattern:** `RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NA\|NS`
- **minLength:** `1`
- **maxLength:** `10`

### `TaxTableEntryTaxCode`
> Código do imposto. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa Intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". Nos recibos emitidos sem a descriçao de imposto deve usar-se "NA".
- **Base:** `xs:string`
- **pattern:** `RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA`
- **minLength:** `1`
- **maxLength:** `10`

### `SAFdateTimeType`
- **Base:** `xs:dateTime`

### `SAFdateType`
- **Base:** `xs:date`

### `SAFdecimalType`
- **Base:** `xs:decimal`
- **minInclusive:** `0.00`

### `SAFmonetaryType`
- **Base:** `xs:decimal`
- **minInclusive:** `0.00`

### `SAFMonetaryType2DecimalPlaces`
- **Base:** `xs:decimal`
- **pattern:** `\d+(\.\d{2})`
- **minInclusive:** `0.00`

### `PostalCodePT`
- **Base:** `xs:string`
- **pattern:** `([0-9]{4}-[0-9]{3})`

### `PostalCodeAO`
- **Base:** `xs:string`
- **minLength:** `0`
- **maxLength:** `10`

### `SAFAOAccountingPeriod`
- **Base:** `xs:integer`
- **minInclusive:** `1`
- **maxInclusive:** `16`

### `SAFAODateSpan`
- **Base:** `xs:date`
- **minInclusive:** `2000-01-01`
- **maxInclusive:** `9999-12-31`

### `SAFTAODocArchivalNumber`
- **Base:** `xs:string`
- **pattern:** `[^ ]{1,20}`
- **minLength:** `1`
- **maxLength:** `20`

### `SAFAOGLAccountID`
> Código da conta
- **Base:** `xs:string`
- **pattern:** `(([0-9a-zA-Z\-/._+*]*))`
- **minLength:** `1`
- **maxLength:** `30`

### `SAFAOJournalID`
- **Base:** `xs:string`
- **pattern:** `[^ ]{1,30}`
- **minLength:** `1`
- **maxLength:** `30`

### `SAFTAOMovementTaxCode`
> Código da taxa na tabela de impostos. Deve ser preenchido com: “RED” – Taxa reduzida; "INT" - Taxa intermédia; “NOR” – Taxa normal; “ISE” – Isenta; “OUT” – Outros, aplicável para os regimes especiais de IVA. No caso de não sujeição deve ser preenchido com «NS».
- **Base:** `xs:string`
- **pattern:** `RED\|INT\|NOR\|ISE\|OUT\|NS\|NA`
- **minLength:** `1`
- **maxLength:** `3`

### `SAFTAOMovementTaxType`
- **Base:** `xs:string`
- **enumeration:** `IVA`
- **enumeration:** `NS`

### `SAFAOTaxExemptionCode`
> Consultar: https://github.com/assoft-portugal/SAF-T-AO/wiki/Tax-Exemption-Codes
- **Base:** `xs:string`
- **pattern:** `(M[0-9]{2})+`

### `SAFTAOPaymentType`
> Deve ser preenchido com: “RC” – Recibo emitido “AR” – Aviso de cobrança/recibo “RG” – Outros recibos emitidos.
- **Base:** `xs:string`
- **enumeration:** `RC`
- **enumeration:** `RG`
- **enumeration:** `AR`

### `SAFAOTaxExemption`
- **Base:** `xs:string`
- **minLength:** `6`
- **maxLength:** `60`

### `SAFAOAngolaVatNumber`
> Preencher com o NIF Angolano sem espaços e sem qualquer prefixo do país.
- **Base:** `xs:string`
- **minLength:** `10`
- **maxLength:** `15`

### `SAFAOProductID`
> Nome da aplicação que gera o SAF-T(AO). Deve ser indicado o nome comercial do software e da empresa empresa produtora no formato «Nome da aplicação/Nome da empresa produtora do software».
- **Base:** `xs:string`
- **pattern:** `[^/]+/[^/]+`
- **minLength:** `3`
- **maxLength:** `255`

### `SAFTAOSourceBilling`
> P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual
- **Base:** `xs:string`
- **enumeration:** `P`
- **enumeration:** `I`
- **enumeration:** `M`

### `SAFTAOSourcePayment`
> P para documento produzido na aplicacao, I para documento integrado e produzido noutra aplicacao, M para documento proveniente de recuperacao ou de emissao manual
- **Base:** `xs:string`
- **enumeration:** `P`
- **enumeration:** `I`
- **enumeration:** `M`

### `SAFAOtextTypeMandatoryMax3Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `3`

### `SAFAOtextTypeMandatoryMax10Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `10`

### `SAFAOtextTypeMandatoryMax15Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `15`

### `SAFAOtextTypeMandatoryMax20Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `20`

### `SAFAOtextTypeMandatoryMax21Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `20`

### `SAFAOtextTypeMandatoryMax30Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `30`

### `SAFAOtextTypeMandatoryMax35Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `35`

### `SAFAOtextTypeMandatoryMax40Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `40`

### `SAFAOtextTypeMandatoryMax50Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `50`

### `SAFAOtextTypeMandatoryMax60Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `60`

### `SAFAOtextTypeMandatoryMax70Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `70`

### `SAFAOtextTypeMandatoryMax90Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `90`

### `SAFAOtextTypeMandatoryMax100Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `100`

### `SAFAOtextTypeMandatoryMax172Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `172`

### `SAFAOtextTypeMandatoryMax200Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `200`

### `SAFAOtextTypeMandatoryMax250Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `250`

### `SAFAOtextTypeMandatoryMax255Car`
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `255`

### `SAFAOtextTypeMax40Car`
- **Base:** `xs:string`
- **minLength:** `0`
- **maxLength:** `40`

### `SAFAOtextValidationNumber`
> Número da validação. atribuído à entidade produtora do software. Deve ser preenchido com: NNN/AGT/AAAA. Se não aplicável, deve ser preenchido com «0» (zero).
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `70`
- **pattern:** `\d+/AGT/\d{4}\|[0]`

### `SAFAOTransactionID`
> O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID).
- **Base:** `xs:string`
- **pattern:** `[1-9][0-9]{3}-[01][0-9]-[0-3][0-9] [^ ]{1,30} [^ ]{1,20}`
- **minLength:** `1`
- **maxLength:** `70`

### `SAFAOUNNumber`
- **Base:** `xs:string`
- **pattern:** `[0-9]{4}`
- **length:** `4`

### `SupplierCountry`
- **Base:** `xs:string`
- **pattern:** `AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW`
- **length:** `2`

## 6. Elementos globais com tipos anónimos e valores controlados

Campos globais que possuem `simpleType` inline são documentados abaixo com a restrição efectiva.
### `AccountID`
> Código da conta Deve ser indicada a respectiva conta-corrente do cliente no plano de contas da contabilidade, caso esteja definida. Caso contrário deve ser preenchido com a designação "Desconhecido".
- **Base:** `xs:string`
- **pattern:** `(([0-9a-zA-Z\-/._+*]*)\|Desconhecido)`
- **minLength:** `1`
- **maxLength:** `30`

### `AuditFileVersion`
> Versão a utilizar do esquema XML
- **Base:** `xs:string`
- **pattern:** `1.01_01`

### `CashVATSchemeIndicator`
> Indicador de regime de IVA de Caixa
- **Base:** `xs:integer`
- **minInclusive:** `0`
- **maxInclusive:** `1`

### `CompanyID`
> Registo comercial.
- **Base:** `xs:string`
- **minLength:** `1`
- **maxLength:** `50`

### `Country`
> País
- **Base:** `xs:string`
- **pattern:** `AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|Desconhecido`
- **minLength:** `2`

### `CurrencyCode`
> Código ISO 4217 de moeda
- **Base:** `xs:string`
- **pattern:** `AED\|AFN\|ALL\|AMD\|ANG\|AOA\|ARS\|AUD\|AWG\|AZN\|BAM\|BBD\|BDT\|BGN\|BHD\|BIF\|BMD\|BND\|BOB\|BOV\|BRL\|BSD\|BTN\|BWP\|BYN\|BZD\|CAD\|CDF\|CHE\|CHF\|CHW\|CLF\|CLP\|CNY\|COP\|COU\|CRC\|CUC\|CUP\|CVE\|CZK\|DJF\|DKK\|DOP\|DZD\|EGP\|ERN\|ETB\|EUR\|FJD\|FKP\|GBP\|GEL\|GHS\|GIP\|GMD\|GNF\|GTQ\|GYD\|HKD\|HNL\|HRK\|HTG\|HUF\|IDR\|ILS\|INR\|IQD\|IRR\|ISK\|JMD\|JOD\|JPY\|KES\|KGS\|KHR\|KMF\|KPW\|KRW\|KWD\|KYD\|KZT\|LAK\|LBP\|LKR\|LRD\|LSL\|LYD\|MAD\|MDL\|MGA\|MKD\|MMK\|MNT\|MOP\|MRU\|MUR\|MVR\|MWK\|MXN\|MXV\|MYR\|MZN\|NAD\|NGN\|NIO\|NOK\|NPR\|NZD\|OMR\|PAB\|PEN\|PGK\|PHP\|PKR\|PLN\|PYG\|QAR\|RON\|RSD\|RUB\|RWF\|SAR\|SBD\|SCR\|SDG\|SEK\|SGD\|SHP\|SLL\|SOS\|SRD\|SSP\|STN\|SVC\|SYP\|SZL\|THB\|TJS\|TMT\|TND\|TOP\|TRY\|TTD\|TWD\|TZS\|UAH\|UGX\|USD\|USN\|UYI\|UYU\|UYW\|UZS\|VES\|VND\|VUV\|WST\|XAF\|XAG\|XAU\|XBA\|XBB\|XBC\|XBD\|XCD\|XDR\|XOF\|XPD\|XPF\|XPT\|XSU\|XTS\|XUA\|XXX\|YER\|ZAR\|ZMW\|ZWL`
- **length:** `3`

### `DeductibleTaxType`
> Deve ser preenchido com: "MFI" - Meios Fixos e Investimentos "INV" - Existências/Inventário "OBC" - Outros Bens de Consumo "SERV" - Serviços "IMPT" - Importação "SCE" - Serviços Contratados no Estrangeiro
- **Base:** `xs:string`
- **enumeration:** `MFI`
- **enumeration:** `INV`
- **enumeration:** `OBC`
- **enumeration:** `SERV`
- **enumeration:** `IMPT`
- **enumeration:** `SCE`

### `DocumentNumber`
> Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (MovementType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos.
- **Base:** `xs:string`
- **pattern:** `[^ ]+ [^/^ ]+/[0-9]+`
- **minLength:** `1`
- **maxLength:** `60`

### `EACCode`
> Código CAE
- **Base:** `xs:string`
- **pattern:** `(([0-9]*))`
- **length:** `5`

### `FiscalYear`
> Ano fiscal. Utilizar as regras do Código do II, no caso de períodos contabilísticos coincidentes com o ano civíl.
- **Base:** `xs:integer`
- **minInclusive:** `2000`
- **maxInclusive:** `9999`

### `GroupingCategory`
> Categoria do tipo de conta. Deve ser indicado o tipo e a categoria da conta: “GR” – Conta de 1.º grau da contabilidade geral; “GA” – Conta agregadora ou integradora da contabilidade geral; “GM” – Conta de movimento da contabilidade geral; “AR” – Conta de 1.º grau da contabilidade analítica; “AA” – Conta agregadora ou integradora da contabilidade analítica; e “AM” – Conta de movimento da contabilidade analítica.
- **Base:** `xs:string`
- **enumeration:** `GR`
- **enumeration:** `GA`
- **enumeration:** `GM`
- **enumeration:** `AR`
- **enumeration:** `AA`
- **enumeration:** `AM`

### `InvoiceNo`
> Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (InvoiceType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. Exemplos: InvoiceType: FT InvoiceNo: FT S001/1 InvoiceType: NC InvoiceNo: NC S001/1
- **Base:** `xs:string`
- **pattern:** `[^ ]+ [^/^ ]+/[0-9]+`
- **minLength:** `1`
- **maxLength:** `60`

### `InvoiceStatus`
> Deve ser preenchido com: “N” - Normal; “S” - Autofacturação; “A” - Documento anulado; “R” - Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação;
- **Base:** `xs:string`
- **enumeration:** `N`
- **enumeration:** `S`
- **enumeration:** `A`
- **enumeration:** `R`

### `InvoiceType`
> Deve ser preenchido com: “FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “ND” - Nota de débito; “NC” - Nota de crédito “AF” - Factura/recibo (autofacturação) “TV” - Talão de venda Para o sector Segurador quando não deva constar da tabela 4.3. - Documentos de conferência de mercadorias ou de prestação de serviços (WorkingDocuments), pode ainda ser preenchido com: “RP” - Prémio ou recibo de prémio; “RE” - Estorno ou recibo de estorno; “CS” - Imputação a co-seguradoras; “LD” - Imputação a co-seguradora líder; “RA” - Resseguro aceite.
- **Base:** `xs:string`
- **enumeration:** `FT`
- **enumeration:** `FR`
- **enumeration:** `GF`
- **enumeration:** `FG`
- **enumeration:** `AC`
- **enumeration:** `AR`
- **enumeration:** `ND`
- **enumeration:** `NC`
- **enumeration:** `AF`
- **enumeration:** `TV`
- **enumeration:** `RP`
- **enumeration:** `RE`
- **enumeration:** `CS`
- **enumeration:** `LD`
- **enumeration:** `RA`

### `MovementStatus`
> Deve ser preenchido com: “N” – Normal; “T” – Por conta de terceiros; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos comerciais a clientes (SalesInvoices) o correspondente do tipo factura. “R” – Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação.
- **Base:** `xs:string`
- **enumeration:** `N`
- **enumeration:** `T`
- **enumeration:** `A`
- **enumeration:** `F`
- **enumeration:** `R`

### `MovementType`
> Deve ser preenchido com: “GR” – Guia de remessa; “GT” – Guia de transporte (incluir aqui as guias globais); “GA” – Guia de movimentação de activos fixos próprios; “GD” – Guia ou nota de devolução.
- **Base:** `xs:string`
- **enumeration:** `GR`
- **enumeration:** `GT`
- **enumeration:** `GA`
- **enumeration:** `GD`

### `PaymentMechanism`
> Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc.
- **Base:** `xs:string`
- **enumeration:** `CC`
- **enumeration:** `CD`
- **enumeration:** `CH`
- **enumeration:** `CI`
- **enumeration:** `CO`
- **enumeration:** `CS`
- **enumeration:** `DE`
- **enumeration:** `MB`
- **enumeration:** `NU`
- **enumeration:** `OU`
- **enumeration:** `PR`
- **enumeration:** `TB`

### `PaymentRefNo`
> Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (PaymentType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador e a série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos.
- **Base:** `xs:string`
- **pattern:** `[^ ]+ [^/^ ]+/[0-9]+`
- **minLength:** `1`
- **maxLength:** `60`

### `PaymentStatus`
> N para normal, A para Anulado
- **Base:** `xs:string`
- **enumeration:** `N`
- **enumeration:** `A`

### `Period`
> Período contabilístico
- **Base:** `xs:integer`
- **minInclusive:** `1`
- **maxInclusive:** `12`

### `ProductType`
> Deve ser preenchido com: “P” – Produtos; “S” – Serviços; “O” – Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); “E” – Impostos Especiais de Consumo – (ex.:IEC); “I” – Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos na tabela 2.5 – Tabela de impostos (Tax Table) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código “E”.
- **Base:** `xs:string`
- **enumeration:** `P`
- **enumeration:** `S`
- **enumeration:** `O`
- **enumeration:** `E`
- **enumeration:** `I`

### `PurchaseType`
> Deve ser preenchido com: "FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global; “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “AF” - Factura/recibo (autofacturação); “TV” - Talão de venda; “NL” - Nota de liquidação; "NC" - Nota de crédito; O recibo somente deve ser preenchido por contribuintes enquadrado no regime de caixa “RC” - Recibo;
- **Base:** `xs:string`
- **enumeration:** `FT`
- **enumeration:** `FR`
- **enumeration:** `GF`
- **enumeration:** `FG`
- **enumeration:** `AC`
- **enumeration:** `AR`
- **enumeration:** `AF`
- **enumeration:** `TV`
- **enumeration:** `NL`
- **enumeration:** `NC`
- **enumeration:** `RC`

### `SelfBillingIndicator`
> Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário.
- **Base:** `xs:integer`
- **minInclusive:** `0`
- **maxInclusive:** `1`

### `TaxAccountingBasis`
> Deve ser preenchido com o tipo de programa fornecendo os dados aplicáveis (incluindo os documentos de conferência e os recibos emitidos, quando existam): “I” - Contabilidade integrada com a facturação; “C” - Contabilidade; “F” - Facturação; “P” - Facturação parcial; “R” - Recibos; “A” - Aquisição de bens e serviços; ”Q” - Aquisição de bens e serviços integrada com a facturação: “S” - Autofacturação; "E" - Faturação para o Estado. (a) Deve ser indicado este tipo de programa se este emitir só este tipo de documento. Caso contrário, deverá ser utilizado o tipo “C”, “F”
- **Base:** `xs:string`
- **enumeration:** `A`
- **enumeration:** `C`
- **enumeration:** `F`
- **enumeration:** `I`
- **enumeration:** `P`
- **enumeration:** `Q`
- **enumeration:** `R`
- **enumeration:** `S`
- **enumeration:** `E`

### `TaxCode`
> Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS".
- **Base:** `xs:string`
- **pattern:** `RED\|INT\|NOR\|ISE\|OUT\|([0-9.])*\|NS\|NA`
- **minLength:** `1`
- **maxLength:** `10`

### `TaxCountryRegion`
> País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda.
- **Base:** `xs:string`
- **pattern:** `AD\|AE\|AF\|AG\|AI\|AL\|AM\|AO\|AO-CAB\|AQ\|AR\|AS\|AT\|AU\|AW\|AX\|AZ\|BA\|BB\|BD\|BE\|BF\|BG\|BH\|BI\|BJ\|BL\|BM\|BN\|BO\|BQ\|BR\|BS\|BT\|BV\|BW\|BY\|BZ\|CA\|CC\|CD\|CF\|CG\|CH\|CI\|CK\|CL\|CM\|CN\|CO\|CR\|CU\|CV\|CW\|CX\|CY\|CZ\|DE\|DJ\|DK\|DM\|DO\|DZ\|EC\|EE\|EG\|EH\|ER\|ES\|ET\|FI\|FJ\|FK\|FM\|FO\|FR\|GA\|GB\|GD\|GE\|GF\|GG\|GH\|GI\|GL\|GM\|GN\|GP\|GQ\|GR\|GS\|GT\|GU\|GW\|GY\|HK\|HM\|HN\|HR\|HT\|HU\|ID\|IE\|IL\|IM\|IN\|IO\|IQ\|IR\|IS\|IT\|JE\|JM\|JO\|JP\|KE\|KG\|KH\|KI\|KM\|KN\|KP\|KR\|KW\|KY\|KZ\|LA\|LB\|LC\|LI\|LK\|LR\|LS\|LT\|LU\|LV\|LY\|MA\|MC\|MD\|ME\|MF\|MG\|MH\|MK\|ML\|MM\|MN\|MO\|MP\|MQ\|MR\|MS\|MT\|MU\|MV\|MW\|MX\|MY\|MZ\|NA\|NC\|NE\|NF\|NG\|NI\|NL\|NO\|NP\|NR\|NU\|NZ\|OM\|PA\|PE\|PF\|PG\|PH\|PK\|PL\|PM\|PN\|PR\|PS\|PT\|PW\|PY\|QA\|RE\|RO\|RS\|RU\|RW\|SA\|SB\|SC\|SD\|SE\|SG\|SH\|SI\|SJ\|SK\|SL\|SM\|SN\|SO\|SR\|SS\|ST\|SV\|SX\|SY\|SZ\|TC\|TD\|TF\|TG\|TH\|TJ\|TK\|TL\|TM\|TN\|TO\|TR\|TT\|TV\|TW\|TZ\|UA\|UG\|UM\|US\|UY\|UZ\|VA\|VC\|VE\|VG\|VI\|VN\|VU\|WF\|WS\|XK\|YE\|YT\|ZA\|ZM\|ZW\|PT-AC\|PT-MA`
- **minLength:** `2`
- **maxLength:** `6`

### `TaxType`
> Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS.
- **Base:** `xs:string`
- **enumeration:** `IVA`
- **enumeration:** `IS`
- **enumeration:** `NS`

### `ThirdPartiesBillingIndicator`
> Indicador de regime de IVA de Caixa Deve ser preenchido com: "0" - Se não cumprir com nenhuma condição; "1" - se o documento for emitido em nome e por conta de terceiros; "2" - se respeitar ao regime de IVA Cativo; "3" - se cumprir com as condições 1 e 2 em simultâneo.
- **Base:** `xs:integer`
- **minInclusive:** `0`
- **maxInclusive:** `3`

### `TransactionType`
> Deve ser preenchido com: “N” – Normal; “R” – Regularizações do período de tributação; “A” – Apuramento de resultados; “J” – Movimentos de ajustamento.
- **Base:** `xs:string`
- **enumeration:** `N`
- **enumeration:** `R`
- **enumeration:** `A`
- **enumeration:** `J`

### `WithholdingTaxType`
> Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos
- **Base:** `xs:string`
- **enumeration:** `IRT`
- **enumeration:** `II`
- **enumeration:** `IS`
- **enumeration:** `IVA`
- **enumeration:** `IPU`
- **enumeration:** `IAC`
- **enumeration:** `OU`

### `WorkStatus`
> Deve ser preenchido com: “N” – Normal; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos Comerciais a clientes (SalesInvoices) o correspondente do tipo factura.
- **Base:** `xs:string`
- **enumeration:** `N`
- **enumeration:** `A`
- **enumeration:** `F`

### `WorkType`
> Deve ser preenchido com: “CM” – Consultas de mesa; “CC” – Credito de consignação; “GR” – Guia de remessa; “NR” – Nota de remessa; “FO” – Folhas de obra; “NE” – Nota de Encomenda; “OU” – Outros; “OR” – Orçamentos; “PF” – Pró-forma; “DC” – Documentos emitidos que sejam susceptíveis de apresentação ao cliente para conferência de mercadorias ou de prestação de serviços. Para o sector Segurador quando para os tipos de documentos a seguir identificados também deva existir na tabela 4.1 - Documentos comerciais a clientes (SalesInvoices) a correspondente factura ou documento rectificativo de factura, ainda pode ser preenchido com: “RP” – Prémio ou recibo de prémio; “RE” – Estorno ou recibo de estorno; “CS” – Imputação a co-seguradoras; “LD” – Imputação a co-seguradora líder; “RA” – Resseguro aceite; “GC” – Guia de consignação;
- **Base:** `xs:string`
- **enumeration:** `CM`
- **enumeration:** `CC`
- **enumeration:** `GR`
- **enumeration:** `NR`
- **enumeration:** `FO`
- **enumeration:** `NE`
- **enumeration:** `OU`
- **enumeration:** `OR`
- **enumeration:** `PF`
- **enumeration:** `DC`
- **enumeration:** `RP`
- **enumeration:** `RE`
- **enumeration:** `CS`
- **enumeration:** `LD`
- **enumeration:** `RA`
- **enumeration:** `PP`
- **enumeration:** `GC`

## 7. Integridade referencial e unicidade

O XSD define 10 `xs:unique` e 14 `xs:keyref` no `AuditFile`. Essas regras ligam as tabelas e impedem identificadores duplicados.
- **UNIQUE `AccountIDConstraint`** — conjunto `ns:MasterFiles/ns:GeneralLedgerAccounts/ns:Account`; campo `ns:AccountID`.
- **KEYREF `GroupingCodeConstraint`** — referencia `AccountIDConstraint`; conjunto `ns:MasterFiles/ns:GeneralLedgerAccounts/ns:Account`; campo `ns:GroupingCode`.
- **UNIQUE `CustomerIDConstraint`** — conjunto `ns:MasterFiles/ns:Customer`; campo `ns:CustomerID`.
- **UNIQUE `SupplierIDConstraint`** — conjunto `ns:MasterFiles/ns:Supplier`; campo `ns:SupplierID`.
- **UNIQUE `ProductCodeConstraint`** — conjunto `ns:MasterFiles/ns:Product`; campo `ns:ProductCode`.
- **KEYREF `GeneralLedgerEntriesDebitLineAccountIDConstraint`** — referencia `AccountIDConstraint`; conjunto `ns:GeneralLedgerEntries/ns:Journal/ns:Transaction/ns:Lines/ns:DebitLine`; campo `ns:AccountID`.
- **KEYREF `GeneralLedgerEntriesCreditLineAccountIDConstraint`** — referencia `AccountIDConstraint`; conjunto `ns:GeneralLedgerEntries/ns:Journal/ns:Transaction/ns:Lines/ns:CreditLine`; campo `ns:AccountID`.
- **KEYREF `GeneralLedgerEntriesCustomerIDConstraint`** — referencia `CustomerIDConstraint`; conjunto `ns:GeneralLedgerEntries/ns:Journal/ns:Transaction`; campo `ns:CustomerID`.
- **UNIQUE `GeneralLedgerEntriesJournalIdConstraint`** — conjunto `ns:GeneralLedgerEntries/ns:Journal`; campo `ns:JournalID`.
- **KEYREF `GeneralLedgerEntriesSupplierIDConstraint`** — referencia `SupplierIDConstraint`; conjunto `ns:GeneralLedgerEntries/ns:Journal/ns:Transaction`; campo `ns:SupplierID`.
- **UNIQUE `GeneralLedgerEntriesTransactionIdConstraint`** — conjunto `ns:GeneralLedgerEntries/ns:Journal/ns:Transaction`; campo `ns:TransactionID`.
- **UNIQUE `InvoiceNoConstraint`** — conjunto `ns:SourceDocuments/ns:SalesInvoices/ns:Invoice`; campo `ns:InvoiceNo`.
- **KEYREF `InvoiceCustomerIDConstraint`** — referencia `CustomerIDConstraint`; conjunto `ns:SourceDocuments/ns:SalesInvoices/ns:Invoice`; campo `ns:CustomerID`.
- **KEYREF `InvoiceProductCodeConstraint`** — referencia `ProductCodeConstraint`; conjunto `ns:SourceDocuments/ns:SalesInvoices/ns:Invoice/ns:Line`; campo `ns:ProductCode`.
- **UNIQUE `DocumentNumberConstraint`** — conjunto `ns:SourceDocuments/ns:MovementOfGoods/ns:StockMovement`; campo `ns:DocumentNumber`.
- **KEYREF `StockMovementCustomerIDConstraint`** — referencia `CustomerIDConstraint`; conjunto `ns:SourceDocuments/ns:MovementOfGoods/ns:StockMovement`; campo `ns:CustomerID`.
- **KEYREF `StockMovementSupplierIDConstraint`** — referencia `SupplierIDConstraint`; conjunto `ns:SourceDocuments/ns:MovementOfGoods/ns:StockMovement`; campo `ns:SupplierID`.
- **KEYREF `StockMovementProductCodeConstraint`** — referencia `ProductCodeConstraint`; conjunto `ns:SourceDocuments/ns:MovementOfGoods/ns:StockMovement/ns:Line`; campo `ns:ProductCode`.
- **UNIQUE `WorkDocumentDocumentNumberConstraint`** — conjunto `ns:SourceDocuments/ns:WorkingDocuments/ns:WorkDocument`; campo `ns:DocumentNumber`.
- **KEYREF `WorkDocumentDocumentCustomerIDConstraint`** — referencia `CustomerIDConstraint`; conjunto `ns:SourceDocuments/ns:WorkingDocuments/ns:WorkDocument`; campo `ns:CustomerID`.
- **KEYREF `WorkDocumentDocumentProductCodeConstraint`** — referencia `ProductCodeConstraint`; conjunto `ns:SourceDocuments/ns:WorkingDocuments/ns:WorkDocument/ns:Line`; campo `ns:ProductCode`.
- **UNIQUE `PaymentPaymentRefNoConstraint`** — conjunto `ns:SourceDocuments/ns:Payments/ns:Payment`; campo `ns:PaymentRefNo`.
- **KEYREF `PaymentPaymentRefNoCustomerIDConstraint`** — referencia `CustomerIDConstraint`; conjunto `ns:SourceDocuments/ns:Payments/ns:Payment`; campo `ns:CustomerID`.
- **KEYREF `InvoiceSupplierIDConstraint`** — referencia `SupplierIDConstraint`; conjunto `ns:SourceDocuments/ns:PurchaseInvoices/ns:Invoice`; campo `ns:SupplierID`.

### 7.1 Interpretação prática das referências

- Contas: `AccountID` é único; `GroupingCode`, `DebitLine/AccountID` e `CreditLine/AccountID` referenciam contas existentes.
- Clientes: `CustomerID` é único e os documentos contabilísticos/comerciais que o referenciam devem apontar para um cliente existente.
- Fornecedores: `SupplierID` é único e os registos que o referenciam devem apontar para um fornecedor existente.
- Produtos: `ProductCode` é único e as linhas dos documentos de venda, movimentos e documentos de conferência devem referenciar produtos existentes.
- Diários e transacções: `JournalID` e `TransactionID` têm unicidade conforme os selectors declarados no XSD.
- Documentos: `InvoiceNo`, `DocumentNumber` e `PaymentRefNo` têm regras de unicidade nos conjuntos declarados.
- Estas afirmações resumem as `xs:unique`/`xs:keyref`; a regra exacta é a expressão XPath original listada no capítulo anterior.

## 8. Regras de `choice`

O schema contém 9 `xs:choice`. Cada grupo representa uma alternativa estrutural; as alternativas não devem ser tratadas como simultaneamente obrigatórias.
1. **Contexto:** `sequence` — `TaxPercentage` — 1..1 **ou** `TaxAmount` — 1..1
2. **Contexto:** `sequence` — `CustomerID` — 0..1 **ou** `SupplierID` — 0..1
3. **Contexto:** `sequence` — `DebitAmount` — 1..1 **ou** `CreditAmount` — 1..1
4. **Contexto:** `sequence` — `CustomerID` — 1..1 **ou** `SupplierID` — 1..1
5. **Contexto:** `sequence` — `DebitAmount` — 1..1 **ou** `CreditAmount` — 1..1
6. **Contexto:** `sequence` — `DebitAmount` — 1..1 **ou** `CreditAmount` — 1..1
7. **Contexto:** `sequence` — `DebitAmount` — 1..1 **ou** `CreditAmount` — 1..1
8. **Contexto:** `sequence` — `TaxPercentage` — 1..1 **ou** `TaxAmount` — 1..1
9. **Contexto:** `sequence` — `TaxPercentage` — 1..1 **ou** `TaxAmount` — 1..1

## 9. Catálogo consolidado dos elementos globais

Esta tabela reúne os 149 elementos globais para consulta rápida. Quando o elemento utiliza um tipo nomeado, as restrições desse tipo encontram-se no capítulo 5 ou 4.

| Elemento | Tipo | Presença global | Regra/descrição |
|---|---|---|---|
| `AuditFile` | `(complexType inline)` | `1..1` | — |
| `Header` | `(complexType inline)` | `1..1` | — |
| `GeneralLedgerAccounts` | `(complexType inline)` | `1..1` | — |
| `Customer` | `(complexType inline)` | `1..1` | Tabela de clientes |
| `Supplier` | `(complexType inline)` | `1..1` | Tabela de fornecedores |
| `Product` | `(complexType inline)` | `1..1` | Tabela de produtos/serviços |
| `TaxTable` | `(complexType inline)` | `1..1` | Tabela de impostos |
| `TaxTableEntry` | `(complexType inline)` | `1..1` | Registo na tabela de impostos |
| `GeneralLedgerEntries` | `(complexType inline)` | `1..1` | Movimentos contabilísticos Neste elemento registam-se os movimentos contabilísticos correspondentes ao periodo de exportação a que diz respeito o SAF-T (AO), não devendo os movimentos de abertura ser objeto de exportação, na medida em que estes são apenas refletidos ao nível do elemento GeneralLedgerAccounts. |
| `SourceDocuments` | `(complexType inline)` | `1..1` | Documentos comerciais |
| `AccountDescription` | `SAFAOtextTypeMandatoryMax100Car` | `1..1` | Descrição da conta |
| `Address` | `AddressStructure` | `1..1` | Endereço |
| `AddressDetail` | `SAFAOtextTypeMandatoryMax250Car` | `1..1` | Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável. |
| `ARCNo` | `SAFAOtextTypeMandatoryMax21Car` | `1..1` | Código de referência administrativo ou D.U |
| `AGTDocCodeID` | `SAFAOtextTypeMandatoryMax200Car` | `1..1` | — |
| `BillingAddress` | `AddressStructure` | `1..1` | Endereço de faturação Corresponde ao endereço da sede ou do estabelecimento estável em território nacional. Endereço |
| `BuildingNumber` | `SAFAOtextTypeMandatoryMax15Car` | `1..1` | Número da porta |
| `BusinessName` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | Designação social do sujeito passivo. |
| `City` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Cidade |
| `ClosingCreditBalance` | `SAFmonetaryType` | `1..1` | Saldo de encerramento da conta a crédito do plano de contas. O saldo de encerramento a crédito será o do fim do período de tributação ou a data de geração, se anterior. |
| `ClosingDebitBalance` | `SAFmonetaryType` | `1..1` | Saldo de encerramento da conta a débito do plano de contas. O saldo de encerramento a débito será o do fim do período de tributação ou a data de geração, se anterior. |
| `CompanyAddress` | `AddressStructureAO` | `1..1` | Endereço da empresa |
| `CompanyName` | `SAFAOtextTypeMandatoryMax200Car` | `1..1` | Denominação social da empresa ou nome do sujeito passivo. |
| `Contact` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Nome do contacto na empresa |
| `CreditAmount` | `SAFmonetaryType` | `1..1` | Valor da linha, sem impostos, dos documentos a crédito. Este valor é deduzido dos descontos de linha e cabeçalho. |
| `CurrencyAmount` | `SAFmonetaryType` | `1..1` | Valor total em moeda estrangeira |
| `CustomerID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final". |
| `CustomerTaxID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Número de identificação fiscal do cliente Deve ser indicado sem o prefixo do país. O cliente genérico, correspondente ao designado ""Consumidor final"", deve ser identificado com o NIF "999999999". |
| `DateCreated` | `SAFAODateSpan` | `1..1` | Data de criação do ficheiro XML do SAF-T (AO). |
| `DebitAmount` | `SAFmonetaryType` | `1..1` | Valor da linha, sem impostos, dos documentos a débito. Este valor é deduzido dos descontos de linha e cabeçalho. |
| `DeductibleAmount` | `SAFMonetaryType2DecimalPlaces` | `1..1` | — |
| `DeductiblePercentage` | `SAFdecimalType` | `1..1` | — |
| `DeliveryDate` | `SAFdateType` | `1..1` | Data da entrega |
| `DeliveryID` | `SAFAOtextTypeMandatoryMax255Car` | `1..1` | Identificador da entrega |
| `Description` | `SAFAOtextTypeMandatoryMax200Car` | `1..1` | — |
| `DocArchivalNumber` | `SAFTAODocArchivalNumber` | `1..1` | Número de arquivo do documento |
| `Email` | `SAFAOtextTypeMandatoryMax255Car` | `1..1` | Email |
| `EndDate` | `SAFAODateSpan` | `1..1` | Data do fim do período do ficheiro |
| `ExchangeRate` | `SAFdecimalType` | `1..1` | Taxa de câmbio |
| `Fax` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Fax |
| `GLPostingDate` | `SAFdateType` | `1..1` | Data do movimento contabilístico |
| `GrossTotal` | `SAFMonetaryType2DecimalPlaces` | `1..1` | Total do documento com impostos |
| `Hash` | `SAFAOtextTypeMandatoryMax172Car` | `1..1` | Chave do documento |
| `HashControl` | `SAFAOtextTypeMandatoryMax70Car` | `1..1` | O campo deve ser preenchido com “0” (zero), caso o documento seja gerado por um programa não validado. |
| `HeaderComment` | `SAFAOtextTypeMandatoryMax255Car` | `1..1` | Comentários adicionais |
| `IECAmount` | `SAFmonetaryType` | `1..1` | Montante do imposto especial de consumo da linha |
| `InputTax` | `SAFMonetaryType2DecimalPlaces` | `1..1` | — |
| `InvoiceDate` | `SAFdateType` | `1..1` | Data do documento de venda |
| `InvoiceStatusDate` | `SAFdateTimeType` | `1..1` | Data e hora do estado actual do documento |
| `JournalID` | `SAFAOJournalID` | `1..1` | Identificador do diário |
| `LineNumber` | `xs:nonNegativeInteger` | `1..1` | Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original. |
| `LocationID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Localização dos bens no armazém de destino |
| `MovementComments` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | — |
| `MovementDate` | `SAFdateType` | `1..1` | — |
| `MovementEndTime` | `SAFdateTimeType` | `1..1` | Data e hora de fim de transporte |
| `MovementStartTime` | `SAFdateTimeType` | `1..1` | Data e hora de início de transporte |
| `MovementStatusDate` | `SAFdateTimeType` | `1..1` | — |
| `NetTotal` | `SAFMonetaryType2DecimalPlaces` | `1..1` | Total do documento sem impostos |
| `NumberOfEntries` | `xs:nonNegativeInteger` | `1..1` | GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos |
| `NumberOfMovementLines` | `xs:nonNegativeInteger` | `1..1` | — |
| `OpeningCreditBalance` | `SAFmonetaryType` | `1..1` | Saldo de abertura a crédito da conta do plano de contas. O saldo de abertura a crédito será sempre o do início do período de tributação. |
| `OpeningDebitBalance` | `SAFmonetaryType` | `1..1` | Saldo de abertura a débito da conta do plano de contas. O saldo de abertura a débito será sempre o do início do período de tributação. |
| `OrderDate` | `SAFdateType` | `1..1` | — |
| `OriginatingON` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | — |
| `PaymentStatusDate` | `SAFdateTimeType` | `1..1` | — |
| `PostalCode` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Código Postal |
| `ProductCode` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E". |
| `ProductCompanyTaxID` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Identificação fiscal da entidade produtora do software |
| `ProductDescription` | `SAFAOtextTypeMandatoryMax200Car` | `1..1` | Descrição do produto ou serviço |
| `ProductGroup` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Família do produto ou serviço |
| `ProductID` | `SAFAOProductID` | `1..1` | Nome da aplicação Nome da aplicação que gera o SAF-T(AO). Deve ser indicado o nome comercial do software e da empresa empresa produtora no formato «Nome da aplicação/Nome da empresa produtora do software». |
| `ProductNumberCode` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | Código do produto. Deve ser usado o código EAN do produto. Quando este não existir, preencher com o valor do elemento ProductCode. |
| `ProductVersion` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Versão da aplicação |
| `Quantity` | `SAFdecimalType` | `1..1` | Quantidade |
| `Reason` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Motivo |
| `RecordID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Identificador do registo de linha |
| `Reference` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | — |
| `Region` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | — |
| `Province` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Província |
| `SerialNumber` | `SAFAOtextTypeMandatoryMax100Car` | `1..1` | — |
| `SettlementAmount` | `SAFmonetaryType` | `1..1` | Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal |
| `ShipFrom` | `ShippingPointStructure` | `1..1` | Local de carga |
| `ShipFromAddress` | `AddressStructure` | `1..1` | Endereço |
| `ShipTo` | `ShippingPointStructure` | `1..1` | Local de descarga |
| `ShipToAddress` | `AddressStructure` | `1..1` | Endereço de expedição Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias. Endereço |
| `SoftwareValidationNumber` | `ns:SAFAOtextValidationNumber` | `1..1` | Número de validação atribuído ao software Número da validação. atribuído à entidade produtora do software. Deve ser preenchido com: NNN/AGT/AAAA. Se não aplicável, deve ser preenchido com «0» (zero). |
| `SourceDocumentID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Chave única da tabela de movimentos contabilísticos |
| `SourceID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Código do utilizador |
| `StartDate` | `SAFAODateSpan` | `1..1` | Data de início do período do ficheiro |
| `StreetName` | `SAFAOtextTypeMandatoryMax200Car` | `1..1` | Nome da rua |
| `SupplierID` | `SAFAOtextTypeMandatoryMax30Car` | `1..1` | Identificador único do fornecedor |
| `SupplierTaxID` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Número de identificação fiscal do fornecedor. Deve ser indicado sem o prefixo do país. |
| `SystemEntryDate` | `SAFdateTimeType` | `1..1` | Timestamp a que corresponde a data de registo do documento |
| `SystemID` | `SAFAOtextTypeMandatoryMax35Car` | `1..1` | — |
| `TaxAmount` | `SAFmonetaryType` | `1..1` | Montante do imposto |
| `TaxBase` | `SAFmonetaryType` | `1..1` | Valor tributável unitário. Valor tributável unitário que não concorre para o Total do documento sem impostos (NetTotal). Este valor é o que serve de base de cálculo dos impostos da linha. O sinal (debito ou crédito) com que o imposto assim calculado concorre para o TaxPayable, resulta da existência na linha do DebitAmount ou do CreditAmount. |
| `TaxEntity` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Identificação do estabelecimento |
| `TaxExemptionReason` | `SAFAOTaxExemption` | `1..1` | — |
| `TaxExemptionCode` | `SAFAOTaxExemptionCode` | `1..1` | Consultar: https://github.com/assoft-portugal/SAF-T-AO/wiki/Tax-Exemption-Codes |
| `TaxExpirationDate` | `SAFdateType` | `1..1` | Data de fim de vigência |
| `TaxPayable` | `SAFMonetaryType2DecimalPlaces` | `1..1` | Valor do imposto a pagar |
| `TaxPercentage` | `SAFdecimalType` | `1..1` | Percentagem da taxa de imposto |
| `TaxPointDate` | `SAFdateType` | `1..1` | Data de envio da mercadoria ou prestação do serviço. Deve coincidir com a data precisa do envio da mercadoria ou da prestação do serviço, o que por vezes pode não coincidir com a data do documento. |
| `TaxVerificationDate` | `SAFdateType` | `1..1` | — |
| `Telephone` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Telefone |
| `TotalCredit` | `SAFmonetaryType` | `1..1` | Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount. |
| `TotalDebit` | `SAFmonetaryType` | `1..1` | Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount. |
| `TotalQuantityIssued` | `SAFdecimalType` | `1..1` | — |
| `TransactionDate` | `SAFdateType` | `1..1` | Data do documento. Para recibos de pagamento corresponde à data do recibo. |
| `TransactionID` | `SAFAOTransactionID` | `1..1` | Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number). O preenchimento é obrigatório, no caso de se tratar de um sistema integrado de contabilidade e facturação, ainda que o tipo de ficheiro (TaxAccountingBasis) não deva conter as tabelas relativas à contabilidade. Deve ser indicada a chave única da tabela 3. Movimentos contabilísticos (GeneralLedgerEntries) da transacção onde foi lançado este documento, respeitando a regra aí definida para o campo 3.4.3.1 - Chave única do movimento contabilístico (TransactionID). |
| `UnitOfMeasure` | `SAFAOtextTypeMandatoryMax20Car` | `1..1` | Unidade de medida |
| `UnitPrice` | `SAFmonetaryType` | `1..1` | Preço unitário deduzido dos descontos de linha e de cabeçalho, sem incluir impostos. |
| `UNNumber` | `SAFAOUNNumber` | `1..1` | Preencher com o nº ONU para produtos perigosos |
| `WarehouseID` | `SAFAOtextTypeMandatoryMax50Car` | `1..1` | Identificador do armazém de destino |
| `Website` | `SAFAOtextTypeMandatoryMax60Car` | `1..1` | Endereço do sítio Web |
| `WorkDate` | `SAFdateType` | `1..1` | — |
| `WorkStatusDate` | `SAFdateTimeType` | `1..1` | — |
| `AccountID` | `(simpleType inline)` | `1..1` | Código da conta Deve ser indicada a respectiva conta-corrente do cliente no plano de contas da contabilidade, caso esteja definida. Caso contrário deve ser preenchido com a designação "Desconhecido". |
| `AuditFileVersion` | `(simpleType inline)` | `1..1` | Versão a utilizar do esquema XML |
| `CashVATSchemeIndicator` | `(simpleType inline)` | `1..1` | Indicador de regime de IVA de Caixa |
| `CompanyID` | `(simpleType inline)` | `1..1` | Registo comercial. |
| `Country` | `(simpleType inline)` | `1..1` | País |
| `CurrencyCode` | `(simpleType inline)` | `1..1` | Código ISO 4217 de moeda |
| `DeductibleTaxType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: "MFI" - Meios Fixos e Investimentos "INV" - Existências/Inventário "OBC" - Outros Bens de Consumo "SERV" - Serviços "IMPT" - Importação "SCE" - Serviços Contratados no Estrangeiro |
| `DocumentNumber` | `(simpleType inline)` | `1..1` | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (MovementType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. |
| `EACCode` | `(simpleType inline)` | `1..1` | Código CAE |
| `FiscalYear` | `(simpleType inline)` | `1..1` | Ano fiscal. Utilizar as regras do Código do II, no caso de períodos contabilísticos coincidentes com o ano civíl. |
| `GroupingCategory` | `(simpleType inline)` | `1..1` | Categoria do tipo de conta. Deve ser indicado o tipo e a categoria da conta: “GR” – Conta de 1.º grau da contabilidade geral; “GA” – Conta agregadora ou integradora da contabilidade geral; “GM” – Conta de movimento da contabilidade geral; “AR” – Conta de 1.º grau da contabilidade analítica; “AA” – Conta agregadora ou integradora da contabilidade analítica; e “AM” – Conta de movimento da contabilidade analítica. |
| `InvoiceNo` | `(simpleType inline)` | `1..1` | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (InvoiceType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. Exemplos: InvoiceType: FT InvoiceNo: FT S001/1 InvoiceType: NC InvoiceNo: NC S001/1 |
| `InvoiceStatus` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “N” - Normal; “S” - Autofacturação; “A” - Documento anulado; “R” - Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação; |
| `InvoiceType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “ND” - Nota de débito; “NC” - Nota de crédito “AF” - Factura/recibo (autofacturação) “TV” - Talão de venda Para o sector Segurador quando não deva constar da tabela 4.3. - Documentos de conferência de mercadorias ou de prestação de serviços (WorkingDocuments), pode ainda ser preenchido com: “RP” - Prémio ou recibo de prémio; “RE” - Estorno ou recibo de estorno; “CS” - Imputação a co-seguradoras; “LD” - Imputação a co-seguradora líder; “RA” - Resseguro aceite. |
| `MovementStatus` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “N” – Normal; “T” – Por conta de terceiros; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos comerciais a clientes (SalesInvoices) o correspondente do tipo factura. “R” – Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação. |
| `MovementType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “GR” – Guia de remessa; “GT” – Guia de transporte (incluir aqui as guias globais); “GA” – Guia de movimentação de activos fixos próprios; “GD” – Guia ou nota de devolução. |
| `PaymentMechanism` | `(simpleType inline)` | `1..1` | Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc. |
| `PaymentRefNo` | `(simpleType inline)` | `1..1` | Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (PaymentType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador e a série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. |
| `PaymentStatus` | `(simpleType inline)` | `1..1` | N para normal, A para Anulado |
| `Period` | `(simpleType inline)` | `1..1` | Período contabilístico |
| `ProductType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “P” – Produtos; “S” – Serviços; “O” – Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); “E” – Impostos Especiais de Consumo – (ex.:IEC); “I” – Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos na tabela 2.5 – Tabela de impostos (Tax Table) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código “E”. |
| `PurchaseType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: "FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global; “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “AF” - Factura/recibo (autofacturação); “TV” - Talão de venda; “NL” - Nota de liquidação; "NC" - Nota de crédito; O recibo somente deve ser preenchido por contribuintes enquadrado no regime de caixa “RC” - Recibo; |
| `SelfBillingIndicator` | `(simpleType inline)` | `1..1` | Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário. |
| `TaxAccountingBasis` | `(simpleType inline)` | `1..1` | Deve ser preenchido com o tipo de programa fornecendo os dados aplicáveis (incluindo os documentos de conferência e os recibos emitidos, quando existam): “I” - Contabilidade integrada com a facturação; “C” - Contabilidade; “F” - Facturação; “P” - Facturação parcial; “R” - Recibos; “A” - Aquisição de bens e serviços; ”Q” - Aquisição de bens e serviços integrada com a facturação: “S” - Autofacturação; "E" - Faturação para o Estado. (a) Deve ser indicado este tipo de programa se este emitir só este tipo de documento. Caso contrário, deverá ser utilizado o tipo “C”, “F” |
| `TaxCode` | `(simpleType inline)` | `1..1` | Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS". |
| `TaxCountryRegion` | `(simpleType inline)` | `1..1` | País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda. |
| `TaxType` | `(simpleType inline)` | `1..1` | Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS. |
| `ThirdPartiesBillingIndicator` | `(simpleType inline)` | `1..1` | Indicador de regime de IVA de Caixa Deve ser preenchido com: "0" - Se não cumprir com nenhuma condição; "1" - se o documento for emitido em nome e por conta de terceiros; "2" - se respeitar ao regime de IVA Cativo; "3" - se cumprir com as condições 1 e 2 em simultâneo. |
| `TransactionType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “N” – Normal; “R” – Regularizações do período de tributação; “A” – Apuramento de resultados; “J” – Movimentos de ajustamento. |
| `WithholdingTaxType` | `(simpleType inline)` | `1..1` | Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos |
| `WorkStatus` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “N” – Normal; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos Comerciais a clientes (SalesInvoices) o correspondente do tipo factura. |
| `WorkType` | `(simpleType inline)` | `1..1` | Deve ser preenchido com: “CM” – Consultas de mesa; “CC” – Credito de consignação; “GR” – Guia de remessa; “NR” – Nota de remessa; “FO” – Folhas de obra; “NE” – Nota de Encomenda; “OU” – Outros; “OR” – Orçamentos; “PF” – Pró-forma; “DC” – Documentos emitidos que sejam susceptíveis de apresentação ao cliente para conferência de mercadorias ou de prestação de serviços. Para o sector Segurador quando para os tipos de documentos a seguir identificados também deva existir na tabela 4.1 - Documentos comerciais a clientes (SalesInvoices) a correspondente factura ou documento rectificativo de factura, ainda pode ser preenchido com: “RP” – Prémio ou recibo de prémio; “RE” – Estorno ou recibo de estorno; “CS” – Imputação a co-seguradoras; “LD” – Imputação a co-seguradora líder; “RA” – Resseguro aceite; “GC” – Guia de consignação; |

## 10. Regras semânticas documentais relevantes

Esta secção mantém, sem reinterpretar, as instruções textuais que o próprio XSD fornece para campos e estruturas.
### `Customer`
- Tabela de clientes
### `Supplier`
- Tabela de fornecedores
### `Product`
- Tabela de produtos/serviços
### `TaxTable`
- Tabela de impostos
### `TaxTableEntry`
- Registo na tabela de impostos
### `SourceDocuments`
- Documentos comerciais
### `AccountDescription`
- Descrição da conta
### `AddressDetail`
- Endereço detalhado. Deve incluir o nome da rua, número da porta e andar, se aplicável.
### `ARCNo`
- Código de referência administrativo ou D.U
### `BillingAddress`
- Endereço de faturação Corresponde ao endereço da sede ou do estabelecimento estável em território nacional.
### `BuildingNumber`
- Número da porta
### `BusinessName`
- Designação social do sujeito passivo.
### `City`
- Cidade
### `ClosingCreditBalance`
- Saldo de encerramento da conta a crédito do plano de contas. O saldo de encerramento a crédito será o do fim do período de tributação ou a data de geração, se anterior.
### `ClosingDebitBalance`
- Saldo de encerramento da conta a débito do plano de contas. O saldo de encerramento a débito será o do fim do período de tributação ou a data de geração, se anterior.
### `CompanyAddress`
- Endereço da empresa
### `CompanyName`
- Denominação social da empresa ou nome do sujeito passivo.
### `Contact`
- Nome do contacto na empresa
### `CreditAmount`
- Valor da linha, sem impostos, dos documentos a crédito. Este valor é deduzido dos descontos de linha e cabeçalho.
### `CurrencyAmount`
- Valor total em moeda estrangeira
### `CustomerID`
- Identificador único do cliente. Na lista de clientes não pode existir mais do que um registo com o mesmo CustomerID. Para o caso de consumidores finais, deve ser criado um cliente genérico com a designação "Consumidor final".
### `CustomerTaxID`
- Número de identificação fiscal do cliente Deve ser indicado sem o prefixo do país. O cliente genérico, correspondente ao designado ""Consumidor final"", deve ser identificado com o NIF "999999999".
### `DateCreated`
- Data de criação do ficheiro XML do SAF-T (AO).
### `DebitAmount`
- Valor da linha, sem impostos, dos documentos a débito. Este valor é deduzido dos descontos de linha e cabeçalho.
### `DeliveryDate`
- Data da entrega
### `DeliveryID`
- Identificador da entrega
### `DocArchivalNumber`
- Número de arquivo do documento
### `Email`
- Email
### `EndDate`
- Data do fim do período do ficheiro
### `ExchangeRate`
- Taxa de câmbio
### `Fax`
- Fax
### `GLPostingDate`
- Data do movimento contabilístico
### `GrossTotal`
- Total do documento com impostos
### `Hash`
- Chave do documento
### `HashControl`
- O campo deve ser preenchido com “0” (zero), caso o documento seja gerado por um programa não validado.
### `HeaderComment`
- Comentários adicionais
### `IECAmount`
- Montante do imposto especial de consumo da linha
### `InvoiceDate`
- Data do documento de venda
### `InvoiceStatusDate`
- Data e hora do estado actual do documento
### `JournalID`
- Identificador do diário
### `LineNumber`
- Número de linha. As linhas devem ser exportadas pela mesma ordem em que se encontram no documento original.
### `LocationID`
- Localização dos bens no armazém de destino
### `MovementEndTime`
- Data e hora de fim de transporte
### `MovementStartTime`
- Data e hora de início de transporte
### `NetTotal`
- Total do documento sem impostos
### `NumberOfEntries`
- GeneralLedgerEntries: Número de registo de movimentos contabilísticos SalesInvoices, WorkingDocuments, Payments, PurchaseInvoices: Número total de documentos
### `OpeningCreditBalance`
- Saldo de abertura a crédito da conta do plano de contas. O saldo de abertura a crédito será sempre o do início do período de tributação.
### `OpeningDebitBalance`
- Saldo de abertura a débito da conta do plano de contas. O saldo de abertura a débito será sempre o do início do período de tributação.
### `PostalCode`
- Código Postal
### `ProductCode`
- Indicador de produto ou serviço: "P" - Produtos; "S" - Serviços; "O" - Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); "E" - Impostos Especiais de Consumo – (ex.:IEC); "I" - Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos TaxTable) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código "E".
### `ProductCompanyTaxID`
- Identificação fiscal da entidade produtora do software
### `ProductDescription`
- Descrição do produto ou serviço
### `ProductGroup`
- Família do produto ou serviço
### `ProductID`
- Nome da aplicação
### `ProductNumberCode`
- Código do produto. Deve ser usado o código EAN do produto. Quando este não existir, preencher com o valor do elemento ProductCode.
### `ProductVersion`
- Versão da aplicação
### `Quantity`
- Quantidade
### `Reason`
- Motivo
### `RecordID`
- Identificador do registo de linha
### `Province`
- Província
### `SettlementAmount`
- Para os elementos presentes em: (1) /AuditFile/SourceDocuments/SalesInvoices/Invoice/Line/SettlementAmount (2) /AuditFile/SourceDocuments/MovementOfGoods/StockMovement/Line/SettlementAmount (3) /AuditFile/SourceDocuments/WorkingDocuments/WorkDocument/Line/SettlementAmount (4) /AuditFile/SourceDocuments/Payments/Payment/Line/SettlementAmount Deve refletir todos os descontos concedidos que afetem o total do documento - GrossTotal (descontos de linha e descontos glogais). Para os elementos presentes em: (5) /AuditFile/SourceDocuments/SalesInvoices/Invoice/DocumentTotals/Settlement/SettlementAmount (6) /AuditFile/SourceDocuments/Payments/Payment/DocumentTotals/Settlement/SettlementAmount Representa o valor acordado para desconto futuro, que afeta o total do documento - GrossTotal
### `ShipFrom`
- Local de carga
### `ShipTo`
- Local de descarga
### `ShipToAddress`
- Endereço de expedição Existindo a necessidade de efectuar mais do que uma referência, esta estrutura poderá ser gerada tantas vezes quantas as necessárias.
### `SoftwareValidationNumber`
- Número de validação atribuído ao software
### `SourceDocumentID`
- Chave única da tabela de movimentos contabilísticos
### `SourceID`
- Código do utilizador
### `StartDate`
- Data de início do período do ficheiro
### `StreetName`
- Nome da rua
### `SupplierID`
- Identificador único do fornecedor
### `SupplierTaxID`
- Número de identificação fiscal do fornecedor. Deve ser indicado sem o prefixo do país.
### `SystemEntryDate`
- Timestamp a que corresponde a data de registo do documento
### `TaxAmount`
- Montante do imposto
### `TaxBase`
- Valor tributável unitário. Valor tributável unitário que não concorre para o Total do documento sem impostos (NetTotal). Este valor é o que serve de base de cálculo dos impostos da linha. O sinal (debito ou crédito) com que o imposto assim calculado concorre para o TaxPayable, resulta da existência na linha do DebitAmount ou do CreditAmount.
### `TaxEntity`
- Identificação do estabelecimento
### `TaxExpirationDate`
- Data de fim de vigência
### `TaxPayable`
- Valor do imposto a pagar
### `TaxPercentage`
- Percentagem da taxa de imposto
### `TaxPointDate`
- Data de envio da mercadoria ou prestação do serviço. Deve coincidir com a data precisa do envio da mercadoria ou da prestação do serviço, o que por vezes pode não coincidir com a data do documento.
### `Telephone`
- Telefone
### `TotalCredit`
- Deve conter a soma dos elementos CreditAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos CreditAmount.
### `TotalDebit`
- Deve conter a soma dos elementos DebitAmount dos documentos cujo os elementos InvoiceStatus, WorkStatus ou PaymentStatus seja igual a N. Em GeneralLedgerEntries deve conter a soma de todos os elementos DebitAmount.
### `TransactionDate`
- Data do documento. Para recibos de pagamento corresponde à data do recibo.
### `TransactionID`
- Chave única do movimento contabilístico Deve ser construída de forma a ser única e a corresponder ao número de documento contabilístico, que é utilizado para detectar o documento físico no arquivo, pelo que, deve resultar de uma relação, separada por espaços, entre os seguintes valores: data do documento, identificador do diário e número de arquivo do documento (Transaction Date, Journal ID e Doc Archival Number).
### `UnitOfMeasure`
- Unidade de medida
### `UnitPrice`
- Preço unitário deduzido dos descontos de linha e de cabeçalho, sem incluir impostos.
### `UNNumber`
- Preencher com o nº ONU para produtos perigosos
### `WarehouseID`
- Identificador do armazém de destino
### `Website`
- Endereço do sítio Web
### `AccountID`
- Código da conta Deve ser indicada a respectiva conta-corrente do cliente no plano de contas da contabilidade, caso esteja definida. Caso contrário deve ser preenchido com a designação "Desconhecido".
### `AuditFileVersion`
- Versão a utilizar do esquema XML
### `CashVATSchemeIndicator`
- Indicador de regime de IVA de Caixa
### `CompanyID`
- Registo comercial.
### `Country`
- País
### `CurrencyCode`
- Código ISO 4217 de moeda
### `DeductibleTaxType`
- Deve ser preenchido com: "MFI" - Meios Fixos e Investimentos "INV" - Existências/Inventário "OBC" - Outros Bens de Consumo "SERV" - Serviços "IMPT" - Importação "SCE" - Serviços Contratados no Estrangeiro
### `DocumentNumber`
- Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (MovementType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos.
### `EACCode`
- Código CAE
### `FiscalYear`
- Ano fiscal. Utilizar as regras do Código do II, no caso de períodos contabilísticos coincidentes com o ano civíl.
### `GroupingCategory`
- Categoria do tipo de conta. Deve ser indicado o tipo e a categoria da conta: “GR” – Conta de 1.º grau da contabilidade geral; “GA” – Conta agregadora ou integradora da contabilidade geral; “GM” – Conta de movimento da contabilidade geral; “AR” – Conta de 1.º grau da contabilidade analítica; “AA” – Conta agregadora ou integradora da contabilidade analítica; e “AM” – Conta de movimento da contabilidade analítica.
### `InvoiceNo`
- Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (InvoiceType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador da série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos. Exemplos: InvoiceType: FT InvoiceNo: FT S001/1 InvoiceType: NC InvoiceNo: NC S001/1
### `InvoiceStatus`
- Deve ser preenchido com: “N” - Normal; “S” - Autofacturação; “A” - Documento anulado; “R” - Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação;
### `InvoiceType`
- Deve ser preenchido com: “FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “ND” - Nota de débito; “NC” - Nota de crédito “AF” - Factura/recibo (autofacturação) “TV” - Talão de venda Para o sector Segurador quando não deva constar da tabela 4.3. - Documentos de conferência de mercadorias ou de prestação de serviços (WorkingDocuments), pode ainda ser preenchido com: “RP” - Prémio ou recibo de prémio; “RE” - Estorno ou recibo de estorno; “CS” - Imputação a co-seguradoras; “LD” - Imputação a co-seguradora líder; “RA” - Resseguro aceite.
### `MovementStatus`
- Deve ser preenchido com: “N” – Normal; “T” – Por conta de terceiros; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos comerciais a clientes (SalesInvoices) o correspondente do tipo factura. “R” – Documento de resumo doutros documentos criados noutras aplicações e gerado nesta aplicação.
### `MovementType`
- Deve ser preenchido com: “GR” – Guia de remessa; “GT” – Guia de transporte (incluir aqui as guias globais); “GA” – Guia de movimentação de activos fixos próprios; “GD” – Guia ou nota de devolução.
### `PaymentMechanism`
- Meio de pagamento: “CC” – Cartão crédito; “CD” – Cartão débito; “CH” – Cheque bancário; “CI” – Crédito documentário internacional; “CO” – Cheque ou cartão oferta; “CS” – Compensação de saldos em conta corrente; “DE” – Dinheiro electrónico, por exemplo residente em cartões de fidelidade ou de pontos; “MB” – Referências de pagamento para Multicaixa; “NU” – Numerário; “OU” – Outros meios aqui não assinalados; “PR” – Permuta de bens; “TB“ – Transferência bancária ou débito directo autorizado; etc.
### `PaymentRefNo`
- Esta identificação é composta sequencialmente pelos seguintes elementos: Tipo de documento (PaymentType), um espaço, o código interno do tipo de documento atribuído pela aplicação o identificador e a série do documento, uma barra (/) e o número sequencial desse documento dentro dessa série. Não podem existir registos com a mesma identificação. Não pode ser utilizado o mesmo código interno de tipo de documento em diferentes tipos de documentos.
### `PaymentStatus`
- N para normal, A para Anulado
### `Period`
- Período contabilístico
### `ProductType`
- Deve ser preenchido com: “P” – Produtos; “S” – Serviços; “O” – Outros (Ex: portes debitados, adiantamentos recebidos ou alienação de activos); “E” – Impostos Especiais de Consumo – (ex.:IEC); “I” – Impostos, taxas e encargos parafiscais – excepto IVA e IS que deverão ser reflectidos na tabela 2.5 – Tabela de impostos (Tax Table) e Impostos Especiais de Consumo, que deverão ser preenchidos com o código “E”.
### `PurchaseType`
- Deve ser preenchido com: "FT” - Factura; “FR” - Factura/recibo; “GF” - Factura genérica; “FG” - Factura global; “AC” - Aviso de cobrança; “AR” - Aviso de cobrança/recibo; “AF” - Factura/recibo (autofacturação); “TV” - Talão de venda; “NL” - Nota de liquidação; "NC" - Nota de crédito; O recibo somente deve ser preenchido por contribuintes enquadrado no regime de caixa “RC” - Recibo;
### `SelfBillingIndicator`
- Indicador de autofacturação Deve ser preenchido com «1» se respeitar autofaturação, com «0» (zero) no caso contrário.
### `TaxAccountingBasis`
- Deve ser preenchido com o tipo de programa fornecendo os dados aplicáveis (incluindo os documentos de conferência e os recibos emitidos, quando existam): “I” - Contabilidade integrada com a facturação; “C” - Contabilidade; “F” - Facturação; “P” - Facturação parcial; “R” - Recibos; “A” - Aquisição de bens e serviços; ”Q” - Aquisição de bens e serviços integrada com a facturação: “S” - Autofacturação; "E" - Faturação para o Estado. (a) Deve ser indicado este tipo de programa se este emitir só este tipo de documento. Caso contrário, deverá ser utilizado o tipo “C”, “F”
### `TaxCode`
- Código da taxa. Caso o valor de TaxType seja "IVA" deve preencher-se com: "NOR" - Taxa normal; "RED" - Taxa reduzida; "INT" - Taxa intermédia; "ISE" - Isenta; "OUT" - Outros, aplicável para os regimes especiais de IVA. Caso o valor de TaxType seja "IS" deve preencher-se com "ISE" - Isenta. No caso de não sujeição deve preencher-se com "NS".
### `TaxCountryRegion`
- País do imposto No caso da província de Cabinda: "AO-CAB" - Espaço Fiscal da Região de Cabinda.
### `TaxType`
- Código do tipo de imposto. Deve ser preenchido com: "IVA" - Imposto sobre o valor acrescentado; "IS" - Imposto de selo; "NS" - Não sujeito a IVA ou IS.
### `ThirdPartiesBillingIndicator`
- Indicador de regime de IVA de Caixa Deve ser preenchido com: "0" - Se não cumprir com nenhuma condição; "1" - se o documento for emitido em nome e por conta de terceiros; "2" - se respeitar ao regime de IVA Cativo; "3" - se cumprir com as condições 1 e 2 em simultâneo.
### `TransactionType`
- Deve ser preenchido com: “N” – Normal; “R” – Regularizações do período de tributação; “A” – Apuramento de resultados; “J” – Movimentos de ajustamento.
### `WithholdingTaxType`
- Neste campo deve ser indicado o tipo de imposto retido, preenchendo- o com: “IRT” - Imposto sobre o rendimento de trabalho; “II” - Imposto industrial; “IS” - Imposto do selo; “IVA” - IVA Cativo; “IPU” - Imposto predial urbano. "IAC" - Imposto sobre a aplicação de capitais "OU" - Outros tipos de impostos retidos
### `WorkStatus`
- Deve ser preenchido com: “N” – Normal; “A” – Documento anulado; “F” – Documento facturado, ainda que parcialmente, quando para este documento também existe na tabela 4.1. – Documentos Comerciais a clientes (SalesInvoices) o correspondente do tipo factura.
### `WorkType`
- Deve ser preenchido com: “CM” – Consultas de mesa; “CC” – Credito de consignação; “GR” – Guia de remessa; “NR” – Nota de remessa; “FO” – Folhas de obra; “NE” – Nota de Encomenda; “OU” – Outros; “OR” – Orçamentos; “PF” – Pró-forma; “DC” – Documentos emitidos que sejam susceptíveis de apresentação ao cliente para conferência de mercadorias ou de prestação de serviços. Para o sector Segurador quando para os tipos de documentos a seguir identificados também deva existir na tabela 4.1 - Documentos comerciais a clientes (SalesInvoices) a correspondente factura ou documento rectificativo de factura, ainda pode ser preenchido com: “RP” – Prémio ou recibo de prémio; “RE” – Estorno ou recibo de estorno; “CS” – Imputação a co-seguradoras; “LD” – Imputação a co-seguradora líder; “RA” – Resseguro aceite; “GC” – Guia de consignação;
## 11. Regras gerais de validação derivadas da gramática XSD

- **Ordem:** elementos em `xs:sequence` devem aparecer na ordem declarada.
- **Obrigatoriedade:** `minOccurs=1` torna o elemento obrigatório; `minOccurs=0` torna-o opcional.
- **Repetição:** `maxOccurs=unbounded` permite quantidade arbitrária de ocorrências.
- **Decimais não negativos:** `SAFdecimalType` possui `minInclusive=0.00`.
- **Valores monetários não negativos:** `SAFmonetaryType` e `SAFMonetaryType2DecimalPlaces` possuem `minInclusive=0.00`.
- **Duas casas decimais:** `SAFMonetaryType2DecimalPlaces` usa o padrão `\d+(\.\d{2})`.
- **Datas de período:** `SAFAODateSpan` limita os valores a `2000-01-01` até `9999-12-31`.
- **NIF angolano:** `SAFAOAngolaVatNumber` exige entre 10 e 15 caracteres.
- **Número ONU:** `SAFAOUNNumber` exige exactamente 4 algarismos.
- **País do fornecedor:** `SupplierCountry` restringe o valor aos códigos ISO 3166-1 alpha-2 enumerados no XSD.
- **O schema não declara atributos de negócio:** a estrutura usa elementos XML; não existem `xs:attribute` no schema.

## 12. Regras condicionais que devem ser tratadas pela aplicação

Algumas regras importantes são fornecidas como `xs:documentation` e não como uma restrição formal de XSD 1.0. Para um exportador SAF-T, estas regras devem ser implementadas na lógica de negócio além da validação estrutural.

- Quando o documento é uma **Nota de crédito (`NC`)**, determinadas estruturas de referência devem ser preenchidas conforme indicado nas documentações de `References`, `OrderReferences` e estruturas relacionadas.
- Quando a **taxa de IVA é 0**, a documentação do XSD determina o preenchimento de `TaxExemptionReason` e `TaxExemptionCode` em conjunto quando aplicável.
- `TransactionID` tem formato específico e é obrigatório em cenário de sistema integrado de contabilidade e facturação, conforme a documentação do tipo `SAFAOTransactionID`.
- Para consumidores finais, a documentação especifica cliente genérico com designação **Consumidor final** e NIF **999999999**.
- `CurrencyCode` é documentado para preenchimento com **AOA**.
- `SoftwareValidationNumber` admite o número de validação no formato definido ou `0` quando não aplicável.

## 13. Inventário técnico

- Elementos globais: **149**
- Tipos simples nomeados: **45**
- Tipos complexos nomeados: **18**
- `xs:sequence`: **66**
- `xs:choice`: **9**
- `xs:unique`: **10**
- `xs:keyref`: **14**
- `xs:attribute`: **0**

## 14. Nota de fidelidade

Este ficheiro não tenta corrigir ou completar o XSD com normas externas. As regras são separadas em: (1) restrições formais do schema; (2) relações de integridade declaradas no `AuditFile`; e (3) instruções semânticas presentes nas `xs:documentation`. Quando uma regra é apenas documental, ela não é apresentada como se fosse uma restrição formal do XSD.