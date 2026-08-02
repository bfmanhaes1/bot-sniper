# -*- coding: utf-8 -*-
"""Testes da camada de confirmação (gate). Roda com: python3 test_confirmacao.py"""
import time
from confirmacao import ConfirmStore, normalizar_cor

CFG = {
    "confirmacao": {
        "ativa": True,
        "bokk_tolerancia_velas": 3,
        "exigir": {"bokk": "mesma", "histograma": "oposta",
                   "plot1": "mesma", "plot2": "mesma", "plot3": "mesma"},
    }
}

falhas = []
def check(nome, cond):
    print(("  OK  " if cond else " FALHA ") + nome)
    if not cond:
        falhas.append(nome)

# --- normalizar_cor ---
check("normalizar verde/green/buy -> green",
      normalizar_cor("verde") == "green" and normalizar_cor("BUY") == "green"
      and normalizar_cor("green") == "green" and normalizar_cor(1) == "green")
check("normalizar vermelho/red/sell -> red",
      normalizar_cor("vermelho") == "red" and normalizar_cor("SELL") == "red"
      and normalizar_cor(-1) == "red")
check("normalizar lixo -> None", normalizar_cor("xyz") is None)

# --- BUY: todas alinhadas passa ---
s = ConfirmStore(CFG)
s.atualizar("bokk", "BTC", "5m", "green")
s.atualizar_varios("BTC", "5m", {"hist": "red", "p1": "green", "p2": "green", "p3": "green"})
ok, det = s.checar("BTC", "5m", "buy", 5.0)
check("BUY passa quando BOKK verde + hist vermelho + plots verdes", ok)

# --- BUY bloqueia se um plot errado ---
s.atualizar("plot2", "BTC", "5m", "red")
ok, det = s.checar("BTC", "5m", "buy", 5.0)
check("BUY bloqueia com plot2 vermelho", (not ok) and "plot2" in det.get("motivo", ""))

# --- BUY bloqueia se histograma verde (regra oposta) ---
s2 = ConfirmStore(CFG)
s2.atualizar("bokk", "ETH", "1m", "green")
s2.atualizar_varios("ETH", "1m", {"hist": "green", "p1": "green", "p2": "green", "p3": "green"})
ok, det = s2.checar("ETH", "1m", "buy", 1.0)
check("BUY bloqueia com histograma VERDE (deve ser vermelho)",
      (not ok) and "histograma" in det.get("motivo", ""))

# --- BUY bloqueia se falta componente (fail-closed) ---
s3 = ConfirmStore(CFG)
s3.atualizar("bokk", "SOL", "15m", "green")
ok, det = s3.checar("SOL", "15m", "buy", 15.0)
check("BUY bloqueia sem dados de histograma/plots (fail-closed)",
      (not ok) and "sem dados" in det.get("motivo", ""))

# --- SELL espelho passa ---
s4 = ConfirmStore(CFG)
s4.atualizar("bokk", "BNB", "5m", "red")
s4.atualizar_varios("BNB", "5m", {"hist": "green", "p1": "red", "p2": "red", "p3": "red"})
ok, det = s4.checar("BNB", "5m", "sell", 5.0)
check("SELL passa quando BOKK vermelho + hist verde + plots vermelhos", ok)

# --- SELL bloqueia se plots verdes ---
s4.atualizar("plot1", "BNB", "5m", "green")
ok, det = s4.checar("BNB", "5m", "sell", 5.0)
check("SELL bloqueia com plot1 verde", not ok)

# --- BOKK stale (tolerância de velas) ---
s5 = ConfirmStore(CFG)
s5.atualizar("bokk", "LINK", "1m", "green")
# força o timestamp do BOKK para 10 min atrás (tolerância = 3 velas * 1min = 3min)
s5._estado["LINK_1m"]["bokk"]["ts"] = time.time() - 600
s5.atualizar_varios("LINK", "1m", {"hist": "red", "p1": "green", "p2": "green", "p3": "green"})
ok, det = s5.checar("LINK", "1m", "buy", 1.0)
check("BUY bloqueia com BOKK fora da tolerância (velas)",
      (not ok) and "tolerância" in det.get("motivo", ""))

# --- BOKK dentro da tolerância passa ---
s5._estado["LINK_1m"]["bokk"]["ts"] = time.time() - 60  # 1 min atrás (< 3 min)
ok, det = s5.checar("LINK", "1m", "buy", 1.0)
check("BUY passa com BOKK dentro da tolerância (1 min < 3 min)", ok)

# --- tolerância 0 desliga o frescor ---
cfg0 = {"confirmacao": dict(CFG["confirmacao"], bokk_tolerancia_velas=0)}
s6 = ConfirmStore(cfg0)
s6.atualizar("bokk", "AVAX", "1m", "green")
s6._estado["AVAX_1m"]["bokk"]["ts"] = time.time() - 99999
s6.atualizar_varios("AVAX", "1m", {"hist": "red", "p1": "green", "p2": "green", "p3": "green"})
ok, det = s6.checar("AVAX", "1m", "buy", 1.0)
check("tolerância 0 ignora frescor do BOKK (passa mesmo antigo)", ok)

# --- gate desligado (ativa=false) sempre passa ---
cfg_off = {"confirmacao": {"ativa": False}}
s7 = ConfirmStore(cfg_off)
ok, det = s7.checar("APT", "5m", "buy", 5.0)
check("ativa=false: passa sem exigir nada", ok and det.get("ativa") is False)

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S) -> {falhas}")
    raise SystemExit(1)
print("RESULTADO: TODOS OS TESTES PASSARAM ✅")
