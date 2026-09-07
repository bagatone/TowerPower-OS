#!/bin/bash
# Applica le migrazioni Alembic fino a 'head' sul database configurato in
# runtime/secrets/operational-scheduler.env (Secret Boundary), senza mai
# stampare le credenziali. Sola lettura/scrittura DI SCHEMA: nessun dato
# applicativo viene toccato, solo DDL Alembic. Uso:
#   scripts/commissioning/migrate_to_head.sh
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)" || exit 1
PYTHON="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "OPERATION_RUNTIME_UNAVAILABLE: virtualenv del progetto non trovato in $PYTHON" >&2
    exit 1
fi

cd "$ROOT"
"$PYTHON" - <<'PYEOF'
import sys
sys.path.insert(0, "scripts/commissioning")
from secret_boundary import load_postgresql_parameters, SecretBoundaryError

from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings
from src.tpo_core.infrastructure.postgresql.alembic import upgrade

try:
    parameters = load_postgresql_parameters()
except SecretBoundaryError as exc:
    print(f"OPERATION_INPUT_INVALID: {exc}", file=sys.stderr)
    raise SystemExit(1)

settings = PostgreSQLSettings.from_mapping({
    "host": parameters["host"],
    "port": int(parameters["port"]),
    "database": parameters["dbname"],
    "user": parameters["user"],
    "password": parameters["password"],
    "sslmode": parameters["sslmode"],
    "connect_timeout_seconds": int(parameters["connect_timeout"]),
})

print("Applico le migrazioni Alembic fino a 'head'...")
upgrade(settings, "head")
print("Migrazioni applicate con successo.")
PYEOF
