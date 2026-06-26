"""
alerts.py — Envío de alertas por Telegram
Necesitas crear un bot en @BotFather y obtener el token y chat_id
"""

import os
import logging
import requests
from datetime import datetime
import pytz

from config import TZ_LOCAL

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def _enviar(mensaje: str) -> bool:
    """
    Envía un mensaje de texto al chat de Telegram configurado.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"[SIN TELEGRAM] {mensaje}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id':    TELEGRAM_CHAT_ID,
        'text':       mensaje,
        'parse_mode': 'HTML',
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("Alerta Telegram enviada")
            return True
        else:
            logger.warning(f"Telegram error {r.status_code}: {r.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"Error enviando Telegram: {e}")
        return False


def alert_signal(estrategia: str, ticker: str, direccion: str,
                  precio: float, sl: float, size: float,
                  adx: float, recorrido: float,
                  factor_estacional: float) -> bool:
    """
    Alerta cuando se detecta una señal de entrada.
    """
    ahora = datetime.now(pytz.timezone(TZ_LOCAL)).strftime('%d/%m %H:%M')
    emoji = '🔴' if direccion == 'SHORT' else '🟢'

    msg = (
        f"{emoji} <b>SEÑAL {direccion} — {estrategia}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Ticker : {ticker}\n"
        f"💲 Entrada : {precio:.2f} cts\n"
        f"🛑 Stop   : {sl:.2f} cts\n"
        f"📏 Recorr.: {recorrido:.2f} cts\n"
        f"📊 ADX    : {adx:.1f}\n"
        f"📦 Size   : ×{size}\n"
        f"📅 Factor : ×{factor_estacional}\n"
        f"🕐 Hora   : {ahora}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>Paper trading — sin dinero real</i>"
    )
    return _enviar(msg)


def alert_close(estrategia: str, ticker: str, motivo: str,
                   resultado_cts: float, resultado_usd: float,
                   entrada: float, salida: float) -> bool:
    """
    Alerta cuando se cierra un trade (TP, SL, trail o tiempo).
    """
    ahora = datetime.now(pytz.timezone(TZ_LOCAL)).strftime('%d/%m %H:%M')
    emoji_res = '✅' if resultado_usd > 0 else '❌'
    emoji_mot = {
        'TP': '🎯', 'SL': '🛑', 'TRAIL': '📉', 'TIEMPO': '⏱️', 'ROLL': '🔄'
    }.get(motivo, '❓')

    msg = (
        f"{emoji_res} <b>CIERRE {motivo} — {estrategia}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Ticker  : {ticker}\n"
        f"{emoji_mot} Motivo  : {motivo}\n"
        f"💲 Entrada : {entrada:.2f} cts\n"
        f"💲 Salida  : {salida:.2f} cts\n"
        f"📈 Resultado: {resultado_cts:+.2f} cts\n"
        f"💵 USD     : {resultado_usd:+.2f}$\n"
        f"🕐 Hora    : {ahora}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>Paper trading — sin dinero real</i>"
    )
    return _enviar(msg)


def alert_rollover(ticker: str, dias_restantes: int,
                     fecha_venc: str) -> bool:
    """
    Alerta cuando un contrato está próximo al vencimiento.
    """
    msg = (
        f"⚠️ <b>ROLLOVER PRÓXIMO</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 Contrato : {ticker}\n"
        f"📅 Vence    : {fecha_venc}\n"
        f"⏳ Quedan   : {dias_restantes} días\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Cerrar posición y abrir en el siguiente contrato."
    )
    return _enviar(msg)


def alert_daily_summary(resumen: dict) -> bool:
    """
    Resumen diario del estado del paper trading.
    """
    if not resumen or resumen.get('trades', 0) == 0:
        return _enviar("📊 <b>Resumen diario</b>\nSin trades cerrados aún.")

    ahora = datetime.now(pytz.timezone(TZ_LOCAL)).strftime('%d/%m/%Y')
    neto  = resumen.get('neto', 0)
    emoji = '📈' if neto >= 0 else '📉'

    msg = (
        f"{emoji} <b>Resumen paper trading — {ahora}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📊 Trades  : {resumen.get('trades', 0)}"
        f" ({resumen.get('wins', 0)}W / {resumen.get('losses', 0)}L)\n"
        f"🎯 Win Rate: {resumen.get('wr', 0)}%\n"
        f"⚖️  Prof.F. : {resumen.get('pf', 0)}\n"
        f"💵 Neto    : {neto:+.2f}$\n"
        f"💚 Media+  : {resumen.get('media_w', 0):.2f}$\n"
        f"🔴 Media-  : {resumen.get('media_l', 0):.2f}$\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>Paper trading — sin dinero real</i>"
    )
    return _enviar(msg)


def alert_error(mensaje: str) -> bool:
    """
    Alerta de error técnico del bot.
    """
    return _enviar(f"🚨 <b>ERROR BOT</b>\n{mensaje}")
