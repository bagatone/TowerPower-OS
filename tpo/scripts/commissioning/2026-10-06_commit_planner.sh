#!/bin/bash
# Committa le correzioni del planner e gli script di verifica/quadratura del 5-6/10/2026, con un elenco ESPLICITO:
# nessun `git add -A`, restano fuori config/, runtime/, work/, outputs/.
# Prima esegue i test coinvolti (quelli su PostgreSQL si saltano da soli se mancano i binari di prova);
# se falliscono, si ferma. NON fa push (vedi l'ultima riga).
# Uso, dalla cartella tpo:  bash scripts/commissioning/2026-10-06_commit_planner.sh
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

FILES=(
  src/tpo_core/infrastructure/postgresql/production_planning_input.py
  src/tpo_core/infrastructure/postgresql/production_planning_commit_writer.py
  scripts/commissioning/2026-10-05_verifica_planner.py
  scripts/commissioning/2026-10-05_diagnostica_allocazioni_chiusi.py
  scripts/commissioning/2026-10-05_quadratura_semine.py
  scripts/commissioning/2026-10-06_commit_planner.sh
  tests/infrastructure/postgresql/test_production_planning_input.py
  tests/integration/postgresql/test_planning_loaded_harvest_commit.py
  tests/integration/postgresql/test_verifica_planner_script.py
  tests/integration/postgresql/test_quadratura_semine_script.py
)

echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "== Test"
.venv/bin/python -m pytest -q \
  tests/infrastructure/postgresql/test_production_planning_input.py \
  tests/infrastructure/postgresql/test_production_planning_commit_writer.py \
  tests/integration/postgresql/test_production_planning_end_to_end.py \
  tests/integration/postgresql/test_planning_loaded_harvest_commit.py \
  tests/integration/postgresql/test_verifica_planner_script.py \
  tests/integration/postgresql/test_quadratura_semine_script.py

echo "== File aggiunti"
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then git add -- "$f"; echo "  + $f"; else echo "  (manca, saltato) $f"; fi
done

echo "== Stato (in stage)"
git status --short
if git diff --cached --quiet; then echo "Niente da committare."; exit 0; fi

git commit -q -F - <<'MSG'
Planner: stock a zero in piu' unita', commit con raccolte gia' caricate; verifica e quadratura

- production_planning_input._stock: varieta' con riga GRAM congelata e riga SET entrambe a 0 non e' piu'
  STOCK_RESOURCE_CONFLICT: si usa la riga SET (con piu' righe vive o senza riga SET resta fail-closed).
- Raccolte gia' (in parte) caricate a magazzino: una sola funzione `harvest_eligible_quantity` per loader e
  commit writer. Prima il commit riconfrontava lo snapshot con la quantita' registrata e falliva con
  CONCURRENCY_CONFLICT HARVEST_CHANGED. Test di regressione riprodotto prima della correzione.
- Script operativi: verifica del planner (controlli pre-run in sola lettura, `--esegui` lancia un run manuale
  con business_at = adesso), diagnostica allocazioni su ordini chiusi, quadratura semine/stock/ordini/piano
  (sola lettura).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XizsFyS6Xx3ZuzGovNVX5D
MSG

git log --oneline -1
echo "Per pubblicare:  git push"
