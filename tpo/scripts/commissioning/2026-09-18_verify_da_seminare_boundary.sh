#!/bin/bash
# Verifica mirata del decimo boundary di lettura "Da seminare"
# (pianificazione_semina_lettura) prima della suite completa.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
PYTHON=".venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "OPERATION_RUNTIME_UNAVAILABLE: virtualenv del progetto non trovato in $PYTHON" >&2
    exit 1
fi

echo "1/3 -- test applicativi (nessun Postgres)"
"$PYTHON" -m pytest tests/application/test_pianificazione_semina_lettura.py -v

echo "2/3 -- test di integrazione Postgres reale (isolato)"
"$PYTHON" -m pytest tests/integration/postgresql/test_pianificazione_semina_lettura.py -v

echo "3/3 -- test web adapter (tutti i 10 boundary, reader finti)"
"$PYTHON" -m pytest tests/web -v
