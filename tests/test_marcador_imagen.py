import hashlib
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

import pfb.imagenes.marcador as marcador
from pfb.imagenes.marcador import fuente_club, generar_marcador, minuto_absoluto

COMERCIANTES, MOQUEGUA = "47107", "114625"  # los dos nombres más largos
ALIANZA, UNIVERSITARIO = "184", "6593"


def hash_de(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def gol(club_id, tiempo, minuto, nombre):
    return {"tipo": "gol", "club_id": club_id, "tiempo": tiempo, "minuto": minuto, "casilla": 10,
            "jugador": {"id": "1", "nombre": nombre}, "penal": False}


def registro(local, visita, goles_local=(), goles_visita=(), fecha=1):
    eventos = sorted([gol(local, *g) for g in goles_local] + [gol(visita, *g) for g in goles_visita],
                     key=lambda e: (e["tiempo"], e["minuto"]))
    return {"partido_id": "F01-P1", "fecha": fecha, "semilla": 1, "estado": "jugado",
            "local": {"club_id": local, "goles": len(goles_local), "bonos": {}},
            "visita": {"club_id": visita, "goles": len(goles_visita), "bonos": {}},
            "alineaciones": {}, "eventos": eventos, "fin": None}


def test_tamano_1200(tmp_path):
    salida = tmp_path / "marcador.png"
    generar_marcador(registro(ALIANZA, UNIVERSITARIO, [(1, 20, "Paolo Guerrero")]), salida)
    with Image.open(salida) as img:
        assert img.size == (1200, 1200)


def test_base_y_escudos_no_se_modifican(tmp_path):
    archivos = [marcador.BASE] + sorted(marcador.ESCUDOS.iterdir())
    antes = {p.name: hash_de(p) for p in archivos}
    generar_marcador(registro(ALIANZA, UNIVERSITARIO, [(2, 10, "Paolo Guerrero")], [(1, 5, "Álex Valera")]),
                     tmp_path / "marcador.png")
    assert {p.name: hash_de(p) for p in archivos} == antes


def test_escudo_null_sin_error(tmp_path, monkeypatch):
    with open(marcador.MAPA_ESCUDOS, encoding="utf-8") as f:
        mapa = json.load(f)
    mapa[COMERCIANTES] = None
    ruta = tmp_path / "escudos.json"
    ruta.write_text(json.dumps(mapa), encoding="utf-8")
    monkeypatch.setattr(marcador, "MAPA_ESCUDOS", ruta)
    generar_marcador(registro(COMERCIANTES, ALIANZA), tmp_path / "marcador.png")


def nombres_cortos():
    with open(marcador.RUTA_COLORES, encoding="utf-8") as f:
        return {c: v["club"].upper() for c, v in json.load(f).items()}


@pytest.mark.parametrize("local,visita", [(COMERCIANTES, MOQUEGUA), (MOQUEGUA, COMERCIANTES)])
def test_nombres_largos_entran_de_local_y_de_visita(local, visita, tmp_path):
    generar_marcador(registro(local, visita), tmp_path / "marcador.png")


def test_los_18_nombres_entran_a_tamano_37():
    nombres = nombres_cortos()
    assert len(nombres) == 18 and marcador.CLUB_TAM == 37
    fuente = ImageFont.truetype(str(marcador.FUENTE_BOLD), 37)
    for nombre in nombres.values():
        assert fuente.getlength(nombre) <= marcador.CLUB_LOCAL_ANCHO, nombre
        assert fuente.getlength(nombre) <= marcador.CLUB_VISITA_ANCHO, nombre


def test_nombre_que_no_entra_da_error_sin_achicar():
    with pytest.raises(ValueError, match="no entra"):
        fuente_club("CLUB CON UN NOMBRE LARGUÍSIMO QUE NO ENTRA", marcador.CLUB_VISITA_ANCHO)


def borde_del_panel():
    """Borde derecho del panel blanco (con el escudo de la base) en la zona de los goleadores de la
    visita: por fila, el último pixel con rojo > 200; a la derecha el fondo es un rojo más oscuro.
    Devuelve x(y) ajustado por una recta."""
    with Image.open(marcador.BASE) as base:
        a = np.asarray(base.convert("RGB")).astype(int)
    ys = np.arange(745, 1086, 5)
    xs = [500 + np.where(a[y, 500:1000, 0] > 200)[0].max() for y in ys]
    m, b = np.polyfit(ys, xs, 1)
    assert m == pytest.approx(0.32, abs=0.02)  # crece ~0.32 px por cada px hacia abajo
    return lambda y: m * y + b


def test_goleadores_de_visita_fuera_del_panel():
    borde = borde_del_panel()
    fuente = ImageFont.truetype(str(marcador.FUENTE_REGULAR), marcador.GOLEADOR_TAM)
    d = ImageDraw.Draw(Image.new("RGB", (1200, 1200)))
    (x0, y0), (dx, dy) = marcador.GOLEADOR_VISITA, marcador.GOLEADOR_VISITA_PASO
    for i in range(7):
        x, y = x0 + dx * i, y0 + dy * i
        izq, arriba, _, abajo = d.textbbox((x, y), "88' ÁLEX VALERA", font=fuente, anchor="la")
        # la línea entera (hasta su parte más baja, donde el borde está más a la derecha) queda afuera
        assert izq >= borde(abajo) + 10, (i, izq, borde(abajo))


def test_siete_goles_de_cada_lado(tmp_path):
    goles = [(1 + (i >= 4), 5 * i, f"Jugador Número {i}") for i in range(7)]
    generar_marcador(registro(ALIANZA, UNIVERSITARIO, goles, goles), tmp_path / "marcador.png")


def test_minuto_absoluto():
    assert minuto_absoluto({"tiempo": 1, "minuto": 30}) == 30
    assert minuto_absoluto({"tiempo": 2, "minuto": 0}) == 45
    assert minuto_absoluto({"tiempo": 2, "minuto": 23}) == 68


def test_sin_fecha_no_falla(tmp_path):
    generar_marcador(registro(ALIANZA, UNIVERSITARIO, fecha=None), tmp_path / "marcador.png")
