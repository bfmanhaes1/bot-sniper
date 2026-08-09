"""
Resumo Diário do BOT-SNIPER
===========================
Processa logs shadow + posições reais e gera relatório diário:
- Total de ordens (real + shadow)
- Breakdown por timeframe
- Win rate (%)
- P&L total
- Losses e gains

Backend de dados:
- PRIMÁRIO: PostgreSQL (tabela estudo_tpsl via DATABASE_URL) — dados persistem.
- FALLBACK: Arquivos JSON locais (crypto2_logs/) — efêmeros no Railway.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# ------------------------------------------------------------------ #
# Paths e imports
# ------------------------------------------------------------------ #
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "crypto2_logs"
POSICOES_FILE = BASE_DIR / "execucao_real_posicoes.json"

# Tenta importar crypto_logger (para acesso ao PostgreSQL)
try:
    import sys
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    import crypto_logger
    HAS_CRYPTO_LOGGER = True
except ImportError:
    HAS_CRYPTO_LOGGER = False
    crypto_logger = None


def ler_logs_dia(data: str = None) -> List[Dict[str, Any]]:
    """Lê eventos do dia (PostgreSQL primário, arquivos JSON fallback).
    
    Args:
        data: YYYY-MM-DD. Se None, usa hoje (UTC).
    
    Returns:
        Lista de eventos (ENTRADA, SAIDA, etc).
    
    Backend:
        Usa crypto_logger.ler_dia() que automaticamente:
        1. Tenta PostgreSQL (tabela crypto_eventos) — dados permanentes
        2. Fallback para arquivos JSON se PostgreSQL indisponível
    """
    if data is None:
        data = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Usa crypto_logger se disponível (lê de PostgreSQL + fallback JSON)
    if HAS_CRYPTO_LOGGER and crypto_logger:
        try:
            return crypto_logger.ler_dia(data)
        except Exception as e:
            print(f"Erro ao ler via crypto_logger: {e}")
    
    # Fallback manual se crypto_logger não disponível
    log_file = LOGS_DIR / f"crypto_{data}.json"
    if not log_file.exists():
        return []
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            eventos = json.load(f)
        return eventos if isinstance(eventos, list) else []
    except Exception as e:
        print(f"Erro ao ler {log_file}: {e}")
        return []


def ler_posicoes_reais() -> Dict[str, Any]:
    """Lê posições reais abertas."""
    if not POSICOES_FILE.exists():
        return {}
    try:
        with open(POSICOES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao ler {POSICOES_FILE}: {e}")
        return {}


def calcular_metricas(eventos: List[Dict], posicoes_abertas: Dict) -> Dict[str, Any]:
    """Calcula métricas diárias a partir dos eventos.
    
    Métricas:
    - total_ordens: entradas simuladas + reais (aberturas)
    - por_tf: breakdown por timeframe
    - fechadas: ordens que tiveram SAIDA (TP/SL/reversão)
    - winners/losers: fechadas com lucro/perda
    - win_rate: % de winners
    - pnl_total: soma de todos os P&L das fechadas
    - maior_gain/maior_loss: extremos
    """
    entradas = [e for e in eventos if e.get("evento") == "ENTRADA"]
    saidas = [e for e in eventos if e.get("evento") == "SAIDA"]
    
    # Total de ordens abertas hoje (shadow)
    total_ordens = len(entradas)
    
    # Breakdown por TF
    por_tf = defaultdict(int)
    for e in entradas:
        tf = e.get("timeframe", "?")
        por_tf[tf] += 1
    
    # Analisar saídas (fechadas)
    fechadas = len(saidas)
    winners = 0
    losers = 0
    pnl_total = 0.0
    gains = []
    losses = []
    
    for s in saidas:
        resultado = s.get("resultado_simulado", "NEUTRO")
        # Alguns eventos têm pnl_percent ou calculado
        pnl = s.get("pnl_percent", 0.0)
        
        # Se não tiver pnl_percent, tenta calcular (se tiver entry/exit)
        if pnl == 0.0:
            entry = s.get("preco_entrada_simulado")
            exit_price = s.get("preco_saida_simulado")
            direcao = s.get("direcao", "buy")
            if entry and exit_price:
                if direcao.lower() == "buy":
                    pnl = ((exit_price - entry) / entry) * 100
                else:
                    pnl = ((entry - exit_price) / entry) * 100
        
        if resultado == "WIN" or pnl > 0:
            winners += 1
            gains.append(pnl)
        elif resultado == "LOSS" or pnl < 0:
            losers += 1
            losses.append(pnl)
        
        pnl_total += pnl
    
    win_rate = (winners / fechadas * 100) if fechadas > 0 else 0.0
    maior_gain = max(gains) if gains else 0.0
    maior_loss = min(losses) if losses else 0.0
    
    # Posições reais abertas agora (não fechadas)
    reais_abertas = len(posicoes_abertas)
    
    return {
        "total_ordens": total_ordens,
        "por_tf": dict(por_tf),
        "fechadas": fechadas,
        "abertas": total_ordens - fechadas,  # aproximação (shadow)
        "reais_abertas": reais_abertas,
        "winners": winners,
        "losers": losers,
        "win_rate_pct": round(win_rate, 1),
        "pnl_total_pct": round(pnl_total, 2),
        "maior_gain_pct": round(maior_gain, 2),
        "maior_loss_pct": round(maior_loss, 2),
    }


def gerar_resumo_texto(metricas: Dict, data: str) -> str:
    """Gera resumo em texto formatado (Markdown)."""
    linhas = [
        f"# 📊 Resumo Diário BOT-SNIPER — {data}",
        "",
        "## Ordens",
        f"- **Total de ordens**: {metricas['total_ordens']}",
        f"- **Fechadas**: {metricas['fechadas']} (TP/SL)",
        f"- **Abertas (shadow)**: {metricas['abertas']}",
        f"- **Reais abertas**: {metricas['reais_abertas']}",
        "",
        "## Por Timeframe",
    ]
    
    for tf, count in sorted(metricas["por_tf"].items()):
        linhas.append(f"- **{tf}**: {count} ordens")
    
    linhas.extend([
        "",
        "## Performance (Shadow)",
        f"- **Winners**: {metricas['winners']} 🟢",
        f"- **Losers**: {metricas['losers']} 🔴",
        f"- **Win Rate**: {metricas['win_rate_pct']}%",
        "",
        "## P&L (Shadow, %)",
        f"- **Total**: {metricas['pnl_total_pct']:+.2f}%",
        f"- **Maior Gain**: {metricas['maior_gain_pct']:+.2f}%",
        f"- **Maior Loss**: {metricas['maior_loss_pct']:+.2f}%",
        "",
        "---",
        f"*Gerado em {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC*",
    ])
    
    return "\n".join(linhas)


def gerar_resumo(data: str = None, output: str = "texto") -> Any:
    """Gera resumo diário.
    
    Args:
        data: YYYY-MM-DD. None = hoje.
        output: "texto" (markdown) | "json" (dict)
    
    Returns:
        str (markdown) ou dict (JSON).
    """
    if data is None:
        data = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    eventos = ler_logs_dia(data)
    posicoes = ler_posicoes_reais()
    metricas = calcular_metricas(eventos, posicoes)
    
    if output == "json":
        return {"data": data, "metricas": metricas}
    else:
        return gerar_resumo_texto(metricas, data)


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    import sys
    
    data_arg = sys.argv[1] if len(sys.argv) > 1 else None
    output_arg = sys.argv[2] if len(sys.argv) > 2 else "texto"
    
    resumo = gerar_resumo(data=data_arg, output=output_arg)
    
    if output_arg == "json":
        print(json.dumps(resumo, indent=2, ensure_ascii=False))
    else:
        print(resumo)
