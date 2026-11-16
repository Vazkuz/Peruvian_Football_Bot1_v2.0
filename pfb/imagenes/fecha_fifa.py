"""Imagen del resultado de la Fecha FIFA (§13.1) sobre assets/Fecha Fifa.png.

La base y las banderas son arte fijo y no se modifican: el código pega las banderas de
assets/banderas/<código FIFA>.png y escribe encima los nombres, el marcador y "FINAL". El local va a
la izquierda. Medidas aprobadas por Daniel (mockup del 15/11/2026), en píxeles sobre la base de
1080x1077.
"""

from PIL import Image, ImageDraw, ImageFont

from pfb.imagenes.alineacion import RAIZ

BASE = RAIZ / "assets" / "Fecha Fifa.png"
BANDERAS = RAIZ / "assets" / "banderas"
FUENTE = RAIZ / "assets" / "fuentes" / "BarlowSemiCondensed-Bold.ttf"

BLANCO = (255, 255, 255)
CIAN = (40, 190, 235)

TEXTO_FIN = 401         # primera fila libre debajo de "AMISTOSO INTERNACIONAL - FECHA FIFA"
PANEL_FIN = 946         # fin del panel azul
BANDERA = (192, 144)    # ancho, alto
BORDE = 4               # borde blanco de la bandera
X_LOCAL, X_VISITA, X_CENTRO = 250, 828, 539
DIST_NOMBRES = 55       # del borde inferior de la bandera al centro de la línea de los nombres
NOMBRE_TAM, MARCADOR_TAM, FINAL_TAM = 56, 126, 42
NOMBRE_ANCHO_MAX = 300  # un nombre más ancho se parte en dos líneas y, si no entra igual, se achica
NOMBRE_TAM_MIN = 30
INTERLINEA = 1.15       # distancia entre líneas de un nombre partido, en veces el tamaño de letra


def _fuente(tam):
    return ImageFont.truetype(str(FUENTE), tam)


def _ancho(d, texto, tam):
    l, _, r, _ = d.textbbox((0, 0), texto, font=_fuente(tam))
    return r - l


def lineas_nombre(d, nombre):
    """(líneas, tamaño) del nombre en mayúsculas: una línea de NOMBRE_TAM si entra; si no, el corte en dos
    líneas que deja la más ancha lo más angosta posible; y si aun así no entra, se achica la letra hasta
    que entre (sin bajar de NOMBRE_TAM_MIN)."""
    texto = nombre.upper()
    if _ancho(d, texto, NOMBRE_TAM) <= NOMBRE_ANCHO_MAX:
        return [texto], NOMBRE_TAM
    palabras = texto.split()
    opciones = [[texto]] + [[" ".join(palabras[:i]), " ".join(palabras[i:])] for i in range(1, len(palabras))]
    lineas = min(opciones, key=lambda ls: max(_ancho(d, linea, NOMBRE_TAM) for linea in ls))
    tam = NOMBRE_TAM
    while tam > NOMBRE_TAM_MIN and max(_ancho(d, linea, tam) for linea in lineas) > NOMBRE_ANCHO_MAX:
        tam -= 1
    return lineas, tam


def _centrado(d, texto, cx, cy, tam, color):
    f = _fuente(tam)
    l, t, r, b = d.textbbox((0, 0), texto, font=f)
    d.text((cx - (r - l) / 2 - l, cy - (b - t) / 2 - t), texto, font=f, fill=color)


def y_bandera(d):
    """Borde superior de la bandera (sin el marco): el bloque bandera + nombres queda con el mismo
    espacio arriba (hasta el texto cian) que abajo (hasta el fin del panel), medido con nombres de una
    línea."""
    f = _fuente(NOMBRE_TAM)
    bajo = max(d.textbbox((0, 0), t, font=f)[3] - sum(d.textbbox((0, 0), t, font=f)[1::2]) / 2
               for t in ("PERÚ", "ARGENTINA"))
    alto = BORDE + BANDERA[1] + DIST_NOMBRES + bajo
    return round((TEXTO_FIN + PANEL_FIN - alto) / 2 + BORDE)


def generar_fecha_fifa(fecha_fifa, nombres, ruta):
    """fecha_fifa: el bloque "fecha_fifa" del registro. nombres: {código FIFA: nombre}. Guarda el PNG en
    ruta y la devuelve."""
    img = Image.open(BASE).convert("RGB")
    d = ImageDraw.Draw(img)
    y = y_bandera(d)
    y_nombres = y + BANDERA[1] + DIST_NOMBRES
    for lado, cx in (("local", X_LOCAL), ("visita", X_VISITA)):
        codigo = fecha_fifa[lado]["seleccion"]
        bandera = Image.open(BANDERAS / f"{codigo}.png").convert("RGB").resize(BANDERA, Image.LANCZOS)
        x = cx - BANDERA[0] // 2
        d.rectangle([x - BORDE, y - BORDE, x + BANDERA[0] + BORDE - 1, y + BANDERA[1] + BORDE - 1], fill=BLANCO)
        img.paste(bandera, (x, y))
        lineas, tam = lineas_nombre(d, nombres[codigo])
        for i, linea in enumerate(lineas):
            _centrado(d, linea, cx, y_nombres + i * tam * INTERLINEA, tam, BLANCO)
    marcador = f"{fecha_fifa['local']['goles']} - {fecha_fifa['visita']['goles']}"
    _centrado(d, marcador, X_CENTRO, y + BANDERA[1] / 2, MARCADOR_TAM, BLANCO)
    _centrado(d, "FINAL", X_CENTRO, y_nombres, FINAL_TAM, CIAN)
    img.save(ruta)
    return ruta
