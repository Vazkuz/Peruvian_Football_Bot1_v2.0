"""Sorteo de la Fecha FIFA (§13.1)."""

import json
import random
from collections import Counter

import pytest

from pfb.motor.fecha_fifa import PERU, cargar_selecciones, generador, sortear_fecha_fifa
from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import cargar_plantilla
from pfb.motor.temporada import cargar_registros, jugar_siguiente, nueva_temporada


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


@pytest.fixture(scope="module")
def selecciones():
    return cargar_selecciones()


def con_prob(params, probabilidad, peru_local=0.5):
    return {**params, "votaciones": {"sancion": 0.0, "mesa": 0.0},
            "fecha_fifa": {"probabilidad": probabilidad, "peru_local": peru_local}}


def reg(semilla=1):
    return {"partido_id": "F01-P1", "fecha": 1, "semilla": semilla}


def test_parametros_de_13_1(params):
    assert params["fecha_fifa"] == {"probabilidad": 0.03, "peru_local": 0.5}


def test_selecciones(selecciones):
    assert len(selecciones) == 211 and PERU in selecciones
    assert selecciones["PER"]["nombre"] == "Perú"


def test_tope_y_ultimo_de_la_fecha(params, selecciones):
    p = con_prob(params, 1.0)
    assert sortear_fecha_fifa(reg(), p, True, False, selecciones) is None
    assert sortear_fecha_fifa(reg(), p, False, True, selecciones) is None
    assert sortear_fecha_fifa(reg(), p, False, False, selecciones) is not None


def test_peru_siempre_juega_y_el_rival_es_otra_seleccion(params, selecciones):
    p = con_prob(params, 1.0)
    for semilla in range(300):
        f = sortear_fecha_fifa(reg(semilla), p, False, False, selecciones)
        lados = (f["local"]["seleccion"], f["visita"]["seleccion"])
        assert lados.count(PERU) == 1
        rival = lados[1] if lados[0] == PERU else lados[0]
        assert rival in selecciones and rival != PERU
        assert f["local"]["goles"] >= 0 and f["visita"]["goles"] >= 0


def test_peru_local_la_mitad_de_las_veces(params, selecciones):
    p = con_prob(params, 1.0)
    n = 4000
    locales = sum(sortear_fecha_fifa(reg(s), p, False, False, selecciones)["local"]["seleccion"] == PERU
                  for s in range(n))
    assert abs(locales / n - 0.5) < 0.03


def test_probabilidad_aproximada(params, selecciones):
    n = 20000
    salen = sum(sortear_fecha_fifa(reg(s), params, False, False, selecciones) is not None for s in range(n))
    assert abs(salen / n - 0.03) < 0.005


def test_rivales_variados(params, selecciones):
    p = con_prob(params, 1.0)
    rivales = Counter()
    for s in range(3000):
        f = sortear_fecha_fifa(reg(s), p, False, False, selecciones)
        rivales[f["visita"]["seleccion"] if f["local"]["seleccion"] == PERU else f["local"]["seleccion"]] += 1
    assert len(rivales) > 190


def test_sin_racha_ni_g5_y_con_localia(params, selecciones):
    p = con_prob(params, 1.0)
    for s in range(200):
        f = sortear_fecha_fifa(reg(s), p, False, False, selecciones)
        assert f["local"]["bonos"]["racha"] == f["local"]["bonos"]["g5"] == 0
        assert f["visita"]["bonos"] == {"racha": 0, "g5": 0}
        assert "localia" in f["local"]["bonos"]


def test_mismo_registro_mismo_resultado_y_generador_propio(params, selecciones):
    p = con_prob(params, 1.0)
    assert sortear_fecha_fifa(reg(7), p, False, False, selecciones) == sortear_fecha_fifa(reg(7), p, False, False,
                                                                                         selecciones)
    assert generador(reg(7)).random() != random.Random(7).random()


def test_temporada_una_por_fecha_y_nunca_tras_el_ultimo(params, tmp_path):
    p = con_prob(params, 1.0)
    nueva_temporada("f", semilla=2, base=tmp_path)
    for _ in range(18):
        jugar_siguiente("f", p, base=tmp_path)
    por_fecha = {}
    for r in cargar_registros("f", base=tmp_path):
        if r["fecha_fifa"]:
            por_fecha.setdefault(r["fecha"], []).append(r["partido_id"])
    assert por_fecha == {1: ["F01-P1"], 2: ["F02-P1"]}


def test_temporada_sin_fecha_fifa_guarda_null(params, tmp_path):
    nueva_temporada("g", semilla=2, base=tmp_path)
    r = jugar_siguiente("g", con_prob(params, 0.0), base=tmp_path)
    assert r["fecha_fifa"] is None


def test_la_fecha_fifa_no_toca_el_partido(params, selecciones):
    # el partido sale de su propia semilla; el sorteo no lo modifica ni consume su generador
    local, visita = cargar_plantilla("184"), cargar_plantilla("6593")
    sin = {"ult_res": None, "g5": None}
    for semilla in range(30):
        registro = simular_partido(params, local, visita, sin, sin, semilla=semilla)
        antes = json.dumps(registro, sort_keys=True)
        assert sortear_fecha_fifa(registro, con_prob(params, 1.0), False, False, selecciones) is not None
        assert json.dumps(registro, sort_keys=True) == antes
        assert antes == json.dumps(simular_partido(params, local, visita, sin, sin, semilla=semilla), sort_keys=True)
