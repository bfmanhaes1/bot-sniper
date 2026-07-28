# -*- coding: utf-8 -*-
"""
market_data.py
==============
Busca dados de mercado em TEMPO REAL diretamente da BITGET (API pública v2)
e calcula os indicadores técnicos localmente:

  - RSI(14)                      -> saúde de momentum
  - Market Cipher B / WaveTrend  -> wt1 / wt2 (LazyBear WaveTrend, n1=10, n2=21)
  - HMA(15)                      -> "Pink HMA" da estratégia Silent Sniper
  - Volume + média de volume
  - Direção (bias) por timeframe  -> usado no alinhamento multi-timeframe

MOTIVO DESTE MÓDULO
-------------------
Antes, o sistema dependia 100% dos valores que o TradingView enviava no
webhook (rsi14, cipher_wt1, cipher_wt2, volume). Quando o TradingView NÃO
preenchia esses campos (ou quando os timeframes de alinhamento não tinham
alerta próprio), tudo virava "n/d" e o score nunca alcançava o threshold.

Agora buscamos os candles reais da Bitget e calculamos os indicadores no
servidor, tornando o bot independente do que o TradingView manda. NÃO usamos
Binance — os dados vêm da mesma corretora onde as ordens são executadas.

Endpoint público usado (não exige assinatura):
  GET https://api.bitget.com/api/v2/mix/market/candles
      ?symbol=BTCUSDT&granularity=15m&productType=USDT-FUTURES&limit=200

Formato do candle retornado (lista de strings):
  [ ts, open, high, low, close, baseVolume, quoteVolume ]

Todos os comentários estão em Português.
"""

import time
import math
import logging
from typing import Dict, Any, Optional, List, Tuple

import requests

logger = logging.getLogger("market_data")

BITGET_BASE_URL = "https://api.bitget.com"
CANDLES_PATH = "/api/v2/mix/market/candles"

# Cache em memória: {(symbol, granularity): (ts, candles)}
_CACHE: Dict[Tuple[str, str], Tuple[float, List[List[float]]]] = {}
_CACHE_TTL = 30  # segundos — evita bater na API a cada webhook

# ------------------------------------------------------------------ #
# Mapeamento de timeframe (TradingView / config) -> granularity Bitget
# ------------------------------------------------------------------ #
# A Bitget v2 aceita: 1m,3m,5m,15m,30m,1H,4H,6H,12H,1D,3D,1W,1M
_GRANULARITY_MAP = {
    "1m": "1m", "1": "1m",
    "3m": "3m", "3": "3m",
    "5m": "5m", "5": "5m",
    "15m": "15m", "15": "15m",
    "30m": "30m", "30": "30m",
    "45m": "30m", "45": "30m",  # aproxima 45m para 30m (Bitget não tem 45m)
    "1h": "1H", "60": "1H", "1H": "1H",
    "2h": "1H", "120": "1H", "2H": "1H",   # aproxima 2h para 1H
    "4h": "4H", "240": "4H", "4H": "4H",
    "6h": "6H", "360": "6H",
    "12h": "12H", "720": "12H",
    "1d": "1D", "d": "1D", "D": "1D", "1D": "1D",
    "1w": "1W", "w": "1W", "W": "1W",
}


def normalize_timeframe(tf: Any) -> str:
    """Normaliza o timeframe para a granularity aceita pela Bitget."""
    if tf is None:
        return "15m"
    key = str(tf).strip()
    return _GRANULARITY_MAP.get(key, _GRANULARITY_MAP.get(key.lower(), "15m"))


def normalize_symbol(symbol: str) -> str:
    """
    Normaliza o símbolo para o formato da API v2 da Bitget.

    A v2 usa símbolos "limpos" (ex.: BTCUSDT, VIRTUALUSDT). O sufixo antigo
    "_UMCBL" era da API v1 e NÃO deve ser usado aqui — se vier, removemos.
    """
    if not symbol:
        return symbol
    s = str(symbol).strip().upper()
    for suffix in ("_UMCBL", "_DMCBL", "_CMCBL", "_SUMCBL"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    return s


# ------------------------------------------------------------------ #
# Busca de candles
# ------------------------------------------------------------------ #
def fetch_candles(
    symbol: str,
    timeframe: str,
    product_type: str = "USDT-FUTURES",
    limit: int = 200,
    timeout: int = 12,
) -> List[List[float]]:
    """
    Busca os candles da Bitget e devolve uma lista ORDENADA do mais antigo
    para o mais novo, com valores já convertidos para float:
        [ [ts, open, high, low, close, baseVol, quoteVol], ... ]

    Usa cache em memória (TTL de 30s). Retorna [] em caso de erro.
    """
    sym = normalize_symbol(symbol)
    gran = normalize_timeframe(timeframe)
    cache_key = (f"{sym}|{product_type}", gran)

    cached = _CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        resp = requests.get(
            BITGET_BASE_URL + CANDLES_PATH,
            params={
                "symbol": sym,
                "granularity": gran,
                "productType": product_type,
                "limit": str(limit),
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if str(payload.get("code")) != "00000":
            logger.warning("Bitget candles erro %s/%s: %s", sym, gran, payload.get("msg"))
            return []
        raw = payload.get("data") or []
        candles: List[List[float]] = []
        for row in raw:
            try:
                candles.append([float(x) for x in row[:7]])
            except (ValueError, TypeError):
                continue
        # A Bitget devolve do mais antigo -> mais novo; garantimos a ordem por ts
        candles.sort(key=lambda c: c[0])
        _CACHE[cache_key] = (time.time(), candles)
        return candles
    except (requests.RequestException, ValueError) as exc:
        logger.error("Falha ao buscar candles %s/%s: %s", sym, gran, exc)
        return []


# ------------------------------------------------------------------ #
# Indicadores — implementações em Python puro (sem numpy)
# ------------------------------------------------------------------ #
def _ema(values: List[float], period: int) -> List[float]:
    """Média móvel exponencial. Retorna lista do mesmo tamanho de values."""
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _sma_last(values: List[float], period: int) -> Optional[float]:
    """SMA dos últimos `period` valores."""
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def _wma(values: List[float], period: int) -> List[float]:
    """Média móvel ponderada (Weighted Moving Average)."""
    if period <= 0 or len(values) < period:
        return []
    weights = list(range(1, period + 1))
    wsum = sum(weights)
    out = []
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out.append(sum(w * x for w, x in zip(weights, window)) / wsum)
    return out


def compute_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """
    RSI de Wilder. Retorna o valor mais recente (0-100) ou None se dados
    insuficientes.
    """
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # Média inicial (primeiros `period`)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Suavização de Wilder para o restante
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_wavetrend(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    n1: int = 10,
    n2: int = 21,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Market Cipher B / WaveTrend (LazyBear). Retorna (wt1, wt2) mais recentes.

    Fórmula:
      ap  = hlc3 = (high + low + close) / 3
      esa = ema(ap, n1)
      d   = ema(abs(ap - esa), n1)
      ci  = (ap - esa) / (0.015 * d)
      tci = ema(ci, n2)     -> wt1
      wt2 = sma(wt1, 4)
    """
    n = min(len(highs), len(lows), len(closes))
    if n < (n1 + n2 + 4):
        return None, None

    ap = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    esa = _ema(ap, n1)
    d = _ema([abs(ap[i] - esa[i]) for i in range(n)], n1)
    ci = []
    for i in range(n):
        denom = 0.015 * d[i]
        ci.append((ap[i] - esa[i]) / denom if denom != 0 else 0.0)
    tci = _ema(ci, n2)          # wt1
    wt1 = tci[-1]
    wt2 = _sma_last(tci, 4)     # média de 4 do wt1
    return wt1, wt2


def compute_hma(closes: List[float], period: int = 15) -> Optional[float]:
    """
    Hull Moving Average (HMA) — a "Pink HMA" da estratégia Silent Sniper.
      hma = wma( 2*wma(price, n/2) - wma(price, n), sqrt(n) )
    Retorna o valor mais recente ou None.
    """
    half = max(1, int(period / 2))
    sqrt_n = max(1, int(round(math.sqrt(period))))
    if len(closes) < period + sqrt_n:
        return None
    wma_half = _wma(closes, half)
    wma_full = _wma(closes, period)
    # Alinha as duas séries pelo final (tamanhos diferentes)
    m = min(len(wma_half), len(wma_full))
    if m < sqrt_n:
        return None
    raw = [2 * wma_half[-m + i] - wma_full[-m + i] for i in range(m)]
    hma_series = _wma(raw, sqrt_n)
    return hma_series[-1] if hma_series else None


# ------------------------------------------------------------------ #
# Agregador principal
# ------------------------------------------------------------------ #
def get_indicators(
    symbol: str,
    timeframe: str,
    product_type: str = "USDT-FUTURES",
) -> Dict[str, Any]:
    """
    Busca candles da Bitget e devolve um dicionário com todos os indicadores
    calculados para o ÚLTIMO candle fechado.

    Retorno (valores podem ser None se não houver dados suficientes):
      {
        "rsi14": float,
        "cipher_wt1": float,
        "cipher_wt2": float,
        "hma15": float,
        "close": float,
        "volume": float,          # volume do candle atual
        "avg_volume": float,      # média dos 20 candles anteriores
        "direction": "buy"/"sell"/None,   # bias multi-timeframe
        "source": "bitget",
        "ok": bool,
      }
    """
    empty = {
        "rsi14": None, "cipher_wt1": None, "cipher_wt2": None, "hma15": None,
        "close": None, "volume": None, "avg_volume": None, "direction": None,
        "source": "bitget", "ok": False,
    }
    candles = fetch_candles(symbol, timeframe, product_type=product_type, limit=200)
    if not candles or len(candles) < 40:
        return empty

    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]
    volumes = [c[5] for c in candles]

    rsi = compute_rsi(closes, 14)
    wt1, wt2 = compute_wavetrend(highs, lows, closes)
    hma = compute_hma(closes, 15)
    close = closes[-1]
    volume = volumes[-1]
    # Média dos 20 candles anteriores (exclui o atual)
    prev_vols = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
    avg_volume = (sum(prev_vols) / len(prev_vols)) if prev_vols else None

    # ----- Direção (bias) para o alinhamento multi-timeframe -----
    # Regra: combina posição do preço vs HMA(15) com o RSI relativo a 50.
    direction: Optional[str] = None
    if hma is not None and rsi is not None:
        if close > hma and rsi >= 50:
            direction = "buy"
        elif close < hma and rsi <= 50:
            direction = "sell"
    elif rsi is not None:
        direction = "buy" if rsi >= 50 else "sell"

    return {
        "rsi14": round(rsi, 2) if rsi is not None else None,
        "cipher_wt1": round(wt1, 2) if wt1 is not None else None,
        "cipher_wt2": round(wt2, 2) if wt2 is not None else None,
        "hma15": round(hma, 6) if hma is not None else None,
        "close": close,
        "volume": volume,
        "avg_volume": avg_volume,
        "direction": direction,
        "source": "bitget",
        "ok": rsi is not None,
    }


# ------------------------------------------------------------------ #
# SÉRIES completas (necessárias para DETECTAR CRUZAMENTOS no modo autônomo)
# ------------------------------------------------------------------ #
# As funções acima devolvem só o ÚLTIMO valor. Para o modo autônomo (o bot
# calcula os próprios sinais) precisamos comparar o candle fechado atual com o
# anterior — por isso versões que devolvem a SÉRIE inteira.

def compute_rsi_series(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """
    RSI de Wilder para TODA a série. Devolve uma lista alinhada a `closes`
    (mesmo tamanho); posições sem RSI definido vêm como None.
    """
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    gains, losses = [], []
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi(avg_gain, avg_loss)          # 1º RSI = closes[period]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


def sma_of_series(series: List[Optional[float]], period: int) -> List[Optional[float]]:
    """SMA de uma série que pode conter None. Alinhada ao tamanho de `series`."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if period <= 0:
        return out
    for i in range(n):
        if i + 1 < period:
            continue
        window = series[i - period + 1 : i + 1]
        if any(x is None for x in window):
            continue
        out[i] = sum(window) / period  # type: ignore[arg-type]
    return out


def wavetrend_series(
    highs: List[float], lows: List[float], closes: List[float],
    n1: int = 10, n2: int = 21,
) -> Tuple[List[Optional[float]], List[Optional[float]]]:
    """Séries (wt1, wt2) do WaveTrend/Market Cipher B. Alinhadas ao tamanho n."""
    n = min(len(highs), len(lows), len(closes))
    if n < (n1 + n2 + 4):
        return [], []
    ap = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    esa = _ema(ap, n1)
    d = _ema([abs(ap[i] - esa[i]) for i in range(n)], n1)
    ci = []
    for i in range(n):
        denom = 0.015 * d[i]
        ci.append((ap[i] - esa[i]) / denom if denom != 0 else 0.0)
    tci = _ema(ci, n2)                       # wt1 (série completa)
    wt2: List[Optional[float]] = [None] * n
    for i in range(n):
        if i >= 3:
            wt2[i] = sum(tci[i - 3 : i + 1]) / 4.0
    return tci, wt2  # type: ignore[return-value]


def hma_series(closes: List[float], period: int = 15) -> List[Optional[float]]:
    """Série da Hull Moving Average (HMA/'Pink HMA'). Devolve os valores finais."""
    half = max(1, int(period / 2))
    sqrt_n = max(1, int(round(math.sqrt(period))))
    if len(closes) < period + sqrt_n:
        return []
    wma_half = _wma(closes, half)
    wma_full = _wma(closes, period)
    m = min(len(wma_half), len(wma_full))
    if m < sqrt_n:
        return []
    raw = [2 * wma_half[-m + i] - wma_full[-m + i] for i in range(m)]
    return _wma(raw, sqrt_n)  # type: ignore[return-value]


def get_signal_frame(
    symbol: str,
    timeframe: str,
    product_type: str = "USDT-FUTURES",
) -> Dict[str, Any]:
    """
    Snapshot para o SCANNER autônomo. Usa SEMPRE o último candle FECHADO
    (descarta o candle em formação) para reproduzir o "Once Per Bar Close" do
    TradingView. Devolve os indicadores do candle fechado atual E do anterior,
    permitindo detectar cruzamentos (RSI x MA, WaveTrend, inclinação da HMA).

    Retorno (None onde não houver dados suficientes):
      {
        "ok": bool,
        "bar_ts": float,            # timestamp do último candle FECHADO
        "close": float,             # fechamento do último candle fechado
        "rsi": float,   "rsi_prev": float,
        "rsi_ma": float,"rsi_ma_prev": float,
        "wt1": float,   "wt1_prev": float,
        "wt2": float,   "wt2_prev": float,
        "hma": float,   "hma_prev": float,
      }
    """
    empty = {"ok": False, "bar_ts": None, "close": None,
             "rsi": None, "rsi_prev": None, "rsi_ma": None, "rsi_ma_prev": None,
             "wt1": None, "wt1_prev": None, "wt2": None, "wt2_prev": None,
             "hma": None, "hma_prev": None}
    candles = fetch_candles(symbol, timeframe, product_type=product_type, limit=200)
    if not candles or len(candles) < 60:
        return empty
    # Descarta o candle em formação (o último). Trabalha só com candles FECHADOS.
    closed = candles[:-1]
    if len(closed) < 50:
        return empty

    highs = [c[2] for c in closed]
    lows = [c[3] for c in closed]
    closes = [c[4] for c in closed]

    rsi_s = compute_rsi_series(closes, 14)
    rsi_ma_s = sma_of_series(rsi_s, 14)
    wt1_s, wt2_s = wavetrend_series(highs, lows, closes)
    hma_s = hma_series(closes, 15)

    def _last2(seq):
        if not seq or len(seq) < 2:
            return None, None
        return seq[-1], seq[-2]

    rsi, rsi_prev = _last2(rsi_s)
    rsi_ma, rsi_ma_prev = _last2(rsi_ma_s)
    wt1, wt1_prev = _last2(wt1_s)
    wt2, wt2_prev = _last2(wt2_s)
    hma, hma_prev = _last2(hma_s)

    ok = all(v is not None for v in (rsi, rsi_prev, rsi_ma, rsi_ma_prev))
    return {
        "ok": bool(ok),
        "bar_ts": closed[-1][0],
        "close": closes[-1],
        "rsi": rsi, "rsi_prev": rsi_prev,
        "rsi_ma": rsi_ma, "rsi_ma_prev": rsi_ma_prev,
        "wt1": wt1, "wt1_prev": wt1_prev,
        "wt2": wt2, "wt2_prev": wt2_prev,
        "hma": hma, "hma_prev": hma_prev,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for s, tf in [("BTCUSDT", "15m"), ("VIRTUALUSDT", "5m"), ("LINKUSDT", "1m")]:
        print(s, tf, "->", get_indicators(s, tf))
        print("   frame ->", get_signal_frame(s, tf))
