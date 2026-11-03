"""Textos de los posts (§6 y §13.1), contra las plantillas aprobadas por Daniel."""

from pfb.publicacion.texto import (COMENTARIO_INSTAGRAM, HASHTAG, TEXTOS_RANDOM, caption_votacion, negrita,
                                   negrita_cursiva, opciones_votacion, sin_tildes, texto_partido, texto_random,
                                   texto_tabla, texto_votacion)

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


# --- Votaciones (§13.1) ---

def con_votacion(votacion, local="2734", visita="1450"):
    r = registro(local, visita, [])
    r["votacion"] = votacion
    return r


def test_post_de_mesa():
    r = con_votacion({"tipo": "mesa", "opcion": 1})
    assert texto_votacion(r, NOMBRES) == (
        "PROBLEMAS EN MESA!\n\n"
        "Se presentaron reclamos por el último partido (Melgar vs Sporting Cristal), reacciona para votar el "
        "resultado del reclamo\n\n"
        "👍 No procede\n"
        "😂 El presidente de la federación está amañado con ambos equipos, por lo que el partido acaba en un "
        "empate 1-1\n"
        "😡 Que se repita el partido\n\n"
        "#PorLosMemesDeNuestroFutbol")


def test_post_de_sancion_con_nombre_completo():
    r = con_votacion({"tipo": "sancion", "club_id": "17479", "casilla": 4,
                      "jugador": {"id": "1", "nombre": "Ángel de la Cruz"}}, local="17479")
    assert texto_votacion(r, NOMBRES) == ("¿Cuántas fechas de sanción se lleva el jugador Ángel de la Cruz del "
                                          "Alianza Atlético?\n\n#PorLosMemesDeNuestroFutbol")
    assert opciones_votacion(r, NOMBRES) == ["❤️ 1 fecha", "😡 2 fechas", "😢 3 fechas", "😂 4 fechas"]


def test_caption_de_instagram():
    for v in ({"tipo": "mesa", "opcion": 5},
              {"tipo": "sancion", "club_id": "2734", "casilla": 4, "jugador": {"id": "1", "nombre": "X Y"}}):
        r = con_votacion(v)
        assert caption_votacion(r, NOMBRES) == "VOTA REACCIONANDO EN LOS COMENTARIOS!\n\n" + texto_votacion(r, NOMBRES)


def test_comentarios_de_mesa():
    r = con_votacion({"tipo": "mesa", "opcion": 11})
    assert opciones_votacion(r, NOMBRES) == [
        "👍 No procede", "😂 Un huaico se llevó el arco de Sporting Cristal. La FPF decreta empate 2-2",
        "😡 Que se repita el partido"]


def test_las_12_random_con_nombres():
    assert sorted(TEXTOS_RANDOM) == list(range(1, 13))
    esperados = {
        2: "Encontraron al goleador de Sporting Cristal amañando el partido en Apesta Potal, por lo que Melgar gana "
           "el partido 3-0",
        3: "El arquero de Melgar salió positivo en el doping, Sporting Cristal gana el partido",
        4: "La barra brava de Sporting Cristal ajustó al presidente de la federación, por lo que Sporting Cristal "
           "gana en mesa por 1-0",
        6: "El Congreso dictamina que Melgar merece campeonar este año, por lo que obliga a la FPF a darlo como "
           "ganador con un marcador de 2-1",
        8: "El FREPAP gana las elecciones y predice que si Melgar y Sporting Cristal no empatan este partido por "
           "1-1, el fin del mundo se acercará.",
        9: "El VAR de Melgar estaba desconectado porque usaron las pantallas para meterle un dotita. Los goles "
           "fueron anulados y queda 0-0",
        12: "El árbitro confesó en TikTok que es hincha de Melgar. Sporting Cristal gana 3-0",
    }
    for n in range(1, 13):
        v = {"tipo": "mesa", "opcion": n}
        if n == 10:
            v["equipo"] = "1450"
        texto = texto_random(con_votacion(v), NOMBRES)
        assert "{" not in texto and "<" not in texto
        if n in esperados:
            assert texto == esperados[n]


def test_random_10_nombra_al_equipo_sorteado():
    for equipo, nombre in (("2734", "Melgar"), ("1450", "Sporting Cristal")):
        r = con_votacion({"tipo": "mesa", "opcion": 10, "equipo": equipo})
        assert texto_random(r, NOMBRES) == (f"La FPF perdió el acta del partido y como es {nombre} a nadie le "
                                            "importa. El resultado queda en 1-1")


def test_votacion_termina_con_hashtag():
    assert texto_votacion(con_votacion({"tipo": "mesa", "opcion": 7}), NOMBRES).endswith("\n\n" + HASHTAG)
