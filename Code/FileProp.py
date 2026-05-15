from datetime import datetime
from pathlib import Path

import os


class FileProp():
    def __init__(self, filePath: str) -> None:
        self._filePath = Path(filePath)
        self.filePath = str(self._filePath)

        # Robustly get the parent directory using pathlib
        self._dirPath = self._filePath.parent
        
        # Get status before making changes
        self.fileAlreadyExists = self._filePath.is_file()
        self.dirAlreadyExists = self._dirPath.is_dir()

        # Ensure directory exists, creating parent directories if necessary
        if not self.dirAlreadyExists: 
            os.makedirs(self._dirPath, exist_ok=True)
        
        # Ensure file exists (create an empty one if not)
        if not self.fileAlreadyExists:
            with open(str(self._filePath), 'w') as f: ...

    def getSize(self) -> int:
        # Check if file exists before getting size to avoid errors
        return os.path.getsize(self.filePath) if os.path.exists(self.filePath) else 0
    
    def isEmpty(self) -> bool:
        return not self.getSize()

    def __eq__(self, value: object) -> bool:
        return hash(self) == hash(value)
    
    def __str__(self) -> str:
        # These properties were commented out in the original, so they are not available
        # out = f'Path: {self.name} | Download date: {self.downloadDate} | Period: {self.period} | Interval: {self.interval}'
        return f'FileProp({self.filePath})'
    
    def __hash__(self) -> int:
        # This property was commented out, hashing self.filePath instead
        # return hash(self._data)
        return hash(self.filePath)