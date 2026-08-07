# -*- coding: utf-8 -*-
"""Teste de integração do GATE do CATALISADOR via Flask test_client + _processar_decisao.
Gate atual = Sniper (rosa x azul) + RSI + CATALISADOR (por moeda).
O gate antigo de cores (BOKK/BS Detector) está DESLIGADO por config (confirmacao.ativa=false),
mas os endpoints continuam existindo (compat). Roda com: python3 test_integracao_gate.py"""
import json
import server

falhas = []
def check(nome, cond):
    print(("  OK  " if cond else " FALHA ") + nome)
    if not cond:
        falhas.append(nome)

app = server.app
ctrl = server.controller
client = app.test_client()

# 1) Webhook do catalisador para BTC: tudo BULL (alinhado) -> BUY deve ENTRAR
r = client.post("/catalyst/BTC",
                json={"c5m": "BULL", "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
check("POST /catalyst/BTC -> 200 ok", r.status_code == 200 and r.get_json().get("ok"))

# 2) Snapshot do catalisador mostra o estado da moeda
snap = ctrl.catalyst.snapshot()
check("snapshot do catalyst tem BTC", "BTC" in snap.get("estado", {}))

# 3) checar direto: BUY BTC deve passar (tudo BULL)
ok, det = ctrl.catalyst.checar("BTC", "buy")
check("checar BUY BTC passa (tudo BULL)", ok)

# 4) Webhook do catalisador para ETH: tudo BEAR -> BUY deve BLOQUEAR (contra a alta)
r = client.post("/catalyst/ETH",
                json={"c5m": "BEAR", "c15m": "BEAR", "c1h": "BEAR", "vwap": "BEAR"})
check("POST /catalyst/ETH -> 200 ok", r.status_code == 200 and r.get_json().get("ok"))
ok, det = ctrl.catalyst.checar("ETH", "buy")
check("checar BUY ETH bloqueia (tudo BEAR)", not ok)

# 5) _processar_decisao com entrar=True e gate BLOQUEADO (ETH BUY contra a alta)
#    o motor JÁ registrou a trava de posição -> ao bloquear ela deve ser liberada
eng = ctrl._engine("ETH", "5m")
eng._registrar_posicao(eng._get("ETH"), "buy")  # simula a trava que o motor põe
res = ctrl._processar_decisao(
    "ETH", "5m", "buy", "TSTS", 55.0, 50.0, 3000.0,
    {"entrar": True, "cruzamento": 1, "motivo": "teste"}, "teste")
check("gate BLOQUEIA entrada ETH 5m (catalisador contra)",
      res.get("decisao") == "bloqueado_catalisador")
check("trava de posição liberada após bloqueio",
      eng._get("ETH").posicao_aberta is False)

# 6) _processar_decisao com entrar=True e gate LIBERADO (BTC BUY tudo BULL)
res = ctrl._processar_decisao(
    "BTC", "5m", "buy", "TSTS", 55.0, 50.0, 60000.0,
    {"entrar": True, "cruzamento": 1, "motivo": "teste"}, "teste")
check("gate LIBERA entrada BTC 5m (catalisador a favor)", res.get("decisao") == "entrar")

# 7) endpoint /diag traz o bloco catalyst
r = client.get("/diag")
dj = r.get_json()
check("/diag traz bloco catalyst", dj.get("catalyst") is not None
      and dj["catalyst"].get("ativa") is True)

# 8) moeda sem estado do catalisador -> fail-open (legado): BUY passa
ok, det = ctrl.catalyst.checar("SOL", "buy")
check("SOL sem estado -> legado (entra, fail-open)", ok and det.get("regra") == "legado")

# 9) endpoint GENÉRICO /catalyst com a moeda no JSON (ticker do TradingView)
r = client.post("/catalyst",
                json={"moeda": "BITGET:LINKUSDT.P", "c5m": "BULL",
                      "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
j = r.get_json()
check("POST /catalyst (moeda no JSON) -> normaliza LINK",
      r.status_code == 200 and j.get("ok") and j.get("moeda") == "LINK")
ok, det = ctrl.catalyst.checar("LINK", "buy")
check("checar BUY LINK passa (recebido via endpoint genérico)", ok)

# 10) moeda FORA das 10 é aceita (usuário pode olhar outras moedas)
r = client.post("/catalyst", json={"ticker": "DOGEUSDT", "c5m": "BULL",
                                    "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
check("moeda fora das 10 (DOGE) é aceita", r.get_json().get("ok") is True)

# 11) payload sem moeda nenhuma -> erro claro
r = client.post("/catalyst", json={"c5m": "BULL"})
check("payload sem moeda -> erro", r.get_json().get("ok") is False)

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S) -> {falhas}")
    raise SystemExit(1)
print("RESULTADO: INTEGRAÇÃO OK ✅")
