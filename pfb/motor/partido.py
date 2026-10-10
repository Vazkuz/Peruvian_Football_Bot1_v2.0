"""Simula un partido completo y arma su registro (§3.10), en el orden de PFB_Liga1.py del v1."""

import json
import random

from pfb.motor.asignacion import goleadores, linea_de_tiempo, penales
from pfb.motor.eventos import cantidad_tarjetas, minutos_de_gol, minutos_tarjetas, ventanas_de_cambio
from pfb.motor.marcador import sortear_marcador
from pfb.motor.plantillas import RAIZ

RUTA_PARAMETROS = RAIZ / "data" / "parametros_motor.json"


def cargar_parametros():
    with open(RUTA_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


def _prioridad(e):
    """Orden dentro de un mismo minuto: roja, amarilla, gol, cambio.
    La roja por doble amarilla va pegada a su amarilla."""
    if e["tipo"] == "roja":
        return 1 if e["doble_amarilla"] else 0
    return {"amarilla": 1, "gol": 2, "cambio": 3}[e["tipo"]]


def _momento(e):
    return (e["tiempo"], e["minuto"])


def _alineacion(plantilla):
    return {
        "formacion": plantilla.formacion,
        "casillas": [
            {
                "casilla": c.numero,
                "rol": c.rol,
                "titular": {"id": c.titular.id, "nombre": c.titular.nombre},
                "suplente": {"id": c.suplente.id, "nombre": c.suplente.nombre},
            }
            for c in plantilla.casillas
        ],
    }


def simular_partido(params, local, visita, estado_local, estado_visita, semilla=None, partido_id=None, fecha=None):
    """local / visita: Plantilla. estado_*: {"ult_res": 1 | 0 | -1 | None, "g5": int | None}.
    Devuelve el registro del partido, serializable con json.dumps."""
    if semilla is None:
        semilla = random.SystemRandom().randrange(2**32)
    rng = random.Random(semilla)

    # a. Marcador
    marcador = sortear_marcador(rng, params, estado_local, estado_visita)
    n_local, n_visita = marcador["local"]["goles"], marcador["visita"]["goles"]

    # b. Ventanas de cambio
    ventanas_local = ventanas_de_cambio(rng, params)
    ventanas_visita = ventanas_de_cambio(rng, params)

    # c. Goleadores
    casillas_local = goleadores(rng, params, local, n_local)
    casillas_visita = goleadores(rng, params, visita, n_visita)

    # d. Minutos de gol, emparejados en orden con las casillas
    goles_local = [(t, m, c) for (t, m), c in zip(minutos_de_gol(rng, n_local), casillas_local)]
    goles_visita = [(t, m, c) for (t, m), c in zip(minutos_de_gol(rng, n_visita), casillas_visita)]

    # e. Cantidad de tarjetas
    rojas_l, rojas_v, amarillas_l, amarillas_v = cantidad_tarjetas(rng, params)

    # f. Minutos de tarjetas
    t_rojas_local, t_amarillas_local = minutos_tarjetas(rng, rojas_l, amarillas_l)
    t_rojas_visita, t_amarillas_visita = minutos_tarjetas(rng, rojas_v, amarillas_v)

    # g. Línea de tiempo de cada equipo
    linea_local = linea_de_tiempo(rng, params, local, goles_local, t_rojas_local, t_amarillas_local, ventanas_local)
    linea_visita = linea_de_tiempo(rng, params, visita, goles_visita, t_rojas_visita, t_amarillas_visita,
                                   ventanas_visita)

    # Unión de los dos equipos: en un mismo minuto, por tipo y local antes que visita.
    # El sort es estable, así que dentro de cada equipo se respeta el orden de su línea.
    eventos = [{"tipo": e["tipo"], "club_id": local.club_id, **e} for e in linea_local]
    eventos += [{"tipo": e["tipo"], "club_id": visita.club_id, **e} for e in linea_visita]
    orden_club = {local.club_id: 0, visita.club_id: 1}
    eventos.sort(key=lambda e: (_momento(e), _prioridad(e), orden_club[e["club_id"]]))

    # Corte por expulsiones: del otro equipo, en el minuto del corte solo quedan sus rojas directas.
    fin = None
    corte = next((e for e in eventos if e.get("fin_partido")), None)
    if corte is not None:
        fin = {"tiempo": corte["tiempo"], "minuto": corte["minuto"], "club_id": corte["club_id"]}
        eventos = [
            e for e in eventos
            if _momento(e) < _momento(corte)
            or (_momento(e) == _momento(corte)
                and (e["club_id"] == corte["club_id"] or (e["tipo"] == "roja" and not e["doble_amarilla"])))
        ]

    # Penales, después del corte: local y después visita.
    for club_id in (local.club_id, visita.club_id):
        goles = [e for e in eventos if e["tipo"] == "gol" and e["club_id"] == club_id]
        for e, penal in zip(goles, penales(rng, params, len(goles))):
            e["penal"] = penal

    def lado(plantilla, datos):
        goles = sum(e["tipo"] == "gol" and e["club_id"] == plantilla.club_id for e in eventos)
        return {"club_id": plantilla.club_id, "goles": goles, "bonos": datos["bonos"]}

    return {
        "partido_id": partido_id,
        "fecha": fecha,
        "semilla": semilla,
        "estado": "jugado",
        "local": lado(local, marcador["local"]),
        "visita": lado(visita, marcador["visita"]),
        "alineaciones": {local.club_id: _alineacion(local), visita.club_id: _alineacion(visita)},
        "eventos": eventos,
        "fin": fin,
    }
