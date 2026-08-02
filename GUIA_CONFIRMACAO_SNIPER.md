# 🎯 Guia — Camada de CONFIRMAÇÃO do Bot SNIPER

Este guia explica, passo a passo, como ligar a **camada de confirmação** (o
"gate") no seu Bot SNIPER. É o mesmo modelo do seu "bot verde" do MNQ, agora
nas 10 moedas de cripto.

---

## 1. O que muda no bot (em uma frase)

Antes, o bot entrava com **Sniper + RSI**. Agora ele **soma** uma última
checagem: quando o sinal do Sniper chega (já confirmado pelo RSI), o bot só
**ENTRA** se as cores dos indicadores fechados estiverem todas certas. Se
não estiverem, ele **NÃO entra** e registra o motivo (`BLOQUEADO`).

### A regra (COMPRA e VENDA são espelho)

| Componente | COMPRA (LONG) | VENDA (SHORT) |
|---|---|---|
| **BOKK** (TSTS Core) | 🟢 verde | 🔴 vermelho |
| **Histograma** (BS Detector) | 🔴 vermelho | 🟢 verde |
| **Plot 1** | 🟢 verde | 🔴 vermelho |
| **Plot 2** | 🟢 verde | 🔴 vermelho |
| **Plot 3** | 🟢 verde | 🔴 vermelho |

> ⚠️ **Confirme comigo o Histograma:** deixei o histograma como **oposto**
> (COMPRA pede histograma **vermelho**). Se na sua convenção a COMPRA pede
> histograma **verde**, é só avisar que eu troco 1 palavra no config
> (`"histograma": "oposta"` → `"mesma"`). Todo o resto funciona igual.

O **BOKK aceita tolerância**: ele pode ter mudado de cor até **3 velas
antes** do sinal e ainda vale (ajustável no config).

---

## 2. ⚠️ IMPORTANTE antes de começar (fail-closed)

O gate já está **LIGADO** (`"ativa": true`). Enquanto uma combinação
**moeda + timeframe** ainda **não tiver os alertas de cor configurados**, ela
**não vai entrar** (o bot bloqueia por falta de dados — isso é de propósito,
para não entrar "no escuro").

👉 Você tem **duas opções**:

- **A) Montar tudo primeiro e depois ligar:** eu deixo `"ativa": false`
  agora, você configura os alertas com calma, e quando terminar a gente liga.
- **B) Ligar já (como está):** vale a pena se você for configurar as moedas
  principais hoje. As que faltarem simplesmente não entram até você terminar.

> Para voltar ao comportamento antigo (só Sniper + RSI) a qualquer momento:
> troque no `config.json` → `"confirmacao": { "ativa": false }`.

---

## 3. Endereço base do bot

Todos os alertas apontam para o **Bot SNIPER**:

```
https://web-production-77454.up.railway.app
```

Troque `<MOEDA>` por: **BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB**
Troque `<TF>` por: **1m, 5m ou 15m**

---

## 4. Configurar o BOKK (TSTS Core) — 2 alertas por gráfico

O BOKK é a mesma ideia do seu MNQ: um alerta **nativo** do indicador manda a
cor atual. Como o BOKK tem 2 estados (verde/vermelho), são **2 alertas por
gráfico** (um para cada cor).

### Alerta 1 — BOKK ficou VERDE
1. Abra o gráfico da moeda no timeframe desejado.
2. Clique no indicador **TSTS Core** → **Adicionar alerta** (ou use a
   condição de "BOKK subindo / cor verde" que você já usa no MNQ).
3. **Once Per Bar Close**.
4. Em **Webhook URL**, cole (exemplo BTC 5m):
   ```
   https://web-production-77454.up.railway.app/verde/bokk/BTC/5m
   ```
5. Em **Mensagem**, cole exatamente:
   ```json
   {"signal":"green"}
   ```

### Alerta 2 — BOKK ficou VERMELHO
Igual ao de cima, **mesma URL**, mudando só a mensagem:
```json
{"signal":"red"}
```

> 💡 É o mesmo padrão das suas fotos do MNQ (`/verde/bokk/MNQ` com
> `{"signal":"red"}`), só trocando `MNQ` por `<MOEDA>/<TF>`.

---

## 5. Configurar o BS Detector — 1 alerta por gráfico (helper v4)

Para o Histograma + Plot 1/2/3 eu preparei um **helper** que junta tudo em
**um único alerta** (em vez de 4). O arquivo é:
`tradingview/bsdet_helper_v4_sniper.pine`.

> **IMPORTANTE — por que o helper mudou.** O Pine (linguagem do TradingView)
> só lê o **valor** (número) de um plot, **nunca a cor**. O BS Detector pinta
> os plots com 6 cores por uma lógica **interna fechada**, então não dá para
> "ler a cor" dele. A solução é por **aproximação**: o helper agora **calcula
> a cor sozinho, a partir do preço**, usando as mesmas contas do indicador
> aberto **"Trend Meter (by Lij_MC)"** — que muda de cor lateralmente igual
> aos plots do BS Detector. Você escolhe a conta de cada componente e vai
> **calibrando** até o painel do helper ficar igual ao BS Detector.

1. No TradingView, abra **Pine Editor** → cole o conteúdo do arquivo →
   **Add to chart**.
2. Deixe no gráfico **os dois**: o **TSTS BS Detector** e o **BSDET HELPER v4**
   (o BS Detector fica só para você **comparar as cores**).
3. Nos **inputs** do helper, no grupo **"Regra de cor por componente"**,
   escolha para cada um (Histograma, Plot 1, Plot 2, Plot 3) **qual conta**
   usar. As opções são as contas do Trend Meter:
   - **Fast MACD 8/21/5** — histograma do MACD rápido
   - **MACD 12/26/9** — histograma do MACD clássico
   - **RSI 13 > 50** / **RSI 5 > 50**
   - **Mom/Dad Cross** (Top Dog) / **RSI Signal Cross 13/21** / **MA Cross 5/11**
   - **Trend Candles** (Heikin-Ashi)
   - (também há **"Fonte: Positivo"** e **"Fonte: Subindo"** como fallback, se
     você preferir ligar direto num plot pelo campo "Fonte ... opcional")
4. **Calibre olhando o painel** (canto superior direito) **contra o BS Detector**:
   - Troque a conta no menu até a cor de cada componente **bater** com o BS
     Detector na maior parte do tempo.
   - Se a cor sair **trocada** (verde onde devia ser vermelho), marque
     **"inverter cor"** daquele componente.
   - É **aproximação**: não precisa ficar 100% em toda vela — busque o que mais
     se aproxima do comportamento do original.
5. Crie **1 alerta**:
   - Condição: **BSDET HELPER v4 — SNIPER** → **"estado (JSON)"** (a mensagem
     já sai pronta; deixe o campo mensagem como `{{strategy.order.alert_message}}`
     ou apenas confie na mensagem padrão do alerta).
   - **Once Per Bar Close**.
   - **Webhook URL** (exemplo BTC 5m):
     ```
     https://web-production-77454.up.railway.app/bsdet/estado/BTC/5m
     ```

> A mensagem que o helper envia é algo como:
> `{"timeframe":"5m","hist":"red","p1":"green","p2":"green","p3":"green"}`

---

## 6. Quantos alertas no total?

Por gráfico (1 moeda + 1 timeframe): **2 (BOKK)** + **1 (BS Detector)** = **3**.

Você **não precisa** fazer as 30 combinações de uma vez. Sugestão: comece
pelas moedas/timeframes que você mais opera e vá somando. As combinações sem
alerta simplesmente não entram (fail-closed).

---

## 7. Como conferir se está funcionando

Abra no navegador (mostra o estado guardado das cores):
```
https://web-production-77454.up.railway.app/diag
```
Procure o bloco **`confirmacao`** → `estado`. Cada combinação que já recebeu
cor aparece ali (ex.: `BTC_5m`) com a cor de cada componente.

Quando um sinal for **bloqueado**, ele aparece nos registros do dia como
evento `BLOQUEADO`, com o **motivo** (ex.: "cor errada: plot2" ou
"sem dados: histograma, plot1").

---

## 8. Ajustes rápidos (no `config.json`, bloco `confirmacao`)

| O que quero | O que mudar |
|---|---|
| Desligar o gate (voltar a Sniper+RSI) | `"ativa": false` |
| Mudar a tolerância do BOKK | `"bokk_tolerancia_velas": 3` (0 = ignora) |
| Histograma deve ser VERDE na compra | `"histograma": "mesma"` |
| Algum plot deve ser oposto | troque `"mesma"` por `"oposta"` |

---

## 9. Segurança

- O bot continua **100% em MODO SOMBRA**: nenhuma ordem real é enviada. A
  confirmação só decide se a **entrada simulada** acontece ou não.
- Nada foi mexido no Bot RIFLE nem no bot do MNQ.
