# PROGRAMMA_FORNITURA — SOSPENSIONE E RIATTIVAZIONE (PROPOSTA)

**Stato:** PROPOSTA — in attesa di approvazione owner. Non introduce alcuna
autorità né autorizza implementazione fino ad approvazione esplicita.
**Ambito:** chiude il gap operativo lasciato aperto da `PROGRAMMI_FORNITURA.md`
(stato SOSPESO definito ma nessun comando applicativo lo governa oggi).
**Origine:** conversazione Owner del 2026-09-10.

## 1. Situazione attuale (verificata sul codice reale)

- `PROGRAMMI_FORNITURA.md` (Freeze v1.0) definisce tre stati iniziali per
  PROGRAMMA_FORNITURA: ATTIVO, SOSPESO, TERMINATO.
- `src/tpo_core/domain/states.py` e
  `application/fornitura_ordini_consegne_lettura/models.py`
  (`STATI_PROGRAMMA_FORNITURA_AMMESSI`) riconoscono già SOSPESO come valore
  ammesso.
- Non esiste alcun modulo applicativo di scrittura per PROGRAMMA_FORNITURA
  (`src/tpo_core/application/` non ha una cartella dedicata di scrittura):
  l'unico punto che scrive righe PROGRAMMA_FORNITURA con `--state SOSPESO` è
  `cli/main.py` sotto `onboarding supply-program` /
  `onboarding correct-never-effective-supply-program` — comandi di
  commissioning/bootstrap per popolare dati iniziali, non un'autorità
  operativa per sospendere un programma già ATTIVO in produzione.
- `scheduling/engine.py:120` salta già le righe non ATTIVO — un PROGRAMMA_FORNITURA
  SOSPESO smette quindi automaticamente di generare nuovi ORDINI, senza
  bisogno di modifiche allo Scheduling Engine.
- Non esiste alcun campo per una data di ripresa informativa su
  `domain/entities/programma_fornitura.py`: andrebbe aggiunto.

In sintesi: SOSPESO esiste come valore di stato "sulla carta", ma manca
completamente il comando applicativo governato che lo attivi/disattivi in
modo controllato su un programma già in vita.

## 2. Owner Decisions (2026-09-10)

- **D1 — Data di ripresa: APPROVATA.** La sospensione registra una data di
  ripresa prevista, puramente informativa. Non innesca alcuna riattivazione
  automatica.
- **D2 — Ordini già generati nella finestra sospesa: APPROVATA.** Restano
  come sono (`PROGRAMMI_FORNITURA.md`: "Gli ORDINI già generati rimangono
  immutabili" — invariato, nessuna eccezione). Quelli che si vogliono
  trattare come regalie/campioni vengono segnalati sulla RACCOLTA collegata,
  non sull'ORDINE: vedi proposta separata
  `RACCOLTA_DESTINAZIONE_PREVISTA_CORREZIONE_PROPOSTA.md`.
- **D3 — Riattivazione: APPROVATA.** Sempre un comando manuale esplicito.
  Nessuna schedulazione automatica alla data di ripresa: quella data resta un
  promemoria per l'operatore, mai un trigger.

## 3. Modello proposto

Due nuovi comandi applicativi governati, simmetrici a
`raccolta registra`/`raccolta correggi`:

### `SospendiProgrammaFornitura`

- Input: `programma_id`, `data_ripresa_prevista` (opzionale — può restare
  NULL se non si sa ancora quando si riprenderà), `actor`, `reason`,
  `correlation_id`.
- Precondizione: il programma deve essere `ATTIVO` (fallisce chiuso
  altrimenti — coerente con "ogni CLIENTE possiede un solo PROGRAMMA_FORNITURA
  attivo").
- Effetto: transizione di stato `ATTIVO → SOSPESO`. Lo Scheduling Engine
  smette di generare nuovi ORDINI da quel momento (nessuna modifica
  richiesta al motore, già verificato).
- Un evento `tpo.audit_eventi` per la transizione.

### `RiattivaProgrammaFornitura`

- Input: `programma_id`, `actor`, `reason`, `correlation_id`.
- Precondizione: il programma deve essere `SOSPESO`.
- Effetto: transizione `SOSPESO → ATTIVO`. Sempre esplicito, mai automatico
  (D3) — la presenza/assenza o il superamento di `data_ripresa_prevista` non
  influenza in alcun modo l'esecuzione del comando.
- Un evento `tpo.audit_eventi` per la transizione.

### Campo nuovo

- `tpo.programmi_fornitura.data_ripresa_prevista DATE NULL` — puramente
  informativo, non letto da alcun Engine, esposto in lettura
  (`fornitura_ordini_consegne_lettura`) per mostrarlo in UI/CLI.

## 4. Guardie proposte

- Vietata la riattivazione automatica basata su `data_ripresa_prevista` in
  qualunque forma (cron, Engine, trigger DB).
- Vietata la sospensione di un programma non `ATTIVO` o la riattivazione di
  un programma non `SOSPESO` (fallisce chiuso).
- Nessuna modifica allo Scheduling Engine: la sospensione agisce
  esclusivamente sullo stato del Register, coerente con "gli Engine leggono
  i Register e non li modificano".
- Gli ORDINI già generati restano immutabili in ogni caso (nessuna eccezione
  per finestre sospese).

## 5. Fuori scope

- Notifiche o promemoria automatici basati su `data_ripresa_prevista` (oggi
  è un campo puramente informativo/di lettura).
- Qualunque azione sugli ORDINI/CONSEGNE già generati durante la sospensione:
  quello è oggetto della proposta RACCOLTA separata.
- UI.

## 6. Prossimo passo

In attesa di approvazione owner. Se approvata: nuovo modulo applicativo
(comando, service, writer PostgreSQL, migrazione per la colonna, CLI, test),
stesso standard di copertura già raggiunto per RACCOLTA V1.
