#!/bin/bash
# Avvia il web adapter (OPERATIONAL_WEB_ADAPTER Fase 1) contro il database
# configurato in runtime/secrets/operational-scheduler.env (Secret
# Boundary), senza mai stampare le credenziali -- stesso schema di
# scripts/commissioning/run_tpo.sh, solo che qui si esegue uvicorn invece
# della CLI.
#
# Uso:
#   scripts/web/run_web.sh                 # 127.0.0.1:8765, solo questo Mac
#   scripts/web/run_web.sh --host 0.0.0.0   # raggiungibile da altri
#                                            # dispositivi sulla stessa LAN
#                                            # (mai su Internet -- Owner
#                                            # Decision D4)
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)" || exit 1
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "OPERATION_RUNTIME_UNAVAILABLE: virtualenv del progetto non trovato in $PYTHON" >&2
    exit 1
fi

ENV_ASSIGNMENTS="$(cd "$ROOT" && "$PYTHON" - <<'PYEOF'
import sys
sys.path.insert(0, "scripts/commissioning")
from secret_boundary import load_postgresql_parameters, SecretBoundaryError

try:
    parameters = load_postgresql_parameters()
except SecretBoundaryError as exc:
    print(f"OPERATION_INPUT_INVALID: {exc}", file=sys.stderr)
    raise SystemExit(1)

mapping = {
    "TPO_DATABASE_HOST": parameters["host"],
    "TPO_DATABASE_PORT": parameters["port"],
    "TPO_DATABASE_NAME": parameters["dbname"],
    "TPO_DATABASE_USER": parameters["user"],
    "TPO_DATABASE_PASSWORD": parameters["password"],
    "TPO_DATABASE_SSLMODE": parameters["sslmode"],
    "TPO_DATABASE_CONNECT_TIMEOUT": parameters["connect_timeout"],
}
for key, value in mapping.items():
    print(f"export {key}={value!r}")
PYEOF
)"

eval "$ENV_ASSIGNMENTS"

cd "$ROOT"
exec "$PYTHON" -m uvicorn src.tpo_core.web.asgi:app --host 127.0.0.1 --port 8765 "$@"
