"""Testes da lógica nova do ExecutorReal: grade C, regras_permitidas, 1m gate/modulador."""
import json, logging, sys
sys.path.insert(0, "/home/ubuntu/bot_tsts_sniper")
from executor_real import ExecutorReal

logging.basicConfig(level=logging.CRITICAL)
log = logging.getLogger("t")

cfg = json.load(open("/home/ubuntu/bot_tsts_sniper/config.json"))
# força ativa + client fake para testar as guardas (sem chamar Bitget)
cfg["execucao_real"]["ativa"] = True
cfg["symbols_bitget"] = {"VIRTUAL": "VIRTUALUSDT"}

ex = ExecutorReal(cfg, log)
# injeta um client fake (pode_entrar checa self.client is not None)
class FakeClient: pass
ex.client = FakeClient()

falhas = []
def check(nome, got, esperado):
    ok = got == esperado
    print(f"[{'OK' if ok else 'FALHA'}] {nome}: got={got} esperado={esperado}")
    if not ok: falhas.append(nome)

def pe(grade, action="buy", regra=None, rel_1m=None, tf="5m", moeda="VIRTUAL"):
    ex._posicoes = {}  # limpa posições entre testes
    return ex.pode_entrar(moeda, tf, grade, action, regra, rel_1m)[0]

print("=== ADMISSIBILIDADE POR GRADE ===")
check("grade A entra", pe("A", rel_1m="FAVOR"), True)
check("grade B entra", pe("B", rel_1m="FAVOR"), True)
check("grade C com 1m FAVOR entra", pe("C", rel_1m="FAVOR"), True)
check("grade C com 1m NEUTRO NAO entra (trava)", pe("C", rel_1m="N"), False)
check("grade C com 1m CONTRA NAO entra (porteiro)", pe("C", rel_1m="CONTRA"), False)
check("grade C sem info do 1m NAO entra (trava)", pe("C", rel_1m=None), False)

print("=== REGRAS PERMITIDAS (grade None) ===")
check("None + R6 + 1m FAVOR entra", pe(None, regra="R6", rel_1m="FAVOR"), True)
check("None + R7 + 1m NEUTRO entra", pe(None, regra="R7", rel_1m="N"), True)
check("None + R6 + 1m CONTRA NAO entra (porteiro)", pe(None, regra="R6", rel_1m="CONTRA"), False)
check("None + R3 (nao permitida) NAO entra", pe(None, regra="R3", rel_1m="FAVOR"), False)
check("None + R9 (nao permitida) NAO entra", pe(None, regra="R9", rel_1m="FAVOR"), False)

print("=== PORTEIRO NAO BARRA A/B (so rebaixa alav) ===")
check("grade A + 1m CONTRA ainda entra (porteiro nao barra A)", pe("A", regra="R4", rel_1m="CONTRA"), True)
check("grade B + 1m CONTRA ainda entra (porteiro nao barra B)", pe("B", regra="R2", rel_1m="CONTRA"), True)

print("=== MODULADOR DE ALAVANCAGEM (via abrir, mockando place_order) ===")
def fake_place_order(**kw):
    return {"code": "00000", "data": {"orderId": "fake123"}}
ex.client.place_order = fake_place_order

def lev(grade, rel_1m, regra=None):
    ex._posicoes = {}
    det = ex.abrir("VIRTUAL", "5m", "buy", 1.0, 1.008, 0.989, grade, regra, rel_1m)
    return det["leverage"] if det else None

check("A + 1m FAVOR = 10x (boost mantido)", lev("A","FAVOR","R4"), 10)
check("A + 1m NEUTRO = 5x (boost removido)", lev("A","N","R4"), 5)
check("A + 1m CONTRA = 5x (rebaixado)", lev("A","CONTRA","R4"), 5)
check("B + 1m FAVOR = 5x (base)", lev("B","FAVOR","R2"), 5)
check("C + 1m FAVOR = 5x (base)", lev("C","FAVOR","R2"), 5)
check("None+R6 + 1m FAVOR = 5x (base)", lev(None,"FAVOR","R6"), 5)

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S): {falhas}")
    sys.exit(1)
print("RESULTADO: TODOS OS TESTES PASSARAM ✅")
