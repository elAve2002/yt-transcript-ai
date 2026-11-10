#!/bin/bash

# Wrapper de compatibilidad: la implementación vive en Python y también se usa en Windows.
DIR_RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR_RAIZ/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Error: no se encontró el intérprete del entorno virtual en $PYTHON" >&2
    echo "Creá el entorno con: uv venv --allow-existing && uv sync" >&2
    exit 1
fi

exec "$PYTHON" -m app.cli pipeline "$@"
