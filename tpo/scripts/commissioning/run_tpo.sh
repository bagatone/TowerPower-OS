#!/bin/bash
# Esegue un comando `tpo` reale contro il database configurato in
# runtime/secrets/operational-scheduler.env (Secret Boundary), senza mai
# stampare le credenziali. Uso:
#   scripts/commissioning/run_tpo.sh <sottocomando tpo...>
# Esempio:
#   scripts/commissioning/run_tpo.sh semente commission --fornitore ... --confirm
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
exec "$PYTHON" -m src.tpo_core.cli.main "$@"
