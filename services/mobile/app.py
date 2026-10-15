"""mobile-app — nuevo consumidor (evento 3). PWA de consulta de afiliados (puerto 8093).

- Solo habla HTTP con el gateway (GATEWAY_URL) usando MOBILE_TOKEN: sin acceso a la base
  y sin permisos de escritura (el gateway responde 403 a cualquier POST de este token).
- El token se queda en el servidor: el navegador del teléfono nunca lo ve.
- Solo reenvía 3 consultas GET: afiliado, beneficiarios y empresa.
"""

import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8082").rstrip("/")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ROUTES = [
    (re.compile(r"^/api/members/(\d{3,15})$"), "/api/v1/members/{0}"),
    (re.compile(r"^/api/members/(\d{3,15})/beneficiaries$"), "/api/v1/members/{0}/beneficiaries"),
    (re.compile(r"^/api/companies/([A-Za-z0-9-]{1,10})$"), "/api/v1/companies/{0}"),
]
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".json": "application/manifest+json",
         ".svg": "image/svg+xml", ".css": "text/css"}


def gateway_get(path):
    req = urllib.request.Request(GATEWAY_URL + path,
                                 headers={"Authorization": "Bearer " + os.environ.get("MOBILE_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception:
        return 502, json.dumps({"message": "Gateway no disponible", "error_id": "MOBILE-502"}).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json; charset=utf-8", cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            return self._send(200, b'{"status": "UP"}')
        for pattern, target in ROUTES:
            match = pattern.match(path)
            if match:
                status, body = gateway_get(target.format(match.group(1)))
                return self._send(status, body)
        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        file_path = os.path.normpath(os.path.join(STATIC, name))
        if file_path.startswith(STATIC) and os.path.isfile(file_path):
            with open(file_path, "rb") as fh:
                return self._send(200, fh.read(), TYPES.get(os.path.splitext(name)[1], "application/octet-stream"),
                                  "no-cache")
        return self._send(404, b'{"message": "no encontrado", "error_id": "MOBILE-404"}')

    def do_POST(self):
        return self._send(405, b'{"message": "La app movil es de solo lectura", "error_id": "MOBILE-405"}')

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8093), Handler).serve_forever()
