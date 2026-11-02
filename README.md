# yt-transcript-ai

Pipeline local para descargar videos de YouTube, transcribirlos con **Whisper**, identificar hablantes con **pyannote** y generar un guion final con tiempos y hablantes.

Todo el procesamiento se hace en tu máquina. La descarga del video, los modelos y el acceso inicial a Hugging Face requieren conexión a internet.

## Aplicación de escritorio

La GUI en español permite operar todo el pipeline sin usar la terminal. Está construida con **PySide6/Qt 6**, QSS propio y qtawesome; no requiere tkinter ni qfluentwidgets.

### Instalación y ejecución

```bash
uv sync
uv run gui
```

También podés iniciarla con:

```bash
uv run python -m app
```

Se usa **PySide6-Essentials 6.12.0**: incluye Qt Widgets bajo el namespace `PySide6` y evita descargar WebEngine y otros módulos que la app no necesita. Su wheel macOS es `cp310-abi3`, compatible con Python 3.14 en Apple Silicon. Los iconos los provee **qtawesome 1.4.2**.

### Pantallas

- **Inicio:** descripción del flujo y accesos rápidos.
- **Descargar:** selector YouTube/archivo local, drag & drop, vista previa con miniatura, formatos reales de yt-dlp, opciones de audio/video, tamaño estimado y progreso con velocidad/ETA. Los archivos locales se validan con ffprobe.
- **Procesar:** etapas activables, modelo e idioma Whisper, reutilización o re-ejecución forzada, estados por etapa, consola en vivo, cancelación y accesos a los archivos generados. Desde aquí también se descargan modelos GGML con progreso.
- **Actualizaciones:** versiones instaladas/disponibles, estados, selección múltiple, confirmación con comandos y log de la instalación. Las consultas son concurrentes y tienen caché de 10 minutos.
- **Ajustes:** tema sistema/claro/oscuro, color de acento y token de Hugging Face enmascarado, con prueba de identidad y acceso al modelo.

La ventana usa una sidebar, tarjetas, estados vacíos, spinners y toasts. Guarda geometría, tema, modelo, calidad, idioma y carpeta mediante `QSettings`. Atajos: **⌘O** para abrir un archivo local, **⌘Enter** para procesar y **⌘,** para Ajustes.

Los logs se guardan con rotación en `logs/app.log`. El token se conserva en `.env` con permisos `600`, puede sobreescribirse con la variable de entorno `PYANNOTE_KEY` y nunca se pasa como argumento del proceso de pyannote.

## Flujo de trabajo

```text
YouTube
   │
   ▼
yt-dlp ───────────────────────────────► salida/<nombre>.mp4
   │                                     salida/<nombre>.md
   ▼
ffmpeg ───────────────────────────────► temporales/<nombre>_BORRAR.wav
   │
   ├──► Whisper ──────────────────────► temporales/<nombre>_BORRAR.srt
   │                                     temporales/<nombre>_BORRAR.json
   │
   └──► pyannote ─────────────────────► temporales/<nombre>_BORRAR.txt
                                          (diarización)
   │
   ▼
Merge por solapamiento temporal ──────► salida/<nombre>_BORRAR_diarizado.txt
```

El resultado final tiene este formato:

```text
[00:00:00 - 00:00:04] SPEAKER_01: Texto de la intervención.
[00:00:05 - 00:02:15] SPEAKER_00: Respuesta de otro hablante...
```

`SPEAKER_00`, `SPEAKER_01`, etc. son etiquetas generadas por pyannote: identifican voces distintas, pero no sus nombres reales. La numeración puede cambiar entre videos.

## Dependencias

### Sistema

- **macOS**, probado en Apple Silicon.
- **Python 3.14 o superior**.
- [uv](https://docs.astral.sh/uv/) para crear el entorno e instalar las dependencias Python.
- **ffmpeg**, necesario tanto para combinar audio/video en yt-dlp como para extraer el WAV.
- **CMake** y un compilador C/C++ para compilar whisper.cpp. En macOS se obtienen con Xcode Command Line Tools.

Instalación de las herramientas con Homebrew:

```bash
xcode-select --install
brew install uv ffmpeg cmake
```

### Python

`uv sync` instala las dependencias declaradas en `pyproject.toml`:

- `yt-dlp`: descarga de videos y metadatos.
- `pyannote-audio`: diarización de hablantes.
- `torch`, `torchaudio` y `torchvision`: ejecución de los modelos de pyannote.
- `torchcodec`: decodificación de audio para pyannote. Va acoplado binariamente a `torch` (no lo declara como dependencia), por eso la familia `torch`/`torchaudio`/`torchvision`/`torchcodec` se actualiza siempre junta.
- `PySide6-Essentials` y `qtawesome`: interfaz de escritorio Qt 6 e iconos.
- `pytest` (grupo de desarrollo): tests del núcleo y de la GUI.

En Apple Silicon, pyannote usa **MPS** si está disponible; en caso contrario, utiliza CPU.

### Modelos

- **Whisper:** `whisper/models/ggml-large-v3-turbo.bin`.
- **pyannote:** `pyannote/speaker-diarization-community-1`, descargado automáticamente en la primera ejecución.
- **Token de Hugging Face** con acceso al modelo de pyannote. Antes de usarlo, acepta las condiciones del modelo en su página de Hugging Face y crea un token en <https://huggingface.co/settings/tokens>.

## Instalación

### 1. Instalar las dependencias Python

```bash
uv sync
```

Esto crea `.venv/` con el intérprete y las dependencias del proyecto.

### 2. Configurar Hugging Face

```bash
cp .env.example .env
```

Edita `.env`:

```dotenv
PYANNOTE_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` está ignorado por git. No compartas ni commitees el token.

### 3. Compilar whisper.cpp

El código fuente está incluido en `whisper/`; el build no se versiona.

```bash
cd whisper
cmake -B build
cmake --build build --config Release -j
cd ..
```

### 4. Descargar el modelo de Whisper

```bash
cd whisper
./models/download-ggml-model.sh large-v3-turbo
cd ..
```

El archivo debe quedar en:

```text
whisper/models/ggml-large-v3-turbo.bin
```

## Actualizar dependencias

```bash
./actualizar.sh
```

El script comprueba por separado:

- `yt-dlp`, `pyannote-audio`, `torch`, `torchaudio`, `torchvision` y `torchcodec` en PyPI.
  - La familia `torch`/`torchaudio`/`torchvision`/`torchcodec` se actualiza **junta en un solo comando**, porque `torchcodec` está acoplado binariamente a `torch` aunque no lo declare como dependencia.
- `ffmpeg`, `cmake` y `uv` en Homebrew.
- La última release estable de whisper.cpp en GitHub.

Cuando encuentra una actualización, muestra las versiones y pregunta si deseas instalarla antes de hacer cualquier cambio. La actualización de whisper.cpp descarga el código fuente, conserva `models/` y `build/`, y recompila `whisper-cli`.

Para consultar sin instalar nada:

```bash
./actualizar.sh --solo-comprobar
```

## Uso del pipeline completo

```bash
./auto.sh <URL_DE_YOUTUBE> [DIRECTORIO_SALIDA]
```

Ejemplo:

```bash
./auto.sh "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

Si no indicas directorio de salida, se usa `salida/`. También puedes elegir otro:

```bash
./auto.sh "https://www.youtube.com/watch?v=XXXXXXXXXXX" /ruta/resultados
```

El script ejecuta estas etapas:

1. Descarga el video con una calidad objetivo de **1080p** y genera un `.md` con sus metadatos.
2. Extrae un WAV PCM de 16 bits, 44,1 kHz y estéreo en `temporales/`.
3. Transcribe el audio en español con Whisper y genera `.srt` y `.json` con timestamps.
4. Diariza el audio con pyannote y genera el `.txt` de hablantes.
5. Combina la transcripción y la diarización por solapamiento temporal.
6. Guarda el guion final `<nombre>_diarizado.txt` en el directorio de salida.

Las rutas del binario, el modelo y el idioma de Whisper se configuran al comienzo de `auto.sh`:

```bash
WHISPER_BIN="$DIR_RAIZ/whisper/build/bin/whisper-cli"
WHISPER_MODEL="$DIR_RAIZ/whisper/models/ggml-large-v3-turbo.bin"
WHISPER_LANG="es"
```

### Reanudar o repetir etapas

Cada etapa se omite si ya existe su archivo de resultado:

- WAV existente: no vuelve a ejecutar ffmpeg.
- SRT existente: no vuelve a transcribir con Whisper.
- TXT de diarización existente: no vuelve a ejecutar pyannote.
- Guion `_diarizado.txt` existente: no vuelve a hacer el merge.

Para repetir una etapa, elimina su archivo de salida y vuelve a ejecutar `auto.sh`.

## Archivos generados

```text
yt-transcript-ai/
├── temporales/
│   ├── <canal>_<fecha>_video_BORRAR.wav
│   ├── <canal>_<fecha>_video_BORRAR.srt
│   ├── <canal>_<fecha>_video_BORRAR.json
│   └── <canal>_<fecha>_video_BORRAR.txt
└── salida/
    ├── <canal>_<fecha>_video.mp4
    ├── <canal>_<fecha>_video.md
    └── <canal>_<fecha>_video_BORRAR_diarizado.txt
```

- **`.mp4`**: video descargado.
- **`.md`**: título, canal, descripción, fecha y otros metadatos.
- **`.wav`**: audio intermedio para Whisper y pyannote.
- **`.srt`**: subtítulos con tiempos, sin etiquetas de hablante.
- **`.json`**: segmentos de Whisper con offsets en milisegundos.
- **`.txt` en `temporales/`**: turnos de hablantes detectados por pyannote.
- **`_diarizado.txt`**: guion final con tiempos, hablantes y texto.

A pesar del sufijo `_BORRAR`, el pipeline no elimina archivos automáticamente.

## Cómo funciona el merge

`merge/merge_whisper_pyannote.py` lee los segmentos de Whisper y los turnos de pyannote:

1. Convierte los offsets de Whisper de milisegundos a segundos.
2. Calcula cuánto se solapa cada segmento con cada hablante.
3. Asigna el segmento al hablante con **mayor solapamiento acumulado**.
4. Si no existe solapamiento, usa el turno de diarización más cercano al centro del segmento.
5. Une los segmentos consecutivos del mismo hablante en un solo bloque.

Si un segmento contiene un cambio de voz, su texto se atribuye al hablante dominante: el JSON utilizado no contiene tiempos por palabra. El pipeline usa `-ml 60 -sow` para generar segmentos más cortos y reducir este problema.

## Ejecutar las herramientas por separado

No hace falta activar manualmente el entorno: puedes usar `.venv/bin/python`.

### Descargar un video

```bash
.venv/bin/python yt_dlp/descargadorYT_V2.py <URL> <calidad> [--audio] [--output RUTA]
```

- `<calidad>`: `720`, `1080`, `2160`, etc. Selecciona la resolución más alta que no supere la solicitada.
- `--audio`: descarga solamente la mejor pista de audio.
- `--output`: directorio de destino; por defecto, el actual.

### Transcribir con Whisper

```bash
whisper/build/bin/whisper-cli \
  -m whisper/models/ggml-large-v3-turbo.bin \
  -f temporales/<nombre>.wav \
  -l es \
  -osrt -oj \
  -ml 60 -sow \
  -of temporales/<nombre>
```

- `-osrt`: genera subtítulos `.srt`.
- `-oj`: genera el `.json` necesario para el merge.
- `-ml 60 -sow`: limita la longitud de los segmentos y los divide por palabras.
- `-of`: prefijo de salida **sin extensión**.

### Diarizar con pyannote

```bash
.venv/bin/python pyannote/prueba_pyannote_V2.py \
  -a /ruta/absoluta/audio.wav
```

El TXT se guarda en el directorio desde el que ejecutas el comando, con el mismo nombre base del audio:

```text
start=0.0s stop=3.2s speaker_SPEAKER_00
start=3.2s stop=7.8s speaker_SPEAKER_01
```

El script toma el token de `PYANNOTE_KEY`. También acepta `-t/--token` para mantener compatibilidad con la CLI anterior, aunque se recomienda el entorno para que el secreto no aparezca en la lista de procesos.

Si ejecutas el comando desde una shell, carga antes la variable con `export PYANNOTE_KEY=...` o reemplázala directamente por tu token.

### Hacer el merge manualmente

```bash
.venv/bin/python merge/merge_whisper_pyannote.py \
  -j temporales/<nombre>.json \
  -d temporales/<nombre>.txt \
  -o salida/<nombre>_diarizado.txt
```

Si omites `-o`, el resultado se crea junto al JSON como `<nombre>_diarizado.txt`.

Para obtener una línea por segmento de Whisper, sin unir turnos consecutivos:

```bash
.venv/bin/python merge/merge_whisper_pyannote.py \
  -j temporales/<nombre>.json \
  -d temporales/<nombre>.txt \
  --sin-fusionar
```

## Tests

```bash
uv run pytest
```

La suite cubre selección de calidad, listado de modelos, parseo/estado de actualizaciones, guardado y carga segura del token, y transiciones/cancelación del pipeline con mocks. Las pruebas de red y subprocess están aisladas: no descargan modelos ni actualizan dependencias.

## Estructura del proyecto

```text
.
├── auto.sh                         # Pipeline completo
├── actualizar.sh                   # Comprobación y actualización de dependencias
├── .env                            # Token local; no se versiona
├── .env.example                    # Plantilla de configuración
├── pyproject.toml / uv.lock        # Dependencias Python y entry point `gui`
├── app/
│   ├── main.py                     # Entrada de la aplicación Qt
│   ├── config.py                   # Rutas del proyecto
│   ├── core/                       # Descarga, pipeline, Whisper y actualizaciones
│   ├── services/                   # Workers, token y servicios compartidos
│   └── ui/                         # Ventana, pantallas, diálogos y tema
├── tests/                          # Tests de calidad, modelos, updates, token y pipeline
├── yt_dlp/
│   ├── descargadorYT.py
│   └── descargadorYT_V2.py         # Descarga y metadatos
├── pyannote/
│   └── prueba_pyannote_V2.py       # Diarización con MPS o CPU
├── merge/
│   └── merge_whisper_pyannote.py   # Unión por solapamiento temporal
├── whisper/                        # Código fuente y modelo de whisper.cpp
├── entrada/                        # Archivos para pruebas manuales
├── temporales/                     # WAV, SRT, JSON y diarización intermedia
├── logs/                           # Log rotativo de la GUI
└── salida/                         # Video, metadatos y guion final
```

## Qué no se sube al repositorio

El `.gitignore` excluye, entre otros:

- `.env`, `.venv/` y cachés de Python.
- Modelos: `*.bin`, `*.gguf`, `*.safetensors`, `*.pt`, etc.
- Builds de whisper.cpp.
- `salida/`, `temporales/`, `logs/`, `basura/` y archivos de audio/video/subtítulos.
- Cachés de Hugging Face.

Los modelos se almacenan localmente en `whisper/models/` y en la caché de Hugging Face; ninguno se versiona.
