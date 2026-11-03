"""Textos de los posts (§6 y §13.1): partido, tabla y votaciones. Sin red.

La negrita y la cursiva son letras Unicode (Mathematical Sans-Serif): Facebook no tiene formato
en posts de página. Unicode no tiene esas letras con tilde ni ñ, así que quedan igual.
"""

import unicodedata

from pfb.imagenes.nombres import corto
from pfb.motor.temporada import cargar_nombres

HASHTAG = "#PorLosMemesDeNuestroFutbol"
SANGRIA = "   "
COMENTARIO_INSTAGRAM = ("¿Te paltea que tu viejita que tienes agregada a Facebook te vea dándole like a huevadas "
                        "como esta? Entonces ve a seguirnos en Instagram https://www.instagram.com/pfbot.1/")


def _convertir(texto, mayuscula, minuscula, digito=None):
    salida = []
    for ch in texto:
        if "A" <= ch <= "Z":
            salida.append(chr(mayuscula + ord(ch) - ord("A")))
        elif "a" <= ch <= "z":
            salida.append(chr(minuscula + ord(ch) - ord("a")))
        elif digito is not None and "0" <= ch <= "9":
            salida.append(chr(digito + ord(ch) - ord("0")))
        else:
            salida.append(ch)
    return "".join(salida)


def negrita(texto):
    """A-Z, a-z y 0-9 en Mathematical Sans-Serif Bold."""
    return _convertir(texto, 0x1D5D4, 0x1D5EE, 0x1D7EC)


def negrita_cursiva(texto):
    """A-Z y a-z en Mathematical Sans-Serif Bold Italic."""
    return _convertir(texto, 0x1D63C, 0x1D656)


def sin_tildes(texto):
    return "".join(ch for ch in unicodedata.normalize("NFD", texto) if not unicodedata.combining(ch))


def _bloque_goles(registro, club_id, nombre):
    lineas = [f"{nombre}:"]
    goles = [e for e in registro["eventos"] if e["tipo"] == "gol" and e["club_id"] == club_id]
    for n, e in enumerate(goles, start=1):
        linea = f"{SANGRIA}{n}) {corto(e['jugador']['nombre'])} {e['minuto']}' {e['tiempo']}T"
        if e.get("penal"):
            linea += " (P)"
        lineas.append(linea)
    return "\n".join(lineas)


def texto_partido(registro, nombres=None):
    """Texto del post del partido. nombres = {club_id: nombre corto}."""
    if nombres is None:
        nombres = cargar_nombres()
    local, visita = registro["local"], registro["visita"]
    nombre_local, nombre_visita = nombres[local["club_id"]], nombres[visita["club_id"]]

    if registro["fin"] is None:
        bloques = [negrita("¡Final del partido!")]
    else:
        bloques = [negrita_cursiva("¡Partido suspendido por exceso de rojas!"), "Resultado Final:"]

    bloques.append(negrita(sin_tildes(f"{nombre_local} {local['goles']} - {visita['goles']} {nombre_visita}")))

    goles = [
        _bloque_goles(registro, lado["club_id"], nombre)
        for lado, nombre in ((local, nombre_local), (visita, nombre_visita))
        if lado["goles"]
    ]
    if goles:
        bloques.append(negrita("Goles:") + "\n" + "\n\n".join(goles))
    else:
        bloques.append("Sin goles")

    bloques.append(HASHTAG)
    return "\n\n".join(bloques)


def texto_tabla(fecha):
    """Texto del post de la tabla al cerrar la fecha."""
    return "\n\n".join([
        negrita(f"¡Ha terminado la fecha {fecha} del Bot 1 Te Apesto!"),
        "Mira la tabla de posiciones actualizada aquí.",
        HASHTAG,
    ])


# --- Votaciones (§13.1) ---

VOTA_INSTAGRAM = "VOTA REACCIONANDO EN LOS COMENTARIOS!"

# Cosas random de la votación 2, tal cual. {local} y {visita} = nombres de los equipos; {equipo} = el
# equipo que sorteó la votación (solo la 10).
TEXTOS_RANDOM = {
    1: "El presidente de la federación está amañado con ambos equipos, por lo que el partido acaba en un empate 1-1",
    2: "Encontraron al goleador de {visita} amañando el partido en Apesta Potal, por lo que {local} gana el partido 3-0",
    3: "El arquero de {local} salió positivo en el doping, {visita} gana el partido",
    4: "La barra brava de {visita} ajustó al presidente de la federación, por lo que {visita} gana en mesa por 1-0",
    5: ("El TAS resuelve que {visita} debía dinero por la construcción de su estadio. De todos modos, esto no "
        "impacta en el resultado del partido, que se mantiene"),
    6: ("El Congreso dictamina que {local} merece campeonar este año, por lo que obliga a la FPF a darlo como "
        "ganador con un marcador de 2-1"),
    7: "Aliens han sido contactados por primera vez, e indican que el partido debe mantener su score o nos invadirán",
    8: ("El FREPAP gana las elecciones y predice que si {local} y {visita} no empatan este partido por 1-1, el fin "
        "del mundo se acercará."),
    9: ("El VAR de {local} estaba desconectado porque usaron las pantallas para meterle un dotita. Los goles fueron "
        "anulados y queda 0-0"),
    10: "La FPF perdió el acta del partido y como es {equipo} a nadie le importa. El resultado queda en 1-1",
    11: "Un huaico se llevó el arco de {visita}. La FPF decreta empate 2-2",
    12: "El árbitro confesó en TikTok que es hincha de {local}. {visita} gana 3-0",
}

OPCIONES_SANCION = ["❤️ 1 fecha", "😡 2 fechas", "😢 3 fechas", "😂 4 fechas"]


def texto_random(registro, nombres=None):
    """Texto de la cosa random que salió en la votación 2, con los nombres puestos."""
    if nombres is None:
        nombres = cargar_nombres()
    votacion = registro["votacion"]
    return TEXTOS_RANDOM[votacion["opcion"]].format(
        local=nombres[registro["local"]["club_id"]],
        visita=nombres[registro["visita"]["club_id"]],
        equipo=nombres[votacion["equipo"]] if "equipo" in votacion else "",
    )


def opciones_votacion(registro, nombres=None):
    """Una línea por opción, con su emoji: van al final del post de Facebook (mesa) y como
    comentarios en Instagram (mesa y sanción)."""
    if registro["votacion"]["tipo"] == "sancion":
        return list(OPCIONES_SANCION)
    return ["👍 No procede", f"😂 {texto_random(registro, nombres)}", "😡 Que se repita el partido"]


def texto_votacion(registro, nombres=None):
    """Texto del post de la votación en Facebook. registro["votacion"] no puede ser None."""
    if nombres is None:
        nombres = cargar_nombres()
    votacion = registro["votacion"]
    if votacion["tipo"] == "sancion":
        bloques = [f"¿Cuántas fechas de sanción se lleva el jugador {votacion['jugador']['nombre']} "
                   f"del {nombres[votacion['club_id']]}?"]
    else:
        local, visita = nombres[registro["local"]["club_id"]], nombres[registro["visita"]["club_id"]]
        bloques = [
            "PROBLEMAS EN MESA!",
            f"Se presentaron reclamos por el último partido ({local} vs {visita}), reacciona para votar el "
            "resultado del reclamo",
            "\n".join(opciones_votacion(registro, nombres)),
        ]
    bloques.append(HASHTAG)
    return "\n\n".join(bloques)


def caption_votacion(registro, nombres=None):
    """Caption del post de la votación en Instagram: el aviso al comienzo y luego el texto de Facebook."""
    return f"{VOTA_INSTAGRAM}\n\n{texto_votacion(registro, nombres)}"
