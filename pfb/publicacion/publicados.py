"""Registro de publicados: data/temporadas/<temporada_id>/publicados.json (§7.2).

Aparte del registro del partido. Una entrada por publicación, con clave "F07-P3" (partido) o
"tabla-F07" (tabla de la fecha 7):
    {"tipo": "partido" | "tabla", "post_id": ..., "pagina": "prueba" | "real", "page_id": ...,
     "fecha_hora": "2026-10-08T17:52:51-05:00"}
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from pfb.motor.temporada import CARPETA_TEMPORADAS, _escribir_json, _leer_json, carpeta_temporada

ZONA = ZoneInfo("America/Lima")


class MezclaDePaginas(Exception):
    """La temporada ya tiene publicaciones en otra página."""


def clave_tabla(fecha):
    return f"tabla-F{fecha:02d}"


def ruta_publicados(temporada_id, base=CARPETA_TEMPORADAS):
    return carpeta_temporada(temporada_id, base) / "publicados.json"


def cargar_publicados(temporada_id, base=CARPETA_TEMPORADAS):
    ruta = ruta_publicados(temporada_id, base)
    return _leer_json(ruta) if ruta.exists() else {}


def comprobar_pagina(publicados, page_id):
    """Aborta si alguna publicación de la temporada fue en otra página."""
    otras = {e["page_id"] for e in publicados.values()} - {page_id}
    if otras:
        paginas = sorted({e["pagina"] for e in publicados.values() if e["page_id"] != page_id})
        raise MezclaDePaginas(f"la temporada ya tiene publicaciones en otra página ({', '.join(paginas)})")


def marcar(temporada_id, clave, tipo, post_id, pagina, page_id, base=CARPETA_TEMPORADAS, ahora=None):
    publicados = cargar_publicados(temporada_id, base)
    publicados[clave] = {
        "tipo": tipo,
        "post_id": post_id,
        "pagina": pagina,
        "page_id": page_id,
        "fecha_hora": (ahora or datetime.now(ZONA)).isoformat(timespec="seconds"),
    }
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados
