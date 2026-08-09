# 📊 Resumo Diário — BOT-SNIPER

## O que é

O bot agora gera **automaticamente** um resumo diário completo com:
- ✅ **Total de ordens** (simuladas + reais)
- ✅ **Breakdown por timeframe** (1m, 5m, 15m, etc)
- ✅ **Win Rate (%)** — porcentagem de vitórias
- ✅ **P&L total** — lucro/prejuízo acumulado (em % e $)
- ✅ **Maior gain e maior loss** — extremos do dia
- ✅ **Posições reais abertas** — quantas ordens $ estão ativas agora

---

## Como funciona

### 🔁 Envio automático ao Telegram
**Todos os dias às 23:59 UTC** (20:59 Brasília), o bot envia automaticamente o resumo completo para o seu Telegram.

Você não precisa fazer nada — é 100% automático! ⚡

---

## Como acessar manualmente

### 1️⃣ **No navegador** (leitura fácil)
Acesse:
```
https://web-production-77454.up.railway.app/resumo?formato=texto
```

Parâmetros opcionais:
- `dia=YYYY-MM-DD` — ver resumo de outro dia (ex: `dia=2026-08-08`)
- Sem `dia` → mostra **hoje** (UTC)

**Exemplo:**
```
https://web-production-77454.up.railway.app/resumo?formato=texto&dia=2026-08-09
```

---

### 2️⃣ **Via API** (JSON estruturado)
Para integrar com scripts ou dashboards:

```bash
# Resumo em JSON (processável)
curl "https://web-production-77454.up.railway.app/resumo" | jq .
```

Retorna:
```json
{
  "dia": "2026-08-09",
  "resumo_html": "<b>RESUMO DIÁRIO — BOT-SNIPER</b>...",
  "enviado_telegram": null
}
```

---

### 3️⃣ **Forçar envio ao Telegram** (manual)
Se quiser enviar o resumo agora (fora do horário):
```
https://web-production-77454.up.railway.app/resumo?enviar=1
```

---

## Exemplo de resumo

```markdown
# 📊 Resumo Diário BOT-SNIPER — 2026-08-08

## Ordens
- **Total de ordens**: 6
- **Fechadas**: 2 (TP/SL)
- **Abertas (shadow)**: 4
- **Reais abertas**: 1

## Por Timeframe
- **5m**: 6 ordens

## Performance (Shadow)
- **Winners**: 0 🟢
- **Losers**: 2 🔴
- **Win Rate**: 0.0%

## P&L (Shadow, %)
- **Total**: -1.60%
- **Maior Gain**: +0.00%
- **Maior Loss**: -0.80%
```

---

## O que cada métrica significa

| Métrica | O que é |
|---------|---------|
| **Total de ordens** | Quantas entradas (simuladas) o bot abriu hoje |
| **Fechadas** | Quantas foram fechadas (atingiram TP/SL ou reversão) |
| **Abertas (shadow)** | Simuladas ainda aguardando fechar |
| **Reais abertas** | Posições com **$ REAL** ativas agora |
| **Por Timeframe** | Quantas ordens em cada TF (1m, 5m, etc) |
| **Winners** | Ordens fechadas com **lucro** 🟢 |
| **Losers** | Ordens fechadas com **prejuízo** 🔴 |
| **Win Rate** | `winners / (winners + losers) × 100%` |
| **P&L total** | Soma de todos os lucros/prejuízos (%) |
| **Maior gain** | Melhor trade do dia |
| **Maior loss** | Pior trade do dia |

---

## Script local (opcional)

Se quiser rodar localmente (sem acessar o Railway):

```bash
cd /home/ubuntu/bot_tsts_sniper
python3 resumo_diario.py 2026-08-09
```

Ou para JSON:
```bash
python3 resumo_diario.py 2026-08-09 json
```

---

## Observações importantes

### 📁 Logs no Railway
Os arquivos `crypto2_logs/*.json` no Railway são **efêmeros** — quando você faz deploy, eles resetam. Então:
- O resumo automático **23:59 UTC** vai capturar os dados do dia.
- Se você fizer deploy no meio do dia, os dados desde o último deploy são perdidos.

### 💾 Logs locais (VM Abacus)
Os logs em `/home/ubuntu/bot_tsts_sniper/crypto2_logs/` **persistem** aqui e têm dados completos desde 07/ago.

---

## Resumo

✅ **Automático**: Todo dia 23:59 UTC no Telegram  
✅ **Manual browser**: `/resumo?formato=texto`  
✅ **API JSON**: `/resumo` (sem formato)  
✅ **Forçar envio**: `/resumo?enviar=1`  
✅ **Script local**: `python3 resumo_diario.py`

🎯 **Objetivo**: ter visibilidade diária das métricas (ordens, TF, WR, P&L) sem esforço!
