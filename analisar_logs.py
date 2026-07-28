#!/usr/bin/env python3
"""
Script de Análise dos Logs do Bot Crypto Sombra
================================================

Analisa os dados coletados em crypto_logs/ para identificar:
- Melhor moeda, timeframe e alavancagem
- Performance por tipo de sinal TSTS (BS, BSC, BSX, SS, SSC, SSX)
- Qual cruzamento RSI tem melhor taxa de acerto (1º, 2º ou 3º)
- Otimização de TP/SL
- Horários com melhor performance
- Análise de trailing stop vs TP fixo

Uso:
    python3 analisar_logs.py --dias 30
    python3 analisar_logs.py --moeda BTC
    python3 analisar_logs.py --periodo 2026-07-01 2026-07-31
"""

import os
import json
import glob
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics

# Diretório dos logs
LOGS_DIR = os.path.expanduser("~/crypto_logs")


def carregar_logs(data_inicio=None, data_fim=None, moeda=None):
    """
    Carrega todos os arquivos JSON dos logs dentro do período especificado.
    
    Returns:
        list: Lista de eventos (dicts)
    """
    eventos = []
    
    # Encontrar todos os arquivos JSON
    arquivos = sorted(glob.glob(f"{LOGS_DIR}/crypto_*.json"))
    
    for arquivo in arquivos:
        # Extrair data do nome do arquivo: crypto_2026-07-20.json
        nome = os.path.basename(arquivo)
        try:
            data_str = nome.replace("crypto_", "").replace(".json", "")
            data_arquivo = datetime.strptime(data_str, "%Y-%m-%d").date()
            
            # Filtrar por período
            if data_inicio and data_arquivo < data_inicio:
                continue
            if data_fim and data_arquivo > data_fim:
                continue
            
            # Carregar eventos
            with open(arquivo, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for evento in data:
                    # Filtrar por moeda se especificado
                    if moeda and evento.get('moeda') != moeda:
                        continue
                    eventos.append(evento)
        
        except (ValueError, json.JSONDecodeError, KeyError) as e:
            print(f"⚠️  Erro ao processar {arquivo}: {e}")
            continue
    
    return eventos


def analisar_performance_geral(eventos):
    """
    Análise geral: win rate, profit médio, melhor combinação
    """
    print("\n" + "="*80)
    print("📊 ANÁLISE GERAL DE PERFORMANCE")
    print("="*80)
    
    # Filtrar apenas entradas simuladas (com resultado)
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        print("❌ Nenhum trade completo (entrada + saída) encontrado nos logs.")
        return
    
    total_trades = len(trades)
    wins = len([t for t in trades if t['resultado_simulado'] > 0])
    losses = len([t for t in trades if t['resultado_simulado'] <= 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    profit_total = sum(t['resultado_simulado'] for t in trades)
    profit_medio = profit_total / total_trades if total_trades > 0 else 0
    
    print(f"\n📈 Resumo:")
    print(f"  Total de trades: {total_trades}")
    print(f"  Wins: {wins} ({win_rate:.1f}%)")
    print(f"  Losses: {losses} ({100-win_rate:.1f}%)")
    print(f"  Profit total: ${profit_total:.2f} USDT")
    print(f"  Profit médio por trade: ${profit_medio:.2f} USDT")
    
    # Melhor e pior trade
    if trades:
        melhor = max(trades, key=lambda t: t['resultado_simulado'])
        pior = min(trades, key=lambda t: t['resultado_simulado'])
        print(f"\n🏆 Melhor trade: {melhor['moeda']} {melhor['timeframe']} → +${melhor['resultado_simulado']:.2f}")
        print(f"💀 Pior trade: {pior['moeda']} {pior['timeframe']} → ${pior['resultado_simulado']:.2f}")


def analisar_por_moeda(eventos):
    """
    Performance por moeda (BTC, ETH, SOL, etc)
    """
    print("\n" + "="*80)
    print("🪙 PERFORMANCE POR MOEDA")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    # Agrupar por moeda
    por_moeda = defaultdict(list)
    for t in trades:
        por_moeda[t['moeda']].append(t['resultado_simulado'])
    
    # Calcular métricas
    resultados = []
    for moeda, results in por_moeda.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((moeda, total, win_rate, profit))
    
    # Ordenar por profit
    resultados.sort(key=lambda x: x[3], reverse=True)
    
    print(f"\n{'Moeda':<10} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 50)
    for moeda, total, wr, profit in resultados:
        print(f"{moeda:<10} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")


def analisar_por_timeframe(eventos):
    """
    Performance por timeframe (1m, 5m, 15m)
    """
    print("\n" + "="*80)
    print("⏱️  PERFORMANCE POR TIMEFRAME")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    por_tf = defaultdict(list)
    for t in trades:
        por_tf[t['timeframe']].append(t['resultado_simulado'])
    
    resultados = []
    for tf, results in por_tf.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((tf, total, win_rate, profit))
    
    resultados.sort(key=lambda x: x[3], reverse=True)
    
    print(f"\n{'Timeframe':<12} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 50)
    for tf, total, wr, profit in resultados:
        print(f"{tf:<12} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")


def analisar_por_alavancagem(eventos):
    """
    Performance por alavancagem (5x vs 10x)
    """
    print("\n" + "="*80)
    print("📈 PERFORMANCE POR ALAVANCAGEM")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    por_alav = defaultdict(list)
    for t in trades:
        alav = t.get('alavancagem')
        if alav:
            por_alav[f"{alav}x"].append(t['resultado_simulado'])
    
    resultados = []
    for alav, results in por_alav.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        profit_medio = profit / total if total > 0 else 0
        resultados.append((alav, total, win_rate, profit, profit_medio))
    
    resultados.sort(key=lambda x: x[3], reverse=True)
    
    print(f"\n{'Alavancagem':<12} {'Trades':<10} {'Win Rate':<12} {'Profit Total':<15} {'Profit Médio':<15}")
    print("-" * 75)
    for alav, total, wr, profit, pm in resultados:
        print(f"{alav:<12} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT {pm:>+10.2f} USDT")


def analisar_tipo_sinal_tsts(eventos):
    """
    Performance por tipo de sinal TSTS: BS, BSC, BSX, SS, SSC, SSX
    """
    print("\n" + "="*80)
    print("🎯 PERFORMANCE POR TIPO DE SINAL TSTS")
    print("="*80)
    
    # Precisamos correlacionar SINAL com ENTRADA
    # Cada entrada tem o sinal_tsts associado
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    # Extrair tipo de sinal (BS, BSC, BSX, SS, SSC, SSX) do campo sinal_tsts
    # sinal_tsts vem como "BUY" ou "SELL", mas o tipo exato (BS, BSC, etc) está no _raw_content do webhook
    # Como não temos isso direto no log, vamos agrupar por direcao (BUY/SELL)
    
    por_sinal = defaultdict(list)
    for t in trades:
        sinal = t.get('sinal_tsts', 'UNKNOWN')
        por_sinal[sinal].append(t['resultado_simulado'])
    
    resultados = []
    for sinal, results in por_sinal.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((sinal, total, win_rate, profit))
    
    resultados.sort(key=lambda x: x[3], reverse=True)
    
    print(f"\n{'Tipo':<10} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 50)
    for sinal, total, wr, profit in resultados:
        print(f"{sinal:<10} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")
    
    print("\n⚠️  Nota: Para análise detalhada de BS/BSC/BSX/SS/SSC/SSX, adicione")
    print("   o campo 'signal_type' no log de entrada (já capturado no webhook).")


def analisar_cruzamentos_rsi(eventos):
    """
    Performance por número de cruzamento RSI (1º, 2º, 3º)
    """
    print("\n" + "="*80)
    print("🔄 PERFORMANCE POR CRUZAMENTO RSI")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    por_cruz = defaultdict(list)
    for t in trades:
        cruz_num = t.get('cruzamento_numero')
        if cruz_num:
            por_cruz[f"{cruz_num}º cruzamento"].append(t['resultado_simulado'])
    
    resultados = []
    for cruz, results in por_cruz.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((cruz, total, win_rate, profit))
    
    # Ordenar por número de cruzamento
    ordem = {"1º cruzamento": 1, "2º cruzamento": 2, "3º cruzamento": 3}
    resultados.sort(key=lambda x: ordem.get(x[0], 99))
    
    print(f"\n{'Cruzamento':<18} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 60)
    for cruz, total, wr, profit in resultados:
        print(f"{cruz:<18} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")
    
    print("\n💡 Insight: Se o 2º ou 3º cruzamento tiver win rate maior, considere")
    print("   ajustar o motor para entrar só no 2º/3º (config: analise_ativa).")


def analisar_horarios(eventos):
    """
    Performance por hora do dia (UTC)
    """
    print("\n" + "="*80)
    print("🕐 PERFORMANCE POR HORÁRIO (UTC)")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    por_hora = defaultdict(list)
    for t in trades:
        timestamp = t.get('timestamp')
        if timestamp:
            try:
                # timestamp vem como "2026-07-20T02:37:27.495285+00:00"
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hora = dt.hour
                por_hora[hora].append(t['resultado_simulado'])
            except:
                continue
    
    resultados = []
    for hora, results in sorted(por_hora.items()):
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((hora, total, win_rate, profit))
    
    if not resultados:
        print("\n❌ Dados de timestamp insuficientes.")
        return
    
    print(f"\n{'Hora (UTC)':<12} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 55)
    for hora, total, wr, profit in resultados:
        print(f"{hora:02d}:00{'':<6} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")


def analisar_melhor_combinacao(eventos):
    """
    Encontra a melhor combinação: MOEDA + TIMEFRAME + ALAVANCAGEM
    """
    print("\n" + "="*80)
    print("🏆 TOP 10 MELHORES COMBINAÇÕES")
    print("="*80)
    
    trades = [e for e in eventos if e.get('evento') == 'ENTRADA' and e.get('resultado_simulado') is not None]
    
    if not trades:
        return
    
    por_combo = defaultdict(list)
    for t in trades:
        combo = f"{t['moeda']} {t['timeframe']} {t.get('alavancagem', '?')}x"
        por_combo[combo].append(t['resultado_simulado'])
    
    resultados = []
    for combo, results in por_combo.items():
        total = len(results)
        wins = len([r for r in results if r > 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        profit = sum(results)
        resultados.append((combo, total, win_rate, profit))
    
    # Top 10 por profit
    resultados.sort(key=lambda x: x[3], reverse=True)
    top10 = resultados[:10]
    
    print(f"\n{'Combinação':<20} {'Trades':<10} {'Win Rate':<12} {'Profit':<15}")
    print("-" * 65)
    for combo, total, wr, profit in top10:
        print(f"{combo:<20} {total:<10} {wr:>5.1f}% {profit:>+10.2f} USDT")


def gerar_relatorio_completo(data_inicio=None, data_fim=None, moeda=None):
    """
    Gera o relatório completo de análise
    """
    print("\n" + "="*80)
    print("🤖 ANÁLISE DOS LOGS - BOT CRYPTO SOMBRA")
    print("="*80)
    
    # Período
    if data_inicio and data_fim:
        print(f"📅 Período: {data_inicio} até {data_fim}")
    elif moeda:
        print(f"🪙 Moeda filtrada: {moeda}")
    else:
        print(f"📅 Período: Todos os logs disponíveis")
    
    # Carregar eventos
    print("\n🔄 Carregando logs...")
    eventos = carregar_logs(data_inicio, data_fim, moeda)
    
    if not eventos:
        print("❌ Nenhum evento encontrado nos logs.")
        return
    
    print(f"✅ {len(eventos)} eventos carregados.")
    
    # Executar análises
    analisar_performance_geral(eventos)
    analisar_por_moeda(eventos)
    analisar_por_timeframe(eventos)
    analisar_por_alavancagem(eventos)
    analisar_tipo_sinal_tsts(eventos)
    analisar_cruzamentos_rsi(eventos)
    analisar_horarios(eventos)
    analisar_melhor_combinacao(eventos)
    
    print("\n" + "="*80)
    print("✅ ANÁLISE CONCLUÍDA")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Analisa os logs do Bot Crypto Sombra',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python3 analisar_logs.py --dias 30
  python3 analisar_logs.py --moeda BTC
  python3 analisar_logs.py --periodo 2026-07-01 2026-07-31
        """
    )
    
    parser.add_argument('--dias', type=int, help='Analisar últimos N dias')
    parser.add_argument('--moeda', type=str, help='Filtrar por moeda (BTC, ETH, etc)')
    parser.add_argument('--periodo', nargs=2, metavar=('INICIO', 'FIM'), 
                       help='Período específico (AAAA-MM-DD AAAA-MM-DD)')
    
    args = parser.parse_args()
    
    # Processar argumentos
    data_inicio = None
    data_fim = None
    
    if args.dias:
        data_fim = datetime.now().date()
        data_inicio = data_fim - timedelta(days=args.dias)
    
    if args.periodo:
        try:
            data_inicio = datetime.strptime(args.periodo[0], "%Y-%m-%d").date()
            data_fim = datetime.strptime(args.periodo[1], "%Y-%m-%d").date()
        except ValueError:
            print("❌ Formato de data inválido. Use AAAA-MM-DD")
            return
    
    # Gerar relatório
    gerar_relatorio_completo(data_inicio, data_fim, args.moeda)


if __name__ == "__main__":
    main()
