from __future__ import annotations

from pathlib import Path

import pytest

from app import config as config_module
from app.config import ProjectPaths


def test_python_path_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "win32")

    python = ProjectPaths(tmp_path).python

    assert python.parts[-3:] == (".venv", "Scripts", "python.exe")


def test_python_path_on_posix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "darwin")

    python = ProjectPaths(tmp_path).python

    assert python.parts[-3:] == (".venv", "bin", "python")


def test_finds_release_whisper_executable_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "win32")
    paths = ProjectPaths(tmp_path)
    release = paths.whisper_cli.parent / "Release" / paths.whisper_cli.name
    release.parent.mkdir(parents=True)
    release.touch()
    monkeypatch.setattr(config_module.shutil, "which", lambda name: None)

    assert paths.find_whisper_cli() == release
    assert paths.whisper_cli.name == "whisper-cli.exe"


def test_missing_whisper_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_module.shutil, "which", lambda name: None)

    assert ProjectPaths(tmp_path).find_whisper_cli() is None
