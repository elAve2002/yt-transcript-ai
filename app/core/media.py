"""Inspección de archivos multimedia locales con ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.core.download import MediaInfo

MEDIA_EXTENSIONS = (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".wav", ".flac")


def is_media_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS


def probe_media(path: Path, timeout: int = 20) -> MediaInfo:
    if not is_media_file(path):
        raise ValueError("Seleccioná un archivo multimedia compatible.")
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("No se encontró ffprobe. Instalá ffmpeg con 'brew install ffmpeg'.")
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-show_entries",
             "format=duration,format_name,size:stream=codec_type",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffprobe tardó demasiado en analizar el archivo.") from exc
    if result.returncode:
        raise RuntimeError(f"No se pudo leer el archivo multimedia. {result.stderr.strip()}")
    data = json.loads(result.stdout)
    format_data = data.get("format") or {}
    streams = data.get("streams") or []
    duration = format_data.get("duration")
    return MediaInfo(
        path=path,
        duration=float(duration) if duration else None,
        format_name=format_data.get("format_name") or path.suffix.lstrip("."),
        size_bytes=int(format_data.get("size") or path.stat().st_size),
        has_video=any(stream.get("codec_type") == "video" for stream in streams),
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
    )
