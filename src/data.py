"""
data.py — Descarga de datos de mercado via yfinance
Incluye detección de proximidad a rollover
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import logging

from config import TZ_CHICAGO, ROLLOVER

logger = logging.getLogger(__name__)


def descargar_datos(ticker: str, periodo: str, intervalo: str) -> pd.DataFrame:
    """
    Descarga datos OHLCV de yfinance.
    Limpia columnas MultiIndex si existen.
    """
    try:
        df = yf.download(ticker, period=periodo, interval=intervalo,
                         auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df = df.astype(float).dropna()
        logger.info(f"Descargado {ticker} {intervalo}: {len(df)} barras")
        return df
    except Exception as e:
        logger.error(f"Error descargando {ticker}: {e}")
        return pd.DataFrame()


def convertir_zona_horaria(df: pd.DataFrame,
                            tz_destino: str = TZ_CHICAGO) -> pd.DataFrame:
    """
    Convierte el índice del DataFrame a la zona horaria deseada.
    """
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert(tz_destino)
    return df


def obtener_adr(ticker: str) -> dict:
    """
    Calcula el ADR (Average Daily Range) actual.
    Retorna dict con adr_actual, adr10 y ratio.
    """
    df = descargar_datos(ticker, '30d', '1d')
    if df.empty:
        return {'adr_actual': 0, 'adr10': 0, 'ratio': 1.0}

    df['rango'] = df['High'] - df['Low']
    adr10 = df['rango'].rolling(10).mean().iloc[-1]
    adr_actual = df['rango'].iloc[-1]
    ratio = adr_actual / adr10 if adr10 > 0 else 1.0

    return {
        'adr_actual': round(float(adr_actual), 2),
        'adr10':      round(float(adr10), 2),
        'ratio':      round(float(ratio), 3),
    }


def cerca_de_rollover(ticker: str, dias_margen: int = None) -> dict:
    """
    Comprueba si el contrato está próximo al vencimiento.
    Retorna dict con info del rollover.
    """
    if ticker not in ROLLOVER:
        return {'proximidad': False, 'dias_restantes': None, 'accion': None}

    cfg_roll = ROLLOVER[ticker]
    if dias_margen is None:
        dias_margen = cfg_roll['dias_antes_roll']

    hoy = datetime.now(pytz.timezone(TZ_CHICAGO))
    meses_venc = cfg_roll['meses_vencimiento']

    # Encontrar el próximo mes de vencimiento
    mes_actual = hoy.month
    año_actual = hoy.year

    proximo_venc = None
    for mes in sorted(meses_venc):
        if mes > mes_actual:
            proximo_venc = datetime(año_actual, mes, 1,
                                     tzinfo=pytz.timezone(TZ_CHICAGO))
            break
        elif mes == mes_actual:
            # Vencimiento este mes — calcular día exacto
            # (último día hábil del mes = aprox día 20-22)
            proximo_venc = datetime(año_actual, mes, 20,
                                     tzinfo=pytz.timezone(TZ_CHICAGO))
            break

    if proximo_venc is None:
        # El siguiente es en el primer mes del año siguiente
        proximo_venc = datetime(año_actual + 1, meses_venc[0], 1,
                                 tzinfo=pytz.timezone(TZ_CHICAGO))

    dias_restantes = (proximo_venc - hoy).days
    proximidad = dias_restantes <= dias_margen

    return {
        'proximidad':      proximidad,
        'dias_restantes':  dias_restantes,
        'fecha_venc':      proximo_venc.strftime('%Y-%m-%d'),
        'accion':          'HACER ROLL' if proximidad else None,
    }


def precio_actual(ticker: str) -> float:
    """
    Retorna el último precio de cierre disponible.
    """
    df = descargar_datos(ticker, '5d', '1d')
    if df.empty:
        return 0.0
    return round(float(df['Close'].iloc[-1]), 2)
