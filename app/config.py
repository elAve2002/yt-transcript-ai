"""Configuración y rutas del proyecto para la aplicación de escritorio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def output_dir(self) -> Path:
        return self.root / "salida"

    @property
    def temp_dir(self) -> Path:
        return self.root / "temporales"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    @property
    def python(self) -> Path:
        return self.root / ".venv" / "bin" / "python"

    @property
    def whisper_dir(self) -> Path:
        return self.root / "whisper"

    @property
    def whisper_cli(self) -> Path:
        return self.whisper_dir / "build" / "bin" / "whisper-cli"

    @property
    def whisper_models(self) -> Path:
        return self.whisper_dir / "models"

    @property
    def pyannote_script(self) -> Path:
        return self.root / "pyannote" / "prueba_pyannote_V2.py"

    @property
    def merge_script(self) -> Path:
        return self.root / "merge" / "merge_whisper_pyannote.py"

    @property
    def downloader_script(self) -> Path:
        return self.root / "yt_dlp" / "descargadorYT_V2.py"


DEFAULT_MODEL = "ggml-large-v3-turbo.bin"
ORGANIZATION = "elAve2002"
APPLICATION = "yt-transcript-ai"


def project_paths() -> ProjectPaths:
    return ProjectPaths(Path(__file__).resolve().parent.parent)
