from __future__ import annotations

import sys
import threading
import time

import pytest

from app.core import process as process_module
from app.core.process import (
    ProcessCancelled,
    SubprocessJob,
    format_command,
    process_group_kwargs,
    terminate_process_tree,
)


def test_failing_command_reports_last_output_lines() -> None:
    """Regresión: deque no soporta slicing; el error real no debe enmascararse."""
    job = SubprocessJob()
    lines: list[str] = []

    with pytest.raises(RuntimeError) as excinfo:
        job.run(
            [sys.executable, "-u", "-c",
             "print('salida uno'); print('salida dos'); print('salida tres'); raise SystemExit(3)"],
            on_line=lines.append,
        )

    message = str(excinfo.value)
    assert "código 3" in message
    assert "salida tres" in message
    assert lines[-1] == "salida tres"


def test_successful_command_returns_zero() -> None:
    job = SubprocessJob()

    result = job.run([sys.executable, "-u", "-c", "print('todo ok')"])

    assert result.returncode == 0


def test_cancelled_job_raises_before_start() -> None:
    job = SubprocessJob()
    job.cancel()

    with pytest.raises(ProcessCancelled):
        job.run([sys.executable, "-c", "print('no debería ejecutarse')"])


def test_cancelling_running_job_interrupts_and_raises() -> None:
    """Cancelar un proceso en ejecución debe terminar el árbol y lanzar ProcessCancelled."""
    job = SubprocessJob()

    def cancel_after_delay() -> None:
        time.sleep(0.5)
        job.cancel()

    canceller = threading.Thread(target=cancel_after_delay)
    canceller.start()

    try:
        with pytest.raises(ProcessCancelled):
            job.run([sys.executable, "-u", "-c", "import time; time.sleep(30)"])
    finally:
        canceller.join(timeout=5)

    assert not canceller.is_alive()


def test_windows_process_options_and_command_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_module.os, "name", "nt")

    assert "creationflags" in process_group_kwargs()
    assert format_command(["python", "-c", "print('hola mundo')"]) == 'python -c "print(\'hola mundo\')"'


def test_posix_process_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_module.os, "name", "posix")

    assert process_group_kwargs() == {"start_new_session": True}


def test_windows_cancellation_uses_taskkill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_module.os, "name", "nt")
    commands = []

    class FakeProcess:
        pid = 123

        def poll(self):
            return None

    monkeypatch.setattr(
        process_module.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command),
    )

    terminate_process_tree(FakeProcess())

    assert commands == [["taskkill", "/PID", "123", "/T", "/F"]]
