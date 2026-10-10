"""Minutos de los eventos del partido."""


def _empujar_repetidos(minutos):
    """Ordena y, si dos caen en el mismo minuto, empuja +1 a los siguientes (como T_Goles del v1)."""
    minutos.sort()
    for i in range(1, len(minutos)):
        if minutos[i] == minutos[i - 1]:
            for j in range(i, len(minutos)):
                minutos[j] += 1
    return minutos


def minutos_de_gol(rng, n):
    """Copia de T_Goles del v1. Devuelve [(tiempo, minuto)], con el 2T guardado de 0 a 45."""
    n_1t = rng.randint(0, n)
    n_2t = n - n_1t
    minutos_1t = _empujar_repetidos([rng.randint(0, 45) for _ in range(n_1t)])
    minutos_2t = _empujar_repetidos([rng.randint(0, 45) for _ in range(n_2t)])
    return [(1, m) for m in minutos_1t] + [(2, m) for m in minutos_2t]


def _cuantas_salen(rng, p, tope):
    """Bucle de nTarjetas del v1: si sale una, sigue sumando mientras salga, hasta el tope."""
    n = 0
    if rng.random() < p:
        n += 1
        while rng.random() < p:
            n += 1
            if n >= tope:
                break
    return n


def cantidad_tarjetas(rng, params):
    """nTarjetas del v1, con el tope de rojas para los dos equipos y sin canc_partido. Las rojas
    siguen con "mientras salga, suma otra"; las amarillas del partido salen de una normal
    redondeada (piso 0, mismo tope). Devuelve (rojas_local, rojas_visita, amarillas_local, amarillas_visita)."""
    t = params["tarjetas"]
    rojas = _cuantas_salen(rng, t["rojas"], t["tope_sorteo"])
    amarillas = min(max(round(rng.gauss(t["amarillas"]["media"], t["amarillas"]["desviacion"])), 0),
                    t["tope_sorteo"])
    rojas_local = rng.randint(0, rojas)
    rojas_visita = rojas - rojas_local
    amarillas_local = rng.randint(0, amarillas)
    amarillas_visita = amarillas - amarillas_local
    tope = t["tope_rojas_por_equipo"]
    return min(rojas_local, tope), min(rojas_visita, tope), amarillas_local, amarillas_visita


def minutos_tarjetas(rng, n_rojas, n_amarillas):
    """Copia de TiemposTarjetas del v1 (sin empuje). Devuelve (rojas, amarillas) como [(tiempo, minuto)]."""
    rojas_1t = rng.randint(0, n_rojas)
    rojas_2t = n_rojas - rojas_1t
    amarillas_1t = rng.randint(0, n_amarillas)
    amarillas_2t = n_amarillas - amarillas_1t

    def minutos(tiempo, n):
        return [(tiempo, m) for m in sorted(rng.randint(0, 45) for _ in range(n))]

    rojas = minutos(1, rojas_1t) + minutos(2, rojas_2t)
    amarillas = minutos(1, amarillas_1t) + minutos(2, amarillas_2t)
    return rojas, amarillas


def _sorteo_excluyente(rng, opciones):
    """Un solo rng.random() sobre {"valor": probabilidad}, en el orden del JSON."""
    r = rng.random()
    acumulado = 0.0
    for valor, p in opciones.items():
        acumulado += p
        if r < acumulado:
            return int(valor)
    return int(valor)  # por si el redondeo deja la suma apenas debajo de 1


def ventanas_de_cambio(rng, params):
    """Ventanas de cambio de un equipo (§3.7): [{"tiempo", "minuto", "jugadores"}] en orden cronológico.
    La de entretiempo es extra y va en (2, 0); ninguna ventana normal puede caer ahí."""
    c = params["cambios"]
    ocupados = {(2, 0)}
    ventanas = []
    for _ in range(_sorteo_excluyente(rng, c["ventanas"])):
        jugadores = _sorteo_excluyente(rng, c["jugadores_por_ventana"])
        tiempo = 1 if rng.random() < c["ventana_en_1t"] else 2
        minuto = rng.randint(0, 45)
        while (tiempo, minuto) in ocupados:
            minuto = rng.randint(0, 45)
        ocupados.add((tiempo, minuto))
        ventanas.append({"tiempo": tiempo, "minuto": minuto, "jugadores": jugadores})

    if rng.random() < c["entretiempo"]:
        jugadores = _sorteo_excluyente(rng, c["jugadores_por_ventana"])
        ventanas.append({"tiempo": 2, "minuto": 0, "jugadores": jugadores})

    ventanas.sort(key=lambda v: (v["tiempo"], v["minuto"]))
    cupo = c["tope_por_equipo"]
    usadas = []
    for v in ventanas:
        if cupo == 0:
            break
        v["jugadores"] = min(v["jugadores"], cupo)
        cupo -= v["jugadores"]
        usadas.append(v)
    return usadas
