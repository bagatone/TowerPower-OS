# PROGRAMMA_FORNITURA — SOSPENSIONE E RIATTIVAZIONE AUTHORITY FREEZE V1

**Stato:** OWNER-APPROVED ARCHITECTURE FREEZE (Owner Decision 2026-09-10).
Implementazione completata 2026-09-17.
**Ambito:** chiude il gap operativo lasciato aperto da `PROGRAMMI_FORNITURA.md`
(stato SOSPESO definito, nessun comando applicativo lo governava).
**Origine:** `PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_PROPOSTA.md`,
Owner Decisions D1/D2/D3, conversazione Owner 2026-09-10.
**Baseline:** branch `sprint-4.4-production-planning`.

## 1. Scopo

`PROGRAMMI_FORNITURA.md` (Freeze v1.0) definisce tre stati per
PROGRAMMA_FORNITURA: ATTIVO, SOSPESO, TERMINATO. SOSPESO esisteva solo "sulla
carta" — riconosciuto da `domain/states.py` e da
`STATI_PROGRAMMA_FORNITURA_AMMESSI`, ma nessun comando applicativo governato
lo attivava su un programma già in vita (l'unico scrittore era
`onboarding supply-program`, un comando di commissioning/bootstrap, non
un'autorità operativa). Questo Freeze introduce quell'autorità.

## 2. Situazione verificata sul codice reale (proposta §1)

- `scheduling/engine.py` salta già le righe non ATTIVO: un PROGRAMMA_FORNITURA
  SOSPESO smette automaticamente di generare nuovi ORDINI, senza alcuna
  modifica allo Scheduling Engine.
- Nessun campo per una data di ripresa informativa esisteva su
  `domain/entities/programma_fornitura.py`.
- L'unico precedente strutturale per scrivere una nuova riga
  `programmi_fornitura_versioni` su un programma esistente era
  `CorrectNeverEffectiveSupplyProgramVersion` (`application/onboarding`) —
  verificato e scartato come modello diretto (§4): quel meccanismo corregge
  una versione **mai divenuta effettiva** (`voided_at`/`replacement_version_id`,
  richiede che la versione non abbia ancora superato `valida_dal`), mentre
  Sospendi/Riattiva operano su un programma **già effettivo, in produzione**
  (ATTIVO o SOSPESO). I due meccanismi restano distinti e non si sostituiscono
  a vicenda.

## 3. Principio adottato

Sospensione e riattivazione sono transizioni di stato **in avanti** sul
programma già effettivo, non correzioni di un errore storico. Ogni
transizione chiude la versione corrente (`valida_al = effective_at`) e apre
una nuova versione (`numero_versione + 1`, `valida_dal = effective_at`,
`valida_al = NULL`), mai una riscrittura in place della versione esistente —
coerente con il modello bitemporale SCD-2 già in vigore su
`tpo.programmi_fornitura_versioni` (`order_commit_schema`, migrazione
`20260806_0002`).

## 4. Modello approvato

### `SospendiProgrammaFornitura` (ATTIVO → SOSPESO)

- Input: `programma_id`, `expected_numero_versione`, `effective_at`,
  `data_ripresa_prevista` (opzionale — D1), `authority`
  (`actor`/`reason`/`correlation_id`/`idempotency_key`).
- Precondizioni (fail-closed): il programma deve esistere ed avere una
  versione corrente; `expected_numero_versione` deve coincidere con la
  versione corrente (optimistic concurrency); il programma deve essere
  `ATTIVO`; `effective_at` deve essere successivo a `valida_dal` della
  versione corrente (nessuna regressione temporale).
- Effetto: chiude la versione ATTIVO corrente, apre una nuova versione
  SOSPESO con le stesse righe/giorni copiati (§5); scrive
  `data_ripresa_prevista` sull'header mutabile `tpo.programmi_fornitura`
  (non sulla versione — §6); un evento `tpo.audit_eventi` `STATE_TRANSITION`.

### `RiattivaProgrammaFornitura` (SOSPESO → ATTIVO)

- Input: `programma_id`, `expected_numero_versione`, `effective_at`,
  `authority`. **Nessun campo legato a `data_ripresa_prevista`** — D3: sempre
  esplicito, mai derivato o automatico.
- Precondizioni: come sopra, con `SOSPESO` al posto di `ATTIVO`.
- Effetto: chiude la versione SOSPESO corrente, apre una nuova versione
  ATTIVO con le stesse righe/giorni copiati; un evento `tpo.audit_eventi`
  `STATE_TRANSITION`.
- Vincolo ereditato invariato: `uq_programmi_fornitura_versioni_cliente_attivo`
  (un solo PROGRAMMA_FORNITURA ATTIVO per CLIENTE) si applica anche qui —
  riattivare un programma il cui CLIENTE possiede già un altro programma
  ATTIVO fallisce chiuso (`ProgrammaFornituraClienteGiaAttivoError`).

### Campo nuovo

- `tpo.programmi_fornitura.data_ripresa_prevista DATE NULL` — vive
  sull'header, non su una versione: è un promemoria operativo che sopravvive
  alla transizione di stato stessa, non un fatto del periodo di validità di
  una specifica versione. Puramente informativo (D1): non letto da alcun
  Engine, mai un trigger. Esposto in lettura
  (`fornitura_ordini_consegne_lettura`).

## 5. Copia di righe e giorni sulla nuova versione

`righe_programma_fornitura`/`righe_programma_giorni` sono FK a uno specifico
`programma_versione_id` con `onupdate=RESTRICT, ondelete=RESTRICT`: nessun
repointing possibile. Ogni transizione (sospendi o riattiva) copia
integralmente le righe e i relativi giorni dalla versione chiusa alla nuova
versione, nella stessa transazione atomica del cambio di stato — le righe
non cambiano di contenuto, cambia solo la versione a cui appartengono.

## 6. Idempotenza — differenza deliberata rispetto a RACCOLTA

A differenza di RACCOLTA (fatti append-only, mai riusati: la reservation
table RACCOLTA impone unicità su `programma_fornitura_id`-equivalente), lo
stesso PROGRAMMA_FORNITURA può essere sospeso e riattivato **più volte** nel
corso della sua vita, con idempotency key diverse ogni volta. Le due tabelle
di reservation (`programma_fornitura_sospendi_requests`,
`programma_fornitura_riattiva_requests`, separate per non mischiare la
semantica di idempotenza tra i due comandi, come già per
`raccolta_recording_requests`/`raccolta_correzione_requests`) impongono
unicità **solo** su `(operation_scope, idempotency_key)`, mai su
`programma_fornitura_id` da solo — scelta di design esplicita, non
un'omissione.

Il risultato committed è ancorato a una riga versione reale tramite FK
composita `(programma_fornitura_id, result_numero_versione)` →
`programmi_fornitura_versioni(programma_fornitura_id, numero_versione)`
(già `UNIQUE` via `uq_programmi_fornitura_versioni_numero`), storicamente
immutabile anche dopo transizioni successive.

**Sottigliezza di replay-safety:** `data_ripresa_prevista` vive sull'header
mutabile, quindi può essere sovrascritto da una sospensione **successiva**
(nuovo ciclo, altra idempotency key). Non è sicuro ricostruire il risultato
di un replay leggendo il valore corrente dell'header. La reservation row di
`programma_fornitura_sospendi_requests` denormalizza quindi
`result_data_ripresa_prevista` al momento del commit: il replay legge sempre
il valore che fu effettivamente committed per **quella** idempotency key, mai
il valore corrente (eventualmente più recente) dell'header. `effective_at` e
`stato` restano invece sicuri da ricostruire via join alla versione storica,
poiché `valida_dal`/`stato` di una versione non cambiano mai una volta
scritti (solo `valida_al` cambia, quando la versione viene successivamente
superata).

## 7. Owner Decisions (2026-09-10) — tutte APPROVATA

- **D1 — Data di ripresa:** puramente informativa, mai un trigger di
  riattivazione automatica.
- **D2 — Ordini già generati nella finestra sospesa:** restano immutabili,
  nessuna eccezione (`PROGRAMMI_FORNITURA.md`, invariato). Il trattamento
  come regalie/campioni passa da RACCOLTA (`destinazione_prevista`,
  `RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` §11), non da questo boundary.
- **D3 — Riattivazione:** sempre un comando manuale esplicito. Nessuna
  schedulazione automatica alla data di ripresa.

## 8. Guardie permanenti

- Vietata la sospensione di un programma non `ATTIVO` o la riattivazione di
  un programma non `SOSPESO` (fail-closed,
  `ProgrammaFornituraStateIneligibleError`).
- Vietata qualunque riattivazione automatica basata su
  `data_ripresa_prevista`, in qualunque forma (cron, Engine, trigger DB).
- Nessuna modifica allo Scheduling Engine: la transizione agisce
  esclusivamente sullo stato del Register.
- Gli ORDINI già generati restano immutabili in ogni caso.
- Vietato introdurre un vincolo di unicità su `programma_fornitura_id` da
  solo nelle tabelle di reservation (§6) — romperebbe la possibilità di
  cicli multipli di sospensione/riattivazione nel tempo.
- Vietata la ricostruzione di un replay di `SospendiProgrammaFornitura` a
  partire dal valore corrente dell'header `data_ripresa_prevista`: deve
  sempre usare il valore denormalizzato sulla reservation row (§6).

## 9. Fuori scope

- Notifiche o promemoria automatici basati su `data_ripresa_prevista`.
- Qualunque azione sugli ORDINI/CONSEGNE già generati durante la sospensione.
- UI/gestionale.

## 10. Copertura di test raggiunta

Stesso standard di RACCOLTA V1: dominio (`tests/domain/test_programma_fornitura.py`),
applicativo (`tests/application/test_programma_fornitura_sospensione.py` —
validazione comandi, distinzione hash sospendi/riattiva, service dispatch),
integrazione contro PostgreSQL reale
(`tests/integration/postgresql/test_programma_fornitura_sospensione.py` —
transizioni, copia righe/giorni, rifiuti tipizzati, idempotenza incluso il
caso di replay-safety di §6, cicli multipli, vincolo cliente-attivo su
riattiva, concorrenza, audit trail), migrazione
(`tests/infrastructure/postgresql/test_programma_fornitura_sospensione_migration.py`
— head lineare, pattern offline-mode, contenuto, assenza del vincolo di
unicità vietato da §8).

## 11. Prossimo passo

Freeze approvato e implementato. `AUTHORITY_REGISTRY.yaml` può essere
aggiornato a implementazione completata quando si estenderà la voce
`PROGRAMMA_FORNITURA` con un test di completezza dedicato (non mandato dai
test esistenti, che verificano solo `REQUIRED_FIELDS` generici per lo stile
`concepts:` — verificato, nessun aggiornamento obbligatorio da questo
Freeze).
