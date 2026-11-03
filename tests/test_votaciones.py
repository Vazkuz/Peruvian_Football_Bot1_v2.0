import json
import random

import pytest

from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import cargar_plantilla
from pfb.motor.temporada import cargar_registros, jugar_siguiente, nueva_temporada
from pfb.motor.votaciones import expulsados, generador, hubo_perdedor, sortear_votacion


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


def roja(club, casilla, jugador_id, doble=False):
    return {"tipo": "roja", "club_id": club, "casilla": casilla, "doble_amarilla": doble,
            "jugador": {"id": jugador_id, "nombre": f"Jugador {jugador_id}"}}


def reg(goles_local, goles_visita, eventos=(), semilla=1):
    return {"partido_id": "F01-P1", "fecha": 1, "semilla": semilla,
            "local": {"club_id": "A", "goles": goles_local}, "visita": {"club_id": "B", "goles": goles_visita},
            "eventos": list(eventos)}


def con_prob(params, sancion, mesa):
    return {**params, "votaciones": {"sancion": sancion, "mesa": mesa}}


# --- piezas ---

def test_parametros_de_13_1(params):
    assert params["votaciones"] == {"sancion": 0.05, "mesa": 0.05}


def test_expulsados_sin_repetir_y_con_doble_amarilla():
    r = reg(1, 0, [roja("A", 4, "1"), roja("B", 7, "2", doble=True), roja("A", 4, "1")])
    assert [(e["club_id"], e["casilla"], e["jugador"]["id"]) for e in expulsados(r)] == [("A", 4, "1"), ("B", 7, "2")]


def test_expulsados_sin_las_casillas_bloqueadas():
    r = reg(1, 0, [roja("A", 4, "1"), roja("B", 7, "2")])
    assert [e["jugador"]["id"] for e in expulsados(r, {("A", 4)})] == ["2"]


def test_perdedor():
    assert hubo_perdedor(reg(2, 1)) and hubo_perdedor(reg(0, 3)) and not hubo_perdedor(reg(1, 1))


def test_generador_no_es_el_del_partido():
    r = reg(1, 0, semilla=123)
    assert generador(r).random() != random.Random(123).random()
    assert generador(r).random() == generador(r).random()


# --- sorteo ---

def test_tope_uno_por_fecha(params):
    r = reg(2, 0, [roja("A", 4, "1")])
    assert sortear_votacion(r, con_prob(params, 1, 1), hubo_votacion_en_la_fecha=True) is None


def test_sancion_va_primero(params):
    r = reg(2, 0, [roja("A", 4, "1")])
    v = sortear_votacion(r, con_prob(params, 1, 1), False)
    assert v == {"tipo": "sancion", "club_id": "A", "casilla": 4, "jugador": {"id": "1", "nombre": "Jugador 1"}}


def test_si_no_sale_la_sancion_se_sortea_la_mesa(params):
    r = reg(2, 0, [roja("A", 4, "1")])
    v = sortear_votacion(r, con_prob(params, 0, 1), False, elegir=lambda rng: 9)
    assert v == {"tipo": "mesa", "opcion": 9}


def test_sin_roja_no_hay_sancion(params):
    assert sortear_votacion(reg(1, 1), con_prob(params, 1, 0), False) is None


def test_sin_perdedor_no_hay_mesa(params):
    assert sortear_votacion(reg(1, 1), con_prob(params, 0, 1), False) is None


def test_solo_casillas_bloqueadas_no_hay_sancion(params):
    r = reg(1, 1, [roja("A", 4, "1")])
    assert sortear_votacion(r, con_prob(params, 1, 0), False, casillas_bloqueadas={("A", 4)}) is None


def test_mesa_sortea_entre_las_12(params):
    vistas = {sortear_votacion(reg(1, 0, semilla=s), con_prob(params, 0, 1), False)["opcion"] for s in range(300)}
    assert vistas == set(range(1, 13))


def test_sancion_sortea_entre_los_expulsados(params):
    eventos = [roja("A", 4, "1"), roja("B", 7, "2"), roja("A", 9, "3", doble=True)]
    vistos = {sortear_votacion(reg(1, 1, eventos, semilla=s), con_prob(params, 1, 0), False)["jugador"]["id"]
              for s in range(100)}
    assert vistos == {"1", "2", "3"}


def test_probabilidades_aproximadas(params):
    # 5 % con roja; sin roja, 5 % de mesa si hay perdedor
    n = 20000
    sancion = sum(sortear_votacion(reg(1, 1, [roja("A", 4, "1")], semilla=s), params, False) is not None
                  for s in range(n))
    mesa = sum(sortear_votacion(reg(1, 0, semilla=s), params, False) is not None for s in range(n))
    assert abs(sancion / n - 0.05) < 0.01
    assert abs(mesa / n - 0.05) < 0.01


def test_mismo_registro_mismo_resultado(params):
    r = reg(2, 0, [roja("A", 4, "1"), roja("B", 7, "2")], semilla=77)
    p = con_prob(params, 0.5, 0.5)
    assert sortear_votacion(r, p, False) == sortear_votacion(r, p, False)


# --- en la temporada ---

def test_temporada_tope_y_registro(params, tmp_path):
    p = con_prob(params, 0.5, 0.5)  # alto para que salgan varias
    nueva_temporada("t", semilla=5, base=tmp_path)
    for _ in range(9 * 6):
        jugar_siguiente("t", p, base=tmp_path)
    registros = cargar_registros("t", base=tmp_path)
    assert all("votacion" in r for r in registros)
    por_fecha = {}
    for r in registros:
        por_fecha.setdefault(r["fecha"], []).append(r["votacion"])
    for votos in por_fecha.values():
        assert sum(v is not None for v in votos) <= 1
    assert any(v is not None for votos in por_fecha.values() for v in votos)
    for r in registros:
        v = r["votacion"]
        if v and v["tipo"] == "sancion":
            assert any(e["tipo"] == "roja" and e["jugador"]["id"] == v["jugador"]["id"] for e in r["eventos"])
        if v and v["tipo"] == "mesa":
            assert r["local"]["goles"] != r["visita"]["goles"]


def test_el_sorteo_no_toca_el_partido(params):
    # el partido sale de su propia semilla; el sorteo no lo modifica ni consume su generador
    local, visita = cargar_plantilla("184"), cargar_plantilla("6593")
    sin = {"ult_res": None, "g5": None}
    for semilla in range(30):
        registro = simular_partido(params, local, visita, sin, sin, semilla=semilla)
        antes = json.dumps(registro, sort_keys=True)
        sortear_votacion(registro, con_prob(params, 1, 1), False)
        assert json.dumps(registro, sort_keys=True) == antes
        assert antes == json.dumps(simular_partido(params, local, visita, sin, sin, semilla=semilla), sort_keys=True)


# --- suspensiones (tanda 2) ---

from pfb.motor.plantillas import con_suspendidos  # noqa: E402
from pfb.motor.temporada import _escribir_json, carpeta_temporada, casillas_bloqueadas, sanciones, suspendidos  # noqa: E402


def sancion(fecha, club, casilla, jugador_id, fechas=None, numero=1, local="A", visita="B"):
    r = reg(1, 0, [roja(club, casilla, jugador_id)])
    r.update(partido_id=f"F{fecha:02d}-P{numero}", fecha=fecha, estado="jugado")
    r["local"]["club_id"], r["visita"]["club_id"] = local, visita
    r["votacion"] = {"tipo": "sancion", "club_id": club, "casilla": casilla,
                     "jugador": {"id": jugador_id, "nombre": "X"}, **({"fechas": fechas} if fechas else {})}
    return r


def jugado(fecha, local, visita, numero=1):
    r = reg(0, 0)
    r.update(partido_id=f"F{fecha:02d}-P{numero}", fecha=fecha, estado="jugado", votacion=None)
    r["local"]["club_id"], r["visita"]["club_id"] = local, visita
    return r


def test_con_suspendidos_titular():
    p = cargar_plantilla("184")
    c = p.casillas[4]
    nueva, bloqueadas = con_suspendidos(p, {c.numero: c.titular.id})
    assert nueva.casillas[4].titular == c.suplente
    assert bloqueadas == {c.numero}
    assert [x for i, x in enumerate(nueva.casillas) if i != 4] == [x for i, x in enumerate(p.casillas) if i != 4]


def test_con_suspendidos_suplente():
    p = cargar_plantilla("184")
    c = p.casillas[7]
    nueva, bloqueadas = con_suspendidos(p, {c.numero: c.suplente.id})
    assert nueva.casillas[7].titular == c.titular
    assert bloqueadas == {c.numero}


def test_casilla_bloqueada_no_tiene_cambios(params):
    local, visita = cargar_plantilla("184"), cargar_plantilla("6593")
    sin = {"ult_res": None, "g5": None}
    for semilla in range(200):
        r = simular_partido(params, local, visita, sin, sin, semilla=semilla, bloqueadas_local={5, 1})
        assert not any(e["tipo"] == "cambio" and e["club_id"] == "184" and e["casilla"] in (1, 5)
                       for e in r["eventos"])


def test_sin_bloqueadas_el_partido_es_el_mismo(params):
    local, visita = cargar_plantilla("184"), cargar_plantilla("6593")
    sin = {"ult_res": None, "g5": None}
    for semilla in range(30):
        assert (simular_partido(params, local, visita, sin, sin, semilla=semilla)
                == simular_partido(params, local, visita, sin, sin, semilla=semilla,
                                   bloqueadas_local=frozenset(), bloqueadas_visita=frozenset()))


def test_sancion_sin_resolver_no_suspende_pero_bloquea():
    regs = [sancion(1, "A", 4, "1")]
    assert suspendidos(regs, "A") == {}
    assert casillas_bloqueadas(regs) == {("A", 4)}


def test_sancion_cuenta_los_partidos_del_club():
    regs = [sancion(1, "A", 4, "1", fechas=2)]
    assert suspendidos(regs, "A") == {4: "1"}
    regs.append(jugado(2, "A", "C"))
    assert suspendidos(regs, "A") == {4: "1"}
    regs.append(jugado(2, "D", "E", numero=2))  # partido de otros: no cuenta
    assert sanciones(regs)[0]["faltan"] == 1
    regs.append(jugado(3, "C", "A"))
    assert suspendidos(regs, "A") == {}
    assert casillas_bloqueadas(regs) == set()


def test_sancion_no_toca_al_otro_club():
    regs = [sancion(1, "A", 4, "1", fechas=3)]
    assert suspendidos(regs, "B") == {}


def test_temporada_suspendido_no_juega(params, tmp_path):
    # sanción resuelta a mano en un partido de la fecha 1; el club no la juega en sus N partidos
    nueva_temporada("s", semilla=11, base=tmp_path)
    jugar_siguiente("s", con_prob(params, 0, 0), base=tmp_path)
    ruta = carpeta_temporada("s", tmp_path) / "partidos" / "F01-P1.json"
    r = cargar_registros("s", base=tmp_path)[0]
    club = r["local"]["club_id"]
    casilla = r["alineaciones"][club]["casillas"][6]
    titular = casilla["titular"]
    r["votacion"] = {"tipo": "sancion", "club_id": club, "casilla": casilla["casilla"],
                     "jugador": titular, "fechas": 2}
    _escribir_json(ruta, r)
    for _ in range(9 * 4):
        jugar_siguiente("s", con_prob(params, 0, 0), base=tmp_path)
    propios = [x for x in cargar_registros("s", base=tmp_path)
               if x["fecha"] > 1 and club in (x["local"]["club_id"], x["visita"]["club_id"])]
    for i, x in enumerate(propios):
        en_casilla = x["alineaciones"][club]["casillas"][6]
        if i < 2:
            assert en_casilla["titular"]["id"] == casilla["suplente"]["id"]
            assert x["suspendidos"] == {club: [{"casilla": casilla["casilla"], "jugador_id": titular["id"]}]}
            assert not any(e["tipo"] == "cambio" and e["club_id"] == club and e["casilla"] == casilla["casilla"]
                           for e in x["eventos"])
        else:
            assert en_casilla["titular"]["id"] == titular["id"]
            assert club not in x["suspendidos"]


# --- mesa (tanda 3) ---

from pfb.motor.temporada import resolver_mesa, tabla  # noqa: E402
from pfb.motor.votaciones import MARCADOR_RANDOM, aplicar_mesa  # noqa: E402


def mesa(goles_local, goles_visita, opcion, semilla=1):
    r = reg(goles_local, goles_visita, semilla=semilla)
    r["votacion"] = {"tipo": "mesa", "opcion": opcion}
    return r


def marcador(r):
    return r["local"]["goles"], r["visita"]["goles"]


def test_opcion_10_trae_equipo(params):
    for s in range(400):
        v = sortear_votacion(reg(1, 0, semilla=s), con_prob(params, 0, 1), False)
        if v["opcion"] == 10:
            assert v["equipo"] in ("A", "B")
        else:
            assert "equipo" not in v


def test_no_procede_y_empate_mantienen(params):
    for ganador in ("no_procede", None):
        r = aplicar_mesa(mesa(2, 1, 3), ganador, params)
        assert marcador(r) == (2, 1)
        assert r["mesa"] == {"ganador": ganador, "original": {"local": 2, "visita": 1}}


def test_random_aplica_su_marcador(params):
    for opcion, esperado in MARCADOR_RANDOM.items():
        r = aplicar_mesa(mesa(2, 1, opcion), "random", params)
        assert marcador(r) == (esperado or (2, 1))
        assert r["mesa"]["original"] == {"local": 2, "visita": 1}


def test_marcadores_de_13_1():
    assert MARCADOR_RANDOM[2] == (3, 0) and MARCADOR_RANDOM[3] == (0, 3) and MARCADOR_RANDOM[4] == (0, 1)
    assert MARCADOR_RANDOM[6] == (2, 1) and MARCADOR_RANDOM[12] == (0, 3) and MARCADOR_RANDOM[11] == (2, 2)
    assert MARCADOR_RANDOM[5] is None and MARCADOR_RANDOM[7] is None


def test_repetir_solo_cambia_el_marcador(params):
    original = mesa(2, 1, 3, semilla=5)
    original["eventos"] = [roja("A", 4, "1")]
    r = aplicar_mesa(original, "repetir", params)
    assert r["eventos"] == original["eventos"]
    assert r["mesa"]["original"] == {"local": 2, "visita": 1}
    assert "bonos" in r["mesa"]
    assert r == aplicar_mesa(original, "repetir", params)  # reproducible
    assert marcador(original) == (2, 1)  # no toca el registro recibido


def test_ganador_desconocido(params):
    with pytest.raises(ValueError):
        aplicar_mesa(mesa(2, 1, 3), "me_sorprende", params)


def test_resolver_mesa_actualiza_la_tabla(params, tmp_path):
    nueva_temporada("m", semilla=3, base=tmp_path)
    for _ in range(9):
        jugar_siguiente("m", con_prob(params, 0, 0), base=tmp_path)
    regs = cargar_registros("m", base=tmp_path)
    r = next(x for x in regs if x["local"]["goles"] != x["visita"]["goles"])
    r["votacion"] = {"tipo": "mesa", "opcion": 9}  # VAR: 0-0
    _escribir_json(carpeta_temporada("m", tmp_path) / "partidos" / f"{r['partido_id']}.json", r)

    nuevo = resolver_mesa("m", r["partido_id"], "random", params, base=tmp_path)
    assert marcador(nuevo) == (0, 0)
    guardado = next(x for x in cargar_registros("m", base=tmp_path) if x["partido_id"] == r["partido_id"])
    assert marcador(guardado) == (0, 0)
    filas = {f["club_id"]: f for f in tabla(cargar_registros("m", base=tmp_path))}
    assert filas[r["local"]["club_id"]]["pe"] == 1 and filas[r["visita"]["club_id"]]["pe"] == 1
    with pytest.raises(ValueError):
        resolver_mesa("m", r["partido_id"], "random", params, base=tmp_path)


def test_resolver_mesa_sin_votacion_falla(params, tmp_path):
    nueva_temporada("n", semilla=3, base=tmp_path)
    jugar_siguiente("n", con_prob(params, 0, 0), base=tmp_path)
    with pytest.raises(ValueError):
        resolver_mesa("n", "F01-P1", "random", params, base=tmp_path)
