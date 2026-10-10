import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

import pfb.publicacion.correr as correr_mod
from pfb.motor.partido import cargar_parametros
from pfb.motor.temporada import (_escribir_json, cargar_nombres, cargar_registros, cargar_temporada,
                                 jugar_siguiente, nueva_temporada)
from pfb.publicacion.correr import armar_post, correr, main, pendientes
from pfb.publicacion.facebook import Cliente, ErrorFacebook, PaginaEquivocada, leer_env
from pfb.publicacion.instagram import CuentaEquivocada, ErrorInstagram, Instagram, comprobar_caption
from pfb.publicacion.publicados import (ZONA, MezclaDePaginas, cargar_publicados, marcar, marcar_comentario,
                                        marcar_instagram, ruta_publicados)
from pfb.publicacion.texto import COMENTARIO_INSTAGRAM, texto_partido, texto_tabla

PAGE_ID = "111"
IG_ID = "17841"
AHORA = datetime(2026, 10, 10, 18, 0, tzinfo=ZONA)   # 23:00 UTC


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


class HttpFalso:
    """Responde como la Graph API y anota cada llamada. fallar(n_llamada, metodo, url) -> bool.
    perder(n_feed) -> bool: ese /feed se publica pero la respuesta no llega.
    comentarios: {post_id: [comentario, ...]} ya existentes.
    Instagram: estado(container_id, n_consulta) -> status_code (FINISHED si no se da);
    ig_media: publicaciones ya existentes en la cuenta, las más nuevas al final; ig_usuario: el
    username de IG_USER_ID."""

    def __init__(self, nombre="Gokú - Kakaroto", page_id=PAGE_ID, fallar=None, perder=None, posts=None,
                 comentarios=None, estado=None, ig_media=None, ig_usuario="pfbot.1"):
        self.ig_usuario = ig_usuario
        self.nombre, self.page_id, self.fallar, self.perder = nombre, page_id, fallar, perder
        self.llamadas = []
        self.posts = list(posts or [])          # los más nuevos al final
        self.comentarios = {k: list(v) for k, v in (comentarios or {}).items()}
        self.n_fotos = self.n_feeds = self.n_comentarios = 0
        self.estado = estado or (lambda cid, n: "FINISHED")
        self.ig_media = list(ig_media or [])
        self.contenedores = {}                  # container_id -> datos del POST /media
        self.consultas = {}                     # container_id -> n de consultas de estado

    def __call__(self, metodo, url, cuerpo, headers):
        self.llamadas.append((metodo, url, cuerpo, headers))
        if self.fallar and self.fallar(len(self.llamadas), metodo, url):
            raise OSError("red caída")
        ruta = url.split("?")[0]
        if ruta.endswith("/me"):
            return {"id": self.page_id, "name": self.nombre}
        if ruta.endswith(f"/{self.page_id}/posts"):
            assert urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["id,message"], "limit": ["10"]}
            return {"data": self.posts[::-1][:10]}
        if ruta.endswith("/photos"):
            self.n_fotos += 1
            return {"id": f"foto{self.n_fotos}"}
        if ruta.endswith("/feed"):
            self.n_feeds += 1
            post = {"id": f"{self.page_id}_post{self.n_feeds}",
                    "message": urllib.parse.parse_qs(cuerpo.decode())["message"][0]}
            self.posts.append(post)
            if self.perder and self.perder(self.n_feeds):
                raise TimeoutError("se perdió la respuesta")
            return {"id": post["id"]}
        if ruta.endswith("/comments"):
            post_id = ruta.rsplit("/", 2)[-2]
            if metodo == "GET":
                assert urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["id,message,from"], "limit": ["25"]}
                return {"data": self.comentarios.get(post_id, [])[:25]}
            self.n_comentarios += 1
            comentario = {"id": f"{post_id}_com{self.n_comentarios}", "from": {"id": self.page_id},
                          "message": urllib.parse.parse_qs(cuerpo.decode())["message"][0]}
            self.comentarios.setdefault(post_id, []).append(comentario)
            return {"id": comentario["id"]}
        ultimo = ruta.rsplit("/", 1)[-1]
        if metodo == "GET" and ultimo.startswith("foto"):
            assert urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["images"]}
            return {"images": [{"source": f"https://scontent.falso/{ultimo}_chica.jpg", "width": 130, "height": 130},
                               {"source": f"https://scontent.falso/{ultimo}.jpg", "width": 1080, "height": 1080},
                               {"source": f"https://scontent.falso/{ultimo}_media.jpg", "width": 720, "height": 720}]}
        if ruta.endswith(f"/{IG_ID}"):
            assert metodo == "GET" and urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["username"]}
            return {"id": IG_ID, "username": self.ig_usuario}
        if ruta.endswith(f"/{IG_ID}/media_publish"):
            creation_id = urllib.parse.parse_qs(cuerpo.decode())["creation_id"][0]
            media = {"id": f"ig{len(self.ig_media) + 1}", "caption": self.contenedores[creation_id].get("caption", ""),
                     "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")}
            self.ig_media.append(media)
            return {"id": media["id"]}
        if ruta.endswith(f"/{IG_ID}/media"):
            if metodo == "GET":
                assert urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["id,caption,timestamp"], "limit": ["10"]}
                return {"data": self.ig_media[::-1][:10]}
            cid = f"cont{len(self.contenedores) + 1}"
            self.contenedores[cid] = {k: v[0] for k, v in urllib.parse.parse_qs(cuerpo.decode()).items()}
            return {"id": cid}
        if metodo == "GET" and ultimo.startswith("cont"):
            assert urllib.parse.parse_qs(url.split("?")[1]) == {"fields": ["status_code,status"]}
            self.consultas[ultimo] = self.consultas.get(ultimo, 0) + 1
            codigo = self.estado(ultimo, self.consultas[ultimo])
            return {"id": ultimo, "status_code": codigo, "status": f"{codigo}: detalle de {ultimo}"}
        raise AssertionError(f"llamada inesperada: {metodo} {url}")

    def rutas(self):
        return [u.split("?")[0].rsplit("/", 1)[-1] for m, u, c, h in self.llamadas]

    def feeds(self):
        return [urllib.parse.parse_qs(c.decode()) for m, u, c, h in self.llamadas if u.endswith("/feed")]

    def comentados(self):
        return [(u.rsplit("/", 2)[-2], urllib.parse.parse_qs(c.decode())["message"][0])
                for m, u, c, h in self.llamadas if m == "POST" and u.endswith("/comments")]

    def subidas(self):
        """Nombre de archivo de cada POST /photos, en orden."""
        return [c.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
                for m, u, c, h in self.llamadas if u.endswith("/photos")]


def cliente(http, pagina="prueba", page_id=PAGE_ID, dormidas=None):
    dormidas = [] if dormidas is None else dormidas
    return Cliente(pagina, page_id, "token-falso", transporte=http, dormir=dormidas.append, avisar=lambda m: None)


def instagram(http, subidor, dormidas=None):
    dormidas = [] if dormidas is None else dormidas
    return Instagram(IG_ID, "token-ig", subidor, transporte=http, dormir=dormidas.append, avisar=lambda m: None)


def foto_falsa(ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"png")
    return ruta


def partido_falso(registro, carpeta):
    return [foto_falsa(carpeta / n) for n in ("marcador.png", "alineacion_local.png", "alineacion_visita.png")]


def tabla_falsa(filas, ruta):
    return foto_falsa(ruta)


def relleno_falso(origen, destino):
    return foto_falsa(destino)


def correr_falso(tmp_path, params, pagina=None, cliente=None, salida=None, **kw):
    """Con un cliente y sin instagram, Instagram usa el mismo HttpFalso que el cliente."""
    if cliente is not None and "instagram" not in kw:
        kw["instagram"] = instagram(cliente._transporte, cliente)
    kw.setdefault("generar_partido", partido_falso)
    kw.setdefault("generar_tabla_img", tabla_falsa)
    return correr("prueba", pagina=pagina, base=tmp_path, params=params, cliente=cliente, rellenar=relleno_falso,
                  mostrar=(salida.append if salida is not None else lambda m: None), **kw)


# --- Cliente ---

def test_fotos_y_attached_media_en_orden(tmp_path):
    fotos = [foto_falsa(tmp_path / n) for n in ("marcador.png", "alineacion_local.png", "alineacion_visita.png")]
    http = HttpFalso()
    post_id = cliente(http).publicar_post("hola", fotos)

    subidas = [c for m, u, c, h in http.llamadas if u.endswith("/photos")]
    assert [f'filename="{f.name}"'.encode() in s for f, s in zip(fotos, subidas)] == [True] * 3
    assert all(b'name="published"\r\n\r\nfalse' in s for s in subidas)
    assert http.llamadas[-1][1].endswith(f"/{PAGE_ID}/feed")
    feed = http.feeds()[0]
    assert feed["message"] == ["hola"]
    assert [json.loads(feed[f"attached_media[{i}]"][0]) for i in range(3)] == \
        [{"media_fbid": "foto1"}, {"media_fbid": "foto2"}, {"media_fbid": "foto3"}]
    assert post_id == f"{PAGE_ID}_post1"


def test_post_nuevo_busca_antes_y_publica(tmp_path):
    foto = foto_falsa(tmp_path / "marcador.png")
    http = HttpFalso(posts=[{"id": "111_viejo", "message": "otro texto"}])
    assert cliente(http).publicar_post("hola", [foto]) == f"{PAGE_ID}_post1"
    assert http.rutas() == ["photos", "posts", "feed"]


def test_post_ya_existente_no_llama_a_feed(tmp_path):
    foto = foto_falsa(tmp_path / "marcador.png")
    avisos = []
    http = HttpFalso(posts=[{"id": "111_viejo", "message": "  hola\n"}, {"id": "111_otro", "message": "chau"}])
    c = Cliente("prueba", PAGE_ID, "token-falso", transporte=http, dormir=lambda s: None, avisar=avisos.append)
    assert c.publicar_post("hola", [foto]) == "111_viejo"
    assert "feed" not in http.rutas()
    assert avisos == ["ya estaba publicado, se marca sin volver a publicar: 111_viejo"]
    assert all("token-falso" not in a for a in avisos)


def test_respuesta_perdida_no_duplica_el_post(tmp_path):
    foto = foto_falsa(tmp_path / "marcador.png")
    http, dormidas = HttpFalso(perder=lambda n: n == 1), []
    assert cliente(http, dormidas=dormidas).publicar_post("hola", [foto]) == f"{PAGE_ID}_post1"
    assert http.rutas() == ["photos", "posts", "feed", "posts"]
    assert http.n_feeds == 1 and len(http.posts) == 1 and dormidas == [60]


def test_busqueda_que_no_responde_agota_sin_reintentos_anidados(tmp_path):
    foto = foto_falsa(tmp_path / "marcador.png")
    http, dormidas = HttpFalso(fallar=lambda n, m, u: "/posts" in u), []
    with pytest.raises(ErrorFacebook):
        cliente(http, dormidas=dormidas).publicar_post("hola", [foto])
    assert http.rutas().count("posts") == 11 and "feed" not in http.rutas()
    assert dormidas == [60] * 10


def test_version_por_defecto_y_token_en_header():
    http = HttpFalso()
    cliente(http).verificar_pagina()
    metodo, url, cuerpo, headers = http.llamadas[0]
    assert url.startswith("https://graph.facebook.com/v26.0/me")
    assert "token-falso" not in url and headers["Authorization"] == "Bearer token-falso"


def test_me_con_nombre_equivocado_aborta_sin_reintentar():
    http = HttpFalso(nombre="Peruvian Football BOT 1")
    with pytest.raises(PaginaEquivocada):
        cliente(http).verificar_pagina()
    assert len(http.llamadas) == 1


def test_me_con_id_equivocado_aborta():
    with pytest.raises(PaginaEquivocada):
        cliente(HttpFalso(page_id="999")).verificar_pagina()


def test_reintentos_agotados_lanzan_error():
    http, dormidas = HttpFalso(fallar=lambda n, m, u: True), []
    with pytest.raises(ErrorFacebook):
        cliente(http, dormidas=dormidas).verificar_pagina()
    assert len(http.llamadas) == 11      # el primero + uno cada 60 s durante 10 minutos
    assert dormidas == [60] * 10


def test_exito_al_tercer_intento():
    http, dormidas = HttpFalso(fallar=lambda n, m, u: n < 3), []
    assert cliente(http, dormidas=dormidas).verificar_pagina()["name"] == "Gokú - Kakaroto"
    assert len(http.llamadas) == 3 and dormidas == [60, 60]


def test_leer_env_solo_las_claves_pedidas(tmp_path):
    env = tmp_path / ".env"
    env.write_text('# comentario\nFB_TEST_PAGE_ID="111"\nFB_PAGE_TOKEN=otro\nFB_API_VERSION=\n', encoding="utf-8")
    assert leer_env({"FB_TEST_PAGE_ID", "FB_API_VERSION"}, env) == {"FB_TEST_PAGE_ID": "111", "FB_API_VERSION": ""}


def test_desde_env_lee_la_version(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FB_TEST_PAGE_ID=111\nFB_TEST_PAGE_TOKEN=x\nFB_API_VERSION=v27.0\n", encoding="utf-8")
    assert Cliente.desde_env("prueba", env).api == "https://graph.facebook.com/v27.0"
    env.write_text("FB_TEST_PAGE_ID=111\nFB_TEST_PAGE_TOKEN=x\nFB_API_VERSION=\n", encoding="utf-8")
    assert Cliente.desde_env("prueba", env).api == "https://graph.facebook.com/v26.0"


def test_desde_env_sin_token_falla(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FB_TEST_PAGE_ID=111\nFB_TEST_PAGE_TOKEN=\n", encoding="utf-8")
    with pytest.raises(ErrorFacebook):
        Cliente.desde_env("prueba", env)


# --- Corrida ---

def test_dry_run_no_escribe_publicados_ni_acumula(tmp_path, params, monkeypatch):
    monkeypatch.setattr(Cliente, "desde_env", classmethod(lambda cls, *a, **k: pytest.fail("tocó el .env")))
    monkeypatch.setattr(Instagram, "desde_env", classmethod(lambda cls, *a, **k: pytest.fail("tocó el .env")))
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    salida = []
    correr_falso(tmp_path, params, salida=salida)
    correr_falso(tmp_path, params, salida=salida)
    assert not ruta_publicados("prueba", tmp_path).exists()
    assert [r["partido_id"] for r in cargar_registros("prueba", tmp_path)] == ["F01-P1"]
    assert len(salida) == 2 and all(s.startswith("[dry-run] F01-P1 (partido)\n") for s in salida)
    assert "alineacion_visita.png" in salida[0]
    assert f"comentario:\n{COMENTARIO_INSTAGRAM}\ninstagram (carrusel" in salida[0]
    carpeta = tmp_path / "prueba" / "imagenes" / "F01-P1"
    assert salida[0].endswith(f"  1. {carpeta / 'marcador.png'}\n  2. {carpeta / 'alineacion_local_ig.png'}\n"
                              f"  3. {carpeta / 'alineacion_visita_ig.png'}")
    assert (carpeta / "alineacion_local_ig.png").exists() and (carpeta / "alineacion_visita_ig.png").exists()


def test_publica_y_marca(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    registro = cargar_registros("prueba", tmp_path)[0]
    assert http.feeds()[0]["message"] == [texto_partido(registro)]
    entrada = cargar_publicados("prueba", tmp_path)["F01-P1"]
    assert entrada["tipo"] == "partido" and entrada["post_id"] == f"{PAGE_ID}_post1"
    assert entrada["pagina"] == "prueba" and entrada["page_id"] == PAGE_ID
    assert entrada["fecha_hora"].endswith("-05:00")


def test_retomar_pendiente_no_vuelve_a_simular(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    caida = HttpFalso(fallar=lambda n, m, u: u.endswith("/feed"))
    with pytest.raises(ErrorFacebook):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(caida))
    pendiente = cargar_registros("prueba", tmp_path)
    assert [r["partido_id"] for r in pendiente] == ["F01-P1"]
    assert cargar_publicados("prueba", tmp_path) == {}

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    registros = cargar_registros("prueba", tmp_path)
    assert registros[0] == pendiente[0]                       # mismo registro, misma semilla
    assert [r["partido_id"] for r in registros] == ["F01-P1", "F01-P2"]
    assert [f["message"][0] for f in http.feeds()] == [texto_partido(r) for r in registros]
    assert set(cargar_publicados("prueba", tmp_path)) == {"F01-P1", "F01-P2"}


def test_pendiente_ya_en_la_pagina_se_marca_sin_publicar(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    registro = jugar_siguiente("prueba", params, base=tmp_path)    # se cayó después de publicar, antes de marcar
    http = HttpFalso(posts=[{"id": "111_ya", "message": texto_partido(registro)}])
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    publicados = cargar_publicados("prueba", tmp_path)
    assert publicados["F01-P1"]["post_id"] == "111_ya"
    assert publicados["F01-P2"]["post_id"] == f"{PAGE_ID}_post1"
    assert http.n_feeds == 1 and http.feeds()[0]["message"] != [texto_partido(registro)]


def test_tabla_solo_al_cerrar_la_fecha(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    tablas = []

    def tabla_anotada(filas, ruta):
        tablas.append(filas)
        return foto_falsa(ruta)

    http = HttpFalso()
    for _ in range(8):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http), generar_tabla_img=tabla_anotada)
    assert "tabla-F01" not in cargar_publicados("prueba", tmp_path) and tablas == []

    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http), generar_tabla_img=tabla_anotada)
    publicados = cargar_publicados("prueba", tmp_path)
    assert publicados["tabla-F01"]["tipo"] == "tabla"
    assert http.feeds()[-1]["message"] == [texto_tabla(1)]
    assert len(tablas) == 1 and sum(f["pj"] for f in tablas[0]) == 18 and len(tablas[0]) == 18
    assert list(publicados)[-2:] == ["F01-P9", "tabla-F01"]


def test_tabla_de_la_fecha_ignora_fechas_posteriores(tmp_path, params):
    t = nueva_temporada("prueba", semilla=1, base=tmp_path)
    for _ in range(10):                                       # fecha 1 completa + F02-P1
        jugar_siguiente("prueba", params, base=tmp_path)
    tablas = []
    armar_post(("tabla", 1), t, cargar_registros("prueba", tmp_path), tmp_path / "img", cargar_nombres(),
               generar_tabla_img=lambda filas, ruta: tablas.append(filas))
    assert sum(f["pj"] for f in tablas[0]) == 18


def test_mezclar_paginas_aborta(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    marcar("prueba", "F01-P1", "partido", "999_post1", "real", "999", base=tmp_path)
    http = HttpFalso()
    with pytest.raises(MezclaDePaginas):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    assert http.llamadas == []


def test_main_sale_con_error_si_se_agotan_los_reintentos(tmp_path, params, monkeypatch):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    caida = cliente(HttpFalso(fallar=lambda n, m, u: True))
    monkeypatch.setattr(correr_mod, "CARPETA_TEMPORADAS", tmp_path)
    monkeypatch.setattr(Cliente, "desde_env", classmethod(lambda cls, pagina, **k: caida))
    monkeypatch.setattr(Instagram, "desde_env", classmethod(lambda cls, subidor, **k: instagram(caida._transporte, subidor)))
    assert main(["prueba", "--pagina", "prueba"]) != 0


# --- Comentario ---

def mi_comentario(cid, mensaje=COMENTARIO_INSTAGRAM, de=PAGE_ID):
    return {"id": cid, "message": mensaje, "from": {"id": de}}


def test_comentar_busca_antes_y_comenta():
    http = HttpFalso()
    assert cliente(http).comentar("111_p", COMENTARIO_INSTAGRAM) == "111_p_com1"
    assert [(m, r) for (m, *_), r in zip(http.llamadas, http.rutas())] == [("GET", "comments"), ("POST", "comments")]
    assert http.comentados() == [("111_p", COMENTARIO_INSTAGRAM)]
    assert all(h["Authorization"] == "Bearer token-falso" and "token-falso" not in u for m, u, c, h in http.llamadas)


def test_comentario_ya_existente_no_comenta_de_nuevo():
    http = HttpFalso(comentarios={"111_p": [mi_comentario("111_p_ya", "  " + COMENTARIO_INSTAGRAM + "\n")]})
    assert cliente(http).comentar("111_p", COMENTARIO_INSTAGRAM) == "111_p_ya"
    assert http.comentados() == []


def test_comentario_igual_de_otro_usuario_no_cuenta():
    http = HttpFalso(comentarios={"111_p": [mi_comentario("111_p_otro", de="555")]})
    assert cliente(http).comentar("111_p", COMENTARIO_INSTAGRAM) == "111_p_com1"
    assert http.comentados() == [("111_p", COMENTARIO_INSTAGRAM)]


def test_partido_nuevo_post_y_comentario_completo(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    post_id = f"{PAGE_ID}_post1"
    assert http.comentados() == [(post_id, COMENTARIO_INSTAGRAM)]
    assert http.rutas().index("feed") < http.rutas().index("comments")
    entrada = cargar_publicados("prueba", tmp_path)["F01-P1"]
    assert entrada["post_id"] == post_id and entrada["comentario_id"] == f"{post_id}_com1"


def test_comentario_fallido_queda_parcial_y_luego_solo_comenta(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    caida = HttpFalso(fallar=lambda n, m, u: m == "POST" and u.endswith("/comments"))
    with pytest.raises(ErrorFacebook):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(caida))
    entrada = cargar_publicados("prueba", tmp_path)["F01-P1"]
    assert entrada["post_id"] == f"{PAGE_ID}_post1" and entrada["comentario_id"] is None
    assert caida.n_feeds == 1

    generados = []

    def partido_anotado(registro, carpeta):
        generados.append(registro["partido_id"])
        return partido_falso(registro, carpeta)

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http), generar_partido=partido_anotado)
    # F01-P1: sin /photos ni /feed para Facebook, solo el comentario y después Instagram (que sí
    # regenera las imágenes); luego se juega y publica F01-P2
    assert http.rutas()[:4] == ["me", IG_ID, "comments", "comments"]
    assert http.comentados()[0] == (f"{PAGE_ID}_post1", COMENTARIO_INSTAGRAM)
    assert [f["message"][0] for f in http.feeds()] == [texto_partido(cargar_registros("prueba", tmp_path)[1])]
    assert generados == ["F01-P1", "F01-P2"]
    publicados = cargar_publicados("prueba", tmp_path)
    assert publicados["F01-P1"]["post_id"] == f"{PAGE_ID}_post1"
    assert publicados["F01-P1"]["comentario_id"] == f"{PAGE_ID}_post1_com1"
    assert publicados["F01-P2"]["comentario_id"]


def test_entrada_vieja_sin_comentario_id_es_completa(tmp_path, params):
    t = nueva_temporada("prueba", semilla=1, base=tmp_path)
    jugar_siguiente("prueba", params, base=tmp_path)
    _escribir_json(ruta_publicados("prueba", tmp_path), {"F01-P1": {
        "tipo": "partido", "post_id": "111_viejo", "pagina": "prueba", "page_id": PAGE_ID,
        "fecha_hora": "2026-10-08T18:08:23-05:00"}})
    assert pendientes(t, cargar_registros("prueba", tmp_path), cargar_publicados("prueba", tmp_path)) == []

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    assert all(post_id != "111_viejo" for post_id, _ in http.comentados())
    assert "comentario_id" not in cargar_publicados("prueba", tmp_path)["F01-P1"]


def test_tabla_no_sale_con_un_partido_incompleto(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    for _ in range(9):
        jugar_siguiente("prueba", params, base=tmp_path)
    registros = cargar_registros("prueba", tmp_path)
    for r in registros:
        marcar("prueba", r["partido_id"], "partido", f"{PAGE_ID}_{r['partido_id']}", "prueba", PAGE_ID, base=tmp_path)
        if r["partido_id"] != "F01-P5":
            marcar_comentario("prueba", r["partido_id"], "com", base=tmp_path)
            marcar_instagram("prueba", r["partido_id"], "ig", base=tmp_path)
    t = cargar_temporada("prueba", tmp_path)

    items = pendientes(t, registros, cargar_publicados("prueba", tmp_path))
    assert [(tipo, d["partido_id"], f) for tipo, d, f in items] == [("partido", "F01-P5", "comentario")]

    marcar_comentario("prueba", "F01-P5", "com", base=tmp_path)
    items = pendientes(t, registros, cargar_publicados("prueba", tmp_path))
    assert [(tipo, d["partido_id"], f) for tipo, d, f in items] == [("partido", "F01-P5", "instagram")]

    marcar_instagram("prueba", "F01-P5", "ig", base=tmp_path)
    assert pendientes(t, registros, cargar_publicados("prueba", tmp_path)) == [("tabla", 1, "post")]


# --- Instagram ---

def test_partido_carrusel_de_3_en_orden_y_entrada_completa(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    registro = cargar_registros("prueba", tmp_path)[0]

    # 3 fotos para el post de Facebook y, aparte, 3 para las URL de Instagram
    assert http.subidas() == ["marcador.png", "alineacion_local.png", "alineacion_visita.png",
                              "marcador.png", "alineacion_local_ig.png", "alineacion_visita_ig.png"]
    assert http.contenedores == {
        "cont1": {"image_url": "https://scontent.falso/foto4.jpg", "is_carousel_item": "true"},
        "cont2": {"image_url": "https://scontent.falso/foto5.jpg", "is_carousel_item": "true"},
        "cont3": {"image_url": "https://scontent.falso/foto6.jpg", "is_carousel_item": "true"},
        "cont4": {"media_type": "CAROUSEL", "children": "cont1,cont2,cont3", "caption": texto_partido(registro)},
    }
    assert http.rutas().index("comments") < http.rutas().index("media")
    # hijos creados y FINISHED antes de crear el padre; el padre FINISHED antes de publicar
    de_instagram = [(m, r) for (m, *_), r in zip(http.llamadas, http.rutas()) if r.startswith(("media", "cont"))]
    assert de_instagram == [("POST", "media")] * 3 + [("GET", "cont1"), ("GET", "cont2"), ("GET", "cont3"),
                                                      ("POST", "media"), ("GET", "cont4"),
                                                      ("GET", "media"), ("POST", "media_publish")]
    publicado = [urllib.parse.parse_qs(c.decode()) for m, u, c, h in http.llamadas if u.endswith("/media_publish")]
    assert publicado == [{"creation_id": ["cont4"]}]

    entrada = cargar_publicados("prueba", tmp_path)["F01-P1"]
    assert entrada["post_id"] and entrada["comentario_id"] and entrada["ig_media_id"] == "ig1"
    assert [(m["id"], m["caption"]) for m in http.ig_media] == [("ig1", texto_partido(registro))]


def test_tabla_en_instagram_es_una_foto_con_caption(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    for _ in range(9):
        jugar_siguiente("prueba", params, base=tmp_path)
    for r in cargar_registros("prueba", tmp_path):
        marcar("prueba", r["partido_id"], "partido", f"{PAGE_ID}_{r['partido_id']}", "prueba", PAGE_ID, base=tmp_path)
        marcar_comentario("prueba", r["partido_id"], "com", base=tmp_path)
        marcar_instagram("prueba", r["partido_id"], "ig", base=tmp_path)

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    assert http.subidas()[:2] == ["tabla-F01.png", "tabla-F01.png"]       # Facebook y la URL de Instagram
    assert http.contenedores["cont1"] == {"image_url": "https://scontent.falso/foto2.jpg", "caption": texto_tabla(1)}
    assert cargar_publicados("prueba", tmp_path)["tabla-F01"]["ig_media_id"] == "ig1"


def test_contenedor_en_error_deja_instagram_pendiente_y_se_rehace_solo_instagram(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    caida = HttpFalso(estado=lambda cid, n: "ERROR" if cid == "cont2" else "FINISHED")
    with pytest.raises(ErrorInstagram, match="cont2 quedó en ERROR: ERROR: detalle de cont2"):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(caida))
    assert "media_publish" not in caida.rutas()
    entrada = cargar_publicados("prueba", tmp_path)["F01-P1"]
    assert entrada["post_id"] == f"{PAGE_ID}_post1" and entrada["comentario_id"] and entrada["ig_media_id"] is None

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    registros = cargar_registros("prueba", tmp_path)
    # F01-P1: cero /feed y cero /comments; Instagram de cero (fotos nuevas, contenedores nuevos)
    antes_de_p2 = http.rutas()[:http.rutas().index("feed")]
    assert "comments" not in antes_de_p2
    assert [f["message"][0] for f in http.feeds()] == [texto_partido(registros[1])]
    assert http.subidas()[:3] == ["marcador.png", "alineacion_local_ig.png", "alineacion_visita_ig.png"]
    assert http.contenedores["cont4"]["caption"] == texto_partido(registros[0])
    assert cargar_publicados("prueba", tmp_path)["F01-P1"]["ig_media_id"] == "ig1"


def test_contenedor_que_no_termina_falla_a_los_2_minutos(tmp_path):
    foto = foto_falsa(tmp_path / "tabla-F01.png")
    http, dormidas = HttpFalso(estado=lambda cid, n: "IN_PROGRESS"), []
    with pytest.raises(ErrorInstagram, match="no terminó a tiempo"):
        instagram(http, cliente(http), dormidas).publicar_foto(foto, "hola", AHORA)
    assert http.consultas == {"cont1": 25} and dormidas == [5] * 24


def test_media_publish_ya_existente_no_publica_de_nuevo(tmp_path):
    foto = foto_falsa(tmp_path / "tabla-F01.png")
    avisos = []
    http = HttpFalso(ig_media=[{"id": "ig_ya", "caption": "  hola\n", "timestamp": "2026-10-10T23:01:00+0000"},
                               {"id": "ig_otro", "caption": "chau", "timestamp": "2026-10-10T23:02:00+0000"}])
    ig = Instagram(IG_ID, "token-ig", cliente(http), transporte=http, dormir=lambda s: None, avisar=avisos.append)
    assert ig.publicar_foto(foto, "hola", AHORA) == "ig_ya"      # AHORA = 23:00 UTC
    assert "media_publish" not in http.rutas()
    assert avisos == ["ya estaba en Instagram, se marca sin volver a publicar: ig_ya"]


def test_respuesta_perdida_de_media_publish_no_duplica(tmp_path):
    foto = foto_falsa(tmp_path / "tabla-F01.png")
    http, dormidas = HttpFalso(), []
    original = http.__call__

    def perder_la_primera(metodo, url, cuerpo, headers):
        respuesta = original(metodo, url, cuerpo, headers)
        if url.endswith("/media_publish") and len(http.ig_media) == 1 and not dormidas:
            raise TimeoutError("se perdió la respuesta")
        return respuesta

    ig = instagram(perder_la_primera, cliente(http), dormidas)
    assert ig.publicar_foto(foto, "hola", datetime.now(timezone.utc)) == "ig1"
    assert http.rutas().count("media_publish") == 1 and len(http.ig_media) == 1 and dormidas == [60]


def test_con_pagina_prueba_fotos_a_goku_e_instagram_con_el_token_de_la_pagina_real(tmp_path, params):
    env = tmp_path / ".env"
    env.write_text(f"FB_TEST_PAGE_ID={PAGE_ID}\nFB_TEST_PAGE_TOKEN=token-goku\nFB_PAGE_ID=999\n"
                   f"FB_PAGE_TOKEN=token-real\nIG_USER_ID={IG_ID}\nFB_API_VERSION=\n", encoding="utf-8")
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso()
    sin_espera = {"transporte": http, "dormir": lambda s: None, "avisar": lambda m: None}
    goku = Cliente.desde_env("prueba", env, **sin_espera)
    ig = Instagram.desde_env(goku, env, **sin_espera)
    correr_falso(tmp_path, params, pagina="prueba", cliente=goku, instagram=ig)

    assert ig.api == "https://graph.facebook.com/v26.0"
    llamadas = [(u.split("?")[0], h["Authorization"]) for m, u, c, h in http.llamadas]
    fotos = [(r, t) for r, t in llamadas if r.endswith("/photos") or "/foto" in r]
    de_instagram = [(r, t) for r, t in llamadas if f"/{IG_ID}" in r or "/cont" in r]
    assert len(fotos) == 9           # 3 subidas para Facebook, 3 para Instagram y sus 3 GET de images
    assert len(de_instagram) == 11   # cuenta, 3 hijos, 3 estados, padre, estado, búsqueda y media_publish
    assert all(r.endswith(f"/{PAGE_ID}/photos") for r, t in fotos if r.endswith("/photos"))
    assert all(t == "Bearer token-goku" for r, t in fotos)
    assert all(t == "Bearer token-real" for r, t in de_instagram)
    assert all("token-" not in u and "/999" not in u for m, u, c, h in http.llamadas)


def test_caption_de_mas_de_2200_falla_sin_red(tmp_path):
    foto = foto_falsa(tmp_path / "marcador.png")
    http = HttpFalso()
    ig = instagram(http, cliente(http))
    with pytest.raises(ErrorInstagram, match="2201"):
        ig.publicar_foto(foto, "x" * 2201, AHORA)
    with pytest.raises(ErrorInstagram):
        ig.publicar_carrusel([foto] * 3, "x" * 2201, AHORA)
    assert http.llamadas == []


def test_entrada_sin_ig_media_id_es_completa(tmp_path, params):
    t = nueva_temporada("prueba", semilla=1, base=tmp_path)
    registro = jugar_siguiente("prueba", params, base=tmp_path)
    _escribir_json(ruta_publicados("prueba", tmp_path), {"F01-P1": {
        "tipo": "partido", "post_id": "111_viejo", "pagina": "prueba", "page_id": PAGE_ID,
        "fecha_hora": "2026-10-09T18:08:23-05:00", "comentario_id": "111_viejo_com"}})
    assert pendientes(t, cargar_registros("prueba", tmp_path), cargar_publicados("prueba", tmp_path)) == []

    http = HttpFalso()
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    assert all(c.get("caption") != texto_partido(registro) for c in http.contenedores.values())
    assert "ig_media_id" not in cargar_publicados("prueba", tmp_path)["F01-P1"]


def test_desde_env_de_instagram_sin_ig_user_id_falla(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FB_PAGE_TOKEN=x\nIG_USER_ID=\n", encoding="utf-8")
    with pytest.raises(ErrorFacebook):
        Instagram.desde_env(None, env)


def fecha_1_completa(tmp_path, params):
    """Los 9 partidos de la fecha 1 jugados y completos: lo siguiente pendiente es la tabla."""
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    for _ in range(9):
        jugar_siguiente("prueba", params, base=tmp_path)
    for r in cargar_registros("prueba", tmp_path):
        marcar("prueba", r["partido_id"], "partido", f"{PAGE_ID}_{r['partido_id']}", "prueba", PAGE_ID, base=tmp_path)
        marcar_comentario("prueba", r["partido_id"], "com", base=tmp_path)
        marcar_instagram("prueba", r["partido_id"], "ig", base=tmp_path)


def utc_ig(fecha):
    return fecha.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


@pytest.mark.parametrize("minutos, duplicado", [(-24 * 60, False), (-6, False), (-4, True), (10, True)])
def test_tabla_anti_duplicado_solo_desde_la_entrada(tmp_path, params, minutos, duplicado):
    """Un post de la cuenta con el mismo caption de la tabla cuenta como duplicado solo si es de
    después de la fecha_hora de la entrada, con 5 minutos de margen."""
    fecha_1_completa(tmp_path, params)
    previo = {"id": "ig_previo", "caption": texto_tabla(1), "timestamp": utc_ig(AHORA + timedelta(minutes=minutos))}
    http = HttpFalso(ig_media=[previo])
    correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http), ahora=AHORA)

    entrada = cargar_publicados("prueba", tmp_path)["tabla-F01"]
    assert entrada["fecha_hora"] == "2026-10-10T18:00:00-05:00"
    assert entrada["ig_media_id"] == ("ig_previo" if duplicado else "ig2")
    publicados_tabla = [c for m, u, c, h in http.llamadas if u.endswith("/media_publish")
                        and http.contenedores[urllib.parse.parse_qs(c.decode())["creation_id"][0]].get("caption")
                        == texto_tabla(1)]
    assert len(publicados_tabla) == (0 if duplicado else 1)


def test_cuenta_de_instagram_equivocada_aborta_antes_de_publicar(tmp_path, params):
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso(ig_usuario="otra.cuenta")
    with pytest.raises(CuentaEquivocada):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http))
    assert http.rutas() == ["me", IG_ID]          # sin reintentos y sin /photos, /feed ni /media
    assert not ruta_publicados("prueba", tmp_path).exists()


def test_sin_ig_user_id_aborta_al_inicio(tmp_path, params, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"FB_TEST_PAGE_ID={PAGE_ID}\nFB_TEST_PAGE_TOKEN=token-goku\nFB_PAGE_TOKEN=token-real\nIG_USER_ID=\n",
                   encoding="utf-8")
    original = Instagram.desde_env.__func__
    monkeypatch.setattr(Instagram, "desde_env", classmethod(lambda cls, subidor, **k: original(cls, subidor, env, **k)))
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    http = HttpFalso()
    goku = Cliente.desde_env("prueba", env, transporte=http, dormir=lambda s: None, avisar=lambda m: None)
    with pytest.raises(ErrorFacebook, match="IG_USER_ID"):
        correr("prueba", pagina="prueba", base=tmp_path, params=params, cliente=goku, generar_partido=partido_falso,
               generar_tabla_img=tabla_falsa, rellenar=relleno_falso, mostrar=lambda m: None)
    assert http.rutas() == ["me"]
    assert not ruta_publicados("prueba", tmp_path).exists()


def test_texto_de_mas_de_2200_falla_antes_de_facebook(tmp_path, params, monkeypatch):
    t = nueva_temporada("prueba", semilla=1, base=tmp_path)
    monkeypatch.setattr(correr_mod, "texto_partido", lambda registro, nombres=None: "x" * 2201)
    generados = []

    def partido_anotado(registro, carpeta):
        generados.append(registro["partido_id"])
        return partido_falso(registro, carpeta)

    # armar el post solo, sin cliente: falla antes de generar las imágenes
    registro = jugar_siguiente("prueba", params, base=tmp_path)
    with pytest.raises(ErrorInstagram, match="2201"):
        armar_post(("partido", registro), t, [registro], tmp_path / "img", cargar_nombres(),
                   generar_partido=partido_anotado)
    assert generados == []

    # en la corrida: ninguna llamada de publicación y nada marcado
    http = HttpFalso()
    with pytest.raises(ErrorInstagram, match="2201"):
        correr_falso(tmp_path, params, pagina="prueba", cliente=cliente(http), generar_partido=partido_anotado)
    assert generados == [] and http.rutas() == ["me", IG_ID]
    assert not ruta_publicados("prueba", tmp_path).exists()


def test_texto_de_2200_entra():
    comprobar_caption("x" * 2200)
