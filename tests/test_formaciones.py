"""Formaciones de la imagen de alineación y roles por formación (tarea 23)."""

import copy
import glob
import importlib.util
import json

import pytest

from pfb.imagenes.alineacion import ANCHO_M, FORMACIONES, LARGO_M, generar
from pfb.motor.asignacion import EXTREMOS
from pfb.motor.plantillas import RAIZ

spec = importlib.util.spec_from_file_location("armar_plantillas", RAIZ / "scripts" / "armar_plantillas.py")
armar_plantillas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(armar_plantillas)

NUEVAS = ("3-4-3", "3-5-2", "3-4-1-2", "3-4-2-1", "4-1-4-1", "4-3-1-2", "4-4-1-1", "4-5-1", "5-3-2", "5-4-1")


@pytest.fixture(scope="module")
def reglas():
    with open(RAIZ / "data" / "criterio_plantillas.json", encoding="utf-8") as f:
        return json.load(f)["reglas_rol"]


@pytest.fixture(scope="module")
def equipos_reales():
    """Las alineaciones de los partidos reales del Clausura (data/partidos)."""
    equipos = []
    for ruta in sorted(glob.glob(str(RAIZ / "data" / "partidos" / "[0-9]*.json"))):
        with open(ruta, encoding="utf-8") as f:
            equipos += json.load(f)["equipos"]
    return equipos


def forma(formacion):
    return "-".join(map(str, armar_plantillas.lineas(formacion)))


def roles(equipo, reglas):
    coords = [(t["top"], t["left"]) for t in equipo["titulares"]]
    return [r for _, r in armar_plantillas.casillas_por_coordenadas(equipo["formacion"], coords, reglas)]


def test_quince_formaciones_de_11_dentro_de_la_cancha():
    assert len(FORMACIONES) == 15 and all(f in FORMACIONES for f in NUEVAS)
    for nombre, casillas in FORMACIONES.items():
        assert len(casillas) == 11, nombre
        assert all(0 < x < ANCHO_M and 0 < y < LARGO_M for x, y in casillas), nombre
        assert casillas[0] == (34.0, 11.0), nombre                                  # arquero
        assert sum(armar_plantillas.lineas(nombre)) == 10, nombre


def test_cada_linea_de_atras_hacia_adelante(reglas):
    for nombre, casillas in FORMACIONES.items():
        i, alturas = 1, []
        for n in armar_plantillas.lineas(nombre):
            linea = casillas[i:i + n]
            assert [x for x, _ in linea] == sorted(x for x, _ in linea), nombre    # de izquierda a derecha
            alturas.append(sum(y for _, y in linea) / n)
            i += n
        assert alturas == sorted(alturas), nombre


def test_toda_formacion_real_tiene_dibujo(equipos_reales):
    assert {forma(e["formacion"]) for e in equipos_reales} <= set(FORMACIONES)


def test_343_un_delantero_dos_extremos_y_carrileros_laterales(equipos_reales, reglas):
    del_343 = [e for e in equipos_reales if forma(e["formacion"]) == "3-4-3"]
    assert del_343
    for e in del_343:
        r = roles(e, reglas)
        assert r.count("delantero") == 1
        assert r[8] == "volante_extremo_izq" and r[10] == "volante_extremo_der"     # los de afuera del ataque
        assert r[4] == "lateral_izq" and r[7] == "lateral_der"                       # carrileros
        assert sum(x in EXTREMOS for x in r) == 2


def test_ninguna_formacion_real_pasa_de_dos_extremos(equipos_reales, reglas):
    for e in equipos_reales:
        r = roles(e, reglas)
        assert sum(x in EXTREMOS for x in r) <= 2, e["formacion"]
        assert r.count("delantero") in (1, 2), e["formacion"]


def test_los_carrileros_solo_en_el_343(equipos_reales, reglas):
    for e in equipos_reales:
        tamanos = armar_plantillas.lineas(e["formacion"])
        if tamanos[0] == 3 and forma(e["formacion"]) != "3-4-3":
            assert "lateral_izq" not in roles(e, reglas), e["formacion"]


@pytest.mark.parametrize("nombre", NUEVAS)
def test_las_nuevas_se_dibujan(nombre, tmp_path):
    with open(RAIZ / "data" / "ejemplo_alineacion.json", encoding="utf-8") as f:
        partido = json.load(f)
    partido = copy.deepcopy(partido)
    partido["formacion"] = nombre
    ruta = tmp_path / f"{nombre}.png"
    generar(partido, ruta)
    assert ruta.exists() and ruta.stat().st_size > 0
