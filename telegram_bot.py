# -*- coding: utf-8 -*-
"""
telegram_bot.py
===============
Envio de notificações para o Telegram (todas as mensagens em Português).

Carrega o token do bot a partir de:
  1. Variável de ambiente TELEGRAM_BOT_TOKEN
  2. Arquivo de secrets: ~/.config/abacusai_auth_secrets.json (telegram.secrets.bot_token)

O chat_id vem do config.json (telegram.chat_id).
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import requests

logger = logging.getLogger("telegram_bot")

DEFAULT_SECRETS_PATH = os.path.expanduser("~/.config/abacusai_auth_secrets.json")

# Nomes de meses abreviados em Português para as mensagens
_MESES_PT = [
    "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]


def _agora_utc_str() -> str:
    """Retorna a data/hora atual UTC no formato '03/Jul 14:35 UTC'."""
    now = datetime.now(timezone.utc)
    return f"{now.day:02d}/{_MESES_PT[now.month - 1]} {now.hour:02d}:{now.minute:02d} UTC"


def load_telegram_token(secrets_path: str = DEFAULT_SECRETS_PATH) -> Optional[str]:
    """Carrega o token do bot do Telegram (env tem prioridade sobre secrets)."""
    env_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if env_token:
        return env_token
    if not os.path.exists(secrets_path):
        logger.warning("Arquivo de secrets não encontrado para Telegram.")
        return None
    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["telegram"]["secrets"]["bot_token"]["value"]
    except (KeyError, TypeError, ValueError, OSError) as exc:
        logger.warning("Falha ao carregar token do Telegram: %s", exc)
        return None


class TelegramNotifier:
    """Wrapper simples sobre a Bot API do Telegram."""

    def __init__(self, chat_id: int, token: Optional[str] = None, timeout: int = 10,
                 bot_label: str = ""):
        self.token = token or load_telegram_token()
        self.chat_id = chat_id
        self.timeout = timeout
        # Rótulo do bot (ex.: "🎯 Bot Walk-Forward") — aparece no topo das
        # mensagens para diferenciar qual bot executou o trade.
        self.bot_label = bot_label
        if not self.token:
            logger.warning(
                "Token do Telegram ausente — notificações serão apenas logadas."
            )

    def send(self, text: str) -> bool:
        """Envia uma mensagem de texto. Retorna True em caso de sucesso."""
        if not self.token:
            logger.info("[TELEGRAM-OFFLINE] %s", text)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.error("Falha ao enviar mensagem Telegram: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Formatação das mensagens
    # ------------------------------------------------------------------ #
    def notify_approved(
        self,
        asset: str,
        analysis: Dict[str, Any],
        execution: Dict[str, Any],
    ) -> bool:
        """Monta e envia a mensagem de trade APROVADO."""
        action = analysis.get("action", "buy")
        lado = "LONG" if action == "buy" else "SHORT"
        emoji = "🟢" if action == "buy" else "🔴"

        tech = analysis.get("technical", {})
        align = tech.get("alignment", {})
        rsis = tech.get("rsis", {})
        cipher = tech.get("cipher", {})
        vol = tech.get("volume", {})
        macro = analysis.get("macro", {})
        news = analysis.get("news", {})

        # Linha de timeframes
        tfs = list(rsis.keys())
        align_txt = "✅ ALINHADOS" if align.get("aligned") else "⚠️ PARCIAL"
        rsi_line = " | ".join(
            f"{tf}: {int(v)}" if v is not None else f"{tf}: n/d"
            for tf, v in rsis.items()
        )

        wt1 = cipher.get("wt1")
        wt2 = cipher.get("wt2")
        if wt1 is not None and wt2 is not None:
            cipher_txt = "Bullish (WT1 > WT2)" if wt1 > wt2 else "Bearish (WT1 < WT2)"
        else:
            cipher_txt = "n/d"

        vol_ratio = "n/d"
        if vol.get("value") and vol.get("avg"):
            vol_ratio = f"{vol['value'] / vol['avg']:.1f}x média"

        fg = macro.get("fear_greed")
        fg_txt = f"{fg}" if fg is not None else "n/d"
        dom = macro.get("btc_dominance")
        dom_txt = f"{dom:.1f}%" if dom is not None else "n/d"

        msg = (
            f"{emoji} <b>{asset} AUTO-TRADE - {lado}</b>\n\n"
            f"📊 <b>ANÁLISE APROVADA</b>\n"
            f"Score: {analysis['score']}/100 (Threshold: {analysis['threshold']})\n\n"
            f"📈 <b>TÉCNICA:</b>\n"
            f"- Timeframes: {' + '.join(tfs)} {align_txt}\n"
            f"- RSI {rsi_line}\n"
            f"- Cipher: {cipher_txt}\n"
            f"- Volume: {vol_ratio}\n\n"
            f"🌍 <b>MACRO:</b>\n"
            f"- Fear & Greed: {fg_txt}\n"
            f"- BTC Dominance: {dom_txt}\n"
            f"- News: {news.get('positive', 0)} positivas, {news.get('negative', 0)} negativas\n\n"
            f"💰 <b>EXECUÇÃO:</b>\n"
            f"- Entrada: {execution.get('entry_str', 'n/d')}\n"
            f"- Posição: {execution.get('position_str', 'n/d')}\n"
            f"- TP: {execution.get('tp_str', 'n/d')}\n"
            f"- SL: {execution.get('sl_str', 'n/d')}\n"
            f"- Risco: {execution.get('risk_str', 'n/d')}\n"
        )
        if execution.get("mode"):
            msg += f"- Modo: {execution['mode']}\n"
        if execution.get("order_id"):
            msg += f"- Ordem: <code>{execution['order_id']}</code>\n"
        msg += f"\n⏰ {_agora_utc_str()}"
        return self.send(msg)

    def notify_rejected(self, asset: str, analysis: Dict[str, Any]) -> bool:
        """Monta e envia a mensagem de sinal REJEITADO."""
        # Seleciona os motivos mais relevantes (que indicam falha/penalidade)
        reasons = analysis.get("reasons", [])
        motivos = [
            r for r in reasons
            if any(k in r.lower() for k in
                   ["desalinh", "sem dados", "abaixo", "n/d", "-5", "ganância",
                    "indispon", "neutro", "sem base", "inválida"])
        ]
        if not motivos:
            motivos = reasons[:3]

        motivos_txt = "\n".join(f"- {m}" for m in motivos[:6])
        msg = (
            f"❌ <b>{asset} SINAL REJEITADO</b>\n\n"
            f"Score: {analysis['score']}/100 (Threshold: {analysis['threshold']})\n\n"
            f"❌ <b>MOTIVOS:</b>\n"
            f"{motivos_txt}\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)

    def notify_procrypto(self, asset: str, execution: Dict[str, Any]) -> bool:
        """Notificação de trade ProCrypto executado (SL/TP dinâmico + 3 saídas)."""
        action = execution.get("action", "buy")
        lado = "LONG" if action == "buy" else "SHORT"
        emoji = "🟢" if action == "buy" else "🔴"
        cabecalho = f"{self.bot_label}\n" if self.bot_label else ""
        msg = (
            f"{cabecalho}"
            f"{emoji} <b>{asset} PROCRYPTO - {lado}</b>\n\n"
            f"⚡ <b>SINAL EXECUTADO</b> (fonte: ProCrypto Scalper)\n"
            f"- Timeframe: {execution.get('tf', 'n/d')}\n\n"
            f"💰 <b>EXECUÇÃO:</b>\n"
            f"- Entrada: {execution.get('entry_str', 'n/d')}\n"
            f"- Posição: {execution.get('position_str', 'n/d')}\n"
            f"- SL: {execution.get('sl_str', 'n/d')}\n"
            f"- TP1 ({execution.get('split1_str','')}): {execution.get('tp1_str', 'n/d')}\n"
            f"- TP2 ({execution.get('split2_str','')}): {execution.get('tp2_str', 'n/d')}\n"
            f"- TP3 ({execution.get('split3_str','')}): {execution.get('tp3_str', 'n/d')}\n"
            f"- Risco: {execution.get('risk_str', 'n/d')}\n"
        )
        if execution.get("mode"):
            msg += f"- Modo: {execution['mode']}\n"
        if execution.get("order_id"):
            msg += f"- Ordem: <code>{execution['order_id']}</code>\n"
        msg += f"\n⏰ {_agora_utc_str()}"
        return self.send(msg)

    def notify_break_even(self, asset: str, entry_str: str) -> bool:
        """Notifica que o SL foi movido para break-even após o TP1."""
        cabecalho = f"{self.bot_label}\n" if self.bot_label else ""
        msg = (
            f"{cabecalho}"
            f"🔒 <b>{asset} BREAK-EVEN</b>\n\n"
            f"TP1 atingido — Stop Loss movido para a entrada ({entry_str}).\n"
            f"Trade agora sem risco. ✅\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)

    def notify_error(self, asset: str, erro: str) -> bool:
        """Envia notificação de erro de execução."""
        cabecalho = f"{self.bot_label}\n" if self.bot_label else ""
        msg = (
            f"{cabecalho}"
            f"⚠️ <b>{asset} ERRO DE EXECUÇÃO</b>\n\n"
            f"{erro}\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)

    def notify_circuit_breaker(self, asset: str, losses: int, cooldown_min: int) -> bool:
        """Notifica que o circuit breaker foi acionado."""
        msg = (
            f"🛑 <b>{asset} CIRCUIT BREAKER ATIVADO</b>\n\n"
            f"{losses} perdas consecutivas detectadas.\n"
            f"Trading pausado por {cooldown_min} minutos.\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)

    def notify_shadow_startup(self, combinacoes: int, moedas: int,
                              timeframes: int, alavancagens: int) -> bool:
        """Notifica que o bot iniciou em MODO SOMBRA (multi-ativo)."""
        nome = self.bot_label or "Bot Crypto Sombra"
        msg = (
            f"🕶️ <b>{nome} conectado (MODO SOMBRA)</b>\n\n"
            f"Coletando dados — <b>NENHUMA ordem real será enviada</b>.\n\n"
            f"• Combinações monitoradas: <b>{combinacoes}</b>\n"
            f"• Moedas: {moedas} | Timeframes: {timeframes} | Alavancagens: {alavancagens}\n"
            f"• Estratégia: TSTS Sniper + confirmação RSI\n"
            f"• Notificação: apenas 1 resumo por dia (23:59 UTC)\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)

    def notify_daily_summary(self, texto_html: str) -> bool:
        """Envia o resumo diário do modo sombra (texto já formatado em HTML)."""
        return self.send(texto_html)

    def notify_startup(self, num_bots: int, dry_run: bool) -> bool:
        """Notifica que o servidor iniciou."""
        modo = "SIMULAÇÃO (dry-run)" if dry_run else "REAL 💵"
        nome = self.bot_label or "Bot Trading"
        msg = (
            f"✅ <b>{nome} conectado com sucesso!</b>\n"
            f"Aguardando sinais do TradingView...\n\n"
            f"- Bots ativos: {num_bots}\n"
            f"- Modo: {modo}\n\n"
            f"⏰ {_agora_utc_str()}"
        )
        return self.send(msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    notifier = TelegramNotifier(cfg["telegram"]["chat_id"])
    notifier.notify_startup(len(cfg["bots"]), cfg["settings"]["dry_run"])
