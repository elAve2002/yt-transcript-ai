from __future__ import annotations

from app.config import project_paths
from app.core.download import (
    _load_legacy_downloader, friendly_yt_dlp_error, quality_options, validate_youtube_url,
)
from yt_dlp.utils import DownloadError


def test_yt_dlp_errors_are_human_and_actionable() -> None:
    forbidden = friendly_yt_dlp_error(DownloadError("HTTP Error 403: Forbidden"))
    assert "403" in forbidden
    assert "Actualizá yt-dlp" in forbidden

    limited = friendly_yt_dlp_error(DownloadError("HTTP Error 429: Too Many Requests"))
    assert "429" in limited and "minutos" in limited

    unavailable = friendly_yt_dlp_error(
        DownloadError("ERROR: [youtube] abc: This video is unavailable"), action="analizar"
    )
    assert unavailable.startswith("No se pudo analizar el video.")
    assert "no está disponible" in unavailable

    generic = friendly_yt_dlp_error(DownloadError("boom"))
    assert generic == "No se pudo descargar el video. boom"


def test_youtube_url_validation() -> None:
    assert validate_youtube_url("https://www.youtube.com/watch?v=abc")
    assert validate_youtube_url("https://youtu.be/abc")
    assert validate_youtube_url("youtube.com/watch?v=abc")
    assert not validate_youtube_url("https://example.com/watch?v=abc")
    assert not validate_youtube_url("")


def test_quality_selection_reuses_legacy_rule() -> None:
    legacy = _load_legacy_downloader(project_paths())
    assert legacy.get_closest_quality({144, 360, 720, 1080, 2160}, 1080) == 1080
    assert legacy.get_closest_quality({144, 360, 720, 2160}, 1080) == 720
    assert legacy.get_closest_quality({1440, 2160}, 1080) == 1440


def test_quality_options_use_real_formats_and_estimate_size() -> None:
    info = {
        "formats": [
            {"height": 360, "vcodec": "avc1", "acodec": "none", "filesize": 1000},
            {"height": 720, "vcodec": "avc1", "acodec": "none", "filesize_approx": 3000},
            {"height": None, "vcodec": "none", "acodec": "mp4a", "filesize": 500},
        ]
    }
    options = quality_options(info)
    assert [option.height for option in options] == [360, 720]
    assert options[0].estimated_bytes == 1500
    assert options[1].estimated_bytes == 3500
