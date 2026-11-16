"""Imagen del resultado de la Fecha FIFA (§13.1)."""

from PIL import Image, ImageDraw

from pfb.imagenes.fecha_fifa import (BANDERA, BANDERAS, NOMBRE_ANCHO_MAX, NOMBRE_TAM, X_LOCAL, X_VISITA, _ancho,
                                     generar_fecha_fifa, lineas_nombre, y_bandera)
from pfb.motor.fecha_fifa import cargar_selecciones

SELECCIONES = cargar_selecciones()
NOMBRES = {k: v["nombre"] for k, v in SELECCIONES.items()}


def lienzo():
    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


def fifa(local, visita, goles=(2, 1)):
    return {"local": {"seleccion": local, "goles": goles[0]}, "visita": {"seleccion": visita, "goles": goles[1]}}


def test_todas_las_selecciones_tienen_bandera():
    assert all((BANDERAS / f"{codigo}.png").exists() for codigo in SELECCIONES)


def test_todos_los_nombres_entran():
    d = lienzo()
    for nombre in NOMBRES.values():
        lineas, tam = lineas_nombre(d, nombre)
        assert 1 <= len(lineas) <= 2
        assert max(_ancho(d, linea, tam) for linea in lineas) <= NOMBRE_ANCHO_MAX, nombre


def test_nombre_corto_en_una_linea_y_largo_en_dos():
    d = lienzo()
    assert lineas_nombre(d, "Perú") == (["PERÚ"], NOMBRE_TAM)
    assert lineas_nombre(d, "Estados Unidos") == (["ESTADOS", "UNIDOS"], NOMBRE_TAM)
    lineas, tam = lineas_nombre(d, "San Vicente y las Granadinas")
    assert len(lineas) == 2 and tam < NOMBRE_TAM


def test_imagen_del_tamano_de_la_base(tmp_path):
    ruta = generar_fecha_fifa(fifa("PER", "ARG"), NOMBRES, tmp_path / "f.png")
    assert Image.open(ruta).size == (1080, 1077)


def rojo_en(img, cx):
    """El color de la franja izquierda de la bandera centrada en cx (la de Perú es roja)."""
    y = y_bandera(ImageDraw.Draw(img)) + BANDERA[1] // 2
    r, g, b = img.getpixel((cx - BANDERA[0] // 2 + 10, y))
    return r > 180 and g < 80 and b < 80


def test_el_local_va_a_la_izquierda(tmp_path):
    local = Image.open(generar_fecha_fifa(fifa("PER", "ARG"), NOMBRES, tmp_path / "a.png")).convert("RGB")
    visita = Image.open(generar_fecha_fifa(fifa("ARG", "PER"), NOMBRES, tmp_path / "b.png")).convert("RGB")
    assert rojo_en(local, X_LOCAL) and not rojo_en(local, X_VISITA)
    assert rojo_en(visita, X_VISITA) and not rojo_en(visita, X_LOCAL)


def test_espacio_igual_arriba_y_abajo():
    from pfb.imagenes.fecha_fifa import BORDE, PANEL_FIN, TEXTO_FIN, DIST_NOMBRES, _fuente
    d = lienzo()
    y = y_bandera(d)
    f = _fuente(NOMBRE_TAM)
    medio_alto = max((d.textbbox((0, 0), t, font=f)[3] - d.textbbox((0, 0), t, font=f)[1]) / 2
                     for t in ("PERÚ", "ARGENTINA"))       # como el mockup aprobado
    fondo = y + BANDERA[1] + DIST_NOMBRES + medio_alto
    assert abs(((y - BORDE) - TEXTO_FIN) - (PANEL_FIN - fondo)) <= 1
