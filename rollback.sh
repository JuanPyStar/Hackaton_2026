#!/usr/bin/env bash
# Rollback de un dominio migrado: lo devuelve a LEGACY.
#   ./rollback.sh affiliations
#
# Qué hace (en segundos, sin reiniciar contenedores):
#   1. Escribe LEGACY para el dominio en config/migration-state.json (escritura atómica).
#   2. El gateway y subsidios-app leen ese archivo en cada petición: desde ese momento
#      Subsidios vuelve a registrar retiros con el procedimiento legacy de siempre.
#   3. Verifica GET /api/v1/migration/status y el modo de subsidios-app, e imprime antes/después.
# Es idempotente: ejecutarlo dos veces deja el mismo estado. Para volver a avanzar:
#   ./scripts/set-migration-state.sh affiliations DUAL
set -euo pipefail
cd "$(dirname "$0")"

DOMAIN="${1:-}"
STATE_FILE="config/migration-state.json"
VALID_DOMAINS="affiliations contributions reports"

if [ -z "$DOMAIN" ] || ! echo " $VALID_DOMAINS " | grep -q " $DOMAIN "; then
  echo "Uso: ./rollback.sh <dominio>   (dominios: $VALID_DOMAINS)" >&2
  exit 2
fi

# Lee una variable de .env (o .env.example) tolerando BOM y finales de línea de Windows.
env_value() {
  local name="$1" file
  for file in .env .env.example; do
    [ -f "$file" ] || continue
    local value
    value="$(sed -e 's/^\xEF\xBB\xBF//' -e 's/\r$//' "$file" | grep -E "^${name}=" | tail -1 | cut -d= -f2- || true)"
    if [ -n "$value" ]; then printf '%s' "$value"; return; fi
  done
}

GATEWAY="http://localhost:${GATEWAY_PORT:-8082}"
SUBSIDIOS="http://localhost:$(env_value SUBSIDIOS_PORT || true)"
[ "$SUBSIDIOS" = "http://localhost:" ] && SUBSIDIOS="http://localhost:8091"
TOKEN="$(env_value PORTAL_TOKEN)"

mkdir -p config
BEFORE="$(python3 - "$STATE_FILE" "$DOMAIN" <<'PY'
import json, sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get("domains", {}).get(sys.argv[2], "LEGACY"))
except Exception:
    print("LEGACY")
PY
)"
echo "[rollback] dominio=$DOMAIN  estado antes=$BEFORE"

python3 - "$STATE_FILE" "$DOMAIN" <<'PY'
import json, os, sys
path, domain = sys.argv[1], sys.argv[2]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    data = {}
domains = data.setdefault("domains", {})
domains.setdefault("affiliations", "DUAL")
domains[domain] = "LEGACY"
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
os.replace(tmp, path)
PY
echo "[rollback] $STATE_FILE -> $DOMAIN=LEGACY"

# Verificación (no bloqueante: el archivo es la fuente de verdad y se lee en cada petición).
STATUS="$(curl -s -m 5 -H "Authorization: Bearer $TOKEN" "$GATEWAY/api/v1/migration/status" || true)"
if echo "$STATUS" | grep -q "\"$DOMAIN\": *\"LEGACY\""; then
  echo "[rollback] gateway confirma: $STATUS"
else
  echo "[rollback] aviso: no se pudo confirmar con el gateway (respuesta: ${STATUS:-sin respuesta})"
fi
if [ "$DOMAIN" = "affiliations" ]; then
  MODE="$(curl -s -m 5 "$SUBSIDIOS/health" || true)"
  echo "[rollback] subsidios-app: ${MODE:-sin respuesta} (esperado modo legacy -> sp_registrar_retiro)"
fi
echo "[rollback] listo: $DOMAIN en LEGACY"
exit 0
