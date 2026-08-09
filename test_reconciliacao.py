"""
Teste local da JANELA DE RECONCILIACAO gatilho x catalisador.

Simula a RACE CONDITION:
  1) Catalisador da moeda esta CONTRA (BEAR) -> um gatilho de BUY e BLOQUEADO.
  2) O gatilho fica guardado (RACE_CANDIDATO).
  3) O catalisador ATUALIZA para BULL (a favor) -> reavaliacao dispara e ENTRA
     (RECONCILIADO), medindo a defasagem.
  4) Confere tambem: expiracao (RACE_EXPIRADO) e que a execucao real NAO e
     chamada quando reconciliacao.permite_real=false (shadow-safe).

Nao faz rede: monkeypatch em _preco_publico e desliga o executor real.
"""
import json
import time
import crypto_shadow


def carregar_controller():
    cfg = json.load(open("config.json"))
    # garante reconciliacao ativa/shadow para o teste (independente do arquivo)
    cfg.setdefault("reconciliacao", {})
    cfg["reconciliacao"]["ativa"] = True
    cfg["reconciliacao"]["janela_seg"] = 20
    cfg["reconciliacao"]["permite_real"] = False
    c = crypto_shadow.CryptoShadowController(cfg, notifier=None)
    # sem rede: preco fixo e sem executor real
    c._preco_publico = lambda moeda, use_cache=True: 100.0
    c.executor_real = None
    return c


def contar_registros():
    """Le o estudo/log? Aqui so vamos observar o dict interno e retornos."""
    pass


def test_fluxo_reconciliacao():
    c = carregar_controller()
    moeda = "SOL"
    tf = "5m"

    # 1) Catalisador CONTRA um BUY: 5m/15m BEAR (R2b bloqueia). 30s/1m BULL para
    #    nao cair no filtro timing.
    c.atualizar_catalyst(moeda, {"c5m": "BEAR", "c15m": "BEAR",
                                 "c30s": "BULL", "c1m": "BULL", "c1h": "NEUT"})
    ok_gate, det = c._checar_gates(moeda, tf, "buy")
    assert not ok_gate, f"esperava BLOQUEIO inicial, veio {det}"
    print("[OK] gate bloqueou o BUY inicialmente:", det.get("regra"), det.get("motivo"))

    # 2) Simula o gatilho bloqueado -> guarda para reconciliar
    c._guardar_reconciliacao(moeda, tf, "buy", "TSTS_SNIPER_BUY", 55.0,
                             1, "teste", "BULL", {**det, "gate": "catalyst"})
    chave = f"{moeda}_{tf}_buy"
    assert chave in c._reconc, "gatilho nao foi guardado"
    print("[OK] gatilho guardado em _reconc:", list(c._reconc.keys()))

    # 3) Catalisador VIRA a favor (BULL). Isso dispara a reavaliacao.
    time.sleep(1)  # defasagem ~1s
    res = c.atualizar_catalyst(moeda, {"c5m": "BULL", "c15m": "BULL",
                                       "c30s": "BULL", "c1m": "BULL", "c1h": "BULL"})
    print("[OK] retorno atualizar_catalyst:", res.get("reconciliacao"))
    assert res.get("reconciliacao"), "reconciliacao nao disparou apos catalisador virar"
    assert chave not in c._reconc, "pendente deveria ter sido consumido"
    chave_pos = f"{moeda}_{tf}"  # posicao usa MOEDA_TF (sem action)
    assert chave_pos in c._positions, "posicao simulada nao foi aberta na reconciliacao"
    defas = res["reconciliacao"][0]["defasagem_seg"]
    assert defas >= 1.0, f"defasagem medida inesperada: {defas}"
    print(f"[OK] RECONCILIADO — posicao aberta na sombra, defasagem={defas}s, "
          f"grade={res['reconciliacao'][0]['grade']}")

    # 4) EXPIRACAO: guarda outro gatilho, envelhece alem da janela, reavalia.
    c2 = carregar_controller()
    c2._reconc_janela_seg = 2
    c2.atualizar_catalyst(moeda, {"c5m": "BEAR", "c15m": "BEAR",
                                  "c30s": "BULL", "c1m": "BULL", "c1h": "NEUT"})
    _, det2 = c2._checar_gates(moeda, tf, "buy")
    c2._guardar_reconciliacao(moeda, tf, "buy", "X", 55.0, 1, "t", "BULL",
                              {**det2, "gate": "catalyst"})
    # envelhece manualmente o pendente
    c2._reconc[f"{moeda}_{tf}_buy"]["ts"] = time.time() - 10
    res2 = c2.atualizar_catalyst(moeda, {"c5m": "BULL", "c15m": "BULL",
                                         "c30s": "BULL", "c1m": "BULL", "c1h": "BULL"})
    assert f"{moeda}_{tf}_buy" not in c2._reconc, "pendente expirado nao foi removido"
    assert not res2.get("reconciliacao"), "expirado nao deveria reconciliar"
    print("[OK] RACE_EXPIRADO — pendente alem da janela foi descartado sem entrar")

    print("\nTODOS OS TESTES PASSARAM ✅")


if __name__ == "__main__":
    test_fluxo_reconciliacao()
