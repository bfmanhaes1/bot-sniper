# -*- coding: utf-8 -*-
"""
autonomous_scanner.py — MODO AUTÔNOMO do Bot Crypto Sombra
==========================================================
Este módulo transforma o bot em UM ÚNICO robô que roda as 60 combinações
(10 moedas x 3 timeframes x 2 alavancagens) SOZINHO, sem depender de nenhum
alerta do TradingView.

POR QUÊ
-------
Antes, o bot só reagia a webhooks do TradingView (sinal TSTS + cruzamento de
RSI). Como o indicador TSTS Sniper Rifle é FECHADO e nem todo alerta chegava
para as 10 moedas, 6 moedas ficavam sem nenhum sinal e a análise não acontecia.

Agora o bot BUSCA os candles públicos da Bitget (só leitura) e CALCULA ele
mesmo, a cada fechamento de candle ("Once Per Bar Close"):

  1. CRUZAMENTO DE RSI  = RSI(14) cruzando a sua média MA(14).
       -> alimenta o mesmo motor de confirmação (engine.on_rsi_cross).
  2. SINAL TSTS-PROXY   = aproximação reproduzível do "Sniper Rifle" com os
       componentes públicos da estratégia Silent Sniper:
         BUY  : WaveTrend (wt1) cruza ACIMA de wt2  + HMA(15) subindo + RSI>=50
         SELL : WaveTrend (wt1) cruza ABAIXO de wt2 + HMA(15) caindo  + RSI<=50
       -> alimenta o mesmo pipeline de decisão/simulação (controller.processar_sinal).

Tudo é registrado no MESMO formato de log de sempre (crypto_logs/), com o campo
extra `_source="autonomo"` e `sinal_origem` para você distinguir do que vinha do
TradingView e validar a fidelidade do proxy.

IMPORTANTE: continua sendo MODO SOMBRA — nenhuma ordem real é enviada. Só
consultamos PREÇO/CANDLE público da Bitget (endpoint aberto, sem credenciais).
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import market_data

logger = logging.getLogger("autonomous_scanner")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutonomousScanner:
    """
    Varre todas as combinações moeda+timeframe, detecta cruzamento de RSI e
    sinal TSTS-proxy a cada NOVO candle fechado e alimenta o controlador de
    sombra (mesma simulação/registro de sempre).
    """

    def __init__(self, controller, config: Dict[str, Any]):
        self.controller = controller
        self.cfg = config
        scan = config.get("scanner", {}) or {}

        self.moedas: List[str] = controller.moedas
        self.timeframes: List[str] = controller.timeframes
        self.symbols: Dict[str, str] = config.get("symbols_bitget", {})

        self.intervalo: int = int(scan.get("intervalo_segundos", 25))
        self.exigir_hma: bool = bool(scan.get("exigir_hma_alinhada", True))
        self.exigir_rsi_lado: bool = bool(scan.get("exigir_rsi_lado", True))
        self.usar_wavetrend: bool = bool(scan.get("usar_wavetrend", True))
        # Pausa curta entre requisições à Bitget (gentileza com a API pública).
        self.pausa_req: float = float(scan.get("pausa_entre_requisicoes_seg", 0.15))

        # Estado por combinação (MOEDA_TF)
        self._ultimo_bar_ts: Dict[str, float] = {}     # última barra JÁ processada
        self._semeado: Dict[str, bool] = {}            # já semeou estado do RSI?

        # Contadores de diagnóstico (resetam no restart)
        self.scans_completos = 0
        self.barras_processadas = 0
        self.rsi_cross_detectados = 0
        self.sinais_proxy_detectados = 0
        self.ultimo_scan_iso: Optional[str] = None
        self.ultimo_erro: Optional[str] = None

        self._parar = threading.Event()

    # ------------------------------------------------------------------ #
    def _chave(self, moeda: str, tf: str) -> str:
        return f"{moeda}_{tf}"

    def _lado_rsi(self, rsi: float, rsi_ma: float) -> str:
        return "up" if rsi >= rsi_ma else "down"

    # ------------------------------------------------------------------ #
    def _processar_combo(self, moeda: str, tf: str) -> None:
        symbol = self.symbols.get(moeda)
        if not symbol:
            return
        frame = market_data.get_signal_frame(symbol, tf)
        if not frame.get("ok"):
            return

        bar_ts = frame.get("bar_ts")
        chave = self._chave(moeda, tf)

        # Só processa quando um NOVO candle fechou (evita duplicar no mesmo bar).
        if self._ultimo_bar_ts.get(chave) == bar_ts:
            return

        rsi = frame["rsi"]; rsi_prev = frame["rsi_prev"]
        rsi_ma = frame["rsi_ma"]; rsi_ma_prev = frame["rsi_ma_prev"]
        close = frame.get("close")

        # 1) SEMEADURA: na primeira observação, define o lado atual do RSI no
        #    motor SEM contar como cruzamento e SEM logar (evita ruído inicial).
        if not self._semeado.get(chave):
            lado = self._lado_rsi(rsi, rsi_ma)
            try:
                self.controller.semear_rsi(moeda, tf, lado)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao semear RSI %s %s: %s", moeda, tf, exc)
            self._semeado[chave] = True
            self._ultimo_bar_ts[chave] = bar_ts
            return  # não gera sinal na barra de semeadura

        # A partir daqui, é um candle novo e o estado já foi semeado.
        self._ultimo_bar_ts[chave] = bar_ts
        self.barras_processadas += 1

        # 2) CRUZAMENTO DE RSI (RSI x MA) nesta barra fechada
        lado_prev = "up" if rsi_prev >= rsi_ma_prev else "down"
        lado_now = "up" if rsi >= rsi_ma else "down"
        if lado_now != lado_prev:
            direction = lado_now  # 'up' = cruzou para cima ; 'down' = para baixo
            self.rsi_cross_detectados += 1
            payload_rsi = {
                "direction": direction, "timeframe": tf,
                "rsi": rsi, "rsi_ma": rsi_ma, "entry": close,
                "_source": "autonomo",
            }
            try:
                self.controller.processar_rsi_cross(moeda, payload_rsi)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Erro no cruzamento RSI %s %s: %s", moeda, tf, exc)

        # 3) SINAL TSTS-PROXY nesta barra fechada
        action = self._detectar_sinal_proxy(frame)
        if action:
            self.sinais_proxy_detectados += 1
            payload_sinal = {
                "action": action, "timeframe": tf,
                "rsi": rsi, "rsi_ma": rsi_ma, "entry": close,
                "_source": "autonomo", "sinal_origem": "tsts_proxy",
            }
            try:
                self.controller.processar_sinal(moeda, payload_sinal)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Erro no sinal proxy %s %s: %s", moeda, tf, exc)

    # ------------------------------------------------------------------ #
    def _detectar_sinal_proxy(self, frame: Dict[str, Any]) -> Optional[str]:
        """
        Aproximação reproduzível do TSTS Sniper Rifle usando WaveTrend + HMA + RSI.
        Devolve 'buy', 'sell' ou None (sem sinal nesta barra).
        """
        wt1 = frame.get("wt1"); wt1_prev = frame.get("wt1_prev")
        wt2 = frame.get("wt2"); wt2_prev = frame.get("wt2_prev")
        hma = frame.get("hma"); hma_prev = frame.get("hma_prev")
        rsi = frame.get("rsi")

        # Gatilho principal: cruzamento do WaveTrend (wt1 x wt2) nesta barra.
        cruz_up = cruz_down = False
        if self.usar_wavetrend and None not in (wt1, wt1_prev, wt2, wt2_prev):
            cruz_up = (wt1_prev <= wt2_prev) and (wt1 > wt2)
            cruz_down = (wt1_prev >= wt2_prev) and (wt1 < wt2)
        else:
            # Sem WaveTrend disponível: usa a virada de inclinação da HMA.
            if None not in (hma, hma_prev):
                cruz_up = hma > hma_prev
                cruz_down = hma < hma_prev

        if not (cruz_up or cruz_down):
            return None

        hma_subindo = (hma is not None and hma_prev is not None and hma > hma_prev)
        hma_caindo = (hma is not None and hma_prev is not None and hma < hma_prev)

        if cruz_up:
            if self.exigir_hma and not hma_subindo:
                return None
            if self.exigir_rsi_lado and (rsi is None or rsi < 50):
                return None
            return "buy"
        if cruz_down:
            if self.exigir_hma and not hma_caindo:
                return None
            if self.exigir_rsi_lado and (rsi is None or rsi > 50):
                return None
            return "sell"
        return None

    # ------------------------------------------------------------------ #
    def scan_once(self) -> Dict[str, Any]:
        """Uma varredura completa das 30 combinações moeda+TF."""
        for moeda in self.moedas:
            for tf in self.timeframes:
                if self._parar.is_set():
                    break
                try:
                    self._processar_combo(moeda, tf)
                except Exception as exc:  # noqa: BLE001
                    self.ultimo_erro = f"{moeda} {tf}: {exc}"
                    logger.exception("Erro ao processar %s %s: %s", moeda, tf, exc)
                if self.pausa_req > 0:
                    time.sleep(self.pausa_req)
        self.scans_completos += 1
        self.ultimo_scan_iso = _now_iso()
        return self.snapshot()

    def loop(self) -> None:
        logger.info("Scanner autônomo iniciado: %d moedas x %d TFs, intervalo %ss.",
                    len(self.moedas), len(self.timeframes), self.intervalo)
        # 1ª passada: semeia o estado de todas as combinações (sem gerar sinal).
        try:
            self.scan_once()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro na varredura inicial: %s", exc)
        while not self._parar.is_set():
            t0 = time.time()
            try:
                self.scan_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Erro na varredura: %s", exc)
            dt = time.time() - t0
            espera = max(1.0, self.intervalo - dt)
            self._parar.wait(espera)

    def start(self) -> None:
        threading.Thread(target=self.loop, name="scanner-autonomo", daemon=True).start()

    def stop(self) -> None:
        self._parar.set()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ativo": not self._parar.is_set(),
            "intervalo_segundos": self.intervalo,
            "combinacoes_moeda_tf": len(self.moedas) * len(self.timeframes),
            "scans_completos": self.scans_completos,
            "barras_processadas": self.barras_processadas,
            "rsi_cross_detectados": self.rsi_cross_detectados,
            "sinais_proxy_detectados": self.sinais_proxy_detectados,
            "ultimo_scan": self.ultimo_scan_iso,
            "ultimo_erro": self.ultimo_erro,
            "filtros": {
                "exigir_hma_alinhada": self.exigir_hma,
                "exigir_rsi_lado": self.exigir_rsi_lado,
                "usar_wavetrend": self.usar_wavetrend,
            },
        }
