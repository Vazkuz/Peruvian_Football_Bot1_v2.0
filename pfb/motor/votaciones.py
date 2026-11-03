"""Sorteo de las votaciones de un partido ya simulado (§13.1).

Dos votaciones excluyentes, con tope de 1 por fecha:
- Sanción: si hubo roja (directa o por doble amarilla), con probabilidad params["votaciones"]["sancion"]
  se vota cuántas fechas se lleva un jugador sorteado entre los expulsados.
- Mesa: si no salió la sanción y el partido tuvo perdedor, con probabilidad
  params["votaciones"]["mesa"] se vota si se lleva el partido a la mesa; la cosa random de "Me da
  risa" se sortea ahí mismo, porque la imagen del post depende de ella.

El sorteo usa su propio generador, sembrado desde la semilla del partido: no consume números del
generador del partido, así que el marcador y los eventos quedan igual que sin votaciones.
"""

import copy
import random

from pfb.imagenes.votacion import elegir_opcion
from pfb.motor.marcador import sortear_marcador

# Marcador que deja cada cosa random de la votación 2 (§13.1): (goles local, goles visita), o None si
# el marcador se mantiene.
MARCADOR_RANDOM = {
    1: (1, 1),    # el presidente de la federación, amañado con ambos
    2: (3, 0),    # goleador de la visita amañando: gana el local 3-0
    3: (0, 3),    # doping del arquero local: gana la visita 3-0
    4: (0, 1),    # la barra de la visita: gana la visita 1-0
    5: None,      # el TAS: se mantiene
    6: (2, 1),    # el Congreso: gana el local 2-1
    7: None,      # aliens: se mantiene
    8: (1, 1),    # FREPAP
    9: (0, 0),    # VAR desconectado
    10: (1, 1),   # la FPF perdió el acta
    11: (2, 2),   # huaico
    12: (0, 3),   # árbitro hincha del local: gana la visita 3-0
}
GANADORES_MESA = ("no_procede", "random", "repetir")


def generador(registro):
    return random.Random(f"votacion-{registro['semilla']}")


def expulsados(registro, casillas_bloqueadas=frozenset()):
    """Los jugadores con roja (directa o por doble amarilla), en el orden de los eventos y sin
    repetir. casillas_bloqueadas: {(club_id, casilla)} que ya tienen a alguien sancionado; esos no
    se pueden elegir."""
    vistos = set()
    salida = []
    for e in registro["eventos"]:
        if e["tipo"] != "roja":
            continue
        clave = (e["club_id"], e["jugador"]["id"])
        if clave in vistos or (e["club_id"], e["casilla"]) in casillas_bloqueadas:
            continue
        vistos.add(clave)
        salida.append({"club_id": e["club_id"], "casilla": e["casilla"], "jugador": dict(e["jugador"])})
    return salida


def hubo_perdedor(registro):
    return registro["local"]["goles"] != registro["visita"]["goles"]


def sortear_votacion(registro, params, hubo_votacion_en_la_fecha, casillas_bloqueadas=frozenset(),
                     elegir=elegir_opcion):
    """Devuelve None, {"tipo": "sancion", "club_id", "casilla", "jugador": {"id", "nombre"}} o
    {"tipo": "mesa", "opcion": n} (con "equipo": club_id si la opción es la 10)."""
    if hubo_votacion_en_la_fecha:
        return None
    p = params["votaciones"]
    rng = generador(registro)

    candidatos = expulsados(registro, casillas_bloqueadas)
    if candidatos and rng.random() < p["sancion"]:
        return {"tipo": "sancion", **rng.choice(candidatos)}

    if hubo_perdedor(registro) and rng.random() < p["mesa"]:
        votacion = {"tipo": "mesa", "opcion": elegir(rng)}
        if votacion["opcion"] == 10:  # su texto nombra a uno de los dos equipos al azar
            votacion["equipo"] = rng.choice([registro["local"]["club_id"], registro["visita"]["club_id"]])
        return votacion

    return None


def aplicar_mesa(registro, ganador, params, estado_local=None, estado_visita=None):
    """Devuelve una copia del registro con el resultado de la votación 2 aplicado (§13.1).
    ganador: "no_procede" (Like), "random" (Me da risa), "repetir" (Me enoja) o None (empate de
    votos: el marcador se mantiene). Al repetir solo cuenta el marcador nuevo, sorteado con Score y
    los estados de los equipos antes del partido; los eventos quedan como estaban.
    El marcador original queda en registro["mesa"]["original"]."""
    if ganador is not None and ganador not in GANADORES_MESA:
        raise ValueError(f"ganador desconocido: {ganador!r}")
    nuevo = copy.deepcopy(registro)
    local, visita = nuevo["local"]["goles"], nuevo["visita"]["goles"]
    nuevo["mesa"] = {"ganador": ganador, "original": {"local": local, "visita": visita}}

    if ganador == "random":
        marcador = MARCADOR_RANDOM[registro["votacion"]["opcion"]]
        if marcador is not None:
            local, visita = marcador
    elif ganador == "repetir":
        sin = {"ult_res": None, "g5": None}
        rng = random.Random(f"repeticion-{registro['semilla']}")
        m = sortear_marcador(rng, params, estado_local or sin, estado_visita or sin)
        local, visita = m["local"]["goles"], m["visita"]["goles"]
        nuevo["mesa"]["bonos"] = {"local": m["local"]["bonos"], "visita": m["visita"]["bonos"]}

    nuevo["local"]["goles"], nuevo["visita"]["goles"] = local, visita
    return nuevo
