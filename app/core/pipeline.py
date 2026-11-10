"""Orquestación del pipeline con estados, reutilización de archivos y cancelación."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from app.config import ProjectPaths
from app.core.download import DownloadOptions, DownloadProgress, VideoInfo, analyze_video, download_video
from app.core.ffmpeg import ensure_ffmpeg
from app.core.process import ProcessCancelled, SubprocessJob
from app.services.token import load_token


class Stage(str, Enum):
    DOWNLOAD = "download"
    EXTRACT = "extract"
    TRANSCRIBE = "transcribe"
    DIARIZE = "diarize"
    MERGE = "merge"


STAGE_LABELS = {
    Stage.DOWNLOAD: "Descargar",
    Stage.EXTRACT: "Extraer audio",
    Stage.TRANSCRIBE: "Transcribir",
    Stage.DIARIZE: "Diarizar",
    Stage.MERGE: "Fusionar",
}


class StageState(str, Enum):
    PENDING = "pendiente"
    RUNNING = "ejecutando"
    DONE = "hecho"
    SKIPPED = "omitido"
    ERROR = "error"
    CANCELLED = "cancelado"


@dataclass
class PipelineStates:
    values: dict[Stage, StageState] = field(default_factory=lambda: {
        stage: StageState.PENDING for stage in Stage
    })

    def transition(self, stage: Stage, state: StageState) -> None:
        self.values[stage] = state

    def as_dict(self) -> dict[Stage, StageState]:
        return dict(self.values)


class PipelineCancelled(RuntimeError):
    pass


@dataclass
class PipelineConfig:
    output_dir: Path
    temp_dir: Path
    enabled_stages: set[Stage]
    whisper_model: Path
    language: str = "es"
    force: bool = False
    source_url: str | None = None
    local_file: Path | None = None
    video_info: VideoInfo | None = None
    download_options: DownloadOptions | None = None


@dataclass
class PipelineResult:
    files: list[Path]
    states: dict[Stage, StageState]
    cancelled: bool = False


class PipelineRunner:
    def __init__(
        self,
        paths: ProjectPaths,
        config: PipelineConfig,
        *,
        on_state: Callable[[Stage, StageState], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
        on_progress: Callable[[DownloadProgress], None] | None = None,
    ) -> None:
        self.paths = paths
        self.config = config
        self.on_state = on_state
        self.on_log = on_log
        self.on_progress = on_progress
        self.states = PipelineStates()
        self.cancel_event = threading.Event()
        self.process = SubprocessJob(self.cancel_event)
        self._files: list[Path] = []
        self._source_file: Path | None = config.local_file
        self._wav_file: Path | None = None
        self._video_info = config.video_info

    def cancel(self) -> None:
        self.cancel_event.set()
        self.process.cancel()

    def _state(self, stage: Stage, state: StageState) -> None:
        self.states.transition(stage, state)
        if self.on_state:
            self.on_state(stage, state)

    def _log(self, message: str, level: str = "INFO") -> None:
        if self.on_log:
            self.on_log(level, message)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise PipelineCancelled("Pipeline cancelado por el usuario.")

    def run(self) -> PipelineResult:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        current: Stage | None = None
        try:
            for stage in Stage:
                current = stage
                self._check_cancel()
                if stage not in self.config.enabled_stages:
                    self._state(stage, StageState.SKIPPED)
                    continue
                self._state(stage, StageState.RUNNING)
                reused = self._execute(stage)
                self._state(stage, StageState.SKIPPED if reused else StageState.DONE)
            return PipelineResult(self._unique_files(), self.states.as_dict())
        except (PipelineCancelled, ProcessCancelled) as exc:
            if current:
                self._state(current, StageState.CANCELLED)
            self._log(str(exc), "WARNING")
            return PipelineResult(self._unique_files(), self.states.as_dict(), cancelled=True)
        except Exception as exc:
            if current:
                self._state(current, StageState.ERROR)
            label = STAGE_LABELS.get(current, "Pipeline") if current else "Pipeline"
            raise RuntimeError(f"{label}: {exc}") from exc

    def _execute(self, stage: Stage) -> bool:
        """Devuelve True si se reutilizó un archivo existente."""
        if stage == Stage.DOWNLOAD:
            return self._download()
        if stage == Stage.EXTRACT:
            return self._extract()
        if stage == Stage.TRANSCRIBE:
            return self._transcribe()
        if stage == Stage.DIARIZE:
            return self._diarize()
        return self._merge()

    def _download(self) -> bool:
        if self.config.local_file:
            self._source_file = self.config.local_file
            self._log("Origen local: no hace falta descargar.")
            return True
        if not self.config.source_url:
            raise RuntimeError("No hay una URL o archivo de origen seleccionado.")
        self._video_info = self._video_info or analyze_video(self.config.source_url, self.paths)
        if not self.config.force:
            existing = self._find_source_file()
            if existing:
                self._source_file = existing
                self._log(f"Se reutiliza la descarga existente: {existing.name}")
                return True
        options = self.config.download_options or DownloadOptions(
            self.config.source_url, self.config.output_dir
        )
        result = download_video(
            options, self.paths, info=self._video_info,
            progress=self.on_progress, cancel_event=self.cancel_event,
        )
        if result.cancelled:
            partial = ", ".join(path.name for path in result.partial_files) or "ninguno"
            raise PipelineCancelled(f"Descarga cancelada. Archivos parciales conservados: {partial}")
        self._source_file = result.media_file or self._find_source_file()
        self._files.extend(result.files)
        return False

    def _find_source_file(self) -> Path | None:
        if not self._video_info:
            return None
        for path in sorted(self.config.output_dir.glob(f"{self._video_info.identifier}_*")):
            if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".wav", ".flac", ".opus", ".ogg"}:
                return path
        return None

    def _require_source(self) -> Path:
        if self._source_file and self._source_file.exists():
            return self._source_file
        self._source_file = self._find_source_file()
        if self._source_file:
            return self._source_file
        raise RuntimeError("No se encontró el archivo de origen. Activá Descargar o seleccioná un archivo local.")

    def _require_wav(self) -> Path:
        if self._wav_file and self._wav_file.exists():
            return self._wav_file
        source = self._require_source()
        candidate = self.config.temp_dir / f"{source.stem}_BORRAR.wav"
        if candidate.exists():
            self._wav_file = candidate
            return candidate
        raise RuntimeError("No se encontró el WAV. Activá Extraer audio antes de esta etapa.")

    def _extract(self) -> bool:
        source = self._require_source()
        self._wav_file = self.config.temp_dir / f"{source.stem}_BORRAR.wav"
        if self._wav_file.exists() and not self.config.force:
            self._log(f"Se reutiliza el audio: {self._wav_file.name}")
            self._files.append(self._wav_file)
            return True
        ffmpeg, _ = ensure_ffmpeg(on_download=self._log)
        self.process.run([
            str(ffmpeg), "-hide_banner", "-y", "-i", source,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", self._wav_file,
        ], on_line=lambda line: self._log(line))
        self._files.append(self._wav_file)
        return False

    def _transcribe(self) -> bool:
        wav = self._require_wav()
        base = self.config.temp_dir / wav.stem
        srt, json_file = base.with_suffix(".srt"), base.with_suffix(".json")
        if srt.exists() and json_file.exists() and not self.config.force:
            self._log("Se reutilizan la transcripción SRT y JSON existentes.")
            self._files.extend([srt, json_file])
            return True
        whisper_cli = self.paths.find_whisper_cli()
        if not whisper_cli:
            raise RuntimeError(
                "Falta whisper-cli. Compilá whisper.cpp con CMake; "
                "la app puede seguir usándose para descargas."
            )
        if not self.config.whisper_model.is_file():
            raise RuntimeError("El modelo Whisper seleccionado no existe. Descargalo desde el selector de modelos.")
        self.process.run([
            whisper_cli, "-m", self.config.whisper_model, "-f", wav,
            "-l", self.config.language, "-osrt", "-oj", "-ml", "60", "-sow", "-of", base,
        ], on_line=lambda line: self._log(line))
        self._files.extend([srt, json_file])
        return False

    def _diarize(self) -> bool:
        wav = self._require_wav()
        output = self.config.temp_dir / f"{wav.stem}.txt"
        if output.exists() and not self.config.force:
            self._log("Se reutiliza la diarización existente.")
            self._files.append(output)
            return True
        token = load_token(self.paths.env_file)
        if not token:
            raise RuntimeError("Configurá el token de Hugging Face en Ajustes antes de diarizar.")
        env = os.environ.copy()
        env["PYANNOTE_KEY"] = token  # no se expone en la línea de comandos ni en ps
        self.process.run([
            self.paths.python, self.paths.pyannote_script, "-a", wav,
        ], cwd=self.config.temp_dir, env=env, on_line=lambda line: self._log(line))
        self._files.append(output)
        return False

    def _merge(self) -> bool:
        wav = self._require_wav()
        json_file = self.config.temp_dir / f"{wav.stem}.json"
        diarization = self.config.temp_dir / f"{wav.stem}.txt"
        output = self.config.output_dir / f"{wav.stem}_diarizado.txt"
        if output.exists() and not self.config.force:
            self._log("Se reutiliza el guion diarizado existente.")
            self._files.append(output)
            return True
        if not json_file.exists() or not diarization.exists():
            raise RuntimeError("Faltan el JSON de Whisper o el TXT de pyannote. Ejecutá las etapas previas.")
        self.process.run([
            self.paths.python, self.paths.merge_script,
            "-j", json_file, "-d", diarization, "-o", output,
        ], on_line=lambda line: self._log(line))
        self._files.append(output)
        return False

    def _unique_files(self) -> list[Path]:
        return list(dict.fromkeys(path for path in self._files if path.exists()))
