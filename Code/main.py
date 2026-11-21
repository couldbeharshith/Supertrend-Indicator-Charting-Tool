import logging
import sys
from functools import partial
from string import Template
from threading import Event

from PyQt5.QtCore import QObject, QRunnable, QSignalBlocker, QThreadPool, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

import bot
from globals import (
    ACCENT_COLOR, CHART_BG, DOWN_COLOR, INDICATOR_LENGTHS, INK_COLOR, INTERVAL, PERIOD,
    RAIL_BG, RULE_COLOR, TEXT_COLOR, TICKERS, UP_COLOR,
)


logger = logging.getLogger(__name__)

STYLE = Template('''
QWidget {
    background: $chart;
    color: $ink;
    font-family: "Segoe UI";
    font-size: 14px;
}
QFrame#sidebar { background: $rail; border-right: 1px solid $rule; }
QFrame#sidebar QLabel, QTabBar, QListWidget { background: $rail; }
QFrame#chartHeader { border-bottom: 1px solid $rule; }
QFrame#sidebarFooter { background: $rail; border-top: 1px solid $rule; }
QLabel#sidebarTitle { font-size: 16px; font-weight: 600; }
QLabel#chartTitle { font-family: "Bahnschrift"; font-size: 32px; }
QLabel#stateTitle { font-size: 21px; font-weight: 600; }
QLabel#muted, QLabel#stateBody, QLabel#sidebarStatus { color: $text; }
QLabel#sidebarStatus, QLabel#signalSetting, QLabel#signalHeading { font-size: 12px; color: $text; }
QLabel#signalDirection { font-size: 13px; font-weight: 600; }
QLineEdit {
    background: $chart; border: 1px solid $rule; border-radius: 2px;
    padding: 6px 9px; selection-background-color: #343e4a;
}
QLineEdit:focus, QPushButton:focus { border-color: $accent; }
QTabBar::tab {
    color: $text; background: $rail; padding: 8px 14px;
    border-bottom: 2px solid $rule;
}
QTabBar::tab:selected { color: $ink; border-bottom-color: $accent; }
QTabBar::tab:hover:!selected { color: $ink; }
QTabBar::tab:focus { color: $accent; }
QListWidget { border: 1px solid transparent; outline: none; font-family: "Bahnschrift"; }
QListWidget:focus { border-color: $rule; }
QListWidget::item { border-left: 2px solid transparent; padding: 6px 12px; }
QListWidget::item:hover { background: #1d2329; }
QListWidget::item:selected { background: #262d35; border-left-color: $accent; color: $ink; }
QScrollBar:vertical { background: $rail; width: 8px; }
QScrollBar::handle:vertical { background: #48535f; min-height: 26px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: $rail; }
QPushButton {
    background: #20262d; border: 1px solid $rule; border-radius: 2px;
    padding: 5px 10px;
}
QPushButton:hover { background: #2a333d; }
QProgressBar { background: $rule; border: 0; max-height: 2px; }
QProgressBar::chunk { background: $accent; }
''').substitute(chart=CHART_BG, rail=RAIL_BG, rule=RULE_COLOR, ink=INK_COLOR,
                text=TEXT_COLOR, accent=ACCENT_COLOR)


class WorkerSignals(QObject):
    finished = pyqtSignal(int, object, str)
    progress = pyqtSignal(object)


class Worker(QRunnable):
    def __init__(self, request_id, work, error_message, report_progress=False):
        super().__init__()
        self.request_id = request_id
        self.work = work
        self.error_message = error_message
        self.signals = WorkerSignals()
        self.report_progress = report_progress

    def run(self):
        try:
            result = self.work(progress=self.signals.progress.emit) if self.report_progress else self.work()
        except bot.ChartUnavailable as exc:
            self.signals.finished.emit(self.request_id, None, str(exc))
        except Exception:
            logger.exception('Background task failed')
            self.signals.finished.emit(self.request_id, None, self.error_message)
        else:
            self.signals.finished.emit(self.request_id, result, '')


class ChartView(QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = QPixmap()

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        bounds = self.rect().adjusted(8, 6, -8, -10)
        size = self.pixmap.size().scaled(bounds.size(), Qt.KeepAspectRatio)
        pixel_ratio = self.devicePixelRatioF()
        scaled = self.pixmap.scaled(size * pixel_ratio, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        scaled.setDevicePixelRatio(pixel_ratio)
        painter = QPainter(self)
        painter.drawPixmap(bounds.center().x() - size.width() // 2, bounds.center().y() - size.height() // 2, scaled)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('SuperTrend — NSE charts')

        self.ticker = None
        self.request_id = 0
        self.scan_running = False
        self.scan_result = None
        self.scan_error = ''
        self.visible_tickers = ()
        self.scan_stop = Event()
        self.chart_pool = QThreadPool(self)
        self.chart_pool.setMaxThreadCount(1)
        self.scan_pool = QThreadPool(self)
        self.scan_pool.setMaxThreadCount(1)

        container = QWidget()
        workspace = QHBoxLayout(container)
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(0)
        self.sidebar = self.create_sidebar()
        workspace.addWidget(self.sidebar)
        workspace.addWidget(self.create_chart_card(), 1)
        self.setCentralWidget(container)
        self.refresh_tickers()
        self.setMinimumSize(720, 460)
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, int(screen.width() * 0.94)), min(820, int(screen.height() * 0.9)))

    def label(self, text, name):
        label = QLabel(text)
        label.setObjectName(name)
        return label

    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(251)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        controls = QVBoxLayout()
        controls.setContentsMargins(14, 16, 14, 8)
        controls.setSpacing(10)
        controls.addWidget(self.label('NSE watchlist', 'sidebarTitle'))

        self.search = QLineEdit()
        self.search.setPlaceholderText('Search tickers')
        self.search.setAccessibleName('Search tickers')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_tickers)
        self.search.returnPressed.connect(self.select_first_match)
        controls.addWidget(self.search)

        self.tabs = QTabBar()
        self.tabs.setAccessibleName('Watchlist filter')
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(False)
        self.tabs.addTab('All')
        self.tabs.addTab('Uptrend')
        self.tabs.currentChanged.connect(self.change_tab)
        controls.addWidget(self.tabs)
        layout.addLayout(controls)

        self.ticker_list = QListWidget()
        self.ticker_list.setAccessibleName('NSE tickers')
        self.ticker_list.setUniformItemSizes(True)
        self.ticker_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ticker_list.currentItemChanged.connect(self.select_ticker)
        layout.addWidget(self.ticker_list, 1)

        footer = QFrame()
        footer.setObjectName('sidebarFooter')
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(14, 9, 14, 12)
        footer_layout.setSpacing(6)
        self.sidebar_status = self.label('', 'sidebarStatus')
        self.sidebar_status.setWordWrap(True)
        footer_layout.addWidget(self.sidebar_status)
        self.scan_progress = QProgressBar()
        self.scan_progress.setAccessibleName('Uptrend scan progress')
        self.scan_progress.setRange(0, len(TICKERS))
        self.scan_progress.setTextVisible(False)
        self.scan_progress.hide()
        footer_layout.addWidget(self.scan_progress)
        self.scan_retry = QPushButton('Retry scan')
        self.scan_retry.clicked.connect(self.start_scan)
        self.scan_retry.hide()
        footer_layout.addWidget(self.scan_retry, alignment=Qt.AlignLeft)
        layout.addWidget(footer)
        return sidebar

    def create_chart_card(self):
        card = QFrame()
        card.setObjectName('chartCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName('chartHeader')
        heading = QHBoxLayout(header)
        heading.setContentsMargins(24, 15, 24, 15)
        heading.setSpacing(15)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.chart_title = self.label('Price history', 'chartTitle')
        self.chart_detail = self.label('', 'muted')
        self.chart_detail.setWordWrap(True)
        titles.addWidget(self.chart_title)
        titles.addWidget(self.chart_detail)
        self.cache_retry = QPushButton('Refresh cached prices')
        self.cache_retry.clicked.connect(lambda: self.load_chart(self.ticker))
        self.cache_retry.hide()
        titles.addWidget(self.cache_retry, alignment=Qt.AlignLeft)
        heading.addLayout(titles, 1)

        self.signal_panel = QWidget()
        panel = QVBoxLayout(self.signal_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(4)
        panel.addWidget(self.label('Latest SuperTrend', 'signalHeading'))
        columns = QHBoxLayout()
        columns.setSpacing(14)
        self.signal_directions = []
        for length, multiplier in INDICATOR_LENGTHS:
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(self.label(f'{length} × {multiplier}', 'signalSetting'))
            direction = self.label('', 'signalDirection')
            column.addWidget(direction)
            self.signal_directions.append(direction)
            columns.addLayout(column)
        panel.addLayout(columns)
        self.signal_panel.hide()
        heading.addWidget(self.signal_panel, alignment=Qt.AlignVCenter)
        layout.addWidget(header)

        self.chart_stack = QStackedWidget()
        self.chart_view = ChartView()
        self.chart_stack.addWidget(self.chart_view)

        self.chart_state = QWidget()
        state = QVBoxLayout(self.chart_state)
        state.setContentsMargins(24, 24, 24, 24)
        state.setSpacing(8)
        state.addStretch()

        self.state_title = self.label('', 'stateTitle')
        self.state_title.setAlignment(Qt.AlignCenter)
        state.addWidget(self.state_title)
        self.state_body = self.label('', 'stateBody')
        self.state_body.setAlignment(Qt.AlignCenter)
        self.state_body.setWordWrap(True)
        state.addWidget(self.state_body)

        self.retry = QPushButton('Retry')
        self.retry.setCursor(Qt.PointingHandCursor)
        self.retry.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.retry.clicked.connect(lambda: self.load_chart(self.ticker))
        state.addWidget(self.retry, alignment=Qt.AlignHCenter)
        state.addStretch()

        self.chart_stack.addWidget(self.chart_state)
        layout.addWidget(self.chart_stack, 1)
        self.show_state('Select a ticker', 'Use the watchlist to open a price chart.')
        return card

    def refresh_tickers(self):
        is_uptrend = self.tabs.currentIndex() == 1
        result = self.scan_result
        tickers = (result.tickers if result else ()) if is_uptrend else TICKERS
        search = self.search.text().strip().upper()
        matches = tuple(ticker for ticker in tickers if search in ticker)

        if matches != self.visible_tickers:
            self.visible_tickers = matches
            scrollbar = self.ticker_list.verticalScrollBar()
            scroll = scrollbar.value()
            with QSignalBlocker(self.ticker_list):
                self.ticker_list.clear()
                for ticker in matches:
                    item = QListWidgetItem(ticker)
                    self.ticker_list.addItem(item)
                    if ticker == self.ticker:
                        self.ticker_list.setCurrentItem(item)
                scrollbar.setValue(scroll)

        scanning = is_uptrend and self.scan_running
        self.scan_progress.setVisible(scanning)
        self.scan_retry.setVisible(is_uptrend and not scanning and bool(self.scan_error or (result and result.unavailable)))
        status = '1 ticker' if len(matches) == 1 else f'{len(matches):,} tickers'
        if search and not matches:
            status = 'No matching tickers'
        if scanning:
            checked = result.checked if result else 0
            self.scan_progress.setValue(checked)
            status += f'\n{checked:,} of {len(TICKERS):,} checked'
        elif is_uptrend and self.scan_error:
            status = self.scan_error
        elif is_uptrend and result:
            if not result.tickers and not search:
                status = 'No tickers with all 3 trends up' if result.unavailable < result.checked else 'Price history unavailable'
            if result.unavailable:
                status += f'\n{result.unavailable:,} without usable history'
        self.sidebar_status.setText(status)

    def select_first_match(self):
        if self.ticker_list.count():
            self.ticker_list.setCurrentRow(0)

    def change_tab(self, index):
        if index == 1 and self.scan_result is None and not self.scan_error:
            self.start_scan()
        self.refresh_tickers()

    def start_scan(self):
        if self.scan_running:
            return
        self.scan_running = True
        self.scan_error = ''
        self.scan_result = None
        worker = Worker(0, partial(bot.init, self.scan_stop), 'Scan interrupted. Retry to check remaining tickers.',
                        report_progress=True)
        worker.signals.progress.connect(self.update_scan)
        worker.signals.finished.connect(self.finish_scan)
        self.scan_pool.start(worker)
        self.refresh_tickers()

    def update_scan(self, result):
        self.scan_result = result
        if self.tabs.currentIndex() == 1:
            self.refresh_tickers()

    def finish_scan(self, request_id, result, error):
        self.scan_running = False
        self.scan_error = error
        self.update_scan(result if result is not None else self.scan_result)

    def select_ticker(self, item, previous):
        if item and item.text() != self.ticker:
            self.load_chart(item.text())

    def load_chart(self, ticker):
        self.ticker = ticker
        self.request_id += 1
        self.chart_title.setText(ticker)
        self.chart_detail.clear()
        self.cache_retry.hide()
        self.signal_panel.hide()
        self.show_state('Loading chart', f'Fetching price history for {ticker}.')
        self.chart_pool.clear()
        worker = Worker(self.request_id, partial(bot.getChart, ticker), 'The chart could not be generated. Try loading it again.')
        worker.signals.finished.connect(self.finish_chart)
        self.chart_pool.start(worker)

    def finish_chart(self, request_id, result, error):
        if request_id != self.request_id:
            return
        if error:
            self.show_state('Chart unavailable', error, retry=True)
            return
        pixmap = QPixmap(str(result.path))
        if pixmap.isNull():
            self.show_state('Chart unavailable', 'The chart image could not be read. Try loading it again.', retry=True)
            return

        timeframe = 'Daily / 1 year' if (INTERVAL, PERIOD) == ('1d', '1y') else f'{INTERVAL} / {PERIOD}'
        prefix = 'Cached through' if result.historical else 'Through'
        self.chart_detail.setText(f'{timeframe}\n{prefix} {result.last_session:%d %b %Y}')
        self.cache_retry.setVisible(result.historical)
        for indicator, direction in zip(self.signal_directions, result.directions):
            label, color = {True: ('Up', UP_COLOR), False: ('Down', DOWN_COLOR), None: ('Unavailable', TEXT_COLOR)}[direction]
            indicator.setText(label)
            indicator.setStyleSheet(f'color: {color};')
        self.signal_panel.show()
        self.chart_view.pixmap = pixmap
        self.chart_view.update()
        self.chart_stack.setCurrentWidget(self.chart_view)

    def show_state(self, title, message, retry=False):
        self.state_title.setText(title)
        self.state_body.setText(message)
        self.retry.setVisible(retry)
        self.chart_stack.setCurrentWidget(self.chart_state)

    def resizeEvent(self, event):
        self.sidebar.setFixedWidth(min(251, max(190, int(event.size().width() * 0.23))))
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.scan_stop.set()
        self.chart_pool.clear()
        super().closeEvent(event)


def darken_title_bar(window):
    if sys.platform != 'win32' or QApplication.platformName() != 'windows':
        return
    from ctypes import WinDLL, byref, c_long, c_void_p, sizeof
    from ctypes.wintypes import DWORD, HWND

    set_attribute = WinDLL('dwmapi').DwmSetWindowAttribute
    set_attribute.argtypes = (HWND, DWORD, c_void_p, DWORD)
    set_attribute.restype = c_long
    hwnd = int(window.winId())

    def colorref(hex_color):
        red, green, blue = bytes.fromhex(hex_color[1:])
        return red | (green << 8) | (blue << 16)

    # DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_CAPTION_COLOR and DWMWA_TEXT_COLOR.
    for attribute, value in ((20, 1), (35, colorref(RAIL_BG)), (36, colorref(INK_COLOR))):
        setting = DWORD(value)
        set_attribute(hwnd, attribute, byref(setting), sizeof(setting))


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = MainWindow()
    darken_title_bar(window)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
