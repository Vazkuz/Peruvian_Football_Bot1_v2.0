"""Carga y valida las plantillas de data/plantillas/<club_id>.json."""

import json
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_PLANTILLAS = RAIZ / "data" / "plantillas"

# Los roles que asigna casillas_por_coordenadas() en scripts/armar_plantillas.py.
ROLES = {
    "arquero",
    "lateral_izq",
    "lateral_der",
    "central",
    "volante_defensivo",
    "volante_central",
    "mediapunta",
    "volante_extremo_izq",
    "volante_extremo_der",
    "delantero",
}


class ErrorPlantilla(ValueError):
    pass


@dataclass(frozen=True)
class Jugador:
    id: str
    nombre: str
    rol: str


@dataclass(frozen=True)
class Casilla:
    numero: int
    rol: str
    titular: Jugador
    suplente: Jugador


@dataclass(frozen=True)
class Plantilla:
    club_id: str
    club_nombre: str
    formacion: str
    casillas: tuple


def validar(plantilla):
    """Lanza ErrorPlantilla si la plantilla no cumple las reglas."""
    club = f"plantilla {plantilla.club_id} ({plantilla.club_nombre})"

    numeros = [c.numero for c in plantilla.casillas]
    if numeros != list(range(1, 12)):
        raise ErrorPlantilla(f"{club}: las casillas deben ser 1 a 11 en orden, vinieron {numeros}")

    if plantilla.casillas[0].rol != "arquero":
        raise ErrorPlantilla(f"{club}: la casilla 1 es {plantilla.casillas[0].rol!r}, no arquero")

    vistos = {}
    for c in plantilla.casillas:
        if c.rol not in ROLES:
            raise ErrorPlantilla(f"{club}: casilla {c.numero} con rol desconocido {c.rol!r}")
        for puesto, j in (("titular", c.titular), ("suplente", c.suplente)):
            if j.rol not in ROLES:
                raise ErrorPlantilla(
                    f"{club}: {puesto} de la casilla {c.numero} ({j.nombre}) con rol desconocido {j.rol!r}")
            if j.id in vistos:
                raise ErrorPlantilla(
                    f"{club}: {j.nombre} ({j.id}) está repetido: {vistos[j.id]} y {puesto} de la casilla {c.numero}")
            vistos[j.id] = f"{puesto} de la casilla {c.numero}"


def _jugador(datos):
    return Jugador(id=str(datos["id"]), nombre=datos["nombre"], rol=datos["rol"])


def plantilla_desde_dict(datos):
    """Arma la Plantilla desde el JSON ya leído y la valida."""
    try:
        plantilla = Plantilla(
            club_id=str(datos["club_id"]),
            club_nombre=datos["club_nombre"],
            formacion=datos["formacion"],
            casillas=tuple(
                Casilla(
                    numero=c["casilla"],
                    rol=c["rol"],
                    titular=_jugador(c["titular"]),
                    suplente=_jugador(c["suplente"]),
                )
                for c in datos["casillas"]
            ),
        )
    except KeyError as e:
        raise ErrorPlantilla(f"plantilla {datos.get('club_id', '?')}: falta el campo {e}") from None
    validar(plantilla)
    return plantilla


def cargar_plantilla(club_id):
    ruta = CARPETA_PLANTILLAS / f"{club_id}.json"
    with open(ruta, encoding="utf-8") as f:
        return plantilla_desde_dict(json.load(f))


def cargar_plantillas():
    """Devuelve {club_id: Plantilla} con todos los archivos de data/plantillas/."""
    return {ruta.stem: cargar_plantilla(ruta.stem) for ruta in sorted(CARPETA_PLANTILLAS.glob("*.json"))}
