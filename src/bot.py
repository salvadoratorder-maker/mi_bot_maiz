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
        df_1w = descargar_datos(E2['ticker'], E2['periodo_data'], E2['intervalo'])
        if df_1w.empty:
            sl_e2['reason'] = 'datos_vacios'
        else:
            df_1w  = calcular_indicadores(df_1w)
            adr    = obtener_adr(E2['ticker'])
            ultima = df_1w.iloc[-1]
            close  = float(ultima['Close'])
            bb_up  = float(ultima['bb_up'])
            bb_mid = float(ultima['bb_mid'])
            adx    = float(ultima['adx'])
            factor = E2['sizing_estacional'].get(mes_actual, 1.0)

            sl_e2.update({
                'close': round(close, 3), 'bb_up': round(bb_up, 3),
                'bb_mid': round(bb_mid, 3), 'adx': round(adx, 2),
                'seasonal_factor': factor, 'adr_ratio': round(adr['ratio'], 3),
            })

            if factor == 0:
                sl_e2['reason'] = 'factor_estacional_cero'
            elif adx <= E2['adx_min']:
                sl_e2['reason'] = f"adx_bajo ({adx:.1f} <= {E2['adx_min']})"
            elif close <= bb_up:
                sl_e2['reason'] = f"precio_fuera_bb (close={close:.3f} <= bb_up={bb_up:.3f})"

            if señal_e2_e3(df_1w, E2):
                size = calcular_size(adr['ratio'], factor)
                sl_e2['size'] = size
                if size > 0:
                    sl_e2['signal'] = True
                    sl_e2['reason'] = 'señal_detectada'
                    trail_cts = round(float(ultima['atr14']) * E2['trail_atr'], 2)
                    sl_precio = round(close - trail_cts, 3)
                    rec       = round(close - bb_mid, 2)
                    señal = save_signal(
                        strategy='E2', ticker=E2['ticker'], direction='LONG',
                        entry_price=close, bb_up=bb_up, bb_mid=bb_mid,
                        adx=adx, range_cts=rec, size=size,
                        seasonal_factor=factor, adr_ratio=adr['ratio'],
                        sl_price=sl_precio,
                    )
                    if señal:
                        open_trade(
                            signal_id=str(señal.get('id', 'paper')),
                            strategy='E2', ticker=E2['ticker'], direction='LONG',
                            entry=close, sl=sl_precio,
                            trail_cts=trail_cts, size=size,
                        )
                    alert_signal(
                        estrategia=E2['nombre'], ticker=E2['ticker'],
                        direccion='LONG', precio=close, sl=sl_precio,
                        size=size, adx=adx, recorrido=rec,
                        factor_estacional=factor,
                    )
                    señales_n += 1
                    logger.info(f"[E2] ✓ Señal LONG detectada @ {close:.2f}")
                else:
                    sl_e2['reason'] = 'factor_estacional_cero'
                    logger.info(f"[E2] Factor=0 (mes {mes_actual}) → omitida")
            else:
                logger.info(f"[E2] Sin señal | motivo: {sl_e2['reason']}")

    except Exception as e:
        sl_e2['reason'] = f"error: {e}"
        errors.append(f"E2: {e}")
        logger.error(f"[E2] Error: {e}")
        alert_error(f"E2 error en señales: {e}")

    strategy_logs.append(sl_e2)

    # ── E3: Soja LONG semanal ──
    logger.info(f"[E3] Evaluando {E3['nombre']}...")
    sl_e3 = {
        'strategy': 'E3', 'ticker': E3['ticker'],
        'signal': False, 'reason': 'sin_señal',
        'close': None, 'bb_up': None, 'bb_mid': None,
        'adx': None, 'adx_min': E3['adx_min'],
        'seasonal_factor': None, 'size': None, 'adr_ratio': None,
    }
    try:
        df_1w = descargar_datos(E3['ticker'], E3['periodo_data'], E3['intervalo'])
        if df_1w.empty:
            sl_e3['reason'] = 'datos_vacios'
        else:
            df_1w  = calcular_indicadores(df_1w)
            adr    = obtener_adr(E3['ticker'])
            ultima = df_1w.iloc[-1]
            close  = float(ultima['Close'])
            bb_up  = float(ultima['bb_up'])
            bb_mid = float(ultima['bb_mid'])
            adx    = float(ultima['adx'])
            factor = E3['sizing_estacional'].get(mes_actual, 1.0)

            sl_e3.update({
                'close': round(close, 3), 'bb_up': round(bb_up, 3),
                'bb_mid': round(bb_mid, 3), 'adx': round(adx, 2),
                'seasonal_factor': factor, 'adr_ratio': round(adr['ratio'], 3),
            })

            if factor == 0:
                sl_e3['reason'] = 'factor_estacional_cero'
            elif adx <= E3['adx_min']:
                sl_e3['reason'] = f"adx_bajo ({adx:.1f} <= {E3['adx_min']})"
            elif close <= bb_up:
                sl_e3['reason'] = f"precio_fuera_bb (close={close:.3f} <= bb_up={bb_up:.3f})"

            if señal_e2_e3(df_1w, E3):
                size = calcular_size(adr['ratio'], factor)
                sl_e3['size'] = size
                if size > 0:
                    sl_e3['signal'] = True
                    sl_e3['reason'] = 'señal_detectada'
                    trail_cts = round(float(ultima['atr14']) * E3['trail_atr'], 2)
                    sl_precio = round(close - trail_cts, 3)
                    rec       = round(close - bb_mid, 2)
                    señal = save_signal(
                        strategy='E3', ticker=E3['ticker'], direction='LONG',
                        entry_price=close, bb_up=bb_up, bb_mid=bb_mid,
                        adx=adx, range_cts=rec, size=size,
                        seasonal_factor=factor, adr_ratio=adr['ratio'],
                        sl_price=sl_precio,
                    )
                    if señal:
                        open_trade(
                            signal_id=str(señal.get('id', 'paper')),
                            strategy='E3', ticker=E3['ticker'], direction='LONG',
                            entry=close, sl=sl_precio,
                            trail_cts=trail_cts, size=size,
                        )
                    alert_signal(
                        estrategia=E3['nombre'], ticker=E3['ticker'],
                        direccion='LONG', precio=close, sl=sl_precio,
                        size=size, adx=adx, recorrido=rec,
                        factor_estacional=factor,
                    )
                    señales_n += 1
                    logger.info(f"[E3] ✓ Señal LONG detectada @ {close:.2f}")
                else:
                    sl_e3['reason'] = 'factor_estacional_cero'
                    logger.info(f"[E3] Factor=0 (mes {mes_actual}) → omitida")
            else:
                logger.info(f"[E3] Sin señal | motivo: {sl_e3['reason']}")

    except Exception as e:
        sl_e3['reason'] = f"error: {e}"
        errors.append(f"E3: {e}")
        logger.error(f"[E3] Error: {e}")
        alert_error(f"E3 error en señales: {e}")

    strategy_logs.append(sl_e3)

    logger.info(f"Señales encontradas hoy: {señales_n}")
    return señales_n, strategy_logs, errors


# ══════════════════════════════════════════════════════════
# PASO 2 — SEGUIMIENTO DE TRADES ABIERTOS
# ══════════════════════════════════════════════════════════

def seguimiento_trades():
    logger.info("=" * 50)
    logger.info("SEGUIMIENTO DE TRADES ABIERTOS...")
    logger.info("=" * 50)

    trades = get_open_trades()
    if not trades:
        logger.info("Sin trades abiertos")
        return 0

    logger.info(f"Trades abiertos: {len(trades)}")

    for trade in trades:
        ticker     = trade['ticker']
        estrategia = trade['estrategia']
        direccion  = trade['direccion']
        entrada    = trade['precio_entrada']
        trail_cts  = trade['trail_cts']
        max_p      = trade['max_precio']
        barras     = trade['barras']
        trade_id   = str(trade['id'])

        try:
            df = descargar_datos(ticker, '5d', '1d')
            if df.empty:
                continue
            precio_actual  = float(df['Close'].iloc[-1])
            precio_max_hoy = float(df['High'].iloc[-1])
            precio_min_hoy = float(df['Low'].iloc[-1])
        except Exception as e:
            logger.error(f"Error obteniendo precio para trade {trade_id}: {e}")
            continue

        cfg        = {'E1': E1, 'E2': E2, 'E3': E3}.get(estrategia, E1)
        tick       = cfg['tick']
        max_barras = cfg['max_barras']

        cerrado       = False
        motivo        = None
        precio_salida = precio_actual
        res_cts       = 0.0

        if direccion == 'LONG':
            nuevo_max   = max(max_p, precio_max_hoy)
            nuevo_trail = nuevo_max - trail_cts
            if precio_min_hoy <= nuevo_trail:
                precio_salida = nuevo_trail
                res_cts       = nuevo_trail - entrada
                motivo        = 'TRAIL'
                cerrado       = True
            elif barras + 1 >= max_barras:
                precio_salida = precio_actual
                res_cts       = precio_actual - entrada
                motivo        = 'TIEMPO'
                cerrado       = True

        elif direccion == 'SHORT':
            nuevo_max   = min(max_p, precio_min_hoy) if barras > 0 else max_p
            nuevo_trail = nuevo_max + trail_cts
            if precio_max_hoy >= nuevo_trail:
                precio_salida = nuevo_trail
                res_cts       = entrada - nuevo_trail
                motivo        = 'SL' if res_cts < 0 else 'TRAIL'
                cerrado       = True
            elif barras + 1 >= max_barras:
                res_cts       = entrada - precio_actual
                motivo        = 'TIEMPO'
                cerrado       = True
                precio_salida = precio_actual

        if cerrado:
            resultado_usd = round(res_cts * tick * trade['size'], 2)
            close_trade(trade_id, precio_salida, motivo, res_cts, resultado_usd)
            alert_close(estrategia, ticker, motivo, res_cts,
                        resultado_usd, entrada, precio_salida)
            logger.info(f"Trade {trade_id} cerrado: {motivo} | {resultado_usd:+.2f}$")
        else:
            update_trade(
                trade_id, nuevo_max,
                nuevo_max - trail_cts if direccion == 'LONG' else nuevo_max + trail_cts,
                barras + 1,
            )
            logger.info(f"Trade {trade_id} actualizado: precio={precio_actual:.2f} | barras={barras+1}")

        roll_info = cerca_de_rollover(ticker)
        if roll_info['proximidad']:
            alert_rollover(ticker, roll_info['dias_restantes'],
                           roll_info['fecha_venc'])
            logger.warning(f"⚠️  ROLLOVER en {roll_info['dias_restantes']} días para {ticker}")

    return len(trades)


# ══════════════════════════════════════════════════════════
# PASO 3 — RESUMEN DIARIO
# ══════════════════════════════════════════════════════════

def enviar_resumen():
    logger.info("=" * 50)
    logger.info("ENVIANDO RESUMEN DIARIO...")
    logger.info("=" * 50)

    resumen = get_summary()

    # Mostrar métricas por estrategia en el log
    if resumen.get('trades', 0) > 0:
        logger.info(f"GLOBAL | trades={resumen['trades']} WR={resumen['wr']}% "
                    f"PF={resumen['pf']} net={resumen['net']:+.2f}$")
        for s, m in resumen.get('by_strategy', {}).items():
            wr_s = round(m['wins'] / m['trades'] * 100, 1) if m['trades'] > 0 else 0
            logger.info(f"  {s} | trades={m['trades']} WR={wr_s}% net={m['net']:+.2f}$")
    else:
        logger.info("Sin trades cerrados aún")

    alert_daily_summary(resumen)
    logger.info(f"Resumen: {resumen}")


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Bot de paper trading de granos')
    parser.add_argument('--modo',
                        choices=['señales', 'seguimiento', 'resumen', 'todo'],
                        default='todo')
    args = parser.parse_args()

    t0   = time.time()
    ahora = datetime.now(pytz.timezone(TZ_LOCAL))
    logger.info(f"Bot iniciado | Modo: {args.modo} | {ahora.strftime('%d/%m/%Y %H:%M')} (Madrid)")

    strategy_logs = []
    signals_n     = 0
    open_trades_n = 0
    errors        = []

    try:
        if args.modo in ('señales', 'todo'):
            signals_n, strategy_logs, errors = buscar_señales()

        if args.modo in ('seguimiento', 'todo'):
            open_trades_n = seguimiento_trades()

        if args.modo in ('resumen', 'todo'):
            enviar_resumen()

    except Exception as e:
        logger.error(f"Error crítico: {e}")
        errors.append(str(e))
        alert_error(f"Error crítico en bot: {e}")
        sys.exit(1)

    finally:
        # Guardar log del ciclo siempre, incluso si hay error
        duration = round(time.time() - t0, 2)
        save_cycle_log(
            mode=args.modo,
            strategy_logs=strategy_logs,
            signals_n=signals_n,
            open_trades_n=open_trades_n,
            errors=errors,
            duration_s=duration,
        )

    logger.info("Bot finalizado correctamente")


if __name__ == '__main__':
    main()
