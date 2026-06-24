# 🌽 Grain Trading Bot

Bot de **paper trading** para futuros de maíz y soja (CBOT).
Detecta señales automáticamente, gestiona trades ficticios y envía alertas por Telegram.

> ⚠️ **Paper trading únicamente** — sin dinero real. Para validar el sistema antes de operar en vivo.

---

## Estrategias implementadas

| ID | Nombre | Activo | Timeframe | Lógica |
|---|---|---|---|---|
| E1 | Maíz SHORT nocturno | ZC=F | 1h | Mean reversion — precio toca BB superior de noche |
| E2 | Maíz LONG breakout | ZC=F | Semanal | Trend following — breakout BB superior con trailing |
| E3 | Soja LONG breakout | ZS=F | Semanal | Trend following — breakout BB superior con trailing |

---

## Arquitectura

```
GitHub Actions (scheduler)
    ↓ cron automático
src/bot.py
    ├── data.py         → descarga datos (yfinance)
    ├── indicators.py   → BB, ADX, ATR, señales
    ├── database.py     → lectura/escritura Supabase
    └── alerts.py       → notificaciones Telegram
```

---

## Instalación paso a paso

### 1. Fork / Clone este repositorio

```bash
git clone https://github.com/TU_USUARIO/grain-bot.git
cd grain-bot
```

### 2. Crear proyecto en Supabase

1. Ve a [supabase.com](https://supabase.com) → New Project (gratuito)
2. Abre el **SQL Editor** → New Query
3. Pega el contenido de `supabase_schema.sql` y ejecuta
4. Ve a **Project Settings → API** y copia:
   - `Project URL` → será tu `SUPABASE_URL`
   - `anon public key` → será tu `SUPABASE_KEY`

### 3. Crear bot de Telegram (opcional pero recomendado)

1. Abre Telegram → busca `@BotFather`
2. Escribe `/newbot` y sigue las instrucciones
3. Copia el **token** que te da BotFather → `TELEGRAM_TOKEN`
4. Escribe `/start` a tu nuevo bot
5. Ve a `https://api.telegram.org/bot<TOKEN>/getUpdates` en el navegador
6. Copia el `chat_id` que aparece → `TELEGRAM_CHAT_ID`

### 4. Configurar Secrets en GitHub

Ve a tu repositorio → **Settings → Secrets and variables → Actions → New repository secret**

Añade estos 4 secrets:

| Secret | Valor |
|---|---|
| `SUPABASE_URL` | URL de tu proyecto Supabase |
| `SUPABASE_KEY` | anon key de Supabase |
| `TELEGRAM_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | Tu chat ID de Telegram |

### 5. Activar GitHub Actions

1. Ve a la pestaña **Actions** de tu repositorio
2. Si aparece un aviso de activación, haz clic en **"I understand my workflows, go ahead and enable them"**
3. El bot se ejecutará automáticamente según el horario configurado

### 6. Prueba manual

En **Actions → Grain Trading Bot → Run workflow** → selecciona el modo `todo` → Run.

Comprueba que:
- El workflow se ejecuta sin errores (verde ✅)
- Aparecen registros en Supabase (Table Editor → trades)
- Recibes mensaje en Telegram

---

## Horario de ejecución (UTC)

| Cron | Hora Madrid (aprox) | Acción |
|---|---|---|
| `0 0 * * 1-5` | 02:00 (invierno) | Buscar señales E1 |
| `0 1 * * 1-5` | 03:00 (verano) | Buscar señales E1 |
| `0 2-8 * * 2-6` | 04:00-10:00 | Seguimiento trades abiertos |
| `30 19 * * 5` | 21:30 viernes | Señales E2/E3 semanales |
| `0 20 * * 1-5` | 22:00 | Resumen diario |

---

## Consultas útiles en Supabase

```sql
-- Ver resumen por estrategia
SELECT * FROM resumen_estrategias;

-- Ver trades abiertos ahora mismo
SELECT * FROM trades WHERE estado = 'ABIERTO';

-- Ver últimos 10 trades cerrados
SELECT estrategia, direccion, resultado_usd, motivo_cierre, fecha_open
FROM trades_recientes LIMIT 10;

-- Neto total del paper trading
SELECT SUM(resultado_usd) AS neto_total FROM trades WHERE estado = 'CERRADO';
```

---

## Estructura de archivos

```
grain-bot/
├── src/
│   ├── bot.py           # Script principal
│   ├── config.py        # Parámetros de las estrategias
│   ├── data.py          # Descarga de datos (yfinance)
│   ├── indicators.py    # BB, ADX, ATR, señales
│   ├── database.py      # Operaciones Supabase
│   └── alerts.py        # Alertas Telegram
├── .github/
│   └── workflows/
│       └── bot.yml      # Scheduler GitHub Actions
├── supabase_schema.sql  # Crear tablas en Supabase
├── requirements.txt
└── README.md
```

---

## Nota sobre el rollover de contratos

Los contratos de futuros vencen periódicamente:
- **Maíz (ZC):** Mar, May, Jul, Sep, Dic
- **Soja (ZS):** Ene, Mar, May, Jul, Ago, Sep, Nov

El bot avisa por Telegram cuando un contrato está a **10 días del vencimiento**.
En ese momento hay que hacer el roll manualmente en tu plataforma de paper trading
(cerrar el contrato actual, abrir el siguiente).

---

## ⚠️ Advertencias importantes

- Este bot es solo para **paper trading** (simulación sin dinero real)
- Los resultados pasados no garantizan resultados futuros
- Las señales usan datos de Yahoo Finance que pueden tener errores de rollover
- Antes de operar con dinero real, valida al menos 6 meses de paper trading
- Consulta a un asesor financiero antes de tomar decisiones de inversión
