"""Utilidades de presentación compartidas."""

from __future__ import annotations


def format_bytes(size: float | int | None) -> str:
    if size is None or size <= 0:
        return "Desconocido"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "Desconocida"
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def format_speed(bytes_per_second: float | None) -> str:
    if not bytes_per_second:
        return "—"
    return f"{format_bytes(bytes_per_second)}/s"


def format_eta(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
