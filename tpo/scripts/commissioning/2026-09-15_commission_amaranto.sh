#!/bin/bash
# Commissiona nel sistema reale la semina AMARANTO del 7/9/2026 (1 SET =
# 10g, confermato da Matteo). DA LANCIARE SOLO DOPO
# 2026-09-15_crea_protocollo_amaranto.py (serve PV-000007 gia' approvato).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 1/2: collega semente Golinucci/Amaranth Red al protocollo PV-000007 ==="
$RUN semente-impiego commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Amaranth Red' \
  --protocol-version 'PV-000007' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale amaranto' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-15-AMARANTO' \
  --idempotency-key 'semente-impiego-golinucci-amaranth-red-pv-000007' \
  --confirm

echo "=== 2/2: commissiona semina AMARANTO (LSE-000012, 10g = 10g x 1 set, 7/9/2026) ==="
OUT=$($RUN semina commission \
  --seed-lot 'LSE-000012' \
  --expected-seed-lot-version 0 \
  --protocol-version 'PV-000007' \
  --actual-seed-grams 10 \
  --physical-started-at '2026-09-07T08:00:00+01:00' \
  --origin ORDINE_CLIENTE \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale amaranto 1 set del 7/9, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-07-AMARANTO' \
  --idempotency-key 'semina-lse-000012-2026-09-07' \
  --confirm)
echo "$OUT"
