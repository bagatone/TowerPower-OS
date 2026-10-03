# BOLLA_DI_CONSEGNA — Freeze (3/10/2026)

## 1. Cosa è

La BOLLA DI CONSEGNA non è una nuova entità commerciale: è il documento PDF
di una CONSEGNA già governata (`tpo.consegne` + `tpo.righe_consegna`,
`public_id CON-######`), con la provenienza di lotto registrata in
`tpo.consumi_lotto` (CONSUMO_LOTTO, vedi `CONSUMO_LOTTO_AUTHORITY_FREEZE.md`).
Il numero della bolla è il `public_id` della CONSEGNA. Una FATTURA continua a
riferirsi a una o più CONSEGNE (`EmitFattura.consegna_ids`): quindi a una o
più bolle. Nessuna modifica a FATTURA.

## 2. Owner Decisions (Matteo, 3/10/2026)

- Output: file PDF salvato in una cartella locale (non vista a schermo).
- Valgono D1–D5 di CONSUMO_LOTTO: FIFO, nessuna bolla retroattiva con codici
  per le consegne storiche, split su più lotti con tutti i codici elencati,
  mai bloccare una consegna per un gap di tracciabilità, giacenza senza
  origine consumata per prima.

## 3. Comando

```text
tpo bolla genera --consegna CON-000012 [--output-dir DIR]
                 [--emittente-file FILE] [--sovrascrivi]
```

- Sola lettura dal database; scrive soltanto il PDF. Nessun `--confirm`.
- Solo per CONSEGNE in stato `CONSEGNATA` (altrimenti errore, nessun file).
- Cartella predefinita `outputs/bolle/` (ignorata da git). File:
  `bolla_CON-######_<cliente>_<AAAA-MM-GG>.pdf`. Non sovrascrive un PDF già
  esistente senza `--sovrascrivi`: una bolla già consegnata al cliente non
  cambia in silenzio.
- Intestazione emittente da `config/bolla_emittente.yaml` (chiave `righe`);
  se assente il PDF riporta solo "Tower Power". Il sistema NON conosce né
  inventa ragione sociale, indirizzo o dati fiscali, né l'indirizzo del
  cliente (non esistono nel database); si stampa `destinazione_fisica` della
  CONSEGNA se presente. `config/bolla_emittente.example.yaml` è il modello.

## 4. Contenuto

Per ogni riga: posizione, varietà, quantità e unità, e sotto i codici
`AAA-GGMM-L` con RACCOLTA di origine, data e quantità esatta (una riga per
lotto se la riga attraversa più lotti). La parte che il registro lotti non
spiega è stampata come "Origine non tracciata - <quantità>", mai con un
codice, con una nota a piè di pagina. Nessun prezzo (la bolla non è una
fattura). Spazi per le firme di ricevente e consegnatario.

## 5. File

- `application/bolla_lettura/` (modelli, porta, servizio, errori)
- `infrastructure/postgresql/bolla_lettura.py` (catena
  righe_consegna → movimenti SCARICO → consumi_lotto → movimenti CARICO →
  raccolte → semine.codice_tracciabilita; un lotto senza codice risolvibile
  non è mai mostrato)
- `infrastructure/pdf/bolla_pdf.py` (reportlab, funzione pura)
- `bootstrap/bolla_lettura.py`, `cli/bolla.py` (import di reportlab pigro:
  un ambiente senza reportlab non rompe gli altri comandi `tpo`)
- `requirements.txt`: aggiunto `reportlab>=4.2,<6`
- Test: `tests/application/test_bolla_lettura.py`,
  `tests/cli/test_bolla_cli.py`,
  `tests/infrastructure/postgresql/test_bolla_lettura_reader.py` (PostgreSQL
  reale), `tests/infrastructure/postgresql/test_consumo_lotto_migration.py`
  (backfill e downgrade della 0036 su PostgreSQL reale).

## 6. Fuori perimetro

- Emissione automatica della bolla alla consegna (oggi è un comando
  esplicito).
- Dati anagrafici/fiscali di emittente e cliente nel database.
- Bolle per CONSEGNE di rettifica con righe negative: compaiono marcate
  "(rettifica)", senza provenienza di lotto.
