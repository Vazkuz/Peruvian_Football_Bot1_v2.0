"""Del registro de un partido al JSON de la imagen de alineación (contrato: data/ejemplo_alineacion.json).

Para ver un partido:
    python -m pfb.motor.salida --local <club_id> --visita <club_id> [--semilla N] [--fecha N] --dir <carpeta>
"""

import argparse
import json
from pathlib import Path

from pfb.imagenes.alineacion import forma_base, generar
from pfb.imagenes.marcador import generar_marcador
from pfb.imagenes.nombres import corto
from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import RAIZ, cargar_plantilla

RUTA_COLORES = RAIZ / "data" / "colores_clubes.json"
SIN_HISTORIAL = {"ult_res": None, "g5": None}


def cargar_colores():
    with open(RUTA_COLORES, encoding="utf-8") as f:
        return json.load(f)


def minuto_imagen(tiempo, minuto):
    """En la imagen el minuto es absoluto: el 2T suma 45 (la ventana de entretiempo, 2T 0', sale 45)."""
    return minuto if tiempo == 1 else minuto + 45


def _tipo_tarjeta(eventos, jugador_id):
    """La tarjeta más grave del jugador: roja > doble_amarilla > amarilla, o None."""
    tipos = set()
    for e in eventos:
        if e["tipo"] in ("amarilla", "roja") and e["jugador"]["id"] == jugador_id:
            tipos.add("doble_amarilla" if e["tipo"] == "roja" and e["doble_amarilla"] else e["tipo"])
    for t in ("roja", "doble_amarilla", "amarilla"):
        if t in tipos:
            return t
    return None


def _goles(eventos, jugador_id):
    return sum(e["tipo"] == "gol" and e["jugador"]["id"] == jugador_id for e in eventos)


def _con_eventos(destino, eventos, jugador_id):
    goles = _goles(eventos, jugador_id)
    if goles:
        destino["goles"] = goles
    tarjeta = _tipo_tarjeta(eventos, jugador_id)
    if tarjeta:
        destino["tarjeta"] = tarjeta
    return destino


def alineacion_desde_registro(registro, club_id, colores=None):
    colores = colores or cargar_colores()
    eventos = [e for e in registro["eventos"] if e["club_id"] == club_id]
    cambios = {e["casilla"]: e for e in eventos if e["tipo"] == "cambio"}

    jugadores = []
    alineacion = registro["alineaciones"][club_id]
    for c in sorted(alineacion["casillas"], key=lambda c: c["casilla"]):
        titular = c["titular"]
        j = _con_eventos({"nombre": corto(titular["nombre"])}, eventos, titular["id"])
        cambio = cambios.get(c["casilla"])
        if cambio:
            entra = cambio["entra"]
            j["cambio"] = _con_eventos(
                {"entra": corto(entra["nombre"]), "minuto": minuto_imagen(cambio["tiempo"], cambio["minuto"])},
                eventos, entra["id"])
        jugadores.append(j)

    color = colores[club_id]
    return {
        "club": color["club"],
        "club_id": club_id,
        "color": {k: color[k] for k in ("base", "segundo", "estilo") if k in color},
        "formacion": forma_base(alineacion["formacion"]),
        "jugadores": jugadores,
    }


def ver_partido(local_id, visita_id, carpeta, semilla=None, fecha=None):
    """Simula el partido (sin historial) y escribe el registro, los JSON y los PNG en carpeta."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    registro = simular_partido(cargar_parametros(), cargar_plantilla(local_id), cargar_plantilla(visita_id),
                               SIN_HISTORIAL, SIN_HISTORIAL, semilla=semilla, fecha=fecha)
    with open(carpeta / "registro.json", "w", encoding="utf-8") as f:
        json.dump(registro, f, ensure_ascii=False, indent=2)
    colores = cargar_colores()
    for club_id in (local_id, visita_id):
        datos = alineacion_desde_registro(registro, club_id, colores)
        with open(carpeta / f"alineacion_{club_id}.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        generar(datos, carpeta / f"alineacion_{club_id}.png")
    generar_marcador(registro, carpeta / "marcador.png")
    return registro


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simula un partido y genera las imágenes de alineación.")
    parser.add_argument("--local", required=True, help="club_id del local")
    parser.add_argument("--visita", required=True, help="club_id de la visita")
    parser.add_argument("--semilla", type=int)
    parser.add_argument("--fecha", type=int)
    parser.add_argument("--dir", required=True, help="carpeta de salida")
    args = parser.parse_args()
    registro = ver_partido(args.local, args.visita, args.dir, semilla=args.semilla, fecha=args.fecha)
    print(f"semilla: {registro['semilla']}")
