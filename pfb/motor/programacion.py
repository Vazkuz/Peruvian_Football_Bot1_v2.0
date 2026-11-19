"""Sorteos de la imagen de la programación (§5.0d, tarea 26): de qué club es la foto y de qué lado va.

La foto es de un club al azar entre los que ganaron en la fecha anterior; si nadie ganó, o si es la
fecha 1, de cualquiera de los clubes de la temporada. No se repite el club de la foto de la fecha anterior
(Daniel, 19/11/2026), salvo que sea el único candidato (p. ej. el único que ganó). La foto va a la
izquierda con probabilidad params["programacion"]["foto_izquierda"].

Usa su propio generador, sembrado desde la semilla de la temporada y el número de fecha: si la corrida
se repite, sale lo mismo, y no consume números de ningún otro sorteo.
"""

import random


def generador(temporada, fecha):
    return random.Random(f"programacion-{temporada['semilla']}-F{fecha:02d}")


def ganadores(registros, fecha):
    """club_id de los que ganaron en la fecha, con el marcador final (después de la mesa, si la hubo)."""
    salida = []
    for r in registros:
        if r["fecha"] != fecha:
            continue
        local, visita = r["local"], r["visita"]
        if local["goles"] > visita["goles"]:
            salida.append(local["club_id"])
        elif visita["goles"] > local["goles"]:
            salida.append(visita["club_id"])
    return salida


def sortear_foto(temporada, fecha, registros, params):
    """(club_id, lado) de la foto de la programación de la fecha (la que se juega mañana); lado =
    "izquierda" o "derecha"."""
    rng = generador(temporada, fecha)
    lado = "izquierda" if rng.random() < params["programacion"]["foto_izquierda"] else "derecha"
    candidatos = sorted(set(ganadores(registros, fecha - 1) if fecha > 1 else []) or temporada["clubes"])
    if fecha > 1:
        anterior = sortear_foto(temporada, fecha - 1, registros, params)[0]
        candidatos = [c for c in candidatos if c != anterior] or candidatos
    return rng.choice(candidatos), lado
