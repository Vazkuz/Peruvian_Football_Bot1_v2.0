"""Arma la formacion de cada club en el Clausura a partir de los partidos ya extraidos (sin red).

Agrupa variantes con los mismos numeros ("4-4-2 double 6" -> "4-4-2"). Gana la mas usada;
si hay empate, la usada en el partido mas reciente.

Uso:
    python scripts/formacion_por_club.py
"""

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLUBES = RAIZ / "data" / "clubes_liga1_2026.json"
PARTIDOS = RAIZ / "data" / "partidos"
IDS = PARTIDOS / "ids_clausura.json"
SALIDA = PARTIDOS / "formacion_por_club.json"

RE_NUMEROS = re.compile(r"^(\d+(?:-\d+)+)(?:\s|$)")
RE_FECHA = re.compile(r"<title>[^<]*, (\d{2})/(\d{2})/(\d{4}) - [^<]*</title>")


def numeros(formacion):
    m = RE_NUMEROS.match(formacion)
    if not m:
        sys.exit(f"Formacion sin numeros reconocibles: {formacion!r}")
    return m.group(1)


def fecha_partido(partido_id):
    html = (PARTIDOS / "raw" / f"{partido_id}.html").read_text(encoding="utf-8")
    m = RE_FECHA.search(html)
    if not m:
        sys.exit(f"Sin fecha en el titulo del partido {partido_id}")
    dia, mes, anio = map(int, m.groups())
    return date(anio, mes, dia)


def main():
    clubes = json.loads(CLUBES.read_text(encoding="utf-8"))["clubs"]
    ids = [p["id"] for p in json.loads(IDS.read_text(encoding="utf-8"))["partidos"]]
    faltan = [i for i in ids if not (PARTIDOS / f"{i}.json").exists()]
    if faltan:
        sys.exit(f"Faltan partidos por extraer: {', '.join(faltan)}")

    usos = defaultdict(list)  # club_id -> [(fecha, partido_id, formacion original)]
    for i in ids:
        partido = json.loads((PARTIDOS / f"{i}.json").read_text(encoding="utf-8"))
        fecha = fecha_partido(i)
        for e in partido["equipos"]:
            usos[e["club_id"]].append((fecha, i, e["formacion"]))

    resultado = []
    for club in clubes:
        partidos = sorted(usos[club["id"]])
        if len({f for f, _, _ in partidos}) != len(partidos):
            sys.exit(f"{club['name']}: dos partidos en la misma fecha, no se puede desempatar")
        conteo, ultima = defaultdict(int), {}
        for fecha, _, original in partidos:
            n = numeros(original)
            conteo[n] += 1
            ultima[n] = fecha
        maximo = max(conteo.values())
        empatadas = [n for n, v in conteo.items() if v == maximo]
        ganadora = max(empatadas, key=lambda n: ultima[n])
        resultado.append({
            "club_id": club["id"],
            "club_nombre": club["name"],
            "formacion": ganadora,
            "veces": maximo,
            "empate_con": sorted(n for n in empatadas if n != ganadora),
            "partidos": len(partidos),
            "conteo": dict(sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))),
            "ultimo_uso": {n: ultima[n].isoformat() for n in empatadas},
        })

    SALIDA.write_text(json.dumps({
        "competicion": "TDeC",
        "temporada_id": "2025",
        "criterio": "mas usada agrupando por numeros; empate: la del partido mas reciente",
        "fecha_generacion": datetime.now().isoformat(timespec="seconds"),
        "clubes": resultado,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(resultado)} clubes -> {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
