"""Sorteo de la Fecha FIFA (§13.1): un amistoso de Perú contra una selección al azar.

Después de cada partido, menos el último de la fecha (ahí va la tabla), con probabilidad
params["fecha_fifa"]["probabilidad"] sale una Fecha FIFA, con tope de una por fecha. El rival se sortea
entre las selecciones de data/selecciones.json menos Perú; Perú es local con probabilidad
params["fecha_fifa"]["peru_local"]. El marcador sale de Score como siempre (§3.3 y §3.9), sin racha ni
G5, porque las selecciones no tienen partidos previos.

Usa su propio generador, sembrado desde la semilla del partido: el partido y su votación quedan igual.
"""

import json
import random

from pfb.motor.marcador import sortear_marcador
from pfb.motor.plantillas import RAIZ

RUTA_SELECCIONES = RAIZ / "data" / "selecciones.json"
PERU = "PER"
SIN_HISTORIA = {"ult_res": None, "g5": None}


def cargar_selecciones(ruta=RUTA_SELECCIONES):
    """{código FIFA: {"nombre", "confederacion", "iso"}}."""
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def generador(registro):
    return random.Random(f"fecha-fifa-{registro['semilla']}")


def sortear_fecha_fifa(registro, params, hubo_en_la_fecha, ultimo_de_la_fecha, selecciones=None):
    """Devuelve None o {"local": {"seleccion", "goles", "bonos"}, "visita": {...}}, con Perú en uno de los
    dos lados. registro: el partido recién jugado, después del cual iría la Fecha FIFA."""
    if hubo_en_la_fecha or ultimo_de_la_fecha:
        return None
    p = params["fecha_fifa"]
    rng = generador(registro)
    if rng.random() >= p["probabilidad"]:
        return None
    if selecciones is None:
        selecciones = cargar_selecciones()
    rival = rng.choice(sorted(c for c in selecciones if c != PERU))
    local, visita = (PERU, rival) if rng.random() < p["peru_local"] else (rival, PERU)
    m = sortear_marcador(rng, params, SIN_HISTORIA, SIN_HISTORIA)
    return {
        "local": {"seleccion": local, "goles": m["local"]["goles"], "bonos": m["local"]["bonos"]},
        "visita": {"seleccion": visita, "goles": m["visita"]["goles"], "bonos": m["visita"]["bonos"]},
    }
