import json
import random
from collections import Counter
from pathlib import Path

import pytest

from pfb.motor.asignacion import goleadores, linea_de_tiempo
from pfb.motor.eventos import cantidad_tarjetas, minutos_de_gol, minutos_tarjetas, ventanas_de_cambio
from pfb.motor.plantillas import cargar_plantillas

RUTA_PARAMETROS = Path(__file__).resolve().parents[1] / "data" / "parametros_motor.json"
SEMILLAS = range(3_000)


@pytest.fixture(scope="module")
def params():
    with open(RUTA_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def plantillas():
    return list(cargar_plantillas().values())


def entradas(rng, params, plantilla, cargado=False):
    """Goles, tarjetas y ventanas de un equipo con las funciones del motor.
    cargado=True fuerza muchas tarjetas y goles para que haya expulsiones seguido."""
    n_goles = rng.randint(3, 8) if cargado else rng.randint(0, 4)
    casillas = goleadores(rng, params, plantilla, n_goles)
    goles = [(t, m, c) for (t, m), c in zip(minutos_de_gol(rng, n_goles), casillas)]
    if cargado:
        n_rojas, n_amarillas = rng.randint(1, 5), rng.randint(4, 14)
    else:
        n_rojas, _, n_amarillas, _ = cantidad_tarjetas(rng, params)
    rojas, amarillas = minutos_tarjetas(rng, n_rojas, n_amarillas)
    return goles, rojas, amarillas, ventanas_de_cambio(rng, params)


def corridas(params, plantillas):
    """(eventos, entradas) para muchas semillas, normales y cargadas."""
    for semilla in SEMILLAS:
        rng = random.Random(semilla)
        plantilla = plantillas[semilla % len(plantillas)]
        datos = entradas(rng, params, plantilla, cargado=semilla % 2 == 1)
        yield linea_de_tiempo(rng, params, plantilla, *datos), datos, plantilla


def momento(e):
    return (e["tiempo"], e["minuto"])


def ids_del_evento(e):
    if e["tipo"] == "cambio":
        return {e["sale"]["id"], e["entra"]["id"]}
    return {e["jugador"]["id"]}


def test_orden_cronologico(params, plantillas):
    for eventos, _, _ in corridas(params, plantillas):
        momentos = [momento(e) for e in eventos]
        assert momentos == sorted(momentos)


def test_expulsado_no_aparece_despues(params, plantillas):
    hubo_expulsiones = 0
    for eventos, _, _ in corridas(params, plantillas):
        expulsados = set()
        for e in eventos:
            assert not (ids_del_evento(e) & expulsados), e
            if e["tipo"] == "roja":
                expulsados.add(e["jugador"]["id"])
                hubo_expulsiones += 1
    assert hubo_expulsiones > 1_000


def test_expulsado_no_sale_de_cambio(params, plantillas):
    for eventos, _, _ in corridas(params, plantillas):
        expulsadas = set()
        for e in eventos:
            if e["tipo"] == "roja":
                expulsadas.add(e["casilla"])
            if e["tipo"] == "cambio":
                assert e["casilla"] not in expulsadas


def test_casilla_cambia_una_vez_y_maximo_5(params, plantillas):
    for eventos, _, plantilla in corridas(params, plantillas):
        cambios = [e for e in eventos if e["tipo"] == "cambio"]
        assert len(cambios) <= 5
        casillas = [e["casilla"] for e in cambios]
        assert len(casillas) == len(set(casillas))
        suplentes = {c.numero: c.suplente.id for c in plantilla.casillas}
        for e in cambios:
            assert e["entra"]["id"] == suplentes[e["casilla"]]


def test_doble_amarilla_da_roja(params, plantillas):
    dobles = 0
    for eventos, _, _ in corridas(params, plantillas):
        vistas = Counter()
        for i, e in enumerate(eventos):
            if e["tipo"] == "amarilla":
                vistas[e["jugador"]["id"]] += 1
                assert vistas[e["jugador"]["id"]] <= 2
                if vistas[e["jugador"]["id"]] == 2:
                    roja = eventos[i + 1]
                    assert roja["tipo"] == "roja" and roja["doble_amarilla"] is True
                    assert roja["jugador"] == e["jugador"] and momento(roja) == momento(e)
                    dobles += 1
            if e["tipo"] == "roja" and e["doble_amarilla"]:
                assert eventos[i - 1]["tipo"] == "amarilla"
                assert eventos[i - 1]["jugador"] == e["jugador"]
    assert dobles > 100


def terminado(eventos):
    return any(e.get("fin_partido") for e in eventos)


def test_ningun_gol_se_pierde(params, plantillas):
    for eventos, (goles, _, _, _), _ in corridas(params, plantillas):
        if terminado(eventos):
            continue  # lo posterior al corte no cuenta, a propósito
        assert sum(e["tipo"] == "gol" for e in eventos) == len(goles)


def test_tarjetas_completas_sin_corte(params, plantillas):
    for eventos, (_, rojas, amarillas, _), _ in corridas(params, plantillas):
        if terminado(eventos):
            continue
        assert sum(e["tipo"] == "amarilla" for e in eventos) == len(amarillas)
        assert sum(e["tipo"] == "roja" and not e["doble_amarilla"] for e in eventos) == len(rojas)


def test_nunca_mas_de_5_expulsados_y_corte_al_quinto(params, plantillas):
    cortes = 0
    for eventos, _, _ in corridas(params, plantillas):
        rojas = [i for i, e in enumerate(eventos) if e["tipo"] == "roja"]
        assert len(rojas) <= 5
        con_fin = [i for i, e in enumerate(eventos) if e.get("fin_partido")]
        if len(rojas) == 5:
            assert con_fin == [len(eventos) - 1] == [rojas[-1]]
            cortes += 1
        else:
            assert con_fin == []
    assert cortes > 50


def test_gol_del_mismo_minuto_despues_del_corte_no_aparece(params, plantillas):
    plantilla = plantillas[0]
    rojas = [(1, 10), (1, 20), (1, 30), (1, 40), (2, 15)]
    goles = [(2, 15, 10), (2, 30, 9)]
    for semilla in range(200):
        eventos = linea_de_tiempo(random.Random(semilla), params, plantilla, goles, rojas, [], [])
        assert eventos[-1]["tipo"] == "roja" and eventos[-1]["fin_partido"] is True
        assert momento(eventos[-1]) == (2, 15)
        assert not any(e["tipo"] == "gol" for e in eventos)


def test_corte_lee_expulsados_fin_partido(params, plantillas):
    alterados = {**params, "tarjetas": {**params["tarjetas"], "expulsados_fin_partido": 3, "tope_rojas_por_equipo": 5}}
    rojas = [(1, 10), (1, 20), (1, 30), (2, 10), (2, 20)]
    for semilla in range(200):
        eventos = linea_de_tiempo(random.Random(semilla), alterados, plantillas[0], [(2, 40, 10)], rojas, [], [])
        assert [e["tipo"] for e in eventos] == ["roja"] * 3
        assert eventos[-1]["fin_partido"] is True
        assert momento(eventos[-1]) == (1, 30)


def con_se_queda(params, p):
    return {**params, "tarjetas": {**params["tarjetas"], "segunda_amarilla_se_queda": p}}


def solo_amarillas(rng, n):
    """n amarillas en minutos distintos y ordenados, sin rojas, goles ni cambios."""
    return sorted(rng.sample([(t, m) for t in (1, 2) for m in range(46)], n))


def test_segunda_amarilla_se_queda_1_es_como_antes(params, plantillas):
    """Con 1, cada amarilla va a la casilla sorteada como en jTarjetas (salvo la de un expulsado)."""
    alterados = con_se_queda(params, 1)
    dobles = 0
    for semilla in range(500):
        plantilla = plantillas[semilla % len(plantillas)]
        amarillas = solo_amarillas(random.Random(semilla), 12)
        copia = random.Random(semilla)
        sorteadas = iter([copia.randint(1, 11) for _ in amarillas])  # los mismos primeros sorteos
        eventos = linea_de_tiempo(random.Random(semilla), alterados, plantilla, [], [], amarillas, [])
        expulsadas = set()
        for e in eventos:
            if e["tipo"] == "amarilla":
                casilla = next(sorteadas)
                if casilla not in expulsadas:
                    assert e["casilla"] == casilla
            else:
                expulsadas.add(e["casilla"])
                dobles += 1
    assert dobles > 500


def test_segunda_amarilla_se_queda_0_sin_dobles_si_hay_a_quien(params, plantillas):
    alterados = con_se_queda(params, 0)
    for semilla in range(500):
        plantilla = plantillas[semilla % len(plantillas)]
        rng = random.Random(semilla)
        eventos = linea_de_tiempo(rng, alterados, plantilla, [], [], solo_amarillas(rng, rng.randint(1, 16)), [])
        con_amarilla = set()
        for e in eventos:
            if e["tipo"] == "amarilla":
                if e["jugador"]["id"] in con_amarilla:
                    # solo puede repetir si ya no quedaba nadie en cancha sin amarilla
                    assert len(con_amarilla) == 11
                con_amarilla.add(e["jugador"]["id"])
        if len([e for e in eventos if e["tipo"] == "amarilla"]) <= 11:
            assert not any(e["tipo"] == "roja" for e in eventos)


@pytest.mark.parametrize("p", [0, 0.5, 1])
def test_segunda_amarilla_no_cambia_el_total(params, plantillas, p):
    alterados = con_se_queda(params, p)
    for semilla in range(1_000):
        rng = random.Random(semilla)
        plantilla = plantillas[semilla % len(plantillas)]
        goles, rojas, amarillas, ventanas = entradas(rng, alterados, plantilla, cargado=semilla % 2 == 1)
        eventos = linea_de_tiempo(rng, alterados, plantilla, goles, rojas, amarillas, ventanas)
        if terminado(eventos):
            continue
        assert sum(e["tipo"] == "amarilla" for e in eventos) == len(amarillas)


def test_en_el_mismo_minuto_amarilla_antes_que_cambio(params, plantillas):
    plantilla = plantillas[0]
    ventanas = [{"tiempo": 2, "minuto": 20, "jugadores": 2}]
    for semilla in range(500):
        eventos = linea_de_tiempo(random.Random(semilla), params, plantilla,
                                  [(2, 20, 10)], [(2, 20)], [(2, 20)], ventanas)
        tipos = [e["tipo"] for e in eventos]
        assert tipos.index("roja") < tipos.index("amarilla") < tipos.index("gol") < tipos.index("cambio")


def test_arquero_sale_en_2_por_ciento(params, plantillas):
    n = 200_000
    rng = random.Random(7)
    sale = 0
    for i in range(n):
        plantilla = plantillas[i % len(plantillas)]
        arquero = next(c.numero for c in plantilla.casillas if c.rol == "arquero")
        eventos = linea_de_tiempo(rng, params, plantilla, [], [], [], ventanas_de_cambio(rng, params))
        sale += any(e["tipo"] == "cambio" and e["casilla"] == arquero for e in eventos)
    assert 100 * sale / n == pytest.approx(2, abs=0.5)


def test_reproducible(params, plantillas):
    for semilla in range(200):
        plantilla = plantillas[semilla % len(plantillas)]
        a = linea_de_tiempo(random.Random(semilla), params, plantilla,
                            *entradas(random.Random(semilla), params, plantilla, cargado=True))
        b = linea_de_tiempo(random.Random(semilla), params, plantilla,
                            *entradas(random.Random(semilla), params, plantilla, cargado=True))
        assert a == b
