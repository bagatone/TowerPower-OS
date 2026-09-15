#!/bin/bash
# Commissiona nel sistema reale la semina CILANTRO del 7/9/2026 (6 SET,
# 96g @ 16g/set), gia' verificata: LSE-000013 version=0, nessuna anomalia,
# collegamento semente-impiego -> PV-000003 gia' presente (creato 10/9).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== commissiona semina CILANTRO (LSE-000013, 96g = 16g x 6 set, 7/9/2026) ==="
OUT=$($RUN semina commission \
  --seed-lot 'LSE-000013' \
  --expected-seed-lot-version 0 \
  --protocol-version 'PV-000003' \
  --actual-seed-grams 96 \
  --physical-started-at '2026-09-07T08:00:00+01:00' \
  --origin ORDINE_CLIENTE \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale cilantro 6 set del 7/9, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-07-CILANTRO' \
  --idempotency-key 'semina-lse-000013-2026-09-07' \
  --confirm)
echo "$OUT"
