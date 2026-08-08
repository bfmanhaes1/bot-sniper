# 📊 STATUS DOS ALERTAS DO BOT-SNIPER

**Última atualização:** 2026-08-08

---

## ✅ ALERTAS CONFIGURADOS

### 1️⃣ Catalisador (10/10 moedas) ✅

| Moeda | Status | Endpoint | Grade/Regra |
|-------|--------|----------|-------------|
| **VIRTUAL** | ✅ Funcionando | `/webhook/VIRTUAL` | A/B/C, R1-R9, 1m relativo |
| **BTC** | ✅ Funcionando | `/webhook/BTC` | A/B/C, R1-R9, 1m relativo |
| **BNB** | ✅ Funcionando | `/webhook/BNB` | A/B/C, R1-R9, 1m relativo |
| **ETH** | ✅ Funcionando | `/webhook/ETH` | A/B/C, R1-R9, 1m relativo |
| **SOL** | ✅ Funcionando | `/webhook/SOL` | A/B/C, R1-R9, 1m relativo |
| **LINK** | ✅ Funcionando | `/webhook/LINK` | A/B/C, R1-R9, 1m relativo |
| **AVAX** | ✅ Funcionando | `/webhook/AVAX` | A/B/C, R1-R9, 1m relativo |
| **NEAR** | ✅ Funcionando | `/webhook/NEAR` | A/B/C, R1-R9, 1m relativo |
| **APT** | ✅ Funcionando | `/webhook/APT` | A/B/C, R1-R9, 1m relativo |
| **BGB** | ✅ Funcionando | `/webhook/BGB` | A/B/C, R1-R9, 1m relativo |

**Payload do catalisador:**
```json
{
  "action": "buy",
  "moeda": "BTC",
  "timeframe": "5m",
  "c30s": "BULL",
  "c1m": "BULL",
  "c5m": "BULL",
  "c15m": "BULL",
  "c1h": "BULL",
  "vwap": "BULL",
  "market": "TRENDING"
}
```

---

### 2️⃣ RSI Cross (0/10 moedas) ❌

| Moeda | Status | Endpoint | Observação |
|-------|--------|----------|------------|
| **VIRTUAL** | ❌ Faltando | `/rsi/VIRTUAL` | Precisa configurar no TradingView |
| **BTC** | ❌ Faltando | `/rsi/BTC` | Precisa configurar no TradingView |
| **BNB** | ❌ Faltando | `/rsi/BNB` | Precisa configurar no TradingView |
| **ETH** | ❌ Faltando | `/rsi/ETH` | Precisa configurar no TradingView |
| **SOL** | ❌ Faltando | `/rsi/SOL` | Precisa configurar no TradingView |
| **LINK** | ❌ Faltando | `/rsi/LINK` | Precisa configurar no TradingView |
| **AVAX** | ❌ Faltando | `/rsi/AVAX` | Precisa configurar no TradingView |
| **NEAR** | ❌ Faltando | `/rsi/NEAR` | Precisa configurar no TradingView |
| **APT** | ❌ Faltando | `/rsi/APT` | Precisa configurar no TradingView |
| **BGB** | ❌ Faltando | `/rsi/BGB` | Precisa configurar no TradingView |

**Payload do RSI:**
```json
{
  "action": "buy",
  "moeda": "BTC",
  "timeframe": "5m",
  "rsi_valor": 52.34
}
```

---

## 🎯 COMO O BOT FUNCIONA

Para uma **entrada** acontecer, o bot precisa de **2 alertas**:

```
1️⃣  Catalisador (TSTS Sniper)
    ↓
    "Sinal recebido, aguardando RSI..."
    ↓
2️⃣  RSI Cross
    ↓
    "RSI confirmou! Processando entrada..."
    ↓
3️⃣  Executor
    ↓
    • Checa guardas (moeda, tf, grade, 1m)
    • Calcula preço, qty, alavancagem
    • [ENTRADA_REAL DRY-RUN] (simulado)
```

---

## 📋 STATUS ATUAL (2026-08-08)

### ✅ O que está funcionando:

- ✅ **Webhooks**: Todos os 10 alertas do catalisador chegando (HTTP 200)
- ✅ **Catalisador**: Grades (A/B/C), regras (R1-R9), 1m relativo
- ✅ **Executor**: ATIVO em modo SOMBRA (dry_run=true)
- ✅ **Guardas do 1m**: Porteiro e modulador funcionando
- ✅ **Proteções**: Anti-stacking, moedas permitidas

### ❌ O que está faltando:

- ❌ **Alertas do RSI**: Nenhum configurado ainda
- ❌ **Entradas simuladas**: Não acontecem sem RSI cross

### ⚠️ Comportamento atual:

Quando um alerta do catalisador chega:
```
Bot responde: "aguardar"
Motivo: "Sinal BUY recebido, mas RSI está UP → SEGURANDO até o RSI cruzar para UP."
```

Isso é **CORRETO** — o bot está esperando a confirmação do RSI.

---

## 🚀 PRÓXIMOS PASSOS

### Passo 1: Configurar alertas do RSI (URGENTE)

Para **CADA uma das 10 moedas**, crie um alerta no TradingView:

1. Abra o gráfico da moeda (ex: BTCUSDT, 5m)
2. Adicione o indicador **"RSI Cross Sniper"**
3. Crie um alerta com condição: **"RSI cruza média"**
4. Configure webhook:
   - **URL**: `https://web-production-77454.up.railway.app/rsi/{MOEDA}`
   - **Payload**: (veja `GUIA_CONFIRMACAO_SNIPER.md`)
5. **"Once Per Bar Close"** ativado

### Passo 2: Testar o fluxo completo

Depois de configurar os RSI:
1. Aguarde um sinal real do TradingView
2. Verifique `/registro` ou `/diag`
3. Procure por: `[ENTRADA_REAL DRY-RUN]`

### Passo 3: Ativar outras moedas no executor

Quando quiser que BTC, ETH, etc. também executem:
1. Edite `config.json`:
   ```json
   "moedas": ["VIRTUAL", "BTC", "ETH", "SOL", ...]
   ```
2. Commit + push
3. Railway faz rebuild

---

## 📖 GUIAS DISPONÍVEIS

- **GUIA_ALERTA_CATALYST_5M.md**: Como criar alertas do catalisador ✅
- **GUIA_CONFIRMACAO_SNIPER.md**: Como criar alertas do RSI ❌ (FAZER)
- **GUIA_LOGS_EXECUTOR_SOMBRA.md**: Como interpretar logs DRY-RUN
- **test_todas_moedas.py**: Script de teste automático

---

## 🔗 Links Úteis

| Endpoint | URL |
|----------|-----|
| Status | https://web-production-77454.up.railway.app/ |
| Diagnóstico | https://web-production-77454.up.railway.app/diag |
| Logs recentes | https://web-production-77454.up.railway.app/registro |
| Resumo | https://web-production-77454.up.railway.app/resumo |
| Teste c1m | https://web-production-77454.up.railway.app/test_c1m |

---

## ✅ CHECKLIST DE ATIVAÇÃO

- [x] Executor ativado em modo sombra (dry_run=true)
- [x] Alertas do catalisador configurados (10/10 moedas)
- [ ] **Alertas do RSI configurados (0/10 moedas)** ← VOCÊ ESTÁ AQUI
- [ ] Testar fluxo completo (catalisador + RSI)
- [ ] Coletar dados por alguns dias
- [ ] Analisar resultados
- [ ] Decidir se ativa modo REAL (dry_run=false)

---

**Última validação:** Script `test_todas_moedas.py` executado com sucesso — 10/10 webhooks do catalisador funcionando.
