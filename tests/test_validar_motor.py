import importlib.util
import random

import pytest

from pfb.motor.plantillas import RAIZ

spec = importlib.util.spec_from_file_location("validar_motor", RAIZ / "scripts" / "validar_motor.py")
validar_motor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validar_motor)


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    salida = tmp_path_factory.mktemp("validacion") / "validacion.txt"
    texto, sim, real = validar_motor.validar(temporadas=1, semilla=7, procesos=1, salida=salida)
    return texto, dict((n, v) for n, v, _ in sim), dict((n, v) for n, v, _ in real), salida


def suma(m, prefijo):
    return sum(v for n, v in m.items() if n.startswith(prefijo))


def test_corre_y_guarda_la_tabla(corrida):
    texto, _, _, salida = corrida
    assert salida.read_text(encoding="utf-8") == texto
    assert "Métrica" in texto and "306 partidos" in texto and "90 partidos reales" in texto


@pytest.mark.parametrize("cual", [1, 2])
def test_porcentajes_suman_100_y_medias_no_negativas(corrida, cual):
    m = corrida[cual]
    assert suma(m, "Partidos con ") - m["Partidos con al menos una roja"] == pytest.approx(100)
    assert m["Goles en el 1T"] + m["Goles en el 2T"] == pytest.approx(100)
    assert m["Gana local"] + m["Empate"] + m["Gana visita"] == pytest.approx(100)
    assert suma(m, "Equipos con ") == pytest.approx(100)
    assert m["Goles del local por partido"] + m["Goles de la visita por partido"] == pytest.approx(m["Goles por partido"])
    for nombre, valor in m.items():
        if not nombre.startswith("Bono"):  # la racha puede ser negativa
            assert valor >= 0, nombre


def test_misma_semilla_misma_corrida():
    a, _ = validar_motor.simular(1, semilla=11, procesos=1)
    b, _ = validar_motor.simular(1, semilla=11, procesos=1)
    assert a == b


def test_no_deja_el_generador_cambiado():
    validar_motor.simular_temporada(3)
    assert validar_motor.partido.random is random
