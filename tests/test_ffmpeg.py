from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from app.core import ffmpeg as ffmpeg_module
from app.core.ffmpeg import ensure_ffmpeg


def test_uses_system_binaries_when_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    system = {"ffmpeg": "/opt/homebrew/bin/ffmpeg", "ffprobe": "/opt/homebrew/bin/ffprobe"}
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda name: system.get(name))

    ffmpeg, ffprobe = ensure_ffmpeg()

    assert ffmpeg == Path("/opt/homebrew/bin/ffmpeg")
    assert ffprobe == Path("/opt/homebrew/bin/ffprobe")


def test_falls_back_to_static_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda name: None)

    run = types.SimpleNamespace(
        get_or_fetch_platform_executables_else_raise=lambda **kwargs: (
            "/venv/static_ffmpeg/bin/darwin_arm64/ffmpeg",
            "/venv/static_ffmpeg/bin/darwin_arm64/ffprobe",
        )
    )
    fake_module = types.ModuleType("static_ffmpeg")
    fake_module.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_module)

    logged: list[str] = []
    ffmpeg, ffprobe = ensure_ffmpeg(on_download=logged.append)

    assert ffmpeg.name == "ffmpeg"
    assert ffprobe.name == "ffprobe"
    assert logged and "empaquetados" in logged[0]


def test_error_message_when_static_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda name: None)

    def raise_(**kwargs: object) -> tuple[str, str]:
        raise OSError("sin conexión")

    run = types.SimpleNamespace(get_or_fetch_platform_executables_else_raise=raise_)
    fake_module = types.ModuleType("static_ffmpeg")
    fake_module.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "static_ffmpeg", fake_module)

    with pytest.raises(RuntimeError, match="ffmpeg.org/download.html"):
        ensure_ffmpeg()


def test_error_message_when_static_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda name: None)
    # None en sys.modules hace que el import falle con ImportError.
    monkeypatch.setitem(sys.modules, "static_ffmpeg", None)

    with pytest.raises(RuntimeError, match="uv sync"):
        ensure_ffmpeg()
