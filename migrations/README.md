# Migrations — PostgreSQL

Migrations para criar tabelas do BOT-SNIPER no PostgreSQL (Railway).

## Como aplicar no Railway

### Via Railway CLI (recomendado)
```bash
# 1. Instalar Railway CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Link ao projeto
railway link

# 4. Conectar ao PostgreSQL
railway run psql $DATABASE_URL -f migrations/001_criar_tabela_eventos.sql
```

### Via interface web Railway
1. Acesse o projeto no Railway
2. Vá em **PostgreSQL** → **Data** → **Query**
3. Cole e execute o conteúdo de `001_criar_tabela_eventos.sql`

### Manualmente (se tiver DATABASE_URL)
```bash
# Exportar DATABASE_URL do Railway (Settings → Variables)
export DATABASE_URL="postgresql://..."

# Aplicar migration
psql $DATABASE_URL < migrations/001_criar_tabela_eventos.sql
```

## Verificar tabela criada
```sql
-- Ver estrutura
\d crypto_eventos

-- Contar registros
SELECT COUNT(*) FROM crypto_eventos;

-- Ver últimos 10 eventos
SELECT criado_em, evento, moeda, timeframe 
FROM crypto_eventos 
ORDER BY id DESC 
LIMIT 10;
```

## Migrations disponíveis

### 001_criar_tabela_eventos.sql
**O quê**: Cria tabela `crypto_eventos` para persistir eventos diários (ENTRADA/SAIDA/BLOQUEADO/etc).

**Por quê**: Os arquivos `crypto2_logs/*.json` são efêmeros no Railway (resetam a cada deploy). Esta tabela garante histórico permanente.

**Quando aplicar**: AGORA (antes do próximo deploy). Sem ela, os dados continuam só nos arquivos JSON efêmeros.

**Depois de aplicar**: O bot automaticamente começa a salvar TUDO no PostgreSQL. Nenhuma mudança de código necessária.

---

## Estado atual

- ✅ `estudo_tpsl` — já existe (dados MFE/DD do estudo de TP/SL)
- ⏳ `crypto_eventos` — **PRECISA CRIAR** (migration 001)

Após aplicar 001, o resumo diário funcionará 100% com dados permanentes! 🎯
