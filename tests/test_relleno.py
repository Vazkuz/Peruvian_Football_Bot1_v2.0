from PIL import Image

from pfb.imagenes.relleno import rellenar_cuadrado

ROJO = (200, 30, 30)
BLANCO = (255, 255, 255)


def test_alineacion_queda_cuadrada_centrada_sobre_blanco(tmp_path):
    origen = tmp_path / "alineacion_local.png"
    Image.new("RGBA", (990, 1489), ROJO + (255,)).save(origen)
    antes = origen.read_bytes()
    destino = tmp_path / "alineacion_local_ig.png"

    assert rellenar_cuadrado(origen, destino) == destino
    with Image.open(destino) as img:
        img = img.convert("RGB")
        assert img.size == (1080, 1080)
        for esquina in ((0, 0), (1079, 0), (0, 1079), (1079, 1079)):
            assert img.getpixel(esquina) == BLANCO
        assert img.getpixel((540, 540)) == ROJO
        # escalada a ~718x1080 sin deformar: franjas blancas solo a los costados
        assert img.getpixel((540, 0)) == ROJO and img.getpixel((540, 1079)) == ROJO
        assert img.getpixel((180, 540)) == BLANCO and img.getpixel((900, 540)) == BLANCO
        assert img.getpixel((190, 540)) == ROJO and img.getpixel((889, 540)) == ROJO
    assert origen.read_bytes() == antes


def test_imagen_ancha_queda_con_franjas_arriba_y_abajo(tmp_path):
    origen = tmp_path / "ancha.png"
    Image.new("RGB", (1200, 600), ROJO).save(origen)
    destino = tmp_path / "ancha_ig.png"
    rellenar_cuadrado(origen, destino)
    with Image.open(destino) as img:
        assert img.size == (1080, 1080)
        assert img.getpixel((540, 100)) == BLANCO and img.getpixel((540, 540)) == ROJO
        assert img.getpixel((0, 540)) == ROJO
