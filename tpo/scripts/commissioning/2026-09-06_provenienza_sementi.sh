#!/bin/bash
# Provenienza sementi in magazzino: commissioning SEMENTE + LOTTO_SEME reali,
# generato il 2026-09-06 dal foglio di raccolta dati confermato con l'utente.
# Esegue 19 sacchi (38 comandi). Si ferma al primo errore (set -e): rivedi
# l'output, correggi se necessario, e rilancia (i comandi gia' andati a buon
# fine sono un COMPATIBLE_REPLAY sicuro se rieseguiti invariati).
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)"

echo '--- [1/19] Mizuna Red (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Mizuna Red' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Mizuna Red' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-01-mizuna-red-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Mizuna Red' \
  --manufacturer-lot-number 'GOL 0945/BM7499' \
  --received-date '2026-06-30' \
  --expiry-date '2027-05-31' \
  --initial-quantity '780' \
  --unit GRAM \
  --anomaly 'Residuo di 780 g dichiarato dal proprietario (somma di due misurazioni: 230 g + 550 g) su un sacco originale da 1 kg.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Mizuna Red' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-01-mizuna-red-2026-09-06' \
  --confirm

echo '--- [2/19] Pisello Utrillo (Bayer/Seminis) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Bayer/Seminis' \
  --referenza-commerciale 'Pisello Utrillo' \
  --marca 'Seminis (Vegetables by Bayer)' \
  --formato '5 kg' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Pisello Utrillo' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-02-pisello-utrillo-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Bayer/Seminis' \
  --seed-commercial-reference 'Pisello Utrillo' \
  --manufacturer-lot-number 'Batch 0603611240 / Lot 10.92.869' \
  --received-date '2026-04-15' \
  --initial-quantity '4900' \
  --unit GRAM \
  --anomaly 'Sacco da 5 kg, residuo attuale dichiarato dal proprietario: 4,900 kg. TSW 326,086 g; passaporto fitosanitario UE C 0242155796, B HU-130761, D HU (Szelei ut Farmos, HU 2765). Varieta'\'' non verra'\'' piu'\'' riacquistata: non adatta alla coltivazione di microgreens.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Pisello Utrillo' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-02-pisello-utrillo-2026-09-06' \
  --confirm

echo '--- [3/19] Albahaca (Verde Microgreens) (Intersemillas) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Intersemillas' \
  --referenza-commerciale 'Albahaca (Verde Microgreens)' \
  --formato '1 kg' \
  --trattamento 'Sin tratamiento' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Albahaca (Verde Microgreens)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-03-albahaca-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Intersemillas' \
  --seed-commercial-reference 'Albahaca (Verde Microgreens)' \
  --manufacturer-lot-number 'MG-00446' \
  --received-date '2026-06-30' \
  --initial-quantity '850' \
  --unit GRAM \
  --anomaly 'Etichetta riporta data di analisi Giugno 2026 (non scadenza). Nome botanico presunto (Ocimum basilicum), non riportato in etichetta. Operador ES17461319.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Albahaca (Verde Microgreens)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-03-albahaca-2026-09-06' \
  --confirm

echo '--- [4/19] Rucula (Intersemillas) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Intersemillas' \
  --referenza-commerciale 'Rucula' \
  --formato '1 kg' \
  --trattamento 'Sin tratamiento' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Rucula' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-04-rucula-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Intersemillas' \
  --seed-commercial-reference 'Rucula' \
  --manufacturer-lot-number 'MG-00479' \
  --received-date '2026-06-30' \
  --initial-quantity '880' \
  --unit GRAM \
  --anomaly 'Etichetta riporta data di analisi Giugno 2026 (non scadenza). Nome botanico presunto (Eruca sativa). Operador ES17461319.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Rucula' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-04-rucula-2026-09-06' \
  --confirm

echo '--- [5/19] Hinojo (Intersemillas) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Intersemillas' \
  --referenza-commerciale 'Hinojo' \
  --formato '500 g' \
  --trattamento 'Sin tratamiento' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Hinojo' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-05-hinojo-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Intersemillas' \
  --seed-commercial-reference 'Hinojo' \
  --manufacturer-lot-number 'MG-00040' \
  --received-date '2026-06-30' \
  --initial-quantity '326' \
  --unit GRAM \
  --anomaly 'Etichetta riporta data di analisi Giugno 2026 (non scadenza). Nome botanico presunto (Foeniculum vulgare). Operador ES17461319.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Hinojo' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-05-hinojo-2026-09-06' \
  --confirm

echo '--- [6/19] Pak Choi (Intersemillas) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Intersemillas' \
  --referenza-commerciale 'Pak Choi' \
  --formato '1 kg' \
  --trattamento 'Sin tratamiento' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Pak Choi' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-06-pak-choi-inter-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Intersemillas' \
  --seed-commercial-reference 'Pak Choi' \
  --manufacturer-lot-number 'MG-00411' \
  --received-date '2026-06-30' \
  --initial-quantity '890' \
  --unit GRAM \
  --anomaly 'Etichetta riporta data di analisi Giugno 2026 (non scadenza). Nome botanico presunto (Brassica rapa chinensis). Operador ES17461319.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Pak Choi' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-06-pak-choi-inter-2026-09-06' \
  --confirm

echo '--- [7/19] Rocket Cultivated (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Rocket Cultivated' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Rocket Cultivated' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-07-rocket-cultivated-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Rocket Cultivated' \
  --manufacturer-lot-number 'GOL 0963/BM7478' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '1000' \
  --unit GRAM \
  --anomaly 'Sacco pieno/non aperto: residuo coincide col peso di confezione originale.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Rocket Cultivated' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-07-rocket-cultivated-2026-09-06' \
  --confirm

echo '--- [8/19] Basil Green (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Basil Green' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Basil Green' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-08-basil-green-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Basil Green' \
  --manufacturer-lot-number 'GOL 0903/BM7517' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '1000' \
  --unit GRAM \
  --anomaly 'Sacco pieno/non aperto. Cifra centrale del codice lotto poco leggibile in etichetta (assunta '\''0903'\'' per coerenza con la numerazione GOL); da confermare sul sacco fisico.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Basil Green' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-08-basil-green-2026-09-06' \
  --confirm

echo '--- [9/19] Sorrel Red Veined (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Sorrel Red Veined' \
  --marca 'Golinucci Organic' \
  --formato '250 g' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Sorrel Red Veined' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-09-sorrel-red-veined-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Sorrel Red Veined' \
  --manufacturer-lot-number 'GOL 0027/BA2426' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '240' \
  --unit GRAM \
  --anomaly 'Residuo di 240 g dichiarato dal proprietario (indicato inizialmente con l'\''abbreviazione "ACE") su un sacco originale da 250 g.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Sorrel Red Veined' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-09-sorrel-red-veined-2026-09-06' \
  --confirm

echo '--- [10/19] Radish Vulcano (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Radish Vulcano' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Radish Vulcano' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-10-radish-vulcano-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Radish Vulcano' \
  --manufacturer-lot-number 'GOL 0961/BM7476' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '1000' \
  --unit GRAM \
  --anomaly 'Sacco pieno/non aperto: residuo coincide col peso di confezione originale.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Radish Vulcano' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-10-radish-vulcano-2026-09-06' \
  --confirm

echo '--- [11/19] Pak Choi White (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Pak Choi White' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Pak Choi White' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-11-pak-choi-white-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Pak Choi White' \
  --manufacturer-lot-number 'GOL 0952/BM7497' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '1000' \
  --unit GRAM \
  --anomaly 'Sacco pieno/non aperto: residuo coincide col peso di confezione originale.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Pak Choi White' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-11-pak-choi-white-2026-09-06' \
  --confirm

echo '--- [12/19] Amaranth Red (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Amaranth Red' \
  --marca 'Golinucci Organic' \
  --formato '500 g' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Amaranth Red' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-12-amaranth-red-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Amaranth Red' \
  --manufacturer-lot-number 'GOL 0003/BA7322' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '440' \
  --unit GRAM \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"UNKNOWN"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Amaranth Red' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-12-amaranth-red-2026-09-06' \
  --confirm

echo '--- [13/19] Coriander Split (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Coriander Split' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Coriander Split' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-13-coriander-split-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Coriander Split' \
  --manufacturer-lot-number 'GOL 0927/BM7442' \
  --received-date '2026-07-31' \
  --expiry-date '2027-07-31' \
  --initial-quantity '660' \
  --unit GRAM \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"UNKNOWN"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Coriander Split' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-13-coriander-split-2026-09-06' \
  --confirm

echo '--- [14/19] Pea Green Affila (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Pea Green Affila' \
  --marca 'Golinucci Organic' \
  --formato '5 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Pea Green Affila' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-14-pea-green-affila-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Pea Green Affila' \
  --manufacturer-lot-number 'GOL 0708/BM736' \
  --received-date '2026-06-30' \
  --expiry-date '2027-05-31' \
  --initial-quantity '3030' \
  --unit GRAM \
  --anomaly 'Residuo di 3,030 kg dichiarato dal proprietario (somma di due misurazioni: 2,030 kg + 1 kg) su un sacco originale da 5 kg, destinato a germogli (sprouts) e non a microgreens.' \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Pea Green Affila' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-14-pea-green-affila-2026-09-06' \
  --confirm

echo '--- [15/19] Mustard White (Golinucci Organic) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Golinucci Organic' \
  --referenza-commerciale 'Mustard White' \
  --marca 'Golinucci Organic' \
  --formato '1 kg' \
  --certificazioni 'IT-BIO-007, Bioagricert' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Mustard White' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-15-mustard-white-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Golinucci Organic' \
  --seed-commercial-reference 'Mustard White' \
  --manufacturer-lot-number 'GOL 0949/BM7464' \
  --received-date '2026-06-30' \
  --expiry-date '2027-05-31' \
  --initial-quantity '750' \
  --unit GRAM \
  --provenance '{"seed_supplier":"LABEL_OR_PACKAGE","seed_commercial_reference":"LABEL_OR_PACKAGE","manufacturer_lot_number":"LABEL_OR_PACKAGE","received_date":"OWNER_AUTHORIZED","expiry_date":"LABEL_OR_PACKAGE","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"UNKNOWN"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Mustard White' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-15-mustard-white-2026-09-06' \
  --confirm

echo '--- [16/19] Col Roja (Cavolo rosso) (Hyfarm) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Hyfarm' \
  --referenza-commerciale 'Col Roja (Cavolo rosso)' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Col Roja (Cavolo rosso)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-16-col-roja-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Hyfarm' \
  --seed-commercial-reference 'Col Roja (Cavolo rosso)' \
  --manufacturer-lot-number 'N/D' \
  --received-date '2026-01-15' \
  --initial-quantity '740' \
  --unit GRAM \
  --anomaly 'Nessuna etichetta disponibile: fornitore, nome e quantita'\'' residua dichiarati direttamente dal proprietario. Nessun codice lotto, formato originale, data di scadenza o certificazione bio disponibili. Specie presunta: Brassica oleracea.' \
  --provenance '{"seed_supplier":"OWNER_AUTHORIZED","seed_commercial_reference":"OWNER_AUTHORIZED","manufacturer_lot_number":"OWNER_AUTHORIZED","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Col Roja (Cavolo rosso)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-16-col-roja-2026-09-06' \
  --confirm

echo '--- [17/19] Girasoli (Sunflower) (Hyfarm) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Hyfarm' \
  --referenza-commerciale 'Girasoli (Sunflower)' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Girasoli (Sunflower)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-17-girasoli-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Hyfarm' \
  --seed-commercial-reference 'Girasoli (Sunflower)' \
  --manufacturer-lot-number 'N/D' \
  --received-date '2026-01-15' \
  --initial-quantity '100' \
  --unit GRAM \
  --anomaly 'Nessuna etichetta disponibile: fornitore, nome e quantita'\'' residua dichiarati direttamente dal proprietario. Nessun codice lotto, formato originale, data di scadenza o certificazione bio disponibili. Specie presunta: Helianthus annuus.' \
  --provenance '{"seed_supplier":"OWNER_AUTHORIZED","seed_commercial_reference":"OWNER_AUTHORIZED","manufacturer_lot_number":"OWNER_AUTHORIZED","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Girasoli (Sunflower)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-17-girasoli-2026-09-06' \
  --confirm

echo '--- [18/19] Lenticchie (Lentils) (Hyfarm) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Hyfarm' \
  --referenza-commerciale 'Lenticchie (Lentils)' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Lenticchie (Lentils)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-18-lenticchie-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Hyfarm' \
  --seed-commercial-reference 'Lenticchie (Lentils)' \
  --manufacturer-lot-number 'N/D' \
  --received-date '2026-01-15' \
  --initial-quantity '660' \
  --unit GRAM \
  --anomaly 'Nessuna etichetta disponibile: fornitore, nome e quantita'\'' residua dichiarati direttamente dal proprietario. Nessun codice lotto, formato originale, data di scadenza o certificazione bio disponibili. Specie presunta: Lens culinaris.' \
  --provenance '{"seed_supplier":"OWNER_AUTHORIZED","seed_commercial_reference":"OWNER_AUTHORIZED","manufacturer_lot_number":"OWNER_AUTHORIZED","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Lenticchie (Lentils)' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-18-lenticchie-2026-09-06' \
  --confirm

echo '--- [19/19] Rabano (Radish) - Hyfarm (Hyfarm) ---'
scripts/commissioning/run_tpo.sh semente commission \
  --fornitore 'Hyfarm' \
  --referenza-commerciale 'Rabano (Radish) - Hyfarm' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning SEMENTE per Rabano (Radish) - Hyfarm' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'semente-19-rabano-hyfarm-2026-09-06' \
  --confirm

scripts/commissioning/run_tpo.sh seed-lot commission \
  --seed-supplier 'Hyfarm' \
  --seed-commercial-reference 'Rabano (Radish) - Hyfarm' \
  --manufacturer-lot-number 'N/D' \
  --received-date '2026-01-15' \
  --initial-quantity '50' \
  --unit GRAM \
  --anomaly 'Nessuna etichetta disponibile. Specie confermata dal proprietario come ravanello (rabano), stessa VARIETA'\'' commerciale di Radish Vulcano (Golinucci) ma lotto/fornitore distinto. Nessun nome varieta'\'' specifico, formato originale, codice lotto o data di scadenza disponibili.' \
  --provenance '{"seed_supplier":"OWNER_AUTHORIZED","seed_commercial_reference":"OWNER_AUTHORIZED","manufacturer_lot_number":"OWNER_AUTHORIZED","received_date":"OWNER_AUTHORIZED","expiry_date":"UNKNOWN","initial_quantity":"OWNER_AUTHORIZED","unit":"OWNER_AUTHORIZED","anomaly":"OWNER_AUTHORIZED"}' \
  --actor 'matteo' \
  --reason 'Provenienza sementi in magazzino - commissioning LOTTO_SEME per Rabano (Radish) - Hyfarm' \
  --correlation-id 'PROV-SEMENTI-2026-09-06' \
  --idempotency-key 'seed-lot-19-rabano-hyfarm-2026-09-06' \
  --confirm

echo 'FATTO: 19 sacchi commissionati (SEMENTE + LOTTO_SEME).'
