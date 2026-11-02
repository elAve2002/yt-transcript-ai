from __future__ import annotations

from app.core.updates import UpdateChecker, UpdateStatus


def test_homebrew_bottle_revision_is_comparable() -> None:
    installed = UpdateChecker._homebrew_base_version("8.1.2_1")
    latest = UpdateChecker._homebrew_base_version("9.0.2_1")

    assert installed == "8.1.2"
    assert latest == "9.0.2"
    assert UpdateChecker._status_for(installed, latest) == UpdateStatus.ACTUALIZABLE
