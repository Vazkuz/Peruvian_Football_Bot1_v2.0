"""Cierra el circuito: motor → imágenes → texto → Facebook → Instagram (§7.2, §8).

    python -m pfb.publicacion.correr <temporada_id> [--pagina prueba|real]

Sin --pagina es dry-run: no toca la red ni marca nada en publicados.json. Si hay algo pendiente lo
muestra y termina; si no, juega el siguiente partido, lo muestra y termina.
Si el partido tiene votación (§13.1), el dry-run muestra también el post de la votación.
Con --pagina: primero publica lo pendiente (sin volver a simular) y después juega el siguiente y
lo publica. Por partido: guardar registro → publicar en Facebook → marcar con el post → publicar en
Instagram → marcar con la publicación → comentar → marcar con el comentario. Si el partido trae
votación (§13.1), después sale su post de la misma forma, con un comentario en Instagram por opción
antes del comentario de Facebook. Si una parte falla, la siguiente corrida retoma desde esa parte.
La tabla de una fecha sale en su propio turno (§13.1): cuando la fecha cierra (todos sus partidos y
votaciones completos), la corrida siguiente publica solo la tabla y no juega partido. Si una
corrida tuvo que terminar algo pendiente de esa fecha, la tabla queda para la siguiente.
Votos (§13.1): al comienzo de cada corrida con --pagina, antes de publicar nada, se leen los votos
de las votaciones ya publicadas completas y sin resolver, y se aplica el resultado. El anuncio del
resultado va como comentario del post siguiente (partido o tabla), en Facebook antes del comentario
de Instagram, y en Instagram. Si una corrida
tuvo que terminar una votación a medias, no juega partido: la votación queda abierta hasta la
corrida siguiente.
Fecha FIFA (§13.1): si el partido trae una, sale en su propio turno como la tabla (foto sola en Facebook
e Instagram y el comentario de Instagram), en la corrida siguiente a la de su partido y su votación; esa
corrida no juega partido. Si hay una votación abierta, se resuelve antes y su anuncio va en este post.
Una fecha por día (§9.1): si la tabla de una fecha ya salió hoy (fecha de Lima), la corrida termina lo
que haya pendiente pero no juega partido.
"""

import argparse
import sys
from datetime import datetime

from pfb.imagenes.alineacion import RAIZ
from pfb.imagenes.alineacion import generar as generar_alineacion
from pfb.imagenes.fecha_fifa import generar_fecha_fifa
from pfb.imagenes.marcador import generar_marcador
from pfb.imagenes.relleno import rellenar_cuadrado
from pfb.imagenes.tabla import generar_tabla
from pfb.imagenes.votacion import imagen_votacion_2
from pfb.motor.fecha_fifa import cargar_selecciones
from pfb.motor.partido import cargar_parametros
from pfb.motor.salida import alineacion_desde_registro, cargar_colores
from pfb.motor.temporada import (CARPETA_TEMPORADAS, cargar_nombres, cargar_registros, cargar_temporada,
                                 carpeta_temporada, jugar_siguiente, partido_id, resolver_votacion)
from pfb.motor.temporada import tabla as calcular_tabla
from pfb.motor.votaciones import REACCIONES, contar_votos
from pfb.publicacion.facebook import PAGINAS, Cliente, ErrorFacebook
from pfb.publicacion.instagram import Instagram, comprobar_caption
from pfb.publicacion.publicados import (ZONA, MezclaDePaginas, cargar_publicados, clave_fifa, clave_tabla, clave_votacion,
                                        comprobar_pagina, falta, marcar, marcar_anuncio, marcar_comentario,
                                        marcar_ig_comentario, marcar_instagram)
from pfb.publicacion.texto import (COMENTARIO_INSTAGRAM, caption_votacion, opciones_votacion, texto_partido,
                                   texto_anuncio, texto_fecha_fifa, texto_tabla, texto_votacion)


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


def generar_imagen_fifa(fecha_fifa, ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return generar_fecha_fifa(fecha_fifa, nombres_selecciones(), ruta)


def nombres_selecciones():
    return {codigo: s["nombre"] for codigo, s in cargar_selecciones().items()}


def fotos_instagram(tipo, fotos, rellenar=rellenar_cuadrado):
    """Partido: el marcador tal cual y las dos alineaciones rellenadas a 1:1 (<nombre>_ig.png, junto
    a las originales). Tabla: la foto tal cual."""
    if tipo != "partido":
        return list(fotos)
    marcador, *alineaciones = fotos
    return [marcador] + [rellenar(r, r.with_name(f"{r.stem}_ig{r.suffix}")) for r in alineaciones]


IMAGEN_SANCION = RAIZ / "assets" / "Rojas.png"


def imagen_votacion(votacion):
    """Imagen fija del post de la votación: Rojas.png (sanción) o la de la cosa random (mesa)."""
    return IMAGEN_SANCION if votacion["tipo"] == "sancion" else imagen_votacion_2(votacion["opcion"])


def armar_votacion(registro, nombres):
    """Devuelve (mensaje de Facebook, caption de Instagram, comentarios de Instagram, foto). El
    caption se comprueba antes de devolver."""
    caption = caption_votacion(registro, nombres)
    comprobar_caption(caption)
    return (texto_votacion(registro, nombres), caption, opciones_votacion(registro, nombres),
            imagen_votacion(registro["votacion"]))


def mostrar_votacion(registro, nombres, parte="post"):
    """Bloque del dry-run con el post de la votación del partido, desde la parte que falta."""
    mensaje, caption, comentarios, foto = armar_votacion(registro, nombres)
    tipo = "sanción" if registro["votacion"]["tipo"] == "sancion" else "mesa"
    partes = ["post", "instagram", "comentarios_ig", "comentario"]
    bloques = [
        f"{mensaje}\nimagen:\n  {foto}",
        f"instagram (foto sola):\n  1. {foto}\ncaption:\n{caption}",
        "comentarios en instagram:\n" + "\n".join(f"  {c}" for c in comentarios),
        f"comentario:\n{COMENTARIO_INSTAGRAM}",
    ][partes.index(parte):]
    encabezado = f"[dry-run] {clave_votacion(registro['partido_id'])} (votación de {tipo})"
    return "\n".join([encabezado + ("" if parte == "post" else f": falta {parte}")] + bloques)


# --- Pendientes ---

def pendientes(temporada, registros, publicados):
    """Lo que falta publicar, en el orden del fixture: ("partido", registro, falta),
    ("votacion", registro, falta), ("fifa", registro, falta) o ("tabla", fecha, falta), con falta =
    "post", "instagram", "comentarios_ig", "anuncio" o "comentario" (ver publicados.falta). La votación de
    un partido está pendiente cuando el partido ya está completo; su Fecha FIFA, cuando también lo está
    la votación; la tabla de una fecha, cuando todos sus partidos, votaciones y Fechas FIFA lo están."""
    por_id = {r["partido_id"]: r for r in registros}
    salida = []
    for f, partidos in enumerate(temporada["fixture"], start=1):
        ids = [partido_id(f, p) for p in range(1, len(partidos) + 1)]
        completa = True
        for pid in ids:
            if pid not in por_id:
                completa = False
                continue
            registro = por_id[pid]
            if falta(publicados, pid):
                salida.append(("partido", registro, falta(publicados, pid)))
                completa = False
            elif registro.get("votacion") and falta(publicados, clave_votacion(pid)):
                salida.append(("votacion", registro, falta(publicados, clave_votacion(pid))))
                completa = False
            elif registro.get("fecha_fifa") and falta(publicados, clave_fifa(pid)):
                salida.append(("fifa", registro, falta(publicados, clave_fifa(pid))))
                completa = False
        if completa and falta(publicados, clave_tabla(f)):
            salida.append(("tabla", f, falta(publicados, clave_tabla(f))))
    return salida


def votaciones_abiertas(registros, publicados):
    """Los registros cuya votación ya está publicada completa y todavía no tiene votos (§13.1), en
    orden cronológico."""
    return [r for r in registros
            if r.get("votacion") and "votos" not in r["votacion"]
            and clave_votacion(r["partido_id"]) in publicados
            and falta(publicados, clave_votacion(r["partido_id"])) is None]


def anuncios_pendientes(registros, publicados):
    """Claves de las votaciones ya resueltas cuyo anuncio todavía no tiene post asignado, en orden."""
    return [clave_votacion(r["partido_id"]) for r in registros
            if r.get("votacion") and "votos" in r["votacion"]
            and "anuncio_en" not in publicados.get(clave_votacion(r["partido_id"]), {"anuncio_en": None})]


def registro_de_votacion(registros, clave):
    partido = clave.removeprefix("votacion-")
    return next(r for r in registros if r["partido_id"] == partido)


def leer_votos(registro, entrada, cliente, instagram):
    """Votos de cada opción: reacciones del post de Facebook + likes del comentario de Instagram de
    esa opción. entrada: la de la votación en publicados.json; si no tiene "ig_comentarios" (entrada de
    antes de esa parte), Instagram no suma votos."""
    reacciones = cliente.reacciones(entrada["post_id"])
    if "ig_comentarios" in entrada:
        likes = [instagram.likes_comentario(c) for c in entrada["ig_comentarios"]]
    else:
        likes = [0] * len(REACCIONES[registro["votacion"]["tipo"]])
    return contar_votos(registro["votacion"]["tipo"], reacciones, likes)


def tabla_de_hoy(publicados, ahora=None):
    """La clave de una tabla publicada hoy (fecha de Lima), o None."""
    hoy = (ahora or datetime.now(ZONA)).astimezone(ZONA).date()
    for clave, entrada in publicados.items():
        if entrada.get("tipo") != "tabla":
            continue
        if datetime.fromisoformat(entrada["fecha_hora"]).astimezone(ZONA).date() == hoy:
            return clave
    return None


TURNO_PROPIO = ("tabla", "fifa")   # salen solas en su corrida (§13.1)


def tipos_de(clave):
    return "fifa" if clave.startswith("fifa-") else "tabla"


def clave_de(item):
    tipo, dato = item[:2]
    if tipo == "partido":
        return dato["partido_id"]
    if tipo == "votacion":
        return clave_votacion(dato["partido_id"])
    if tipo == "fifa":
        return clave_fifa(dato["partido_id"])
    return clave_tabla(dato)


def armar_post(item, temporada, registros, carpeta_imagenes, nombres,
               generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla,
               generar_fifa=generar_imagen_fifa):
    """Devuelve (clave, tipo, mensaje, fotos). La tabla de la fecha F sale solo de las fechas 1..F.
    El texto también es el caption de Instagram (salvo en la votación, ver armar_votacion): si no
    entra, falla antes de generar las imágenes."""
    tipo, dato = item
    if tipo == "votacion":
        mensaje, _, _, foto = armar_votacion(dato, nombres)
        return clave_votacion(dato["partido_id"]), tipo, mensaje, [foto]
    if tipo == "partido":
        clave = dato["partido_id"]
        mensaje = texto_partido(dato, nombres)
        comprobar_caption(mensaje)
        return clave, tipo, mensaje, generar_partido(dato, carpeta_imagenes / clave)
    if tipo == "fifa":
        clave = clave_fifa(dato["partido_id"])
        mensaje = texto_fecha_fifa(dato["fecha_fifa"], nombres_selecciones())
        comprobar_caption(mensaje)
        return clave, tipo, mensaje, [generar_fifa(dato["fecha_fifa"], carpeta_imagenes / f"{clave}.png")]
    clave = clave_tabla(dato)
    mensaje = texto_tabla(dato)
    comprobar_caption(mensaje)
    filas = calcular_tabla([r for r in registros if r["fecha"] <= dato], club_ids=temporada["clubes"],
                           nombres=nombres)
    return clave, tipo, mensaje, [generar_tabla_img(filas, carpeta_imagenes / f"{clave}.png")]


# --- Corrida ---

def correr(temporada_id, pagina=None, base=CARPETA_TEMPORADAS, params=None, cliente=None, instagram=None,
           generar_partido=generar_imagenes_partido, generar_tabla_img=generar_imagen_tabla,
           generar_fifa=generar_imagen_fifa, rellenar=rellenar_cuadrado, mostrar=print, ahora=None):
    """pagina None = dry-run. cliente: un facebook.Cliente ya armado; instagram: un
    instagram.Instagram ya armado (si no, salen del .env)."""
    temporada = cargar_temporada(temporada_id, base)
    nombres = cargar_nombres()
    carpeta_imagenes = carpeta_temporada(temporada_id, base) / "imagenes"
    params = params or cargar_parametros()

    def armar(item):
        return armar_post(item, temporada, cargar_registros(temporada_id, base), carpeta_imagenes, nombres,
                          generar_partido, generar_tabla_img, generar_fifa)

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

        def mostrar_item(item):
            tipo, parte, clave = item[0], item[2], clave_de(item)
            if tipo == "votacion":
                mostrar(mostrar_votacion(item[1], nombres, parte))
                return
            entrada = publicados.get(clave, {})
            bloques = [f"[dry-run] {clave} ({tipo})" + ("" if parte == "post" else f": falta {parte}")]
            if parte == "anuncio":
                registro_v = registro_de_votacion(cargar_registros(temporada_id, base), entrada["anuncio"]["de"])
                bloques.append(f"anuncio (facebook e instagram):\n{texto_anuncio(registro_v, nombres)}")
            elif parte != "comentario":
                _, _, mensaje, fotos = armar(item[:2])
                if parte == "post":
                    bloques.append(f"{mensaje}\nimágenes:\n" + "\n".join(f"  {r}" for r in fotos))
                forma = "carrusel" if tipo == "partido" else "foto sola"
                bloques.append(f"instagram ({forma}, caption = texto del post):\n" + "\n".join(
                    f"  {i}. {r}" for i, r in enumerate(fotos_instagram(tipo, fotos, rellenar), start=1)))
            if parte in ("post", "anuncio") or ("comentario_id" in entrada and not entrada["comentario_id"]):
                bloques.append(f"comentario:\n{COMENTARIO_INSTAGRAM}")
            mostrar("\n".join(bloques))
            if tipo == "partido" and parte == "post" and item[1].get("votacion"):
                mostrar(mostrar_votacion(item[1], nombres))
            if tipo == "partido" and parte == "post" and item[1].get("fecha_fifa"):
                mostrar_item(("fifa", item[1], "post"))

        for item in items:
            mostrar_item(item)
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
    votacion_publicada = []   # claves de votaciones que salieron (o se completaron) en publicar_pendientes

    for registro in votaciones_abiertas(cargar_registros(temporada_id, base), cargar_publicados(temporada_id, base)):
        clave = clave_votacion(registro["partido_id"])
        votos = leer_votos(registro, cargar_publicados(temporada_id, base)[clave], cliente, instagram)
        nuevo = resolver_votacion(temporada_id, registro["partido_id"], votos, params, base)
        mostrar(f"resuelta {clave}: votos {votos}\n{texto_anuncio(nuevo, nombres)}")

    def publicar_pendientes():
        """Publica lo pendiente. La tabla y la Fecha FIFA salen en su propio turno: solo si son lo primero
        que hay que publicar; si antes salió otra cosa, se detiene al llegar a una de ellas. Devuelve
        ("salio", tipo) si publicó una, ("espera", tipo) si se detuvo antes de una, o None."""
        propio = None
        hubo_otra = False
        # de a una parte y recalculando: cada parte que sale vuelve pendiente la siguiente, y publicar
        # el último partido (o la última votación) de una fecha vuelve pendiente su tabla
        while items := lista():
            item = items[0]
            tipo, parte, clave = item[0], item[2], clave_de(item)
            if tipo in TURNO_PROPIO:
                if hubo_otra or (propio and propio != clave):
                    return ("espera", tipo)
                propio = clave
            else:
                hubo_otra = True
            if tipo == "votacion" and clave not in votacion_publicada:
                votacion_publicada.append(clave)
            if parte == "post":
                armados[clave] = armar(item[:2])
                _, tipo, mensaje, fotos = armados[clave]
                post_id = cliente.publicar_post(mensaje, fotos)
                n_ig = len(opciones_votacion(item[1], nombres)) if tipo == "votacion" else 0
                anuncio_de = None
                if tipo != "votacion":
                    por_anunciar = anuncios_pendientes(cargar_registros(temporada_id, base),
                                                       cargar_publicados(temporada_id, base))
                    anuncio_de = por_anunciar[0] if por_anunciar else None
                marcar(temporada_id, clave, tipo, post_id, cliente.pagina, cliente.page_id, base, ahora,
                       ig_comentarios=n_ig, anuncio_de=anuncio_de)
                mostrar(f"publicado {clave} ({tipo}): post {post_id}")
            elif parte == "comentarios_ig":
                entrada = cargar_publicados(temporada_id, base)[clave]
                opciones = opciones_votacion(item[1], nombres)
                for n, comentario_id in enumerate(entrada["ig_comentarios"]):
                    if comentario_id is None:
                        comentario_id = instagram.comentar(entrada["ig_media_id"], opciones[n])
                        marcar_ig_comentario(temporada_id, clave, n, comentario_id, base)
                        mostrar(f"comentado en Instagram {clave}: {opciones[n]} ({comentario_id})")
            elif parte == "anuncio":
                entrada = cargar_publicados(temporada_id, base)[clave]
                anuncio = entrada["anuncio"]
                texto = texto_anuncio(registro_de_votacion(cargar_registros(temporada_id, base), anuncio["de"]),
                                      nombres)
                if anuncio["fb_id"] is None:
                    comentario_id = cliente.comentar(entrada["post_id"], texto)
                    marcar_anuncio(temporada_id, clave, "fb_id", comentario_id, base)
                    mostrar(f"anuncio de {anuncio['de']} en {clave}: comentario {comentario_id}")
                if anuncio["ig_id"] is None:
                    comentario_id = instagram.comentar(entrada["ig_media_id"], texto)
                    marcar_anuncio(temporada_id, clave, "ig_id", comentario_id, base)
                    mostrar(f"anuncio de {anuncio['de']} en Instagram {clave}: {comentario_id}")
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
                caption = caption_votacion(item[1], nombres) if tipo == "votacion" else mensaje
                desde = datetime.fromisoformat(cargar_publicados(temporada_id, base)[clave]["fecha_hora"])
                if tipo == "partido":
                    ig_media_id = instagram.publicar_carrusel(fotos_ig, caption, desde)
                else:
                    ig_media_id = instagram.publicar_foto(fotos_ig[0], caption, desde)
                marcar_instagram(temporada_id, clave, ig_media_id, base)
                mostrar(f"publicado en Instagram {clave}: {ig_media_id}")
        return ("salio", tipos_de(propio)) if propio else None

    resultado = publicar_pendientes()
    if resultado:
        accion, tipo = resultado
        nombre = "la tabla" if tipo == "tabla" else "la Fecha FIFA"
        if accion == "salio":
            mostrar(f"salió {nombre} en su propio turno: esta corrida no juega partido")
        else:
            mostrar(f"{nombre} sale en la corrida siguiente: esta corrida no juega partido")
        return
    if votacion_publicada:
        mostrar(f"{votacion_publicada[-1]} queda abierta hasta la corrida siguiente: esta corrida no juega partido")
        return
    if tabla := tabla_de_hoy(cargar_publicados(temporada_id, base), ahora):
        mostrar(f"{tabla} ya salió hoy: una fecha por día, esta corrida no juega partido")
        return
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
