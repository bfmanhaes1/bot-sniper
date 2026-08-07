# -*- coding: utf-8 -*-
"""
Teste do ESTUDO FORCADO de TP/SL (livro-razao duravel + MFE/DD de janela completa).
Roda com: python3 test_estudo_tpsl.py

Nao envia nenhuma ordem: usa dados simulados (monkeypatch nos metodos de preco/velas).
Isola o diretorio de dados via CRYPTO_DATA_DIR (pasta temporaria) para nao sujar nada.
"""
import os
import tempfile

# Isola o DATA_DIR ANTES de importar o crypto_logger (ele resolve o caminho no import).
_TMP = tempfile.mkdtemp(prefix="estudo_test_")
os.environ["CRYPTO_DATA_DIR"] = _TMP

import crypto_logger          # noqa: E402
from crypto_shadow import CryptoShadowController  # noqa: E402
from datetime import timedelta  # noqa: E402

falhas = []


def check(nome, cond):
    print(("  OK  " if cond else " FALHA ") + nome)
    if not cond:
        falhas.append(nome)


# --------------------------------------------------------------------------- #
# 1) Livro-razao: registrar_estudo / ler_estudo / resumo_estudo
# --------------------------------------------------------------------------- #
check("DATA_DIR aponta para a pasta temporaria", crypto_logger.DATA_DIR == _TMP)
check("livro-razao comeca vazio", crypto_logger.ler_estudo() == [])

crypto_logger.registrar_estudo({"moeda": "BTC", "tf": "5m", "mfe_pct": 1.0, "dd_pct": 0.5})
crypto_logger.registrar_estudo({"moeda": "BTC", "tf": "5m", "mfe_pct": 3.0, "dd_pct": 1.5})
linhas = crypto_logger.ler_estudo()
check("append acumulou 2 linhas", len(linhas) == 2)
check("append-only preserva a ordem", linhas[0]["mfe_pct"] == 1.0 and linhas[1]["mfe_pct"] == 3.0)

res = crypto_logger.resumo_estudo()
check("resumo conta total", res["total_entradas"] == 2)
check("resumo MFE medio = 2.0", res["geral"]["mfe_medio"] == 2.0)
check("resumo DD max = 1.5", res["geral"]["dd_max"] == 1.5)
check("resumo por_combinacao tem BTC_5m", "BTC_5m" in res["por_combinacao"])

res_btc = crypto_logger.resumo_estudo(moeda="BTC", tf="5m")
check("filtro moeda/tf funciona", res_btc["total_entradas"] == 2)
res_eth = crypto_logger.resumo_estudo(moeda="ETH")
check("filtro por moeda inexistente = 0", res_eth["total_entradas"] == 0)

# Zera o livro para o proximo bloco medir apenas a entrada observada.
open(crypto_logger.ESTUDO_PATH, "w").close()
check("livro-razao zerado", crypto_logger.ler_estudo() == [])


# --------------------------------------------------------------------------- #
# 2) Ciclo de observacao de janela completa (a parte central do pedido)
# --------------------------------------------------------------------------- #
CFG = {
    "moedas": ["BTC"], "timeframes": ["5m"], "alavancagens": [5, 10],
    "symbols_bitget": {"BTC": "BTCUSDT"},
    "simulacao": {"margin_usdt": 50, "tp_percent": 2.0, "sl_percent": 1.0,
                  "poll_price_minutes": 5},
    "simulacao_por_tf": {"5m": {"tp_percent": 0.80, "sl_percent": 1.10}},
    "estudo_tpsl": {"ativa": True, "janela_min_por_tf": {"5m": 120}},
    "engine": {"posicao_timeout_min": 240},
}
ctrl = CryptoShadowController(CFG)
check("estudo ativo lido do config", ctrl.estudo_ativa is True)
check("janela 5m = 120 min", ctrl._janela_estudo_min("5m") == 120)

# A janela completa correu de 98 (contra) a 105 (a favor); entrada em 100 (LONG).
# Isso e MUITO alem do TP de 0.8% (~100.8) -> prova que o estudo NAO trava no TP.
ctrl._high_low_desde = lambda moeda, tf, desde, ate=None: (105.0, 98.0)
# Preco atual toca o TP (100.8) logo de cara.
ctrl._preco_publico = lambda moeda, use_cache=True: 101.0

ctrl._abrir_simulacao("BTC", "5m", "buy", 100.0, 1, "TSTS", 55.0)
pos = ctrl._positions["BTC_5m"]
check("posicao criada com observa_ate", pos.observa_ate is not None)

# 1a passada do monitor: toca TP -> registra P&L, mas CONTINUA observando.
ctrl.verificar_tp_sl()
check("P&L registrado no toque do TP", pos.fechada_pnl is True)
check("motivo de saida = TP", pos.motivo_saida == "TP")
check("posicao AINDA em observacao (nao removida)", "BTC_5m" in ctrl._positions)
check("livro-razao ainda vazio (janela nao terminou)", crypto_logger.ler_estudo() == [])

# Forca o fim da janela e roda de novo -> finaliza o estudo e grava a excursao.
pos.observa_ate = pos.aberta_em - timedelta(minutes=1)
ctrl.verificar_tp_sl()
check("posicao removida apos finalizar", "BTC_5m" not in ctrl._positions)

livro = crypto_logger.ler_estudo()
check("livro-razao ganhou 1 linha", len(livro) == 1)
if livro:
    reg = livro[0]
    check("MFE da janela completa = 5.0% (105 vs 100)", reg["mfe_pct"] == 5.0)
    check("DD da janela completa = 2.0% (100 vs 98)", reg["dd_pct"] == 2.0)
    check("MFE >> TP configurado (nao circular)", reg["mfe_pct"] > reg["tp_percent_cfg"])
    check("registra o que o TP/SL teria feito (saida_tpsl=TP)", reg["saida_tpsl"] == "TP")
    check("guarda tp_percent_cfg=0.8", reg["tp_percent_cfg"] == 0.8)
    check("direcao LONG", reg["direcao"] == "LONG")


# --------------------------------------------------------------------------- #
# 3) Entrada que NUNCA bate TP/SL -> fecha por timeout ao fim da janela
# --------------------------------------------------------------------------- #
open(crypto_logger.ESTUDO_PATH, "w").close()
ctrl._high_low_desde = lambda moeda, tf, desde, ate=None: (100.3, 99.7)
ctrl._preco_publico = lambda moeda, use_cache=True: 100.0  # nao toca TP nem SL
ctrl._abrir_simulacao("BTC", "5m", "buy", 100.0, 1, "TSTS", 55.0)
pos2 = ctrl._positions["BTC_5m"]
ctrl.verificar_tp_sl()
check("sem tocar TP/SL, ainda nao fechou P&L", pos2.fechada_pnl is False)
pos2.observa_ate = pos2.aberta_em - timedelta(minutes=1)
ctrl.verificar_tp_sl()
livro2 = crypto_logger.ler_estudo()
check("timeout gravou 1 linha", len(livro2) == 1)
check("motivo de saida = timeout", livro2 and livro2[0]["saida_tpsl"] == "timeout")


# --------------------------------------------------------------------------- #
print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S) ❌ -> {falhas}")
    raise SystemExit(1)
print("RESULTADO: ESTUDO DE TP/SL OK ✅")
