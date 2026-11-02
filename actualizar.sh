#!/bin/bash

# Comprueba actualizaciones de las dependencias del proyecto y pregunta antes de instalarlas.
# Uso:
#   ./actualizar.sh                  # comprueba y ofrece actualizar
#   ./actualizar.sh --solo-comprobar # solo informa; no instala nada

set -u

DIR_RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR_RAIZ/.venv/bin/python"
WHISPER_DIR="$DIR_RAIZ/whisper"
SOLO_COMPROBAR=0
DISPONIBLES=0
ACTUALIZADAS=0

if [ "${1:-}" = "--solo-comprobar" ] || [ "${1:-}" = "-n" ]; then
    SOLO_COMPROBAR=1
fi

if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 || true)"
fi

if [ -z "$PYTHON" ]; then
    echo "Error: no se encontró Python. Ejecutá primero 'uv sync'." >&2
    exit 1
fi

preguntar() {
    if [ "$SOLO_COMPROBAR" -eq 1 ]; then
        return 1
    fi

    local respuesta
    read -r -p "$1 [s/N]: " respuesta
    [[ "$respuesta" =~ ^[sS]$ ]]
}

comprobar_paquete_python() {
    local paquete="$1"
    local resultado instalada ultima estado

    if ! resultado=$("$PYTHON" - "$paquete" <<'PY'
import json
import sys
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from packaging.version import Version

paquete = sys.argv[1]
try:
    instalada = version(paquete)
except PackageNotFoundError:
    print(f"NO_INSTALADO||")
    raise SystemExit(0)

try:
    url = f"https://pypi.org/pypi/{paquete}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "yt-transcript-ai-updater"})
    with urllib.request.urlopen(request, timeout=20) as response:
        ultima = json.load(response)["info"]["version"]
except Exception as exc:
    print(f"No se pudo consultar PyPI para {paquete}: {exc}", file=sys.stderr)
    raise SystemExit(1)

if Version(ultima) > Version(instalada):
    estado = "ACTUALIZABLE"
elif Version(ultima) == Version(instalada):
    estado = "AL_DIA"
else:
    estado = "DISTINTA"

print(f"{estado}|{instalada}|{ultima}")
PY
    ); then
        return
    fi

    IFS='|' read -r estado instalada ultima <<< "$resultado"

    case "$estado" in
        NO_INSTALADO)
            echo "  $paquete: no está instalado en .venv; se omite."
            ;;
        AL_DIA)
            echo "  $paquete $instalada: actualizado."
            ;;
        DISTINTA)
            echo "  $paquete: versión local $instalada (PyPI: $ultima); no se cambia."
            ;;
        ACTUALIZABLE)
            DISPONIBLES=$((DISPONIBLES + 1))
            echo "  $paquete: $instalada → $ultima disponible."
            if preguntar "    ¿Actualizar $paquete?"; then
                if ! command -v uv >/dev/null 2>&1; then
                    echo "    Error: uv no está instalado." >&2
                elif (cd "$DIR_RAIZ" && uv sync $(parametros_actualizacion "$paquete")); then
                    ACTUALIZADAS=$((ACTUALIZADAS + 1))
                else
                    echo "    Error al actualizar $paquete." >&2
                fi
            fi
            ;;
    esac
}

comprobar_python() {
    printf '\n== Dependencias Python (PyPI/uv) ==\n'
    local paquete
    for paquete in yt-dlp pyannote-audio torch torchaudio torchvision torchcodec; do
        comprobar_paquete_python "$paquete"
    done
}

# torchcodec no declara torch como dependencia pero van acoplados binariamente:
# actualizar uno sin el otro rompe pyannote en runtime. La familia se mueve junta.
parametros_actualizacion() {
    case "$1" in
        torch|torchaudio|torchvision|torchcodec)
            echo "--upgrade-package torch --upgrade-package torchaudio --upgrade-package torchvision --upgrade-package torchcodec"
            ;;
        *)
            echo "--upgrade-package $1"
            ;;
    esac
}

comprobar_homebrew() {
    printf '\n== Herramientas del sistema (Homebrew) ==\n'

    if ! command -v brew >/dev/null 2>&1; then
        echo "  Homebrew no está instalado; se omite esta sección."
        return
    fi

    if [ "$SOLO_COMPROBAR" -eq 0 ]; then
        echo "  Actualizando la información de fórmulas de Homebrew..."
        if ! brew update >/dev/null; then
            echo "  Aviso: 'brew update' falló; se usará la información local disponible." >&2
        fi
    fi

    local formula instalada desactualizada
    for formula in ffmpeg cmake uv; do
        if ! instalada=$(brew list --versions "$formula" 2>/dev/null); then
            echo "  $formula: no está instalado mediante Homebrew; se omite."
            continue
        fi

        desactualizada=$(brew outdated --verbose "$formula" 2>/dev/null || true)
        if [ -z "$desactualizada" ]; then
            echo "  $instalada: actualizado."
            continue
        fi

        DISPONIBLES=$((DISPONIBLES + 1))
        echo "  Actualización disponible: $desactualizada"
        if preguntar "    ¿Actualizar $formula con Homebrew?"; then
            if brew upgrade "$formula"; then
                ACTUALIZADAS=$((ACTUALIZADAS + 1))
            else
                echo "    Error al actualizar $formula." >&2
            fi
        fi
    done
}

comparar_versiones() {
    "$PYTHON" - "$1" "$2" <<'PY'
import sys
from packaging.version import Version

local, remota = sys.argv[1:3]
if Version(remota) > Version(local):
    print("ACTUALIZABLE")
elif Version(remota) == Version(local):
    print("AL_DIA")
else:
    print("DISTINTA")
PY
}

actualizar_whisper() {
    local url="$1"
    local temporal fuente

    mkdir -p "$DIR_RAIZ/temporales"
    temporal=$(mktemp -d "$DIR_RAIZ/temporales/whisper-update.XXXXXX") || return 1

    echo "    Descargando el código fuente..."
    if ! curl -fL --retry 2 "$url" -o "$temporal/whisper.tar.gz"; then
        echo "    Error al descargar whisper.cpp." >&2
        rm -rf "$temporal"
        return 1
    fi

    if ! tar -xzf "$temporal/whisper.tar.gz" -C "$temporal"; then
        echo "    Error al descomprimir whisper.cpp." >&2
        rm -rf "$temporal"
        return 1
    fi

    fuente=$(find "$temporal" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    if [ -z "$fuente" ]; then
        echo "    No se encontró el código fuente descargado." >&2
        rm -rf "$temporal"
        return 1
    fi

    # No se usa --delete: se conservan modelos, builds y cualquier archivo adicional.
    if command -v rsync >/dev/null 2>&1; then
        rsync -a \
            --exclude='build/' \
            --exclude='models/' \
            --exclude='.git/' \
            "$fuente/" "$WHISPER_DIR/" || {
                echo "    Error al copiar el código fuente." >&2
                rm -rf "$temporal"
                return 1
            }
    else
        (cd "$fuente" && tar -cf - .) | (cd "$WHISPER_DIR" && tar -xf -) || {
            echo "    Error al copiar el código fuente." >&2
            rm -rf "$temporal"
            return 1
        }
    fi

    rm -rf "$temporal"

    echo "    Recompilando whisper-cli..."
    cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build" && \
        cmake --build "$WHISPER_DIR/build" --config Release -j
}

comprobar_whisper() {
    printf '\n== whisper.cpp ==\n'

    if [ ! -d "$WHISPER_DIR" ]; then
        echo "  No existe $WHISPER_DIR; se omite."
        return
    fi

    if ! command -v curl >/dev/null 2>&1; then
        echo "  curl no está disponible; no se puede consultar GitHub."
        return
    fi

    local version_local release tag version_remota url estado
    version_local=$(sed -n 's/.*project("whisper.cpp" VERSION \([^ )]*\).*/\1/p' \
        "$WHISPER_DIR/CMakeLists.txt" | head -n 1)

    if ! release=$(curl -fsSL --max-time 20 \
        -H 'User-Agent: yt-transcript-ai-updater' \
        'https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest'); then
        echo "  No se pudo consultar la última release de whisper.cpp en GitHub." >&2
        return
    fi

    tag=$("$PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("tag_name", ""))' <<< "$release")
    url=$("$PYTHON" -c 'import json,sys; print(json.load(sys.stdin).get("tarball_url", ""))' <<< "$release")
    version_remota="${tag#v}"

    if [ -z "$version_local" ] || [ -z "$version_remota" ] || [ -z "$url" ]; then
        echo "  No se pudieron determinar las versiones local/remota de whisper.cpp."
        return
    fi

    estado=$(comparar_versiones "$version_local" "$version_remota")
    case "$estado" in
        AL_DIA)
            echo "  whisper.cpp $version_local: actualizado."
            ;;
        DISTINTA)
            echo "  whisper.cpp: versión local $version_local (última release: $version_remota); no se cambia."
            ;;
        ACTUALIZABLE)
            DISPONIBLES=$((DISPONIBLES + 1))
            echo "  whisper.cpp: $version_local → $version_remota disponible."
            echo "  La actualización sobrescribe el código fuente, conserva models/ y build/, y recompila."
            if preguntar "    ¿Actualizar whisper.cpp?"; then
                if actualizar_whisper "$url"; then
                    ACTUALIZADAS=$((ACTUALIZADAS + 1))
                else
                    echo "    Error al actualizar whisper.cpp." >&2
                fi
            fi
            ;;
    esac
}

echo "Buscando actualizaciones de yt-transcript-ai..."
if [ "$SOLO_COMPROBAR" -eq 1 ]; then
    echo "Modo solo comprobación: no se instalará nada."
fi

comprobar_python
comprobar_homebrew
comprobar_whisper

printf '\n== Resumen ==\n'
echo "Actualizaciones disponibles detectadas: $DISPONIBLES"
if [ "$SOLO_COMPROBAR" -eq 0 ]; then
    echo "Componentes actualizados: $ACTUALIZADAS"
else
    echo "No se realizó ninguna instalación."
fi
