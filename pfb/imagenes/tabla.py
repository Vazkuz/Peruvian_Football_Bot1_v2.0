"""Genera la imagen de la tabla de posiciones sobre assets/Tabla_final.jpg.

La base es arte fijo y no se modifica: el codigo solo escribe encima los clubes, PJ, DG y
puntos, y pega el escudo de cada club segun data/escudos.json (club_id -> archivo en
assets/escudos/, o null si todavia no hay). Los numeros de POS ya vienen impresos en la base.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from PIL import Image

from pfb.imagenes.alineacion import ASSETS as ASSETS_ALINEACION
from pfb.imagenes.alineacion import DPI, RAIZ

BASE = RAIZ / "assets" / "Tabla_final.jpg"
ESCUDOS = RAIZ / "assets" / "escudos"
MAPA_ESCUDOS = RAIZ / "data" / "escudos.json"
FUENTE_TEXTO = RAIZ / "assets" / "fuentes" / "BarlowSemiCondensed-Regular.ttf"  # CLUB, PJ y DG
FUENTE_PUNTOS = ASSETS_ALINEACION / "Inter-Bold.otf"

COLOR_TEXTO = "#FFFFFF"
COLOR_PUNTOS = "#ebb182"

# Filas, medidas sobre Tabla_final.jpg (1080x1350), en pixeles: la fila n (1 a 18) va de
# FILA_Y0 + (n - 1) * FILA_PASO a ese valor + FILA_ALTO.
N_FILAS = 18
FILA_Y0 = 285
FILA_PASO = 49
FILA_ALTO = 45

# Columnas (x0, x1) de cada celda, sin las lineas de la grilla, en pixeles.
COL_POS = (200, 268)  # los numeros ya vienen impresos
COL_ESCUDO = (272, 333)
COL_CLUB = (336, 601)
COL_PJ = (605, 695)
COL_DG = (699, 782)
COL_PUNTOS = (786, 881)

TXT_PX = 22  # tamano de letra en pixeles
MARGEN_CLUB = 12  # espacio a la izquierda y a la derecha del nombre dentro de su celda
MARGEN_ESCUDO = 4  # espacio alrededor del escudo dentro de su celda


def centro_fila(n):
    return FILA_Y0 + (n - 1) * FILA_PASO + FILA_ALTO / 2


def texto_dg(dg):
    """+23, -7 y 0."""
    return f"{dg:+d}" if dg else "0"


class LienzoTabla:
    def __init__(self):
        base = Image.open(BASE).convert("RGB")
        self.w, self.h = base.size
        self.fig = plt.figure(figsize=(self.w / DPI, self.h / DPI), dpi=DPI)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.imshow(np.asarray(base), extent=(0, self.w, self.h, 0), zorder=0)
        self.ax.set_xlim(0, self.w)
        self.ax.set_ylim(self.h, 0)
        self.ax.axis("off")
        for fuente in (FUENTE_TEXTO, FUENTE_PUNTOS):
            font_manager.fontManager.addfont(str(fuente))
        self.fuente_texto = font_manager.FontProperties(fname=str(FUENTE_TEXTO))
        self.fuente_puntos = font_manager.FontProperties(fname=str(FUENTE_PUNTOS))

    def texto(self, x, y, s, ha="center", fuente=None, color=COLOR_TEXTO):
        return self.ax.text(x, y, s, ha=ha, va="center", color=color, fontsize=TXT_PX * 72 / DPI,
                            fontproperties=fuente or self.fuente_texto, zorder=4)

    def ancho(self, artista):
        b = artista.get_window_extent(renderer=self.fig.canvas.get_renderer())
        b = b.transformed(self.ax.transData.inverted())
        return abs(b.x1 - b.x0)

    def centrado(self, columna, y, s, **estilo):
        x0, x1 = columna
        self.texto((x0 + x1) / 2, y, s, **estilo)

    def club(self, y, nombre):
        """En mayúsculas (con sus tildes) y alineado a la izquierda; si no entra en la celda, se achica
        la letra solo para este nombre."""
        x0, x1 = COL_CLUB
        disponible = (x1 - x0) - 2 * MARGEN_CLUB
        artista = self.texto(x0 + MARGEN_CLUB, y, nombre.upper(), ha="left")
        ancho = self.ancho(artista)
        if ancho > disponible:
            artista.set_fontsize(artista.get_fontsize() * disponible / ancho)

    def escudo(self, y, archivo):
        """Centrado en su celda, escalado sin deformarse y con su transparencia.
        Si no hay archivo (null en el mapeo, o no existe), la celda queda vacía."""
        if not archivo or not (ESCUDOS / archivo).exists():
            return
        x0, x1 = COL_ESCUDO
        lado_w, lado_h = (x1 - x0) - 2 * MARGEN_ESCUDO, FILA_ALTO - 2 * MARGEN_ESCUDO
        with Image.open(ESCUDOS / archivo) as original:
            img = original.convert("RGBA")
        escala = min(lado_w / img.width, lado_h / img.height)
        img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))),
                         Image.LANCZOS)
        # zoom 72 / DPI: un pixel de la imagen = un pixel de la salida
        self.ax.add_artist(AnnotationBbox(OffsetImage(np.asarray(img) / 255.0, zoom=72 / DPI),
                                          ((x0 + x1) / 2, y), frameon=False, zorder=3))

    def guardar(self, salida):
        self.fig.savefig(salida, dpi=DPI)
        plt.close(self.fig)


def generar_tabla(filas, salida):
    """filas: la salida de temporada.tabla() (18 filas, ya ordenadas)."""
    if len(filas) != N_FILAS:
        raise ValueError(f"se esperaban {N_FILAS} filas, vinieron {len(filas)}")
    with open(MAPA_ESCUDOS, encoding="utf-8") as f:
        escudos = json.load(f)
    lienzo = LienzoTabla()
    for n, f in enumerate(filas, start=1):
        y = centro_fila(n)
        lienzo.escudo(y, escudos.get(f["club_id"]))
        lienzo.club(y, f["club"])
        lienzo.centrado(COL_PJ, y, str(f["pj"]))
        lienzo.centrado(COL_DG, y, texto_dg(f["dg"]))
        lienzo.centrado(COL_PUNTOS, y, str(f["pts"]), fuente=lienzo.fuente_puntos, color=COLOR_PUNTOS)
    lienzo.guardar(salida)
