# Notificação de Validação de Software — AGT
## Ref: 0000497/01180000/AGT/2026 · 27 de Março de 2026

**Entidade emissora**: Direcção de Cobrança, Reembolso e Restituição — AGT  
**Destinatário**: SOTARQ Software — Comércio & Serviços (SU), Lda · NIF 5002764377  
**Email de submissão**: `produtos.dfe.dcrr.agt@minfin.gov.ao`  
**Prazo de resposta**: 15 dias úteis a partir de 27/03/2026  
**Base legal**: Art. 6.º do Regime Jurídico de Submissão Eletrónica (Decreto Presidencial 312/18, 21/Dez) · Art. 9.º, n.º 2 (suspensão do prazo de certificação até conclusão dos testes)  
**Consequência de incumprimento**: Indeferimento automático da solicitação (Art. 6.º do mesmo diploma)

---

## Regras Gerais para Todos os Documentos

- Formato: **PDF**
- Emitidos em **dois meses diferentes**
- Devem conter o campo **Período Contabilístico (Period)**:
  - Campo `4.1.4.5.` (faturas), ou
  - Campo `4.2.3.5.` (notas de crédito/débito), ou
  - Campo `4.3.4.5` (outros documentos) — conforme tipologia da aplicação
- Cada PDF deve conter:
  - Os **4 primeiros caracteres do hash** do documento (extracto da Chave do Documento)
  - Um hífen (`-`)
  - A mensagem: **"Processado por programa válido n31.1/AGT20"**
- O campo **UniPrice** (preço unitário) deve:
  - Ser **sem imposto**
  - Reflectir os descontos de linha e descontos globais (cabeçalho)
  - Conter as casas decimais necessárias para minimizar diferenças de arredondamento (**recomendado: 4 casas decimais**)
- Para cada documento enviado, deve ser indicado a qual ponto do pedido corresponde
- Para documentos **não produzidos pela aplicação**, indicar: `"Não aplicável"`

---

## Documentos Exigidos (17 pontos)

### 1. Factura com NIF do cliente
- Factura emitida para um cliente que **forneceu o seu NIF**.
- Campo obrigatório: `CustomerTaxID` preenchido.

---

### 2. Factura anulada
- Uma factura **anulada** com o respectivo PDF após anulação.
- O PDF deve indicar **visivelmente** que o documento está anulado.
- Obrigações de sistema:
  - Registo da anulação na **base de dados** da aplicação.
  - Registo no **campo respectivo do SAF-T** (campo `DocumentStatus` com valor `A`).

---

### 3. Documento pró-forma (conferência de bens/serviços)
- Um documento susceptível de ser entregue ao cliente para **conferência de transmissão de bens ou de prestação de serviços**.
- Tipologia: **Fatura Pró-Forma**.

---

### 4. Factura a partir da pró-forma + Nota de Crédito
**4a — Factura com referência à pró-forma:**
- Factura emitida **com base no documento do ponto 3**.
- Deve gerar o elemento SAF-T: **`OrderReferences`** (referência ao documento de origem).

**4b — Nota de Crédito com referência à factura:**
- Nota de Crédito emitida **com base na factura do ponto 4a**.
- Deve gerar o elemento SAF-T: **`OrderReference`** (referência ao documento de origem).
- Se não houver factura emitida a partir de pró-forma, criar a NC sobre outro documento qualquer.

---

### 5. Factura com 2 linhas — IVA e Isenção
**Linha 1:**
- Produto tributado a **14% ou 5% de IVA**.

**Linha 2:**
- Produto **isento de IVA**.
- Deve gerar o elemento SAF-T: **`TaxExemptionReason`** com um dos seguintes códigos obrigatórios:

| Código | Motivo de Isenção |
|--------|-------------------|
| **M00** | Regime Transitório |
| **M02** | Transmissão de bens e serviço não sujeita |
| **M04** | IVA — Regime de não Sujeição |
| **M11** | Isento Artigo 12.º b) do CIVA |
| **M12** | Isento Artigo 12.º c) do CIVA |
| **M13** | Isento Artigo 12.º d) do CIVA |
| **M14** | Isento Artigo 12.º e) do CIVA |
| **M15** | Isento Artigo 12.º f) do CIVA |
| **M17** | Isento Artigo 12.º h) do CIVA |
| **M18** | Isento Artigo 12.º i) do CIVA |
| **M19** | Isento Artigo 12.º j) do CIVA |
| **M20** | Isento Artigo 12.º k) do CIVA |
| **M30** | Isento Artigo 15.º 1 a) do CIVA |
| **M31** | Isento Artigo 15.º 1 b) do CIVA |
| **M32** | Isento Artigo 15.º 1 c) do CIVA |
| **M33** | Isento Artigo 15.º 1 d) do CIVA |
| **M34** | Isento Artigo 15.º 1 e) do CIVA |
| **M35** | Isento Artigo 15.º 1 f) do CIVA |
| **M36** | Isento Artigo 15.º 1 g) do CIVA |
| **M37** | Isento Artigo 15.º 1 h) do CIVA |
| **M38** | Isento Artigo 15.º 1 i) do CIVA |

> **Nota**: A tabela da notificação AGT difere ligeiramente da lista do Decreto Executivo 683/25.
> Os códigos M10, M16, M21–M24 e os grupos M80–M93, S01–S03, I01–I16 constam do Decreto
> mas **não figuram** nesta notificação. Para o ficheiro SAF-T de homologação usar **apenas os
> códigos da tabela acima**. Os restantes ficam activos no sistema para uso operacional futuro.

---

### 6. Documento com desconto global (SettlementAmount)
**Linha única com:**
- Transmissão de bens ou prestação de serviços
- Quantidade: **100**
- Preço unitário: **0,55** (UniPrice sem imposto, 4 casas decimais → `0.5500`)
- Taxa de IVA: **8,8%**

**Desconto global ao documento:**
- Deve gerar o elemento SAF-T: **`SettlementAmount`** no cabeçalho do documento.

---

### 7. Documento em moeda estrangeira
- Um documento emitido em **moeda estrangeira** (ex.: USD ou EUR).
- Deve incluir os campos SAF-T de moeda: `Currency` → `CurrencyCode`, `CurrencyAmount`, `ExchangeRate`.

---

### 8. Documento — cliente identificado sem NIF, total < 50 AOA, hora ≤ 10h
- Cliente identificado (nome/dados) mas **sem NIF**.
- Campo `GrossTotal` (Total Bruto) inferior a **50,00 AOA**.
- `SystemEntryDate` deve estar registado **até às 10:00 da manhã** (hora do sistema ≤ 10h00).

---

### 9. Documento — outro cliente identificado sem NIF
- Outro cliente identificado mas **sem NIF** (distinto do cliente do ponto 8).

---

### 10. Duas guias de remessa
- **Dois** documentos de transporte / guias de remessa (tipologia DT/GT).
- Ambos devem gerar os campos de transporte do SAF-T.

---

### 11. Orçamento ou factura pró-forma (adicional)
- Um segundo orçamento ou factura pró-forma (independente do ponto 3, se aplicável).
- Indicar `"Não aplicável"` se a aplicação não suportar orçamentos em separado das pró-formas.

---

### 12. Factura genérica e factura de auto-facturação
- Uma **factura genérica** (se aplicável ao modelo de negócio).
- Uma **factura de auto-facturação** (emitida pelo comprador em nome do fornecedor).
- Indicar `"Não aplicável"` para cada uma que não se aplique.

---

### 13. Factura global
- Uma **factura global** (documento que agrega múltiplas operações/períodos num único documento).

---

### 14. Outros tipos de documento
- Qualquer outro tipo de documento emitido pela aplicação que **não tenha sido coberto** pelos pontos 1–13.
- Exemplo: nota de débito, talão de venda, recibo, etc.

---

### 15. Índice de correspondência
- Para cada ponto enviado, indicar explicitamente **qual o documento de exemplo** que responde a esse ponto (ex.: "Ponto 1 — FT A/0001.pdf").

---

### 16. Documentos não aplicáveis
- Para cada ponto em que a aplicação **não produz** o tipo de documento exigido, escrever: `"Não aplicável"`.

---

### 17. Ficheiro SAF-T XML único
- Um **único ficheiro XML de SAF-T** por aplicação.
- Estrutura conforme **Decreto Presidencial 312/18**.
- Deve integrar **todos os documentos exemplo** dos pontos anteriores.
- Os campos relativos à **Chave do Controlo (HashControl)** devem estar devidamente preenchidos:
  - Campo `4.1.4.4.` (faturas)
  - Campo `4.2.3.4.` (notas)
  - Campo `4.3.4.4.` (outros)
- O bloco `Header` deve identificar correctamente a aplicação.
- O ficheiro deve passar a validação do schema XSD SAF-T AO 1.01_01.

---

## Implicações para o VistoGest Pro / Checklist de Implementação

> Os itens abaixo derivam directamente dos requisitos acima e identificam o que ainda pode
> faltar ou precisar de validação no sistema antes da submissão à AGT.

- [ ] **Ponto 2** — `documentStatus = "A"` gravado no SAF-T ao anular uma factura; PDF com marca visual de anulado.
- [ ] **Ponto 4** — `OrderReferences` gerado na factura quando existe pró-forma de origem; `OrderReference` gerado na NC quando existe factura de origem.
- [ ] **Ponto 5** — `TaxExemptionReason` presente na linha de IVA isento com um dos 21 códigos da tabela acima.
- [ ] **Ponto 6** — `SettlementAmount` gerado no cabeçalho do documento quando existe desconto global; `UniPrice` com 4 casas decimais.
- [ ] **Ponto 7** — Campos `Currency` (`CurrencyCode`, `CurrencyAmount`, `ExchangeRate`) no SAF-T para documentos em moeda estrangeira.
- [ ] **Ponto 8** — `SystemEntryDate` com hora ≤ 10h00 registado correctamente no SAF-T; `GrossTotal < 50.00`.
- [ ] **Ponto 10** — Dois documentos de transporte (GT/DT) no SAF-T.
- [ ] **Ponto 17** — Ficheiro SAF-T XML com `HashControl` preenchido em todos os documentos, validado contra o XSD.
- [ ] **Geral** — Todos os PDFs contêm os 4 caracteres do hash + hífen + "Processado por programa válido n31.1/AGT20".
- [ ] **Geral** — Documentos emitidos em dois meses distintos (exigência de período contabilístico diferente).
