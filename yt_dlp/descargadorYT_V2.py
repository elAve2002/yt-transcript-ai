#!/usr/bin/env python3
"""
Descargador de videos/audio de YouTube con selección inteligente de calidad,
nombrado estructurado y generación de archivos de metadatos.

Dependencias:
    - yt-dlp (instalar con: pip install yt-dlp)
    - ffmpeg (opcional pero recomendado): necesario para fusionar formatos de
      video y audio en un único archivo. Descargar de https://ffmpeg.org/
      y asegurarse de que esté en el PATH.

Uso:
    python download.py <URL> <calidad> [--audio] [--output RUTA]

Ejemplos:
    python download.py "https://youtu.be/abc123" 720
    python download.py "https://youtube.com/watch?v=abc123" 1080 --audio --output /home/user/Videos

Funciones adicionales:
    - Guarda el archivo con el patrón: <canal>_<fecha>_<tipo>.<extensión>
    - Crea un archivo de metadatos .md con título, descripción, fecha/hora de
      transmisión, likes y fecha de registro.
    - El identificador común <canal>_<fecha> vincula ambos archivos.

Selección de calidad:
    - Si existe una resolución <= a la solicitada, se elige la más alta de ellas.
    - Si no, se elige la menor resolución mayor (la más próxima en valor absoluto).
Con el flag --audio se ignora la calidad y se descarga solo la mejor pista de audio.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError


def progress_hook(d):
    """Callback que muestra el progreso de descarga."""
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            percent = d.get('downloaded_bytes', 0) / total * 100
            print(f"\rDescargando... {percent:.1f}%", end='', flush=True)
        else:
            downloaded = d.get('downloaded_bytes', 0)
            print(f"\rDescargando... {downloaded / 1024 / 1024:.1f} MiB recibidos", end='', flush=True)
    elif d['status'] == 'finished':
        print("\nDescarga finalizada. Procesando archivo...")


def sanitize_filename(name: str) -> str:
    """
    Elimina caracteres problemáticos para nombres de archivo en cualquier SO.
    Reemplaza espacios por guiones bajos y conserva caracteres alfanuméricos,
    punto, guion y guion bajo. El resto se descarta.
    """
    # Reemplazar espacios por '_' y filtrar el resto
    name = name.replace(' ', '_')
    keepchars = ('_', '-', '.')
    return "".join(c for c in name if c.isalnum() or c in keepchars).rstrip()


def get_closest_quality(available_heights: set, target: int) -> int:
    """
    Aplica la regla de calidad:
    1) Mayor resolución que no supere el target.
    2) Si no hay ninguna <= target, la menor resolución > target.
    """
    heights = sorted(available_heights)
    if not heights:
        raise ValueError("No hay formatos de video disponibles.")
    lower = [h for h in heights if h <= target]
    if lower:
        return max(lower)
    return min(heights)


def write_metadata(info: dict, output_dir: Path, identifier: str) -> None:
    """
    Crea un archivo Markdown con los metadatos del video.
    El nombre del archivo será <identifier>.md en el directorio de salida.

    :param info: diccionario con la información extraída por yt-dlp.
    :param output_dir: carpeta donde se guardará el archivo.
    :param identifier: cadena común para vincular los archivos.
    """
    title = info.get('title', 'Título desconocido')
    description = info.get('description', 'Sin descripción')
    upload_date = info.get('upload_date')  # YYYYMMDD
    timestamp = info.get('timestamp')      # Unix timestamp (segundos)
    like_count = info.get('like_count')
    channel = info.get('channel') or info.get('uploader') or 'Desconocido'

    # Formatear fecha y hora de transmisión
    if upload_date:
        date_obj = datetime.strptime(upload_date, "%Y%m%d")
        date_str = date_obj.strftime("%Y-%m-%d")
    else:
        date_str = "Fecha desconocida"

    if timestamp:
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    else:
        time_str = "Hora desconocida"

    # Fecha en que se registraron los likes (ahora)
    registered_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Contenido Markdown
    md_content = f"""# {title}

**Canal:** {channel}

**Fecha de transmisión:** {date_str}
**Hora de transmisión:** {time_str}

**Descripción:**
{description}

**Likes registrados:** {like_count if like_count is not None else 'No disponible'}
**Fecha de registro de likes:** {registered_at}
"""

    md_path = output_dir / f"{identifier}.md"
    try:
        md_path.write_text(md_content, encoding='utf-8')
        print(f"Archivo de metadatos guardado: {md_path}")
    except Exception as e:
        print(f"Error al escribir el archivo de metadatos: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Descarga videos o audio de YouTube con calidad seleccionable."
    )
    parser.add_argument("url", help="URL del video de YouTube")
    parser.add_argument("quality", type=int, help="Resolución deseada (ej. 144, 360, 720, 1080). Ignorada si --audio.")
    parser.add_argument("--audio", action="store_true", help="Descargar solo el audio (mejor calidad disponible).")
    parser.add_argument("--output", type=str, default=".", help="Carpeta de destino para los archivos descargados.")
    args = parser.parse_args()

    # Validar carpeta de salida
    output_dir = Path(args.output).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error: no se pudo crear el directorio de salida: {e}", file=sys.stderr)
        sys.exit(1)

    # Tipo de descarga: 'video' o 'audio'
    tipo = "audio" if args.audio else "video"

    # Paso 1: Extraer información del video (necesaria para calidad y metadatos)
    print(f"Analizando información del video: {args.url}")
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
        try:
            info = ydl.extract_info(args.url, download=False)
        except DownloadError as e:
            print(f"Error al obtener información del video: {e}", file=sys.stderr)
            sys.exit(2)

    # Extraer campos necesarios
    channel = info.get('channel') or info.get('uploader') or 'unknown'
    upload_date = info.get('upload_date')  # YYYYMMDD

    # Sanitizar canal y formatear fecha
    sanitized_channel = sanitize_filename(channel)
    if upload_date:
        try:
            date_str = datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            date_str = "unknown_date"
    else:
        date_str = "unknown_date"

    # Identificador común
    identifier = f"{sanitized_channel}_{date_str}"

    # Configuración base de yt-dlp
    ydl_opts = {
        'outtmpl': str(output_dir / f"{identifier}_{tipo}.%(ext)s"),
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
    }

    if args.audio:
        # Solo audio: mejor calidad disponible
        ydl_opts['format'] = 'bestaudio/best'
        print(f"Descargando audio (mejor calidad) desde: {args.url}")
    else:
        # Descarga de video: seleccionar calidad adecuada
        formats = info.get('formats', [])
        video_heights = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('height'):
                video_heights.add(f['height'])

        # Si no hay video puro, usar combinados
        if not video_heights:
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('height'):
                    video_heights.add(f['height'])

        if not video_heights:
            print("Error: no se encontraron streams de video en el enlace proporcionado.", file=sys.stderr)
            sys.exit(2)

        try:
            chosen = get_closest_quality(video_heights, args.quality)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)

        print(f"Calidad solicitada: {args.quality}p -> usando {chosen}p")

        # Formato: mejor video con esa altura + mejor audio. Forzar contenedor MP4.
        ydl_opts['format'] = f"bestvideo[height={chosen}]+bestaudio/best"
        ydl_opts['merge_output_format'] = 'mp4'

    # Paso 2: Descargar
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            print("Iniciando descarga...")
            ydl.download([args.url])
        except DownloadError as e:
            print(f"\nError durante la descarga: {e}", file=sys.stderr)
            sys.exit(2)
        except KeyboardInterrupt:
            print("\nDescarga interrumpida por el usuario.", file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f"\nError inesperado: {e}", file=sys.stderr)
            sys.exit(2)

    # Paso 3: Crear archivo de metadatos
    write_metadata(info, output_dir, identifier)

    print("Proceso completado exitosamente.")


if __name__ == "__main__":
    main()