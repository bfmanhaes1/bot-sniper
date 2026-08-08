"""
executor_real.py — Camada de EXECUÇÃO REAL na Bitget para o BOT-SNIPER.

Filosofia de segurança (leia antes de mexer):
  * MASTER SWITCH: só executa se config["execucao_real"]["ativa"] == true.
    Enquanto false (padrão), este módulo NÃO abre nenhuma ordem — o bot segue
    100% em modo sombra.
  * dry_run: mesmo com "ativa": true, se "dry_run": true o BitgetClient apenas
    SIMULA as chamadas (não manda ordem de verdade). Use para validar o fluxo.
  * GUARDAS por camada, todas configuráveis:
      - moedas permitidas   (ex.: só VIRTUAL)
      - timeframes           (ex.: só 5m)
      - grade do catalisador (ex.: só A/B — barra C = contra-tendência)
      - máx. posições simultâneas (ex.: 3 => 3 x $100 = $300)
      - 1 ordem por moeda (não empilha)
  * A execução real roda EM PARALELO à sombra. A sombra nunca para de coletar.

Este módulo é aditivo: se qualquer coisa falhar, ele loga e retorna sem
derrubar o fluxo de sombra.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from bitget_client import BitgetClient, load_bitget_credentials
    _BITGET_OK = True
    _BITGET_IMPORT_ERR = None
except Exception as exc:  # noqa: BLE001
    _BITGET_OK = False
    _BITGET_IMPORT_ERR = repr(exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutorReal:
    def __init__(self, config: Dict[str, Any], logger, notifier=None,
                 data_dir: Optional[str] = None):
        self.log = logger
        self.notifier = notifier
        cfg = (config or {}).get("execucao_real", {}) or {}
        self.cfg = cfg

        # ---- Flags principais -------------------------------------------
        self.ativa: bool = bool(cfg.get("ativa", False))
        self.dry_run: bool = bool(cfg.get("dry_run", True))

        # ---- Guardas ----------------------------------------------------
        self.moedas: List[str] = [m.upper() for m in cfg.get("moedas", ["VIRTUAL"])]
        self.timeframes: List[str] = list(cfg.get("timeframes", ["5m"]))
        self.grades_permitidas: List[str] = list(cfg.get("grades_permitidas", ["A", "B"]))
        self.exigir_grade: bool = bool(cfg.get("exigir_grade", True))
        self.max_posicoes: int = int(cfg.get("max_posicoes", 3))
        self.uma_ordem_por_moeda: bool = bool(cfg.get("uma_ordem_por_moeda", True))

        # ---- Dinheiro / alavancagem ------------------------------------
        self.margem_usdt: float = float(cfg.get("margem_usdt", 100))
        self.capital_total_usdt: float = float(cfg.get("capital_total_usdt", 300))
        self.alav_base: int = int(cfg.get("alavancagem_base", 5))
        self.alav_grade_a: int = int(cfg.get("alavancagem_grade_a", 10))

        # ---- Símbolos Bitget -------------------------------------------
        self.symbols: Dict[str, str] = config.get("symbols_bitget", {}) or {}

        # ---- Persistência de posições reais ----------------------------
        base = data_dir or os.getenv("DATA_DIR") or "/data"
        if not os.path.isdir(base):
            base = os.path.dirname(os.path.abspath(__file__))
        self._pos_path = os.path.join(base, "execucao_real_posicoes.json")
        self._lock = threading.RLock()
        self._posicoes: Dict[str, Dict[str, Any]] = self._carregar()

        # ---- Cliente Bitget --------------------------------------------
        # O cliente é inicializado SEMPRE (mesmo com o master switch desligado)
        # para permitir validar as credenciais via /diag. O construtor NÃO faz
        # chamadas de rede; nenhuma ORDEM é enviada enquanto ativa=false.
        self.client: Optional[BitgetClient] = None
        self.erro_init: Optional[str] = None
        self.credenciais_validas: Optional[bool] = None
        self.saldo_usdt: Optional[float] = None
        self._init_client()
        if not self.ativa:
            self.log.info("[EXEC-REAL] MASTER SWITCH desligado (ativa=false). "
                          "Nenhuma ordem real será enviada — só sombra.")

    # ------------------------------------------------------------------ #
    def _init_client(self):
        if not _BITGET_OK:
            self.erro_init = f"import bitget_client falhou: {_BITGET_IMPORT_ERR}"
            self.log.error("[EXEC-REAL] %s", self.erro_init)
            return
        try:
            creds = load_bitget_credentials()
            self.client = BitgetClient(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                passphrase=creds["passphrase"],
                product_type=self.cfg.get("product_type", "USDT-FUTURES"),
                margin_coin=self.cfg.get("margin_coin", "USDT"),
                margin_mode=self.cfg.get("margin_mode", "isolated"),
                dry_run=self.dry_run,
            )
            modo = "DRY-RUN (simulado)" if self.dry_run else "AO VIVO ($ REAL)"
            self.log.warning("[EXEC-REAL] Cliente Bitget iniciado — modo %s | "
                             "moedas=%s tf=%s grades=%s máx=%d margem=$%.0f",
                             modo, self.moedas, self.timeframes,
                             self.grades_permitidas, self.max_posicoes,
                             self.margem_usdt)
            # Validação read-only das credenciais: consulta o saldo (chamada
            # autenticada, NÃO envia ordem). Confirma que as chaves são válidas.
            self._validar_credenciais()
        except Exception as exc:  # noqa: BLE001
            self.erro_init = repr(exc)
            self.log.error("[EXEC-REAL] Falha ao iniciar cliente Bitget: %s", exc)

    # ------------------------------------------------------------------ #
    def _validar_credenciais(self):
        """Faz UMA chamada autenticada read-only (saldo) p/ validar as chaves.

        A Bitget devolve code=='00000' em caso de sucesso; qualquer outro
        código (ou erro de rede) significa chave inválida / sem permissão.
        O cliente NÃO lança exceção nesses casos, por isso checamos o code.
        """
        if self.client is None:
            return
        try:
            resp = self.client.get_account_balance()
            code = str(resp.get("code"))
            if code == "00000":
                saldo = self.client.get_available_usdt()
                self.saldo_usdt = float(saldo)
                self.credenciais_validas = True
                self.log.warning("[EXEC-REAL] Credenciais Bitget VÁLIDAS. "
                                 "Saldo disponível: $%.2f USDT", self.saldo_usdt)
            else:
                self.credenciais_validas = False
                self.erro_init = f"Bitget code={code}: {resp.get('msg')}"
                self.log.error("[EXEC-REAL] Credenciais Bitget INVÁLIDAS/sem "
                               "permissão: %s", self.erro_init)
        except Exception as exc:  # noqa: BLE001
            self.credenciais_validas = False
            self.erro_init = repr(exc)
            self.log.error("[EXEC-REAL] Erro ao validar credenciais Bitget: %s",
                           exc)

    # ------------------------------------------------------------------ #
    def _carregar(self) -> Dict[str, Dict[str, Any]]:
        try:
            if os.path.exists(self._pos_path):
                with open(self._pos_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception as exc:  # noqa: BLE001
            self.log.error("[EXEC-REAL] Falha ao carregar posições: %s", exc)
        return {}

    def _salvar(self):
        try:
            with open(self._pos_path, "w", encoding="utf-8") as f:
                json.dump(self._posicoes, f, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001
            self.log.error("[EXEC-REAL] Falha ao salvar posições: %s", exc)

    # ------------------------------------------------------------------ #
    def _liberar_fechadas(self):
        """Consulta a Bitget e remove do tracking posições que já fecharam
        (TP/SL disparou na corretora), liberando vaga de capital."""
        if not self.client or self.dry_run:
            return
        for moeda in list(self._posicoes.keys()):
            symbol = self.symbols.get(moeda)
            if not symbol:
                continue
            try:
                if not self.client.has_open_position(symbol):
                    self.log.info("[EXEC-REAL] %s fechou na corretora — liberando vaga.",
                                  moeda)
                    self._posicoes.pop(moeda, None)
            except Exception as exc:  # noqa: BLE001
                self.log.error("[EXEC-REAL] has_open_position %s erro: %s", moeda, exc)
        self._salvar()

    # ------------------------------------------------------------------ #
    def pode_entrar(self, moeda: str, tf: str, grade: Optional[str],
                    action: str) -> Tuple[bool, str]:
        """Roda TODAS as guardas. Retorna (ok, motivo)."""
        if not self.ativa:
            return False, "execucao_real desligada"
        if self.client is None:
            return False, f"cliente Bitget não iniciado ({self.erro_init})"
        moeda = (moeda or "").upper()
        if moeda not in self.moedas:
            return False, f"moeda {moeda} fora da lista permitida {self.moedas}"
        if tf not in self.timeframes:
            return False, f"tf {tf} fora da lista permitida {self.timeframes}"
        if action not in ("buy", "sell"):
            return False, f"action inválida: {action}"
        if self.exigir_grade and (grade not in self.grades_permitidas):
            return False, (f"grade {grade} não permitida "
                           f"(só {self.grades_permitidas})")
        if self.symbols.get(moeda) is None:
            return False, f"sem símbolo Bitget para {moeda}"
        with self._lock:
            self._liberar_fechadas()
            if self.uma_ordem_por_moeda and moeda in self._posicoes:
                return False, f"já existe posição real aberta em {moeda}"
            if len(self._posicoes) >= self.max_posicoes:
                return False, (f"limite de {self.max_posicoes} posições "
                               f"simultâneas atingido")
        return True, "ok"

    # ------------------------------------------------------------------ #
    def abrir(self, moeda: str, tf: str, action: str, entry: float,
              tp: float, sl: float, grade: Optional[str],
              regra: Optional[str]) -> Optional[Dict[str, Any]]:
        """Abre a ordem REAL (ou dry-run) se todas as guardas passarem.
        Retorna o detalhe ou None se não entrou."""
        moeda = (moeda or "").upper()
        ok, motivo = self.pode_entrar(moeda, tf, grade, action)
        if not ok:
            self.log.info("[EXEC-REAL] %s %s: NÃO entrou — %s", moeda, tf, motivo)
            return None

        symbol = self.symbols[moeda]
        leverage = self.alav_grade_a if (grade == "A") else self.alav_base
        notional = self.margem_usdt * leverage
        if not entry or entry <= 0:
            self.log.error("[EXEC-REAL] %s: entry inválido (%s).", moeda, entry)
            return None
        qty = notional / float(entry)

        try:
            resp = self.client.place_order(
                symbol=symbol, side=action, quantity=qty, leverage=leverage,
                tp_price=tp, sl_price=sl,
            )
        except Exception as exc:  # noqa: BLE001
            self.log.error("[EXEC-REAL] place_order %s falhou: %s", symbol, exc)
            return None

        code = str(resp.get("code"))
        if code not in ("00000",):
            self.log.error("[EXEC-REAL] %s ordem REJEITADA: %s", symbol, resp)
            return None

        order_id = (resp.get("data") or {}).get("orderId")
        registro = {
            "moeda": moeda, "symbol": symbol, "tf": tf,
            "action": action, "direcao": "LONG" if action == "buy" else "SHORT",
            "entry": float(entry), "tp": tp, "sl": sl,
            "leverage": leverage, "margem_usdt": self.margem_usdt,
            "notional_usdt": round(notional, 2), "qty": qty,
            "grade": grade, "regra": regra,
            "order_id": order_id, "dry_run": self.dry_run,
            "aberta_em": _now_iso(),
        }
        with self._lock:
            self._posicoes[moeda] = registro
            self._salvar()

        modo = "DRY-RUN" if self.dry_run else "AO VIVO"
        msg = (f"[EXEC-REAL {modo}] ENTRADA {registro['direcao']} {moeda} {tf} "
               f"@ {entry} | {leverage}x | margem ${self.margem_usdt:.0f} "
               f"(notional ${notional:.0f}) | qty {qty:.6f} | "
               f"TP {tp} SL {sl} | grade {grade} regra {regra} | ordem {order_id}")
        self.log.warning(msg)
        if self.notifier is not None:
            try:
                self.notifier.send(f"🟢 {msg}")
            except Exception:  # noqa: BLE001
                pass
        return registro

    # ------------------------------------------------------------------ #
    def status(self) -> Dict[str, Any]:
        with self._lock:
            posicoes = list(self._posicoes.values())
        return {
            "ativa": self.ativa,
            "dry_run": self.dry_run,
            "cliente_ok": self.client is not None,
            "credenciais_validas": self.credenciais_validas,
            "saldo_usdt": self.saldo_usdt,
            "erro_init": self.erro_init,
            "moedas": self.moedas,
            "timeframes": self.timeframes,
            "grades_permitidas": self.grades_permitidas,
            "exigir_grade": self.exigir_grade,
            "max_posicoes": self.max_posicoes,
            "uma_ordem_por_moeda": self.uma_ordem_por_moeda,
            "margem_usdt": self.margem_usdt,
            "capital_total_usdt": self.capital_total_usdt,
            "alavancagem_base": self.alav_base,
            "alavancagem_grade_a": self.alav_grade_a,
            "posicoes_abertas": len(posicoes),
            "posicoes": posicoes,
        }
