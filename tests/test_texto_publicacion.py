"""Textos de los posts (§6), contra las plantillas aprobadas por Daniel."""

from pfb.publicacion.texto import (COMENTARIO_INSTAGRAM, negrita, negrita_cursiva, sin_tildes, texto_partido,
                                   texto_tabla)

NOMBRES = {
    "17479": "Alianza Atlético",
    "grau": "Atlético Grau",
    "1450": "Sporting Cristal",
    "2734": "Melgar",
    "boys": "Sport Boys",
    "cienciano": "Cienciano",
}


def gol(club_id, nombre, tiempo, minuto, penal=False):
    return {"tipo": "gol", "club_id": club_id, "jugador": {"id": nombre, "nombre": nombre},
            "tiempo": tiempo, "minuto": minuto, "penal": penal}


def registro(local, visita, eventos, fin=None):
    def lado(club_id):
        return {"club_id": club_id, "goles": sum(e["tipo"] == "gol" and e["club_id"] == club_id for e in eventos)}
    return {"local": lado(local), "visita": lado(visita), "eventos": eventos, "fin": fin}


FIN = {"tiempo": 2, "minuto": 31, "club_id": "cienciano"}


def test_negrita_y_cursiva():
    assert negrita("Ab9 ¡é!") == "𝗔𝗯𝟵 ¡é!"
    assert negrita_cursiva("Ab9 ñ") == "𝘼𝙗9 ñ"
    assert sin_tildes("Atlético Ñandú") == "Atletico Nandu"


def test_normal_goles_de_los_dos_y_penal():
    reg = registro("17479", "grau", [
        gol("17479", "Juan Uno", 1, 12),
        gol("grau", "José Tres", 2, 5),
        gol("17479", "Juan Dos", 2, 30, penal=True),
    ])
    assert texto_partido(reg, NOMBRES) == (
        "¡𝗙𝗶𝗻𝗮𝗹 𝗱𝗲𝗹 𝗽𝗮𝗿𝘁𝗶𝗱𝗼!\n"
        "\n"
        "𝗔𝗹𝗶𝗮𝗻𝘇𝗮 𝗔𝘁𝗹𝗲𝘁𝗶𝗰𝗼 𝟮 - 𝟭 𝗔𝘁𝗹𝗲𝘁𝗶𝗰𝗼 𝗚𝗿𝗮𝘂\n"
        "\n"
        "𝗚𝗼𝗹𝗲𝘀:\n"
        "Alianza Atlético:\n"
        "   1) J. Uno 12' 1T\n"
        "   2) J. Dos 30' 2T (P)\n"
        "\n"
        "Atlético Grau:\n"
        "   1) J. Tres 5' 2T\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_solo_marca_la_visita():
    reg = registro("2734", "1450", [gol("1450", "Ana Cuatro", 1, 40), gol("1450", "Ana Cinco", 2, 44)])
    assert texto_partido(reg, NOMBRES) == (
        "¡𝗙𝗶𝗻𝗮𝗹 𝗱𝗲𝗹 𝗽𝗮𝗿𝘁𝗶𝗱𝗼!\n"
        "\n"
        "𝗠𝗲𝗹𝗴𝗮𝗿 𝟬 - 𝟮 𝗦𝗽𝗼𝗿𝘁𝗶𝗻𝗴 𝗖𝗿𝗶𝘀𝘁𝗮𝗹\n"
        "\n"
        "𝗚𝗼𝗹𝗲𝘀:\n"
        "Sporting Cristal:\n"
        "   1) A. Cuatro 40' 1T\n"
        "   2) A. Cinco 44' 2T\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_un_solo_gol_de_un_solo_equipo():
    reg = registro("cienciano", "17479", [gol("cienciano", "Pedro Siete", 2, 21, penal=True)])
    assert texto_partido(reg, NOMBRES) == (
        "¡𝗙𝗶𝗻𝗮𝗹 𝗱𝗲𝗹 𝗽𝗮𝗿𝘁𝗶𝗱𝗼!\n"
        "\n"
        "𝗖𝗶𝗲𝗻𝗰𝗶𝗮𝗻𝗼 𝟭 - 𝟬 𝗔𝗹𝗶𝗮𝗻𝘇𝗮 𝗔𝘁𝗹𝗲𝘁𝗶𝗰𝗼\n"
        "\n"
        "𝗚𝗼𝗹𝗲𝘀:\n"
        "Cienciano:\n"
        "   1) P. Siete 21' 2T (P)\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_cero_a_cero():
    reg = registro("1450", "2734", [{"tipo": "amarilla", "club_id": "1450"}])
    assert texto_partido(reg, NOMBRES) == (
        "¡𝗙𝗶𝗻𝗮𝗹 𝗱𝗲𝗹 𝗽𝗮𝗿𝘁𝗶𝗱𝗼!\n"
        "\n"
        "𝗦𝗽𝗼𝗿𝘁𝗶𝗻𝗴 𝗖𝗿𝗶𝘀𝘁𝗮𝗹 𝟬 - 𝟬 𝗠𝗲𝗹𝗴𝗮𝗿\n"
        "\n"
        "Sin goles\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_suspendido_con_goles():
    reg = registro("boys", "cienciano", [gol("boys", "Juan Uno", 1, 12), gol("boys", "Juan Dos", 2, 30)], fin=FIN)
    assert texto_partido(reg, NOMBRES) == (
        "¡𝙋𝙖𝙧𝙩𝙞𝙙𝙤 𝙨𝙪𝙨𝙥𝙚𝙣𝙙𝙞𝙙𝙤 𝙥𝙤𝙧 𝙚𝙭𝙘𝙚𝙨𝙤 𝙙𝙚 𝙧𝙤𝙟𝙖𝙨!\n"
        "\n"
        "Resultado Final:\n"
        "\n"
        "𝗦𝗽𝗼𝗿𝘁 𝗕𝗼𝘆𝘀 𝟮 - 𝟬 𝗖𝗶𝗲𝗻𝗰𝗶𝗮𝗻𝗼\n"
        "\n"
        "𝗚𝗼𝗹𝗲𝘀:\n"
        "Sport Boys:\n"
        "   1) J. Uno 12' 1T\n"
        "   2) J. Dos 30' 2T\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_suspendido_cero_a_cero():
    reg = registro("boys", "cienciano", [], fin=FIN)
    assert texto_partido(reg, NOMBRES) == (
        "¡𝙋𝙖𝙧𝙩𝙞𝙙𝙤 𝙨𝙪𝙨𝙥𝙚𝙣𝙙𝙞𝙙𝙤 𝙥𝙤𝙧 𝙚𝙭𝙘𝙚𝙨𝙤 𝙙𝙚 𝙧𝙤𝙟𝙖𝙨!\n"
        "\n"
        "Resultado Final:\n"
        "\n"
        "𝗦𝗽𝗼𝗿𝘁 𝗕𝗼𝘆𝘀 𝟬 - 𝟬 𝗖𝗶𝗲𝗻𝗰𝗶𝗮𝗻𝗼\n"
        "\n"
        "Sin goles\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_club_con_tilde():
    reg = registro("grau", "2734", [gol("grau", "Luis Seis", 1, 3)])
    texto = texto_partido(reg, NOMBRES)
    assert "𝗔𝘁𝗹𝗲𝘁𝗶𝗰𝗼 𝗚𝗿𝗮𝘂 𝟭 - 𝟬 𝗠𝗲𝗹𝗴𝗮𝗿" in texto
    assert "\nAtlético Grau:\n" in texto
    assert "é" not in texto.split("\n")[2]


def test_nombre_del_jugador_corto():
    reg = registro("2734", "1450", [gol("2734", "Ángel de la Cruz", 2, 7), gol("2734", "Cristiano", 2, 9)])
    texto = texto_partido(reg, NOMBRES)
    assert "\n   1) A. De La Cruz 7' 2T\n" in texto
    assert "\n   2) Cristiano 9' 2T\n" in texto


def test_sin_nombres_usa_colores_clubes():
    reg = registro("17479", "1450", [])
    assert "𝗔𝗹𝗶𝗮𝗻𝘇𝗮 𝗔𝘁𝗹𝗲𝘁𝗶𝗰𝗼 𝟬 - 𝟬 𝗦𝗽𝗼𝗿𝘁𝗶𝗻𝗴 𝗖𝗿𝗶𝘀𝘁𝗮𝗹" in texto_partido(reg)


def test_texto_tabla():
    assert texto_tabla(7) == (
        "¡𝗛𝗮 𝘁𝗲𝗿𝗺𝗶𝗻𝗮𝗱𝗼 𝗹𝗮 𝗳𝗲𝗰𝗵𝗮 𝟳 𝗱𝗲𝗹 𝗕𝗼𝘁 𝟭 𝗧𝗲 𝗔𝗽𝗲𝘀𝘁𝗼!\n"
        "\n"
        "Mira la tabla de posiciones actualizada aquí.\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )
    assert texto_tabla(12) == (
        "¡𝗛𝗮 𝘁𝗲𝗿𝗺𝗶𝗻𝗮𝗱𝗼 𝗹𝗮 𝗳𝗲𝗰𝗵𝗮 𝟭𝟮 𝗱𝗲𝗹 𝗕𝗼𝘁 𝟭 𝗧𝗲 𝗔𝗽𝗲𝘀𝘁𝗼!\n"
        "\n"
        "Mira la tabla de posiciones actualizada aquí.\n"
        "\n"
        "#PorLosMemesDeNuestroFutbol"
    )


def test_sin_tabs_ni_espacios_al_final():
    textos = [
        texto_partido(registro("17479", "grau", [gol("17479", "Juan Uno", 1, 12, penal=True),
                                                  gol("grau", "José Tres", 2, 5)]), NOMBRES),
        texto_partido(registro("1450", "2734", []), NOMBRES),
        texto_partido(registro("boys", "cienciano", [gol("boys", "Juan Uno", 1, 12)], fin=FIN), NOMBRES),
        texto_tabla(7),
    ]
    for texto in textos:
        assert "\t" not in texto
        assert all(linea == linea.rstrip() for linea in texto.split("\n"))


def test_comentario_instagram():
    assert COMENTARIO_INSTAGRAM == (
        "¿Te paltea que tu viejita que tienes agregada a Facebook te vea dándole like a huevadas como "
        "esta? Entonces ve a seguirnos en Instagram https://www.instagram.com/pfbot.1/"
    )
    assert "\n" not in COMENTARIO_INSTAGRAM and "\r" not in COMENTARIO_INSTAGRAM
