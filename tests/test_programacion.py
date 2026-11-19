"""Sorteos y texto de la programación de la fecha siguiente (§5.0d y §6, tarea 26)."""

from collections import Counter

from pfb.motor.partido import cargar_parametros
from pfb.motor.programacion import ganadores, sortear_foto
from pfb.publicacion.texto import HASHTAG, negrita, texto_programacion

PARAMS = cargar_parametros()
CLUBES = [str(n) for n in range(1, 19)]


def temporada(semilla=328888473):
    return {"semilla": semilla, "clubes": CLUBES}


def partido(fecha, local, goles_local, visita, goles_visita):
    return {"fecha": fecha, "local": {"club_id": local, "goles": goles_local},
            "visita": {"club_id": visita, "goles": goles_visita}}


REGISTROS = [
    partido(1, "1", 2, "2", 0),   # gana el local
    partido(1, "3", 1, "4", 3),   # gana la visita
    partido(1, "5", 1, "6", 1),   # empate
    partido(2, "7", 4, "8", 0),   # otra fecha
]


def test_ganadores_de_la_fecha():
    assert ganadores(REGISTROS, 1) == ["1", "4"]
    assert ganadores(REGISTROS, 2) == ["7"]
    assert ganadores(REGISTROS, 3) == []


def test_la_foto_es_de_un_ganador_de_la_fecha_anterior():
    for semilla in range(200):
        club, lado = sortear_foto(temporada(semilla), 2, REGISTROS, PARAMS)
        assert club in ("1", "4")
        assert lado in ("izquierda", "derecha")


def test_sin_ganadores_o_en_la_fecha_1_cualquier_club():
    empates = [partido(1, "1", 0, "2", 0)]
    vistos = {sortear_foto(temporada(s), 2, empates, PARAMS)[0] for s in range(300)}
    assert vistos <= set(CLUBES) and len(vistos) > 10
    vistos = {sortear_foto(temporada(s), 1, REGISTROS, PARAMS)[0] for s in range(300)}
    assert len(vistos) > 10


def test_no_repite_el_club_de_la_fecha_anterior():
    # en la fecha 2 ganan 1 y 4; en la 3, 1, 4 y 9
    registros = REGISTROS[:2] + [partido(2, "1", 1, "2", 0), partido(2, "3", 0, "4", 2), partido(2, "9", 3, "10", 0)]
    for semilla in range(300):
        t = temporada(semilla)
        assert sortear_foto(t, 3, registros, PARAMS)[0] != sortear_foto(t, 2, registros, PARAMS)[0]
        assert sortear_foto(t, 4, registros, PARAMS)[0] != sortear_foto(t, 3, registros, PARAMS)[0]


def test_si_es_el_unico_ganador_se_repite():
    registros = [partido(1, "1", 1, "2", 0), partido(2, "1", 2, "3", 0)]
    for semilla in range(50):
        t = temporada(semilla)
        assert sortear_foto(t, 2, registros, PARAMS)[0] == sortear_foto(t, 3, registros, PARAMS)[0] == "1"


def test_el_sorteo_se_repite_igual():
    assert sortear_foto(temporada(), 5, REGISTROS, PARAMS) == sortear_foto(temporada(), 5, REGISTROS, PARAMS)


def test_lado_mitad_y_mitad():
    lados = Counter(sortear_foto(temporada(s), 2, REGISTROS, PARAMS)[1] for s in range(2000))
    assert 900 < lados["izquierda"] < 1100


def test_texto_programacion():
    assert texto_programacion(2) == "\n\n".join([
        negrita("FIXTURE PARA LA FECHA 2"),
        "Acabada la Fecha 1, te presentamos la programación del día de mañana para que no te pierdas de tu "
        "partido favorito.",
        HASHTAG,
        "*Los horarios pueden estar sujetos a cambios",
    ])
