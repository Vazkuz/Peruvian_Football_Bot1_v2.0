"""Arma la plantilla de cada club con puntaje ponderado a partir de los partidos del Clausura (sin red).

Parametros en data/criterio_plantillas.json.

Uso:
    python scripts/armar_plantillas.py                                # los 18 clubes
    python scripts/armar_plantillas.py --club 184 6593                # solo algunos clubes
    python scripts/armar_plantillas.py --revisar-roles <partido_id>   # roles y minutos de un partido
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from formacion_por_club import fecha_partido  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CRITERIO = RAIZ / "data" / "criterio_plantillas.json"
PARTIDOS = RAIZ / "data" / "partidos"
IDS = PARTIDOS / "ids_clausura.json"
SALIDA = RAIZ / "data" / "plantillas"

RE_NUMEROS = re.compile(r"^(\d+(?:-\d+)+)(?:\s|$)")
EXPULSIONES = ("roja", "doble_amarilla")


class ErrorPlantilla(Exception):
    pass


def cargar_criterio():
    return json.loads(CRITERIO.read_text(encoding="utf-8"))


def lineas(formacion):
    m = RE_NUMEROS.match(formacion)
    if not m:
        raise ErrorPlantilla(f"formacion sin numeros: {formacion!r}")
    return [int(n) for n in m.group(1).split("-")]


# --- c. rol a partir de coordenadas ---

def roles_por_coordenadas(formacion, coords, reglas):
    """coords: lista de (top, left). Devuelve {(top, left): rol}."""
    return dict(casillas_por_coordenadas(formacion, coords, reglas))


def casillas_por_coordenadas(formacion, coords, reglas):
    """Devuelve [((top, left), rol)] en orden de casillas: arquero, luego cada linea de atras
    hacia adelante y, dentro de la linea, de izquierda a derecha."""
    if len(coords) != 11:
        raise ErrorPlantilla(f"{len(coords)} coordenadas en vez de 11")
    tope = max(t for t, _ in coords)
    arqueros = [c for c in coords if c[0] == tope]
    if len(arqueros) != 1:
        raise ErrorPlantilla("no hay un unico arquero (top maximo)")
    roles = {arqueros[0]: "arquero"}

    campo = sorted((c for c in coords if c != arqueros[0]), key=lambda c: (-c[0], c[1]))
    tamanos = lineas(formacion)
    if sum(tamanos) != 10:
        raise ErrorPlantilla(f"la formacion {formacion!r} no suma 10 jugadores de campo")
    bloques, i = [], 0
    for n in tamanos:
        bloques.append(sorted(campo[i:i + n], key=lambda c: c[1]))
        i += n

    izq_max, der_min = reglas["abierto_izquierda_left_max"], reglas["abierto_derecha_left_min"]
    defensivo_min = reglas["volante_defensivo_top_min"]

    defensa, ataque, medio = bloques[0], bloques[-1], bloques[1:-1]
    if len(defensa) == 3:
        roles.update({c: "central" for c in defensa})
    elif len(defensa) in (4, 5):
        roles[defensa[0]] = "lateral_izq"
        roles[defensa[-1]] = "lateral_der"
        roles.update({c: "central" for c in defensa[1:-1]})
    else:
        raise ErrorPlantilla(f"linea defensiva de {len(defensa)} no contemplada")

    if len(ataque) in (1, 2):
        roles.update({c: "delantero" for c in ataque})
    elif len(ataque) == 3:
        roles[ataque[0]] = "volante_extremo_izq"
        roles[ataque[1]] = "delantero"
        roles[ataque[2]] = "volante_extremo_der"
    else:
        raise ErrorPlantilla(f"linea de ataque de {len(ataque)} no contemplada")

    rombo = "-".join(map(str, tamanos)) in reglas["formaciones_rombo"]
    for k, bloque in enumerate(medio):
        if rombo and k == 0 and len(bloque) == 3:  # rombo: VD al centro, VC a los lados
            roles[bloque[0]], roles[bloque[1]], roles[bloque[2]] = "volante_central", "volante_defensivo", "volante_central"
            continue
        abiertos_izq = [c for c in bloque if c[1] <= izq_max]
        abiertos_der = [c for c in bloque if c[1] >= der_min]
        centrales = [c for c in bloque if izq_max < c[1] < der_min]
        roles.update({c: "volante_extremo_izq" for c in abiertos_izq})
        roles.update({c: "volante_extremo_der" for c in abiertos_der})
        ultimo = k == len(medio) - 1 and len(medio) >= 2
        mediapunta = ultimo and (len(centrales) == 1 or len(centrales) == len(bloque))
        for c in centrales:
            if mediapunta:
                roles[c] = "mediapunta"
            elif c[0] >= defensivo_min:
                roles[c] = "volante_defensivo"
            else:
                roles[c] = "volante_central"
    return [(arqueros[0], "arquero")] + [(c, roles[c]) for bloque in bloques for c in bloque]


# --- a. minutos por jugador ---

def minutos_por_jugador(partido, equipo, criterio):
    """Devuelve {jugador_id: {"inicio", "fin", "rol", "origen"}} para un equipo de un partido."""
    duracion = criterio["minutos"]["duracion"]
    roles = roles_por_coordenadas(equipo["formacion"], [(t["top"], t["left"]) for t in equipo["titulares"]],
                                  criterio["reglas_rol"])
    jugadores = {t["id"]: {"inicio": 0, "fin": duracion, "rol": roles[(t["top"], t["left"])], "origen": "titular"}
                 for t in equipo["titulares"]}
    banca = {b["id"]: b for b in equipo["banca"]}
    club = equipo["club_id"]

    for c in sorted((c for c in partido["cambios"] if c["club_id"] == club), key=lambda c: c["minuto"]):
        m = min(c["minuto"], duracion)
        sale, entra = c["sale"]["id"], c["entra"]["id"]
        if sale not in jugadores:
            raise ErrorPlantilla(f"sale {c['sale']['nombre']} sin haber estado en cancha")
        jugadores[sale]["fin"] = m
        if entra not in banca:
            raise ErrorPlantilla(f"entra {c['entra']['nombre']} y no esta en la banca")
        rol = criterio["rol_banca"].get(banca[entra]["posicion"])
        if rol is None:
            raise ErrorPlantilla(f"posicion de banca no reconocida para {c['entra']['nombre']}: "
                                 f"{banca[entra]['posicion']!r}")
        jugadores[entra] = {"inicio": m, "fin": duracion, "rol": rol, "origen": "banca"}

    for t in partido["tarjetas"]:
        if t["tipo"] in EXPULSIONES and t["jugador"]["id"] in jugadores:
            j = jugadores[t["jugador"]["id"]]
            j["fin"] = min(j["fin"], min(t["minuto"], duracion))

    for j in jugadores.values():
        j["minutos"] = max(0, j["fin"] - j["inicio"])
    return jugadores


# --- b. pesos ---

def peso_rival(club_id, rival_id, criterio):
    for c in criterio["clasicos"]:
        if set(c["clubes"]) == {club_id, rival_id}:
            return c["peso"]
    pos = {e["club_id"]: e["posicion"] for e in criterio["tabla_clausura"]}
    if rival_id not in pos:
        raise ErrorPlantilla(f"el rival {rival_id} no esta en la tabla")
    p = criterio["peso_rival"]
    return 1 + (p["ultimo_puesto"] - pos[rival_id]) / p["divisor"]


def pesos_fecha(criterio):
    """{(club_id, partido_id): peso} segun el orden de fecha de los partidos de cada club."""
    ids = [p["id"] for p in json.loads(IDS.read_text(encoding="utf-8"))["partidos"]]
    por_club = {}
    for i in ids:
        partido = json.loads((PARTIDOS / f"{i}.json").read_text(encoding="utf-8"))
        fecha = fecha_partido(i)
        for e in partido["equipos"]:
            por_club.setdefault(e["club_id"], []).append((fecha, i))
    divisor = criterio["peso_fecha"]["divisor"]
    pesos = {}
    for club, lista in por_club.items():
        for k, (_, i) in enumerate(sorted(lista), start=1):
            pesos[(club, i)] = 1 + (k - 1) / divisor
    return pesos


def cargar_partidos():
    """[(partido_id, fecha, partido)] de todos los partidos de ids_clausura.json."""
    salida = []
    for p in json.loads(IDS.read_text(encoding="utf-8"))["partidos"]:
        ruta = PARTIDOS / f"{p['id']}.json"
        if not ruta.exists():
            raise ErrorPlantilla(f"falta el partido {p['id']}")
        salida.append((p["id"], fecha_partido(p["id"]), json.loads(ruta.read_text(encoding="utf-8"))))
    return salida


def nombres_completos(club_id, partidos):
    """id -> nombre completo: primero data/rendimiento, luego banca y eventos de los partidos."""
    nombres = {}
    for _, _, p in partidos:
        for e in p["equipos"]:
            if e["club_id"] == club_id:
                nombres.update({b["id"]: b["nombre"] for b in e["banca"]})
        for c in p["cambios"]:
            nombres.update({c["sale"]["id"]: c["sale"]["nombre"], c["entra"]["id"]: c["entra"]["nombre"]})
        for g in p["goles"]:
            for j in (g["autor"], g["asistencia"]):
                if j:
                    nombres[j["id"]] = j["nombre"]
        for t in p["tarjetas"]:
            nombres[t["jugador"]["id"]] = t["jugador"]["nombre"]
    rendimiento = RAIZ / "data" / "rendimiento" / f"{club_id}.json"
    plantel = set()
    if rendimiento.exists():
        for j in json.loads(rendimiento.read_text(encoding="utf-8"))["jugadores"]:
            nombres[j["id"]] = j["nombre"]
            plantel.add(j["id"])
    return nombres, plantel


def puntajes_club(club_id, partidos, criterio, pf):
    """{jugador_id: {rol: puntaje}} y nombres cortos de los titulares como respaldo."""
    puntajes, cortos = {}, {}
    duracion = criterio["minutos"]["duracion"]
    for pid, _, p in partidos:
        ids_equipos = [e["club_id"] for e in p["equipos"]]
        for e in p["equipos"]:
            if e["club_id"] != club_id:
                continue
            rival = next(c for c in ids_equipos if c != club_id)
            factor = peso_rival(club_id, rival, criterio) * pf[(club_id, pid)]
            cortos.update({t["id"]: t["nombre"] for t in e["titulares"]})
            for jid, j in minutos_por_jugador(p, e, criterio).items():
                if j["minutos"] > 0:
                    roles = puntajes.setdefault(jid, {})
                    roles[j["rol"]] = roles.get(j["rol"], 0) + j["minutos"] / duracion * factor
    return puntajes, cortos


def convocatorias_club(club_id, partidos, criterio):
    """{(jugador_id, rol): veces en la banca del club con la posicion de ese rol}."""
    veces = {}
    for _, _, p in partidos:
        for e in p["equipos"]:
            if e["club_id"] != club_id:
                continue
            for b in e["banca"]:
                rol = criterio["rol_banca"].get(b["posicion"])
                if rol:
                    veces[(b["id"], rol)] = veces.get((b["id"], rol), 0) + 1
    return veces


def plantel_rendimiento(club_id):
    ruta = RAIZ / "data" / "rendimiento" / f"{club_id}.json"
    if not ruta.exists():
        raise ErrorPlantilla(f"falta {ruta.relative_to(RAIZ)}")
    return json.loads(ruta.read_text(encoding="utf-8"))["jugadores"]


def minutos_rendimiento(club_id):
    return {j["id"]: j["minutos"] for j in plantel_rendimiento(club_id)}


def variante_club(club_id, formacion, partidos):
    """La variante de Transfermarkt mas usada por el club dentro de la formacion agrupada
    (empate: la mas reciente) y las coordenadas de sus titulares."""
    usos = {}
    for _, fecha, p in partidos:
        for e in p["equipos"]:
            if e["club_id"] == club_id and "-".join(map(str, lineas(e["formacion"]))) == formacion:
                veces, ultima, _ = usos.get(e["formacion"], (0, None, None))
                coords = [(t["top"], t["left"]) for t in e["titulares"]]
                usos[e["formacion"]] = (veces + 1, max(fecha, ultima) if ultima else fecha, coords)
    if not usos:
        raise ErrorPlantilla(f"el club no uso nunca la formacion {formacion}")
    variante = max(usos, key=lambda v: (usos[v][0], usos[v][1]))
    return variante, usos[variante][2]


def armar_club(club_id, partidos, criterio, pf):
    formaciones = json.loads((PARTIDOS / "formacion_por_club.json").read_text(encoding="utf-8"))["clubes"]
    club = next((c for c in formaciones if c["club_id"] == club_id), None)
    if club is None:
        raise ErrorPlantilla(f"el club {club_id} no esta en formacion_por_club.json")
    variante, coords = variante_club(club_id, club["formacion"], partidos)
    casillas = [rol for _, rol in casillas_por_coordenadas(variante, coords, criterio["reglas_rol"])]
    puntajes, cortos = puntajes_club(club_id, partidos, criterio, pf)
    nombres, plantel = nombres_completos(club_id, partidos)

    usados = set()
    titulares, suplentes = [None] * len(casillas), [None] * len(casillas)

    def natural(destino):
        # de mayor a menor puntaje: cada jugador va a la primera casilla libre de su rol
        candidatos = sorted(((pts, jid, rol) for jid, rs in puntajes.items() for rol, pts in rs.items()),
                            key=lambda x: (-x[0], x[1]))
        for pts, jid, rol in candidatos:
            if jid in usados:
                continue
            libre = next((k for k, r in enumerate(casillas) if r == rol and destino[k] is None), None)
            if libre is not None:
                destino[libre] = {"id": jid, "rol": rol, "puntaje": pts}
                usados.add(jid)

    def reemplazo(k):
        rol = casillas[k]
        for grupo in criterio["reemplazos"][rol]:
            opciones = [(pts, jid, r) for jid, rs in puntajes.items() if jid not in usados
                        for r, pts in rs.items() if r in grupo]
            if opciones:
                pts, jid, r = max(opciones, key=lambda x: (x[0], x[1]))
                usados.add(jid)
                return {"id": jid, "rol": rol, "puntaje": pts, "reemplazo_de_rol": r}
        return None

    convocatorias = convocatorias_club(club_id, partidos, criterio)
    min_rend = minutos_rendimiento(club_id)

    def por_banca(k):
        # suplente: el que fue a la banca con la posicion de ese rol, por convocatorias;
        # empate: mas minutos en data/rendimiento
        rol = casillas[k]
        opciones = [(n, min_rend.get(jid, 0), jid) for (jid, r), n in convocatorias.items()
                    if r == rol and jid not in usados]
        if not opciones:
            return None
        n, _, jid = max(opciones)
        usados.add(jid)
        return {"id": jid, "rol": rol, "puntaje": puntajes.get(jid, {}).get(rol, 0), "convocatorias": n}

    avisos = []

    def sin_jugador(k, cual):
        extra = " (ERROR: faltan arqueros, se revisa a mano)" if casillas[k] == "arquero" else ""
        avisos.append(f"casilla {k + 1} ({casillas[k]}) sin {cual}{extra}")

    jugadores_plantel = plantel_rendimiento(club_id)
    rol_posicion = criterio["rol_posicion_plantel"]

    # data/rendimiento trae el total de la temporada, con jugadores que ya se fueron:
    # se descarta a quien aparece con otro club en el Clausura
    de_otro_club = set()
    for _, _, p in partidos:
        for e in p["equipos"]:
            if e["club_id"] != club_id:
                de_otro_club.update(j["id"] for j in e["titulares"] + e["banca"])
        for c in p["cambios"]:
            if c["club_id"] != club_id:
                de_otro_club.update((c["sale"]["id"], c["entra"]["id"]))

    def es_arquero(j):
        return rol_posicion.get(j["posicion"]) == "arquero"

    def por_plantel(k, cualquier_rol=False):
        # suplente: del plantel de data/rendimiento, por minutos en la temporada;
        # con cualquier_rol=True es el ultimo recurso: no mira la posicion, salvo arquero / campo
        rol = casillas[k]
        opciones = [(j["minutos"], j["id"]) for j in jugadores_plantel
                    if j["id"] not in usados and j["id"] not in de_otro_club
                    and (es_arquero(j) == (rol == "arquero") if cualquier_rol
                         else rol_posicion.get(j["posicion"]) == rol)]
        if not opciones:
            return None
        _, jid = max(opciones)
        usados.add(jid)
        return {"id": jid, "rol": rol, "puntaje": puntajes.get(jid, {}).get(rol, 0)}

    natural(titulares)
    natural(suplentes)
    for j in suplentes:
        if j:
            j["origen"] = "minutos"
    for k in range(len(casillas)):
        if titulares[k] is None:
            titulares[k] = reemplazo(k)
            if titulares[k] is None:
                sin_jugador(k, "titular")
    pasos = (("banca", por_banca), ("plantel", por_plantel), ("reemplazo", reemplazo),
             ("ultimo_recurso", lambda k: por_plantel(k, cualquier_rol=True)))
    for origen, paso in pasos:
        for k in range(len(casillas)):
            if suplentes[k] is None:
                suplentes[k] = paso(k)
                if suplentes[k] is not None:
                    suplentes[k]["origen"] = origen
    for k in range(len(casillas)):
        if suplentes[k] is None:
            sin_jugador(k, "suplente")

    def ficha(j):
        if j is None:
            return None
        if j["id"] not in plantel:
            avisos.append(f"{nombres.get(j['id'], j['id'])} no figura en data/rendimiento del club")
        return {"id": j["id"], "nombre": nombres.get(j["id"], cortos.get(j["id"])), "rol": j["rol"],
                "puntaje": round(j["puntaje"], 3),
                **({"reemplazo_de_rol": j["reemplazo_de_rol"]} if "reemplazo_de_rol" in j else {}),
                **({"origen": j["origen"]} if "origen" in j else {}),
                **({"convocatorias": j["convocatorias"]} if "convocatorias" in j else {})}

    salida = {
        "club_id": club_id,
        "club_nombre": club["club_nombre"],
        "formacion": club["formacion"],
        "variante": variante,
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "casillas": [{"casilla": k + 1, "rol": rol, "titular": ficha(titulares[k]), "suplente": ficha(suplentes[k])}
                     for k, rol in enumerate(casillas)],
    }
    return salida, avisos


def revisar_roles(partido_id):
    criterio = cargar_criterio()
    partido = json.loads((PARTIDOS / f"{partido_id}.json").read_text(encoding="utf-8"))
    pf = pesos_fecha(criterio)
    ids_equipos = [e["club_id"] for e in partido["equipos"]]
    for e in partido["equipos"]:
        rival = next(c for c in ids_equipos if c != e["club_id"])
        pr, pfe = peso_rival(e["club_id"], rival, criterio), pf[(e["club_id"], partido_id)]
        print(f"\n{e['club_nombre']} - {e['formacion']} | peso rival {pr:.3f} | peso fecha {pfe:.3f}")
        nombres = {t["id"]: t for t in e["titulares"]} | {b["id"]: b for b in e["banca"]}
        for jid, j in minutos_por_jugador(partido, e, criterio).items():
            t = nombres[jid]
            pos = f"top {t['top']:g} left {t['left']:g}" if "top" in t else f"banca {t['posicion']}"
            puntaje = j["minutos"] / criterio["minutos"]["duracion"] * pr * pfe
            print(f"  {t['nombre']:<22} {pos:<22} -> {j['rol']:<20} {j['inicio']:>2}-{j['fin']:<2} "
                  f"{j['minutos']:>2}' puntaje {puntaje:.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--revisar-roles", metavar="PARTIDO_ID", help="muestra roles, minutos y puntaje de un partido")
    ap.add_argument("--club", nargs="+", metavar="CLUB_ID", help="arma solo estos clubes")
    args = ap.parse_args()
    try:
        if args.revisar_roles:
            revisar_roles(args.revisar_roles)
            return
        criterio = cargar_criterio()
        partidos = cargar_partidos()
        pf = pesos_fecha(criterio)
        clubes = args.club or [c["club_id"] for c in criterio["tabla_clausura"]]
        SALIDA.mkdir(parents=True, exist_ok=True)
        for club_id in clubes:
            plantilla, avisos = armar_club(club_id, partidos, criterio, pf)
            (SALIDA / f"{club_id}.json").write_text(json.dumps(plantilla, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
            print(f"OK    {club_id:>6} {plantilla['club_nombre']}: {plantilla['formacion']} ({plantilla['variante']})")
            for a in avisos:
                print(f"      AVISO: {a}")
    except ErrorPlantilla as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
