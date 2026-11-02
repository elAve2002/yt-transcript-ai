"""Widgets reutilizables de la interfaz."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from app.ui.theme import get_palette


def icon(name: str, color: str | None = None):
    return qta.icon(name, color=color or get_palette().text)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, margins: int = 16) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(margins, margins, margins, margins)
        self.layout.setSpacing(10)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        heading = QLabel(title)
        heading.setObjectName("title")
        layout.addWidget(heading)
        if subtitle:
            description = QLabel(subtitle)
            description.setObjectName("subtitle")
            description.setWordWrap(True)
            layout.addWidget(description)


class Spinner(QProgressBar):
    def __init__(self) -> None:
        super().__init__()
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setMaximumWidth(180)
        self.hide()

    def running(self, active: bool) -> None:
        self.setVisible(active)


class DropZone(QFrame):
    dropped = Signal(str)

    def __init__(self, text: str) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("previewCard")
        layout = QVBoxLayout(self)
        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setProperty("muted", True)
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            value = urls[0].toLocalFile() or urls[0].toString()
        else:
            value = event.mimeData().text().strip()
        if value:
            self.dropped.emit(value)
            event.acceptProposedAction()


class LogConsole(QWidget):
    COLORS = {"INFO": "#d8dee9", "WARNING": "#fbbf24", "ERROR": "#f87171", "SUCCESS": "#4ade80", "DEBUG": "#93c5fd"}

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        title = QLabel("Consola")
        title.setObjectName("sectionTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()
        self.autoscroll = QCheckBox("Autoscroll")
        self.autoscroll.setChecked(True)
        toolbar.addWidget(self.autoscroll)
        copy = QPushButton("Copiar")
        copy.clicked.connect(self.copy)
        toolbar.addWidget(copy)
        save = QPushButton("Guardar…")
        save.clicked.connect(self.save_as)
        toolbar.addWidget(save)
        layout.addLayout(toolbar)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.document().setMaximumBlockCount(5000)
        self.text.setMinimumHeight(150)
        layout.addWidget(self.text)

    def append(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = self.COLORS.get(level.upper(), self.COLORS["INFO"])
        for line in message.splitlines() or [""]:
            self.text.appendHtml(
                f'<span style="color:#7f8c9f">{timestamp}</span> '
                f'<span style="color:{color}">[{html.escape(level.upper())}] '
                f'{html.escape(line)}</span>'
            )
        if self.autoscroll.isChecked():
            self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())

    def copy(self) -> None:
        self.text.selectAll()
        self.text.copy()
        cursor = self.text.textCursor()
        cursor.clearSelection()
        self.text.setTextCursor(cursor)

    def save_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Guardar log", "app-gui.log", "Log (*.log);;Texto (*.txt)")
        if filename:
            Path(filename).write_text(self.text.toPlainText(), encoding="utf-8")


class FileResultList(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def set_files(self, files: list[Path]) -> None:
        self.clear()
        for path in files:
            row = QHBoxLayout()
            label = QLabel(path.name)
            label.setToolTip(str(path))
            row.addWidget(label, 1)
            open_file = QPushButton("Abrir archivo")
            open_file.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            row.addWidget(open_file)
            open_folder = QPushButton("Abrir carpeta")
            open_folder.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent))))
            row.addWidget(open_folder)
            self.layout.addLayout(row)
        self.setVisible(bool(files))
