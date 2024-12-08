import pandas as pd

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
        self.multiplier = self.mul = multiplier
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

        high, low, close =  df['High'], df['Low'], df['Close']

        ATR = self._ATR(high, low, close, self.length)
        
        hl2 = (high + low) / 2
        upperband = hl2 + (self.multiplier * ATR)
        lowerband = hl2 - (self.multiplier * ATR)
        
        trendDirec = [False] * len(df)
        
        for i in range(1, len(df)):
            if close.iloc[i] > upperband.iloc[i-1]: upperband.iloc[i] = max(upperband.iloc[i], upperband.iloc[i-1])
            else: upperband.iloc[i] = upperband.iloc[i]
            
            if close.iloc[i] < lowerband.iloc[i-1]: lowerband.iloc[i] = min(lowerband.iloc[i], lowerband.iloc[i-1])
            else: lowerband.iloc[i] = lowerband.iloc[i]
            
            # Check for trend shift
            if close.iloc[i] > upperband.iloc[i-1]: trendDirec[i] = True
            elif close.iloc[i] < lowerband.iloc[i-1]: trendDirec[i] = False
            else:
                trendDirec[i] = trendDirec[i-1]
                if trendDirec[i] == True and lowerband.iloc[i] < lowerband.iloc[i-1]: lowerband.iloc[i] = lowerband.iloc[i-1]
                if trendDirec[i] == False and upperband.iloc[i] > upperband.iloc[i-1]: upperband.iloc[i] = upperband.iloc[i-1]
        
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

    def addIndicatorData(self, other: pd.DataFrame | pd.Series) -> pd.DataFrame: return pd.concat((other, self.indicatorData), axis=1)
    
    def __repr__(self) -> str: return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'

    def __str__(self) -> str: return f'SuperTrend_{self.length}_{self.multiplier}_{self.ticker}'
