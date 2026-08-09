# Guia — Janela de Reconciliação (gatilho × catalisador) + Cascata 30s/45s

## O problema que isso resolve (a "race condition")
O **gatilho** (RSI/Sniper) e o **catalisador** chegam ao bot como **webhooks separados**,
cada um com sua latência. Quando o gatilho chega **antes** do catalisador virar a favor:

1. o gate do catalisador ainda está CONTRA → a entrada é **BLOQUEADA**;
2. segundos depois o catalisador atualiza e fica a favor…
3. …mas **ninguém reavalia** o gatilho que já foi jogado fora → **boa entrada perdida**.

Isso explica os casos em que a cascata (30s→45s→1m) já tinha virado e mesmo assim
"não entrou": o catalisador do 5m ainda não tinha chegado no instante do gatilho.

## Como funciona a solução (SÓ NA SOMBRA por enquanto)
Quando um gatilho é **bloqueado pelo catalisador**, o bot agora **guarda** esse gatilho
por uma **janela** (padrão **20 s**). Assim que o **catalisador daquela moeda atualizar**
(chega um webhook em `/catalyst/<MOEDA>`), o bot **reavalia** os gatilhos guardados:

- se o gate **agora libera** → **ENTRA** e grava a **defasagem** (quantos segundos o
  gatilho esperou pelo catalisador);
- se **passou da janela** sem liberar → descarta.

> **Trava de segurança:** `permite_real = false`. Isso significa que as entradas
> reconciliadas ficam **SÓ NA SOMBRA** — **não viram ordem real**, nem no 5m.
> A execução real continua **exatamente como estava** (só 5m, 7 moedas, grades A/B/C).
> O objetivo agora é **MEDIR** quantas boas entradas a reconciliação recupera, sem risco.

## O que olhar nos logs (instrumentação)
Três novos tipos de registro:

| Registro          | Significado |
|-------------------|-------------|
| `RACE_CANDIDATO`  | um gatilho foi bloqueado pelo catalisador e ficou guardado |
| `RECONCILIADO`    | o catalisador virou a favor dentro da janela → **entrou** (tem `defasagem_seg`) |
| `RACE_EXPIRADO`   | passou da janela sem o catalisador virar → descartado |

Com o campo `defasagem_seg` você vê a **defasagem típica** entre os webhooks e pode
ajustar a `janela_seg` (aumentar se aparecerem defasagens maiores).

## Onde ver o estado
`GET /diag` agora traz:

```json
"timeframes": ["30s","45s","1m","5m","15m"],
"reconciliacao": {
  "ativa": true, "janela_seg": 20, "permite_real": false,
  "aguardando_agora": 0, "pendentes": []
}
```

## Cascata 30s → 45s → 1m → 5m (estudo em sombra)
- Os timeframes **30s** e **45s** entraram no monitoramento de **sombra** (estudo da
  cascata e da reconciliação). O catalisador agora aceita e guarda o campo **`c45s`**.
- `simulacao_por_tf` para 30s/45s: TP 0.4% / SL 0.5% (placeholder de micro-scalp — será
  calibrado com o MFE/DD reais coletados).
- **Importante:** a execução real **continua só no 5m**. 30s/45s/1m geram apenas
  simulação/estudo em sombra — nunca viram ordem real.

## O que VOCÊ precisa fazer no TradingView
1. **Reativar os alertas de 1m** (você mencionou que faria).
2. **Criar alertas de catalisador de 30s e 45s** para as 7 moedas
   (SOL, VIRTUAL, AVAX, NEAR, LINK, APT, BNB), apontando para o webhook:

   ```
   https://web-production-77454.up.railway.app/catalyst/<MOEDA>
   ```

   No JSON do alerta, envie o campo do timeframe correspondente, por exemplo:
   - alerta de 30s → `{"c30s": "BULL"}` (ou BEAR/NEUT)
   - alerta de 45s → `{"c45s": "BULL"}`

   Quanto **mais frequentes** os webhooks de catalisador (30s/45s), **mais chances** a
   reconciliação tem de pegar o momento em que o contexto vira a favor dentro da janela.

## Próximo passo (depois de coletar dados)
Deixe rodar alguns dias e olhe os `RECONCILIADO`/`RACE_EXPIRADO` e as `defasagem_seg`.
Com isso decidimos:
- ajustar a `janela_seg` (ex.: 20 → 30 s se as defasagens forem maiores);
- e, só então, avaliar ligar `reconciliacao.permite_real = true` para que entradas
  reconciliadas no 5m também possam virar ordem real.
