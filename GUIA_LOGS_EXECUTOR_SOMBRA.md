# 📊 GUIA — Logs do Executor Real em Modo Sombra

## O que esperar quando um alerta chegar

Quando o TradingView enviar um alerta que **passar por todos os filtros** (TSTS → RSI → Catalisador → Guardas do Executor), você verá nos logs:

### ✅ ENTRADA SIMULADA (DRY-RUN)

```
[ENTRADA_REAL DRY-RUN] VIRTUAL 5m buy | grade=A regra=R4 1m=FAVOR
  preco=1.2345 margem=$100 alav=10x qty=808.8 (moeda VIRTUAL no config)
  TP=1.2469 (+1.0%) SL=1.2185 (-1.3%)
```

**O que cada campo significa:**

- **`DRY-RUN`**: Simulado, **nenhuma ordem real** foi enviada à Bitget
- **`VIRTUAL 5m buy`**: moeda, timeframe, direção
- **`grade=A`**: grade do catalisador (A/B/C/None)
- **`regra=R4`**: regra aplicada (R1-R9)
- **`1m=FAVOR`**: micro-tendência do 1m (FAVOR/CONTRA/N)
- **`alav=10x`**: alavancagem usada
  - Grade A + 1m FAVOR = **10x** (boost)
  - Grade A + 1m CONTRA/N = **5x** (modulador rebaixou)
  - Grade B = **5x** sempre
  - Grade C + 1m FAVOR = **5x**
- **`qty=808.8`**: quantidade calculada (margem × alav ÷ preço)

---

## 🚫 ENTRADAS BLOQUEADAS

Se um sinal for **bloqueado** por alguma guarda, você verá:

### Exemplo 1: Porteiro do 1m bloqueou

```
[GUARDA] VIRTUAL 5m buy BLOQUEADO: grade C com 1m CONTRA - porteiro bloqueou
```

**Causa:** Grade C só entra com 1m A FAVOR

### Exemplo 2: Grade não permitida

```
[GUARDA] VIRTUAL 5m buy BLOQUEADO: grade None sem regra permitida (regra=R3)
```

**Causa:** Regra R3 não está em `regras_permitidas: [R6, R7]`

### Exemplo 3: Moeda não configurada

```
[GUARDA] BTC 5m buy BLOQUEADO: moeda BTC nao esta em moedas=['VIRTUAL']
```

**Causa:** Só VIRTUAL está ativa no config (você vai adicionar BTC depois)

---

## 📈 ACOMPANHAMENTO DE POSIÇÕES

O bot **não fecha** as posições simuladas automaticamente (isso é só no modo sombra puro do `crypto_shadow.py`). 

Quando você ativar **modo REAL** (`dry_run=false`), o executor:
- Abrirá a ordem com TP/SL na Bitget
- A exchange fechará automaticamente quando bater TP ou SL
- O arquivo `execucao_real_posicoes.json` registra as posições abertas

---

## 🎯 EXEMPLO DE FLUXO COMPLETO

### Alerta do TradingView chega:

```json
{
  "action": "buy",
  "moeda": "VIRTUAL",
  "c30s": "BULL", "c1m": "BULL", "c5m": "BULL",
  "c15m": "BULL", "c1h": "BULL",
  "vwap": "BULL", "market": "TRENDING"
}
```

### Processamento:

1. **TSTS Sniper** → Sinal de cruzamento rosa×azul detectado
2. **RSI Cross** → Confirma que RSI cruzou a média (fresh ≤3 velas)
3. **Catalisador** → Grade **A** (5m+15m+1h a favor), regra **R4**, `relativo.c1m` = **FAVOR**
4. **Executor — Guardas:**
   - ✅ Moeda VIRTUAL está em `moedas: [VIRTUAL]`
   - ✅ Timeframe 5m está em `timeframes: [5m]`
   - ✅ Grade A está em `grades_permitidas: [A,B,C]`
   - ✅ 1m=FAVOR → porteiro **não bloqueia**
   - ✅ Posições abertas < 3
   - ✅ Não tem posição aberta em VIRTUAL
5. **Executor — Alavancagem:**
   - Grade A + 1m FAVOR → **10x** (boost ativado)
6. **Executor — Ordem (simulada):**
   ```
   [ENTRADA_REAL DRY-RUN] VIRTUAL 5m buy | grade=A regra=R4 1m=FAVOR
     preco=1.2345 margem=$100 alav=10x qty=808.8
     TP=1.2469 (+1.0%) SL=1.2185 (-1.3%)
   ```

---

## 🔍 COMO VERIFICAR OS LOGS

### 1. Via Railway (web)

Acesse: https://web-production-77454.up.railway.app/registro

Mostra os últimos eventos em tempo real.

### 2. Via endpoint `/diag`

```bash
curl https://web-production-77454.up.railway.app/diag | jq '.execucao_real_bitget'
```

Mostra status do executor + posições abertas.

### 3. Logs locais (arquivo)

Se configurou um Volume no Railway montado em `/data`:

```
/data/crypto2_logs/crypto_2026-08-08.json  # JSON (máquina)
/data/crypto2_logs/crypto_2026-08-08.md    # Markdown (humano)
```

---

## ⚠️ IMPORTANTE — MODO SOMBRA vs MODO REAL

### MODO SOMBRA (atual: `ativa=true` + `dry_run=true`)

- ✅ Executor processa tudo (TSTS → RSI → Catalisador → Guardas)
- ✅ Calcula preço, alavancagem, quantidade, TP/SL
- ✅ Loga **`[ENTRADA_REAL DRY-RUN]`**
- ❌ **Não envia** nenhuma ordem à Bitget
- ❌ **Não movimenta** dinheiro

### MODO REAL (`ativa=true` + `dry_run=false`)

- ✅ Tudo do modo sombra +
- ✅ **Envia** ordem market para Bitget
- ✅ **Abre** posição alavancada com **dinheiro real**
- ✅ Configura TP/SL automático na exchange
- ✅ Loga **`[ENTRADA_REAL EXECUTADA]`**

---

## 🚀 COMO ATIVAR MODO REAL (quando decidir)

### Passo 1: Ativar dry_run=true primeiro (já está ✅)

- Valide os logs de entrada simulada
- Confirme que os filtros estão funcionando
- Veja se as grades/regras estão corretas

### Passo 2: Quando tiver certeza

1. Edite `config.json`:
   ```json
   "execucao_real": {
     "ativa": true,
     "dry_run": false  // ← MUDA ISSO
   }
   ```

2. Commit + push para o GitHub:
   ```bash
   git add config.json
   git commit -m "ATIVA MODO REAL - dinheiro de verdade"
   git push origin main
   ```

3. Railway faz rebuild automático (2-3 min)

4. Verifique `/diag`:
   ```bash
   curl https://web-production-77454.up.railway.app/diag | jq '.execucao_real_bitget.dry_run'
   # Deve retornar: false
   ```

5. 🎯 **A partir desse momento, toda entrada será REAL na Bitget!**

---

## 📊 ANÁLISE DOS RESULTADOS

Depois de coletar dados em modo sombra por alguns dias/semanas:

1. Veja quantas entradas foram **simuladas** (logs `DRY-RUN`)
2. Veja quantas foram **bloqueadas** por cada guarda
3. Analise se as grades/regras fazem sentido
4. Ajuste `regras_permitidas` se necessário (adicionar R5, R8, etc.)
5. Veja se o porteiro do 1m está bloqueando demais ou de menos

**Quando estiver satisfeito** → ative modo REAL.

---

## ❓ PERGUNTAS FREQUENTES

### O que acontece se eu enviar um alerta de BTC agora?

```
[GUARDA] BTC 5m buy BLOQUEADO: moeda BTC nao esta em moedas=['VIRTUAL']
```

Não faz nada. Só quando você adicionar `"BTC"` em `execucao_real.moedas`.

### O porteiro bloqueia grade A ou B?

**NÃO.** O porteiro só bloqueia:
- Grade **C** quando 1m CONTRA
- Grade **None** (entradas por regra) quando 1m CONTRA

Grade A e B **sempre passam** (recuo no 1m dentro de tendência forte = bom ponto).

### O modulador faz o quê?

Ajusta a alavancagem baseado no 1m:
- Grade A + 1m **FAVOR** → **10x** (boost)
- Grade A + 1m **CONTRA** ou **N** → **5x** (sem boost)
- Grades B e C → sempre **5x**

---

## ✅ CHECKLIST DE VALIDAÇÃO

Antes de ativar modo REAL, confirme:

- [ ] Logs mostram `[ENTRADA_REAL DRY-RUN]` quando esperado
- [ ] Porteiro bloqueou corretamente (grade C + 1m CONTRA)
- [ ] Modulador ajustou alavancagem (A + 1m CONTRA = 5x)
- [ ] Grades A/B/C estão entrando nos momentos certos
- [ ] Regras R6/R7 liberaram entradas boas em grade None
- [ ] Saldo Bitget suficiente (≥ $300 para max 3 posições × $100)
- [ ] **CRUCIAL:** Chaves Bitget regeneradas (sem saque)

---

**Boa coleta de dados! 🚀**
