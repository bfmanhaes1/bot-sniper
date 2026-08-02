# -*- coding: utf-8 -*-
"""
confirmacao.py — Camada de CONFIRMAÇÃO (gate) por MOEDA + TIMEFRAME
==================================================================
Replica no Bot SNIPER (cripto) o modelo comprovado do "bot verde" do MNQ:
os indicadores fechados (TSTS Core = BOKK; TSTS BS Detector = histograma +
plot1/2/3) mandam a COR ATUAL de cada componente para o bot, que guarda esse
estado. Quando chega o sinal do Sniper (rosa x azul) já confirmado pelo RSI,
o bot só ENTRA se TODAS as cores estiverem de acordo com a regra. Caso
contrário, NÃO entra (registra o motivo em modo sombra).

REGRA (definida pelo usuário — a VENDA é o espelho exato da COMPRA):
  COMPRA (LONG):
    • BOKK ......... VERDE   (aceita a mudança de cor até N velas antes — tolerância)
    • Histograma ... VERMELHO
    • Plot 1/2/3 ... VERDES
  VENDA (SHORT) = espelho:
    • BOKK ......... VERMELHO (tolerância)
    • Histograma ... VERDE
    • Plot 1/2/3 ... VERMELHOS

Tudo é dirigido por config (bloco "confirmacao") para ajuste fácil:
  - "ativa": liga/desliga o gate inteiro.
  - "bokk_tolerancia_velas": quantas velas o BOKK pode ter mudado de cor ANTES
    do sinal e ainda valer (frescor do BOKK; 0 = desliga o frescor).
  - "exigir": para cada componente, se a cor exigida é "mesma" (igual à direção
    do trade: buy=verde/sell=vermelho) ou "oposta".

Este módulo NÃO fala com corretora nem TradingView; só guarda estado e decide.
Todos os comentários e mensagens em Português.
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("confirmacao")

# Componentes rastreados (ordem usada nas mensagens de diagnóstico).
COMPONENTES = ("bokk", "histograma", "plot1", "plot2", "plot3")

# Regra padrão: qual cor cada componente precisa ter em relação à direção do
# trade. "mesma" = buy→verde / sell→vermelho. "oposta" = o contrário.
_EXIGIR_PADRAO = {
    "bokk": "mesma",
    "histograma": "oposta",   # ⚠️ regra do usuário: COMPRA pede histograma VERMELHO
    "plot1": "mesma",
    "plot2": "mesma",
    "plot3": "mesma",
}


def normalizar_cor(valor: Any) -> Optional[str]:
    """
    Converte várias formas de entrada para 'green' ou 'red'.
    Aceita: green/verde/buy/long/up/bull/1 -> green
            red/vermelho/sell/short/down/bear/-1 -> red
    Retorna None se não reconhecer.
    """
    s = str(valor if valor is not None else "").strip().lower()
    if s in ("green", "verde", "buy", "long", "up", "bull", "alta", "1", "compra"):
        return "green"
    if s in ("red", "vermelho", "sell", "short", "down", "bear", "baixa", "-1", "venda"):
        return "red"
    return None


class ConfirmStore:
    """Guarda a cor atual de cada componente por MOEDA+TIMEFRAME e decide o gate."""

    def __init__(self, config: Dict[str, Any]):
        conf = (config or {}).get("confirmacao", {}) or {}
        self.ativa: bool = bool(conf.get("ativa", True))
        self.bokk_tol_velas: int = int(conf.get("bokk_tolerancia_velas", 3))
        exigir = dict(_EXIGIR_PADRAO)
        for k, v in (conf.get("exigir") or {}).items():
            if k in _EXIGIR_PADRAO and str(v).lower() in ("mesma", "oposta"):
                exigir[k] = str(v).lower()
        self.exigir: Dict[str, str] = exigir
        # Estado: chave "MOEDA_TF" -> {componente: {"cor": "green"/"red", "ts": epoch}}
        self._estado: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _chave(moeda: str, tf: str) -> str:
        return f"{(moeda or '').upper()}_{tf}"

    def atualizar(self, componente: str, moeda: str, tf: str, cor: str) -> Dict[str, Any]:
        """Registra a cor atual de UM componente para uma combinação moeda+TF."""
        componente = (componente or "").strip().lower()
        if componente not in COMPONENTES:
            return {"ok": False, "error": f"componente '{componente}' desconhecido"}
        cor_norm = normalizar_cor(cor)
        if cor_norm is None:
            return {"ok": False, "error": f"cor '{cor}' não reconhecida (use green/red)"}
        chave = self._chave(moeda, tf)
        with self._lock:
            self._estado.setdefault(chave, {})[componente] = {
                "cor": cor_norm, "ts": time.time()
            }
        logger.info("Confirmação %s: %s=%s", chave, componente, cor_norm)
        return {"ok": True, "componente": componente, "moeda": (moeda or "").upper(),
                "timeframe": tf, "cor": cor_norm}

    def atualizar_varios(self, moeda: str, tf: str,
                         cores: Dict[str, Any]) -> Dict[str, Any]:
        """
        Atualiza vários componentes de uma vez (usado pelo helper consolidado do
        BS Detector, que manda hist/plot1/plot2/plot3 numa única mensagem).
        `cores` ex.: {"hist":"red","p1":"green","p2":"green","p3":"green"}
        Aceita apelidos: hist->histograma, p1/plot_1->plot1, etc.
        """
        apelidos = {
            "hist": "histograma", "histograma": "histograma", "histogram": "histograma",
            "p1": "plot1", "plot_1": "plot1", "plot1": "plot1",
            "p2": "plot2", "plot_2": "plot2", "plot2": "plot2",
            "p3": "plot3", "plot_3": "plot3", "plot3": "plot3",
            "bokk": "bokk",
        }
        aplicados = {}
        for k, v in (cores or {}).items():
            comp = apelidos.get(str(k).strip().lower())
            if not comp:
                continue
            r = self.atualizar(comp, moeda, tf, v)
            if r.get("ok"):
                aplicados[comp] = r["cor"]
        if not aplicados:
            return {"ok": False, "error": "nenhum componente/cor válido no payload"}
        return {"ok": True, "moeda": (moeda or "").upper(), "timeframe": tf,
                "aplicados": aplicados}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _cor_alvo(action: str, regra: str) -> str:
        """Cor exigida para um componente dado o lado do trade e a regra."""
        base = "green" if action == "buy" else "red"
        if regra == "oposta":
            base = "red" if base == "green" else "green"
        return base

    def estado_combo(self, moeda: str, tf: str) -> Dict[str, Any]:
        """Devolve o estado atual (cores) de uma combinação, para diagnóstico."""
        with self._lock:
            st = self._estado.get(self._chave(moeda, tf), {})
            return {c: dict(st[c]) for c in st}

    def checar(self, moeda: str, tf: str, action: str,
               tf_minutos: float) -> Tuple[bool, Dict[str, Any]]:
        """
        Decide se a entrada pode ocorrer.
        Retorna (ok, detalhe). `ok=False` => NÃO entra (registra o detalhe).

        Regras:
          - Todo componente precisa estar na cor exigida (config "exigir").
          - Componente SEM cor recebida ainda => bloqueia (fail-closed).
          - BOKK: além da cor certa, o registro precisa estar "fresco" — a
            última atualização foi há no máximo `bokk_tolerancia_velas` velas
            (usa tf_minutos). tolerância 0 => ignora o frescor.
        """
        if not self.ativa:
            return True, {"ativa": False, "motivo": "gate desligado"}
        action = (action or "").lower()
        if action not in ("buy", "sell"):
            return False, {"motivo": f"ação inválida: {action!r}"}

        with self._lock:
            st = dict(self._estado.get(self._chave(moeda, tf), {}))

        agora = time.time()
        faltando: List[str] = []
        errados: List[str] = []
        stale_bokk = False
        detalhe_comp: Dict[str, Any] = {}

        for comp in COMPONENTES:
            regra = self.exigir.get(comp, "mesma")
            alvo = self._cor_alvo(action, regra)
            reg = st.get(comp)
            if not reg or not reg.get("cor"):
                faltando.append(comp)
                detalhe_comp[comp] = {"exigido": alvo, "recebido": None}
                continue
            cor = reg["cor"]
            detalhe_comp[comp] = {"exigido": alvo, "recebido": cor}
            if cor != alvo:
                errados.append(comp)
            # Frescor só para o BOKK (tolerância em velas).
            if comp == "bokk" and self.bokk_tol_velas > 0:
                idade_min = (agora - float(reg.get("ts", 0))) / 60.0
                limite_min = self.bokk_tol_velas * max(tf_minutos, 0.0001)
                detalhe_comp[comp]["idade_min"] = round(idade_min, 2)
                detalhe_comp[comp]["limite_min"] = round(limite_min, 2)
                if idade_min > limite_min:
                    stale_bokk = True

        ok = (not faltando) and (not errados) and (not stale_bokk)
        detalhe = {
            "ativa": True,
            "action": action,
            "moeda": (moeda or "").upper(),
            "timeframe": tf,
            "ok": ok,
            "componentes": detalhe_comp,
        }
        if not ok:
            motivos = []
            if faltando:
                motivos.append(f"sem dados: {', '.join(faltando)}")
            if errados:
                motivos.append(f"cor errada: {', '.join(errados)}")
            if stale_bokk:
                motivos.append(f"BOKK fora da tolerância de {self.bokk_tol_velas} velas")
            detalhe["motivo"] = " | ".join(motivos)
        else:
            detalhe["motivo"] = "todas as confirmações alinhadas"
        return ok, detalhe

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ativa": self.ativa,
                "bokk_tolerancia_velas": self.bokk_tol_velas,
                "exigir": dict(self.exigir),
                "combinacoes_com_estado": len(self._estado),
                "estado": {k: {c: v[c] for c in v} for k, v in self._estado.items()},
            }
