"""Cortacircuitos hacia el legacy.

CLOSED   -> las llamadas pasan.
OPEN     -> tras una falla de disponibilidad, se responde 503 al instante sin tocar
            la base durante OPEN_SECONDS (garantiza respuesta < 3 s).
HALF_OPEN-> pasado ese tiempo, deja pasar una llamada de prueba; si funciona, cierra.

Además cada llamada tiene un PLAZO MÁXIMO (CALL_TIMEOUT_SECONDS, 2 s por defecto): si la base
no contesta a tiempo (p. ej. Docker Desktop tarda ~4 s en rechazar la conexión a un contenedor
detenido) se responde 503 igual y el circuito se abre. Así el contrato "< 3 s" no depende del
sistema operativo. En escrituras es seguro: si la llamada tardía llegara a completarse, el
reintento desde la outbox es idempotente por requestId y no duplica.
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from domain.errors import LegacyUnavailable

OPEN_SECONDS = float(os.environ.get("BREAKER_OPEN_SECONDS", "5"))
CALL_TIMEOUT_SECONDS = float(os.environ.get("LEGACY_CALL_TIMEOUT_SECONDS", "2"))
_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="legacy-call")


def with_deadline(fn, *args, timeout: float = CALL_TIMEOUT_SECONDS, **kwargs):
    """Ejecuta fn con un plazo máximo; si se vence lanza LegacyUnavailable."""
    future = _executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        raise LegacyUnavailable() from exc


class CircuitBreaker:
    def __init__(self, open_seconds: float = OPEN_SECONDS):
        self.open_seconds = open_seconds
        self._opened_at = None
        self._trial_running = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "CLOSED"
            if time.monotonic() - self._opened_at >= self.open_seconds:
                return "HALF_OPEN"
            return "OPEN"

    def _allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at < self.open_seconds or self._trial_running:
                return False
            self._trial_running = True
            return True

    def record_success(self):
        with self._lock:
            self._opened_at = None
            self._trial_running = False

    def record_failure(self):
        with self._lock:
            self._opened_at = time.monotonic()
            self._trial_running = False

    def call(self, fn, *args, timeout: float = CALL_TIMEOUT_SECONDS, **kwargs):
        if not self._allow():
            raise LegacyUnavailable()
        try:
            result = with_deadline(fn, *args, timeout=timeout, **kwargs)
        except LegacyUnavailable:
            self.record_failure()
            raise
        except Exception:
            # Un error de negocio (404, 409...) prueba que el legacy sí responde.
            self.record_success()
            raise
        self.record_success()
        return result


breaker = CircuitBreaker()
