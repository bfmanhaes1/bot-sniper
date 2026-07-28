# -*- coding: utf-8 -*-
"""
analysis.py
===========
Módulo de análise técnica + macro para o sistema de trading híbrido.

Responsabilidades:
  - Manter um "signal store" com o último sinal recebido por ativo/timeframe,
    permitindo a análise multi-timeframe (alinhamento).
  - Calcular um score de 0 a 100 combinando:
      * Alinhamento de timeframes (30 pts)
      * Saúde do RSI (20 pts)
      * Market Cipher B / WaveTrend (15 pts)
      * Volume (10 pts)
      * Fear & Greed Index (10 pts)
      * Dominância do BTC (10 pts)
      * Sentimento de notícias (5 pts)
  - Buscar contexto macro em APIs grátis, com cache em disco.

Todos os comentários estão em Português.
"""

import os
import json
import time
import logging
from collections import deque, defaultdict
from typing import Dict, Any, Optional, List

import requests

import market_data

logger = logging.getLogger("analysis")

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# ====================================================================== #
# SIGNAL STORE — memória dos últimos sinais por ativo/timeframe
# ====================================================================== #
class SignalStore:
    """
    Guarda em memória o último payload recebido de cada ativo/timeframe e
    um histórico de volume para calcular a média móvel de 20 períodos.

    Estrutura:
      self.latest[asset][timeframe] = {dados do webhook + recv_ts}
      self.volume_hist[asset][timeframe] = deque(maxlen=20)
    """

    def __init__(self, volume_window: int = 20, stale_seconds: int = 3 * 3600):
        self.latest: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        self.volume_hist: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=volume_window))
        )
        self.stale_seconds = stale_seconds

    def update(self, asset: str, timeframe: str, data: Dict[str, Any]) -> None:
        """Registra o sinal mais recente e alimenta o histórico de volume."""
        record = dict(data)
        record["recv_ts"] = time.time()
        self.latest[asset][timeframe] = record

        vol = _safe_float(data.get("volume"))
        if vol is not None:
            self.volume_hist[asset][timeframe].append(vol)

    def get(self, asset: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Retorna o último sinal se não estiver 'velho' (stale)."""
        rec = self.latest.get(asset, {}).get(timeframe)
        if not rec:
            return None
        if time.time() - rec.get("recv_ts", 0) > self.stale_seconds:
            return None
        return rec

    def avg_volume(self, asset: str, timeframe: str) -> Optional[float]:
        """Média de volume dos últimos períodos disponíveis (mín. 3)."""
        hist = self.volume_hist.get(asset, {}).get(timeframe)
        if not hist or len(hist) < 3:
            return None
        return sum(hist) / len(hist)


def _safe_float(value: Any) -> Optional[float]:
    """Converte para float com segurança; retorna None se impossível."""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if s == "" or s.lower() in ("nan", "none", "null"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


def normalize_action(action: Any) -> Optional[str]:
    """Normaliza o campo action para 'buy' ou 'sell'."""
    if action is None:
        return None
    a = str(action).strip().lower()
    if a in ("buy", "long", "compra"):
        return "buy"
    if a in ("sell", "short", "venda"):
        return "sell"
    return None


# ====================================================================== #
# CACHE EM DISCO
# ====================================================================== #
def _cache_read(name: str, max_age: int) -> Optional[Any]:
    """Lê um valor do cache se ainda estiver dentro da validade (max_age s)."""
    path = os.path.join(CACHE_DIR, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if time.time() - blob.get("_ts", 0) > max_age:
            return None
        return blob.get("value")
    except (ValueError, OSError):
        return None


def _cache_write(name: str, value: Any) -> None:
    """Grava um valor no cache com timestamp."""
    path = os.path.join(CACHE_DIR, name)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_ts": time.time(), "value": value}, f)
    except OSError as exc:
        logger.warning("Não foi possível gravar cache %s: %s", name, exc)


# ====================================================================== #
# CONTEXTO MACRO (APIs grátis)
# ====================================================================== #
def get_fear_greed(url: str, cache_seconds: int = 3600) -> Optional[int]:
    """
    Fear & Greed Index (0-100) via alternative.me. Cache padrão de 1h.
    """
    cached = _cache_read("fear_greed.json", cache_seconds)
    if cached is not None:
        return cached
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        value = int(data["data"][0]["value"])
        _cache_write("fear_greed.json", value)
        return value
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        logger.warning("Falha ao obter Fear & Greed: %s", exc)
        return None


def get_btc_dominance(url: str, cache_seconds: int = 3600) -> Optional[float]:
    """
    Dominância do BTC (%) via CoinGecko /global. Cache padrão de 1h.
    """
    cached = _cache_read("btc_dominance.json", cache_seconds)
    if cached is not None:
        return cached
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        dom = float(data["data"]["market_cap_percentage"]["btc"])
        _cache_write("btc_dominance.json", dom)
        return dom
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Falha ao obter dominância BTC: %s", exc)
        return None


def get_crypto_news(
    base_url: str,
    asset: str,
    cache_seconds: int = 900,
    auth_token: str = "",
) -> Dict[str, int]:
    """
    Busca notícias recentes do ativo via CryptoPanic (plano free).
    Retorna contagem {'positive': x, 'negative': y, 'total': z}.
    Cache padrão de 15 min por ativo.

    Obs.: A API free do CryptoPanic exige um auth_token. Se não houver token,
    a função retorna zeros (sem penalizar nem beneficiar o score).
    """
    cache_name = f"news_{asset}.json"
    cached = _cache_read(cache_name, cache_seconds)
    if cached is not None:
        return cached

    result = {"positive": 0, "negative": 0, "total": 0}
    if not auth_token:
        # Sem token não conseguimos consultar; devolve neutro.
        _cache_write(cache_name, result)
        return result

    # Mapeia o nome interno para o ticker usado pelo CryptoPanic
    currency = {"APTOS": "APT", "VIRTUAL": "VIRTUAL"}.get(asset, asset)
    try:
        params = {
            "auth_token": auth_token,
            "currencies": currency,
            "public": "true",
            "kind": "news",
        }
        resp = requests.get(base_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for post in data.get("results", []) or []:
            votes = post.get("votes", {}) or {}
            pos = (votes.get("positive", 0) or 0) + (votes.get("liked", 0) or 0)
            neg = (votes.get("negative", 0) or 0) + (votes.get("disliked", 0) or 0)
            result["total"] += 1
            if pos > neg:
                result["positive"] += 1
            elif neg > pos:
                result["negative"] += 1
        _cache_write(cache_name, result)
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Falha ao obter notícias de %s: %s", asset, exc)
    return result


def get_macro_context(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reúne o contexto macro (Fear & Greed + Dominância BTC) com cache.
    Notícias são buscadas por ativo dentro de analyze_signal.
    """
    apis = config.get("apis", {})
    settings = config.get("settings", {})
    macro_cache = int(settings.get("macro_cache_seconds", 3600))
    return {
        "fear_greed": get_fear_greed(
            apis.get("fear_greed", "https://api.alternative.me/fng/"), macro_cache
        ),
        "btc_dominance": get_btc_dominance(
            apis.get("btc_dominance", "https://api.coingecko.com/api/v3/global"),
            macro_cache,
        ),
    }


# ====================================================================== #
# COMPONENTES DE SCORE
# ====================================================================== #
def check_timeframe_alignment(
    asset: str,
    action: str,
    alignment_tfs: List[str],
    store: SignalStore,
    current_tf: str,
    current_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Verifica se todos os timeframes de alinhamento apontam para a mesma direção.

    Usa o sinal atual para o timeframe de gatilho e os sinais armazenados para
    os timeframes superiores. Um timeframe é considerado 'alinhado' quando sua
    última ação registrada é igual à ação do gatilho.

    Retorna dict com: aligned (bool), details (por timeframe), missing (list).
    """
    details = {}
    missing = []
    aligned_count = 0

    for tf in alignment_tfs:
        if tf == current_tf:
            tf_action = action
        else:
            rec = store.get(asset, tf)
            tf_action = normalize_action(rec.get("action")) if rec else None

        details[tf] = tf_action
        if tf_action is None:
            missing.append(tf)
        elif tf_action == action:
            aligned_count += 1

    # Alinhado somente se TODOS conhecidos apontam na mesma direção e não há divergência
    known = [tf for tf in alignment_tfs if details[tf] is not None]
    aligned = (
        len(known) == len(alignment_tfs)
        and all(details[tf] == action for tf in alignment_tfs)
    )
    return {
        "aligned": aligned,
        "aligned_count": aligned_count,
        "details": details,
        "missing": missing,
    }


def collect_multi_tf_rsi(
    asset: str,
    alignment_tfs: List[str],
    store: SignalStore,
    current_tf: str,
    current_data: Dict[str, Any],
) -> Dict[str, Optional[float]]:
    """Coleta o RSI de cada timeframe de alinhamento (do store ou do sinal atual)."""
    rsis = {}
    for tf in alignment_tfs:
        if tf == current_tf:
            rsis[tf] = _safe_float(current_data.get("rsi14"))
        else:
            rec = store.get(asset, tf)
            rsis[tf] = _safe_float(rec.get("rsi14")) if rec else None
    return rsis


def calculate_technical_score(
    asset: str,
    action: str,
    bot_config: Dict[str, Any],
    store: SignalStore,
    current_tf: str,
    current_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calcula a parte TÉCNICA do score (máx. 90 pts) — calibrado para a
    estratégia Silent Sniper (RSI + HMA15 + alinhamento multi-timeframe):
      - Alinhamento multi-TF (55)  <- ESTRATÉGIA CENTRAL, domina o score
      - RSI confirmação (15)       <- bônus tolerante, não bloqueia
      - Cipher B / WaveTrend (10)  <- bônus opcional (não faz parte do Sniper)
      - Volume (10)                <- bônus opcional, crédito neutro se sem base

    Filosofia: quando os 3 timeframes do Silent Sniper estão ALINHADOS, o
    setup deve poder ser aprovado. Cipher/Volume/RSI-window nunca devem
    derrubar um sinal alinhado (era a causa de "alinhado mas não dispara").
    """
    reasons: List[str] = []
    breakdown: Dict[str, int] = {}
    score = 0

    # Resolve os timeframes de alinhamento tolerando ambas as estruturas de
    # config ("timeframe_alignment" [lista] ou "timeframes" [dict]).
    alignment_tfs = _resolve_alignment_tfs(bot_config, current_tf)

    # ---- 1. Alinhamento de timeframes (30 pts) ----
    align = check_timeframe_alignment(
        asset, action, alignment_tfs, store, current_tf, current_data
    )
    # O alinhamento multi-timeframe do Silent Sniper É a estratégia central.
    # Por isso ele domina o score (55 pts). RSI/Cipher/Volume abaixo são
    # apenas CONFIRMAÇÕES (bônus) e nunca devem bloquear um setup alinhado.
    total_tfs = len(alignment_tfs)
    contradiction = any(
        v is not None and v != action for v in align["details"].values()
    )
    if align["aligned"]:
        score += 55
        breakdown["alignment"] = 55
        reasons.append(
            f"Timeframes {' + '.join(alignment_tfs)} ALINHADOS ({action}) (+55)"
        )
    elif not contradiction and align["aligned_count"] >= 1:
        # Alinhamento parcial (falta dado de algum TF, mas nenhum contradiz):
        # crédito proporcional, insuficiente sozinho para aprovar.
        partial = int(round(55 * align["aligned_count"] / max(total_tfs, 1)))
        score += partial
        breakdown["alignment"] = partial
        reasons.append(
            f"Alinhamento parcial {align['aligned_count']}/{total_tfs} "
            f"(faltam: {', '.join(align['missing']) or 'n/d'}) (+{partial})"
        )
    else:
        breakdown["alignment"] = 0
        reasons.append(
            f"Timeframes desalinhados/contraditórios: {align['details']}"
        )

    # ---- 2. RSI saudável (20 pts) ----
    rsis = collect_multi_tf_rsi(
        asset, alignment_tfs, store, current_tf, current_data
    )
    trigger_rsi = _safe_float(current_data.get("rsi14"))

    # Bandas TOLERANTES: o Silent Sniper já validou RSI+HMA no TradingView.
    # Aqui o RSI (recalculado da Bitget) é só confirmação — usamos margem
    # ampla para tolerar diferenças de feed entre TradingView e Bitget e para
    # aceitar CONTINUAÇÃO de tendência (não só pullback).
    def rsi_healthy(v: Optional[float]) -> bool:
        if v is None:
            return False
        if action == "buy":
            return v >= 45  # momentum de alta (tolerante)
        return v <= 55      # momentum de baixa (tolerante)

    rsi_pts = 0
    if rsi_healthy(trigger_rsi):
        rsi_pts += 10
    known_rsis = [v for v in rsis.values() if v is not None]
    if known_rsis and all(rsi_healthy(v) for v in rsis.values() if v is not None) and len(known_rsis) == len(alignment_tfs):
        rsi_pts += 5
    score += rsi_pts
    breakdown["rsi"] = rsi_pts
    rsi_str = " | ".join(
        f"{tf}: {int(v)}" if v is not None else f"{tf}: n/d"
        for tf, v in rsis.items()
    )
    reasons.append(f"RSI {rsi_str} (+{rsi_pts})")

    # ---- 3. Cipher B / WaveTrend (15 pts) ----
    wt1 = _safe_float(current_data.get("cipher_wt1"))
    wt2 = _safe_float(current_data.get("cipher_wt2"))
    cipher_pts = 0
    if wt1 is not None and wt2 is not None:
        if action == "buy" and wt1 > wt2 and wt1 < -20:
            cipher_pts = 10
            reasons.append("Cipher B bullish (WT1>WT2 e sobrevendido) (+10)")
        elif action == "sell" and wt1 < wt2 and wt1 > 20:
            cipher_pts = 10
            reasons.append("Cipher B bearish (WT1<WT2 e sobrecomprado) (+10)")
        else:
            reasons.append(f"Cipher B neutro (WT1={wt1}, WT2={wt2})")
    else:
        reasons.append("Cipher B sem dados")
    score += cipher_pts
    breakdown["cipher"] = cipher_pts

    # ---- 4. Volume (10 pts) ----
    vol = _safe_float(current_data.get("volume"))
    # Média de volume: usa o histórico do store; se insuficiente, cai para a
    # média calculada a partir dos candles reais da Bitget (_avg_volume).
    avg_vol = store.avg_volume(asset, current_tf) or _safe_float(current_data.get("_avg_volume"))
    # Volume NÃO faz parte do Silent Sniper (RSI+HMA). É só um bônus de
    # confirmação. Quando não há base confiável (candles de futuros da Bitget
    # às vezes vêm com volume ~0), damos crédito NEUTRO em vez de penalizar.
    vol_pts = 0
    if vol is not None and avg_vol and avg_vol > 0:
        ratio = vol / avg_vol
        if ratio > 1.3:
            vol_pts = 10
            reasons.append(f"Volume {ratio:.1f}x da média (+10)")
        elif ratio >= 0.5:
            vol_pts = 5
            reasons.append(f"Volume {ratio:.1f}x da média (neutro +5)")
        else:
            vol_pts = 5
            reasons.append(f"Volume {ratio:.1f}x baixo (crédito neutro +5)")
    else:
        vol_pts = 5
        reasons.append("Volume sem base confiável (crédito neutro +5)")
    score += vol_pts
    breakdown["volume"] = vol_pts

    return {
        "score": score,
        "breakdown": breakdown,
        "reasons": reasons,
        "alignment": align,
        "rsis": rsis,
        "cipher": {"wt1": wt1, "wt2": wt2},
        "volume": {"value": vol, "avg": avg_vol},
    }


def calculate_macro_score(
    asset: str,
    macro: Dict[str, Any],
    news: Dict[str, int],
) -> Dict[str, Any]:
    """
    Calcula a parte MACRO do score:
      - Fear & Greed (10)
      - Dominância BTC (10)
      - Notícias (5)
    Pode gerar pontos negativos (penalidades) conforme o plano.
    """
    reasons: List[str] = []
    breakdown: Dict[str, int] = {}
    score = 0

    # ---- Fear & Greed (10 pts) ----
    fg = macro.get("fear_greed")
    fg_pts = 0
    if fg is not None:
        if fg < 30:
            fg_pts = 10  # medo extremo -> contrarian bullish
            reasons.append(f"Fear & Greed {fg} (Medo) contrarian (+10)")
        elif fg > 75:
            fg_pts = -5  # ganância extrema -> cautela
            reasons.append(f"Fear & Greed {fg} (Ganância Extrema) (-5)")
        else:
            reasons.append(f"Fear & Greed {fg} (neutro)")
    else:
        reasons.append("Fear & Greed indisponível")
    score += fg_pts
    breakdown["fear_greed"] = fg_pts

    # ---- Dominância BTC (10 pts) ----
    dom = macro.get("btc_dominance")
    dom_pts = 0
    if dom is not None:
        if dom > 55:
            if asset == "BTC":
                dom_pts = 10
                reasons.append(f"BTC.D {dom:.1f}% favorece BTC (+10)")
            else:
                dom_pts = -5
                reasons.append(f"BTC.D {dom:.1f}% pressiona alts (-5)")
        else:
            if asset != "BTC":
                dom_pts = 5
                reasons.append(f"BTC.D {dom:.1f}% favorece alts (+5)")
            else:
                reasons.append(f"BTC.D {dom:.1f}% (neutro p/ BTC)")
    else:
        reasons.append("Dominância BTC indisponível")
    score += dom_pts
    breakdown["btc_dominance"] = dom_pts

    # ---- Notícias (5 pts) ----
    news_pts = 0
    pos = news.get("positive", 0)
    neg = news.get("negative", 0)
    if pos > 3:
        news_pts = 5
        reasons.append(f"Notícias: {pos} positivas, {neg} negativas (+5)")
    elif news.get("total", 0) > 0:
        reasons.append(f"Notícias: {pos} positivas, {neg} negativas")
    else:
        reasons.append("Notícias: sem dados")
    score += news_pts
    breakdown["news"] = news_pts

    return {"score": score, "breakdown": breakdown, "reasons": reasons}


# ====================================================================== #
# ENRIQUECIMENTO COM DADOS REAIS DA BITGET
# ====================================================================== #
def _resolve_symbol(bot_config: Dict[str, Any]) -> Optional[str]:
    """Extrai o símbolo Bitget do bot_config (aceita as duas estruturas de config)."""
    sym = bot_config.get("symbol")
    return market_data.normalize_symbol(sym) if sym else None


def _resolve_alignment_tfs(bot_config: Dict[str, Any], current_tf: str) -> List[str]:
    """
    Devolve a lista de timeframes de alinhamento, tolerando as duas estruturas
    de config:
      - Estrutura "bots":   {"timeframe_trigger": "15m", "timeframe_alignment": ["15m","1h","4h"]}
      - Estrutura "assets": {"timeframes": {"primary": "15m", "secondary": "1h", "tertiary": "4h"}}
    """
    if bot_config.get("timeframe_alignment"):
        return list(bot_config["timeframe_alignment"])
    tfs = bot_config.get("timeframes")
    if isinstance(tfs, dict) and tfs:
        return [str(v) for v in tfs.values() if v]
    return [current_tf]


def enrich_from_market(
    asset: str,
    bot_config: Dict[str, Any],
    store: "SignalStore",
    current_tf: str,
    webhook_data: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """
    Preenche, a partir dos dados REAIS da Bitget, os indicadores que estiverem
    faltando — tanto no timeframe de gatilho (webhook_data) quanto nos
    timeframes de alinhamento (injetados no SignalStore).

    Isso elimina o problema de "n/d": mesmo que o TradingView não envie
    rsi14/cipher/volume, ou que os timeframes superiores não tenham alerta
    próprio, o bot passa a calcular tudo localmente com candles da Bitget.
    """
    symbol = _resolve_symbol(bot_config)
    if not symbol:
        logger.warning("%s: sem 'symbol' no config; não é possível buscar dados da Bitget.", asset)
        return

    settings = config.get("settings", {})
    product_type = settings.get("product_type", "USDT-FUTURES")

    alignment_tfs = _resolve_alignment_tfs(bot_config, current_tf)
    trigger_action = normalize_action(webhook_data.get("action"))

    # ---- 1. Timeframe de gatilho: completa o que faltar no payload ----
    ind = market_data.get_indicators(symbol, current_tf, product_type=product_type)
    if ind.get("ok"):
        if _safe_float(webhook_data.get("rsi14")) is None and ind["rsi14"] is not None:
            webhook_data["rsi14"] = ind["rsi14"]
        if _safe_float(webhook_data.get("cipher_wt1")) is None and ind["cipher_wt1"] is not None:
            webhook_data["cipher_wt1"] = ind["cipher_wt1"]
        if _safe_float(webhook_data.get("cipher_wt2")) is None and ind["cipher_wt2"] is not None:
            webhook_data["cipher_wt2"] = ind["cipher_wt2"]
        if _safe_float(webhook_data.get("volume")) is None and ind["volume"] is not None:
            webhook_data["volume"] = ind["volume"]
        # Guarda a média de volume calculada da Bitget para o scoring de volume
        if ind.get("avg_volume") is not None:
            webhook_data["_avg_volume"] = ind["avg_volume"]
        if _safe_float(webhook_data.get("price")) is None and ind.get("close") is not None:
            webhook_data["price"] = ind["close"]
        webhook_data["_market_source"] = "bitget"
    else:
        logger.warning("%s: não foi possível obter dados da Bitget para %s/%s.",
                       asset, symbol, current_tf)

    # ---- 2. Timeframes de alinhamento: injeta bias/rsi no store se ausente ----
    for tf in alignment_tfs:
        if tf == current_tf:
            continue
        existing = store.get(asset, tf)
        # Se já existe um alerta recente do TradingView com ação, respeitamos ele.
        if existing and normalize_action(existing.get("action")) is not None:
            # Ainda assim completa RSI/cipher/volume que faltem
            tf_ind = market_data.get_indicators(symbol, tf, product_type=product_type)
            if tf_ind.get("ok"):
                merged = dict(existing)
                for k in ("rsi14", "cipher_wt1", "cipher_wt2", "volume"):
                    if _safe_float(merged.get(k)) is None and tf_ind.get(k) is not None:
                        merged[k] = tf_ind[k]
                if tf_ind.get("avg_volume") is not None:
                    merged["_avg_volume"] = tf_ind["avg_volume"]
                store.update(asset, tf, merged)
            continue

        # Sem alerta próprio -> calcula tudo da Bitget e injeta no store
        tf_ind = market_data.get_indicators(symbol, tf, product_type=product_type)
        if not tf_ind.get("ok"):
            continue
        # Direção: usa o bias calculado; se neutro, herda a ação do gatilho para
        # não bloquear injustamente o alinhamento por indefinição de HMA.
        direction = tf_ind.get("direction") or trigger_action
        synthetic = {
            "action": direction,
            "timeframe": tf,
            "rsi14": tf_ind.get("rsi14"),
            "cipher_wt1": tf_ind.get("cipher_wt1"),
            "cipher_wt2": tf_ind.get("cipher_wt2"),
            "volume": tf_ind.get("volume"),
            "_avg_volume": tf_ind.get("avg_volume"),
            "price": tf_ind.get("close"),
            "_market_source": "bitget",
            "_synthetic": True,
        }
        store.update(asset, tf, synthetic)


# ====================================================================== #
# FUNÇÃO PRINCIPAL
# ====================================================================== #
def analyze_signal(
    asset: str,
    webhook_data: Dict[str, Any],
    bot_config: Dict[str, Any],
    store: SignalStore,
    config: Dict[str, Any],
    macro: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Analisa um sinal recebido e devolve o veredito completo.

    Retorna um dicionário com:
      - approved (bool)
      - action ('buy'/'sell')
      - score (int)
      - threshold (int)
      - reasons (list[str])
      - breakdown (dict)
      - macro (dict)
      - news (dict)
    """
    action = normalize_action(webhook_data.get("action"))
    current_tf = str(webhook_data.get("timeframe", bot_config.get("timeframe_trigger", "")))
    threshold = int(bot_config.get("score_threshold", 60))

    # Se a ação não for válida, rejeita imediatamente
    if action is None:
        return {
            "approved": False,
            "action": None,
            "score": 0,
            "threshold": threshold,
            "reasons": ["Ação inválida ou ausente no payload"],
            "breakdown": {},
            "macro": macro or {},
            "news": {"positive": 0, "negative": 0, "total": 0},
        }

    # Enriquecimento com dados REAIS da Bitget (RSI, Cipher B, volume, alinhamento).
    # Preenche o que o TradingView não mandou e evita o problema de "n/d".
    try:
        enrich_from_market(asset, bot_config, store, current_tf, webhook_data, config)
    except Exception as exc:  # noqa: BLE001 - nunca deixa a análise quebrar por causa de dados
        logger.warning("%s: falha ao enriquecer com dados da Bitget: %s", asset, exc)

    # Macro (usa cache); se não passado, busca
    if macro is None:
        macro = get_macro_context(config)

    # Notícias por ativo
    settings = config.get("settings", {})
    news = get_crypto_news(
        config.get("apis", {}).get(
            "crypto_news", "https://cryptopanic.com/api/free/v1/posts/"
        ),
        asset,
        int(settings.get("news_cache_seconds", 900)),
        settings.get("cryptopanic_auth_token", ""),
    )

    # Score técnico + macro
    tech = calculate_technical_score(
        asset, action, bot_config, store, current_tf, webhook_data
    )
    macro_score = calculate_macro_score(asset, macro, news)

    total = tech["score"] + macro_score["score"]
    total = max(0, min(100, total))  # limita ao intervalo 0-100

    reasons = tech["reasons"] + macro_score["reasons"]
    breakdown = {**tech["breakdown"], **macro_score["breakdown"]}

    approved = total >= threshold

    return {
        "approved": approved,
        "action": action,
        "score": total,
        "threshold": threshold,
        "reasons": reasons,
        "breakdown": breakdown,
        "technical": tech,
        "macro": macro,
        "news": news,
    }
