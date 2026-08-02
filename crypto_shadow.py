# -*- coding: utf-8 -*-
"""
crypto_shadow.py
================
Controlador do MODO SOMBRA multi-ativo (cripto).

Responsabilidades:
  1. Manter um motor de decisão (DecisionEngine) por combinação MOEDA+TIMEFRAME.
     -> 10 moedas x 3 TFs = 30 fluxos de decisão independentes.
  2. Processar alertas TSTS (buy/sell) e cruzamentos de RSI vindos do TradingView,
     decidindo ENTRAR / AGUARDAR / ANALISAR (1º, 2º, 3º cruzamento).
  3. SIMULAR a entrada e a saída (TP/SL fixos ou reversão), calculando o P&L
     para as 2 alavancagens (5x e 10x) -> 60 combinações logadas.
  4. Registrar TUDO em crypto_logs/ (JSON + Markdown), sem NUNCA enviar ordem real.
  5. Gerar o resumo diário (para o Telegram).

TRAVA DE SEGURANÇA: este módulo não importa nem instancia o cliente da Bitget
para operar. Ele só consulta PREÇO PÚBLICO (endpoint aberto, sem credenciais)
para avaliar TP/SL das posições simuladas.

Todos os comentários e mensagens em Português.
"""

import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import requests

import crypto_logger
from engine import DecisionEngine
from confirmacao import ConfirmStore

logger = logging.getLogger("crypto_shadow")

# Endpoint PÚBLICO de preço da Bitget (NÃO requer credenciais; somente leitura).
_BITGET_TICKER = "https://api.bitget.com/api/v2/mix/market/ticker"
# Endpoint PÚBLICO de candles (velas) da Bitget. Usado SOMENTE para calcular,
# no fechamento simulado, o DD (excursão adversa máxima) e o MFE (o quanto o
# preço correu a favor) a partir dos high/low reais das velas. Somente leitura.
_BITGET_CANDLES = "https://api.bitget.com/api/v2/mix/market/candles"

# Mapa timeframe canônico -> granularity aceito pelo endpoint de candles.
_GRAN_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "2h": "2H", "4h": "4H", "1d": "1D",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_action(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("buy", "long", "compra", "1", "b"):
        return "buy"
    if s in ("sell", "short", "venda", "-1", "s"):
        return "sell"
    return ""


def _norm_direction(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in ("up", "buy", "long", "1", "compra", "acima"):
        return "up"
    if s in ("down", "sell", "short", "-1", "venda", "abaixo"):
        return "down"
    return ""


# Mapa dos intervalos que o TradingView envia em {{interval}} (número puro,
# em minutos, ou "D"/"W"/"M") para o formato canônico usado no config
# ("1m", "5m", "15m", "1h", "4h", "1d", ...).
_TF_MAP = {
    "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m", "45": "45m",
    "60": "1h", "120": "2h", "180": "3h", "240": "4h",
    "d": "1d", "1d": "1d", "w": "1w", "1w": "1w", "m": "1M",
}


def _tf_seg(tf: str) -> float:
    """Converte um timeframe canônico ('1m','5m','15m','1h','4h','1d') em segundos."""
    s = str(tf or "").strip().lower()
    try:
        if s.endswith("m"):
            return float(s[:-1] or 0) * 60.0
        if s.endswith("h"):
            return float(s[:-1] or 0) * 3600.0
        if s.endswith("d"):
            return float(s[:-1] or 0) * 86400.0
        if s.isdigit():
            return float(s) * 60.0
    except ValueError:
        pass
    return 60.0


def _norm_tf(raw: Any) -> str:
    """
    Normaliza o timeframe recebido para o formato do config.

    O TradingView, no placeholder {{interval}}, manda apenas o número de
    minutos ("1", "5", "15") ou letras ("D", "W", "M"). Já o TSTS/RSI podem
    mandar "5m", "15m" direto. Esta função aceita ambos e devolve o canônico.
    """
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    # Já vem no formato canônico (ex.: "5m", "15m", "1h", "4h", "1d")?
    if re.fullmatch(r"\d+[mhdw]", s) or s in ("1m", "5m", "15m"):
        return s
    # Número puro de minutos (ex.: "5" -> "5m") ou letra ("d" -> "1d").
    return _TF_MAP.get(s, f"{s}m" if s.isdigit() else s)


class SimPosition:
    """Uma posição SIMULADA aberta para uma combinação moeda+TF."""

    def __init__(self, moeda: str, tf: str, action: str, entry: float,
                 tp: float, sl: float, cruzamento: int):
        self.moeda = moeda
        self.tf = tf
        self.action = action              # buy/sell
        self.entry = entry
        self.tp = tp
        self.sl = sl
        self.cruzamento = cruzamento
        self.aberta_em = _now()
        # Rastreamento contínuo dos extremos de preço enquanto a posição está
        # aberta (atualizado a cada verificação do monitor). Serve de reserva
        # caso o cálculo por velas (candles) falhe no fechamento.
        self.max_preco = entry            # maior preço visto desde a entrada
        self.min_preco = entry            # menor preço visto desde a entrada

    def registrar_preco(self, px: float) -> None:
        """Atualiza os extremos (máx/mín) com um novo preço observado."""
        if px and px > 0:
            if px > self.max_preco:
                self.max_preco = px
            if px < self.min_preco:
                self.min_preco = px

    def chave(self) -> str:
        return f"{self.moeda}_{self.tf}"


class CryptoShadowController:
    def __init__(self, config: Dict[str, Any], notifier=None):
        self.cfg = config
        self.notifier = notifier
        self.moedas: List[str] = config.get("moedas", [])
        self.timeframes: List[str] = config.get("timeframes", [])
        self.alavancagens: List[int] = config.get("alavancagens", [5, 10])
        self.symbols: Dict[str, str] = config.get("symbols_bitget", {})

        sim = config.get("simulacao", {})
        self.margin_usdt: float = float(sim.get("margin_usdt", 50))
        self.tp_percent: float = float(sim.get("tp_percent", 2.0)) / 100.0
        self.sl_percent: float = float(sim.get("sl_percent", 1.0)) / 100.0
        self.poll_minutes: int = int(sim.get("poll_price_minutes", 5))

        # TP/SL calibrado POR TIMEFRAME (fallback = global acima). Guardado em
        # fração (0.30% -> 0.0030). Ignora chaves de comentário (_...).
        self.tp_sl_por_tf: Dict[str, Tuple[float, float]] = {}
        for _tf, _cfg in (config.get("simulacao_por_tf") or {}).items():
            if _tf.startswith("_") or not isinstance(_cfg, dict):
                continue
            try:
                _tp = float(_cfg["tp_percent"]) / 100.0
                _sl = float(_cfg["sl_percent"]) / 100.0
            except (KeyError, TypeError, ValueError):
                continue
            self.tp_sl_por_tf[_tf] = (_tp, _sl)

        eng = config.get("engine", {})
        # Um motor de decisão por MOEDA+TF (estado de RSI independente).
        self._engines: Dict[str, DecisionEngine] = {}
        self._eng_settings = {
            "require_fresh_cross_bars": eng.get("require_fresh_cross_bars", 0),
            "pending_timeout_bars": eng.get("pending_timeout_bars", 12),
            "analise_ativa": eng.get("analise_ativa", True),
            "max_cruzamentos": eng.get("max_cruzamentos", 3),
            "anti_empilhamento": eng.get("anti_empilhamento", True),
            "max_contratos": 999,  # sem limite de "contratos" no modo sombra
            "posicao_timeout_min": eng.get("posicao_timeout_min", 240),
        }
        self.analise_modo: str = config.get("analise", {}).get("modo", "regras")

        self._lock = threading.RLock()
        self._positions: Dict[str, SimPosition] = {}     # chave = MOEDA_TF
        self._price_cache: Dict[str, Tuple[float, float]] = {}  # symbol -> (preco, ts)

        # Contadores em memória para diagnóstico rápido (resetam no restart).
        self.contador_sinais = 0
        self.contador_rsi = 0
        self.contador_entradas_sim = 0

        # Dedup anti-duplicação: ignora um SINAL idêntico (moeda+tf+ação) que
        # chegue de novo dentro desta janela. Protege caso o scanner autônomo e
        # um eventual webhook do TradingView disparem quase juntos.
        self._dedup_seg: float = float(config.get("dedup_sinal_segundos", 90))
        self._ultimo_sinal: Dict[str, float] = {}  # "MOEDA_TF_ACAO" -> epoch

        # Camada de CONFIRMAÇÃO (gate) por moeda+TF — modelo do "bot verde" MNQ.
        # Guarda a cor atual de BOKK / histograma / plot1/2/3 e só libera a
        # entrada quando todas baterem com a regra (config "confirmacao").
        self.confirm = ConfirmStore(config)

    # ------------------------------------------------------------------ #
    def atualizar_confirmacao(self, componente: str, moeda: str,
                              data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recebe a COR ATUAL de UM componente (bokk/histograma/plot1/2/3) vinda de
        um webhook do TradingView e guarda no ConfirmStore.
        `data` pode trazer: signal/cor/color/value (a cor) e timeframe/tf/interval.
        """
        moeda = (moeda or "").upper()
        tf = _norm_tf(data.get("timeframe") or data.get("tf") or data.get("interval"))
        erro = self._validar(moeda, tf)
        if erro:
            return {"ok": False, "error": erro}
        cor = (data.get("signal") or data.get("cor") or data.get("color")
               or data.get("value") or data.get("estado"))
        return self.confirm.atualizar(componente, moeda, tf, cor)

    def atualizar_confirmacao_varios(self, moeda: str,
                                     data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recebe VÁRIAS cores de uma vez (helper consolidado do BS Detector:
        hist + plot1/2/3 numa única mensagem) e guarda todas.
        `data` traz timeframe/tf/interval + as cores (hist/p1/p2/p3/...).
        """
        moeda = (moeda or "").upper()
        tf = _norm_tf(data.get("timeframe") or data.get("tf") or data.get("interval"))
        erro = self._validar(moeda, tf)
        if erro:
            return {"ok": False, "error": erro}
        # Tudo que não for metadado de timeframe é candidato a cor de componente.
        cores = {k: v for k, v in (data or {}).items()
                 if str(k).lower() not in ("timeframe", "tf", "interval", "moeda", "symbol", "ticker")}
        return self.confirm.atualizar_varios(moeda, tf, cores)

    # ------------------------------------------------------------------ #
    def _engine(self, moeda: str, tf: str) -> DecisionEngine:
        chave = f"{moeda}_{tf}"
        if chave not in self._engines:
            self._engines[chave] = DecisionEngine(self._eng_settings)
        return self._engines[chave]

    def semear_rsi(self, moeda: str, tf: str, direction: str) -> None:
        """Semeia o lado atual do RSI no motor da combinação (scanner autônomo)."""
        moeda = (moeda or "").upper()
        if self._validar(moeda, tf):
            return
        self._engine(moeda, tf).semear_estado(moeda, direction)

    def _preco_publico(self, moeda: str, use_cache: bool = True) -> Optional[float]:
        """Consulta o preço público (mark price) da Bitget. Somente leitura."""
        symbol = self.symbols.get(moeda)
        if not symbol:
            return None
        if use_cache:
            cached = self._price_cache.get(symbol)
            if cached and (time.time() - cached[1]) < 30:
                return cached[0]
        try:
            r = requests.get(
                _BITGET_TICKER,
                params={"symbol": symbol, "productType": "USDT-FUTURES"},
                timeout=8,
            )
            data = r.json()
            arr = data.get("data") or []
            if arr:
                px = float(arr[0].get("lastPr") or arr[0].get("markPrice") or 0)
                if px > 0:
                    self._price_cache[symbol] = (px, time.time())
                    return px
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao consultar preço público de %s: %s", moeda, exc)
        return None

    def _high_low_desde(self, moeda: str, tf: str, desde: datetime,
                        ate: Optional[datetime] = None):
        """
        Busca as velas públicas da Bitget e devolve (high_max, low_min) no
        intervalo [desde, ate]. Usado no fechamento simulado para calcular o
        DD (excursão adversa) e o MFE (excursão favorável) com base nos
        high/low REAIS das velas. Somente leitura; sem credenciais.
        Retorna (None, None) se falhar (o chamador cai no fallback por polls).
        """
        symbol = self.symbols.get(moeda)
        if not symbol:
            return None, None
        gran = _GRAN_MAP.get(tf, "1m")
        desde_ep = desde.timestamp()
        ate_ep = (ate or _now()).timestamp()
        try:
            r = requests.get(
                _BITGET_CANDLES,
                params={"symbol": symbol, "productType": "USDT-FUTURES",
                        "granularity": gran, "limit": 200},
                timeout=8,
            )
            data = r.json()
            arr = data.get("data") or []
            highs: List[float] = []
            lows: List[float] = []
            for c in arr:
                # Formato: [ts_ms, open, high, low, close, volume, quote_vol]
                try:
                    ts = int(c[0]) / 1000.0
                except (TypeError, ValueError, IndexError):
                    continue
                # Mantém as velas que tocam a janela da posição (com folga de
                # 1 timeframe para pegar a vela onde a entrada aconteceu).
                folga = _tf_seg(tf)
                if ts < desde_ep - folga:
                    continue
                if ts > ate_ep + folga:
                    continue
                try:
                    highs.append(float(c[2]))
                    lows.append(float(c[3]))
                except (TypeError, ValueError, IndexError):
                    continue
            if highs and lows:
                return max(highs), min(lows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao consultar velas de %s (%s): %s", moeda, tf, exc)
        return None, None

    # ------------------------------------------------------------------ #
    def _validar(self, moeda: str, tf: str) -> Optional[str]:
        moeda = (moeda or "").upper()
        if moeda not in self.moedas:
            return f"moeda '{moeda}' não monitorada"
        if tf not in self.timeframes:
            return f"timeframe '{tf}' não monitorado"
        return None

    def _preco_entrada(self, moeda: str, data: Dict[str, Any]) -> Optional[float]:
        """Preço de entrada simulado: usa o do payload; senão, o preço público."""
        for k in ("entry", "price", "close", "preco"):
            v = data.get(k)
            if v is not None:
                try:
                    p = float(v)
                    if p > 0:
                        return p
                except (TypeError, ValueError):
                    pass
        return self._preco_publico(moeda)

    def _tp_sl(self, action: str, entry: float,
               tf: Optional[str] = None) -> Tuple[float, float]:
        # Usa TP/SL específico do timeframe se configurado; senão o global.
        tp_pct, sl_pct = self.tp_sl_por_tf.get(
            tf, (self.tp_percent, self.sl_percent)
        )
        if action == "buy":
            return entry * (1 + tp_pct), entry * (1 - sl_pct)
        return entry * (1 - tp_pct), entry * (1 + sl_pct)

    def _decisao_analista_regras(self, action: str, cruzamento: int,
                                 rsi: Optional[float], rsi_ma: Optional[float]) -> str:
        """
        Heurística de custo zero (modo sombra) para o 1º/2º cruzamento.
        Registra o que o analista TERIA decidido: 'entrar' ou 'aguardar'.
        Regra simples: entra se o RSI está claramente do lado do sinal e com
        alguma folga em relação à média; caso contrário aguarda o próximo.
        """
        try:
            if rsi is None:
                return "entrar" if cruzamento >= 2 else "aguardar"
            if action == "buy":
                folga = (rsi - (rsi_ma if rsi_ma is not None else 50))
                if rsi >= 50 and folga >= 1:
                    return "entrar"
            else:
                folga = ((rsi_ma if rsi_ma is not None else 50) - rsi)
                if rsi <= 50 and folga >= 1:
                    return "entrar"
        except (TypeError, ValueError):
            pass
        # No 2º cruzamento tende a entrar (sinal persistente); no 1º, aguarda.
        return "entrar" if cruzamento >= 2 else "aguardar"

    # ------------------------------------------------------------------ #
    def _abrir_simulacao(self, moeda: str, tf: str, action: str, entry: float,
                         cruzamento: int, sinal_tsts: str, rsi: Optional[float]):
        """Abre uma posição simulada e registra ENTRADA para cada alavancagem."""
        tp, sl = self._tp_sl(action, entry, tf)
        with self._lock:
            self._positions[f"{moeda}_{tf}"] = SimPosition(
                moeda, tf, action, entry, tp, sl, cruzamento
            )
            self.contador_entradas_sim += 1
        for alav in self.alavancagens:
            crypto_logger.registrar("ENTRADA", {
                "moeda": moeda, "timeframe": tf, "alavancagem": f"{alav}x",
                "sinal_tsts": sinal_tsts, "rsi_valor": rsi,
                "cruzamento_numero": cruzamento, "decisao_agente": "entrar",
                "direcao": "LONG" if action == "buy" else "SHORT",
                "preco_entrada_simulado": entry,
                "preco_saida_simulado": None, "resultado_simulado": None,
                "tp_simulado": tp, "sl_simulado": sl,
            })

    def _calcular_dd_mfe(self, pos: SimPosition):
        """
        Calcula, para a posição que está fechando:
          - MFE (excursão favorável): o QUANTO o preço correu A FAVOR (melhor
            ponto para um TP). Em %, sempre >= 0.
          - DD/MAE (excursão adversa): o QUANTO o preço correu CONTRA (pior
            ponto; base para dimensionar o SL). Em %, sempre >= 0.
        Usa os high/low REAIS das velas da Bitget. Se a consulta falhar, cai
        no fallback dos extremos observados nos polls (pos.max_preco/min_preco).
        Devolve (mfe_pct, dd_pct, high_usado, low_usado).
        """
        high, low = self._high_low_desde(pos.moeda, pos.tf, pos.aberta_em)
        if high is None or low is None:
            high, low = pos.max_preco, pos.min_preco
        # Garante que a entrada esteja dentro da faixa (protege cálculo).
        high = max(high, pos.entry)
        low = min(low, pos.entry)
        if pos.action == "buy":   # LONG: favor = subiu; contra = caiu
            mfe_pct = (high - pos.entry) / pos.entry * 100.0
            dd_pct = (pos.entry - low) / pos.entry * 100.0
        else:                     # SHORT: favor = caiu; contra = subiu
            mfe_pct = (pos.entry - low) / pos.entry * 100.0
            dd_pct = (high - pos.entry) / pos.entry * 100.0
        return (round(max(mfe_pct, 0.0), 4), round(max(dd_pct, 0.0), 4),
                round(high, 8), round(low, 8))

    def _fechar_simulacao(self, pos: SimPosition, exit_price: float, motivo: str):
        """Fecha uma posição simulada e registra SAIDA para cada alavancagem."""
        if pos.action == "buy":
            pnl_pct = (exit_price - pos.entry) / pos.entry
        else:
            pnl_pct = (pos.entry - exit_price) / pos.entry
        # DD (excursão adversa) e MFE (excursão favorável) para estudo de TP/SL.
        mfe_pct, dd_pct, high_usado, low_usado = self._calcular_dd_mfe(pos)
        duracao_min = round((_now() - pos.aberta_em).total_seconds() / 60.0, 1)
        for alav in self.alavancagens:
            pnl_usdt = self.margin_usdt * alav * pnl_pct
            resultado = {
                "pnl_pct": round(pnl_pct * 100, 4),
                f"pnl_usdt_{alav}x": round(pnl_usdt, 2),
                "motivo": motivo,
                "ganho": pnl_pct > 0,
                # --- Dados para eventual otimização de TP e SL ---
                "mfe_pct": mfe_pct,          # o quanto correu A FAVOR (%)
                "dd_pct": dd_pct,            # DD / excursão adversa CONTRA (%)
                "mfe_usdt": round(self.margin_usdt * alav * mfe_pct / 100.0, 2),
                "dd_usdt": round(self.margin_usdt * alav * dd_pct / 100.0, 2),
                "high_periodo": high_usado,
                "low_periodo": low_usado,
                "duracao_min": duracao_min,
            }
            crypto_logger.registrar("SAIDA", {
                "moeda": pos.moeda, "timeframe": pos.tf, "alavancagem": f"{alav}x",
                "sinal_tsts": "-", "rsi_valor": None,
                "cruzamento_numero": pos.cruzamento,
                "decisao_agente": "fechar",
                "direcao": "LONG" if pos.action == "buy" else "SHORT",
                "preco_entrada_simulado": pos.entry,
                "preco_saida_simulado": exit_price,
                "resultado_simulado": resultado,
            })
        with self._lock:
            self._positions.pop(pos.chave(), None)

    # ------------------------------------------------------------------ #
    def processar_sinal(self, moeda: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Processa um alerta TSTS (buy/sell) para uma moeda."""
        moeda = (moeda or "").upper()
        action = _norm_action(data.get("action") or data.get("side")
                              or data.get("signal") or data.get("direction"))
        tf = _norm_tf(data.get("timeframe") or data.get("tf"))
        erro = self._validar(moeda, tf)
        if erro:
            return {"ok": False, "error": erro}
        if action not in ("buy", "sell"):
            return {"ok": False, "error": "ação (buy/sell) ausente/ inválida"}

        # Dedup: ignora sinal idêntico repetido dentro da janela configurada.
        if self._dedup_seg > 0:
            chave_dd = f"{moeda}_{tf}_{action}"
            agora_ep = time.time()
            ultimo = self._ultimo_sinal.get(chave_dd)
            if ultimo is not None and (agora_ep - ultimo) < self._dedup_seg:
                return {"ok": True, "decisao": "ignorado",
                        "motivo": f"sinal {action.upper()} duplicado em <{int(self._dedup_seg)}s"}
            self._ultimo_sinal[chave_dd] = agora_ep

        self.contador_sinais += 1
        rsi = _safe_float(data.get("rsi"))
        rsi_ma = _safe_float(data.get("rsi_ma") or data.get("rsi_media"))
        entry = self._preco_entrada(moeda, data)
        sinal_txt = action.upper()

        # Registra o SINAL bruto recebido (útil para o estudo e para a contagem).
        crypto_logger.registrar("SINAL", {
            "moeda": moeda, "timeframe": tf, "alavancagem": None,
            "sinal_tsts": sinal_txt, "rsi_valor": rsi,
            "cruzamento_numero": None, "decisao_agente": None,
            "preco_entrada_simulado": entry,
            "direcao": "LONG" if action == "buy" else "SHORT",
        })

        eng = self._engine(moeda, tf)
        # Antes de decidir, verifica reversão: se há posição simulada oposta aberta,
        # fecha-a pelo preço atual (registra o resultado).
        self._checar_reversao(moeda, tf, action, entry)

        decisao = eng.on_signal(moeda, action, timeframe=tf,
                                extra={"rsi": rsi, "rsi_ma": rsi_ma, "entry": entry})

        return self._processar_decisao(
            moeda, tf, action, sinal_txt, rsi, rsi_ma, entry, decisao, origem="SINAL")

    def processar_rsi_cross(self, moeda: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Processa um alerta de cruzamento de RSI (up/down) para uma moeda."""
        moeda = (moeda or "").upper()
        direction = _norm_direction(data.get("direction") or data.get("cross")
                                    or data.get("rsi_cross") or data.get("action")
                                    or data.get("side"))
        tf = _norm_tf(data.get("timeframe") or data.get("tf"))
        erro = self._validar(moeda, tf)
        if erro:
            return {"ok": False, "error": erro}
        if direction not in ("up", "down"):
            return {"ok": False, "error": "direção do RSI (up/down) ausente/ inválida"}

        self.contador_rsi += 1
        rsi = _safe_float(data.get("rsi"))
        rsi_ma = _safe_float(data.get("rsi_ma") or data.get("rsi_media"))
        entry = self._preco_entrada(moeda, data)

        eng = self._engine(moeda, tf)
        decisao = eng.on_rsi_cross(moeda, direction, timeframe=tf)
        action = decisao.get("action") or ("buy" if direction == "up" else "sell")
        sinal_txt = (decisao.get("action") or direction).upper()

        return self._processar_decisao(
            moeda, tf, action, sinal_txt, rsi, rsi_ma, entry, decisao,
            origem="RSI_CROSS", direction=direction)

    def _checar_reversao(self, moeda: str, tf: str, nova_action: str,
                         preco: Optional[float]):
        chave = f"{moeda}_{tf}"
        with self._lock:
            pos = self._positions.get(chave)
        if pos and pos.action != nova_action:
            px = preco or self._preco_publico(moeda) or pos.entry
            self._fechar_simulacao(pos, px, "reversao")

    def _processar_decisao(self, moeda, tf, action, sinal_txt, rsi, rsi_ma, entry,
                           decisao: Dict[str, Any], origem: str,
                           direction: str = "") -> Dict[str, Any]:
        cruzamento = decisao.get("cruzamento")

        # 0) GATE DE CONFIRMAÇÃO — modelo "bot verde" MNQ.
        # O motor já disse "entrar" (Sniper + RSI ok) e JÁ registrou a trava de
        # posição. Antes de simular a entrada, exigimos que as cores dos
        # indicadores fechados (BOKK / histograma / plot1/2/3) batam com a regra.
        # Se NÃO baterem: registra BLOQUEADO, SOLTA a trava (senão o motor acha
        # que abriu posição e trava a combinação) e NÃO entra.
        if decisao.get("entrar") and getattr(self, "confirm", None) and self.confirm.ativa:
            ok_conf, det_conf = self.confirm.checar(
                moeda, tf, (action or "").lower(), _tf_seg(tf) / 60.0)
            if not ok_conf:
                self._engine(moeda, tf).liberar_posicao(moeda)
                crypto_logger.registrar("BLOQUEADO", {
                    "moeda": moeda, "timeframe": tf, "alavancagem": None,
                    "sinal_tsts": sinal_txt, "rsi_valor": rsi,
                    "cruzamento_numero": cruzamento or 1,
                    "decisao_agente": "bloqueado_confirmacao",
                    "direcao": (action or "").lower(),
                    "motivo": det_conf.get("motivo"),
                    "confirmacao": det_conf,
                })
                logger.info("%s %s: entrada BLOQUEADA pela confirmação — %s",
                            moeda, tf, det_conf.get("motivo"))
                return {"ok": True, "decisao": "bloqueado_confirmacao",
                        "cruzamento": cruzamento or 1, "detalhe": det_conf}

        # 1) ENTRADA (automática no lado alinhado ou no cruzamento máximo)
        if decisao.get("entrar"):
            n = cruzamento or 1
            if entry and entry > 0:
                self._abrir_simulacao(moeda, tf, action, entry, n, sinal_txt, rsi)
            else:
                crypto_logger.registrar("ENTRADA", {
                    "moeda": moeda, "timeframe": tf, "alavancagem": None,
                    "sinal_tsts": sinal_txt, "rsi_valor": rsi,
                    "cruzamento_numero": n, "decisao_agente": "entrar",
                    "motivo": "sem preço para simular",
                })
            return {"ok": True, "decisao": "entrar", "cruzamento": n,
                    "motivo": decisao.get("motivo")}

        # 2) ANALISAR (1º/2º cruzamento) -> registra o que o analista TERIA decidido
        if decisao.get("analisar"):
            n = cruzamento or 1
            hipotese = self._decisao_analista_regras(action, n, rsi, rsi_ma)
            crypto_logger.registrar("ANALISE", {
                "moeda": moeda, "timeframe": tf, "alavancagem": None,
                "sinal_tsts": sinal_txt, "rsi_valor": rsi,
                "cruzamento_numero": n, "decisao_agente": hipotese,
                "motivo": decisao.get("motivo"),
            })
            # Em modo sombra registramos a hipótese, mas NÃO forçamos a entrada:
            # deixamos o motor seguir até o cruzamento máximo (entrada automática),
            # a menos que a hipótese seja 'entrar' — aí simulamos a entrada também.
            if hipotese == "entrar" and entry and entry > 0:
                # Também passa pelo gate de confirmação (mesmo no modo análise).
                if getattr(self, "confirm", None) and self.confirm.ativa:
                    ok_conf, det_conf = self.confirm.checar(
                        moeda, tf, (action or "").lower(), _tf_seg(tf) / 60.0)
                    if not ok_conf:
                        crypto_logger.registrar("BLOQUEADO", {
                            "moeda": moeda, "timeframe": tf, "alavancagem": None,
                            "sinal_tsts": sinal_txt, "rsi_valor": rsi,
                            "cruzamento_numero": n,
                            "decisao_agente": "bloqueado_confirmacao",
                            "direcao": (action or "").lower(),
                            "motivo": det_conf.get("motivo"),
                            "confirmacao": det_conf,
                        })
                        return {"ok": True, "decisao": "bloqueado_confirmacao",
                                "analise": True, "cruzamento": n,
                                "detalhe": det_conf}
                self._abrir_simulacao(moeda, tf, action, entry, n, sinal_txt, rsi)
                self._engine(moeda, tf).confirmar_entrada(moeda)
            return {"ok": True, "decisao": hipotese, "analise": True,
                    "cruzamento": n, "motivo": decisao.get("motivo")}

        # 3) AGUARDAR / SEGURAR (sinal pendente aguardando cruzamento do RSI)
        crypto_logger.registrar("AGUARDAR", {
            "moeda": moeda, "timeframe": tf, "alavancagem": None,
            "sinal_tsts": sinal_txt, "rsi_valor": rsi,
            "cruzamento_numero": cruzamento,
            "decisao_agente": "aguardar",
            "motivo": decisao.get("motivo"),
        })
        return {"ok": True, "decisao": "aguardar", "motivo": decisao.get("motivo")}

    # ------------------------------------------------------------------ #
    def verificar_tp_sl(self) -> int:
        """
        Percorre as posições simuladas abertas e fecha as que atingiram TP/SL.
        Chamado periodicamente pelo monitor. Retorna quantas foram fechadas.
        """
        with self._lock:
            posicoes = list(self._positions.values())
        fechadas = 0
        for pos in posicoes:
            px = self._preco_publico(pos.moeda, use_cache=False)
            if not px:
                continue
            # Atualiza os extremos (máx/mín) para o cálculo de DD/MFE (fallback).
            pos.registrar_preco(px)
            if pos.action == "buy":
                if px >= pos.tp:
                    self._fechar_simulacao(pos, pos.tp, "TP"); fechadas += 1
                elif px <= pos.sl:
                    self._fechar_simulacao(pos, pos.sl, "SL"); fechadas += 1
            else:
                if px <= pos.tp:
                    self._fechar_simulacao(pos, pos.tp, "TP"); fechadas += 1
                elif px >= pos.sl:
                    self._fechar_simulacao(pos, pos.sl, "SL"); fechadas += 1
        return fechadas

    # ------------------------------------------------------------------ #
    def gerar_resumo_diario(self, dia: Optional[str] = None) -> str:
        """Monta o texto (HTML Telegram) do resumo diário do modo sombra."""
        if dia is None:
            dia = _now().strftime("%Y-%m-%d")
        regs = crypto_logger.ler_dia(dia)

        total_sinais = sum(1 for r in regs if r.get("evento") == "SINAL")
        entradas = [r for r in regs if r.get("evento") == "ENTRADA"]
        saidas = [r for r in regs if r.get("evento") == "SAIDA"]
        analises = [r for r in regs if r.get("evento") == "ANALISE"]
        aguardar = [r for r in regs if r.get("evento") == "AGUARDAR"]

        # Sinais por moeda (conta eventos ENTRADA/ANALISE/AGUARDAR como atividade)
        por_moeda: Dict[str, int] = {}
        for r in regs:
            if r.get("evento") in ("ENTRADA", "ANALISE", "AGUARDAR"):
                m = r.get("moeda", "?")
                por_moeda[m] = por_moeda.get(m, 0) + 1

        # Performance simulada (usa saídas; agrega P&L por alavancagem)
        wins = losses = 0
        pnl_total = {f"{a}x": 0.0 for a in self.alavancagens}
        por_config: Dict[str, Dict[str, Any]] = {}  # "MOEDA TF alavX" -> stats
        # Acúmulo de MFE (o quanto correu a favor) e DD (excursão adversa) para
        # eventual estudo de TP/SL. Contamos cada trade fechado uma única vez
        # (uma alavancagem de referência) para não inflar as médias.
        mfe_vals: List[float] = []
        dd_vals: List[float] = []
        mfe_max = dd_max = 0.0
        _alav_ref = f"{self.alavancagens[0]}x" if self.alavancagens else None
        for r in saidas:
            res = r.get("resultado_simulado") or {}
            if not isinstance(res, dict):
                continue
            alav = r.get("alavancagem", "")
            for k, v in res.items():
                if k.startswith("pnl_usdt_"):
                    tag = k.replace("pnl_usdt_", "")
                    pnl_total.setdefault(tag, 0.0)
                    pnl_total[tag] += float(v or 0)
            # MFE/DD são em % (independentes de alavancagem) → conta 1x por trade
            if _alav_ref is None or alav == _alav_ref:
                mv = _safe_float(res.get("mfe_pct"))
                dv = _safe_float(res.get("dd_pct"))
                if mv is not None:
                    mfe_vals.append(mv)
                    mfe_max = max(mfe_max, mv)
                if dv is not None:
                    dd_vals.append(dv)
                    dd_max = max(dd_max, dv)
            if res.get("ganho"):
                wins += 1
            else:
                losses += 1
            chave = f"{r.get('moeda')} {r.get('timeframe')} {alav}"
            st = por_config.setdefault(chave, {"pnl": 0.0, "n": 0, "wins": 0})
            for k, v in res.items():
                if k.startswith("pnl_usdt_"):
                    st["pnl"] += float(v or 0)
            st["n"] += 1
            if res.get("ganho"):
                st["wins"] += 1

        trades_fechados = wins + losses
        wr = (wins / trades_fechados * 100) if trades_fechados else 0.0

        # Top 5 melhores configurações por P&L
        melhores = sorted(por_config.items(), key=lambda kv: kv[1]["pnl"], reverse=True)[:5]

        _MES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        try:
            d = datetime.strptime(dia, "%Y-%m-%d")
            data_fmt = f"{d.day:02d}/{_MES[d.month - 1]}/{d.year}"
        except ValueError:
            data_fmt = dia

        linhas = [
            f"🕶️ <b>RESUMO DIÁRIO — Modo Sombra Crypto</b>",
            f"📅 {data_fmt} (UTC)\n",
            f"📊 <b>Atividade</b>",
            f"• Sinais TSTS recebidos: {total_sinais}",
            f"• Entradas simuladas: {len(entradas) // max(len(self.alavancagens),1)}",
            f"• Análises (1º/2º cruz.): {len(analises)}",
            f"• Sinais aguardando RSI: {len(aguardar)}",
            f"• Trades simulados fechados: {trades_fechados}\n",
            f"📈 <b>Performance simulada</b>",
            f"• Vitórias/Derrotas: {wins}/{losses} (WR {wr:.1f}%)",
        ]
        for tag, v in pnl_total.items():
            emoji = "🟢" if v >= 0 else "🔴"
            linhas.append(f"• P&L {tag}: {emoji} ${v:,.2f}")

        # Excursões (base para calibrar TP e SL futuramente)
        if mfe_vals or dd_vals:
            media_mfe = sum(mfe_vals) / len(mfe_vals) if mfe_vals else 0.0
            media_dd = sum(dd_vals) / len(dd_vals) if dd_vals else 0.0
            linhas.append("\n🎯 <b>Excursões (para calibrar TP/SL)</b>")
            linhas.append(f"• MFE médio (correu a favor): {media_mfe:.2f}%")
            linhas.append(f"• MFE máximo: {mfe_max:.2f}%")
            linhas.append(f"• DD médio (correu contra): {media_dd:.2f}%")
            linhas.append(f"• DD máximo: {dd_max:.2f}%")

        if por_moeda:
            linhas.append("\n🪙 <b>Atividade por moeda</b>")
            for m, c in sorted(por_moeda.items(), key=lambda kv: kv[1], reverse=True):
                linhas.append(f"• {m}: {c}")

        if melhores:
            linhas.append("\n🏆 <b>Melhores configurações (P&L)</b>")
            for chave, st in melhores:
                wrc = (st["wins"] / st["n"] * 100) if st["n"] else 0
                linhas.append(f"• {chave}: ${st['pnl']:,.2f} ({st['n']} trades, WR {wrc:.0f}%)")

        if trades_fechados == 0 and total_sinais == 0:
            linhas.append("\n<i>Nenhum sinal recebido hoje. Verifique os alertas do TradingView.</i>")

        linhas.append("\n<i>Modo Sombra: nenhuma ordem real foi enviada. Dados salvos em crypto2_logs/.</i>")
        return "\n".join(linhas)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            posicoes = {k: {
                "moeda": p.moeda, "tf": p.tf, "action": p.action,
                "entry": p.entry, "tp": p.tp, "sl": p.sl,
                "cruzamento": p.cruzamento,
                "aberta_em": p.aberta_em.isoformat(),
            } for k, p in self._positions.items()}
        return {
            "combinacoes": len(self.moedas) * len(self.timeframes) * len(self.alavancagens),
            "moedas": self.moedas,
            "timeframes": self.timeframes,
            "alavancagens": self.alavancagens,
            "posicoes_simuladas_abertas": posicoes,
            "contador_sinais": self.contador_sinais,
            "contador_rsi": self.contador_rsi,
            "contador_entradas_sim": self.contador_entradas_sim,
            "confirmacao": self.confirm.snapshot() if getattr(self, "confirm", None) else None,
        }


def _safe_float(v) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
