from datetime import datetime
from pathlib import Path

import os


class FileProp():
    def __init__(self, filePath: str) -> None:
        self._filePath = Path(filePath)
        self.filePath = str(self._filePath)

        tokens = self.filePath.split('\\')
        self._dirPath = Path('\\'.join(tokens[:-1]))
        # _, self.period, self.interval, self.downloadDate = self.name[:-4].split('_')


        # self._data = self.filePath, self.ticker, self.period, self.interval

        self.fileAlreadyExists = self._filePath.is_file()
        self.dirAlreadyExists = self._dirPath.exists()

        # self.tickerFiles = [file for file in os.listdir(f'Historical Data\\{self.ticker}')] if self.dirAlreadyExists else []

        if not self.dirAlreadyExists: 
            os.mkdir(str(self._dirPath))
        if not self.fileAlreadyExists:
            with open(str(self._filePath), 'w') as f: ...

    def getSize(self) -> int:
        return os.path.getsize(self.filePath)
    
    def isEmpty(self) -> bool:
        return not self.getSize()

    def __eq__(self, value: object) -> bool:
        return hash(self) == hash(value)
    
    def __str__(self) -> str:
        out = f'Path: {self.name} | Download date: {self.downloadDate} | Period: {self.period} | Interval: {self.interval}'
        return out
    
    def __hash__(self) -> int:
        return hash(self._data)
