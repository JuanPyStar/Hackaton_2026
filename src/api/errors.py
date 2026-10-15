"""Formato único de error: {"message", "error_id"} (+ "code" en 503). Sin trazas ni SQL."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from domain.errors import DomainError, LegacyUnavailable

log = logging.getLogger("gateway")


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def new_error_id() -> str:
    return "ERR-" + uuid.uuid4().hex[:12].upper()


def error_response(request: Request, status_code: int, message: str, code: str = None) -> JSONResponse:
    error_id = new_error_id()
    request.state.error_id = error_id
    body = {"message": message, "error_id": error_id}
    if code:
        body["code"] = code
    headers = {"Retry-After": "5"} if status_code == 503 else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def install(app: FastAPI):
    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError):
        return error_response(request, exc.status_code, exc.message)

    @app.exception_handler(LegacyUnavailable)
    async def _legacy(request: Request, exc: LegacyUnavailable):
        return error_response(request, 503, exc.message, code="LEGACY_UNAVAILABLE")

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError):
        return error_response(request, exc.status_code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = sorted({str(e.get("loc", ["?"])[-1]) for e in exc.errors()})
        return error_response(request, 400, "Solicitud inválida; revise los campos: " + ", ".join(fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        message = {404: "Ruta no encontrada", 405: "Método no permitido"}.get(exc.status_code, "Error en la solicitud")
        return error_response(request, exc.status_code, message)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        response = error_response(request, 500, "Error interno del gateway")
        log.error("error_id=%s %s", request.state.error_id, exc.__class__.__name__)
        return response
