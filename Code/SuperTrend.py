import pandas as pd
import numpy as np

class SuperTrend:
    def __init__(
            self,
            stockData: pd.DataFrame,
            length: int = 10,
            multiplier: int | float = 1,
            ticker: str = None
            ) -> None:

        self.ticker = ticker
        self.stockData = stockData.copy()
        self.length = length
        self.multiplier = multiplier
        self.indicatorData = self.calculateSupertrend()

    def _ATR(self,
            high: pd.Series,
            low: pd.Series,
            close: pd.Series,
            length: int = 10
            ) -> pd.Series:

        TR1 = high - low
        TR2 = abs(high - close.shift(1))
        TR3 = abs(low - close.shift(1))

        TR = pd.concat([TR1, TR2, TR3], axis=1, join='inner').max(axis=1)

        return TR.ewm(span=length, adjust=False).mean()

    def calculateSupertrend(self) -> pd.DataFrame:
        df = self.stockData

        # Defensive handling for multi-level columns from yfinance
        high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
        low = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']

        if df.empty or len(df) < self.length:
            return pd.DataFrame()

        atr = self._ATR(high, low, close, self.length).reindex(df.index)
        midpoint = (high + low) / 2
        upper = (midpoint + self.multiplier * atr).to_numpy(copy=True)
        lower = (midpoint - self.multiplier * atr).to_numpy(copy=True)
        closes = close.to_numpy()
        trend = np.zeros(len(df), dtype=bool)

        for i in range(1, len(df)):
            if closes[i] < lower[i - 1]:
                lower[i] = min(lower[i], lower[i - 1])

            if closes[i] > upper[i - 1]:
                trend[i] = True
            elif closes[i] < lower[i - 1]:
                trend[i] = False
            else:
                trend[i] = trend[i - 1]
                if trend[i] and lower[i] < lower[i - 1]:
                    lower[i] = lower[i - 1]
                if not trend[i] and upper[i] > upper[i - 1]:
                    upper[i] = upper[i - 1]

        key = f'{self.length}_{self.multiplier}'
        return pd.DataFrame({
            f'TrendDirec_{key}': trend,
            f'Lowerband_{key}': lower,
            f'Upperband_{key}': upper,
            f'Supertrend_{key}': np.where(trend, lower, upper),
        }, index=df.index)

    def addIndicatorData(self, other: pd.DataFrame) -> pd.DataFrame:
        if self.indicatorData.empty:
            return other
        return pd.concat([other, self.indicatorData], axis=1)

    def __repr__(self) -> str:
        return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'

    def __str__(self) -> str:
        return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'
