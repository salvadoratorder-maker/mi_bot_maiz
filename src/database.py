"""
database.py — Operaciones con Supabase (PostgreSQL)
Tablas: signals, trades, bot_logs, price_bars
"""

import os
import logging
from datetime import datetime
from typing import Optional
import pytz

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    SUPABASE_OK = True
except ImportError:
    SUPABASE_OK = False
    logger.warning("supabase-py no instalado — modo sin base de datos")


def get_client() -> Optional[object]:
    if not SUPABASE_OK:
        return None
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        logger.warning("SUPABASE_URL o SUPABASE_KEY no configurados")
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Error conectando a Supabase: {e}")
        return None


# ══════════════════════════════════════════════════════════
# SIGNALS
# ══════════════════════════════════════════════════════════

def save_signal(strategy, ticker, direction, entry_price, bb_up, bb_mid,
                adx, range_cts, size, seasonal_factor, adr_ratio,
                sl_price, notes='') -> Optional[dict]:
    client = get_client()
    data = {
        'created_at':      datetime.now(pytz.UTC).isoformat(),
        'strategy':        strategy,
        'ticker':          ticker,
        'direction':       direction,
        'entry_price':     round(entry_price, 3),
        'bb_up':           round(bb_up, 3),
        'bb_mid':          round(bb_mid, 3),
        'adx':             round(adx, 2),
        'range_cts':       round(range_cts, 3),
        'size':            size,
        'seasonal_factor': seasonal_factor,
        'adr_ratio':       round(adr_ratio, 3),
        'sl_price':        round(sl_price, 3),
        'status':          'OPEN',
        'notes':           notes,
    }
    if client is None:
        logger.info(f"[NO DB] Signal: {strategy} {direction} {ticker} @ {entry_price}")
        return data
    try:
        res = client.table('signals').insert(data).execute()
        logger.info(f"Signal saved: {strategy} {direction} {ticker} @ {entry_price}")
        return res.data[0] if res.data else data
    except Exception as e:
        logger.error(f"Error saving signal: {e}")
        return None


# ══════════════════════════════════════════════════════════
# TRADES
# ══════════════════════════════════════════════════════════

def open_trade(signal_id, strategy, ticker, direction,
               entry, sl, trail_cts, size) -> Optional[dict]:
    client = get_client()
    data = {
        'signal_id':     signal_id,
        'opened_at':     datetime.now(pytz.UTC).isoformat(),
        'strategy':      strategy,
        'ticker':        ticker,
        'direction':     direction,
        'entry_price':   round(entry, 3),
        'sl_initial':    round(sl, 3),
        'trail_cts':     round(trail_cts, 3),
        'max_price':     round(entry, 3),
        'trail_current': round(sl, 3),
        'size':          size,
        'bars':          0,
        'status':        'OPEN',
    }
    if client is None:
        logger.info(f"[NO DB] Trade opened: {strategy} {direction} {ticker} @ {entry}")
        return data
    try:
        res = client.table('trades').insert(data).execute()
        logger.info(f"Trade opened: {strategy} {direction} {ticker} @ {entry}")
        return res.data[0] if res.data else data
    except Exception as e:
        logger.error(f"Error opening trade: {e}")
        return None


def update_trade(trade_id, max_price, trail_current, bars) -> bool:
    client = get_client()
    data = {
        'max_price':     round(max_price, 3),
        'trail_current': round(trail_current, 3),
        'bars':          bars,
    }
    if client is None:
        logger.info(f"[NO DB] Update trade {trade_id}: bars={bars}")
        return True
    try:
        client.table('trades').update(data).eq('id', trade_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating trade {trade_id}: {e}")
        return False


def close_trade(trade_id, exit_price, reason, result_cts, result_usd) -> bool:
    client = get_client()
    data = {
        'closed_at':    datetime.now(pytz.UTC).isoformat(),
        'exit_price':   round(exit_price, 3),
        'close_reason': reason,
        'result_cts':   round(result_cts, 3),
        'result_usd':   round(result_usd, 2),
        'status':       'CLOSED',
    }
    if client is None:
        logger.info(f"[NO DB] Close trade {trade_id}: {reason} {result_usd:+.2f}$")
        return True
    try:
        client.table('trades').update(data).eq('id', trade_id).execute()
        logger.info(f"Trade closed: {reason} | {result_usd:+.2f}$")
        return True
    except Exception as e:
        logger.error(f"Error closing trade {trade_id}: {e}")
        return False


def get_open_trades() -> list:
    client = get_client()
    if client is None:
        return []
    try:
        res = client.table('trades').select('*').eq('status', 'OPEN').execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Error getting open trades: {e}")
        return []


def get_summary() -> dict:
    client = get_client()
    if client is None:
        return {}
    try:
        res = client.table('trades').select('*').eq('status', 'CLOSED').execute()
        trades = res.data or []
        if not trades:
            return {'trades': 0, 'message': 'No closed trades yet'}
        wins = [t for t in trades if t['result_usd'] > 0]
        loss = [t for t in trades if t['result_usd'] <= 0]
        tg   = sum(t['result_usd'] for t in wins)
        tp   = sum(abs(t['result_usd']) for t in loss)
        neto = round(tg - tp, 2)

        # Por estrategia
        by_strategy = {}
        for t in trades:
            s = t['strategy']
            if s not in by_strategy:
                by_strategy[s] = {'trades': 0, 'wins': 0, 'net': 0.0}
            by_strategy[s]['trades'] += 1
            by_strategy[s]['net']    += t['result_usd']
            if t['result_usd'] > 0:
                by_strategy[s]['wins'] += 1

        return {
            'trades':      len(trades),
            'wins':        len(wins),
            'losses':      len(loss),
            'wr':          round(len(wins) / len(trades) * 100, 1),
            'pf':          round(tg / tp, 2) if tp > 0 else 999,
            'net':         neto,
            'avg_win':     round(tg / len(wins), 2) if wins else 0,
            'avg_loss':    round(-tp / len(loss), 2) if loss else 0,
            'by_strategy': by_strategy,
        }
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return {}


# ══════════════════════════════════════════════════════════
# PRICE BARS — historico propio acumulado con el tiempo
# ══════════════════════════════════════════════════════════

def save_price_bars(ticker: str, interval: str, df) -> int:
    """
    Guarda en price_bars todas las barras de un DataFrame OHLCV
    (indice = timestamp de la barra). Usa upsert sobre
    (ticker, interval, bar_time) para no duplicar si el bot
    vuelve a descargar barras ya vistas.

    Retorna el numero de barras que se intentaron guardar.
    """
    client = get_client()
    if df is None or df.empty:
        return 0

    rows = []
    for ts, row in df.iterrows():
        try:
            rows.append({
                'ticker':       ticker,
                'bar_interval': interval,
                'bar_time':     ts.isoformat(),
                'open':     round(float(row['Open']), 3),
                'high':     round(float(row['High']), 3),
                'low':      round(float(row['Low']), 3),
                'close':    round(float(row['Close']), 3),
                'volume':   int(row['Volume']) if not pd_isna(row.get('Volume')) else None,
            })
        except Exception as e:
            logger.warning(f"Fila descartada al preparar price_bars: {e}")

    if not rows:
        return 0

    if client is None:
        logger.info(f"[NO DB] {len(rows)} barras de {ticker} {interval} listas (no guardadas, sin cliente)")
        return len(rows)

    try:
        # upsert: si (ticker, interval, bar_time) ya existe, lo ignora/actualiza
        # el flag on_conflict requiere el constraint UNIQUE creado en el SQL
        client.table('price_bars').upsert(
            rows, on_conflict='ticker,bar_interval,bar_time'
        ).execute()
        logger.info(f"price_bars: {len(rows)} barras de {ticker} {interval} guardadas/actualizadas")
        return len(rows)
    except Exception as e:
        logger.error(f"Error guardando price_bars ({ticker} {interval}): {e}")
        return 0


def pd_isna(value) -> bool:
    """Helper minimo para no importar pandas solo para esto."""
    try:
        return value is None or value != value  # NaN != NaN
    except Exception:
        return value is None


# ══════════════════════════════════════════════════════════
# CYCLE LOG — observabilidad por ciclo
# ══════════════════════════════════════════════════════════

def save_cycle_log(mode: str, strategy_logs: list, signals_n: int,
                   open_trades_n: int, errors: list = None,
                   duration_s: float = 0.0) -> bool:
    """
    Guarda en bot_logs el detalle de un ciclo de ejecución.

    strategy_logs: lista de dicts con el detalle de cada estrategia evaluada:
        {
          'strategy':        'E1',
          'ticker':          'ZC=F',
          'signal':          True/False,
          'reason':          'sin_señal' | 'adx_bajo' | 'precio_fuera_bb' |
                             'factor_estacional_cero' | 'datos_vacios' |
                             'error' | 'señal_detectada',
          'close':           float o None,
          'bb_up':           float o None,
          'bb_mid':          float o None,
          'adx':             float o None,
          'adx_min':         float o None,
          'seasonal_factor': float o None,
          'size':            float o None,
          'adr_ratio':       float o None,
          'hora':            int o None,    # solo E1
          'horas_op':        list o None,   # solo E1
        }
    """
    import json

    client = get_client()
    data = {
        'created_at':    datetime.now(pytz.UTC).isoformat(),
        'mode':          mode,
        'signals_n':     signals_n,
        'trades_n':      open_trades_n,
        'errors':        json.dumps(errors or []),
        'duration_s':    round(duration_s, 2),
    }

    # Loguear siempre en consola para que GitHub Actions lo capture
    logger.info("=" * 50)
    logger.info(f"CYCLE LOG | modo={mode} señales={signals_n} trades_abiertos={open_trades_n}")
    for sl in strategy_logs:
        if sl['signal']:
            logger.info(
                f"  [{sl['strategy']}] ✓ SEÑAL | {sl['ticker']} "
                f"close={sl.get('close')} bb_up={sl.get('bb_up')} "
                f"adx={sl.get('adx'):.1f} size={sl.get('size')} "
                f"factor={sl.get('seasonal_factor')}"
            )
        else:
            logger.info(
                f"  [{sl['strategy']}] ✗ SIN SEÑAL | motivo={sl['reason']} | "
                f"close={sl.get('close')} bb_up={sl.get('bb_up')} "
                f"adx={sl.get('adx')} adx_min={sl.get('adx_min')} "
                f"factor={sl.get('seasonal_factor')} "
                + (f"hora={sl.get('hora')} horas_op={sl.get('horas_op')}"
                   if sl['strategy'] == 'E1' else "")
            )
    if errors:
        for err in errors:
            logger.warning(f"  ERROR: {err}")
    logger.info("=" * 50)

    # Guardar en Supabase
    if client is None:
        return True
    try:
        client.table('bot_logs').insert(data).execute()
        return True
    except Exception as e:
        logger.error(f"Error saving cycle log: {e}")
        return False
