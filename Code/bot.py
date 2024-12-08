# Core Modules
import multiprocessing as mp
import matplotlib as mat
import contextlib as ct
import yfinance as yf
import pandas as pd
import numpy as np

# Sub modules
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# External classes
from matplotlib.collections import LineCollection
from concurrent.futures import ProcessPoolExecutor as Executor

# External functions
from pickle import load, dump
from functools import wraps
from csv import writer
from numba import njit

# External vars
from os import devnull, walk, makedirs
from shutil import rmtree

# Custom classes
from SuperTrend import SuperTrend
from FileProp import FileProp
from typing import Callable

# Global vars
from globals import *


mat.use('Agg')
plt.rcParams['font.size'] = 8

allData: dict[str, tuple[pd.DataFrame, list[SuperTrend]]]
uptrendTickers: list[str] = []
err: list[str] = []

def fileStructSetup() -> None:
    todayExists = False
    yesterdayExists = False
    for dir in next(walk('Temp'))[1]:
        path = f'Temp\\{dir}'
        date = path.split('\\')[-1]
        if  date == TODAY: todayExists = True
        elif date == YESTERDAY: yesterdayExists = True
        else: rmtree(path)

    if not todayExists: makedirs(f'Temp\\{TODAY}')
    if not yesterdayExists: makedirs(f'Temp\\{YESTERDAY}')

fileStructSetup()
fileAllData = FileProp(f'Temp\\{TODAY}\\All Data\\{uID}.bin')


def _removeSuffix(tickers: list[str]) -> list[str]: return list(map(lambda x: x[:-3], tickers))

@njit(fastmath=True)
def getEMA(data: np.ndarray, span: int) -> np.ndarray:
    nData = len(data)
    alpha = 2 / (span + 1)
    ema = np.empty(nData)
    ema[0] = data[0]  # Start EMA at the first value
    for i in range(1, nData): ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _suppress_output(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with ct.redirect_stdout(open(devnull, 'w')), ct.redirect_stderr(open(devnull, 'w')): return func(*args, **kwargs)
    return wrapper


@_suppress_output
def _downloadTickerData(
        ticker: str,
        period: str = None, 
        interval: str ='1d',
        start: str = None, 
        end: str = None
        ) -> pd.DataFrame:
    
    if all((period, start, end)) or all(map(lambda x: not x, (period, start, end))):
        raise ValueError("Enter either both Start and End date or only period")
    
    elif period and (not all((start, end))): 
        data: pd.DataFrame = yf.download(ticker, period=period, interval=interval)
    
    elif all((start, end)) and not period: 
        data: pd.DataFrame= yf.download(ticker, start=start, end=end, interval=interval)
    
    else: 
        raise ValueError("Check arguments provided")

    if data.empty: err.append(ticker)
        
    return data


def _getAllData() -> dict[str, tuple[pd.DataFrame, list[SuperTrend]]] | None:
    
    if NEW_DATA or not fileAllData.getSize(): return None

    if fileAllData.fileAlreadyExists and fileAllData.getSize():
        print('Loading All Data into Memory.')
        with open(fileAllData.filePath, 'rb') as file: allData = load(file)
        print('Done Loading All Data into Memory.\n')
    
    return allData if allData else None


def _getTickerAllData(ticker: str) -> tuple[pd.DataFrame, list[SuperTrend], str]:
    filebin = FileProp(f'Temp\\{TODAY}\\Historical Data\\{ticker[:-3]}_{uID}.bin')

    if NEW_DATA or not filebin.fileAlreadyExists or not filebin.getSize():
        data: pd.DataFrame = _downloadTickerData(ticker=ticker, period=PERIOD, interval=INTERVAL)

        data.reset_index(inplace=True)
        data.set_index('Date', inplace=True)
        data['EMA'] = getEMA(data['Close'].to_numpy(dtype=np.float32), span=5)

        if SAVE_CSV: 
            filecsv = FileProp(f'Temp\\{TODAY}\\Historical Data\\{ticker[:-3]}_{uID}.csv')
            data.to_csv(filecsv.filePath, index=False)

        with open(filebin.filePath, 'wb') as file: dump(data, file)

    else: 
        with open(filebin.filePath, 'rb') as file: data: pd.DataFrame = load(file)
            
    for indicator in (indicators:=[SuperTrend(data, length=i, multiplier=i-9, ticker=ticker) for i in range(10, 13)]):
        data = indicator.addIndicatorData(data)
        
    return data, indicators


def getChartImagePath(ticker: str) -> str:
    global tickerNum, allData

    data, indicators = allData[ticker]

    if data.empty: 
        err.append(ticker)
        tickerNum += 1
        print('DATA EMPTY')
    
    if (imgFile := FileProp(f'Temp\\{TODAY}\\Chart Images\\{ticker}.png')).fileAlreadyExists: 
        tickerNum += 1
        return imgFile.filePath


    ema = np.array(data['EMA'], dtype=np.float32)
    fig, ax = plt.subplots(figsize=FIGSIZE_INCHES)

    ax.plot(data.index, ema, color='blue', linewidth=1.2, label='Close Price', alpha=0.85)

    dates = mdates.date2num(data.index.to_pydatetime())
    
    for indicator in indicators:
        indID = f'{indicator.length}_{indicator.multiplier}'

        supertrend, trend = np.array(data[f'Supertrend_{indID}'], dtype=np.float32), np.array(data[f'TrendDirec_{indID}'], dtype=np.bool)
        trendTemp = trend[1:]

        segments = np.dstack([dates[:-1], supertrend[:-1], dates[1:], supertrend[1:]]).reshape(-1, 2, 2)

        lc = LineCollection(segments, colors=np.where(trendTemp, 'green', 'red'), linewidths=0.6, alpha=0.5)
        ax.add_collection(lc)

        ax.fill_between(
            x=data.index,
            y1=supertrend,
            y2=ema,
            where=trend,
            color='green',
            alpha=FILL_ALPHA,
            interpolate=True
        )
        ax.fill_between(
            x=data.index,
            y1=supertrend,
            y2=ema,
            where=~trend,
            color='red',
            alpha=FILL_ALPHA,
            interpolate=True
        )

    ax.set_title(f'{ticker} Stock Price')
    ax.legend(loc='best')

    ax.xaxis_date()

    fig.savefig(imgFile.filePath, dpi=DPI, bbox_inches='tight')
    plt.close(fig)

    return imgFile.filePath


def _checkUptrend(ticker: str) -> bool:
    data, indicators = allData[ticker]

    return all(
        [data.at[data.index[-1], f'TrendDirec_{ind.length}_{ind.multiplier}'] for ind in indicators]
        ) if not data.empty else False


def _getUptrendTickers(tickers: list[str]) -> list[str]: return _removeSuffix([ticker for ticker in tickers if _checkUptrend(ticker)])


def _logData() -> None:
    uptrendTickers = _getUptrendTickers(TICKERS)
         
    with open(f'Database\\Logs\\UptrendTickers_{TODAY}.csv', 'w', newline='') as file:
        w = writer(file)
        w.writerows(list(map(lambda x: [x], uptrendTickers)))

    with open('Database\\Logs\\ErrorTickers.csv', 'w', newline='') as file:
        w = writer(file)
        w.writerows(err)


def init() -> None:
    global allData, tickerNum, loadedAllData
    
    loadedAllData = _getAllData()

    if loadedAllData is None:
        print('Downloading All Data')
        with Executor() as exec: allData = dict(zip(TICKERS, exec.map(_getTickerAllData, TICKERS)))
    else: allData = loadedAllData

    tickerNum = 0

    if not (fileAllData.fileAlreadyExists and fileAllData.getSize()):
        print('\nWriting Data.')
        with open(fileAllData.filePath, 'wb') as file: dump(allData, file)
        print('Done Writing All Data.\n')

    _logData()

    print(f'Total time taken (seconds): {time() - START_TIME}')

if __name__ == '__main__':
    init()
