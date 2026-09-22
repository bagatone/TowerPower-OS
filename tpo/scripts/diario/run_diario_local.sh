#!/bin/bash
# Avvia il diario in locale per un test manuale prima del deploy su Render,
# stesso schema di scripts/commissioning/run_tpo.sh e scripts/web/run_web.sh:
# credenziali database lette da runtime/secrets/ (Secret Boundary), mai
# stampate. In più servono qui ANTHROPIC_API_KEY e DIARIO_PASSWORD, che
# NON sono nel Secret Boundary esistente -- vanno esportate a mano prima di
# lanciare questo script (mai committarle in nessun file):
#
#   export ANTHROPIC_API_KEY=sk-ant-...
#   export DIARIO_PASSWORD=una-password-a-scelta
#   scripts/diario/run_diario_local.sh
#
# Uso: scripts/diario/run_diario_local.sh [--host 0.0.0.0]   (di default
# solo 127.0.0.1, cioè solo questo Mac -- per provarlo anche da telefono
# sulla stessa Wi-Fi usa --host 0.0.0.0, MAI su una rete non fidata: qui
# non gira ancora dietro alla password se non l'hai esportata).
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)" || exit 1
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "OPERATION_RUNTIME_UNAVAILABLE: virtualenv del progetto non trovato in $PYTHON" >&2
    exit 1
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "OPERATION_INPUT_INVALID: esporta ANTHROPIC_API_KEY prima di lanciare questo script." >&2
    exit 1
fi
if [ -z "${DIARIO_PASSWORD:-}" ]; then
    echo "OPERATION_INPUT_INVALID: esporta DIARIO_PASSWORD prima di lanciare questo script." >&2
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
exec "$PYTHON" -m uvicorn src.tpo_core.diario_web.app:app --host 127.0.0.1 --port 8766 "$@"
