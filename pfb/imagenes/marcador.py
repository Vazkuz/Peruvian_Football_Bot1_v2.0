"""Genera la imagen del marcador de un partido sobre assets/marcador_base - 2026.jpg.

La base y los escudos son arte fijo y no se modifican: el codigo solo escribe encima la fecha,
los clubes, los goles y los goleadores, y pega los escudos segun data/escudos.json.
"""

import json

from PIL import Image, ImageDraw, ImageFont

from pfb.imagenes.alineacion import RAIZ

BASE = RAIZ / "assets" / "marcador_base - 2026.jpg"
ESCUDOS = RAIZ / "assets" / "escudos"
MAPA_ESCUDOS = RAIZ / "data" / "escudos.json"
RUTA_COLORES = RAIZ / "data" / "colores_clubes.json"
FUENTE_REGULAR = RAIZ / "assets" / "fuentes" / "BarlowSemiCondensed-Regular.ttf"
FUENTE_BOLD = RAIZ / "assets" / "fuentes" / "BarlowSemiCondensed-Bold.ttf"

COLOR = (240, 240, 240)

# Medidas aprobadas por Daniel, en pixeles sobre la base de 1200x1200.
ESCUDO_CAJA = (94, 120)  # ancho, alto
ESCUDO_LOCAL = (928, 537)  # esquina superior izquierda de la caja
ESCUDO_VISITA = (557, 637)

FECHA_POS, FECHA_TAM = (1010, 68), 22  # centrada

GOLES_TAM = 60  # centrados
GOLES_LOCAL = (458, 618)
GOLES_VISITA = (1090, 703)

CLUB_TAM = 37  # tamano fijo; anclado a la izquierda y centrado verticalmente
CLUB_LOCAL, CLUB_LOCAL_ANCHO = (545, 618), 370
CLUB_VISITA, CLUB_VISITA_ANCHO = (672, 703), 355

GOLEADOR_TAM = 24  # anclados arriba a la izquierda; la linea i se corre (dx, dy) * i
GOLEADOR_LOCAL, GOLEADOR_LOCAL_PASO = (655, 542), (-10, -30)  # suben en escalera
GOLEADOR_VISITA, GOLEADOR_VISITA_PASO = (730, 750), (10, 30)  # bajan en escalera, fuera del panel blanco


def _leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def minuto_absoluto(evento):
    """1T = minuto; 2T = minuto + 45."""
    return evento["minuto"] if evento["tiempo"] == 1 else evento["minuto"] + 45


def fuente_club(nombre, ancho_max):
    """Barlow Semi Condensed Bold a CLUB_TAM. No se achica: si el nombre no entra, es un error."""
    fuente = ImageFont.truetype(str(FUENTE_BOLD), CLUB_TAM)
    ancho = fuente.getlength(nombre)
    if ancho > ancho_max:
        raise ValueError(f"el nombre {nombre!r} mide {ancho:.0f} px a tamaño {CLUB_TAM} y no entra "
                         f"en los {ancho_max} px de su celda")
    return fuente


def pegar_escudo(img, archivo, esquina):
    """Escalado sin deformarse dentro de ESCUDO_CAJA, centrado y con su transparencia.
    Si no hay archivo (null en el mapeo, o no existe), no se pega nada."""
    if not archivo or not (ESCUDOS / archivo).exists():
        return
    with Image.open(ESCUDOS / archivo) as original:
        escudo = original.convert("RGBA")
    caja_w, caja_h = ESCUDO_CAJA
    escala = min(caja_w / escudo.width, caja_h / escudo.height)
    escudo = escudo.resize((max(1, round(escudo.width * escala)), max(1, round(escudo.height * escala))),
                           Image.LANCZOS)
    x = esquina[0] + (caja_w - escudo.width) // 2
    y = esquina[1] + (caja_h - escudo.height) // 2
    img.paste(escudo, (x, y), escudo)


def generar_marcador(registro, salida):
    escudos = _leer_json(MAPA_ESCUDOS)
    nombres = {club_id: c["club"] for club_id, c in _leer_json(RUTA_COLORES).items()}
    with Image.open(BASE) as base:
        img = base.convert("RGB")
    d = ImageDraw.Draw(img)

    local, visita = registro["local"], registro["visita"]
    pegar_escudo(img, escudos.get(local["club_id"]), ESCUDO_LOCAL)
    pegar_escudo(img, escudos.get(visita["club_id"]), ESCUDO_VISITA)

    if registro.get("fecha") is not None:
        d.text(FECHA_POS, f"F E C H A    {registro['fecha']}", font=ImageFont.truetype(str(FUENTE_REGULAR), FECHA_TAM),
               fill=COLOR, anchor="mm")

    fuente_goles = ImageFont.truetype(str(FUENTE_BOLD), GOLES_TAM)
    d.text(GOLES_LOCAL, str(local["goles"]), font=fuente_goles, fill=COLOR, anchor="mm")
    d.text(GOLES_VISITA, str(visita["goles"]), font=fuente_goles, fill=COLOR, anchor="mm")

    for lado, pos, ancho in ((local, CLUB_LOCAL, CLUB_LOCAL_ANCHO), (visita, CLUB_VISITA, CLUB_VISITA_ANCHO)):
        nombre = nombres[lado["club_id"]].upper()
        d.text(pos, nombre, font=fuente_club(nombre, ancho), fill=COLOR, anchor="lm")

    fuente_goleador = ImageFont.truetype(str(FUENTE_REGULAR), GOLEADOR_TAM)
    for lado, (x0, y0), (dx, dy) in ((local, GOLEADOR_LOCAL, GOLEADOR_LOCAL_PASO),
                                     (visita, GOLEADOR_VISITA, GOLEADOR_VISITA_PASO)):
        goles = [e for e in registro["eventos"] if e["tipo"] == "gol" and e["club_id"] == lado["club_id"]]
        for i, e in enumerate(goles):  # los eventos del registro ya vienen en orden cronologico
            texto = f"{minuto_absoluto(e)}' {e['jugador']['nombre'].upper()}"
            d.text((x0 + dx * i, y0 + dy * i), texto, font=fuente_goleador, fill=COLOR, anchor="la")

    img.save(salida)
