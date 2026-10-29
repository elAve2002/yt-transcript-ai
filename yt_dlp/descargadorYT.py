#!/usr/bin/env python3
"""
Descargador de videos/audio de YouTube con selección inteligente de calidad.

Dependencias:
    - yt-dlp: descarga desde YouTube (instalar con: pip install yt-dlp)
    - ffmpeg (opcional pero recomendado): necesario para fusionar formatos de
      video y audio en un único archivo. Descargar de https://ffmpeg.org/
      y asegurarse de que esté en el PATH.

Uso:
    python download.py <URL> <calidad> [--audio] [--output RUTA]

Ejemplos:
    python download.py "https://youtu.be/abc123" 720
    python download.py "https://youtube.com/watch?v=abc123" 1080 --audio --output /home/user/Videos

El programa selecciona la resolución más cercana a la solicitada:
    - Si existe una resolución <= a la pedida, se elige la más alta de ellas.
    - Si no, se elige la menor resolución mayor (la más próxima en valor absoluto).
Con el flag --audio se ignora la calidad y se descarga solo la mejor pista de audio.
"""

import argparse
import sys
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError


def progress_hook(d):
    """Callback que muestra el progreso de descarga."""
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            percent = d.get('downloaded_bytes', 0) / total * 100
            # \r para sobreescribir la línea en la terminal
            print(f"\rDescargando... {percent:.1f}%", end='', flush=True)
        else:
            # Sin tamaño total (streams en vivo)
            downloaded = d.get('downloaded_bytes', 0)
            print(f"\rDescargando... {downloaded / 1024 / 1024:.1f} MiB recibidos", end='', flush=True)
    elif d['status'] == 'finished':
        print("\nDescarga finalizada. Procesando archivo...")


def sanitize_filename(name: str) -> str:
    """Elimina caracteres problemáticos para nombres de archivo en cualquier SO."""
    # Reemplazar caracteres no permitidos en Windows, macOS y Linux
    keepchars = (' ', '.', '_', '-')
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
    # Todas son mayores
    return min(heights)


def main():
    parser = argparse.ArgumentParser(
        description="Descarga videos o audio de YouTube con calidad seleccionable."
    )
    parser.add_argument("url", help="URL del video de YouTube")
    parser.add_argument("quality", type=int, help="Resolución deseada (ej. 144, 360, 720, 1080). Ignorada si --audio.")
    parser.add_argument("--audio", action="store_true", help="Descargar solo el audio (mejor calidad disponible).")
    parser.add_argument("--output", type=str, default=".", help="Carpeta de destino para el archivo descargado.")
    args = parser.parse_args()

    # Validar carpeta de salida
    output_dir = Path(args.output).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error: no se pudo crear el directorio de salida: {e}", file=sys.stderr)
        sys.exit(1)

    # Configuración base de yt-dlp
    ydl_opts = {
        'outtmpl': str(output_dir / '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'restrictfilenames': False,   # Permite caracteres Unicode, yt-dlp los sanitiza
        'quiet': True,                # Silenciamos la salida propia de yt-dlp, usamos nuestro hook
        'no_warnings': True,
    }

    if args.audio:
        # Solo audio: mejor calidad disponible, sin importar la resolución
        ydl_opts['format'] = 'bestaudio/best'
        print(f"Descargando audio desde: {args.url}")
    else:
        # Descarga de video con calidad seleccionada
        # Primero obtenemos información para buscar alturas disponibles
        print(f"Analizando formatos disponibles para: {args.url}")
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            try:
                info = ydl.extract_info(args.url, download=False)
            except DownloadError as e:
                print(f"Error al obtener información del video: {e}", file=sys.stderr)
                sys.exit(2)

        formats = info.get('formats', [])
        # Recolectamos alturas de formatos solo de video (vcodec != none, acodec == none)
        video_heights = set()
        for f in formats:
            if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('height'):
                video_heights.add(f['height'])

        # Si no se encontró ningún video puro, buscamos formatos combinados (video+audio)
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

        # Seleccionamos el mejor video con esa altura exacta y lo combinamos con el mejor audio
        ydl_opts['format'] = f"bestvideo[height={chosen}]+bestaudio/best"

    # Descarga real
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

    print("Proceso completado exitosamente.")


if __name__ == "__main__":
    main()