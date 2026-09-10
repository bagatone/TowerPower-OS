#!/bin/bash
# Registra in TPO le semine reali di Rabano e Cilantro del 7/9/2026,
# rimaste fuori dal sistema per il bug dello script del 7/9 (flag CLI
# incompatibili). Ricostruisce la catena mancante (semente_impieghi),
# commissiona le semine con la data reale, poi le porta allo stato
# reale di oggi (GERMINAZIONE).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== 1/6: collega semente Hyfarm/Rabano al protocollo PV-000002 ==="
$RUN semente-impiego commission \
  --fornitore 'Hyfarm' \
  --referenza-commerciale 'Rabano (Radish) - Hyfarm' \
  --protocol-version 'PV-000002' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale rabano' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-10-RABANO' \
  --idempotency-key 'semente-impiego-hyfarm-rabano-pv-000002' \
  --confirm

echo "=== 2/6: collega semente Golinucci/Coriander Split al protocollo PV-000003 ==="
$RUN semente-impiego commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Coriander Split' \
  --protocol-version 'PV-000003' \
  --raccomandazione RACCOMANDATA \
  --actor 'giulia' \
  --reason 'collegamento semente-protocollo per commissioning semina reale cilantro' \
  --correlation-id 'SEMENTE-IMPIEGO-2026-09-10-CILANTRO' \
  --idempotency-key 'semente-impiego-golinucci-coriander-pv-000003' \
  --confirm

echo "=== 3/6: commissiona semina RABANO (LSE-000019, 48g = 16g x 3 set) ==="
RABANO_OUT=$($RUN semina commission \
  --seed-lot 'LSE-000019' \
  --expected-seed-lot-version 0 \
  --protocol-version 'PV-000002' \
  --actual-seed-grams 48 \
  --physical-started-at '2026-09-07T08:00:00+01:00' \
  --origin ORDINE_CLIENTE \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale rabano 3 set, registrata in ritardo (bug script 7/9)' \
  --correlation-id 'SEMINA-2026-09-07-RABANO' \
  --idempotency-key 'semina-lse-000019-2026-09-07' \
  --confirm)
echo "$RABANO_OUT"
RABANO_SEM_ID=$(echo "$RABANO_OUT" | grep '^PUBLIC_ID:' | awk '{print $2}')
echo "--> SEMINA RABANO: $RABANO_SEM_ID"

echo "=== 4/6: commissiona semina CILANTRO (LSE-000013, 96g = 16g x 6 set) ==="
CILANTRO_OUT=$($RUN semina commission \
  --seed-lot 'LSE-000013' \
  --expected-seed-lot-version 0 \
  --protocol-version 'PV-000003' \
  --actual-seed-grams 96 \
  --physical-started-at '2026-09-07T08:00:00+01:00' \
  --origin ORDINE_CLIENTE \
  --provenance '{"physical_started_at":"OWNER_AUTHORIZED","actual_seed_grams":"OWNER_AUTHORIZED","selected_lse":"OWNER_AUTHORIZED","selected_pv":"OWNER_AUTHORIZED","origin":"OWNER_AUTHORIZED"}' \
  --actor 'giulia' \
  --reason 'semina reale cilantro 6 set, registrata in ritardo (bug script 7/9)' \
  --correlation-id 'SEMINA-2026-09-07-CILANTRO' \
  --idempotency-key 'semina-lse-000013-2026-09-07' \
  --confirm)
echo "$CILANTRO_OUT"
CILANTRO_SEM_ID=$(echo "$CILANTRO_OUT" | grep '^PUBLIC_ID:' | awk '{print $2}')
echo "--> SEMINA CILANTRO: $CILANTRO_SEM_ID"

echo "=== 5/6: transizione RABANO AVVIATA -> GERMINAZIONE ==="
$RUN semina transition \
  --semina "$RABANO_SEM_ID" \
  --expected-semina-version 0 \
  --target-state GERMINAZIONE \
  --effective-at '2026-09-08T08:00:00+01:00' \
  --provenance '{}' \
  --actor 'giulia' \
  --reason 'inizio germinazione osservato, registrato in ritardo' \
  --correlation-id "GERMINAZIONE-$RABANO_SEM_ID" \
  --idempotency-key "germinazione-$RABANO_SEM_ID" \
  --confirm

echo "=== 6/6: transizione CILANTRO AVVIATA -> GERMINAZIONE ==="
$RUN semina transition \
  --semina "$CILANTRO_SEM_ID" \
  --expected-semina-version 0 \
  --target-state GERMINAZIONE \
  --effective-at '2026-09-08T08:00:00+01:00' \
  --provenance '{}' \
  --actor 'giulia' \
  --reason 'inizio germinazione osservato, registrato in ritardo' \
  --correlation-id "GERMINAZIONE-$CILANTRO_SEM_ID" \
  --idempotency-key "germinazione-$CILANTRO_SEM_ID" \
  --confirm

echo
echo "FATTO: RABANO=$RABANO_SEM_ID  CILANTRO=$CILANTRO_SEM_ID"
