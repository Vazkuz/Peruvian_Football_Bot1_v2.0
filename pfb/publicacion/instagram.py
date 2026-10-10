"""Publicación en Instagram con la Graph API (Instagram con Facebook Login). Solo urllib.

Usa siempre FB_PAGE_TOKEN e IG_USER_ID del .env (la cuenta de Instagram está vinculada a la página
real), también con --pagina prueba. Las imágenes van como image_url: se suben sin publicar a la
página del modo (el `subidor`, un facebook.Cliente) y se pasa la URL de su versión más grande.
"""

import urllib.parse
from datetime import datetime, timedelta

from pfb.publicacion.facebook import RUTA_ENV, VERSION_POR_DEFECTO, ErrorFacebook, Graph, leer_env

USUARIO_ESPERADO = "pfbot.1"
MAX_CAPTION = 2200
ESPERA_ESTADO = 5       # segundos entre consultas del estado de un contenedor
DURACION_ESTADO = 120   # segundos de espera por contenedor
MARGEN_DUPLICADO = timedelta(minutes=5)


class ErrorInstagram(ErrorFacebook):
    """Un contenedor terminó en ERROR o EXPIRED, no terminó a tiempo, o el caption no sirve."""


class CuentaEquivocada(ErrorInstagram):
    """IG_USER_ID no es la cuenta esperada."""


def comprobar_caption(caption):
    """Falla si el texto no entra como caption de Instagram. Sin red."""
    if len(caption) > MAX_CAPTION:
        raise ErrorInstagram(f"el texto tiene {len(caption)} caracteres (máximo {MAX_CAPTION} en Instagram)")


def _fecha_ig(texto):
    """El timestamp de la Graph API, p. ej. 2026-10-10T23:08:23+0000."""
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%S%z")


class Instagram(Graph):
    def __init__(self, ig_user_id, token, subidor, version=VERSION_POR_DEFECTO,
                 espera_estado=ESPERA_ESTADO, duracion_estado=DURACION_ESTADO, **kwargs):
        if not ig_user_id or not token:
            raise ErrorFacebook("faltan IG_USER_ID o FB_PAGE_TOKEN en el .env")
        super().__init__(token, version, **kwargs)
        self.ig_user_id = ig_user_id
        self._subidor = subidor
        self._espera_estado = espera_estado
        self._consultas_estado = 1 + duracion_estado // espera_estado

    @classmethod
    def desde_env(cls, subidor, ruta_env=RUTA_ENV, **kwargs):
        env = leer_env({"IG_USER_ID", "FB_PAGE_TOKEN", "FB_API_VERSION"}, ruta_env)
        return cls(env.get("IG_USER_ID", ""), env.get("FB_PAGE_TOKEN", ""), subidor,
                   env.get("FB_API_VERSION") or VERSION_POR_DEFECTO, **kwargs)

    def verificar_cuenta(self):
        """GET /{IG_USER_ID}: el username tiene que ser el esperado. Si no, aborta sin reintentar."""
        ruta = f"{self.ig_user_id}?" + urllib.parse.urlencode({"fields": "username"})
        cuenta = self._llamar("verificación de la cuenta de Instagram", "GET", ruta, clave="username")
        if cuenta["username"] != USUARIO_ESPERADO:
            raise CuentaEquivocada(f"IG_USER_ID no es la cuenta {USUARIO_ESPERADO!r}")
        return cuenta

    def _crear_contenedor(self, paso, datos):
        cuerpo = urllib.parse.urlencode(datos).encode("utf-8")
        return self._llamar(paso, "POST", f"{self.ig_user_id}/media", cuerpo,
                            "application/x-www-form-urlencoded")["id"]

    def esperar(self, container_id):
        """Consulta status_code cada `espera_estado` segundos hasta FINISHED. ERROR, EXPIRED o que no
        termine a tiempo: ErrorInstagram (con el detalle de status), sin reintentos."""
        ruta = f"{container_id}?" + urllib.parse.urlencode({"fields": "status_code,status"})
        for consulta in range(1, self._consultas_estado + 1):
            respuesta = self._llamar(f"estado del contenedor {container_id}", "GET", ruta, clave="status_code")
            estado = respuesta["status_code"]
            if estado == "FINISHED":
                return
            if estado in ("ERROR", "EXPIRED"):
                raise ErrorInstagram(f"el contenedor {container_id} quedó en {estado}: {respuesta.get('status')}")
            if consulta < self._consultas_estado:
                self._dormir(self._espera_estado)
        raise ErrorInstagram(f"el contenedor {container_id} no terminó a tiempo (último estado: {estado})")

    def buscar_media(self, caption, desde):
        """El id de una publicación reciente de la cuenta con el mismo caption (sin espacios al inicio
        ni al final) y con timestamp desde `desde` menos el margen, o None. Una publicación igual más
        vieja (otra temporada con el mismo texto) no cuenta."""
        ruta = f"{self.ig_user_id}/media?" + urllib.parse.urlencode({"fields": "id,caption,timestamp", "limit": 10})
        for media in self._llamar("búsqueda de publicaciones de Instagram", "GET", ruta, clave="data")["data"]:
            if (media.get("caption", "").strip() == caption.strip() and media.get("timestamp")
                    and _fecha_ig(media["timestamp"]) >= desde - MARGEN_DUPLICADO):
                return media["id"]
        return None

    def _publicar(self, container_id, caption, desde):
        """media_publish. Antes de cada intento busca el mismo caption entre las publicaciones
        recientes (desde `desde`): si ya está, devuelve ese id sin volver a publicar."""
        cuerpo = urllib.parse.urlencode({"creation_id": container_id}).encode("utf-8")

        def publicar():
            existente = self.buscar_media(caption, desde)
            if existente:
                self._avisar(f"ya estaba en Instagram, se marca sin volver a publicar: {existente}")
                return existente
            return self._una_llamada("POST", f"{self.ig_user_id}/media_publish", cuerpo,
                                     "application/x-www-form-urlencoded")["id"]

        return self._reintentar("publicación en Instagram", publicar)

    def publicar_carrusel(self, rutas_fotos, caption, desde):
        """Carrusel con las fotos en ese orden. Devuelve el id de la publicación.
        desde: fecha_hora de la entrada en publicados.json (para el anti-duplicado)."""
        comprobar_caption(caption)
        urls = [self._subidor.subir_para_url(ruta) for ruta in rutas_fotos]
        hijos = [self._crear_contenedor(f"contenedor de la foto {i}", {"image_url": url, "is_carousel_item": "true"})
                 for i, url in enumerate(urls, start=1)]
        for hijo in hijos:
            self.esperar(hijo)
        padre = self._crear_contenedor("contenedor del carrusel",
                                       {"media_type": "CAROUSEL", "children": ",".join(hijos), "caption": caption})
        self.esperar(padre)
        return self._publicar(padre, caption, desde)

    def publicar_foto(self, ruta_foto, caption, desde):
        """Una foto sola. Devuelve el id de la publicación.
        desde: fecha_hora de la entrada en publicados.json (para el anti-duplicado)."""
        comprobar_caption(caption)
        url = self._subidor.subir_para_url(ruta_foto)
        contenedor = self._crear_contenedor("contenedor de la foto", {"image_url": url, "caption": caption})
        self.esperar(contenedor)
        return self._publicar(contenedor, caption, desde)
