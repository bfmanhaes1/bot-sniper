# 🚀 Bot SNIPER — Deploy no Railway (Passo a Passo)

Este guia mostra como subir o **Bot SNIPER** no Railway, **100% separado do Bot RIFLE**. Os dois bots ficam em projetos Railway diferentes, URLs diferentes, e gravam logs em diretórios diferentes (`crypto2_logs/` vs. `crypto_logs/`).

---

## ✅ Pré-requisitos

- Conta no GitHub (mesma do Bot RIFLE)
- Conta no Railway (mesma do Bot RIFLE)
- Token do bot do Telegram (pode ser o mesmo dos dois bots; o `bot_label` diferente identifica as mensagens)

---

## 📦 Etapa 1: Criar o repositório `bot-sniper` no GitHub

**⚠️ IMPORTANTE:** O token de acesso usado aqui não tem permissão para criar repositórios automaticamente. Você precisa criar o repositório manualmente uma única vez.

### 1.1 — Acesse o GitHub

Vá em: **https://github.com/new**

### 1.2 — Preencha os dados do repositório

- **Repository name:** `bot-sniper`
- **Description:** `Bot SNIPER (modo sombra): TSTS Sniper linha rosa x azul + RSI ate 3 velas, coleta DD/MFE para TP/SL`
- **Visibilidade:** 🔒 **Private**
- **⚠️ NÃO marque** "Add a README file" (já temos um README pronto)
- **⚠️ NÃO marque** "Add .gitignore" (já temos um .gitignore pronto)

### 1.3 — Clique em **"Create repository"**

O GitHub vai mostrar a página de instruções do repositório vazio. **Deixe essa aba aberta** — você vai precisar do endereço do repositório (exemplo: `https://github.com/bfmanhaes1/bot-sniper.git`).

---

## 🚢 Etapa 2: Fazer o push do código do Bot SNIPER

Agora, **no terminal do Abacus AI Agent** (ou no seu Mac, se preferir), execute:

```bash
cd /home/ubuntu/bot_tsts_sniper
git push -u origin main
```

**Se pedir senha/token:** o remote já está configurado com autenticação. Se ainda assim pedir, use suas credenciais do GitHub.

**Resultado esperado:**
```
Enumerating objects: 45, done.
Counting objects: 100% (45/45), done.
...
To https://github.com/bfmanhaes1/bot-sniper.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

**Confirme:** atualize a página do repositório no GitHub — você deve ver os arquivos do Bot SNIPER (README.md, config.json, server.py, crypto_shadow.py, etc.).

---

## ☁️ Etapa 3: Criar o projeto Railway para o Bot SNIPER

### 3.1 — Acesse o Railway

Vá em: **https://railway.app/new**

### 3.2 — Escolha "Deploy from GitHub repo"

- Clique em **"Deploy from GitHub repo"**.
- Se pedir autorização, clique em **"Configure GitHub App"** e dê acesso ao repositório `bot-sniper`.

### 3.3 — Selecione o repositório

- Procure por **`bfmanhaes1/bot-sniper`** na lista.
- Clique no repositório.

### 3.4 — Configure o projeto

- O Railway vai detectar automaticamente o `Procfile` e começar o build.
- **Aguarde o primeiro deploy** (vai falhar porque faltam as variáveis de ambiente — é esperado).

---

## 🔑 Etapa 4: Configurar as variáveis de ambiente no Railway

No painel do projeto Railway (bot-sniper), vá em **"Variables"** e adicione:

| Nome | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | O token do seu bot do Telegram (ex: `1234567890:ABCD...`) |

**⚠️ NÃO precisa** das credenciais da Bitget (`BITGET_API_KEY`, etc.) — o bot SNIPER só consulta preço público (MODO SOMBRA).

**Salve** as variáveis. O Railway vai fazer um **redeploy automático**.

---

## 🌐 Etapa 5: Gerar a URL pública do Bot SNIPER

### 5.1 — Abra o projeto no Railway

Clique no serviço `bot-sniper` (o card com o nome do repositório).

### 5.2 — Vá em "Settings"

Role até a seção **"Networking"**.

### 5.3 — Clique em "Generate Domain"

O Railway vai criar uma URL pública, algo como:

```
https://bot-sniper-production-XXXX.up.railway.app
```

**⚠️ Anote essa URL** — você vai usá-la nos alertas do TradingView (ela é diferente da URL do Bot RIFLE).

---

## ✅ Etapa 6: Verificar se o Bot SNIPER está rodando

### 6.1 — Acesse a URL raiz (health check)

Abra no navegador:

```
https://bot-sniper-production-XXXX.up.railway.app/
```

**Resultado esperado (JSON):**
```json
{
  "status": "online",
  "bot_id": "BOT-SNIPER",
  "bot_label": "🎯 Bot SNIPER",
  "strategy": "TSTS Sniper + RSI",
  "modo_sombra": true,
  ...
}
```

**Confirme:**
- `bot_id` deve ser **`BOT-SNIPER`** (não `BOT-TSTS-RIFLE` ou outro).
- `modo_sombra` deve ser **`true`**.

### 6.2 — Acesse o endpoint de diagnóstico

Abra:

```
https://bot-sniper-production-XXXX.up.railway.app/diag
```

**Confirme:**
- `telegram_ok: true`
- `combinacoes: 60`
- `moedas: ["BTC", "BNB", "ETH", "SOL", "VIRTUAL", "LINK", "AVAX", "NEAR", "APT", "BGB"]`
- `signal_source: "tsts_sniper_pink_blue_rsi_sombra"`

### 6.3 — Confira o Telegram

Você deve receber a mensagem de startup:

```
🎯 Bot SNIPER conectado com sucesso!

Bot ID: BOT-SNIPER
Estratégia: TSTS Sniper + RSI
Modo: 🕶️ MODO SOMBRA (nenhuma ordem real será enviada)
...
```

**Se não recebeu:** verifique o `TELEGRAM_BOT_TOKEN` nas variáveis do Railway.

---

## 🔔 Etapa 7: Configurar os alertas do TradingView para o Bot SNIPER

⚠️ **ATENÇÃO:** os alertas do Bot SNIPER são **SEPARADOS** dos alertas do Bot RIFLE. Você precisa criar **novos alertas** apontando para a **URL do Bot SNIPER**.

### 7.1 — URL dos webhooks

- **Sinal TSTS Sniper (linha rosa × azul):** `https://bot-sniper-production-XXXX.up.railway.app/webhook/<MOEDA>`
- **Cruzamento de RSI:** `https://bot-sniper-production-XXXX.up.railway.app/rsi/<MOEDA>`

Substitua `<MOEDA>` pelo par (BTC, ETH, SOL, etc.) e `XXXX` pela sua URL do Railway.

### 7.2 — Payload JSON

**Alerta TSTS Sniper (rosa × azul):**
```json
{
  "action": "{{strategy.order.action}}",
  "timeframe": "{{interval}}",
  "rsi": {{plot("RSI")}},
  "rsi_ma": {{plot("RSI_MA")}},
  "entry": {{close}}
}
```

**Alerta de cruzamento de RSI:**
```json
{
  "direction": "up",
  "timeframe": "{{interval}}",
  "rsi": {{plot("RSI")}},
  "rsi_ma": {{plot("RSI_MA")}}
}
```
(Para cruzamento pra baixo, use `"direction": "down"`.)

### 7.3 — Configurações do alerta no TradingView

- **Trigger:** Once Per Bar Close ✅ (obrigatório)
- **Webhook URL:** a URL do Bot SNIPER (veja 7.1)
- **Message:** o JSON do payload (veja 7.2)

**Repita para:**
- Cada moeda (10 moedas)
- Cada timeframe (1m, 5m, 15m)
- Cada tipo de alerta (TSTS + RSI) = **60 alertas no total** (10 × 3 × 2)

---

## ⏸️ Etapa 8: Como pausar / reativar o Bot SNIPER

### Pausar (parar a coleta de dados)

**Opção 1:** Pausar o serviço no Railway
- Vá no painel do Railway → bot-sniper → **"Settings"** → **"Pause"**.

**Opção 2:** Desativar os alertas no TradingView
- Vá no TradingView → Alertas → desmarque os alertas do Bot SNIPER.

### Reativar

- No Railway: clique em **"Resume"**.
- No TradingView: reative os alertas.

---

## 📊 Etapa 9: Acompanhar a coleta de dados

### Resumo diário (Telegram)

Todo dia às **23:59 UTC**, você recebe o resumo com:
- Total de sinais por ativo
- Entradas simuladas / Sinais aguardando RSI
- Performance simulada (WR, P&L 5x e 10x)
- **🎯 Excursões:** MFE médio/máximo (o quanto correu a favor) e DD médio/máximo (o quanto correu contra) — base para calibrar TP e SL.

### Logs diários (endpoint)

```
https://bot-sniper-production-XXXX.up.railway.app/registro?dia=2026-07-28
```

Retorna o JSON dos registros do dia (SINAL, ENTRADA, SAIDA). Para ver o resumo:

```
https://bot-sniper-production-XXXX.up.railway.app/resumo?dia=2026-07-28
```

---

## ⚠️ Diferenças entre Bot RIFLE e Bot SNIPER

| Item | Bot RIFLE | Bot SNIPER |
|---|---|---|
| Indicador TSTS | **Sniper Rifle** | **Sniper** (linha rosa × azul) |
| Estudo de cruzamento | 1º/2º/3º cruzamento (analisa) | Entrada **direta** (sem estudo) |
| Janela de confirmação | RSI em até 3 velas antes | RSI em até 3 velas antes (igual) |
| Coleta de DD/MFE | ❌ Não | ✅ **Sim** (high/low das velas reais) |
| Logs | `crypto_logs/` | `crypto2_logs/` |
| URL Railway | `web-production-ed705...` | `bot-sniper-production-XXXX...` |
| Repositório GitHub | `bot-wf-optimized` | `bot-sniper` |

**Ambos os bots:**
- MODO SOMBRA: nenhuma ordem real é enviada.
- Reversão ativa: sinal oposto fecha a posição simulada e abre a nova (flip).
- 60 combinações (10 moedas × 3 TFs × 2 alavancagens).

---

## ❓ Dúvidas frequentes

### O Bot SNIPER vai interferir com o Bot RIFLE?

**Não.** São dois projetos Railway separados, URLs separadas, logs separados (`crypto2_logs/` vs. `crypto_logs/`). Você precisa criar alertas TradingView separados para cada um.

### Posso usar o mesmo `TELEGRAM_BOT_TOKEN` nos dois bots?

**Sim.** O `bot_label` diferente (`🎯 Bot SNIPER` vs. `🎯 Bot RIFLE`) identifica qual bot enviou a mensagem.

### Como sei qual bot está enviando os alertas?

- No Telegram: veja o `bot_label` na mensagem de startup e no resumo diário.
- No Railway: cada projeto tem seu próprio nome e URL.
- Nos logs: `BOT_ID` é diferente (`BOT-SNIPER` vs. `BOT-TSTS-RIFLE`).

---

## ✅ Checklist final

- [ ] Repositório `bot-sniper` criado no GitHub
- [ ] Código do Bot SNIPER enviado (`git push -u origin main`)
- [ ] Projeto Railway criado e linkado ao repositório `bot-sniper`
- [ ] Variável `TELEGRAM_BOT_TOKEN` configurada no Railway
- [ ] URL pública gerada no Railway
- [ ] Endpoint `/` retorna `bot_id: "BOT-SNIPER"` e `modo_sombra: true`
- [ ] Endpoint `/diag` confirma 60 combinações e Telegram OK
- [ ] Mensagem de startup recebida no Telegram
- [ ] Alertas do TradingView configurados (60 alertas: TSTS + RSI, 10 moedas, 3 TFs)
- [ ] Primeiro resumo diário recebido no Telegram (após 23:59 UTC)

---

**Pronto!** O Bot SNIPER está no ar coletando dados. Após 30 dias, use os dados de **MFE** e **DD** (nos logs `crypto2_logs/`) para calibrar TP e SL.
