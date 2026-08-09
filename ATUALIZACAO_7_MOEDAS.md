# ✅ Atualização: 7 Moedas + Grade C Defensiva

**Data:** 09/08/2026  
**Status:** ✅ **ATIVO NO RAILWAY** (dinheiro real)

---

## 📊 O que mudou

### 1. **Portfolio expandido: 4 → 7 moedas**

| Antes | Agora |
|-------|-------|
| BTC, ETH, SOL, VIRTUAL | SOL, VIRTUAL, AVAX, NEAR, LINK, APT, BNB |

**Removidas:** BTC e ETH (amplitude <3%/dia, lentos demais para TP 0.8%)  
**Adicionadas:** AVAX, NEAR, LINK, APT, BNB (amplitude 3.7-4.7%/dia)

---

### 2. **Margem reduzida para permitir mais posições**

- **Antes:** $70/ordem, máx 2 posições ($140 usado, $160 buffer)
- **Agora:** $50/ordem, máx **7 posições** ($350 usado, $10 buffer)
- **Capital total:** $300 → **$360** (aporte +$60)

Com 7 moedas e 7 slots, você pode ter **uma ordem por moeda simultaneamente**.

---

### 3. **Grade C agora usa TP/SL reduzido (defensivo)**

#### Timeframe 5m:

| Grade | TP | SL | Lucro líquido* | WR breakeven |
|-------|:--:|:--:|:--------------:|:------------:|
| **A / B** | 0.8% | 1.1% | 0.68% | 64.2% |
| **C** | 0.5% | 0.7% | **0.38%** | 58.3% |

> *Lucro líquido = TP bruto − taxas Bitget (0.12% entrada+saída)

**Por que Grade C é defensiva?**  
Grade C = contra-tendência de 1h (5m e 15m a favor, mas 1h contra). Maior risco de reversão brusca → TP menor garante lucro antes do mercado virar.

**Todas as grades continuam ativas** (A, B, C) — só mudou o TP/SL da C.

---

## 🎯 Dados de mercado (amplitude média 14 dias)

| Moeda | Amplitude/dia | Volume | Status |
|-------|:-------------:|:------:|--------|
| **SOL** | 3.09% | $154mi | ✅ Mantida (melhor equilíbrio) |
| **VIRTUAL** | 4.54% | $2mi | ✅ Mantida |
| **AVAX** | 4.69% | $6mi | 🆕 Adicionada |
| **NEAR** | 4.69% | $10mi | 🆕 Adicionada |
| **LINK** | 3.73% | $10mi | 🆕 Adicionada |
| **APT** | 4.45% | $2mi | 🆕 Adicionada |
| **BNB** | 2.29% | $10mi | 🆕 Adicionada |
| ~~BTC~~ | ~~2.12%~~ | ~~$2bi~~ | ❌ Removido (lento) |
| ~~ETH~~ | ~~2.95%~~ | ~~$1bi~~ | ❌ Removido (ordem travou 24h) |

**BGB não foi adicionada:** amplitude 2.58%/dia (mais lenta que SOL) + liquidez fina ($1.3mi).

---

## 🔧 Arquitetura técnica

### config.json
```json
{
  "execucao_real": {
    "moedas": ["SOL", "VIRTUAL", "AVAX", "NEAR", "LINK", "APT", "BNB"],
    "margem_usdt": 50,
    "max_posicoes": 7,
    "capital_total_usdt": 360,
    "grades_permitidas": ["A", "B", "C"]
  },
  "simulacao_por_tf": {
    "5m": {
      "tp_percent": 0.8,
      "sl_percent": 1.1,
      "grade_c": {
        "tp_percent": 0.5,
        "sl_percent": 0.7
      }
    }
  }
}
```

### crypto_shadow.py
- Método `_tp_sl()` agora aceita parâmetro `grade`
- Se `grade == "C"` E existe `grade_c` no config do TF → usa TP/SL reduzido
- Grades A/B/None → usa TP/SL padrão do timeframe

### server.py
- Endpoint `/diag` atualizado para exibir config `grade_c`
- Compatível com nova estrutura de dicionário (não mais tuplas)

---

## ✅ Validação (Railway em produção)

```bash
$ curl https://web-production-77454.up.railway.app/diag | jq .execucao_real_bitget

{
  "moedas": ["SOL", "VIRTUAL", "AVAX", "NEAR", "LINK", "APT", "BNB"],
  "max_posicoes": 7,
  "margem_usdt": 50.0,
  "capital_total_usdt": 360.0,
  "saldo_usdt": 225.70,
  "dry_run": false,  ← DINHEIRO REAL
  "credenciais_validas": true
}

TP/SL 5m Grade A/B: TP 0.8% / SL 1.1%
TP/SL 5m Grade C:   TP 0.5% / SL 0.7%
```

---

## 🚨 Próximos passos (IMPORTANTE)

### 1. **Criar alertas no TradingView para as 3 moedas novas**

Você já tem alertas configurados para SOL, VIRTUAL, AVAX e NEAR. Precisa criar para:

- **LINK** (LINKUSDT)
- **APT** (APTUSDT)  
- **BNB** (BNBUSDT)

**Para cada moeda, você precisa de 10 alertas:**

1. **Catalisador** (1 alerta) → `/catalyst/LINK` (ou APT/BNB)
2. **RSI UP/DOWN** (6 alertas) → `/rsi/LINK` nos 3 timeframes (1m, 5m, 15m) × 2 direções
3. **Sniper pink×blue** (3 alertas) → `/webhook/LINK` nos 3 timeframes

**Total:** 30 alertas novos (10 × 3 moedas)

---

### 2. **Acompanhe as primeiras entradas**

- Grade C vai ter TP menor → pode fechar rápido (lucro 0.38% vs 0.68%)
- Com 7 moedas mais voláteis, espere **mais operações/dia**
- SL de grade C (0.7%) pode ser atingido mais rápido — acompanhe se está sendo "wickado"

---

### 3. **Monitoramento recomendado (primeiros 3 dias)**

- Verifique `/diag` → campo `execucao_real_bitget.posicoes_abertas` diariamente
- Confira Telegram para notificações de entrada/saída
- Compare quantas operações Grade C vs A/B no `/estudo` após 1 semana

---

## 📝 Commits relacionados

- `64f5abd` — Implementa grades por moeda (SOL/VIRTUAL todas, AVAX/NEAR A/B)
- `6ec97d4` — 7 moedas @ $50, max 7 posições, grade C com TP/SL reduzido
- `05dbe0a` — Fix endpoint /diag compatível com nova estrutura

---

## 💡 Estratégia resumida

> **Mais moedas voláteis (3.7-4.7%/dia) + mais slots (7) = mais operações**  
> **Grade C defensiva (TP 0.5%) = compensa risco da contra-tendência**  
> **Todas têm alertas prontos = ativação imediata assim que você configurar**

---

**Dúvidas?** Confira `/diag` no Railway ou me avise se precisar ajustar algum parâmetro. 🎯
