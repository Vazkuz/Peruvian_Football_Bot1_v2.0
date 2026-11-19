"""Imagen de la programación de la fecha siguiente (§5.0d)."""

import json

import pytest
from PIL import Image

from pfb.imagenes.programacion import (FRANJA_TAM, FRANJAS, NOMBRE_ANCHO_MAX, NOMBRES_PROPIOS, PANEL_TAM, FUENTE,
                                       generar_programacion, horas, nombres_programacion, tam_nombre)
from pfb.motor.temporada import RAIZ, cargar_nombres

CLUBES = sorted(json.load(open(RAIZ / "data" / "escudos.json", encoding="utf-8")))
PARTIDOS = [(CLUBES[2 * i], CLUBES[2 * i + 1]) for i in range(9)]


def test_las_18_franjas_existen_y_miden_lo_mismo():
    for club_id in CLUBES:
        with Image.open(FRANJAS / f"{club_id}.png") as img:
            assert img.size == FRANJA_TAM, club_id


def test_horas_desde_las_9():
    assert horas() == ["9:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]


def test_nombres_propios_solo_en_esta_imagen():
    nombres = nombres_programacion()
    assert nombres["114625"] == "D. Moquegua" and nombres["35588"] == "ADT Tarma"
    assert nombres["21170"] == "UTC Cajamarca" and nombres["47107"] == "Comerciantes U."
    assert cargar_nombres()["114625"] == "Deportivo Moquegua"   # la tabla y los posts no cambian
    assert set(NOMBRES_PROPIOS) <= set(CLUBES)


def test_todos_los_nombres_entran():
    from PIL import ImageFont
    for nombre in nombres_programacion().values():
        texto = nombre.upper()
        assert ImageFont.truetype(str(FUENTE), tam_nombre(texto)).getlength(texto) <= NOMBRE_ANCHO_MAX, nombre


def test_tamano_y_lado_de_la_foto(tmp_path):
    franja = Image.open(FRANJAS / f"{CLUBES[0]}.png").convert("RGB")
    izq = Image.open(generar_programacion(2, PARTIDOS, CLUBES[0], "izquierda", tmp_path / "i.png")).convert("RGB")
    der = Image.open(generar_programacion(2, PARTIDOS, CLUBES[0], "derecha", tmp_path / "d.png")).convert("RGB")
    ancho = FRANJA_TAM[0] + PANEL_TAM[0]
    assert izq.size == der.size == (ancho, PANEL_TAM[1])
    assert izq.crop((0, 0, FRANJA_TAM[0], FRANJA_TAM[1])).tobytes() == franja.tobytes()
    assert der.crop((PANEL_TAM[0], 0, ancho, FRANJA_TAM[1])).tobytes() == franja.tobytes()


def test_falla_con_lado_o_partidos_raros(tmp_path):
    with pytest.raises(ValueError):
        generar_programacion(2, PARTIDOS, CLUBES[0], "centro", tmp_path / "x.png")
    with pytest.raises(ValueError):
        generar_programacion(2, PARTIDOS[:8], CLUBES[0], "izquierda", tmp_path / "x.png")
