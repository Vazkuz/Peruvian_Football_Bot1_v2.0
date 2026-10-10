import json
import random

import pytest

from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import cargar_plantillas

SIN_HISTORIAL = {"ult_res": None, "g5": None}
PRIORIDAD = {"amarilla": 1, "gol": 2, "cambio": 3}


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


@pytest.fixture(scope="module")
def plantillas():
    return cargar_plantillas()


def momento(e):
    return (e["tiempo"], e["minuto"])


def estado_al_azar(rng):
    return {"ult_res": rng.choice([None, -1, 0, 1]), "g5": rng.choice([None, 0, 3, 8, 15])}


def partido_al_azar(params, plantillas, semilla):
    rng = random.Random(semilla)
    local, visita = rng.sample(sorted(plantillas), 2)
    return simular_partido(params, plantillas[local], plantillas[visita],
                           estado_al_azar(rng), estado_al_azar(rng), semilla=semilla)


def goles_por_club(registro, club_id):
    return sum(e["tipo"] == "gol" and e["club_id"] == club_id for e in registro["eventos"])


def test_misma_semilla_mismo_registro(params, plantillas):
    for semilla in range(100):
        a = partido_al_azar(params, plantillas, semilla)
        b = partido_al_azar(params, plantillas, semilla)
        assert json.dumps(a) == json.dumps(b)


def test_semillas_distintas_registros_distintos(params, plantillas):
    local, visita = plantillas["184"], plantillas["6593"]
    registros = {json.dumps(simular_partido(params, local, visita, SIN_HISTORIAL, SIN_HISTORIAL, semilla=s))
                 for s in range(100)}
    assert len(registros) == 100


def test_semilla_generada_reproduce_el_partido(params, plantillas):
    local, visita = plantillas["184"], plantillas["6593"]
    for _ in range(50):
        a = simular_partido(params, local, visita, SIN_HISTORIAL, SIN_HISTORIAL)
        b = simular_partido(params, local, visita, SIN_HISTORIAL, SIN_HISTORIAL, semilla=a["semilla"])
        assert json.dumps(a) == json.dumps(b)


def test_goles_coinciden_con_eventos(params, plantillas):
    for semilla in range(500):
        r = partido_al_azar(params, plantillas, semilla)
        for lado in ("local", "visita"):
            assert r[lado]["goles"] == goles_por_club(r, r[lado]["club_id"])


def test_corte_por_expulsiones(params, plantillas):
    alterados = {**params, "tarjetas": {**params["tarjetas"], "expulsados_fin_partido": 1}}
    cortes = 0
    for semilla in range(3_000):
        r = partido_al_azar(alterados, plantillas, semilla)
        eventos = r["eventos"]
        if r["fin"] is None:
            assert not any(e.get("fin_partido") for e in eventos)
            continue
        cortes += 1
        fin = (r["fin"]["tiempo"], r["fin"]["minuto"])
        assert all(momento(e) <= fin for e in eventos)
        # en el minuto del corte, el otro equipo solo conserva rojas directas
        for e in eventos:
            if momento(e) == fin and e["club_id"] != r["fin"]["club_id"]:
                assert e["tipo"] == "roja" and not e["doble_amarilla"]
        assert any(e.get("fin_partido") and e["club_id"] == r["fin"]["club_id"] and momento(e) == fin
                   for e in eventos)
        for lado in ("local", "visita"):
            assert r[lado]["goles"] == goles_por_club(r, r[lado]["club_id"])
    assert cortes > 300


def test_2000_partidos_sin_error_y_serializables(params, plantillas):
    for semilla in range(2_000):
        r = partido_al_azar(params, plantillas, semilla)
        assert json.loads(json.dumps(r)) == r
        ids = {r["local"]["club_id"], r["visita"]["club_id"]}
        orden = {r["local"]["club_id"]: 0, r["visita"]["club_id"]: 1}
        claves = []
        for e in r["eventos"]:
            assert e["club_id"] in ids
            if e["tipo"] == "gol":
                assert isinstance(e["penal"], bool)
            prioridad = (1 if e["doble_amarilla"] else 0) if e["tipo"] == "roja" else PRIORIDAD[e["tipo"]]
            claves.append((momento(e), prioridad))
        assert claves == sorted(claves)
