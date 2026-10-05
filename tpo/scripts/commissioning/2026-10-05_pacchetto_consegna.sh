#!/bin/bash
# Prepara la cartella (e lo zip) da inviare per mail per una consegna: bolla PDF.
# Le etichette di tracciabilita' (una per SET) si includono SOLO con --etichette
# (Matteo le chiede caso per caso). Sola lettura dal DB.
# Uso: scripts/commissioning/2026-10-05_pacchetto_consegna.sh CON-000004 [--etichette] [cartella-destinazione]
set -euo pipefail
CON="${1:?uso: $0 CON-000000 [--etichette] [cartella-destinazione]}"
shift
ETICHETTE=0
if [ "${1:-}" = "--etichette" ]; then ETICHETTE=1; shift; fi
DEST="${1:-$HOME/Desktop}"
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
OUT="$DEST/${CON}_consegna"
mkdir -p "$OUT"
"$HERE/run_tpo.sh" bolla genera --consegna "$CON" --output-dir "$OUT" --sovrascrivi
if [ "$ETICHETTE" = "1" ]; then
    "$HERE/run_tpo.sh" etichetta genera --consegna "$CON" --output-dir "$OUT" --sovrascrivi
fi
( cd "$DEST" && rm -f "${CON}_consegna.zip" && zip -qr "${CON}_consegna.zip" "${CON}_consegna" )
echo "CARTELLA: $OUT"
echo "ZIP_PER_MAIL: $DEST/${CON}_consegna.zip"
ls -l "$OUT"
