"""
bot.py — Script principal del bot de paper trading
Se ejecuta automáticamente via GitHub Actions según el horario configurado

Modos:
  python bot.py --modo señales    → busca señales nuevas
  python bot.py --modo seguimiento → actualiza trades abiertos
  python bot.py --modo resumen     → envía resumen diario
  python bot.py --modo todo        → ejecuta los tres pasos
"""

import argparse
import logging
import sys
from datetime import datetime
import pytz

# Importar módulos propios
from config import ESTRATEGIAS, E1, E2, E3, RIESGO, TZ_CHICAGO, TZ_LOCAL
from data import descargar_datos, convertir_zona_horaria, obtener_adr, cerca_de_rollover
from indicators import calcular_indicadores, señal_e1, señal_e2_e3, calcular_size
from database import (save_signal, open_trade, update_trade,
                       close_trade, get_open_trades, get_summary)
from alerts import (alert_signal, alert_close, alert_rollover,
                    alert_daily_summary, alert_error)

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# PASO 1 — BUSCAR SEÑALES NUEVAS
# ══════════════════════════════════════════════════════════

def buscar_señales():
    """
    Evalúa las 3 estrategias y registra señales si las hay.
    """
    logger.info("=" * 50)
    logger.info("BUSCANDO SEÑALES...")
    logger.info("=" * 50)

    ahora_chicago = datetime.now(pytz.timezone(TZ_CHICAGO))
    mes_actual = ahora_chicago.month

    señales_encontradas = 0

    # ── E1: Maíz SHORT nocturno ──
    logger.info(f"[E1] Evaluando {E1['nombre']}...")
    try:
        df_1h = descargar_datos(E1['ticker'], E1['periodo_data'], E1['intervalo'])
        if not df_1h.empty:
            df_1h = convertir_zona_horaria(df_1h, TZ_CHICAGO)
            df_1h = calcular_indicadores(df_1h)
            adr   = obtener_adr(E1['ticker'])

            if señal_e1(df_1h, E1):
                ultima = df_1h.iloc[-1]
                factor = E1['sizing_estacional'].get(mes_actual, 1.0)
                size   = calcular_size(adr['ratio'], factor)

                if size > 0:
                    sl_precio = round(float(ultima['Close']) + E1['sl_cts'], 3)
                    rec       = round(float(ultima['Close']) - float(ultima['bb_mid']), 3)

                    señal = save_signal(
                        estrategia='E1', ticker=E1['ticker'],
                        direccion='SHORT',
                        precio_entrada=float(ultima['Close']),
                        bb_up=float(ultima['bb_up']),
                        bb_mid=float(ultima['bb_mid']),
                        adx=float(ultima['adx']),
                        recorrido=rec,
                        size=size,
                        factor_estacional=factor,
                        ratio_adr=adr['ratio'],
                        sl=sl_precio,
                    )

                    if señal:
                        open_trade(
                            señal_id=str(señal.get('id', 'paper')),
                            estrategia='E1', ticker=E1['ticker'],
                            direccion='SHORT',
                            entrada=float(ultima['Close']),
                            sl=sl_precio,
                            trail_cts=E1['sl_cts'],
                            size=size,
                        )

                    alert_signal(
                        estrategia=E1['nombre'],
                        ticker=E1['ticker'], direccion='SHORT',
                        precio=float(ultima['Close']), sl=sl_precio,
                        size=size, adx=float(ultima['adx']),
                        recorrido=rec, factor_estacional=factor,
                    )
                    señales_encontradas += 1
                    logger.info(f"[E1] ✓ Señal SHORT detectada @ {ultima['Close']:.2f}")
                else:
                    logger.info(f"[E1] Señal detectada pero factor estacional=0 (mes {mes_actual}) → omitida")
            else:
                logger.info("[E1] Sin señal")
    except Exception as e:
        logger.error(f"[E1] Error: {e}")
        alert_error(f"E1 error en señales: {e}")

    # ── E2: Maíz LONG semanal ──
    logger.info(f"[E2] Evaluando {E2['nombre']}...")
    try:
        df_1w = descargar_datos(E2['ticker'], E2['periodo_data'], E2['intervalo'])
        if not df_1w.empty:
            df_1w = calcular_indicadores(df_1w)
            adr   = obtener_adr(E2['ticker'])

            if señal_e2_e3(df_1w, E2):
                ultima = df_1w.iloc[-1]
                factor = E2['sizing_estacional'].get(mes_actual, 1.0)
                size   = calcular_size(adr['ratio'], factor)

                if size > 0:
                    trail_cts = round(float(ultima['atr14']) * E2['trail_atr'], 2)
                    sl_precio = round(float(ultima['Close']) - trail_cts, 3)

                    señal = save_signal(
                        estrategia='E2', ticker=E2['ticker'],
                        direccion='LONG',
                        precio_entrada=float(ultima['Close']),
                        bb_up=float(ultima['bb_up']),
                        bb_mid=float(ultima['bb_mid']),
                        adx=float(ultima['adx']),
                        recorrido=round(float(ultima['Close']) - float(ultima['bb_mid']), 2),
                        size=size,
                        factor_estacional=factor,
                        ratio_adr=adr['ratio'],
                        sl=sl_precio,
                    )

                    if señal:
                        open_trade(
                            señal_id=str(señal.get('id', 'paper')),
                            estrategia='E2', ticker=E2['ticker'],
                            direccion='LONG',
                            entrada=float(ultima['Close']),
                            sl=sl_precio,
                            trail_cts=trail_cts,
                            size=size,
                        )

                    alert_signal(
                        estrategia=E2['nombre'],
                        ticker=E2['ticker'], direccion='LONG',
                        precio=float(ultima['Close']), sl=sl_precio,
                        size=size, adx=float(ultima['adx']),
                        recorrido=round(float(ultima['Close']) - float(ultima['bb_mid']), 2),
                        factor_estacional=factor,
                    )
                    señales_encontradas += 1
                    logger.info(f"[E2] ✓ Señal LONG detectada @ {ultima['Close']:.2f}")
                else:
                    logger.info(f"[E2] Factor estacional=0 (mes {mes_actual}) → omitida")
            else:
                logger.info("[E2] Sin señal")
    except Exception as e:
        logger.error(f"[E2] Error: {e}")
        alert_error(f"E2 error en señales: {e}")

    # ── E3: Soja LONG semanal ──
    logger.info(f"[E3] Evaluando {E3['nombre']}...")
    try:
        df_1w = descargar_datos(E3['ticker'], E3['periodo_data'], E3['intervalo'])
        if not df_1w.empty:
            df_1w = calcular_indicadores(df_1w)
            adr   = obtener_adr(E3['ticker'])

            if señal_e2_e3(df_1w, E3):
                ultima = df_1w.iloc[-1]
                factor = E3['sizing_estacional'].get(mes_actual, 1.0)
                size   = calcular_size(adr['ratio'], factor)

                if size > 0:
                    trail_cts = round(float(ultima['atr14']) * E3['trail_atr'], 2)
                    sl_precio = round(float(ultima['Close']) - trail_cts, 3)

                    señal = save_signal(
                        estrategia='E3', ticker=E3['ticker'],
                        direccion='LONG',
                        precio_entrada=float(ultima['Close']),
                        bb_up=float(ultima['bb_up']),
                        bb_mid=float(ultima['bb_mid']),
                        adx=float(ultima['adx']),
                        recorrido=round(float(ultima['Close']) - float(ultima['bb_mid']), 2),
                        size=size,
                        factor_estacional=factor,
                        ratio_adr=adr['ratio'],
                        sl=sl_precio,
                    )

                    if señal:
                        open_trade(
                            señal_id=str(señal.get('id', 'paper')),
                            estrategia='E3', ticker=E3['ticker'],
                            direccion='LONG',
                            entrada=float(ultima['Close']),
                            sl=sl_precio,
                            trail_cts=trail_cts,
                            size=size,
                        )

                    alert_signal(
                        estrategia=E3['nombre'],
                        ticker=E3['ticker'], direccion='LONG',
                        precio=float(ultima['Close']), sl=sl_precio,
                        size=size, adx=float(ultima['adx']),
                        recorrido=round(float(ultima['Close']) - float(ultima['bb_mid']), 2),
                        factor_estacional=factor,
                    )
                    señales_encontradas += 1
                    logger.info(f"[E3] ✓ Señal LONG detectada @ {ultima['Close']:.2f}")
                else:
                    logger.info(f"[E3] Factor estacional=0 (mes {mes_actual}) → omitida")
            else:
                logger.info("[E3] Sin señal")
    except Exception as e:
        logger.error(f"[E3] Error: {e}")
        alert_error(f"E3 error en señales: {e}")

    logger.info(f"Señales encontradas hoy: {señales_encontradas}")
    return señales_encontradas


# ══════════════════════════════════════════════════════════
# PASO 2 — SEGUIMIENTO DE TRADES ABIERTOS
# ══════════════════════════════════════════════════════════

def seguimiento_trades():
    """
    Para cada trade abierto:
    - Actualiza el precio máximo y el trailing stop
    - Cierra si se activa el stop o se supera el tiempo máximo
    - Avisa si hay rollover próximo
    """
    logger.info("=" * 50)
    logger.info("SEGUIMIENTO DE TRADES ABIERTOS...")
    logger.info("=" * 50)

    trades = get_open_trades()
    if not trades:
        logger.info("Sin trades abiertos")
        return

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

        # Precio actual
        try:
            df = descargar_datos(ticker, '5d', '1d')
            if df.empty:
                continue
            precio_actual = float(df['Close'].iloc[-1])
            precio_max_hoy = float(df['High'].iloc[-1])
            precio_min_hoy = float(df['Low'].iloc[-1])
        except Exception as e:
            logger.error(f"Error obteniendo precio para trade {trade_id}: {e}")
            continue

        # Determinar config según estrategia
        cfg = {'E1': E1, 'E2': E2, 'E3': E3}.get(estrategia, E1)
        tick = cfg['tick']
        max_barras = cfg['max_barras']

        # Actualizar máximo precio y trailing stop
        cerrado = False
        motivo = None
        precio_salida = precio_actual
        res_cts = 0.0

        if direccion == 'LONG':
            nuevo_max = max(max_p, precio_max_hoy)
            nuevo_trail = nuevo_max - trail_cts
            # ¿Se activó el trailing?
            if precio_min_hoy <= nuevo_trail:
                precio_salida = nuevo_trail
                res_cts = nuevo_trail - entrada
                motivo = 'TRAIL'
                cerrado = True
            # ¿Tiempo máximo?
            elif barras + 1 >= max_barras:
                precio_salida = precio_actual
                res_cts = precio_actual - entrada
                motivo = 'TIEMPO'
                cerrado = True

        elif direccion == 'SHORT':
            # Para SHORT: max_precio es en realidad el mínimo alcanzado
            nuevo_max = min(max_p, precio_min_hoy) if barras > 0 else max_p
            nuevo_trail = nuevo_max + trail_cts
            # ¿Se activó el stop?
            if precio_max_hoy >= nuevo_trail:
                precio_salida = nuevo_trail
                res_cts = entrada - nuevo_trail
                motivo = 'SL' if res_cts < 0 else 'TRAIL'
                cerrado = True
            # ¿Llegó al TP (BB_mid)?
            elif barras + 1 >= max_barras:
                res_cts = entrada - precio_actual
                motivo = 'TIEMPO'
                cerrado = True
                precio_salida = precio_actual

        if cerrado:
            resultado_usd = round(res_cts * tick * trade['size'], 2)
            close_trade(trade_id, precio_salida, motivo, res_cts, resultado_usd)
            alert_close(estrategia, ticker, motivo, res_cts,
                          resultado_usd, entrada, precio_salida)
            logger.info(f"Trade {trade_id} cerrado: {motivo} | {resultado_usd:+.2f}$")
        else:
            # Actualizar estado
            update_trade(trade_id, nuevo_max, nuevo_max - trail_cts
                              if direccion == 'LONG' else nuevo_max + trail_cts,
                              barras + 1)
            logger.info(f"Trade {trade_id} actualizado: precio={precio_actual:.2f} | barras={barras+1}")

        # Comprobar rollover
        roll_info = cerca_de_rollover(ticker)
        if roll_info['proximidad']:
            alert_rollover(ticker, roll_info['dias_restantes'],
                            roll_info['fecha_venc'])
            logger.warning(f"⚠️  ROLLOVER en {roll_info['dias_restantes']} días para {ticker}")


# ══════════════════════════════════════════════════════════
# PASO 3 — RESUMEN DIARIO
# ══════════════════════════════════════════════════════════

def enviar_resumen():
    """
    Calcula y envía el resumen del paper trading.
    """
    logger.info("=" * 50)
    logger.info("ENVIANDO RESUMEN DIARIO...")
    logger.info("=" * 50)

    resumen = get_summary()
    alert_daily_summary(resumen)
    logger.info(f"Resumen: {resumen}")


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Bot de paper trading de granos')
    parser.add_argument('--modo', choices=['señales', 'seguimiento', 'resumen', 'todo'],
                        default='todo', help='Modo de ejecución')
    args = parser.parse_args()

    ahora = datetime.now(pytz.timezone(TZ_LOCAL))
    logger.info(f"Bot iniciado | Modo: {args.modo} | {ahora.strftime('%d/%m/%Y %H:%M')} (Madrid)")

    try:
        if args.modo in ('señales', 'todo'):
            buscar_señales()

        if args.modo in ('seguimiento', 'todo'):
            seguimiento_trades()

        if args.modo in ('resumen', 'todo'):
            enviar_resumen()

    except Exception as e:
        logger.error(f"Error crítico: {e}")
        alert_error(f"Error crítico en bot: {e}")
        sys.exit(1)

    logger.info("Bot finalizado correctamente")


if __name__ == '__main__':
    main()
