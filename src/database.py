"""
database.py — Operaciones con Supabase (PostgreSQL)
Tablas: signals, trades, bot_logs (sin tildes ni caracteres especiales)
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
        'signal_id':    signal_id,
        'opened_at':    datetime.now(pytz.UTC).isoformat(),
        'strategy':     strategy,
        'ticker':       ticker,
        'direction':    direction,
        'entry_price':  round(entry, 3),
        'sl_initial':   round(sl, 3),
        'trail_cts':    round(trail_cts, 3),
        'max_price':    round(entry, 3),
        'trail_current':round(sl, 3),
        'size':         size,
        'bars':         0,
        'status':       'OPEN',
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
        wins  = [t for t in trades if t['result_usd'] > 0]
        loss  = [t for t in trades if t['result_usd'] <= 0]
        tg    = sum(t['result_usd'] for t in wins)
        tp    = sum(abs(t['result_usd']) for t in loss)
        neto  = round(tg - tp, 2)
        return {
            'trades':  len(trades),
            'wins':    len(wins),
            'losses':  len(loss),
            'wr':      round(len(wins) / len(trades) * 100, 1),
            'pf':      round(tg / tp, 2) if tp > 0 else 999,
            'net':     neto,
            'avg_win': round(tg / len(wins), 2) if wins else 0,
            'avg_loss':round(-tp / len(loss), 2) if loss else 0,
        }
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return {}
