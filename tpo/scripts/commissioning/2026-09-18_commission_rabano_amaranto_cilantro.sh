#!/bin/bash
# Commissiona nel sistema reale tre semine del 17/9/2026 ore 21:00, origine
# RIPRISTINO_STOCK: Rabano 3 SET (LSE-000010, Golinucci Radish Vulcano,
# nuovo collegamento semente->protocollo PV-000002), Amaranto 1 SET
# (LSE-000012, PV-000007, gia' collegato), Cilantro 4 SET (LSE-000013,
# PV-000003, gia' collegato). Grammi/set dai protocolli reali verificati
# il 18/9: RAB 14g/set, AMA 10g/set, CIL 14g/set.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 1/4: collega semente Golinucci/Radish Vulcano al protocollo PV-000002 (Rabano) ==="
$RUN semente-impiego commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Radish Vulcano' \
  --protocol-version 'PV-000002' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale rabano (lotto Golinucci, non quello Hyfarm gia collegato)' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-18-RABANO-GOLINUCCI' \
  --idempotency-key 'semente-impiego-golinucci-radish-vulcano-pv-000002' \
  --confirm

echo "=== 2/4: commissiona semina RABANO (LSE-000010, 42g = 14g x 3 set, 17/9/2026 ore 21:00) ==="
OUT_RAB=$($RUN semina commission \
  --seed-lot 'LSE-000010' \
  --expected-seed-lot-version 0 \
  --protocol-version 'PV-000002' \
  --actual-seed-grams 42 \
  --physical-started-at '2026-09-17T21:00:00+01:00' \
  --origin RIPRISTINO_STOCK \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale rabano 3 set del 17/9 ore 21, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-17-RABANO' \
  --idempotency-key 'semina-lse-000010-2026-09-17' \
  --confirm)
echo "$OUT_RAB"

echo "=== 3/4: commissiona semina AMARANTO (LSE-000012, 10g = 10g x 1 set, 17/9/2026 ore 21:00) ==="
OUT_AMA=$($RUN semina commission \
  --seed-lot 'LSE-000012' \
  --expected-seed-lot-version 1 \
  --protocol-version 'PV-000007' \
  --actual-seed-grams 10 \
  --physical-started-at '2026-09-17T21:00:00+01:00' \
  --origin RIPRISTINO_STOCK \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale amaranto 1 set del 17/9 ore 21, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-17-AMARANTO' \
  --idempotency-key 'semina-lse-000012-2026-09-17' \
  --confirm)
echo "$OUT_AMA"

echo "=== 4/4: commissiona semina CILANTRO (LSE-000013, 56g = 14g x 4 set, 17/9/2026 ore 21:00) ==="
OUT_CIL=$($RUN semina commission \
  --seed-lot 'LSE-000013' \
  --expected-seed-lot-version 1 \
  --protocol-version 'PV-000003' \
  --actual-seed-grams 56 \
  --physical-started-at '2026-09-17T21:00:00+01:00' \
  --origin RIPRISTINO_STOCK \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale cilantro 4 set del 17/9 ore 21, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-17-CILANTRO' \
  --idempotency-key 'semina-lse-000013-2026-09-17' \
  --confirm)
echo "$OUT_CIL"
