from __future__ import annotations

from pathlib import Path

from app.core.whisper import list_installed_models, official_model


def test_list_installed_models(tmp_path: Path) -> None:
    (tmp_path / "ggml-base.bin").write_bytes(b"1234")
    (tmp_path / "ggml-large-v3-turbo.bin").write_bytes(b"12345678")
    (tmp_path / "otro.txt").write_text("no es modelo", encoding="utf-8")

    models = list_installed_models(tmp_path)

    assert [model.name for model in models] == ["ggml-large-v3-turbo.bin", "ggml-base.bin"]
    assert models[0].is_default
    assert models[0].size_bytes == 8
    assert models[1].display_name == "base"


def test_list_models_empty_directory(tmp_path: Path) -> None:
    assert list_installed_models(tmp_path) == []


def test_official_model_url() -> None:
    model = official_model("large-v3-turbo-q5_0")
    assert model.filename == "ggml-large-v3-turbo-q5_0.bin"
    assert model.url.endswith("/ggml-large-v3-turbo-q5_0.bin")
