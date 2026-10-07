# Portal do Parceiro — Facturação Electrónica AGT

> **Fonte:** documentação publicada pela Administração Geral Tributária (AGT) no Portal do Parceiro — Facturação Electrónica.
>
> **Documento consolidado:** visão geral da API, autenticação, JWS, gestão de chaves, serviços, regras de negócio, estados, erros, processamento assíncrono e QR Code.
>
> **Fonte principal:** https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/index.html
>
> **Nota editorial:** este arquivo reorganiza e normaliza a matéria publicada para uso como documentação técnica de implementação. As regras de negócio abaixo são apresentadas como regras da publicação; não foram substituídas por interpretações externas. Onde a própria publicação apresenta exemplos ou endereços que merecem conferência, eles permanecem identificados como tal.

---

# 1. Introdução

A API de Facturação Electrónica define as interfaces, regras e padrões técnicos necessários para a comunicação automática de documentos fiscais entre os softwares de facturação certificados e a Administração Tributária.

O objectivo é garantir:

- integridade dos documentos;
- autenticidade dos emissores;
- rastreabilidade das operações;
- assinatura digital através de JWS;
- controlo das séries de numeração;
- validação dos documentos;
- sincronização entre o software do contribuinte e a base fiscal da AGT.

A arquitectura utiliza processamento **assíncrono**, baseado em filas. A submissão é aceite inicialmente a nível estrutural e recebe um `requestID`; a validação fiscal completa ocorre posteriormente.

O acompanhamento pode ser feito por **polling**, através do serviço de consulta do estado. A documentação menciona também um mecanismo de **callback**, mas indica que esse mecanismo estará disponível em versões futuras.

## 1.1 Propósito da API

A API pretende permitir que os softwares de facturação comuniquem os documentos fiscais à Administração Tributária em tempo real ou quase real, garantindo:

1. integridade e autenticidade por assinatura digital JWS;
2. validação automática e retorno do estado do documento;
3. sincronização entre os sistemas internos do contribuinte e a base fiscal;
4. auditoria e rastreabilidade através de `requestID`, timestamps e histórico de processamento.

## 1.2 Arquitectura geral

O fluxo de processamento é:

```text
Software do contribuinte
        |
        | JSON + autenticação + assinaturas
        v
API de Facturação Electrónica
        |
        | validação estrutural
        v
Fila de processamento
        |
        | validações fiscais e de negócio
        v
Estado final da submissão
        |
        +--> Polling /obterEstado
        |
        +--> Callback (versões futuras)
```

### Processamento assíncrono

1. O contribuinte envia o documento em JSON.
2. A API devolve imediatamente um `requestID`, confirmando a recepção.
3. O pedido entra na fila de processamento.
4. O processamento fiscal ocorre de forma diferida.
5. O contribuinte consulta posteriormente o estado ou, quando disponível, recebe callback.

O modelo foi concebido para suportar:

- volumes elevados;
- redução de latência no front-end;
- isolamento de falhas;
- desacoplamento entre submissão e processamento.

### Mecanismos

| Mecanismo | Funcionamento |
|---|---|
| Polling | O cliente consulta posteriormente a decisão final. |
| Callback | A API efectua POST para um endpoint do contribuinte quando o documento for validado. A documentação indica que este mecanismo ficará disponível em versões futuras. |

---

# 2. Autenticação e Autorização

A API utiliza **Basic Authentication** para validar e autorizar o acesso dos produtores de software.

O acesso é feito através de um par de credenciais:

- `username`;
- `password`.

As credenciais são emitidas pela entidade gestora da Facturação Electrónica e devem ser enviadas em todas as chamadas aos serviços protegidos.

## 2.1 Solicitação das credenciais

O produtor de software deve enviar um pedido formal para:

`produtores.dfe.dcrr.agt@minfin.gov.ao`

O pedido deve conter:

- Nome da Empresa;
- NIF da Empresa.

## 2.2 Basic Auth

O cabeçalho HTTP utiliza:

```http
Authorization: Basic <Base64(username:password)>
```

Exemplo publicado:

```text
Username: cliente123
Password: s3nh@F0rte!

Texto antes de Base64:
cliente123:s3nh@F0rte!

Base64:
Y2xpZW50ZTEyMzpzM25oQEYwcnRlIQ==
```

## 2.3 Exemplo de header HTTP

```http
POST /sigt/fe/v1/registarFactura HTTP/1.1
Host: https://sifphml.minfin.gov.ao
Authorization: Basic Y2xpZW50ZTEyMzpzM25oQEYwcnRlIQ==
Content-Type: application/json
Accept: application/json
Content-Length: 524
```

## 2.4 Exemplo cURL

```bash
curl -X POST "https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura" \
  -u cliente123:"s3nh@F0rte!" \
  -H "Accept: application/json"
```

O `curl` executa automaticamente a codificação Base64 quando é utilizado o parâmetro `-u`.

## 2.5 Exemplo JavaScript / Fetch API

```javascript
const auth = btoa("cliente123:s3nh@F0rte!");

fetch("https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura", {
  method: "POST",
  headers: {
    "Authorization": `Basic ${auth}`,
    "Content-Type": "application/json",
    "Accept": "application/json"
  }
})
  .then(res => res.json())
  .then(console.log);
```

## 2.6 Exemplo C#

```csharp
var client = new HttpClient();

var byteArray = Encoding.ASCII.GetBytes("cliente123:s3nh@F0rte!");

client.DefaultRequestHeaders.Authorization =
    new AuthenticationHeaderValue(
        "Basic",
        Convert.ToBase64String(byteArray)
    );

var response = await client.GetAsync(
    "https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura"
);

var content = await response.Content.ReadAsStringAsync();
```

---

# 3. Assinaturas Digitais JWS

A API utiliza **JSON Web Signature (JWS)** para assinatura digital de três categorias de informação:

- `jwsSoftwareSignature` — informação do software;
- `jwsDocumentSignature` — documento fiscal;
- `jwsSignature` — requisição enviada ao serviço.

As assinaturas destinam-se a garantir:

- **Integridade:** os dados assinados não foram alterados;
- **Autenticidade:** o emissor corresponde à identidade esperada;
- **Não-repúdio:** a autoria da assinatura não pode ser negada pelo emissor.

A chave privada utilizada depende da assinatura:

| Assinatura | Chave privada |
|---|---|
| `jwsSoftwareSignature` | Chave do produtor de software |
| `jwsDocumentSignature` | Chave do contribuinte/emissor |
| `jwsSignature` | Chave do contribuinte/emissor |

## 3.1 Algoritmo

Todas as assinaturas JWS utilizam:

**RS256 — RSA + SHA-256**

Requisitos publicados:

- RSA mínimo de 2048 bits;
- recomendação de 4096 bits;
- SHA-256 como algoritmo de hash.

Cabeçalho JWS de referência:

```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

## 3.2 JSON canónico

A documentação recomenda transformar o objecto a assinar em JSON canónico antes da assinatura.

Regras apresentadas:

1. sem quebras de linha;
2. sem espaços ou indentação;
3. utilização de aspas duplas;
4. números sem formatação adicional.

Exemplo:

```json
{"productId":"Nome","productVersion":"1.0","softwareValidationNumber":"123"}
```

## 3.3 Processo de assinatura

Fluxo geral:

1. Criar o objecto JSON com os campos exigidos.
2. Usar a forma canónica recomendada.
3. Construir o JWS Compact Serialization.
4. Codificar header e payload com Base64URL.
5. Formar `base64url(header).base64url(payload)`.
6. Assinar utilizando RSA-SHA256 e a chave privada.
7. Formar o JWS final:

```text
header.payload.signature
```

## 3.4 `jwsSoftwareSignature`

O objecto de assinatura contém:

```json
{
  "productId": "",
  "productVersion": "",
  "softwareValidationNumber": ""
}
```

A documentação determina que o payload seja o **objecto completo**, e não uma concatenação individual dos campos.

## 3.5 `jwsDocumentSignature`

A assinatura do documento utiliza os principais elementos fiscais:

```json
{
  "documentNo": "...",
  "taxRegistrationNumber": "...",
  "documentType": "...",
  "documentDate": "...",
  "customerTaxID": "...",
  "customerCountry": "...",
  "companyName": "...",
  "documentTotals": {
    "taxPayable": 70,
    "netTotal": 500,
    "grossTotal": 570
  }
}
```

É o **objecto completo** que é assinado.

## 3.6 `jwsSignature`

A assinatura da requisição utiliza um objecto dependente do serviço.

Exemplo:

```json
{
  "taxRegistrationNumber": "5001234567",
  "requestID": "REQ-000001"
}
```

A documentação salienta que os campos do payload de `jwsSignature` **podem variar segundo a requisição**.

## 3.7 Exemplos de implementação

### Node.js

```javascript
const fs = require("fs");
const jwt = require("jsonwebtoken");

const privateKey = fs.readFileSync("private.pem", "utf8");

const payload = {
  productId: "ClinicaHub",
  productVersion: "1.0.0",
  softwareValidationNumber: "123456789"
};

const token = jwt.sign(payload, privateKey, {
  algorithm: "RS256"
});

console.log(token);
```

### Java

```java
import java.nio.file.*;
import java.util.*;
import io.jsonwebtoken.*;

String key = Files.readString(Path.of("private.pem"));
PrivateKey privateKey = Keys.privateKeyFromPem(key);

Map<String, Object> payload = Map.of(
    "productId", "ClinicaHub",
    "productVersion", "1.0.0",
    "softwareValidationNumber", "123456789"
);

String jws = Jwts.builder()
    .setClaims(payload)
    .signWith(privateKey, SignatureAlgorithm.RS256)
    .compact();

System.out.println(jws);
```

### C# (.NET)

```csharp
using System.IdentityModel.Tokens.Jwt;
using Microsoft.IdentityModel.Tokens;
using System.Security.Cryptography;

var payload = new Dictionary<string, object>
{
    { "productId", "ClinicaHub" },
    { "productVersion", "1.0.0" },
    { "softwareValidationNumber", "123456789" }
};

var privateKey = RSA.Create();
privateKey.ImportFromPem(File.ReadAllText("private.pem"));

var credentials = new SigningCredentials(
    new RsaSecurityKey(privateKey),
    SecurityAlgorithms.RsaSha256
);

var token = new JwtSecurityToken(
    claims: payload.Select(kv =>
        new Claim(kv.Key, kv.Value.ToString())),
    signingCredentials: credentials
);

var jwt = new JwtSecurityTokenHandler().WriteToken(token);
Console.WriteLine(jwt);
```

### Go

```go
package main

import (
    "fmt"
    "os"
    jwt "github.com/golang-jwt/jwt/v5"
)

func main() {
    keyData, _ := os.ReadFile("private.pem")
    privateKey, _ := jwt.ParseRSAPrivateKeyFromPEM(keyData)

    payload := jwt.MapClaims{
        "productId": "ClinicaHub",
        "productVersion": "1.0.0",
        "softwareValidationNumber": "123456789",
    }

    token := jwt.NewWithClaims(jwt.SigningMethodRS256, payload)
    signed, _ := token.SignedString(privateKey)

    fmt.Println(signed)
}
```

### Python

```python
import jwt

with open("private.pem", "r") as f:
    private_key = f.read()

payload = {
    "productId": "ClinicaHub",
    "productVersion": "1.0.0",
    "softwareValidationNumber": "123456789"
}

token = jwt.encode(payload, private_key, algorithm="RS256")
print(token)
```

## 3.8 Erros comuns de JWS

A documentação destaca quatro erros:

| Prática incorrecta | Regra indicada |
|---|---|
| Concatenar campos para assinar | Assinar o objecto JSON completo |
| Usar RSA inferior a 2048 bits | Utilizar no mínimo 2048 bits; 4096 bits é recomendado |
| Assinar com chave pública | A assinatura é feita com a chave privada |
| Utilizar Base64 normal | Utilizar Base64URL, sem padding `=` |

---

# 4. Solicitar Criação de Série

Serviço destinado a solicitar a criação de séries de numeração de Facturas Electrónicas.

A resposta indica o sucesso ou insucesso do pedido e, em caso de sucesso, devolve o intervalo de documentos autorizado.

## 4.1 Endpoints

### Homologação

```text
POST https://sifphml.minfin.gov.ao/sigt/fe/ws/v1/registarFactura
```

> **Observação da publicação:** este caminho aparece na página de “Solicitar Criação de Série” como endereço de homologação. Deve ser conferido no ambiente de homologação antes da integração definitiva, porque o endpoint de produção publicado para esta operação é diferente.

### Produção

```text
POST https://sifp.minfin.gov.ao/sigt/fe/v1/solicitarSerie
```

## 4.2 Payload

```json
{
  "schemaVersion": "2.0",
  "submissionUUID": "a1b2c3d4-e5f6-7890-g1h2-i238j234k5122",
  "taxRegistrationNumber": "5001636863",
  "submissionTimeStamp": "2025-09-02T14:30:00Z",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  },
  "seriesYear": "2025",
  "documentType": "LD",
  "establishmentNumber": "10",
  "jwsSignature": "string",
  "seriesContingencyIndicator": "N"
}
```

`establishmentNumber` identifica a agência/estabelecimento a partir do qual o contribuinte emissor realiza a emissão fiscal.

Os estabelecimentos devem estar previamente cadastrados no Portal do Contribuinte.

No sandbox ou quando o contribuinte possui uma única localização, a documentação indica que pode ser utilizado o valor `SEDE`.

## 4.3 Payload utilizado na assinatura da solicitação

```json
{
  "taxRegistrationNumber": "...",
  "seriesYear": "...",
  "documentType": "...",
  "establishmentNumber": "...",
  "seriesContingencyIndicator": "..."
}
```

## 4.4 Resposta

```json
{
  "resultCode": 1,
  "errorList": [],
  "seriesFEResult": {
    "seriesCode": "LD6325S2042N",
    "authorizedQuantity": "999999999999",
    "firstDocumentNo": "1",
    "lastDocumentNo": "999999999999"
  }
}
```

## 4.5 Parâmetros de entrada

| Campo | Tipo | Restrições | Obrigatório | Regra |
|---|---|---|---|---|
| `schemaVersion` | string | — | Sim | Versão do schema, exemplo `2.0`. |
| `submissionUUID` | string | UUID standard | Sim | Identificador único da submissão. |
| `taxRegistrationNumber` | string | max. 15 | Sim | NIF do contribuinte. |
| `submissionTimeStamp` | string | ISO 8601 | Sim | Data/hora da submissão. |
| `softwareInfo` | object | — | Sim | Informação do software. |
| `jwsSignature` | string | Base64URL | Sim | Assinatura da solicitação. |
| `seriesYear` | integer | — | Sim | Ano associado à série. |
| `documentType` | string | 2 caracteres | Sim | Tipo de documento fiscal. |
| `establishmentNumber` | string | 1–200 | Sim | Estabelecimento emissor. |
| `seriesContingencyIndicator` | string | max. 1 | Sim | `N` normal ou `C` contingência. |

### UUID

O `submissionUUID` deve seguir o formato standard:

```text
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
```

Onde:

- `x` é dígito hexadecimal;
- `M` identifica a versão do UUID;
- `N` identifica o variant.

Exemplo:

```text
550e8400-e29b-41d4-a716-446655440000
```

O identificador deve ser único para cada submissão do contribuinte emissor.

### `seriesYear`

Regra publicada:

- de 1 de Janeiro a 15 de Dezembro: podem ser criadas séries apenas para o ano de sistema;
- após 15 de Dezembro: pode ser criada série para o ano de sistema e para o ano imediatamente seguinte.

### Tipos de documento

| Código | Significado |
|---|---|
| `FA` | Factura de Adiantamento |
| `FT` | Factura |
| `FR` | Factura/Recibo |
| `FG` | Factura Global |
| `GF` | Factura Genérica |
| `AC` | Aviso de Cobrança |
| `AR` | Aviso de Cobrança/Recibo |
| `TV` | Talão de Venda |
| `RC` | Recibo em numerário (cash) |
| `RG` | Recibo Geral |
| `RE` | Estorno ou Recibo de Estorno |
| `ND` | Nota de Débito |
| `NC` | Nota de Crédito |
| `AF` | Factura/Recibo de Autofacturação |
| `RP` | Prémio ou Recibo de Prémio |
| `RA` | Resseguro Aceite |
| `CS` | Imputação a Co-seguradoras |
| `LD` | Imputação a Co-seguradora Líder |

### Indicador de contingência

- `N` — série do regime normal;
- `C` — série destinada à emissão em contingência.

## 4.6 `softwareInfo`

```json
{
  "softwareInfoDetail": {
    "productId": "Meu ERP CERTO",
    "productVersion": "1.0.1",
    "softwareValidationNumber": "C_134"
  },
  "jwsSoftwareSignature": "<JWS>"
}
```

Campos:

- `productId` — nome do software;
- `productVersion` — versão do software;
- `softwareValidationNumber` — número de certificação;
- `jwsSoftwareSignature` — assinatura digital do software.

A publicação indica para `jwsSoftwareSignature` comprimento de 256 caracteres neste serviço, embora também refira que, de forma geral, o tamanho depende da chave utilizada. Esta particularidade deve ser preservada como regra da página do serviço e confrontada com o contrato técnico em vigor no ambiente de integração.

## 4.7 Resultado da série

| Campo | Tipo | Regra |
|---|---|---|
| `seriesCode` | string | 3–60 caracteres |
| `authorizedQuantity` | integer | Quantidade autorizada |
| `firstDocumentNo` | string | max. 60 |
| `lastDocumentNo` | string | max. 60 |

## 4.8 Erros de negócio da criação/extensão de séries

| Regra | Código | Descrição |
|---|---|---|
| FE-RNG-010 | E08 | `jwsSoftwareSignature` não está de acordo com a informação transmitida. |
| FE-RNG-011 | E39 | Dados da assinatura do software divergem do processo de certificação. |
| FE-RNG-032 | E40 | Dados de `jwsSignature` não correspondem à chamada. |
| FE-RNG-049 | E30 | Contribuinte indicado não possui actividade registada no sistema da AGT. |
| FE-RNG-050 | E06 | Contribuinte indicado não aderiu à Facturação Electrónica. |
| FE-RNG-051 | E31 | Código de série já está em utilização para o contribuinte. |
| FE-RNG-053 | E32 | Código de série mal construído; deve conter o ano de emissão com 2 ou 4 dígitos. |
| FE-RNG-055 | E33 | Ano da série não coincide com o ano de sistema nas solicitações anteriores a 15 de Dezembro. |
| FE-RNG-056 | E34 | Série indicada é inexistente para o contribuinte. |
| FE-RNG-057 | E35 | Série indicada corresponde a documentos não electrónicos. |
| FE-RNG-058 | E36 | Software que gera a factura não coincide com o software que gerou a série. |
| FE-RNG-059 | E37 | Tipo de documento não coincide com o tipo destinado à série. |
| FE-RNG-060 | E38 | Ano da factura não coincide com o ano associado à série. |
| FE-RNG-080 | E48 | Estabelecimento desconhecido e não registado nos dados de adesão. |
| FE-RNG-081 | E49 | Série foi originalmente criada para outro estabelecimento. |

---

# 5. Listar Séries

Serviço para obter as séries de numeração registadas em nome do contribuinte.

## 5.1 Endpoints

```text
Homologação:
POST https://sifphml.minfin.gov.ao/sigt/fe/v1/listarSeries

Produção:
POST https://sifp.minfin.gov.ao/sigt/fe/v1/listarSeries
```

## 5.2 Exemplo de pedido

```json
{
  "schemaVersion": "2.0",
  "taxRegistrationNumber": "5001636863",
  "submissionTimeStamp": "2025-10-28T18:51:10.178Z",
  "seriesCode": "LD6325S1N",
  "seriesYear": "2025",
  "seriesStatus": "A",
  "documentType": "LD",
  "establishmentNumber": 10,
  "jwsSignature": "string",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  }
}
```

### Payload de assinatura

```json
{
  "taxRegistrationNumber": "..."
}
```

> A publicação apresenta esta forma resumida para a assinatura do serviço. Deve ser seguida juntamente com a versão técnica efectivamente disponibilizada para o endpoint em uso.

## 5.3 Resposta

```json
{
  "resultCode": "1",
  "seriesResultCount": "0",
  "seriresInfo": []
}
```

> O exemplo publicado contém `seriresInfo` (com a grafia apresentada na publicação), enquanto a estrutura documentada posteriormente utiliza `seriesInfo`. Esta diferença deve ser tratada como uma inconsistência documental a confirmar antes da implementação.

## 5.4 Parâmetros

| Campo | Tipo | Restrições | Obrigatório | Descrição |
|---|---|---|---|---|
| `schemaVersion` | string | — | Sim | Versão do schema. |
| `taxRegistrationNumber` | string | max. 15 | Sim | NIF do contribuinte. |
| `submissionTimeStamp` | string | ISO 8601 | Sim | Timestamp da submissão. |
| `softwareInfo` | object | — | Sim | Dados do software. |
| `jwsSignature` | string | Base64URL | Sim | Assinatura da solicitação. |
| `seriesCode` | string | 3–60 | Não | Código da série. |
| `seriesYear` | integer | — | Não | Ano da série. |
| `documentType` | string | 2 caracteres | Não | Tipo de documento. |
| `establishmentNumber` | string | 1–200 | Sim | Estabelecimento. |
| `seriesStatus` | string | 2 caracteres | Não | Estado da série. |

### Formato de `seriesCode`

Deve:

- possuir entre 3 e 60 caracteres;
- conter o ano de emissão com 2 ou 4 dígitos;
- utilizar caracteres alfanuméricos;
- em contingência, conter o indicador correspondente (`25C` ou `2025C`, por exemplo).

### Estados de série

| Código | Estado |
|---|---|
| `A` | Série aberta |
| `U` | Série em utilização |
| `F` | Série fechada |

A publicação especifica que uma série pode ser considerada fechada após o fim do ano de emissão; para séries de contingência, também após terminar o respectivo período de emissão.

## 5.5 Resultado da pesquisa de séries

```text
seriesListResult
├── seriesResultCount
└── seriesInfo[]
    ├── seriesCode
    ├── seriesYear
    ├── documentType
    ├── seriesStatus
    ├── seriesCreationDate
    ├── firstDocumentApproved
    ├── lastDocumentApproved
    ├── firstDocumentCreated
    ├── lastDocumentCreated
    ├── invoicingMethod
    └── seriesContingencyIndicator
```

### `seriesInfo`

| Campo | Tipo | Regra |
|---|---|---|
| `seriesCode` | string | 3–60 |
| `seriesYear` | integer | Ano da emissão |
| `documentType` | string | 2 caracteres |
| `seriesStatus` | string | 2 caracteres |
| `seriesCreationDate` | string | date |
| `firstDocumentApproved` | string | Primeiro número autorizado |
| `lastDocumentApproved` | string | Último número autorizado |
| `firstDocumentCreated` | string | Primeiro documento efectivamente criado; opcional |
| `lastDocumentCreated` | string | Último documento criado; opcional |
| `invoicingMethod` | string | 2–4 caracteres |
| `seriesContingencyIndicator` | string | 1 caractere |

### Métodos de facturação

| Código | Significado |
|---|---|
| `FEPC` | Facturação electrónica com emissão no Portal do Contribuinte |
| `FESF` | Facturação electrónica com emissão via Software de Facturação |
| `SF` | Facturação não electrónica com emissão via Software de Facturação |

### Indicador de contingência

- `N` — regime normal;
- `C` — série criada para contingência.

## 5.6 Respostas HTTP

| HTTP | Resultado |
|---|---|
| `200` | Objecto `seriesListResult` |
| `422` | `errorEntry`: E94 — NIF diferente |
| `429` | `errorEntry`: E98 — demasiadas solicitações repetidas |
| `400` | `errorEntry`: E96 — solicitação mal efectuada / erro de estrutura |

---

# 6. Registar Factura

Serviço que recebe pedidos de registo de facturas electrónicas.

A resposta imediata não representa a validação fiscal final: devolve um **`requestID`** que permite acompanhar o processamento posterior.

## 6.1 Endpoints

```text
Homologação:
POST https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura

Produção:
POST https://sifp.minfin.gov.ao/sigt/fe/v1/registarFactura
```

## 6.2 Característica principal

O serviço realiza inicialmente uma validação preliminar da estrutura recebida. Se o pedido for aceite estruturalmente, é gerado um `requestID` e a validação completa ocorre de forma diferida, de acordo com a capacidade e programação dos processamentos batch.

## 6.3 Payload de referência

```json
{
  "schemaVersion": "2.0",
  "submissionUUID": "a1b2c3d4-e5f6-7890-g1h2-i23822j2232-3784",
  "taxRegistrationNumber": "5001636863",
  "submissionTimeStamp": "2025-11-04T14:30:00Z",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  },
  "numberOfEntries": 1,
  "documents": [
    {
      "documentNo": "FT FT6325S2C/10006",
      "documentStatus": "N",
      "jwsDocumentSignature": "<JWS>",
      "documentDate": "2025-11-04",
      "documentType": "FT",
      "eacCode": "12345",
      "systemEntryDate": "2025-11-04T11:15:30Z",
      "customerTaxID": "PT987654321",
      "customerCountry": "PT",
      "companyName": "Cliente Exemplo Lda",
      "lines": [
        {
          "lineNumber": 1,
          "productCode": "PROD001",
          "productDescription": "Produto Exemplo 1",
          "quantity": 2,
          "unitOfMeasure": "UN",
          "unitPrice": 250,
          "unitPriceBase": 250,
          "debitAmount": 0,
          "creditAmount": 500,
          "taxes": [
            {
              "taxType": "IVA",
              "taxCountryRegion": "AO",
              "taxCode": "NOR",
              "taxPercentage": 14,
              "taxContribution": 70
            }
          ],
          "settlementAmount": 0
        }
      ],
      "documentTotals": {
        "taxPayable": 70,
        "netTotal": 500,
        "grossTotal": 570
      },
      "withholdingTaxList": [
        {
          "withholdingTaxType": "IRT",
          "withholdingTaxDescription": "Retenção na fonte",
          "withholdingTaxAmount": 16.5
        }
      ]
    }
  ]
}
```

## 6.4 Assinatura do documento

A publicação apresenta como payload de `jwsDocumentSignature`:

```json
{
  "documentNo": "...",
  "taxRegistrationNumber": "...",
  "documentType": "...",
  "documentDate": "...",
  "customerTaxID": "...",
  "customerCountry": "...",
  "companyName": "...",
  "documentTotals": {
    "taxPayable": 70,
    "netTotal": 500,
    "grossTotal": 570
  }
}
```

## 6.5 Resposta

Exemplo:

```json
{
  "requestID": "202500000010689",
  "errorList": []
}
```

O `requestID` identifica a submissão a acompanhar posteriormente.

## 6.6 Parâmetros de nível superior

| Campo | Tipo | Obrigatório | Regra |
|---|---|---|---|
| `schemaVersion` | string | Sim | Versão do schema, exemplo `2.0`. |
| `submissionUUID` | string | Sim | UUID único por submissão. |
| `taxRegistrationNumber` | string | Sim | Max. 15 caracteres. |
| `submissionTimeStamp` | string | Sim | ISO 8601. |
| `softwareInfo` | object | Sim | Dados do software e assinatura. |
| `numberOfEntries` | integer | Sim | Número de documentos na chamada. |
| `documents` | array | Sim | Lista de facturas. Máximo previsto: 30 documentos. |

## 6.7 `softwareInfo`

```json
{
  "softwareInfoDetail": {
    "productId": "Meu ERP CERTO",
    "productVersion": "1.0.1",
    "softwareValidationNumber": "C_134",
    "signatureVersion": 1
  },
  "jwsSoftwareSignature": "<JWS>"
}
```

### Campos

| Campo | Regra |
|---|---|
| `productId` | Nome do software. |
| `productVersion` | Versão do software. |
| `softwareValidationNumber` | Número de certificação. |
| `signatureVersion` | Número da assinatura/chave activa utilizada. |
| `jwsSoftwareSignature` | Assinatura do conteúdo total de `softwareInfoDetail`. |

A documentação explica que o produtor pode ter mais de uma assinatura activa para facilitar a transição entre chaves. As chaves públicas necessárias são transmitidas no processo de registo do software e geridas pelo produtor.

## 6.8 Objecto `document`

### Identificação

| Campo | Tipo | Regra |
|---|---|---|
| `documentNo` | string | 8–60 |
| `documentStatus` | string | 1 caractere: `N` ou `C` |
| `rejectedDocumentNo` | string | 8–60, obrigatório para `documentStatus = C` |
| `jwsDocumentSignature` | string | mínimo 256 / conforme chave e publicação |
| `documentDate` | string | date |
| `documentType` | string | 2 caracteres |
| `eacCode` | string | 5 caracteres, opcional |
| `systemEntryDate` | string | date-time |
| `customerCountry` | string | 2 caracteres |
| `customerTaxID` | string | 1–50 |
| `companyName` | string | 1–200 |
| `lines` | array | condicional |
| `paymentReceipt` | object | condicional |
| `documentTotals` | object | obrigatório |
| `withholdingTaxList` | array | opcional |

### `documentStatus`

- `N` — documento normal;
- `C` — documento gerado para correcção de documento anteriormente rejeitado pela AGT.

Quando `documentStatus = C`, `rejectedDocumentNo` é obrigatório e deve identificar o documento rejeitado anteriormente.

### `documentNo`

A documentação descreve o identificador como o código interno do documento, um espaço, a série, o carácter `/` e o número sequencial.

Exemplo:

```text
FT FT6325S2C/10006
```

### `customerCountry`

Utiliza ISO 3166-1 alpha-2.

Para compradores domésticos:

```text
AO
```

### `customerTaxID`

Para clientes domésticos com `customerCountry = AO`, deve ser utilizado o NIF angolano.

Para documentos domésticos sem identificação do comprador, a documentação permite:

```text
999999999
```

### Linhas vs. recibos

`lines` não é preenchido para:

- `AR` — Aviso de Cobrança/Recibo;
- `RC` — Recibo Emitido;
- `RG` — Outros Recibos Emitidos.

Para os restantes tipos de documento, `lines` é obrigatoriamente preenchido.

`paymentReceipt` funciona de forma inversa:

- obrigatório para `AR`, `RC` e `RG`;
- não preenchido para os demais tipos.

---

# 7. Linhas de Facturação

Cada linha é representada por um objecto dentro de `documents[].lines[]`.

## 7.1 Estrutura

```text
documents[]
└── lines[]
    └── line
        ├── lineNumber
        ├── operationType
        ├── operationDate
        ├── productCode
        ├── productDescription
        ├── quantity
        ├── unitOfMeasure
        ├── unitPriceBase
        ├── unitPrice
        ├── referenceInfo
        ├── debitAmount
        ├── creditAmount
        ├── taxes[]
        └── settlementAmount
```

## 7.2 Regras dos campos

| Campo | Tipo / restrição | Regra |
|---|---|---|
| `lineNumber` | integer >= 1 | Deve começar em 1 e incrementar de uma unidade por linha. |
| `operationType` | 2–3 caracteres | Tipo da operação. |
| `operationDate` | date | Obrigatória para `GF` e `FG`. |
| `productCode` | 1–60 | Código do produto/serviço. |
| `productDescription` | 1–200 | Descrição. |
| `quantity` | number >= 0 | Quantidade inteira ou decimal. |
| `unitOfMeasure` | 1–20 | Unidade. |
| `unitPriceBase` | number >= 0 | Preço sem descontos e sem impostos. |
| `unitPrice` | number >= 0 | Preço após descontos, sem impostos. |
| `referenceInfo` | object | Obrigatório para determinadas NC. |
| `debitAmount` | number >= 0 | Montante da linha sem impostos. |
| `creditAmount` | number >= 0 | Montante da linha sem impostos. |
| `taxes` | array | Impostos da linha. |
| `settlementAmount` | number >= 0 | Total de descontos atribuídos à linha. |

## 7.3 `operationType`

| Código | Significado |
|---|---|
| `SE` | Prestação de serviços de educação |
| `SS` | Prestação de serviços de saúde |
| `STP` | Prestação de serviços de transporte de passageiros |
| `SR` | Prestação de serviços sujeitos a royalties |
| `SIF` | Prestação de serviços de intermediação financeira ou seguradora |
| `SHS` | Prestação de serviços de hotelaria e similares |
| `ST` | Prestação de serviços de telecomunicações |
| `SG` | Prestação de serviço geral/outros |
| `TB` | Transmissão de bens |
| `AS` | Arrendamento e subarrendamento |
| `QT` | Quotas |
| `RD` | Repasse de despesas |

## 7.4 `debitAmount` e `creditAmount`

A documentação estabelece exclusividade entre os dois campos:

> **Um e um só** de `debitAmount` e `creditAmount` pode estar preenchido.

## 7.5 Descontos

`settlementAmount` representa o desconto total atribuído à linha, reflectindo:

- proporção de desconto global;
- desconto específico da linha.

## 7.6 Referência

`referenceInfo` é utilizado para indicar o documento base.

Para notas de crédito, é obrigatório quando necessário para identificar a factura de origem da devolução de artigos.

```json
{
  "reference": "FT FT6325S2C/10001",
  "reason": "Devolução de artigos"
}
```

Campos:

| Campo | Restrição |
|---|---|
| `reference` | 1–60 caracteres; obrigatório dentro de `referenceInfo`. |
| `reason` | máximo 60 caracteres; opcional. |

---

# 8. Impostos por Linha

Cada linha pode possuir um array `taxes`.

## 8.1 Estrutura

```text
taxes[]
├── taxType
├── taxCountryRegion
├── taxCode
├── taxBase
├── taxPercentage
├── taxAmount
├── taxContribution
└── taxExemptionCode
```

## 8.2 `taxType`

| Código | Significado |
|---|---|
| `IVA` | Imposto sobre o Valor Acrescentado |
| `IS` | Imposto do Selo |
| `IEC` | Imposto Especial de Consumo |
| `CEOC` | Contribuição Especial de Consumo |
| `NS` | Não sujeito a IVA, IS, IEC ou CEOC |

## 8.3 `taxCountryRegion`

- Para países: ISO 3166-1 alpha-2.
- Para Cabinda: `AO-CAB`.

Restrições publicadas: mínimo 2 e máximo 6 caracteres.

## 8.4 `taxCode`

### Quando `taxType = IVA`

| Código | Significado |
|---|---|
| `NOR` | Taxa normal |
| `INT` | Taxa intermédia |
| `RED` | Taxa reduzida |
| `ISE` | Isento |
| `OUT` | Outra |

### Quando `taxType = IS`

Pode ser preenchido com a verba de Imposto do Selo conforme os valores do anexo indicado pela publicação.

Também admite:

```text
ISE — Isento
```

### Quando `taxType = IEC`

Pode conter o código pautal aplicável, de acordo com os valores previstos para IEC.

Também admite:

```text
ISE — Isento
```

### Quando `taxType = CEOC`

- `NOR` — taxa normal;
- `RED` — taxa reduzida.

A publicação indica:

- 10% para colectivos na taxa normal;
- 2,5% para singulares na taxa reduzida.

## 8.5 `taxBase`

É o valor tributável unitário que pode ser usado quando o montante da linha representa unicamente imposto e a base subjacente não constitui receita do sujeito passivo.

A documentação apresenta como exemplos:

- correcções de imposto através de nota de débito/crédito quando a base não é anulada;
- situações de crédito em que a base considerada para o Imposto do Selo não constitui receita do sujeito passivo.

Regra de combinação:

> `taxBase` não pode coexistir com `debitAmount` nem com `creditAmount`.

## 8.6 `taxPercentage`

A taxa é representada em percentagem.

Exemplo:

```text
14 = 14%
```

A publicação estabelece que a taxa deve ser `0` em caso de isenção ou não sujeição.

## 8.7 `taxAmount`

Valor fixo da verba de Imposto do Selo, quando aplicável. Concorre para o total do imposto após a aplicação da quantidade.

## 8.8 `taxContribution`

Representa o imposto calculado para a linha fiscal.

A publicação exige valor decimal com, no máximo, duas casas e determina **arredondamento por excesso para o cêntimo seguinte**.

Exemplos publicados:

| Cálculo | `taxContribution` |
|---:|---:|
| 23,144 | 23,15 |
| 0,001844 | 0,01 |
| 5,9999999 | 6,00 |

## 8.9 `taxExemptionCode`

Tem 3 caracteres.

É obrigatório quando:

- `taxCode = ISE`;
- `taxType = NS`.

Os códigos dependem do tipo de imposto e são referenciados nos anexos da documentação.

---

# 9. Recibos e `paymentReceipt`

`paymentReceipt` contém dados dos documentos que estão a ser regularizados pelo recibo.

## 9.1 Estrutura

```text
paymentReceipt
└── sourceDocuments[]
    ├── lineNo
    ├── sourceDocumentID
    │   ├── OriginatingON
    │   └── documentDate
    ├── debitAmount
    └── creditAmount
```

## 9.2 `sourceDocuments[]`

### `lineNo`

- integer;
- mínimo 1;
- começa em 1;
- incrementa de uma unidade por nova linha.

### `sourceDocumentID`

Identifica o documento regularizado.

| Campo | Regra |
|---|---|
| `OriginatingON` | número do documento regularizado; 1–60 caracteres |
| `documentDate` | data de emissão do documento regularizado |

### `debitAmount` / `creditAmount`

Apenas um deles pode estar preenchido.

---

# 10. Totais do Documento

`documentTotals` é obrigatório.

```json
{
  "taxPayable": 70,
  "netTotal": 500,
  "grossTotal": 570
}
```

## 10.1 `taxPayable`

É o total de imposto devido.

Para `AR`, `RC` e `RG`, é calculado com base nos documentos de origem regularizados pelo recibo, considerando notas de crédito com sinal negativo.

Não pode possuir mais de duas casas decimais.

## 10.2 `netTotal`

Total do documento sem imposto.

Nos recibos (`AR`, `RC`, `RG`) é calculado pela soma dos `netTotal` dos documentos de origem, com notas de crédito em sinal negativo.

## 10.3 `grossTotal`

É a soma de:

```text
netTotal + taxPayable
```

---

# 11. Moeda, Contra-valor e Câmbio

`currency` é opcional.

Em transacções gerais no território nacional em Kwanzas, a publicação indica que não deve ser preenchido quando não existe conversão cambial nem exportação.

Deve ser especificado para:

- regularização em divisa;
- regularização futura em divisa;
- facturas relativas a exportações.

## 11.1 Estrutura

```json
{
  "currencyCode": "EUR",
  "currencyAmount": 615.00,
  "exchangeRate": 950.00
}
```

## 11.2 `currencyCode`

- 3 caracteres;
- norma ISO 4217.

A publicação determina uma regra específica para `AOA`:

- se `currencyCode != AOA`, `currencyAmount` representa o contra-valor em Kwanzas;
- se `currencyCode = AOA`, `currencyAmount` representa o contra-valor em divisas.

## 11.3 Fórmulas

### Quando `currencyCode != AOA`

```text
grossTotal × exchangeRate
```

O resultado, arredondado matematicamente a duas casas, deve coincidir com `currencyAmount`.

### Quando `currencyCode = AOA`

```text
grossTotal / exchangeRate
```

O resultado, arredondado matematicamente a duas casas, deve coincidir com `currencyAmount`.

## 11.4 Arredondamento matemático

- primeira casa eliminada inferior a 5: mantém;
- primeira casa eliminada igual ou superior a 5: arredonda para cima.

Exemplos:

| Resultado | Valor final |
|---:|---:|
| 1000000,12222000000 | 1000000,12 |
| 100,12500000000 | 100,13 |
| 99990,12499990000 | 99990,12 |
| 555550,13500000000 | 555550,14 |
| 222220,13499990000 | 222220,13 |
| 11110,99999990000 | 11111,00 |

---

# 12. Retenção na Fonte

`withholdingTaxList` é opcional.

Cada item possui:

| Campo | Regra |
|---|---|
| `withholdingTaxType` | máximo 3 caracteres; obrigatório |
| `withholdingTaxDescription` | máximo 120 caracteres; opcional |
| `withholdingTaxAmount` | obrigatório |

## 12.1 Tipos publicados

| Código | Significado |
|---|---|
| `IRT` | Imposto sobre os Rendimentos do Trabalho |
| `II` | Imposto Industrial |
| `IS` | Imposto do Selo |
| `IVA` | Imposto sobre o Valor Acrescentado |
| `IP` | Imposto Predial |
| `IAC` | Imposto sobre Aplicação de Capitais |
| `OU` | Outros |
| `IRPC` | Imposto sobre rendimento de pessoas colectivas (impostos futuros) |
| `IRPS` | Imposto sobre rendimento de pessoas singulares (impostos futuros) |

Nos recibos `AR`, `RC` e `RG`, o valor é obtido agrupando as retenções dos documentos de origem pelo mesmo `withholdingTaxType`, com notas de crédito em sinal negativo.

---

# 13. Resposta de `Registar Factura`

## HTTP 200

Devolve `requestID`.

A publicação indica:

- máximo de 15 caracteres para `requestID`;
- o mesmo `requestID` pode ser devolvido no caso específico de requisição duplicada, permitindo identificar o registo original.

## HTTP 400

Devolve `errorList` com os erros detectados na recepção do pedido.

### `errorList`

| Campo | Obrigatório | Regra |
|---|---|---|
| `idError` | Sim | Código do erro |
| `descriptionError` | Sim | Descrição |
| `documentNo` | Condicional | Documento relacionado com o erro; torna-se obrigatório quando o erro ocorre dentro de `documents`. |

---

# 14. Regras de Negócio — Registar Factura

A tabela abaixo consolida as regras explicitamente publicadas para o serviço.

| Regra | Código | Regra de negócio |
|---|---|---|
| FE-RNG-001 / FE-RNG-002 | E01 | Falta do parâmetro indicado. |
| FE-RNG-003 | E02 | Formato inválido do parâmetro. |
| FE-RNG-004 | E03 | Valor não esperado do parâmetro. |
| FE-RNG-005 | E04 | `numberOfEntries` não coincide com o número de elementos de `documents`. |
| FE-RNG-008 | E06 | NIF/emissor sem actividade registada ou condição indicada na regra publicada. |
| FE-RNG-009 | E07 | Software de facturação especificado não está certificado. |
| FE-RNG-010 | E08 | `jwsSoftwareSignature` não corresponde aos dados transmitidos. |
| FE-RNG-011 | E39 | Dados da assinatura do software não correspondem ao processo de certificação. |
| FE-RNG-012 | E09 | Factura já consta no repositório do sistema. |
| FE-RNG-013 | E10 | Contribuinte especificado incorrectamente nos parâmetros de identificação. |
| FE-RNG-014 | E11 | NIF angolano desconhecido no sistema da AGT. |
| FE-RNG-015 | E12 | Número de linha incorrecto, repetido ou fora de sequência. |
| FE-RNG-016 | E13 | Documento de referência esperado não foi indicado. |
| FE-RNG-017 | E14 | Documento de referência desconhecido. |
| FE-RNG-018 | E15 | Dois parâmetros mutuamente exclusivos foram preenchidos ao mesmo tempo. |
| FE-RNG-019 | E16 | Em nota de crédito, soma de créditos deve ser inferior à soma de débitos. |
| FE-RNG-020 | E17 | Em documento diferente de nota de crédito, soma de créditos deve ser superior à soma de débitos. |
| FE-RNG-021 | E18 | Combinação de campos não permitida. |
| FE-RNG-022 | E19 | `taxBase` não pode coexistir com `debitAmount` ou `creditAmount`. |
| FE-RNG-023 | E20 | Combinação de campos não permitida. |
| FE-RNG-024 | E21 | Valor não coincide com `quantity × unitPriceBase`. |
| FE-RNG-025 | E22 | `taxPayable` não coincide com a soma dos impostos das linhas. |
| FE-RNG-026 | E23 | Total sem imposto não coincide com a soma das linhas. |
| FE-RNG-027 | E24 | Total com imposto não coincide com a soma calculada. |
| FE-RNG-028 | E25 | `grossTotal` não corresponde ao contra-valor da divisa ao câmbio indicado. |
| FE-RNG-029 | E26 | Utilização incorrecta de `lines` para o tipo de factura. |
| FE-RNG-029 | E27 | Utilização incorrecta de `paymentReceipt` para o tipo de factura. |
| FE-RNG-007 | E28 | NIF emissor não aderiu à Facturação Electrónica. |
| FE-RNG-030 | E29 | Data do documento é anterior à data de adesão à Facturação Electrónica. |
| FE-RNG-031 | E40 | Dados de `jwsSignature` não correspondem à chamada. |
| FE-RNG-061 | E41 | Montante a regularizar excede o remanescente do documento de origem. |
| FE-RNG-068 | E42 | Montante a anular/devolver excede o remanescente do documento base. |
| FE-RNG-069 | E43 | Em correcções via `taxBase`, a quantidade deve ser zero. |
| FE-RNG-073 | E46 | Não é aceite reutilizar o mesmo `documentNo` para corrigir documento rejeitado; a correcção deve utilizar novo número. |
| — | E99 | Outro erro não detalhado. |

> **Nota:** algumas descrições e associações de códigos são reproduzidas conforme a publicação, inclusive onde a numeração/descrição pode aparentar repetição ou variação entre secções.

---

# 15. Consultar Estado da Factura

Serviço para consultar o estado de validação dos documentos previamente transmitidos por `registarFactura`.

## 15.1 Endpoints

```text
Homologação:
POST https://sifphml.minfin.gov.ao/sigt/fe/v1/obterEstado

Produção:
POST https://sifp.minfin.gov.ao/sigt/fe/v1/obterEstado
```

## 15.2 Payload

```json
{
  "schemaVersion": "2.0",
  "submissionUUID": "a1b2c3d4-e5f6-7890-g1h2-i238j234k5122",
  "taxRegistrationNumber": "5001636863",
  "submissionTimeStamp": "2025-09-02T14:30:00Z",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  },
  "requestID": "202500000000118"
}
```

### Payload da assinatura

```json
{
  "taxRegistrationNumber": "...",
  "requestID": "..."
}
```

## 15.3 Resposta

```json
{
  "requestID": "202500000000118",
  "resultCode": "2",
  "taxRegistrationNumber": "5001636863",
  "documentStatusList": [],
  "requestErrorList": [],
  "successRequestID": ""
}
```

## 15.4 `resultCode`

| Código | Significado |
|---:|---|
| `0` | Processamento concluído, sem facturas inválidas. |
| `1` | Processamento concluído, com facturas válidas e inválidas. |
| `2` | Processamento concluído, sem facturas válidas. |
| `7` | Solicitação não respondida por ser prematura ou repetitiva; deve aguardar. |
| `8` | Processamento ainda em curso. |
| `9` | Processamento cancelado. |

## 15.5 `documentStatusList`

É obrigatório quando `resultCode` é diferente de `7`, `8` ou `9`.

Cada item contém:

| Campo | Regra |
|---|---|
| `documentNo` | 1–60 caracteres |
| `documentStatus` | `V` ou `I` |
| `errorList` | Obrigatório quando `documentStatus = I` |

### Estado do documento

- `V` — factura válida;
- `I` — factura inválida.

### Erros do documento

```text
errorList[]
├── errorCode
└── errorDescription
```

Restrições publicadas:

- `errorCode`: 3 caracteres;
- `errorDescription`: máximo 100 caracteres.

## 15.6 Respostas HTTP

| HTTP | Situação publicada |
|---|---|
| `200` | Consulta concluída; devolve `statusResult`. |
| `422` | E96 — solicitação ainda em processamento, conforme a descrição publicada. |
| `422` | E97 — solicitação prematura. |
| `422` | E95 — NIF emissor diferente. |
| `429` | E98 — demasiadas solicitações repetidas. |
| `400` | E96 — solicitação mal efectuada / erro de estrutura. |

> A publicação utiliza alguns códigos de erro em mais de uma situação/descrição. Esta característica é mantida no presente documento e deve ser confirmada no contrato de API vigente.

---

# 16. Listar Facturas Electrónicas

Serviço destinado a obter a lista das facturas registadas em nome do contribuinte dentro de um determinado período.

## 16.1 Endpoints

```text
Homologação:
POST https://sifphml.minfin.gov.ao/sigt/fe/ws/v1/listarFacturas

Produção:
POST https://sifp.minfin.gov.ao/sigt/fe/v1/listarFacturas
```

## 16.2 Payload

```json
{
  "schemaVersion": "2.0",
  "submissionGUID": "a1b2c3d4-e5f6-7890-g1h2-i2302832271",
  "taxRegistrationNumber": "5406024493",
  "submissionTimeStamp": "2025-09-19T07:41:54.473Z",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  },
  "jwsSignature": "string",
  "queryStartDate": "2025-09-10",
  "queryEndDate": "2025-09-20"
}
```

> A publicação utiliza `submissionGUID` no exemplo, enquanto outros serviços usam `submissionUUID`. Esta diferença é mantida como parte do material publicado e merece confirmação na especificação técnica efectiva.

### Campos assinados

```json
{
  "taxRegistrationNumber": "...",
  "queryStartDate": "...",
  "queryEndDate": "..."
}
```

## 16.3 Parâmetros

| Campo | Tipo | Restrição | Obrigatório | Regra |
|---|---|---|---|---|
| `schemaVersion` | string | — | Sim | Versão do schema. |
| `taxRegistrationNumber` | string | max. 15 | Sim | NIF. |
| `submissionTimeStamp` | string | ISO 8601 | Sim | Timestamp. |
| `softwareInfo` | object | — | Sim | Informação do software. |
| `jwsSignature` | string | Base64URL | Sim | Assinatura. |
| `queryStartDate` | string | date | Sim | Data inicial. |
| `queryEndDate` | string | date | Sim | Data final. |
| `tipoListagem` | string | max. 9 | Não | `EMITIDAS` ou `RECEBIDAS`. |
| `page` | number/integer | >= 0 | Não | Página de resultados. |
| `size` | number/integer | >= 1 | Não | Máximo de registos por página. |

> A descrição publicada para `queryEndDate` repete “data inicial”; a estrutura dos parâmetros indica claramente a função como data final. A formulação original é mantida como uma observação documental, não como nova regra.

## 16.4 Resposta

`documentListResult`:

```text
documentListResult
├── documentResultCount
└── documentResultList[]
    ├── documentNo
    └── documentDate
```

`documentNo`: máximo 60 caracteres.

`documentDate`: formato `date`.

## 16.5 Respostas HTTP

| HTTP | Resultado |
|---|---|
| `200` | `documentListResult` |
| `422` | E94 — NIF diferente |
| `429` | E98 — demasiadas solicitações repetidas |
| `400` | E96 — solicitação mal efectuada / erro de estrutura |

---

# 17. Validar Documento

Serviço para o adquirente confirmar ou rejeitar uma factura ou documento equivalente e, quando aplicável, indicar a percentagem de IVA dedutível.

## 17.1 Endpoints

```text
Homologação:
POST https://sifphml.minfin.gov.ao/sigt/fe/v1/validarDocumento

Produção:
POST https://sifp.minfin.gov.ao/sigt/fe/v1/validarDocumento
```

## 17.2 Payload

```json
{
  "schemaVersion": "2.0",
  "submissionTimeStamp": "2025-10-28T18:51:10.178Z",
  "taxRegistrationNumber": "5001636863",
  "softwareInfo": {
    "softwareInfoDetail": {
      "productId": "Meu ERP CERTO",
      "productVersion": "1.0.1",
      "softwareValidationNumber": "C_134"
    },
    "jwsSoftwareSignature": "<JWS>"
  },
  "jwsSignature": "string",
  "documentNo": "FT FT6325S2C/7",
  "action": "C",
  "deductibleVATPercentage": "72.5",
  "nonDeductibleAmount": "200.00"
}
```

### Payload de assinatura

```json
{
  "taxRegistrationNumber": "...",
  "documentNo": "FT FT6325S2C/7",
  "action": "C",
  "deductibleVATPercentage": "72.5",
  "nonDeductibleAmount": "200.00"
}
```

## 17.3 Parâmetros

| Campo | Regra |
|---|---|
| `schemaVersion` | obrigatório |
| `taxRegistrationNumber` | obrigatório; máximo 15 |
| `submissionTimeStamp` | obrigatório; ISO 8601 |
| `softwareInfo` | obrigatório |
| `jwsSignature` | obrigatório; RS256 + Base64URL |
| `documentNo` | obrigatório; máximo 60 |
| `action` | obrigatório; `C` ou `R` |
| `deductibleVATPercentage` | 0–100; opcional |
| `nonDeductibleAmount` | >= 0; opcional |

### `action`

- `C` — confirmação;
- `R` — rejeição.

### IVA dedutível

`deductibleVATPercentage` é utilizado quando:

- `action = C`;
- o documento não é recibo nem nota de crédito.

Se não for preenchido, a publicação considera que o contribuinte não possui direito à dedução.

### Valor não dedutível

`nonDeductibleAmount` identifica o valor não sujeito a dedução de IVA.

Se não for preenchido, a publicação considera a totalidade do valor do documento como dedutível.

### Exclusividade

Os campos:

- `deductibleVATPercentage`;
- `nonDeductibleAmount`

não podem ser preenchidos simultaneamente.

## 17.4 Resposta

```text
confirmRejectResult
├── actionResultCode
├── documentStatusCode
└── errorList[]
```

### `actionResultCode`

| Código | Significado |
|---|---|
| `C_OK` | Confirmação com sucesso |
| `R_OK` | Rejeição com sucesso |
| `C_NOK` | Confirmação não possível |
| `R_NOK` | Rejeição não possível |

### `documentStatusCode`

| Código | Estado |
|---|---|
| `S_A` | Anulado |
| `S_C` | Confirmado |
| `S_I` | Inválido |
| `S_RG` | Registado |
| `S_RJ` | Rejeitado |
| `S_V` | Válido |

`errorList` é obrigatória quando `actionResultCode` for `C_NOK` ou `R_NOK`.

## 17.5 Erros específicos

| Regra | Código | Descrição |
|---|---|---|
| FE-RNG-033 | E44 | O estado do documento não permite confirmação pelo adquirente. |
| FE-RNG-034 | E45 | O estado do documento não permite rejeição pelo adquirente. |
| FE-RNG-077 | E47 | `deductibleVATPercentage` não pode coexistir com `nonDeductibleAmount`. |

---

# 18. Modelo de Processamento Assíncrono

A submissão de documentos fiscais é deliberadamente separada da validação final.

## 18.1 Fluxo

```text
1. Software envia registarFactura
           |
           v
2. API valida estrutura JSON
           |
      estrutura válida?
        /       \
      não       sim
      |          |
      erro       v
             gera requestID
                  |
                  v
             fila de processamento
                  |
                  v
          validações fiscais
          + regras tributárias
          + série
          + integridade
                  |
                  v
             resultado final
                  |
                  v
             obterEstado
```

## 18.2 Consequência para a implementação

O software do contribuinte deve separar, internamente:

- o estado de **submissão técnica**;
- o estado de **processamento/validação fiscal**.

Não se deve considerar a recepção de `requestID` como confirmação de validade da factura.

---

# 19. Gestão de Certificados e Chaves

A infraestrutura utiliza criptografia assimétrica RSA.

As chaves seguem responsabilidades distintas:

- chaves do contribuinte: utilizadas para documentos e requisições;
- chaves do produtor de software: utilizadas para `jwsSoftwareSignature`.

## 19.1 Chaves do contribuinte

A publicação indica que as chaves privadas e públicas dos contribuintes serão geradas pela AGT e disponibilizadas na conta do Portal do Contribuinte para consulta.

As chaves dos contribuintes são utilizadas para:

- `jwsDocumentSignature`;
- `jwsSignature`.

## 19.2 Chaves do produtor de software

As chaves utilizadas para `jwsSoftwareSignature` não são emitidas pela AGT.

Cada produtor deve:

1. gerar localmente um par RSA;
2. manter a chave privada dentro do ambiente seguro do produtor;
3. enviar à AGT a chave pública;
4. submeter a chave pública no processo de registo do produtor/software.

### Ambientes indicados

**Testes:**

```text
https://portaldoparceiro.hml.minfin.gov.ao/
```

**Produção:**

```text
https://portaldoparceiro.minfin.gov.ao/
```

## 19.3 Características da chave

| Propriedade | Regra publicada |
|---|---|
| Tipo | RSA |
| Tamanho | mínimo 2048 bits |
| Recomendação | 4096 bits |
| Formato | PEM |
| Codificação do conteúdo PEM | Base64 |

### Chave pública

```text
-----BEGIN PUBLIC KEY-----
...
-----END PUBLIC KEY-----
```

### Chave privada

```text
-----BEGIN PRIVATE KEY-----
...
-----END PRIVATE KEY-----
```

A chave privada nunca deve ser enviada à AGT.

## 19.4 Comprometimento de chave

Se houver suspeita de exposição da chave privada:

1. revogar imediatamente a chave comprometida;
2. gerar novo par RSA;
3. actualizar o software com a nova chave pública;
4. submeter/actualizar a chave no Portal do Parceiro;
5. marcar a chave antiga como revogada no portal.

## 19.5 Efeito sobre documentos anteriores

Segundo a documentação, documentos assinados com a chave comprometida permanecem válidos quando:

- já foram processados e aceites pela AGT;
- a assinatura era tecnicamente válida.

As novas submissões deixam de ser aceites com a chave revogada.

## 19.6 Validação do JWS pela API

O fluxo descrito é:

1. receber o JSON;
2. extrair `jwsSoftwareSignature`, `jwsDocumentSignature` e/ou `jwsSignature` conforme aplicável;
3. localizar a chave pública activa ou a chave correspondente à versão;
4. reconstruir o JSON canónico;
5. recalcular o hash;
6. utilizar a chave pública para verificar a assinatura.

Resultado:

- assinatura válida → documento segue para processamento;
- assinatura inválida → retorna erro de assinatura.

---

# 20. QR Code dos Documentos Impressos

A documentação define as seguintes características para o QR Code:

| Propriedade | Valor |
|---|---|
| Padrão | QR Code Model 2 |
| Versão | 4 |
| Dimensão lógica | 33 × 33 módulos |
| Correcção de erros | M — 15% |
| Modo de dados | Byte |
| Codificação | UTF-8 |
| Formato | PNG |
| Dimensão | 350 × 350 px |

## 20.1 URL codificada

```text
https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor=nifEmissor&document=documentNo
```

Os parâmetros representam:

- `emissor` → NIF do emissor;
- `document` → `documentNo`.

## 20.2 Espaços em `documentNo`

Cada espaço existente no `documentNo` deve ser substituído por:

```text
%20
```

Exemplo:

```text
FT FT6325S2C/10006
```

torna-se:

```text
FT%20FT6325S2C/10006
```

## 20.3 Logotipo da AGT

A publicação determina que o QR Code deve incluir o logotipo da AGT e que o logotipo deve ocupar menos de 20% da área total da imagem.

---

# 21. Regras Transversais para Implementação

A matéria publicada permite consolidar os seguintes requisitos de implementação.

## 21.1 Identidade e autenticação

O software deve possuir:

- credenciais de Basic Auth válidas;
- chave privada do contribuinte para as assinaturas requeridas;
- chave privada do produtor para `jwsSoftwareSignature`;
- armazenamento seguro das chaves;
- controlo de versão/rotação de chaves quando aplicável.

## 21.2 Assinaturas

Toda implementação deve assegurar:

- RSA;
- mínimo de 2048 bits;
- RS256;
- SHA-256;
- Base64URL;
- JWS Compact Serialization;
- payload exacto correspondente ao serviço;
- consistência do JSON que é assinado.

## 21.3 Submissão

Antes de enviar:

1. validar os campos obrigatórios;
2. validar formatos;
3. verificar enumerações;
4. verificar cardinalidade e número de documentos;
5. calcular os totais;
6. validar referências;
7. gerar as assinaturas;
8. enviar via HTTPS + Basic Auth;
9. guardar o `requestID`.

## 21.4 Pós-submissão

Após receber `requestID`:

1. não assumir que a factura está válida;
2. aguardar processamento;
3. consultar `obterEstado` respeitando o comportamento de repetição indicado;
4. guardar os estados por documento;
5. guardar os erros retornados;
6. actualizar o estado interno do documento.

---

# 22. Tipos de Documento — Referência Rápida

```text
FA  Factura de Adiantamento
FT  Factura
FR  Factura/Recibo
FG  Factura Global
GF  Factura Genérica
AC  Aviso de Cobrança
AR  Aviso de Cobrança/Recibo
TV  Talão de Venda
RC  Recibo em numerário / Recibo Emitido
RG  Recibo Geral / Outros Recibos Emitidos
RE  Estorno ou Recibo de Estorno
ND  Nota de Débito
NC  Nota de Crédito
AF  Factura/Recibo de Autofacturação
RP  Prémio ou Recibo de Prémio
RA  Resseguro Aceite
CS  Imputação a Co-seguradoras
LD  Imputação a Co-seguradora Líder
```

> A nomenclatura de `RC` e `RG` apresenta ligeiras variações entre as secções da própria publicação. Este arquivo mantém as designações conforme cada contexto, em vez de forçar uma reconciliação que não está explicitada pela fonte.

---

# 23. Estados de Documento — Referência Rápida

## 23.1 Estado de submissão / validação

```text
V  Factura válida
I  Factura inválida
```

## 23.2 Estado usado na acção de validação do adquirente

```text
S_A   Anulado
S_C   Confirmado
S_I   Inválido
S_RG  Registado
S_RJ  Rejeitado
S_V   Válido
```

## 23.3 Resultado da acção do adquirente

```text
C_OK   Confirmação com sucesso
R_OK   Rejeição com sucesso
C_NOK  Confirmação não possível
R_NOK  Rejeição não possível
```

---

# 24. Códigos de Serviço e Ambientes

| Serviço | Homologação | Produção |
|---|---|---|
| Solicitar série | `https://sifphml.minfin.gov.ao/sigt/fe/ws/v1/registarFactura`* | `https://sifp.minfin.gov.ao/sigt/fe/v1/solicitarSerie` |
| Listar séries | `https://sifphml.minfin.gov.ao/sigt/fe/v1/listarSeries` | `https://sifp.minfin.gov.ao/sigt/fe/v1/listarSeries` |
| Registar factura | `https://sifphml.minfin.gov.ao/sigt/fe/v1/registarFactura` | `https://sifp.minfin.gov.ao/sigt/fe/v1/registarFactura` |
| Consultar estado | `https://sifphml.minfin.gov.ao/sigt/fe/v1/obterEstado` | `https://sifp.minfin.gov.ao/sigt/fe/v1/obterEstado` |
| Listar facturas | `https://sifphml.minfin.gov.ao/sigt/fe/ws/v1/listarFacturas`* | `https://sifp.minfin.gov.ao/sigt/fe/v1/listarFacturas` |
| Validar documento | `https://sifphml.minfin.gov.ao/sigt/fe/v1/validarDocumento` | `https://sifp.minfin.gov.ao/sigt/fe/v1/validarDocumento` |

`*` A própria publicação apresenta a rota `ws/v1` nestes dois pontos. Deve ser confirmada no ambiente de homologação efectivo antes de codificar uma integração definitiva.

---

# 25. Modelo de Dados Simplificado

```text
Request
│
├── schemaVersion
├── submissionUUID / submissionGUID (conforme serviço)
├── taxRegistrationNumber
├── submissionTimeStamp
├── softwareInfo
│   ├── softwareInfoDetail
│   │   ├── productId
│   │   ├── productVersion
│   │   ├── softwareValidationNumber
│   │   └── signatureVersion (quando aplicável)
│   └── jwsSoftwareSignature
│
├── jwsSignature
│
└── documents[]                       (registarFactura)
    └── document
        ├── documentNo
        ├── documentStatus
        ├── rejectedDocumentNo
        ├── jwsDocumentSignature
        ├── documentDate
        ├── documentType
        ├── eacCode
        ├── systemEntryDate
        ├── customerCountry
        ├── customerTaxID
        ├── companyName
        │
        ├── lines[]
        │   └── line
        │       ├── lineNumber
        │       ├── operationType
        │       ├── operationDate
        │       ├── productCode
        │       ├── productDescription
        │       ├── quantity
        │       ├── unitOfMeasure
        │       ├── unitPriceBase
        │       ├── unitPrice
        │       ├── referenceInfo
        │       ├── debitAmount
        │       ├── creditAmount
        │       ├── taxes[]
        │       └── settlementAmount
        │
        ├── paymentReceipt
        │   └── sourceDocuments[]
        │
        ├── documentTotals
        │   ├── taxPayable
        │   ├── netTotal
        │   ├── grossTotal
        │   └── currency
        │       ├── currencyCode
        │       ├── currencyAmount
        │       └── exchangeRate
        │
        └── withholdingTaxList[]
```

---

# 26. Checklist de Conformidade para um Software

## Segurança

- [ ] Basic Auth configurado.
- [ ] Chaves privadas protegidas.
- [ ] Chave pública do produtor registada na AGT.
- [ ] RSA >= 2048 bits.
- [ ] RS256 configurado.
- [ ] Base64URL utilizado para JWS.
- [ ] Rotação/revogação de chaves suportada.

## Assinatura

- [ ] `jwsSoftwareSignature` assina o objecto de software exigido.
- [ ] `jwsDocumentSignature` assina exactamente o conjunto de campos exigido.
- [ ] `jwsSignature` varia segundo o serviço.
- [ ] JSON utilizado na assinatura é consistente/canónico conforme recomendação.
- [ ] Não são assinadas concatenações arbitrárias dos campos.

## Facturas

- [ ] `documentNo` segue o formato esperado.
- [ ] `documentType` é válido.
- [ ] `customerCountry` usa ISO 3166-1 alpha-2.
- [ ] `customerTaxID` é coerente com o país.
- [ ] Linhas são sequenciais.
- [ ] `debitAmount`/`creditAmount` respeitam exclusividade.
- [ ] `taxBase` respeita as regras de combinação.
- [ ] Impostos e totais são recalculados antes do envio.
- [ ] Recibos utilizam `paymentReceipt` conforme o tipo documental.
- [ ] Notas de crédito/débito respeitam documentos de referência.
- [ ] Valores monetários respeitam as regras de arredondamento.

## Processamento

- [ ] `requestID` é persistido.
- [ ] O estado da submissão é separado do estado fiscal final.
- [ ] O polling respeita o estado `7`/`8` e as respostas de processamento.
- [ ] Erros por documento são persistidos.
- [ ] Pedidos duplicados são tratados através do `requestID` devolvido.

## Impressão

- [ ] QR Code Model 2.
- [ ] Versão 4.
- [ ] ECC M.
- [ ] UTF-8.
- [ ] PNG 350×350 px.
- [ ] Espaços de `documentNo` codificados como `%20`.
- [ ] Logotipo AGT com ocupação inferior a 20%.

---

# 27. Observações Documentais Importantes

A documentação publicada apresenta alguns exemplos e secções com pequenas inconsistências editoriais. Para uma implementação de produção, estas situações devem ser validadas com a versão de API efectivamente disponibilizada pela AGT, em vez de serem “corrigidas” silenciosamente no software.

## 27.1 Endpoints de homologação com `ws/v1`

A página de criação de séries apresenta:

```text
https://sifphml.minfin.gov.ao/sigt/fe/ws/v1/registarFactura
```

enquanto o endpoint de produção indicado é:

```text
https://sifp.minfin.gov.ao/sigt/fe/v1/solicitarSerie
```

A listagem de facturas também é apresentada com `/ws/v1` na homologação.

## 27.2 `seriesInfo` vs. `seriresInfo`

O exemplo de resposta de `listarSeries` contém `seriresInfo`, enquanto a estrutura documentada utiliza `seriesInfo`.

## 27.3 `submissionUUID` vs. `submissionGUID`

A maioria dos exemplos usa `submissionUUID`, mas o exemplo de `listarFacturas` usa `submissionGUID`.

## 27.4 Códigos de erro repetidos/variáveis

Alguns códigos são descritos de forma diferente em secções distintas, principalmente `E96`, `E39`, `E40` e outros códigos contextuais. O comportamento efectivo deve ser obtido do contrato técnico vigente do ambiente utilizado.

## 27.5 Terminologia `RC` e `RG`

Algumas secções utilizam:

- `RC` — Recibo em numerário / Recibo Emitido;
- `RG` — Recibo Geral / Outros Recibos Emitidos.

A semântica funcional é consistente nas regras de `lines` e `paymentReceipt`, mas a nomenclatura textual varia.

---

# 28. Fontes Oficiais Consultadas

- Introdução: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/index.html
- Autenticação: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/api.html
- JWS: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/estrutura.html
- Gestão de chaves: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/gestao.html
- Solicitar série: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/servicos/solicitar.html
- Registar factura: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/servicos/registar.html
- Consultar estado: https://portaldoparceiro.minfin.gov.ao/doc-agt/faturacao-electronica/1/servicos/consultar.html
- Listar séries: página de serviço `listarSeries` do Portal do Parceiro.
- Listar facturas: página de serviço `listarFacturas` do Portal do Parceiro.
- Validar documento: página de serviço `validarDocumento` do Portal do Parceiro.

---

# 29. Referência de Integração — Fluxo Completo

```text
┌──────────────────────────────┐
│ 1. Configuração do software  │
│ - certificação                │
│ - Basic Auth                  │
│ - chaves RSA                  │
│ - chave pública na AGT        │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 2. Solicitar/consultar série │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 3. Gerar documento           │
│ - documentNo                 │
│ - linhas                     │
│ - impostos                   │
│ - totais                     │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 4. Gerar JWS                 │
│ - software                   │
│ - documento                  │
│ - requisição                 │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 5. POST registarFactura      │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 6. Receber requestID         │
│    (não significa validade)  │
└──────────────┬───────────────┘
               │
               v
┌──────────────────────────────┐
│ 7. Obter estado              │
│    obterEstado               │
└──────────────┬───────────────┘
               │
        ┌──────┴──────┐
        │             │
        v             v
      Válido        Inválido
        │             │
        v             v
  consolidar      tratar erro /
  estado fiscal   correcção

               │
               v
┌──────────────────────────────┐
│ 8. Para facturas recebidas   │
│    validarDocumento          │
└──────────────────────────────┘
```

---

# 30. Resumo Técnico

A integração descrita pela AGT assenta em cinco pilares:

1. **Autenticação HTTP:** Basic Auth para acesso aos serviços protegidos.
2. **Assinatura criptográfica:** JWS com RS256 e RSA >= 2048 bits.
3. **Controlo de séries:** as séries são solicitadas e geridas pela API, associadas ao contribuinte, software, ano, tipo de documento e estabelecimento.
4. **Submissão assíncrona:** `registarFactura` devolve `requestID` e a validação fiscal é posterior.
5. **Rastreabilidade:** o sistema acompanha documentos através de identificadores, estados, timestamps e erros.

O software certificado deve, portanto, possuir uma camada de integração fiscal independente do front-end, responsável por:

- serialização dos payloads;
- validação preliminar;
- cálculo de totais;
- geração das assinaturas;
- autenticação;
- envio dos pedidos;
- persistência de `requestID`;
- polling de estados;
- tratamento de erros;
- gestão de séries;
- gestão de chaves;
- produção/validação do QR Code.

---

## Fim do documento

Este arquivo é uma consolidação técnica da documentação publicada pela AGT no Portal do Parceiro. As regras e exemplos são apresentados de acordo com a matéria disponível e com o conteúdo fornecido para análise. Em caso de divergência entre versões da documentação, deve prevalecer a especificação oficial vigente no ambiente de integração da AGT.
