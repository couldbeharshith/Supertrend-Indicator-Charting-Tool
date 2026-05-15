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
        self.multiplier = multiplier # Corrected from self.mul
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

        # Using your exact original ATR calculation with 'join=inner'
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

        # 1. Calculate ATR using your original method. This creates a Series that is one element shorter.
        atr = self._ATR(high, low, close, self.length)
        
        # 2. **Crucial Fix**: Reindex the ATR and bands to match the main DataFrame.
        # This aligns the data correctly and introduces a NaN at the start, which is how we make the loop safe.
        atr = atr.reindex(df.index)
        
        hl2 = (high + low) / 2
        upperband = hl2 + (self.multiplier * atr)
        lowerband = hl2 - (self.multiplier * atr)
        
        # Initialize trend direction as you did
        trendDirec = [False] * len(df)
        
        # 3. --- Your exact original loop, made safe with .iloc ---
        # This loop will now work correctly because the bands are properly aligned with the close prices.
        for i in range(1, len(df)):
            # The initial NaN in upperband.iloc[i-1] is handled correctly by the comparison (it evaluates to False)
            if close.iloc[i] < lowerband.iloc[i-1]: lowerband.iloc[i] = min(lowerband.iloc[i], lowerband.iloc[i-1])
            else: lowerband.iloc[i] = lowerband.iloc[i]
            
            if close.iloc[i] > upperband.iloc[i-1]:
                trendDirec[i] = True
            elif close.iloc[i] < lowerband.iloc[i-1]:
                trendDirec[i] = False
            else:
                trendDirec[i] = trendDirec[i-1]
                if trendDirec[i] == True and lowerband.iloc[i] < lowerband.iloc[i-1]:
                    lowerband.iloc[i] = lowerband.iloc[i-1]
                if trendDirec[i] == False and upperband.iloc[i] > upperband.iloc[i-1]:
                    upperband.iloc[i] = upperband.iloc[i-1]
        
        # 4. Create the final output exactly as you did
        out = pd.DataFrame({
            f'TrendDirec_{self.length}_{self.multiplier}': trendDirec,
            f'Lowerband_{self.length}_{self.multiplier}': lowerband,
            f'Upperband_{self.length}_{self.multiplier}': upperband
            }, index=df.index)
        
        out[f'Supertrend_{self.length}_{self.multiplier}'] = out.apply(
            lambda row: (row[f'Lowerband_{self.length}_{self.multiplier}'] 
                         if row[f'TrendDirec_{self.length}_{self.multiplier}'] 
                         else row[f'Upperband_{self.length}_{self.multiplier}']),
            axis=1)
            
        return out 

    def addIndicatorData(self, other: pd.DataFrame) -> pd.DataFrame:
        if self.indicatorData.empty:
            return other
        return pd.concat([other, self.indicatorData], axis=1)
    
    def __repr__(self) -> str:
        return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'

    def __str__(self) -> str:
        return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'