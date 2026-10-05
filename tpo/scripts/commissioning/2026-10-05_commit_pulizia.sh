#!/bin/bash
# Committa il lavoro di pulizia ordini/allocazioni del 5/10/2026 con un elenco ESPLICITO:
# nessun `git add -A`, restano fuori config/, runtime/, work/, outputs/.
# Prima esegue i test coinvolti (quelli su PostgreSQL si saltano da soli se mancano i binari di prova);
# se falliscono, si ferma. NON fa push (vedi l'ultima riga).
# Uso, dalla cartella tpo:  scripts/commissioning/2026-10-05_commit_pulizia.sh
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

FILES=(
  src/tpo_core/application/production_planning/service.py
  src/tpo_core/infrastructure/postgresql/production_planning_input.py
  src/tpo_core/infrastructure/postgresql/allocation_invalidation.py
  src/tpo_core/infrastructure/postgresql/order_cancellation.py
  src/tpo_core/infrastructure/postgresql/order_residual_closure.py
  src/tpo_core/infrastructure/postgresql/pianificazione_semina_lettura.py
  src/tpo_core/diario_web/rendiconto.py
  scripts/commissioning/2026-10-05_diagnostica_replanning.py
  scripts/commissioning/2026-10-05_diagnostica_ordini_aperti.py
  scripts/commissioning/2026-10-05_diagnostica_raccolte.py
  scripts/commissioning/2026-10-05_invalida_stock_obsoleto.py
  scripts/commissioning/2026-10-05_chiudi_ordini_scaduti.py
  scripts/commissioning/2026-10-05_chiudi_residuo_ordini.py
  scripts/commissioning/2026-10-05_scarica_raccolte_storiche.py
  scripts/commissioning/2026-10-05_commit_pulizia.sh
  tests/infrastructure/postgresql/test_production_planning_input.py
  tests/integration/postgresql/replan_disposition_authoring.py
  tests/integration/postgresql/test_production_planning_replan_dispositions_e2e.py
  tests/integration/postgresql/test_allocation_invalidation.py
  tests/integration/postgresql/test_invalida_stock_obsoleto_script.py
  tests/integration/postgresql/test_order_cancellation.py
  tests/integration/postgresql/test_chiudi_ordini_scaduti_script.py
  tests/integration/postgresql/test_order_residual_closure.py
  tests/integration/postgresql/test_scarica_raccolte_storiche_script.py
)

echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "== Test"
.venv/bin/python -m pytest -q \
  tests/infrastructure/postgresql/test_production_planning_input.py \
  tests/integration/postgresql/test_production_planning_replan_dispositions_e2e.py \
  tests/integration/postgresql/test_allocation_invalidation.py \
  tests/integration/postgresql/test_invalida_stock_obsoleto_script.py \
  tests/integration/postgresql/test_order_cancellation.py \
  tests/integration/postgresql/test_chiudi_ordini_scaduti_script.py \
  tests/integration/postgresql/test_order_residual_closure.py \
  tests/integration/postgresql/test_scarica_raccolte_storiche_script.py

echo "== File aggiunti"
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then git add -- "$f"; echo "  + $f"; else echo "  (manca, saltato) $f"; fi
done

echo "== Stato (in stage)"
git status --short
if git diff --cached --quiet; then echo "Niente da committare."; exit 0; fi

git commit -q -F - <<'MSG'
Pulizia ordini e allocazioni obsolete del 5/10/2026; fix planner su raccolte e replanning

- Planner: una raccolta gia' (in parte) caricata a magazzino non viene piu' contata due volte
  (disponibilita' = max(allocato, registrato - caricato)); il replanning con disposition autorizzate
  non viene piu' rifiutato come "iniziale" (INITIAL_DISPOSITIONS_NOT_EMPTY).
- "Da seminare" e rendiconto considerano solo ordini APERTO/PARZIALMENTE_EVASO.
- allocation_invalidation: invalida solo allocazioni STOCK realmente sovra-allocate (append-only, audit).
- order_cancellation: ordini storici scaduti senza consegne -> ANNULLATO (EVASO richiede consegne
  registrate), allocazioni rilasciate; si rifiuta se una raccolta allocata non e' caricata a stock.
- order_residual_closure: residuo non piu' dovuto di ordini parzialmente evasi -> quantita' ordinata
  portata alla consegnata, ordine EVASO, quantita' originale nell'audit; consegne intatte.
- Script operativi (anteprima di default, --esegui scrive): invalida stock obsoleto, chiudi ordini
  scaduti, chiudi residuo ordini, carico+rettifica "vendita non registrata" delle raccolte storiche,
  diagnostiche di sola lettura (replanning, ordini aperti, raccolte).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XizsFyS6Xx3ZuzGovNVX5D
MSG

git log --oneline -1
echo "Per pubblicare:  git push"
