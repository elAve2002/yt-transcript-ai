# yt-transcript-ai

Pipeline local para descargar vídeos de YouTube, extraer el audio y transcribirlo/diarizarlo (identificar **quién habla** y **cuándo**) usando modelos de IA que corren en tu propia máquina.

El flujo completo es:

```
YouTube ──► yt-dlp ──► vídeo (.mp4/.webm/.mkv) ──► ffmpeg ──► audio (.wav)
                                                                    │
                                                                    ▼
                                                        pyannote (diarización)
                                                                    │
                                                                    ▼
                                                     salida/<nombre>.txt
```

## Estructura del proyecto

```
.
├── auto.sh                        # Pipeline completo: descarga + wav + diarización
├── .env                           # Secretos (NO se sube al repo)
├── pyproject.toml / uv.lock       # Dependencias Python (uv)
├── yt_dlp/
│   ├── descargadorYT.py           # Versión 1 del descargador
│   └── descargadorYT_V2.py        # Descargador con metadatos y nombrado estructurado
├── pyannote/
│   └── prueba_pyannote_V2.py      # Diarización de hablantes (MPS en Apple Silicon)
├── whisper/                       # Copia de whisper.cpp (código fuente + build)
├── entrada/                       # Audios de entrada para pruebas manuales
└── salida/                        # Resultados (ignorado por git)
```

## Requisitos

- **macOS** (probado en Apple Silicon; se usa MPS si está disponible, si no CPU)
- **Python 3.14+** y [uv](https://docs.astral.sh/uv/)
- **ffmpeg** en el `PATH` (`brew install ffmpeg`)
- **Token de Hugging Face** con acceso a `pyannote/speaker-diarization-community-1`
  - Acepta las condiciones del modelo en Hugging Face y crea un token en <https://huggingface.co/settings/tokens>

## Instalación

```bash
# 1. Dependencias Python (crea .venv)
uv sync

# 2. Configurar el token en .env
cp .env.example .env      # si no existe, créalo a mano
```

`.env`:

```dotenv
PYANNOTE_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` está en `.gitignore`. Nunca commitees el token.

## Uso

### Pipeline completo

```bash
./auto.sh <URL_DE_YOUTUBE> [DIRECTORIO_SALIDA]
```

Ejemplo:

```bash
./auto.sh "https://www.youtube.com/watch?v=XXXXXXXXXXX"
# → salida/<canal>_<fecha>_video.mp4
# → salida/<canal>_<fecha>_video_BORRAR.wav
# → salida/<canal>_<fecha>_video_BORRAR.txt   (diarización)
```

Pasos que ejecuta:

1. Descarga el vídeo a 1080p con `yt_dlp/descargadorYT_V2.py`.
2. Convierte a WAV PCM 16 bit / 44.1 kHz / estéreo con `ffmpeg`.
3. Ejecuta la diarización con `pyannote/prueba_pyannote_V2.py`.

Si un `.wav` ya existe se salta la conversión; si ya existe el `.txt` de diarización se salta ese audio.

### Descargador por separado

```bash
source .venv/bin/activate
python3 yt_dlp/descargadorYT_V2.py <URL> <calidad> [--audio] [--output RUTA]
```

- `<calidad>`: `720`, `1080`, `2160`, etc. Elige la resolución más alta que no supere la pedida.
- `--audio`: descarga solo la mejor pista de audio.
- `--output`: directorio de destino (por defecto, el actual).
- Genera además un `.md` con metadatos (título, descripción, fecha, likes).
- Nombrado: `<canal>_<fecha>_<tipo>.<ext>`.

### Diarización por separado

```bash
source .venv/bin/activate
python3 pyannote/prueba_pyannote_V2.py -t "$PYANNOTE_KEY" -a /ruta/audio.wav
```

Salida (`<audio>.txt`):

```
start=0.0s stop=3.2s speaker_SPEAKER_00
start=3.2s stop=7.8s speaker_SPEAKER_01
```

## Whisper (transcripción)

`whisper/` es una copia de [whisper.cpp](https://github.com/ggml-org/whisper.cpp). Los binarios se compilan localmente y **no** se suben al repo.

```bash
cd whisper
cmake -B build
cmake --build build --config Release -j
```

Descarga un modelo (ejemplo, large-v3):

```bash
cd whisper
./models/download-ggml-model.sh large-v3
```

Transcribir:

```bash
./build/bin/whisper-cli -m models/ggml-large-v3.bin -f ../entrada/audio.wav -l es > salida.txt
```

Opciones útiles:

| Opción | Descripción |
| --- | --- |
| `-l auto` | Detección automática de idioma |
| `-l es` | Forzar español |
| `--threads N` | Número de hilos |
| `--task translate` | Traducir a inglés |

## Qué no se sube al repositorio

Definido en `.gitignore`:

- `.env` (secretos) y `.venv`
- Modelos de IA: `*.bin`, `*.ggml`, `*.gguf`, `*.safetensors`, `*.onnx`, `*.pt`, `*.pth`, etc.
- Cachés de modelos (`cache/`, `models--*/`, `.huggingface/`)
- Builds de whisper.cpp (`whisper/build/`)
- Medios y resultados: `salida/`, `basura/`, `*.wav`, `*.mp4`, `*.srt`, …

Los modelos descargados se guardan en `~/.cache/huggingface` (pyannote) y en `whisper/models/` (whisper.cpp); ninguno se versiona.
