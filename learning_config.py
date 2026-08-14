# -*- coding: utf-8 -*-
"""
learning_config.py — Camada de APRENDIZADO (self-learning) do BOT-SNIPER cripto.
================================================================================
Este modulo aplica, de forma 100% BACKWARDS-COMPATIBLE, os overrides definidos
em `learning_config.json` sobre o `config.json` do bot.

FILOSOFIA DE SEGURANCA (leia antes de mexer):
  * Se `learning_config.json` NAO existir -> `mesclar_config(config)` devolve o
    config ORIGINAL sem tocar em nada. O bot funciona EXATAMENTE como antes.
  * Se existir -> apenas os campos MAPEADOS abaixo sao sobrescritos. Nada mais
    do config.json e alterado.
  * O merge trabalha sobre uma COPIA PROFUNDA: nunca muta o dict original.
  * Qualquer erro ao ler/aplicar o learning_config e ENGOLIDO (log) e o config
    original e devolvido — o bot nunca quebra por causa desta camada.

MAPEAMENTO learning_config.json -> config.json:
  moedas_focadas       -> execucao_real.moedas
  tp_sl_por_tf[tf]     -> simulacao_por_tf[tf].tp_percent / sl_percent  (SOMBRA)
  grades_operar        -> execucao_real.grades_permitidas
  leverage_por_grade   -> execucao_real.alavancagem_grade_a (grade "A")
                          execucao_real.alavancagem_base    (grade "B")
  margem_usdt          -> execucao_real.margem_usdt E simulacao.margin_usdt
  max_posicoes         -> execucao_real.max_posicoes
  janela_entradas_seg  -> reconciliacao.janela_seg
  timeframes_ativos    -> execucao_real.timeframes

Campos SO informativos (nao alteram comportamento hoje):
  grades_dobrar, estrategia_tf, metas  (metas sao usadas pelo agent_metrics.py).

Todos os comentarios/mensagens em Portugues.
"""
from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger("learning_config")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEARNING_CONFIG_PATH = os.path.join(BASE_DIR, "learning_config.json")


def caminho_learning_config() -> str:
    """Caminho absoluto do learning_config.json (na pasta do projeto)."""
    return LEARNING_CONFIG_PATH


def existe_learning_config() -> bool:
    return os.path.exists(LEARNING_CONFIG_PATH)


def carregar_learning_config() -> Optional[Dict[str, Any]]:
    """Le o learning_config.json. Retorna dict ou None (se ausente/erro).

    NUNCA lanca excecao — em caso de erro devolve None e o bot segue com o
    config.json puro.
    """
    if not existe_learning_config():
        return None
    try:
        with open(LEARNING_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("[LEARNING] learning_config.json nao e um objeto JSON — ignorando.")
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        logger.error("[LEARNING] Falha ao ler learning_config.json (%s) — usando config.json puro.", exc)
        return None


def salvar_learning_config(learn: Dict[str, Any]) -> bool:
    """Grava um novo learning_config.json no disco (atomico via arquivo temporario).

    Retorna True em sucesso, False em falha (sem lancar excecao).
    """
    try:
        tmp = LEARNING_CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(learn, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LEARNING_CONFIG_PATH)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("[LEARNING] Falha ao salvar learning_config.json: %s", exc)
        return False


def _num(valor: Any) -> Optional[float]:
    """Converte para float com seguranca (None se nao der)."""
    try:
        if valor is None:
            return None
        return float(valor)
    except (TypeError, ValueError):
        return None


def aplicar_overrides(config: Dict[str, Any], learn: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica os overrides do learning_config sobre uma COPIA do config.

    Retorna a copia mesclada. So mexe nos campos mapeados; tudo mais e preservado.
    """
    cfg = copy.deepcopy(config or {})

    # Garante os sub-dicts que vamos tocar (sem sobrescrever se ja existem).
    exec_real = cfg.setdefault("execucao_real", {})
    simulacao = cfg.setdefault("simulacao", {})
    sim_por_tf = cfg.setdefault("simulacao_por_tf", {})
    reconc = cfg.setdefault("reconciliacao", {})

    # --- moedas_focadas -> execucao_real.moedas + moedas_por_tf coerente ------
    moedas_focadas = learn.get("moedas_focadas")
    if isinstance(moedas_focadas, list) and moedas_focadas:
        moedas_up = [str(m).upper() for m in moedas_focadas]
        exec_real["moedas"] = moedas_up

    # --- tp_sl_por_tf -> simulacao_por_tf[tf].tp_percent / sl_percent ---------
    tp_sl = learn.get("tp_sl_por_tf")
    if isinstance(tp_sl, dict):
        for tf, valores in tp_sl.items():
            if str(tf).startswith("_") or not isinstance(valores, dict):
                continue
            alvo = sim_por_tf.setdefault(tf, {})
            tp = _num(valores.get("tp_percent"))
            sl = _num(valores.get("sl_percent"))
            if tp is not None:
                alvo["tp_percent"] = tp
            if sl is not None:
                alvo["sl_percent"] = sl

    # --- grades_operar -> execucao_real.grades_permitidas ---------------------
    grades = learn.get("grades_operar")
    if isinstance(grades, list) and grades:
        exec_real["grades_permitidas"] = [str(g).upper() for g in grades]

    # --- leverage_por_grade -> alavancagem_grade_a (A) e alavancagem_base (B) -
    lev = learn.get("leverage_por_grade")
    if isinstance(lev, dict):
        lev_a = _num(lev.get("A"))
        lev_b = _num(lev.get("B"))
        if lev_a is not None:
            exec_real["alavancagem_grade_a"] = int(lev_a)
        if lev_b is not None:
            exec_real["alavancagem_base"] = int(lev_b)

    # --- margem_usdt -> execucao_real.margem_usdt E simulacao.margin_usdt ------
    margem = _num(learn.get("margem_usdt"))
    if margem is not None and margem > 0:
        exec_real["margem_usdt"] = margem
        simulacao["margin_usdt"] = margem

    # --- max_posicoes -> execucao_real.max_posicoes ---------------------------
    max_pos = _num(learn.get("max_posicoes"))
    if max_pos is not None and max_pos > 0:
        exec_real["max_posicoes"] = int(max_pos)

    # --- janela_entradas_seg -> reconciliacao.janela_seg ----------------------
    janela = _num(learn.get("janela_entradas_seg"))
    if janela is not None and janela > 0:
        reconc["janela_seg"] = janela

    # --- timeframes_ativos -> execucao_real.timeframes ------------------------
    tfs = learn.get("timeframes_ativos")
    if isinstance(tfs, list) and tfs:
        exec_real["timeframes"] = [str(t) for t in tfs]

    # Marca de rastreio (nao afeta a estrategia; util no /diag e nos logs).
    cfg["_learning_config_aplicado"] = {
        "version": learn.get("version"),
        "updated_at": learn.get("updated_at"),
        "updated_by": learn.get("updated_by"),
    }
    return cfg


def mesclar_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ponto de entrada. Devolve o config com os overrides do learning_config.

    * Sem learning_config.json -> devolve o config ORIGINAL (mesma referencia),
      preservando 100% o comportamento antigo.
    * Com learning_config.json -> devolve uma COPIA mesclada.
    * Qualquer erro -> devolve o config original (fail-safe).
    """
    learn = carregar_learning_config()
    if not learn:
        return config
    try:
        cfg = aplicar_overrides(config, learn)
        logger.info("[LEARNING] learning_config.json v%s aplicado sobre o config.json.",
                    learn.get("version"))
        return cfg
    except Exception as exc:  # noqa: BLE001
        logger.error("[LEARNING] Erro ao aplicar overrides (%s) — usando config.json puro.", exc)
        return config
