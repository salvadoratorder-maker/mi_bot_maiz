-- ══════════════════════════════════════════════════════════
-- ESQUEMA DE BASE DE DATOS — Grain Trading Bot (Supabase)
-- Ejecuta este SQL en el SQL Editor de tu proyecto Supabase
-- ══════════════════════════════════════════════════════════

-- ── Tabla: señales ──
-- Registra cada señal detectada por el bot
CREATE TABLE IF NOT EXISTS señales (
    id                 BIGSERIAL PRIMARY KEY,
    timestamp          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estrategia         TEXT NOT NULL,          -- 'E1', 'E2', 'E3'
    ticker             TEXT NOT NULL,          -- 'ZC=F', 'ZS=F'
    direccion          TEXT NOT NULL,          -- 'LONG', 'SHORT'
    precio_entrada     NUMERIC(10, 3),
    bb_up              NUMERIC(10, 3),
    bb_mid             NUMERIC(10, 3),
    adx                NUMERIC(6, 2),
    recorrido_cts      NUMERIC(8, 3),
    size               NUMERIC(4, 1),
    factor_estacional  NUMERIC(4, 1),
    ratio_adr          NUMERIC(6, 3),
    sl_precio          NUMERIC(10, 3),
    estado             TEXT DEFAULT 'ABIERTA', -- 'ABIERTA', 'CERRADA', 'OMITIDA'
    notas              TEXT
);

-- ── Tabla: trades ──
-- Registro completo de cada trade (paper)
CREATE TABLE IF NOT EXISTS trades (
    id               BIGSERIAL PRIMARY KEY,
    señal_id         TEXT,
    timestamp_open   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    timestamp_close  TIMESTAMPTZ,
    estrategia       TEXT NOT NULL,
    ticker           TEXT NOT NULL,
    direccion        TEXT NOT NULL,
    precio_entrada   NUMERIC(10, 3),
    precio_salida    NUMERIC(10, 3),
    sl_inicial       NUMERIC(10, 3),
    trail_cts        NUMERIC(8, 3),
    max_precio       NUMERIC(10, 3),      -- máximo alcanzado (LONG) o mínimo (SHORT)
    trail_actual     NUMERIC(10, 3),      -- nivel actual del trailing stop
    size             NUMERIC(4, 1),
    barras           INTEGER DEFAULT 0,   -- barras transcurridas desde entrada
    motivo_cierre    TEXT,               -- 'TP', 'SL', 'TRAIL', 'TIEMPO', 'ROLL'
    resultado_cts    NUMERIC(8, 3),
    resultado_usd    NUMERIC(10, 2),
    estado           TEXT DEFAULT 'ABIERTO'  -- 'ABIERTO', 'CERRADO'
);

-- ── Tabla: logs ──
-- Registro de ejecuciones del bot
CREATE TABLE IF NOT EXISTS logs (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modo        TEXT,
    señales_n   INTEGER DEFAULT 0,
    trades_n    INTEGER DEFAULT 0,
    errores     TEXT,
    duracion_s  NUMERIC(6, 2)
);

-- ── Índices para consultas rápidas ──
CREATE INDEX IF NOT EXISTS idx_trades_estado    ON trades (estado);
CREATE INDEX IF NOT EXISTS idx_trades_ticker    ON trades (ticker);
CREATE INDEX IF NOT EXISTS idx_señales_ts       ON señales (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_ts_open   ON trades (timestamp_open DESC);

-- ── Vista: resumen por estrategia ──
CREATE OR REPLACE VIEW resumen_estrategias AS
SELECT
    estrategia,
    COUNT(*)                                          AS total_trades,
    COUNT(*) FILTER (WHERE resultado_usd > 0)         AS wins,
    COUNT(*) FILTER (WHERE resultado_usd <= 0)        AS losses,
    ROUND(
        COUNT(*) FILTER (WHERE resultado_usd > 0)::NUMERIC
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                                 AS win_rate_pct,
    ROUND(SUM(resultado_usd)::NUMERIC, 2)             AS neto_usd,
    ROUND(AVG(resultado_usd)::NUMERIC, 2)             AS media_usd,
    ROUND(
        SUM(resultado_usd) FILTER (WHERE resultado_usd > 0)::NUMERIC
        / NULLIF(ABS(SUM(resultado_usd) FILTER (WHERE resultado_usd <= 0)), 0)
    , 2)                                              AS profit_factor,
    ROUND(AVG(barras)::NUMERIC, 1)                    AS duracion_media_barras
FROM trades
WHERE estado = 'CERRADO'
GROUP BY estrategia
ORDER BY estrategia;

-- ── Vista: trades recientes ──
CREATE OR REPLACE VIEW trades_recientes AS
SELECT
    id,
    estrategia,
    ticker,
    direccion,
    precio_entrada,
    precio_salida,
    resultado_cts,
    resultado_usd,
    motivo_cierre,
    barras,
    estado,
    timestamp_open::DATE AS fecha_open,
    timestamp_close::DATE AS fecha_close
FROM trades
ORDER BY timestamp_open DESC
LIMIT 50;

-- ══════════════════════════════════════════════════════════
-- INSTRUCCIONES DE USO
-- ══════════════════════════════════════════════════════════
-- 1. Ve a tu proyecto en supabase.com
-- 2. SQL Editor → New Query
-- 3. Pega todo este archivo y ejecuta (Run)
-- 4. Verifica en Table Editor que aparecen las tablas
--
-- Para ver el resumen del paper trading:
--   SELECT * FROM resumen_estrategias;
--
-- Para ver los trades abiertos:
--   SELECT * FROM trades WHERE estado = 'ABIERTO';
--
-- Para ver los últimos trades:
--   SELECT * FROM trades_recientes;
-- ══════════════════════════════════════════════════════════
