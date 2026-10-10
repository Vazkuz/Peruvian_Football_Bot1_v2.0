"""Quién hace cada evento del partido."""

EXTREMOS = ("volante_extremo_izq", "volante_extremo_der")


class ErrorAsignacion(ValueError):
    pass


def probabilidades_goleador(params, plantilla):
    """Devuelve {numero de casilla: probabilidad de hacer el gol} según el rol de la casilla."""
    g = params["goleador"]
    roles = {c.numero: c.rol for c in plantilla.casillas}
    delanteros = [n for n, rol in roles.items() if rol == "delantero"]
    arqueros = [n for n, rol in roles.items() if rol == "arquero"]
    campo = [n for n, rol in roles.items() if rol not in ("delantero", "arquero")]

    prob = {n: 0.0 for n in roles}
    for n in arqueros:
        prob[n] = g["arquero"] / g["arquero_divisor"]

    if len(delanteros) == 2:
        for n in delanteros:
            prob[n] = g["delantero_si_son_2"]
    elif len(delanteros) == 1:
        prob[delanteros[0]] = g["delantero_si_es_1"]
        extremos = [n for n in campo if roles[n] in EXTREMOS]
        mediapuntas = [n for n in campo if roles[n] == "mediapunta"]
        extra = 2 * g["extremo_extra_si_es_1"]
        if len(extremos) == 1:
            prob[extremos[0]] += extra  # un solo extremo se lleva el extra completo
            extra = 0
        elif extremos:
            for n in extremos:
                prob[n] += g["extremo_extra_si_es_1"]
            extra -= g["extremo_extra_si_es_1"] * len(extremos)
        # sin extremos, el extra va al mediapunta o, si no hay, al resto
        if extra > 0 and mediapuntas:
            for n in mediapuntas:
                prob[n] += extra / len(mediapuntas)
    else:
        raise ErrorAsignacion(
            f"plantilla {plantilla.club_id} ({plantilla.club_nombre}): {len(delanteros)} delanteros; "
            "el goleador solo está definido para 1 o 2")

    resto = (1 - sum(prob.values())) / len(campo)
    for n in campo:
        prob[n] += resto
    return prob


def goleadores(rng, params, plantilla, n):
    """n números de casilla, cada uno con un solo rng.random() sobre probabilidades excluyentes."""
    prob = probabilidades_goleador(params, plantilla)
    casillas = sorted(prob)
    resultado = []
    for _ in range(n):
        r = rng.random()
        acumulado = 0.0
        elegida = casillas[-1]  # por si el redondeo deja la suma apenas debajo de 1
        for numero in casillas:
            acumulado += prob[numero]
            if r < acumulado:
                elegida = numero
                break
        resultado.append(elegida)
    return resultado


def penales(rng, params, n):
    """n booleanos: si cada gol fue de penal."""
    p = params["penal"]["por_gol"]
    return [rng.random() < p for _ in range(n)]


# Dentro de un mismo minuto: rojas, amarillas, goles y al final la ventana de cambio.
_ROJA, _AMARILLA, _GOL, _VENTANA = range(4)


def _jugador(j):
    return {"id": j.id, "nombre": j.nombre}


def linea_de_tiempo(rng, params, plantilla, goles, rojas, amarillas, ventanas):
    """Eventos de un equipo en orden cronológico: quién recibe cada tarjeta, quién sale en cada
    ventana y quién hace cada gol, respetando cambios y expulsiones.
    goles: [(tiempo, minuto, casilla)]; rojas / amarillas: [(tiempo, minuto)];
    ventanas: la salida de eventos.ventanas_de_cambio."""
    casillas = {c.numero: c for c in plantilla.casillas}
    arquero = next(c.numero for c in plantilla.casillas if c.rol == "arquero")

    # 1. Casilla de cada tarjeta, como jTarjetas del v1.
    casillas_amarillas = [rng.randint(1, 11) for _ in amarillas]
    casillas_rojas = rng.sample(range(1, 12), len(rojas))

    # 2. Cupo de cambio del arquero, elegido entre todos los cupos de todas las ventanas.
    cupos = sum(v["jugadores"] for v in ventanas)
    cupo_arquero = None
    if rng.random() < params["cambios"]["arquero_sale"] and cupos > 0:
        cupo_arquero = rng.randrange(cupos)

    pendientes = []
    for (tiempo, minuto), casilla in zip(rojas, casillas_rojas):
        pendientes.append((tiempo, minuto, _ROJA, casilla))
    for (tiempo, minuto), casilla in zip(amarillas, casillas_amarillas):
        pendientes.append((tiempo, minuto, _AMARILLA, casilla))
    for tiempo, minuto, casilla in goles:
        pendientes.append((tiempo, minuto, _GOL, casilla))
    primer_cupo = 0
    for numero, v in enumerate(ventanas, start=1):
        pendientes.append((v["tiempo"], v["minuto"], _VENTANA, (numero, primer_cupo, v["jugadores"])))
        primer_cupo += v["jugadores"]
    pendientes.sort(key=lambda e: e[:3])  # sort estable: dentro de cada tipo se respeta el orden recibido

    ocupante = {n: c.titular for n, c in casillas.items()}
    expulsadas = set()
    cambiadas = set()
    con_amarilla = set()
    prob_gol = probabilidades_goleador(params, plantilla)
    eventos = []

    def en_cancha():
        return [n for n in sorted(casillas) if n not in expulsadas]

    def evento(tipo, tiempo, minuto, casilla, **extra):
        e = {"tipo": tipo, "tiempo": tiempo, "minuto": minuto, "casilla": casilla}
        if tipo != "cambio":
            e["jugador"] = _jugador(ocupante[casilla])
        e.update(extra)
        eventos.append(e)

    tope_expulsados = params["tarjetas"]["expulsados_fin_partido"]

    def expulsar(tiempo, minuto, casilla, doble_amarilla):
        """Registra la roja; devuelve True si es el expulsado que termina el partido."""
        expulsadas.add(casilla)
        if len(expulsadas) == tope_expulsados:
            evento("roja", tiempo, minuto, casilla, doble_amarilla=doble_amarilla, fin_partido=True)
            return True
        evento("roja", tiempo, minuto, casilla, doble_amarilla=doble_amarilla)
        return False

    for tiempo, minuto, tipo, dato in pendientes:
        if tipo in (_ROJA, _AMARILLA):
            casilla = dato
            if casilla in expulsadas:
                casilla = rng.choice(en_cancha())
            if tipo == _ROJA:
                if expulsar(tiempo, minuto, casilla, doble_amarilla=False):
                    return eventos
            else:
                # Cautela del amonestado: si ya tiene amarilla, con cierta probabilidad la amarilla
                # va a otro en cancha que no tenga (si no queda ninguno, se queda con él).
                if (ocupante[casilla].id in con_amarilla
                        and rng.random() >= params["tarjetas"]["segunda_amarilla_se_queda"]):
                    sin_amarilla = [n for n in en_cancha() if ocupante[n].id not in con_amarilla]
                    if sin_amarilla:
                        casilla = rng.choice(sin_amarilla)
                evento("amarilla", tiempo, minuto, casilla)
                if ocupante[casilla].id in con_amarilla:
                    if expulsar(tiempo, minuto, casilla, doble_amarilla=True):
                        return eventos
                else:
                    con_amarilla.add(ocupante[casilla].id)

        elif tipo == _GOL:
            casilla = dato
            if casilla in expulsadas:
                vivas = en_cancha()
                total = sum(prob_gol[n] for n in vivas)
                r = rng.random() * total
                acumulado = 0.0
                casilla = vivas[-1]  # por si el redondeo deja la suma apenas debajo del total
                for n in vivas:
                    acumulado += prob_gol[n]
                    if r < acumulado:
                        casilla = n
                        break
            evento("gol", tiempo, minuto, casilla)

        else:
            numero, primer_cupo, jugadores = dato
            for cupo in range(primer_cupo, primer_cupo + jugadores):
                disponibles = [n for n in en_cancha() if n not in cambiadas]
                if cupo == cupo_arquero and arquero in disponibles:
                    casilla = arquero
                else:
                    campo = [n for n in disponibles if n != arquero]
                    if not campo:
                        continue  # no queda casilla válida: el cupo se pierde
                    casilla = rng.choice(campo)
                sale = ocupante[casilla]
                entra = casillas[casilla].suplente
                cambiadas.add(casilla)
                ocupante[casilla] = entra
                evento("cambio", tiempo, minuto, casilla, ventana=numero, sale=_jugador(sale), entra=_jugador(entra))

    return eventos
