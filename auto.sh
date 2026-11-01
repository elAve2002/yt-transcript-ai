#!/bin/bash

DIR_RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$DIR_RAIZ/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Error: no se encontró el intérprete del entorno virtual en $PYTHON" >&2
    echo "Creá el entorno con: uv venv --allow-existing && uv sync" >&2
    exit 1
fi

URL_VIDEO=$1
CALIDAD_VIDEO="1080"
PYANNOTE="$DIR_RAIZ/pyannote/prueba_pyannote_V2.py"
KEY_PYANNOTE=$(grep '^PYANNOTE_KEY=' "$DIR_RAIZ/.env" | cut -d= -f2-)
WHISPER_BIN="$DIR_RAIZ/whisper/build/bin/whisper-cli"
WHISPER_MODEL="$DIR_RAIZ/whisper/models/ggml-large-v3-turbo.bin"
WHISPER_LANG="es"
 
if [ -z "$2" ]; then
    SALIDA="$DIR_RAIZ/salida"   # dir salida por defecto
else
    SALIDA="$2"
fi

mkdir -p "$SALIDA"

"$PYTHON" "$DIR_RAIZ/yt_dlp/descargadorYT_V2.py" "$URL_VIDEO" "$CALIDAD_VIDEO" --output "$SALIDA"

cd "$SALIDA" || exit 1
for video in *.mp4 *.webm *.mkv; do
    if [ -f "$video" ]; then
        nombre_base="${video%.*}"
        archivo_wav="${nombre_base}_BORRAR.wav"
        if [ -f "$archivo_wav" ]; then
            continue
        fi
        
        ffmpeg -i "$video" -vn -acodec pcm_s16le -ar 44100 -ac 2 "$archivo_wav"
    fi
done

# Transcripción con whisper: SRT + JSON con timestamps, para enganchar con la diarización
for audio in *.wav; do
    if [ -f "$audio" ]; then
        nombre_base="${audio%.*}"
        archivo_srt="${nombre_base}.srt"

        if [ -f "$archivo_srt" ]; then
            continue
        fi

        "$WHISPER_BIN" \
            -m "$WHISPER_MODEL" \
            -f "$(pwd)/$audio" \
            -l "$WHISPER_LANG" \
            -osrt -oj \
            -ml 60 -sow \
            -of "$(pwd)/$nombre_base"
    fi
done

for audio in *.wav; do
    if [ -f "$audio" ]; then
        nombre_base="${audio%.*}"
        archivo_txt="${nombre_base}_BORRAR.txt"
        
        if [ -f "$archivo_txt" ]; then
            continue
        fi
        
        "$PYTHON" "$PYANNOTE" -t "$KEY_PYANNOTE" -a "$(pwd)/$audio"
    fi
done
