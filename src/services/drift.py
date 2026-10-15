"""Comparador de deriva (shadow check) para el estado DUAL.

Toma una muestra de afiliados y compara lo que entrega el gateway (modelo canónico)
contra lo que ve una aplicación que sigue leyendo la base directamente (Educación).
Si 0 diferencias durante N días, el dominio puede avanzar de DUAL a MODERN: el
criterio del plan de migración se vuelve evidencia medible.
"""

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

from domain.errors import NotFound
from services.audit import mask

EDUCACION_URL = os.environ.get("EDUCACION_URL", "http://educacion-app:8090").rstrip("/")
_STATUS_ES = {"ACTIVE": "ACTIVO", "RETIRED": "RETIRADO", "SUSPENDED": "SUSPENDIDO"}
_lock = threading.Lock()
_last = {"checked": 0, "differences": 0, "unavailable": 0, "lastRun": None, "examples": []}


def _norm(value) -> str:
    return " ".join(str(value or "").upper().split())


def _legacy_view(document: str):
    try:
        with urllib.request.urlopen("{0}/afiliados/{1}".format(EDUCACION_URL, document), timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {} if exc.code == 404 else None
    except Exception:
        return None


def run(repository, sample: int = 20) -> dict:
    sample = max(1, min(int(sample), 100))
    checked = differences = unavailable = 0
    examples = []
    for document in repository.sample_documents(sample):
        legacy = _legacy_view(document)
        if legacy is None:
            unavailable += 1
            continue
        try:
            member = repository.get_member(document).to_dict()
        except NotFound:
            member = None
        checked += 1
        fields = []
        if member is None or not legacy:
            fields = ["existence"] if bool(member) != bool(legacy) else []
        else:
            if _norm(member["fullName"]) != _norm(legacy.get("nombre")):
                fields.append("fullName")
            if _STATUS_ES.get(member["status"]) != _norm(legacy.get("estado")):
                fields.append("status")
            if _norm((member.get("company") or {}).get("name")) != _norm(legacy.get("empresa")):
                fields.append("company")
        if fields:
            differences += 1
            if len(examples) < 5:
                examples.append({"document": mask(document), "fields": fields})
    result = {
        "comparedWith": "educacion-app",
        "checked": checked,
        "differences": differences,
        "unavailable": unavailable,
        "lastRun": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "examples": examples,
    }
    with _lock:
        _last.update(result)
    return result


def last() -> dict:
    with _lock:
        return dict(_last)
