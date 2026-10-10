"""Extrae partidos jugados y minutos por jugador de la pagina de rendimiento de cada club en Transfermarkt.

Uso:
    python scripts/extraer_rendimiento.py              # los 18 clubes
    python scripts/extraer_rendimiento.py --club 184   # un solo club
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

TEMPORADA_ESPERADA = "25/26"
ETIQUETA_ESPERADA = f"Total {TEMPORADA_ESPERADA}"
URL = "https://www.transfermarkt.com/-/leistungsdaten/verein/{club_id}"
PAUSA_SEGUNDOS = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

RAIZ = Path(__file__).resolve().parent.parent
CLUBES = RAIZ / "data" / "clubes_liga1_2026.json"
SALIDA = RAIZ / "data" / "rendimiento"
SALIDA_RAW = SALIDA / "raw"

COL_PARTIDOS = "Appearances"
COL_MINUTOS = "Minutes played"
SIN_USO = ("Not used during this season", "Not in squad during this season")
RE_SPIELER = re.compile(r"/profil/spieler/(\d+)")
RE_CANONICAL_ID = re.compile(r"/verein/(\d+)")


class ErrorExtraccion(Exception):
    pass


class Bloqueo403(Exception):
    pass


class PaginaRendimiento(HTMLParser):
    """Lee la tabla.items, la etiqueta de temporada seleccionada y el canonical."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical = None
        self.temporada = None
        self.encabezados = []
        self.filas = []
        self._en_reldata = False
        self._opcion_sel = None
        self._prof = 0  # profundidad de tablas dentro de table.items
        self._seccion = None  # "thead" | "tbody"
        self._th = None
        self._fila = None
        self._td = None
        self._td_inline = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "select" and a.get("name") == "reldata":
            self._en_reldata = True
        elif tag == "option" and self._en_reldata and "selected" in a:
            self._opcion_sel = []
        elif tag == "table":
            if self._prof:
                self._prof += 1
            elif a.get("class") == "items":
                self._prof = 1
        elif not self._prof:
            return
        elif tag in ("thead", "tbody") and self._prof == 1:
            self._seccion = tag
        elif tag == "th" and self._prof == 1 and self._seccion == "thead":
            self._th = {"texto": [], "title": None}
        elif tag == "span" and self._th is not None and a.get("title"):
            self._th["title"] = a["title"]
        elif tag == "tr" and self._prof == 1 and self._seccion == "tbody":
            self._fila = {"tds": [], "inline": [], "id": None, "nombre": None}
        elif tag == "td" and self._fila is not None:
            if self._prof == 1:
                self._td = []
            elif self._prof == 2:
                self._td_inline = []
        elif tag == "a" and self._fila is not None and self._fila["id"] is None:
            m = RE_SPIELER.search(a.get("href") or "")
            if m:
                self._fila["id"] = m.group(1)
                self._fila["nombre"] = a.get("title")

    def handle_endtag(self, tag):
        if tag == "select" and self._en_reldata:
            self._en_reldata = False
        elif tag == "option" and self._opcion_sel is not None:
            self.temporada = " ".join("".join(self._opcion_sel).split())
            self._opcion_sel = None
        elif tag == "table" and self._prof:
            self._prof -= 1
        elif not self._prof:
            return
        elif tag in ("thead", "tbody") and self._prof == 1:
            self._seccion = None
        elif tag == "th" and self._th is not None:
            self.encabezados.append(self._th["title"] or "".join(self._th["texto"]).strip())
            self._th = None
        elif tag == "td" and self._prof == 1 and self._td is not None:
            self._fila["tds"].append(" ".join("".join(self._td).split()))
            self._td = None
        elif tag == "td" and self._prof == 2 and self._td_inline is not None:
            self._fila["inline"].append(" ".join("".join(self._td_inline).split()))
            self._td_inline = None
        elif tag == "tr" and self._prof == 1 and self._fila is not None:
            self.filas.append(self._fila)
            self._fila = None

    def handle_data(self, data):
        if self._opcion_sel is not None:
            self._opcion_sel.append(data)
        if self._th is not None:
            self._th["texto"].append(data)
        if self._td_inline is not None:
            self._td_inline.append(data)
        elif self._td is not None:
            self._td.append(data)


def a_entero(texto, campo, jugador):
    """'2.430'' -> 2430, '27' -> 27, '-' o un texto de SIN_USO -> 0. Cualquier otra cosa es error."""
    if texto == "-" or texto in SIN_USO:
        return 0
    limpio = texto.rstrip("'").replace(".", "")
    if not limpio.isdigit():
        raise ErrorExtraccion(f"{campo} no reconocido para {jugador}: {texto!r}")
    return int(limpio)


def extraer(html, club_id):
    p = PaginaRendimiento()
    p.feed(html)
    p.close()

    m = RE_CANONICAL_ID.search(p.canonical or "")
    if not m or m.group(1) != club_id:
        raise ErrorExtraccion(f"canonical no corresponde al club {club_id}: {p.canonical!r}")
    if p.temporada != ETIQUETA_ESPERADA:
        raise ErrorExtraccion(f"temporada {p.temporada!r}, se esperaba {ETIQUETA_ESPERADA!r}")
    if COL_PARTIDOS not in p.encabezados or COL_MINUTOS not in p.encabezados:
        raise ErrorExtraccion(f"encabezados inesperados: {p.encabezados}")
    if not p.filas:
        raise ErrorExtraccion("table.items sin filas")

    i_part = p.encabezados.index(COL_PARTIDOS)
    i_min = p.encabezados.index(COL_MINUTOS)
    jugadores = []
    for f in p.filas:
        if f["id"] is None or len(f["tds"]) != len(p.encabezados) or not f["inline"]:
            raise ErrorExtraccion(f"fila con estructura inesperada: {f}")
        jugadores.append({
            "id": f["id"],
            "nombre": f["nombre"],
            "posicion": f["inline"][-1],
            "partidos": a_entero(f["tds"][i_part], "partidos", f["nombre"]),
            "minutos": a_entero(f["tds"][i_min], "minutos", f["nombre"]),
        })
    return p.temporada, jugadores


def descargar(club_id):
    url = URL.format(club_id=club_id)
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=60) as r:
            return r.read()
    except HTTPError as e:
        if e.code == 403:
            raise Bloqueo403(url) from e
        raise ErrorExtraccion(f"HTTP {e.code} en {url}") from e


def procesar(club):
    club_id = club["id"]
    raw = descargar(club_id)
    temporada, jugadores = extraer(raw.decode("utf-8"), club_id)
    SALIDA_RAW.mkdir(parents=True, exist_ok=True)
    (SALIDA_RAW / f"{club_id}.html").write_bytes(raw)
    datos = {
        "club_id": club_id,
        "club_nombre": club["name"],
        "temporada": temporada,
        "fecha_extraccion": datetime.now().isoformat(timespec="seconds"),
        "jugadores": jugadores,
    }
    (SALIDA / f"{club_id}.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return len(jugadores)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--club", help="id de Transfermarkt de un solo club")
    args = ap.parse_args()

    clubes = json.loads(CLUBES.read_text(encoding="utf-8"))["clubs"]
    if args.club:
        clubes = [c for c in clubes if c["id"] == args.club]
        if not clubes:
            sys.exit(f"El club {args.club} no esta en {CLUBES.name}")

    fallidos = []
    for n, club in enumerate(clubes):
        if n:
            time.sleep(PAUSA_SEGUNDOS)
        try:
            total = procesar(club)
            print(f"OK    {club['id']:>6} {club['name']}: {total} jugadores")
        except Bloqueo403 as e:
            sys.exit(f"403   {club['id']:>6} {club['name']}: bloqueo en {e}. Se detiene sin reintentar.")
        except ErrorExtraccion as e:
            print(f"ERROR {club['id']:>6} {club['name']}: {e}. No se guardo nada de este club.")
            fallidos.append(club["id"])

    if fallidos:
        sys.exit(f"Clubes sin guardar: {', '.join(fallidos)}")


if __name__ == "__main__":
    main()
