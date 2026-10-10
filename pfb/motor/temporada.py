"""Temporada: fixture, estado en archivos, último resultado, G5 y tabla.

El estado vive en data/temporadas/<temporada_id>/: temporada.json y partidos/<partido_id>.json.
La tabla, el último resultado y el G5 se recalculan desde los partidos guardados (§3.10).

    python -m pfb.motor.temporada nueva <temporada_id> [--semilla N]
    python -m pfb.motor.temporada siguiente <temporada_id>
    python -m pfb.motor.temporada tabla <temporada_id>
"""

import argparse
import json
import os
import random
import sys
import unicodedata

from pfb.motor.partido import cargar_parametros, simular_partido
from pfb.motor.plantillas import RAIZ, cargar_plantilla, cargar_plantillas

CARPETA_TEMPORADAS = RAIZ / "data" / "temporadas"
RUTA_COLORES = RAIZ / "data" / "colores_clubes.json"


# --- Fixture (mod_fixture.py del v1) ---

def make_day(num_teams, day):
    # algoritmo del círculo, https://en.wikipedia.org/wiki/Round-robin_tournament#Scheduling_algorithm
    assert not num_teams % 2, "Number of teams must be even!"
    lst = list(range(1, num_teams + 1))
    day %= (num_teams - 1)
    if day:
        lst = lst[:1] + lst[-day:] + lst[1:-day]
    half = num_teams // 2
    return list(zip(lst[:half], lst[half:][::-1]))


def make_schedule(num_teams):
    """Todos contra todos, ida y vuelta: la vuelta es la ida con local y visita invertidos."""
    if num_teams % 2:
        num_teams += 1
    schedule = [make_day(num_teams, day) for day in range(num_teams - 1)]
    swapped = [[(away, home) for home, away in day] for day in schedule]
    return schedule + swapped


def crear_fixture(rng, club_ids):
    """Baraja el mapeo número→club (como crear_fixture del v1) y arma las fechas con make_schedule.
    Corrección al v1: el equipo fijo del círculo (el 1) era local en toda la ida; ahora es local en
    las fechas pares y visita en las impares. La vuelta sigue siendo la ida invertida.
    Devuelve [[(local, visita), ...], ...]."""
    claves = list(club_ids)
    rng.shuffle(claves)
    por_numero = {i: claves[i - 1] for i in range(1, len(claves) + 1)}
    schedule = make_schedule(len(claves))
    ida = [
        [(b, a) if 1 in (a, b) and fecha % 2 == 1 else (a, b) for a, b in partidos]
        for fecha, partidos in enumerate(schedule[:len(schedule) // 2], start=1)
    ]
    vuelta = [[(b, a) for a, b in partidos] for partidos in ida]
    return [[(por_numero[a], por_numero[b]) for a, b in fecha] for fecha in ida + vuelta]


def partido_id(fecha, numero):
    """fecha y numero desde 1: (7, 3) -> 'F07-P3'."""
    return f"F{fecha:02d}-P{numero}"


# --- Archivos ---

def _escribir_json(ruta, datos):
    """Escribe en un temporal y lo renombra: una corrida cortada nunca deja un JSON a medias."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def _leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def carpeta_temporada(temporada_id, base=CARPETA_TEMPORADAS):
    return base / temporada_id


def nueva_temporada(temporada_id, semilla=None, club_ids=None, base=CARPETA_TEMPORADAS):
    carpeta = carpeta_temporada(temporada_id, base)
    if (carpeta / "temporada.json").exists():
        raise FileExistsError(f"la temporada {temporada_id} ya existe en {carpeta}")
    if semilla is None:
        semilla = random.SystemRandom().randrange(2**32)
    clubes = sorted(club_ids if club_ids is not None else cargar_plantillas())
    datos = {
        "temporada_id": temporada_id,
        "semilla": semilla,
        "clubes": clubes,
        "fixture": crear_fixture(random.Random(semilla), clubes),
    }
    _escribir_json(carpeta / "temporada.json", datos)
    return json.loads(json.dumps(datos))  # como queda en el archivo: tuplas -> listas


def cargar_temporada(temporada_id, base=CARPETA_TEMPORADAS):
    return _leer_json(carpeta_temporada(temporada_id, base) / "temporada.json")


def cargar_registros(temporada_id, base=CARPETA_TEMPORADAS):
    """Los registros guardados, en orden cronológico. Los .tmp no cuentan."""
    carpeta = carpeta_temporada(temporada_id, base) / "partidos"
    if not carpeta.exists():
        return []
    return _ordenados([_leer_json(r) for r in carpeta.glob("*.json")])


def _ordenados(registros):
    return sorted(registros, key=lambda r: (r["fecha"], r["partido_id"]))


# --- Estado de cada equipo ---

def _jugados(registros):
    return [r for r in _ordenados(registros) if r["estado"] == "jugado"]


def _goles(registro, club_id):
    """(a favor, en contra) del club en ese partido."""
    if registro["local"]["club_id"] == club_id:
        return registro["local"]["goles"], registro["visita"]["goles"]
    return registro["visita"]["goles"], registro["local"]["goles"]


def _juega(registro, club_id):
    return club_id in (registro["local"]["club_id"], registro["visita"]["club_id"])


def estado_equipo(registros, club_id, params):
    """{"ult_res": 1 | 0 | -1 | None, "g5": goles a favor en sus últimos N partidos | None}."""
    propios = [r for r in _jugados(registros) if _juega(r, club_id)]
    if not propios:
        return {"ult_res": None, "g5": None}
    gf, gc = _goles(propios[-1], club_id)
    ult_res = (gf > gc) - (gf < gc)
    n = params["marcador"]["g5"]["partidos"]
    g5 = sum(_goles(r, club_id)[0] for r in propios[-n:])
    return {"ult_res": ult_res, "g5": g5}


# --- Tabla ---

def cargar_nombres():
    return {club_id: c["club"] for club_id, c in _leer_json(RUTA_COLORES).items()}


def _alfabetico(nombre):
    return "".join(ch for ch in unicodedata.normalize("NFD", nombre) if not unicodedata.combining(ch)).casefold()


def _puntos(gf, gc):
    return 3 if gf > gc else 1 if gf == gc else 0


def tabla(registros, club_ids=None, nombres=None):
    """Filas ordenadas: puntos, DG, GF; entre los que sigan empatados, puntos en los partidos entre
    ellos; si sigue el empate, orden alfabético del nombre corto."""
    nombres = nombres or cargar_nombres()
    jugados = _jugados(registros)
    if club_ids is None:
        club_ids = sorted({r[lado]["club_id"] for r in jugados for lado in ("local", "visita")})

    filas = {c: {"club_id": c, "club": nombres[c], "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0}
             for c in club_ids}
    for r in jugados:
        for c in (r["local"]["club_id"], r["visita"]["club_id"]):
            gf, gc = _goles(r, c)
            f = filas[c]
            f["pj"] += 1
            f["gf"] += gf
            f["gc"] += gc
            f[{3: "pg", 1: "pe", 0: "pp"}[_puntos(gf, gc)]] += 1
    for f in filas.values():
        f["dg"] = f["gf"] - f["gc"]
        f["pts"] = 3 * f["pg"] + f["pe"]

    def puntos_entre(grupo):
        pts = dict.fromkeys(grupo, 0)
        for r in jugados:
            local, visita = r["local"]["club_id"], r["visita"]["club_id"]
            if local in grupo and visita in grupo:
                pts[local] += _puntos(*_goles(r, local))
                pts[visita] += _puntos(*_goles(r, visita))
        return pts

    grupos = {}
    for f in filas.values():
        grupos.setdefault((f["pts"], f["dg"], f["gf"]), []).append(f)
    orden = []
    for clave in sorted(grupos, reverse=True):
        grupo = grupos[clave]
        pts = puntos_entre({f["club_id"] for f in grupo})
        orden += sorted(grupo, key=lambda f: (-pts[f["club_id"]], _alfabetico(f["club"])))

    columnas = ("club_id", "club", "pj", "pg", "pe", "pp", "gf", "gc", "dg", "pts")
    return [{"pos": i, **{k: f[k] for k in columnas}} for i, f in enumerate(orden, start=1)]


def tabla_en_texto(filas):
    ancho = max(len(f["club"]) for f in filas)
    lineas = [f"{'Pos':>3}  {'Club':<{ancho}}  {'PJ':>3} {'PG':>3} {'PE':>3} {'PP':>3} "
              f"{'GF':>3} {'GC':>3} {'DG':>4} {'Pts':>4}"]
    for f in filas:
        lineas.append(f"{f['pos']:>3}  {f['club']:<{ancho}}  {f['pj']:>3} {f['pg']:>3} {f['pe']:>3} {f['pp']:>3} "
                      f"{f['gf']:>3} {f['gc']:>3} {f['dg']:>+4} {f['pts']:>4}")
    return "\n".join(lineas)


# --- Jugar ---

def jugar_siguiente(temporada_id, params, base=CARPETA_TEMPORADAS):
    """Juega el primer partido del fixture que no tenga archivo. Devuelve su registro, o None si la
    temporada terminó."""
    temporada = cargar_temporada(temporada_id, base)
    carpeta = carpeta_temporada(temporada_id, base) / "partidos"
    for f, partidos in enumerate(temporada["fixture"], start=1):
        for p, (local, visita) in enumerate(partidos, start=1):
            pid = partido_id(f, p)
            ruta = carpeta / f"{pid}.json"
            if ruta.exists():
                continue
            registros = cargar_registros(temporada_id, base)
            registro = simular_partido(params, cargar_plantilla(local), cargar_plantilla(visita),
                                       estado_equipo(registros, local, params),
                                       estado_equipo(registros, visita, params),
                                       partido_id=pid, fecha=f)
            _escribir_json(ruta, registro)
            return registro
    return None


def _main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Temporada del PFB v2.")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_nueva = sub.add_parser("nueva", help="crea la temporada y su fixture")
    p_nueva.add_argument("temporada_id")
    p_nueva.add_argument("--semilla", type=int)
    sub.add_parser("siguiente", help="juega el siguiente partido").add_argument("temporada_id")
    p_tabla = sub.add_parser("tabla", help="imprime la tabla")
    p_tabla.add_argument("temporada_id")
    p_tabla.add_argument("--png", help="además, genera la imagen de la tabla en esta ruta")
    args = parser.parse_args()

    if args.comando == "nueva":
        t = nueva_temporada(args.temporada_id, semilla=args.semilla)
        print(f"temporada {t['temporada_id']} creada: {len(t['fixture'])} fechas, semilla {t['semilla']}")
    elif args.comando == "siguiente":
        r = jugar_siguiente(args.temporada_id, cargar_parametros())
        if r is None:
            print("la temporada ya terminó")
        else:
            nombres = cargar_nombres()
            print(f"{r['partido_id']}: {nombres[r['local']['club_id']]} {r['local']['goles']} - "
                  f"{r['visita']['goles']} {nombres[r['visita']['club_id']]} (semilla {r['semilla']})")
    else:
        t = cargar_temporada(args.temporada_id)
        filas = tabla(cargar_registros(args.temporada_id), club_ids=t["clubes"])
        print(tabla_en_texto(filas))
        if args.png:
            from pfb.imagenes.tabla import generar_tabla
            generar_tabla(filas, args.png)
            print(f"imagen: {args.png}")


if __name__ == "__main__":
    _main()
