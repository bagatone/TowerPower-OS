# RACCOLTA / HARVEST AUTHORITY FREEZE V1

**Stato:** OWNER-APPROVED ARCHITECTURE FREEZE
**Ambito:** Sprint 5.13, registrazione autorevole delle RACCOLTE
**Prior-art gate:** PRIOR ART REVIEW PASSED

## 1. Scopo e autorità

RACCOLTA è il fatto fisico immutabile che registra una quantità realmente
raccolta da una specifica SEMINA. Questo Freeze riconcilia il precedente
`RACCOLTE.md`, il Register storico, lo schema PostgreSQL esistente, il Core
Domain e la Semina Traceability Authority. Le decisioni qui contenute
prevalgono sulle regole predecessore incompatibili per RACCOLTA V1.

RACCOLTA resta distinta da SEMINA, lifecycle, STOCK, MOVIMENTO_MAGAZZINO,
ASSEGNAZIONE, CONSEGNA e documentazione commerciale.

## 2. Identità

```text
type     = RaccoltaId
format   = RAC-[0-9]{6,}
prefix   = RAC
sequence = RACCOLTA_ID
```

`RACCOLTA_ID` appartiene a `tpo.id_sequences`. Il writer deve allocarla mediante
row lock nella stessa transazione della registrazione. L'identità è unica,
permanente e immutabile. Un rollback non consuma il valore; un replay
compatibile restituisce lo stesso `RAC-*`. Nessuna identità Harvest alternativa
è ammessa.

## 3. Cardinalità e lifecycle

```text
SEMINA 1 -> RACCOLTA 0..N
RACCOLTA N -> SEMINA 1
```

Una RACCOLTA può essere registrata soltanto quando la SEMINA origine è
`PRONTA_ALLA_RACCOLTA`. Ogni altro stato fallisce chiuso. Sono ammesse più
RACCOLTE parziali mentre la SEMINA resta `PRONTA_ALLA_RACCOLTA`.

La registrazione non transiziona e non chiude automaticamente la SEMINA, non
scrive eventi lifecycle e non altera il suo storico. La chiusura resta un
comando esplicito della Semina Lifecycle Event Authority.

## 4. Quantità e unità

La quantità è positiva, usa `numeric(20,6)` e ha come unica UOM V1 `SET`.
Quantità frazionarie, incluso `0.5 SET`, sono valide. Il significato operativo
`1 SET = 4 trays` non introduce `TRAY` come seconda UOM RACCOLTA.

## 5. Autorità temporale

`effective_at` è l'istante fisico e persiste in
`tpo.raccolte.data_raccolta`. `recorded_at` è l'istante di persistenza e
persiste in `tpo.raccolte.created_at`.

Sono timestamp aware; l'orario operativo canonico è `Atlantic/Canary` e
PostgreSQL usa `timestamptz`. La data civile locale può essere derivata da
`effective_at`, ma non è una seconda autorità scrivibile.

## 6. Tracciabilità

```text
RAC-*       = identità dell'evento Harvest
SEM-*       = identità tecnica del gruppo fisico di produzione
AAA-GGMM-L  = codice di origine fisica autorevole della SEMINA
```

RACCOLTA conserva il riferimento permanente alla SEMINA. La creazione fallisce
chiusa se la SEMINA non possiede una tracciabilità canonica valida. In V1
RACCOLTA non persiste una copia autorevole di `AAA-GGMM-L`: result, CLI e audit
possono esporla leggendo la SEMINA, che resta l'unica autorità.

Sono vietati `LOTTO_PRODUZIONE`, una seconda identità produttiva e un secondo
codice di tracciabilità. RACCOLTE multiple della stessa SEMINA conservano la
medesima origine.

## 7. Immutabilità e correzioni

RACCOLTA è append-only. Dopo la creazione:

```text
UPDATE = FORBIDDEN
DELETE = FORBIDDEN
```

L'implementazione deve imporre il vincolo anche nel database. Questo supersede
esplicitamente la regola precedente che consentiva di eliminare una
registrazione quando l'evento fisico non era avvenuto.

Quantità, SEMINA o `effective_at` errati e gli eventi inesistenti saranno
corretti in futuro mediante un'autorità collegata di correction/reversal/void,
senza riscrivere o cancellare l'originale. L'implementazione è DEFERRED e fuori
dallo Sprint 5.13.

## 8. Idempotenza e concorrenza

Il comando richiede una request identity immutabile. La persistenza dedicata
segue la convenzione `tpo.raccolta_recording_requests`.

- stessa request identity e stesso canonical payload: `COMPATIBLE_REPLAY` e
  restituzione dello stesso `RAC-*`;
- stessa request identity e payload diverso: typed conflict, nessuna mutazione;
- richieste identiche concorrenti: convergono su una sola RACCOLTA;
- richieste valide distinte: ricevono identità `RAC-*` distinte.

Request reservation, lock/allocazione identità, insert RACCOLTA, audit e
request completion formano una sola transazione PostgreSQL atomica. Il
repository non esegue retry autonomi.

## 9. Audit e actor

Ogni creazione produce esattamente un evento in `tpo.audit_eventi`, con actor,
reason, request/correlation identity, `RAC-*`, `SEM-*`, codice di tracciabilità
esposto, quantità/UOM, `effective_at` e `recorded_at`.

Actor, reason e request/correlation identity provengono dall'authority context
Core. Il campo legacy `operatore` non è una seconda identità. Può ricevere
soltanto un display derivato dall'actor canonico oppure restare NULL; nessun
master Operatore appartiene allo Sprint 5.13.

## 10. Destinazione e qualità

`destinazione_prevista` non è ASSEGNAZIONE e il nuovo comando V1 non la
popola. La colonna può restare NULL per compatibilità; non autorizza clienti,
proprietà o allocazione fisica.

`QUALITY AUTHORITY = DEFERRED`. Nessun campo quality libero e nessun
vocabolario non governato entra nel comando V1.

## 11. Confine RACCOLTA, MOVIMENTO e STOCK

```text
RACCOLTA             -> fatto fisico
MOVIMENTO_MAGAZZINO  -> autorità di mutazione inventario
STOCK                -> stato inventariale corrente
```

Registrare una RACCOLTA non modifica STOCK e non crea automaticamente un
MOVIMENTO_MAGAZZINO nascosto. La pubblicazione Raccolta -> Movimento è una
futura authority boundary. Resta permanente:

```text
DISPONIBILE < PRENOTATO -> ALLARME ROSSO / PRIORITÀ ASSOLUTA
```

## 12. Origine downstream

STOCK provenance, ASSEGNAZIONE, CONSEGNA, BOLLA e FATTURA dovranno preservare
le componenti di origine `AAA-GGMM-L` senza fonderle. Una consegna aggregata
può contenere più codici, ma ogni quantità conserva la propria origine. Questi
domini non sono implementati da questo Sprint.

## 13. Boundary applicativo e PostgreSQL

Lo Sprint implementativo aggiunge comando governato, result tipizzato,
application service, PostgreSQL writer, Bootstrap e CLI. Il writer usa
l'esistente `tpo.raccolte`; non crea una seconda tabella evento.

Il boundary fallisce chiuso per SEMINA assente o non eleggibile, quantità o
tempo invalidi, tracciabilità mancante/incoerente, request conflittuale,
identity authority mancante e persistenza incerta. Vincoli, trigger,
idempotenza, audit e allocazione richiedono test PostgreSQL reali.

## 14. Sprint 5.13

IN SCOPE: `RACCOLTA_ID`, comando governato, eligibility, traceability check,
quantità SET, tempi, request idempotency, writer atomico, enforcement
immutabilità, audit, service, Bootstrap, CLI, migrazione e test, inclusi
concorrenza e regressione completa.

OUT OF SCOPE: mutazione STOCK, Movimento automatico, ASSEGNAZIONE, CONSEGNA,
BOLLA, FATTURA, pagamento, UI, qualità, correction/reversal/void,
ricostruzione storica, backfill SEMINE e ogni seconda identità produttiva.

## 15. Guardie permanenti

Sono vietati:

- prefisso o sequenza alternativi a `RAC` / `RACCOLTA_ID`;
- raccolta fuori da `PRONTA_ALLA_RACCOLTA`;
- transizione o chiusura automatica della SEMINA;
- UPDATE o DELETE di RACCOLTA;
- `LOTTO_PRODUZIONE` o altra identità produttiva concorrente;
- snapshot autorevole di `AAA-GGMM-L` su RACCOLTA;
- mutazione diretta STOCK o Movimento nascosto;
- uso di `destinazione_prevista` come ASSEGNAZIONE;
- qualità free-text o vocabolari non approvati;
- identità Operatore concorrente con l'authority context Core.
