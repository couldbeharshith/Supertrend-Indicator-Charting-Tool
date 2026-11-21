from datetime import date
from pathlib import Path
from pickle import load


DATABASE = Path(__file__).resolve().parent.parent / 'Database'
with (DATABASE / 'Init Data' / 'Tickers.bin').open('rb') as f:
    TICKERS = tuple(sorted(symbol + '.NS' for symbol in load(f)))

TODAY = date.today().strftime('%d-%m-%Y')
PERIOD = '1y'
INTERVAL = '1d'
INDICATOR_LENGTHS = ((10, 1), (11, 2), (12, 3))

CHART_BG = '#0d1013'
RAIL_BG = '#15191d'
RULE_COLOR = '#2a3037'
INK_COLOR = '#e9edf1'
ACCENT_COLOR = '#e8c387'
PRICE_COLOR = '#d7ecff'
UP_COLOR = '#5fc493'
DOWN_COLOR = '#e77f89'
TEXT_COLOR = '#a8b2be'

DPI = 150
FIGSIZE_INCHES = (12, 7)

