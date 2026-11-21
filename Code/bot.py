import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import writer
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from pickle import PickleError, dump, load
from tempfile import NamedTemporaryFile
from threading import Event, Lock
from time import monotonic

import matplotlib.dates as mdates
import matplotlib.patheffects as path_effects
import numpy as np
import pandas as pd
import yfinance as yf
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PIL import Image
from yfinance.exceptions import YFTickerMissingError

from globals import (
    CHART_BG, DATABASE, DOWN_COLOR, DPI, FIGSIZE_INCHES, INDICATOR_LENGTHS, INTERVAL,
    PERIOD, PRICE_COLOR, RULE_COLOR, TEXT_COLOR, TICKERS, TODAY, UP_COLOR,
)
from SuperTrend import SuperTrend


logger = logging.getLogger(__name__)
HISTORY_DIR = DATABASE / 'Temp'
# Older launches from the repository root wrote their history one level above it.
LEGACY_HISTORY_DIR = DATABASE.parent.parent / 'Database' / 'Temp'
PRICE_COLUMNS = ['High', 'Low', 'Close']
price_locks = [Lock() for _ in range(64)]
render_lock = Lock()

class ChartUnavailable(Exception):
    pass


@dataclass(frozen=True)
class ChartResult:
    path: Path
    last_session: date
    historical: bool
    directions: tuple[bool | None, ...]


@dataclass(frozen=True)
class ScanResult:
    tickers: tuple[str, ...]
    checked: int
    unavailable: int


@dataclass(frozen=True)
class TrendLine:
    values: np.ndarray
    rising: np.ndarray

    @property
    def last_direction(self) -> bool | None:
        if len(self.values) < 2 or not np.isfinite(self.values[-2:]).all():
            return None
        return bool(self.rising[-1])


def _write_cache(path, mode, write):
    path.parent.mkdir(parents=True, exist_ok=True)
    file = NamedTemporaryFile(mode=mode, dir=path.parent, delete=False, newline='' if mode == 'w' else None)
    temp_path = Path(file.name)
    try:
        with file:
            write(file)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _clean_prices(df):
    if not isinstance(df, pd.DataFrame) or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
    if not set(PRICE_COLUMNS).issubset(df.columns):
        return pd.DataFrame()

    prices = df[PRICE_COLUMNS].apply(pd.to_numeric, errors='coerce').replace([np.inf, -np.inf], np.nan)
    prices = prices.loc[prices.index.notna()].dropna().sort_index()
    return prices.loc[~prices.index.duplicated(keep='last')]


def _history_path(ticker, cache_date, root=None):
    root = HISTORY_DIR if root is None else root
    return root / cache_date / 'Historical Data' / f'{ticker.removesuffix(".NS")}_{PERIOD}_{INTERVAL}_{cache_date}.bin'


def _read_prices(path):
    try:
        with path.open('rb') as file:
            return _clean_prices(load(file))
    except (OSError, EOFError, PickleError, ValueError, ImportError, AttributeError):
        return pd.DataFrame()


def _cached_prices(ticker, cache_date):
    prices = _read_prices(_history_path(ticker, cache_date))
    if len(prices) < 2:
        prices = _read_prices(_history_path(ticker, cache_date, LEGACY_HISTORY_DIR))
    return prices


def _current_prices(ticker):
    path = _history_path(ticker, TODAY)
    with price_locks[hash(ticker) % len(price_locks)]:
        prices = _cached_prices(ticker, TODAY)
        if len(prices) >= 2:
            return prices

        try:
            history = yf.Ticker(ticker).history(period=PERIOD, interval=INTERVAL, timeout=8, raise_errors=True)
        except YFTickerMissingError as exc:
            logger.debug('No Yahoo Finance price history for %s: %s', ticker, exc)
            return pd.DataFrame()
        except Exception as exc:
            logger.warning('Yahoo Finance history request failed for %s: %s', ticker, exc)
            return pd.DataFrame()
        prices = _clean_prices(history)
        if len(prices) >= 2:
            _write_cache(path, 'wb', lambda file: dump(prices, file))
        return prices


def _older_prices(ticker):
    def folder_date(name):
        try:
            return datetime.strptime(name, '%d-%m-%Y').date()
        except ValueError:
            return date.min

    dates = {folder.name for root in (HISTORY_DIR, LEGACY_HISTORY_DIR) if root.is_dir()
             for folder in root.iterdir() if folder.is_dir()}
    today = folder_date(TODAY)
    for cache_date in sorted(dates, key=folder_date, reverse=True):
        if date.min < folder_date(cache_date) < today:
            prices = _cached_prices(ticker, cache_date)
            if len(prices) >= 2:
                return prices, cache_date
    raise ChartUnavailable('Yahoo Finance did not return enough price history. Select Retry to try again.')


def _trend_lines(prices):
    lines = []
    for length, multiplier in INDICATOR_LENGTHS:
        indicator = SuperTrend(prices, length=length, multiplier=multiplier).indicatorData
        if indicator.empty:
            lines.append(None)
            continue
        key = f'{length}_{multiplier}'
        lines.append(TrendLine(indicator[f'Supertrend_{key}'].to_numpy(),
                               indicator[f'TrendDirec_{key}'].to_numpy(dtype=bool)))
    return lines


def _render_chart(prices, lines, path):
    fig = Figure(figsize=FIGSIZE_INCHES, facecolor=CHART_BG, layout='constrained')
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(facecolor=CHART_BG)
    fig.get_layout_engine().set(w_pad=0.27, h_pad=0.25)
    ema = prices['Close'].ewm(span=5, adjust=False).mean()
    price_line, = ax.plot(prices.index, ema, color=PRICE_COLOR, linewidth=2.2,
                         label='Price (5-day EMA)', zorder=4,
                         path_effects=[path_effects.withStroke(linewidth=3.8, foreground=CHART_BG)])
    dates = mdates.date2num(prices.index.to_pydatetime())
    legend = [price_line]
    fill_alpha = 0.13

    for line, width in zip(lines, (1.15, 0.9, 0.7)):
        if line is None:
            continue
        points = np.column_stack((dates, line.values))
        segments = np.stack((points[:-1], points[1:]), axis=1)
        ax.add_collection(LineCollection(segments, colors=np.where(line.rising[1:], UP_COLOR, DOWN_COLOR),
                                         linewidths=width, zorder=2))
        ax.fill_between(dates, line.values, ema, where=line.rising, color=UP_COLOR,
                        alpha=fill_alpha, interpolate=True, linewidth=0, zorder=1)
        ax.fill_between(dates, line.values, ema, where=~line.rising, color=DOWN_COLOR,
                        alpha=fill_alpha, interpolate=True, linewidth=0, zorder=1)

    if ax.collections:
        legend.extend([
            Line2D([], [], color=UP_COLOR, label='SuperTrend up'),
            Line2D([], [], color=DOWN_COLOR, label='SuperTrend down'),
        ])
    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position('right')
    ax.set_ylabel('Price (INR)', color=TEXT_COLOR, labelpad=9, fontsize=8.5)
    ax.tick_params(colors=TEXT_COLOR, length=0, pad=6, labelsize=9)
    for axis in (ax.xaxis, ax.yaxis):
        axis.offsetText.set_fontsize(9)
    ax.set_axisbelow(True)
    ax.grid(axis='y', color=RULE_COLOR, linewidth=0.65)
    ax.margins(x=0.012, y=0.09)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(handles=legend, loc='lower left', bbox_to_anchor=(0, 1.015), ncol=len(legend),
              frameon=False, labelcolor=TEXT_COLOR, borderaxespad=0, fontsize=8.5,
              handlelength=1.6, handletextpad=0.55, columnspacing=1.4)
    _write_cache(path, 'wb', lambda file: fig.savefig(file, format='png', dpi=DPI))


def _valid_image(path):
    try:
        with Image.open(path) as image:
            image.load()
        return True
    except (OSError, ValueError):
        return False


def getChart(ticker: str) -> ChartResult:
    if ticker not in TICKERS:
        raise ChartUnavailable('This ticker is missing from the NSE watchlist.')

    prices = _current_prices(ticker)
    cache_date = TODAY
    if len(prices) < 2:
        prices, cache_date = _older_prices(ticker)

    lines = _trend_lines(prices)
    directions = tuple(line.last_direction if line else None for line in lines)
    path = HISTORY_DIR / cache_date / 'Charts' / f'{ticker}_{PERIOD}_{INTERVAL}_v4.png'
    with render_lock:
        if not _valid_image(path):
            _render_chart(prices, lines, path)
    return ChartResult(path, prices.index[-1].date(), cache_date != TODAY, directions)


def getChartImagePath(ticker: str) -> str:
    return str(getChart(ticker).path)


def _in_uptrend(prices):
    if len(prices) < max(length for length, _ in INDICATOR_LENGTHS):
        return None
    directions = [line.last_direction if line else None for line in _trend_lines(prices)]
    return None if None in directions else all(directions)


def init(stop: Event | None = None, progress=None) -> ScanResult:
    stop = stop if stop is not None else Event()
    matches, unavailable, missing = [], [], []
    checked = 0
    next_report = 0

    def record(ticker, result):
        nonlocal checked, next_report
        checked += 1
        if result is True:
            matches.append(ticker)
        elif result is None:
            unavailable.append(ticker)
        if progress and (monotonic() >= next_report or (result is True and len(matches) == 1)):
            progress(ScanResult(tuple(sorted(matches)), checked, len(unavailable)))
            next_report = monotonic() + 0.25

    for ticker in TICKERS:
        if stop.is_set():
            break
        prices = _cached_prices(ticker, TODAY)
        if len(prices) < 2:
            missing.append(ticker)
        else:
            record(ticker, _in_uptrend(prices))

    if missing and not stop.is_set():
        with ThreadPoolExecutor(max_workers=8) as executor:
            def fetch(ticker):
                return _in_uptrend(_current_prices(ticker)) if not stop.is_set() else None

            pending = {executor.submit(fetch, ticker): ticker for ticker in missing}
            for future in as_completed(pending):
                if stop.is_set():
                    executor.shutdown(cancel_futures=True)
                    break
                record(pending[future], future.result())

    tickers = tuple(sorted(matches))
    if not stop.is_set():
        log_dir = DATABASE / 'Logs'
        _write_cache(log_dir / f'UptrendTickers_{TODAY}.csv', 'w',
                     lambda file: writer(file).writerows([ticker.removesuffix('.NS')] for ticker in tickers))
        _write_cache(log_dir / 'ErrorTickers.csv', 'w', lambda file: writer(file).writerows([ticker] for ticker in unavailable))
    return ScanResult(tickers, checked, len(unavailable))


if __name__ == '__main__':
    init()
