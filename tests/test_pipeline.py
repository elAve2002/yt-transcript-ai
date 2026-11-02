from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.config import ProjectPaths
from app.core.pipeline import PipelineConfig, PipelineRunner, Stage, StageState


def make_runner(tmp_path: Path, enabled: set[Stage] | None = None) -> PipelineRunner:
    paths = ProjectPaths(tmp_path)
    config = PipelineConfig(
        output_dir=tmp_path / "salida",
        temp_dir=tmp_path / "temporales",
        enabled_stages=enabled if enabled is not None else set(Stage),
        whisper_model=tmp_path / "model.bin",
        local_file=tmp_path / "video.mp4",
    )
    return PipelineRunner(paths, config)


def test_pipeline_state_flow_with_mocks(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    for name, reused in (
        ("_download", False), ("_extract", False), ("_transcribe", True),
        ("_diarize", False), ("_merge", False),
    ):
        setattr(runner, name, Mock(return_value=reused))

    result = runner.run()

    assert not result.cancelled
    assert result.states[Stage.DOWNLOAD] == StageState.DONE
    assert result.states[Stage.EXTRACT] == StageState.DONE
    assert result.states[Stage.TRANSCRIBE] == StageState.SKIPPED
    assert result.states[Stage.MERGE] == StageState.DONE


def test_disabled_stages_are_skipped(tmp_path: Path) -> None:
    runner = make_runner(tmp_path, {Stage.EXTRACT})
    runner._extract = Mock(return_value=False)

    result = runner.run()

    assert result.states[Stage.DOWNLOAD] == StageState.SKIPPED
    assert result.states[Stage.EXTRACT] == StageState.DONE
    assert result.states[Stage.MERGE] == StageState.SKIPPED


def test_pipeline_cancellation_does_not_raise(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    runner.cancel()

    result = runner.run()

    assert result.cancelled
    assert result.states[Stage.DOWNLOAD] == StageState.CANCELLED


def test_stage_error_is_reported_with_human_stage_name(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    runner._download = Mock(side_effect=ValueError("fallo simulado"))

    with pytest.raises(RuntimeError, match="Descargar: fallo simulado"):
        runner.run()
    assert runner.states.values[Stage.DOWNLOAD] == StageState.ERROR
