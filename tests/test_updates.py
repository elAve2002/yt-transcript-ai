from __future__ import annotations

import io
import json
import subprocess
import tarfile
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from app.core import updates
from app.core.updates import UpdateChecker, UpdateComponent, UpdateExecutor, UpdateStatus


class FakeResponse(io.BytesIO):
    def __init__(self, data: dict[str, object] | bytes) -> None:
        payload = json.dumps(data).encode() if isinstance(data, dict) else data
        super().__init__(payload)


def component(
    key: str = "demo",
    kind: str = "python",
    command: list[str] | None = None,
) -> UpdateComponent:
    return UpdateComponent(
        key=key,
        name=key,
        kind=kind,
        installed="1.0",
        latest="2.0",
        status=UpdateStatus.ACTUALIZABLE,
        command=command or ["uv", "sync", "--upgrade-package", key],
        tarball_url="https://example.test/whisper.tar.gz" if kind == "whisper" else None,
    )


@pytest.mark.parametrize(
    ("installed", "latest", "expected"),
    [
        ("2.0", "2.0", UpdateStatus.AL_DIA),
        ("1.9", "2.0", UpdateStatus.ACTUALIZABLE),
        ("2.1", "2.0", UpdateStatus.DISTINTA),
        (None, "2.0", UpdateStatus.NO_INSTALADO),
    ],
)
def test_python_version_status_and_command(
    monkeypatch: pytest.MonkeyPatch,
    installed: str | None,
    latest: str,
    expected: UpdateStatus,
) -> None:
    def fake_version(package: str) -> str:
        assert package == "yt-dlp"
        if installed is None:
            raise updates.importlib.metadata.PackageNotFoundError(package)
        return installed

    monkeypatch.setattr(updates.importlib.metadata, "version", fake_version)
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"info": {"version": latest}}),
    )

    result = UpdateChecker(Path("."))._check_python("yt-dlp")

    assert result.status is expected
    assert result.installed == installed
    assert result.latest == latest
    assert result.command == ["uv", "sync", "--upgrade-package", "yt-dlp"]


def test_torch_family_is_upgraded_together(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regresión: actualizar torch aislado rompe el acoplamiento con torchcodec."""
    monkeypatch.setattr(updates.importlib.metadata, "version", lambda package: "2.13.0")
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"info": {"version": "2.15.0"}}),
    )

    result = UpdateChecker(Path("."))._check_python("torch")

    assert result.status is UpdateStatus.ACTUALIZABLE
    assert result.command == [
        "uv", "sync",
        "--upgrade-package", "torch",
        "--upgrade-package", "torchaudio",
        "--upgrade-package", "torchvision",
        "--upgrade-package", "torchcodec",
    ]

    # Un paquete fuera de la familia conserva el comando individual.
    monkeypatch.setattr(updates.importlib.metadata, "version", lambda package: "2026.7.4")
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"info": {"version": "2026.10.26"}}),
    )
    assert UpdateChecker(Path("."))._upgrade_command("yt-dlp") == [
        "uv", "sync", "--upgrade-package", "yt-dlp",
    ]


def test_python_network_error_is_a_component(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates.importlib.metadata, "version", lambda package: "1.0")

    def fail(request: object, timeout: int) -> None:
        assert timeout <= 20
        raise URLError("sin red")

    monkeypatch.setattr(updates.urllib.request, "urlopen", fail)

    result = UpdateChecker(Path("."))._check_python("torch")

    assert result.status is UpdateStatus.ERROR
    assert result.installed == "1.0"
    assert result.detail == "No se pudo comprobar"


def test_homebrew_response_and_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        assert kwargs["timeout"] <= 20
        assert not kwargs.get("shell", False)
        if command[1] == "list":
            return SimpleNamespace(returncode=0, stdout="ffmpeg 6.1 7.0\n")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"formulae": [{"versions": {"stable": "7.1"}}]}),
        )

    monkeypatch.setattr(updates.subprocess, "run", fake_run)

    result = UpdateChecker(Path("."))._check_homebrew("ffmpeg")

    assert result.status is UpdateStatus.ACTUALIZABLE
    assert result.installed == "7.0"
    assert result.latest == "7.1"
    assert result.command == ["brew", "upgrade", "ffmpeg"]
    assert calls == [
        ["brew", "list", "--versions", "ffmpeg"],
        ["brew", "info", "--json=v2", "ffmpeg"],
    ]


def test_homebrew_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[1] == "list":
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"formulae": [{"versions": {"stable": "3.31"}}]}),
        )

    monkeypatch.setattr(updates.subprocess, "run", fake_run)

    result = UpdateChecker(Path("."))._check_homebrew("cmake")

    assert result.status is UpdateStatus.NO_INSTALADO
    assert result.installed is None
    assert result.latest == "3.31"


def test_missing_homebrew_is_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(command: list[str], **kwargs: object) -> None:
        raise FileNotFoundError("brew")

    monkeypatch.setattr(updates.subprocess, "run", missing)

    result = UpdateChecker(Path("."))._check_homebrew("uv")

    assert result.status is UpdateStatus.NO_INSTALADO
    assert result.detail == "Homebrew no está instalado"


def test_whisper_cmake_and_github_parsing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    whisper = tmp_path / "whisper"
    whisper.mkdir()
    (whisper / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.20)\nproject("whisper.cpp" VERSION 1.7.6)\n',
        encoding="utf-8",
    )
    url = "https://api.github.test/whisper.tar.gz"
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"tag_name": "v1.8.0", "tarball_url": url}),
    )

    result = UpdateChecker(tmp_path)._check_whisper()

    assert result.status is UpdateStatus.ACTUALIZABLE
    assert result.installed == "1.7.6"
    assert result.latest == "1.8.0"
    assert result.tarball_url == url
    assert result.command == ["curl", "-fL", url]


def test_check_all_uses_cache_and_force(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checker = UpdateChecker(tmp_path)
    calls = 0
    calls_lock = threading.Lock()

    def fake_check(key: str, kind: str = "python") -> UpdateComponent:
        nonlocal calls
        with calls_lock:
            calls += 1
        return component(key, kind)

    monkeypatch.setattr(checker, "_check_python", lambda package: fake_check(package))
    monkeypatch.setattr(
        checker,
        "_check_homebrew",
        lambda formula: fake_check(formula, "homebrew"),
    )
    monkeypatch.setattr(checker, "_check_whisper", lambda: fake_check("whisper.cpp", "whisper"))

    expected = len(checker._PYTHON_PACKAGES) + 1
    if updates.sys.platform == "darwin":
        expected += len(checker._HOMEBREW_FORMULAS)

    first = checker.check_all()
    assert len(first) == expected
    assert calls == expected

    first[0].command.append("cambio-local")
    second = checker.check_all()
    assert calls == expected
    assert "cambio-local" not in second[0].command

    checker.check_all(force=True)
    assert calls == expected * 2


def test_check_all_omits_homebrew_outside_macos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(updates.sys, "platform", "win32")
    checker = UpdateChecker(tmp_path)
    monkeypatch.setattr(checker, "_check_python", lambda package: component(package))
    monkeypatch.setattr(
        checker,
        "_check_homebrew",
        lambda formula: pytest.fail("Homebrew no debe consultarse en Windows"),
    )
    monkeypatch.setattr(checker, "_check_whisper", lambda: component("whisper.cpp", "whisper"))

    components = checker.check_all()

    assert len(components) == len(checker._PYTHON_PACKAGES) + 1
    assert all(item.kind != "homebrew" for item in components)


def test_check_all_cache_expires(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    now = 100.0
    monkeypatch.setattr(updates.time, "monotonic", lambda: now)
    checker = UpdateChecker(tmp_path, cache_ttl_seconds=600)
    calls = 0

    def fake_check() -> UpdateComponent:
        nonlocal calls
        calls += 1
        return component()

    monkeypatch.setattr(checker, "_check_python", lambda package: fake_check())
    monkeypatch.setattr(checker, "_check_homebrew", lambda formula: fake_check())
    monkeypatch.setattr(checker, "_check_whisper", fake_check)

    expected = len(checker._PYTHON_PACKAGES) + 1
    if updates.sys.platform == "darwin":
        expected += len(checker._HOMEBREW_FORMULAS)

    checker.check_all()
    checker.check_all()
    assert calls == expected

    now += 601
    checker.check_all()
    assert calls == expected * 2


class FakeProcess:
    def __init__(self, output: str = "primera\nsegunda\n", returncode: int = 0) -> None:
        self.stdout = io.StringIO(output)
        self.returncode = returncode
        self.terminated = False

    def wait(self, timeout: int | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


def test_executor_streams_combined_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    process = FakeProcess()
    popen_kwargs: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        popen_kwargs.update(kwargs)
        return process

    monkeypatch.setattr(updates.subprocess, "Popen", fake_popen)
    lines: list[str] = []

    UpdateExecutor(tmp_path).execute([component()], lines.append, threading.Event())

    assert lines == ["$ uv sync --upgrade-package demo", "primera", "segunda"]
    assert popen_kwargs["cwd"] == tmp_path
    assert popen_kwargs["stderr"] == subprocess.STDOUT
    assert not popen_kwargs.get("shell", False)


def test_executor_whisper_fallback_preserves_local_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    whisper = tmp_path / "whisper"
    for directory in (whisper / "models", whisper / "build", whisper / ".git"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "conservar.txt").write_text("local", encoding="utf-8")
    (whisper / "CMakeLists.txt").write_text("viejo", encoding="utf-8")

    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, contents in (
            ("whisper.cpp-2.0/CMakeLists.txt", "nuevo"),
            ("whisper.cpp-2.0/models/no-copiar.txt", "remoto"),
        ):
            data = contents.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(archive_bytes.getvalue()),
    )
    monkeypatch.setattr(updates.shutil, "which", lambda executable: None)
    executor = UpdateExecutor(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        executor,
        "_run_command",
        lambda command, on_line, cancel_event: commands.append(command),
    )

    executor.execute([component("whisper.cpp", "whisper")], lambda line: None, threading.Event())

    assert (whisper / "CMakeLists.txt").read_text(encoding="utf-8") == "nuevo"
    for directory in ("models", "build", ".git"):
        assert (whisper / directory / "conservar.txt").read_text(encoding="utf-8") == "local"
    assert not (whisper / "models" / "no-copiar.txt").exists()
    assert commands == [
        ["cmake", "-S", str(whisper), "-B", str(whisper / "build")],
        ["cmake", "--build", str(whisper / "build"), "--config", "Release", "-j"],
    ]
