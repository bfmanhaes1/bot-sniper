# -*- coding: utf-8 -*-
"""
agent/agent_metrics.py — Metricas para o agente self-learning (BOT-SNIPER cripto).
==================================================================================
Le os logs de trades (PostgreSQL via crypto_logger, com fallback para
crypto2_logs/*.json) e calcula as metricas que o LOOP DE REFLEXAO consome para
decidir se muda a estrategia (learning_config.json):

  - trades_fechados        : nº de trades fechados no dia (dedup por alavancagem)
  - win_rate_pct           : % de trades vencedores
  - pnl_usd                : P&L total em USD (na alavancagem de referencia)
  - pnl_pct_capital        : P&L em % do capital total
  - dd_max_pct             : drawdown maximo da curva de equity (% do capital)
  - por_moeda              : breakdown por moeda (trades, win_rate, pnl_usd)
  - moedas_melhores/pior   : ranking por P&L
  - trades_desde_ultimo_ciclo : trades fechados desde o ultimo ciclo de reflexao
  - meta_atingida / score  : comparacao com as metas do learning_config.json

IMPORTANTE (limitacao conhecida): o bot roda em MODO SOMBRA e a execucao real
(Bitget) nao devolve o fill de fechamento. Portanto as metricas de P&L vem dos
trades SIMULADOS (sombra) — que sao a fonte confiavel de performance hoje.

O evento de SAIDA guarda `resultado_simulado` como um DICT:
  {"pnl_pct": ..., "pnl_usdt_5x": ..., "pnl_usdt_10x": ..., "ganho": bool, ...}
Cada trade gera UMA SAIDA por alavancagem (5x e 10x). Para nao contar em dobro,
filtramos por uma alavancagem de referencia (padrao 5x).

Todos os comentarios/mensagens em Portugues.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------------ #
# Paths / imports (mesmo padrao do resumo_diario.py)
# ------------------------------------------------------------------ #
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(AGENT_DIR)          # raiz do projeto (bot_tsts_sniper)
LOGS_DIR = os.path.join(BASE_DIR, "crypto2_logs")
AGENT_STATE_PATH = os.path.join(AGENT_DIR, "agent_state.json")
LEARNING_CONFIG_PATH = os.path.join(BASE_DIR, "learning_config.json")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import crypto_logger  # PostgreSQL + fallback JSON
    HAS_CRYPTO_LOGGER = True
except Exception:  # noqa: BLE001
    HAS_CRYPTO_LOGGER = False
    crypto_logger = None  # type: ignore

# Alavancagem de referencia para nao contar o mesmo trade 2x (5x e 10x).
ALAV_REFERENCIA = "5x"
CAPITAL_PADRAO = 360.0  # fallback se nao houver capital no config


# ================================================================== #
# Leitura de dados
# ================================================================== #
def _hoje_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ler_eventos_dia(dia: Optional[str] = None) -> List[Dict[str, Any]]:
    """Le todos os eventos de um dia (YYYY-MM-DD). PostgreSQL primario, JSON fallback."""
    if dia is None:
        dia = _hoje_utc()
    if HAS_CRYPTO_LOGGER and crypto_logger:
        try:
            eventos = crypto_logger.ler_dia(dia)
            if eventos:
                return eventos
        except Exception:  # noqa: BLE001
            pass
    # Fallback manual: crypto2_logs/crypto_YYYY-MM-DD.json
    caminho = os.path.join(LOGS_DIR, f"crypto_{dia}.json")
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, list) else []
    except Exception:  # noqa: BLE001
        return []


def _carregar_learning_config() -> Dict[str, Any]:
    try:
        if os.path.exists(LEARNING_CONFIG_PATH):
            with open(LEARNING_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _carregar_metas(learn: Dict[str, Any]) -> Dict[str, float]:
    metas = (learn.get("metas") or {}) if isinstance(learn, dict) else {}
    return {
        "lucro_min_diario_pct": float(metas.get("lucro_min_diario_pct", 5.0)),
        "dd_max_pct": float(metas.get("dd_max_pct", 22.5)),
        "win_rate_min_pct": float(metas.get("win_rate_min_pct", 55.0)),
        "lucro_por_trade_alvo_usd": float(metas.get("lucro_por_trade_alvo_usd", 1.0)),
        "trades_min_dia_por_moeda": float(metas.get("trades_min_dia_por_moeda", 5)),
    }


def _capital_total() -> float:
    """Capital total configurado (execucao_real.capital_total_usdt) ou fallback."""
    try:
        cfg_path = os.path.join(BASE_DIR, "config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cap = (cfg.get("execucao_real") or {}).get("capital_total_usdt")
        if cap:
            return float(cap)
    except Exception:  # noqa: BLE001
        pass
    return CAPITAL_PADRAO


# ================================================================== #
# Extracao de trades fechados (SAIDA)
# ================================================================== #
def _saida_pnl(res: Dict[str, Any]) -> Tuple[float, float, bool]:
    """Extrai (pnl_pct, pnl_usd_ref, ganho) de um resultado_simulado (dict).

    pnl_usd_ref usa a alavancagem de referencia; se ausente, deriva de pnl_pct.
    """
    pnl_pct = float(res.get("pnl_pct", 0.0) or 0.0)
    chave_usd = f"pnl_usdt_{ALAV_REFERENCIA}"
    pnl_usd = res.get(chave_usd)
    if pnl_usd is None:
        # deriva a partir de pnl_pct: margem*alav*pct. Sem margem no evento,
        # usa 50 * 5 (ref) como aproximacao.
        alav_num = float(ALAV_REFERENCIA.replace("x", "") or 5)
        pnl_usd = 50.0 * alav_num * (pnl_pct / 100.0)
    ganho = bool(res.get("ganho", pnl_pct > 0))
    return pnl_pct, float(pnl_usd), ganho


def extrair_trades_fechados(eventos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Retorna a lista de trades fechados (uma entrada por trade, na alav de ref).

    Cada item: {moeda, timeframe, pnl_pct, pnl_usd, ganho, hora}.
    """
    trades: List[Dict[str, Any]] = []
    for ev in eventos:
        if ev.get("evento") != "SAIDA":
            continue
        alav = str(ev.get("alavancagem") or "")
        # Dedup: fica so com a alavancagem de referencia. Se o log nao tiver a
        # de referencia, aceita a primeira alavancagem vista por (moeda,tf,hora).
        if alav and alav != ALAV_REFERENCIA:
            continue
        res = ev.get("resultado_simulado")
        if not isinstance(res, dict):
            continue
        pnl_pct, pnl_usd, ganho = _saida_pnl(res)
        trades.append({
            "moeda": (ev.get("moeda") or "?").upper(),
            "timeframe": ev.get("timeframe") or "?",
            "pnl_pct": round(pnl_pct, 4),
            "pnl_usd": round(pnl_usd, 4),
            "ganho": ganho,
            "hora": ev.get("hora") or ev.get("timestamp") or "",
        })
    # Se o filtro por alavancagem de referencia zerou tudo (logs sem "5x"),
    # refaz aceitando UMA saida por (moeda, tf, hora) para nao perder dados.
    if not trades:
        vistos = set()
        for ev in eventos:
            if ev.get("evento") != "SAIDA":
                continue
            res = ev.get("resultado_simulado")
            if not isinstance(res, dict):
                continue
            chave = (ev.get("moeda"), ev.get("timeframe"),
                     ev.get("hora") or ev.get("timestamp"))
            if chave in vistos:
                continue
            vistos.add(chave)
            pnl_pct, pnl_usd, ganho = _saida_pnl(res)
            trades.append({
                "moeda": (ev.get("moeda") or "?").upper(),
                "timeframe": ev.get("timeframe") or "?",
                "pnl_pct": round(pnl_pct, 4),
                "pnl_usd": round(pnl_usd, 4),
                "ganho": ganho,
                "hora": ev.get("hora") or ev.get("timestamp") or "",
            })
    return trades


def _max_drawdown_usd(trades: List[Dict[str, Any]]) -> float:
    """Drawdown maximo (USD) da curva de equity acumulada (ordem cronologica)."""
    ordenados = sorted(trades, key=lambda t: str(t.get("hora") or ""))
    equity = 0.0
    pico = 0.0
    dd_max = 0.0
    for t in ordenados:
        equity += float(t.get("pnl_usd", 0.0))
        if equity > pico:
            pico = equity
        dd = pico - equity
        if dd > dd_max:
            dd_max = dd
    return dd_max


# ================================================================== #
# Estado do ciclo de reflexao (a cada 5 trades)
# ================================================================== #
def carregar_estado() -> Dict[str, Any]:
    try:
        if os.path.exists(AGENT_STATE_PATH):
            with open(AGENT_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:  # noqa: BLE001
        pass
    return {}


def salvar_estado(estado: Dict[str, Any]) -> bool:
    try:
        tmp = AGENT_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        os.replace(tmp, AGENT_STATE_PATH)
        return True
    except Exception:  # noqa: BLE001
        return False


def marcar_ciclo(total_trades_dia: int, dia: Optional[str] = None) -> None:
    """Registra que um ciclo de reflexao foi executado neste ponto.

    O daemon self-learning chama isto apos aplicar (ou nao) uma mudanca, para
    que `trades_desde_ultimo_ciclo` reinicie a contagem.
    """
    if dia is None:
        dia = _hoje_utc()
    estado = carregar_estado()
    estado["ultimo_ciclo_dia"] = dia
    estado["ultimo_ciclo_trades"] = int(total_trades_dia)
    estado["ultimo_ciclo_em"] = datetime.now(timezone.utc).isoformat()
    salvar_estado(estado)


def _trades_desde_ultimo_ciclo(total_trades_dia: int, dia: str) -> int:
    estado = carregar_estado()
    if estado.get("ultimo_ciclo_dia") != dia:
        # Novo dia: conta todos os trades do dia.
        return total_trades_dia
    base = int(estado.get("ultimo_ciclo_trades", 0))
    return max(0, total_trades_dia - base)


# ================================================================== #
# Score vs metas
# ================================================================== #
def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def calcular_score(pnl_pct_capital: float, win_rate_pct: float,
                   dd_max_pct: float, metas: Dict[str, float]) -> float:
    """Score de -1 (longe da meta) a +1 (meta batida com folga).

    Combina 3 componentes:
      - lucro    (peso 0.5): pnl_pct_capital / lucro_min_diario_pct
      - win_rate (peso 0.3): (wr - wr_min) / wr_min
      - drawdown (peso 0.2): penaliza se dd_max_pct > dd_max_meta
    """
    alvo_lucro = metas.get("lucro_min_diario_pct", 5.0) or 5.0
    alvo_wr = metas.get("win_rate_min_pct", 55.0) or 55.0
    alvo_dd = metas.get("dd_max_pct", 22.5) or 22.5

    s_lucro = _clamp(pnl_pct_capital / alvo_lucro)
    s_wr = _clamp((win_rate_pct - alvo_wr) / alvo_wr)
    # DD: 0 se dentro da meta; ate -1 conforme excede.
    if dd_max_pct <= alvo_dd:
        s_dd = 0.0
    else:
        s_dd = _clamp(-(dd_max_pct - alvo_dd) / alvo_dd)

    score = 0.5 * s_lucro + 0.3 * s_wr + 0.2 * s_dd
    return round(_clamp(score), 3)


# ================================================================== #
# Metrica principal
# ================================================================== #
def calcular_metricas(dia: Optional[str] = None) -> Dict[str, Any]:
    """Calcula todas as metricas do dia para o agente self-learning."""
    if dia is None:
        dia = _hoje_utc()

    eventos = ler_eventos_dia(dia)
    trades = extrair_trades_fechados(eventos)
    learn = _carregar_learning_config()
    metas = _carregar_metas(learn)
    capital = _capital_total()

    total = len(trades)
    wins = sum(1 for t in trades if t["ganho"])
    win_rate = round((wins / total * 100.0), 1) if total else 0.0
    pnl_usd = round(sum(t["pnl_usd"] for t in trades), 2)
    pnl_por_trade = round((pnl_usd / total), 4) if total else 0.0
    pnl_pct_capital = round((pnl_usd / capital * 100.0), 2) if capital else 0.0
    dd_max_usd = round(_max_drawdown_usd(trades), 2)
    dd_max_pct = round((dd_max_usd / capital * 100.0), 2) if capital else 0.0

    # Breakdown por moeda
    por_moeda: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        m = t["moeda"]
        d = por_moeda.setdefault(m, {"trades": 0, "wins": 0, "pnl_usd": 0.0})
        d["trades"] += 1
        d["wins"] += 1 if t["ganho"] else 0
        d["pnl_usd"] += t["pnl_usd"]
    for m, d in por_moeda.items():
        d["win_rate"] = round((d["wins"] / d["trades"] * 100.0), 1) if d["trades"] else 0.0
        d["pnl_usd"] = round(d["pnl_usd"], 2)

    ranking = sorted(por_moeda.items(), key=lambda kv: kv[1]["pnl_usd"], reverse=True)
    moedas_melhores = [m for m, _ in ranking[:3]]
    pior_moeda = ranking[-1][0] if ranking else None

    trades_ciclo = _trades_desde_ultimo_ciclo(total, dia)
    score = calcular_score(pnl_pct_capital, win_rate, dd_max_pct, metas)

    # Meta atingida: lucro >= alvo diario E win rate >= alvo E DD dentro do limite.
    meta_atingida = (
        pnl_pct_capital >= metas["lucro_min_diario_pct"]
        and win_rate >= metas["win_rate_min_pct"]
        and dd_max_pct <= metas["dd_max_pct"]
    )

    return {
        "periodo": "hoje",
        "dia": dia,
        "trades_fechados": total,
        "win_rate_pct": win_rate,
        "pnl_usd": pnl_usd,
        "pnl_por_trade_usd": pnl_por_trade,
        "pnl_pct_capital": pnl_pct_capital,
        "dd_max_usd": dd_max_usd,
        "dd_max_pct": dd_max_pct,
        "capital_total_usd": capital,
        "trades_desde_ultimo_ciclo": trades_ciclo,
        "por_moeda": por_moeda,
        "moedas_melhores": moedas_melhores,
        "pior_moeda": pior_moeda,
        "learning_config_version": learn.get("version") if learn else None,
        "metas": metas,
        "meta_atingida": bool(meta_atingida),
        "score": score,
        "fonte": "sombra (simulado)",
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


# ================================================================== #
# CLI
# ================================================================== #
if __name__ == "__main__":
    dia_arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(calcular_metricas(dia_arg), indent=2, ensure_ascii=False))
