"""Cliente HTTP hacia account-service, identity-service y ledger-service para card-service."""
import logging
import uuid
import httpx
from .config import settings

logger = logging.getLogger(__name__)

LEDGER_URL = "http://ledger-service:8003"
CUENTA_PUENTE_EXTERNA = "00000000-0000-0000-0000-000000000001"
BONO_BIENVENIDA_COP = "2000000"

IDENTITY_URL = "http://identity-service:8001"


def get_account(id_cuenta: str) -> dict | None:
    """Consulta síncronamente account-service para obtener datos de la cuenta."""
    try:
        url = f"{settings.account_service_url}/accounts/{id_cuenta}"
        r = httpx.get(url, timeout=settings.account_timeout_seconds)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("No se pudo consultar account-service: %s", exc)
        return None


def get_user(id_usuario: str) -> dict | None:
    """Consulta síncronamente identity-service para validar el estado del usuario."""
    try:
        url = f"{IDENTITY_URL}/users/{id_usuario}"
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("No se pudo consultar identity-service: %s", exc)
        return None


def registrar_bono_bienvenida(id_cuenta: str) -> dict | None:
    """Registra un crédito de bienvenida de 2M COP en el ledger-service.

    Usa doble partida: crédito a la cuenta del cliente, débito a la cuenta puente.
    Esto además crea la cuenta_contable en el ledger si no existía,
    resolviendo el problema de 'Saldo no disponible'.
    """
    try:
        ref = f"BONO-BIENVENIDA-{uuid.uuid4().hex[:12]}"
        payload = {
            "tipo_transaccion": "bono_bienvenida",
            "referencia": ref,
            "movimientos": [
                {"id_cuenta": id_cuenta, "tipo_movimiento": "credito", "monto": BONO_BIENVENIDA_COP},
                {"id_cuenta": CUENTA_PUENTE_EXTERNA, "tipo_movimiento": "debito", "monto": BONO_BIENVENIDA_COP},
            ],
        }
        r = httpx.post(f"{LEDGER_URL}/ledger/entries", json=payload, timeout=10.0)
        r.raise_for_status()
        logger.info("Bono de bienvenida registrado para cuenta %s: %s", id_cuenta, ref)
        return r.json()
    except Exception as exc:
        logger.error("Error al registrar bono de bienvenida para cuenta %s: %s", id_cuenta, exc)
        return None
