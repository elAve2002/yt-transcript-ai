"""Punto de entrada de la GUI."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from PySide6.QtWidgets import QApplication

from app.config import APPLICATION, ORGANIZATION, project_paths
from app.core.ffmpeg import ensure_ffmpeg
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


def warm_ffmpeg_in_background() -> None:
    """Deja el ffmpeg empaquetado listo sin bloquear el arranque de la GUI."""

    def worker() -> None:
        try:
            ensure_ffmpeg()
        except Exception:  # el pipeline reintenta y informa al usarlo
            logging.getLogger(__name__).warning(
                "No se pudo preparar el ffmpeg empaquetado; se reintentará al usarlo.",
                exc_info=True,
            )

    threading.Thread(target=worker, daemon=True, name="ffmpeg-warmup").start()


def main() -> int:
    configure_logging()
    warm_ffmpeg_in_background()
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
