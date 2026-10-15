"""Estado de migración por dominio (Strangler Fig).

Se lee de config/migration-state.json en cada petición, así rollback.sh puede cambiarlo
sin reiniciar el gateway. Si el archivo falta o está dañado, se usa el valor por defecto.
"""

import json
import os

STATE_PATH = os.environ.get("MIGRATION_STATE_PATH", "/app/config/migration-state.json")
VALID = {"LEGACY", "DUAL", "MODERN"}
DEFAULT = {"affiliations": "DUAL", "contributions": "LEGACY", "reports": "LEGACY"}


def domains() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as fh:
            data = json.load(fh).get("domains", {})
        clean = {str(k): str(v).upper() for k, v in data.items() if str(v).upper() in VALID}
        return clean or dict(DEFAULT)
    except (OSError, ValueError, AttributeError):
        return dict(DEFAULT)
