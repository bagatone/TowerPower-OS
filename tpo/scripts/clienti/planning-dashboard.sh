#!/bin/bash
# Dashboard di pianificazione: prossime consegne e semine prioritarie

set -e

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 1
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd -P)" || exit 1

TODAY="${1:-$(date +%Y-%m-%d)}"

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║              PLANNING DASHBOARD - PROSSIME SEMINE                 ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo
echo "Data riferimento: $TODAY"
echo

# Mappping VARIETA -> LOTTO
declare -A VAR_TO_LOTTO=(
  ["VAR-000001"]="LSE-000014"
  ["VAR-000002"]="LSE-000010"
  ["VAR-000003"]="LSE-000013"
  ["VAR-000004"]="LSE-000001"
  ["VAR-000005"]="LSE-000005"
  ["VAR-000006"]="LSE-000008"
  ["VAR-000007"]="LSE-000007"
  ["VAR-000008"]="LSE-000011"
  ["VAR-000009"]="LSE-000009"
  ["VAR-000010"]="LSE-000012"
  ["VAR-000011"]="LSE-000015"
  ["VAR-000012"]="LSE-000016"
  ["VAR-000013"]="LSE-000017"
  ["VAR-000014"]="LSE-000018"
)

# Stock tracking
declare -A STOCK_LOTTI=(
  ["LSE-000001"]=780
  ["LSE-000005"]=326
  ["LSE-000007"]=1000
  ["LSE-000008"]=1000
  ["LSE-000009"]=240
  ["LSE-000010"]=1000
  ["LSE-000011"]=1000
  ["LSE-000013"]=660
  ["LSE-000014"]=3030
  ["LSE-000015"]=750
  ["LSE-000016"]=740
  ["LSE-000017"]=100
  ["LSE-000018"]=660
)

to_italian_day() {
  case "$1" in
    monday) echo "lunedi" ;;
    tuesday) echo "martedi" ;;
    wednesday) echo "mercoledi" ;;
    thursday) echo "giovedi" ;;
    friday) echo "venerdi" ;;
    saturday) echo "sabato" ;;
    sunday) echo "domenica" ;;
  esac
}

get_dow_en() {
  date -d "$1" +%A 2>/dev/null | tr A-Z a-z || date -jf "%Y-%m-%d" "$1" +%A 2>/dev/null | tr A-Z a-z
}

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                   PROSSIME 7 CONSEGNE ORDINATE                    ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo

# Raccoglimi tutte le consegne nei prossimi 7 giorni
declare -a UPCOMING_ORDERS

for cliente_dir in "$ROOT/clienti"/*; do
  [ ! -d "$cliente_dir" ] || [ "$(basename "$cliente_dir")" = "_templates" ] && continue
  
  cliente_name=$(basename "$cliente_dir")
  ordini_file="$cliente_dir/ordini-ricorrenti.json"
  [ ! -f "$ordini_file" ] && continue
  
  # Estrai prossima_consegna con jq
  if command -v jq &>/dev/null; then
    prossima=$(jq -r '.[0].prossima_consegna // empty' "$ordini_file" 2>/dev/null)
    if [ -n "$prossima" ]; then
      # Converti data a timestamp per sorting
      prossima_ts=$(date -d "$prossima" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$prossima" +%s 2>/dev/null)
      today_ts=$(date -d "$TODAY" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$TODAY" +%s 2>/dev/null)
      
      # Se è entro 7 giorni
      if [ "$((prossima_ts - today_ts))" -le 604800 ] && [ "$((prossima_ts - today_ts))" -ge 0 ]; then
        UPCOMING_ORDERS+=("$prossima|$cliente_name|$ordini_file")
      fi
    fi
  fi
done

# Sort by date
IFS=$'\n' sorted=($(sort <<<"${UPCOMING_ORDERS[*]}"))
unset IFS

for order in "${sorted[@]}"; do
  IFS='|' read -r data cliente file <<< "$order"
  dow=$(get_dow_en "$data")
  dow_it=$(to_italian_day "$dow")
  
  echo "📅 $data ($dow_it) - $cliente"
  
  # Mostra varietà
  if command -v jq &>/dev/null; then
    jq -r '.[0].varieta[] | "   • \(.denominazione) × \(.quantita)"' "$file" 2>/dev/null
  fi
  echo
done

echo
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                      STATO STOCK LOTTI                            ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo

echo "Lotto        | Varietà              | Grammi | Status"
echo "─────────────┼──────────────────────┼────────┼────────────"

# Stock warning se < 300g
for lotto in LSE-000001 LSE-000005 LSE-000007 LSE-000008 LSE-000009 LSE-000010 LSE-000011 LSE-000013 LSE-000014 LSE-000015 LSE-000016 LSE-000017 LSE-000018; do
  grammi=${STOCK_LOTTI[$lotto]:-0}
  
  if [ "$grammi" -lt 300 ]; then
    status="⚠ BASSO"
  elif [ "$grammi" -lt 500 ]; then
    status="⚡ Attenzione"
  else
    status="✓ OK"
  fi
  
  # Estrai varietà dal file stock-lotti.json
  if [ -f "$ROOT/clienti/stock-lotti.json" ]; then
    varieta=$(jq -r ".lotti[] | select(.lotto_id == \"$lotto\") | .denominazione" "$ROOT/clienti/stock-lotti.json" 2>/dev/null || echo "?")
  else
    varieta="?"
  fi
  
  printf "%-12s | %-20s | %6d | %s\n" "$lotto" "$varieta" "$grammi" "$status"
done

echo
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║               AZIONI CONSIGLIATE PER OGGI                         ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo

bash "$ROOT/scripts/clienti/generate_semina_for_orders.sh" "$TODAY" | tail -5

echo
