"""Resolución de ffmpeg/ffprobe con respaldo empaquetado (static-ffmpeg).

Prefiere los binarios del sistema (por ejemplo, los instalados con Homebrew).
Si faltan, usa ``static-ffmpeg``, que descarga los binarios estáticos la
primera vez que se los necesita y queda dentro de ``.venv``.
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_ffmpeg(on_download: Callable[[str], None] | None = None) -> tuple[Path, Path]:
    """Devuelve ``(ffmpeg, ffprobe)`` como rutas listas para subprocess.

    Si el sistema no tiene ambos binarios, ``static-ffmpeg`` los descarga en
    su carpeta del entorno virtual (requiere internet la primera vez).
    """
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return Path(ffmpeg), Path(ffprobe)

    try:
        from static_ffmpeg import run
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "Faltan ffmpeg/ffprobe y el paquete estático 'static-ffmpeg'. "
            "Ejecutá 'uv sync' o instalá FFmpeg desde https://ffmpeg.org/download.html."
        ) from exc

    message = "Obteniendo ffmpeg/ffprobe empaquetados (solo la primera vez)..."
    logger.info(message)
    if on_download:
        on_download(message)
    try:
        ffmpeg_path, ffprobe_path = run.get_or_fetch_platform_executables_else_raise()
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo obtener el ffmpeg empaquetado: {exc}. "
            "Revisá la conexión a internet o instalá FFmpeg desde https://ffmpeg.org/download.html."
        ) from exc
    return Path(ffmpeg_path), Path(ffprobe_path)
