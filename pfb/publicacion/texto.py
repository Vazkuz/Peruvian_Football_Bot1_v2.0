"""Textos de los posts (§6): partido y tabla. Sin red.

La negrita y la cursiva son letras Unicode (Mathematical Sans-Serif): Facebook no tiene formato
en posts de página. Unicode no tiene esas letras con tilde ni ñ, así que quedan igual.
"""

import unicodedata

from pfb.imagenes.nombres import corto
from pfb.motor.temporada import cargar_nombres

HASHTAG = "#PorLosMemesDeNuestroFutbol"
SANGRIA = "   "


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
