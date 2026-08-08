# -*- coding: utf-8 -*-
"""
bitget_client.py
================
Cliente standalone para a API v2 da Bitget (mercado de Futuros USDT-M).

Este módulo NÃO depende do Abacus. Ele apenas lê as credenciais do arquivo
de secrets (que já foi gerado pelo Abacus) OU de variáveis de ambiente,
para que o servidor possa rodar em qualquer VPS.

Ordem de prioridade das credenciais:
  1. Variáveis de ambiente: BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE
  2. Arquivo de secrets: /home/ubuntu/.config/abacusai_auth_secrets.json

Documentação oficial usada como base:
  - Autenticação: https://www.bitget.com/api-doc/common/signature
  - Futuros v2:    https://www.bitget.com/api-doc/contract/account/...

Todos os comentários estão em Português.
"""

import os
import json
import time
import math
import hmac
import base64
import hashlib
import logging
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger("bitget_client")

# URL base da API pública da Bitget
BITGET_BASE_URL = "https://api.bitget.com"

# Caminho padrão do arquivo de secrets criado pelo Abacus
DEFAULT_SECRETS_PATH = os.path.expanduser("~/.config/abacusai_auth_secrets.json")


def load_bitget_credentials(secrets_path: str = DEFAULT_SECRETS_PATH) -> Dict[str, str]:
    """
    Carrega as credenciais da Bitget.

    Retorna um dicionário com as chaves: api_key, api_secret, passphrase.

    Primeiro tenta variáveis de ambiente (útil para VPS / Docker).
    Se não encontrar, lê o arquivo de secrets JSON.
    """
    env_key = os.getenv("BITGET_API_KEY")
    env_secret = os.getenv("BITGET_API_SECRET")
    # Aceita os dois nomes de passphrase por robustez (alguns serviços usam
    # BITGET_PASSPHRASE, outros BITGET_API_PASSPHRASE).
    env_pass = os.getenv("BITGET_PASSPHRASE") or os.getenv("BITGET_API_PASSPHRASE")

    if env_key and env_secret and env_pass:
        logger.info("Credenciais Bitget carregadas de variáveis de ambiente.")
        return {
            "api_key": env_key,
            "api_secret": env_secret,
            "passphrase": env_pass,
        }

    # Caso contrário, lê do arquivo de secrets
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(
            f"Arquivo de secrets não encontrado em {secrets_path} e "
            "variáveis de ambiente BITGET_* não definidas."
        )

    with open(secrets_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        bitget = data["bitget"]["secrets"]
        creds = {
            "api_key": bitget["api_key"]["value"],
            "api_secret": bitget["api_secret"]["value"],
            "passphrase": bitget["passphrase"]["value"],
        }
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "Estrutura inválida do arquivo de secrets para 'bitget'. "
            "Esperado bitget.secrets.{api_key,api_secret,passphrase}.value"
        ) from exc

    logger.info("Credenciais Bitget carregadas do arquivo de secrets.")
    return creds


class BitgetClient:
    """
    Cliente minimalista para a API v2 de Futuros da Bitget.

    Parâmetros principais:
      - product_type: "USDT-FUTURES" (contratos perpétuos USDT-M)
      - margin_coin:  "USDT"
      - dry_run:      Se True, NÃO envia ordens reais. Apenas simula e loga.
                      Extremamente recomendado para os primeiros testes.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        product_type: str = "USDT-FUTURES",
        margin_coin: str = "USDT",
        margin_mode: str = "isolated",
        dry_run: bool = True,
        timeout: int = 15,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.product_type = product_type
        self.margin_coin = margin_coin
        self.margin_mode = margin_mode
        self.dry_run = dry_run
        self.timeout = timeout
        self.session = requests.Session()
        # Cache de specs de contrato (precisão de qty/preço) por símbolo.
        self._contract_specs: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # Specs de contrato / arredondamento de precisão
    # ------------------------------------------------------------------ #
    def get_contract_specs(self, symbol: str) -> Dict[str, Any]:
        """
        Busca (e cacheia) as specs do contrato: número de casas decimais da
        quantidade (volumePlace), do preço (pricePlace), passo mínimo e
        quantidade mínima. Essencial para não tomar 400 por precisão inválida.
        """
        if symbol in self._contract_specs:
            return self._contract_specs[symbol]
        specs = {"volumePlace": 4, "pricePlace": 2, "minTradeNum": 0.0,
                 "sizeMultiplier": 0.0, "priceEndStep": 1}
        try:
            resp = self.session.get(
                f"{BITGET_BASE_URL}/api/v2/mix/market/contracts",
                params={"productType": self.product_type, "symbol": symbol},
                timeout=self.timeout,
            ).json()
            data = resp.get("data") or []
            if data:
                c = data[0]
                specs = {
                    "volumePlace": int(c.get("volumePlace", 4)),
                    "pricePlace": int(c.get("pricePlace", 2)),
                    "minTradeNum": float(c.get("minTradeNum", 0) or 0),
                    "sizeMultiplier": float(c.get("sizeMultiplier", 0) or 0),
                    "priceEndStep": float(c.get("priceEndStep", 1) or 1),
                }
                self._contract_specs[symbol] = specs
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_contract_specs %s falhou: %s (usando defaults)", symbol, exc)
        return specs

    def round_qty(self, symbol: str, qty: float) -> float:
        """Arredonda a quantidade ao volumePlace e ao múltiplo de sizeMultiplier."""
        specs = self.get_contract_specs(symbol)
        step = specs.get("sizeMultiplier") or 0.0
        vp = specs.get("volumePlace", 4)
        if step and step > 0:
            qty = math.floor(qty / step) * step
        qty = float(f"{qty:.{vp}f}")
        min_num = specs.get("minTradeNum") or 0.0
        if min_num and qty < min_num:
            qty = min_num
        return qty

    def round_price(self, symbol: str, price: float) -> float:
        """Arredonda o preço ao pricePlace do contrato."""
        specs = self.get_contract_specs(symbol)
        pp = specs.get("pricePlace", 2)
        return float(f"{price:.{pp}f}")

    # ------------------------------------------------------------------ #
    # Assinatura / requisições
    # ------------------------------------------------------------------ #
    def _timestamp(self) -> str:
        """Timestamp em milissegundos, exigido pela Bitget."""
        return str(int(time.time() * 1000))

    def _sign(self, timestamp: str, method: str, request_path: str, body: str) -> str:
        """
        Gera a assinatura HMAC-SHA256 em Base64.

        A mensagem a ser assinada é:
            timestamp + method.upper() + requestPath + body
        """
        message = f"{timestamp}{method.upper()}{request_path}{body}"
        mac = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _headers(self, timestamp: str, sign: str) -> Dict[str, str]:
        """Monta os cabeçalhos de autenticação exigidos pela Bitget."""
        return {
            "ACCESS-KEY": self.api_key,
            "ACCESS-SIGN": sign,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    def _request(
        self,
        method: str,
        request_path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executa uma requisição autenticada.

        Para GET, os parâmetros vão na query string (que também entra na assinatura).
        Para POST, o corpo é serializado em JSON.
        """
        method = method.upper()
        query = ""
        if params:
            # Ordena para consistência da assinatura
            query = "?" + "&".join(f"{k}={v}" for k, v in params.items())

        body_str = ""
        if body is not None:
            body_str = json.dumps(body, separators=(",", ":"))

        full_path = request_path + query
        timestamp = self._timestamp()
        sign = self._sign(timestamp, method, full_path, body_str)
        headers = self._headers(timestamp, sign)

        url = BITGET_BASE_URL + full_path

        try:
            if method == "GET":
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
            else:
                resp = self.session.post(
                    url, headers=headers, data=body_str, timeout=self.timeout
                )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.error("Erro de rede na chamada Bitget %s %s: %s", method, full_path, exc)
            return {"code": "network_error", "msg": str(exc), "data": None}
        except ValueError as exc:
            logger.error("Resposta não-JSON da Bitget: %s", exc)
            return {"code": "invalid_json", "msg": str(exc), "data": None}

        # A Bitget retorna code == "00000" em caso de sucesso
        if str(data.get("code")) != "00000":
            logger.error("Bitget retornou erro: %s", data)
        return data

    # ------------------------------------------------------------------ #
    # Endpoints de conta
    # ------------------------------------------------------------------ #
    def get_account_balance(self) -> Dict[str, Any]:
        """
        Retorna o saldo da conta de futuros.
        Endpoint: GET /api/v2/mix/account/accounts
        """
        return self._request(
            "GET",
            "/api/v2/mix/account/accounts",
            params={"productType": self.product_type},
        )

    def get_available_usdt(self) -> float:
        """
        Retorna o saldo disponível (available) em USDT como float.
        Retorna 0.0 em caso de erro.
        """
        data = self.get_account_balance()
        try:
            for acc in data.get("data", []) or []:
                if acc.get("marginCoin") == self.margin_coin:
                    return float(acc.get("available", 0) or 0)
        except (TypeError, ValueError) as exc:
            logger.error("Falha ao interpretar saldo: %s", exc)
        return 0.0

    def get_open_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna as posições abertas.
        Endpoint: GET /api/v2/mix/position/all-position
        """
        params = {"productType": self.product_type, "marginCoin": self.margin_coin}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/api/v2/mix/position/all-position", params=params)

    def has_open_position(self, symbol: str) -> bool:
        """
        Retorna True se existe posição ABERTA (size > 0) para o símbolo.

        Obs.: o endpoint all-position ignora o filtro de símbolo e devolve
        TODAS as posições; por isso filtramos manualmente aqui.
        """
        resp = self.get_open_positions()
        for p in (resp.get("data") or []):
            if p.get("symbol") == symbol:
                try:
                    if float(p.get("total", 0) or 0) > 0:
                        return True
                except (ValueError, TypeError):
                    continue
        return False

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """
        Retorna o último preço (lastPr) de um símbolo.
        Endpoint: GET /api/v2/mix/market/ticker  (público)
        """
        try:
            url = f"{BITGET_BASE_URL}/api/v2/mix/market/ticker"
            resp = self.session.get(
                url,
                params={"symbol": symbol, "productType": self.product_type},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            lst = data.get("data") or []
            if lst:
                return float(lst[0].get("lastPr"))
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            logger.error("Falha ao obter preço de %s: %s", symbol, exc)
        return None

    # ------------------------------------------------------------------ #
    # Configuração de alavancagem
    # ------------------------------------------------------------------ #
    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Configura a alavancagem para um símbolo.

        No modo ISOLATED a Bitget exige definir a alavancagem separadamente
        para o lado long e o lado short (parâmetro holdSide). No modo crossed
        um único set-leverage cobre os dois lados.

        Endpoint: POST /api/v2/mix/account/set-leverage
        """
        if self.dry_run:
            logger.info("[DRY-RUN] set_leverage %s -> %sx", symbol, leverage)
            return {"code": "00000", "msg": "dry_run", "data": {"leverage": leverage}}

        base = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
            "leverage": str(leverage),
        }

        # No isolated: define para long e short. No crossed: uma chamada só.
        if str(self.margin_mode).lower().startswith("iso"):
            results = {}
            for side in ("long", "short"):
                body = dict(base, holdSide=side)
                resp = self._request(
                    "POST", "/api/v2/mix/account/set-leverage", body=body
                )
                results[side] = resp
                if str(resp.get("code")) != "00000":
                    logger.error(
                        "set_leverage %s (%s) FALHOU: %s", symbol, side, resp
                    )
                else:
                    logger.info(
                        "set_leverage %s (%s) -> %sx OK", symbol, side, leverage
                    )
            return results.get("long", {})

        resp = self._request("POST", "/api/v2/mix/account/set-leverage", body=base)
        if str(resp.get("code")) != "00000":
            logger.error("set_leverage %s FALHOU: %s", symbol, resp)
        else:
            logger.info("set_leverage %s -> %sx OK", symbol, leverage)
        return resp

    def set_margin_mode(self, symbol: str) -> Dict[str, Any]:
        """
        Define o modo de margem (isolated/crossed).
        Endpoint: POST /api/v2/mix/account/set-margin-mode
        """
        if self.dry_run:
            logger.info("[DRY-RUN] set_margin_mode %s -> %s", symbol, self.margin_mode)
            return {"code": "00000", "msg": "dry_run", "data": None}

        body = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
            "marginMode": self.margin_mode,
        }
        return self._request("POST", "/api/v2/mix/account/set-margin-mode", body=body)

    # ------------------------------------------------------------------ #
    # Ordens
    # ------------------------------------------------------------------ #
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        leverage: Optional[int] = None,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Envia uma ordem MARKET no mercado de futuros.

        Parâmetros:
          - symbol:   ex. "BTCUSDT"
          - side:     "buy" (long) ou "sell" (short)
          - quantity: tamanho da posição na moeda base (ex.: 0.001 BTC)
          - leverage: se informado, configura alavancagem antes da ordem
          - tp_price / sl_price: preços de Take Profit e Stop Loss (opcionais)
                                 anexados diretamente à ordem (presetStopSurplusPrice /
                                 presetStopLossPrice)

        Endpoint: POST /api/v2/mix/order/place-order
        """
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side deve ser 'buy' ou 'sell'")

        # 1) Define o modo de margem (isolated/crossed) ANTES da alavancagem.
        #    Obs.: a Bitget rejeita mudar margin mode / leverage se já existir
        #    posição ABERTA no símbolo. Por isso o erro é logado mas não impede
        #    a ordem (a posição existente mantém suas configs até ser fechada).
        try:
            mm = self.set_margin_mode(symbol)
            if str(mm.get("code")) not in ("00000", None):
                logger.warning("set_margin_mode %s retornou: %s", symbol, mm)
        except Exception as exc:  # noqa: BLE001
            logger.error("set_margin_mode %s exceção: %s", symbol, exc)

        # 2) Configura alavancagem (long+short no isolated).
        if leverage is not None:
            try:
                self.set_leverage(symbol, leverage)
            except Exception as exc:  # noqa: BLE001
                logger.error("set_leverage %s exceção: %s", symbol, exc)

        # 3) Arredonda quantidade e preços conforme a PRECISÃO do contrato.
        #    (Causa do erro 400: BTC aceita 4 casas na qty e 1 no preço, mas
        #    enviávamos 6 casas -> "Bad Request".)
        qty_rounded = self.round_qty(symbol, float(quantity))
        body: Dict[str, Any] = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginMode": self.margin_mode,
            "marginCoin": self.margin_coin,
            "size": str(qty_rounded),
            "side": side,
            "orderType": "market",
            # tradeSide "open" abre nova posição no modo hedge; em one-way é ignorado
            "tradeSide": "close" if reduce_only else "open",
            "reduceOnly": "YES" if reduce_only else "NO",
        }
        if tp_price is not None:
            body["presetStopSurplusPrice"] = str(self.round_price(symbol, tp_price))
        if sl_price is not None:
            body["presetStopLossPrice"] = str(self.round_price(symbol, sl_price))

        if self.dry_run:
            logger.info("[DRY-RUN] place_order %s", json.dumps(body))
            return {
                "code": "00000",
                "msg": "dry_run",
                "data": {"orderId": f"DRYRUN-{int(time.time())}", "clientOid": None},
            }

        return self._request("POST", "/api/v2/mix/order/place-order", body=body)

    def set_tp_sl(
        self,
        symbol: str,
        hold_side: str,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        size: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Cria ordens de Take Profit e/ou Stop Loss para uma posição existente
        (útil quando não anexadas diretamente na ordem de entrada).

        Endpoint: POST /api/v2/mix/order/place-tpsl-order

        Parâmetros:
          - hold_side: "long" ou "short" (lado da posição a proteger)
        """
        results = {}

        def _submit(plan_type: str, trigger_price: float):
            body = {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "planType": plan_type,          # "pos_profit" ou "pos_loss"
                "triggerPrice": str(round(trigger_price, 6)),
                "triggerType": "mark_price",
                "holdSide": hold_side,
            }
            if size is not None:
                body["size"] = str(size)
            if self.dry_run:
                logger.info("[DRY-RUN] set_tp_sl %s", json.dumps(body))
                return {"code": "00000", "msg": "dry_run", "data": None}
            return self._request("POST", "/api/v2/mix/order/place-tpsl-order", body=body)

        if tp_price is not None:
            results["tp"] = _submit("pos_profit", tp_price)
        if sl_price is not None:
            results["sl"] = _submit("pos_loss", sl_price)
        return results

    # ------------------------------------------------------------------ #
    # TP/SL parcial (3 saídas) + break-even
    # ------------------------------------------------------------------ #
    def place_partial_tp(
        self, symbol: str, hold_side: str, trigger_price: float, size: float
    ) -> Dict[str, Any]:
        """
        Cria uma ordem de TAKE-PROFIT PARCIAL (fecha apenas `size` contratos
        quando o preço atinge `trigger_price`). Usa planType "profit_plan",
        que permite múltiplas ordens parciais na mesma posição.

        Endpoint: POST /api/v2/mix/order/place-tpsl-order
        """
        size_r = self.round_qty(symbol, float(size))
        body = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
            "planType": "profit_plan",
            "triggerPrice": str(self.round_price(symbol, trigger_price)),
            "triggerType": "mark_price",
            "holdSide": hold_side,
            "size": str(size_r),
        }
        if self.dry_run:
            logger.info("[DRY-RUN] place_partial_tp %s", json.dumps(body))
            return {"code": "00000", "msg": "dry_run",
                    "data": {"orderId": f"DRYRUN-TP-{int(time.time()*1000)}"}}
        return self._request("POST", "/api/v2/mix/order/place-tpsl-order", body=body)

    def set_position_sl(
        self, symbol: str, hold_side: str, trigger_price: float
    ) -> Dict[str, Any]:
        """
        Define/ATUALIZA o Stop Loss de POSIÇÃO INTEIRA (planType "pos_loss").
        Reenviar substitui o SL anterior — usado para mover ao break-even.

        Endpoint: POST /api/v2/mix/order/place-tpsl-order
        """
        body = {
            "symbol": symbol,
            "productType": self.product_type,
            "marginCoin": self.margin_coin,
            "planType": "pos_loss",
            "triggerPrice": str(self.round_price(symbol, trigger_price)),
            "triggerType": "mark_price",
            "holdSide": hold_side,
        }
        if self.dry_run:
            logger.info("[DRY-RUN] set_position_sl %s", json.dumps(body))
            return {"code": "00000", "msg": "dry_run", "data": None}
        return self._request("POST", "/api/v2/mix/order/place-tpsl-order", body=body)

    def get_pending_plan_orders(
        self, symbol: str, plan_type: str = "profit_loss"
    ) -> Dict[str, Any]:
        """
        Lista as ordens de plano (TP/SL) pendentes de um símbolo.
        Endpoint: GET /api/v2/mix/order/orders-plan-pending
        """
        params = {
            "symbol": symbol,
            "productType": self.product_type,
            "planType": plan_type,
        }
        return self._request("GET", "/api/v2/mix/order/orders-plan-pending", params=params)

    def cancel_all_tpsl(self, symbol: str) -> Dict[str, Any]:
        """
        Cancela (best-effort) todas as ordens TP/SL pendentes de um símbolo.
        Usado na limpeza quando a posição é totalmente fechada, para não deixar
        ordens órfãs que atrapalhem a próxima entrada.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] cancel_all_tpsl %s", symbol)
            return {"code": "00000", "msg": "dry_run", "data": None}
        try:
            pending = self.get_pending_plan_orders(symbol, "profit_loss")
            entrust = ((pending.get("data") or {}).get("entrustedList")) or []
            id_list = []
            for o in entrust:
                oid = o.get("orderId")
                if oid:
                    id_list.append({"orderId": oid, "clientOid": o.get("clientOid", "")})
            if not id_list:
                return {"code": "00000", "msg": "no pending plans", "data": None}
            body = {
                "symbol": symbol,
                "productType": self.product_type,
                "marginCoin": self.margin_coin,
                "orderIdList": id_list,
            }
            return self._request("POST", "/api/v2/mix/order/cancel-plan-order", body=body)
        except Exception as exc:  # noqa: BLE001
            logger.error("cancel_all_tpsl %s falhou: %s", symbol, exc)
            return {"code": "error", "msg": str(exc), "data": None}


def build_client_from_config(config: Dict[str, Any]) -> "BitgetClient":
    """
    Fábrica que constrói um BitgetClient a partir do dicionário de configuração
    (config.json) + secrets. Facilita o uso no server.py.
    """
    settings = config.get("settings", {})
    creds = load_bitget_credentials()
    return BitgetClient(
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        passphrase=creds["passphrase"],
        product_type=settings.get("product_type", "USDT-FUTURES"),
        margin_coin=settings.get("margin_coin", "USDT"),
        margin_mode=settings.get("margin_mode", "isolated"),
        dry_run=bool(settings.get("dry_run", True)),
    )


if __name__ == "__main__":
    # Teste rápido de conectividade (apenas leitura)
    logging.basicConfig(level=logging.INFO)
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    client = build_client_from_config(cfg)
    print("Saldo USDT disponível:", client.get_available_usdt())
    print("Preço BTCUSDT:", client.get_ticker_price("BTCUSDT"))
