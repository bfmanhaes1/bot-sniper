#!/usr/bin/env python3
"""
TESTE COMPLETO DAS 10 MOEDAS
Simula alertas do TradingView para todas as moedas configuradas
e verifica se o bot processa corretamente.
"""
import requests
import json
import time
from datetime import datetime

# URL do bot no Railway
BASE_URL = "https://web-production-77454.up.railway.app"

# As 10 moedas configuradas
MOEDAS = ["BTC", "BNB", "ETH", "SOL", "VIRTUAL", "LINK", "AVAX", "NEAR", "APT", "BGB"]

# Payload base do catalisador (grade A - forte)
PAYLOAD_GRADE_A = {
    "c30s": "BULL",
    "c1m": "BULL",     # 1m a FAVOR
    "c5m": "BULL",     # 5m a favor
    "c15m": "BULL",    # 15m a favor
    "c1h": "BULL",     # 1h a favor → GRADE A
    "vwap": "BULL",
    "market": "TRENDING"
}

# Payload grade C (contra-tendência 1h)
PAYLOAD_GRADE_C_1M_FAVOR = {
    "c30s": "BULL",
    "c1m": "BULL",     # 1m A FAVOR (deve passar)
    "c5m": "BULL",
    "c15m": "BULL",
    "c1h": "BEAR",     # 1h contra → GRADE C
    "vwap": "BULL",
    "market": "TRENDING"
}

# Payload grade C com 1m CONTRA (deve bloquear)
PAYLOAD_GRADE_C_1M_CONTRA = {
    "c30s": "BULL",
    "c1m": "BEAR",     # 1m CONTRA (porteiro deve bloquear)
    "c5m": "BULL",
    "c15m": "BULL",
    "c1h": "BEAR",     # 1h contra → GRADE C
    "vwap": "BULL",
    "market": "TRENDING"
}

def colorir(texto, cor):
    """Adiciona cor ao texto no terminal"""
    cores = {
        "verde": "\033[92m",
        "vermelho": "\033[91m",
        "amarelo": "\033[93m",
        "azul": "\033[94m",
        "reset": "\033[0m"
    }
    return f"{cores.get(cor, '')}{texto}{cores['reset']}"

def enviar_alerta(moeda, payload, descricao=""):
    """Envia um alerta de catalisador para uma moeda"""
    url = f"{BASE_URL}/webhook/{moeda}"
    payload_completo = {
        "action": "buy",
        "moeda": moeda,
        "timeframe": "5m",  # Timeframe obrigatório
        **payload
    }
    
    try:
        resp = requests.post(url, json=payload_completo, timeout=10)
        return {
            "moeda": moeda,
            "status_code": resp.status_code,
            "descricao": descricao,
            "sucesso": resp.status_code == 200,
            "resposta": resp.text[:200] if resp.status_code != 200 else resp.json()
        }
    except Exception as e:
        return {
            "moeda": moeda,
            "status_code": 0,
            "descricao": descricao,
            "sucesso": False,
            "resposta": str(e)
        }

def verificar_diag():
    """Busca diagnóstico do bot"""
    try:
        resp = requests.get(f"{BASE_URL}/diag", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

def main():
    print("=" * 80)
    print(colorir("🧪 TESTE COMPLETO DAS 10 MOEDAS - BOT-SNIPER", "azul"))
    print("=" * 80)
    print()
    
    # 1. Verifica status do bot
    print(colorir("📊 ETAPA 1: Verificando status do bot...", "azul"))
    diag = verificar_diag()
    
    if not diag:
        print(colorir("❌ ERRO: Não conseguiu conectar ao bot!", "vermelho"))
        return
    
    ex = diag.get("execucao_real_bitget", {})
    print(f"   Bot ID: {diag.get('bot_id')}")
    print(f"   Executor ativo: {ex.get('ativa')}")
    print(f"   Dry-run: {ex.get('dry_run')}")
    print(f"   Moedas permitidas no executor: {ex.get('moedas', [])}")
    print()
    
    # 2. Teste rápido: uma moeda de cada vez
    print(colorir("🎯 ETAPA 2: Testando alerta GRADE A (todas devem processar)...", "azul"))
    print()
    
    resultados = []
    for moeda in MOEDAS:
        print(f"   Testando {moeda}...", end=" ", flush=True)
        resultado = enviar_alerta(moeda, PAYLOAD_GRADE_A, "Grade A + 1m FAVOR")
        resultados.append(resultado)
        
        if resultado["sucesso"]:
            print(colorir("✅ OK", "verde"))
        else:
            print(colorir(f"❌ FALHOU (HTTP {resultado['status_code']})", "vermelho"))
        
        time.sleep(0.5)  # Evita sobrecarga
    
    print()
    
    # 3. Teste específico: VIRTUAL (única no executor)
    print(colorir("🔍 ETAPA 3: Testes específicos em VIRTUAL (única moeda ativa no executor)...", "azul"))
    print()
    
    # 3a. Grade A + 1m FAVOR (deve entrar com 10x)
    print("   3a. Grade A + 1m FAVOR (deve simular entrada com 10x)...", end=" ", flush=True)
    r1 = enviar_alerta("VIRTUAL", PAYLOAD_GRADE_A, "Grade A + 1m FAVOR")
    if r1["sucesso"]:
        print(colorir("✅ PROCESSADO", "verde"))
    else:
        print(colorir(f"❌ ERRO HTTP {r1['status_code']}", "vermelho"))
    time.sleep(1)
    
    # 3b. Grade C + 1m FAVOR (deve entrar com 5x)
    print("   3b. Grade C + 1m FAVOR (deve simular entrada com 5x)...", end=" ", flush=True)
    r2 = enviar_alerta("VIRTUAL", PAYLOAD_GRADE_C_1M_FAVOR, "Grade C + 1m FAVOR")
    if r2["sucesso"]:
        print(colorir("✅ PROCESSADO", "verde"))
    else:
        print(colorir(f"❌ ERRO HTTP {r2['status_code']}", "vermelho"))
    time.sleep(1)
    
    # 3c. Grade C + 1m CONTRA (porteiro deve bloquear)
    print("   3c. Grade C + 1m CONTRA (porteiro deve BLOQUEAR)...", end=" ", flush=True)
    r3 = enviar_alerta("VIRTUAL", PAYLOAD_GRADE_C_1M_CONTRA, "Grade C + 1m CONTRA")
    if r3["sucesso"]:
        print(colorir("✅ PROCESSADO (bloqueio esperado nos logs)", "verde"))
    else:
        print(colorir(f"❌ ERRO HTTP {r3['status_code']}", "vermelho"))
    time.sleep(1)
    
    print()
    
    # 4. Teste de moeda NÃO configurada no executor (BTC)
    print(colorir("⚠️  ETAPA 4: Testando BTC (não está em moedas=['VIRTUAL'])...", "azul"))
    print("   Espera-se que o catalisador processe mas o executor bloqueie.")
    print()
    r_btc = enviar_alerta("BTC", PAYLOAD_GRADE_A, "Grade A mas moeda não permitida")
    if r_btc["sucesso"]:
        print(colorir("   ✅ Webhook processado (bloqueio do executor esperado nos logs)", "verde"))
    else:
        print(colorir(f"   ❌ ERRO HTTP {r_btc['status_code']}", "vermelho"))
    
    print()
    
    # 5. Aguarda processamento e busca logs recentes
    print(colorir("📋 ETAPA 5: Aguardando processamento (5s)...", "azul"))
    time.sleep(5)
    
    print()
    print(colorir("🔍 ETAPA 6: Verificando últimos eventos no /diag...", "azul"))
    diag_final = verificar_diag()
    
    if diag_final and "ultimos_eventos" in diag_final:
        eventos = diag_final["ultimos_eventos"][-10:]  # Últimos 10
        print()
        print("   Últimos eventos registrados:")
        for ev in eventos:
            ts = ev.get("timestamp", "")
            tipo = ev.get("tipo", "")
            moeda = ev.get("moeda", "")
            msg = ev.get("mensagem", "")
            print(f"   [{ts}] {tipo:15s} {moeda:8s} {msg[:60]}")
    
    print()
    print("=" * 80)
    print(colorir("📊 RESUMO DOS TESTES", "azul"))
    print("=" * 80)
    print()
    
    # Conta sucessos
    total = len(MOEDAS)
    sucessos = sum(1 for r in resultados if r["sucesso"])
    
    print(f"   Total de moedas testadas: {total}")
    print(f"   Webhooks processados com sucesso: {colorir(str(sucessos), 'verde')}/{total}")
    
    if sucessos == total:
        print()
        print(colorir("   ✅ TODOS OS ALERTAS FUNCIONANDO!", "verde"))
        print()
        print("   🎯 Próximos passos:")
        print("      1. Verifique os logs em /registro para ver as entradas simuladas")
        print("      2. Confirme que VIRTUAL está gerando [ENTRADA_REAL DRY-RUN]")
        print("      3. Confirme que outras moedas (BTC, ETH, etc.) estão sendo bloqueadas")
        print("         pelo executor (moeda não permitida)")
        print("      4. Quando quiser ativar outras moedas, adicione em config.json:")
        print("         'moedas': ['VIRTUAL', 'BTC', 'ETH', ...]")
    else:
        print()
        print(colorir("   ⚠️  ALGUNS ALERTAS FALHARAM:", "amarelo"))
        for r in resultados:
            if not r["sucesso"]:
                print(f"      - {r['moeda']}: HTTP {r['status_code']} - {r['resposta'][:100]}")
    
    print()
    print("=" * 80)
    print()
    print(colorir("🔗 Links úteis:", "azul"))
    print(f"   Status: {BASE_URL}/")
    print(f"   Diagnóstico: {BASE_URL}/diag")
    print(f"   Logs recentes: {BASE_URL}/registro")
    print(f"   Resumo: {BASE_URL}/resumo")
    print()

if __name__ == "__main__":
    main()
