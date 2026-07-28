# 🔔 Alertas TradingView — Bot SNIPER (60 alertas)

Guia completo para configurar os alertas do **Bot SNIPER** no TradingView.

---

## 📊 Visão geral

O Bot SNIPER precisa de **60 alertas** no total:

- **10 moedas**: BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB
- **3 timeframes**: 1m, 5m, 15m
- **2 tipos por combinação**:
  1. **Sinal TSTS Sniper** (cruzamento linha rosa × azul) → `/webhook/<MOEDA>`
  2. **Cruzamento de RSI** (RSI × média do RSI) → `/rsi/<MOEDA>`

**Total:** 10 × 3 × 2 = **60 alertas**

---

## 🌐 URL base do Bot SNIPER

```
https://web-production-77454.up.railway.app
```

**⚠️ IMPORTANTE:** esta URL é **diferente** do Bot RIFLE. Não misture os alertas dos dois bots.

---

## 📡 Estrutura dos webhooks

### 1️⃣ Alerta TSTS Sniper (linha rosa × azul)

**Webhook URL:**
```
https://web-production-77454.up.railway.app/webhook/<MOEDA>
```

**Substitua `<MOEDA>` por:** BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB

> ⚠️ **IMPORTANTE — não use `{{plot("RSI")}}` nem `{{strategy.order.action}}`.**
> Esses placeholders **não existem** no indicador TSTS Sniper. Quando o TradingView não os encontra, deixa o campo vazio e o JSON quebra (erro **"Expected '}'"**). Como o TSTS Sniper é um *indicador* (study) e não uma *strategy*, `{{strategy.order.action}}` também fica vazio.
>
> **Solução:** `action` é **fixo** — você já sabe a direção pelo nome do alerta (UP = buy, DOWN = sell). Crie **dois alertas separados** por moeda+TF: um para o cruzamento Pink×Blue **pra cima** e outro **pra baixo**.

**Payload JSON — Pink × Blue UP (compra):**
```json
{"action":"buy","timeframe":"{{interval}}","entry":{{close}}}
```

**Payload JSON — Pink × Blue DOWN (venda):**
```json
{"action":"sell","timeframe":"{{interval}}","entry":{{close}}}
```

**Descrição dos campos:**
- `action` → **fixo** "buy" (alerta UP) ou "sell" (alerta DOWN)
- `timeframe` → `{{interval}}` (placeholder universal — o bot converte automaticamente)
- `entry` → `{{close}}` (preço de fechamento da vela; opcional — se faltar, o bot busca o preço público da Bitget)

**Campos opcionais:** `rsi` e `rsi_ma` **não são necessários** e devem ser omitidos (evita o erro de JSON).

---

### 2️⃣ Alerta de cruzamento de RSI

**Webhook URL:**
```
https://web-production-77454.up.railway.app/rsi/<MOEDA>
```

**Substitua `<MOEDA>` por:** BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB

**Payload JSON (RSI cruza pra cima):**
```json
{"direction":"up","timeframe":"{{interval}}"}
```

**Payload JSON (RSI cruza pra baixo):**
```json
{"direction":"down","timeframe":"{{interval}}"}
```

**Descrição dos campos:**
- `direction` → **fixo** "up" (RSI cruza média pra cima) ou "down" (RSI cruza média pra baixo)
- `timeframe` → `{{interval}}` (placeholder universal)

> ⚠️ **Não inclua `rsi`/`rsi_ma` com `{{plot(...)}}`.** Se o seu indicador de RSI não expuser esses plots com esse nome exato, o campo fica vazio e quebra o JSON. Esses valores são opcionais para o bot.

---

## 🛠️ Passo a passo — Criar um alerta no TradingView

### Exemplo: BTC no timeframe 5m

#### **Alerta 1: TSTS Sniper (linha rosa × azul)**

1. **Abra o gráfico** BTCUSDT no TradingView, timeframe **5m**
2. **Adicione o indicador** "TSTS Sniper" (o que tem a linha rosa e azul)
3. **Clique no relógio** (⏰ Alertas) no menu superior
4. **Clique em "Criar alerta"**
5. **Configure:**
   - **Condição:** selecione o indicador TSTS Sniper → cruzamento da linha rosa × azul
   - **Trigger:** **Once Per Bar Close** ✅ (obrigatório)
   - **Validade:** deixe indefinido ou escolha a data de expiração
6. **Aba "Notifications":**
   - **Desmarque** "Enviar notificação push/email" (se não quiser spam)
   - **Marque** "Webhook URL"
7. **Webhook URL:**
   ```
   https://web-production-77454.up.railway.app/webhook/BTC
   ```
8. **Message (payload JSON):** — para o alerta de cruzamento **pra cima** (compra):
   ```json
   {"action":"buy","timeframe":"{{interval}}","entry":{{close}}}
   ```
   (para o alerta de cruzamento **pra baixo**, troque `"buy"` por `"sell"`)
9. **Nome do alerta (sugestão):**
   ```
   [SNIPER] BTC 5m - TSTS UP
   ```
10. **Clique em "Criar"**

---

#### **Alerta 2: Cruzamento de RSI (pra cima)**

1. **No mesmo gráfico** BTCUSDT 5m
2. **Adicione o indicador** RSI(14) (se ainda não tiver)
3. **Adicione a média do RSI** (SMA ou EMA de 14 períodos sobre o RSI)
4. **Clique em "Criar alerta"**
5. **Configure:**
   - **Condição:** RSI(14) **cruza acima** da média do RSI
   - **Trigger:** **Once Per Bar Close** ✅ (obrigatório)
6. **Webhook URL:**
   ```
   https://web-production-77454.up.railway.app/rsi/BTC
   ```
7. **Message (payload JSON):**
   ```json
   {"direction":"up","timeframe":"{{interval}}"}
   ```
8. **Nome do alerta (sugestão):**
   ```
   [SNIPER] BTC 5m - RSI UP
   ```
9. **Clique em "Criar"**

---

#### **Alerta 3: Cruzamento de RSI (pra baixo)**

1. **No mesmo gráfico** BTCUSDT 5m
2. **Clique em "Criar alerta"**
3. **Configure:**
   - **Condição:** RSI(14) **cruza abaixo** da média do RSI
   - **Trigger:** **Once Per Bar Close** ✅ (obrigatório)
4. **Webhook URL:**
   ```
   https://web-production-77454.up.railway.app/rsi/BTC
   ```
5. **Message (payload JSON):**
   ```json
   {"direction":"down","timeframe":"{{interval}}"}
   ```
6. **Nome do alerta (sugestão):**
   ```
   [SNIPER] BTC 5m - RSI DOWN
   ```
7. **Clique em "Criar"**

---

**Resultado:** você criou **3 alertas** para BTC no timeframe 5m (1 TSTS + 2 RSI).

**Repita o processo para:**
- **Mesma moeda, outros timeframes:** BTC 1m, BTC 15m
- **Outras moedas, todos os TFs:** ETH, SOL, BNB, VIRTUAL, LINK, AVAX, NEAR, APT, BGB (cada uma nos 3 timeframes)

---

## 📋 Checklist completo dos 60 alertas

### BTC (6 alertas)
- [ ] BTC 1m - TSTS Sniper
- [ ] BTC 1m - RSI UP
- [ ] BTC 1m - RSI DOWN
- [ ] BTC 5m - TSTS Sniper
- [ ] BTC 5m - RSI UP
- [ ] BTC 5m - RSI DOWN
- [ ] BTC 15m - TSTS Sniper
- [ ] BTC 15m - RSI UP
- [ ] BTC 15m - RSI DOWN

### BNB (6 alertas)
- [ ] BNB 1m - TSTS Sniper
- [ ] BNB 1m - RSI UP
- [ ] BNB 1m - RSI DOWN
- [ ] BNB 5m - TSTS Sniper
- [ ] BNB 5m - RSI UP
- [ ] BNB 5m - RSI DOWN
- [ ] BNB 15m - TSTS Sniper
- [ ] BNB 15m - RSI UP
- [ ] BNB 15m - RSI DOWN

### ETH (6 alertas)
- [ ] ETH 1m - TSTS Sniper
- [ ] ETH 1m - RSI UP
- [ ] ETH 1m - RSI DOWN
- [ ] ETH 5m - TSTS Sniper
- [ ] ETH 5m - RSI UP
- [ ] ETH 5m - RSI DOWN
- [ ] ETH 15m - TSTS Sniper
- [ ] ETH 15m - RSI UP
- [ ] ETH 15m - RSI DOWN

### SOL (6 alertas)
- [ ] SOL 1m - TSTS Sniper
- [ ] SOL 1m - RSI UP
- [ ] SOL 1m - RSI DOWN
- [ ] SOL 5m - TSTS Sniper
- [ ] SOL 5m - RSI UP
- [ ] SOL 5m - RSI DOWN
- [ ] SOL 15m - TSTS Sniper
- [ ] SOL 15m - RSI UP
- [ ] SOL 15m - RSI DOWN

### VIRTUAL (6 alertas)
- [ ] VIRTUAL 1m - TSTS Sniper
- [ ] VIRTUAL 1m - RSI UP
- [ ] VIRTUAL 1m - RSI DOWN
- [ ] VIRTUAL 5m - TSTS Sniper
- [ ] VIRTUAL 5m - RSI UP
- [ ] VIRTUAL 5m - RSI DOWN
- [ ] VIRTUAL 15m - TSTS Sniper
- [ ] VIRTUAL 15m - RSI UP
- [ ] VIRTUAL 15m - RSI DOWN

### LINK (6 alertas)
- [ ] LINK 1m - TSTS Sniper
- [ ] LINK 1m - RSI UP
- [ ] LINK 1m - RSI DOWN
- [ ] LINK 5m - TSTS Sniper
- [ ] LINK 5m - RSI UP
- [ ] LINK 5m - RSI DOWN
- [ ] LINK 15m - TSTS Sniper
- [ ] LINK 15m - RSI UP
- [ ] LINK 15m - RSI DOWN

### AVAX (6 alertas)
- [ ] AVAX 1m - TSTS Sniper
- [ ] AVAX 1m - RSI UP
- [ ] AVAX 1m - RSI DOWN
- [ ] AVAX 5m - TSTS Sniper
- [ ] AVAX 5m - RSI UP
- [ ] AVAX 5m - RSI DOWN
- [ ] AVAX 15m - TSTS Sniper
- [ ] AVAX 15m - RSI UP
- [ ] AVAX 15m - RSI DOWN

### NEAR (6 alertas)
- [ ] NEAR 1m - TSTS Sniper
- [ ] NEAR 1m - RSI UP
- [ ] NEAR 1m - RSI DOWN
- [ ] NEAR 5m - TSTS Sniper
- [ ] NEAR 5m - RSI UP
- [ ] NEAR 5m - RSI DOWN
- [ ] NEAR 15m - TSTS Sniper
- [ ] NEAR 15m - RSI UP
- [ ] NEAR 15m - RSI DOWN

### APT (6 alertas)
- [ ] APT 1m - TSTS Sniper
- [ ] APT 1m - RSI UP
- [ ] APT 1m - RSI DOWN
- [ ] APT 5m - TSTS Sniper
- [ ] APT 5m - RSI UP
- [ ] APT 5m - RSI DOWN
- [ ] APT 15m - TSTS Sniper
- [ ] APT 15m - RSI UP
- [ ] APT 15m - RSI DOWN

### BGB (6 alertas)
- [ ] BGB 1m - TSTS Sniper
- [ ] BGB 1m - RSI UP
- [ ] BGB 1m - RSI DOWN
- [ ] BGB 5m - TSTS Sniper
- [ ] BGB 5m - RSI UP
- [ ] BGB 5m - RSI DOWN
- [ ] BGB 15m - TSTS Sniper
- [ ] BGB 15m - RSI UP
- [ ] BGB 15m - RSI DOWN

---

## ✅ Como testar se os alertas estão funcionando

### 1. Acesse o endpoint de diagnóstico:

```
https://web-production-77454.up.railway.app/diag
```

### 2. Procure a seção `ultimos_eventos`:

Se os alertas estão chegando, você verá algo como:

```json
"ultimos_eventos": [
  {
    "moeda": "BTC",
    "tf": "5",
    "note": "webhook_tsts",
    "action": "buy",
    "time": "2026-07-28T02:00:00+00:00"
  },
  {
    "moeda": "BTC",
    "tf": "5",
    "note": "webhook_rsi",
    "direction": "up",
    "time": "2026-07-28T02:01:00+00:00"
  }
]
```

### 3. Contadores:

```json
"contadores": {
  "sinais_tsts": 10,
  "rsi_cross": 15,
  "entradas_simuladas": 3
}
```

Se os números estiverem subindo, ✅ **os alertas estão funcionando!**

---

## 🚨 Erros comuns e soluções

### ❌ Erro: `"error": "ação (buy/sell) ausente/inválida"`

**Causa:** o payload JSON do alerta TSTS não está enviando o campo `action` corretamente.

**Solução:** verifique se o indicador TSTS Sniper está gerando `{{strategy.order.action}}`. Se não estiver, use:
```json
{
  "action": "buy",
  "timeframe": "{{interval}}"
}
```
E configure alertas separados para BUY e SELL.

---

### ❌ Erro: `"error": "moeda não configurada"`

**Causa:** a moeda na URL do webhook não está na lista do bot.

**Solução:** verifique se a moeda está correta (BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB) e se está em **MAIÚSCULAS**.

---

### ❌ Alerta não dispara

**Causa:** configuração "Once Per Bar Close" não está marcada.

**Solução:** edite o alerta e marque **"Once Per Bar Close"** ✅. Sem essa opção, o alerta pode disparar várias vezes por vela (flood).

---

### ❌ Webhook não chega ao bot

**Causa:** URL do webhook está incorreta ou a URL do Railway mudou.

**Solução:** confirme a URL base no Railway:
1. Acesse o projeto `bot-sniper` no Railway
2. Vá em "Settings" → "Networking"
3. Copie a URL pública gerada
4. Atualize todos os alertas com a nova URL

---

## 🔄 Diferenças entre Bot RIFLE e Bot SNIPER

| Item | Bot RIFLE | Bot SNIPER |
|---|---|---|
| **URL** | `web-production-ed705.up.railway.app` | `web-production-77454.up.railway.app` |
| **Indicador TSTS** | Sniper **Rifle** | Sniper (rosa × azul) |
| **Alertas** | Separados (36 alertas) | Separados (60 alertas) |
| **Timeframes** | 1m, 5m, 15m | 1m, 5m, 15m (igual) |
| **Moedas** | 6 moedas | **10 moedas** |

**⚠️ IMPORTANTE:** os alertas dos dois bots são **SEPARADOS**. Cada alerta deve apontar para a URL correta do bot correspondente.

---

## 📞 Suporte

- **Problemas com payload JSON:** verifique se todos os campos obrigatórios estão presentes (`action` para TSTS, `direction` para RSI, `timeframe` sempre).
- **Bot não recebe alertas:** acesse `/diag` e verifique se `total_webhooks_recebidos` está aumentando.
- **Dúvidas sobre setup:** consulte `ETAPA1_DEPLOY_RAILWAY.md` e `REFERENCIA_RAPIDA.md`.

---

**Boa sorte com os alertas!** 🎯 Após configurá-los, o Bot SNIPER vai começar a coletar dados dos 60 pares automaticamente.
