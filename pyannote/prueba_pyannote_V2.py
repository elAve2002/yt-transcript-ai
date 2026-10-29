import argparse
import os
import torch
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook

def main():
    # 1. Configurar el parser de argumentos
    parser = argparse.ArgumentParser(description="Diarización de audio con pyannote optimizado para Apple Silicon (M5).")
    parser.add_argument("-t", "--token", required=True, help="Tu token de acceso de Hugging Face.")
    parser.add_argument("-a", "--audio", required=True, help="Ruta al archivo de audio que querés procesar.")
    
    args = parser.parse_args()

    print(f"Cargando pipeline para el archivo: {args.audio}...")

    # 2. Cargar el pipeline usando el token proporcionado
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1",
        token=args.token
    )

    # 3. Detectar si Apple Silicon GPU (MPS) está disponible
    if torch.backends.mps.is_available():
        device = torch.device("mps")
        print("⚡ Usando el chip M5 (MPS) para aceleración.")
    else:
        device = torch.device("cpu")
        print("⚠️ MPS no disponible, usando CPU.")

    pipeline.to(device)

    # 4. Aplicar el pipeline con el archivo de audio proporcionado
    with ProgressHook() as hook:
        output = pipeline(args.audio, hook=hook)

    # 5. Guardar los resultados en un archivo .txt
    # Generar nombre de salida basado en el audio
    base_name = os.path.splitext(os.path.basename(args.audio))[0]
    output_file = base_name + ".txt"
    # Si quieres guardar en otra carpeta, puedes especificar una ruta, ej: os.path.join("resultados", output_file)

    with open(output_file, "w", encoding="utf-8") as f:
        for turn, speaker in output.speaker_diarization:
            f.write(f"start={turn.start:.1f}s stop={turn.end:.1f}s speaker_{speaker}\n")

    print(f"\n✅ Resultados guardados en: {output_file}")

if __name__ == "__main__":
    main()