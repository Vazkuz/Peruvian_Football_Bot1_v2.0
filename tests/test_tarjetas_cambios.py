import json
import random
from collections import Counter
from pathlib import Path

import pytest

from pfb.motor.eventos import cantidad_tarjetas, minutos_tarjetas, ventanas_de_cambio

RUTA_PARAMETROS = Path(__file__).resolve().parents[1] / "data" / "parametros_motor.json"
N = 200_000


@pytest.fixture(scope="module")
def params():
    with open(RUTA_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


# --- cantidad_tarjetas ---

def test_ningun_equipo_pasa_de_5_rojas(params):
    rng = random.Random(1)
    for _ in range(N):
        rojas_local, rojas_visita, amarillas_local, amarillas_visita = cantidad_tarjetas(rng, params)
        assert 0 <= rojas_local <= 5
        assert 0 <= rojas_visita <= 5
        assert amarillas_local >= 0 and amarillas_visita >= 0


def test_amarillas_media_4_4_y_nunca_negativas(params):
    rng = random.Random(5)
    totales = []
    for _ in range(N):
        _, _, amarillas_local, amarillas_visita = cantidad_tarjetas(rng, params)
        assert amarillas_local >= 0 and amarillas_visita >= 0
        totales.append(amarillas_local + amarillas_visita)
    assert max(totales) <= params["tarjetas"]["tope_sorteo"]
    # el piso en 0 sube la media apenas (~0.01) sobre 4.4
    assert sum(totales) / N == pytest.approx(4.4, abs=0.05)


def test_cantidad_tarjetas_reproducible(params):
    for semilla in range(50):
        assert cantidad_tarjetas(random.Random(semilla), params) == cantidad_tarjetas(random.Random(semilla), params)


# --- minutos_tarjetas ---

def test_minutos_tarjetas_cantidades_y_rango():
    rng = random.Random(2)
    for _ in range(20_000):
        n_rojas, n_amarillas = rng.randint(0, 5), rng.randint(0, 12)
        rojas, amarillas = minutos_tarjetas(rng, n_rojas, n_amarillas)
        assert len(rojas) == n_rojas
        assert len(amarillas) == n_amarillas
        for tiempo, minuto in rojas + amarillas:
            assert tiempo in (1, 2)
            assert 0 <= minuto <= 45


# --- ventanas_de_cambio ---

def test_ventanas_tope_minutos_distintos_y_entretiempo(params):
    rng = random.Random(3)
    vio_entretiempo = False
    for _ in range(50_000):
        ventanas = ventanas_de_cambio(rng, params)
        assert 1 <= sum(v["jugadores"] for v in ventanas) <= 5
        momentos = [(v["tiempo"], v["minuto"]) for v in ventanas]
        assert len(set(momentos)) == len(momentos)
        assert momentos == sorted(momentos)
        for v in ventanas:
            assert v["jugadores"] in (1, 2)
            assert 0 <= v["minuto"] <= 45
        vio_entretiempo |= (2, 0) in momentos
    assert vio_entretiempo


def test_distribucion_del_total_de_cambios(params):
    rng = random.Random(4)
    totales = Counter(sum(v["jugadores"] for v in ventanas_de_cambio(rng, params)) for _ in range(N))
    # por enumeración exhaustiva con los parámetros del 04/10/2026 (ventanas 90/8/2, jugadores 55/45,
    # entretiempo 25 %, tope 5)
    esperado = {5: 61.52, 4: 26.11, 3: 9.55, 2: 2.14, 1: 0.68}
    assert set(totales) == set(esperado)
    for total, pct in esperado.items():
        assert 100 * totales[total] / N == pytest.approx(pct, abs=0.5)
    media = sum(total * n for total, n in totales.items()) / N
    assert media == pytest.approx(4.457, abs=0.02)
