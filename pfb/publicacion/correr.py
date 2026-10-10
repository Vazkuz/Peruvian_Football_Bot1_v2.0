"""Cierra el circuito: motor → imágenes → texto → Facebook → Instagram (§7.2, §8).

    python -m pfb.publicacion.correr <temporada_id> [--pagina prueba|real]

Sin --pagina es dry-run: no toca la red ni marca nada en publicados.json. Si hay algo pendiente lo
muestra y termina; si no, juega el siguiente partido, lo muestra y termina.
Con --pagina: primero publica lo pendiente (sin volver a simular) y después juega el siguiente y
lo publica. Por partido: guardar registro → publicar en Facebook → marcar con el post → publicar en
Instagram → marcar con la publicación → comentar → marcar con el comentario. Si una parte falla,
la siguiente corrida retoma desde esa parte. Cuando una fecha cierra (todos sus partidos completos),
publica la tabla de la misma forma.
"""

import argparse
import sys
from datetime import datetime

from pfb.imagenes.alineacion import generar as generar_alineacion
from pfb.imagenes.marcador import generar_marcador
from pfb.imagenes.relleno import rellenar_cuadrado
from pfb.imagenes.tabla import generar_tabla
from pfb.motor.partido import cargar_parametros
from pfb.motor.salida import alineacion_desde_registro, cargar_colores
from pfb.motor.temporada import (CARPETA_TEMPORADAS, cargar_nombres, cargar_registros, cargar_temporada,
                                 carpeta_temporada, jugar_siguiente, partido_id)
from pfb.motor.temporada import tabla as calcular_tabla
from pfb.publicacion.facebook import PAGINAS, Cliente, ErrorFacebook
from pfb.publicacion.instagram import Instagram, comprobar_caption
from pfb.publicacion.publicados import (MezclaDePaginas, cargar_publicados, clave_tabla, comprobar_pagina, falta,
                                        marcar, marcar_comentario, marcar_instagram)
from pfb.publicacion.texto import COMENTARIO_INSTAGRAM, texto_partido, texto_tabla


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


def fotos_instagram(tipo, fotos, rellenar=rellenar_cuadrado):
    """Partido: el marcador tal cual y las dos alineaciones rellenadas a 1:1 (<nombre>_ig.png, junto
    a las originales). Tabla: la foto tal cual."""
    if tipo != "partido":
        return list(fotos)
    marcador, *alineaciones = fotos
    return [marcador] + [rellenar(r, r.with_name(f"{r.stem}_ig{r.suffix}")) for r in alineaciones]


# --- Pendientes ---

def pendientes(temporada, registros, publicados):
    """Lo que falta publicar, en el orden del fixture: ("partido", registro, falta) o
    ("tabla", fecha, falta), con falta = "post", "instagram" o "comentario" (ver publicados.falta).
    La tabla de una fecha está pendiente cuando todos sus partidos ya están completos."""
    por_id = {r["partido_id"]: r for r in registros}
    salida = []
    for f, partidos in enumerate(temporada["fixture"], start=1):
        ids = [partido_id(f, p) for p in range(1, len(partidos) + 1)]
        salida += [("partido", por_id[pid], falta(publicados, pid))
                   for pid in ids if pid in por_id and falta(publicados, pid)]
        if all(falta(publicados, pid) is None for pid in ids) and falta(publicados, clave_tabla(f)):
            salida.append(("tabla", f, falta(publicados, clave_tabla(f))))
    return salida


def clave_de(item):
    tipo, dato = item[:2]
    return dato["partido_id"] if tipo == "partido" else clave_tabla(dato)


def armar_post(item, temporada, registros, carpeta_imagenes, nombres,
               generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla):
    """Devuelve (clave, tipo, mensaje, fotos). La tabla de la fecha F sale solo de las fechas 1..F.
    El texto también es el caption de Instagram: si no entra, falla antes de generar las imágenes."""
    tipo, dato = item
    if tipo == "partido":
        clave = dato["partido_id"]
        mensaje = texto_partido(dato, nombres)
        comprobar_caption(mensaje)
        return clave, tipo, mensaje, generar_partido(dato, carpeta_imagenes / clave)
    clave = clave_tabla(dato)
    mensaje = texto_tabla(dato)
    comprobar_caption(mensaje)
    filas = calcular_tabla([r for r in registros if r["fecha"] <= dato], club_ids=temporada["clubes"],
                           nombres=nombres)
    return clave, tipo, mensaje, [generar_tabla_img(filas, carpeta_imagenes / f"{clave}.png")]


# --- Corrida ---

def correr(temporada_id, pagina=None, base=CARPETA_TEMPORADAS, params=None, cliente=None, instagram=None,
           generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla,
           rellenar=rellenar_cuadrado, mostrar=print, ahora=None):
    """pagina None = dry-run. cliente: un facebook.Cliente ya armado; instagram: un
    instagram.Instagram ya armado (si no, salen del .env)."""
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
            items = [("partido", registro, "post")]
        publicados = cargar_publicados(temporada_id, base)
        for item in items:
            tipo, parte, clave = item[0], item[2], clave_de(item)
            entrada = publicados.get(clave, {})
            bloques = [f"[dry-run] {clave} ({tipo})" + ("" if parte == "post" else f": falta {parte}")]
            if parte != "comentario":
                _, _, mensaje, fotos = armar(item[:2])
                if parte == "post":
                    bloques.append(f"{mensaje}\nimágenes:\n" + "\n".join(f"  {r}" for r in fotos))
                forma = "carrusel" if tipo == "partido" else "foto sola"
                bloques.append(f"instagram ({forma}, caption = texto del post):\n" + "\n".join(
                    f"  {i}. {r}" for i, r in enumerate(fotos_instagram(tipo, fotos, rellenar), start=1)))
            if parte == "post" or ("comentario_id" in entrada and not entrada["comentario_id"]):
                bloques.append(f"comentario:\n{COMENTARIO_INSTAGRAM}")
            mostrar("\n".join(bloques))
        return

    if cliente is None:
        cliente = Cliente.desde_env(pagina)
    elif cliente.pagina != pagina:
        raise ValueError(f"el cliente es de la página {cliente.pagina}, no de {pagina}")
    comprobar_pagina(cargar_publicados(temporada_id, base), cliente.page_id)
    cliente.verificar_pagina()
    if instagram is None:
        instagram = Instagram.desde_env(cliente)
    instagram.verificar_cuenta()
    armados = {}   # imágenes y texto ya armados en esta corrida, por clave

    def publicar_pendientes():
        # de a una parte y recalculando: cada parte que sale vuelve pendiente la siguiente, y publicar
        # el último partido de una fecha vuelve pendiente su tabla
        while items := lista():
            item = items[0]
            parte, clave = item[2], clave_de(item)
            if parte == "post":
                armados[clave] = armar(item[:2])
                _, tipo, mensaje, fotos = armados[clave]
                post_id = cliente.publicar_post(mensaje, fotos)
                marcar(temporada_id, clave, tipo, post_id, cliente.pagina, cliente.page_id, base, ahora)
                mostrar(f"publicado {clave} ({tipo}): post {post_id}")
            elif parte == "comentario":
                post_id = cargar_publicados(temporada_id, base)[clave]["post_id"]
                comentario_id = cliente.comentar(post_id, COMENTARIO_INSTAGRAM)
                marcar_comentario(temporada_id, clave, comentario_id, base)
                mostrar(f"comentado {clave}: comentario {comentario_id}")
            else:
                # los contenedores y las URL caducan: Instagram se hace siempre de cero
                if clave not in armados:
                    armados[clave] = armar(item[:2])
                _, tipo, mensaje, fotos = armados[clave]
                fotos_ig = fotos_instagram(tipo, fotos, rellenar)
                desde = datetime.fromisoformat(cargar_publicados(temporada_id, base)[clave]["fecha_hora"])
                if tipo == "partido":
                    ig_media_id = instagram.publicar_carrusel(fotos_ig, mensaje, desde)
                else:
                    ig_media_id = instagram.publicar_foto(fotos_ig[0], mensaje, desde)
                marcar_instagram(temporada_id, clave, ig_media_id, base)
                mostrar(f"publicado en Instagram {clave}: {ig_media_id}")

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
