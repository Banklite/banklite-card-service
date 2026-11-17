"""Pruebas UNITARIAS del enriquecimiento de tarjetas por BIN.

Los proveedores externos (handyapi y binlist) se simulan con un mock de httpx.get:
se comprueba el orden de consulta, el respaldo, la cache y el comportamiento fail-open.
"""
from unittest.mock import patch

import httpx
import pytest

from app import bin_lookup

HANDY_OK = {
    "Status": "SUCCESS", "Scheme": "VISA", "Type": "DEBIT", "Issuer": "BANCOLOMBIA S.A.",
    "Country": {"Name": "Colombia", "A2": "CO"},
}
BINLIST_OK = {
    "scheme": "mastercard", "type": "credit", "bank": {"name": "Banco de Bogota"},
    "country": {"name": "Colombia", "alpha2": "CO"},
}


@pytest.fixture(autouse=True)
def cache_limpia():
    bin_lookup._cache.clear()
    yield
    bin_lookup._cache.clear()


def _proveedores(respuestas: dict):
    """Devuelve un httpx.get falso: responde segun el dominio y anota las URLs consultadas."""
    llamadas = []

    def fake_get(url, **kwargs):
        llamadas.append(url)
        for dominio, (status, cuerpo) in respuestas.items():
            if dominio in url:
                return httpx.Response(status, json=cuerpo)
        raise httpx.ConnectError("sin red")

    return fake_get, llamadas


def test_usa_handyapi_y_normaliza_los_datos():
    fake, llamadas = _proveedores({"handyapi": (200, HANDY_OK)})
    with patch("app.bin_lookup.httpx.get", side_effect=fake):
        info = bin_lookup.consultar_bin("4411190000001234")

    assert info == {
        "marca": "visa", "tipo": "debit", "banco": "BANCOLOMBIA S.A.",
        "pais": "Colombia", "pais_codigo": "CO", "proveedor": "handyapi",
    }
    assert llamadas == ["https://data.handyapi.com/bin/441119"]  # solo los 6 primeros digitos salen del servicio


def test_si_handyapi_responde_429_usa_binlist_de_respaldo():
    fake, llamadas = _proveedores({"handyapi": (429, {}), "binlist": (200, BINLIST_OK)})
    with patch("app.bin_lookup.httpx.get", side_effect=fake):
        info = bin_lookup.consultar_bin("5399830000001234")

    assert info["proveedor"] == "binlist" and info["marca"] == "mastercard"
    assert len(llamadas) == 2


def test_la_segunda_consulta_del_mismo_bin_sale_de_la_cache():
    fake, llamadas = _proveedores({"handyapi": (200, HANDY_OK)})
    with patch("app.bin_lookup.httpx.get", side_effect=fake):
        bin_lookup.consultar_bin("4411190000001234")
        bin_lookup.consultar_bin("4411199999999999")

    assert len(llamadas) == 1


def test_si_ningun_proveedor_responde_devuelve_none_sin_fallar():
    fake, _ = _proveedores({})  # los dos lanzan error de red
    with patch("app.bin_lookup.httpx.get", side_effect=fake):
        assert bin_lookup.consultar_bin("4411190000001234") is None


@pytest.mark.parametrize("numero", ["", "4411", None, "abcd-efgh"])
def test_numero_sin_seis_digitos_no_consulta_a_nadie(numero):
    with patch("app.bin_lookup.httpx.get") as mock_get:
        assert bin_lookup.consultar_bin(numero) is None
    mock_get.assert_not_called()
