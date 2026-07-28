# 📋 Bot SNIPER — Referência Rápida

Guia de consulta rápida para o Bot SNIPER (modo sombra).

---

## 🆔 Identificação

| Item | Valor |
|---|---|
| Bot ID | `BOT-SNIPER` |
| Label | `🎯 Bot SNIPER` |
| Estratégia | `TSTS Sniper + RSI` |
| Repositório GitHub | `bfmanhaes1/bot-sniper` |
| Railway URL | `https://bot-sniper-production-XXXX.up.railway.app` |
| Logs | `crypto2_logs/` (separado do Bot RIFLE) |

---

## 🎯 Lógica de entrada (modelo SNIPER)

1. **Sinal TSTS Sniper** chega (cruzamento da **linha rosa × azul** → buy/sell).
2. Espera **confirmação do RSI**: cruzamento do **RSI(14) × média do RSI(14)** na mesma direção.
3. **Janela de confirmação:** o cruzamento do RSI vale se ocorreu **em até 3 velas antes** do sinal TSTS.
   - RSI já cruzou a favor nas últimas ≤3 velas → **entrada simulada imediata**.
   - RSI ainda não cruzou → sinal fica **aguardando** até o RSI cruzar (ou expirar).
4. **Entrada direta:** sem estudo de 1º/2º/3º cruzamento (diferente do Bot RIFLE).
5. **Saída simulada:** TP, SL ou reversão (sinal oposto fecha a posição e abre a nova).

---

## 📊 O que o Bot SNIPER coleta

### Dados tradicionais (igual ao Bot RIFLE)

- Sinais TSTS recebidos
- Cruzamentos de RSI
- Decisões (entrar / aguardar)
- Entradas e saídas simuladas
- P&L por alavancagem (5x, 10x)

### 🎯 Dados novos (exclusivos do Bot SNIPER)

Em cada saída, grava em `resultado_simulado`:

| Campo | Significado |
|---|---|
| `mfe_pct` | **MFE** — o quanto o preço correu **A FAVOR** (%), melhor ponto para TP |
| `dd_pct` | **DD/MAE** — o quanto correu **CONTRA** (%), base para dimensionar SL |
| `mfe_usdt` / `dd_usdt` | O mesmo em dólares, por alavancagem |
| `high_periodo` / `low_periodo` | Máxima e mínima reais durante o trade (velas da Bitget) |
| `duracao_min` | Duração do trade simulado, em minutos |

**Uso:** após 30 dias, analise a distribuição de MFE e DD para responder:
- *"Qual TP capturaria a maior parte do MFE sem cortar trades bons cedo demais?"*
- *"Qual SL evitaria as reversões sem cortar por volatilidade normal?"*

---

## 🔌 Endpoints

| Método | Rota | Função |
|---|---|---|
| GET | `/` | Health check: `bot_id`, `modo_sombra`, combinações |
| GET | `/diag` | Diagnóstico: Telegram, contadores, últimos eventos |
| GET | `/status` | Estado do motor + posições simuladas abertas |
| GET | `/registro?dia=AAAA-MM-DD` | Registros do dia em JSON (padrão: hoje UTC) |
| GET | `/resumo?dia=AAAA-MM-DD&enviar=1` | Gera resumo; `enviar=1` envia ao Telegram |
| POST | `/webhook/<moeda>` | Recebe sinal TSTS Sniper (linha rosa × azul) |
| POST | `/rsi/<moeda>` | Recebe cruzamento de RSI (up/down) |

**Exemplo:**
```bash
curl https://bot-sniper-production-XXXX.up.railway.app/diag
```

---

## 📡 Payloads dos alertas TradingView

### Sinal TSTS Sniper (linha rosa × azul)

**Webhook URL:** `https://bot-sniper-production-XXXX.up.railway.app/webhook/BTC`

**JSON:**
```json
{
  "action": "buy",
  "timeframe": "5m",
  "rsi": 58.2,
  "rsi_ma": 52.1,
  "entry": 60000
}
```

**Campos:**
- `action` (buy/sell) — **obrigatório**
- `timeframe` (1m/5m/15m) — **obrigatório**
- `rsi`, `rsi_ma`, `entry` — opcionais (se `entry` faltar, usa o preço público)

### Cruzamento de RSI

**Webhook URL:** `https://bot-sniper-production-XXXX.up.railway.app/rsi/BTC`

**JSON (RSI cruza pra cima):**
```json
{
  "direction": "up",
  "timeframe": "5m",
  "rsi": 55.0,
  "rsi_ma": 50.0
}
```

**JSON (RSI cruza pra baixo):**
```json
{
  "direction": "down",
  "timeframe": "5m",
  "rsi": 45.0,
  "rsi_ma": 50.0
}
```

**Campos:**
- `direction` (up/down) — **obrigatório**
- `timeframe` (1m/5m/15m) — **obrigatório**
- `rsi`, `rsi_ma` — opcionais

**⚠️ IMPORTANTE:**
- Crie **1 par de alertas (TSTS + RSI) por moeda e por timeframe**.
- A moeda vai **na URL** (`/webhook/BTC`, `/webhook/ETH`, ...).
- O timeframe vai **no payload JSON**.
- Configuração obrigatória: **"Once Per Bar Close"** ✅

---

## 🕒 Resumo diário (Telegram)

Todo dia às **23:59 UTC**, recebe:

```
🕶️ RESUMO DIÁRIO — Modo Sombra Crypto
📅 28/Jul/2026 (UTC)

📊 Atividade
• Sinais TSTS recebidos: 15
• Entradas simuladas: 8
• Sinais aguardando RSI: 2
• Trades simulados fechados: 6

📈 Performance simulada
• Vitórias/Derrotas: 4/2 (WR 66.7%)
• P&L 5x: 🟢 $18.50
• P&L 10x: 🟢 $37.00

🎯 Excursões (para calibrar TP/SL)
• MFE médio (correu a favor): 1.85%
• MFE máximo: 3.20%
• DD médio (correu contra): 0.65%
• DD máximo: 1.10%

🪙 Atividade por moeda
• BTC: 5
• ETH: 3
...
```

---

## 📁 Estrutura dos logs

### Diretório: `crypto2_logs/`

**Arquivos diários:**
- `crypto_AAAA-MM-DD.json` — lista JSON (para scripts/backtest)
- `crypto_AAAA-MM-DD.md` — tabela Markdown (para leitura humana)

**Tipos de evento:**
- `SINAL` — alerta bruto recebido do TradingView
- `AGUARDAR` — sinal segurando até o RSI confirmar
- `ENTRADA` — entrada simulada (1 registro por alavancagem)
- `SAIDA` — fechamento simulado com `resultado_simulado` (**inclui MFE e DD**)

**Campos principais:**
`timestamp`, `hora`, `evento`, `moeda`, `timeframe`, `alavancagem`, `sinal_tsts`, `rsi_valor`, `decisao_agente`, `preco_entrada_simulado`, `preco_saida_simulado`, `resultado_simulado`, `direcao`, `motivo`.

---

## ⚖️ Bot SNIPER vs. Bot RIFLE

| Item | Bot RIFLE | Bot SNIPER |
|---|---|---|
| **Indicador TSTS** | Sniper **Rifle** | Sniper (rosa × azul) |
| **Modelo de entrada** | Estudo 1º/2º/3º cruzamento | Entrada **direta** |
| **Janela RSI** | Até 3 velas antes | Até 3 velas antes (igual) |
| **Coleta DD/MFE** | ❌ Não | ✅ **Sim** |
| **Logs** | `crypto_logs/` | `crypto2_logs/` |
| **Bot ID** | `BOT-TSTS-RIFLE` | `BOT-SNIPER` |
| **Repositório** | `bot-wf-optimized` | `bot-sniper` |
| **Railway URL** | `...ed705...` | `...bot-sniper...` |

**Ambos:**
- MODO SOMBRA: zero ordens reais.
- Reversão ativa (flip).
- 60 combinações (10 moedas × 3 TFs × 2 alavancagens).

---

## 🔧 Manutenção

### Ver estado atual

```bash
curl https://bot-sniper-production-XXXX.up.railway.app/status
```

### Baixar logs do dia

```bash
curl https://bot-sniper-production-XXXX.up.railway.app/registro?dia=2026-07-28 > logs_sniper_2026-07-28.json
```

### Forçar envio do resumo diário

```bash
curl "https://bot-sniper-production-XXXX.up.railway.app/resumo?enviar=1"
```

### Pausar coleta de dados

**Opção 1:** Railway → Settings → Pause
**Opção 2:** TradingView → desativar os alertas do Bot SNIPER

---

## 📞 Suporte

- **README completo:** [README.md](README.md)
- **Deploy:** [ETAPA1_DEPLOY_RAILWAY.md](ETAPA1_DEPLOY_RAILWAY.md)
- **Diferenças RIFLE vs. SNIPER:** esta página, seção "⚖️"

---

**Modo Sombra:** nenhuma ordem real é enviada. Dados salvos em `crypto2_logs/`.
