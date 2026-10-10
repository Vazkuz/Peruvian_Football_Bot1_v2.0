"""Registro de publicados: data/temporadas/<temporada_id>/publicados.json (§7.2).

Aparte del registro del partido. Una entrada por publicación, con clave "F07-P3" (partido) o
"tabla-F07" (tabla de la fecha 7):
    {"tipo": "partido" | "tabla", "post_id": ..., "pagina": "prueba" | "real", "page_id": ...,
     "fecha_hora": "2026-10-08T17:52:51-05:00", "comentario_id": ... | null, "ig_media_id": ... | null}

La entrada se escribe apenas sale el post de Facebook, con comentario_id e ig_media_id null, y se
completa en orden: Instagram, después el comentario. Una entrada sin el campo comentario_id o sin el
campo ig_media_id es de antes de esa parte y esa parte cuenta como hecha.
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


def falta(publicados, clave):
    """La primera parte que falta publicar, en orden: "post", "instagram", "comentario"; None si
    está completa."""
    entrada = publicados.get(clave)
    if entrada is None or not entrada.get("post_id"):
        return "post"
    if "ig_media_id" in entrada and not entrada["ig_media_id"]:
        return "instagram"
    if "comentario_id" in entrada and not entrada["comentario_id"]:
        return "comentario"
    return None


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
        "comentario_id": None,
        "ig_media_id": None,
    }
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados


def marcar_comentario(temporada_id, clave, comentario_id, base=CARPETA_TEMPORADAS):
    publicados = cargar_publicados(temporada_id, base)
    publicados[clave]["comentario_id"] = comentario_id
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados


def marcar_instagram(temporada_id, clave, ig_media_id, base=CARPETA_TEMPORADAS):
    publicados = cargar_publicados(temporada_id, base)
    publicados[clave]["ig_media_id"] = ig_media_id
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados
