"""Outbox durable de retiros aceptados mientras el legacy está caído.

- POST /retirements con el legacy caído -> el retiro se guarda aquí y se responde 202.
- El archivo vive en un volumen (/app/data/outbox.json): sobrevive a reinicios del gateway.
- Un hilo de fondo (worker) reintenta cada pocos segundos. Cada reintento pasa por el
  registro idempotente por requestId, así que aunque se repita nunca se duplica.
- Si el afiliado no existe, el retiro va a /app/data/outbox-dead.jsonl (no se reintenta).
"""

import json
import logging
import os
import threading
import time
from datetime import date

from domain.errors import LegacyUnavailable, NotFound, DomainError
from domain.models import RetirementCommand

log = logging.getLogger("gateway.outbox")
DATA_DIR = os.environ.get("OUTBOX_DIR", "/app/data")
OUTBOX_PATH = os.path.join(DATA_DIR, "outbox.json")
DEAD_PATH = os.path.join(DATA_DIR, "outbox-dead.jsonl")
INTERVAL_S = float(os.environ.get("OUTBOX_INTERVAL_SECONDS", "2"))


class Outbox:
    def __init__(self, path: str = OUTBOX_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._items = {}
        self._load()

    # ------------------------------------------------------------------ persistencia
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                self._items = {item["request_id"]: item for item in json.load(fh)}
        except (OSError, ValueError, KeyError, TypeError):
            self._items = {}

    def _flush(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(list(self._items.values()), fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)   # escritura atómica: nunca queda un archivo a medias

    # ------------------------------------------------------------------ API
    def add(self, cmd: RetirementCommand) -> dict:
        with self._lock:
            existing = self._items.get(cmd.request_id)
            if existing:
                return existing
            item = {
                "request_id": cmd.request_id,
                "document": cmd.document,
                "date": cmd.date.isoformat(),
                "reason": cmd.reason,
                "consumer": cmd.consumer,
                "accepted_at": time.time(),
                "attempts": 0,
            }
            self._items[cmd.request_id] = item
            self._flush()
            return item

    def get(self, request_id: str):
        with self._lock:
            return self._items.get(request_id)

    def pending(self) -> list:
        with self._lock:
            return sorted(self._items.values(), key=lambda i: i["accepted_at"])

    def size(self) -> int:
        with self._lock:
            return len(self._items)

    def _remove(self, request_id: str):
        with self._lock:
            self._items.pop(request_id, None)
            self._flush()

    def _bump(self, request_id: str):
        with self._lock:
            if request_id in self._items:
                self._items[request_id]["attempts"] += 1
                self._flush()

    def _dead_letter(self, item: dict, reason: str):
        os.makedirs(os.path.dirname(DEAD_PATH), exist_ok=True)
        with open(DEAD_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(item, failed_reason=reason, failed_at=time.time())) + "\n")
        self._remove(item["request_id"])

    # ------------------------------------------------------------------ worker
    def drain(self, register, is_up) -> int:
        """Aplica los pendientes en orden de llegada. Devuelve cuántos se aplicaron."""
        items = self.pending()
        if not items or not is_up():
            return 0
        applied = 0
        for item in items:
            cmd = RetirementCommand(request_id=item["request_id"], document=item["document"],
                                    date=date.fromisoformat(item["date"]), reason=item["reason"],
                                    consumer=item["consumer"])
            try:
                register(cmd)
            except LegacyUnavailable:
                self._bump(item["request_id"])
                break                      # se volvió a caer: esperar al siguiente ciclo
            except NotFound:
                self._dead_letter(item, "member_not_found")
                continue
            except DomainError as exc:
                self._dead_letter(item, exc.__class__.__name__)
                continue
            self._remove(item["request_id"])
            applied += 1
            log.info("retiro pendiente aplicado request_id=%s", item["request_id"][:8])
        return applied

    def start_worker(self, register, is_up):
        def loop():
            while True:
                try:
                    self.drain(register, is_up)
                except Exception as exc:     # el worker nunca muere
                    log.error("outbox worker: %s", exc.__class__.__name__)
                time.sleep(INTERVAL_S)

        thread = threading.Thread(target=loop, name="outbox-worker", daemon=True)
        thread.start()
        return thread


outbox = Outbox()
