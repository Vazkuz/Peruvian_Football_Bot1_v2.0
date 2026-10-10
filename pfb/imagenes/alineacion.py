"""Genera la imagen de alineacion de un equipo para un partido.

Uso (desde la raiz del repo):
    python -m pfb.imagenes.alineacion <partido.json> <salida.png>

La cancha, el balon y el icono de cambio son imagenes fijas en assets/alineacion/.
Los circulos de los jugadores, las tarjetas y los textos se dibujan por codigo.
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import to_rgb
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle, Wedge
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[2]
ASSETS = RAIZ / "assets" / "alineacion"
ESCUDOS = RAIZ / "assets" / "escudos"
MAPA_ESCUDOS = RAIZ / "data" / "escudos.json"
DPI = 100  # con DPI 100 la salida tiene exactamente los pixeles de la cancha

# Area de juego dentro de cancha.jpg (lineas blancas exteriores), en pixeles.
CAMPO_X0, CAMPO_X1 = 33, 957
CAMPO_Y_ARCO_PROPIO, CAMPO_Y_ARCO_RIVAL = 1461, 36
LARGO_M, ANCHO_M = 105, 68
ESCALA = (CAMPO_X1 - CAMPO_X0) / ANCHO_M  # pixeles por metro

# Formaciones: lista de casillas (x, y) en metros, en este orden:
#   arquero, y luego cada linea desde la defensa hacia adelante, de izquierda a derecha.
# x: 0 = banda izquierda, 68 = banda derecha. y: 0 = arco propio, 105 = arco rival.
# (El orden de casillas es solo para dibujar; no es la numeracion de puestos del motor.)
ARQUERO = [(34.0, 11.0)]
DEFENSA_4 = [(10.5, 33.0), (25.5, 25.0), (42.5, 25.0), (57.5, 33.0)]
DEFENSA_3 = [(17.0, 26.0), (34.0, 24.0), (51.0, 26.0)]
DELANTEROS_2 = [(24.0, 83.0), (44.0, 83.0)]
FORMACIONES = {
    "4-2-3-1": ARQUERO + DEFENSA_4
    + [(25.5, 45.0), (42.5, 45.0)]
    + [(11.0, 64.0), (34.0, 62.0), (57.0, 64.0)]
    + [(34.0, 83.0)],
    "4-3-3": ARQUERO + DEFENSA_4
    + [(18.0, 55.0), (34.0, 46.0), (50.0, 55.0)]
    + [(11.0, 78.0), (34.0, 84.0), (57.0, 78.0)],
    "4-4-2": ARQUERO + DEFENSA_4
    + [(10.5, 60.0), (25.5, 53.0), (42.5, 53.0), (57.5, 60.0)]
    + DELANTEROS_2,
    "4-1-3-2": ARQUERO + DEFENSA_4
    + [(34.0, 43.0)]
    + [(12.0, 62.0), (34.0, 59.0), (56.0, 62.0)]
    + DELANTEROS_2,
    "3-1-4-2": ARQUERO + DEFENSA_3
    + [(34.0, 41.0)]
    + [(8.0, 61.0), (24.0, 57.0), (44.0, 57.0), (60.0, 61.0)]
    + DELANTEROS_2,
}


def forma_base(formacion):
    """'4-4-2 double 6' -> '4-4-2', '4-3-3 Attacking' -> '4-3-3'."""
    return formacion.split()[0]


# Tamanos en metros de cancha.
RADIO_JUGADOR = 2.6
RADIO_BALON = 1.15
RADIO_BALON_SUPLENTE = 0.95
LADO_CAMBIO = 3.0
TARJETA_ANCHO, TARJETA_ALTO = 1.5, 2.1
ANCHO_RAYA = 0.42  # ancho de la raya vertical (en radios del circulo)
# Placa "x2" de goles, en radios del balon (relativa al centro del balon).
PLACA_DX, PLACA_DY, PLACA_ANCHO, PLACA_ALTO, PLACA_TEXTO = 0.2, 0.18, 1.9, 1.5, 1.0
TXT_NOMBRE, TXT_SUPLENTE, TXT_CONTADOR, TXT_TITULO = 1.41, 1.27, 1.18, 1.99
ESCUDO_LADO = 8.0  # m, lado del cuadrado donde entra el escudo
ESCUDO_DESDE_FONDO = 5.3  # m, del fondo de la cancha (arco rival) al centro del escudo

BLANCO = "white"
AMARILLO_SUPLENTE = "#ffe9a8"
COLOR_TARJETA = {"amarilla": "#f4c430", "roja": "#d62828"}
FONDO_ETIQUETA = "#00000070"


def px(x_m, y_m):
    """Metros de cancha -> pixeles de la imagen."""
    x = CAMPO_X0 + x_m * ESCALA
    y = CAMPO_Y_ARCO_PROPIO - y_m * (CAMPO_Y_ARCO_PROPIO - CAMPO_Y_ARCO_RIVAL) / LARGO_M
    return x, y


def pt(metros):
    """Tamano de letra: metros de cancha -> puntos."""
    return metros * ESCALA * 72 / DPI


def borde_de(color, factor=0.45):
    r, g, b = to_rgb(color)
    return (r * factor, g * factor, b * factor)


def cargar_balon():
    """El balon viene con fondo blanco: se vuelve transparente lo de fuera del circulo."""
    img = Image.open(ASSETS / "balon.png").convert("RGBA")
    w, h = img.size
    for esquina in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(img, esquina, (255, 255, 255, 0), thresh=40)
    return np.asarray(img) / 255.0


def cargar_png(nombre):
    return np.asarray(Image.open(ASSETS / nombre).convert("RGBA")) / 255.0


def escudo_escalado(archivo, caja_w, caja_h):
    """El escudo escalado sin deformarse para entrar en caja_w x caja_h, con su transparencia."""
    with Image.open(ESCUDOS / archivo) as original:
        img = original.convert("RGBA")
    escala = min(caja_w / img.width, caja_h / img.height)
    return img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)


class Lienzo:
    def __init__(self):
        cancha = Image.open(ASSETS / "cancha.jpg").convert("RGB")
        self.w, self.h = cancha.size
        self.fig = plt.figure(figsize=(self.w / DPI, self.h / DPI), dpi=DPI)
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.imshow(np.asarray(cancha), extent=(0, self.w, self.h, 0), zorder=0)
        self.ax.set_xlim(0, self.w)
        self.ax.set_ylim(self.h, 0)
        self.ax.axis("off")
        font_manager.fontManager.addfont(str(ASSETS / "Inter-Bold.otf"))
        self.fuente = font_manager.FontProperties(fname=str(ASSETS / "Inter-Bold.otf"))
        self.img_balon = cargar_balon()
        self.img_cambio = cargar_png("cambio.png")

    def texto(self, x, y, s, tam, color=BLANCO, fondo=FONDO_ETIQUETA, ha="center", va="top", z=4):
        return self.ax.text(
            x, y, s, ha=ha, va=va, color=color, fontsize=pt(tam), fontproperties=self.fuente,
            zorder=z, bbox=dict(boxstyle="round,pad=0.25", fc=fondo, ec="none"),
        )

    def caja(self, artista):
        """Caja que ocupa un texto, en pixeles de la imagen."""
        self.fig.canvas.draw()
        return artista.get_window_extent().transformed(self.ax.transData.inverted())

    def dentro_del_campo(self, artista, margen=6, extra_derecha=0):
        """Corre una etiqueta horizontalmente si se sale de las lineas laterales.
        extra_derecha: pixeles que ocupan los iconos que van a la derecha de la etiqueta."""
        b = self.caja(artista)
        x0, x1 = min(b.x0, b.x1), max(b.x0, b.x1)
        dx = 0
        if x0 < CAMPO_X0 + margen:
            dx = CAMPO_X0 + margen - x0
        elif x1 + extra_derecha > CAMPO_X1 - margen:
            dx = CAMPO_X1 - margen - x1 - extra_derecha
        if dx:
            x, y = artista.get_position()
            artista.set_position((x + dx, y))

    def icono(self, img, x, y, lado_m):
        lado_px = lado_m * ESCALA
        zoom = lado_px * 72 / DPI / img.shape[0]
        self.ax.add_artist(AnnotationBbox(OffsetImage(img, zoom=zoom), (x, y), frameon=False, zorder=6))

    def balon(self, x, y, goles, radio_m):
        self.icono(self.img_balon, x, y, 2 * radio_m)
        if goles > 1:
            ANCHO_RAYA = 0.42  # ancho de la raya vertical (en radios del circulo)
# Placa "x2" encima del balon, montada sobre su cuarto inferior derecho.
            r = radio_m * ESCALA
            x0, y0 = x + PLACA_DX * r, y + PLACA_DY * r  # esquina superior izquierda
            w, h = PLACA_ANCHO * r, PLACA_ALTO * r
            self.ax.add_patch(FancyBboxPatch(
                (x0, y0), w, h, boxstyle=f"round,pad=0,rounding_size={0.28 * r}",
                fc="#3a3a3a", ec="black", lw=1.0, alpha=0.92, zorder=7,
            ))
            self.ax.text(
                x0 + w / 2, y0 + h / 2, f"x{goles}", ha="center", va="center", color=BLANCO,
                fontsize=pt(PLACA_TEXTO * radio_m), fontproperties=self.fuente, zorder=7.1,
            )

    def una_tarjeta(self, x, y, color, angulo, z=6):
        w, h = TARJETA_ANCHO * ESCALA, TARJETA_ALTO * ESCALA
        self.ax.add_patch(Rectangle(
            (x - w / 2, y - h / 2), w, h, angle=angulo, rotation_point="center",
            color=color, ec="#333333", lw=0.6, zorder=z,
        ))

    def tarjeta(self, x, y, tipo):
        """'amarilla', 'roja' o 'doble_amarilla' (amarilla detras y roja encima)."""
        if tipo == "doble_amarilla":
            d = 0.45 * ESCALA
            self.una_tarjeta(x - d, y + d * 0.3, COLOR_TARJETA["amarilla"], 8, z=6)
            self.una_tarjeta(x + d, y - d * 0.3, COLOR_TARJETA["roja"], -14, z=6.5)
        else:
            self.una_tarjeta(x, y, COLOR_TARJETA[tipo], -12)

    def circulo(self, x, y, r, color):
        """color: "#hex" (un color) o {"base": "#hex", "segundo": "#hex", "estilo": "raya"|"mitades"}.
        raya = franja vertical al centro; mitades = mitad izquierda base, mitad derecha segundo."""
        if isinstance(color, str):
            color = {"base": color}
        base = color["base"]
        self.ax.add_patch(Circle((x, y), r, color=base, zorder=3))
        estilo, segundo = color.get("estilo"), color.get("segundo")
        if estilo == "raya":
            borde_clip = Circle((x, y), r, transform=self.ax.transData)
            franja = Rectangle((x - ANCHO_RAYA * r / 2, y - r), ANCHO_RAYA * r, 2 * r,
                               color=segundo, zorder=3.1)
            self.ax.add_patch(franja)
            franja.set_clip_path(borde_clip)
        elif estilo == "mitades":
            self.ax.add_patch(Wedge((x, y), r, -90, 90, color=segundo, zorder=3.1))
        self.ax.add_patch(Circle((x, y), r, fill=False, ec=borde_de(base), lw=1.5, zorder=3.2))

    def jugador(self, x_m, y_m, j, color):
        x, y = px(x_m, y_m)
        r = RADIO_JUGADOR * ESCALA
        self.circulo(x, y, r, color)

        if j.get("tarjeta"):
            self.tarjeta(x + r * 0.8, y - r * 0.75, j["tarjeta"])
        if j.get("goles"):
            self.balon(x + r * 0.85, y + r * 0.75, j["goles"], RADIO_BALON)
        cambio = j.get("cambio")
        if cambio:
            self.icono(self.img_cambio, x - r * 0.85, y + r * 0.75, LADO_CAMBIO)

        nombre = self.texto(x, y + 3.9 * ESCALA, j["nombre"], TXT_NOMBRE)
        self.dentro_del_campo(nombre)

        if cambio:
            linea = self.texto(
                x, y + 6.9 * ESCALA, f"{cambio['entra']} {cambio['minuto']}'", TXT_SUPLENTE,
                color=AMARILLO_SUPLENTE, fondo="#00000060",
            )
            r_b = RADIO_BALON_SUPLENTE
            g, tj = cambio.get("goles"), cambio.get("tarjeta")
            # Distancias en metros: del borde de la etiqueta al balon, y del balon a la tarjeta.
            al_balon = 1.3
            ancho_tj = TARJETA_ANCHO + (0.9 if tj == "doble_amarilla" else 0)  # la doble ocupa mas
            a_tarjeta = ((PLACA_DX + PLACA_ANCHO) * r_b if (g and g > 1) else r_b) + 0.25 + ancho_tj / 2
            extra = 0
            if g:
                extra = al_balon + (a_tarjeta + ancho_tj / 2 if tj else ((PLACA_DX + PLACA_ANCHO) * r_b if g > 1 else r_b))
            elif tj:
                extra = 0.6 + ancho_tj + 0.6
            extra *= ESCALA
            self.dentro_del_campo(linea, extra_derecha=extra)
            # Iconos del suplente, a la derecha de su linea: primero el balon, luego la tarjeta.
            b = self.caja(linea)
            borde, cy = max(b.x0, b.x1), (b.y0 + b.y1) / 2
            if g:
                bx = borde + al_balon * ESCALA
                self.balon(bx, cy, g, r_b)
                if tj:
                    self.tarjeta(bx + a_tarjeta * ESCALA, cy, tj)
            elif tj:
                self.tarjeta(borde + (0.6 + ancho_tj / 2) * ESCALA, cy, tj)

    def titulo(self, s, escudo=None):
        """Nombre del club en su recuadro. Si hay escudo (archivo en assets/escudos/), va arriba
        del nombre, centrado a lo ancho, a la altura del area chica del arco rival."""
        x, y = px(ANCHO_M / 2, LARGO_M - 12.5)
        self.ax.text(
            x, y, s, ha="center", va="center", color=BLANCO, fontsize=pt(TXT_TITULO),
            fontproperties=self.fuente, zorder=5,
            bbox=dict(boxstyle="round,pad=0.35", fc="#00000080", ec="none"),
        )
        if not escudo or not (ESCUDOS / escudo).exists():
            return
        lado = ESCUDO_LADO * ESCALA
        img = escudo_escalado(escudo, lado, lado)
        # zoom 72 / DPI: un pixel de la imagen = un pixel de la salida
        self.ax.add_artist(AnnotationBbox(OffsetImage(np.asarray(img) / 255.0, zoom=72 / DPI),
                                          px(ANCHO_M / 2, LARGO_M - ESCUDO_DESDE_FONDO),
                                          frameon=False, zorder=5))

    def guardar(self, salida):
        self.fig.savefig(salida, dpi=DPI)
        plt.close(self.fig)


def generar(partido, salida):
    casillas = FORMACIONES[forma_base(partido["formacion"])]
    if len(partido["jugadores"]) != len(casillas):
        raise ValueError("se esperaban 11 jugadores")
    lienzo = Lienzo()
    for x_m, y_m, j in [(*casillas[i], j) for i, j in enumerate(partido["jugadores"])]:
        lienzo.jugador(x_m, y_m, j, partido["color"])
    with open(MAPA_ESCUDOS, encoding="utf-8") as f:
        escudos = json.load(f)
    lienzo.titulo(partido["club"], escudos.get(partido.get("club_id")))
    lienzo.guardar(salida)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: python -m pfb.imagenes.alineacion <partido.json> <salida.png>")
    with open(sys.argv[1], encoding="utf-8") as f:
        generar(json.load(f), sys.argv[2])
