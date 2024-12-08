from datetime import date, timedelta
from time import time
from pickle import load


with open('D:\\Harshith\\Techninal analysis bot (ST indicator)\\Database\\Init Data\\Tickers.bin', 'rb') as f: 
    TICKERS: tuple[str] = sorted(tuple(map(lambda x: x + '.NS', load(f))))
    print(f'No. of tickers: {len(TICKERS)}')

_today = date.today()
TODAY = _today.strftime(r'%d-%m-%Y')
YESTERDAY = (_today - timedelta(days=1)).strftime(r'%d-%m-%Y')
FILL_ALPHA = 0.18

PERIOD = '1y'
INTERVAL = '1d'
START = None
END = None
NEW_DATA = False
SAVE_CSV = False

DPI = 230
FIGSIZE_INCHES = (17, 10) # in inches

uID = f'{PERIOD}_{INTERVAL}_{TODAY}'

START_TIME = time()

