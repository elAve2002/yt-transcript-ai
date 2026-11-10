"""CLI multiplataforma para el pipeline, modelos y actualizaciones."""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from typing import Sequence

from app.config import DEFAULT_MODEL, project_paths
from app.core.download import DownloadOptions, DownloadProgress
from app.core.pipeline import STAGE_LABELS, PipelineConfig, PipelineRunner, Stage
from app.core.updates import UpdateChecker, UpdateComponent, UpdateExecutor, UpdateStatus
from app.core.utils import format_bytes
from app.core.whisper import OFFICIAL_MODELS, ModelDownloadProgress, download_model, official_model

STATUS_TEXT = {
    UpdateStatus.AL_DIA: "al día",
    UpdateStatus.ACTUALIZABLE: "actualización disponible",
    UpdateStatus.NO_INSTALADO: "no instalado",
    UpdateStatus.ERROR: "no se pudo comprobar",
    UpdateStatus.DISTINTA: "versión local distinta",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yt-transcript", description="Herramientas de yt-transcript-ai.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline = subparsers.add_parser("pipeline", help="Descarga, transcribe, diariza y fusiona un video.")
    pipeline.add_argument("url", help="URL de YouTube.")
    pipeline.add_argument("output", nargs="?", type=Path, help="Carpeta de salida (por defecto: salida/).")
    pipeline.add_argument("--calidad", type=int, default=1080, help="Resolución objetivo (por defecto: 1080).")
    pipeline.add_argument("--idioma", default="es", help="Idioma de Whisper (por defecto: es).")
    pipeline.add_argument("--modelo", type=Path, help="Ruta a otro modelo GGML.")
    pipeline.add_argument("--forzar", action="store_true", help="Repite etapas aunque ya existan sus resultados.")

    updates = subparsers.add_parser("actualizar", help="Comprueba y aplica actualizaciones.")
    updates.add_argument("--solo-comprobar", "-n", action="store_true", help="Informa sin instalar nada.")
    updates.add_argument("--yes", "-y", action="store_true", help="Instala todas las actualizaciones sin preguntar.")

    model = subparsers.add_parser("modelo", help="Descarga un modelo GGML de Whisper.")
    model.add_argument("name", choices=OFFICIAL_MODELS, help="Nombre del modelo oficial.")
    model.add_argument("--models-dir", type=Path, help="Carpeta de modelos (por defecto: whisper/models/).")
    return parser


def run_pipeline(args: argparse.Namespace) -> int:
    paths = project_paths()
    output_dir = (args.output or paths.output_dir).expanduser().resolve()
    whisper_model = (args.modelo or paths.whisper_models / DEFAULT_MODEL).expanduser()
    options = DownloadOptions(args.url, output_dir, video_height=args.calidad)
    config = PipelineConfig(
        output_dir=output_dir,
        temp_dir=paths.temp_dir,
        enabled_stages=set(Stage),
        whisper_model=whisper_model,
        language=args.idioma,
        force=args.forzar,
        source_url=args.url,
        download_options=options,
    )

    def on_state(stage: Stage, state) -> None:
        print(f"[{state.value}] {STAGE_LABELS[stage]}", flush=True)

    def on_log(level: str, message: str) -> None:
        stream = sys.stderr if level.upper() in {"ERROR", "WARNING"} else sys.stdout
        print(message, file=stream, flush=True)

    def on_progress(progress: DownloadProgress) -> None:
        if progress.percent is not None:
            print(f"\rDescarga: {progress.percent:5.1f}%", end="", flush=True)

    runner = PipelineRunner(paths, config, on_state=on_state, on_log=on_log, on_progress=on_progress)
    try:
        result = runner.run()
    except KeyboardInterrupt:
        runner.cancel()
        print("\nPipeline cancelado.", file=sys.stderr)
        return 130
    if on_progress:
        print()
    if result.cancelled:
        return 130
    print("\nArchivos generados:")
    for path in result.files:
        print(f"  {path}")
    return 0


def _print_component(component: UpdateComponent) -> None:
    installed = component.installed or "—"
    latest = component.latest or "—"
    detail = f" ({component.detail})" if component.detail else ""
    print(f"  {component.name}: instalada {installed}; disponible {latest}; {STATUS_TEXT[component.status]}{detail}")


def run_updates(args: argparse.Namespace) -> int:
    root = project_paths().root
    components = UpdateChecker(root).check_all(force=True)
    print("Componentes comprobados:")
    for component in components:
        _print_component(component)

    available = [component for component in components if component.status is UpdateStatus.ACTUALIZABLE]
    print(f"\nActualizaciones disponibles: {len(available)}")
    if not available or args.solo_comprobar:
        return 0

    selected: list[UpdateComponent] = []
    for component in available:
        if args.yes:
            selected.append(component)
            continue
        try:
            answer = input(f"¿Actualizar {component.name}? [s/N]: ")
        except EOFError:
            answer = ""
        if answer.strip().lower() == "s":
            selected.append(component)
    if not selected:
        print("No se realizó ninguna instalación.")
        return 0

    cancel_event = threading.Event()
    try:
        UpdateExecutor(root).execute(selected, print, cancel_event)
    except KeyboardInterrupt:
        cancel_event.set()
        print("\nActualización cancelada.", file=sys.stderr)
        return 130
    print(f"Componentes actualizados: {len(selected)}")
    return 0


def run_model_download(args: argparse.Namespace) -> int:
    models_dir = (args.models_dir or project_paths().whisper_models).expanduser()

    def on_progress(progress: ModelDownloadProgress) -> None:
        downloaded = format_bytes(progress.downloaded_bytes)
        if progress.percent is None:
            print(f"\rDescargados: {downloaded}", end="", flush=True)
        else:
            print(f"\rDescarga: {progress.percent:5.1f}% ({downloaded})", end="", flush=True)

    destination = download_model(official_model(args.name), models_dir, progress=on_progress)
    print(f"\nModelo instalado en: {destination}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "pipeline":
            return run_pipeline(args)
        if args.command == "actualizar":
            return run_updates(args)
        return run_model_download(args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
