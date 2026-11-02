"""Pantalla de inicio y accesos rápidos."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.widgets import Card, PageHeader


class HomePage(QWidget):
    navigateRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)
        root.addWidget(PageHeader(
            "Inicio",
            "Descargá, transcribí y separá hablantes con un pipeline local. Los datos y tokens permanecen en tu Mac.",
        ))
        hero = Card()
        title = QLabel("Tu próximo guion, sin terminal")
        title.setObjectName("sectionTitle")
        hero.layout.addWidget(title)
        description = QLabel(
            "Pegá una URL o arrastrá un archivo, elegí el modelo Whisper y ejecutá solo las etapas que necesites. "
            "Podés cancelar en cualquier momento y reutilizar los resultados existentes."
        )
        description.setWordWrap(True)
        hero.layout.addWidget(description)
        actions = QHBoxLayout()
        download = QPushButton("Nuevo video")
        download.setObjectName("primary")
        download.clicked.connect(lambda: self.navigateRequested.emit("download"))
        actions.addWidget(download)
        process = QPushButton("Ir a Procesar")
        process.clicked.connect(lambda: self.navigateRequested.emit("process"))
        actions.addWidget(process)
        actions.addStretch()
        hero.layout.addLayout(actions)
        root.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(12)
        items = [
            ("1 · Origen", "YouTube con formatos reales, miniatura y metadatos, o multimedia local validado con ffprobe."),
            ("2 · Transcripción", "Modelos GGML instalables desde la app, SRT y JSON con timestamps."),
            ("3 · Hablantes", "Diarización con pyannote y token protegido; nunca aparece en la línea de comandos."),
            ("4 · Resultado", "Guion final con tiempos y hablantes, archivos reutilizables y accesos directos para abrirlos."),
        ]
        for index, (heading, text) in enumerate(items):
            card = Card()
            label = QLabel(heading)
            label.setObjectName("sectionTitle")
            card.layout.addWidget(label)
            body = QLabel(text)
            body.setWordWrap(True)
            card.layout.addWidget(body)
            grid.addWidget(card, index // 2, index % 2)
        root.addLayout(grid)
        root.addStretch()
