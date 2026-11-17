"""Pruebas UNITARIAS del cliente hacia ledger-service (cobro de compras con tarjeta).

ledger-service se simula con mocks de httpx: nunca se aprueba una compra si el
ledger no pudo descontarla.
"""
import uuid
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest

from app.ledger_client import (
    CUENTA_PUENTE_EXTERNA, LedgerRejected, LedgerUnavailable, cobrar_compra, saldo_cuenta,
)

ID_CUENTA = uuid.uuid4()


def _respuesta(status: int, cuerpo: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=cuerpo or {}, request=httpx.Request("GET", "http://ledger-service"))


def test_saldo_se_lee_como_decimal():
    with patch("app.ledger_client.httpx.get", return_value=_respuesta(200, {"saldo_actual": "125000.50"})):
        assert saldo_cuenta(ID_CUENTA) == Decimal("125000.50")


def test_cuenta_sin_movimientos_tiene_saldo_cero():
    with patch("app.ledger_client.httpx.get", return_value=_respuesta(404)):
        assert saldo_cuenta(ID_CUENTA) == Decimal("0")


def test_ledger_caido_al_consultar_saldo():
    with patch("app.ledger_client.httpx.get", side_effect=httpx.ConnectTimeout("timeout")):
        with pytest.raises(LedgerUnavailable):
            saldo_cuenta(ID_CUENTA)
    with patch("app.ledger_client.httpx.get", return_value=_respuesta(502)):
        with pytest.raises(LedgerUnavailable, match="502"):
            saldo_cuenta(ID_CUENTA)


def test_cobrar_compra_envia_un_asiento_de_partida_doble():
    with patch("app.ledger_client.httpx.post", return_value=_respuesta(201)) as mock_post:
        cobrar_compra("AUT-1", ID_CUENTA, Decimal("89900"))

    cuerpo = mock_post.call_args.kwargs["json"]
    assert cuerpo["tipo_transaccion"] == "compra_tarjeta" and cuerpo["referencia"] == "AUT-1"
    debito, credito = cuerpo["movimientos"]
    assert debito == {"id_cuenta": str(ID_CUENTA), "tipo_movimiento": "debito", "monto": "89900"}
    assert credito == {"id_cuenta": str(CUENTA_PUENTE_EXTERNA), "tipo_movimiento": "credito", "monto": "89900"}


def test_rechazo_del_ledger_conserva_codigo_y_detalle():
    respuesta = _respuesta(409, {"detail": "La cuenta no esta activa"})
    with patch("app.ledger_client.httpx.post", return_value=respuesta):
        with pytest.raises(LedgerRejected) as error:
            cobrar_compra("AUT-2", ID_CUENTA, Decimal("10"))
    assert error.value.status_code == 409 and "no esta activa" in error.value.detail


def test_ledger_caido_al_cobrar():
    with patch("app.ledger_client.httpx.post", return_value=_respuesta(500)):
        with pytest.raises(LedgerUnavailable):
            cobrar_compra("AUT-3", ID_CUENTA, Decimal("10"))
    with patch("app.ledger_client.httpx.post", side_effect=httpx.ConnectError("sin red")):
        with pytest.raises(LedgerUnavailable):
            cobrar_compra("AUT-4", ID_CUENTA, Decimal("10"))
