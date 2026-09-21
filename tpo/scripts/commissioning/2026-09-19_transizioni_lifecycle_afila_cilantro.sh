#!/bin/bash
# Porta le semine Afila (SEM-000002) e Cilantro (SEM-000001) attraverso il
# ciclo di vita AVVIATA -> GERMINAZIONE -> LUCE -> CRESCITA ->
# PRONTA_ALLA_RACCOLTA, mai dichiarato finora per nessuna semina nel
# sistema reale (prima volta che si usa `tpo semina transition`).
#
# IMPORTANTE: le date delle 3 transizioni intermedie (GERMINAZIONE, LUCE,
# CRESCITA) sono AMMINISTRATIVE, non osservazioni reali -- Matteo/Giulia
# non hanno mai annotato quando questi lotti sono passati effettivamente
# di stadio. Confermato esplicitamente da Matteo il 19/9: "vanno bene,
# possono essere vendute" -- i tempi del protocollo (Afila 5+5gg,
# Cilantro 7+6gg) risultano piu' lunghi del raccolto reale (17-18/9), da
# rivedere in futuro, non toccati qui. Le date usate qui sono solo
# scaffolding per soddisfare la sequenza di stato richiesta dal sistema,
# compresse a +1/+2/+3/+4 giorni dalla semina, sempre prima della prima
# raccolta reale che le usa (17/9 ore 9 per entrambe, consegna Selvaje).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

transizione() {
  local label="$1" semina="$2" expected_version="$3" target_state="$4" \
        effective_at="$5" corr="$6" idem="$7"

  echo "=== TRANSIZIONE: $label -> $target_state ($effective_at) ==="
  T_OUT=$($RUN semina transition \
    --semina "$semina" \
    --expected-semina-version "$expected_version" \
    --target-state "$target_state" \
    --effective-at "$effective_at" \
    --provenance '{"target_state":"OWNER_AUTHORIZED","effective_at":"OWNER_AUTHORIZED"}' \
    --actor 'giulia' \
    --reason "Transizione amministrativa $target_state (data di comodo, non osservazione reale -- vedi commento script) per sbloccare la raccolta gia' avvenuta" \
    --correlation-id "$corr" \
    --idempotency-key "$idem" \
    --confirm)
  echo "$T_OUT"
  echo ""
}

echo "########## AFILA (SEM-000002, semina reale 13/9) ##########"
transizione "Afila" 'SEM-000002' 0 'GERMINAZIONE' '2026-09-14T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-AFILA-GERMINAZIONE' 'lifecycle-afila-germinazione-2026-09-19'
transizione "Afila" 'SEM-000002' 1 'LUCE' '2026-09-15T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-AFILA-LUCE' 'lifecycle-afila-luce-2026-09-19'
transizione "Afila" 'SEM-000002' 2 'CRESCITA' '2026-09-16T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-AFILA-CRESCITA' 'lifecycle-afila-crescita-2026-09-19'
transizione "Afila" 'SEM-000002' 3 'PRONTA_ALLA_RACCOLTA' '2026-09-17T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-AFILA-PRONTA' 'lifecycle-afila-pronta-2026-09-19'

echo "########## CILANTRO (SEM-000001, semina reale 7/9) ##########"
transizione "Cilantro" 'SEM-000001' 0 'GERMINAZIONE' '2026-09-08T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-CILANTRO-GERMINAZIONE' 'lifecycle-cilantro-germinazione-2026-09-19'
transizione "Cilantro" 'SEM-000001' 1 'LUCE' '2026-09-09T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-CILANTRO-LUCE' 'lifecycle-cilantro-luce-2026-09-19'
transizione "Cilantro" 'SEM-000001' 2 'CRESCITA' '2026-09-10T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-CILANTRO-CRESCITA' 'lifecycle-cilantro-crescita-2026-09-19'
transizione "Cilantro" 'SEM-000001' 3 'PRONTA_ALLA_RACCOLTA' '2026-09-11T08:00:00+01:00' \
  'SEMINA-LIFECYCLE-2026-09-19-CILANTRO-PRONTA' 'lifecycle-cilantro-pronta-2026-09-19'

echo "=== FATTO: entrambe le semine ora PRONTA_ALLA_RACCOLTA. Ora si puo' lanciare 2026-09-19_raccolta_carico_afila_cilantro.sh ==="
