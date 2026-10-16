import random

import pytest

import pfb.imagenes.votacion as votacion
from pfb.imagenes.votacion import elegir_opcion, imagen_votacion_2, opciones_disponibles


def test_estan_las_12_imagenes():
    assert opciones_disponibles() == list(range(1, 13))


def test_imagen_de_cada_opcion():
    for n in range(1, 13):
        assert imagen_votacion_2(n) == votacion.CARPETA_IMAGENES / f"votacion_opcion_{n}.png"


def test_solo_sortea_entre_las_disponibles():
    rng = random.Random(1)
    assert {elegir_opcion(rng, [3, 7]) for _ in range(50)} == {3, 7}


def test_por_defecto_sortea_entre_las_que_tienen_imagen():
    assert elegir_opcion(random.Random(1)) in opciones_disponibles()


def test_sin_disponibles_falla():
    with pytest.raises(ValueError):
        elegir_opcion(random.Random(1), [])


def test_opcion_sin_imagen_falla():
    with pytest.raises(FileNotFoundError):
        imagen_votacion_2(99)
