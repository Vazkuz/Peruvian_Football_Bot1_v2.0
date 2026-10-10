import random
from collections import Counter

import pytest

import pfb.motor.temporada as temporada
from pfb.motor.partido import cargar_parametros
from pfb.motor.plantillas import cargar_plantillas
from pfb.motor.temporada import (cargar_registros, crear_fixture, estado_equipo, jugar_siguiente,
                                 nueva_temporada, tabla)


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


@pytest.fixture(scope="module")
def clubes():
    return sorted(cargar_plantillas())


def reg(fecha, numero, local, goles_local, visita, goles_visita, estado="jugado"):
    """Registro mínimo armado a mano."""
    return {"partido_id": f"F{fecha:02d}-P{numero}", "fecha": fecha, "estado": estado,
            "local": {"club_id": local, "goles": goles_local}, "visita": {"club_id": visita, "goles": goles_visita}}


# --- fixture ---

def test_fixture_34_fechas_de_9(clubes):
    fixture = crear_fixture(random.Random(1), clubes)
    assert len(fixture) == 34
    assert all(len(fecha) == 9 for fecha in fixture)
    for fecha in fixture:
        equipos = [c for partido in fecha for c in partido]
        assert sorted(equipos) == clubes


def test_fixture_cada_par_dos_veces_una_de_local(clubes):
    fixture = crear_fixture(random.Random(2), clubes)
    pares = Counter(partido for fecha in fixture for partido in fecha)
    assert len(pares) == 18 * 17
    assert set(pares.values()) == {1}
    # la vuelta es la ida con local y visita invertidos
    for ida, vuelta in zip(fixture[:17], fixture[17:]):
        assert vuelta == [(v, l) for l, v in ida]


def test_fixture_localia_pareja(clubes):
    for semilla in range(50):
        fixture = crear_fixture(random.Random(semilla), clubes)
        ida = Counter(local for fecha in fixture[:17] for local, _ in fecha)
        total = Counter(local for fecha in fixture for local, _ in fecha)
        assert all(ida[c] in (8, 9) for c in clubes)
        assert all(total[c] == 17 for c in clubes)


def test_fixture_reproducible(clubes):
    assert crear_fixture(random.Random(3), clubes) == crear_fixture(random.Random(3), clubes)
    assert crear_fixture(random.Random(3), clubes) != crear_fixture(random.Random(4), clubes)


# --- estado_equipo ---

def test_estado_sin_partidos(params):
    assert estado_equipo([], "A", params) == {"ult_res": None, "g5": None}
    assert estado_equipo([reg(1, 1, "B", 1, "C", 0)], "A", params) == {"ult_res": None, "g5": None}


def test_estado_con_menos_de_5(params):
    registros = [reg(1, 1, "A", 2, "B", 0), reg(2, 1, "C", 3, "A", 1)]
    assert estado_equipo(registros, "A", params) == {"ult_res": -1, "g5": 3}
    assert estado_equipo(registros, "B", params) == {"ult_res": -1, "g5": 0}
    assert estado_equipo(registros, "C", params) == {"ult_res": 1, "g5": 3}


def test_estado_con_mas_de_5_y_desordenados(params):
    # A hace 1, 2, 3, 4, 5, 6 goles en las fechas 1 a 6; los últimos 5 suman 20
    registros = [reg(f, 1, "A", f, "B", f if f == 6 else 0) for f in range(1, 7)]
    random.Random(0).shuffle(registros)
    assert estado_equipo(registros, "A", params) == {"ult_res": 0, "g5": 20}


def test_estado_ignora_lo_que_no_es_jugado(params):
    registros = [reg(1, 1, "A", 2, "B", 0), reg(2, 1, "A", 0, "B", 3, estado="mesa")]
    assert estado_equipo(registros, "A", params) == {"ult_res": 1, "g5": 2}


# --- tabla ---

def orden(filas):
    return [f["club_id"] for f in filas]


def test_tabla_desempate_por_dg():
    registros = [reg(1, 1, "A", 3, "C", 0), reg(1, 2, "B", 1, "D", 0)]
    filas = tabla(registros, nombres={"A": "Zeta", "B": "Alfa", "C": "C", "D": "D"})
    assert orden(filas)[:2] == ["A", "B"]
    assert [f["pos"] for f in filas] == [1, 2, 3, 4]


def test_tabla_desempate_por_gf():
    registros = [reg(1, 1, "A", 3, "C", 2), reg(1, 2, "B", 1, "D", 0)]
    filas = tabla(registros, nombres={"A": "Zeta", "B": "Alfa", "C": "C", "D": "D"})
    assert orden(filas)[:2] == ["A", "B"]
    assert filas[0]["dg"] == filas[1]["dg"] == 1


def test_tabla_desempate_entre_ellos():
    # A y B quedan con 3 pts, DG 0 y GF 1; A le ganó a B. C le gana 5-0 a D para quedar aparte.
    registros = [reg(1, 1, "A", 1, "B", 0), reg(2, 1, "C", 1, "A", 0), reg(3, 1, "B", 1, "C", 0),
                 reg(4, 1, "C", 5, "D", 0)]
    filas = tabla(registros, nombres={"A": "Zeta", "B": "Alfa", "C": "Ce", "D": "De"})
    a, b = (next(f for f in filas if f["club_id"] == c) for c in "AB")
    assert (a["pts"], a["dg"], a["gf"]) == (b["pts"], b["dg"], b["gf"]) == (3, 0, 1)
    assert orden(filas) == ["C", "A", "B", "D"]


def test_tabla_desempate_alfabetico():
    registros = [reg(1, 1, "A", 1, "B", 1)]
    filas = tabla(registros, nombres={"A": "Beta", "B": "Ápice"})
    assert orden(filas) == ["B", "A"]


def test_tabla_columnas_y_puntos():
    registros = [reg(1, 1, "A", 2, "B", 1), reg(2, 1, "B", 0, "A", 0)]
    filas = tabla(registros, nombres={"A": "A", "B": "B"})
    assert filas[0] == {"pos": 1, "club_id": "A", "club": "A", "pj": 2, "pg": 1, "pe": 1, "pp": 0,
                        "gf": 2, "gc": 1, "dg": 1, "pts": 4}


# --- jugar_siguiente ---

def test_jugar_siguiente_no_repite_ni_salta(params, tmp_path):
    t = nueva_temporada("prueba", semilla=1, base=tmp_path)
    a = jugar_siguiente("prueba", params, base=tmp_path)
    b = jugar_siguiente("prueba", params, base=tmp_path)
    assert (a["partido_id"], b["partido_id"]) == ("F01-P1", "F01-P2")
    assert [a["local"]["club_id"], a["visita"]["club_id"]] == t["fixture"][0][0]
    assert [r["partido_id"] for r in cargar_registros("prueba", base=tmp_path)] == ["F01-P1", "F01-P2"]


def test_archivo_a_medias_no_aparece(params, tmp_path, monkeypatch):
    nueva_temporada("prueba", semilla=1, base=tmp_path)

    def cortar(*_):
        raise OSError("corrida cortada")

    monkeypatch.setattr(temporada.os, "replace", cortar)
    with pytest.raises(OSError):
        jugar_siguiente("prueba", params, base=tmp_path)
    partidos = tmp_path / "prueba" / "partidos"
    assert not (partidos / "F01-P1.json").exists()
    assert (partidos / "F01-P1.json.tmp").exists()
    assert cargar_registros("prueba", base=tmp_path) == []

    monkeypatch.undo()
    r = jugar_siguiente("prueba", params, base=tmp_path)
    assert r["partido_id"] == "F01-P1"
    assert (partidos / "F01-P1.json").exists() and not (partidos / "F01-P1.json.tmp").exists()


def test_temporada_completa(params, clubes, tmp_path):
    nueva_temporada("completa", semilla=2026, base=tmp_path)
    jugados = 0
    while jugar_siguiente("completa", params, base=tmp_path) is not None:
        jugados += 1
    assert jugados == 306
    assert jugar_siguiente("completa", params, base=tmp_path) is None
    filas = tabla(cargar_registros("completa", base=tmp_path), club_ids=clubes)
    assert len(filas) == 18
    assert all(f["pj"] == 34 for f in filas)
    assert sum(f["gf"] for f in filas) == sum(f["gc"] for f in filas)
