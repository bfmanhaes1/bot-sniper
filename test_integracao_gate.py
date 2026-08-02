# -*- coding: utf-8 -*-
"""Teste de integração do gate via Flask test_client + fluxo _processar_decisao.
Roda com: python3 test_integracao_gate.py"""
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

# 1) Webhook BOKK verde para BTC 5m
r = client.post("/verde/bokk/BTC/5m", json={"signal": "green"})
check("POST /verde/bokk/BTC/5m -> 200 ok", r.status_code == 200 and r.get_json().get("ok"))

# 2) Webhook estado consolidado BS Detector (hist vermelho, plots verdes)
r = client.post("/bsdet/estado/BTC/5m",
                json={"hist": "red", "p1": "green", "p2": "green", "p3": "green"})
j = r.get_json()
check("POST /bsdet/estado/BTC/5m -> aplica 4 componentes",
      r.status_code == 200 and j.get("ok") and len(j.get("aplicados", {})) == 4)

# 3) Snapshot mostra o estado
snap = ctrl.confirm.snapshot()
check("snapshot tem combinação BTC_5m", "BTC_5m" in snap.get("estado", {}))

# 4) checar direto: BUY deve passar (tudo alinhado)
ok, det = ctrl.confirm.checar("BTC", "5m", "buy", 5.0)
check("checar BUY BTC 5m passa (alinhado)", ok)

# 5) _processar_decisao com entrar=True e gate BLOQUEADO (moeda sem cores)
#    ETH 5m não recebeu nenhuma cor -> fail-closed deve bloquear
eng = ctrl._engine("ETH", "5m")
eng._registrar_posicao(eng._get("ETH"), "buy")  # simula a trava que o motor põe
res = ctrl._processar_decisao(
    "ETH", "5m", "buy", "TSTS", 55.0, 50.0, 3000.0,
    {"entrar": True, "cruzamento": 1, "motivo": "teste"}, "teste")
check("gate BLOQUEIA entrada ETH 5m sem cores (fail-closed)",
      res.get("decisao") == "bloqueado_confirmacao")
# a trava deve ter sido liberada
check("trava de posição liberada após bloqueio",
      eng._get("ETH").posicao_aberta is False)

# 6) _processar_decisao com entrar=True e gate LIBERADO (BTC 5m alinhado)
res = ctrl._processar_decisao(
    "BTC", "5m", "buy", "TSTS", 55.0, 50.0, 60000.0,
    {"entrar": True, "cruzamento": 1, "motivo": "teste"}, "teste")
check("gate LIBERA entrada BTC 5m alinhado", res.get("decisao") == "entrar")

# 7) endpoint /diag traz o bloco confirmacao
r = client.get("/diag")
dj = r.get_json()
check("/diag traz bloco confirmacao", dj.get("confirmacao") is not None
      and dj["confirmacao"].get("ativa") is True)

# 8) componente individual (compat v3)
r = client.post("/bsdet/hist/SOL/1m", json={"signal": "red"})
check("POST /bsdet/hist/SOL/1m -> 200 ok (compat v3)",
      r.status_code == 200 and r.get_json().get("ok"))

# 9) moeda não monitorada é rejeitada
r = client.post("/verde/bokk/DOGE/5m", json={"signal": "green"})
check("moeda não monitorada (DOGE) -> erro", r.get_json().get("ok") is False)

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S) -> {falhas}")
    raise SystemExit(1)
print("RESULTADO: INTEGRAÇÃO OK ✅")
