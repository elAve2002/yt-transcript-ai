"""Ajustes de apariencia y token de Hugging Face."""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from app.config import ProjectPaths
from app.services.token import TokenStatus, TokenValidation, load_token, mask_token, save_token, validate_token
from app.services.workers import TaskFailure, TaskWorker
from app.ui.widgets import Card, PageHeader, Spinner


class SettingsPage(QWidget):
    themeChanged = Signal(str, str)
    logMessage = Signal(str, str)
    errorOccurred = Signal(object)

    def __init__(self, paths: ProjectPaths) -> None:
        super().__init__()
        self.paths = paths
        self.settings = QSettings()
        self.accent = self.settings.value("appearance/accent", "#4f46e5", str)
        self._build_ui()
        self.token_edit.setText(load_token(self.paths.env_file))
        self._update_override_label()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(PageHeader("Ajustes", "Apariencia y credenciales locales de la aplicación."))

        appearance = Card()
        title = QLabel("Apariencia")
        title.setObjectName("sectionTitle")
        appearance.layout.addWidget(title)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Tema"))
        self.theme = QComboBox()
        self.theme.addItem("Sistema", "system")
        self.theme.addItem("Claro", "light")
        self.theme.addItem("Oscuro", "dark")
        index = self.theme.findData(self.settings.value("appearance/theme", "system", str))
        self.theme.setCurrentIndex(max(0, index))
        theme_row.addWidget(self.theme)
        theme_row.addStretch()
        appearance.layout.addLayout(theme_row)
        accent_row = QHBoxLayout()
        accent_row.addWidget(QLabel("Color de acento"))
        self.accent_button = QPushButton(self.accent)
        self.accent_button.clicked.connect(self.choose_accent)
        accent_row.addWidget(self.accent_button)
        accent_row.addStretch()
        appearance.layout.addLayout(accent_row)
        apply_button = QPushButton("Aplicar apariencia")
        apply_button.clicked.connect(self.apply_appearance)
        appearance.layout.addWidget(apply_button)
        root.addWidget(appearance)

        token = Card()
        title = QLabel("Hugging Face / pyannote")
        title.setObjectName("sectionTitle")
        token.layout.addWidget(title)
        help_text = QLabel(
            'Necesitás un token con acceso a <b>pyannote/speaker-diarization-community-1</b>. '
            'Se guarda localmente en <code>.env</code> con permisos 600.'
        )
        help_text.setWordWrap(True)
        token.layout.addWidget(help_text)
        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("hf_…")
        self.token_edit.setAccessibleName("Token de Hugging Face")
        token_row.addWidget(self.token_edit, 1)
        self.show_token = QCheckBox("Mostrar")
        self.show_token.toggled.connect(self._toggle_token)
        token_row.addWidget(self.show_token)
        token.layout.addLayout(token_row)
        self.override_label = QLabel("")
        self.override_label.setProperty("muted", True)
        self.override_label.setWordWrap(True)
        token.layout.addWidget(self.override_label)
        buttons = QHBoxLayout()
        save = QPushButton("Guardar")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        buttons.addWidget(save)
        self.test_button = QPushButton("Probar token")
        self.test_button.clicked.connect(self.test)
        buttons.addWidget(self.test_button)
        link = QPushButton("Crear token en Hugging Face")
        link.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://huggingface.co/settings/tokens")))
        buttons.addWidget(link)
        buttons.addStretch()
        token.layout.addLayout(buttons)
        status_row = QHBoxLayout()
        self.token_status = QLabel("El token nunca se incluye en logs ni en la línea de comandos.")
        self.token_status.setWordWrap(True)
        status_row.addWidget(self.token_status, 1)
        self.spinner = Spinner()
        status_row.addWidget(self.spinner)
        token.layout.addLayout(status_row)
        root.addWidget(token)
        root.addStretch()

    def _toggle_token(self, visible: bool) -> None:
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def _update_override_label(self) -> None:
        if os.environ.get("PYANNOTE_KEY"):
            self.override_label.setText(
                "Hay un override activo por variable de entorno PYANNOTE_KEY; tiene prioridad sobre el archivo .env."
            )
        elif self.token_edit.text():
            self.override_label.setText(f"Token cargado: {mask_token(self.token_edit.text())}")

    def save(self) -> None:
        value = self.token_edit.text().strip()
        try:
            save_token(self.paths.env_file, value)
        except Exception as exc:
            self.token_status.setText(f"No se pudo guardar: {exc}")
            return
        self.token_status.setText("Token guardado en .env con permisos 600.")
        self._update_override_label()
        self.logMessage.emit("SUCCESS", "Configuración de Hugging Face guardada.")

    def test(self) -> None:
        value = self.token_edit.text().strip()
        if not value:
            self.token_status.setText("Pegá un token antes de probarlo.")
            return
        self.test_button.setEnabled(False)
        self.spinner.running(True)
        self.token_status.setText("Validando identidad y acceso al modelo…")
        worker = TaskWorker(lambda: validate_token(value))
        worker.signals.result.connect(self._validation_ready)
        worker.signals.failed.connect(self._failed)
        worker.signals.done.connect(lambda: self.test_button.setEnabled(True))
        worker.signals.done.connect(lambda: self.spinner.running(False))
        QThreadPool.globalInstance().start(worker)

    def _validation_ready(self, result: TokenValidation) -> None:
        prefixes = {
            TokenStatus.VALID: "✅ Válido",
            TokenStatus.NO_ACCESS: "⚠️ Sin acceso al modelo",
            TokenStatus.INVALID: "❌ Token inválido",
            TokenStatus.ERROR: "⚠️ No se pudo comprobar",
        }
        user = f" · Cuenta: {result.user}" if result.user else ""
        self.token_status.setText(f"{prefixes[result.status]} · {result.message}{user}")

    def _failed(self, failure: TaskFailure) -> None:
        self.token_status.setText(failure.message)
        self.errorOccurred.emit(failure)

    def choose_accent(self) -> None:
        color = QColorDialog.getColor(QColor(self.accent), self, "Color de acento")
        if color.isValid():
            self.accent = color.name()
            self.accent_button.setText(self.accent)

    def apply_appearance(self) -> None:
        theme = self.theme.currentData()
        self.settings.setValue("appearance/theme", theme)
        self.settings.setValue("appearance/accent", self.accent)
        self.themeChanged.emit(theme, self.accent)
