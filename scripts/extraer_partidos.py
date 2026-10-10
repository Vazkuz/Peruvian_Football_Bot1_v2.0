"""Extrae alineaciones y eventos de los partidos jugados del Liga 1 Clausura desde Transfermarkt.

Uso:
    python scripts/extraer_partidos.py                 # usa data/partidos/ids_clausura.json (o lo arma) y baja los partidos
    python scripts/extraer_partidos.py --solo-ids      # arma (o rehace) solo la lista de ids desde los 18 calendarios
    python scripts/extraer_partidos.py --partido <id>  # un solo partido
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

COMPETICION = "TDeC"
TEMPORADA_ID = "2025"
BASE = "https://www.transfermarkt.com"
RUTA_CALENDARIO = "/-/spielplan/verein/{club_id}"
RUTA_PARTIDO = "/spielbericht/index/spielbericht/{partido_id}"
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
SALIDA = RAIZ / "data" / "partidos"
SALIDA_RAW = SALIDA / "raw"
IDS = SALIDA / "ids_clausura.json"

# El minuto viene en un sprite de celdas de 36 px: 10 minutos por fila.
# Verificado contra la linea de tiempo (left %) en el partido 5034417.
CELDA_SPRITE = 36
TARJETAS = {"sb-gelb": "amarilla", "sb-rot": "roja", "sb-gelbrot": "doble_amarilla"}

RE_SPIELER = re.compile(r"/profil/spieler/(\d+)|/leistungsdatendetails/spieler/(\d+)")
RE_VEREIN = re.compile(r"/verein/(\d+)")
RE_PARTIDO = re.compile(r"/spielbericht/(\d+)$")
RE_RESULTADO = re.compile(r"^\d+:\d+$")
RE_SPRITE = re.compile(r"background-position:\s*-?(\d+)px\s+-?(\d+)px")
RE_TOP_LEFT = re.compile(r"top:\s*([\d.]+)%;\s*left:\s*([\d.]+)%")
VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class ErrorEstructura(Exception):
    pass


class Bloqueo403(Exception):
    pass


# --- arbol HTML minimo sobre html.parser ---

class Nodo:
    def __init__(self, tag, attrs, padre):
        self.tag, self.attrs, self.padre = tag, dict(attrs), padre
        self.hijos = []

    def clases(self):
        return (self.attrs.get("class") or "").split()

    def texto(self):
        partes = []
        for h in self.hijos:
            partes.append(h if isinstance(h, str) else h.texto())
        return " ".join(" ".join(partes).split())

    def recorrer(self):
        for h in self.hijos:
            if isinstance(h, Nodo):
                yield h
                yield from h.recorrer()

    def buscar(self, tag=None, clase=None, **attrs):
        for n in self.recorrer():
            if tag and n.tag != tag:
                continue
            if clase and clase not in n.clases():
                continue
            if all(n.attrs.get(k) == v for k, v in attrs.items()):
                yield n

    def primero(self, tag=None, clase=None, **attrs):
        return next(self.buscar(tag, clase, **attrs), None)


class Arbol(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.raiz = Nodo("#doc", [], None)
        self._actual = self.raiz
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        n = Nodo(tag, attrs, self._actual)
        self._actual.hijos.append(n)
        if tag not in VACIOS:
            self._actual = n

    def handle_startendtag(self, tag, attrs):
        self._actual.hijos.append(Nodo(tag, attrs, self._actual))

    def handle_endtag(self, tag):
        n = self._actual
        while n is not self.raiz and n.tag != tag:
            n = n.padre
        if n is not self.raiz:  # cierres sin apertura se ignoran
            self._actual = n.padre

    def handle_data(self, data):
        self._actual.hijos.append(data)


# --- red ---

_ultima_llamada = None


def descargar(ruta):
    global _ultima_llamada
    if _ultima_llamada is not None:
        espera = PAUSA_SEGUNDOS - (time.monotonic() - _ultima_llamada)
        if espera > 0:
            time.sleep(espera)
    url = BASE + ruta
    try:
        with urlopen(Request(url, headers=HEADERS), timeout=60) as r:
            return r.read()
    except HTTPError as e:
        if e.code == 403:
            raise Bloqueo403(url) from e
        raise ErrorEstructura(f"HTTP {e.code} en {url}") from e
    finally:
        _ultima_llamada = time.monotonic()


# --- calendario ---

def ids_de_calendario(html, club_id):
    raiz = Arbol(html).raiz
    canonical = raiz.primero("link", rel="canonical")
    m = RE_VEREIN.search(canonical.attrs.get("href", "") if canonical else "")
    if not m or m.group(1) != club_id:
        raise ErrorEstructura(f"canonical no corresponde al club {club_id}")
    select = raiz.primero("select", name="saison_id")
    sel = select and next((o for o in select.buscar("option") if "selected" in o.attrs), None)
    if not sel or sel.attrs.get("value") != TEMPORADA_ID:
        raise ErrorEstructura(f"temporada seleccionada {sel and sel.attrs.get('value')!r}, se esperaba {TEMPORADA_ID!r}")

    nodos = list(raiz.recorrer())
    ancla = next((i for i, n in enumerate(nodos) if n.tag == "a" and n.attrs.get("name") == COMPETICION), None)
    if ancla is None:
        raise ErrorEstructura(f"no hay bloque {COMPETICION} en el calendario")
    tabla = next((n for n in nodos[ancla:] if n.tag == "table"), None)
    if tabla is None or tabla.primero("tbody") is None:
        raise ErrorEstructura(f"bloque {COMPETICION} sin tabla")

    jugados = []
    for tr in tabla.primero("tbody").buscar("tr"):
        a = tr.primero("a", clase="ergebnis-link")
        if a is None or not RE_RESULTADO.match(a.texto()):
            continue
        ruta = a.attrs.get("href", "")
        m = RE_PARTIDO.search(ruta)
        if not m:
            raise ErrorEstructura(f"link de partido inesperado: {ruta!r}")
        jugados.append({"id": m.group(1), "ruta": ruta})
    return jugados


def armar_ids():
    clubes = json.loads(CLUBES.read_text(encoding="utf-8"))["clubs"]
    partidos, fallidos = {}, []
    for club in clubes:
        try:
            html = descargar(RUTA_CALENDARIO.format(club_id=club["id"])).decode("utf-8")
            jugados = ids_de_calendario(html, club["id"])
            for p in jugados:
                partidos.setdefault(p["id"], p)
            print(f"OK    calendario {club['id']:>6} {club['name']}: {len(jugados)} jugados")
        except ErrorEstructura as e:
            print(f"ERROR calendario {club['id']:>6} {club['name']}: {e}")
            fallidos.append(club["id"])
    if fallidos:
        sys.exit(f"Calendarios con error: {', '.join(fallidos)}. No se guardo {IDS.name}.")
    datos = {
        "competicion": COMPETICION,
        "temporada_id": TEMPORADA_ID,
        "fecha_extraccion": datetime.now().isoformat(timespec="seconds"),
        "partidos": sorted(partidos.values(), key=lambda p: int(p["id"])),
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    IDS.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(partidos)} partidos jugados sin repetir -> {IDS.relative_to(RAIZ)}")
    return datos["partidos"]


# --- ficha del partido ---

def jugador(a):
    if a is None:
        return None
    m = RE_SPIELER.search(a.attrs.get("href", ""))
    if not m:
        raise ErrorEstructura(f"link de jugador inesperado: {a.attrs.get('href')!r}")
    return {"id": m.group(1) or m.group(2), "nombre": a.attrs.get("title") or a.texto()}


def club_de(nodo):
    a = next((x for x in nodo.buscar("a") if RE_VEREIN.search(x.attrs.get("href", ""))), None)
    if a is None:
        raise ErrorEstructura("bloque sin link de club")
    return RE_VEREIN.search(a.attrs["href"]).group(1), a.attrs.get("title") or a.texto()


def dorsal(texto):
    return int(texto) if texto.isdigit() else None


def minuto(li):
    span = li.primero("span", clase="sb-sprite-uhr-klein")
    m = RE_SPRITE.search(span.attrs.get("style", "")) if span else None
    if not m:
        raise ErrorEstructura("evento sin minuto reconocible")
    x, y = int(m.group(1)) // CELDA_SPRITE, int(m.group(2)) // CELDA_SPRITE
    extra = span.texto()
    if extra and not re.fullmatch(r"\+\d+", extra):
        raise ErrorEstructura(f"tiempo anadido no reconocido: {extra!r}")
    return y * 10 + x + 1, int(extra[1:]) if extra else 0


def eventos(raiz, seccion):
    div = raiz.primero("div", id=seccion)
    if div is None:  # la seccion no aparece si no hubo eventos de ese tipo
        return []
    salida = []
    for li in div.buscar("li"):
        if not any(c in ("sb-aktion-heim", "sb-aktion-gast") for c in li.clases()):
            continue
        wappen = li.primero("div", clase="sb-aktion-wappen")
        if wappen is None:
            raise ErrorEstructura(f"evento sin club en {seccion}")
        m, extra = minuto(li)
        salida.append((li, {"club_id": club_de(wappen)[0], "minuto": m, "anadido": extra}))
    return salida


def alineacion(bloque):
    titulo = next((n for n in bloque if "formation-subtitle" in n.clases()), None)
    if titulo is None or not titulo.texto().startswith("Starting Line-up:"):
        raise ErrorEstructura("equipo sin 'Starting Line-up'")
    titulares = []
    for c in (n for n in bloque if "formation-player-container" in n.clases()):
        pos = RE_TOP_LEFT.search(c.attrs.get("style", ""))
        num = c.primero("div", clase="tm-shirt-number")
        span = c.primero("span", clase="formation-number-name")
        if not pos or num is None or span is None:
            raise ErrorEstructura("titular con estructura inesperada")
        j = jugador(span.primero("a"))
        titulares.append({**j, "dorsal": dorsal(num.texto()),
                          "top": float(pos.group(1)), "left": float(pos.group(2))})
    if len(titulares) != 11:
        raise ErrorEstructura(f"{len(titulares)} titulares en vez de 11")
    caja = next((n for n in bloque if "aufstellung-ersatzbank-box" in n.clases()), None)
    if caja is None:
        raise ErrorEstructura("equipo sin banca")
    banca = []
    for tr in caja.buscar("tr"):
        a = next((x for x in tr.buscar("a") if RE_SPIELER.search(x.attrs.get("href", ""))), None)
        if a is None:
            continue  # fila del entrenador
        tds = list(tr.buscar("td"))
        num = tr.primero("td", clase="formation-number-substitute")
        banca.append({**jugador(a), "dorsal": dorsal(num.texto()) if num else None,
                      "posicion": tds[-1].texto()})
    return {"formacion": titulo.texto().split(":", 1)[1].strip(), "titulares": titulares, "banca": banca}


def parsear_partido(html, partido_id):
    raiz = Arbol(html).raiz
    canonical = raiz.primero("link", rel="canonical")
    if not canonical or not canonical.attrs.get("href", "").endswith(f"/spielbericht/{partido_id}"):
        raise ErrorEstructura(f"canonical no corresponde al partido {partido_id}")
    comp = raiz.primero("a", clase="direct-headline__link")
    if comp is None or f"/wettbewerb/{COMPETICION}/saison_id/{TEMPORADA_ID}" not in comp.attrs.get("href", ""):
        raise ErrorEstructura(f"el partido no es {COMPETICION} {TEMPORADA_ID}: {comp and comp.attrs.get('href')!r}")
    local = raiz.primero("div", clase="sb-heim")
    if local is None:
        raise ErrorEstructura("sin equipo local en la cabecera")
    local_id = club_de(local)[0]

    # cada equipo va en su propio div.large-6 cuyo primer hijo es la cabecera con el club
    cabeceras = list(raiz.buscar("div", clase="aufstellung-unterueberschrift-mannschaft"))
    if len(cabeceras) != 2:
        raise ErrorEstructura(f"{len(cabeceras)} equipos en las alineaciones")
    equipos = []
    for cab in cabeceras:
        club_id, nombre = club_de(cab)
        equipos.append({"club_id": club_id, "club_nombre": nombre, "local": club_id == local_id,
                        **alineacion(list(cab.padre.recorrer()))})
    if sum(e["local"] for e in equipos) != 1:
        raise ErrorEstructura("no se pudo identificar al local en las alineaciones")

    goles = []
    for li, ev in eventos(raiz, "sb-tore"):
        accion = li.primero("div", clase="sb-aktion-aktion")
        links = [a for a in accion.buscar("a", clase="wichtig")] if accion else []
        if not links:
            raise ErrorEstructura("gol sin autor")
        asistencia = links[1] if "Assist:" in accion.texto() and len(links) > 1 else None
        marcador = li.primero("div", clase="sb-aktion-spielstand")
        goles.append({**ev, "marcador": marcador.texto() if marcador else None,
                      "autor": jugador(links[0]), "asistencia": jugador(asistencia)})

    cambios = []
    for li, ev in eventos(raiz, "sb-wechsel"):
        entra, sale = li.primero("span", clase="sb-aktion-wechsel-ein"), li.primero("span", clase="sb-aktion-wechsel-aus")
        if entra is None or sale is None:
            raise ErrorEstructura("cambio sin jugador que entra o sale")
        cambios.append({**ev, "sale": jugador(sale.primero("a")), "entra": jugador(entra.primero("a"))})

    tarjetas = []
    for li, ev in eventos(raiz, "sb-karten"):
        icono = li.primero("div", clase="sb-aktion-spielstand")
        sprite = icono and icono.primero("span", clase="sb-sprite")
        tipo = next((TARJETAS[c] for c in (sprite.clases() if sprite else []) if c in TARJETAS), None)
        if tipo is None:
            raise ErrorEstructura(f"tipo de tarjeta no reconocido: {sprite and sprite.attrs.get('class')!r}")
        accion = li.primero("div", clase="sb-aktion-aktion")
        tarjetas.append({**ev, "jugador": jugador(accion.primero("a", clase="wichtig") if accion else None),
                         "tipo": tipo, "detalle": accion.texto() if accion else None})

    return {"equipos": equipos, "goles": goles, "cambios": cambios, "tarjetas": tarjetas}


def procesar_partido(p):
    destino = SALIDA / f"{p['id']}.json"
    if destino.exists():
        print(f"YA    partido {p['id']}: existe {destino.name}, no se pide")
        return
    crudo = SALIDA_RAW / f"{p['id']}.html"
    if crudo.exists():  # bajado antes pero no parseado: se reusa sin pedirlo de nuevo
        raw = crudo.read_bytes()
    else:
        raw = descargar(p["ruta"])
        SALIDA_RAW.mkdir(parents=True, exist_ok=True)
        crudo.write_bytes(raw)  # antes de parsear, para no volver a pedirlo si falla
    datos = parsear_partido(raw.decode("utf-8"), p["id"])
    destino.write_text(json.dumps({
        "partido_id": p["id"],
        "ruta": p["ruta"],
        "fecha_extraccion": datetime.now().isoformat(timespec="seconds"),
        **datos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    eq = " vs ".join(f"{e['club_nombre']} ({e['formacion']})" for e in datos["equipos"])
    print(f"OK    partido {p['id']}: {eq}; {len(datos['goles'])} goles, "
          f"{len(datos['cambios'])} cambios, {len(datos['tarjetas'])} tarjetas")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--partido", help="id de Transfermarkt de un solo partido")
    grupo.add_argument("--solo-ids", action="store_true", help="arma solo la lista de ids desde los calendarios")
    args = ap.parse_args()

    try:
        if args.solo_ids:
            armar_ids()
            return
        if args.partido:
            partidos = [{"id": args.partido, "ruta": RUTA_PARTIDO.format(partido_id=args.partido)}]
        elif IDS.exists():
            partidos = json.loads(IDS.read_text(encoding="utf-8"))["partidos"]
        else:
            partidos = armar_ids()

        fallidos = []
        for p in partidos:
            try:
                procesar_partido(p)
            except ErrorEstructura as e:
                print(f"ERROR partido {p['id']}: {e}. No se guardo este partido.")
                fallidos.append(p["id"])
        if fallidos:
            sys.exit(f"Partidos sin guardar: {', '.join(fallidos)}")
    except Bloqueo403 as e:
        sys.exit(f"403 en {e}. Se detiene sin reintentar.")


if __name__ == "__main__":
    main()
