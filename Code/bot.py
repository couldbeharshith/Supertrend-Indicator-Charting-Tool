# Core Modules
import multiprocessing as mp
import matplotlib as mat
import contextlib as ct
import yfinance as yf
import pandas as pd
import numpy as np
import os

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
    makedirs('../Database/Temp', exist_ok=True)
    todayExists, yesterdayExists = False, False
    for dir_name in next(walk('../Database/Temp'))[1]:
        path = f'../Database/Temp/{dir_name}'
        date = path.split('/')[-1]
        if date == TODAY: todayExists = True
        elif date == YESTERDAY: yesterdayExists = True
        else: rmtree(path)
    if not todayExists: makedirs(f'../Database/Temp/{TODAY}')
    if not yesterdayExists: makedirs(f'../Database/Temp/{YESTERDAY}')

fileStructSetup()
fileAllData = FileProp(f'../Database/Temp/{TODAY}/All Data/{uID}.bin')


def _removeSuffix(tickers: list[str]) -> list[str]: return list(map(lambda x: x[:-3], tickers))

@njit(fastmath=True)
def getEMA(data: np.ndarray, span: int) -> np.ndarray:
    nData = len(data)
    alpha = 2 / (span + 1)
    ema = np.empty_like(data)
    ema[0] = data[0]
    for i in range(1, nData): ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _suppress_output(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with ct.redirect_stdout(open(devnull, 'w')), ct.redirect_stderr(open(devnull, 'w')): return func(*args, **kwargs)
    return wrapper


@_suppress_output
def _downloadTickerData(ticker: str, period: str = None, interval: str ='1d', start: str = None, end: str = None) -> pd.DataFrame:
    if period: return yf.download(ticker, period=period, interval=interval)
    elif start and end: return yf.download(ticker, start=start, end=end, interval=interval)
    else: raise ValueError("Check arguments provided")


def _getAllData() -> dict | None:
    if NEW_DATA or not fileAllData.getSize(): return None
    if fileAllData.fileAlreadyExists and fileAllData.getSize():
        with open(fileAllData.filePath, 'rb') as file: return load(file)
    return None


def _getTickerAllData(ticker: str) -> tuple[pd.DataFrame, list[SuperTrend]]:
    filebin = FileProp(f'../Database/Temp/{TODAY}/Historical Data/{ticker[:-3]}_{uID}.bin')
    
    if NEW_DATA or not filebin.fileAlreadyExists or not filebin.getSize():
        df = _downloadTickerData(ticker=ticker, period=PERIOD, interval=INTERVAL)
        if df.empty: return pd.DataFrame(), []
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            df = df.loc[:,~df.columns.duplicated()]

        if not isinstance(df.index, pd.DatetimeIndex):
            df.reset_index(inplace=True)
            if 'Date' in df.columns: df.set_index('Date', inplace=True)
        with open(filebin.filePath, 'wb') as file: dump(df, file)
    else:
        with open(filebin.filePath, 'rb') as file: df = load(file)
        if not isinstance(df, pd.DataFrame): return pd.DataFrame(), []

    if df.empty or not all(col in df.columns for col in ['High', 'Low', 'Close']):
        return pd.DataFrame(), []

    final_df = df.copy()
    final_df['EMA'] = getEMA(df['Close'].to_numpy(dtype=np.float32), span=5)
    
    indicators = [SuperTrend(df, length=i[0], multiplier=i[1], ticker=ticker) for i in INDICATOR_LENGTHS]
    for indicator in indicators:
        final_df = pd.concat([final_df, indicator.indicatorData], axis=1)
        
    return final_df, indicators


def getChartImagePath(ticker: str) -> str:
    global tickerNum, allData
    imgFile = FileProp(f'../Database/Temp/{TODAY}/Chart Images/{ticker}.png')
    if imgFile.fileAlreadyExists and imgFile.getSize() > 0:
        tickerNum += 1
        return imgFile.filePath

    data, indicators = allData[ticker]
    
    # --- Definitive Plotting Fix ---
    # 1. Identify all columns we will ever need for the plot.
    required_cols = ['EMA']
    for ind in indicators:
        required_cols.append(f'Supertrend_{ind.length}_{ind.multiplier}')
        required_cols.append(f'TrendDirec_{ind.length}_{ind.multiplier}')
    
    # 2. Filter for columns that actually exist in the DataFrame.
    cols_to_plot = [col for col in required_cols if col in data.columns]
    
    # 3. Create one single, clean DataFrame by dropping all rows with ANY NaN values.
    # This guarantees all arrays used for plotting are aligned and valid.
    plot_data = data[cols_to_plot].dropna()

    if len(plot_data) < 2:
        if ticker not in err: err.append(ticker)
        tickerNum += 1
        return imgFile.filePath
    
    # 4. Proceed to plot using only the guaranteed clean 'plot_data'
    fig, ax = plt.subplots(figsize=FIGSIZE_INCHES)
    
    ema_clean = plot_data['EMA']
    dates_clean = mdates.date2num(plot_data.index.to_pydatetime())
    
    ax.plot(plot_data.index, ema_clean, color='blue', linewidth=1.2, label='Close Price', alpha=0.85)

    for indicator in indicators:
        indID = f'{indicator.length}_{indicator.multiplier}'
        st_col = f'Supertrend_{indID}'
        trend_col = f'TrendDirec_{indID}'

        if st_col not in plot_data.columns or trend_col not in plot_data.columns:
            continue
            
        supertrend = plot_data[st_col].to_numpy()
        trend = plot_data[trend_col].to_numpy(dtype=bool)
        
        # The key is that 'dates_clean', 'supertrend', and 'trend' are now all derived
        # from the same 'plot_data' DataFrame, so they are guaranteed to have the same length.
        segments = np.dstack([dates_clean[:-1], supertrend[:-1], dates_clean[1:], supertrend[1:]]).reshape(-1, 2, 2)
        lc = LineCollection(segments, colors=np.where(trend[1:], 'green', 'red'), linewidths=0.6, alpha=0.5)
        ax.add_collection(lc)

        ax.fill_between(x=plot_data.index, y1=supertrend, y2=ema_clean, where=trend, color='green', alpha=FILL_ALPHA, interpolate=True)
        ax.fill_between(x=plot_data.index, y1=supertrend, y2=ema_clean, where=~trend, color='red', alpha=FILL_ALPHA, interpolate=True)

    ax.set_title(f'{ticker} Stock Price')
    ax.legend(loc='best')
    ax.xaxis_date()
    fig.savefig(imgFile.filePath, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    return imgFile.filePath


def _checkUptrend(ticker: str) -> bool:
    data, indicators = allData[ticker]
    if data.empty: return False
    for ind in indicators:
        key = f'TrendDirec_{ind.length}_{ind.multiplier}'
        if key not in data.columns or pd.isna(data.at[data.index[-1], key]) or not data.at[data.index[-1], key]:
            return False
    return True


def _getUptrendTickers(tickers: list[str]) -> list[str]: return _removeSuffix([ticker for ticker in tickers if _checkUptrend(ticker)])


def _logData() -> None:
    uptrendTickers = _getUptrendTickers(TICKERS)
    log_dir = '../Database/Logs'
    makedirs(log_dir, exist_ok=True)
    with open(f'{log_dir}/UptrendTickers_{TODAY}.csv', 'w', newline='') as file:
        w = writer(file); w.writerows([[x] for x in uptrendTickers])
    with open(f'{log_dir}/ErrorTickers.csv', 'w', newline='') as file:
        w = writer(file); w.writerows([[x] for x in err])


def init() -> None:
    global allData, tickerNum
    print("Initializing...")
    loadedAllData = _getAllData()
    if loadedAllData is None:
        print('Downloading All Data. This may take a while...')
        with Executor() as exec: allData = dict(zip(TICKERS, exec.map(_getTickerAllData, TICKERS)))
        print('\nWriting Data to cache.')
        with open(fileAllData.filePath, 'wb') as file: dump(allData, file)
        print('Done Writing All Data.\n')
    else: 
        print("Loaded data from cache.")
        allData = loadedAllData
    tickerNum = 0
    _logData()
    from globals import START_TIME
    from time import time
    print(f'Total time taken (seconds): {time() - START_TIME}')

if __name__ == '__main__':
    init()