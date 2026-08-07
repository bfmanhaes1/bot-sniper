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

## 4. ⚠️ Isto é SÓ para o CRIPTO (os índices NÃO são tocados)

Tudo aqui é **exclusivo do cripto**. O seu bot do MNQ e os alertas dos índices
**continuam iguais, sem nenhuma alteração**. Para não correr risco nenhum de
mexer no MNQ, a gente vai usar uma **cópia** do indicador só para o cripto:

1. No TradingView, abra o indicador **"MNQ Catalyst - Ultimate Pro B Right"**
   no Pine Editor.
2. Clique em **Salvar como…** (Save as…) e dê um nome novo, ex.:
   **"Catalyst CRIPTO"**.
3. Faça o ajuste da seção 5 **só nessa cópia**. O indicador original do MNQ
   **fica intocado**.

> Assim os índices seguem exatamente como estão hoje — o ajuste vive só na
> cópia que você vai usar nos gráficos de cripto.

---

## 5. Ajuste de 1 linha (só na cópia CRIPTO)

Na cópia **"Catalyst CRIPTO"**, procure a linha do **feed do bot** (a que monta
o `azul_json`) e troque por esta — a única diferença é que ela agora inclui a
**moeda** no começo:

```pine
azul_json = '{"moeda":"' + syminfo.ticker + '","c5m":"' + c5m_txt + '","c15m":"' + c15m_txt + '","c1h":"' + c1h_txt + '","vwap":"' + vwap_txt + '"}'
```

Salve. Agora essa cópia manda algo assim (a moeda vem junto):

```json
{"moeda":"BTCUSDT.P","c5m":"BULL","c15m":"BULL","c1h":"BEAR","vwap":"BULL"}
```

O bot entende o ticker do TradingView e converte para a moeda base sozinho
(`BTCUSDT.P` → `BTC`, `ETHUSDT` → `ETH`, etc.).

---

## 6. Criar o alerta do CATALISADOR — UM alerta, qualquer moeda

O endereço do catalisador é **um só**, e serve para **qualquer moeda de cripto**:

```
https://web-production-77454.up.railway.app/catalyst
```

Com o ajuste da seção 5, você cria o alerta assim:

1. Abra o gráfico da moeda de cripto e adicione a cópia **"Catalyst CRIPTO"**.
2. Clique no indicador → **Adicionar alerta**.
3. **Condição:** **"Catalyst CRIPTO"** → **"Any alert() function call"**.
4. **Once Per Bar Close** (uma vez ao fechar a vela).
5. **Webhook URL** — sempre a mesma, para qualquer moeda:
   ```
   https://web-production-77454.up.railway.app/catalyst
   ```
6. **Mensagem:** deixe a **padrão do indicador** (já sai com a moeda e as 4
   leituras). Não precisa digitar nada.
7. Salve.

Para acompanhar **outra moeda**, é só **repetir** (adicionar a cópia naquele
gráfico e criar o alerta com a **mesma URL**). Como a moeda vai dentro da
mensagem, o bot separa tudo certinho — **funciona em qualquer par**, inclusive
fora das 10 que o bot opera.

> 💡 O bot só **opera** as 10 moedas (BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX,
> NEAR, APT, BGB), mas **guarda** o catalisador de qualquer moeda que você
> mandar — útil se um dia você quiser incluir moedas novas.

> Se preferir, ainda dá para usar a versão antiga com a moeda na URL
> (`.../catalyst/BTC`) — mas com o ajuste acima você não precisa dela.

---

## 7. Como conferir se está funcionando

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

## 8. Ajustes rápidos (no `config.json`, bloco `catalyst`)

| O que quero | O que mudar |
|---|---|
| Desligar o catalisador (voltar a Sniper+RSI) | `"ativa": false` |
| Só entrar com catalisador confirmando (bloquear quem não tem alerta) | `"fail_closed": true` |
| Considerar o alerta "velho" com mais/menos tempo | `"stale_segundos": 900` (900 = 15 min) |

---

## 9. Segurança

- O bot continua **100% em MODO SOMBRA**: nenhuma ordem real é enviada. O
  catalisador só decide se a **entrada simulada** acontece ou não.
- **Nada foi mexido no Bot RIFLE**, nem no bot do MNQ, nem nos alertas dos
  **índices**. Este catalisador é **exclusivo do cripto** e roda em outro bot,
  em outro endereço. Por isso pedimos para usar uma **cópia** do indicador
  (seção 4) — o indicador do MNQ fica intocado.
- O gate antigo de cores (BOKK/BS Detector) está **desligado**, mas o código e
  os endpoints continuam no bot (não atrapalham; ficam de reserva).
