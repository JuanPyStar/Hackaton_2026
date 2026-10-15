"""Las 6 rutas del contrato v1 (+ deriva). Solo hablan el modelo canónico."""

import datetime as dt
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from adapter.legacy_repository import repository
from api.auth import require_reader, require_writer
from api.errors import ApiError
from domain.errors import LegacyUnavailable
from domain.models import RetirementCommand
from services import drift, migration
from services.outbox import outbox
from services.breaker import breaker, with_deadline

router = APIRouter()
_DOCUMENT = re.compile(r"^\d{3,15}$")
_COMPANY = re.compile(r"^[A-Za-z0-9-]{1,10}$")


class RetirementRequest(BaseModel):
    requestId: str = Field(min_length=1, max_length=100)
    date: dt.date
    reason: str = Field(min_length=1, max_length=200)


def _document(value: str) -> str:
    value = value.strip()
    if not _DOCUMENT.match(value):
        raise ApiError(400, "El documento debe ser numérico (3 a 15 dígitos)")
    return value


@router.get("/health")
def health():
    # Siempre 200: el gateway está arriba aunque el legacy no.
    if breaker.state == "OPEN":
        legacy_up = False
    else:
        try:
            legacy_up = with_deadline(repository.ping, timeout=1.5)
        except LegacyUnavailable:
            legacy_up = False
        if legacy_up:
            breaker.record_success()
        else:
            breaker.record_failure()
    return {"status": "UP", "legacy": "UP" if legacy_up else "DOWN", "pendingRetirements": outbox.size()}


@router.get("/api/v1/members/{document}")
def get_member(document: str, consumer: str = Depends(require_reader)):
    return breaker.call(repository.get_member, _document(document)).to_dict()


@router.get("/api/v1/members/{document}/beneficiaries")
def get_beneficiaries(document: str, consumer: str = Depends(require_reader)):
    return [b.to_dict() for b in breaker.call(repository.get_beneficiaries, _document(document))]


@router.get("/api/v1/companies/{company_id}")
def get_company(company_id: str, consumer: str = Depends(require_reader)):
    if not _COMPANY.match(company_id):
        raise ApiError(400, "Identificador de empresa inválido")
    return breaker.call(repository.get_company, company_id).to_dict()


@router.post("/api/v1/members/{document}/retirements")
async def register_retirement(document: str, request: Request, consumer: str = Depends(require_writer)):
    # El cuerpo se valida DESPUÉS de la autorización: un consumidor sin permiso recibe 403 siempre.
    try:
        payload = RetirementRequest.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise ApiError(400, "Cuerpo inválido: se esperan requestId, date (AAAA-MM-DD) y reason")
    request.state.request_id = payload.requestId
    cmd = RetirementCommand(request_id=payload.requestId, document=_document(document),
                            date=payload.date, reason=payload.reason, consumer=consumer)
    try:
        result = await run_in_threadpool(breaker.call, repository.register_retirement, cmd)
    except LegacyUnavailable:
        # Legacy caído: el retiro NO se pierde. Queda en la outbox durable y el worker lo
        # aplica una sola vez (idempotencia por requestId) cuando la base vuelva.
        item = await run_in_threadpool(outbox.add, cmd)
        return JSONResponse(status_code=202, content={
            "requestId": item["request_id"], "document": item["document"], "date": item["date"],
            "reason": item["reason"], "status": "PENDING",
            "message": "Legacy no disponible: el retiro quedó en cola y se aplicará al recuperarse",
        })
    return JSONResponse(status_code=200 if result.replayed else 201, content=result.to_dict())


@router.get("/api/v1/migration/status")
def migration_status(consumer: str = Depends(require_reader)):
    return {"domains": migration.domains()}


@router.get("/api/v1/migration/drift")
def migration_drift(sample: int = 20, consumer: str = Depends(require_reader)):
    """Shadow check DUAL: gateway vs. lectura directa de Educación. Criterio para avanzar a MODERN."""
    if sample <= 0:
        return drift.last()
    return breaker.call(drift.run, repository, sample, timeout=30)
