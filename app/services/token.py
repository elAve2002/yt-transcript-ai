"""Gestión y validación del token de Hugging Face."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_ENV_KEY = "PYANNOTE_KEY"
_WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
_MODEL_URL = "https://huggingface.co/api/models/pyannote/speaker-diarization-community-1"
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?PYANNOTE_KEY\s*=")


def load_token(env_path: Path, environ: Mapping[str, str] | None = None) -> str:
    """Carga el token, dando prioridad a la variable de entorno."""
    source = os.environ if environ is None else environ
    override = source.get(_ENV_KEY)
    if override:
        return override

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""

    for line in lines:
        if not _ENV_LINE.match(line):
            continue
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return ""


def save_token(env_path: Path, token: str) -> None:
    """Guarda el token sin alterar el resto del archivo, de forma atómica."""
    try:
        original = env_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        original = ""

    lines = original.splitlines(keepends=True)
    replacement = f"{_ENV_KEY}={token}"
    replaced = False
    output: list[str] = []

    for line in lines:
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        if _ENV_LINE.match(body):
            output.append(replacement + ending)
            replaced = True
        else:
            output.append(line)

    if not replaced:
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += "\n"
        output.append(replacement + "\n")

    fd, temporary_name = tempfile.mkstemp(
        dir=env_path.parent, prefix=f".{env_path.name}.", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        if os.name != "nt":
            os.chmod(temporary_path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write("".join(output))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, env_path)
        if os.name != "nt":
            os.chmod(env_path, 0o600)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def mask_token(token: str) -> str:
    """Devuelve una representación que nunca expone el token completo."""
    if len(token) <= 8:
        return "••••"
    return f"{token[:4]}…{token[-4:]}"


class TokenStatus(Enum):
    VALID = auto()
    NO_ACCESS = auto()
    INVALID = auto()
    ERROR = auto()


@dataclass
class TokenValidation:
    status: TokenStatus
    message: str
    user: str | None = None


def _request(token: str, url: str, timeout: float):
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    return urlopen(request, timeout=timeout)


def validate_token(token: str, timeout: float = 15) -> TokenValidation:
    """Valida el token y su acceso al modelo sin propagar errores de red."""
    if not token:
        return TokenValidation(TokenStatus.INVALID, "No se proporcionó un token.")

    try:
        with _request(token, _WHOAMI_URL, timeout) as response:
            status = response.getcode()
            if status != 200:
                return TokenValidation(
                    TokenStatus.ERROR, "No se pudo validar el token con Hugging Face."
                )
            data = json.load(response)
        user = data.get("name") if isinstance(data, dict) else None
    except HTTPError as error:
        if error.code in (401, 403):
            return TokenValidation(
                TokenStatus.INVALID, "El token es inválido o no está autorizado."
            )
        return TokenValidation(
            TokenStatus.ERROR, "Hugging Face no pudo validar el token."
        )
    except (URLError, TimeoutError, OSError):
        return TokenValidation(
            TokenStatus.ERROR, "Error de red al validar el token con Hugging Face."
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return TokenValidation(
            TokenStatus.ERROR, "Hugging Face devolvió una respuesta inválida."
        )
    except Exception:
        return TokenValidation(
            TokenStatus.ERROR, "No se pudo validar el token con Hugging Face."
        )

    try:
        with _request(token, _MODEL_URL, timeout) as response:
            status = response.getcode()
        if status == 200:
            return TokenValidation(
                TokenStatus.VALID,
                "Token válido con acceso al modelo de diarización.",
                user=user,
            )
        if status in (401, 403, 404):
            return TokenValidation(
                TokenStatus.NO_ACCESS,
                "El token no tiene acceso al modelo de diarización.",
                user=user,
            )
        return TokenValidation(
            TokenStatus.ERROR,
            "No se pudo comprobar el acceso al modelo de diarización.",
            user=user,
        )
    except HTTPError as error:
        if error.code in (401, 403, 404):
            return TokenValidation(
                TokenStatus.NO_ACCESS,
                "El token no tiene acceso al modelo de diarización.",
                user=user,
            )
        return TokenValidation(
            TokenStatus.ERROR,
            "Hugging Face no pudo comprobar el acceso al modelo.",
            user=user,
        )
    except (URLError, TimeoutError, OSError):
        return TokenValidation(
            TokenStatus.ERROR,
            "Error de red al comprobar el acceso al modelo.",
            user=user,
        )
    except Exception:
        return TokenValidation(
            TokenStatus.ERROR,
            "No se pudo comprobar el acceso al modelo de diarización.",
            user=user,
        )
