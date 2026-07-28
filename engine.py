# -*- coding: utf-8 -*-
"""
engine.py
=========
Motor de decisão do bot de índices (NQ/MNQ, ES/MES).

Lógica (confirmação por RSI):
  - O indicador TSTS Sniper Rifle envia um alerta de sinal (BUY/SELL).
  - O bot NÃO entra na hora. Ele olha o estado ATUAL do RSI em relação à sua média:
      * RSI acima da média  -> estado "up"
      * RSI abaixo da média -> estado "down"
  - Regras de entrada:
      * Sinal BUY  + RSI já está "up"   -> ENTRA agora (o cruzamento já aconteceu).
      * Sinal BUY  + RSI está "down"    -> SEGURA. Entra quando o RSI cruzar para "up".
      * Sinal SELL + RSI já está "down"  -> ENTRA agora.
      * Sinal SELL + RSI está "up"       -> SEGURA. Entra quando o RSI cruzar para "down".

O estado do RSI é atualizado pelos alertas de cruzamento vindos do TradingView
(Forma A): um alerta quando o RSI cruza para cima da média (up) e outro quando
cruza para baixo (down).

Opções de segurança (config):
  - require_fresh_cross_bars: se > 0, um sinal só entra "na hora" se o último
    cruzamento do RSI na direção certa aconteceu há no máximo N barras (evita
    entrar com base em um cruzamento muito antigo). 0 = desligado (usa só o estado).
  - pending_timeout_bars: um sinal pendente (segurando) expira depois de N barras
    sem confirmação. 0 = nunca expira.

Este módulo NÃO fala com nenhuma corretora nem com o Telegram. Ele apenas decide
e devolve uma "decisão" que o servidor usa para executar/notificar. Isso deixa a
lógica 100% testável sem depender de rede.

Todos os comentários e mensagens em Português.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("engine")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tf_minutes(timeframe: str) -> float:
    """Converte um timeframe ('5m', '15m', '1h', '5', '15') em minutos."""
    if timeframe is None:
        return 5.0
    s = str(timeframe).strip().lower()
    try:
        if s.endswith("m"):
            return float(s[:-1] or 0)
        if s.endswith("h"):
            return float(s[:-1] or 0) * 60.0
        if s.endswith("d"):
            return float(s[:-1] or 0) * 60.0 * 24.0
        # só número -> assume minutos (padrão TradingView)
        return float(s)
    except ValueError:
        return 5.0


class SymbolState:
    """Estado por símbolo (ex.: MNQ, MES)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        # Estado atual do RSI vs média: "up", "down" ou None (desconhecido)
        self.rsi_state: Optional[str] = None
        self.rsi_state_time: Optional[datetime] = None
        # Sinal pendente aguardando confirmação do RSI
        self.pending_action: Optional[str] = None   # "buy" / "sell"
        self.pending_time: Optional[datetime] = None
        self.pending_extra: Dict[str, Any] = {}      # sl/tp/preço, se vierem
        # Quantos cruzamentos na direção do sinal já ocorreram (para o analista).
        self.pending_cross_count: int = 0
        # ---- TRAVA anti-empilhamento ----
        # Enquanto houver posição aberta no mesmo lado, novos sinais são IGNORADOS
        # (não empilha contratos). Limpa na reversão, no timeout ou via /flat.
        self.posicao_aberta: bool = False
        self.posicao_action: Optional[str] = None    # "buy" / "sell"
        self.posicao_time: Optional[datetime] = None
        self.posicao_contratos: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rsi_state": self.rsi_state,
            "rsi_state_time": self.rsi_state_time.isoformat() if self.rsi_state_time else None,
            "pending_action": self.pending_action,
            "pending_time": self.pending_time.isoformat() if self.pending_time else None,
            "pending_extra": self.pending_extra,
            "pending_cross_count": self.pending_cross_count,
            "posicao_aberta": self.posicao_aberta,
            "posicao_action": self.posicao_action,
            "posicao_time": self.posicao_time.isoformat() if self.posicao_time else None,
            "posicao_contratos": self.posicao_contratos,
        }


class DecisionEngine:
    """
    Guarda o estado de cada símbolo e decide quando entrar.

    Métodos principais:
      - on_signal(symbol, action, timeframe, extra)  -> decisão
      - on_rsi_cross(symbol, direction, timeframe)    -> decisão
    Cada um devolve um dict:
      {"entrar": bool, "action": "buy"/"sell"/None, "motivo": str, "estado": {...}}
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self._states: Dict[str, SymbolState] = {}
        self._lock = threading.RLock()
        s = settings or {}
        # Quantas barras um cruzamento continua "fresco" para entrada imediata.
        # 0 = desligado: basta o RSI estar no lado certo (recomendado p/ começar).
        self.require_fresh_cross_bars: int = int(s.get("require_fresh_cross_bars", 0))
        # Quantas barras um sinal pendente sobrevive sem confirmação. 0 = nunca expira.
        self.pending_timeout_bars: int = int(s.get("pending_timeout_bars", 0))
        # ---- Agente analista ----
        # Se ativo, o bot NÃO entra no 1º cruzamento automaticamente: ele pede
        # uma ANÁLISE (regras/IA). Entra se a análise disser "entrar"; senão
        # aguarda o próximo cruzamento. No cruzamento de nº max_cruzamentos a
        # entrada é AUTOMÁTICA (sem análise). Se inativo, comportamento clássico
        # (entra no 1º cruzamento na direção certa).
        self.analise_ativa: bool = bool(s.get("analise_ativa", False))
        self.max_cruzamentos: int = int(s.get("max_cruzamentos", 3))
        # ---- TRAVA anti-empilhamento ----
        self.anti_empilhamento: bool = bool(s.get("anti_empilhamento", True))
        self.max_contratos: int = int(s.get("max_contratos", 8))
        # Minutos até considerar a posição encerrada (0 = nunca expira sozinha).
        self.posicao_timeout_min: float = float(s.get("posicao_timeout_min", 120))

    # ------------------------------------------------------------------ #
    def _get(self, symbol: str) -> SymbolState:
        symbol = symbol.upper()
        if symbol not in self._states:
            self._states[symbol] = SymbolState(symbol)
        return self._states[symbol]

    @staticmethod
    def _dir_for_action(action: str) -> str:
        """buy -> up ; sell -> down."""
        return "up" if action == "buy" else "down"

    def _pending_expired(self, st: SymbolState, timeframe: str) -> bool:
        if self.pending_timeout_bars <= 0 or st.pending_time is None:
            return False
        age_min = (_now() - st.pending_time).total_seconds() / 60.0
        limit = self.pending_timeout_bars * _tf_minutes(timeframe)
        return age_min > limit

    def _cross_is_fresh(self, st: SymbolState, timeframe: str) -> bool:
        """True se o cruzamento do RSI ainda está dentro da janela de frescor."""
        if self.require_fresh_cross_bars <= 0:
            return True  # desligado: só importa o lado atual do RSI
        if st.rsi_state_time is None:
            return False
        age_min = (_now() - st.rsi_state_time).total_seconds() / 60.0
        limit = self.require_fresh_cross_bars * _tf_minutes(timeframe)
        return age_min <= limit

    # ---- TRAVA anti-empilhamento ------------------------------------- #
    def _posicao_expirada(self, st: SymbolState) -> bool:
        """True se a posição aberta já passou do timeout (considera-se encerrada)."""
        if self.posicao_timeout_min <= 0 or st.posicao_time is None:
            return False
        idade_min = (_now() - st.posicao_time).total_seconds() / 60.0
        return idade_min > self.posicao_timeout_min

    def _limpar_posicao(self, st: SymbolState) -> None:
        st.posicao_aberta = False
        st.posicao_action = None
        st.posicao_time = None
        st.posicao_contratos = 0

    def _pode_entrar(self, st: SymbolState, action: str):
        """
        Aplica a trava anti-empilhamento.
        Retorna (True, "") se pode entrar; (False, motivo) se deve BLOQUEAR.
        - Direção OPOSTA à posição aberta => reversão: libera (o PMT fecha a
          posição antiga via reverse_order_close) e permite a nova.
        - Timeout vencido => libera e permite.
        - Mesma direção ainda aberta => BLOQUEIA (sinal repetido / empilhamento).
        """
        if not self.anti_empilhamento:
            return True, ""
        if st.posicao_aberta:
            if self._posicao_expirada(st):
                self._limpar_posicao(st)
                return True, ""
            if st.posicao_action and st.posicao_action != action:
                # reversão: solta a trava; a posição oposta será fechada no PMT.
                self._limpar_posicao(st)
                return True, ""
            return False, (f"Já existe posição {(st.posicao_action or '').upper()} "
                           f"aberta (anti-empilhamento). Sinal repetido ignorado — "
                           f"sem re-entrada; aguardando o próximo alerta.")
        return True, ""

    def _registrar_posicao(self, st: SymbolState, action: str,
                           contratos: int = 0) -> None:
        st.posicao_aberta = True
        st.posicao_action = action
        st.posicao_time = _now()
        st.posicao_contratos = contratos

    def _entrada(self, st: SymbolState, symbol: str, action: str,
                 motivo: str, entrada_tipo: str,
                 extra: Optional[Dict[str, Any]] = None,
                 **campos) -> Dict[str, Any]:
        """
        Monta a decisão de ENTRADA aplicando a trava anti-empilhamento.
        Se bloqueado, devolve uma decisão {"entrar": False, "bloqueado": True}.
        entrada_tipo: "AUTO" (RSI já alinhado quando o sinal chegou) ou
                      "ESPERA" (sinal segurado até o RSI cruzar depois).
        """
        ok, bloq = self._pode_entrar(st, action)
        if not ok:
            logger.info("%s: %s", symbol, bloq)
            d = {"entrar": False, "bloqueado": True, "action": action,
                 "motivo": bloq, "estado": st.to_dict()}
            d.update(campos)
            return d
        self._registrar_posicao(st, action)
        logger.info("%s: %s", symbol, motivo)
        d = {"entrar": True, "action": action, "motivo": motivo,
             "entrada_tipo": entrada_tipo, "estado": st.to_dict(),
             "extra": extra or {}}
        d.update(campos)
        return d

    def liberar_posicao(self, symbol: str) -> Dict[str, Any]:
        """Solta a trava manualmente (endpoint /flat). Usar quando a posição
        foi encerrada na corretora para o bot voltar a aceitar entradas."""
        with self._lock:
            st = self._get(symbol)
            tinha = st.posicao_aberta
            self._limpar_posicao(st)
            return {"symbol": symbol.upper(), "tinha_posicao": tinha,
                    "estado": st.to_dict()}

    # ------------------------------------------------------------------ #
    def on_signal(self, symbol: str, action: str, timeframe: str = "5",
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Recebe um sinal TSTS (buy/sell) e decide."""
        action = (action or "").lower()
        if action not in ("buy", "sell"):
            return {"entrar": False, "action": None,
                    "motivo": f"ação inválida: {action!r}", "estado": None}

        with self._lock:
            st = self._get(symbol)
            needed = self._dir_for_action(action)  # up p/ buy, down p/ sell

            # RSI já está no lado certo -> é o 1º ponto de decisão
            if st.rsi_state == needed and self._cross_is_fresh(st, timeframe):
                if not self.analise_ativa:
                    # Comportamento clássico: entra imediatamente.
                    st.pending_action = None
                    st.pending_time = None
                    st.pending_extra = {}
                    st.pending_cross_count = 0
                    motivo = (f"Sinal {action.upper()} e RSI já está {needed.upper()} "
                              f"→ entrada imediata.")
                    # entrada_tipo=AUTO: o RSI já estava alinhado quando o sinal chegou.
                    return self._entrada(st, symbol, action, motivo,
                                         entrada_tipo="AUTO", extra=extra or {})
                # Modo análise: RSI já alinhado conta como 1º cruzamento → ANALISA.
                st.pending_action = action
                st.pending_time = _now()
                st.pending_extra = extra or {}
                st.pending_cross_count = 1
                motivo = (f"Sinal {action.upper()} e RSI já está {needed.upper()} "
                          f"→ 1º cruzamento: pedir ANÁLISE.")
                logger.info("%s: %s", symbol, motivo)
                return {"entrar": False, "analisar": True, "action": action,
                        "cruzamento": 1, "max_cruzamentos": self.max_cruzamentos,
                        "motivo": motivo, "estado": st.to_dict(),
                        "extra": extra or {}}

            # Caso contrário, segura o sinal aguardando o cruzamento do RSI
            st.pending_action = action
            st.pending_time = _now()
            st.pending_extra = extra or {}
            st.pending_cross_count = 0
            alvo = needed.upper()
            motivo = (f"Sinal {action.upper()} recebido, mas RSI está "
                      f"{(st.rsi_state or 'desconhecido').upper()} "
                      f"→ SEGURANDO até o RSI cruzar para {alvo}.")
            logger.info("%s: %s", symbol, motivo)
            return {"entrar": False, "action": action, "motivo": motivo,
                    "estado": st.to_dict()}

    # ------------------------------------------------------------------ #
    def on_rsi_cross(self, symbol: str, direction: str,
                     timeframe: str = "5") -> Dict[str, Any]:
        """Recebe um alerta de cruzamento do RSI (up/down) e decide."""
        direction = (direction or "").lower()
        if direction in ("up", "buy", "long", "1", "compra"):
            direction = "up"
        elif direction in ("down", "sell", "short", "-1", "venda"):
            direction = "down"
        else:
            return {"entrar": False, "action": None,
                    "motivo": f"direção de RSI inválida: {direction!r}", "estado": None}

        with self._lock:
            st = self._get(symbol)
            st.rsi_state = direction
            st.rsi_state_time = _now()

            # Expira sinal pendente muito antigo
            if st.pending_action and self._pending_expired(st, timeframe):
                logger.info("%s: sinal pendente %s expirou.", symbol, st.pending_action)
                st.pending_action = None
                st.pending_time = None
                st.pending_extra = {}

            # Se havia um sinal pendente que combina com este cruzamento
            if st.pending_action:
                needed = self._dir_for_action(st.pending_action)
                if needed == direction:
                    action = st.pending_action
                    extra = st.pending_extra

                    # Comportamento clássico (análise desligada): entra já.
                    if not self.analise_ativa:
                        st.pending_action = None
                        st.pending_time = None
                        st.pending_extra = {}
                        st.pending_cross_count = 0
                        motivo = (f"RSI cruzou para {direction.upper()} e havia sinal "
                                  f"{action.upper()} pendente → entrada confirmada.")
                        # entrada_tipo=ESPERA: o sinal foi segurado até o RSI cruzar.
                        return self._entrada(st, symbol, action, motivo,
                                             entrada_tipo="ESPERA", extra=extra)

                    # Modo análise: conta o cruzamento.
                    st.pending_cross_count += 1
                    n = st.pending_cross_count

                    # Último cruzamento (máx) → entra AUTOMÁTICO, sem análise.
                    if n >= self.max_cruzamentos:
                        st.pending_action = None
                        st.pending_time = None
                        st.pending_extra = {}
                        st.pending_cross_count = 0
                        motivo = (f"{n}º cruzamento (máximo) para {direction.upper()} "
                                  f"→ entrada AUTOMÁTICA do {action.upper()} "
                                  f"(sem análise).")
                        return self._entrada(st, symbol, action, motivo,
                                             entrada_tipo="ESPERA", extra=extra,
                                             cruzamento=n,
                                             max_cruzamentos=self.max_cruzamentos,
                                             auto_ultimo=True)

                    # Cruzamentos intermediários → pedir ANÁLISE.
                    motivo = (f"{n}º cruzamento para {direction.upper()} com sinal "
                              f"{action.upper()} pendente → pedir ANÁLISE.")
                    logger.info("%s: %s", symbol, motivo)
                    return {"entrar": False, "analisar": True, "action": action,
                            "cruzamento": n, "max_cruzamentos": self.max_cruzamentos,
                            "motivo": motivo, "estado": st.to_dict(), "extra": extra}

            motivo = f"RSI atualizado para {direction.upper()} (sem sinal pendente correspondente)."
            logger.info("%s: %s", symbol, motivo)
            return {"entrar": False, "action": None, "motivo": motivo,
                    "estado": st.to_dict()}

    # ------------------------------------------------------------------ #
    def semear_estado(self, symbol: str, direction: str) -> None:
        """
        Define o lado atual do RSI (up/down) SEM contar como cruzamento e SEM
        efeitos colaterais. Usado pelo scanner autônomo na 1ª observação de cada
        combinação, para o motor já nascer com o estado correto (evita segurar
        o 1º sinal só porque o estado do RSI ainda era desconhecido).
        """
        d = (direction or "").strip().lower()
        if d not in ("up", "down"):
            return
        with self._lock:
            st = self._get(symbol)
            st.rsi_state = d
            st.rsi_state_time = _now()

    # ------------------------------------------------------------------ #
    def confirmar_entrada(self, symbol: str) -> None:
        """
        Limpa o sinal pendente após a ANÁLISE decidir ENTRAR.
        (Quando a análise decide HOLD, NÃO chamamos isto: o pendente continua,
         com o contador de cruzamentos já incrementado, aguardando o próximo.)
        """
        with self._lock:
            st = self._get(symbol)
            # Marca a posição como aberta (trava anti-empilhamento) usando a
            # direção do sinal pendente, ANTES de limpar o pendente.
            if st.pending_action:
                self._registrar_posicao(st, st.pending_action)
            st.pending_action = None
            st.pending_time = None
            st.pending_extra = {}
            st.pending_cross_count = 0

    # ------------------------------------------------------------------ #
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {sym: st.to_dict() for sym, st in self._states.items()}
