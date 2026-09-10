#!/bin/bash
# Genera SEMINA automaticamente per ordini ricorrenti in scadenza

set -e

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)" || exit 1

TODAY="${1:-$(date +%Y-%m-%d)}"
echo "=== GENERAZIONE SEMINA ==="
echo "Data riferimento: $TODAY"
echo

# Mapping VARIETA -> LOTTO_SEME
declare -A VAR_TO_LOTTO=(
  ["VAR-000001"]="LSE-000014"  # Afila
  ["VAR-000002"]="LSE-000010"  # Rabano
  ["VAR-000003"]="LSE-000013"  # Cilantro
  ["VAR-000004"]="LSE-000001"  # Mizuna
  ["VAR-000005"]="LSE-000005"  # Hinojo
  ["VAR-000006"]="LSE-000008"  # Basilico
  ["VAR-000007"]="LSE-000007"  # Rucola
  ["VAR-000008"]="LSE-000011"  # Pak Choi
  ["VAR-000009"]="LSE-000009"  # Acetosella
  ["VAR-000010"]="LSE-000012"  # Amaranto
  ["VAR-000011"]="LSE-000015"  # Senape
  ["VAR-000012"]="LSE-000016"  # Cavolo rosso
  ["VAR-000013"]="LSE-000017"  # Girasole
  ["VAR-000014"]="LSE-000018"  # Lenticchia
)

# Converti data a giorno (normalizzato a inglese)
get_dow_en() {
  date -d "$1" +%A 2>/dev/null | tr A-Z a-z || date -jf "%Y-%m-%d" "$1" +%A 2>/dev/null | tr A-Z a-z
}

# Converti inglese a italiano
to_italian_day() {
  case "$1" in
    monday) echo "lunedi" ;;
    tuesday) echo "martedi" ;;
    wednesday) echo "mercoledi" ;;
    thursday) echo "giovedi" ;;
    friday) echo "venerdi" ;;
    saturday) echo "sabato" ;;
    sunday) echo "domenica" ;;
    *) echo "$1" ;;
  esac
}

TODAY_DOW=$(get_dow_en "$TODAY")
TODAY_DOW_IT=$(to_italian_day "$TODAY_DOW")
echo "Giorno di oggi: $TODAY_DOW_IT ($TODAY_DOW)"
echo

ORDINI_TROVATI=0
SEMINA_GENERATE=0

# Scansiona clienti
for cliente_dir in "$ROOT/clienti"/*; do
  if [ ! -d "$cliente_dir" ] || [ "$(basename "$cliente_dir")" = "_templates" ]; then
    continue
  fi

  cliente_name=$(basename "$cliente_dir")
  ordini_file="$cliente_dir/ordini-ricorrenti.json"

  if [ ! -f "$ordini_file" ]; then
    continue
  fi

  echo "Cliente: $cliente_name"

  # Parsing con jq (se disponibile)
  if command -v jq &>/dev/null; then
    while IFS= read -r line; do
      giorno=$(echo "$line" | jq -r '.giorno_settimana' 2>/dev/null)
      stato=$(echo "$line" | jq -r '.stato' 2>/dev/null)
      data_inizio=$(echo "$line" | jq -r '.data_inizio' 2>/dev/null)
      
      if [ "$giorno" = "$TODAY_DOW_IT" ] && [ "$stato" = "attivo" ]; then
        # Verifica data_inizio non è futura
        start_ts=$(date -d "$data_inizio" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$data_inizio" +%s 2>/dev/null)
        today_ts=$(date -d "$TODAY" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$TODAY" +%s 2>/dev/null)
        
        if [ "$today_ts" -ge "$start_ts" ]; then
          ORDINI_TROVATI=$((ORDINI_TROVATI + 1))
          echo "  ✓ Ordine attivo per oggi ($giorno)"
          
          # Estrai VAR-ID
          var_ids=$(echo "$line" | jq -r '.varieta[].var_id' 2>/dev/null)
          for var_id in $var_ids; do
            lotto_seme="${VAR_TO_LOTTO[$var_id]}"
            if [ -n "$lotto_seme" ]; then
              echo "    → SEMINA: $var_id → $lotto_seme"
              SEMINA_GENERATE=$((SEMINA_GENERATE + 1))
            fi
          done
        fi
      fi
    done < <(jq -c '.[]' "$ordini_file" 2>/dev/null)
  else
    echo "  ⚠ jq non disponibile"
  fi
done

echo
echo "=== RISULTATI ==="
echo "Ordini trovati: $ORDINI_TROVATI"
echo "SEMINA da generare: $SEMINA_GENERATE"

if [ $ORDINI_TROVATI -eq 0 ]; then
  echo "ℹ Nessun ordine per oggi"
fi
