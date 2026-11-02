"""Une la transcripción de Whisper con la diarización de pyannote por solapamiento temporal.

Entradas (las que genera auto.sh en el directorio de salida):
  - JSON de whisper-cli (-oj): segmentos con "offsets" en milisegundos y "text".
  - TXT de pyannote: líneas "start=0.0s stop=4.2s speaker_SPEAKER_01".

Salida: un .txt con un turno por hablante, por ejemplo:
  [00:00:00 - 00:00:04] SPEAKER_01: Fantino destapó el plan de la casta...

Cada segmento de Whisper se asigna al hablante con el que más se solapa en el
tiempo; los segmentos consecutivos del mismo hablante se fusionan en un turno.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

PATRON_PYANNOTE = re.compile(
    r"start=(?P<start>[\d.]+)s\s+stop=(?P<stop>[\d.]+)s\s+speaker_(?P<speaker>\S+)"
)


@dataclass
class TurnoDiarizacion:
    inicio: float
    fin: float
    hablante: str


@dataclass
class Segmento:
    inicio: float
    fin: float
    texto: str
    hablante: str = ""


def cargar_diarizacion(ruta):
    """Lee el TXT de pyannote y devuelve los turnos ordenados por inicio."""
    turnos = []
    with open(ruta, encoding="utf-8") as f:
        for nro_linea, linea in enumerate(f, start=1):
            linea = linea.strip()
            if not linea:
                continue
            m = PATRON_PYANNOTE.search(linea)
            if not m:
                print(f"Aviso: línea {nro_linea} de diarización ignorada: {linea!r}", file=sys.stderr)
                continue
            turnos.append(
                TurnoDiarizacion(
                    inicio=float(m.group("start")),
                    fin=float(m.group("stop")),
                    hablante=m.group("speaker"),
                )
            )
    if not turnos:
        raise ValueError(f"No se encontraron turnos de diarización en {ruta}")
    return sorted(turnos, key=lambda t: t.inicio)


def timestamp_a_segundos(valor):
    """Convierte 'HH:MM:SS,mmm' (o con '.') a segundos."""
    horas, minutos, resto = valor.replace(".", ",").split(":")
    segundos, milisegundos = resto.split(",")
    return int(horas) * 3600 + int(minutos) * 60 + int(segundos) + int(milisegundos) / 1000.0


def cargar_transcripcion(ruta):
    """Lee el JSON de whisper-cli y devuelve los segmentos en segundos."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)

    segmentos = []
    for item in datos.get("transcription", []):
        if "offsets" in item:
            inicio = item["offsets"]["from"] / 1000.0
            fin = item["offsets"]["to"] / 1000.0
        else:  # respaldo: usar los timestamps de texto
            inicio = timestamp_a_segundos(item["timestamps"]["from"])
            fin = timestamp_a_segundos(item["timestamps"]["to"])
        texto = item.get("text", "").strip()
        if texto:
            segmentos.append(Segmento(inicio=inicio, fin=fin, texto=texto))

    if not segmentos:
        raise ValueError(f"No se encontraron segmentos de transcripción en {ruta}")
    return segmentos


def solapamiento(a_inicio, a_fin, b_inicio, b_fin):
    return max(0.0, min(a_fin, b_fin) - max(a_inicio, b_inicio))


def asignar_hablante(segmento, turnos):
    """Hablante con mayor solapamiento; si no hay solape, el turno más cercano."""
    tiempos = {}
    for turno in turnos:
        if turno.inicio >= segmento.fin:
            break  # los turnos están ordenados: ya no puede haber más solape
        ov = solapamiento(segmento.inicio, segmento.fin, turno.inicio, turno.fin)
        if ov > 0:
            tiempos[turno.hablante] = tiempos.get(turno.hablante, 0.0) + ov

    if tiempos:
        return max(tiempos, key=tiempos.get)

    # Sin solape (huecos de la diarización): usar el turno más cercano al centro.
    centro = (segmento.inicio + segmento.fin) / 2.0

    def distancia(turno):
        if turno.inicio <= centro <= turno.fin:
            return 0.0
        return min(abs(centro - turno.inicio), abs(centro - turno.fin))

    return min(turnos, key=distancia).hablante


def fusionar_turnos(segmentos):
    """Agrupa segmentos consecutivos del mismo hablante en un solo turno."""
    turnos = []
    for seg in segmentos:
        if turnos and turnos[-1].hablante == seg.hablante:
            turnos[-1].fin = seg.fin
            turnos[-1].texto += " " + seg.texto
        else:
            turnos.append(Segmento(seg.inicio, seg.fin, seg.texto, seg.hablante))
    return turnos


def formatear_tiempo(segundos):
    total = max(0, int(round(segundos)))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Merge de la transcripción de Whisper con la diarización de pyannote."
    )
    parser.add_argument("-j", "--json", required=True, help="JSON de whisper-cli (-oj).")
    parser.add_argument("-d", "--diarizacion", required=True, help="TXT de diarización de pyannote.")
    parser.add_argument("-o", "--output", help="Archivo de salida (por defecto: <base>_diarizado.txt).")
    parser.add_argument(
        "--sin-fusionar",
        action="store_true",
        help="Escribe una línea por segmento de Whisper en vez de fusionar turnos.",
    )
    args = parser.parse_args()

    turnos_diar = cargar_diarizacion(args.diarizacion)
    segmentos = cargar_transcripcion(args.json)

    for seg in segmentos:
        seg.hablante = asignar_hablante(seg, turnos_diar)

    resultado = segmentos if args.sin_fusionar else fusionar_turnos(segmentos)

    salida = args.output
    if not salida:
        base = os.path.splitext(args.json)[0]
        salida = base + ("_segmentos.txt" if args.sin_fusionar else "_diarizado.txt")

    with open(salida, "w", encoding="utf-8") as f:
        for turno in resultado:
            f.write(
                f"[{formatear_tiempo(turno.inicio)} - {formatear_tiempo(turno.fin)}] "
                f"{turno.hablante}: {turno.texto}\n"
            )

    hablantes = sorted({seg.hablante for seg in segmentos})
    print(f"✅ {len(segmentos)} segmentos → {len(resultado)} turnos, hablantes: {', '.join(hablantes)}")
    print(f"   Guardado en: {salida}")


if __name__ == "__main__":
    main()
