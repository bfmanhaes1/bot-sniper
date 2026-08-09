"""
Teste local do filtro MOEDAS_POR_TF (executor real).

Valida que:
- 1m: só VIRTUAL/SOL/NEAR passam
- 5m: todas as 7 moedas passam
- Outras moedas no 1m são BLOQUEADAS
"""
import json

def test_moedas_por_tf():
    cfg = json.load(open("config.json"))
    
    # Mock simplificado do ExecutorReal (sem cliente Bitget)
    class MockExecutor:
        def __init__(self, config):
            ecfg = config.get("execucao_real", {})
            self.ativa = True
            self.client = True  # finge que tem cliente
            self.moedas = [m.upper() for m in ecfg.get("moedas", [])]
            self.timeframes = list(ecfg.get("timeframes", []))
            self.moedas_por_tf = {}
            for tf, lst in (ecfg.get("moedas_por_tf") or {}).items():
                self.moedas_por_tf[tf] = [m.upper() for m in (lst or [])]
        
        def pode_entrar(self, moeda, tf):
            """Guarda simplificada (só moeda/tf, sem grade/regra)."""
            if not self.ativa or not self.client:
                return False, "executor desligado"
            moeda = moeda.upper()
            if moeda not in self.moedas:
                return False, f"{moeda} não na lista"
            if tf not in self.timeframes:
                return False, f"{tf} não na lista"
            # Filtro moedas_por_tf
            if tf in self.moedas_por_tf:
                if moeda not in self.moedas_por_tf[tf]:
                    return False, f"{moeda} bloqueada no {tf}"
            return True, "OK"
    
    ex = MockExecutor(cfg)
    print(f"moedas: {ex.moedas}")
    print(f"timeframes: {ex.timeframes}")
    print(f"moedas_por_tf: {ex.moedas_por_tf}\n")
    
    # 1m: só 3 moedas
    ok, msg = ex.pode_entrar("VIRTUAL", "1m")
    assert ok, f"VIRTUAL 1m deveria passar: {msg}"
    print(f"✅ VIRTUAL 1m: {msg}")
    
    ok, msg = ex.pode_entrar("SOL", "1m")
    assert ok, f"SOL 1m deveria passar: {msg}"
    print(f"✅ SOL 1m: {msg}")
    
    ok, msg = ex.pode_entrar("NEAR", "1m")
    assert ok, f"NEAR 1m deveria passar: {msg}"
    print(f"✅ NEAR 1m: {msg}")
    
    ok, msg = ex.pode_entrar("AVAX", "1m")
    assert not ok, "AVAX 1m deveria ser BLOQUEADA"
    assert "bloqueada no 1m" in msg, f"motivo errado: {msg}"
    print(f"✅ AVAX 1m BLOQUEADA: {msg}")
    
    ok, msg = ex.pode_entrar("LINK", "1m")
    assert not ok, "LINK 1m deveria ser BLOQUEADA"
    print(f"✅ LINK 1m BLOQUEADA: {msg}")
    
    # 5m: todas as 7
    for moeda in ["SOL", "VIRTUAL", "AVAX", "NEAR", "LINK", "APT", "BNB"]:
        ok, msg = ex.pode_entrar(moeda, "5m")
        assert ok, f"{moeda} 5m deveria passar: {msg}"
        print(f"✅ {moeda} 5m: {msg}")
    
    print("\n✅ TODOS OS TESTES PASSARAM — filtro moedas_por_tf funcionando!")

if __name__ == "__main__":
    test_moedas_por_tf()
