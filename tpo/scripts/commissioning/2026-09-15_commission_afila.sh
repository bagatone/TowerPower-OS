#!/bin/bash
# Commissiona nel sistema reale la semina AFILA del 13/9/2026 (6 SET,
# 192g = 32g/set, grammi_seme_per_set REALE del protocollo PV-000001 --
# non 30g come nei documenti, quello era stimato/stale).
# DA LANCIARE SOLO DOPO 2026-09-15_correggi_anomalia_afila.py (altrimenti
# il sistema rifiuta il lotto per anomalia, ed espected-seed-lot-version
# deve essere 1, non 0, perche' la correzione fa avanzare la versione).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 1/2: collega semente Golinucci/Pea Green Affila al protocollo PV-000001 ==="
$RUN semente-impiego commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Pea Green Affila' \
  --protocol-version 'PV-000001' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale afila' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-15-AFILA' \
  --idempotency-key 'semente-impiego-golinucci-pea-affila-pv-000001' \
  --confirm

echo "=== 2/2: commissiona semina AFILA (LSE-000014, 192g = 32g x 6 set, 13/9/2026) ==="
OUT=$($RUN semina commission \
  --seed-lot 'LSE-000014' \
  --expected-seed-lot-version 1 \
  --protocol-version 'PV-000001' \
  --actual-seed-grams 192 \
  --physical-started-at '2026-09-13T08:00:00+01:00' \
  --origin ORDINE_CLIENTE \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale afila 6 set del 13/9, registrata in ritardo nel sistema' \
  --correlation-id 'SEMINA-2026-09-13-AFILA' \
  --idempotency-key 'semina-lse-000014-2026-09-13' \
  --confirm)
echo "$OUT"
