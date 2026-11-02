"""Análisis y descarga con yt-dlp reutilizando el descargador existente."""

from __future__ import annotations

import importlib.util
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from app.config import ProjectPaths


class DownloadCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class QualityOption:
    height: int
    estimated_bytes: int | None = None

    @property
    def label(self) -> str:
        return f"{self.height}p"


@dataclass
class VideoInfo:
    url: str
    title: str
    channel: str
    duration: float | None
    thumbnail: str | None
    identifier: str
    qualities: list[QualityOption]
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class DownloadOptions:
    url: str
    output_dir: Path
    audio_only: bool = False
    audio_format: str = "best"  # best, m4a, mp3, wav
    audio_quality: str = "best"
    video_height: int = 1080


@dataclass(frozen=True)
class DownloadProgress:
    percent: float | None
    downloaded_bytes: int
    total_bytes: int | None
    speed: float | None
    eta: float | None
    status: str


@dataclass
class DownloadResult:
    files: list[Path]
    media_file: Path | None
    metadata_file: Path | None
    partial_files: list[Path] = field(default_factory=list)
    cancelled: bool = False


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float | None
    format_name: str
    size_bytes: int
    has_video: bool
    has_audio: bool


def validate_youtube_url(url: str) -> bool:
    candidate = url.strip()
    if not candidate:
        return False
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        host = (urlparse(candidate).hostname or "").lower()
    except ValueError:
        return False
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _load_legacy_downloader(paths: ProjectPaths):
    """La carpeta local yt_dlp queda oculta por el paquete pip; se carga por ruta."""
    spec = importlib.util.spec_from_file_location("_yt_transcript_legacy_downloader", paths.downloader_script)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo cargar el descargador existente.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def friendly_yt_dlp_error(exc: Exception, action: str = "descargar") -> str:
    """Convierte errores de yt-dlp en mensajes accionables para la GUI."""
    text = str(exc)
    lowered = text.lower()
    if "403" in text or "forbidden" in lowered:
        detail = (
            "YouTube bloqueó la petición (403), normalmente por una versión vieja de yt-dlp. "
            "Actualizá yt-dlp desde la pantalla Actualizaciones y volvé a intentar."
        )
    elif "429" in text or "too many requests" in lowered:
        detail = "YouTube limitó las peticiones (429). Esperá unos minutos antes de reintentar."
    elif "unavailable" in lowered:
        detail = "El video no está disponible (privado, eliminado o con restricción regional)."
    elif "sign in" in lowered or "login" in lowered or "age" in lowered and "restrict" in lowered:
        detail = "YouTube pidió iniciar sesión; el video puede ser privado o con restricción de edad."
    else:
        detail = text
    return f"No se pudo {action} el video. {detail}"


def _identifier(info: dict[str, Any], paths: ProjectPaths) -> str:
    legacy = _load_legacy_downloader(paths)
    channel = info.get("channel") or info.get("uploader") or "unknown"
    upload_date = info.get("upload_date")
    if upload_date:
        try:
            date = datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            date = "unknown_date"
    else:
        date = "unknown_date"
    return f"{legacy.sanitize_filename(channel)}_{date}"


def quality_options(info: dict[str, Any]) -> list[QualityOption]:
    formats = info.get("formats") or []
    heights = sorted({
        int(item["height"]) for item in formats
        if item.get("height") and item.get("vcodec") != "none"
    })
    audio_sizes = [
        int(item.get("filesize") or item.get("filesize_approx") or 0)
        for item in formats
        if item.get("acodec") != "none" and item.get("vcodec") == "none"
    ]
    audio_size = max(audio_sizes, default=0)
    options: list[QualityOption] = []
    for height in heights:
        video_sizes = [
            int(item.get("filesize") or item.get("filesize_approx") or 0)
            for item in formats
            if item.get("height") == height and item.get("vcodec") != "none"
        ]
        video_size = max(video_sizes, default=0)
        estimate = video_size + audio_size
        options.append(QualityOption(height, estimate or None))
    return options


def analyze_video(url: str, paths: ProjectPaths, timeout: int = 25) -> VideoInfo:
    if not validate_youtube_url(url):
        raise ValueError("Ingresá una URL válida de youtube.com o youtu.be.")
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": timeout,
        "extract_flat": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
    except DownloadError as exc:
        raise RuntimeError(friendly_yt_dlp_error(exc, "analizar")) from exc
    if not info:
        raise RuntimeError("YouTube no devolvió información del video.")
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]
    return VideoInfo(
        url=url.strip(),
        title=info.get("title") or "Video de YouTube",
        channel=info.get("channel") or info.get("uploader") or "Canal desconocido",
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail"),
        identifier=_identifier(info, paths),
        qualities=quality_options(info),
        raw=info,
    )


def _generated_files(output_dir: Path, identifier: str) -> tuple[list[Path], list[Path]]:
    complete: list[Path] = []
    partial: list[Path] = []
    for path in output_dir.glob(f"{identifier}_*"):
        if not path.is_file():
            continue
        if path.name.endswith((".part", ".ytdl")) or ".part-" in path.name:
            partial.append(path)
        else:
            complete.append(path)
    return sorted(complete), sorted(partial)


def download_video(
    options: DownloadOptions,
    paths: ProjectPaths,
    *,
    info: VideoInfo | None = None,
    progress: Callable[[DownloadProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> DownloadResult:
    cancel_event = cancel_event or threading.Event()
    video_info = info or analyze_video(options.url, paths)
    options.output_dir.mkdir(parents=True, exist_ok=True)
    identifier = video_info.identifier

    def emit(value: DownloadProgress) -> None:
        if progress:
            progress(value)

    def hook(data: dict[str, Any]) -> None:
        if cancel_event.is_set():
            raise DownloadCancelled("Descarga cancelada por el usuario.")
        status = data.get("status")
        if status == "downloading":
            downloaded = int(data.get("downloaded_bytes") or 0)
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = downloaded * 100 / total if total else None
            emit(DownloadProgress(
                percent, downloaded, int(total) if total else None,
                data.get("speed"), data.get("eta"), "Descargando",
            ))
        elif status == "finished":
            emit(DownloadProgress(100.0, int(data.get("total_bytes") or 0),
                                  data.get("total_bytes"), None, 0, "Procesando archivo"))

    ydl_options: dict[str, Any] = {
        "outtmpl": str(options.output_dir / f"{identifier}_{'audio' if options.audio_only else 'video'}.%(ext)s"),
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "continuedl": True,
        "socket_timeout": 25,
    }
    if options.audio_only:
        ydl_options["format"] = "bestaudio/best"
        if options.audio_format != "best":
            processor: dict[str, Any] = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": options.audio_format,
            }
            if options.audio_format == "mp3" and options.audio_quality != "best":
                processor["preferredquality"] = options.audio_quality
            ydl_options["postprocessors"] = [processor]
    else:
        legacy = _load_legacy_downloader(paths)
        heights = {quality.height for quality in video_info.qualities}
        if not heights:
            raise RuntimeError("No se encontraron streams de video en el enlace.")
        chosen = legacy.get_closest_quality(heights, options.video_height)
        ydl_options["format"] = f"bestvideo[height={chosen}]+bestaudio/best"
        ydl_options["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            ydl.download([options.url])
    except Exception as exc:
        if cancel_event.is_set() or isinstance(exc, DownloadCancelled):
            _, partial = _generated_files(options.output_dir, identifier)
            return DownloadResult([], None, None, partial, cancelled=True)
        if isinstance(exc, DownloadError):
            raise RuntimeError(friendly_yt_dlp_error(exc)) from exc
        raise

    legacy = _load_legacy_downloader(paths)
    legacy.write_metadata(video_info.raw, options.output_dir, identifier)
    files, _ = _generated_files(options.output_dir, identifier)
    metadata = options.output_dir / f"{identifier}.md"
    if metadata.exists() and metadata not in files:
        files.append(metadata)
    media = next((path for path in files if path.suffix.lower() in {
        ".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".wav", ".flac", ".opus", ".ogg"
    }), None)
    return DownloadResult(files, media, metadata if metadata.exists() else None)
