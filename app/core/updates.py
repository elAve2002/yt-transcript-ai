"""Comprobación y ejecución de actualizaciones, sin dependencias de Qt."""

from __future__ import annotations

import importlib.metadata
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from packaging.version import Version

from app.core.process import format_command, process_group_kwargs, terminate_process_tree


class UpdateStatus(str, Enum):
    AL_DIA = "AL_DIA"
    ACTUALIZABLE = "ACTUALIZABLE"
    NO_INSTALADO = "NO_INSTALADO"
    ERROR = "ERROR"
    DISTINTA = "DISTINTA"


@dataclass
class UpdateComponent:
    key: str
    name: str
    kind: str
    installed: str | None
    latest: str | None
    status: UpdateStatus
    command: list[str]
    detail: str | None = None
    tarball_url: str | None = None


class UpdateChecker:
    """Consulta versiones en paralelo y conserva el último resultado en cache."""

    _PYTHON_PACKAGES = (
        "yt-dlp",
        "pyannote-audio",
        "torch",
        "torchaudio",
        "torchvision",
        "torchcodec",
        "static-ffmpeg",
    )
    # torchcodec no declara torch como dependencia, pero van acoplados binariamente:
    # actualizar uno sin el otro rompe pyannote en runtime. Se mueven siempre juntos.
    _TORCH_FAMILY = ("torch", "torchaudio", "torchvision", "torchcodec")
    _HOMEBREW_FORMULAS = ("ffmpeg", "cmake", "uv")
    _TIMEOUT = 20
    _ERROR_DETAIL = "No se pudo comprobar"

    def __init__(self, root: Path, cache_ttl_seconds: int = 600) -> None:
        self.root = Path(root)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: list[UpdateComponent] | None = None
        self._cache_time = 0.0
        self._cache_lock = threading.Lock()

    def check_all(self, force: bool = False) -> list[UpdateComponent]:
        with self._cache_lock:
            if (
                not force
                and self._cache is not None
                and time.monotonic() - self._cache_time < self.cache_ttl_seconds
            ):
                return self._copy_components(self._cache)

        jobs: list[tuple[tuple[str, str, str, list[str]], Callable[[], UpdateComponent]]] = []
        for package in self._PYTHON_PACKAGES:
            metadata = (
                package,
                package,
                "python",
                self._upgrade_command(package),
            )
            jobs.append((metadata, lambda package=package: self._check_python(package)))
        if sys.platform == "darwin":
            for formula in self._HOMEBREW_FORMULAS:
                metadata = (formula, formula, "homebrew", ["brew", "upgrade", formula])
                jobs.append((metadata, lambda formula=formula: self._check_homebrew(formula)))
        whisper_metadata = (
            "whisper.cpp",
            "whisper.cpp",
            "whisper",
            ["curl", "-fL", self._WHISPER_API_URL],
        )
        jobs.append((whisper_metadata, self._check_whisper))

        components: list[UpdateComponent] = []
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            futures = [executor.submit(check) for _, check in jobs]
            for (metadata, _), future in zip(jobs, futures, strict=True):
                try:
                    components.append(future.result())
                except Exception:
                    key, name, kind, command = metadata
                    components.append(
                        UpdateComponent(
                            key=key,
                            name=name,
                            kind=kind,
                            installed=None,
                            latest=None,
                            status=UpdateStatus.ERROR,
                            command=command,
                            detail=self._ERROR_DETAIL,
                        )
                    )

        with self._cache_lock:
            self._cache = self._copy_components(components)
            self._cache_time = time.monotonic()
        return components

    _WHISPER_API_URL = "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest"

    @staticmethod
    def _copy_components(components: list[UpdateComponent]) -> list[UpdateComponent]:
        return [replace(component, command=list(component.command)) for component in components]

    @staticmethod
    def _status_for(installed: str | None, latest: str) -> UpdateStatus:
        if installed is None:
            return UpdateStatus.NO_INSTALADO
        installed_version = Version(installed)
        latest_version = Version(latest)
        if installed_version < latest_version:
            return UpdateStatus.ACTUALIZABLE
        if installed_version == latest_version:
            return UpdateStatus.AL_DIA
        return UpdateStatus.DISTINTA

    @staticmethod
    def _homebrew_base_version(value: str | None) -> str | None:
        """Quita la revisión de botella (_1) solo para comparar versiones."""
        return value.split("_", 1)[0] if value else value

    @classmethod
    def _get_json(cls, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "yt-transcript-ai-updater",
            },
        )
        with urllib.request.urlopen(request, timeout=cls._TIMEOUT) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError("Respuesta JSON inesperada")
        return data

    def _upgrade_command(self, package: str) -> list[str]:
        """La familia torch se actualiza como unidad por su acoplamiento binario."""
        if package in self._TORCH_FAMILY:
            command = ["uv", "sync"]
            for member in self._TORCH_FAMILY:
                command += ["--upgrade-package", member]
            return command
        return ["uv", "sync", "--upgrade-package", package]

    def _check_python(self, package: str) -> UpdateComponent:
        command = self._upgrade_command(package)
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        except Exception:
            return self._error(package, package, "python", command)

        try:
            data = self._get_json(f"https://pypi.org/pypi/{package}/json")
            latest = data["info"]["version"]
            if not isinstance(latest, str) or not latest:
                raise ValueError("Versión de PyPI ausente")
            status = self._status_for(installed, latest)
        except Exception:
            return self._error(package, package, "python", command, installed=installed)

        return UpdateComponent(package, package, "python", installed, latest, status, command)

    def _check_homebrew(self, formula: str) -> UpdateComponent:
        command = ["brew", "upgrade", formula]
        try:
            installed_result = subprocess.run(
                ["brew", "list", "--versions", formula],
                capture_output=True,
                text=True,
                timeout=self._TIMEOUT,
            )
        except FileNotFoundError:
            return UpdateComponent(
                formula,
                formula,
                "homebrew",
                None,
                None,
                UpdateStatus.NO_INSTALADO,
                command,
                "Homebrew no está instalado",
            )
        except Exception:
            return self._error(formula, formula, "homebrew", command)

        installed = None
        if installed_result.returncode == 0:
            fields = (installed_result.stdout or "").strip().split()
            if len(fields) >= 2:
                installed = fields[-1]

        try:
            info_result = subprocess.run(
                ["brew", "info", "--json=v2", formula],
                capture_output=True,
                text=True,
                timeout=self._TIMEOUT,
            )
            if info_result.returncode != 0:
                raise ValueError("No se encontró la fórmula")
            data = json.loads(info_result.stdout or "{}")
            latest = data["formulae"][0]["versions"]["stable"]
            if not isinstance(latest, str) or not latest:
                raise ValueError("Versión de Homebrew ausente")
            status = self._status_for(
                self._homebrew_base_version(installed),
                self._homebrew_base_version(latest),
            )
        except FileNotFoundError:
            return UpdateComponent(
                formula,
                formula,
                "homebrew",
                installed,
                None,
                UpdateStatus.NO_INSTALADO,
                command,
                "Homebrew no está instalado",
            )
        except Exception:
            return self._error(formula, formula, "homebrew", command, installed=installed)

        return UpdateComponent(formula, formula, "homebrew", installed, latest, status, command)

    def _installed_whisper_version(self) -> str | None:
        cmake_file = self.root / "whisper" / "CMakeLists.txt"
        try:
            contents = cmake_file.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return None
        match = re.search(
            r'\bproject\s*\(\s*["\']?whisper\.cpp["\']?\s+VERSION\s+([^\s\)]+)',
            contents,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip("\"'") if match else None

    def _check_whisper(self) -> UpdateComponent:
        installed = self._installed_whisper_version()
        command = ["curl", "-fL", self._WHISPER_API_URL]
        try:
            data = self._get_json(self._WHISPER_API_URL)
            tag = data["tag_name"]
            tarball_url = data["tarball_url"]
            if not isinstance(tag, str) or not tag or not isinstance(tarball_url, str) or not tarball_url:
                raise ValueError("Release de GitHub incompleta")
            latest = tag[1:] if tag.startswith(("v", "V")) else tag
            status = self._status_for(installed, latest)
        except Exception:
            return self._error("whisper.cpp", "whisper.cpp", "whisper", command, installed=installed)

        return UpdateComponent(
            key="whisper.cpp",
            name="whisper.cpp",
            kind="whisper",
            installed=installed,
            latest=latest,
            status=status,
            command=["curl", "-fL", tarball_url],
            tarball_url=tarball_url,
        )

    def _error(
        self,
        key: str,
        name: str,
        kind: str,
        command: list[str],
        *,
        installed: str | None = None,
    ) -> UpdateComponent:
        return UpdateComponent(
            key=key,
            name=name,
            kind=kind,
            installed=installed,
            latest=None,
            status=UpdateStatus.ERROR,
            command=command,
            detail=self._ERROR_DETAIL,
        )


class UpdateExecutor:
    """Ejecuta actualizaciones y transmite su salida línea por línea."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def execute(
        self,
        components: list[UpdateComponent],
        on_line: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        for component in components:
            if cancel_event.is_set():
                raise RuntimeError("Actualización cancelada.")
            if component.kind in {"python", "homebrew", "brew"}:
                if not component.command:
                    raise RuntimeError(f"No hay un comando para actualizar {component.name}.")
                self._run_command(component.command, on_line, cancel_event)
            elif component.kind in {"whisper", "whisper.cpp"}:
                self._update_whisper(component, on_line, cancel_event)
            else:
                raise RuntimeError(f"Tipo de componente desconocido: {component.kind}.")

    def _run_command(
        self,
        command: list[str],
        on_line: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        on_line(f"$ {format_command(command)}")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=self.root,
                **process_group_kwargs(),
            )
        except OSError as exc:
            raise RuntimeError(f"No se pudo ejecutar {command[0]}: {exc}") from exc

        output: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    output.put(line)
            finally:
                output.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        recent_lines: deque[str] = deque(maxlen=5)
        try:
            while True:
                if cancel_event.is_set():
                    self._terminate(process)
                    raise RuntimeError("Actualización cancelada.")
                try:
                    line = output.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                clean = line.rstrip()
                recent_lines.append(clean)
                on_line(clean)

            returncode = process.wait()
            reader.join()
        except Exception:
            if process.poll() is None:
                self._terminate(process)
            raise

        if cancel_event.is_set():
            raise RuntimeError("Actualización cancelada.")
        if returncode != 0:
            details = "\n".join(recent_lines) or "Sin salida del proceso."
            raise RuntimeError(f"El comando {command[0]} falló (código {returncode}).\n{details}")

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        terminate_process_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def _update_whisper(
        self,
        component: UpdateComponent,
        on_line: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        if not component.tarball_url:
            raise RuntimeError("No se encontró la URL de descarga de whisper.cpp.")

        temporary_root = self.root / "temporales"
        temporary_root.mkdir(parents=True, exist_ok=True)
        whisper_root = self.root / "whisper"
        try:
            with tempfile.TemporaryDirectory(prefix="whisper-update.", dir=temporary_root) as temporary:
                temporary_path = Path(temporary)
                tarball = temporary_path / "whisper.tar.gz"
                self._download(component.tarball_url, tarball, on_line, cancel_event)

                extracted = temporary_path / "source"
                extracted.mkdir()
                on_line("Extrayendo el código fuente de whisper.cpp...")
                with tarfile.open(tarball, "r:gz") as archive:
                    archive.extractall(extracted, filter="data")

                source = self._source_directory(extracted)
                self._copy_whisper_source(source, whisper_root, on_line, cancel_event)
        except RuntimeError:
            raise
        except (OSError, tarfile.TarError) as exc:
            raise RuntimeError(f"No se pudo actualizar whisper.cpp: {exc}") from exc

        build = whisper_root / "build"
        self._run_command(
            ["cmake", "-S", str(whisper_root), "-B", str(build)],
            on_line,
            cancel_event,
        )
        self._run_command(
            ["cmake", "--build", str(build), "--config", "Release", "-j"],
            on_line,
            cancel_event,
        )

    def _download(
        self,
        url: str,
        destination: Path,
        on_line: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        on_line(f"Descargando whisper.cpp desde {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "yt-transcript-ai-updater"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response, destination.open("wb") as output:
                while True:
                    if cancel_event.is_set():
                        raise RuntimeError("Actualización cancelada.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"No se pudo descargar whisper.cpp: {exc}") from exc
        on_line("Descarga de whisper.cpp completada.")

    @staticmethod
    def _source_directory(extracted: Path) -> Path:
        entries = list(extracted.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            return entries[0]
        if any(path.is_file() for path in entries):
            return extracted
        raise RuntimeError("El archivo descargado no contiene el código de whisper.cpp.")

    def _copy_whisper_source(
        self,
        source: Path,
        destination: Path,
        on_line: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> None:
        if cancel_event.is_set():
            raise RuntimeError("Actualización cancelada.")
        destination.mkdir(parents=True, exist_ok=True)
        rsync = shutil.which("rsync")
        if rsync:
            self._run_command(
                [
                    rsync,
                    "-a",
                    "--exclude=models/",
                    "--exclude=build/",
                    "--exclude=.git/",
                    f"{source}{os.sep}",
                    f"{destination}{os.sep}",
                ],
                on_line,
                cancel_event,
            )
            return

        on_line("Copiando el código fuente (se conservan models/, build/ y .git/)...")
        preserved = {"models", "build", ".git"}
        for item in source.iterdir():
            if cancel_event.is_set():
                raise RuntimeError("Actualización cancelada.")
            if item.name in preserved:
                continue
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
