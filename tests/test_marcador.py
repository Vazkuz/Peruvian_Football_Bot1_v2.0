import json
import random
from collections import Counter
from pathlib import Path

import pytest

from pfb.motor.marcador import sortear_marcador

RUTA_PARAMETROS = Path(__file__).resolve().parents[1] / "data" / "parametros_motor.json"


@pytest.fixture(scope="module")
def params():
    with open(RUTA_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


def equipo(ult_res=None, g5=None):
    return {"ult_res": ult_res, "g5": g5}


def test_misma_semilla_mismo_resultado(params):
    for semilla in range(50):
        a = sortear_marcador(random.Random(semilla), params, equipo(1, 8), equipo(-1, 3))
        b = sortear_marcador(random.Random(semilla), params, equipo(1, 8), equipo(-1, 3))
        assert a == b


def test_semillas_distintas_resultados_variados(params):
    marcadores = {
        (r["local"]["goles"], r["visita"]["goles"])
        for r in (sortear_marcador(random.Random(s), params, equipo(0, 5), equipo(0, 5)) for s in range(200))
    }
    assert len(marcadores) > 5


def test_ningun_marcador_negativo(params):
    rng = random.Random(1)
    for _ in range(20_000):
        r = sortear_marcador(rng, params, equipo(-1, 0), equipo(-1, 0))
        assert r["local"]["goles"] >= 0
        assert r["visita"]["goles"] >= 0


def test_fecha_1_sin_racha_ni_g5(params):
    rng = random.Random(2)
    for _ in range(5_000):
        r = sortear_marcador(rng, params, equipo(), equipo())
        assert r["local"]["bonos"]["racha"] == 0
        assert r["local"]["bonos"]["g5"] == 0
        assert r["visita"]["bonos"] == {"racha": 0, "g5": 0}


def test_g5_34_nunca_cero_y_g5_0_siempre_cero(params):
    rng = random.Random(3)
    for _ in range(20_000):
        r = sortear_marcador(rng, params, equipo(0, 34), equipo(0, 0))
        assert r["local"]["bonos"]["g5"] != 0
        assert r["visita"]["bonos"]["g5"] == 0


def test_frecuencias_localia_y_g5(params):
    n = 200_000
    rng = random.Random(4)
    localia, g5 = Counter(), Counter()
    for _ in range(n):
        r = sortear_marcador(rng, params, equipo(0, 10), equipo(0, 0))
        localia[r["local"]["bonos"]["localia"]] += 1
        g5[r["local"]["bonos"]["g5"]] += 1

    def pct(c, k):
        return 100 * c[k] / n

    assert pct(localia, 2) == pytest.approx(8.5, abs=0.5)
    assert pct(localia, 1) == pytest.approx(24, abs=0.5)
    assert pct(localia, 0) == pytest.approx(67.5, abs=0.5)
    assert pct(g5, 2) == pytest.approx(10, abs=0.5)
    assert pct(g5, 1) == pytest.approx(20, abs=0.5)
    assert pct(g5, 0) == pytest.approx(70, abs=0.5)
