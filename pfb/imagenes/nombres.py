"""Nombres cortos para la imagen de alineacion: 'Ángel de la Cruz' -> 'A. De La Cruz'."""

import unicodedata

PARTICULAS = {"de", "del", "di", "la", "las", "los", "da", "do", "dos", "van", "von"}


def sin_tilde(letra):
    return unicodedata.normalize("NFD", letra)[0]


def capitalizar(apellido):
    return " ".join(p[:1].upper() + p[1:] for p in apellido.split())


def apellido_de(nombre_completo):
    partes = nombre_completo.split()
    if len(partes) == 1:
        return partes[0]
    resto = partes[1:]
    if any(p.lower() in PARTICULAS for p in resto):
        return " ".join(resto)
    return resto[-1]


def corto(nombre_completo, apellido=None):
    """'Ángel de la Cruz' -> 'A. De La Cruz'. Los de un solo nombre ('Cristiano') quedan igual."""
    if len(nombre_completo.split()) == 1 and not apellido:
        return nombre_completo
    inicial = sin_tilde(nombre_completo.split()[0][0]).upper()
    return f"{inicial}. {capitalizar(apellido or apellido_de(nombre_completo))}"
