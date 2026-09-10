#!/bin/bash
# SEMINA Commissioning Script - 2026-09-07
# Links LOTTO_SEME (seed lots) to VARIETA (varieties) and generates traceability codes
# Covers all 19 commissioned seed lots (LSE-000001 through LSE-000019)

set -e

echo "=== SEMINA COMMISSIONING PHASE ==="
echo "Commissioning all 19 seed lots + generating final traceability codes"
echo

# Verify run_tpo.sh exists
if [[ ! -f "scripts/commissioning/run_tpo.sh" ]]; then
  echo "ERROR: run_tpo.sh not found in scripts/commissioning/" >&2
  exit 1
fi

# SEMINA commissioning for each seed lot
echo '--- [1/19] Rucola (Rocket Cultivated) - Lotto LSE-000001 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000001' \
  --varieta-id 'VAR-000007' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Rucola Rocket Cultivated (Golinucci) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000001-var-000007'

echo '--- [2/19] Rucola (Rucula Intersemillas) - Lotto LSE-000002 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000002' \
  --varieta-id 'VAR-000007' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Rucola Rucula Intersemillas per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000002-var-000007'

echo '--- [3/19] Pak Choi (White) - Lotto LSE-000003 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000003' \
  --varieta-id 'VAR-000008' \
  --planted-date '2026-09-07' \
  --quantity-consumed '500' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Pak Choi White (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000003-var-000008'

echo '--- [4/19] Pak Choi (Intersemillas) - Lotto LSE-000004 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000004' \
  --varieta-id 'VAR-000008' \
  --planted-date '2026-09-07' \
  --quantity-consumed '500' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Pak Choi Intersemillas per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000004-var-000008'

echo '--- [5/19] Acetosella (Sorrel Red Veined) - Lotto LSE-000005 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000005' \
  --varieta-id 'VAR-000009' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Acetosella Sorrel Red Veined (Galbani) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000005-var-000009'

echo '--- [6/19] Amaranto (Red) - Lotto LSE-000006 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000006' \
  --varieta-id 'VAR-000010' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Amaranto Red (Intersemillas) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000006-var-000010'

echo '--- [7/19] Senape/Mustard (White) - Lotto LSE-000007 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000007' \
  --varieta-id 'VAR-000011' \
  --planted-date '2026-09-07' \
  --quantity-consumed '200' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Senape Mustard White (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000007-var-000011'

echo '--- [8/19] Cavolo Rosso (Red Cabbage) - Lotto LSE-000008 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000008' \
  --varieta-id 'VAR-000012' \
  --planted-date '2026-09-07' \
  --quantity-consumed '4900' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Cavolo Rosso Col Roja (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000008-var-000012'

echo '--- [9/19] Girasole (Sunflower) - Lotto LSE-000009 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000009' \
  --varieta-id 'VAR-000013' \
  --planted-date '2026-09-07' \
  --quantity-consumed '100' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Girasole Sunflower (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000009-var-000013'

echo '--- [10/19] Lenticchia (Lentils) - Lotto LSE-000010 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000010' \
  --varieta-id 'VAR-000014' \
  --planted-date '2026-09-07' \
  --quantity-consumed '660' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Lenticchia Lentils (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000010-var-000014'

echo '--- [11/19] Rabano (Radish Hyfarm) - Lotto LSE-000011 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000011' \
  --varieta-id 'VAR-000002' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Rabano Radish Hyfarm per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000011-var-000002'

echo '--- [12/19] Cilantro (Coriander) - Lotto LSE-000012 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000012' \
  --varieta-id 'VAR-000003' \
  --planted-date '2026-09-07' \
  --quantity-consumed '100' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Cilantro Coriander per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000012-var-000003'

echo '--- [13/19] Mizuna (Asian Greens) - Lotto LSE-000013 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000013' \
  --varieta-id 'VAR-000004' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Mizuna Asian Greens per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000013-var-000004'

echo '--- [14/19] Hinojo (Fennel) - Lotto LSE-000014 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000014' \
  --varieta-id 'VAR-000005' \
  --planted-date '2026-09-07' \
  --quantity-consumed '200' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Hinojo Fennel per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000014-var-000005'

echo '--- [15/19] Basilico (Basil) - Lotto LSE-000015 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000015' \
  --varieta-id 'VAR-000006' \
  --planted-date '2026-09-07' \
  --quantity-consumed '100' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Basilico Basil per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000015-var-000006'

echo '--- [16/19] Afila (Tomato Hyfarm) - Lotto LSE-000016 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000016' \
  --varieta-id 'VAR-000001' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Afila Tomato Hyfarm per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000016-var-000001'

echo '--- [17/19] Girasole Hyfarm 2 - Lotto LSE-000017 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000017' \
  --varieta-id 'VAR-000013' \
  --planted-date '2026-09-07' \
  --quantity-consumed '100' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Girasole Sunflower (Hyfarm) lotto 2 per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000017-var-000013'

echo '--- [18/19] Lenticchie (Lentils) - Lotto LSE-000018 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000018' \
  --varieta-id 'VAR-000014' \
  --planted-date '2026-09-07' \
  --quantity-consumed '660' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Lenticchie Lentils (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000018-var-000014'

echo '--- [19/19] Rabano (Radish) - Hyfarm - Lotto LSE-000019 ---'
scripts/commissioning/run_tpo.sh semina commission \
  --lotto-seme-id 'LSE-000019' \
  --varieta-id 'VAR-000002' \
  --planted-date '2026-09-07' \
  --quantity-consumed '50' \
  --actor 'matteo' \
  --reason 'SEMINA commissioning per Rabano Radish (Hyfarm) per tracciabilita hotel' \
  --correlation-id 'SEMINA-2026-09-07' \
  --idempotency-key 'semina-lse-000019-var-000002'

echo
echo "FATTO: 19 SEMINA commissioning commands executed."
echo "Final traceability codes (SeminaTraceabilityCode: AAA-GGMM-L) are now available for hotel delivery."
