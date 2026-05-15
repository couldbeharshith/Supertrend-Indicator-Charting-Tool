import sys
import bot

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QTabWidget, QPushButton, QScrollArea, 
    QLabel
)

from PyQt5.QtGui import QPixmap, QGuiApplication
from PyQt5.QtCore import Qt

from csv import reader
from globals import *


def getUptrendTickers() -> list[str]:
    log_path = f'../Database/Logs/UptrendTickers_{TODAY}.csv'
    try:
        with open(log_path, 'r') as file: return [i[0] + '.NS' for i in reader(file)]
    except FileNotFoundError:
        return []

    
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        screenSize = QGuiApplication.primaryScreen().size()
        self.WIDTH, self.HEIGHT = screenSize.width(), screenSize.height()
        self.IMAGE_WIDTH, self.IMAGE_HEIGHT = int(self.WIDTH*0.885), int(self.HEIGHT*0.92)

        self.setWindowTitle("Ticker Plotting App")
        self.setGeometry(0, 0, self.WIDTH, self.HEIGHT-80)

        mainLayout = QHBoxLayout()
        sidebar = self.createSidebar()
        mainLayout.addWidget(sidebar)

        self.imageLabel = QLabel("Select a ticker to display an image", self)
        self.imageLabel.setAlignment(Qt.AlignCenter)
        mainLayout.addWidget(self.imageLabel)

        container = QWidget()
        container.setLayout(mainLayout)
        self.setCentralWidget(container)

    def createSidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebarLayout = QVBoxLayout()
        tabs = QTabWidget(self)

        allTab = QWidget(self)
        allTabScrollArea = self.createScrollArea(TICKERS)
        allTabLayout = QVBoxLayout()
        allTabLayout.addWidget(allTabScrollArea)
        allTab.setLayout(allTabLayout)
        tabs.addTab(allTab, "All")

        uptrendTab = QWidget()
        uptrendTabScrollArea = self.createScrollArea(getUptrendTickers())
        uptrendTabLayout = QVBoxLayout()
        uptrendTabLayout.addWidget(uptrendTabScrollArea)
        uptrendTab.setLayout(uptrendTabLayout)
        tabs.addTab(uptrendTab, "Uptrend")

        sidebarLayout.addWidget(tabs)
        sidebar.setLayout(sidebarLayout)
        return sidebar

    def createScrollArea(self, tickers: list[str]) -> QScrollArea:
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        buttonContainer = QWidget()
        buttonLayout = QVBoxLayout()
        for ticker in tickers:
            button = QPushButton(ticker)
            button.clicked.connect(lambda _, t=ticker: self.displayImage(t))
            buttonLayout.addWidget(button)
        buttonLayout.addStretch()
        buttonContainer.setLayout(buttonLayout)
        scrollArea.setWidget(buttonContainer)
        return scrollArea

    # **FIX**: This function now checks if the image is valid and displays an error if not.
    def displayImage(self, ticker: str) -> None:
        imagePath = bot.getChartImagePath(ticker)
        pixmap = QPixmap(imagePath)

        # Check if the pixmap was successfully loaded. This handles empty/invalid image files.
        if pixmap.isNull():
            print(f"Could not load image for {ticker}.")
            self.imageLabel.setText(f"Could not display plot for {ticker}.\n(Image may not have been generated due to insufficient data)")
            self.imageLabel.setPixmap(QPixmap()) # Clear any old image
        else:
            self.imageLabel.setText("") # Clear any previous error message
            self.imageLabel.setPixmap(pixmap)
            self.imageLabel.setScaledContents(True)
            self.imageLabel.setFixedSize(self.IMAGE_WIDTH, self.IMAGE_HEIGHT)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    bot.init()    
    main()