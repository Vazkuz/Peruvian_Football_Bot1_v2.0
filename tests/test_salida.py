import copy
import json
import random
from pathlib import Path

import pytest

from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import RAIZ, cargar_plantillas
from pfb.motor.salida import alineacion_desde_registro, minuto_imagen, ver_partido

SIN_HISTORIAL = {"ult_res": None, "g5": None}
CLAVES_JUGADOR = {"nombre", "goles", "tarjeta", "cambio"}
CLAVES_CAMBIO = {"entra", "minuto", "goles", "tarjeta"}


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


@pytest.fixture(scope="module")
def plantillas():
    return cargar_plantillas()


@pytest.fixture(scope="module")
def contrato():
    with open(RAIZ / "data" / "ejemplo_alineacion.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def base(params, plantillas):
    """Un registro real de Alianza (184) contra Universitario (6593), para alterar sus eventos."""
    return simular_partido(params, plantillas["184"], plantillas["6593"], SIN_HISTORIAL, SIN_HISTORIAL, semilla=1)


def con_eventos(base, eventos):
    r = copy.deepcopy(base)
    r["eventos"] = eventos
    return r


def jugador(base, club_id, casilla, puesto="titular"):
    return dict(base["alineaciones"][club_id]["casillas"][casilla - 1][puesto])


def partidos(params, plantillas, n):
    for semilla in range(n):
        rng = random.Random(semilla)
        local, visita = rng.sample(sorted(plantillas), 2)
        yield simular_partido(params, plantillas[local], plantillas[visita], SIN_HISTORIAL, SIN_HISTORIAL,
                              semilla=semilla)


def test_claves_del_contrato_y_11_jugadores(params, plantillas, contrato):
    for r in partidos(params, plantillas, 300):
        for lado in ("local", "visita"):
            datos = alineacion_desde_registro(r, r[lado]["club_id"])
            assert set(datos) == set(contrato)
            assert set(datos["color"]) <= set(contrato["color"]) and "base" in datos["color"]
            assert len(datos["jugadores"]) == 11
            for j in datos["jugadores"]:
                assert "nombre" in j and set(j) <= CLAVES_JUGADOR
                if "cambio" in j:
                    assert {"entra", "minuto"} <= set(j["cambio"]) <= CLAVES_CAMBIO


def test_lleva_el_club_id(base):
    for club_id in ("184", "6593"):
        assert alineacion_desde_registro(base, club_id)["club_id"] == club_id


def test_goles_del_json_igual_al_registro(params, plantillas):
    for r in partidos(params, plantillas, 300):
        for lado in ("local", "visita"):
            datos = alineacion_desde_registro(r, r[lado]["club_id"])
            total = sum(j.get("goles", 0) + j.get("cambio", {}).get("goles", 0) for j in datos["jugadores"])
            assert total == r[lado]["goles"]


def test_minuto_absoluto(base):
    assert minuto_imagen(2, 0) == 45
    assert minuto_imagen(2, 23) == 68
    assert minuto_imagen(1, 30) == 30
    eventos = []
    for casilla, (tiempo, minuto) in zip((3, 4, 5), ((2, 0), (2, 23), (1, 30))):
        eventos.append({"tipo": "cambio", "club_id": "184", "tiempo": tiempo, "minuto": minuto, "casilla": casilla,
                        "ventana": 1, "sale": jugador(base, "184", casilla),
                        "entra": jugador(base, "184", casilla, "suplente")})
    datos = alineacion_desde_registro(con_eventos(base, eventos), "184")
    assert [datos["jugadores"][i]["cambio"]["minuto"] for i in (2, 3, 4)] == [45, 68, 30]


def test_doble_amarilla_y_roja_directa(base):
    doble, directa = jugador(base, "184", 6), jugador(base, "184", 7)
    eventos = [
        {"tipo": "amarilla", "club_id": "184", "tiempo": 1, "minuto": 10, "casilla": 6, "jugador": doble},
        {"tipo": "amarilla", "club_id": "184", "tiempo": 2, "minuto": 5, "casilla": 6, "jugador": doble},
        {"tipo": "roja", "club_id": "184", "tiempo": 2, "minuto": 5, "casilla": 6, "jugador": doble,
         "doble_amarilla": True},
        {"tipo": "amarilla", "club_id": "184", "tiempo": 2, "minuto": 8, "casilla": 7, "jugador": directa},
        {"tipo": "roja", "club_id": "184", "tiempo": 2, "minuto": 20, "casilla": 7, "jugador": directa,
         "doble_amarilla": False},
    ]
    datos = alineacion_desde_registro(con_eventos(base, eventos), "184")
    assert datos["jugadores"][5]["tarjeta"] == "doble_amarilla"
    assert datos["jugadores"][6]["tarjeta"] == "roja"


def test_suplente_lleva_sus_eventos_dentro_de_cambio(base):
    sale, entra = jugador(base, "184", 10), jugador(base, "184", 10, "suplente")
    eventos = [
        {"tipo": "gol", "club_id": "184", "tiempo": 1, "minuto": 20, "casilla": 10, "jugador": sale, "penal": False},
        {"tipo": "cambio", "club_id": "184", "tiempo": 2, "minuto": 10, "casilla": 10, "ventana": 1,
         "sale": sale, "entra": entra},
        {"tipo": "amarilla", "club_id": "184", "tiempo": 2, "minuto": 15, "casilla": 10, "jugador": entra},
        {"tipo": "gol", "club_id": "184", "tiempo": 2, "minuto": 30, "casilla": 10, "jugador": entra, "penal": False},
        {"tipo": "gol", "club_id": "184", "tiempo": 2, "minuto": 40, "casilla": 10, "jugador": entra, "penal": True},
    ]
    j = alineacion_desde_registro(con_eventos(base, eventos), "184")["jugadores"][9]
    assert j["goles"] == 1 and "tarjeta" not in j
    assert j["cambio"] == {"entra": "P. Guerrero", "minuto": 55, "goles": 2, "tarjeta": "amarilla"}


def test_3_partidos_generan_los_png(plantillas, tmp_path):
    rng = random.Random(99)
    for i in range(3):
        local, visita = rng.sample(sorted(plantillas), 2)
        carpeta = tmp_path / f"partido_{i}"
        ver_partido(local, visita, carpeta, semilla=i)
        for club_id in (local, visita):
            png = carpeta / f"alineacion_{club_id}.png"
            assert png.stat().st_size > 0
            assert (carpeta / f"alineacion_{club_id}.json").exists()
        assert (carpeta / "registro.json").exists()
