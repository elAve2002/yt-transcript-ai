"""Ejecución de procesos externos con log en vivo y cancelación real."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


class ProcessCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int


class SubprocessJob:
    """Ejecuta un comando en un worker; cancel() es seguro desde el hilo de UI."""

    def __init__(self, cancel_event: threading.Event | None = None) -> None:
        self.cancel_event = cancel_event or threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            process = self._process
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()

    def run(
        self,
        command: Sequence[str | Path],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        if self.cancel_event.is_set():
            raise ProcessCancelled("Operación cancelada.")
        args = tuple(str(part) for part in command)
        if on_line:
            on_line(f"$ {shlex.join(args)}")
        process = subprocess.Popen(
            args,
            cwd=str(cwd) if cwd else None,
            env=dict(env) if env is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        with self._lock:
            self._process = process
        tail: deque[str] = deque(maxlen=12)
        try:
            assert process.stdout is not None
            for line in process.stdout:
                clean = line.rstrip()
                tail.append(clean)
                if on_line:
                    on_line(clean)
            returncode = process.wait()
        finally:
            with self._lock:
                self._process = None
        if self.cancel_event.is_set():
            raise ProcessCancelled("Operación cancelada por el usuario.")
        if returncode:
            details = "\n".join(list(tail)[-4:]) or "Sin salida del proceso."
            raise RuntimeError(f"El comando terminó con código {returncode}. {details}")
        return ProcessResult(args, returncode)
