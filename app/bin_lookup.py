"""Enriquecimiento real de tarjetas con APIs publicas de BIN (sin credenciales).

Proveedores en orden: data.handyapi.com y lookup.binlist.net. Se consulta el
BIN de 6 digitos al emitir la tarjeta; si ninguno responde (p. ej. 429) la
emision continua sin bloquearse (fail-open) y se registra en el log.
"""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

HANDYAPI_URL = "https://data.handyapi.com/bin/{bin}"
BINLIST_URL = "https://lookup.binlist.net/{bin}"
CACHE_TTL = 12 * 3600.0
_cache: dict[str, tuple[float, dict | None]] = {}


def _desde_handyapi(prefijo: str) -> dict | None:
    r = httpx.get(HANDYAPI_URL.format(bin=prefijo), timeout=6.0)
    if r.status_code != 200:
        return None
    datos = r.json()
    if datos.get("Status") != "SUCCESS":
        return None
    pais = datos.get("Country") or {}
    return {
        "marca": (datos.get("Scheme") or "").lower() or None,
        "tipo": (datos.get("Type") or "").lower() or None,
        "banco": datos.get("Issuer"),
        "pais": pais.get("Name"),
        "pais_codigo": pais.get("A2"),
        "proveedor": "handyapi",
    }


def _desde_binlist(prefijo: str) -> dict | None:
    r = httpx.get(
        BINLIST_URL.format(bin=prefijo),
        headers={"Accept-Version": "3", "User-Agent": "BankLite-Card-Service"},
        timeout=6.0,
    )
    if r.status_code != 200:
        return None
    datos = r.json()
    if not datos.get("scheme"):
        return None
    pais = datos.get("country") or {}
    return {
        "marca": datos.get("scheme"),
        "tipo": datos.get("type"),
        "banco": (datos.get("bank") or {}).get("name"),
        "pais": pais.get("name"),
        "pais_codigo": pais.get("alpha2"),
        "proveedor": "binlist",
    }


def consultar_bin(numero_tarjeta: str) -> dict | None:
    """Devuelve {'marca','tipo','banco','pais','pais_codigo'} del BIN o None."""
    prefijo = "".join(c for c in (numero_tarjeta or "") if c.isdigit())[:6]
    if len(prefijo) < 6:
        return None

    ahora = time.time()
    cacheado = _cache.get(prefijo)
    if cacheado and (ahora - cacheado[0]) < CACHE_TTL:
        return cacheado[1]

    for proveedor in (_desde_handyapi, _desde_binlist):
        try:
            info = proveedor(prefijo)
            if info:
                _cache[prefijo] = (ahora, info)
                logger.info(
                    "[BIN] %s -> %s / %s / %s (%s)",
                    prefijo, info["marca"], info["banco"], info["pais"], info["proveedor"],
                )
                return info
        except Exception as exc:  # noqa: BLE001
            logger.warning("[BIN] Fallo con %s para %s: %s", proveedor.__name__, prefijo, exc)

    logger.info("[BIN] %s sin datos en los proveedores gratuitos", prefijo)
    return None
