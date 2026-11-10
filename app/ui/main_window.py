"""Ventana principal, navegación lateral y servicios de UX globales."""

from __future__ import annotations

import logging

import qtawesome as qta
from PySide6.QtCore import QByteArray, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from app.config import ProjectPaths
from app.services.workers import TaskFailure
from app.ui.pages_download import DownloadPage
from app.ui.pages_home import HomePage
from app.ui.pages_process import ProcessPage
from app.ui.pages_settings import SettingsPage
from app.ui.pages_updates import UpdatesPage
from app.ui.theme import get_palette, stylesheet

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, paths: ProjectPaths) -> None:
        super().__init__()
        self.paths = paths
        self.settings = QSettings()
        self.theme_name = self.settings.value("appearance/theme", "system", str)
        self.accent = self.settings.value("appearance/accent", "#4f46e5", str)
        self.setWindowTitle("yt-transcript-ai")
        self.setMinimumSize(1000, 700)
        self.resize(1240, 820)
        self._build_ui()
        self._build_menu()
        self._restore_geometry()
        self.apply_theme(self.theme_name, self.accent)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(215)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 22, 12, 14)
        side.setSpacing(6)
        brand = QLabel("yt-transcript-ai")
        brand.setObjectName("sectionTitle")
        side.addWidget(brand)
        subtitle = QLabel("Pipeline multimedia local")
        subtitle.setProperty("muted", True)
        side.addWidget(subtitle)
        side.addSpacing(20)

        self.stack = QStackedWidget()
        self.nav_group = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages: dict[str, QWidget] = {}
        definitions = [
            ("home", "Inicio", "fa5s.home"),
            ("download", "Descargar", "fa5s.download"),
            ("process", "Procesar", "fa5s.play"),
            ("updates", "Actualizaciones", "fa5s.sync-alt"),
            ("settings", "Ajustes", "fa5s.cog"),
        ]
        for key, label, icon_name in definitions:
            button = QPushButton(qta.icon(icon_name), label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            side.addWidget(button)
        side.addStretch()
        open_key = QKeySequence("Ctrl+O").toString(QKeySequence.SequenceFormat.NativeText)
        process_key = QKeySequence("Ctrl+Return").toString(QKeySequence.SequenceFormat.NativeText)
        side.addWidget(QLabel(f"{open_key} abrir · {process_key} procesar"))
        root.addWidget(sidebar)

        self.home_page = HomePage()
        self.download_page = DownloadPage(self.paths)
        self.process_page = ProcessPage(self.paths, self.download_page)
        self.updates_page = UpdatesPage(self.paths)
        self.settings_page = SettingsPage(self.paths)
        for key, page in (
            ("home", self.home_page),
            ("download", self.download_page),
            ("process", self.process_page),
            ("updates", self.updates_page),
            ("settings", self.settings_page),
        ):
            self.pages[key] = page
            self.stack.addWidget(self._scroll(page))
        root.addWidget(self.stack, 1)

        self.home_page.navigateRequested.connect(self.navigate)
        self.download_page.processRequested.connect(self._open_process)
        self.download_page.sourceChanged.connect(self.process_page.update_source)
        self.process_page.sourceRequested.connect(lambda: self.navigate("download"))
        self.updates_page.updatesCounted.connect(self._update_badge)
        self.settings_page.themeChanged.connect(self.apply_theme)
        for page in (self.download_page, self.process_page, self.updates_page, self.settings_page):
            page.errorOccurred.connect(self.show_error)
        for page in (self.download_page, self.process_page, self.updates_page, self.settings_page):
            page.logMessage.connect(self._log)

        self.toast = QLabel("", central)
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.setWordWrap(True)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)
        self.navigate("home")

    @staticmethod
    def _scroll(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Archivo")
        open_action = QAction("Abrir archivo local…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._open_local)
        file_menu.addAction(open_action)

        actions_menu = self.menuBar().addMenu("Acciones")
        process_action = QAction("Iniciar pipeline", self)
        process_action.setShortcuts([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        process_action.triggered.connect(self._start_process)
        actions_menu.addAction(process_action)

        preferences = QAction("Ajustes…", self)
        preferences.setMenuRole(QAction.MenuRole.PreferencesRole)
        preferences.setShortcut(QKeySequence("Ctrl+,"))
        preferences.triggered.connect(lambda: self.navigate("settings"))
        self.menuBar().addAction(preferences)

    def navigate(self, key: str) -> None:
        if key not in self.pages:
            return
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentIndex(list(self.pages).index(key))
        if key == "process":
            self.process_page.update_source()
            self.process_page.refresh_models()

    def _open_process(self) -> None:
        self.navigate("process")

    def _open_local(self) -> None:
        self.navigate("download")
        self.download_page.select_local_file()

    def _start_process(self) -> None:
        self.navigate("process")
        self.process_page.start()

    def _update_badge(self, count: int) -> None:
        self.nav_buttons["updates"].setText(f"Actualizaciones  {count}" if count else "Actualizaciones")

    def apply_theme(self, theme: str, accent: str) -> None:
        self.theme_name = theme
        self.accent = accent
        QApplication.instance().setStyleSheet(stylesheet(theme, accent))
        palette = get_palette(theme, accent)
        self.toast.setStyleSheet(
            f"background: {palette.surface}; color: {palette.text}; border: 1px solid {palette.accent}; "
            "border-radius: 9px; padding: 11px 16px;"
        )

    def show_toast(self, message: str) -> None:
        self.toast.setText(message)
        self.toast.adjustSize()
        self.toast.setMaximumWidth(480)
        self.toast.show()
        self.toast.raise_()
        self._position_toast()
        self.toast_timer.start(4000)

    def _position_toast(self) -> None:
        central = self.centralWidget()
        self.toast.move(
            central.width() - self.toast.width() - 28,
            central.height() - self.toast.height() - 24,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self._position_toast()

    def show_error(self, failure: TaskFailure) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("No se pudo completar la operación")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(failure.message)
        copy = box.addButton("Copiar diagnóstico", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)
        box.exec()
        if box.clickedButton() == copy:
            QGuiApplication.clipboard().setText(failure.diagnostic)
            self.show_toast("Diagnóstico copiado. No incluye tu token.")

    def _log(self, level: str, message: str) -> None:
        numeric = getattr(logging, level.upper(), logging.INFO)
        logger.log(numeric, "%s", message)
        if level.upper() == "SUCCESS":
            self.show_toast(message)

    def _restore_geometry(self) -> None:
        geometry = self.settings.value("window/geometry", QByteArray())
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.download_page.cancel_event.set()
        if self.process_page.runner:
            self.process_page.runner.cancel()
        super().closeEvent(event)
