# POSTGRESQL PHYSICAL SCHEMA

**Stato:** POSTGRESQL PHYSICAL SCHEMA FREEZE v1.0

## Executive Summary

Questo documento definisce il modello fisico PostgreSQL ufficiale del Tower Power Operations.

PostgreSQL è la sorgente autorevole dei Register, delle sequenze identificative, delle RUN e delle proiezioni operative persistenti. Il modello è progettato in forma relazionale normalizzata e non costituisce una trasposizione dei fogli Google.

Il nucleo utilizza:

- chiavi primarie interne `bigint` per join e foreign key efficienti;
- identificativi pubblici permanenti `text`, univoci e immutabili;
- quantità `numeric(20,6)`;
- date civili `date`;
- istanti `timestamp with time zone`;
- enum PostgreSQL per insiemi chiusi e congelati;
- vincoli relazionali per integrità, idempotenza e cardinalità;
- una tabella versionata per il compare-and-set delle sequenze pubbliche;
- tabelle append-only per Facts, RUN, messaggi e audit;
- viste per PRENOTAZIONI, scheduling, evasione e reporting;
- JSONB esclusivamente nell’audit e nei log eterogenei.

Google Sheets non è il database. È una destinazione secondaria per reporting, export e consultazione, alimentata da PostgreSQL in modo unidirezionale e rigenerabile.

Il Freeze definisce struttura, responsabilità e vincoli. Non costituisce SQL, migrazione o autorizzazione alla produzione.

## 1. Principi architetturali

1. PostgreSQL conserva la verità persistente del dominio.
2. Ogni Register mantiene la responsabilità definita dal proprio documento congelato.
3. Le tabelle non duplicano Facts autorevoli per comodità di lettura.
4. Le proiezioni derivate sono viste o tabelle esplicitamente governate come stato corrente.
5. Gli identificativi pubblici `PREFIX-NNNNNN` restano l’identità permanente esposta dal Domain.
6. Le chiavi interne non escono dall’Infrastructure e non modificano l’identità di dominio.
7. Le righe degli aggregati possiedono una chiave tecnica stabile e una posizione esplicita; la posizione non è un identificativo di dominio.
8. I Facts storici non sono aggiornati o eliminati durante il normale esercizio.
9. Le correzioni avvengono mediante nuovi Facts o operazioni amministrative auditabili quando il Register lo consente.
10. La generazione, la validazione e il commit degli ORDINI sono separati logicamente ma il commit persistente è una transazione PostgreSQL unica.
11. Le chiavi idempotenti sono protette da un vincolo univoco, non soltanto da una verifica applicativa.
12. Le foreign key usano `ON UPDATE RESTRICT`; gli identificativi e le relazioni storiche non vengono riscritti.
13. Le cancellazioni a cascata sono ammesse soltanto tra una testata e componenti posseduti integralmente dall’aggregato, e soltanto nei flussi amministrativi autorizzati.
14. Le relazioni verso Facts o configurazioni referenziate usano `ON DELETE RESTRICT`.
15. Gli istanti sono memorizzati come `timestamp with time zone`; il runtime presenta e calcola in `Atlantic/Canary`.
16. Nessuna credenziale, stringa di connessione o segreto appartiene allo schema o al repository.
17. La logica degli Engine resta nell’Application Layer. Vincoli, unicità e integrità persistente appartengono al database.

## 2. Convenzioni fisiche

### 2.1 Nomi

- Schema applicativo: `tpo`.
- Tabelle, colonne, indici e vincoli: `snake_case` minuscolo.
- Nomi al plurale per le tabelle di entità e Facts.
- Nomi espliciti per le tabelle associative.
- Nessun nome dipendente da Supabase.

### 2.2 Chiavi

Le entità dotate di identificativo pubblico usano:

- `id bigint`: chiave primaria interna, generata dal database;
- `public_id text`: chiave candidata `UNIQUE NOT NULL`, immutabile;
- `CHECK` sul formato e sul prefisso ufficiale.

Le foreign key interne fanno riferimento a `id`. Gli adapter convertono tra `public_id` e Value Object tipizzati.

Il tipo `uuid` non viene usato nel modello v1.0: gli identificativi pubblici congelati sono sequenziali e tipizzati, mentre `bigint` è più compatto per PK e join. UUID potrà essere usato in futuro per identificatori tecnici distribuiti che non rappresentino identità di dominio.

### 2.3 Quantità

- Tipo: `numeric(20,6)`.
- Quantità operative: `CHECK quantità > 0`.
- STOCK: `CHECK disponibile >= 0`.
- Nessun `double precision` o `real` per quantità di dominio.
- L’unità di misura è sempre esplicita.

### 2.4 Testo

- `text` per identificativi pubblici, denominazioni, motivi, origini e note.
- `varchar` non viene usato senza un limite semantico approvato.
- Testi obbligatori hanno `CHECK btrim(valore) <> ''`.
- `citext` non è richiesto nella v1.0 perché non esiste ancora un attributo autorevole case-insensitive, come un’email cliente congelata.

### 2.5 Temporali

- `date` per date senza ora.
- `time without time zone` per l’orario ricorrente locale del PROGRAMMA_FORNITURA.
- `timestamp with time zone` per eventi, RUN e audit.
- `created_at` ha default all’istante della transazione.
- `updated_at` esiste soltanto per dati mutabili e proiezioni correnti.

### 2.6 Audit di base

Le tabelle mutabili includono:

- `created_at timestamp with time zone NOT NULL`;
- `created_by text NOT NULL`;
- `updated_at timestamp with time zone NOT NULL`;
- `updated_by text NOT NULL`;
- `version bigint NOT NULL DEFAULT 0`, con valore non negativo.

I Facts immutabili includono `created_at`, `created_by` e, quando applicabile, `run_id`; non includono un generico `updated_at` che suggerirebbe modificabilità ordinaria.

## 3. Modello relazionale

```text
clienti
└── programmi_fornitura
    └── programmi_fornitura_versioni
        └── righe_programma_fornitura
            └── righe_programma_giorni
                 │
                 └── origini_righe_ordine ── righe_ordine ── ordini
                                                        │        │
                                                        │        └── runs
                                                        │
                                                        └── righe_consegna
                                                                 │
ordini ── consegne_ordini ── consegne ───────────────────────────┘

varieta
├── cultivar
│   └── cultivar_usi ── usi_produttivi
│       ├── protocolli ── protocollo_versioni
│       └── semente_impieghi ── sementi ── lotti_seme
├── semine ── raccolte
├── righe_programma_fornitura
├── righe_ordine
├── righe_consegna
├── movimenti_magazzino
└── stock

raccolte ── provenienze_righe_consegna ── righe_consegna

id_sequences
runs ── run_messaggi
     └── run_log
audit_eventi
```

## 4. Elenco tabelle

| Area | Tabelle |
|---|---|
| Anagrafiche | `clienti`, `varieta`, `cultivar`, `usi_produttivi` |
| Conoscenza produttiva | `cultivar_usi`, `protocolli`, `protocollo_versioni`, `sementi`, `semente_impieghi`, `lotti_seme` |
| Pianificazione operativa | `programmi_fornitura`, `programmi_fornitura_versioni`, `righe_programma_fornitura`, `righe_programma_giorni` |
| ORDINI | `ordini`, `righe_ordine`, `origini_righe_ordine` |
| CONSEGNE | `consegne`, `consegne_ordini`, `righe_consegna`, `provenienze_righe_consegna` |
| Produzione | `semine`, `raccolte` |
| Magazzino | `movimenti_magazzino`, `stock` |
| Runtime | `id_sequences`, `runs`, `run_messaggi`, `run_log` |
| Audit | `audit_eventi` |

`RACCOLTI` non diventa una tabella: il nome ufficiale del Register e dell’evento è RACCOLTE, pertanto la tabella è `raccolte`.

PRENOTAZIONI non diventa una tabella autonoma: resta una conseguenza logica degli ORDINI e viene esposta tramite vista.

WritePlan e ValidatedWritePlan non diventano tabelle nella v1.0. Sono Value Object applicativi immutabili e transitori. Le prove persistenti del risultato sono RUN, ORDINI, chiavi idempotenti, audit ed esito della transazione. Una futura persistenza dei piani richiederà una decisione dedicata e non dovrà duplicare ORDINI come seconda fonte autorevole.

## 5. Definizione completa delle tabelle

### 5.1 `clienti`

**Responsabilità:** identità minima del CLIENTE referenziata dai Register operativi.

| Colonna | Tipo | Null/Default | Vincoli |
|---|---|---|---|
| `id` | `bigint` | NOT NULL, generato | PK |
| `public_id` | `text` | NOT NULL | UNIQUE, formato `CLI-[0-9]{6,}` |
| `denominazione` | `text` | NOT NULL | non vuota |
| `created_at` | `timestamp with time zone` | NOT NULL, default transazione |  |
| `created_by` | `text` | NOT NULL | non vuoto |
| `updated_at` | `timestamp with time zone` | NOT NULL | non precedente a `created_at` |
| `updated_by` | `text` | NOT NULL | non vuoto |
| `version` | `bigint` | NOT NULL, default 0 | >= 0 |

Chiavi candidate: `public_id`. La denominazione non è univoca perché non costituisce identità.

Indici: PK; UK su `public_id`; indice su denominazione per consultazione.

Relazioni: un CLIENTE ha molti PROGRAMMI_FORNITURA, ORDINI e CONSEGNE.

Delete/update: `ON DELETE RESTRICT` da tutti i Register; nessun soft delete generico. L’eventuale ciclo di vita CLIENTI richiede un Register dedicato futuro.

### 5.2 `varieta`

**Responsabilità:** identità produttiva generale della coltura.

| Colonna | Tipo | Null/Default | Vincoli |
|---|---|---|---|
| `id` | `bigint` | NOT NULL, generato | PK |
| `public_id` | `text` | NOT NULL | UNIQUE, formato `VAR-[0-9]{6,}` |
| `denominazione` | `text` | NOT NULL | non vuota |
| `stato` | `varieta_state` | NOT NULL |  |
| campi audit mutabili | come §2.6 | NOT NULL | version >= 0 |

Chiavi candidate: `public_id`; `denominazione` con unicità case-insensitive logica da applicare mediante indice funzionale univoco su denominazione normalizzata.

Indici: PK; UK public ID; UK denominazione normalizzata; indice su `stato`.

Relazioni: una VARIETÀ ha molte CULTIVAR, SEMINE, righe operative, MOVIMENTI e al massimo una riga STOCK.

Delete/update: RESTRICT se referenziata; dismissione tramite stato, non cancellazione.

### 5.3 `cultivar`

**Responsabilità:** identità specifica appartenente a una VARIETÀ.

Colonne:

- `id bigint` PK generata;
- `varieta_id bigint NOT NULL` FK → `varieta.id`;
- `denominazione text NOT NULL` non vuota;
- `stato varieta_state NOT NULL`;
- campi audit mutabili e `version`.

Chiave candidata: (`varieta_id`, denominazione normalizzata) UNIQUE.

Indici: FK `varieta_id`; (`varieta_id`, `stato`).

Cardinalità: VARIETÀ 1:N CULTIVAR. Delete RESTRICT; ON UPDATE RESTRICT.

Motivo: CULTIVAR è distinta dalla VARIETÀ e non viene duplicata per USO PRODUTTIVO.

### 5.4 `usi_produttivi`

**Responsabilità:** vocabolario ufficiale degli obiettivi produttivi.

Colonne:

- `id bigint` PK generata;
- `codice text NOT NULL` UNIQUE, stabile e non vuoto;
- `denominazione text NOT NULL` non vuota;
- `attivo boolean NOT NULL DEFAULT true`;
- campi audit mutabili e `version`.

Indici: UK `codice`; indice su `attivo`.

Delete: RESTRICT quando referenziato; disattivazione logica tramite `attivo`.

### 5.5 `cultivar_usi`

**Responsabilità:** associazione autorevole CULTIVAR × USO PRODUTTIVO e centro della conoscenza produttiva.

Colonne:

- `id bigint` PK generata;
- `cultivar_id bigint NOT NULL` FK → `cultivar.id`;
- `uso_produttivo_id bigint NOT NULL` FK → `usi_produttivi.id`;
- `stato_validazione text NOT NULL` non vuoto;
- campi audit mutabili e `version`.

Vincoli: UNIQUE (`cultivar_id`, `uso_produttivo_id`).

Indici: entrambi gli FK; indice su `stato_validazione`.

Cardinalità: CULTIVAR N:M USI PRODUTTIVI. Delete RESTRICT.

`stato_validazione` resta text nella v1.0 perché il Register non congela un insieme chiuso di valori.

### 5.6 `protocolli`

**Responsabilità:** identità stabile di un Protocollo Standard o Sperimentale relativo a `cultivar_usi`.

Colonne:

- `id bigint` PK generata;
- `cultivar_uso_id bigint NOT NULL` FK;
- `tipo protocollo_tipo NOT NULL`;
- `denominazione text NOT NULL` non vuota;
- `attivo boolean NOT NULL DEFAULT true`;
- campi audit mutabili e `version`.

Vincoli: UNIQUE (`cultivar_uso_id`, `tipo`, denominazione normalizzata). Un solo Protocollo Standard attivo per `cultivar_uso_id` tramite indice univoco parziale.

Indici: FK; (`cultivar_uso_id`, `tipo`, `attivo`). Delete RESTRICT.

### 5.7 `protocollo_versioni`

**Responsabilità:** versioni immutabili e genealogia del Protocollo.

Colonne:

- `id bigint` PK generata;
- `protocollo_id bigint NOT NULL` FK;
- `numero_versione integer NOT NULL` > 0;
- `valida_dal date NOT NULL`;
- `valida_al date NULL`, non precedente a `valida_dal`;
- `versione_precedente_id bigint NULL` FK auto-referenziale;
- `contenuto text NOT NULL` non vuoto;
- `motivazione text NOT NULL` non vuota;
- `evidenze text NULL` non vuoto se presente;
- `created_at`, `created_by` NOT NULL.

Vincoli: UNIQUE (`protocollo_id`, `numero_versione`); UNIQUE (`versione_precedente_id`) per una genealogia lineare nella v1.0; nessuna sovrapposizione di validità per lo stesso Protocollo, da garantire con exclusion constraint su intervallo di date.

Indici: FK protocollo; `valida_dal`; versione precedente.

Delete/update: RESTRICT; versioni append-only.

### 5.8 `sementi`

**Responsabilità:** referenza sementiera commerciale, distinta dal materiale fisico.

Colonne:

- `id bigint` PK generata;
- `fornitore text NOT NULL` non vuoto;
- `referenza_commerciale text NOT NULL` non vuota;
- `marca text NULL`;
- `formato text NULL`;
- `trattamento text NULL`;
- `certificazioni text NULL`;
- `attiva boolean NOT NULL DEFAULT true`;
- campi audit mutabili e `version`.

Vincoli: UNIQUE su fornitore e referenza normalizzati. Testi opzionali non vuoti se presenti.

Indici: fornitore; `attiva`. Delete RESTRICT.

### 5.9 `semente_impieghi`

**Responsabilità:** associazione e valutazione SEMENTE × CULTIVAR × USO PRODUTTIVO.

Colonne:

- `id bigint` PK generata;
- `semente_id bigint NOT NULL` FK;
- `cultivar_uso_id bigint NOT NULL` FK;
- `raccomandazione semente_raccomandazione NOT NULL`;
- `rating numeric(5,2) NULL` con intervallo 0–100;
- `motivazione text NULL`;
- `ultima_revisione date NOT NULL`;
- campi audit mutabili e `version`.

Vincoli: UNIQUE (`semente_id`, `cultivar_uso_id`).

Indici: entrambi gli FK; (`cultivar_uso_id`, `raccomandazione`). Delete RESTRICT.

### 5.10 `lotti_seme`

**Responsabilità:** materiale fisico ricevuto per una SEMENTE.

Colonne:

- `id bigint` PK generata;
- `semente_id bigint NOT NULL` FK;
- `numero_lotto_produttore text NOT NULL` non vuoto;
- `data_ricezione date NOT NULL`;
- `data_scadenza date NULL` non precedente a ricezione;
- `quantita_iniziale numeric(20,6) NOT NULL` > 0;
- `quantita_residua numeric(20,6) NOT NULL` >= 0 e <= iniziale;
- `unita_misura unit_of_measure NOT NULL`;
- `anomalia text NULL`;
- campi audit mutabili e `version`.

Vincoli: UNIQUE (`semente_id`, `numero_lotto_produttore`).

Indici: FK; scadenza; (`semente_id`, `data_ricezione`). Delete RESTRICT.

### 5.11 `programmi_fornitura`

**Responsabilità:** identità permanente dell’accordo operativo con un CLIENTE.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `PF-[0-9]{6,}`;
- `cliente_id bigint NOT NULL` FK;
- `created_at`, `created_by` NOT NULL.

La configurazione variabile non è collocata nella testata, ma nelle versioni immutabili.

Vincoli aggiuntivi: UNIQUE (`id`, `cliente_id`) per consentire alle versioni una FK composta che ne garantisca il CLIENTE senza affidarsi a trigger.

Indici: UK public ID; FK cliente. Delete RESTRICT se esistono versioni o ORDINI.

Cardinalità: CLIENTE 1:N programmi storici.

### 5.12 `programmi_fornitura_versioni`

**Responsabilità:** fotografia immutabile di una configurazione del PROGRAMMA_FORNITURA.

Colonne:

- `id bigint` PK generata;
- `programma_fornitura_id bigint NOT NULL` FK;
- `cliente_id bigint NOT NULL`;
- `numero_versione integer NOT NULL` > 0;
- `stato programma_fornitura_state NOT NULL`;
- `data_inizio date NOT NULL`;
- `data_fine date NULL` >= data inizio;
- `orario_generazione time without time zone NOT NULL DEFAULT 05:00`;
- `finestra_operativa_giorni integer NOT NULL` >= 0;
- `valida_dal timestamp with time zone NOT NULL`;
- `valida_al timestamp with time zone NULL` > valida dal;
- `created_at`, `created_by` NOT NULL.

Vincoli: FK composta (`programma_fornitura_id`, `cliente_id`) → PROGRAMMI_FORNITURA; UNIQUE (`programma_fornitura_id`, `numero_versione`); una sola versione corrente (`valida_al IS NULL`) per programma; un solo PROGRAMMA nello stato ATTIVO corrente per CLIENTE tramite indice univoco parziale su `cliente_id` per le versioni correnti ATTIVE.

La non riattivabilità di TERMINATO è una regola di transizione verificata nella stessa transazione di creazione versione e auditata.

Indici: FK composta programma/cliente; (`stato`, `valida_al`); (`data_inizio`, `data_fine`). Delete RESTRICT; versioni append-only.

Denormalizzazione intenzionale: `cliente_id` è ripetuto nella versione esclusivamente per rendere applicabile il vincolo univoco del PROGRAMMA ATTIVO; la FK composta impedisce divergenze dalla testata.

### 5.13 `righe_programma_fornitura`

**Responsabilità:** righe immutabili possedute da una versione del PROGRAMMA.

Colonne:

- `id bigint` PK generata;
- `programma_versione_id bigint NOT NULL` FK;
- `posizione integer NOT NULL` > 0;
- `varieta_id bigint NOT NULL` FK;
- `quantita numeric(20,6) NOT NULL` > 0;
- `unita_misura unit_of_measure NOT NULL`;
- `tipo_ricorrenza tipo_ricorrenza NOT NULL`;
- `intervallo_giorni integer NULL`.

Vincoli: UNIQUE (`programma_versione_id`, `posizione`); `intervallo_giorni` positivo soltanto per OGNI_X_GIORNI e NULL negli altri casi.

Indici: FK versione; FK varietà; (`tipo_ricorrenza`, `programma_versione_id`).

Delete: CASCADE soltanto se una versione non ancora referenziata viene eliminata amministrativamente; RESTRICT quando la riga è origine di ORDINI.

### 5.14 `righe_programma_giorni`

**Responsabilità:** giorni ISO normalizzati della ricorrenza GIORNI_SETTIMANA.

Colonne:

- `riga_programma_id bigint NOT NULL` FK;
- `giorno_iso smallint NOT NULL` tra 1 e 7.

PK composta (`riga_programma_id`, `giorno_iso`). La presenza è ammessa esclusivamente per righe GIORNI_SETTIMANA; almeno un giorno è obbligatorio per tale tipo, verificato al termine della transazione mediante vincolo differibile o validazione transazionale.

Indici: PK sufficiente; indice inverso su (`giorno_iso`, `riga_programma_id`) per scheduling.

Delete: CASCADE con la riga posseduta.

### 5.15 `ordini`

**Responsabilità:** richiesta storica di prodotto e metadati persistenti di scheduling.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `ORD-[0-9]{6,}`;
- `cliente_id bigint NOT NULL` FK;
- `programma_fornitura_id bigint NULL` FK;
- `run_id bigint NULL` FK → `runs.id`;
- `data_ordine date NOT NULL`;
- `data_consegna_prevista date NULL`;
- `stato ordine_state NOT NULL`;
- `tipo_creazione ordine_creation_type NOT NULL`, senza default;
- `chiave_idempotenza text NULL`;
- `created_at`, `created_by` NOT NULL.

Vincoli:

- `chiave_idempotenza` UNIQUE quando presente;
- ORDINI automatici richiedono programma, RUN, data prevista e chiave idempotente;
- ORDINI manuali richiedono RUN, programma e chiave idempotente NULL; la data prevista resta facoltativa;
- `tipo_creazione` è immutabile e non viene dedotto da RUN, programma, chiave o provenance;
- data prevista non precedente a data ordine, salvo import storico esplicitamente validato prima del Freeze dati.

La matrice fisica congelata è:

| `tipo_creazione` | `run_id` | `programma_fornitura_id` | `data_consegna_prevista` | `chiave_idempotenza` | origini righe |
|---|---|---|---|---|---|
| `AUTOMATICO` | NOT NULL | NOT NULL | NOT NULL | NOT NULL | almeno una per ogni riga |
| `MANUALE` | NULL | NULL | NULL ammesso | NULL | nessuna |

Il CHECK di riga applica le combinazioni dei cinque campi. L'obbligatorietà o il divieto della provenance è verificato al termine della transazione mediante vincolo differibile o validazione transazionale.

Indici: UK public ID; UK idempotency key; FK cliente, programma e RUN; (`stato`, `data_consegna_prevista`); (`cliente_id`, `data_ordine`); (`programma_fornitura_id`, `data_consegna_prevista`).

Delete/update: ORDINE registrato append-only nella struttura. ON DELETE RESTRICT dalle relazioni. Lo stato evolve tramite transazione auditata; righe e riferimenti originari non cambiano.

Nel commit automatico `created_by` è obbligatoriamente
`CommitRequest.execution_context.actor.value`. Non esiste un default e il
writer non deduce o sostituisce l'actor.

Nel commit automatico `created_at` è valorizzato esplicitamente con
`CommitRequest.requested_at.datetime`. Il writer non usa il default PostgreSQL
quando il valore applicativo è disponibile e non sostituisce tale valore con
`SchedulingRunCompletion.completed_at`, con il parametro `completed_at` di
`execute_commit()` o con un clock interno. Il parametro di `execute_commit()`
alimenta esclusivamente `CommitExecutionReceipt.commit_completed_at` nel
protocollo di commit.

Ai fini della ricevuta PostgreSQL,
`CommitExecutionReceipt.appended_physical_row_count` conta esclusivamente i
record inseriti in `tpo.righe_ordine`. Non conta testate `tpo.ordini`, origini,
messaggi, audit, aggiornamento della RUN, lookup o query di controllo.

### 5.16 `righe_ordine`

**Responsabilità:** righe prodotto immutabili dell’ORDINE.

Colonne:

- `id bigint` PK generata;
- `ordine_id bigint NOT NULL` FK;
- `posizione integer NOT NULL` > 0;
- `varieta_id bigint NOT NULL` FK;
- `quantita numeric(20,6) NOT NULL` > 0;
- `unita_misura unit_of_measure NOT NULL`.

Vincoli: UNIQUE (`ordine_id`, `posizione`).

Candidate key per il fulfilment:
`CONSTRAINT uq_righe_ordine_fulfilment_key UNIQUE (id, ordine_id, varieta_id,
unita_misura)`. È il target autorevole della FK composita di
`righe_consegna` e non introduce una seconda authority quantitativa.

Indici: FK ordine; FK varietà; (`varieta_id`, `ordine_id`).

Delete: CASCADE soltanto nell’eliminazione amministrativa autorizzata dell’intero ORDINE mai realmente registrato; altrimenti struttura immutabile.

### 5.17 `origini_righe_ordine`

**Responsabilità:** riferimento permanente tra una riga ORDINE automatica e una o più righe PROGRAMMA che l’hanno originata.

Colonne:

- `riga_ordine_id bigint NOT NULL` FK;
- `riga_programma_id bigint NOT NULL` FK.

PK composta sui due FK. Ogni riga ORDINE automatica deve avere almeno un’origine; le righe manuali non ne hanno.

Indici: PK; indice inverso su `riga_programma_id`.

Delete: RESTRICT verso entrambe le fonti storiche.

### 5.18 `consegne`

**Responsabilità:** evento logistico reale o pianificato verso un CLIENTE.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `CON-[0-9]{6,}`;
- `cliente_id bigint NOT NULL` FK;
- `stato consegna_state NOT NULL`;
- `data_prevista date NOT NULL`;
- `data_effettiva timestamp with time zone NULL`;
- `motivazione text NULL`;
- `operatore text NULL`;
- `destinazione_fisica text NULL`;
- `created_at`, `created_by` NOT NULL.

Vincoli: data effettiva obbligatoria per CONSEGNATA e NULL per PROGRAMMATA/ANNULLATA; motivazione obbligatoria se non esistono ORDINI collegati, verificata transazionalmente; testi opzionali non vuoti.

Indici: UK public ID; FK cliente; (`stato`, `data_prevista`); `data_effettiva`.

Delete/update: una CONSEGNA CONSEGNATA è immutabile; ON DELETE RESTRICT. Stati preparatori evolvono con optimistic locking applicativo e audit.

### 5.19 `consegne_ordini`

**Responsabilità:** relazione N:M tra CONSEGNE e ORDINI.

Colonne:

- `consegna_id bigint NOT NULL` senza default;
- `ordine_id bigint NOT NULL` senza default;
- `posizione integer NOT NULL` senza default.

Constraint fisici definitivi:

- `CONSTRAINT pk_consegne_ordini PRIMARY KEY (consegna_id, ordine_id)`;
- `CONSTRAINT uq_consegne_ordini_consegna_posizione UNIQUE (consegna_id, posizione)`;
- `CONSTRAINT ck_consegne_ordini_posizione_positive CHECK (posizione > 0)`;
- `CONSTRAINT fk_consegne_ordini_consegna FOREIGN KEY (consegna_id) REFERENCES tpo.consegne(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT fk_consegne_ordini_ordine FOREIGN KEY (ordine_id) REFERENCES tpo.ordini(id) ON UPDATE RESTRICT ON DELETE RESTRICT`.

Indice aggiuntivo non ridondante:
`CREATE INDEX ix_consegne_ordini_ordine_id ON tpo.consegne_ordini (ordine_id ASC)`.

Il CLIENTE dell'ORDINE deve coincidere con `consegne.cliente_id`. Il Delivery
Fulfilment Writer lo verifica sotto lock. L'enforcement strutturale differito è
distinto per ciascuna tabella coinvolta:

- il trigger della relazione verifica INSERT/UPDATE di `consegne_ordini`;
- il trigger parent CONSEGNA verifica UPDATE di `consegne.cliente_id`;
- il trigger parent ORDINE verifica UPDATE di `ordini.cliente_id`.

I tre trigger operano anche quando la CONSEGNA è PROGRAMMATA o
IN_PREPARAZIONE. L'immutabilità post-CONSEGNATA è un invariante separato. DELETE
della relazione non richiede un trigger di coerenza CLIENTE perché non può
creare una nuova associazione incoerente.

La relazione è modificabile esclusivamente prima di `CONSEGNATA`; dopo il fatto
è append-only, senza hard delete. Writer unico: Delivery Fulfilment Writer.

### 5.20 `righe_consegna`

**Responsabilità:** prodotto realmente o programmato nella CONSEGNA.

Colonne:

- `id bigint GENERATED BY DEFAULT AS IDENTITY NOT NULL` senza default applicativo;
- `consegna_id bigint NOT NULL` senza default;
- `ordine_id bigint NOT NULL` senza default;
- `riga_ordine_id bigint NOT NULL` senza default;
- `posizione integer NOT NULL` senza default;
- `varieta_id bigint NOT NULL` senza default;
- `quantita numeric(20,6) NOT NULL` senza default;
- `unita_misura tpo.unit_of_measure NOT NULL` senza default;
- `rettifica_riga_consegna_id bigint NULL` senza default;
- `created_at timestamp with time zone NOT NULL` senza default;
- `created_by text NOT NULL` senza default.

Non possiede `public_id`, stato, version, `updated_at` o `updated_by`.
L'identità operativa è `consegne.public_id` + `posizione`; non viene creata una
nuova sequenza Identity.

Constraint fisici definitivi:

- `CONSTRAINT pk_righe_consegna PRIMARY KEY (id)`;
- `CONSTRAINT uq_righe_consegna_consegna_posizione UNIQUE (consegna_id, posizione)`;
- `CONSTRAINT uq_righe_consegna_id_consegna UNIQUE (id, consegna_id)`;
- `CONSTRAINT ck_righe_consegna_posizione_positive CHECK (posizione > 0)`;
- `CONSTRAINT ck_righe_consegna_quantita_nonzero CHECK (quantita <> 0)`;
- `CONSTRAINT ck_righe_consegna_created_by_not_blank CHECK (btrim(created_by) <> '')`;
- `CONSTRAINT ck_righe_consegna_ordinary_or_correction CHECK ((rettifica_riga_consegna_id IS NULL AND quantita > 0) OR rettifica_riga_consegna_id IS NOT NULL)`;
- `CONSTRAINT fk_righe_consegna_consegna_ordine FOREIGN KEY (consegna_id, ordine_id) REFERENCES tpo.consegne_ordini(consegna_id, ordine_id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT fk_righe_consegna_riga_ordine FOREIGN KEY (riga_ordine_id, ordine_id, varieta_id, unita_misura) REFERENCES tpo.righe_ordine(id, ordine_id, varieta_id, unita_misura) ON UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT fk_righe_consegna_varieta FOREIGN KEY (varieta_id) REFERENCES tpo.varieta(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT fk_righe_consegna_rettifica FOREIGN KEY (rettifica_riga_consegna_id) REFERENCES tpo.righe_consegna(id) ON UPDATE RESTRICT ON DELETE RESTRICT`.

La FK composita richiede su `tpo.righe_ordine`:
`CONSTRAINT uq_righe_ordine_fulfilment_key UNIQUE (id, ordine_id, varieta_id, unita_misura)`.
Essa rende strutturali appartenenza all'ORDINE, VARIETÀ e UOM; nessuna
conversione implicita è ammessa.

Una riga ordinaria ha riferimento rettifica NULL e quantità positiva. Una riga
correttiva appartiene a una nuova CONSEGNA, ha quantità signed non zero e
riferisce direttamente una sola riga ordinaria storica; V1 vieta correzioni di
correzioni e cicli. Il constraint trigger `ct_righe_consegna_rettifica_coerente`
su INSERT/UPDATE è `DEFERRABLE INITIALLY DEFERRED` e verifica che la riga
riferita non sia a sua volta correttiva, sia diversa dalla nuova riga e abbia
stessi `riga_ordine_id`, `varieta_id` e `unita_misura`.

Indici fisici:

- `ix_righe_consegna_consegna_id (consegna_id ASC)`;
- `ix_righe_consegna_ordine_id (ordine_id ASC)`;
- `ix_righe_consegna_riga_ordine_id (riga_ordine_id ASC)`;
- `ix_righe_consegna_rettifica_id (rettifica_riga_consegna_id ASC)`;
- `ix_righe_consegna_riga_ordine_consegna (riga_ordine_id ASC, consegna_id ASC)`.

La riga è append-only. Prima di `CONSEGNATA` il writer può sostituire la bozza;
dopo `CONSEGNATA` testata, collegamenti e righe sono immutabili e non
cancellabili. Writer unico: Delivery Fulfilment Writer.

### 5.21 `provenienze_righe_consegna`

**Responsabilità:** tracciabilità facoltativa del prodotto di una riga CONSEGNA verso una o più RACCOLTE.

Colonne:

- `riga_consegna_id bigint NOT NULL` FK;
- `raccolta_id bigint NOT NULL` FK;
- `quantita numeric(20,6) NULL` > 0 se presente;
- `unita_misura unit_of_measure NULL`, presente insieme alla quantità.

PK composta (`riga_consegna_id`, `raccolta_id`). Quantità e unità sono entrambe NULL o entrambe valorizzate.

Indici: PK; indice inverso su `raccolta_id`. Delete RESTRICT per preservare provenienza.

### 5.22 `semine`

**Responsabilità:** ciclo produttivo omogeneo realmente avviato.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `SEM-[0-9]{6,}`;
- `varieta_id bigint NOT NULL` FK;
- `cultivar_id bigint NOT NULL` FK;
- `cultivar_uso_id bigint NOT NULL` FK;
- `lotto_seme_id bigint NOT NULL` FK;
- `protocollo_versione_id bigint NOT NULL` FK;
- `stato semina_state NOT NULL`;
- `quantita_seme numeric(20,6) NOT NULL` > 0;
- `unita_misura unit_of_measure NOT NULL`, obbligatoriamente GRAM;
- `data_avvio timestamp with time zone NOT NULL`;
- `causa_origine text NOT NULL` non vuota;
- `esito_finale semina_esito NULL`;
- snapshot storici `cultivar_snapshot`, `uso_produttivo_snapshot`, `lotto_seme_snapshot`, `protocollo_snapshot` text NOT NULL;
- `created_at`, `created_by` NOT NULL.

Vincoli: esito finale obbligatorio solo per CHIUSA e vietato negli altri stati; cultivar e cultivar_uso devono essere coerenti; lotto e versione protocollo devono appartenere al contesto selezionato.

Indici: UK public ID; FK varietà/cultivar/uso/lotto/protocollo; (`stato`, `data_avvio`); `causa_origine`.

Denormalizzazione intenzionale: gli snapshot preservano il contesto storico approvato e non sostituiscono le FK autorevoli.

Delete/update: dopo avvio è Fact storico; RESTRICT. Evoluzione stato auditata, identità e dati costitutivi immutabili.

### 5.23 `raccolte`

**Responsabilità:** evento storico di prelievo da una sola SEMINA.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `RAC-[0-9]{6,}`;
- `semina_id bigint NOT NULL` FK;
- `data_raccolta timestamp with time zone NOT NULL`;
- `quantita numeric(20,6) NOT NULL` > 0;
- `unita_misura unit_of_measure NOT NULL`, obbligatoriamente SET;
- `operatore text NULL`;
- `destinazione_prevista text NULL`;
- `note text NULL`;
- `created_at`, `created_by` NOT NULL.

Indici: UK public ID; FK semina; (`semina_id`, `data_raccolta`); `data_raccolta`.

Delete/update: Fact immutabile, ON DELETE RESTRICT. Eliminazione ammessa solo per registrazione errata di evento mai avvenuto, mediante procedura amministrativa auditata.

### 5.24 `stock`

**Responsabilità:** proiezione corrente della disponibilità per VARIETÀ.

Colonne:

- `varieta_id bigint NOT NULL` PK e FK;
- `disponibile numeric(20,6) NOT NULL DEFAULT 0` >= 0;
- `unita_misura unit_of_measure NOT NULL`;
- `ultimo_movimento_id bigint NULL` FK differita → `movimenti_magazzino.id`;
- `updated_at timestamp with time zone NOT NULL`;
- `version bigint NOT NULL DEFAULT 0` >= 0.

Chiave candidata aggiuntiva: (`varieta_id`, `unita_misura`) per FK composta dai MOVIMENTI.

Indici: PK; `updated_at`. Una sola riga STOCK per VARIETÀ.

Delete: RESTRICT. STOCK non viene cancellato quando esiste storia.

### 5.25 `movimenti_magazzino`

**Responsabilità:** storico ufficiale append-only delle variazioni STOCK.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `MOV-[0-9]{6,}`;
- `varieta_id bigint NOT NULL`;
- `unita_misura unit_of_measure NOT NULL`;
- `tipo movimento_type NOT NULL`;
- `direzione movimento_direction NOT NULL`;
- `quantita numeric(20,6) NOT NULL` > 0;
- `data_movimento timestamp with time zone NOT NULL`;
- `motivo text NOT NULL` non vuoto;
- `origine_tipo text NOT NULL` non vuoto;
- `origine_riferimento text NULL`;
- `raccolta_id bigint NULL` FK;
- `consegna_id bigint NULL` FK;
- `riga_consegna_id bigint NULL` senza default;
- `run_id bigint NULL` FK;
- `created_at`, `created_by` NOT NULL.

Foreign key composta (`varieta_id`, `unita_misura`) → STOCK. Per origine
RACCOLTA è obbligatorio `raccolta_id` e sono
vietati `consegna_id`/`riga_consegna_id`; per origine CONSEGNA sono obbligatori
`consegna_id` e `riga_consegna_id`, è vietato `raccolta_id` e i due riferimenti
devono appartenere alla stessa CONSEGNA. Origini SCARTO, RETTIFICA o future
usano tipo e riferimento senza creare una FK polimorfica falsa e lasciano NULL
le FK non pertinenti. Il CHECK fisico resta
`ck_movimenti_magazzino_origine_references`, esteso con questa matrice.

La coerenza `(riga_consegna_id, consegna_id)` è protetta dalla candidate key
`CONSTRAINT uq_righe_consegna_id_consegna UNIQUE (id, consegna_id)` e dalla FK
`CONSTRAINT fk_movimenti_magazzino_riga_consegna_consegna FOREIGN KEY
(riga_consegna_id, consegna_id) REFERENCES tpo.righe_consegna(id, consegna_id)
ON UPDATE RESTRICT ON DELETE RESTRICT`. Questa FK composita costituisce il
riferimento definitivo; una FK singola su `riga_consegna_id` è omessa perché
ridondante.

Indici: UK public ID; (`varieta_id`, `data_movimento`); tipo; origine; raccolta;
consegna; `ix_movimenti_magazzino_riga_consegna_id (riga_consegna_id ASC)`; RUN.

Delete/update: Fact immutabile, RESTRICT.

### 5.26 `id_sequences`

**Responsabilità:** stato transazionale autorevole delle sequenze degli identificativi pubblici.

Colonne:

- `sequence_name text NOT NULL` PK;
- `identifier_type text NOT NULL` UNIQUE;
- `prefix text NOT NULL` UNIQUE;
- `next_value bigint NOT NULL` > 0;
- `version bigint NOT NULL DEFAULT 0` >= 0;
- `updated_at timestamp with time zone NOT NULL`;
- `updated_by text NOT NULL`.

Sequenze iniziali obbligatorie: almeno RUN_ID e ORDINE_ID; lo stesso modello ospita CLI, PF, VAR, SEM, RAC, MOV e CON quando i relativi writer vengono attivati.

Il compare-and-set verifica `identifier_type`, `prefix`, `next_value` e `version` sotto row lock; aggiorna `next_value` e `version` insieme. Nessun ID viene ricostruito scansionando tabelle operative.

Non vengono usate sequence PostgreSQL esplicite per gli ID pubblici nella v1.0, perché la porta applicativa richiede lettura e versione CAS. Le PK interne generate possono usare identity/sequence interne non esposte.

Delete: vietato durante l’esercizio. I buchi sono ammessi; il riuso è vietato.

### 5.27 `runs`

**Responsabilità:** stato persistente e versionato di ogni esecuzione dello Scheduling Engine.

Colonne:

- `id bigint` PK generata;
- `public_id text NOT NULL` UNIQUE, formato `RUN-[0-9]{6,}`;
- `started_at timestamp with time zone NOT NULL`;
- `completed_at timestamp with time zone NULL`;
- `simulation boolean NOT NULL`;
- `state run_state NULL` mentre aperta;
- contatori `programmi_letti`, `righe_valutate`, `occorrenze_valutate`, `ordini_generati`, `elementi_saltati` bigint NOT NULL DEFAULT 0, tutti >= 0;
- `version bigint NOT NULL DEFAULT 0` >= 0;
- `created_by text NOT NULL`.

Vincoli: completamento, stato finale e `completed_at` sono coerenti; `completed_at >= started_at`; SUCCESS non ha warning/error, SUCCESS_WITH_WARNINGS ha warning e nessun errore, FAILED ha almeno un errore, verificati transazionalmente con `run_messaggi`.

Indici: UK public ID; (`state`, `started_at`); `completed_at`; (`simulation`, `started_at`).

Delete/update: apertura una volta; completamento con optimistic locking su `version`; nessuna riapertura; RESTRICT se referenziata.

### 5.28 `run_messaggi`

**Responsabilità:** warning ed errori ordinati appartenenti alla RUN.

Colonne:

- `id bigint` PK generata;
- `run_id bigint NOT NULL` FK;
- `tipo run_message_type NOT NULL`;
- `posizione integer NOT NULL` > 0;
- `messaggio text NOT NULL` non vuoto;
- `created_at timestamp with time zone NOT NULL`.

Vincoli: UNIQUE (`run_id`, `tipo`, `posizione`).

Indici: FK; (`run_id`, `tipo`). Delete CASCADE soltanto se una RUN aperta viene rimossa in ambiente sandbox prima di produrre effetti; in produzione RESTRICT tramite privilegi.

### 5.29 `run_log`

**Responsabilità:** log strutturato append-only della RUN.

Colonne:

- `id bigint` PK generata;
- `run_id bigint NOT NULL` FK;
- `occurred_at timestamp with time zone NOT NULL`;
- `level run_log_level NOT NULL`;
- `event_type text NOT NULL` non vuoto;
- `message text NOT NULL` non vuoto;
- `context jsonb NOT NULL DEFAULT oggetto vuoto`.

JSONB è giustificato perché il contesto diagnostico varia per tipo evento e non è una fonte di dominio. Deve essere un oggetto, non un array o scalare, e non può contenere credenziali o dati sensibili non necessari.

Indici: (`run_id`, `occurred_at`); (`level`, `occurred_at`); GIN su `context` soltanto quando query reali lo giustificheranno.

Delete: RESTRICT in produzione; retention futura tramite policy approvata.

### 5.30 `audit_eventi`

**Responsabilità:** traccia append-only delle modifiche amministrative e delle transizioni persistenti rilevanti.

Colonne:

- `id bigint` PK generata;
- `occurred_at timestamp with time zone NOT NULL`;
- `actor text NOT NULL` non vuoto;
- `run_id bigint NULL` FK;
- `entity_type text NOT NULL`;
- `entity_public_id text NULL`;
- `operation audit_operation NOT NULL`;
- `reason text NOT NULL` non vuoto;
- `before_data jsonb NULL`;
- `after_data jsonb NULL`;
- `correlation_id text NULL`.

Vincoli: almeno uno tra before/after è presente; i JSONB devono essere oggetti; DELETE richiede before, INSERT richiede after.

Indici: (`entity_type`, `entity_public_id`, `occurred_at`); `run_id`; `actor`; `occurred_at`; GIN sui payload soltanto se necessario.

Delete/update: vietati. La tabella non sostituisce i Facts del dominio e non è usata per ricostruire lo STOCK.

Per il commit automatico la cardinalità congelata è un evento `ORDINE` con
operation `INSERT` per ogni testata inserita, seguito da un solo evento `RUN`
con operation `STATE_TRANSITION`. Gli eventi ORDINE seguono l'ordine del
WritePlan e RUN è sempre ultimo. Actor, reason e correlation ID provengono
senza default dal `CommitExecutionContext`.

L'evento ORDINE ha `before_data NULL` e un `after_data` composto esattamente
da `public_id`, `cliente_id`, `programma_fornitura_id`, `run_id`,
`data_ordine`, `data_consegna_prevista`, `stato`, `tipo_creazione`,
`chiave_idempotenza`, `righe_count`, `origini_count`.

L'evento RUN ha `before_data` composto esattamente da `public_id`, stato
aperto persistente, versione attesa e `completed_at` NULL. `after_data`
contiene esattamente `public_id`, stato finale, versione incrementata,
completed_at, simulation, programmi_letti, righe_valutate,
occorrenze_valutate, ordini_generati ed elementi_saltati. Non vengono creati
eventi per righe, provenance, preflight, collisioni, errori o rollback.

## 6. Enum PostgreSQL

| Enum | Valori v1.0 |
|---|---|
| `unit_of_measure` | SET, GRAM, UNIT |
| `varieta_state` | ATTIVA, IN_SPERIMENTAZIONE, SOSPESA, DISMESSA |
| `programma_fornitura_state` | ATTIVO, SOSPESO, TERMINATO |
| `ordine_state` | APERTO, PARZIALMENTE_EVASO, EVASO, ANNULLATO |
| `ordine_creation_type` | AUTOMATICO, MANUALE |
| `consegna_state` | PROGRAMMATA, IN_PREPARAZIONE, CONSEGNATA, ANNULLATA |
| `semina_state` | AVVIATA, GERMINAZIONE, LUCE, CRESCITA, PRONTA_ALLA_RACCOLTA, CHIUSA |
| `semina_esito` | RACCOLTA_COMPLETA, RACCOLTA_PARZIALE_CON_SCARTO, SCARTO_TOTALE, INTERRUZIONE |
| `movimento_type` | CARICO, SCARICO, RETTIFICA |
| `movimento_direction` | POSITIVO, NEGATIVO |
| `tipo_ricorrenza` | SETTIMANALE, QUINDICINALE, MENSILE, OGNI_X_GIORNI, GIORNI_SETTIMANA |
| `run_state` | SUCCESS, SUCCESS_WITH_WARNINGS, FAILED |
| `run_message_type` | WARNING, ERROR |
| `run_log_level` | DEBUG, INFO, WARNING, ERROR |
| `protocollo_tipo` | STANDARD, SPERIMENTALE |
| `semente_raccomandazione` | RACCOMANDATA, UTILIZZABILE, SCONSIGLIATA |
| `audit_operation` | INSERT, UPDATE, DELETE, STATE_TRANSITION, CORRECTION |

Un enum è usato solo quando l’insieme è chiuso e architetturalmente approvato. Origine, motivo, causa e stato di validazione restano `text` estensibili.

L’aggiunta di valori a enum di dominio richiede una nuova Architecture Review e una migrazione. Gli enum non devono contenere valori di convenienza infrastrutturale.

## 7. Sequence e identificativi

### 7.1 Identità pubblica

| Tipo | Prefisso | Esempio |
|---|---|---|
| ClienteId | CLI | CLI-000001 |
| VarietaId | VAR | VAR-000001 |
| ProgrammaFornituraId | PF | PF-000001 |
| OrdineId | ORD | ORD-000001 |
| ConsegnaId | CON | CON-000001 |
| SeminaId | SEM | SEM-000001 |
| RaccoltaId | RAC | RAC-000001 |
| MovimentoId | MOV | MOV-000001 |
| RunId | RUN | RUN-000001 |

Il valore pubblico è persistito integralmente e protetto da UNIQUE e CHECK. Il numero allocato non viene ricalcolato dal massimo presente.

### 7.2 Allocazione

L’allocazione usa `id_sequences`:

1. apertura transazione breve;
2. selezione della riga con row lock;
3. verifica tipo, prefisso, `next_value` e `version`;
4. calcolo e validazione dell’identificativo;
5. incremento atomico di valore e versione;
6. commit;
7. restituzione dell’ID allocato.

Nessun retry appartiene al repository. L’orchestratore può decidere un retry limitato soltanto per errori transitori classificati e mai riutilizza un valore già committato.

Le PK interne usano generatori database separati e non hanno significato di dominio.

## 8. Viste

### 8.1 Viste ordinarie

- `v_programmi_attivi_scheduling`: versione corrente ATTIVA, righe e calendario necessari allo Scheduling Engine.
- `v_prenotazioni_ordini`: quantità prenotata derivata dalle righe di ORDINI APERTI o PARZIALMENTE EVASI.
- `v_evasione_ordini`: quantità richiesta e consegnata per ORDINE/riga/VARIETÀ.
- `v_stock_operativo`: DISPONIBILE, PRENOTATO e saldo operativo, senza modificare STOCK.
- `v_movimenti_stock`: storico cronologico con saldo analitico derivato per verifica.
- `v_run_summary`: RUN, contatori, numero warning/error e durata.
- `v_consegne_fatturabili_future`: CONSEGNE reali disponibili alla futura fatturazione, senza creare FATTURE.

Le viste non sono writer e non diventano fonti autorevoli.

### 8.2 Future materialized view

Sono candidate, ma non fanno parte del write path v1.0:

- forecast produttivo;
- briefing giornaliero;
- dashboard STOCK storica;
- rese per VARIETÀ/CULTIVAR/USO;
- performance PROGRAMMI_FORNITURA;
- aggregati per reporting Google Sheets.

Ogni materialized view futura deve dichiarare sorgenti, refresh, writer e tolleranza alla staleness.

## 9. Relazioni e cardinalità

| Relazione | Cardinalità |
|---|---|
| CLIENTE → PROGRAMMI_FORNITURA | 1:N storica, massimo uno ATTIVO corrente |
| PROGRAMMA → VERSIONI | 1:N, una corrente |
| VERSIONE PROGRAMMA → RIGHE | 1:N, almeno una |
| VARIETÀ → CULTIVAR | 1:N |
| CULTIVAR ↔ USI PRODUTTIVI | N:M tramite `cultivar_usi` |
| CULTIVAR_USO → PROTOCOLLI | 1:N |
| PROTOCOLLO → VERSIONI | 1:N |
| SEMENTE ↔ CULTIVAR_USO | N:M tramite `semente_impieghi` |
| SEMENTE → LOTTI_SEME | 1:N |
| CLIENTE → ORDINI | 1:N |
| PROGRAMMA → ORDINI | 1:N opzionale sul lato ORDINE |
| RUN → ORDINI automatici | 1:N |
| ORDINE → RIGHE | 1:N, almeno una |
| RIGA PROGRAMMA ↔ RIGA ORDINE | N:M tramite origini |
| ORDINI ↔ CONSEGNE | N:M |
| CONSEGNA → RIGHE | 1:N, almeno una |
| RACCOLTE ↔ RIGHE CONSEGNA | N:M opzionale |
| VARIETÀ → SEMINE | 1:N |
| SEMINA → RACCOLTE | 1:N, anche zero |
| VARIETÀ → MOVIMENTI | 1:N |
| VARIETÀ → STOCK | 1:0..1, una volta inizializzato 1:1 |
| RUN → MESSAGGI/LOG | 1:N |

## 10. Vincoli inter-tabella e differibili

Alcuni invarianti non sono esprimibili con un semplice CHECK di riga e devono essere garantiti dalla transazione, da constraint trigger differibili o da indici appropriati:

- almeno una riga per PROGRAMMA, ORDINE e CONSEGNA;
- almeno un giorno per ricorrenza GIORNI_SETTIMANA;
- un solo PROGRAMMA ATTIVO corrente per CLIENTE;
- divieto di riattivare un PROGRAMMA TERMINATO;
- coerenza CLIENTE tra CONSEGNA e ORDINI collegati;
- prodotti CONSEGNA contenuti negli ORDINI ordinari collegati;
- rettifica RIGA_CONSEGNA riferita direttamente a una riga ordinaria con stessa
  RIGA_ORDINE, VARIETÀ e UOM;
- saldo consegnato per RIGA_ORDINE compreso tra zero e quantità ordinata;
- stato ORDINE coerente con i residui di tutte le righe;
- coerenza tra riferimenti costitutivi della SEMINA;
- coerenza stato RUN con warning ed errori;
- coerenza stato CONSEGNA e presenza data effettiva;
- motivazione obbligatoria per CONSEGNA straordinaria senza ORDINI;
- ultimo MOVIMENTO e saldo STOCK;
- immutabilità dei Facts dopo il loro verificarsi.

I trigger di integrità non devono eseguire logica di scheduling, pianificazione o dominio. Possono soltanto proteggere invarianti persistenti già approvati.

Le funzioni tecniche definitive per la coerenza CLIENTE sono tre funzioni
PL/pgSQL separate, tutte nel namespace `tpo`, `RETURNS trigger`, senza
argomenti e senza scritture:

- `tpo.fn_consegne_ordini_cliente_coerente()`: legge le testate indicate da
  `NEW.consegna_id` e `NEW.ordine_id` e solleva eccezione se i CLIENTI
  differiscono;
- `tpo.fn_consegne_cliente_coerente_ordini()`: per `NEW.id` legge tutti gli
  ORDINI collegati mediante `tpo.consegne_ordini` e solleva eccezione se almeno
  uno ha CLIENTE diverso da `NEW.cliente_id`; nessun collegamento produce PASS;
- `tpo.fn_ordini_cliente_coerente_consegne()`: per `NEW.id` legge tutte le
  CONSEGNE collegate mediante `tpo.consegne_ordini` e solleva eccezione se
  almeno una ha CLIENTE diverso da `NEW.cliente_id`; nessun collegamento produce
  PASS.

Le funzioni restituiscono `NEW` quando l'invariante è soddisfatto. Non cambiano
CLIENTE, stato o altre righe; non producono audit, fulfilment, movimenti o stock
e non applicano policy di dominio.

I constraint trigger definitivi del fulfilment sono istanze fisiche distinte:

- `ct_consegne_ordini_cliente_coerente`, AFTER INSERT OR UPDATE ON
  `tpo.consegne_ordini`, FOR EACH ROW, `DEFERRABLE INITIALLY DEFERRED`, esegue
  `tpo.fn_consegne_ordini_cliente_coerente()`; la coppia deve riferire testate
  con lo stesso CLIENTE;
- `ct_consegne_cliente_coerente_ordini`, AFTER UPDATE OF `cliente_id` ON
  `tpo.consegne`, FOR EACH ROW, `DEFERRABLE INITIALLY DEFERRED`, esegue
  `tpo.fn_consegne_cliente_coerente_ordini()`; verifica tutte le relazioni della
  CONSEGNA aggiornata e, se non ne esistono, produce PASS;
- `ct_ordini_cliente_coerente_consegne`, AFTER UPDATE OF `cliente_id` ON
  `tpo.ordini`, FOR EACH ROW, `DEFERRABLE INITIALLY DEFERRED`, esegue
  `tpo.fn_ordini_cliente_coerente_consegne()`; verifica tutte le relazioni
  dell'ORDINE aggiornato e, se non ne esistono, produce PASS;
- `ct_righe_consegna_rettifica_coerente`, AFTER INSERT OR UPDATE ON
  `righe_consegna`, `DEFERRABLE INITIALLY DEFERRED`: protegge riferimento
  diretto a riga ordinaria, assenza di cicli e uguaglianza
  RIGA_ORDINE/VARIETÀ/UOM;
- `ct_righe_consegna_fulfilment_bounds`, AFTER INSERT OR UPDATE OR DELETE ON
  `righe_consegna`, `DEFERRABLE INITIALLY DEFERRED`: verifica OLD e NEW
  RIGA_ORDINE tra zero e quantità ordinata;
- `ct_consegne_fulfilment_bounds`, AFTER UPDATE OF `stato` ON `consegne`,
  `DEFERRABLE INITIALLY DEFERRED`: verifica tutte le righe interessate dalla
  transizione dentro gli stessi limiti;
- `ct_righe_consegna_order_state`, AFTER INSERT OR UPDATE OR DELETE ON
  `righe_consegna`, `DEFERRABLE INITIALLY DEFERRED`: verifica lo stato degli
  ORDINI OLD e NEW rispetto ai residui;
- `ct_consegne_order_state`, AFTER UPDATE OF `stato` ON `consegne`, `DEFERRABLE
  INITIALLY DEFERRED`: verifica gli ORDINI interessati dalla transizione;
- `ct_ordini_fulfilment_state`, AFTER UPDATE OF `stato` ON `ordini`,
  `DEFERRABLE INITIALLY DEFERRED`: verifica APERTO, PARZIALMENTE_EVASO, EVASO e
  il divieto di nuovo fulfilment per ANNULLATO;
- `tr_consegne_effective_immutable`, BEFORE UPDATE OR DELETE ON `consegne`, non
  differibile: rifiuta la riscrittura di una testata già CONSEGNATA;
- `tr_consegne_ordini_effective_immutable`, BEFORE UPDATE OR DELETE ON
  `consegne_ordini`, non differibile: rifiuta la riscrittura di un collegamento
  appartenente a una CONSEGNA già effettiva;
- `tr_righe_consegna_effective_immutable`, BEFORE UPDATE OR DELETE ON
  `righe_consegna`, non differibile: rifiuta la riscrittura di una riga
  appartenente a una CONSEGNA già effettiva.

Questi trigger sono difese di integrità, non writer e non producono dati,
movimenti, stati, versioni o audit. Tali scritture appartengono esclusivamente
al Delivery Fulfilment Writer.

## 11. Transazioni

### 11.1 Allocazione ID

Confine: una singola riga `id_sequences`. Isolation level minimo `READ COMMITTED` con row lock. Nessuna scansione e nessun lock globale.

### 11.2 Apertura e conclusione RUN

- apertura: inserimento RUN unica;
- conclusione: lock o update condizionale su `version`;
- inserimento messaggi e log;
- aggiornamento stato e contatori;
- commit unico della conclusione.

Una conclusione concorrente perde il confronto di versione e non sovrascrive la prima.

### 11.3 Commit ORDINI da Scheduling

Ordine delle operazioni:

1. verificare RUN aperta e non simulata;
2. acquisire lock sulla RUN;
3. verificare versione e stato;
4. validare che tutte le chiavi idempotenti non esistano;
5. inserire testate ORDINI;
6. inserire righe e origini;
7. completare RUN e messaggi;
8. scrivere audit essenziale;
9. commit.

Isolation level: `READ COMMITTED` è sufficiente con unique constraint e row lock. `SERIALIZABLE` è ammesso per casi d’uso multi-aggregato futuri, con retry limitato nell’orchestratore per serialization failure. Il vincolo UNIQUE resta l’ultima difesa dall’idempotenza concorrente.

Un errore produce rollback totale. Dopo un timeout o perdita di connessione, il client non ripete ciecamente: interroga RUN e chiavi idempotenti per determinare l’esito.

### 11.4 MOVIMENTO e STOCK

1. lock della riga STOCK per VARIETÀ;
2. verifica unità e disponibilità;
3. calcolo del nuovo saldo;
4. rifiuto saldo negativo;
5. inserimento MOVIMENTO immutabile;
6. aggiornamento STOCK, ultimo movimento, timestamp e versione;
7. audit;
8. commit.

Il MOVIMENTO e lo STOCK non possono divergere.

### 11.5 CONSEGNA

Il Delivery Fulfilment Writer è l'unico writer autorevole. La transizione a
CONSEGNATA, `consegne_ordini`, `righe_consegna`, eventuali rettifiche,
MOVIMENTI_MAGAZZINO, aggiornamento STOCK, stato ORDINE, versioni ORDINE e
RIGA_ORDINE e audit avvengono in una singola transazione orchestrata. Una
CONSEGNA ANNULLATA non produce MOVIMENTI né fulfilment.

Il writer blocca ORDINI e poi RIGHE_ORDINE per PK crescente, quindi STOCK per PK
crescente; verifica expected version, CLIENTE, UOM, VARIETÀ, rettifiche e saldo
aggregato. Ogni riga interessata incrementa `righe_ordine.version`; ogni ORDINE
interessato incrementa `ordini.version` una sola volta per transazione. La sola
preparazione PROGRAMMATA/IN_PREPARAZIONE non incrementa versioni commerciali.
Nessun I/O esterno avviene sotto lock e nessun commit parziale o dual writer è
ammesso.

L'audit append-only registra actor, reason, correlation ID, CONSEGNA, righe e
rettifiche nel medesimo commit. La chiave operativa di una RIGA_CONSEGNA è
`consegne.public_id` + `posizione`; `audit_eventi.entity_public_id` usa il public
ID della CONSEGNA e i payload identificano la posizione, senza inventare una
nuova Identity.

La quantità commerciale è derivata univocamente da:

```sql
SELECT
    ro.id,
    ro.quantita AS quantita_ordinata,
    COALESCE(
        SUM(rc.quantita) FILTER (WHERE c.stato = 'CONSEGNATA'),
        0::numeric
    )::numeric(20,6) AS quantita_consegnata,
    (ro.quantita - COALESCE(
        SUM(rc.quantita) FILTER (WHERE c.stato = 'CONSEGNATA'),
        0::numeric
    ))::numeric(20,6) AS domanda_residua_commerciale
FROM tpo.righe_ordine AS ro
LEFT JOIN tpo.righe_consegna AS rc ON rc.riga_ordine_id = ro.id
LEFT JOIN tpo.consegne AS c ON c.id = rc.consegna_id
WHERE ro.id = :riga_ordine_id
GROUP BY ro.id, ro.quantita;
```

Scenari normativi: `1 SET` senza consegne produce delivered 0/residual 1/APERTO;
prima consegna `+0.5` produce 0.5/0.5/PARZIALMENTE_EVASO; seconda `+0.5`
produce 1/0/EVASO; ogni riga di un ORDINE multiriga è calcolata separatamente;
una rettifica `-0.25` riporta il totale a 0.75, residuo 0.25 e stato
PARZIALMENTE_EVASO. Ogni scenario effettivo incrementa le versioni secondo il
contratto, mentre lo scenario senza variazione non le incrementa.

## 12. Concorrenza

- **Optimistic locking:** `version` su RUN, configurazioni mutabili e STOCK.
- **Row locking:** sequenza ID, RUN in commit, STOCK in movimento.
- **Unique constraint:** public ID, chiave idempotente, posizioni e chiavi candidate.
- **Retry:** nessun retry nei repository; retry applicativo limitato solo per conflitti classificati come transitori.
- **Collisioni ID:** impossibili dopo commit della sequenza; i buchi restano ammessi.
- **RUN concorrenti:** possono leggere in parallelo, ma la unique key impedisce doppio ORDINE. Una futura policy può serializzare RUN operative mediante advisory lock, senza modificare lo schema.
- **Deadlock:** lock sempre in ordine deterministico, per ID interno crescente; transazioni brevi; nessuna chiamata esterna mentre sono detenuti lock.
- **Reporting Google:** eseguito dopo il commit PostgreSQL e fuori dalla transazione autorevole.

## 13. Audit e conservazione storica

### 13.1 Facts immutabili

RACCOLTE e MOVIMENTI sono append-only. ORDINI e CONSEGNE conservano struttura e identità; le sole transizioni ammesse sono auditabili. SEMINE preserva riferimenti e snapshot costitutivi.

### 13.2 Soft e hard delete

- Nessun soft delete generico sui Facts: nascondere un Fact non equivale a correggerlo.
- Configurazioni usano stati ATTIVO/SOSPESO/TERMINATO/DISMESSO quando approvati.
- Hard delete è vietato dopo un evento reale.
- Le eccezioni approvate per registrazioni errate di eventi mai avvenuti richiedono ruolo amministrativo, motivo obbligatorio e audit con snapshot precedente.
- I riferimenti storici usano RESTRICT.

### 13.3 Actor e RUN

`created_by` e `updated_by` contengono un identificatore dell’attore applicativo, non un nome libero presentato all’utente. `run_id` viene persistito su Facts generati dall’Engine. Le operazioni manuali usano correlation ID e actor.

## 14. Normalizzazione

- **1NF:** nessuna lista serializzata nelle colonne; giorni settimana, righe e relazioni N:M sono tabelle.
- **2NF:** le tabelle associative contengono attributi dipendenti dall’intera chiave.
- **3NF:** attributi di CLIENTE, VARIETÀ, configurazioni e Facts sono conservati nella propria fonte.
- **BCNF:** chiavi candidate esplicite; le dipendenze funzionali principali hanno determinante candidato.

Denormalizzazioni intenzionali:

1. snapshot storici nella SEMINA, richiesti per ricostruire il contesto iniziale;
2. STOCK come proiezione corrente autorevole dello stato, derivabile dai MOVIMENTI ma mantenuta per operatività;
3. contatori RUN per lettura diretta e verifica dell’esito;
4. `origine_tipo`/`origine_riferimento` nei MOVIMENTI per origini estensibili non ancora dotate di tabella.

Ogni denormalizzazione ha una fonte dichiarata e un confine transazionale.

## 15. Indici e prestazioni

### 15.1 Principi

- PK e UK creano indici automatici.
- Ogni FK usata in join o delete check riceve un indice lato figlio.
- Gli indici compositi seguono le query reali e iniziano dalle colonne di filtro più selettive/stabili.
- Nessun indice GIN preventivo salvo contesti JSONB interrogati realmente.
- Gli indici parziali proteggono unicità e code operative correnti.

### 15.2 Query critiche

- Scheduling: programmi ATTIVI correnti, date valide, righe e ricorrenze.
- Idempotenza: lookup esatto su chiave.
- ORDINI: stato/data prevista/cliente/programma.
- CONSEGNE: stato/data prevista e relazione con ORDINI.
- STOCK: lookup per VARIETÀ e lock puntuale.
- MOVIMENTI: storico per VARIETÀ ordinato temporalmente.
- RUN: stato, avvio, esito e log cronologico.
- Reporting: viste e future materialized view, non scansioni nel write path.

### 15.3 Volumi e crescita

Le tabelle a crescita principale sono MOVIMENTI, ORDINI/righe, RACCOLTE, RUN_LOG e AUDIT. La v1.0 non introduce partizionamento anticipato. Quando volumi e piani di esecuzione lo richiederanno, MOVIMENTI, RUN_LOG e AUDIT potranno essere partizionati per intervallo temporale senza cambiare l’identità del dominio.

## 16. Google Sheets

Google Sheets NON è il database.

Ruoli ammessi:

- reporting;
- export;
- consultazione;
- dashboard leggere;
- eventuale import controllato, esplicito e validato.

Sincronizzazione:

1. una RUN di reporting legge viste PostgreSQL da una replica o connessione read-only;
2. produce un export deterministico con versione dello schema;
3. aggiorna un foglio dichiarato non autorevole;
4. registra esito e watermark dell’export;
5. può essere ripetuta integralmente;
6. non partecipa alla transazione PostgreSQL;
7. un errore Google non modifica né rende incerto il commit autorevole.

Le modifiche manuali nei fogli non rientrano automaticamente nel database. Un import futuro richiede file/staging, validazione, anteprima, autorizzazione e audit. È vietato il dual-write sincrono PostgreSQL/Sheets.

## 17. Strategia di migrazione

### 17.1 Ordine di creazione logico

1. schema e ruoli;
2. enum ed eventuali estensioni approvate;
3. anagrafiche senza dipendenze;
4. conoscenza produttiva;
5. `id_sequences` e RUN;
6. PROGRAMMI e versioni;
7. ORDINI e origini;
8. SEMINE e RACCOLTE;
9. CONSEGNE e associazioni;
10. STOCK e MOVIMENTI con FK differite necessarie;
11. audit e log;
12. viste;
13. indici aggiuntivi e constraint differibili;
14. privilegi finali.

### 17.2 Bootstrap dati

1. enum e vocabolari;
2. righe iniziali `id_sequences` con valori esplicitamente riconciliati;
3. CLIENTI e VARIETÀ;
4. CULTIVAR, USI, SEMENTI, LOTTI e PROTOCOLLI;
5. PROGRAMMI e versioni;
6. SEMINE e RACCOLTE;
7. ORDINI;
8. CONSEGNE;
9. MOVIMENTI in ordine cronologico;
10. ricostruzione e confronto STOCK;
11. verifica sequenze contro tutti gli ID importati;
12. report finale di riconciliazione.

### 17.3 Ordine adapter

1. Identity e RUN;
2. repository read-only PROGRAMMI e ORDINI;
3. committer PostgreSQL;
4. repository operativi restanti;
5. bootstrap e CLI;
6. import sandbox;
7. reporting Google Sheets;
8. isolamento writer legacy;
9. readiness review.

Ogni migrazione è versionata, forward-only in produzione e accompagnata da procedura di restore. Nessuna modifica manuale dello schema produttivo è ammessa.

## 18. Sicurezza e privilegi

Ruoli separati:

- migrator: modifica schema, non usato dal runtime;
- runtime_writer: esegue casi d’uso autorizzati;
- runtime_reader: sola lettura per Engine e preflight dove applicabile;
- reporting_reader: accesso esclusivamente a viste autorizzate;
- operator: accesso amministrativo limitato;
- auditor: sola lettura di Facts e audit.

Il runtime non è owner delle tabelle. Il namespace pubblico Supabase non deve esporre tabelle autorevoli senza RLS e grant espliciti. Le credenziali privilegiate restano in secret manager o ambiente runtime e non vengono registrate in Git.

## 19. Rischi

- lock prolungati su STOCK o sequenze: mitigare con transazioni brevi e nessun I/O esterno;
- hotspot su ORDINE_ID/RUN_ID: una riga per sequenza limita il lock al singolo tipo; adeguato ai volumi previsti;
- crescita RUN_LOG/AUDIT: retention e partizionamento futuro;
- query di dashboard pesanti: viste/materialized view e replica read-only;
- abuso di JSONB: vietato per entità e relazioni del dominio;
- trigger troppo complessi: limitati a invarianti persistenti;
- modifiche manuali Supabase: privilegi minimi e audit;
- doppia autorità durante migrazione: cutover formale e writer unico;
- timeout con commit incerto: riconciliazione tramite RUN e chiavi univoche;
- schema CLIENTI ancora minimo: nuove informazioni richiedono Architecture Review del dominio CLIENTI;
- riferimenti `origine_riferimento` non vincolati per eventi futuri: sostituire con FK quando il relativo Register sarà congelato.

## 20. Roadmap

1. Sprint 2.10 — PostgreSQL Identity and Run Adapters.
2. Sprint 2.11 — PostgreSQL Programmi and Ordini Adapters.
3. Sprint 2.12 — PostgreSQL Commit Transaction.
4. Sprint 2.13 — Bootstrap and CLI PostgreSQL.
5. Sprint 2.14 — Data Migration Sandbox.
6. Sprint 2.15 — First End-to-End Sandbox Run.
7. Sprint 2.16 — Google Sheets Reporting Adapter.
8. Sprint 2.17 — Production Readiness Review.

Prima dell’implementazione, lo schema deve essere tradotto in migrazioni revisionabili senza alterare le decisioni congelate.

## 21. Questioni aperte

Le seguenti questioni operative non modificano il modello fisico congelato, ma devono essere risolte prima della produzione:

- regione Supabase;
- piano e budget;
- RPO, RTO e retention;
- strumento di migrazione SQL;
- secret manager;
- identità concreta degli actor;
- retention RUN_LOG e AUDIT;
- soglie che giustificano partizionamento;
- frequenza del reporting Google;
- dataset e procedura di importazione;
- strategia di staging separata dalla sandbox;
- monitoraggio di lock, deadlock e query lente.

## 22. Decisioni future

Richiedono una nuova Architecture Review:

- nuovi Register o entità di dominio;
- schema completo CLIENTI;
- FATTURE e SCARTI;
- identificativi pubblici per CULTIVAR, USI, SEMENTI, LOTTI e PROTOCOLLI;
- nuovi valori degli enum di dominio;
- persistenza autonoma del WritePlan;
- materialized view autorevoli o nuove proiezioni persistenti;
- import bidirezionale da Google Sheets;
- soft delete su Facts;
- partizionamento che modifichi chiavi o vincoli;
- modifica dei confini transazionali MOVIMENTO/STOCK o CONSEGNA/MOVIMENTI;
- passaggio a un modello documentale.

## 23. Conclusioni

Il modello fisico PostgreSQL v1.0 preserva i Register congelati, normalizza aggregati e relazioni, rende atomiche Identity, RUN, idempotenza e variazioni STOCK e mantiene il Core indipendente dal provider.

Le fonti autorevoli sono le tabelle PostgreSQL governate da questo documento. Le viste e Google Sheets restano rappresentazioni derivate.

Il presente documento costituisce l’autorità ufficiale per gli Sprint PostgreSQL successivi ed è dichiarato:

**POSTGRESQL PHYSICAL SCHEMA FREEZE v1.0**
