"""
Teste local: simula o resumo diário do Telegram.
"""
import sys
sys.path.insert(0, "/home/ubuntu/bot_tsts_sniper")

from resumo_diario import gerar_resumo

# Teste com dados de 2026-08-08
resumo_md = gerar_resumo(data="2026-08-08", output="texto")
print(resumo_md)
print("\n" + "="*60)
print("✅ Resumo gerado com sucesso!")
