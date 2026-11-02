"""Pantalla de configuración y ejecución del pipeline."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.config import DEFAULT_MODEL, ProjectPaths
from app.core.download import DownloadProgress
from app.core.pipeline import (
    STAGE_LABELS, PipelineConfig, PipelineResult, PipelineRunner, Stage, StageState,
)
from app.core.utils import format_bytes, format_eta, format_speed
from app.core.whisper import list_installed_models
from app.services.workers import TaskFailure, TaskWorker
from app.ui.dialogs import ModelDownloadDialog
from app.ui.widgets import Card, FileResultList, LogConsole, PageHeader


class ProcessPage(QWidget):
    errorOccurred = Signal(object)
    logMessage = Signal(str, str)
    sourceRequested = Signal()

    STATE_TEXT = {
        StageState.PENDING: "Pendiente",
        StageState.RUNNING: "Ejecutando…",
        StageState.DONE: "Hecho",
        StageState.SKIPPED: "Omitido / reutilizado",
        StageState.ERROR: "Error",
        StageState.CANCELLED: "Cancelado",
    }

    def __init__(self, paths: ProjectPaths, download_page) -> None:
        super().__init__()
        self.paths = paths
        self.download_page = download_page
        self.settings = QSettings()
        self.runner: PipelineRunner | None = None
        self.active_worker: TaskWorker | None = None
        self.stage_checks: dict[Stage, QCheckBox] = {}
        self._build_ui()
        self.refresh_models()
        self.update_source()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(PageHeader("Procesar", "Ejecutá solo las etapas necesarias y reutilizá resultados existentes."))

        source = Card()
        row = QHBoxLayout()
        self.source_label = QLabel("Sin origen")
        self.source_label.setWordWrap(True)
        row.addWidget(self.source_label, 1)
        change = QPushButton("Cambiar origen")
        change.clicked.connect(self.sourceRequested.emit)
        row.addWidget(change)
        source.layout.addLayout(row)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Salida"))
        self.output_edit = QLineEdit(self.settings.value("paths/output", str(self.paths.output_dir), str))
        self.output_edit.editingFinished.connect(
            lambda: self.settings.setValue("paths/output", self.output_edit.text())
        )
        output_row.addWidget(self.output_edit, 1)
        choose = QPushButton("Elegir…")
        choose.clicked.connect(self.choose_output)
        output_row.addWidget(choose)
        source.layout.addLayout(output_row)
        root.addWidget(source)

        options = Card()
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Modelo Whisper"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentIndexChanged.connect(self._model_selected)
        model_row.addWidget(self.model_combo, 1)
        refresh = QPushButton("Actualizar lista")
        refresh.clicked.connect(self.refresh_models)
        model_row.addWidget(refresh)
        download = QPushButton("Descargar modelo…")
        download.clicked.connect(self.download_model)
        model_row.addWidget(download)
        options.layout.addLayout(model_row)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Idioma"))
        self.language = QComboBox()
        self.language.addItems(["es", "en", "auto"])
        self.language.setCurrentText(self.settings.value("pipeline/language", "es", str))
        language_row.addWidget(self.language)
        language_row.addStretch()
        options.layout.addLayout(language_row)
        self.whisper_warning = QLabel("")
        self.whisper_warning.setWordWrap(True)
        self.whisper_warning.setProperty("muted", True)
        options.layout.addWidget(self.whisper_warning)
        root.addWidget(options)

        stages = Card()
        title = QLabel("Etapas")
        title.setObjectName("sectionTitle")
        stages.layout.addWidget(title)
        check_row = QHBoxLayout()
        for stage in Stage:
            check = QCheckBox(STAGE_LABELS[stage])
            check.setChecked(True)
            self.stage_checks[stage] = check
            check_row.addWidget(check)
        check_row.addStretch()
        stages.layout.addLayout(check_row)
        self.force = QCheckBox("Forzar re-ejecución (sobrescribe resultados reutilizables)")
        stages.layout.addWidget(self.force)
        self.stage_table = QTableWidget(len(Stage), 2)
        self.stage_table.setHorizontalHeaderLabels(["Etapa", "Estado"])
        self.stage_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stage_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stage_table.verticalHeader().hide()
        self.stage_table.setMaximumHeight(190)
        self.stage_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, stage in enumerate(Stage):
            self.stage_table.setItem(row, 0, QTableWidgetItem(STAGE_LABELS[stage]))
            self.stage_table.setItem(row, 1, QTableWidgetItem(self.STATE_TEXT[StageState.PENDING]))
        stages.layout.addWidget(self.stage_table)
        root.addWidget(stages)

        run_card = Card()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        run_card.layout.addWidget(self.progress)
        self.status = QLabel("Listo.")
        self.status.setWordWrap(True)
        run_card.layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.run_button = QPushButton("Iniciar pipeline")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.start)
        buttons.addWidget(self.run_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("danger")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        run_card.layout.addLayout(buttons)
        self.results = FileResultList()
        self.results.hide()
        run_card.layout.addWidget(self.results)
        root.addWidget(run_card)

        self.console = LogConsole()
        root.addWidget(self.console, 1)

    def update_source(self) -> None:
        local = not self.download_page.is_youtube
        self.stage_checks[Stage.DOWNLOAD].setEnabled(not local)
        self.stage_checks[Stage.DOWNLOAD].setChecked(not local)
        self.source_label.setText(f"Origen: {self.download_page.source_description()}")

    def refresh_models(self) -> None:
        previous = self.settings.value("pipeline/model", DEFAULT_MODEL, str)
        models = list_installed_models(self.paths.whisper_models)
        self.model_combo.clear()
        for model in models:
            suffix = " · predeterminado" if model.is_default else ""
            self.model_combo.addItem(
                f"{model.display_name} · {format_bytes(model.size_bytes)}{suffix}", str(model.path)
            )
            self.model_combo.setItemData(self.model_combo.count() - 1, str(model.path), Qt.ItemDataRole.ToolTipRole)
        if not models:
            self.model_combo.addItem("No hay modelos instalados", None)
        else:
            index = self.model_combo.findData(str(self.paths.whisper_models / previous))
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
        warnings = []
        if not self.paths.whisper_cli.is_file():
            warnings.append("Falta whisper-cli: compilá con cmake -S whisper -B whisper/build && cmake --build whisper/build -j.")
        if not models:
            warnings.append("No hay ggml-*.bin: usá Descargar modelo. Las descargas y otras pantallas siguen disponibles.")
        self.whisper_warning.setText(" ".join(warnings))

    def _model_selected(self) -> None:
        path = self.model_combo.currentData()
        if path:
            self.settings.setValue("pipeline/model", Path(path).name)

    def download_model(self) -> None:
        dialog = ModelDownloadDialog(self.paths.whisper_models, self)
        if dialog.exec() and dialog.selected_path:
            self.settings.setValue("pipeline/model", dialog.selected_path.name)
            self.refresh_models()
            index = self.model_combo.findData(str(dialog.selected_path))
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

    def choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)
            self.settings.setValue("paths/output", directory)

    def start(self) -> None:
        if self.active_worker:
            return
        if not self.download_page.has_source():
            self.status.setText("Seleccioná y analizá un origen en la pantalla Descargar.")
            self.sourceRequested.emit()
            return
        model = self.model_combo.currentData()
        if self.stage_checks[Stage.TRANSCRIBE].isChecked() and not model:
            self.status.setText("Seleccioná o descargá un modelo Whisper antes de transcribir.")
            return
        output_dir = Path(self.output_edit.text()).expanduser()
        local = not self.download_page.is_youtube
        enabled = {stage for stage, check in self.stage_checks.items() if check.isChecked()}
        if local:
            enabled.discard(Stage.DOWNLOAD)
        config = PipelineConfig(
            output_dir=output_dir,
            temp_dir=self.paths.temp_dir,
            enabled_stages=enabled,
            whisper_model=Path(model) if model else self.paths.whisper_models / DEFAULT_MODEL,
            language=self.language.currentText(),
            force=self.force.isChecked(),
            source_url=self.download_page.url_edit.text().strip() if not local else None,
            local_file=self.download_page.local_info.path if local and self.download_page.local_info else None,
            video_info=self.download_page.video_info if not local else None,
            download_options=self.download_page.download_options(output_dir) if not local else None,
        )
        self.settings.setValue("paths/output", str(output_dir))
        self.settings.setValue("pipeline/language", self.language.currentText())
        self.results.hide()
        self.progress.setValue(0)
        for row in range(self.stage_table.rowCount()):
            self.stage_table.item(row, 1).setText(self.STATE_TEXT[StageState.PENDING])
        self.runner = PipelineRunner(
            self.paths, config,
            on_state=lambda stage, state: worker.signals.progress.emit(("state", stage, state)),
            on_log=lambda level, message: worker.signals.progress.emit(("log", level, message)),
            on_progress=lambda value: worker.signals.progress.emit(value),
        )
        worker: TaskWorker
        worker = TaskWorker(self.runner.run, cancel=self.runner.cancel)
        worker.signals.progress.connect(self._event)
        worker.signals.result.connect(self._finished)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(self._done)
        self.active_worker = worker
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Pipeline en ejecución…")
        self.console.append("INFO", "Iniciando pipeline.")
        QThreadPool.globalInstance().start(worker)

    def _event(self, value) -> None:
        if isinstance(value, DownloadProgress):
            if value.percent is not None:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(value.percent))
            else:
                self.progress.setRange(0, 0)
            self.status.setText(f"Descarga · {format_speed(value.speed)} · Restante: {format_eta(value.eta)}")
            return
        kind = value[0]
        if kind == "state":
            _, stage, state = value
            row = list(Stage).index(stage)
            self.stage_table.item(row, 1).setText(self.STATE_TEXT[state])
        elif kind == "log":
            _, level, message = value
            self.console.append(level, message)
            self.logMessage.emit(level, message)

    def _finished(self, result: PipelineResult) -> None:
        if result.cancelled:
            self.status.setText("Pipeline cancelado. Los archivos parciales se conservaron.")
            self.console.append("WARNING", "Pipeline cancelado.")
        else:
            self.status.setText("Pipeline finalizado correctamente.")
            self.console.append("SUCCESS", "Pipeline finalizado.")
            self.progress.setValue(100)
        self.results.set_files(result.files)
        self.results.setVisible(bool(result.files))

    def _failed(self, failure: TaskFailure) -> None:
        self.status.setText(failure.message)
        self.console.append("ERROR", failure.message)
        self.errorOccurred.emit(failure)

    def _done(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.active_worker = None
        self.runner = None

    def cancel(self) -> None:
        if self.runner:
            self.runner.cancel()
            self.status.setText("Cancelando etapa actual…")
            self.cancel_button.setEnabled(False)
