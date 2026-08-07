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

# ---------------------------------------------------------------------------
# DIRETÓRIO DE DADOS DURÁVEL
# ---------------------------------------------------------------------------
# O disco padrão do Railway é EFÊMERO: some a cada redeploy/reinício. Para não
# perder o histórico do estudo de TP/SL, os dados vão para um VOLUME persistente
# montado em /data (padrão que o bot do MNQ já usa). Se não houver /data (ex.:
# rodando localmente) ou se quiser forçar outro caminho, use a env CRYPTO_DATA_DIR.
#   - Railway: crie um Volume com mount path /data no serviço do bot.
#   - Local:   cai automaticamente na pasta do projeto (comportamento antigo).
DATA_DIR = (
    os.environ.get("CRYPTO_DATA_DIR")
    or ("/data" if os.path.isdir("/data") else BASE_DIR)
)
LOG_DIR = os.path.join(DATA_DIR, "crypto2_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Livro-razão APPEND-ONLY do estudo de TP/SL: 1 linha JSON por entrada observada.
# NUNCA sobrescreve — acumula entre dias e sobrevive a redeploys (quando em /data).
# É a fonte durável dos números de MFE (correu a favor) e DD/MAE (correu contra)
# que servem para escolher o TP e o SL.
ESTUDO_PATH = os.path.join(DATA_DIR, "estudo_tpsl.jsonl")

logger.info("crypto_logger: DATA_DIR=%s | LOG_DIR=%s | ESTUDO=%s",
            DATA_DIR, LOG_DIR, ESTUDO_PATH)

_lock = threading.Lock()

# =========================================================================== #
# BACKEND DURÁVEL DO ESTUDO: POSTGRES (com fallback automático para JSONL)
# =========================================================================== #
# O disco do Railway é EFÊMERO e o plano não expôs Volumes, então o livro-razão
# do estudo de TP/SL é gravado num POSTGRES (mesmo padrão do bot do MNQ). O
# Railway injeta a variável DATABASE_URL quando você adiciona o addon Postgres.
# Se DATABASE_URL não existir (ex.: rodando local nos testes), o código cai
# automaticamente no arquivo JSONL — nada quebra. A API pública
# (registrar_estudo / ler_estudo / resumo_estudo) é a MESMA nos dois backends,
# então crypto_shadow.py e server.py não precisam saber qual está em uso.
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("DATABASE_PUBLIC_URL")
    or ""
).strip()

# Nome da tabela do livro-razão (append-only) no Postgres.
ESTUDO_TABELA = os.environ.get("ESTUDO_TABELA", "estudo_tpsl")

_USE_PG = False
_psycopg2 = None
_pg8000 = None
_pg_driver = None          # "psycopg2" | "pg8000" | None
_pg_import_error = None
if DATABASE_URL:
    # 1ª opção: psycopg2 (rápido, em C). Pode falhar no Railway/Nixpacks por
    #           falta da libpq do sistema (libpq.so.5). Se falhar, tentamos o
    #           pg8000, que é PURO-PYTHON e não depende de nenhuma lib nativa.
    _erros = []
    try:
        import psycopg2 as _psycopg2  # type: ignore
        _pg_driver = "psycopg2"
        _USE_PG = True
    except Exception as _exc:  # noqa: BLE001
        _erros.append("psycopg2 -> %s: %s" % (type(_exc).__name__, _exc))
        try:
            import pg8000.dbapi as _pg8000  # type: ignore
            _pg_driver = "pg8000"
            _USE_PG = True
        except Exception as _exc2:  # noqa: BLE001
            _erros.append("pg8000 -> %s: %s" % (type(_exc2).__name__, _exc2))
    if _USE_PG:
        logger.info("crypto_logger: estudo usará POSTGRES via driver '%s'.", _pg_driver)
    else:
        _pg_import_error = " | ".join(_erros)
        logger.error("crypto_logger: nenhum driver Postgres disponível (%s) — usando JSONL.",
                     _pg_import_error)
else:
    logger.info("crypto_logger: sem DATABASE_URL — estudo usará arquivo JSONL (%s).",
                ESTUDO_PATH)

_pg_ready = False
_pg_lock = threading.Lock()


def _pg_connect():
    """Abre uma conexão nova (autocommit). Conexão curta = robusto a drops.
    Funciona tanto com psycopg2 (aceita a URL direto) quanto com pg8000
    (puro-Python, precisa dos campos separados extraídos da URL)."""
    if _pg_driver == "psycopg2":
        conn = _psycopg2.connect(DATABASE_URL, connect_timeout=10)
        conn.autocommit = True
        return conn
    # pg8000: precisa de host/porta/usuário/senha/database separados.
    from urllib.parse import urlparse, unquote
    u = urlparse(DATABASE_URL)
    conn = _pg8000.connect(
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        host=u.hostname or "localhost",
        port=int(u.port or 5432),
        database=(u.path or "/").lstrip("/") or "railway",
        timeout=10,
    )
    conn.autocommit = True
    return conn


def _pg_exec(sql: str, params=None, fetch: Optional[str] = None):
    """Executa uma query fechando a conexão ao final. fetch: None|'one'|'all'."""
    conn = None
    cur = None
    try:
        conn = _pg_connect()
        cur = conn.cursor()
        cur.execute(sql, params or ())
        if fetch == "all":
            return cur.fetchall()
        if fetch == "one":
            return cur.fetchone()
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:  # noqa: BLE001
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _pg_init() -> bool:
    """Cria a tabela do estudo se ainda não existir. Idempotente e cacheado."""
    global _pg_ready
    if not _USE_PG:
        return False
    if _pg_ready:
        return True
    with _pg_lock:
        if _pg_ready:
            return True
        try:
            _pg_exec(
                f"""
                CREATE TABLE IF NOT EXISTS {ESTUDO_TABELA} (
                    id         BIGSERIAL PRIMARY KEY,
                    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    moeda      TEXT,
                    tf         TEXT,
                    mfe_pct    DOUBLE PRECISION,
                    dd_pct     DOUBLE PRECISION,
                    payload    JSONB NOT NULL
                );
                """
            )
            _pg_exec(
                f"CREATE INDEX IF NOT EXISTS idx_{ESTUDO_TABELA}_moeda_tf "
                f"ON {ESTUDO_TABELA} (moeda, tf);"
            )
            _pg_ready = True
            logger.info("crypto_logger: tabela Postgres '%s' pronta.", ESTUDO_TABELA)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("crypto_logger: falha ao inicializar Postgres (%s) — "
                         "caindo para JSONL nesta gravação.", exc)
            return False


def estudo_backend() -> str:
    """Rótulo do backend em uso, para exibir em /diag e /estudo."""
    if _USE_PG:
        return f"postgres ({ESTUDO_TABELA})" if _pg_ready else "postgres (conectando)"
    return "jsonl"


def estudo_diag() -> Dict[str, Any]:
    """Diagnóstico do backend do estudo (sem vazar a senha da DATABASE_URL).
    Ajuda a descobrir POR QUE o Postgres não está ativo em produção."""
    url = DATABASE_URL or ""
    host = ""
    if "@" in url:
        try:
            host = url.split("@", 1)[1].split("/", 1)[0]  # host:porta
        except Exception:  # noqa: BLE001
            host = "?"
    conexao_ok = None
    erro_conexao = None
    if _USE_PG:
        try:
            _pg_exec("SELECT 1", fetch="one")
            conexao_ok = True
        except Exception as exc:  # noqa: BLE001
            conexao_ok = False
            erro_conexao = str(exc)[:300]
    return {
        "backend": estudo_backend(),
        "database_url_presente": bool(url),
        "database_url_host": host,          # só host:porta, sem usuário/senha
        "driver": _pg_driver,
        "psycopg2_importado": _psycopg2 is not None,
        "pg8000_importado": _pg8000 is not None,
        "erro_import_driver": _pg_import_error,
        "use_pg": _USE_PG,
        "pg_ready": _pg_ready,
        "conexao_ok": conexao_ok,
        "erro_conexao": erro_conexao,
        "tabela": ESTUDO_TABELA,
    }

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


# =========================================================================== #
# LIVRO-RAZÃO DO ESTUDO DE TP/SL (append-only, durável)
# =========================================================================== #
# Objetivo: para calibrar TP e SL SEM viés, o bot observa CADA entrada simulada
# por uma janela FIXA completa (não para no TP/SL) e grava aqui a excursão máxima
# a favor (MFE) e contra (DD/MAE). Uma linha JSON por entrada. Nunca sobrescreve.

def _f(v):
    """Converte para float de forma segura (ou None)."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def registrar_estudo(reg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Grava UMA entrada observada no livro-razão durável do estudo de TP/SL.
    Backend: POSTGRES quando há DATABASE_URL (durável, sobrevive a redeploys);
    senão, arquivo JSONL. Em erro no Postgres, cai para o JSONL (nunca perde).
    """
    reg = dict(reg or {})
    reg.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    if _USE_PG and _pg_init():
        try:
            _pg_exec(
                f"INSERT INTO {ESTUDO_TABELA} "
                f"(moeda, tf, mfe_pct, dd_pct, payload) VALUES (%s, %s, %s, %s, %s::jsonb)",
                (reg.get("moeda"), reg.get("tf"),
                 _f(reg.get("mfe_pct")), _f(reg.get("dd_pct")),
                 json.dumps(reg, ensure_ascii=False)),
            )
            return reg
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao gravar estudo no Postgres (%s) — fallback JSONL.", exc)

    try:
        with _lock:
            with open(ESTUDO_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("Falha ao gravar estudo de TP/SL: %s", exc)
    return reg


def ler_estudo(limite: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Lê o livro-razão do estudo (todas as linhas, ou as últimas `limite`).
    Backend: POSTGRES quando disponível; senão, arquivo JSONL.
    Ignora linhas corrompidas silenciosamente (robustez).
    """
    if _USE_PG and _pg_init():
        try:
            if limite and limite > 0:
                rows = _pg_exec(
                    f"SELECT payload FROM {ESTUDO_TABELA} ORDER BY id DESC LIMIT %s",
                    (limite,), fetch="all") or []
                rows = list(reversed(rows))
            else:
                rows = _pg_exec(
                    f"SELECT payload FROM {ESTUDO_TABELA} ORDER BY id",
                    fetch="all") or []
            # psycopg2 decodifica JSONB em dict; pg8000 pode devolver str.
            saida: List[Dict[str, Any]] = []
            for r in rows:
                p = r[0]
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except ValueError:
                        continue
                if isinstance(p, dict):
                    saida.append(p)
            return saida
        except Exception as exc:  # noqa: BLE001
            logger.error("Falha ao ler estudo do Postgres (%s) — fallback JSONL.", exc)

    if not os.path.exists(ESTUDO_PATH):
        return []
    linhas: List[Dict[str, Any]] = []
    try:
        with open(ESTUDO_PATH, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    linhas.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        return []
    if limite and limite > 0:
        return linhas[-limite:]
    return linhas


def _percentil(valores: List[float], p: float) -> Optional[float]:
    """Percentil simples (p em 0..100) por interpolação linear."""
    if not valores:
        return None
    vs = sorted(valores)
    if len(vs) == 1:
        return vs[0]
    k = (len(vs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    if f == c:
        return vs[f]
    return vs[f] + (vs[c] - vs[f]) * (k - f)


def resumo_estudo(moeda: Optional[str] = None,
                  tf: Optional[str] = None) -> Dict[str, Any]:
    """
    Agrega o livro-razão em estatísticas de MFE (correu a favor) e DD/MAE
    (correu contra) — globais e por combinação MOEDA+TF. Base direta para
    escolher o TP (perto do MFE típico) e o SL (além do DD típico).
    Filtros opcionais por `moeda` e/ou `tf`.
    """
    regs = ler_estudo()
    if moeda:
        regs = [r for r in regs if (r.get("moeda") or "").upper() == moeda.upper()]
    if tf:
        regs = [r for r in regs if r.get("tf") == tf]

    def _stats(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
        mfe = [float(r["mfe_pct"]) for r in rs if r.get("mfe_pct") is not None]
        dd = [float(r["dd_pct"]) for r in rs if r.get("dd_pct") is not None]
        n = len(rs)
        def _m(v):
            return round(sum(v) / len(v), 4) if v else None
        def _pp(v, p):
            r = _percentil(v, p)
            return round(r, 4) if r is not None else None
        return {
            "n": n,
            "mfe_medio": _m(mfe), "mfe_mediana": _pp(mfe, 50),
            "mfe_p75": _pp(mfe, 75), "mfe_p90": _pp(mfe, 90),
            "mfe_max": round(max(mfe), 4) if mfe else None,
            "dd_medio": _m(dd), "dd_mediana": _pp(dd, 50),
            "dd_p75": _pp(dd, 75), "dd_p90": _pp(dd, 90),
            "dd_max": round(max(dd), 4) if dd else None,
        }

    por_combo: Dict[str, List[Dict[str, Any]]] = {}
    for r in regs:
        chave = f"{r.get('moeda', '?')}_{r.get('tf', '?')}"
        por_combo.setdefault(chave, []).append(r)

    return {
        "backend": estudo_backend(),
        "arquivo": (f"postgres::{ESTUDO_TABELA}" if _USE_PG else ESTUDO_PATH),
        "total_entradas": len(regs),
        "geral": _stats(regs),
        "por_combinacao": {k: _stats(v) for k, v in sorted(por_combo.items())},
    }
