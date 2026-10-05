#!/bin/bash
# Committa i file di lavoro del 5/10/2026 (script, generatore etichette, test) con un elenco ESPLICITO:
# nessun `git add -A`, restano fuori config/, runtime/, work/, outputs/.
# Prima esegue i test delle etichette; se falliscono, si ferma. NON fa push (vedi l'ultima riga).
# Uso, dalla cartella tpo:  scripts/commissioning/2026-10-05_commit.sh
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

FILES=(
  scripts/commissioning/2026-10-04_commission_semine_afila_cilantro.py
  scripts/commissioning/2026-10-04_registra_materiali.py
  scripts/commissioning/2026-10-05_check_sistema.py
  scripts/commissioning/2026-10-05_diagnostica_scheduler.py
  scripts/commissioning/2026-10-05_diagnostica_allocazioni.py
  scripts/commissioning/2026-10-05_consegne_bahia_splash.py
  scripts/commissioning/2026-10-05_cerca_albahaca.py
  scripts/commissioning/2026-10-05_registra_albahaca.py
  scripts/commissioning/2026-10-05_passa_a_luce.py
  scripts/commissioning/2026-10-05_chiudi_semina.py
  scripts/commissioning/2026-10-05_pacchetto_consegna.sh
  scripts/commissioning/2026-10-05_commit.sh
  src/tpo_core/infrastructure/pdf/etichette_pdf.py
  src/tpo_core/cli/etichetta.py
  src/tpo_core/cli/main.py
  tests/cli/test_etichetta_cli.py
)

echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
echo "== Test etichette"
.venv/bin/python -m pytest tests/cli/test_etichetta_cli.py -q

echo "== File aggiunti"
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then git add -- "$f"; echo "  + $f"; else echo "  (manca, saltato) $f"; fi
done

echo "== Stato (in stage)"
git status --short
if git diff --cached --quiet; then echo "Niente da committare."; exit 0; fi

git commit -q -F - <<'MSG'
Consegne, albahaca, luce e chiusura semine del 5/10/2026; etichette di tracciabilita'

- Script operativi 2026-10-05: controllo di salute, diagnostica scheduler/allocazioni,
  consegne Bahia/Splash, ricerca e registrazione albahaca, passaggio a luce, chiusura semina,
  pacchetto consegna (bolla, etichette opzionali).
- `tpo etichetta genera`: etichette 62x29 mm in PDF, una per SET (--etichette-per-set), sola lettura.
- Regola: LUCE e CRESCITA sono lo stesso processo (CRESCITA registrata 1 minuto dopo la luce).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XizsFyS6Xx3ZuzGovNVX5D
MSG

git log --oneline -1
echo "Per pubblicare:  git push"
