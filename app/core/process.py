"""Ejecución multiplataforma de procesos con log en vivo y cancelación real."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class ProcessCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcessResult:
    command: tuple[str, ...]
    returncode: int


def process_group_kwargs() -> dict[str, Any]:
    """Opciones de Popen para aislar el proceso y poder cancelarlo por SO."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def format_command(command: Sequence[str]) -> str:
    """Representa un comando con el quoting nativo, solo para mostrarlo."""
    args = list(command)
    return subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Termina el proceso y sus hijos sin propagar errores si ya finalizó."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.terminate()
        except OSError:
            pass
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        try:
            process.terminate()
        except OSError:
            pass


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
        if process:
            terminate_process_tree(process)

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
            on_line(f"$ {format_command(args)}")
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
            **process_group_kwargs(),
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
