"""subsidios-app — registra retiros de afiliados (SÍ se puede modificar).

POST /retiros  {"documento": "...", "fecha": "YYYY-MM-DD", "motivo": "..."}  (puerto 8091)
Responde como siempre: 201 {"movimiento": N}.

Migración (Strangler Fig): el camino se decide en cada petición leyendo
config/migration-state.json (el mismo archivo que usa el gateway y que cambia rollback.sh):
  - affiliations = DUAL o MODERN -> el retiro va por el gateway (POST /api/v1/members/{doc}/retirements)
                                    con SUBSIDIOS_TOKEN y un requestId estable (sin duplicados en reintentos).
  - affiliations = LEGACY        -> camino de siempre: sp_registrar_retiro directo en la base.
Si el gateway no responde en absoluto (conexión rechazada), se usa el camino legacy para no
detener el negocio: el gateway nunca recibió la petición, así que no hay riesgo de duplicado.
"""

import hashlib
import json
import os
import socket
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8082").rstrip("/")
STATE_PATH = os.environ.get("MIGRATION_STATE_PATH", "/app/config/migration-state.json")


def connect():
    return psycopg2.connect(
        host=os.environ.get("LEGACY_DB_HOST", "legacy-db"),
        port=int(os.environ.get("LEGACY_DB_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "legacy"),
        user=os.environ.get("POSTGRES_USER", "legacy"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=2,
    )


def modo():
    """'gateway' si Afiliaciones está en DUAL/MODERN; 'legacy' en cualquier otro caso."""
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            estado = str(json.load(fh).get("domains", {}).get("affiliations", "LEGACY")).upper()
    except (OSError, ValueError, AttributeError):
        estado = "LEGACY"
    return "gateway" if estado in ("DUAL", "MODERN") else "legacy"


def registrar_retiro(documento, fecha, motivo):
    """Camino legacy original (se conserva para el rollback)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT sp_registrar_retiro(%s, %s, %s, %s)", (documento, fecha, motivo, "SUBSIDIOS"))
            movimiento = cur.fetchone()[0]
        conn.commit()
        return movimiento
    finally:
        conn.close()


class GatewayNoDisponible(Exception):
    pass


def registrar_por_gateway(documento, fecha, motivo, request_id):
    body = json.dumps({"requestId": request_id, "date": fecha, "reason": motivo}).encode("utf-8")
    req = urllib.request.Request(
        "{0}/api/v1/members/{1}/retirements".format(GATEWAY_URL, documento),
        data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.environ.get("SUBSIDIOS_TOKEN", "")},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            return exc.code, {}
    except urllib.error.URLError as exc:
        # Conexión rechazada o nombre inexistente: el gateway no recibió nada -> camino legacy.
        if isinstance(exc.reason, (ConnectionRefusedError, socket.gaierror)):
            raise GatewayNoDisponible() from exc
        return 504, {"message": "el gateway no respondió a tiempo; reintente con el mismo retiro"}
    except (TimeoutError, socket.timeout):
        return 504, {"message": "el gateway no respondió a tiempo; reintente con el mismo retiro"}


def request_id_para(data):
    """requestId estable: el mismo retiro reintentado produce el mismo id (incidente 2021-07)."""
    if data.get("requestId"):
        return str(data["requestId"])[:100]
    base = "{0}|{1}|{2}".format(data.get("documento"), data.get("fecha"), data.get("motivo", "RETIRO"))
    return "subsidios-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "UP", "modo": modo()})
        return self._send(404, {"error": "ruta no encontrada"})

    def do_POST(self):
        if self.path != "/retiros":
            return self._send(404, {"error": "ruta no encontrada"})
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            documento, fecha = data["documento"], data["fecha"]
        except (ValueError, KeyError):
            return self._send(400, {"error": "se esperan documento y fecha"})
        motivo = data.get("motivo", "RETIRO")

        if modo() == "gateway":
            try:
                status, body = registrar_por_gateway(documento, fecha, motivo, request_id_para(data))
            except GatewayNoDisponible:
                status, body = None, None
            if status in (200, 201):
                return self._send(201, {"movimiento": body.get("movementId")})
            if status == 202:
                return self._send(202, {"movimiento": None, "estado": "PENDIENTE"})
            if status == 404:
                return self._send(500, {"error": "AFI-404 afiliado {0} no existe".format(documento)})
            if status is not None:
                return self._send(500 if status >= 500 else status, {"error": body.get("message", "error en el gateway")})
            # status None: el gateway no está; se sigue con el camino legacy.

        try:
            movimiento = registrar_retiro(documento, fecha, motivo)
        except psycopg2.Error as exc:
            return self._send(500, {"error": str(exc).strip()})
        return self._send(201, {"movimiento": movimiento})

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()