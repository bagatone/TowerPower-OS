#!/bin/bash
# Commit + push del mini-progetto "stock a chiave composita" (Fatto 24+25+26)
# e delle due consegne reali sbloccate (21/9/2026). Scritto come script (non
# da incollare a mano nel terminale) apposta per evitare i problemi di
# quoting/interleaving di un blocco lungo incollato interattivamente.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

echo "=== git status (prima di aggiungere nulla) ==="
git status

FILES=(
  migrations/versions/20260919_0035_stock_unita_composita.py
  src/tpo_core/application/movimento_carico/models.py
  src/tpo_core/application/disponibilita_commerciale/errors.py
  src/tpo_core/infrastructure/postgresql/movimento_carico.py
  src/tpo_core/infrastructure/postgresql/disponibilita_commerciale.py
  src/tpo_core/infrastructure/postgresql/delivery_fulfilment_writer.py
  src/tpo_core/infrastructure/postgresql/production_planning_input.py
  src/tpo_core/infrastructure/postgresql/production_planning_commit_writer.py
  src/tpo_core/cli/movimento_carico.py
  src/tpo_core/cli/main.py
  scripts/commissioning/2026-09-19_migrazione_stock_set_afila_cilantro.py
  scripts/commissioning/2026-09-19_raccolta_carico_afila_cilantro.sh
  scripts/commissioning/2026-09-19_transizioni_lifecycle_afila_cilantro.sh
  scripts/commissioning/2026-09-19_check_ordini_versions.py
  scripts/commissioning/2026-09-21_consegna_callao_lines.json
  scripts/commissioning/2026-09-21_consegna_azulysal_lines.json
  scripts/commissioning/2026-09-21_consegna_callao_azulysal.sh
  scripts/commissioning/2026-09-21_commit_stock_set.sh
  tests/application/test_movimento_carico.py
  tests/integration/postgresql/test_movimento_carico.py
  tests/cli/test_movimento_carico_cli.py
  tests/infrastructure/postgresql/test_stock_unita_composita_migration.py
  tests/infrastructure/postgresql/test_production_planning_migrations.py
  tests/infrastructure/postgresql/test_migrations.py
  tests/infrastructure/postgresql/test_programma_fornitura_sospensione_migration.py
  tests/infrastructure/postgresql/test_finanze_aziendali_migration.py
  tests/infrastructure/postgresql/test_delivery_fulfilment_migration.py
  tests/infrastructure/postgresql/test_fattura_rettifica_migration.py
  tests/infrastructure/postgresql/test_assegnazione_fisica_migration.py
  tests/infrastructure/postgresql/test_movimento_carico_migration.py
  tests/infrastructure/postgresql/test_id_sequences_backfill_migration.py
  tests/infrastructure/postgresql/test_fattura_emissione_migration.py
  tests/infrastructure/postgresql/test_raccolta_migration.py
  tests/infrastructure/postgresql/test_articolo_migration.py
  tests/infrastructure/postgresql/test_semina_traceability_migration.py
  tests/infrastructure/postgresql/test_semina_lifecycle_migration.py
  tests/infrastructure/postgresql/test_raccolta_correzione_migration.py
  tests/infrastructure/postgresql/test_raccolta_correzione_annotazione_migration.py
  docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md
  docs/architecture/STOCK.md
  docs/architecture/STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md
  docs/architecture/STOCK_UNITA_VENDITA_INTERA_PROPOSTA.md
)

echo ""
echo "=== git add (solo i file di questo mini-progetto, elencati esplicitamente) ==="
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then
    git add -- "$f"
  else
    echo "ATTENZIONE: non trovato, saltato: $f" >&2
  fi
done

echo ""
echo "=== git status DOPO l'add (controlla che non ci sia nulla di runtime/ o secrets) ==="
git status

echo ""
read -r -p "Procedo con commit + push? [y/N] " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "Annullato. Nulla e' stato committato (puoi controllare con 'git status' e fare 'git reset' se serve)."
  exit 0
fi

MSG_FILE="$(mktemp)"
cat > "$MSG_FILE" <<'MSG_EOF'
Stock a chiave composita (varieta_id, unita_misura): sblocca vendita a SET

Il carico in GRAM non permetteva di rappresentare prodotto venduto a SET
interi (i microgreens). Aggiunto movimento carica-raccolta --unita-misura
SET (D13/D14). La prima migrazione dati (UPDATE in place) e' fallita con
ForeignKeyViolation: i MOVIMENTI storici in GRAM di Afila/Cilantro
referenziano ancora quella riga STOCK, e sono immutabili per definizione.

Risolto rilassando la PK di tpo.stock a (varieta_id, unita_misura): una
VARIETA puo' avere piu' righe STOCK, mai due vive nella stessa unita'.
allocazioni_stock guadagna stock_unita_misura. Aggiornati i lettori che
assumevano una riga sola per varieta_id (disponibilita_commerciale,
delivery_fulfilment_writer, production_planning_input/commit_writer),
con la policy: preferisci la riga disponibile>0, fallisci chiuso se
ambiguo. Corretto anche un bug di JOIN-fanout latente in
production_planning_input scoperto nello stesso giro.

Corretti dopo il primo run pytest reale post-ristrutturazione (16
falliti): un INSERT di test senza la nuova colonna NOT NULL, due lookup
dinamici su pg_constraint incompatibili con la generazione SQL offline
(sostituiti con nomi letterali verificati), due test che verificavano il
comportamento vecchio ora deliberatamente superato.

Verificato con pytest reale: 2526 passed, 8 skipped. Migrazione e script
dati applicati al Postgres di produzione; registrate le prime due
consegne reali sbloccate da questo lavoro (CON-000001 El Callao,
CON-000002 Azul y Sal).
MSG_EOF

git commit -F "$MSG_FILE"
rm -f "$MSG_FILE"

echo ""
echo "=== git push ==="
git push

echo ""
echo "=== FATTO ==="
git log -1 --stat
