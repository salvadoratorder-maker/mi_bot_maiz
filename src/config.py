"""
config.py — Parámetros del sistema de trading de granos
Todas las constantes están aquí. Para cambiar algo, solo toca este archivo.
"""

# ══════════════════════════════════════════════════════════
# ESTRATEGIA 1 — Maíz SHORT nocturno (barras 1h)
# ══════════════════════════════════════════════════════════
E1 = {
    'nombre':       'Maíz SHORT nocturno',
    'ticker':       'ZC=F',
    'intervalo':    '1h',
    'periodo_data': '2y',
    'direccion':    'SHORT',
    'tick':         10.0,        # $10 por centavo (mini YC)
    'bb_periodo':   20,
    'bb_desv':      2.0,
    'adx_min':      30,
    'rec_min':      3.0,         # centavos mínimos entrada - BB_mid
    'sl_cts':       8.0,         # stop loss fijo en centavos
    'max_barras':   20,          # máximo barras hasta cierre forzado
    'horas_op':     list(range(18, 24)) + list(range(0, 8)),  # Chicago
    # Sizing estacional (factor × size base ADR)
    # julio: cambiado 0.0 → 1.0 para observar comportamiento en paper trading
    'sizing_estacional': {
        1: 1.0, 2: 1.0, 3: 1.0, 4: 0.5,
        5: 1.5, 6: 1.5, 7: 1.0, 8: 1.0,
        9: 0.5, 10: 1.0, 11: 1.5, 12: 0.5,
    },
}

# ══════════════════════════════════════════════════════════
# ESTRATEGIA 2 — Maíz LONG breakout semanal
# ══════════════════════════════════════════════════════════
E2 = {
    'nombre':       'Maíz LONG semanal',
    'ticker':       'ZC=F',
    'intervalo':    '1wk',
    'periodo_data': '25y',
    'direccion':    'LONG',
    'tick':         50.0,        # $50 por centavo (contrato estándar ZC)
    'bb_periodo':   20,
    'bb_desv':      2.0,
    'adx_min':      25,
    'trail_atr':    0.5,         # trailing stop = 0.5 × ATR14
    'max_barras':   8,           # máximo semanas hasta cierre forzado
    # Sizing estacional
    # julio: cambiado 0.0 → 1.0 para observar comportamiento en paper trading
    'sizing_estacional': {
        1: 1.5, 2: 1.0, 3: 1.0, 4: 1.5,
        5: 0.5, 6: 0.5, 7: 1.0, 8: 1.0,
        9: 1.5, 10: 1.0, 11: 0.5, 12: 2.0,
    },
}

# ══════════════════════════════════════════════════════════
# ESTRATEGIA 3 — Soja LONG breakout semanal
# ══════════════════════════════════════════════════════════
E3 = {
    'nombre':       'Soja LONG semanal',
    'ticker':       'ZS=F',
    'intervalo':    '1wk',
    'periodo_data': '25y',
    'direccion':    'LONG',
    'tick':         50.0,        # $50 por centavo (contrato estándar ZS)
    'bb_periodo':   20,
    'bb_desv':      2.0,
    'adx_min':      25,
    'trail_atr':    0.5,
    'max_barras':   8,
    # Sizing estacional
    # julio: cambiado 0.0 → 1.0 para observar comportamiento en paper trading
    'sizing_estacional': {
        1: 1.5, 2: 1.5, 3: 1.0, 4: 1.5,
        5: 0.5, 6: 1.0, 7: 1.0, 8: 0.0,
        9: 0.0, 10: 1.5, 11: 1.5, 12: 1.0,
    },
}

ESTRATEGIAS = [E1, E2, E3]

# ══════════════════════════════════════════════════════════
# GESTIÓN DE RIESGO
# ══════════════════════════════════════════════════════════
RIESGO = {
    'pct_max_por_trade': 0.02,   # máximo 2% del capital por trade
    'capital_paper':     50000,  # capital ficticio para paper trading
    'adr_mult_size':     1.5,    # si ADR >= 1.5× media → size × 1.5
}

# ══════════════════════════════════════════════════════════
# CALENDARIOS DE ROLLOVER
# ══════════════════════════════════════════════════════════
ROLLOVER = {
    'ZC=F': {  # Maíz: Mar(H), May(K), Jul(N), Sep(U), Dic(Z)
        'meses_vencimiento': [3, 5, 7, 9, 12],
        'dias_antes_roll':   10,
    },
    'ZS=F': {  # Soja: Ene(F), Mar(H), May(K), Jul(N), Ago(Q), Sep(U), Nov(X)
        'meses_vencimiento': [1, 3, 5, 7, 8, 9, 11],
        'dias_antes_roll':   10,
    },
}

# ══════════════════════════════════════════════════════════
# ZONA HORARIA
# ══════════════════════════════════════════════════════════
TZ_CHICAGO  = 'America/Chicago'
TZ_LOCAL    = 'Europe/Madrid'
