"""Convierte un partido real extraido de Transfermarkt (data/partidos/<id>.json) en el JSON
que espera pfb/imagenes/alineacion.py, para un club de ese partido.

Uso (desde la raiz del repo):
    python scripts/partido_a_alineacion.py <partido_id> <club_id> <salida.json>

Toma data/partidos/<partido_id>.json, data/rendimiento/<club_id>.json y el color del club de
data/colores_clubes.json.

El rendimiento del club (data/rendimiento/<club_id>.json) se usa solo para sacar el nombre
de pila de los titulares, porque la ficha del partido trae solo el apellido.
"""

import json
import sys

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pfb.imagenes.alineacion import FORMACIONES, forma_base  # noqa: E402
from pfb.imagenes.nombres import corto  # noqa: E402


def tipo_tarjeta(partido, jugador_id):
    """La tarjeta mas grave del jugador en el partido, o None."""
    tipos = {x["tipo"] for x in partido["tarjetas"] if x["jugador"]["id"] == jugador_id}
    for t in ("roja", "doble_amarilla", "amarilla"):
        if t in tipos:
            return t
    return None


def minuto(evento):
    return evento["minuto"] + (evento.get("anadido") or 0)


def convertir(partido, club_id, color, rendimiento):
    equipo = next(e for e in partido["equipos"] if e["club_id"] == club_id)
    nombres = {j["id"]: j["nombre"] for j in rendimiento["jugadores"]}

    # Arquero = el de mayor 'top'. El resto, de atras hacia adelante por lineas
    # segun la formacion; dentro de cada linea, de izquierda a derecha ('left').
    tit = sorted(equipo["titulares"], key=lambda j: -j["top"])
    arquero, campo = tit[0], tit[1:]
    lineas = [int(n) for n in forma_base(equipo["formacion"]).split("-")]
    ordenados, i = [arquero], 0
    for n in lineas:
        ordenados += sorted(campo[i:i + n], key=lambda j: j["left"])
        i += n
    assert len(ordenados) == len(FORMACIONES[forma_base(equipo["formacion"])])

    jugadores = []
    for t in ordenados:
        completo = nombres.get(t["id"], t["nombre"])
        # La ficha a veces trae el apellido cortado ('Miguel Sil.'): ahi se usa el del nombre completo.
        cortado = t["nombre"].endswith(".") and t["id"] in nombres
        j = {"nombre": corto(completo, None if cortado else t["nombre"])}
        goles = [g for g in partido["goles"] if g["autor"]["id"] == t["id"]]
        if goles:
            j["goles"] = len(goles)
        tipo = tipo_tarjeta(partido, t["id"])
        if tipo:
            j["tarjeta"] = tipo
        sale = next((c for c in partido["cambios"] if c["sale"]["id"] == t["id"]), None)
        if sale:
            entra = sale["entra"]
            c = {"entra": corto(entra["nombre"]), "minuto": minuto(sale)}
            g_sup = [g for g in partido["goles"] if g["autor"]["id"] == entra["id"]]
            if g_sup:
                c["goles"] = len(g_sup)
            tipo_sup = tipo_tarjeta(partido, entra["id"])
            if tipo_sup:
                c["tarjeta"] = tipo_sup
            j["cambio"] = c
        jugadores.append(j)

    return {
        "club": rendimiento.get("club_nombre", equipo["club_nombre"]),
        "club_id": str(club_id),
        "color": color,
        "formacion": forma_base(equipo["formacion"]),
        "jugadores": jugadores,
    }


def cargar_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    partido_id, club_id, salida = sys.argv[1:]
    partido = cargar_json(RAIZ / "data" / "partidos" / f"{partido_id}.json")
    rendimiento = cargar_json(RAIZ / "data" / "rendimiento" / f"{club_id}.json")
    c = cargar_json(RAIZ / "data" / "colores_clubes.json")[club_id]
    color = {k: v for k, v in c.items() if k != "club"}
    datos = convertir(partido, club_id, color, rendimiento)
    datos["club"] = c["club"]
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
