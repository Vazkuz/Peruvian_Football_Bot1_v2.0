"""Arma las imagenes de la votacion 2 en assets/votacion_2/TAS/votacion_opcion_<n>.png.

Se corre a mano solo cuando cambia una foto: el bot usa las imagenes ya armadas.

Parte de assets/TAS.png (foto de arriba, Like con la mesa tachada y Me enoja con su foto) y en
el hueco del medio pega la foto de la opcion (assets/votacion_2/Opcion_<n>.<ext>) con el icono
de Me da risa encima. La base, las fotos y el icono no se modifican.

    python scripts/armar_votacion_2.py            # las 12
    python scripts/armar_votacion_2.py 7 12       # solo esas
"""

import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
BASE = RAIZ / "assets" / "TAS.png"
CARPETA_FOTOS = RAIZ / "assets" / "votacion_2"
CARPETA_SALIDA = CARPETA_FOTOS / "TAS"
ICONO_RISA = RAIZ / "assets" / "reacciones" / "me_da_risa.png"

OPCIONES = range(1, 13)
EXTENSIONES = (".jpg", ".jpeg", ".png")

# Medidas sobre la base de 720x606, tomadas del boceto de Daniel (15/10/2026).
FOTO_CAJA = (277, 435, 181, 140)  # x, y, ancho, alto; la foto entra sin deformarse, centrada
ICONO_POS = (268, 417)  # esquina superior izquierda del icono
ICONO_LADO = 90  # mismo tamano que el Like y el Me enoja de la base


def ruta_foto(n):
    for ext in EXTENSIONES:
        ruta = CARPETA_FOTOS / f"Opcion_{n}{ext}"
        if ruta.exists():
            return ruta
    return None


def armar(opcion, salida):
    ruta = ruta_foto(opcion)
    if ruta is None:
        raise FileNotFoundError(f"falta la foto de la opcion {opcion} en {CARPETA_FOTOS}")

    with Image.open(BASE) as base:
        img = base.convert("RGBA")

    with Image.open(ruta) as original:
        foto = original.convert("RGBA")
    x, y, caja_w, caja_h = FOTO_CAJA
    escala = min(caja_w / foto.width, caja_h / foto.height)
    foto = foto.resize((max(1, round(foto.width * escala)), max(1, round(foto.height * escala))),
                       Image.LANCZOS)
    img.paste(foto, (x + (caja_w - foto.width) // 2, y + (caja_h - foto.height) // 2), foto)

    with Image.open(ICONO_RISA) as original:
        icono = original.convert("RGBA").resize((ICONO_LADO, ICONO_LADO), Image.LANCZOS)
    img.paste(icono, ICONO_POS, icono)

    img.convert("RGB").save(salida)
    return salida


def main(args):
    opciones = [int(a) for a in args] or list(OPCIONES)
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    for n in opciones:
        salida = armar(n, CARPETA_SALIDA / f"votacion_opcion_{n}.png")
        print(f"opcion {n} -> {salida.relative_to(RAIZ)}")


if __name__ == "__main__":
    main(sys.argv[1:])
