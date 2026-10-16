"""Imagen de la votacion 2 ("¿Se lleva el partido a la mesa?").

Las 12 imagenes ya estan armadas en assets/votacion_2/TAS/votacion_opcion_<n>.png (una por
cada cosa random). El bot solo sortea la opcion y usa la imagen que le corresponde; no compone
nada. Si cambia una foto, las imagenes se rearman con scripts/armar_votacion_2.py.
"""

import random

from pfb.imagenes.alineacion import RAIZ

CARPETA_IMAGENES = RAIZ / "assets" / "votacion_2" / "TAS"

OPCIONES = range(1, 13)  # las 12 cosas random de la votacion 2


def ruta_imagen(n):
    """Imagen lista de la opcion n, o None si no esta."""
    ruta = CARPETA_IMAGENES / f"votacion_opcion_{n}.png"
    return ruta if ruta.exists() else None


def opciones_disponibles():
    """Las opciones que tienen su imagen lista."""
    return [n for n in OPCIONES if ruta_imagen(n) is not None]


def elegir_opcion(rng=None, disponibles=None):
    """Sortea una opcion entre las disponibles (por defecto, las que tienen imagen)."""
    rng = rng or random.Random()
    disponibles = opciones_disponibles() if disponibles is None else list(disponibles)
    if not disponibles:
        raise ValueError("no hay ninguna opcion disponible para la votacion 2")
    return rng.choice(disponibles)


def imagen_votacion_2(opcion):
    """Ruta de la imagen de la votacion 2 para la opcion dada."""
    ruta = ruta_imagen(opcion)
    if ruta is None:
        raise FileNotFoundError(f"falta votacion_opcion_{opcion}.png en {CARPETA_IMAGENES}")
    return ruta
