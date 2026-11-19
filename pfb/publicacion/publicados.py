"""Registro de publicados: data/temporadas/<temporada_id>/publicados.json (§7.2).

Aparte del registro del partido. Una entrada por publicación, con clave "F07-P3" (partido),
"votacion-F07-P3" (votación de ese partido, §13.1), "fifa-F07-P3" (Fecha FIFA que salió después de ese
partido, §13.1), "tabla-F07" (tabla de la fecha 7) o "programacion-F08" (programación de la fecha 8, que
sale la noche anterior; tarea 26):
    {"tipo": "partido" | "votacion" | "fifa" | "tabla" | "programacion", "post_id": ..., "pagina": "prueba" | "real",
     "page_id": ..., "fecha_hora": "2026-10-08T17:52:51-05:00", "comentario_id": ... | null,
     "ig_media_id": ... | null}
La votación lleva además "ig_comentarios": [id | null, ...], un comentario de Instagram por opción.
Anuncio del resultado de una votación (§13.1): va en el post que sale después de resolverla (partido o
tabla). Ese post lleva "anuncio": {"de": "votacion-F07-P3", "fb_id": id | null, "ig_id": id | null}
y la votación lleva "anuncio_en": la clave de ese post. Las dos marcas se escriben juntas.

La entrada se escribe apenas sale el post de Facebook, con comentario_id, ig_media_id y los
ig_comentarios en null, y se completa en orden: Instagram, los comentarios de Instagram (solo la
votación), el anuncio (Facebook y después Instagram, si lleva), después el comentario de Facebook. Una entrada sin el campo comentario_id o sin el campo
ig_media_id es de antes de esa parte y esa parte cuenta como hecha.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from pfb.motor.temporada import CARPETA_TEMPORADAS, _escribir_json, _leer_json, carpeta_temporada

ZONA = ZoneInfo("America/Lima")


class MezclaDePaginas(Exception):
    """La temporada ya tiene publicaciones en otra página."""


def clave_tabla(fecha):
    return f"tabla-F{fecha:02d}"


def clave_votacion(partido_id):
    return f"votacion-{partido_id}"


def clave_fifa(partido_id):
    return f"fifa-{partido_id}"


def clave_programacion(fecha):
    """Programación de la fecha (la que se juega al día siguiente de publicarla; tarea 26)."""
    return f"programacion-F{fecha:02d}"


def ruta_publicados(temporada_id, base=CARPETA_TEMPORADAS):
    return carpeta_temporada(temporada_id, base) / "publicados.json"


def cargar_publicados(temporada_id, base=CARPETA_TEMPORADAS):
    ruta = ruta_publicados(temporada_id, base)
    return _leer_json(ruta) if ruta.exists() else {}


def falta(publicados, clave):
    """La primera parte que falta publicar, en orden: "post", "instagram", "comentarios_ig" (solo la
    votación), "anuncio" (solo si lleva), "comentario"; None si está completa."""
    entrada = publicados.get(clave)
    if entrada is None or not entrada.get("post_id"):
        return "post"
    if "ig_media_id" in entrada and not entrada["ig_media_id"]:
        return "instagram"
    if None in entrada.get("ig_comentarios", []):
        return "comentarios_ig"
    anuncio = entrada.get("anuncio")
    if anuncio and (anuncio["fb_id"] is None or anuncio["ig_id"] is None):
        return "anuncio"
    if "comentario_id" in entrada and not entrada["comentario_id"]:
        return "comentario"
    return None


def comprobar_pagina(publicados, page_id):
    """Aborta si alguna publicación de la temporada fue en otra página."""
    otras = {e["page_id"] for e in publicados.values()} - {page_id}
    if otras:
        paginas = sorted({e["pagina"] for e in publicados.values() if e["page_id"] != page_id})
        raise MezclaDePaginas(f"la temporada ya tiene publicaciones en otra página ({', '.join(paginas)})")


def marcar(temporada_id, clave, tipo, post_id, pagina, page_id, base=CARPETA_TEMPORADAS, ahora=None,
           ig_comentarios=0, anuncio_de=None):
    """ig_comentarios: cuántos comentarios de Instagram lleva (las opciones de la votación).
    anuncio_de: la clave de la votación cuyo resultado se anuncia en este post; queda marcada con
    "anuncio_en" en la misma escritura."""
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
    if ig_comentarios:
        publicados[clave]["ig_comentarios"] = [None] * ig_comentarios
    if anuncio_de:
        publicados[clave]["anuncio"] = {"de": anuncio_de, "fb_id": None, "ig_id": None}
        publicados[anuncio_de]["anuncio_en"] = clave
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


def marcar_ig_comentario(temporada_id, clave, n, comentario_id, base=CARPETA_TEMPORADAS):
    """Guarda el id del comentario de Instagram n (desde 0)."""
    publicados = cargar_publicados(temporada_id, base)
    publicados[clave]["ig_comentarios"][n] = comentario_id
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados


def marcar_anuncio(temporada_id, clave, campo, comentario_id, base=CARPETA_TEMPORADAS):
    """Guarda el id del comentario del anuncio: campo = "fb_id" o "ig_id"."""
    publicados = cargar_publicados(temporada_id, base)
    publicados[clave]["anuncio"][campo] = comentario_id
    _escribir_json(ruta_publicados(temporada_id, base), publicados)
    return publicados
