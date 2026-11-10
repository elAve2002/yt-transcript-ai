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

Se usa **PySide6-Essentials 6.12.0**: incluye Qt Widgets bajo el namespace `PySide6` y evita descargar WebEngine y otros módulos que la app no necesita. Sus wheels `abi3` son compatibles con Python 3.14 en macOS y Windows. Los iconos los provee **qtawesome 1.4.2**.

### Pantallas

- **Inicio:** descripción del flujo y accesos rápidos.
- **Descargar:** selector YouTube/archivo local, drag & drop, vista previa con miniatura, formatos reales de yt-dlp, opciones de audio/video, tamaño estimado y progreso con velocidad/ETA. Los archivos locales se validan con ffprobe.
- **Procesar:** etapas activables, modelo e idioma Whisper, reutilización o re-ejecución forzada, estados por etapa, consola en vivo, cancelación y accesos a los archivos generados. Desde aquí también se descargan modelos GGML con progreso.
- **Actualizaciones:** versiones instaladas/disponibles, estados, selección múltiple, confirmación con comandos y log de la instalación. Las consultas son concurrentes y tienen caché de 10 minutos.
- **Ajustes:** tema sistema/claro/oscuro, color de acento y token de Hugging Face enmascarado, con prueba de identidad y acceso al modelo.

La ventana usa una sidebar, tarjetas, estados vacíos, spinners y toasts. Guarda geometría, tema, modelo, calidad, idioma y carpeta mediante `QSettings`. Atajos: **Cmd/Ctrl+O** para abrir un archivo local, **Cmd/Ctrl+Enter** para procesar y **Cmd/Ctrl+,** para Ajustes; Qt selecciona el modificador apropiado en cada sistema.

Los logs se guardan con rotación en `logs/app.log`. El token se conserva en `.env`, puede sobreescribirse con la variable de entorno `PYANNOTE_KEY` y nunca se pasa como argumento del proceso de pyannote. En macOS/Linux el archivo recibe permisos `600`; en Windows se respetan las ACL de la carpeta del usuario.

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

- **macOS** (probado en Apple Silicon) o **Windows 10/11 x64**.
- **Python 3.14 o superior**.
- [uv](https://docs.astral.sh/uv/) para crear el entorno e instalar las dependencias Python.
- **ffmpeg** para combinar audio/video en yt-dlp y extraer el WAV. No hace falta instalarlo: `uv sync` incluye **static-ffmpeg**, que baja los ejecutables `ffmpeg` y `ffprobe` a `.venv/` la primera vez que se los necesita. Si existe un ffmpeg en el sistema, la app siempre le da prioridad.
- **CMake** y un compilador C/C++ para compilar whisper.cpp. En macOS se obtienen con Xcode Command Line Tools; en Windows, con Visual Studio Build Tools y la carga de trabajo **Desarrollo para el escritorio con C++**.

En macOS, las herramientas pueden instalarse con Homebrew:

```bash
xcode-select --install
brew install uv cmake
```

En Windows, instalá uv, CMake y Visual Studio Build Tools desde sus sitios oficiales. No hace falta WSL, Git Bash ni FFmpeg del sistema.

> **Audio de pyannote:** el WAV se precarga con `torchaudio` y se entrega a pyannote como waveform. Por eso la diarización no necesita las bibliotecas compartidas de FFmpeg que `torchcodec` podría requerir para decodificar otros archivos.

### Python

`uv sync` instala las dependencias declaradas en `pyproject.toml`:

- `yt-dlp`: descarga de videos y metadatos.
- `pyannote-audio`: diarización de hablantes.
- `torch`, `torchaudio` y `torchvision`: ejecución de los modelos de pyannote.
- `torchcodec`: decodificación de audio para pyannote. Va acoplado binariamente a `torch` (no lo declara como dependencia), por eso la familia `torch`/`torchaudio`/`torchvision`/`torchcodec` se actualiza siempre junta.
- `static-ffmpeg`: provee los ejecutables `ffmpeg` y `ffprobe` sin Homebrew. El paquete en sí es liviano; los binarios se descargan automáticamente en `.venv/` la primera vez que el pipeline los usa.
- `PySide6-Essentials` y `qtawesome`: interfaz de escritorio Qt 6 e iconos.
- `pytest` (grupo de desarrollo): tests del núcleo y de la GUI.

pyannote selecciona **CUDA** si hay una GPU NVIDIA compatible, **MPS** en Apple Silicon y **CPU** como respaldo.

### Modelos

- **Whisper:** `whisper/models/ggml-large-v3-turbo.bin`.
- **pyannote:** `pyannote/speaker-diarization-community-1`, descargado automáticamente en la primera ejecución.
- **Token de Hugging Face** con acceso al modelo de pyannote. Antes de usarlo, acepta las condiciones del modelo en su página de Hugging Face y crea un token en <https://huggingface.co/settings/tokens>.

## Instalación

### 1. Instalar las dependencias Python

```bash
uv sync
```

Esto crea `.venv/` con el intérprete y las dependencias del proyecto, incluido el ffmpeg empaquetado: `uv sync` instala `static-ffmpeg` y los binarios `ffmpeg`/`ffprobe` se descargan solos la primera vez que el pipeline los usa (o en el arranque de la GUI). Si querés bajarlos ya, sin esperar:

```bash
uv run python -c "from app.core.ffmpeg import ensure_ffmpeg; print(ensure_ffmpeg())"
```

### 2. Configurar Hugging Face

En macOS/Linux:

```bash
cp .env.example .env
```

En Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

También podés pegar y guardar el token desde la pantalla **Ajustes** de la GUI. Edita `.env`:

```dotenv
PYANNOTE_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> `.env` está ignorado por git. No compartas ni commitees el token.

### 3. Compilar whisper.cpp

El código fuente está incluido en `whisper/`; el build no se versiona.

Los mismos comandos funcionan en macOS y Windows:

```bash
cmake -S whisper -B whisper/build
cmake --build whisper/build --config Release --parallel
```

La aplicación encuentra el ejecutable tanto en `whisper/build/bin/whisper-cli` como en la salida multiconfiguración de Visual Studio, `whisper/build/bin/Release/whisper-cli.exe`.

### 4. Descargar el modelo de Whisper

```bash
uv run yt-transcript modelo large-v3-turbo
```

El archivo debe quedar en:

```text
whisper/models/ggml-large-v3-turbo.bin
```

## Actualizar dependencias

En macOS/Linux:

```bash
./actualizar.sh
```

En Windows:

```bat
actualizar.cmd
```

También podés usar directamente `uv run yt-transcript actualizar`. La implementación está en Python y comprueba por separado:

- `yt-dlp`, `pyannote-audio`, `torch`, `torchaudio`, `torchvision`, `torchcodec` y `static-ffmpeg` en PyPI.
  - La familia `torch`/`torchaudio`/`torchvision`/`torchcodec` se actualiza **junta en un solo comando**, porque `torchcodec` está acoplado binariamente a `torch` aunque no lo declare como dependencia.
  - Actualizar `static-ffmpeg` reinstala los binarios `ffmpeg`/`ffprobe` empaquetados: la app los vuelve a descargar automáticamente al primer uso.
- `ffmpeg`, `cmake` y `uv` en Homebrew, **solo en macOS** y si están instalados ahí.
- La última release estable de whisper.cpp en GitHub.

Cuando encuentra una actualización, muestra las versiones y pregunta si deseas instalarla antes de hacer cualquier cambio. La actualización de whisper.cpp descarga el código fuente, conserva `models/` y `build/`, y recompila `whisper-cli`.

Para consultar sin instalar nada:

```bash
./actualizar.sh --solo-comprobar
```

En Windows: `actualizar.cmd --solo-comprobar`.

## Uso del pipeline completo

En macOS/Linux:

```bash
./auto.sh <URL_DE_YOUTUBE> [DIRECTORIO_SALIDA]
```

En Windows:

```bat
auto.cmd "https://www.youtube.com/watch?v=XXXXXXXXXXX" C:\ruta\resultados
```

La forma multiplataforma directa es:

```bash
uv run yt-transcript pipeline "https://www.youtube.com/watch?v=XXXXXXXXXXX" salida
```

Si no indicas directorio de salida, se usa `salida/`. El comando ejecuta estas etapas:

1. Descarga el video con una calidad objetivo de **1080p** y genera un `.md` con sus metadatos.
2. Extrae un WAV PCM de 16 bits, 44,1 kHz y estéreo en `temporales/`.
3. Transcribe el audio en español con Whisper y genera `.srt` y `.json` con timestamps.
4. Diariza el audio con pyannote y genera el `.txt` de hablantes.
5. Combina la transcripción y la diarización por solapamiento temporal.
6. Guarda el guion final `<nombre>_diarizado.txt` en el directorio de salida.

La calidad, el idioma y el modelo se pueden cambiar sin editar archivos:

```bash
uv run yt-transcript pipeline "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  --calidad 720 --idioma es --modelo whisper/models/ggml-large-v3-turbo.bin
```

Agregá `--forzar` para repetir etapas aunque ya existan sus resultados.

### Reanudar o repetir etapas

Cada etapa se omite si ya existe su archivo de resultado:

- WAV existente: no vuelve a ejecutar ffmpeg.
- SRT existente: no vuelve a transcribir con Whisper.
- TXT de diarización existente: no vuelve a ejecutar pyannote.
- Guion `_diarizado.txt` existente: no vuelve a hacer el merge.

Para repetir una etapa, eliminá su archivo de salida y volvé a ejecutar el comando, o usá `--forzar`.

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

No hace falta activar manualmente el entorno ni conocer si usa `bin/` o `Scripts/`: `uv run python` selecciona el intérprete correcto en ambos sistemas.

### Descargar un video

```bash
uv run python yt_dlp/descargadorYT_V2.py <URL> <calidad> [--audio] [--output RUTA]
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

En Windows con Visual Studio, reemplazá `whisper/build/bin/whisper-cli` por `whisper/build/bin/Release/whisper-cli.exe`. La GUI y el CLI detectan ambas ubicaciones automáticamente.

### Diarizar con pyannote

```bash
uv run python pyannote/prueba_pyannote_V2.py \
  -a /ruta/absoluta/audio.wav
```

El TXT se guarda en el directorio desde el que ejecutas el comando, con el mismo nombre base del audio:

```text
start=0.0s stop=3.2s speaker_SPEAKER_00
start=3.2s stop=7.8s speaker_SPEAKER_01
```

El script toma el token de `PYANNOTE_KEY`. También acepta `-t/--token` para mantener compatibilidad con la CLI anterior, aunque se recomienda el entorno para que el secreto no aparezca en la lista de procesos.

Si ejecutás el comando desde una shell, cargá antes la variable con `export PYANNOTE_KEY=...` en macOS/Linux o `$env:PYANNOTE_KEY="..."` en PowerShell. También podés guardarla en `.env` desde la GUI.

### Hacer el merge manualmente

```bash
uv run python merge/merge_whisper_pyannote.py \
  -j temporales/<nombre>.json \
  -d temporales/<nombre>.txt \
  -o salida/<nombre>_diarizado.txt
```

Si omites `-o`, el resultado se crea junto al JSON como `<nombre>_diarizado.txt`.

Para obtener una línea por segmento de Whisper, sin unir turnos consecutivos:

```bash
uv run python merge/merge_whisper_pyannote.py \
  -j temporales/<nombre>.json \
  -d temporales/<nombre>.txt \
  --sin-fusionar
```

## Tests

```bash
uv run pytest
```

La suite cubre selección de calidad, listado de modelos, resolución de ffmpeg/ffprobe, rutas de Python/Whisper en POSIX y Windows, creación y cancelación de procesos por SO, actualizaciones, token, CLI y transiciones del pipeline. Las pruebas de red y subprocess están aisladas: no descargan modelos ni actualizan dependencias. El workflow `.github/workflows/tests.yml` ejecuta la suite en macOS y Windows con Python 3.14.

## Estructura del proyecto

```text
.
├── auto.sh / auto.cmd              # Pipeline completo en macOS/Linux y Windows
├── actualizar.sh / actualizar.cmd  # Actualizaciones en macOS/Linux y Windows
├── .gitattributes                  # Fines de línea y archivos binarios
├── .github/workflows/tests.yml     # Tests en macOS y Windows
├── .env                            # Token local; no se versiona
├── .env.example                    # Plantilla de configuración
├── pyproject.toml / uv.lock        # Dependencias y entry points `gui` / `yt-transcript`
├── app/
│   ├── main.py                     # Entrada de la aplicación Qt
│   ├── cli.py                      # CLI multiplataforma
│   ├── config.py                   # Rutas del proyecto y ejecutables por SO
│   ├── core/                       # Descarga, pipeline, ffmpeg, Whisper y actualizaciones
│   ├── services/                   # Workers, token y servicios compartidos
│   └── ui/                         # Ventana, pantallas, diálogos y tema
├── tests/                          # Tests del núcleo, CLI, rutas, procesos y plataforma
├── yt_dlp/
│   ├── descargadorYT.py
│   └── descargadorYT_V2.py         # Descarga y metadatos
├── pyannote/
│   └── prueba_pyannote_V2.py       # Diarización con CUDA, MPS o CPU
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
