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
    with open(f'Database\\Logs\\UptrendTickers_{TODAY}.csv', 'r') as file: return [i[0] + '.NS' for i in reader(file)]

    
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
        allTab.setLayout(allTabScrollArea)
        tabs.addTab(allTab, "All")

        uptrendTab = QWidget()
        uptrendTabScrollArea = self.createScrollArea(getUptrendTickers())
        uptrendTab.setLayout(uptrendTabScrollArea)
        tabs.addTab(uptrendTab, "Uptrend")

        sidebarLayout.addWidget(tabs)
        sidebar.setLayout(sidebarLayout)

        return sidebar

    def createScrollArea(self, tickers: list[str]) -> QVBoxLayout:
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)

        buttonContainer = QWidget()
        buttonLayout = QVBoxLayout()

        for ticker in tickers:
            button = QPushButton(ticker)
            button.clicked.connect(lambda _, ticker=ticker: self.displayImage(ticker))
            buttonLayout.addWidget(button)

        buttonLayout.addStretch()
        buttonContainer.setLayout(buttonLayout)
        scrollArea.setWidget(buttonContainer)

        tabLayout = QVBoxLayout()
        tabLayout.addWidget(scrollArea)

        return tabLayout

    def displayImage(self, ticker: str) -> None:
        imagePath =  bot.getChartImagePath(ticker)
        pixmap = QPixmap(imagePath)

        self.imageLabel.setPixmap(pixmap)
        self.imageLabel.setScaledContents(True)
        # self.imageLabel.setFixedSize(self.imageLabel.size())
        self.imageLabel.setFixedSize(self.IMAGE_WIDTH, self.IMAGE_HEIGHT)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    bot.init()    
    main()
