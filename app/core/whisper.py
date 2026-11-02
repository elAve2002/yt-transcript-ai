"""Inventario y descarga de modelos GGML de whisper.cpp."""

from __future__ import annotations

import os
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import DEFAULT_MODEL

# Lista oficial publicada por whisper.cpp/models/download-ggml-model.sh.
OFFICIAL_MODELS = (
    "tiny", "tiny.en", "tiny-q5_1", "tiny.en-q5_1", "tiny-q8_0",
    "base", "base.en", "base-q5_1", "base.en-q5_1", "base-q8_0",
    "small", "small.en", "small-q5_1", "small.en-q5_1", "small-q8_0",
    "medium", "medium.en", "medium-q5_0", "medium.en-q5_0", "medium-q8_0",
    "large-v3", "large-v3-q5_0", "large-v3-turbo",
    "large-v3-turbo-q5_0", "large-v3-turbo-q8_0",
)
MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


@dataclass(frozen=True)
class WhisperModel:
    name: str
    path: Path
    size_bytes: int
    is_default: bool

    @property
    def display_name(self) -> str:
        return self.name.removeprefix("ggml-").removesuffix(".bin")


@dataclass(frozen=True)
class OfficialModel:
    name: str
    filename: str
    url: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class ModelDownloadProgress:
    downloaded_bytes: int
    total_bytes: int | None
    percent: float | None
    speed: float | None


def list_installed_models(models_dir: Path, default_filename: str = DEFAULT_MODEL) -> list[WhisperModel]:
    if not models_dir.exists():
        return []
    models = [
        WhisperModel(path.name, path, path.stat().st_size, path.name == default_filename)
        for path in models_dir.glob("ggml-*.bin") if path.is_file()
    ]
    return sorted(models, key=lambda model: (not model.is_default, model.name.lower()))


def official_model(name: str) -> OfficialModel:
    if name not in OFFICIAL_MODELS:
        raise ValueError(f"Modelo desconocido: {name}")
    filename = f"ggml-{name}.bin"
    return OfficialModel(name, filename, f"{MODEL_BASE_URL}/{filename}")


def _request(url: str, method: str = "GET", timeout: int = 20) -> urllib.request.Request:
    return urllib.request.Request(
        url, method=method,
        headers={"User-Agent": "yt-transcript-ai/1.0"},
    )


def fetch_model_size(model: OfficialModel, timeout: int = 20) -> int | None:
    try:
        with urllib.request.urlopen(_request(model.url, "HEAD", timeout), timeout=timeout) as response:
            value = response.headers.get("X-Linked-Size") or response.headers.get("Content-Length")
            return int(value) if value else None
    except Exception:
        return None


def official_models_with_sizes(workers: int = 6) -> list[OfficialModel]:
    models = [official_model(name) for name in OFFICIAL_MODELS]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sizes = list(pool.map(fetch_model_size, models))
    return [OfficialModel(model.name, model.filename, model.url, size)
            for model, size in zip(models, sizes, strict=True)]


def download_model(
    model: OfficialModel,
    models_dir: Path,
    *,
    progress: Callable[[ModelDownloadProgress], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    cancel_event = cancel_event or threading.Event()
    models_dir.mkdir(parents=True, exist_ok=True)
    destination = models_dir / model.filename
    if destination.exists():
        return destination
    partial = destination.with_suffix(".bin.part")
    downloaded = 0
    try:
        with urllib.request.urlopen(_request(model.url), timeout=30) as response:
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header else None
            with partial.open("wb") as output:
                while True:
                    if cancel_event.is_set():
                        raise RuntimeError("Descarga del modelo cancelada.")
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(ModelDownloadProgress(
                            downloaded, total,
                            downloaded * 100 / total if total else None,
                            None,
                        ))
        if cancel_event.is_set():
            raise RuntimeError("Descarga del modelo cancelada.")
        os.replace(partial, destination)
        return destination
    except Exception:
        partial.unlink(missing_ok=True)
        raise
