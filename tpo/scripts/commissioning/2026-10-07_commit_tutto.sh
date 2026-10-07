#!/bin/bash
# Committa TUTTO il lavoro non ancora committato (planner, script del 6-7/10, comando ordini) in 3 commit,
# con elenchi ESPLICITI: nessun `git add -A`, restano fuori .env*, config/, runtime/, work/, outputs/, clienti/.
# Per ogni commit esegue prima i test dei suoi file (quelli su PostgreSQL si saltano da soli se mancano i binari
# di prova); se falliscono, si ferma PRIMA di committare. I file gia' committati e invariati non cambiano nulla.
# Alla fine mostra cosa NON e' stato committato e chiede conferma prima del push (Ctrl-C per annullare).
# Uso, dalla cartella tpo:  bash scripts/commissioning/2026-10-07_commit_tutto.sh
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

PY=.venv/bin/python
TRAILER=$'Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01XizsFyS6Xx3ZuzGovNVX5D'

echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "Commit non ancora pubblicati: $(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 'upstream non impostato')"

commit_group() {  # $1 = titolo+corpo del messaggio; resto = file
  local message="$1"; shift
  local files=("$@") tests=() f
  echo; echo "================ ${message%%$'\n'*}"
  for f in "${files[@]}"; do
    case "$f" in tests/*test_*.py) [ -e "$f" ] && tests+=("$f");; esac
  done
  if [ "${#tests[@]}" -gt 0 ]; then
    echo "== Test (${#tests[@]} file)"
    "$PY" -m pytest -q "${tests[@]}"
  fi
  echo "== File aggiunti"
  for f in "${files[@]}"; do
    if [ -e "$f" ]; then git add -- "$f"; else echo "  (manca, saltato) $f"; fi
  done
  if git diff --cached --quiet; then echo "Niente da committare in questo gruppo."; return 0; fi
  git diff --cached --stat | tail -n 25
  git commit -q -m "$message" -m "$TRAILER"
  git log --oneline -1
}

# ---------------------------------------------------------------- 1. motore del planner
commit_group "Planner: produzione in corso come risorsa, finestra predittiva, stock a zero, raccolte gia' caricate

- Autorita' delle semine in corso (in_progress_authority) e assemblaggio PRODUZIONE_IN_CORSO nel piano; la
  quantita' idonea e' max(allocata, attesa - raccolta, 0) e una semina e' idonea solo se la finestra inizia
  entro consegna - harvest_min_lead_days.
- semina_predictive_authority: compila il quartetto predittivo (quantita' utile attesa, finestra di raccolta)
  con comando governato separato da \`semina commission\` (freeze §10).
- production_planning_input: stock a zero in piu' unita' non e' piu' STOCK_RESOURCE_CONFLICT; raccolte gia'
  (in parte) caricate: una sola funzione \`harvest_eligible_quantity\` per loader e commit writer.
- Addendum nei freeze PRODUCTION_PLANNING_ENGINE e SEMINA_COMMISSIONING_BOUNDARY." \
  src/tpo_core/application/production_planning/in_progress_authority.py \
  src/tpo_core/application/production_planning/assembler.py \
  src/tpo_core/application/production_planning/service.py \
  src/tpo_core/infrastructure/postgresql/production_planning_input.py \
  src/tpo_core/infrastructure/postgresql/production_planning_commit_writer.py \
  src/tpo_core/infrastructure/postgresql/semina_predictive_authority.py \
  docs/architecture/PRODUCTION_PLANNING_ENGINE_FREEZE.md \
  docs/architecture/SEMINA_COMMISSIONING_BOUNDARY_FREEZE.md \
  tests/application/production_planning/test_in_progress_authority.py \
  tests/application/production_planning/test_assembler.py \
  tests/infrastructure/postgresql/test_production_planning_input.py \
  tests/integration/postgresql/test_planning_in_progress_semine.py \
  tests/integration/postgresql/test_semina_predictive_authority.py \
  tests/integration/postgresql/test_planning_loaded_harvest_commit.py

# ---------------------------------------------------------------- 2. script operativi 5-7/10 su semine e planner
commit_group "Script operativi del 6-7/10: semine, produzione in corso, piano ipotetico, verifica e quadratura

Compilazione/simulazione delle semine in corso, semine del mattino, chiusura semine raccolte, registrazione di
una semina passata (con passaggi di stato e finestra predittiva), produzione in corso per varieta', storia di una
varieta', piano ipotetico a risorse liberate (sola lettura), verifica del planner, diagnostica allocazioni su
ordini chiusi, quadratura semine/stock/ordini/piano. Ognuno in anteprima senza --esegui, con test su PostgreSQL." \
  scripts/commissioning/2026-10-05_verifica_planner.py \
  scripts/commissioning/2026-10-05_diagnostica_allocazioni_chiusi.py \
  scripts/commissioning/2026-10-05_quadratura_semine.py \
  scripts/commissioning/2026-10-06_commit_planner.sh \
  scripts/commissioning/2026-10-06_chiudi_semine_raccolte.py \
  scripts/commissioning/2026-10-06_compila_semine_in_corso.py \
  scripts/commissioning/2026-10-06_simula_semine_in_corso.py \
  scripts/commissioning/2026-10-06_semine_mattina.py \
  scripts/commissioning/2026-10-06_piano_ipotetico.py \
  scripts/commissioning/2026-10-06_produzione_in_corso.py \
  scripts/commissioning/2026-10-06_storia_varieta.py \
  scripts/commissioning/2026-10-06_registra_semina_passata.py \
  tests/integration/postgresql/test_verifica_planner_script.py \
  tests/integration/postgresql/test_quadratura_semine_script.py \
  tests/integration/postgresql/test_chiudi_semine_raccolte_script.py \
  tests/integration/postgresql/test_compila_semine_in_corso_script.py \
  tests/integration/postgresql/test_simula_semine_in_corso_script.py \
  tests/integration/postgresql/test_piano_ipotetico_script.py \
  tests/integration/postgresql/test_produzione_in_corso_script.py \
  tests/integration/postgresql/test_storia_varieta_script.py \
  tests/integration/postgresql/test_registra_semina_passata_sql.py \
  tests/scripts/test_registra_semina_passata_script.py \
  tests/scripts/test_semine_mattina_script.py

# ---------------------------------------------------------------- 3. ordini
commit_group "Ordini: comando unico di modifica (annulla, quantita', data) e strumenti di lettura

- order_amendment: modifica governata di UN ordine APERTO (quantita' di una riga, data di consegna prevista);
  l'originale resta nell'audit (before_data / amended_from), le allocazioni interessate vengono rilasciate,
  tutto o niente, mai su ordini con consegne.
- order_cancellation.allocations_to_release: parametro opzionale line_pks per rilasciare le allocazioni di una
  sola riga (i chiamanti esistenti non cambiano).
- Script: modifica_ordine (annulla | quantita | data), annulla_ordini, ordini_varieta, programma_fornitura,
  allocazioni_ordine, protocolli_attuali (sola lettura), con test su PostgreSQL." \
  src/tpo_core/infrastructure/postgresql/order_amendment.py \
  src/tpo_core/infrastructure/postgresql/order_cancellation.py \
  scripts/commissioning/2026-10-07_modifica_ordine.py \
  scripts/commissioning/2026-10-07_annulla_ordini.py \
  scripts/commissioning/2026-10-07_ordini_varieta.py \
  scripts/commissioning/2026-10-07_programma_fornitura.py \
  scripts/commissioning/2026-10-07_allocazioni_ordine.py \
  scripts/commissioning/2026-10-07_protocolli_attuali.py \
  scripts/commissioning/2026-10-07_commit_tutto.sh \
  tests/integration/postgresql/test_modifica_ordine_script.py \
  tests/integration/postgresql/test_annulla_ordini_script.py \
  tests/integration/postgresql/test_ordini_varieta_script.py \
  tests/integration/postgresql/test_programma_fornitura_script.py \
  tests/integration/postgresql/test_allocazioni_ordine_script.py \
  tests/integration/postgresql/test_protocolli_attuali_script.py \
  tests/integration/postgresql/test_order_cancellation.py \
  tests/integration/postgresql/test_order_residual_closure.py

echo; echo "================ NON committato (modificato o nuovo, fuori dagli elenchi sopra):"
git status --short | grep -v '^??.*\(\.venv\|\.pytest_cache\|__pycache__\)' || echo "  (niente)"

echo; echo "Commit in attesa di pubblicazione:"
git log --oneline '@{u}..HEAD' 2>/dev/null || git log --oneline -8
echo
read -r -p "Pubblico con push su origin/$(git rev-parse --abbrev-ref HEAD)? [Invio = si, Ctrl-C = no] " _
git push -u origin "$(git rev-parse --abbrev-ref HEAD)"
echo "== PUBBLICATO"
