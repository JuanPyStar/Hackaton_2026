"""Autenticación Bearer: un token por consumidor, leído de variables de entorno.

portal    -> lectura y escritura
subsidios -> lectura y escritura
mobile    -> solo lectura (un POST devuelve 403)
"""

import hmac
import os

from fastapi import Request

from api.errors import ApiError

CONSUMERS = {"portal": "PORTAL_TOKEN", "subsidios": "SUBSIDIOS_TOKEN", "mobile": "MOBILE_TOKEN"}
WRITERS = {"portal", "subsidios"}


def identify(authorization: str):
    """Devuelve el consumidor dueño del token, o None."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    presented = authorization[7:].strip().encode("utf-8")
    for consumer, env_name in CONSUMERS.items():
        expected = os.environ.get(env_name, "")
        if expected and hmac.compare_digest(presented, expected.encode("utf-8")):
            return consumer
    return None


def require_reader(request: Request) -> str:
    consumer = getattr(request.state, "consumer", None)
    if consumer not in CONSUMERS:
        raise ApiError(401, "Token ausente o inválido")
    return consumer


def require_writer(request: Request) -> str:
    consumer = require_reader(request)
    if consumer not in WRITERS:
        raise ApiError(403, "Este consumidor no tiene permisos de escritura")
    return consumer
