import json
import random
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from pfb.motor.asignacion import ErrorAsignacion, goleadores, penales, probabilidades_goleador
from pfb.motor.eventos import minutos_de_gol
from pfb.motor.plantillas import cargar_plantillas

RUTA_PARAMETROS = Path(__file__).resolve().parents[1] / "data" / "parametros_motor.json"
N = 200_000


@pytest.fixture(scope="module")
def params():
    with open(RUTA_PARAMETROS, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def plantillas():
    return cargar_plantillas()


def con_roles(plantilla, cambios):
    """Copia de la plantilla con otros roles en algunas casillas ({numero: rol})."""
    casillas = tuple(replace(c, rol=cambios.get(c.numero, c.rol)) for c in plantilla.casillas)
    return replace(plantilla, casillas=casillas)


# --- minutos_de_gol ---

def test_minutos_con_cero_goles():
    assert minutos_de_gol(random.Random(0), 0) == []


def test_minutos_sin_repetidos_y_cantidad_correcta():
    rng = random.Random(1)
    for _ in range(20_000):
        n = rng.randint(0, 12)
        minutos = minutos_de_gol(rng, n)
        assert len(minutos) == n
        assert len(set(minutos)) == n
        assert all(t in (1, 2) and m >= 0 for t, m in minutos)


def test_minutos_reproducibles():
    for semilla in range(50):
        assert minutos_de_gol(random.Random(semilla), 6) == minutos_de_gol(random.Random(semilla), 6)


# --- goleadores ---

def test_probabilidades_suman_1_en_las_18(params, plantillas):
    assert len(plantillas) == 18
    for p in plantillas.values():
        assert sum(probabilidades_goleador(params, p).values()) == pytest.approx(1)


def test_probabilidades_4_4_2(params, plantillas):
    p = plantillas["2729"]
    assert p.formacion == "4-4-2"
    prob = probabilidades_goleador(params, p)
    for c in p.casillas:
        esperado = {"delantero": 20, "arquero": 0.91}.get(c.rol, 7.39)
        assert 100 * prob[c.numero] == pytest.approx(esperado, abs=0.005)


def test_probabilidades_4_2_3_1(params, plantillas):
    p = plantillas["114625"]
    assert p.formacion == "4-2-3-1"
    prob = probabilidades_goleador(params, p)
    esperados = {"delantero": 30, "arquero": 0.91, "volante_extremo_izq": 11.57, "volante_extremo_der": 11.57}
    for c in p.casillas:
        assert 100 * prob[c.numero] == pytest.approx(esperados.get(c.rol, 6.57), abs=0.005)


@pytest.mark.parametrize("club_id", ["2729", "114625"])
def test_frecuencias_goleador(params, plantillas, club_id):
    p = plantillas[club_id]
    prob = probabilidades_goleador(params, p)
    conteo = Counter(goleadores(random.Random(5), params, p, N))
    for numero, esperado in prob.items():
        assert 100 * conteo[numero] / N == pytest.approx(100 * esperado, abs=0.5)


def test_un_delantero_sin_extremos_va_al_mediapunta(params, plantillas):
    p = plantillas["114625"]
    extremos = [c.numero for c in p.casillas if c.rol.startswith("volante_extremo")]
    sin_extremos = con_roles(p, {n: "volante_central" for n in extremos})
    prob = probabilidades_goleador(params, sin_extremos)
    mediapunta = next(c.numero for c in p.casillas if c.rol == "mediapunta")
    assert 100 * prob[mediapunta] == pytest.approx(16.57, abs=0.005)
    assert sum(prob.values()) == pytest.approx(1)


def test_un_delantero_y_un_solo_extremo_se_lleva_el_extra(params, plantillas):
    p = plantillas["114625"]
    derecho = next(c.numero for c in p.casillas if c.rol == "volante_extremo_der")
    izquierdo = next(c.numero for c in p.casillas if c.rol == "volante_extremo_izq")
    un_extremo = con_roles(p, {derecho: "volante_central"})
    prob = probabilidades_goleador(params, un_extremo)

    g = params["goleador"]
    campo = [c.numero for c in un_extremo.casillas if c.rol not in ("delantero", "arquero")]
    fijo = g["delantero_si_es_1"] + 2 * g["extremo_extra_si_es_1"] + g["arquero"] / g["arquero_divisor"]
    resto = (1 - fijo) / len(campo)
    mediapunta = next(c.numero for c in p.casillas if c.rol == "mediapunta")

    assert prob[izquierdo] == pytest.approx(2 * g["extremo_extra_si_es_1"] + resto)
    assert 100 * prob[izquierdo] == pytest.approx(16.57, abs=0.005)
    assert prob[mediapunta] == pytest.approx(resto)
    assert prob[derecho] == pytest.approx(resto)
    assert sum(prob.values()) == pytest.approx(1)


@pytest.mark.parametrize("delanteros", [0, 3])
def test_cero_o_tres_delanteros_dan_error(params, plantillas, delanteros):
    p = plantillas["2729"]
    actuales = [c.numero for c in p.casillas if c.rol == "delantero"]
    if delanteros == 0:
        cambios = {n: "mediapunta" for n in actuales}
    else:
        otro = next(c.numero for c in p.casillas if c.rol == "volante_central" or c.rol == "volante_defensivo")
        cambios = {otro: "delantero"}
    with pytest.raises(ErrorAsignacion, match=f"{delanteros} delanteros"):
        goleadores(random.Random(0), params, con_roles(p, cambios), 1)


# --- penales ---

def test_frecuencia_de_penales(params):
    resultado = penales(random.Random(6), params, N)
    assert len(resultado) == N
    assert 100 * sum(resultado) / N == pytest.approx(10, abs=0.5)
