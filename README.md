# 🎯 Bot SNIPER — MODO SOMBRA (Multi-Ativo)

Segundo bot de **coleta de dados** para cripto, **100% independente** do Bot RIFLE
(roda em outro repositório, outro Railway, outra URL e grava em `crypto2_logs/`).

Ele recebe os alertas do TradingView do indicador **TSTS Sniper** (o **cruzamento
da linha ROSA com a AZUL**), espera a **confirmação por cruzamento de RSI(14) × média
do RSI(14)**, **SIMULA** a entrada e a saída, e **registra tudo** — mas **NUNCA
envia ordem real para a Bitget**.

O objetivo é rodar **30 dias** e coletar dados para depois descobrir:
- Se a entrada no cruzamento rosa×azul + RSI é boa
- **TP e SL ótimos**, usando o **MFE** (o quanto o preço correu a favor) e o
  **DD/MAE** (o quanto correu contra) de cada trade simulado
- Reverse engineering para construir um indicador próprio

> **Diferença para o Bot RIFLE:** o RIFLE usa o indicador *TSTS Sniper Rifle* e
> estuda 1º/2º/3º cruzamento. O SNIPER usa o *TSTS Sniper* (linha rosa × azul),
> entra de forma **direta** assim que o RSI confirma, e **coleta DD/MFE** para
> calibrar TP/SL. São dois bots separados coletando dados em paralelo.

---

## 🧠 Lógica do SNIPER (como ele decide)

1. Chega o **sinal TSTS Sniper** (cruzamento da **linha rosa com a azul** → buy/sell).
2. O bot exige a **confirmação do RSI**: cruzamento do **RSI(14)** com a **média do
   RSI(14)** no mesmo sentido do sinal.
3. **A confirmação pode já ter acontecido:** o cruzamento do RSI vale se tiver
   ocorrido **até 3 velas antes** do sinal TSTS (janela `require_fresh_cross_bars = 3`).
   - RSI já cruzou a favor nas últimas ≤3 velas → **entrada simulada imediata**.
   - RSI ainda não cruzou → o sinal fica **aguardando**; se o RSI cruzar dentro de
     `pending_timeout_bars` velas, entra; senão o sinal expira.
4. Ao **entrar (simulado)**: registra preço de entrada e cria TP/SL simulados.
5. **Saída simulada** por **TP**, **SL** ou **reversão** (sinal oposto). O P&L é
   calculado para **5x e 10x**.
6. Em cada saída o bot calcula e grava o **MFE** e o **DD** (ver abaixo).

> `analise_ativa = false`: o SNIPER **não** faz o estudo de 1º/2º/3º cruzamento do
> RIFLE. É modelo de **entrada direta** (sinal + RSI confirmado em até 3 velas).

---

## 📈 Coleta de DD e MFE (para calibrar TP/SL)

Para cada trade simulado, ao fechar, o bot registra em `resultado_simulado`:

| Campo | Significado |
|---|---|
| `mfe_pct` | **MFE** — o quanto o preço correu **A FAVOR** (%), o melhor ponto para um TP |
| `dd_pct` | **DD/MAE** — o quanto correu **CONTRA** (%), base para dimensionar o SL |
| `mfe_usdt` / `dd_usdt` | O mesmo em dólares, por alavancagem |
| `high_periodo` / `low_periodo` | Máxima e mínima reais durante o trade |
| `duracao_min` | Duração do trade simulado, em minutos |

Como é calculado: o bot busca os **high/low reais das velas da Bitget** durante o
período do trade. Se a consulta falhar, usa como fallback os extremos observados
nos polls de preço (a cada 5 min). Assim, depois de 30 dias dá para responder:
*"qual TP capturaria a maior parte do MFE?"* e *"qual SL evitaria as reversões sem
cortar trades bons cedo demais?"*.

O **resumo diário no Telegram** já traz **MFE médio/máximo** e **DD médio/máximo**.

---

## 📡 FONTE DOS SINAIS: TradingView (oficial)

O sinal de entrada é o **TSTS Sniper** (linha rosa × azul), um indicador **FECHADO**.
Ele PRECISA vir do TradingView — cada moeda/timeframe tem o seu alerta apontando
para a URL **deste** bot (a do SNIPER, diferente da do RIFLE):

- **Sinal TSTS (rosa×azul)** → `POST https://<url-do-SNIPER>/webhook/<MOEDA>`
- **Cruzamento de RSI** → `POST https://<url-do-SNIPER>/rsi/<MOEDA>`

> Continua sendo **MODO SOMBRA**: nenhuma ordem real é enviada.

### Config relevante (`config.json`)

| Chave | Efeito |
|---|---|
| `aceitar_webhooks` | `true` = o bot **recebe** os alertas do TradingView. |
| `engine.require_fresh_cross_bars` | **3** = aceita o cruzamento de RSI ocorrido em até 3 velas antes do sinal. |
| `engine.analise_ativa` | **false** = entrada direta (sem estudo 1º/2º/3º cruzamento). |
| `engine.pending_timeout_bars` | Quantas velas o sinal fica aguardando o RSI cruzar antes de expirar. |
| `dedup_sinal_segundos` | Ignora sinal idêntico (moeda+TF+ação) repetido dentro dessa janela. |

### ⚠️ Modo autônomo (proxy) — DESLIGADO de propósito

O `autonomous_scanner.py` fica como referência e **não roda** com
`modo_autonomo=false`. **Não ative** durante a coleta.

---

## ⚙️ O que ele monitora (60 combinações)

| Item | Valores |
|---|---|
| **Moedas (10)** | BTC, BNB, ETH, SOL, VIRTUAL, LINK, AVAX, NEAR, APT, BGB |
| **Timeframes (3)** | 1m, 5m, 15m |
| **Alavancagens (2)** | 5x, 10x |
| **Total** | 10 × 3 × 2 = **60 combinações** |

---

## 🛡️ Garantia de MODO SOMBRA

- No `config.json` existe a trava **`"MODO_SOMBRA": true`**.
- O `server.py` **não importa** o cliente de execução da Bitget. Só consulta
  **preço público** (sem credenciais) para avaliar TP/SL e calcular DD/MFE.
- Se `MODO_SOMBRA` for `false`, o servidor **recusa** iniciar. **Nenhuma ordem
  real é enviada em hipótese alguma.**

---

## 📁 Onde ficam os dados (logs)

Um arquivo por dia, na pasta **`crypto2_logs/`** (diferente do RIFLE):

- `crypto_AAAA-MM-DD.json` → lista JSON (para backtest / máquina)
- `crypto_AAAA-MM-DD.md` → tabela Markdown (para leitura humana)

**Tipos de `evento`:** `SINAL`, `AGUARDAR` (segurando até o RSI confirmar),
`ENTRADA` (1 por alavancagem), `SAIDA` (fechamento com `resultado_simulado`,
incluindo **MFE e DD**).

> ⚠️ **O disco do Railway é efêmero.** Por isso o **resumo diário vai para o
> Telegram** (durável). Para histórico garantido, baixe `crypto2_logs/` de tempos
> em tempos (endpoint `/registro`).

---

## 📲 Resumo diário no Telegram

Todo dia às **23:59 UTC**, com:
- Total de sinais por ativo e decisões (entradas / aguardando)
- Performance simulada (WR, P&L 5x e 10x)
- **Excursões: MFE médio/máximo e DD médio/máximo** (para calibrar TP/SL)
- Melhores configurações do dia (por P&L)

---

## 🔌 Endpoints

| Método | Rota | Função |
|---|---|---|
| GET | `/` | Health check + resumo da configuração |
| GET | `/diag` | Diagnóstico: modo sombra, Telegram, contadores, últimos webhooks |
| GET | `/status` | Estado do motor + posições simuladas abertas |
| GET | `/registro?dia=AAAA-MM-DD` | Registros do dia em JSON (padrão: hoje UTC) |
| GET | `/resumo?dia=AAAA-MM-DD&enviar=1` | Gera o resumo; `enviar=1` força o envio ao Telegram |
| POST | `/webhook/<moeda>` | Recebe **sinal TSTS Sniper** (buy/sell) |
| POST | `/rsi/<moeda>` | Recebe **cruzamento de RSI** (up/down) |

---

## 📡 Alertas do TradingView (payloads)

**Sinal TSTS Sniper (rosa×azul)** → `POST https://SEU-APP-SNIPER.up.railway.app/webhook/BTC`
```json
{ "action": "buy", "timeframe": "5m", "rsi": 58.2, "rsi_ma": 52.1, "entry": 60000 }
```
Campos: `action` (buy/sell) **obrigatório**; `timeframe` **obrigatório** (1m/5m/15m);
`rsi`, `rsi_ma`, `entry` opcionais (sem `entry`, usa o preço público).

**Cruzamento de RSI** → `POST https://SEU-APP-SNIPER.up.railway.app/rsi/BTC`
```json
{ "direction": "up", "timeframe": "5m", "rsi": 55.0, "rsi_ma": 50.0 }
```
Campos: `direction` (up/down) **obrigatório**; `timeframe` **obrigatório**.

> Crie **1 par de alertas (sinal + RSI) por moeda e por timeframe**, sempre com
> **"Once Per Bar Close"**. A moeda vai **na URL**; o timeframe vai **no payload**.
> Use a URL do **SNIPER** (não a do RIFLE).

---

## ▶️ Como ATIVAR

1. Confirme no `config.json`: `"MODO_SOMBRA": true`, `bot_id: "BOT-SNIPER"`.
2. Suba num **novo projeto Railway** (o `Procfile` já roda `gunicorn server:app`).
3. Configure a variável **`TELEGRAM_BOT_TOKEN`** (para o resumo diário).
   - **Não precisa** de credenciais da Bitget.
4. Abra `GET /` e `GET /diag` e confirme: `modo_sombra: true`, `bot_id: BOT-SNIPER`,
   `combinacoes: 60`.
5. Configure os alertas do TradingView apontando para os endpoints **deste** bot.

## ⏸️ Como PAUSAR

- **Pausa total:** pare o serviço no Railway (ou remova os alertas no TradingView).
- Como não há ordem real, "pausar" apenas interrompe a **coleta**.

---

## 📦 Arquivos principais

| Arquivo | Função |
|---|---|
| `server.py` | Servidor Flask (webhooks, diagnóstico, threads de fundo) |
| `crypto_shadow.py` | Controlador do modo sombra (simulação, DD/MFE, resumo) |
| `engine.py` | Motor de decisão TSTS + RSI (janela de até 3 velas) |
| `crypto_logger.py` | Registro diário em JSON + Markdown (grava em `crypto2_logs/`) |
| `telegram_bot.py` | Envio do startup e do resumo diário ao Telegram |
| `config.json` | Configuração (moedas, TFs, alavancagens, trava sombra) |
| `crypto2_logs/` | Onde os registros diários são gravados |
