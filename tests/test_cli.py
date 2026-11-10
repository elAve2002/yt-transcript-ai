from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import cli
from app.config import ProjectPaths
from app.core.updates import UpdateComponent, UpdateStatus


def test_pipeline_uses_shared_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured = {}

    class FakeRunner:
        def __init__(self, paths, config, **callbacks):
            captured["paths"] = paths
            captured["config"] = config

        def run(self):
            return SimpleNamespace(cancelled=False, files=[])

    monkeypatch.setattr(cli, "project_paths", lambda: ProjectPaths(tmp_path))
    monkeypatch.setattr(cli, "PipelineRunner", FakeRunner)

    result = cli.main(["pipeline", "https://youtu.be/abc", str(tmp_path / "salida"), "--calidad", "720"])

    assert result == 0
    assert captured["config"].download_options.video_height == 720
    assert captured["config"].enabled_stages
    assert captured["config"].source_url == "https://youtu.be/abc"


def test_update_check_only_does_not_execute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    component = UpdateComponent("demo", "demo", "python", "1.0", "1.0", UpdateStatus.AL_DIA, [])

    class FakeChecker:
        def __init__(self, root):
            pass

        def check_all(self, force=False):
            return [component]

    monkeypatch.setattr(cli, "project_paths", lambda: ProjectPaths(tmp_path))
    monkeypatch.setattr(cli, "UpdateChecker", FakeChecker)
    monkeypatch.setattr(
        cli.UpdateExecutor,
        "execute",
        lambda *args, **kwargs: pytest.fail("No debería ejecutar actualizaciones"),
    )

    assert cli.main(["actualizar", "--solo-comprobar"]) == 0


def test_model_download_uses_core(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "whisper" / "models" / "ggml-tiny.bin"
    monkeypatch.setattr(cli, "project_paths", lambda: ProjectPaths(tmp_path))
    monkeypatch.setattr(cli, "download_model", lambda model, directory, progress: destination)

    assert cli.main(["modelo", "tiny"]) == 0
