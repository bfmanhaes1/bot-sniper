# 📋 Cola Rápida — Alertas Bot SNIPER

Guia ultra-resumido para copiar e colar ao configurar os alertas.

---

## 🌐 URL base

```
https://web-production-77454.up.railway.app
```

---

## 🎯 Templates de URL

### Alerta TSTS Sniper (linha rosa × azul)
```
https://web-production-77454.up.railway.app/webhook/BTC
https://web-production-77454.up.railway.app/webhook/BNB
https://web-production-77454.up.railway.app/webhook/ETH
https://web-production-77454.up.railway.app/webhook/SOL
https://web-production-77454.up.railway.app/webhook/VIRTUAL
https://web-production-77454.up.railway.app/webhook/LINK
https://web-production-77454.up.railway.app/webhook/AVAX
https://web-production-77454.up.railway.app/webhook/NEAR
https://web-production-77454.up.railway.app/webhook/APT
https://web-production-77454.up.railway.app/webhook/BGB
```

### Alerta RSI
```
https://lh7-us.googleusercontent.com/docsz/AD_4nXe_i3VX1n4dCxcB1letxnv53UW7Qy1pcMfcizwM_Hj-floQbkGfX1fckXAw059wrfsb4VPxA_OAB4U6oA4bH1MQebK0WHUF7IzJ24oXkD6d9l1BKG24WWhBNiBcdnAt2n5hENZ6P9eSU2Nzd_uTfGUDdJlq?key=_fZgaCXNW4lE552Wu9ggPA
https://public.bnbstatic.com/image/pgc/202403/c1bd14cb10d4a1f75fff147903796a21.jpg
https://lh7-us.googleusercontent.com/docsz/AD_4nXeOuZQl8rM6rtZZ6uh2ohILl3MOp4JIcwcf-U9zrY3DYrd6pEW-m0MvnMgEj2qB7P7Zo82g-eIZPc37KmthXyNP18RC08IFr419i0qVhlFXSh-A_ykIUzCoenl2SvV-yXth-0bva-x3yNpp_TVh8aNbDC6x?key=_fZgaCXNW4lE552Wu9ggPA
https://cryptowaves-app.s3.us-east-2.amazonaws.com/heatmap.png
https://pbs.twimg.com/media/G1xkPGDW0AA8rfi?format=jpg&name=medium
https://pbs.twimg.com/media/D91yIB0XoAA4zkq.png
https://s3.tradingview.com/news/image/invezz:8aa19cd6f094b-1d9d0142852d0a67bd1eb393778197cc-resized.webp
https://pbs.twimg.com/media/E1b1Qn2X0AUN3Ec.jpg
https://public.bnbstatic.com/static/content/square/images/86dba5730d364a6c809fbc2a8e8f4079.png
https://img.bgstatic.com/multiLang/image/social/e54cfb12e41b01b5848d7e68a847f5c11735173849420.png
```

---

## 📦 Payloads JSON (copiar e colar)

> ⚠️ **NÃO use `{{plot("RSI")}}` nem `{{strategy.order.action}}`.** Esses placeholders não existem no indicador TSTS Sniper e deixam o JSON quebrado ("Expected '}'"). Use os payloads mínimos abaixo — `action`/`direction` são **fixos** (você já sabe a direção pelo nome do alerta), e `{{interval}}` + `{{close}}` funcionam em qualquer alerta.

### 🟢 TSTS Sniper — Pink × Blue **UP** (compra)
```json
{"action":"buy","timeframe":"{{interval}}","entry":{{close}}}
```

### 🔴 TSTS Sniper — Pink × Blue **DOWN** (venda)
```json
{"action":"sell","timeframe":"{{interval}}","entry":{{close}}}
```

### 🟢 RSI cruza pra **cima**
```json
{"direction":"up","timeframe":"{{interval}}"}
```

### 🔴 RSI cruza pra **baixo**
```json
{"direction":"down","timeframe":"{{interval}}"}
```

---

## ✅ Configuração obrigatória em TODOS os alertas

- ✅ **Trigger:** Once Per Bar Close
- ✅ **Webhook URL:** marcar e preencher
- ✅ **Message:** colar o JSON correto

---

## 🔢 Total de alertas

- **10 moedas** × **3 timeframes** (1m, 5m, 15m) × **3 alertas por TF** (1 TSTS + 2 RSI) = **60 alertas**

Ou, simplificando:
- **6 alertas por moeda** (3 TFs × 2 tipos, sendo o RSI dividido em UP/DOWN)

---

## 📊 Como nomear os alertas (sugestão)

### Padrão:
```
[SNIPER] <MOEDA> <TF> - <TIPO>
```

### Exemplos:
```
[SNIPER] BTC 1m - TSTS
[SNIPER] BTC 1m - RSI UP
[SNIPER] BTC 1m - RSI DOWN
[SNIPER] BTC 5m - TSTS
[SNIPER] BTC 5m - RSI UP
[SNIPER] BTC 5m - RSI DOWN
[SNIPER] BTC 15m - TSTS
[SNIPER] BTC 15m - RSI UP
[SNIPER] BTC 15m - RSI DOWN
```

(Repita para as 10 moedas)

---

## 🧪 Teste rápido

Após criar alguns alertas, acesse:

```
https://web-production-77454.up.railway.app/diag
```

Procure por:
- `total_webhooks_recebidos` → deve estar aumentando
- `ultimos_eventos` → deve listar os webhooks recebidos
- `contadores` → `sinais_tsts` e `rsi_cross` devem subir

Se estiver tudo zero após 10-15 minutos, **revise a configuração dos alertas**.

---

## 🚨 Checklist rápido por alerta

- [ ] Gráfico correto (moeda + TF)?
- [ ] Indicador correto (TSTS Sniper ou RSI)?
- [ ] Condição correta (cruzamento rosa×azul, RSI up/down)?
- [ ] **Once Per Bar Close** ✅?
- [ ] Webhook URL correto (`/webhook/<MOEDA>` ou `/rsi/<MOEDA>`)?
- [ ] Payload JSON correto (copiar/colar do template)?
- [ ] Nome do alerta identificável?

---

**Dica:** configure **uma moeda completa** (6 alertas) primeiro, teste, e depois replique para as outras 9 moedas.
