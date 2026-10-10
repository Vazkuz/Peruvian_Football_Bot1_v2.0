import json
import urllib.parse

import pytest

import pfb.publicacion.correr as correr_mod
from pfb.motor.partido import cargar_parametros
from pfb.motor.temporada import cargar_nombres, cargar_registros, jugar_siguiente, nueva_temporada
from pfb.publicacion.correr import armar_post, correr, main
from pfb.publicacion.facebook import Cliente, ErrorFacebook, PaginaEquivocada, leer_env
from pfb.publicacion.publicados import (MezclaDePaginas, cargar_publicados, marcar, ruta_publicados)
from pfb.publicacion.texto import texto_partido, texto_tabla

PAGE_ID = "111"


@pytest.fixture(scope="module")
def params():
    return cargar_parametros()


class HttpFalso:
    """Responde como la Graph API y anota cada llamada. fallar(n_llamada, metodo, url) -> bool.
    perder(n_feed) -> bool: ese /feed se publica pero la respuesta no llega."""

    def __init__(self, nombre="Gokú - Kakaroto", page_id=PAGE_ID, fallar=None, perder=None, posts=None):
        self.nombre, self.page_id, self.fallar, self.perder = nombre, page_id, fallar, perder
        self.llamadas = []
        self.posts = list(posts or [])          # los más nuevos al final
        self.n_fotos = self.n_feeds = 0

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
        raise AssertionError(f"llamada inesperada: {metodo} {url}")

    def rutas(self):
        return [u.split("?")[0].rsplit("/", 1)[-1] for m, u, c, h in self.llamadas]

    def feeds(self):
        return [urllib.parse.parse_qs(c.decode()) for m, u, c, h in self.llamadas if u.endswith("/feed")]


def cliente(http, pagina="prueba", page_id=PAGE_ID, dormidas=None):
    dormidas = [] if dormidas is None else dormidas
    return Cliente(pagina, page_id, "token-falso", transporte=http, dormir=dormidas.append, avisar=lambda m: None)


def foto_falsa(ruta):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"png")
    return ruta


def partido_falso(registro, carpeta):
    return [foto_falsa(carpeta / n) for n in ("marcador.png", "alineacion_local.png", "alineacion_visita.png")]


def tabla_falsa(filas, ruta):
    return foto_falsa(ruta)


def correr_falso(tmp_path, params, pagina=None, cliente=None, salida=None, **kw):
    return correr("prueba", pagina=pagina, base=tmp_path, params=params, cliente=cliente,
                  generar_partido=partido_falso, generar_tabla_img=kw.pop("generar_tabla_img", tabla_falsa),
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
    nueva_temporada("prueba", semilla=1, base=tmp_path)
    salida = []
    correr_falso(tmp_path, params, salida=salida)
    correr_falso(tmp_path, params, salida=salida)
    assert not ruta_publicados("prueba", tmp_path).exists()
    assert [r["partido_id"] for r in cargar_registros("prueba", tmp_path)] == ["F01-P1"]
    assert len(salida) == 2 and all(s.startswith("[dry-run] F01-P1 (partido)") for s in salida)
    assert "alineacion_visita.png" in salida[0]


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
    assert main(["prueba", "--pagina", "prueba"]) != 0
