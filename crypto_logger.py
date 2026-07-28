# -*- coding: utf-8 -*-
"""
crypto_logger.py
================
Registro PERMANENTE (modo sombra) das decisões do bot de cripto multi-ativo.

Grava CADA evento importante em DOIS formatos, um arquivo por dia:
  - crypto2_logs/crypto_AAAA-MM-DD.json   -> lista JSON (para backtest/máquina)
  - crypto2_logs/crypto_AAAA-MM-DD.md     -> tabela Markdown (para leitura humana)

Campos de cada registro (conforme especificação):
  timestamp, moeda, timeframe, alavancagem, sinal_tsts, rsi_valor,
  cruzamento_numero, decisao_agente, preco_entrada_simulado, resultado_simulado
  (+ campos extras úteis: evento, direcao, motivo, preco_saida_simulado, pnl_pct)

IMPORTANTE (limitação honesta): o disco do Railway é EFÊMERO — ele é apagado a
cada redeploy/reinício. Por isso o resumo diário vai para o Telegram (durável).
Para histórico 100% garantido, baixe os arquivos crypto2_logs/ periodicamente ou
plugue um Google Sheets/banco depois.

Todos os comentários e mensagens em Português.
"""

import os
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("crypto_logger")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "crypto2_logs")
os.makedirs(LOG_DIR, exist_ok=True)

_lock = threading.Lock()

# Campos na ordem em que aparecem na tabela Markdown
_COLUNAS = [
    "hora", "evento", "moeda", "timeframe", "alavancagem", "sinal_tsts",
    "rsi_valor", "cruzamento_numero", "decisao_agente",
    "preco_entrada_simulado", "preco_saida_simulado", "resultado_simulado",
]

_CABECALHO_MD = (
    "# 🕶️ Registro Modo Sombra — Bot Crypto Multi-Ativo\n\n"
    "> Cada linha é uma decisão/evento registrado pelo bot em MODO SOMBRA "
    "(nenhuma ordem real foi enviada à Bitget).\n\n"
    "| Hora (UTC) | Evento | Moeda | TF | Alav. | Sinal TSTS | RSI | Cruz. | "
    "Decisão | Entrada sim. | Saída sim. | Resultado sim. |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


def _arquivo_json(dt: datetime) -> str:
    return os.path.join(LOG_DIR, f"crypto_{dt.strftime('%Y-%m-%d')}.json")


def _arquivo_md(dt: datetime) -> str:
    return os.path.join(LOG_DIR, f"crypto_{dt.strftime('%Y-%m-%d')}.md")


def _fmt(v, casas=4):
    if v is None:
        return "-"
    try:
        return f"{float(v):.{casas}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _resultado_str(reg: Dict[str, Any]) -> str:
    """Formata o campo resultado_simulado para a tabela Markdown."""
    r = reg.get("resultado_simulado")
    if r is None:
        return "aberto" if reg.get("evento") == "ENTRADA" else "-"
    if isinstance(r, dict):
        pnl_pct = r.get("pnl_pct")
        motivo = r.get("motivo", "")
        pnls = []
        for k, v in r.items():
            if k.startswith("pnl_usdt_"):
                pnls.append(f"{k.replace('pnl_usdt_', '')}=${_fmt(v, 2)}")
        base = f"{_fmt(pnl_pct, 3)}%" if pnl_pct is not None else ""
        extra = (" " + " ".join(pnls)) if pnls else ""
        tag = f" ({motivo})" if motivo else ""
        # Excursões p/ estudo de TP/SL (MFE = correu a favor; DD = correu contra)
        exc = ""
        if r.get("mfe_pct") is not None or r.get("dd_pct") is not None:
            exc = f" [MFE={_fmt(r.get('mfe_pct'), 2)}% DD={_fmt(r.get('dd_pct'), 2)}%]"
        return (base + extra + exc + tag).strip() or str(r)
    return str(r)


def _linha_md(reg: Dict[str, Any]) -> str:
    resultado = _resultado_str(reg)
    return (
        f"| {reg.get('hora', '-')} "
        f"| {reg.get('evento', '-')} "
        f"| {reg.get('moeda', '-')} "
        f"| {reg.get('timeframe', '-')} "
        f"| {reg.get('alavancagem', '-') or '-'} "
        f"| {reg.get('sinal_tsts', '-') or '-'} "
        f"| {_fmt(reg.get('rsi_valor'), 1)} "
        f"| {reg.get('cruzamento_numero', '-') or '-'} "
        f"| {reg.get('decisao_agente', '-') or '-'} "
        f"| {_fmt(reg.get('preco_entrada_simulado'))} "
        f"| {_fmt(reg.get('preco_saida_simulado'))} "
        f"| {resultado} |\n"
    )


def registrar(evento: str, dados: Dict[str, Any]) -> Dict[str, Any]:
    """
    Grava UM evento nos arquivos JSON e Markdown do dia.

    `evento`: rótulo curto (ex.: "SINAL", "RSI_CROSS", "ENTRADA", "AGUARDAR",
              "ANALISE", "SAIDA", "BLOQUEADO").
    `dados`:  dicionário com os campos da especificação (moeda, timeframe, ...).

    Retorna o registro completo (com timestamp), para uso pelo servidor.
    """
    agora = datetime.now(timezone.utc)
    reg: Dict[str, Any] = {
        "timestamp": agora.isoformat(),
        "data": agora.strftime("%Y-%m-%d"),
        "hora": agora.strftime("%H:%M:%S"),
        "evento": evento,
    }
    # Preenche campos padrão da especificação (garante que sempre existam)
    for campo in ("moeda", "timeframe", "alavancagem", "sinal_tsts", "rsi_valor",
                  "cruzamento_numero", "decisao_agente", "preco_entrada_simulado",
                  "preco_saida_simulado", "resultado_simulado", "direcao", "motivo"):
        reg.setdefault(campo, dados.get(campo))
    # Copia quaisquer campos extras
    for k, v in dados.items():
        if k not in reg:
            reg[k] = v

    caminho_json = _arquivo_json(agora)
    caminho_md = _arquivo_md(agora)
    try:
        with _lock:
            # --- JSON (lista) ---
            registros: List[Dict[str, Any]] = []
            if os.path.exists(caminho_json):
                try:
                    with open(caminho_json, "r", encoding="utf-8") as f:
                        registros = json.load(f) or []
                except (ValueError, OSError):
                    registros = []
            registros.append(reg)
            with open(caminho_json, "w", encoding="utf-8") as f:
                json.dump(registros, f, ensure_ascii=False, indent=2)

            # --- Markdown (append de linha; cria cabeçalho se novo) ---
            novo = not os.path.exists(caminho_md)
            with open(caminho_md, "a", encoding="utf-8") as f:
                if novo:
                    f.write(_CABECALHO_MD)
                f.write(_linha_md(reg))
    except OSError as exc:
        logger.error("Falha ao gravar registro de sombra: %s", exc)
    return reg


def ler_dia(dia: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lê os registros de um dia (AAAA-MM-DD). Sem argumento = hoje (UTC)."""
    if dia is None:
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    caminho = os.path.join(LOG_DIR, f"crypto_{dia}.json")
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f) or []
    except (ValueError, OSError):
        return []


def dias_disponiveis() -> List[str]:
    """Lista os dias com arquivo de registro (mais recente primeiro)."""
    dias = []
    try:
        for nome in os.listdir(LOG_DIR):
            if nome.startswith("crypto_") and nome.endswith(".json"):
                dias.append(nome[len("crypto_"):-len(".json")])
    except OSError:
        pass
    return sorted(dias, reverse=True)


def limpar_dia(dia: Optional[str] = None) -> Dict[str, Any]:
    """
    Deleta os arquivos de log de um dia específico (JSON e Markdown).
    Se dia=None, usa hoje (UTC).
    
    Retorna dict com status da operação:
        {"ok": True, "dia": "2026-07-20", "arquivos_deletados": ["crypto_2026-07-20.json", ...]}
    """
    if not dia:
        dia = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    arquivos_deletados = []
    erros = []
    
    for ext in (".json", ".md"):
        caminho = os.path.join(LOG_DIR, f"crypto_{dia}{ext}")
        if os.path.exists(caminho):
            try:
                os.remove(caminho)
                arquivos_deletados.append(os.path.basename(caminho))
                logger.info("Arquivo de log deletado: %s", caminho)
            except OSError as e:
                erros.append(f"{os.path.basename(caminho)}: {e}")
                logger.error("Erro ao deletar %s: %s", caminho, e)
    
    return {
        "ok": len(erros) == 0,
        "dia": dia,
        "arquivos_deletados": arquivos_deletados,
        "erros": erros,
    }
