"""Valida el motor v2 contra los 90 partidos reales del Clausura (data/partidos/<id>.json).

Simula N temporadas completas (nueva temporada + jugar_siguiente hasta terminar, en carpetas
temporales que se borran al final) y compara las mismas metricas con los partidos reales.
No publica, no genera imagenes y no cambia ningun parametro.

Uso (desde la raiz del repo):
    python scripts/validar_motor.py [--temporadas 200] [--semilla N] [--procesos N] [--salida tmp/validacion_motor.txt]

Con --semilla la corrida se puede repetir: las semillas de cada fixture y de cada partido salen
de un generador sembrado con ella, en vez de random.SystemRandom.
"""

import argparse
import json
import os
import random
import sys
import tempfile
import types
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import pfb.motor.partido as partido  # noqa: E402
from pfb.motor.partido import cargar_parametros  # noqa: E402
from pfb.motor.temporada import cargar_registros, jugar_siguiente, nueva_temporada  # noqa: E402

CARPETA_REALES = RAIZ / "data" / "partidos"
SALIDA = RAIZ / "tmp" / "validacion_motor.txt"
CLAVES_GOLES = ["0", "1", "2", "3", "4", "5", "6", "7+"]


# --- Conteos: cada partido suma a un Counter; al final se convierten en metricas ---

def _sumar_partido(c, goles_local, goles_visita, minutos_goles, amarillas, rojas_directas, dobles,
                   cambios_por_equipo, cambios_1t, arqueros_que_salen):
    """minutos_goles: lista de tiempos (1 o 2) de cada gol. cambios_por_equipo: [n_local, n_visita]."""
    total = goles_local + goles_visita
    c["partidos"] += 1
    c["goles"] += total
    c["goles_local"] += goles_local
    c["goles_visita"] += goles_visita
    c["dist_goles_" + (str(total) if total < 7 else "7+")] += 1
    c["goles_1t"] += sum(t == 1 for t in minutos_goles)
    c["goles_2t"] += sum(t == 2 for t in minutos_goles)
    c["gana_local" if goles_local > goles_visita else "empate" if goles_local == goles_visita else "gana_visita"] += 1
    c["amarillas"] += amarillas
    c["rojas_directas"] += rojas_directas
    c["dobles"] += dobles
    c["con_roja"] += (rojas_directas + dobles) > 0
    for n in cambios_por_equipo:
        c["equipos"] += 1
        c["cambios"] += n
        c[f"dist_cambios_{min(n, 5)}"] += 1
    c["cambios_1t"] += cambios_1t
    c["sale_arquero"] += arqueros_que_salen


def contar_simulado(registro, c):
    local, visita = registro["local"]["club_id"], registro["visita"]["club_id"]
    eventos = registro["eventos"]
    arquero = {club: next(x["casilla"] for x in registro["alineaciones"][club]["casillas"] if x["rol"] == "arquero")
               for club in (local, visita)}
    goles = [e for e in eventos if e["tipo"] == "gol"]
    cambios = [e for e in eventos if e["tipo"] == "cambio"]
    rojas = [e for e in eventos if e["tipo"] == "roja"]
    _sumar_partido(
        c,
        goles_local=registro["local"]["goles"],
        goles_visita=registro["visita"]["goles"],
        minutos_goles=[e["tiempo"] for e in goles],
        # amarillas mostradas, incluida la segunda de una doble (como en los reales: amarilla + doble_amarilla)
        amarillas=sum(e["tipo"] == "amarilla" for e in eventos),
        rojas_directas=sum(not e["doble_amarilla"] for e in rojas),
        dobles=sum(e["doble_amarilla"] for e in rojas),
        cambios_por_equipo=[sum(e["club_id"] == club for e in cambios) for club in (local, visita)],
        cambios_1t=sum(e["tiempo"] == 1 for e in cambios),
        arqueros_que_salen=sum(e["casilla"] == arquero[e["club_id"]] for e in cambios),
    )
    c["fin_por_expulsiones"] += registro["fin"] is not None
    c["bono_localia"] += registro["local"]["bonos"]["localia"]
    c["bono_racha"] += registro["local"]["bonos"]["racha"] + registro["visita"]["bonos"]["racha"]
    c["bono_g5"] += registro["local"]["bonos"]["g5"] + registro["visita"]["bonos"]["g5"]


def tiempo_real(evento):
    """El añadido cuenta en su tiempo: 45+2 es 1T; el 46 (entretiempo) en adelante es 2T."""
    return 1 if evento["minuto"] <= 45 else 2


def contar_real(p, c):
    local = next(e["club_id"] for e in p["equipos"] if e["local"])
    visita = next(e["club_id"] for e in p["equipos"] if not e["local"])
    # el arquero titular es el de mayor 'top' (como en scripts/partido_a_alineacion.py)
    arqueros = {max(e["titulares"], key=lambda j: j["top"])["id"] for e in p["equipos"]}
    tipos = Counter(t["tipo"] for t in p["tarjetas"])
    _sumar_partido(
        c,
        goles_local=sum(g["club_id"] == local for g in p["goles"]),
        goles_visita=sum(g["club_id"] == visita for g in p["goles"]),
        minutos_goles=[tiempo_real(g) for g in p["goles"]],
        amarillas=tipos["amarilla"] + tipos["doble_amarilla"],
        rojas_directas=tipos["roja"],
        dobles=tipos["doble_amarilla"],
        cambios_por_equipo=[sum(x["club_id"] == club for x in p["cambios"]) for club in (local, visita)],
        cambios_1t=sum(tiempo_real(x) == 1 for x in p["cambios"]),
        arqueros_que_salen=sum(x["sale"]["id"] in arqueros for x in p["cambios"]),
    )


def partidos_reales():
    """Solo los archivos de partidos (<id>.json); formacion_por_club.json e ids_clausura.json no lo son."""
    for ruta in sorted(CARPETA_REALES.glob("*.json")):
        if ruta.stem.isdigit():
            with open(ruta, encoding="utf-8") as f:
                yield json.load(f)


# --- Simulacion ---

def simular_temporada(semilla):
    """Juega una temporada completa en una carpeta temporal y devuelve sus conteos.
    Las semillas de los partidos salen de random.Random(semilla) para que la corrida se repita."""
    semillero = random.Random(semilla)
    original = partido.random
    partido.random = types.SimpleNamespace(Random=random.Random, SystemRandom=lambda: semillero)
    try:
        params = cargar_parametros()
        c = Counter()
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            nueva_temporada("validacion", semilla=semillero.randrange(2**32), base=base)
            while jugar_siguiente("validacion", params, base=base) is not None:
                pass
            for registro in cargar_registros("validacion", base=base):
                contar_simulado(registro, c)
        return c
    finally:
        partido.random = original


def simular(temporadas, semilla=None, procesos=None):
    if semilla is None:
        semilla = random.SystemRandom().randrange(2**32)
    semillas = [random.Random(semilla).randrange(2**32) + i for i in range(temporadas)]
    total = Counter()
    if procesos == 1:
        for s in semillas:
            total.update(simular_temporada(s))
    else:
        with ProcessPoolExecutor(max_workers=procesos) as ex:
            for c in ex.map(simular_temporada, semillas):
                total.update(c)
    return total, semilla


# --- Metricas y tabla ---

def metricas(c, simulado):
    """Lista de (nombre, valor, formato). formato: 'n' (media) o '%'."""
    p, e = c["partidos"], c["equipos"]
    goles = c["goles_1t"] + c["goles_2t"]
    m = [("Goles por partido", c["goles"] / p, "n")]
    m += [(f"Partidos con {k} goles", 100 * c["dist_goles_" + k] / p, "%") for k in CLAVES_GOLES]
    m += [
        ("Goles en el 1T", 100 * c["goles_1t"] / goles if goles else 0, "%"),
        ("Goles en el 2T", 100 * c["goles_2t"] / goles if goles else 0, "%"),
        ("Gana local", 100 * c["gana_local"] / p, "%"),
        ("Empate", 100 * c["empate"] / p, "%"),
        ("Gana visita", 100 * c["gana_visita"] / p, "%"),
        ("Goles del local por partido", c["goles_local"] / p, "n"),
        ("Goles de la visita por partido", c["goles_visita"] / p, "n"),
        ("Amarillas por partido", c["amarillas"] / p, "n"),
        ("Rojas directas por partido", c["rojas_directas"] / p, "n"),
        ("Dobles amarillas por partido", c["dobles"] / p, "n"),
        ("Partidos con al menos una roja", 100 * c["con_roja"] / p, "%"),
        ("Cambios por equipo y partido", c["cambios"] / e, "n"),
    ]
    m += [(f"Equipos con {k} cambios", 100 * c[f"dist_cambios_{k}"] / e, "%") for k in range(6)]
    m += [
        ("Cambios en el 1T", 100 * c["cambios_1t"] / c["cambios"] if c["cambios"] else 0, "%"),
        ("Equipos en que sale el arquero", 100 * c["sale_arquero"] / e, "%"),
    ]
    if simulado:
        m += [
            ("Partidos terminados por expulsiones", 100 * c["fin_por_expulsiones"] / p, "%"),
            ("Bono de localía (media, local)", c["bono_localia"] / p, "n"),
            ("Bono de racha (media por equipo)", c["bono_racha"] / e, "n"),
            ("Bono G5 (media por equipo)", c["bono_g5"] / e, "n"),
        ]
    return m


def _fmt(valor, formato):
    if valor is None:
        return "—"
    return f"{valor:.2f} %" if formato == "%" else f"{valor:.3f}"


def tabla_texto(sim, real, temporadas, semilla, partidos_sim, partidos_real):
    reales = {nombre: valor for nombre, valor, _ in real}
    filas = []
    for nombre, valor, formato in sim:
        r = reales.get(nombre)
        dif = None if r is None else valor - r
        dif_txt = "—" if dif is None else (f"{dif:+.2f} pp" if formato == "%" else f"{dif:+.3f}")
        filas.append((nombre, _fmt(valor, formato), _fmt(r, formato), dif_txt))
    anchos = [max(len(f[i]) for f in filas + [("Métrica", "Simulado", "Real", "Diferencia")]) for i in range(4)]
    linea = lambda f: f"{f[0]:<{anchos[0]}} | {f[1]:>{anchos[1]}} | {f[2]:>{anchos[2]}} | {f[3]:>{anchos[3]}}"
    cabecera = [
        f"Validación del motor v2: {temporadas} temporadas simuladas ({partidos_sim} partidos), semilla {semilla}",
        f"contra {partidos_real} partidos reales del Clausura. Diferencia = Simulado - Real.",
        "",
        linea(("Métrica", "Simulado", "Real", "Diferencia")),
        "-+-".join("-" * a for a in anchos),
    ]
    return "\n".join(cabecera + [linea(f) for f in filas]) + "\n"


def validar(temporadas=200, semilla=None, procesos=None, salida=SALIDA):
    sim, semilla = simular(temporadas, semilla, procesos)
    real = Counter()
    for p in partidos_reales():
        contar_real(p, real)
    texto = tabla_texto(metricas(sim, True), metricas(real, False), temporadas, semilla,
                        sim["partidos"], real["partidos"])
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(texto, encoding="utf-8")
    return texto, metricas(sim, True), metricas(real, False)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Valida el motor contra los partidos reales del Clausura.")
    parser.add_argument("--temporadas", type=int, default=200)
    parser.add_argument("--semilla", type=int)
    parser.add_argument("--procesos", type=int, default=None, help="por defecto, todos los núcleos")
    parser.add_argument("--salida", default=str(SALIDA))
    args = parser.parse_args()
    texto, _, _ = validar(args.temporadas, args.semilla, args.procesos, args.salida)
    print(texto)
    print(f"guardado en {args.salida}")
