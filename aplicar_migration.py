#!/usr/bin/env python3
"""
Aplica migration 001 (criar tabela crypto_eventos) no PostgreSQL do Railway.

Uso:
    python3 aplicar_migration.py

Requerimentos:
    - DATABASE_URL configurada (Railway injeta automaticamente quando tem addon Postgres)
    - psycopg2 ou pg8000 instalado
"""
import os
import sys
from pathlib import Path

# Adiciona diretório do bot ao path para importar crypto_logger
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

def main():
    print("=" * 60)
    print("📦 APLICADOR DE MIGRATION - BOT-SNIPER")
    print("=" * 60)
    print()
    
    # Verifica DATABASE_URL
    DATABASE_URL = (
        os.environ.get("DATABASE_URL") 
        or os.environ.get("DATABASE_PUBLIC_URL")
        or ""
    ).strip()
    
    if not DATABASE_URL:
        print("❌ ERRO: DATABASE_URL não encontrada!")
        print()
        print("SOLUÇÃO:")
        print("1. No Railway, vá em PostgreSQL → Variables")
        print("2. Copie o valor de DATABASE_URL")
        print("3. Execute:")
        print("   export DATABASE_URL='...'")
        print("   python3 aplicar_migration.py")
        print()
        return 1
    
    print(f"✅ DATABASE_URL encontrada: {DATABASE_URL[:30]}...")
    print()
    
    # Tenta importar driver PostgreSQL
    driver = None
    try:
        import psycopg2
        driver = "psycopg2"
        print("✅ Driver PostgreSQL: psycopg2")
    except ImportError:
        try:
            import pg8000
            driver = "pg8000"
            print("✅ Driver PostgreSQL: pg8000")
        except ImportError:
            print("❌ ERRO: Nenhum driver PostgreSQL instalado!")
            print()
            print("SOLUÇÃO:")
            print("   pip3 install psycopg2-binary")
            print("   # ou")
            print("   pip3 install pg8000")
            print()
            return 1
    
    print()
    print("🔧 Lendo migration 001_criar_tabela_eventos.sql...")
    
    # Lê SQL da migration
    migration_file = BASE_DIR / "migrations" / "001_criar_tabela_eventos.sql"
    if not migration_file.exists():
        print(f"❌ ERRO: Arquivo não encontrado: {migration_file}")
        return 1
    
    with open(migration_file, "r", encoding="utf-8") as f:
        sql = f.read()
    
    print(f"✅ SQL carregado ({len(sql)} caracteres)")
    print()
    
    # Conecta e executa
    print("🔌 Conectando ao PostgreSQL...")
    
    try:
        if driver == "psycopg2":
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        else:  # pg8000
            import pg8000
            from urllib.parse import urlparse
            u = urlparse(DATABASE_URL)
            conn = pg8000.connect(
                host=u.hostname,
                port=u.port or 5432,
                user=u.username,
                password=u.password,
                database=u.path.lstrip("/"),
                timeout=10,
                ssl_context=True
            )
        
        print("✅ Conectado com sucesso!")
        print()
        print("⚙️  Aplicando migration...")
        
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        
        print("✅ Migration aplicada com sucesso!")
        print()
        
        # Verifica se a tabela foi criada
        print("🔍 Verificando tabela crypto_eventos...")
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'crypto_eventos' 
            ORDER BY ordinal_position
        """)
        colunas = cursor.fetchall()
        
        if colunas:
            print(f"✅ Tabela criada com {len(colunas)} colunas:")
            for col_name, col_type in colunas:
                print(f"   - {col_name}: {col_type}")
        else:
            print("⚠️  Tabela não encontrada (pode ser problema de schema)")
        
        print()
        
        # Conta registros
        cursor.execute("SELECT COUNT(*) FROM crypto_eventos")
        count = cursor.fetchone()[0]
        print(f"📊 Registros na tabela: {count}")
        
        cursor.close()
        conn.close()
        
        print()
        print("=" * 60)
        print("✅ MIGRATION CONCLUÍDA COM SUCESSO!")
        print("=" * 60)
        print()
        print("PRÓXIMOS PASSOS:")
        print("1. Faça commit e push das mudanças:")
        print("   git push origin main")
        print()
        print("2. O Railway vai fazer redeploy automático")
        print()
        print("3. Depois do deploy, TODOS os eventos serão salvos no PostgreSQL!")
        print()
        print("4. Acesse o resumo diário em:")
        print("   https://web-production-77454.up.railway.app/resumo?formato=texto")
        print()
        
        return 0
        
    except Exception as e:
        print(f"❌ ERRO ao aplicar migration: {e}")
        print()
        print("POSSÍVEIS CAUSAS:")
        print("- DATABASE_URL incorreta")
        print("- PostgreSQL não acessível")
        print("- Tabela já existe (não é erro grave)")
        print()
        return 1

if __name__ == "__main__":
    sys.exit(main())
