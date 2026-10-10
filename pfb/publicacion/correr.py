"""Cierra el circuito: motor → imágenes → texto → Facebook (§7.2, §8).

    python -m pfb.publicacion.correr <temporada_id> [--pagina prueba|real]

Sin --pagina es dry-run: no toca la red ni marca nada en publicados.json. Si hay algo pendiente lo
muestra y termina; si no, juega el siguiente partido, lo muestra y termina.
Con --pagina: primero publica lo pendiente (sin volver a simular) y después juega el siguiente y
lo publica. Por partido: guardar registro → publicar → marcar como publicado. Cuando una fecha
cierra (todos sus partidos publicados), publica la tabla.
"""

import argparse
import sys

from pfb.imagenes.alineacion import generar as generar_alineacion
from pfb.imagenes.marcador import generar_marcador
from pfb.imagenes.tabla import generar_tabla
from pfb.motor.partido import cargar_parametros
from pfb.motor.salida import alineacion_desde_registro, cargar_colores
from pfb.motor.temporada import (CARPETA_TEMPORADAS, cargar_nombres, cargar_registros, cargar_temporada,
                                 carpeta_temporada, jugar_siguiente, partido_id)
from pfb.motor.temporada import tabla as calcular_tabla
from pfb.publicacion.facebook import PAGINAS, Cliente, ErrorFacebook
from pfb.publicacion.publicados import (MezclaDePaginas, cargar_publicados, clave_tabla, comprobar_pagina,
                                        marcar)
from pfb.publicacion.texto import texto_partido, texto_tabla


# --- Imágenes ---

def generar_imagenes_partido(registro, carpeta):
    """Marcador, alineación local y alineación visita, en ese orden."""
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = [carpeta / "marcador.png", carpeta / "alineacion_local.png", carpeta / "alineacion_visita.png"]
    generar_marcador(registro, rutas[0])
    colores = cargar_colores()
    for lado, ruta in zip(("local", "visita"), rutas[1:]):
        generar_alineacion(alineacion_desde_registro(registro, registro[lado]["club_id"], colores), ruta)
    return rutas


def generar_imagen_tabla(filas, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    generar_tabla(filas, ruta)
    return ruta


# --- Pendientes ---

def pendientes(temporada, registros, publicados):
    """Lo que falta publicar, en el orden del fixture: ("partido", registro) o ("tabla", fecha).
    La tabla de una fecha está pendiente cuando todos sus partidos ya están publicados."""
    por_id = {r["partido_id"]: r for r in registros}
    salida = []
    for f, partidos in enumerate(temporada["fixture"], start=1):
        ids = [partido_id(f, p) for p in range(1, len(partidos) + 1)]
        salida += [("partido", por_id[pid]) for pid in ids if pid in por_id and pid not in publicados]
        if all(pid in publicados for pid in ids) and clave_tabla(f) not in publicados:
            salida.append(("tabla", f))
    return salida


def armar_post(item, temporada, registros, carpeta_imagenes, nombres,
               generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla):
    """Devuelve (clave, tipo, mensaje, fotos). La tabla de la fecha F sale solo de las fechas 1..F."""
    tipo, dato = item
    if tipo == "partido":
        clave = dato["partido_id"]
        return clave, tipo, texto_partido(dato, nombres), generar_partido(dato, carpeta_imagenes / clave)
    clave = clave_tabla(dato)
    filas = calcular_tabla([r for r in registros if r["fecha"] <= dato], club_ids=temporada["clubes"],
                           nombres=nombres)
    return clave, tipo, texto_tabla(dato), [generar_tabla_img(filas, carpeta_imagenes / f"{clave}.png")]


# --- Corrida ---

def correr(temporada_id, pagina=None, base=CARPETA_TEMPORADAS, params=None, cliente=None,
           generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla,
           mostrar=print, ahora=None):
    """pagina None = dry-run. cliente: un facebook.Cliente ya armado (si no, sale del .env)."""
    temporada = cargar_temporada(temporada_id, base)
    nombres = cargar_nombres()
    carpeta_imagenes = carpeta_temporada(temporada_id, base) / "imagenes"
    params = params or cargar_parametros()

    def armar(item):
        return armar_post(item, temporada, cargar_registros(temporada_id, base), carpeta_imagenes, nombres,
                          generar_partido, generar_tabla_img)

    def lista():
        return pendientes(temporada, cargar_registros(temporada_id, base), cargar_publicados(temporada_id, base))

    if pagina is None:
        items = lista()
        if not items:
            registro = jugar_siguiente(temporada_id, params, base)
            if registro is None:
                mostrar("la temporada ya terminó")
                return
            items = [("partido", registro)]
        for item in items:
            clave, tipo, mensaje, fotos = armar(item)
            mostrar(f"[dry-run] {clave} ({tipo})\n{mensaje}\nimágenes:\n" + "\n".join(f"  {r}" for r in fotos))
        return

    if cliente is None:
        cliente = Cliente.desde_env(pagina)
    elif cliente.pagina != pagina:
        raise ValueError(f"el cliente es de la página {cliente.pagina}, no de {pagina}")
    comprobar_pagina(cargar_publicados(temporada_id, base), cliente.page_id)
    cliente.verificar_pagina()

    def publicar_pendientes():
        # de a uno y recalculando: publicar el último partido de una fecha vuelve pendiente su tabla
        while items := lista():
            clave, tipo, mensaje, fotos = armar(items[0])
            post_id = cliente.publicar_post(mensaje, fotos)
            marcar(temporada_id, clave, tipo, post_id, cliente.pagina, cliente.page_id, base, ahora)
            mostrar(f"publicado {clave} ({tipo}): post {post_id}")

    publicar_pendientes()
    if jugar_siguiente(temporada_id, params, base) is None:
        mostrar("la temporada ya terminó")
        return
    publicar_pendientes()


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Juega y publica el siguiente partido del PFB v2.")
    parser.add_argument("temporada_id")
    parser.add_argument("--pagina", choices=sorted(PAGINAS), help="sin esta opción es dry-run")
    args = parser.parse_args(argv)
    try:
        correr(args.temporada_id, pagina=args.pagina, base=CARPETA_TEMPORADAS)
    except (ErrorFacebook, MezclaDePaginas) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
