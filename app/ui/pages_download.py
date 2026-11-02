"""Pantalla de análisis y descarga de YouTube o archivos locales."""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QSettings, QThreadPool, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from app.config import ProjectPaths
from app.core.download import (
    DownloadOptions, DownloadProgress, DownloadResult, MediaInfo, VideoInfo,
    analyze_video, download_video, validate_youtube_url,
)
from app.core.media import MEDIA_EXTENSIONS, probe_media
from app.core.utils import format_bytes, format_duration, format_eta, format_speed
from app.services.workers import TaskFailure, TaskWorker
from app.ui.widgets import Card, DropZone, FileResultList, PageHeader, Spinner


class DownloadPage(QWidget):
    sourceChanged = Signal()
    processRequested = Signal()
    errorOccurred = Signal(object)
    logMessage = Signal(str, str)

    def __init__(self, paths: ProjectPaths) -> None:
        super().__init__()
        self.paths = paths
        self.video_info: VideoInfo | None = None
        self.local_info: MediaInfo | None = None
        self.last_result: DownloadResult | None = None
        self.cancel_event = threading.Event()
        self.active_worker: TaskWorker | None = None
        self.settings = QSettings()
        self._build_ui()
        self._restore_settings()
        self._set_mode("youtube")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(PageHeader("Descargar", "Analizá un video de YouTube o usá un archivo multimedia local."))

        source = Card()
        mode_row = QHBoxLayout()
        self.youtube_button = QPushButton("YouTube")
        self.local_button = QPushButton("Archivo local")
        for button in (self.youtube_button, self.local_button):
            button.setObjectName("segment")
            button.setCheckable(True)
            mode_row.addWidget(button)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.youtube_button)
        self.mode_group.addButton(self.local_button)
        self.youtube_button.clicked.connect(lambda: self._set_mode("youtube"))
        self.local_button.clicked.connect(lambda: self._set_mode("local"))
        mode_row.addStretch()
        source.layout.addLayout(mode_row)

        self.source_stack = QStackedWidget()
        youtube = QWidget()
        yt_layout = QVBoxLayout(youtube)
        yt_layout.setContentsMargins(0, 0, 0, 0)
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=… o https://youtu.be/…")
        self.url_edit.textChanged.connect(self._url_changed)
        self.url_edit.returnPressed.connect(self.analyze)
        url_row.addWidget(self.url_edit, 1)
        self.analyze_button = QPushButton("Analizar")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        self.analyze_button.setEnabled(False)
        url_row.addWidget(self.analyze_button)
        yt_layout.addLayout(url_row)
        yt_drop = DropZone("Arrastrá aquí un enlace de YouTube")
        yt_drop.dropped.connect(self._url_dropped)
        yt_layout.addWidget(yt_drop)
        self.source_stack.addWidget(youtube)

        local = QWidget()
        local_layout = QVBoxLayout(local)
        local_layout.setContentsMargins(0, 0, 0, 0)
        select = QPushButton("Seleccionar archivo…")
        select.clicked.connect(self.select_local_file)
        local_layout.addWidget(select)
        local_drop = DropZone("Arrastrá aquí un video o audio")
        local_drop.dropped.connect(self.probe_local)
        local_layout.addWidget(local_drop)
        self.source_stack.addWidget(local)
        source.layout.addWidget(self.source_stack)
        root.addWidget(source)

        self.preview = Card()
        self.preview.setObjectName("previewCard")
        preview_row = QHBoxLayout()
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(192, 108)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setText("Sin miniatura")
        self.thumbnail.setStyleSheet("border-radius: 7px; background: rgba(128,128,128,30);")
        preview_row.addWidget(self.thumbnail)
        info_layout = QVBoxLayout()
        self.preview_title = QLabel("—")
        self.preview_title.setObjectName("sectionTitle")
        self.preview_title.setWordWrap(True)
        info_layout.addWidget(self.preview_title)
        self.preview_details = QLabel("")
        self.preview_details.setProperty("muted", True)
        self.preview_details.setWordWrap(True)
        info_layout.addWidget(self.preview_details)
        info_layout.addStretch()
        preview_row.addLayout(info_layout, 1)
        self.preview.layout.addLayout(preview_row)
        self.preview.hide()
        root.addWidget(self.preview)

        self.options_card = Card()
        title = QLabel("Opciones de descarga")
        title.setObjectName("sectionTitle")
        self.options_card.layout.addWidget(title)
        self.audio_only = QCheckBox("Solo audio (desactivado = video)")
        self.audio_only.toggled.connect(self._download_type_changed)
        self.options_card.layout.addWidget(self.audio_only)
        form = QFormLayout()
        self.audio_format = QComboBox()
        self.audio_format.addItems(["best", "m4a", "mp3", "wav"])
        self.audio_format.currentTextChanged.connect(self._download_type_changed)
        self.audio_format.currentTextChanged.connect(
            lambda value: self.settings.setValue("download/audio_format", value)
        )
        self.audio_quality = QComboBox()
        self.audio_quality.addItems(["best", "320", "256", "192", "128", "64"])
        self.audio_quality.currentTextChanged.connect(
            lambda value: self.settings.setValue("download/audio_quality", value)
        )
        self.audio_format_label = QLabel("Formato de audio")
        self.audio_quality_label = QLabel("Calidad")
        form.addRow(self.audio_format_label, self.audio_format)
        form.addRow(self.audio_quality_label, self.audio_quality)
        self.video_quality = QComboBox()
        self.video_quality.currentIndexChanged.connect(self._update_size_estimate)
        self.video_quality_label = QLabel("Calidad de video")
        form.addRow(self.video_quality_label, self.video_quality)
        self.options_card.layout.addLayout(form)
        self.size_estimate = QLabel("Tamaño estimado: — · Contenedor de video: MP4")
        self.size_estimate.setProperty("muted", True)
        self.options_card.layout.addWidget(self.size_estimate)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(self.paths.output_dir))
        self.output_edit.editingFinished.connect(
            lambda: self.settings.setValue("paths/output", self.output_edit.text())
        )
        output_row.addWidget(self.output_edit, 1)
        choose_output = QPushButton("Carpeta…")
        choose_output.clicked.connect(self.choose_output)
        output_row.addWidget(choose_output)
        self.options_card.layout.addLayout(output_row)
        root.addWidget(self.options_card)

        actions = Card()
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_row.addWidget(self.progress, 1)
        self.spinner = Spinner()
        progress_row.addWidget(self.spinner)
        actions.layout.addLayout(progress_row)
        self.status = QLabel("Listo para analizar o seleccionar un archivo.")
        self.status.setWordWrap(True)
        actions.layout.addWidget(self.status)
        button_row = QHBoxLayout()
        self.download_button = QPushButton("Descargar ahora")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self.start_download)
        button_row.addWidget(self.download_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setEnabled(False)
        button_row.addWidget(self.cancel_button)
        self.process_button = QPushButton("Usar en Procesar")
        self.process_button.clicked.connect(self.processRequested.emit)
        button_row.addWidget(self.process_button)
        button_row.addStretch()
        actions.layout.addLayout(button_row)
        self.results = FileResultList()
        self.results.hide()
        actions.layout.addWidget(self.results)
        root.addWidget(actions)
        root.addStretch()

    def _restore_settings(self) -> None:
        self.audio_only.setChecked(self.settings.value("download/audio_only", False, bool))
        self.audio_format.setCurrentText(self.settings.value("download/audio_format", "best", str))
        self.audio_quality.setCurrentText(self.settings.value("download/audio_quality", "best", str))
        self.output_edit.setText(self.settings.value("paths/output", str(self.paths.output_dir), str))

    def _set_mode(self, mode: str) -> None:
        is_youtube = mode == "youtube"
        self.youtube_button.setChecked(is_youtube)
        self.local_button.setChecked(not is_youtube)
        self.source_stack.setCurrentIndex(0 if is_youtube else 1)
        self.options_card.setVisible(is_youtube)
        self.download_button.setVisible(is_youtube)
        self.cancel_button.setVisible(is_youtube)
        self.preview.hide()
        self.results.hide()
        self.status.setText("Pegá una URL de YouTube." if is_youtube else "Seleccioná o arrastrá un archivo multimedia.")
        self.sourceChanged.emit()

    @property
    def is_youtube(self) -> bool:
        return self.youtube_button.isChecked()

    def _url_changed(self) -> None:
        self.analyze_button.setEnabled(validate_youtube_url(self.url_edit.text()))
        self.video_info = None

    def _url_dropped(self, value: str) -> None:
        self.url_edit.setText(value.strip())
        if validate_youtube_url(value):
            self.analyze()

    def analyze(self) -> None:
        url = self.url_edit.text().strip()
        if not validate_youtube_url(url):
            self.status.setText("La URL debe pertenecer a youtube.com o youtu.be.")
            return
        self.analyze_button.setEnabled(False)
        self.spinner.running(True)
        self.status.setText("Analizando formatos y metadatos…")
        worker = TaskWorker(lambda: analyze_video(url, self.paths))
        worker.signals.result.connect(self._analysis_ready)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(lambda: self.spinner.running(False))
        worker.signals.done.connect(lambda: self.analyze_button.setEnabled(True))
        QThreadPool.globalInstance().start(worker)

    def _analysis_ready(self, info: VideoInfo) -> None:
        self.video_info = info
        self.preview.show()
        self.preview_title.setText(info.title)
        self.preview_details.setText(f"{info.channel} · Duración: {format_duration(info.duration)}")
        saved_height = int(self.settings.value("download/video_height", 1080, int))
        self.video_quality.blockSignals(True)
        self.video_quality.clear()
        default_row = 0
        lower = [q.height for q in info.qualities if q.height <= 1080]
        nearest = max(lower) if lower else min((q.height for q in info.qualities), default=1080)
        available = {quality.height for quality in info.qualities}
        default_height = saved_height if saved_height in available else nearest
        for row, quality in enumerate(info.qualities):
            self.video_quality.addItem(quality.label, quality.height)
            if quality.height == default_height:
                default_row = row
        self.video_quality.setCurrentIndex(default_row)
        self.video_quality.blockSignals(False)
        self._update_size_estimate()
        self.status.setText(f"Análisis completo: {len(info.qualities)} calidades disponibles.")
        self._download_type_changed()
        self.sourceChanged.emit()
        if info.thumbnail:
            worker = TaskWorker(lambda: self._fetch_thumbnail(info.thumbnail or ""))
            worker.signals.result.connect(self._set_thumbnail)
            QThreadPool.globalInstance().start(worker)

    @staticmethod
    def _fetch_thumbnail(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "yt-transcript-ai/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read(8 * 1024 * 1024)

    def _set_thumbnail(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.thumbnail.setPixmap(pixmap.scaled(
                self.thumbnail.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def select_local_file(self) -> None:
        filters = " ".join(f"*{ext}" for ext in MEDIA_EXTENSIONS)
        filename, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar multimedia", str(Path.home()),
            f"Multimedia ({filters});;Todos los archivos (*)",
        )
        if filename:
            self.local_button.setChecked(True)
            self._set_mode("local")
            self.probe_local(filename)

    def probe_local(self, filename: str) -> None:
        path = Path(filename).expanduser()
        self.spinner.running(True)
        self.status.setText(f"Validando {path.name} con ffprobe…")
        worker = TaskWorker(lambda: probe_media(path))
        worker.signals.result.connect(self._local_ready)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(lambda: self.spinner.running(False))
        QThreadPool.globalInstance().start(worker)

    def _local_ready(self, info: MediaInfo) -> None:
        self.local_info = info
        self.preview.show()
        self.thumbnail.setText(info.path.suffix.upper().lstrip("."))
        self.preview_title.setText(info.path.name)
        self.preview_details.setText(
            f"Duración: {format_duration(info.duration)} · Formato: {info.format_name} · "
            f"Tamaño: {format_bytes(info.size_bytes)} · "
            f"{'Video y audio' if info.has_video and info.has_audio else 'Audio' if info.has_audio else 'Sin audio detectado'}"
        )
        self.status.setText("Archivo válido. Ya podés usarlo en Procesar.")
        self.sourceChanged.emit()

    def _download_type_changed(self) -> None:
        audio = self.audio_only.isChecked()
        self.audio_format.setVisible(audio)
        self.audio_quality.setVisible(audio and self.audio_format.currentText() == "mp3")
        self.audio_format_label.setVisible(audio)
        self.audio_quality_label.setVisible(audio and self.audio_format.currentText() == "mp3")
        self.video_quality.setVisible(not audio)
        self.video_quality_label.setVisible(not audio)
        self.size_estimate.setVisible(not audio)
        self.settings.setValue("download/audio_only", audio)

    def _update_size_estimate(self) -> None:
        if not self.video_info:
            self.size_estimate.setText("Tamaño estimado: — · Contenedor: MP4")
            return
        height = self.video_quality.currentData()
        option = next((q for q in self.video_info.qualities if q.height == height), None)
        estimate = format_bytes(option.estimated_bytes) if option else "Desconocido"
        self.size_estimate.setText(f"Tamaño estimado: {estimate} · Contenedor: MP4")
        self.settings.setValue("download/video_height", height or 1080)

    def choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)
            self.settings.setValue("paths/output", directory)

    def download_options(self, output_dir: Path | None = None) -> DownloadOptions:
        return DownloadOptions(
            url=self.url_edit.text().strip(),
            output_dir=output_dir or Path(self.output_edit.text()).expanduser(),
            audio_only=self.audio_only.isChecked(),
            audio_format=self.audio_format.currentText(),
            audio_quality=self.audio_quality.currentText(),
            video_height=int(self.video_quality.currentData() or 1080),
        )

    def start_download(self) -> None:
        if not self.video_info:
            self.status.setText("Primero analizá la URL para obtener los formatos reales.")
            return
        self.cancel_event.clear()
        self.progress.setValue(0)
        self.results.hide()
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        options = self.download_options()
        worker: TaskWorker
        worker = TaskWorker(
            lambda: download_video(
                options, self.paths, info=self.video_info,
                progress=lambda value: worker.signals.progress.emit(value),
                cancel_event=self.cancel_event,
            ),
            cancel=self.cancel_event.set,
        )
        worker.signals.progress.connect(self._download_progress)
        worker.signals.result.connect(self._download_finished)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(self._download_done)
        self.active_worker = worker
        QThreadPool.globalInstance().start(worker)
        self.status.setText("Iniciando descarga…")

    def _download_progress(self, value: DownloadProgress) -> None:
        if value.percent is None:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(int(value.percent))
        self.status.setText(
            f"{value.status} · {format_speed(value.speed)} · Restante: {format_eta(value.eta)}"
        )

    def _download_finished(self, result: DownloadResult) -> None:
        self.last_result = result
        if result.cancelled:
            partial = ", ".join(path.name for path in result.partial_files) or "No quedó archivo parcial."
            self.status.setText(f"Descarga cancelada. Parcial conservado: {partial}")
            return
        self.progress.setValue(100)
        self.status.setText("Descarga completa. También se generó el archivo de metadatos.")
        self.results.set_files(result.files)
        self.results.show()
        self.sourceChanged.emit()

    def _download_done(self) -> None:
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.active_worker = None

    def cancel_download(self) -> None:
        self.cancel_event.set()
        self.status.setText("Cancelando; el archivo .part se conservará…")
        self.cancel_button.setEnabled(False)

    def source_description(self) -> str:
        if self.is_youtube:
            return self.video_info.title if self.video_info else self.url_edit.text().strip()
        return self.local_info.path.name if self.local_info else "Sin archivo local"

    def has_source(self) -> bool:
        return bool(self.video_info) if self.is_youtube else bool(self.local_info)

    def _failed(self, failure: TaskFailure) -> None:
        self.status.setText(failure.message)
        self.errorOccurred.emit(failure)
