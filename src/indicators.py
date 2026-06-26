"""
indicators.py — Cálculo de indicadores técnicos
BB, ADX, ATR — misma lógica que usamos en los backtests
"""

import pandas as pd
import numpy as np


def calcular_indicadores(df: pd.DataFrame, bb_periodo: int = 20,
                          adx_periodo: int = 14) -> pd.DataFrame:
    """
    Añade BB, ADX y ATR a un DataFrame OHLC.
    Devuelve el mismo DataFrame con columnas nuevas.
    """
    df = df.copy()
    c = df['Close']
    h = df['High']
    lo = df['Low']

    # ── Bollinger Bands ──
    df['ma']     = c.rolling(bb_periodo).mean()
    df['std']    = c.rolling(bb_periodo).std()
    df['bb_up']  = df['ma'] + 2.0 * df['std']
    df['bb_low'] = df['ma'] - 2.0 * df['std']
    df['bb_mid'] = df['ma']

    # ── True Range y ATR ──
    prev_c = c.shift(1)
    df['tr'] = np.maximum(h - lo,
               np.maximum(abs(h - prev_c), abs(lo - prev_c)))
    df['atr14'] = df['tr'].ewm(alpha=1 / adx_periodo, adjust=False).mean()

    # ── ADX (Wilder) ──
    up   = h - h.shift(1)
    down = lo.shift(1) - lo
    dm_pos = np.where((up > down) & (up > 0), up, 0.0)
    dm_neg = np.where((down > up) & (down > 0), down, 0.0)

    tr_s   = df['tr'].ewm(alpha=1 / adx_periodo, adjust=False).mean()
    dmp_s  = pd.Series(dm_pos, index=df.index).ewm(
                alpha=1 / adx_periodo, adjust=False).mean()
    dmn_s  = pd.Series(dm_neg, index=df.index).ewm(
                alpha=1 / adx_periodo, adjust=False).mean()

    di_pos = 100 * dmp_s / tr_s
    di_neg = 100 * dmn_s / tr_s
    dx     = 100 * abs(di_pos - di_neg) / (di_pos + di_neg)
    df['adx']    = dx.ewm(alpha=1 / adx_periodo, adjust=False).mean()
    df['di_pos'] = di_pos
    df['di_neg'] = di_neg

    # ── ADR (Average Daily Range) ──
    df['rango_dia'] = h - lo
    df['adr10']     = df['rango_dia'].rolling(10).mean()
    df['ratio_adr'] = df['rango_dia'] / df['adr10']

    # ── MA50 ──
    df['ma50'] = c.rolling(50).mean()

    return df.dropna()


def señal_e1(df: pd.DataFrame, cfg: dict) -> bool:
    """
    Evalúa si la última barra tiene señal E1 (SHORT nocturno).
    Retorna True/False.
    """
    if df.empty or len(df) < 2:
        return False

    ultima = df.iloc[-1]
    close  = ultima['Close']
    bb_up  = ultima['bb_up']
    bb_mid = ultima['bb_mid']
    adx    = ultima['adx']
    hora   = df.index[-1].hour

    rec = close - bb_mid

    return (
        close >= bb_up and
        hora in cfg['horas_op'] and
        adx > cfg['adx_min'] and
        rec >= cfg['rec_min']
    )


def señal_e2_e3(df: pd.DataFrame, cfg: dict) -> bool:
    """
    Evalúa si la última barra semanal tiene señal E2/E3 (LONG breakout).
    Retorna True/False.
    """
    if df.empty or len(df) < 2:
        return False

    ultima = df.iloc[-1]
    close  = ultima['Close']
    bb_up  = ultima['bb_up']
    adx    = ultima['adx']

    return (
        close > bb_up and
        adx > cfg['adx_min']
    )


def trailing_stop_activo(precio_actual: float, max_precio: float,
                          trail_cts: float, direccion: str) -> bool:
    """
    Comprueba si el trailing stop se ha activado.
    Para LONG: activo si precio_actual <= max_precio - trail_cts
    Para SHORT: activo si precio_actual >= min_precio + trail_cts
    """
    if direccion == 'LONG':
        return precio_actual <= max_precio - trail_cts
    else:
        return precio_actual >= max_precio + trail_cts


def calcular_size(ratio_adr: float, factor_estacional: float,
                  size_base: float = 1.0) -> float:
    """
    Calcula el tamaño de la posición combinando ADR y estacionalidad.
    """
    if factor_estacional == 0:
        return 0.0
    adr_mult = 1.5 if ratio_adr >= 1.5 else 1.0
    return round(size_base * adr_mult * factor_estacional, 1)
