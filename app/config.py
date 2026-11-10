"""Configuración y rutas del proyecto para la aplicación de escritorio."""

from __future__ import annotations

import shutil
import sys
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
        if sys.platform == "win32":
            return self.root / ".venv" / "Scripts" / "python.exe"
        return self.root / ".venv" / "bin" / "python"

    @property
    def whisper_dir(self) -> Path:
        return self.root / "whisper"

    @property
    def whisper_cli(self) -> Path:
        executable = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
        return self.whisper_dir / "build" / "bin" / executable

    def find_whisper_cli(self) -> Path | None:
        """Busca el ejecutable en builds POSIX y multiconfiguración de Windows."""
        candidates = [
            self.whisper_cli,
            self.whisper_cli.parent / "Release" / self.whisper_cli.name,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        executable = shutil.which(self.whisper_cli.name)
        return Path(executable) if executable else None

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
