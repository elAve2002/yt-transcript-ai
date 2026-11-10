"""Panel no bloqueante de actualizaciones con confirmación y log en vivo."""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config import ProjectPaths
from app.core.process import format_command
from app.core.updates import UpdateChecker, UpdateComponent, UpdateExecutor, UpdateStatus
from app.services.workers import TaskFailure, TaskWorker
from app.ui.widgets import Card, PageHeader, Spinner

STATUS_TEXT = {
    UpdateStatus.AL_DIA: "Al día",
    UpdateStatus.ACTUALIZABLE: "Actualizable",
    UpdateStatus.NO_INSTALADO: "No instalado",
    UpdateStatus.ERROR: "No se pudo comprobar",
    UpdateStatus.DISTINTA: "Versión distinta",
}


class UpdateLogDialog(QDialog):
    def __init__(self, executor: UpdateExecutor, components: list[UpdateComponent], parent=None) -> None:
        super().__init__(parent)
        self.executor = executor
        self.components = components
        self.cancel_event = threading.Event()
        self.worker: TaskWorker | None = None
        self.success = False
        self.setWindowTitle("Aplicando actualizaciones")
        self.resize(760, 460)
        layout = QVBoxLayout(self)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        row = QHBoxLayout()
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.close)
        self.close_button.setEnabled(False)
        row.addStretch()
        row.addWidget(self.close_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel_event.set)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def start(self) -> None:
        worker: TaskWorker
        worker = TaskWorker(
            lambda: self.executor.execute(
                self.components,
                on_line=lambda line: worker.signals.log.emit("INFO", line),
                cancel_event=self.cancel_event,
            ),
            cancel=self.cancel_event.set,
        )
        worker.signals.log.connect(lambda _level, line: self.log.appendPlainText(line))
        worker.signals.result.connect(self._finished)
        worker.signals.failed.connect(self._failed)
        self.worker = worker
        QThreadPool.globalInstance().start(worker)

    def _finished(self, _result) -> None:
        self.success = True
        self.log.appendPlainText("\nActualizaciones finalizadas.")
        self.close_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def _failed(self, failure: TaskFailure) -> None:
        self.log.appendPlainText(f"\nError: {failure.message}")
        self.close_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        if self.worker and not self.close_button.isEnabled():
            self.cancel_event.set()
            event.ignore()
            return
        super().closeEvent(event)


class UpdatesPage(QWidget):
    updatesCounted = Signal(int)
    errorOccurred = Signal(object)
    logMessage = Signal(str, str)

    def __init__(self, paths: ProjectPaths) -> None:
        super().__init__()
        self.paths = paths
        self.checker = UpdateChecker(paths.root)
        self.components: list[UpdateComponent] = []
        self.checks: dict[str, QCheckBox] = {}
        self.active_worker: TaskWorker | None = None
        self._build_ui()
        QTimer.singleShot(400, lambda: self.check_updates(False))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        sources = "PyPI, Homebrew y whisper.cpp" if sys.platform == "darwin" else "PyPI y whisper.cpp"
        root.addWidget(PageHeader(
            "Actualizaciones", f"Versiones de {sources}. La caché dura 10 minutos."
        ))
        card = Card()
        toolbar = QHBoxLayout()
        self.check_button = QPushButton("Buscar actualizaciones")
        self.check_button.setObjectName("primary")
        self.check_button.clicked.connect(lambda: self.check_updates(False))
        toolbar.addWidget(self.check_button)
        self.update_button = QPushButton("Actualizar seleccionados")
        self.update_button.clicked.connect(self.update_selected)
        self.update_button.setEnabled(False)
        toolbar.addWidget(self.update_button)
        toolbar.addStretch()
        self.spinner = Spinner()
        toolbar.addWidget(self.spinner)
        card.layout.addLayout(toolbar)
        self.status = QLabel("Todavía no se comprobaron las versiones.")
        self.status.setWordWrap(True)
        card.layout.addWidget(self.status)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Componente", "Instalada", "Última", "Estado", "Acción"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        card.layout.addWidget(self.table)
        root.addWidget(card, 1)

    def check_updates(self, force: bool) -> None:
        if self.active_worker:
            return
        self.check_button.setEnabled(False)
        self.spinner.running(True)
        self.status.setText("Comprobando versiones en segundo plano…")
        worker = TaskWorker(lambda: self.checker.check_all(force=force))
        worker.signals.result.connect(self._loaded)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(self._check_done)
        self.active_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _loaded(self, components: list[UpdateComponent]) -> None:
        self.components = components
        self.checks.clear()
        self.table.setRowCount(len(components))
        available = 0
        for row, component in enumerate(components):
            check = QCheckBox()
            check.setEnabled(component.status == UpdateStatus.ACTUALIZABLE)
            check.toggled.connect(self._selection_changed)
            self.checks[component.key] = check
            self.table.setCellWidget(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(component.name))
            self.table.setItem(row, 2, QTableWidgetItem(component.installed or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(component.latest or "—"))
            status = STATUS_TEXT[component.status]
            if component.detail and component.status == UpdateStatus.ERROR:
                status = "No se pudo comprobar"
            item = QTableWidgetItem(status)
            item.setToolTip(component.detail or "")
            self.table.setItem(row, 4, item)
            action = QPushButton("Actualizar")
            action.setEnabled(component.status == UpdateStatus.ACTUALIZABLE)
            action.clicked.connect(lambda _=False, c=component: self.confirm_update([c]))
            self.table.setCellWidget(row, 5, action)
            available += component.status == UpdateStatus.ACTUALIZABLE
        self.status.setText(f"{available} actualizaciones disponibles." if available else "No hay actualizaciones pendientes.")
        self.updatesCounted.emit(available)
        self._selection_changed()

    def _check_done(self) -> None:
        self.check_button.setEnabled(True)
        self.spinner.running(False)
        self.active_worker = None

    def _failed(self, failure: TaskFailure) -> None:
        self.status.setText(f"No se pudo comprobar: {failure.message}")
        self.errorOccurred.emit(failure)

    def _selection_changed(self) -> None:
        selected = any(check.isChecked() for check in self.checks.values())
        self.update_button.setEnabled(selected)

    def update_selected(self) -> None:
        components = [
            component for component in self.components
            if self.checks.get(component.key) and self.checks[component.key].isChecked()
        ]
        self.confirm_update(components)

    @staticmethod
    def commands_text(components: list[UpdateComponent]) -> str:
        lines: list[str] = []
        for component in components:
            if component.kind == "whisper":
                lines.extend([
                    f"# {component.name}",
                    "Descargar y extraer la release en temporales/",
                    "Copiar el código conservando models/, build/ y .git/",
                    "cmake -S whisper -B whisper/build",
                    "cmake --build whisper/build --config Release --parallel",
                ])
            else:
                lines.append(format_command(component.command))
        return "\n".join(lines)

    def confirm_update(self, components: list[UpdateComponent]) -> None:
        if not components:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Confirmar actualización")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Se actualizarán {len(components)} componentes. Revisá los comandos exactos antes de continuar.")
        box.setDetailedText(self.commands_text(components))
        accept = box.addButton("Actualizar", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() != accept:
            return
        dialog = UpdateLogDialog(UpdateExecutor(self.paths.root), components, self)
        dialog.start()
        dialog.exec()
        if dialog.success:
            self.logMessage.emit("SUCCESS", "Actualizaciones aplicadas correctamente.")
        self.check_updates(True)
