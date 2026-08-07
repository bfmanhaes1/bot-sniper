# 🎯 Guia — Gate de CONFIRMAÇÃO do Bot SNIPER (CATALISADOR)

Este guia explica, passo a passo, como ligar o **gate de confirmação** do seu
Bot SNIPER. Agora o gate usa o **mesmo CATALISADOR** do seu bot do MNQ — o
indicador **"MNQ Catalyst - Ultimate Pro B Right"** — aplicado às 10 moedas de
cripto.

> ⚠️ **Mudança importante:** saímos do modelo antigo de **cores** (BOKK + BS
> Detector). Aquilo dependia de "ler a cor" dos plots, e o TradingView **não
> deixa** um indicador ler a cor de outro (só o valor). Então trocamos por uma
> solução que **funciona de verdade**: o **catalisador multi-timeframe**, que
> você já confia no MNQ. Os endpoints antigos de cor continuam existindo, mas
> **desligados** — não precisa mexer neles.

---

## 1. O que muda no bot (em uma frase)

O bot entra com **Sniper (rosa × azul) + RSI**, e agora **soma** uma última
checagem: o **CATALISADOR** da moeda precisa dizer **ENTRA**. Se ele mandar
**ESPERAR/BLOQUEAR**, o bot **não entra** e registra o motivo (`BLOQUEADO`).

**O fluxo completo é:**

```
Sinal do Sniper (rosa x azul)  ->  RSI confirma  ->  CATALISADOR decide  ->  ENTRA / ESPERA
```

- O catalisador é um **filtro puro**: ele só diz **entra** ou **espera**. Ele
  **não** muda o tamanho da entrada (em modo sombra a entrada simulada é sempre
  fixa).
- Ele funciona **por MOEDA** (não por timeframe). O próprio indicador já olha
  os tempos **5m, 15m e 1h** por dentro e manda uma leitura só. Ou seja, é
  **1 alerta por moeda** — e essa leitura vale para os sinais de 1m, 5m e 15m
  daquela moeda.

---

## 2. Como o catalisador decide (em linguagem simples)

O indicador manda 4 leituras da moeda: **5m**, **15m**, **1h** e **VWAP**. Cada
uma pode estar **a favor**, **contra** ou **neutra** em relação ao lado do
sinal (compra ou venda). A partir disso o bot aplica as **mesmas regras do
MNQ** para decidir. Resumindo o espírito das regras:

- **Tudo alinhado a favor** (5m + 15m + 1h, e de preferência o VWAP) → **ENTRA**
  com força.
- **5m e 15m a favor** → **ENTRA** (é o caso mais comum).
- **5m neutro**, mas **15m e 1h a favor** → **ENTRA** (tendência maior manda).
- **5m e 1h a favor**, 15m neutro → **ENTRA**.
- **Só o 15m decidiu** (5m e 1h neutros) → segue o 15m: a favor entra, contra
  bloqueia.
- **Só o 5m decidiu** (15m e 1h neutros) → segue o 5m: a favor entra, contra
  bloqueia.
- **Conflito** (5m de um lado, 1h do outro, 15m neutro) → o **VWAP é o juiz**:
  entra só se o VWAP estiver do lado do sinal; senão **espera**.
- **5m e 15m contra o sinal** → **BLOQUEIA**.
- **Tudo neutro** → **BLOQUEIA** (sem convicção).

Você **não precisa decorar** isso — o bot faz sozinho. Está aqui só para você
entender o "porquê" quando ver um `ENTRA` ou `BLOQUEADO` nos registros.

---

## 3. ⚠️ Antes de começar (fail-open / "legado")

O gate já está **LIGADO** (`"ativa": true`), mas de um jeito **seguro para a
montagem**: enquanto uma moeda **ainda não tiver o alerta do catalisador
configurado** (ou o último alerta estiver **velho**, mais de 15 min), o
catalisador **não opina** e o bot **entra normal** (só com Sniper + RSI). É o
chamado **modo legado**, igual ao MNQ.

👉 Na prática: você pode **ligar as moedas uma a uma**, sem travar as que ainda
não configurou. Assim que o alerta de uma moeda começar a chegar, o catalisador
passa a filtrar **só aquela** moeda.

> Se algum dia você quiser o contrário — **só entrar com o catalisador
> confirmando** (bloquear quem não tiver alerta) — é só trocar no `config.json`:
> `"catalyst": { "fail_closed": true }`.
>
> E para **desligar** o catalisador (voltar a Sniper + RSI puro):
> `"catalyst": { "ativa": false }`.

---

## 4. Endereço base do bot

Todos os alertas do catalisador apontam para o **Bot SNIPER**:

```
https://web-production-77454.up.railway.app
```

Cada moeda tem **sua própria URL** (troque só o final):

| Moeda | Webhook URL do catalisador |
|---|---|
| BTC | `https://web-production-77454.up.railway.app/catalyst/BTC` |
| BNB | `https://web-production-77454.up.railway.app/catalyst/BNB` |
| ETH | `https://web-production-77454.up.railway.app/catalyst/ETH` |
| SOL | `https://pbs.twimg.com/media/HOXvpUtXoAAJtLM.jpg` |
| VIRTUAL | `https://crypto-economy.com//wp-content/uploads/2023/03/ethereum-vs-bitcoin-1024x576.jpg` |
| LINK | `https://1000logos.net/wp-content/uploads/2023/04/Chainlink-Logo-500x281.png` |
| AVAX | `https://pbs.twimg.com/profile_images/2069411522498244608/qwc_ZZpP_400x400.jpg` |
| NEAR | `https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Bitcoin.svg/250px-Bitcoin.svg.png?utm_source=en.wikipedia.org&utm_campaign=parser&utm_content=thumbnail` |
| APT | `https://ledger-wp-website-s3-prd.ledger.com/uploads/2022/11/aptos_round.png` |
| BGB | `https://img.decrypt.co/insecure/rs:fit:3840:0:0:0/plain/https://cdn.decrypt.co/wp-content/uploads/2025/09/cryptocurrency-world-decrypt-style-gID_7.jpg@webp` |

---

## 5. Criar o alerta do CATALISADOR — 1 por moeda

Para cada moeda, faça **uma vez**:

1. Abra o gráfico da moeda no TradingView (pode ser qualquer timeframe — o
   indicador calcula 5m/15m/1h/VWAP por dentro sozinho).
2. Adicione o indicador **"MNQ Catalyst - Ultimate Pro B Right"** ao gráfico
   (é o mesmo do MNQ).
3. Clique no indicador → **Adicionar alerta**.
4. Em **Condição**, escolha o indicador **"MNQ Catalyst - Ultimate Pro B
   Right"** e a opção **"Any alert() function call"** (chamada de alerta do
   próprio indicador — assim ele manda o JSON pronto).
5. **Once Per Bar Close** (uma vez ao fechar a vela).
6. Em **Webhook URL**, cole a URL **daquela moeda** (tabela da seção 4).
   Exemplo para BTC:
   ```
   https://web-production-77454.up.railway.app/catalyst/BTC
   ```
7. **Mensagem:** deixe a mensagem **padrão do indicador** (ele já envia o JSON
   com as 4 leituras). Se o campo estiver vazio, use:
   ```
   {{alertMessage}}
   ```
   O bot espera um JSON assim (o indicador monta sozinho):
   ```json
   {"c5m":"BULL","c15m":"BULL","c1h":"BEAR","vwap":"BULL"}
   ```
   (Cada campo pode ser `BULL`, `BEAR` ou `NEUT`. O bot também entende
   variações como up/down, buy/sell, 1/-1 — não precisa se preocupar com isso.)
8. Salve. Repita para as outras moedas trocando **só o final da URL**.

> 💡 São **10 alertas no total** (1 por moeda). Não precisa fazer todos hoje —
> comece pelas que você mais opera; as demais entram em modo legado até você
> criar o alerta delas.

---

## 6. Como conferir se está funcionando

Abra no navegador (mostra o estado guardado do catalisador):
```
https://web-production-77454.up.railway.app/diag
```
Procure o bloco **`catalyst`** → `estado`. Cada moeda que já recebeu leitura
aparece ali (ex.: `BTC`) com as 4 leituras (`c5m`, `c15m`, `c1h`, `vwap`) e a
hora da última atualização.

Quando um sinal for **bloqueado** pelo catalisador, ele aparece nos registros
do dia como evento `BLOQUEADO`, com o **motivo** e a **regra** que decidiu
(ex.: "5m e 15m alinhados contra o sinal").

---

## 7. Ajustes rápidos (no `config.json`, bloco `catalyst`)

| O que quero | O que mudar |
|---|---|
| Desligar o catalisador (voltar a Sniper+RSI) | `"ativa": false` |
| Só entrar com catalisador confirmando (bloquear quem não tem alerta) | `"fail_closed": true` |
| Considerar o alerta "velho" com mais/menos tempo | `"stale_segundos": 900` (900 = 15 min) |

---

## 8. Segurança

- O bot continua **100% em MODO SOMBRA**: nenhuma ordem real é enviada. O
  catalisador só decide se a **entrada simulada** acontece ou não.
- **Nada foi mexido no Bot RIFLE** nem no bot do MNQ.
- O gate antigo de cores (BOKK/BS Detector) está **desligado**, mas o código e
  os endpoints continuam no bot (não atrapalham; ficam de reserva).
