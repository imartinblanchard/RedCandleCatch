#!/usr/bin/env python3
"""Registre des univers du labo swing. Chaque univers = une liste de tickers daily à fetcher/tester.

⚠️ ETF = sans biais du survivant. NASDAQ100 = membres ACTUELS (biais du survivant : ce sont les
survivants d'aujourd'hui). On le compense en jugeant RELATIVEMENT (strat vs B&H des mêmes titres) ;
résiduel sur le momentum (les survivants sont les gagnants). À lire comme tel."""

ETF = ['SPY', 'QQQ', 'IWM', 'DIA',
       'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLU', 'XLB', 'XLRE', 'XLC']

# Nasdaq-100 (snapshot membres actuels ~2025 ; l'exactitude de l'index importe peu pour la recherche,
# ce sont tous des grosses capis Nasdaq liquides et volatiles). Le fetch ignore les symboles en erreur.
NASDAQ100 = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'GOOG', 'META', 'AVGO', 'TSLA', 'NFLX',
    'ADBE', 'AMD', 'QCOM', 'TXN', 'INTU', 'CSCO', 'INTC', 'AMAT', 'MU', 'ADI',
    'LRCX', 'KLAC', 'NXPI', 'MRVL', 'MCHP', 'ON', 'ASML', 'PANW', 'CRWD', 'FTNT',
    'ZS', 'DDOG', 'TEAM', 'WDAY', 'SNPS', 'CDNS', 'ADSK', 'MDB', 'PLTR', 'APP',
    'ARM', 'COST', 'PEP', 'SBUX', 'MDLZ', 'MNST', 'KDP', 'KHC', 'CCEP', 'ROST',
    'ORLY', 'LULU', 'MAR', 'ABNB', 'BKNG', 'DASH', 'EA', 'TTWO', 'AMGN', 'ISRG',
    'VRTX', 'GILD', 'REGN', 'DXCM', 'IDXX', 'BIIB', 'MRNA', 'GEHC', 'CMCSA', 'TMUS',
    'CHTR', 'WBD', 'HON', 'LIN', 'CSX', 'PCAR', 'CPRT', 'CTAS', 'PAYX', 'ADP',
    'FAST', 'VRSK', 'CSGP', 'ODFL', 'EXC', 'AEP', 'XEL', 'BKR', 'FANG', 'CDW',
    'CTSH', 'MELI', 'PDD', 'PYPL',
]

# ETF VOLATILS / À LEVIER : thématiques, sectoriels, 3x. Très volatils, liquides, SANS biais du
# survivant (l'ETF gère ses composants). C'est ce que tradent vraiment les swing traders (TQQQ/SOXL…).
# ⚠️ les 3x (TQQQ/SOXL/TNA/LABU/SPXL/FAS/TECL/YINN/NUGT) ont une DÉCAY de volatilité -> le buy&hold y
# est faussé à la baisse ; comparer strat vs B&H du MÊME ETF (la décay est dans les deux).
VOL_ETF = [
    # à levier 3x (très volatils)
    'TQQQ', 'SOXL', 'TNA', 'LABU', 'SPXL', 'FAS', 'TECL', 'YINN', 'NUGT',
    # thématiques / sectoriels volatils (1x)
    'ARKK', 'ARKG', 'XBI', 'IBB', 'SMH', 'SOXX', 'KWEB', 'TAN', 'URA',
    'GDX', 'GDXJ', 'XOP', 'KRE', 'JETS', 'ICLN', 'BOTZ', 'LIT',
]

UNIVERSES = {'etf': ETF, 'nasdaq100': NASDAQ100, 'vol_etf': VOL_ETF}
