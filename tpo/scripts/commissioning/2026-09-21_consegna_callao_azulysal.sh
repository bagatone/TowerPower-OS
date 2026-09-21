#!/bin/bash
# Registra le due consegne reali rimaste bloccate dal Fatto 21 in poi,
# sbloccate dal mini-progetto stock/carico in SET (Fatto 24) e dalla
# ristrutturazione a chiave composita (Fatto 25): El Callao (1 SET Afila,
# contro ORD-000014/RO-000032) e Azul y Sal (1 SET Cilantro, contro
# ORD-000009/RO-000019). Consegna parziale rispetto alla riga ordine (2 SET
# e 5 SET rispettivamente): supportato dal motore (vedi Fatto 22).
#
# Versioni ordine/riga (expected_order_version/expected_order_line_version)
# verificate il 21/9/2026 con
# scripts/commissioning/2026-09-19_check_ordini_versions.py: entrambe le
# righe a version=0, nessuna consegna mai registrata su questi ordini.
# Se questo script fallisce con un errore di versione (CAS), le versioni
# sono cambiate nel frattempo: rilanciare lo script di verifica prima di
# ritentare, non semplicemente incrementare i numeri a mano.
#
# effective_at coerente con l'orario reale gia' usato per il carico
# corrispondente (2026-09-19_raccolta_carico_afila_cilantro.sh, Fatto 23):
# 18/9/2026 09:00 (+01:00), mattina, "cut to order" — raccolto e consegnato
# lo stesso giorno.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

echo "=== CONSEGNA: 1 SET Afila -> El Callao (ORD-000014/RO-000032) ==="
$RUN delivery fulfil \
  --client 'CLI-000009' \
  --planned-date '2026-09-18' \
  --effective-at '2026-09-18T09:00:00+01:00' \
  --lines-file 'scripts/commissioning/2026-09-21_consegna_callao_lines.json' \
  --actor 'giulia' \
  --reason 'Consegna 1 SET Afila a El Callao, gia raccolto/caricato il 18/9 (Fatto 23), sbloccata dal mini-progetto stock in SET' \
  --correlation-id 'CONSEGNA-2026-09-18-AFILA-CALLAO' \
  --confirm

echo ""
echo "=== CONSEGNA: 1 SET Cilantro -> Azul y Sal (ORD-000009/RO-000019) ==="
$RUN delivery fulfil \
  --client 'CLI-000005' \
  --planned-date '2026-09-18' \
  --effective-at '2026-09-18T09:00:00+01:00' \
  --lines-file 'scripts/commissioning/2026-09-21_consegna_azulysal_lines.json' \
  --actor 'giulia' \
  --reason 'Consegna 1 SET Cilantro a Azul y Sal, gia raccolto/caricato il 18/9 (Fatto 23), sbloccata dal mini-progetto stock in SET' \
  --correlation-id 'CONSEGNA-2026-09-18-CILANTRO-AZULYSAL' \
  --confirm

echo ""
echo "=== FATTO: 2 consegne reali registrate. ==="
