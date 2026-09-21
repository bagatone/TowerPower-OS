#!/bin/bash
# Registra 4 eventi reali di raccolta+carico (18/9 Callao/Azul y Sal, 17/9
# Salvaje), sempre "cut to order": il SET raccolto coincide esattamente con
# il SET consegnato/da consegnare (nessuna eccedenza pre-raccolta, prodotto
# lasciato in piedi finche' non serve). Pesi reali dichiarati da Giulia
# (SET+substrato+germinato, non calcolati da alcun fattore di resa, mai
# ammesso dal sistema -- vedi MOVIMENTO_CARICO_AUTHORITY_FREEZE.md D11/D12):
# Afila 311g/SET, Cilantro 204g/SET.
#
# NOTA IMPORTANTE (vedi handoff/scoperta-tpo-roadmap-2026-09.md, Fatto 21/22):
# questo script carica lo STOCK in GRAM (unico percorso oggi esistente per
# VARIETA). Le CONSEGNE a El Callao/Azul y Sal restano bloccate comunque,
# perche' le righe ordine sono in SET e il writer di consegna richiede la
# STESSA unita' sia sulla riga ordine sia sullo stock -- verificato leggendo
# il codice, nessun percorso di conversione esiste. Questo script NON tenta
# nessuna consegna: registra solo raccolta+carico, dato reale utile a
# prescindere dal gap.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RUN="scripts/commissioning/run_tpo.sh"

raccolta_e_carico() {
  local label="$1" semina="$2" qty_set="$3" grammi="$4" effective_at="$5" \
        corr_racc="$6" idem_racc="$7" corr_car="$8" idem_car="$9" note="${10}" motivo="${11}"

  echo "=== RACCOLTA: $label ($qty_set SET, semina $semina, $effective_at) ==="
  R_OUT=$($RUN raccolta record \
    --semina "$semina" \
    --quantity "$qty_set" \
    --uom SET \
    --effective-at "$effective_at" \
    --notes "$note" \
    --actor 'giulia' \
    --reason "$note" \
    --correlation-id "$corr_racc" \
    --idempotency-key "$idem_racc" \
    --confirm)
  echo "$R_OUT"
  RACCOLTA_ID=$(echo "$R_OUT" | grep '^RACCOLTA_ID=' | cut -d= -f2)
  if [ -z "$RACCOLTA_ID" ]; then
    echo "ERRORE: RACCOLTA_ID non trovato nell'output sopra per $label. Fermo qui." >&2
    exit 1
  fi
  echo "RACCOLTA registrata: $RACCOLTA_ID"

  echo "=== CARICO: $label ($RACCOLTA_ID, ${grammi}g) ==="
  C_OUT=$($RUN movimento carica-raccolta \
    --raccolta "$RACCOLTA_ID" \
    --quantita-pesata "$grammi" \
    --effective-at "$effective_at" \
    --motivo "$motivo" \
    --actor 'giulia' \
    --reason "$motivo" \
    --correlation-id "$corr_car" \
    --idempotency-key "$idem_car" \
    --confirm)
  echo "$C_OUT"
  echo ""
}

raccolta_e_carico \
  "Afila per El Callao" 'SEM-000002' 1 311 '2026-09-18T09:00:00+01:00' \
  'RACCOLTA-2026-09-18-AFILA-CALLAO' 'raccolta-afila-callao-2026-09-18' \
  'CARICO-2026-09-18-AFILA-CALLAO' 'carico-afila-callao-2026-09-18' \
  'Raccolto 1 SET Afila (peso reale con substrato) per consegna a El Callao' \
  'Carico magazzino da raccolta Afila per consegna El Callao'

raccolta_e_carico \
  "Cilantro per Azul y Sal" 'SEM-000001' 1 204 '2026-09-18T09:00:00+01:00' \
  'RACCOLTA-2026-09-18-CILANTRO-AZULYSAL' 'raccolta-cilantro-azulysal-2026-09-18' \
  'CARICO-2026-09-18-CILANTRO-AZULYSAL' 'carico-cilantro-azulysal-2026-09-18' \
  'Raccolto 1 SET Cilantro (peso reale con substrato) per consegna a Azul y Sal' \
  'Carico magazzino da raccolta Cilantro per consegna Azul y Sal'

raccolta_e_carico \
  "Afila per Selvaje" 'SEM-000002' 2 622 '2026-09-17T09:00:00+01:00' \
  'RACCOLTA-2026-09-17-AFILA-SELVAJE' 'raccolta-afila-selvaje-2026-09-17' \
  'CARICO-2026-09-17-AFILA-SELVAJE' 'carico-afila-selvaje-2026-09-17' \
  'Raccolti 2 SET Afila (peso reale con substrato) per consegna a Selvaje del 17/9 (consegna non ancora registrabile: nessun ordine aperto trovato per il cliente)' \
  'Carico magazzino da raccolta Afila per consegna Selvaje del 17/9'

raccolta_e_carico \
  "Cilantro per Selvaje" 'SEM-000001' 1 204 '2026-09-17T09:00:00+01:00' \
  'RACCOLTA-2026-09-17-CILANTRO-SELVAJE' 'raccolta-cilantro-selvaje-2026-09-17' \
  'CARICO-2026-09-17-CILANTRO-SELVAJE' 'carico-cilantro-selvaje-2026-09-17' \
  'Raccolto 1 SET Cilantro (peso reale con substrato) per consegna a Selvaje del 17/9 (consegna non ancora registrabile: nessun ordine aperto trovato per il cliente)' \
  'Carico magazzino da raccolta Cilantro per consegna Selvaje del 17/9'

echo "=== FATTO: 4 raccolte + 4 carichi registrati. Le consegne restano da affrontare a parte (vedi roadmap). ==="
