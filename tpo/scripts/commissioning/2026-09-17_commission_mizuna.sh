#!/bin/bash
# Commissiona nel sistema reale la semina MIZUNA del 16/9/2026 (2 SET,
# 20g = 10g/set, grammi_seme_per_set dal protocollo gia' approvato PV-000004).
# Il collegamento semente->protocollo (semente_impieghi) non esisteva ancora
# per Mizuna (0 righe verificate il 17/9) -- va creato per primo, come gia'
# fatto per Afila il 15/9.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 1/2: collega semente Golinucci/Mizuna Red al protocollo PV-000004 ==="
$RUN semente-impiego commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Mizuna Red' \
  --protocol-version 'PV-000004' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale mizuna' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-17-MIZUNA' \
  --idempotency-key 'semente-impiego-golinucci-mizuna-red-pv-000004' \
  --confirm

echo "=== 2/2: commissiona semina MIZUNA (LSE-000001, 20g = 10g x 2 set, 16/9/2026 ore 9:00) ==="
OUT=$($RUN semina commission \
  --seed-lot 'LSE-000001' \
  --expected-seed-lot-version 1 \
  --protocol-version 'PV-000004' \
  --actual-seed-grams 20 \
  --physical-started-at '2026-09-16T09:00:00+01:00' \
  --origin RIPRISTINO_STOCK \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale mizuna 2 set del 16/9, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-16-MIZUNA' \
  --idempotency-key 'semina-lse-000001-2026-09-16' \
  --confirm)
echo "$OUT"
