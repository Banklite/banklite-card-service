"""Cliente REST sincrono hacia ledger-service para cobrar las compras con tarjeta."""

import logging
import uuid
from decimal import Decimal

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# Debe coincidir con CUENTA_PUENTE_EXTERNA de ledger-service: representa al comercio
# (el dinero sale de la cuenta del cliente hacia afuera del banco).
CUENTA_PUENTE_EXTERNA = uuid.UUID("00000000-0000-0000-0000-000000000001")


class LedgerUnavailable(RuntimeError):
    """ledger-service no respondio: no se puede aprobar sin poder descontar."""


class LedgerRejected(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def saldo_cuenta(id_cuenta: uuid.UUID) -> Decimal:
    """Saldo actual segun el ledger (0 si la cuenta aun no tiene movimientos)."""
    try:
        r = httpx.get(f"{settings.ledger_service_url}/ledger/accounts/{id_cuenta}", timeout=settings.ledger_timeout_seconds)
    except httpx.RequestError as exc:
        raise LedgerUnavailable(str(exc)) from exc
    if r.status_code == 404:
        return Decimal("0")
    if r.status_code >= 500:
        raise LedgerUnavailable(f"ledger-service respondio {r.status_code}")
    r.raise_for_status()
    return Decimal(str(r.json()["saldo_actual"]))


def cobrar_compra(referencia: str, id_cuenta: uuid.UUID, monto: Decimal) -> None:
    """Debita la cuenta del cliente y acredita la cuenta puente (partida doble)."""
    payload = {
        "tipo_transaccion": "compra_tarjeta",
        "referencia": referencia,
        "movimientos": [
            {"id_cuenta": str(id_cuenta), "tipo_movimiento": "debito", "monto": str(monto)},
            {"id_cuenta": str(CUENTA_PUENTE_EXTERNA), "tipo_movimiento": "credito", "monto": str(monto)},
        ],
    }
    try:
        r = httpx.post(f"{settings.ledger_service_url}/ledger/entries", json=payload, timeout=settings.ledger_timeout_seconds)
    except httpx.RequestError as exc:
        raise LedgerUnavailable(str(exc)) from exc
    if r.status_code >= 500:
        raise LedgerUnavailable(f"ledger-service respondio {r.status_code}")
    if r.status_code >= 400:
        raise LedgerRejected(r.status_code, r.json().get("detail", "ledger-service rechazo la operacion"))
