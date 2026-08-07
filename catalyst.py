# -*- coding: utf-8 -*-
"""
catalyst.py — Camada CATALISADORA (gate) por MOEDA
==================================================
Porta para o Bot SNIPER (cripto) o MESMO catalisador multi-timeframe do MNQ
(indicador "MNQ Catalyst - Ultimate Pro B Right"). No SNIPER o catalisador é
um FILTRO PURO: dado o sinal do Sniper (rosa x azul) já confirmado pelo RSI,
o catalisador só responde ENTRA ou ESPERA (não dimensiona ordem — em modo
sombra a entrada simulada é sempre fixa).

O indicador do TradingView manda, por MOEDA, um JSON com o estado de três
timeframes internos + o VWAP:
    {"c5m":"BULL/BEAR/NEUT","c15m":"...","c1h":"...","vwap":"BULL/BEAR/NEUT"}

REGRAS (as mesmas 9 do MNQ — Azul/Roxo/Sniper compartilham o conjunto).
Referência = a DIREÇÃO DO SINAL do Sniper (buy => alvo BULL; sell => alvo BEAR).
Para cada timeframe classificamos:
    FAVOR  = mesma direção do sinal
    CONTRA = direção oposta ao sinal
    N      = neutro/indeciso (NEUT)

Ordem de avaliação (idêntica ao _catalyst_plano do MNQ):
    R1  todos neutros                              -> BLOQUEIA
    R8  só 15m decidido (5m e 1h N)                -> segue 15m (contra = bloqueia)
    R5  5m N                                       -> entra só se 15m E 1h a favor
    R2b 5m e 15m alinhados CONTRA                  -> BLOQUEIA
    R4  5m+15m+1h+VWAP a favor                      -> ENTRA (tudo alinhado)
    R2  5m e 15m a favor                            -> ENTRA
    R6  5m e 1h a favor, 15m N                       -> ENTRA
    R7  só 5m decidido (15m e 1h N)                 -> segue 5m (contra = bloqueia)
    R9  ZONA DE CONFLITO: 5m decidido, 15m N,
        1h OPOSTO ao 5m  -> VWAP é o JUIZ:
           entra só se o VWAP estiver do lado do SINAL; senão ESPERA
    R3  fallback                                    -> ENTRA (aguardando alinhamento)

FRESCOR / LEGADO: se o estado do catalisador da moeda estiver velho (mais de
`stale_segundos`, padrão 900s = 15min) ou nunca tiver chegado, o filtro NÃO
opina — deixa passar como LEGADO (entra), a menos que `fail_closed` seja true
(aí bloqueia por falta de dados). Isso é fiel ao MNQ e permite ligar as moedas
uma a uma sem travar o que ainda não tem alerta do catalisador.

Este módulo NÃO fala com corretora nem TradingView; só guarda estado e decide.
Todos os comentários e mensagens em Português.
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("catalyst")

# Timeframes que o catalisador acompanha (nomes das chaves do payload).
TFS = ("c5m", "c15m", "c1h")


def normalizar_dir(valor: Any) -> str:
    """Converte várias formas para 'BULL' / 'BEAR' / 'NEUT'."""
    s = str(valor if valor is not None else "").strip().lower()
    if s in ("bull", "up", "buy", "long", "alta", "1", "green", "verde",
             "above", "acima", "compra", "b"):
        return "BULL"
    if s in ("bear", "down", "sell", "short", "baixa", "-1", "red", "vermelho",
             "below", "abaixo", "venda", "s"):
        return "BEAR"
    return "NEUT"


def normalizar_market(valor: Any) -> str:
    """Converte o campo de regime de mercado para 'RANGING' / 'TRENDING'."""
    s = str(valor if valor is not None else "").strip().lower()
    if s in ("ranging", "range", "lateral", "lateralizado", "chop", "choppy"):
        return "RANGING"
    if s in ("trending", "trend", "tendencia", "tendência", "direcional"):
        return "TRENDING"
    return "TRENDING"  # padrão seguro: sem info => não bloqueia por ranging


def normalizar_pullback(valor: Any) -> str:
    """Converte o campo de pullback para 'BULL' / 'BEAR' / 'NONE'.
    BULL = pullback (recuo) DENTRO de uma tendência de ALTA -> setup de compra
           na RETOMADA. BEAR = recuo dentro de tendência de BAIXA -> setup de
           venda na retomada. NONE = sem pullback identificado."""
    s = str(valor if valor is not None else "").strip().lower()
    if s in ("bull", "pb_bull", "buyback", "buy_back", "alta", "up", "long"):
        return "BULL"
    if s in ("bear", "pb_bear", "sellback", "sell_back", "baixa", "down", "short"):
        return "BEAR"
    return "NONE"


class CatalystStore:
    """Guarda o estado do catalisador por MOEDA e decide o gate (entra/espera)."""

    def __init__(self, config: Dict[str, Any]):
        conf = (config or {}).get("catalyst", {}) or {}
        self.ativa: bool = bool(conf.get("ativa", True))
        self.stale_segundos: float = float(conf.get("stale_segundos", 900))
        self.fail_closed: bool = bool(conf.get("fail_closed", False))
        # --- Regras NOVAS portadas do MNQ Catalyst V2 (todas configuráveis) ---
        # RANGING: descarta a entrada quando o mercado está lateral.
        # Padrão DESLIGADO (a pedido) — só bloqueia se explicitamente ligado.
        self.bloquear_ranging: bool = bool(conf.get("bloquear_ranging", False))
        # PULLBACK: só entra na RETOMADA (pullback a favor do sinal); se o
        # pullback for contra o sinal, é reversão -> cancela/espera.
        self.pullback_ativo: bool = bool(conf.get("pullback_ativo", True))
        # TIMING 30S/1M: usa os timeframes rápidos para afinar o gatilho.
        # Se ambos (30s E 1m) estiverem CONTRA o sinal, o timing está ruim -> espera.
        self.timing_rapido: bool = bool(conf.get("timing_rapido", True))
        # MACRO 2H/4H (scalping no 5m): tendência-mãe. Se TODOS os TFs macro
        # decididos (c2h/c4h) estiverem CONTRA o sinal, bloqueia (evita scalp
        # contra a tendência maior). Padrão desligado (use no 5m).
        self.bloquear_contra_macro: bool = bool(conf.get("bloquear_contra_macro", False))
        # Estado: "MOEDA" -> {"c30s","c1m","c5m","c15m","c1h","vwap",
        #                      "market","pullback","ts"}
        self._estado: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _chave(moeda: str) -> str:
        return (moeda or "").upper()

    @staticmethod
    def normalizar_moeda(sym: Any) -> str:
        """Converte o símbolo do TradingView na MOEDA base.
        Ex.: 'BITGET:BTCUSDT.P' -> 'BTC', 'ETHUSDT' -> 'ETH', 'SOL' -> 'SOL'.
        Assim o MESMO alerta funciona em QUALQUER moeda: o indicador manda o
        próprio ticker ({{ticker}}/syminfo.ticker) e o bot descobre a moeda."""
        s = str(sym if sym is not None else "").strip().upper()
        if not s:
            return ""
        if ":" in s:            # remove prefixo de corretora "BITGET:..."
            s = s.split(":")[-1]
        s = s.split(".")[0]     # remove sufixo de perpétuo ".P" / ".PS"
        s = s.replace("PERP", "")
        for suf in ("USDT", "USDC", "USD", "BUSD"):   # remove a moeda de cotação
            if s.endswith(suf) and len(s) > len(suf):
                s = s[:-len(suf)]
                break
        return s.strip()

    def atualizar(self, moeda: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Registra o estado atual do catalisador para uma MOEDA.
        Aceita chaves c5m/c15m/c1h/vwap (e apelidos m5/m15/h1). Ignora o payload
        se nenhum desses campos vier (ex.: textos de sinal não apagam o estado).
        """
        if not data:
            return {"ok": False, "error": "payload vazio"}
        # Campos DIRECIONAIS (BULL/BEAR/NEUT): timeframes + VWAP.
        apelidos_dir = {
            "c30s": "c30s", "30s": "c30s", "s30": "c30s", "tf30s": "c30s",
            "c1m": "c1m", "1m": "c1m", "m1": "c1m", "tf1m": "c1m",
            "c5m": "c5m", "5m": "c5m", "m5": "c5m", "tf5m": "c5m",
            "c15m": "c15m", "15m": "c15m", "m15": "c15m", "tf15m": "c15m",
            "c1h": "c1h", "1h": "c1h", "h1": "c1h", "tf1h": "c1h",
            "c2h": "c2h", "2h": "c2h", "h2": "c2h", "tf2h": "c2h",
            "c4h": "c4h", "4h": "c4h", "h4": "c4h", "tf4h": "c4h",
            "vwap": "vwap", "vw": "vwap",
        }
        # Campos ESPECIAIS (valores próprios).
        apelidos_market = {"market": 1, "mercado": 1, "regime": 1}
        apelidos_pb = {"pullback": 1, "pb": 1}

        achou: Dict[str, Any] = {}
        for k, v in data.items():
            kl = str(k).strip().lower()
            if kl in apelidos_dir:
                achou[apelidos_dir[kl]] = normalizar_dir(v)
            elif kl in apelidos_market:
                achou["market"] = normalizar_market(v)
            elif kl in apelidos_pb:
                achou["pullback"] = normalizar_pullback(v)
        if not achou:
            return {"ok": False,
                    "error": "sem c30s/c1m/c5m/c15m/c1h/vwap/market/pullback "
                             "no payload (ignorado)"}
        chave = self._chave(moeda)
        with self._lock:
            reg = self._estado.get(chave, {})
            reg.update(achou)
            reg["ts"] = time.time()
            self._estado[chave] = reg
        campos = ("c30s", "c1m", "c5m", "c15m", "c1h", "c2h", "c4h",
                  "vwap", "market", "pullback")
        logger.info("Catalisador %s: %s", chave,
                    {k: reg.get(k) for k in campos})
        return {"ok": True, "moeda": chave,
                "estado": {k: reg.get(k) for k in campos}}

    # ------------------------------------------------------------------ #
    @staticmethod
    def _rel(v: str, alvo: str) -> str:
        """Classifica um timeframe em relação à direção do sinal."""
        if v == "NEUT":
            return "N"
        return "FAVOR" if v == alvo else "CONTRA"

    def estado_moeda(self, moeda: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._estado.get(self._chave(moeda), {}))

    def checar(self, moeda: str, action: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Decide ENTRA (ok=True) ou ESPERA/BLOQUEIA (ok=False) para o sinal.
        Retorna (ok, detalhe) com a regra aplicada e o motivo.
        """
        if not self.ativa:
            return True, {"ativa": False, "motivo": "catalisador desligado",
                          "regra": "off"}
        action = (action or "").lower()
        if action not in ("buy", "sell"):
            return False, {"motivo": f"ação inválida: {action!r}", "regra": "erro"}
        alvo = "BULL" if action == "buy" else "BEAR"

        st = self.estado_moeda(moeda)
        agora = time.time()
        idade = agora - float(st.get("ts", 0)) if st else None

        # --- Frescor / LEGADO -----------------------------------------
        campos_estado = ("c30s", "c1m", "c5m", "c15m", "c1h", "c2h", "c4h",
                         "vwap", "market", "pullback")
        if not st or idade is None or idade > self.stale_segundos:
            base = {"ativa": True, "moeda": self._chave(moeda), "action": action,
                    "idade_seg": round(idade, 1) if idade is not None else None,
                    "estado": {k: st.get(k) for k in campos_estado}}
            if self.fail_closed:
                base.update({"ok": False, "regra": "legado_fail_closed",
                             "motivo": "sem estado fresco do catalisador (bloqueado)"})
                return False, base
            base.update({"ok": True, "regra": "legado",
                         "motivo": "sem estado fresco do catalisador (passa como legado)"})
            return True, base

        c30s = st.get("c30s", "NEUT")
        c1m = st.get("c1m", "NEUT")
        c5m = st.get("c5m", "NEUT")
        c15 = st.get("c15m", "NEUT")
        c1h = st.get("c1h", "NEUT")
        c2h = st.get("c2h", "NEUT")
        c4h = st.get("c4h", "NEUT")
        vwap = st.get("vwap", "NEUT")
        market = normalizar_market(st.get("market"))
        pullback = normalizar_pullback(st.get("pullback"))
        r30 = self._rel(c30s, alvo)
        r1m = self._rel(c1m, alvo)
        r5 = self._rel(c5m, alvo)
        r15 = self._rel(c15, alvo)
        r1 = self._rel(c1h, alvo)
        r2h = self._rel(c2h, alvo)
        r4h = self._rel(c4h, alvo)
        vw = self._rel(vwap, alvo)
        rpb = self._rel(
            "BULL" if pullback == "BULL" else "BEAR" if pullback == "BEAR" else "NEUT",
            alvo)

        # GRADE A/B/C — força do contexto de 1h QUANDO 5m e 15m estão a favor.
        #   A = 5m+15m a favor E 1h a favor  (contexto forte)
        #   B = 5m+15m a favor, 1h neutro    (contexto ok)
        #   C = 5m+15m a favor, 1h contra    (contexto fraco / contra-tendência)
        # Fora desse arranjo a grade não se aplica (None).
        if r5 == "FAVOR" and r15 == "FAVOR":
            grade = "A" if r1 == "FAVOR" else ("B" if r1 == "N" else "C")
        else:
            grade = None

        def resp(ok: bool, regra: str, motivo: str):
            det = {
                "ativa": True, "ok": ok, "regra": regra, "motivo": motivo,
                "moeda": self._chave(moeda), "action": action, "alvo": alvo,
                "grade": grade,
                "market": market, "pullback": pullback,
                "estado": {"c30s": c30s, "c1m": c1m, "c5m": c5m, "c15m": c15,
                           "c1h": c1h, "c2h": c2h, "c4h": c4h, "vwap": vwap,
                           "market": market, "pullback": pullback},
                "relativo": {"c30s": r30, "c1m": r1m, "c5m": r5, "c15m": r15,
                             "c1h": r1, "c2h": r2h, "c4h": r4h,
                             "vwap": vw, "pullback": rpb},
                "idade_seg": round(idade, 1),
            }
            return ok, det

        # === REGRA RANGING (V2) — mercado lateral é DESCARTADO =========
        if self.bloquear_ranging and market == "RANGING":
            return resp(False, "RANGING", "mercado lateral (ranging) — descartado")

        # === FILTRO MACRO 2H/4H (scalping no 5m) ======================
        # Tendência-mãe: se TODOS os TFs macro DECIDIDOS (2h/4h) estiverem
        # CONTRA o sinal, bloqueia (não faz scalp contra a tendência maior).
        # Se nenhum macro veio decidido (ambos N/ausentes), não opina.
        if self.bloquear_contra_macro:
            macro = [r for r in (r2h, r4h) if r != "N"]
            if macro and all(r == "CONTRA" for r in macro):
                return resp(False, "macro",
                            "contra a tendência-mãe (2h/4h) — bloqueado")

        # === DECISÃO-BASE: as 9 regras clássicas (R1..R9) ==============
        def _base() -> Tuple[bool, str, str]:
            # R1 — todos neutros
            if r5 == "N" and r15 == "N" and r1 == "N":
                return False, "R1", "todos os timeframes neutros"
            # R8 — só 15m decidido (5m e 1h neutros)
            if r5 == "N" and r1 == "N" and r15 != "N":
                if r15 == "FAVOR":
                    return True, "R8", "segue o 15m (5m/1h neutros)"
                return False, "R8", "15m contra o sinal (5m/1h neutros)"
            # R5 — 5m neutro (com 15m e/ou 1h decididos)
            if r5 == "N":
                if r15 == "FAVOR" and r1 == "FAVOR":
                    return True, "R5", "5m neutro, mas 15m e 1h a favor"
                return False, "R5", "5m neutro sem 15m+1h a favor"
            # (daqui pra baixo o 5m está decidido)
            # R2b — 5m e 15m alinhados CONTRA o sinal
            if r5 == "CONTRA" and r15 == "CONTRA":
                return False, "R2b", "5m e 15m alinhados contra o sinal"
            # R4 — tudo a favor + VWAP a favor
            if r5 == "FAVOR" and r15 == "FAVOR" and r1 == "FAVOR" and vw == "FAVOR":
                return True, "R4", "5m+15m+1h+VWAP totalmente alinhados"
            # R2 — 5m e 15m a favor
            if r5 == "FAVOR" and r15 == "FAVOR":
                return True, "R2", "5m e 15m a favor"
            # R6 — 5m e 1h a favor, 15m neutro
            if r5 == "FAVOR" and r1 == "FAVOR" and r15 == "N":
                return True, "R6", "5m e 1h a favor (15m neutro)"
            # R7 — só 5m decidido (15m e 1h neutros)
            if r15 == "N" and r1 == "N":
                if r5 == "FAVOR":
                    return True, "R7", "segue o 5m (15m/1h neutros)"
                return False, "R7", "5m contra o sinal (15m/1h neutros)"
            # R9 — zona de conflito: 5m decidido, 15m neutro, 1h oposto ao 5m
            if r15 == "N" and ((r5 == "FAVOR" and r1 == "CONTRA") or
                               (r5 == "CONTRA" and r1 == "FAVOR")):
                if vw == "FAVOR":
                    return True, "R9", "conflito 5m x 1h — VWAP confirma o sinal"
                return False, "R9", "conflito 5m x 1h — VWAP não confirma (espera)"
            # R3 — fallback: entra aguardando alinhamento
            return True, "R3", "fallback (entra aguardando alinhamento)"

        ok_base, regra_base, motivo_base = _base()
        if not ok_base:
            return resp(False, regra_base, motivo_base)

        # === FILTROS V2 (só quando a base LIBEROU a entrada) ===========
        # PULLBACK — só entra na RETOMADA. Se há pullback e ele aponta CONTRA
        # o sinal, é reversão -> cancela. Pullback a favor confirma a retomada.
        if self.pullback_ativo and pullback != "NONE" and rpb == "CONTRA":
            return resp(False, "PB-contra",
                        "pullback contrário ao sinal (reversão) — cancela")

        # TIMING 30S/1M — se AMBOS os rápidos estão CONTRA o sinal, o gatilho
        # ainda não virou -> espera a retomada dos timeframes rápidos.
        if self.timing_rapido and r30 == "CONTRA" and r1m == "CONTRA":
            return resp(False, "timing",
                        "timing ruim: 30s e 1m ainda contra o sinal")

        # Entrada confirmada pela base + filtros V2.
        return resp(True, regra_base, motivo_base)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ativa": self.ativa,
                "stale_segundos": self.stale_segundos,
                "fail_closed": self.fail_closed,
                "bloquear_ranging": self.bloquear_ranging,
                "pullback_ativo": self.pullback_ativo,
                "timing_rapido": self.timing_rapido,
                "bloquear_contra_macro": self.bloquear_contra_macro,
                "moedas_com_estado": len(self._estado),
                "estado": {k: dict(v) for k, v in self._estado.items()},
            }
