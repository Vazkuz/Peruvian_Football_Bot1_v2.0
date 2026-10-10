"""Cliente de la Graph API para publicar en la página (§7, §7.2). Solo urllib.

Las credenciales se leen del .env del repo: FB_PAGE_ID / FB_PAGE_TOKEN (página real) o
FB_TEST_PAGE_ID / FB_TEST_PAGE_TOKEN (página de prueba), y FB_API_VERSION.
Ni el token ni el .env salen en los mensajes de error.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from pfb.motor.plantillas import RAIZ

RUTA_ENV = RAIZ / ".env"
VERSION_POR_DEFECTO = "v26.0"
PAGINAS = {
    "prueba": {"id": "FB_TEST_PAGE_ID", "token": "FB_TEST_PAGE_TOKEN", "nombre": "Gokú - Kakaroto"},
    "real": {"id": "FB_PAGE_ID", "token": "FB_PAGE_TOKEN", "nombre": "Peruvian Football BOT 1"},
}
ESPERA = 60       # segundos entre intentos
DURACION = 600    # segundos de reintentos por llamada


class ErrorFacebook(Exception):
    """La llamada siguió fallando después de los reintentos, o la configuración no sirve."""


class PaginaEquivocada(ErrorFacebook):
    """El token no es de la página esperada."""


class ReintentosAgotados(ErrorFacebook):
    """Una llamada siguió fallando durante todo el tiempo de reintentos."""


def leer_env(claves, ruta=RUTA_ENV):
    """Solo las claves pedidas del .env (sin python-dotenv)."""
    env = {}
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        if clave in claves:
            env[clave] = valor.strip().strip('"').strip("'")
    return env


def transporte_urllib(metodo, url, cuerpo, headers):
    """Hace la llamada y devuelve el JSON de la respuesta. Lanza excepción si falla."""
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ErrorFacebook(f"HTTP {e.code} {e.read().decode('utf-8', errors='replace')}") from None


def _multipart(campos, archivo):
    """campos: {nombre: valor}; archivo: (nombre del campo, Path) de un PNG."""
    limite = uuid.uuid4().hex
    partes = [f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
              for k, v in campos.items()]
    nombre, ruta = archivo
    partes.append((f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"; filename="{ruta.name}"\r\n'
                   f"Content-Type: image/png\r\n\r\n").encode() + ruta.read_bytes() + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


class Graph:
    """Llamadas a la Graph API con un token, con reintentos. Base de Cliente e Instagram."""

    def __init__(self, token, version=VERSION_POR_DEFECTO, transporte=transporte_urllib, dormir=time.sleep,
                 espera=ESPERA, duracion=DURACION, avisar=None):
        self._token = token
        self.api = f"https://graph.facebook.com/{version or VERSION_POR_DEFECTO}"
        self._transporte = transporte
        self._dormir = dormir
        self._espera = espera
        self._intentos = 1 + duracion // espera
        self._avisar = avisar or (lambda m: print(m, file=sys.stderr))

    def _reintentar(self, paso, funcion):
        """Llama a funcion() cada `espera` segundos hasta que salga bien o se agoten los intentos.
        Si adentro se agotaron los reintentos de otra llamada, no se reintenta encima."""
        for intento in range(1, self._intentos + 1):
            try:
                return funcion()
            except ReintentosAgotados:
                raise
            except Exception as e:
                detalle = f"{paso}: {type(e).__name__}: {e}"
                if intento == self._intentos:
                    raise ReintentosAgotados(f"{detalle} (sin éxito tras {self._intentos} intentos)") from None
                self._avisar(f"falló {detalle}; reintento {intento + 1}/{self._intentos} en {self._espera} s")
                self._dormir(self._espera)

    def _una_llamada(self, metodo, ruta, cuerpo=None, content_type=None, clave="id"):
        """Un solo intento. La respuesta tiene que traer `clave`; si no, cuenta como falla."""
        headers = {"Authorization": f"Bearer {self._token}"}
        if content_type:
            headers["Content-Type"] = content_type
        respuesta = self._transporte(metodo, f"{self.api}/{ruta}", cuerpo, headers)
        if clave not in respuesta:
            raise ErrorFacebook(f"respuesta sin {clave}: {respuesta}")
        return respuesta

    def _llamar(self, paso, metodo, ruta, cuerpo=None, content_type=None, clave="id"):
        """Una llamada con reintentos."""
        return self._reintentar(paso, lambda: self._una_llamada(metodo, ruta, cuerpo, content_type, clave))


class Cliente(Graph):
    def __init__(self, pagina, page_id, token, version=VERSION_POR_DEFECTO, **kwargs):
        if pagina not in PAGINAS:
            raise ValueError(f"página desconocida: {pagina}")
        if not page_id or not token:
            raise ErrorFacebook(f"faltan {PAGINAS[pagina]['id']} o {PAGINAS[pagina]['token']} en el .env")
        super().__init__(token, version, **kwargs)
        self.pagina = pagina
        self.page_id = page_id

    @classmethod
    def desde_env(cls, pagina, ruta_env=RUTA_ENV, **kwargs):
        if pagina not in PAGINAS:
            raise ValueError(f"página desconocida: {pagina}")
        claves = PAGINAS[pagina]
        env = leer_env({claves["id"], claves["token"], "FB_API_VERSION"}, ruta_env)
        return cls(pagina, env.get(claves["id"], ""), env.get(claves["token"], ""),
                   env.get("FB_API_VERSION") or VERSION_POR_DEFECTO, **kwargs)

    def _subir_foto(self, ruta):
        """Sube la foto a la página sin publicar. Devuelve su id."""
        ruta = Path(ruta)
        cuerpo, tipo = _multipart({"published": "false"}, ("source", ruta))
        return self._llamar(f"subida de {ruta.name}", "POST", f"{self.page_id}/photos", cuerpo, tipo)["id"]

    def subir_para_url(self, ruta):
        """Sube la foto a la página sin publicar y devuelve la URL de su versión más grande (para
        pasarla a Instagram como image_url)."""
        foto_id = self._subir_foto(ruta)
        ruta_images = f"{foto_id}?" + urllib.parse.urlencode({"fields": "images"})
        imagenes = self._llamar(f"URL de {Path(ruta).name}", "GET", ruta_images, clave="images")["images"]
        if not imagenes:
            raise ErrorFacebook(f"la foto {foto_id} no tiene versiones en images")
        return max(imagenes, key=lambda i: i.get("width", 0) * i.get("height", 0))["source"]

    def buscar_post(self, mensaje):
        """El id de un post reciente de la página con el mismo mensaje (sin espacios al inicio ni al
        final), o None."""
        ruta = f"{self.page_id}/posts?" + urllib.parse.urlencode({"fields": "id,message", "limit": 10})
        for post in self._llamar("búsqueda de posts", "GET", ruta, clave="data")["data"]:
            if post.get("message", "").strip() == mensaje.strip():
                return post["id"]
        return None

    def verificar_pagina(self):
        """GET /me: el token tiene que ser de la página esperada (nombre e id). Si no, aborta."""
        yo = self._llamar("verificación de la página", "GET", "me?" + urllib.parse.urlencode({"fields": "id,name"}))
        esperado = PAGINAS[self.pagina]["nombre"]
        if yo.get("name") != esperado or yo.get("id") != self.page_id:
            raise PaginaEquivocada(f"el token no es de la página {esperado!r} (página {self.pagina})")
        return yo

    def publicar_post(self, mensaje, rutas_fotos):
        """Sube cada foto sin publicar y después crea el post con las fotos en el mismo orden.
        Devuelve el id del post.
        Antes de cada intento de /feed busca el mismo mensaje entre los posts recientes: si ya está
        (respuesta perdida, o una corrida que se cayó antes de marcar), devuelve ese id sin volver
        a publicar. Las fotos subidas en esta corrida quedan sueltas."""
        ids = [self._subir_foto(ruta) for ruta in rutas_fotos]
        datos = {"message": mensaje}
        for i, fid in enumerate(ids):
            datos[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
        cuerpo = urllib.parse.urlencode(datos).encode("utf-8")

        def crear():
            existente = self.buscar_post(mensaje)
            if existente:
                self._avisar(f"ya estaba publicado, se marca sin volver a publicar: {existente}")
                return existente
            return self._una_llamada("POST", f"{self.page_id}/feed", cuerpo, "application/x-www-form-urlencoded")["id"]

        return self._reintentar("creación del post", crear)

    def comentar(self, post_id, mensaje):
        """Comenta en el post como la página. Devuelve el id del comentario.
        Sin anti-duplicado: leer los comentarios pide el permiso pages_read_user_content, que la app
        no tiene. Si se pierde la respuesta, el reintento puede comentar dos veces."""
        cuerpo = urllib.parse.urlencode({"message": mensaje}).encode("utf-8")
        return self._llamar("comentario", "POST", f"{post_id}/comments", cuerpo,
                            "application/x-www-form-urlencoded")["id"]
