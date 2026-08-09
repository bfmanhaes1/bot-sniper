-- Migration: Tabela para persistir eventos diários do BOT-SNIPER
-- 
-- Resolve: Os arquivos crypto2_logs/*.json são efêmeros no Railway (resetam
--          a cada deploy). Esta tabela garante histórico permanente.
-- 
-- Uso: crypto_logger.registrar() salva AQUI quando DATABASE_URL existe.

CREATE TABLE IF NOT EXISTS public.crypto_eventos (
    id BIGSERIAL PRIMARY KEY,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    data DATE NOT NULL,  -- índice para filtro rápido por dia
    hora TIME NOT NULL,
    evento VARCHAR(50) NOT NULL,  -- SINAL, ENTRADA, SAIDA, BLOQUEADO, etc
    moeda VARCHAR(20),
    timeframe VARCHAR(10),
    payload JSONB NOT NULL  -- registro completo (campos extras variáveis)
);

-- Índices para queries rápidas
CREATE INDEX IF NOT EXISTS idx_crypto_eventos_data ON public.crypto_eventos(data);
CREATE INDEX IF NOT EXISTS idx_crypto_eventos_moeda ON public.crypto_eventos(moeda);
CREATE INDEX IF NOT EXISTS idx_crypto_eventos_evento ON public.crypto_eventos(evento);
CREATE INDEX IF NOT EXISTS idx_crypto_eventos_moeda_data ON public.crypto_eventos(moeda, data);

-- Comentário
COMMENT ON TABLE public.crypto_eventos IS 'Eventos diários do BOT-SNIPER (ENTRADA/SAIDA/BLOQUEADO/etc). Substitui crypto2_logs/*.json efêmeros.';
