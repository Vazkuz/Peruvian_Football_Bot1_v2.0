"""Imagen de la programación de la fecha siguiente (§5.0d, tarea 26).

El panel y las franjas son arte fijo y no se modifican: el código pega el panel
assets/Fixture del Día - sin jugador.png y la franja del club de la foto (assets/programacion/<club_id>.png)
a la izquierda o a la derecha, y escribe encima "FECHA N" y las 9 filas (hora, escudos y nombres).
Medidas aprobadas por Daniel (mockup del 19/11/2026), en píxeles sobre el panel de 588x1077.
"""

import json

from PIL import Image, ImageDraw, ImageFont

from pfb.imagenes.alineacion import RAIZ
from pfb.motor.temporada import cargar_nombres

PANEL = RAIZ / "assets" / "Fixture del Día - sin jugador.png"
FRANJAS = RAIZ / "assets" / "programacion"
ESCUDOS = RAIZ / "assets" / "escudos"
MAPA_ESCUDOS = RAIZ / "data" / "escudos.json"
FUENTE = RAIZ / "assets" / "fuentes" / "BarlowSemiCondensed-Bold.ttf"
FUENTE_FECHA = RAIZ / "assets" / "fuentes" / "JetBrainsMono-Bold.ttf"

PANEL_TAM = (588, 1077)
FRANJA_TAM = (337, 1077)
LADOS = ("izquierda", "derecha")

# Nombres que solo cambian en esta imagen (Daniel, 19/11/2026); el resto sale de colores_clubes.json.
NOMBRES_PROPIOS = {
    "114625": "D. Moquegua",
    "35588": "ADT Tarma",
    "21170": "UTC Cajamarca",
    "47107": "Comerciantes U.",
}

HORA_INICIO = 9         # el primer partido de la fecha sale a las 9:00 y luego uno por hora

FECHA_CENTRO, FECHA_TAM, FECHA_COLOR = (294, 160), 30, "#d8bab1"

N_FILAS = 9
FILA_Y0, FILA_PASO, FILA_ALTO = 300, 72, 62
FILA_X = (48, 545)
FILA_RADIO, FILA_COLOR = 10, (0, 0, 0, 70)

HORA_CAJA_X = (56, 128)
HORA_CAJA_Y = (12, 50)  # desde el borde superior de la fila
HORA_RADIO, HORA_FONDO = 8, (255, 255, 255, 235)
HORA_TAM, HORA_COLOR = 24, (170, 20, 30)

ESCUDO_X_LOCAL, ESCUDO_X_VISITA, ESCUDO_LADO = 160, 515, 46
NOMBRE_X_LOCAL, NOMBRE_X_VISITA = 186, 489   # local alineado a la izquierda, visita a la derecha
NOMBRE_TAM, NOMBRE_ANCHO_MAX, NOMBRE_COLOR = 21, 130, (255, 255, 255)
VS_X, VS_TAM, VS_COLOR = 338, 20, "#ebb182"


def nombres_programacion(nombres=None):
    """{club_id: nombre} para esta imagen: los cortos de siempre con los NOMBRES_PROPIOS encima."""
    return {**(nombres or cargar_nombres()), **NOMBRES_PROPIOS}


def horas(n=N_FILAS):
    return [f"{HORA_INICIO + i}:00" for i in range(n)]


def tam_nombre(texto):
    """Tamaño de letra del nombre (ya en mayúsculas): NOMBRE_TAM, o menos hasta que entre en NOMBRE_ANCHO_MAX."""
    tam = NOMBRE_TAM
    while tam > 1 and ImageFont.truetype(str(FUENTE), tam).getlength(texto) > NOMBRE_ANCHO_MAX:
        tam -= 1
    return tam


def _escudo(archivo):
    with Image.open(ESCUDOS / archivo) as original:
        img = original.convert("RGBA")
    escala = min(ESCUDO_LADO / img.width, ESCUDO_LADO / img.height)
    return img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)


def generar_panel(fecha, partidos, nombres):
    """El panel de 588x1077 con "FECHA N" y las filas. partidos: [(local, visita)] en club_id, en orden."""
    if len(partidos) != N_FILAS:
        raise ValueError(f"se esperaban {N_FILAS} partidos, vinieron {len(partidos)}")
    with open(MAPA_ESCUDOS, encoding="utf-8") as f:
        escudos = json.load(f)
    panel = Image.open(PANEL).convert("RGBA")
    if panel.size != PANEL_TAM:
        raise ValueError(f"el panel mide {panel.size}, se esperaba {PANEL_TAM}")

    capa = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    for i in range(N_FILAS):
        y = FILA_Y0 + i * FILA_PASO
        dc.rounded_rectangle([FILA_X[0], y, FILA_X[1], y + FILA_ALTO], radius=FILA_RADIO, fill=FILA_COLOR)
    panel.alpha_composite(capa)

    d = ImageDraw.Draw(panel)
    d.text(FECHA_CENTRO, f"FECHA {fecha}", font=ImageFont.truetype(str(FUENTE_FECHA), FECHA_TAM),
           fill=FECHA_COLOR, anchor="mm")
    fuente_hora = ImageFont.truetype(str(FUENTE), HORA_TAM)
    fuente_vs = ImageFont.truetype(str(FUENTE), VS_TAM)
    for i, ((local, visita), hora) in enumerate(zip(partidos, horas())):
        y = FILA_Y0 + i * FILA_PASO
        cy = y + FILA_ALTO // 2
        d.rounded_rectangle([HORA_CAJA_X[0], y + HORA_CAJA_Y[0], HORA_CAJA_X[1], y + HORA_CAJA_Y[1]],
                            radius=HORA_RADIO, fill=HORA_FONDO)
        d.text(((HORA_CAJA_X[0] + HORA_CAJA_X[1]) / 2, cy), hora, font=fuente_hora, fill=HORA_COLOR, anchor="mm")
        for club_id, x_escudo, x_nombre, ancla in ((local, ESCUDO_X_LOCAL, NOMBRE_X_LOCAL, "lm"),
                                                   (visita, ESCUDO_X_VISITA, NOMBRE_X_VISITA, "rm")):
            if escudos.get(club_id) and (ESCUDOS / escudos[club_id]).exists():
                e = _escudo(escudos[club_id])
                panel.alpha_composite(e, (x_escudo - e.width // 2, cy - e.height // 2))
            texto = nombres[club_id].upper()
            d.text((x_nombre, cy), texto, font=ImageFont.truetype(str(FUENTE), tam_nombre(texto)),
                   fill=NOMBRE_COLOR, anchor=ancla)
        d.text((VS_X, cy), "VS", font=fuente_vs, fill=VS_COLOR, anchor="mm")
    return panel.convert("RGB")


def generar_programacion(fecha, partidos, club_foto, lado, ruta, nombres=None):
    """fecha: la que se juega mañana. partidos: [(local, visita)] de esa fecha, en el orden del fixture.
    club_foto: club_id de la franja. lado: "izquierda" o "derecha" (dónde va la foto). Guarda el PNG en
    ruta (925x1077) y la devuelve."""
    if lado not in LADOS:
        raise ValueError(f"lado debe ser {' o '.join(LADOS)}, no {lado!r}")
    panel = generar_panel(fecha, partidos, nombres_programacion(nombres))
    franja = Image.open(FRANJAS / f"{club_foto}.png").convert("RGB")
    if franja.size != FRANJA_TAM:
        raise ValueError(f"la franja de {club_foto} mide {franja.size}, se esperaba {FRANJA_TAM}")
    img = Image.new("RGB", (FRANJA_TAM[0] + PANEL_TAM[0], PANEL_TAM[1]))
    if lado == "izquierda":
        img.paste(franja, (0, 0))
        img.paste(panel, (FRANJA_TAM[0], 0))
    else:
        img.paste(panel, (0, 0))
        img.paste(franja, (PANEL_TAM[0], 0))
    img.save(ruta)
    return ruta
