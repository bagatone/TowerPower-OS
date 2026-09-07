#!/bin/bash
# Onboarding VARIETA per le colture non ancora presenti nel sistema,
# generato il 2026-09-07 e confermato con l'utente (nomi, codici a 3
# lettere, raggruppamenti). NON tocca le 6 VARIETA gia' esistenti
# (Afila/AFI, Rabano/RAB, Cilantro/CIL, Mizuna/MIZ, Hinojo/HIN,
# Basilico/ALB) che vengono riusate cosi' come sono.
# ATTENZIONE: il codice di tracciabilita' a 3 lettere e' PERMANENTE e
# univoco una volta commissionato (nessuna correzione possibile).
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

echo '--- [1/9] Rucola (VAR-000007) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000007' \
  --denomination 'Rucola' \
  --traceability-code 'RUC' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Rocket Cultivated (Golinucci) e Rucula (Intersemillas)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [2/9] Pak Choi (VAR-000008) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000008' \
  --denomination 'Pak Choi' \
  --traceability-code 'PAK' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Pak Choi White (Golinucci) e Pak Choi (Intersemillas)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [3/9] Acetosella (VAR-000009) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000009' \
  --denomination 'Acetosella' \
  --traceability-code 'ACE' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Sorrel Red Veined (Golinucci)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [4/9] Amaranto (VAR-000010) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000010' \
  --denomination 'Amaranto' \
  --traceability-code 'AMA' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Amaranth Red (Golinucci)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [5/9] Senape (VAR-000011) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000011' \
  --denomination 'Senape' \
  --traceability-code 'MOS' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Mustard White (Golinucci)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [6/9] Cavolo rosso (VAR-000012) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000012' \
  --denomination 'Cavolo rosso' \
  --traceability-code 'COL' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Col Roja (Hyfarm)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [7/9] Girasole (VAR-000013) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000013' \
  --denomination 'Girasole' \
  --traceability-code 'GIR' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Girasoli (Hyfarm)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [8/9] Lenticchia (VAR-000014) ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000014' \
  --denomination 'Lenticchia' \
  --traceability-code 'LEN' \
  --state 'ATTIVA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita - copre Lenticchie (Hyfarm)' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo '--- [9/9] Utrillo (VAR-000015) - DISMESSA ---'
scripts/commissioning/run_tpo.sh onboarding variety \
  --variety-id 'VAR-000015' \
  --denomination 'Utrillo' \
  --traceability-code 'UTR' \
  --state 'DISMESSA' \
  --actor 'matteo' \
  --reason 'Onboarding VARIETA per tracciabilita storica - copre Pisello Utrillo (Bayer/Seminis), varieta da non ricomprare, non adatta a microgreens' \
  --correlation-id 'VARIETA-ONBOARDING-2026-09-07'

echo 'FATTO: 9 VARIETA onboardate.'
