"""Gateway de Afiliaciones — Legacy Escape (puerto 8082).

Portal / Subsidios / Móvil -> Gateway API -> Modelo canónico -> Adapter -> Legacy DB
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from api import errors
from api.auth import identify
from adapter.legacy_repository import repository
from api.routes import router
from domain.errors import DomainError
from services import audit
from services.breaker import breaker
from services.outbox import outbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

log = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        repository.warm_up()
    except DomainError:
        log.warning("legacy no disponible al arrancar; se reintentará en cada petición")

    def is_up() -> bool:
        up = repository.ping()
        if up:
            breaker.record_success()
        return up

    outbox.start_worker(repository.register_retirement, is_up)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Legacy Escape Gateway",
    version="1.0.0",
    description="Capa de transición del dominio Afiliaciones sobre el sistema legacy.",
)
errors.install(app)
app.include_router(router)


def _openapi_with_bearer():
    """Agrega el esquema Bearer a /docs para que aparezca el botón Authorize."""
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {"bearerAuth": {"type": "http", "scheme": "bearer"}}
    for path, methods in schema.get("paths", {}).items():
        if path != "/health":
            for operation in methods.values():
                operation["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_with_bearer


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    started = time.perf_counter()
    request.state.consumer = identify(request.headers.get("authorization", ""))
    request.state.error_id = None
    request.state.request_id = None
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # El healthcheck interno de Docker (cada 5 s) no es una petición de un consumidor:
        # no se audita para no tapar las líneas reales del log.
        internal = request.headers.get("x-internal-healthcheck") == "1" and request.url.path == "/health"
        if not internal:
            audit.write(
                consumer=request.state.consumer or "anonymous",
                method=request.method,
                endpoint=request.url.path,
                status=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                error_id=request.state.error_id,
                request_id=request.state.request_id,
            )
