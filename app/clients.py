"""Cliente HTTP hacia account-service, identity-service y ledger-service para card-service."""
import logging
import httpx
from .config import settings

logger = logging.getLogger(__name__)


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
        url = f"{settings.identity_service_url}/users/{id_usuario}"
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("No se pudo consultar identity-service: %s", exc)
        return None
