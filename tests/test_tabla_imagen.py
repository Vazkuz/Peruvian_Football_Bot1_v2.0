import hashlib
import json

import pytest
from PIL import Image

import pfb.imagenes.tabla as tabla_imagen
from pfb.imagenes.tabla import BASE, generar_tabla, texto_dg
from pfb.motor.temporada import cargar_nombres

NOMBRES_LARGOS = ["Universidad Técnica de Cajamarca Fútbol Club Oficial", "Alianza Lima"]


def filas_a_mano():
    filas = []
    for i in range(18):
        nombre = NOMBRES_LARGOS[i] if i < len(NOMBRES_LARGOS) else f"Club {i + 1}"
        dg = 20 - 3 * i
        filas.append({"pos": i + 1, "club_id": str(1000 + i), "club": nombre, "pj": 34, "pg": 0, "pe": 0,
                      "pp": 0, "gf": 0, "gc": 0, "dg": dg, "pts": 70 - 3 * i})
    return filas


def hash_de(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_texto_dg():
    assert texto_dg(23) == "+23"
    assert texto_dg(-7) == "-7"
    assert texto_dg(0) == "0"


def test_genera_con_el_tamano_de_la_base_sin_tocarla(tmp_path, monkeypatch):
    monkeypatch.setattr(tabla_imagen, "ESCUDOS", tmp_path / "no_existe")
    antes = hash_de(BASE)
    salida = tmp_path / "tabla.png"
    generar_tabla(filas_a_mano(), salida)
    assert hash_de(BASE) == antes
    with Image.open(salida) as img, Image.open(BASE) as base:
        assert img.size == base.size


def test_pega_escudo_si_existe(tmp_path, monkeypatch):
    escudos = tmp_path / "escudos"
    escudos.mkdir()
    Image.new("RGBA", (200, 240), (0, 255, 0, 255)).save(escudos / "verde.png")
    mapa = tmp_path / "escudos.json"
    mapa.write_text(json.dumps({"1000": "verde.png", "1001": None}), encoding="utf-8")
    monkeypatch.setattr(tabla_imagen, "ESCUDOS", escudos)
    monkeypatch.setattr(tabla_imagen, "MAPA_ESCUDOS", mapa)
    salida = tmp_path / "tabla.png"
    generar_tabla(filas_a_mano(), salida)
    with Image.open(salida) as img:
        x = sum(tabla_imagen.COL_ESCUDO) // 2
        r, g, b = img.convert("RGB").getpixel((x, round(tabla_imagen.centro_fila(1))))
        assert g > 200 and r < 60  # el verde del escudo de prueba, en la fila 1
        r, g, b = img.convert("RGB").getpixel((x, round(tabla_imagen.centro_fila(2))))
        assert g < 100  # la fila 2 no tiene escudo: la celda queda como está


def filas_reales():
    """18 filas con los club_id y nombres reales, con y sin escudo en data/escudos.json."""
    nombres = cargar_nombres()
    filas = filas_a_mano()
    for f, club_id in zip(filas, sorted(nombres)):
        f["club_id"], f["club"] = club_id, nombres[club_id]
    return filas


def test_los_18_escudos_del_mapeo_existen():
    with open(tabla_imagen.MAPA_ESCUDOS, encoding="utf-8") as f:
        mapa = json.load(f)
    assert set(mapa) == set(cargar_nombres())
    for club_id, archivo in mapa.items():
        assert archivo and (tabla_imagen.ESCUDOS / archivo).exists(), club_id


def test_escudo_null_no_da_error(tmp_path, monkeypatch):
    with open(tabla_imagen.MAPA_ESCUDOS, encoding="utf-8") as f:
        mapa = json.load(f)
    filas = filas_reales()
    for f in filas[::2]:
        mapa[f["club_id"]] = None
    ruta = tmp_path / "escudos.json"
    ruta.write_text(json.dumps(mapa), encoding="utf-8")
    monkeypatch.setattr(tabla_imagen, "MAPA_ESCUDOS", ruta)
    salida = tmp_path / "tabla.png"
    generar_tabla(filas, salida)
    assert salida.stat().st_size > 0


def test_escudos_no_se_modifican(tmp_path):
    antes = {p.name: hash_de(p) for p in tabla_imagen.ESCUDOS.iterdir()}
    generar_tabla(filas_reales(), tmp_path / "tabla.png")
    assert {p.name: hash_de(p) for p in tabla_imagen.ESCUDOS.iterdir()} == antes


def test_exige_18_filas(tmp_path):
    with pytest.raises(ValueError):
        generar_tabla(filas_a_mano()[:17], tmp_path / "tabla.png")
