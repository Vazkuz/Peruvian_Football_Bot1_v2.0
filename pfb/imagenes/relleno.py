"""Relleno a cuadrado para Instagram: la imagen escalada sin deformar, centrada sobre blanco.

Genera un archivo nuevo; la imagen de origen no se modifica.
"""

from PIL import Image

BLANCO = (255, 255, 255)


def rellenar_cuadrado(origen, destino, lado=1080):
    """Escala `origen` para que su lado mayor mida `lado`, la centra sobre un lienzo blanco de
    lado x lado y la guarda en `destino`."""
    with Image.open(origen) as original:
        img = original.convert("RGBA")
    escala = lado / max(img.size)
    img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)
    lienzo = Image.new("RGB", (lado, lado), BLANCO)
    lienzo.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2), img)
    lienzo.save(destino)
    return destino
