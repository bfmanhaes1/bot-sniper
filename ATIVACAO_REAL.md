# 🔴 ATIVAÇÃO MODO REAL — BOT-SNIPER

**Data de ativação:** 08/08/2026  
**Commit:** 7ed034c  
**Status:** ✅ **ATIVO COM DINHEIRO REAL**

---

## ⚙️ CONFIGURAÇÃO FINAL

### 💰 Capital e Margem

| Item | Valor |
|------|-------|
| **Capital total** | $300.00 USDT |
| **Margem por ordem** | $70.00 USDT |
| **Máximo posições simultâneas** | 2 |
| **Capital máximo usado** | $140.00 (2 × $70) |
| **Buffer de segurança** | $160.00 (53% livre) |

### 🪙 Moedas Ativas

| Moeda | Símbolo | Liquidez | Perfil |
|-------|---------|----------|--------|
| **BTC** | BTCUSDT | Máxima | Base obrigatória |
| **ETH** | ETHUSDT | Alta | Diversificação |
| **SOL** | SOLUSDT | Alta | Volatilidade/potencial |
| **VIRTUAL** | VIRTUALUSDT | Média | Monitoramento contínuo |

**Total:** 4 moedas, máximo 2 abertas simultaneamente.

### 📊 Timeframe e Alavancagem

- **Timeframe:** 5m apenas
- **Alavancagem base:** 5x (todas as grades)
- **Alavancagem grade A:** 10x (contexto forte)
- **Tipo de margem:** Isolated (USDT-FUTURES)

### 🛡️ Guardas de Entrada

#### Grades Permitidas
- ✅ **Grade A**: 5m+15m+1h alinhados (10x)
- ✅ **Grade B**: 5m+15m alinhados, 1h neutro (5x)
- ✅ **Grade C**: 5m alinhado, 1h contra (5x, **trava 1m obrigatória**)

#### Regras Permitidas (Grade None)
- ✅ **R6**: 5m+1h a favor, 15m neutro
- ✅ **R7**: Só 5m a favor (15m e 1h neutros)

#### Micro-Tendência 1m (Ativa)
- **Porteiro:** Bloqueia C/None quando 1m está CONTRA
- **Modulador:** 1m CONTRA remove boost 10x do grade A (volta p/ 5x)
- **Grade C:** Só entra com 1m A FAVOR

### 📍 Take Profit / Stop Loss (5m)

| Timeframe | TP | SL | TP real (após taxas) | WR mín breakeven |
|-----------|----|----|---------------------|------------------|
| **5m** | 0.8% | 1.1% | 0.68% | 64.2% |

> Valores já incluem margem para taxas Bitget (0.12% entry+exit).

---

## 📋 CHECKLIST DE SEGURANÇA

### ✅ Pré-Ativação

- [x] Credenciais Bitget válidas
- [x] Saldo disponível: $300.65 USDT
- [x] Alertas TradingView configurados (10 moedas × catalisador)
- [x] Alertas RSI configurados (10 moedas × UP+DOWN)
- [x] Fluxo end-to-end validado (Sniper→RSI→entrada)

### ✅ Ativação

- [x] `config.json` atualizado (commit 7ed034c)
- [x] Push para GitHub bem-sucedido
- [x] Railway rebuild completo
- [x] `/diag` confirma: `ativa=true`, `dry_run=false`
- [x] Moedas ativas: BTC, ETH, SOL, VIRTUAL
- [x] Margem por ordem: $70

### 🔍 Pós-Ativação (MONITORAR)

- [ ] **Primeira entrada real** → verificar execução, TP/SL, alavancagem
- [ ] **Telegram:** mensagens `[ENTRADA_REAL AO VIVO]` chegando
- [ ] **Bitget:** posições abertas com margem $70, SL/TP corretos
- [ ] **Nenhuma duplicação:** BTC/ETH/SOL/VIRTUAL só no BOT-SNIPER
- [ ] **Revisar após 3 dias:** win rate, deslizes, ajustes necessários

---

## 🚨 MONITORAMENTO ATIVO

### 📱 Telegram

Você receberá notificações assim:

```
[EXEC-REAL AO VIVO] ENTRADA LONG BTC 5m @ 95234.50 | 5x | margem $70
(notional $350) | qty 0.00367 | TP 95995.58 SL 94186.55 | grade A regra None
| ordem 1234567890
```

**O que verificar:**
- ✅ Margem = $70
- ✅ Alavancagem correta (5x ou 10x conforme grade)
- ✅ TP/SL dentro do esperado (0.8%/1.1%)
- ✅ Moeda está em [BTC, ETH, SOL, VIRTUAL]

### 🌐 Endpoints de Diagnóstico

| Endpoint | URL | O que mostra |
|----------|-----|--------------|
| **Status** | https://web-production-77454.up.railway.app/ | Saúde geral do bot |
| **Diagnóstico** | https://web-production-77454.up.railway.app/diag | Config executor, credenciais, contadores |
| **Logs recentes** | https://web-production-77454.up.railway.app/registro | Últimos eventos registrados |
| **Resumo** | https://web-production-77454.up.railway.app/resumo | Performance diária |

### 🔄 Bitget

Acesse [Bitget Futures](https://www.bitget.com/pt-BR/futures/usdt) e verifique:

- **Posições abertas** → devem ter margem isolada $70
- **Histórico de ordens** → confirme que o bot está operando
- **TP/SL ativos** → todas as posições devem ter TP e SL configurados

---

## ⚠️ REGRAS DE OURO

### 1️⃣ **NÃO opere estas 4 moedas manualmente**

- BTC, ETH, SOL, VIRTUAL estão **EXCLUSIVAS** do BOT-SNIPER
- Operação manual = conflito + risco de duplicação

### 2️⃣ **Monitore as primeiras 5 entradas de perto**

- Confirme execução correta
- Verifique TP/SL aplicado
- Acompanhe fechamento (win ou loss)

### 3️⃣ **Se algo estiver errado, PAUSE IMEDIATAMENTE**

Edite `config.json` no GitHub:
```json
"execucao_real": {
  "ativa": false,  ← DESLIGA EXECUTOR
  ...
}
```
Commit + push → Railway rebuild → bot volta ao modo sombra.

### 4️⃣ **Revise o desempenho semanalmente**

- **Win rate:** deve estar acima de 64% (breakeven 5m)
- **Drawdown:** não deve superar $50 (25% do capital usado)
- **Slippage:** compare preço entrada real vs. alerta TradingView

---

## 📊 EXPECTATIVAS REALISTAS

### Com WR 65% (conservador)

| Métrica | Valor |
|---------|-------|
| **Trades/dia** | 2-5 (depende dos sinais) |
| **Capital usado** | $70-$140 (1-2 posições) |
| **Lucro médio por win** | $2.38 (0.68% × $70 × 5x) |
| **Perda média por loss** | $3.85 (1.1% × $70 × 5x) |
| **Resultado líquido/dia** | $0-$5 (estimativa) |

> **Atenção:** Primeiras semanas são de **coleta de dados reais**. Não espere lucros imediatos. Foco: validar que o bot executa corretamente e que o sistema está estável.

---

## 🆘 SUPORTE

### Se algo der errado:

1. **Pause o executor** (config.json → `ativa: false`)
2. **Verifique os logs** (`/registro`, `/diag`)
3. **Telegram:** `[ERRO]` ou `[BLOQUEIO]` indicam problemas
4. **Bitget:** feche posições manualmente se necessário
5. **Entre em contato** com o desenvolvedor (você tem os logs)

---

## 📝 CHANGELOG

### 2026-08-08 — Ativação Inicial

- ✅ Modo real ativado (`dry_run: false`)
- ✅ 4 moedas: BTC, ETH, SOL, VIRTUAL
- ✅ Margem reduzida: $100 → $70
- ✅ Max posições: 3 → 2
- ✅ Guardas 1m (porteiro + modulador) ativos
- ✅ Grades A/B/C + regras R6/R7 configuradas
- ✅ Alertas TradingView + RSI validados end-to-end

---

## ✅ PRÓXIMOS PASSOS

1. **Agora:** Aguardar primeiro sinal real do TradingView
2. **Primeiras 24h:** Monitorar execuções de perto (Telegram + Bitget)
3. **Após 3 dias:** Revisar win rate, ajustar TP/SL se necessário
4. **Após 1 semana:** Decidir se adiciona mais moedas (BNB, LINK, etc.)
5. **Após 2 semanas:** Avaliar se sobe alavancagem base de 5x para 7x

---

**🎯 BOT-SNIPER ESTÁ ATIVO E OPERACIONAL!**

Boa sorte! 🚀
