"""Auditoría: una línea JSON por petición en logs/audit.log.

Campos obligatorios: timestamp, consumer, endpoint, status, latency_ms.
Extras: method, error_id (correlaciona con la respuesta de error), request_id.
Todo documento (secuencia de 5+ dígitos) se enmascara: solo quedan 4 dígitos visibles.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone

AUDIT_PATH = os.environ.get("AUDIT_LOG_PATH", "/app/logs/audit.log")
_DIGITS = re.compile(r"\d{5,}")
_lock = threading.Lock()


def mask(text: str) -> str:
    """'/api/v1/members/1019282447' -> '/api/v1/members/******2447'."""
    if not text:
        return text
    return _DIGITS.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], text)


def write(consumer: str, method: str, endpoint: str, status: int, latency_ms: float,
          error_id: str = None, request_id: str = None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "consumer": consumer,
        "endpoint": mask(endpoint),
        "method": method,
        "status": status,
        "latency_ms": round(latency_ms, 1),
    }
    if error_id:
        entry["error_id"] = error_id
    if request_id:
        entry["request_id"] = mask(request_id)
    line = json.dumps(entry, ensure_ascii=False)
    try:
        os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
        with _lock, open(AUDIT_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # la auditoría nunca tumba una petición
