"""Punto de entrada de la GUI."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import QApplication

from app.config import APPLICATION, ORGANIZATION, project_paths
from app.ui.main_window import MainWindow
from app.ui.theme import stylesheet


def configure_logging() -> None:
    paths = project_paths()
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        paths.logs_dir / "app.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> int:
    configure_logging()
    application = QApplication(sys.argv)
    application.setOrganizationName(ORGANIZATION)
    application.setApplicationName(APPLICATION)
    application.setApplicationDisplayName("yt-transcript-ai")
    application.setStyleSheet(stylesheet())
    window = MainWindow(project_paths())
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
