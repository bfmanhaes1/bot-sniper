# -*- coding: utf-8 -*-
"""
server.py — Bot Crypto MODO SOMBRA (multi-ativo)
================================================
Servidor Flask que recebe os alertas do TradingView (TSTS Sniper + cruzamentos de
RSI) para 10 moedas x 3 timeframes e, em MODO SOMBRA, apenas DECIDE e SIMULA —
NUNCA envia ordem real para a Bitget.

Fluxo:
  1. TradingView dispara webhook:
        POST /webhook/<moeda>        -> sinal TSTS (buy/sell)
        POST /rsi/<moeda>            -> cruzamento de RSI (up/down)
     (também aceito: /webhook/<moeda> com campo "tipo":"rsi" ou "rsi_cross")
  2. O controlador de sombra decide (entrar/aguardar/analisar 1º-2º-3º cruzamento).
  3. A entrada/saída é SIMULADA (TP/SL fixos ou reversão) e o P&L é calculado
     para 5x e 10x.
  4. TUDO é registrado em crypto_logs/ (JSON + Markdown). Sem Telegram por sinal.
  5. Um resumo diário é enviado ao Telegram às 23:59 UTC.

TRAVA DE SEGURANÇA: se config.MODO_SOMBRA != true, o servidor RECUSA a iniciar a
execução (garante que nunca opere de verdade neste pacote).

Rotas:
  GET  /                 -> health check
  GET  /diag            -> diagnóstico (combinações, contadores, últimos eventos)
  GET  /status          -> estado do motor + posições simuladas abertas
  GET  /registro        -> registros do dia (JSON)
  GET  /resumo          -> texto do resumo diário (e força envio se ?enviar=1)
  POST /webhook/<moeda> -> sinal TSTS (ou RSI, via "tipo")
  POST /rsi/<moeda>     -> cruzamento de RSI

Todos os comentários e mensagens em Português.
"""

import os
import re
import json
import time
import logging
import threading
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Dict, Any

from flask import Flask, request, jsonify

import crypto_logger
from crypto_shadow import CryptoShadowController
from telegram_bot import TelegramNotifier
from autonomous_scanner import AutonomousScanner

# --------------------------------------------------------------------- #
# Caminhos e configuração
# --------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def load_config() -> Dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()

BOT_ID = CONFIG.get("bot_id", "BOT-CRYPTO-SOMBRA")
BOT_LABEL = CONFIG.get("bot_label", "🕶️ Bot Crypto Sombra")
STRATEGY = CONFIG.get("strategy", "TSTS + RSI (Modo Sombra)")
MODO_SOMBRA = bool(CONFIG.get("MODO_SOMBRA", True))
MODO_AUTONOMO = bool(CONFIG.get("modo_autonomo", False))
ACEITAR_WEBHOOKS = bool(CONFIG.get("aceitar_webhooks", True))

# --------------------------------------------------------------------- #
# Logging (console + arquivo rotativo)
# --------------------------------------------------------------------- #
logger = logging.getLogger("crypto_server")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter(f"%(asctime)s [%(levelname)s] [{BOT_ID}] %(name)s: %(message)s")
_file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "trading.log"), maxBytes=5 * 1024 * 1024, backupCount=5
)
_file_handler.setFormatter(_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_fmt)
for h in (_file_handler, _console_handler):
    logger.addHandler(h)
    logging.getLogger("crypto_shadow").addHandler(h)
    logging.getLogger("crypto_logger").addHandler(h)
    logging.getLogger("engine").addHandler(h)
    logging.getLogger("telegram_bot").addHandler(h)
for nome in ("crypto_shadow", "crypto_logger", "engine", "telegram_bot"):
    logging.getLogger(nome).setLevel(logging.INFO)

# --------------------------------------------------------------------- #
# Objetos globais
# --------------------------------------------------------------------- #
notifier = TelegramNotifier(CONFIG["telegram"]["chat_id"], bot_label=BOT_LABEL)
controller = CryptoShadowController(CONFIG, notifier=notifier)
# Scanner autônomo (só é iniciado se modo_autonomo=true — ver start_background_threads).
scanner = AutonomousScanner(controller, CONFIG)

# Buffer de diagnóstico (últimos webhooks) — não persiste.
_recent_events: list = []
_recent_lock = threading.Lock()


def _record_event(moeda: str, note: str, extra: Dict[str, Any] = None) -> None:
    ev = {"time": datetime.now(timezone.utc).isoformat(), "moeda": moeda, "note": note}
    if extra:
        ev.update(extra)
    with _recent_lock:
        _recent_events.append(ev)
        if len(_recent_events) > 40:
            del _recent_events[: len(_recent_events) - 40]


def _parse_payload():
    """
    Extrai o dict do corpo do request.
    Aceita:
      1. JSON puro (para alertas RSI customizáveis)
      2. Formato TSTS Sniper Rifle (JSON com campo "content")
      3. Texto simples do TradingView
    """
    # Primeiro tenta JSON direto
    data = request.get_json(silent=True)
    if data is not None and isinstance(data, dict):
        # Pode ser:
        # A) JSON customizado (RSI) -> retorna direto
        # B) TSTS Sniper com campo "content" -> precisa processar
        
        if "content" in data:
            # FORMATO TSTS SNIPER RIFLE:
            # {"content":"TSTS SNIPER RIFLE: ={\"inputs\":{},...} 5 SS"}
            # Onde: 5 = timeframe (minutos), SS = Short Signal (sell), LS = Long Signal (buy)
            content = str(data.get("content") or "")
            payload = {}
            
            # Extrair símbolo: "symbol":"BITGET:XXXUSDT.P"
            symbol_match = re.search(r'"symbol"\s*:\s*"[^:]*:([A-Z]{3,10}USDT)(?:\.P)?"', content, re.IGNORECASE)
            if symbol_match:
                payload["symbol"] = symbol_match.group(1)
            
            # Extrair timeframe e action do final: " 5 SS" ou " 15 BS"
            # Padrão: dígitos seguidos de um código de sinal
            # BUY: BS, BSC, BSX | SELL: SS, SSC, SSX
            signal_match = re.search(r'(\d+)\s+(BS[CX]?|SS[CX]?)', content, re.IGNORECASE)
            if signal_match:
                tf_num = signal_match.group(1)
                signal_type = signal_match.group(2).upper()
                
                # Timeframe (assumindo minutos)
                payload["timeframe"] = f"{tf_num}m"
                
                # Action: BS/BSC/BSX = Buy Signal, SS/SSC/SSX = Sell Signal
                payload["action"] = "buy" if signal_type.startswith("BS") else "sell"
                payload["signal_type"] = signal_type  # Guardar o tipo exato (BS, SSC, etc.)
            
            if payload:
                payload["_source"] = "tsts_sniper"
                payload["_raw_content"] = content[:300]
                logger.info("TSTS Sniper detectado: %s", json.dumps(payload, ensure_ascii=False))
                return payload
            else:
                logger.warning("TSTS Sniper: campo 'content' presente mas não conseguiu extrair dados: %s", content[:200])
                return None
        
        # Não tem "content" -> é JSON customizado (RSI ou outro)
        return data

    # Não é JSON válido - vem como texto puro
    raw = request.get_data(as_text=True) or ""

    # RESGATE: às vezes o corpo É um JSON de RSI, mas um placeholder numérico
    # (tipicamente {{plot_0}}) não foi expandido pelo TradingView — o indicador
    # de RSI do usuário pode não expor esse plot. Isso quebra o JSON inteiro.
    # Trocamos qualquer {{...}} remanescente por null e tentamos de novo, para
    # que o alerta de RSI continue valendo (o valor do rsi é opcional).
    if "{{" in raw and "}}" in raw and raw.lstrip().startswith("{"):
        sanitizado = re.sub(r'"?\{\{[^}]*\}\}"?', "null", raw)
        try:
            data2 = json.loads(sanitizado)
            if isinstance(data2, dict):
                logger.warning("Placeholder do TradingView não expandido; "
                               "payload recuperado como: %s",
                               json.dumps(data2, ensure_ascii=False))
                return data2
        except Exception:  # noqa: BLE001
            pass

    # TradingView placeholders ainda não expandidos
    if "{{" in raw and "}}" in raw:
        logger.warning("Payload contém placeholders do TradingView ainda não expandidos: %s", raw[:200])
        return None
    
    # Tentar extrair de texto simples (fallback)
    payload = {}
    raw_lower = raw.lower()
    
    # Detectar ação (buy/sell/long/short)
    if any(w in raw_lower for w in ("buy", "long", "compra", " ls")):
        payload["action"] = "buy"
    elif any(w in raw_lower for w in ("sell", "short", "venda", " ss")):
        payload["action"] = "sell"
    
    # Detectar direção RSI (up/down)
    if any(w in raw_lower for w in ("rsi up", "rsi cross up", "acima")):
        payload["direction"] = "up"
    elif any(w in raw_lower for w in ("rsi down", "rsi cross down", "abaixo")):
        payload["direction"] = "down"
    
    # Detectar timeframe: 1m, 5m, 15m, 1h, 4h, etc.
    tf_match = re.search(r'\b(\d+[mhd])\b', raw_lower)
    if tf_match:
        payload["timeframe"] = tf_match.group(1)
    
    # Detectar símbolo (BTCUSDT, BNBUSDT, etc.)
    symbol_match = re.search(r'\b([A-Z]{3,10}USDT(?:\.P)?)\b', raw, re.IGNORECASE)
    if symbol_match:
        payload["symbol"] = symbol_match.group(1).replace(".P", "")
    
    # Se não conseguimos extrair nada útil, retorna None
    if not payload:
        logger.warning("Payload texto não reconhecido: %s", raw[:200])
        return None
    
    payload["_raw_text"] = raw[:300]
    return payload


# --------------------------------------------------------------------- #
# Aplicação Flask
# --------------------------------------------------------------------- #
app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "crypto_shadow_bot",
        "bot_id": BOT_ID,
        "strategy": STRATEGY,
        "modo_sombra": MODO_SOMBRA,
        "status": "online",
        "combinacoes": len(controller.moedas) * len(controller.timeframes) * len(controller.alavancagens),
        "moedas": controller.moedas,
        "timeframes": controller.timeframes,
        "alavancagens": controller.alavancagens,
        "time": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/diag", methods=["GET"])
def diag():
    tg_token_ok = bool(getattr(notifier, "token", None))
    tg_valid = None
    if tg_token_ok:
        try:
            import requests
            r = requests.get(f"https://api.telegram.org/bot{notifier.token}/getMe", timeout=8)
            tg_valid = bool(r.ok and r.json().get("ok"))
        except Exception:  # noqa: BLE001
            tg_valid = False
    with _recent_lock:
        eventos = list(_recent_events[-20:])
    return jsonify({
        "bot_id": BOT_ID,
        "strategy": STRATEGY,
        "modo_sombra": MODO_SOMBRA,
        "modo_autonomo": MODO_AUTONOMO,
        "aceitar_webhooks": ACEITAR_WEBHOOKS,
        "scanner_autonomo": scanner.snapshot() if MODO_AUTONOMO else {"ativo": False},
        "execucao_real_bitget": False,
        "telegram": {"token_presente": tg_token_ok, "token_valido": tg_valid,
                     "chat_id": getattr(notifier, "chat_id", None)},
        "combinacoes_totais": len(controller.moedas) * len(controller.timeframes) * len(controller.alavancagens),
        "engine": {
            "analise_ativa": controller._eng_settings.get("analise_ativa"),
            "require_fresh_cross_bars": controller._eng_settings.get("require_fresh_cross_bars"),
            "tp_sl_global": {
                "tp_percent": round(controller.tp_percent * 100, 3),
                "sl_percent": round(controller.sl_percent * 100, 3),
            },
            "tp_sl_por_tf": {
                tf: {"tp_percent": round(tp * 100, 3), "sl_percent": round(sl * 100, 3)}
                for tf, (tp, sl) in getattr(controller, "tp_sl_por_tf", {}).items()
            },
        },
        "contadores": {
            "sinais_tsts": controller.contador_sinais,
            "rsi_cross": controller.contador_rsi,
            "entradas_simuladas": controller.contador_entradas_sim,
        },
        "confirmacao": controller.confirm.snapshot() if getattr(controller, "confirm", None) else None,
        "catalyst": controller.catalyst.snapshot() if getattr(controller, "catalyst", None) else None,
        "dias_com_registro": crypto_logger.dias_disponiveis()[:10],
        "total_webhooks_recebidos": len(_recent_events),
        "ultimos_eventos": eventos,
    })


@app.route("/status", methods=["GET"])
def status():
    snap = controller.snapshot()
    snap["modo_autonomo"] = MODO_AUTONOMO
    snap["scanner_autonomo"] = scanner.snapshot() if MODO_AUTONOMO else {"ativo": False}
    return jsonify(snap)


@app.route("/registro", methods=["GET"])
def registro():
    dia = request.args.get("dia")  # AAAA-MM-DD (opcional; padrão = hoje UTC)
    return jsonify({"dia": dia or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "registros": crypto_logger.ler_dia(dia)})


@app.route("/limpar_logs", methods=["POST"])
def limpar_logs():
    """
    Deleta os arquivos de log de um dia específico. Requer confirmação.
    Query params:
      - dia: AAAA-MM-DD (opcional; padrão = hoje UTC)
      - confirmar: "sim" (obrigatório para executar)
    
    Exemplo: POST /limpar_logs?dia=2026-07-20&confirmar=sim
    """
    dia = request.args.get("dia")
    confirmar = request.args.get("confirmar", "").lower()
    
    if confirmar != "sim":
        return jsonify({
            "ok": False,
            "error": "Confirmação necessária. Adicione ?confirmar=sim à URL."
        }), 400
    
    resultado = crypto_logger.limpar_dia(dia)
    code = 200 if resultado["ok"] else 500
    return jsonify(resultado), code


@app.route("/resumo", methods=["GET"])
def resumo():
    dia = request.args.get("dia")
    texto = controller.gerar_resumo_diario(dia)
    enviado = None
    if request.args.get("enviar") == "1":
        enviado = notifier.notify_daily_summary(texto)
    return jsonify({"dia": dia or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "resumo_html": texto, "enviado_telegram": enviado})


@app.route("/webhook/<moeda>", methods=["POST"])
def webhook(moeda: str):
    """
    Recebe um sinal do TradingView para uma moeda.
    Por padrão trata como sinal TSTS (buy/sell). Se o payload trouxer
    "tipo":"rsi" (ou "rsi_cross"), trata como cruzamento de RSI.
    """
    if not ACEITAR_WEBHOOKS:
        _record_event(moeda.upper(), "webhook_ignorado_modo_autonomo")
        return jsonify({"ok": True, "decisao": "ignorado",
                        "motivo": "MODO AUTÔNOMO: o bot calcula os próprios sinais; "
                                  "webhooks do TradingView estão desativados "
                                  "(aceitar_webhooks=false)."}), 200
    data = _parse_payload()
    if data is None:
        _record_event(moeda.upper(), "ERRO_payload_nao_json")
        return jsonify({"ok": False, "error": "Payload não é JSON válido"}), 400

    tipo = str(data.get("tipo") or data.get("type") or "").strip().lower()
    is_rsi = tipo in ("rsi", "rsi_cross", "cross", "cruzamento")

    _record_event(moeda.upper(), "webhook_rsi" if is_rsi else "webhook_sinal", {
        "tf": str(data.get("timeframe") or data.get("tf") or ""),
        "action": str(data.get("action") or data.get("side") or data.get("signal")
                      or data.get("direction") or ""),
        "keys": sorted(list(data.keys())),
    })
    logger.info("Webhook %s (%s): %s", moeda.upper(),
                "RSI" if is_rsi else "SINAL", json.dumps(data, ensure_ascii=False))

    if is_rsi:
        res = controller.processar_rsi_cross(moeda, data)
    else:
        res = controller.processar_sinal(moeda, data)

    code = 200 if res.get("ok") else 400
    return jsonify(res), code


@app.route("/rsi/<moeda>", methods=["POST"])
def rsi_cross(moeda: str):
    """Recebe um alerta de cruzamento de RSI (up/down) para uma moeda."""
    if not ACEITAR_WEBHOOKS:
        _record_event(moeda.upper(), "webhook_ignorado_modo_autonomo")
        return jsonify({"ok": True, "decisao": "ignorado",
                        "motivo": "MODO AUTÔNOMO: webhooks desativados "
                                  "(aceitar_webhooks=false)."}), 200
    data = _parse_payload()
    if data is None:
        _record_event(moeda.upper(), "ERRO_payload_nao_json")
        return jsonify({"ok": False, "error": "Payload não é JSON válido"}), 400
    _record_event(moeda.upper(), "webhook_rsi", {
        "tf": str(data.get("timeframe") or data.get("tf") or ""),
        "direction": str(data.get("direction") or data.get("cross")
                         or data.get("action") or ""),
    })
    logger.info("Webhook RSI %s: %s", moeda.upper(), json.dumps(data, ensure_ascii=False))
    res = controller.processar_rsi_cross(moeda, data)
    return jsonify(res), (200 if res.get("ok") else 400)


# --------------------------------------------------------------------- #
# CAMADA DE CONFIRMAÇÃO (gate) — cores dos indicadores fechados
# --------------------------------------------------------------------- #
# Estas rotas recebem a COR ATUAL de cada componente (não geram entrada
# sozinhas). O bot guarda a cor por MOEDA+TF e, quando o sinal do Sniper
# chega, só ENTRA se todas as cores baterem com a regra (config "confirmacao").
_COMPONENTES_BSDET = {
    "hist": "histograma", "histograma": "histograma", "histogram": "histograma",
    "plot1": "plot1", "p1": "plot1",
    "plot2": "plot2", "p2": "plot2",
    "plot3": "plot3", "p3": "plot3",
}


def _prep_confirm_payload(tf: str = None):
    """Lê o payload do webhook e injeta o timeframe do path (se veio na URL)."""
    if not ACEITAR_WEBHOOKS:
        return None, jsonify({"ok": True, "decisao": "ignorado",
                              "motivo": "MODO AUTÔNOMO: webhooks desativados "
                                        "(aceitar_webhooks=false)."}), 200
    data = _parse_payload()
    if data is None:
        data = {}
    if tf:  # timeframe veio na URL -> tem prioridade
        data["timeframe"] = tf
    return data, None, None


@app.route("/verde/bokk/<moeda>", methods=["POST"])
@app.route("/verde/bokk/<moeda>/<tf>", methods=["POST"])
def confirm_bokk(moeda: str, tf: str = None):
    """Cor atual do BOKK (TSTS Core). Alerta nativo do indicador fechado.
    Mensagem esperada: {"signal":"green"} ou {"signal":"red"}."""
    data, resp, code = _prep_confirm_payload(tf)
    if resp is not None:
        return resp, code
    res = controller.atualizar_confirmacao("bokk", moeda, data)
    _record_event(moeda.upper(), "confirm_bokk", {
        "tf": str(data.get("timeframe") or ""), "ok": res.get("ok"),
        "cor": res.get("cor"), "erro": res.get("error"),
    })
    return jsonify(res), (200 if res.get("ok") else 400)


@app.route("/bsdet/estado/<moeda>", methods=["POST"])
@app.route("/bsdet/estado/<moeda>/<tf>", methods=["POST"])
def confirm_bsdet_estado(moeda: str, tf: str = None):
    """Estado CONSOLIDADO do BS Detector (helper v4): histograma + plot1/2/3
    numa única mensagem JSON. Ex.: {"timeframe":"5m","hist":"red",
    "p1":"green","p2":"green","p3":"green"}."""
    data, resp, code = _prep_confirm_payload(tf)
    if resp is not None:
        return resp, code
    res = controller.atualizar_confirmacao_varios(moeda, data)
    _record_event(moeda.upper(), "confirm_bsdet_estado", {
        "tf": str(data.get("timeframe") or ""), "ok": res.get("ok"),
        "aplicados": res.get("aplicados"), "erro": res.get("error"),
    })
    return jsonify(res), (200 if res.get("ok") else 400)


@app.route("/catalyst/<moeda>", methods=["POST"])
@app.route("/est-rsi/catalyst/<moeda>", methods=["POST"])
def catalyst_estado(moeda: str):
    """Estado do CATALISADOR (indicador MNQ Catalyst) de UMA moeda.
    Mensagem esperada (JSON): {"c5m":"BULL","c15m":"NEUT","c1h":"BEAR","vwap":"BULL"}.
    Aceita BULL/BEAR/NEUT (e apelidos up/down/buy/sell/green/red/above/below).
    1 alerta por MOEDA (o indicador já calcula 5m/15m/1h internamente)."""
    if not ACEITAR_WEBHOOKS:
        return jsonify({"ok": True, "decisao": "ignorado",
                        "motivo": "MODO AUTÔNOMO: webhooks desativados."}), 200
    data = _parse_payload() or {}
    res = controller.atualizar_catalyst(moeda, data)
    _record_event(moeda.upper(), "catalyst", {
        "ok": res.get("ok"), "estado": res.get("estado"), "erro": res.get("error"),
    })
    return jsonify(res), (200 if res.get("ok") else 400)


@app.route("/bsdet/<comp>/<moeda>", methods=["POST"])
@app.route("/bsdet/<comp>/<moeda>/<tf>", methods=["POST"])
def confirm_bsdet_componente(comp: str, moeda: str, tf: str = None):
    """Cor de UM componente do BS Detector (compatibilidade com o helper v3
    que dispara alertas separados). comp = hist/plot1/plot2/plot3."""
    componente = _COMPONENTES_BSDET.get(str(comp).strip().lower())
    if not componente:
        return jsonify({"ok": False,
                        "error": f"componente '{comp}' desconhecido "
                                 "(use hist/plot1/plot2/plot3)"}), 400
    data, resp, code = _prep_confirm_payload(tf)
    if resp is not None:
        return resp, code
    res = controller.atualizar_confirmacao(componente, moeda, data)
    _record_event(moeda.upper(), f"confirm_{componente}", {
        "tf": str(data.get("timeframe") or ""), "ok": res.get("ok"),
        "cor": res.get("cor"), "erro": res.get("error"),
    })
    return jsonify(res), (200 if res.get("ok") else 400)


# --------------------------------------------------------------------- #
# Threads de fundo: monitor de TP/SL + scheduler do resumo diário
# --------------------------------------------------------------------- #
_threads_started = False
_threads_lock = threading.Lock()


def _monitor_tp_sl_loop():
    """Verifica periodicamente se as posições simuladas atingiram TP/SL."""
    intervalo = max(int(controller.poll_minutes), 1) * 60
    logger.info("Monitor de TP/SL simulado iniciado (intervalo %ss).", intervalo)
    while True:
        try:
            fechadas = controller.verificar_tp_sl()
            if fechadas:
                logger.info("Monitor: %d posição(ões) simulada(s) fechada(s) por TP/SL.", fechadas)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro no monitor de TP/SL: %s", exc)
        time.sleep(intervalo)


def _resumo_diario_loop():
    """Envia o resumo diário ao Telegram no horário configurado (UTC)."""
    tg = CONFIG.get("telegram", {})
    hora = int(tg.get("resumo_diario_hora_utc", 23))
    minuto = int(tg.get("resumo_diario_minuto_utc", 59))
    logger.info("Scheduler do resumo diário iniciado (%02d:%02d UTC).", hora, minuto)
    ultimo_envio_dia = None
    while True:
        try:
            agora = datetime.now(timezone.utc)
            dia_atual = agora.strftime("%Y-%m-%d")
            if (agora.hour == hora and agora.minute >= minuto
                    and ultimo_envio_dia != dia_atual):
                texto = controller.gerar_resumo_diario(dia_atual)
                ok = notifier.notify_daily_summary(texto)
                ultimo_envio_dia = dia_atual
                logger.info("Resumo diário enviado ao Telegram (ok=%s).", ok)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro no scheduler do resumo diário: %s", exc)
        time.sleep(30)


def start_background_threads():
    """Inicia as threads de fundo (idempotente). Só roda em MODO SOMBRA."""
    global _threads_started
    with _threads_lock:
        if _threads_started:
            return
        if not MODO_SOMBRA:
            logger.error("MODO_SOMBRA=false — threads de sombra NÃO iniciadas. "
                         "Este pacote é exclusivamente de coleta (sombra).")
            return
        _threads_started = True
    threading.Thread(target=_monitor_tp_sl_loop, name="monitor-tpsl", daemon=True).start()
    threading.Thread(target=_resumo_diario_loop, name="resumo-diario", daemon=True).start()
    if MODO_AUTONOMO:
        logger.info("MODO AUTÔNOMO ativo — iniciando scanner interno "
                    "(o bot calcula os próprios sinais; TradingView não é necessário).")
        scanner.start()
    else:
        logger.info("MODO AUTÔNOMO desligado — o bot depende dos webhooks do TradingView.")


def _boot():
    """Inicialização comum (startup Telegram + threads)."""
    if not MODO_SOMBRA:
        logger.error("=" * 60)
        logger.error("ATENÇÃO: MODO_SOMBRA=false. Este pacote NÃO executa ordens reais.")
        logger.error("Mantenha MODO_SOMBRA=true no config.json. Abortando execução ativa.")
        logger.error("=" * 60)
        return
    combos = len(controller.moedas) * len(controller.timeframes) * len(controller.alavancagens)
    logger.info("Iniciando [%s] MODO SOMBRA | %d combinações (%d moedas x %d TFs x %d alav.)",
                BOT_ID, combos, len(controller.moedas), len(controller.timeframes),
                len(controller.alavancagens))
    try:
        notifier.notify_shadow_startup(combos, len(controller.moedas),
                                       len(controller.timeframes), len(controller.alavancagens))
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao enviar startup ao Telegram: %s", exc)
    start_background_threads()


# Inicia no import (necessário sob gunicorn, que não chama main()).
_boot()


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    logger.info("Servidor [%s] em %s:%s (MODO SOMBRA=%s)", BOT_ID, host, port, MODO_SOMBRA)
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
