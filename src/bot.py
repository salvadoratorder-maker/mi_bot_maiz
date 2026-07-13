
"""
bot.py — Script principal del bot de paper trading
Se ejecuta automáticamente via GitHub Actions según el horario configurado

Modos:
  python bot.py --modo señales     → busca señales nuevas
  python bot.py --modo seguimiento → actualiza trades abiertos
  python bot.py --modo resumen     → envía resumen diario
  python bot.py --modo todo        → ejecuta los tres pasos
"""

import argparse
import logging
import sys
import time
from datetime import datetime
import pytz

from config import ESTRATEGIAS, E1, E2, E3, RIESGO, TZ_CHICAGO, TZ_LOCAL
from data import descargar_datos, convertir_zona_horaria, obtener_adr, cerca_de_rollover
from indicators import calcular_indicadores, señal_e1, señal_e2_e3, calcular_size
from database import (save_signal, open_trade, update_trade,
                       close_trade, get_open_trades, get_summary,
                       save_cycle_log, save_price_bars)
from alerts import (alert_signal, alert_close, alert_rollover,
                    alert_daily_summary, alert_error)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# PASO 1 — BUSCAR SEÑALES NUEVAS
# ══════════════════════════════════════════════════════════

def buscar_señales():
    logger.info("=" * 50)
    logger.info("BUSCANDO SEÑALES...")
    logger.info("=" * 50)

    ahora_chicago  = datetime.now(pytz.timezone(TZ_CHICAGO))
    mes_actual     = ahora_chicago.month
    señales_n      = 0
    strategy_logs  = []   # observabilidad por ciclo
    errors         = []

    # ── E1: Maíz SHORT nocturno ──
    logger.info(f"[E1] Evaluando {E1['nombre']}...")
    sl_e1 = {
        'strategy': 'E1', 'ticker': E1['ticker'],
        'signal': False, 'reason': 'sin_señal',
        'close': None, 'bb_up': None, 'bb_mid': None,
        'adx': None, 'adx_min': E1['adx_min'],
        'seasonal_factor': None, 'size': None,
        'adr_ratio': None, 'hora': None,
        'horas_op': E1.get('horas_op'),
    }
    try:
        df_1h = descargar_datos(E1['ticker'], E1['periodo_data'], E1['intervalo'])
        if df_1h.empty:
            sl_e1['reason'] = 'datos_vacios'
        else:
            df_1h  = convertir_zona_horaria(df_1h, TZ_CHICAGO)

            # ── Acumular historico propio de barras horarias ──
            # Guardamos TODAS las barras descargadas (no solo las que dan señal).
            # save_price_bars hace upsert, asi que no duplica lo ya guardado.
            # Con el tiempo esto construye un historico horario propio mas
            # largo que el limite de ~2 anios que da yfinance.
            try:
                n_guardadas = save_price_bars(E1['ticker'], E1['intervalo'], df_1h)
                logger.info(f"[E1] price_bars: {n_guardadas} barras procesadas para histórico propio")
            except Exception as e:
                logger.warning(f"[E1] No se pudo guardar price_bars: {e}")

            df_1h  = calcular_indicadores(df_1h)
            adr    = obtener_adr(E1['ticker'])
            ultima = df_1h.iloc[-1]
            close  = float(ultima['Close'])
            bb_up  = float(ultima['bb_up'])
            bb_mid = float(ultima['bb_mid'])
            adx    = float(ultima['adx'])
            hora   = df_1h.index[-1].hour
            factor = E1['sizing_estacional'].get(mes_actual, 1.0)

            sl_e1.update({
                'close': round(close, 3), 'bb_up': round(bb_up, 3),
                'bb_mid': round(bb_mid, 3), 'adx': round(adx, 2),
                'seasonal_factor': factor, 'adr_ratio': round(adr['ratio'], 3),
                'hora': hora,
            })

            # Diagnóstico detallado del motivo de no-señal
            if factor == 0:
                sl_e1['reason'] = 'factor_estacional_cero'
            elif adx <= E1['adx_min']:
                sl_e1['reason'] = f"adx_bajo ({adx:.1f} <= {E1['adx_min']})"
            elif close < bb_up:
                sl_e1['reason'] = f"precio_fuera_bb (close={close:.3f} < bb_up={bb_up:.3f})"
            elif hora not in E1.get('horas_op', []):
                sl_e1['reason'] = f"hora_fuera_rango (hora={hora} no en {E1.get('horas_op')})"
            elif (close - bb_mid) < E1.get('rec_min', 0):
                sl_e1['reason'] = f"recorrido_insuficiente ({close-bb_mid:.3f} < {E1.get('rec_min')})"

            if señal_e1(df_1h, E1):
                size = calcular_size(adr['ratio'], factor)
                sl_e1['size'] = size
                if size > 0:
                    sl_e1['signal'] = True
                    sl_e1['reason'] = 'señal_detectada'
                    sl_precio = round(close + E1['sl_cts'], 3)
                    rec       = round(close - bb_mid, 3)
                    señal = save_signal(
                        strategy='E1', ticker=E1['ticker'], direction='SHORT',
                        entry_price=close, bb_up=bb_up, bb_mid=bb_mid,
                        adx=adx, range_cts=rec, size=size,
                        seasonal_factor=factor, adr_ratio=adr['ratio'],
                        sl_price=sl_precio,
                    )
                    if señal:
                        open_trade(
                            signal_id=str(señal.get('id', 'paper')),
                            strategy='E1', ticker=E1['ticker'], direction='SHORT',
                            entry=close, sl=sl_precio,
                            trail_cts=E1['sl_cts'], size=size,
                        )
                    alert_signal(
                        estrategia=E1['nombre'], ticker=E1['ticker'],
                        direccion='SHORT', precio=close, sl=sl_precio,
                        size=size, adx=adx, recorrido=rec,
                        factor_estacional=factor,
                    )
                    señales_n += 1
                    logger.info(f"[E1] ✓ Señal SHORT detectada @ {close:.2f}")
                else:
                    sl_e1['reason'] = 'factor_estacional_cero'
                    logger.info(f"[E1] Señal detectada pero factor=0 (mes {mes_actual}) → omitida")
            else:
                logger.info(f"[E1] Sin señal | motivo: {sl_e1['reason']}")

    except Exception as e:
        sl_e1['reason'] = f"error: {e}"
        errors.append(f"E1: {e}")
        logger.error(f"[E1] Error: {e}")
        alert_error(f"E1 error en señales: {e}")

    strategy_logs.append(sl_e1)

    # ── E2: Maíz LONG semanal ──
    logger.info(f"[E2] Evaluando {E2['nombre']}...")
    sl_e2 = {
        'strategy': 'E2', 'ticker': E2['ticker'],
        'signal': False, 'reason': 'sin_señal',
        'close': None, 'bb_up': None, 'bb_mid': None,
        'adx': None, 'adx_min': E2['adx_min'],
        'seasonal_factor': None, 'size': None, 'adr_ratio': None,
    }
    try:
        df_1w = descargar_datos(E2['ticker'], E2['periodo_data'], E2
