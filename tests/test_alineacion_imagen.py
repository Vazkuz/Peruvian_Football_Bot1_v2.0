import hashlib
import json

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.offsetbox import AnnotationBbox
from PIL import Image

import pfb.imagenes.alineacion as alineacion
from pfb.imagenes.alineacion import Lienzo, generar

MAGENTA = (255, 0, 255, 255)


@pytest.fixture
def ejemplo():
    with open(alineacion.RAIZ / "data" / "ejemplo_alineacion.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def escudos_de_prueba(tmp_path, monkeypatch):
    """assets/escudos/ y data/escudos.json de prueba: '184' con un escudo magenta de 200x400,
    '6593' en null y '1450' con un archivo que no existe."""
    carpeta = tmp_path / "escudos"
    carpeta.mkdir()
    Image.new("RGBA", (200, 400), MAGENTA).save(carpeta / "magenta.png")
    mapa = tmp_path / "escudos.json"
    mapa.write_text(json.dumps({"184": "magenta.png", "6593": None, "1450": "no_existe.png"}), encoding="utf-8")
    monkeypatch.setattr(alineacion, "ESCUDOS", carpeta)
    monkeypatch.setattr(alineacion, "MAPA_ESCUDOS", mapa)


def hash_de(ruta):
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def caja(lienzo, artista):
    lienzo.fig.canvas.draw()
    return artista.get_window_extent().transformed(lienzo.ax.transData.inverted())


def titulo(escudo):
    """Dibuja el titulo y devuelve (posicion del texto, caja del recuadro, AnnotationBbox del escudo o None)."""
    lienzo = Lienzo()
    lienzo.titulo("Alianza Lima", escudo)
    texto = lienzo.ax.texts[-1]
    recuadro = caja(lienzo, texto.get_bbox_patch())
    escudos = [a for a in lienzo.ax.artists if isinstance(a, AnnotationBbox)]
    plt.close(lienzo.fig)
    assert len(escudos) <= 1
    return texto.get_position(), recuadro, (escudos[0] if escudos else None)


def test_escudo_arriba_del_nombre_centrado_y_sin_deformarse(escudos_de_prueba):
    _, recuadro, escudo = titulo("magenta.png")
    alto_img, ancho_img = escudo.offsetbox.get_data().shape[:2]  # un pixel de la imagen = uno de la salida
    lado = alineacion.ESCUDO_LADO * alineacion.ESCALA
    # 200x400 dentro del cuadrado: llena el alto y queda con la mitad de ancho
    assert alto_img == pytest.approx(lado, abs=1)
    assert ancho_img == pytest.approx(lado / 2, abs=1)
    # centrado a lo ancho, con su centro a ESCUDO_DESDE_FONDO del fondo de la cancha
    assert escudo.xy == alineacion.px(alineacion.ANCHO_M / 2, alineacion.LARGO_M - alineacion.ESCUDO_DESDE_FONDO)
    # no se superpone con el recuadro del nombre (en la imagen, y crece hacia abajo)
    assert escudo.xy[1] + alto_img / 2 < min(recuadro.y0, recuadro.y1)


def test_recuadro_del_nombre_no_se_mueve_con_escudo(escudos_de_prueba):
    original = alineacion.px(alineacion.ANCHO_M / 2, alineacion.LARGO_M - 12.5)
    pos_con, recuadro_con, escudo = titulo("magenta.png")
    pos_sin, recuadro_sin, sin_escudo = titulo(None)
    assert escudo is not None and sin_escudo is None
    assert pos_con == pos_sin == original
    assert recuadro_con.bounds == pytest.approx(recuadro_sin.bounds)


def test_generar_pega_el_escudo_del_club(escudos_de_prueba, ejemplo, tmp_path):
    salida = tmp_path / "alineacion.png"
    generar(ejemplo, salida)
    a = np.asarray(Image.open(salida).convert("RGB")).astype(int)
    magenta = (a[:, :, 0] > 230) & (a[:, :, 1] < 30) & (a[:, :, 2] > 230)
    ys, xs = np.nonzero(magenta)
    assert len(xs) > 0
    x, y = alineacion.px(alineacion.ANCHO_M / 2, alineacion.LARGO_M - alineacion.ESCUDO_DESDE_FONDO)
    assert xs.min() < x < xs.max() and ys.min() < y < ys.max()


def test_sin_escudo_el_titulo_sale_como_hoy(escudos_de_prueba, ejemplo, tmp_path):
    """null, archivo que no existe y JSON sin club_id dan la misma imagen."""
    rutas = []
    for i, club_id in enumerate(("6593", "1450", None)):
        datos = dict(ejemplo)
        if club_id:
            datos["club_id"] = club_id
        else:
            del datos["club_id"]
        rutas.append(tmp_path / f"alineacion_{i}.png")
        generar(datos, rutas[-1])
    assert len({hash_de(r) for r in rutas}) == 1


def test_escudos_reales_no_se_modifican(ejemplo, tmp_path):
    antes = {p.name: hash_de(p) for p in alineacion.ESCUDOS.iterdir()}
    for club_id in ("47107", "120792", "35588"):
        generar(dict(ejemplo, club_id=club_id), tmp_path / f"alineacion_{club_id}.png")
    assert {p.name: hash_de(p) for p in alineacion.ESCUDOS.iterdir()} == antes
