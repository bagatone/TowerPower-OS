#!/bin/bash
# Commissiona nel sistema reale la semina HINOJO del 18/9/2026 ore 21:00
# (2 SET), con la grammatura seme rivista da 12g/set a 10g/set (Owner
# Decision 19/9/2026: risparmio, nessun impatto su qualita' del set) ->
# 20g totali. Passi:
#   0) rimuove l'anomalia informativa sul lotto LSE-000005 (autorizzato,
#      stesso genere di caso gia' visto su Mizuna);
#   1) crea la nuova versione del protocollo Hinojo (PV-000005 v1, 12g/set
#      -> nuova versione v2 PV-000008, 10g/set), chiudendo la v1. La nuova
#      versione vale SOLO da quando viene creata (19/9) in avanti: non si
#      applica retroattivamente alla semina fisica gia' avvenuta il 18/9,
#      che resta commissionata con la versione storicamente valida in
#      quella data (PV-000005, 12g/set);
#   2) collega semente Intersemillas/Hinojo alla NUOVA versione del
#      protocollo (mai collegata finora, 0 righe verificate il 19/9),
#      cosi' che le prossime semine Hinojo usino gia' i 10g/set;
#   3) commissiona la semina fisica del 18/9 usando la versione ANTICA
#      del protocollo (PV-000005) e i grammi storicamente corretti
#      (24g = 12g/set x 2 set). Il primo tentativo con la nuova versione
#      (PV-000008/20g) e' stato rifiutato dal sistema reale con
#      PROTOCOL_NOT_FOUND_OR_UNAVAILABLE, correttamente: la revisione non
#      e' retroattiva.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 0/3: rimuove anomalia informativa su LSE-000005 (autorizzato) ==="
python3 scripts/commissioning/2026-09-19_correggi_anomalia_hinojo.py

echo "=== 1/3: crea nuova versione protocollo Hinojo (12g/set -> 10g/set) ==="
REVISIONE_OUT=$(python3 scripts/commissioning/2026-09-19_revisiona_protocollo_hinojo.py)
echo "$REVISIONE_OUT"
NEW_PV=$(echo "$REVISIONE_OUT" | grep '^NUOVO_PROTOCOLLO_VERSIONE=' | cut -d= -f2)
if [ -z "$NEW_PV" ]; then
  echo "ERRORE: non ho trovato la nuova versione del protocollo nell'output sopra. Fermo qui." >&2
  exit 1
fi
echo "Nuova versione protocollo: $NEW_PV"

echo "=== 2/3: collega semente Intersemillas/Hinojo al protocollo $NEW_PV ==="
$RUN semente-impiego commission \
  --fornitore 'Intersemillas' \
  --referenza-commerciale 'Hinojo' \
  --protocol-version "$NEW_PV" \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale hinojo (nuova versione, 10g/set)' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-19-HINOJO' \
  --idempotency-key 'semente-impiego-intersemillas-hinojo' \
  --confirm

echo "=== 3/3: commissiona semina HINOJO (LSE-000005, 24g = 12g/set storici x 2 set, 18/9/2026 ore 21:00, protocollo PV-000005 storicamente valido in quella data) ==="
OUT=$($RUN semina commission \
  --seed-lot 'LSE-000005' \
  --expected-seed-lot-version 1 \
  --protocol-version 'PV-000005' \
  --actual-seed-grams 24 \
  --physical-started-at '2026-09-18T21:00:00+01:00' \
  --origin RIPRISTINO_STOCK \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale hinojo 2 set del 18/9 ore 21, commissionata con la grammatura storicamente valida in quella data (12g/set, PV-000005); la nuova grammatura 10g/set (PV-000008) vale dalle prossime semine' \
  --correlation-id 'SEMINA-2026-09-18-HINOJO' \
  --idempotency-key 'semina-lse-000005-2026-09-18' \
  --confirm)
echo "$OUT"
