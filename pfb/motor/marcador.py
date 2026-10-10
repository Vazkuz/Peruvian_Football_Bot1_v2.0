"""Goles del partido, reparto y bonos (orden de resultados.Score del v1)."""


def _bono(rng, p2, p1, valor2, valor1):
    """Un solo sorteo con probabilidades excluyentes: valor2 con p2, valor1 con p1, si no 0."""
    r = rng.random()
    if r < p2:
        return valor2
    if r < p2 + p1:
        return valor1
    return 0


def _racha(rng, m, ult_res):
    if ult_res == 1:
        return _bono(rng, m["racha_gano"]["mas2"], m["racha_gano"]["mas1"], 2, 1)
    if ult_res == -1:
        return _bono(rng, m["racha_perdio"]["menos2"], m["racha_perdio"]["menos1"], -2, -1)
    return 0


def _g5(rng, m, g5):
    if g5 is None:
        return 0
    p2 = min(g5 / m["g5"]["divisor_mas2"], 1)
    p1 = min(g5 / m["g5"]["divisor_mas1"], 1 - p2)
    return _bono(rng, p2, p1, 2, 1)


def sortear_marcador(rng, params, local, visita):
    """rng: random.Random ya sembrado. params: el contenido de data/parametros_motor.json.
    local / visita: {"ult_res": 1 | 0 | -1 | None, "g5": int | None}."""
    m = params["marcador"]

    goles = max(round(rng.gauss(m["goles_partido"]["media"], m["goles_partido"]["desviacion"])), 0)
    goles_local = rng.randint(0, goles)
    goles_visita = goles - goles_local

    localia = _bono(rng, m["localia"]["mas2"], m["localia"]["mas1"], 2, 1)
    goles_local += localia

    racha_local = _racha(rng, m, local["ult_res"])
    goles_local = max(goles_local + racha_local, 0)

    g5_local = _g5(rng, m, local["g5"])
    goles_local += g5_local

    racha_visita = _racha(rng, m, visita["ult_res"])
    goles_visita = max(goles_visita + racha_visita, 0)

    g5_visita = _g5(rng, m, visita["g5"])
    goles_visita += g5_visita

    return {
        "local": {"goles": goles_local, "bonos": {"localia": localia, "racha": racha_local, "g5": g5_local}},
        "visita": {"goles": goles_visita, "bonos": {"racha": racha_visita, "g5": g5_visita}},
    }
