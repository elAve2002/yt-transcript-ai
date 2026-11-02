"""Diálogos de descarga de modelos Whisper."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.core.utils import format_bytes
from app.core.whisper import (
    ModelDownloadProgress, OfficialModel, download_model, official_models_with_sizes,
)
from app.services.workers import TaskWorker
from app.ui.widgets import Spinner


class ModelDownloadDialog(QDialog):
    def __init__(self, models_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.models_dir = models_dir
        self.models: list[OfficialModel] = []
        self.selected_path: Path | None = None
        self.cancel_event = threading.Event()
        self.setWindowTitle("Descargar modelo Whisper")
        self.resize(650, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Modelos oficiales de whisper.cpp. Los tamaños se consultan en Hugging Face."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Modelo", "Tamaño", "Estado"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.spinner = Spinner()
        layout.addWidget(self.spinner)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_button)
        self.download_button = QPushButton("Descargar")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self.start_download)
        buttons.addWidget(self.download_button)
        layout.addLayout(buttons)
        self.load_models()

    def load_models(self) -> None:
        self.spinner.running(True)
        self.download_button.setEnabled(False)
        worker = TaskWorker(official_models_with_sizes)
        worker.signals.result.connect(self._models_loaded)
        worker.signals.failed.connect(lambda failure: self._load_error(failure.message))
        QThreadPool.globalInstance().start(worker)

    def _models_loaded(self, models: list[OfficialModel]) -> None:
        self.spinner.running(False)
        self.models = models
        self.table.setRowCount(len(models))
        selected_row = 0
        for row, model in enumerate(models):
            self.table.setItem(row, 0, QTableWidgetItem(model.name))
            self.table.setItem(row, 1, QTableWidgetItem(format_bytes(model.size_bytes)))
            installed = (self.models_dir / model.filename).exists()
            self.table.setItem(row, 2, QTableWidgetItem("Instalado" if installed else "Disponible"))
            if model.name == "large-v3-turbo":
                selected_row = row
        self.table.selectRow(selected_row)
        self.download_button.setEnabled(True)

    def _load_error(self, message: str) -> None:
        self.spinner.running(False)
        self.status.setText(f"No se pudieron consultar los tamaños: {message}")

    def start_download(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.models):
            self.status.setText("Seleccioná un modelo.")
            return
        model = self.models[row]
        destination = self.models_dir / model.filename
        if destination.exists():
            self.selected_path = destination
            self.accept()
            return
        self.cancel_event.clear()
        self.progress.setValue(0)
        self.progress.show()
        self.download_button.setEnabled(False)
        self.status.setText(f"Descargando {model.name}…")
        worker: TaskWorker
        worker = TaskWorker(
            lambda: download_model(
                model, self.models_dir,
                progress=lambda value: worker.signals.progress.emit(value),
                cancel_event=self.cancel_event,
            ),
            cancel=self.cancel_event.set,
        )
        worker.signals.progress.connect(self._update_progress)
        self._active_worker = worker
        worker.signals.result.connect(self._download_finished)
        worker.signals.failed.connect(self._download_failed)
        QThreadPool.globalInstance().start(worker)

    def _update_progress(self, value: ModelDownloadProgress) -> None:
        if value.percent is not None:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(value.percent))
        else:
            self.progress.setRange(0, 0)
        total = format_bytes(value.total_bytes)
        self.status.setText(f"{format_bytes(value.downloaded_bytes)} de {total}")

    def _download_finished(self, path: Path) -> None:
        self.selected_path = path
        self.status.setText(f"Modelo instalado: {path.name}")
        self.progress.hide()
        self.accept()

    def _download_failed(self, failure) -> None:
        self.progress.hide()
        self.download_button.setEnabled(True)
        self.status.setText(failure.message)

    def cancel(self) -> None:
        if self.download_button.isEnabled():
            self.reject()
        else:
            self.cancel_event.set()
            self.status.setText("Cancelando descarga…")

    def closeEvent(self, event) -> None:
        self.cancel_event.set()
        super().closeEvent(event)
