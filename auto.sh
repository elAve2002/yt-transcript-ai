#!/bin/bash

source .venv/bin/activate

URL_VIDEO=$1
CALIDAD_VIDEO="1080"
DIR_RAIZ="$(pwd)"
PYANNOTE="$DIR_RAIZ/pyannote/prueba_pyannote_V2.py"
KEY_PYANNOTE=$(grep '^PYANNOTE_KEY=' "$DIR_RAIZ/.env" | cut -d= -f2-)
 
if [ -z "$2" ]; then
    SALIDA="$DIR_RAIZ/salida"   # dir salida por defecto
else
    SALIDA="$2"
fi

mkdir -p "$SALIDA"

python3 "$DIR_RAIZ/yt_dlp/descargadorYT_V2.py" "$URL_VIDEO" "$CALIDAD_VIDEO" --output "$SALIDA"

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

for audio in *.wav; do
    if [ -f "$audio" ]; then
        nombre_base="${audio%.*}"
        archivo_txt="${nombre_base}_BORRAR.txt"
        
        if [ -f "$archivo_txt" ]; then
            continue
        fi
        
        python3 "$PYANNOTE" -t "$KEY_PYANNOTE" -a "$(pwd)/$audio"
    fi
done
