# -*- coding: utf-8 -*-
"""
Teste de INTEGRAÇÃO do backend Postgres do estudo de TP/SL.

Roda com: python3 test_estudo_postgres.py

Requer uma DATABASE_URL acessível (o Railway injeta automaticamente quando o
addon Postgres está ligado). Se NÃO houver DATABASE_URL no ambiente, o teste é
PULADO (skip) — não falha —, porque aí o backend correto é o JSONL, já coberto
por test_estudo_tpsl.py.

Segurança: usa uma TABELA TEMPORÁRIA exclusiva do teste (via ESTUDO_TABELA) e a
APAGA no final (DROP TABLE), então NÃO toca no livro-razão de produção.
"""
import os
import sys
import uuid

if not (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")):
    print("SKIP: sem DATABASE_URL — backend Postgres não testável aqui "
          "(o JSONL é coberto por test_estudo_tpsl.py).")
    sys.exit(0)

# Força uma tabela temporária ANTES de importar o crypto_logger (ele lê no import).
_TABELA = f"estudo_tpsl_test_{uuid.uuid4().hex[:8]}"
os.environ["ESTUDO_TABELA"] = _TABELA

import crypto_logger  # noqa: E402

falhas = []


def check(desc, cond):
    print(("  OK  " if cond else " FALHA ") + desc)
    if not cond:
        falhas.append(desc)


try:
    check("backend detectado = postgres", crypto_logger._USE_PG is True)

    # 1) Começa vazio (tabela nova, ainda nem existe -> _pg_init cria)
    check("livro-razao Postgres comeca vazio", crypto_logger.ler_estudo() == [])
    check("estudo_backend() indica postgres", "postgres" in crypto_logger.estudo_backend())

    # 2) Grava duas entradas
    crypto_logger.registrar_estudo({"moeda": "BTC", "tf": "5m",
                                     "mfe_pct": 1.0, "dd_pct": 0.5, "direcao": "LONG"})
    crypto_logger.registrar_estudo({"moeda": "BTC", "tf": "5m",
                                     "mfe_pct": 3.0, "dd_pct": 1.5, "direcao": "SHORT"})
    linhas = crypto_logger.ler_estudo()
    check("insert gravou 2 linhas", len(linhas) == 2)
    check("payload JSONB preservou campos", linhas[0].get("moeda") == "BTC"
          and linhas[0].get("direcao") == "LONG")
    check("ordem preservada (id crescente)", linhas[0].get("mfe_pct") == 1.0
          and linhas[1].get("mfe_pct") == 3.0)

    # 3) limite retorna as ÚLTIMAS N na ordem cronológica
    ult = crypto_logger.ler_estudo(limite=1)
    check("limite=1 retorna a ultima entrada", len(ult) == 1 and ult[0].get("mfe_pct") == 3.0)

    # 4) resumo agrega corretamente
    res = crypto_logger.resumo_estudo()
    check("resumo total_entradas = 2", res["total_entradas"] == 2)
    check("resumo MFE medio = 2.0", res["geral"]["mfe_medio"] == 2.0)
    check("resumo DD max = 1.5", res["geral"]["dd_max"] == 1.5)
    check("resumo por_combinacao tem BTC_5m", "BTC_5m" in res["por_combinacao"])
    check("resumo reporta backend postgres", "postgres" in res.get("backend", ""))

    # 5) filtro por moeda/tf
    res_btc = crypto_logger.resumo_estudo(moeda="BTC", tf="5m")
    check("filtro BTC/5m = 2 entradas", res_btc["geral"]["n"] == 2)
    res_eth = crypto_logger.resumo_estudo(moeda="ETH")
    check("filtro moeda inexistente = 0", res_eth["geral"]["n"] == 0)

finally:
    # Limpeza: apaga a tabela temporária do teste (não toca produção).
    try:
        crypto_logger._pg_exec(f"DROP TABLE IF EXISTS {_TABELA};")
        print(f"  (tabela temporaria {_TABELA} removida)")
    except Exception as exc:  # noqa: BLE001
        print(f"  AVISO: falha ao remover tabela temporaria {_TABELA}: {exc}")

print()
if falhas:
    print(f"RESULTADO: {len(falhas)} FALHA(S)")
    sys.exit(1)
print("RESULTADO: TODOS OS TESTES PASSARAM (backend Postgres)")
