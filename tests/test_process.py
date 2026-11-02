from __future__ import annotations

import sys

import pytest

from app.core.process import ProcessCancelled, SubprocessJob


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
