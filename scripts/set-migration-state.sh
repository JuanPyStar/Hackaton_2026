#!/usr/bin/env bash
# Cambia el estado de migración de un dominio (avance controlado del Strangler Fig).
#   ./scripts/set-migration-state.sh affiliations DUAL
#   ./scripts/set-migration-state.sh affiliations MODERN
# Para volver atrás use ./rollback.sh <dominio>.
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN="${1:-}"
STATE="$(echo "${2:-}" | tr '[:lower:]' '[:upper:]')"
case "$STATE" in LEGACY|DUAL|MODERN) ;; *) echo "Uso: $0 <dominio> LEGACY|DUAL|MODERN" >&2; exit 2;; esac
[ -n "$DOMAIN" ] || { echo "Uso: $0 <dominio> LEGACY|DUAL|MODERN" >&2; exit 2; }

mkdir -p config
python3 - config/migration-state.json "$DOMAIN" "$STATE" <<'PY'
import json, os, sys
path, domain, state = sys.argv[1:4]
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    data = {}
data.setdefault("domains", {})[domain] = state
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
os.replace(tmp, path)
print("config/migration-state.json ->", json.dumps(data["domains"]))
PY
