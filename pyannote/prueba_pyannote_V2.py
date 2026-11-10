import argparse
import os
from pathlib import Path

import torch
import torchaudio
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook


def select_device() -> torch.device:
    """Usa la GPU disponible y conserva CPU como respaldo multiplataforma."""
    if torch.cuda.is_available():
        print("Usando GPU CUDA para aceleración.")
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        print("Usando GPU Apple Silicon (MPS) para aceleración.")
        return torch.device("mps")
    print("No hay GPU compatible disponible; usando CPU.")
    return torch.device("cpu")


def main():
    parser = argparse.ArgumentParser(description="Diarización de audio con pyannote.")
    parser.add_argument("-t", "--token", default=os.environ.get("PYANNOTE_KEY"), help="Tu token de acceso de Hugging Face.")
    parser.add_argument("-a", "--audio", required=True, help="Ruta al archivo de audio WAV que querés procesar.")

    args = parser.parse_args()
    if not args.token:
        parser.error("Debés proporcionar un token con -t/--token o definir la variable de entorno PYANNOTE_KEY.")

    print(f"Cargando pipeline para el archivo: {args.audio}...")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1",
        token=args.token,
    )
    pipeline.to(select_device())

    # El pipeline genera WAV PCM. Decodificarlo con torchaudio evita exigir las
    # bibliotecas compartidas de FFmpeg que torchcodec necesita en algunos SO.
    waveform, sample_rate = torchaudio.load(args.audio)
    audio = {"waveform": waveform, "sample_rate": sample_rate}
    with ProgressHook() as hook:
        output = pipeline(audio, hook=hook)

    base_name = Path(args.audio).stem
    output_file = base_name + ".txt"
    with open(output_file, "w", encoding="utf-8") as file:
        for turn, speaker in output.speaker_diarization:
            file.write(f"start={turn.start:.1f}s stop={turn.end:.1f}s speaker_{speaker}\n")

    print(f"\nResultados guardados en: {output_file}")


if __name__ == "__main__":
    main()
