from dataclasses import replace

import pytest

from pfb.motor.plantillas import ErrorPlantilla, cargar_plantillas, validar


@pytest.fixture(scope="module")
def plantillas():
    return cargar_plantillas()


def test_carga_las_18(plantillas):
    assert len(plantillas) == 18
    for club_id, p in plantillas.items():
        assert p.club_id == club_id
        assert len(p.casillas) == 11


def test_todas_pasan_la_validacion(plantillas):
    for p in plantillas.values():
        validar(p)


def _con_casilla(plantilla, indice, **cambios):
    casillas = list(plantilla.casillas)
    casillas[indice] = replace(casillas[indice], **cambios)
    return replace(plantilla, casillas=tuple(casillas))


def test_jugador_repetido_dispara_error(plantillas):
    p = plantillas["184"]
    alterada = _con_casilla(p, 1, suplente=p.casillas[2].titular)
    with pytest.raises(ErrorPlantilla, match="repetido"):
        validar(alterada)


def test_casilla_1_no_arquero_dispara_error(plantillas):
    alterada = _con_casilla(plantillas["184"], 0, rol="central")
    with pytest.raises(ErrorPlantilla, match="no arquero"):
        validar(alterada)


def test_rol_desconocido_dispara_error(plantillas):
    alterada = _con_casilla(plantillas["184"], 5, rol="libero")
    with pytest.raises(ErrorPlantilla, match="rol desconocido"):
        validar(alterada)


def test_numeracion_incorrecta_dispara_error(plantillas):
    p = plantillas["184"]
    alterada = replace(p, casillas=p.casillas[:10])
    with pytest.raises(ErrorPlantilla, match="1 a 11"):
        validar(alterada)
