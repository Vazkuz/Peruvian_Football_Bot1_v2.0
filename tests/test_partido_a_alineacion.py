import json
import subprocess
import sys

from pfb.motor.plantillas import RAIZ

sys.path.insert(0, str(RAIZ / "scripts"))
from partido_a_alineacion import cargar_json, convertir  # noqa: E402

PARTIDO, CUSCO = "4942759", "28999"  # Comerciantes Unidos vs Cusco FC


def test_la_salida_lleva_club_id(tmp_path):
    salida = tmp_path / "alineacion.json"
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "partido_a_alineacion.py"), PARTIDO, CUSCO, str(salida)],
                   check=True)
    with open(salida, encoding="utf-8") as f:
        assert json.load(f)["club_id"] == CUSCO


def test_apellido_cortado_en_la_ficha_usa_el_nombre_completo():
    """En la ficha, el titular 662338 viene como 'Miguel Sil.'; en el rendimiento, 'Miguel Silveira'."""
    partido = cargar_json(RAIZ / "data" / "partidos" / f"{PARTIDO}.json")
    titular = next(t for e in partido["equipos"] if e["club_id"] == CUSCO for t in e["titulares"] if t["id"] == "662338")
    assert titular["nombre"] == "Miguel Sil."
    rendimiento = cargar_json(RAIZ / "data" / "rendimiento" / f"{CUSCO}.json")
    color = cargar_json(RAIZ / "data" / "colores_clubes.json")[CUSCO]
    nombres = [j["nombre"] for j in convertir(partido, CUSCO, color, rendimiento)["jugadores"]]
    assert "M. Silveira" in nombres and "M. Miguel Sil." not in nombres
