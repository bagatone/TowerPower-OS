# Production Planning PostgreSQL Physical Schema Freeze V1

## 1. Stato e autorità

**Stato:** PHYSICAL SCHEMA FREEZE V1 — candidato a Freeze Review.

Questo documento traduce `PRODUCTION_PLANNING_ENGINE_FREEZE.md` nel modello
fisico PostgreSQL V1. Non autorizza migration, provisioning, backfill,
commissioning Identity o attivazione runtime. PostgreSQL usa lo schema `tpo`.

Restano normative le convenzioni di `POSTGRESQL_PHYSICAL_SCHEMA.md`: PK interne
`bigint`, public ID `text`, quantità `numeric(20,6)`, istanti `timestamptz`, date
business `date`, orari locali `time without time zone`, nessun `float`, audit
esplicito, delete conservativo e PK interne mai esposte come identità di dominio.

Regole comuni:

- public ID `NOT NULL`, `UNIQUE`, immutabile, prefisso più almeno sei cifre;
- FK operative e storiche `ON DELETE RESTRICT` dopo il commit autorevole;
- `version bigint NOT NULL DEFAULT 0 CHECK (version >= 0)` per entità mutabili;
- actor `text` non vuoto e timestamp applicativi espliciti, senza default nascosti;
- revisioni, snapshot, log e fatti storici append-only;
- `Atlantic/Canary` per la semantica locale, `timestamptz` per gli istanti;
- JSONB non è l'unica authority di alcuno snapshot Planning.

## 2. Enum PostgreSQL

```text
production_planning_run_state =
  OPEN | COMMITTED | FAILED | RECONCILIATION_REQUIRED

protocollo_versione_approval_state =
  BOZZA | APPROVATA | RITIRATA

planning_allocation_state =
  ATTIVA | CONSUMATA | RILASCIATA | SOSTITUITA | INVALIDA

allocation_type =
  DOMANDA | STOCK | PRODUZIONE_IN_CORSO | RACCOLTA

quantitative_buffer_policy_type =
  NONE | PERCENTAGE | ABSOLUTE_SET

replanning_reason_code =
  DEMAND_CHANGED | DELIVERY_CHANGED | STOCK_CHANGED |
  IN_PROGRESS_CHANGED | HARVEST_RESULT_CHANGED | PROTOCOL_CHANGED |
  PLAN_LATE | MANUAL_REPLAN_AUTHORIZED

planning_failure_category =
  PLANNING_INPUT_INVALID | PRODUCTION_KNOWLEDGE_INVALID |
  PLANNING_INFEASIBLE | ALLOCATION_CONFLICT | CONCURRENCY_CONFLICT |
  COMMIT_FAILED_ROLLED_BACK | RECONCILIATION_REQUIRED | INTERNAL_ERROR

riga_piano_semina_state =
  PIANIFICATA | PRONTA | AVVIATA | SODDISFATTA |
  ANNULLATA | SOSTITUITA | TARDIVA
```

`run_message_type`, `run_log_level`, `ordine_state`, `semina_state` e
`unit_of_measure` esistenti vengono riutilizzati. `stato_complessivo` del piano
resta `text NOT NULL` non vuoto: il contratto non congela un insieme chiuso e
non viene inventato un enum.

### 2.1 Hash fisico e canonical encoding V1

`planning_key_v1`, `replanning_key_v1`, `revision_request_key` e
`canonical_snapshot_hash` usano esclusivamente SHA-256 su input UTF-8. Il digest
è lowercase hexadecimal ASCII di 64 caratteri, persistito come `text` con CHECK
`value ~ '^[0-9a-f]{64}$'`.

Ogni valore non NULL è framed come `<length-in-utf8-bytes>:<value>`; NULL è
esattamente `-1:`. Una lista è `<count-base10>;` seguita dagli elementi, ciascuno
framed allo stesso modo. Record e mappe serializzano i campi esclusivamente
nell'ordine normativo. Vietati concatenazione libera, JSON, pickle, `repr()`,
SHA-512 ed encoding provider-specific.

Decimal: base 10, mai float/scientifica, trailing zero rimossi, zero `0`. Date:
`YYYY-MM-DD`. Local time: `HH:MM`. Timestamp: ISO 8601 timezone-aware, offset
Atlantic/Canary effettivo, precisione al minuto. Boolean: `true`/`false`. Enum:
valore normativo case-sensitive. Public ID: stringa esatta. Integer: base 10
senza leading zero salvo `0`.

`canonical_bytes=UTF-8(canonical_framed_string)`;
`digest=SHA256(canonical_bytes)`; `stored_key=lowercase_hex(digest)`.

`planning_key_v1` serializza, nell'ordine: `production-planning-v1`, public ID
riga ordine, quantità residua canonica, data consegna, public ID versione
protocollo, Planning Policy Set Version. `replanning_key_v1` serializza:
`production-replanning-v1`, public ID revisione precedente, public ID riga
ordine, reason code, snapshot autorevole completo, Planning Policy Set Version.

La prima `revision_request_key` serializza: `production-planning-revision-v1`,
policy set code, policy set version, numero righe e lista delle planning key
ordinata lessicograficamente crescente. In replanning coincide con
`replanning_key_v1`. `canonical_hash` è SHA-256 dello snapshot autorevole
completo con lo stesso framing.

### 2.2 PostgreSQL required extensions

V1 richiede l'estensione PostgreSQL `btree_gist` esclusivamente per le
exclusion constraint che combinano uguaglianza GiST su `bigint` o `text` con
overlap su `daterange`.

Prerequisito DDL della migration:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```

Ordine obbligatorio: verificare la presenza dell'estensione; crearla se assente;
soltanto dopo creare le exclusion constraint. Se l'ambiente target non autorizza
`CREATE EXTENSION`, commissioning/deployment deve verificare che `btree_gist`
sia già disponibile prima della migration e dell'attivazione. Estensione
indisponibile significa failure fail-closed: non è ammessa sostituzione silenziosa
con validazione applicativa. La dipendenza resta confinata all'Infrastructure
PostgreSQL e non introduce dipendenze applicative provider-specific.

Per entrambe le exclusion constraint, il range è esattamente
`daterange(valida_dal, valida_al, '[)')`: `valida_al NULL` produce un upper bound
infinito PostgreSQL e conserva la semantica half-open `[valida_dal,valida_al)`.

## 3. Identity persistente

| `sequence_name` | `identifier_type` | `prefix` | esempio |
|---|---|---|---|
| `RUN_PIANIFICAZIONE_PRODUZIONE_ID` | `RunPianificazioneProduzioneId` | `RPP` | `RPP-000001` |
| `PIANO_PRODUZIONE_ID` | `PianoProduzioneId` | `PP` | `PP-000001` |
| `REVISIONE_PIANO_PRODUZIONE_ID` | `RevisionePianoProduzioneId` | `RVP` | `RVP-000001` |
| `RIGA_PIANO_SEMINA_ID` | `RigaPianoSeminaId` | `RPS` | `RPS-000001` |
| `ALLOCAZIONE_ID` | `AllocazioneId` | `ALL` | `ALL-000001` |
| `RIGA_ORDINE_ID` | `RigaOrdineId` | `RO` | `RO-000001` |
| `VERSIONE_PROTOCOLLO_ID` | `VersioneProtocolloId` | `PV` | `PV-000001` |

La migration non inserisce righe in `id_sequences` e non sceglie `next_value`.
Commissioning e riconciliazione di ID storici sono separati e fail-closed.
Snapshot, policy, messaggi, log, risorsa seme e relazione piano-semina non
ricevono public ID.

## 4. Estensioni esistenti

### 4.1 `tpo.ordini`

Aggiunge `version bigint NOT NULL DEFAULT 0 CHECK (version >= 0)`. Una
transizione del solo stato incrementa la testata. Ogni evento autorevole che
cambia quantità consegnata o residuo di una riga incrementa atomicamente testata
e riga. Identità e struttura commerciale restano immutate. Nessun nuovo indice:
la versione è confrontata sulla PK sotto row lock. Writer e delete policy
ORDINI/CONSEGNE restano invariati; Planning è read-only.

### 4.2 `tpo.righe_ordine`

| colonna | tipo | null/default | vincolo |
|---|---|---|---|
| `public_id` | `text` | `NOT NULL` | `UNIQUE`, `CHECK (public_id ~ '^RO-[0-9]{6,}$')` |
| `version` | `bigint` | `NOT NULL DEFAULT 0` | `CHECK (version >= 0)` |

Le nuove righe ricevono l'ID da `RIGA_ORDINE_ID` prima dell'INSERT. Nessun
backfill è implicito. Righe operative preesistenti richiedono commissioning e
backfill separati prima di convalidare `NOT NULL`. La versione protegge input e
residuo; quantità ordinata, varietà e posizione restano immutabili. Indice UK
`public_id`; indici e delete policy esistenti invariati.

### 4.3 `tpo.protocollo_versioni`

Conserva PK, FK, numero, genealogia, motivazione, evidenze e audit esistenti.

| colonna | tipo | null/default | vincolo |
|---|---|---|---|
| `public_id` | `text` | `NOT NULL` | UNIQUE, formato `PV-[0-9]{6,}` |
| `stato_approvazione` | `protocollo_versione_approval_state` | `NOT NULL` | nessun default |
| `idratazione_ore` | `numeric(20,6)` | `NOT NULL` | `>= 0` |
| `orario_semina_previsto` | `time without time zone` | `NOT NULL` | — |
| `orario_raccolta_target` | `time without time zone` | `NOT NULL` | — |
| `germinazione_giorni` | `integer` | `NOT NULL` | `>= 0` |
| `crescita_luce_giorni` | `integer` | `NOT NULL` | `>= 0` |
| `ciclo_produttivo_nominale_giorni` | `integer GENERATED ALWAYS AS (germinazione_giorni + crescita_luce_giorni) STORED` | `NOT NULL` | derivato |
| `grammi_seme_per_set` | `numeric(20,6)` | `NOT NULL` | `> 0` |
| `resa_attesa` | `numeric(20,6)` | `NOT NULL` | `> 0` |
| `resa_unita_misura` | `unit_of_measure` | `NOT NULL` | — |
| `granularita_produttiva` | `numeric(20,6)` | `NOT NULL` | `> 0` |
| `harvest_min_lead_giorni` | `integer` | `NOT NULL` | `>= 1` |
| `harvest_max_lead_giorni` | `integer` | `NOT NULL` | `>= harvest_min_lead_giorni` |
| `buffer_temporale_minuti` | `integer` | `NOT NULL` | `>= 0` |
| `valida_dal` | `date` | `NOT NULL` | limite incluso |
| `valida_al` | `date` | `NULL` | `NULL OR > valida_dal` |
| `provenance` | `text` | `NOT NULL` | non vuoto |
| `approvata_at/by` | `timestamptz` / `text` | `NULL` | valorizzati insieme |
| `ritirata_at/by` | `timestamptz` / `text` | `NULL` | valorizzati insieme |

`contenuto` esistente resta descrittivo legacy e non è authority Planning.
Validità `[valida_dal,valida_al)`. Exclusion GiST sullo stesso `protocollo_id`
e `daterange(valida_dal,valida_al,'[)')` impedisce sovrapposizioni tra versioni
APPROVATA. Restano `UNIQUE(protocollo_id,numero_versione)` e
`UNIQUE(versione_precedente_id)`.

Lifecycle CHECK: BOZZA non ha approvazione/ritiro; APPROVATA ha approvazione e
non ritiro; RITIRATA conserva sempre ritiro e conserva approvazione soltanto se
proveniente da APPROVATA. Per RITIRATA `approvata_at` e `approvata_by` sono
quindi entrambi NULL dopo BOZZA→RITIRATA oppure entrambi NOT NULL dopo
APPROVATA→RITIRATA; una coppia parzialmente valorizzata è vietata. Transizioni
esclusive BOZZA→APPROVATA, BOZZA→RITIRATA, APPROVATA→RITIRATA; il writer vieta
APPROVATA→BOZZA e qualunque transizione in uscita da RITIRATA. Parametri,
provenance ed evidenze sono immutabili dopo approvazione. Dopo il primo uso sono
immutabili anche identità, numero, genealogia e `valida_dal`; sono ammesse
soltanto chiusura auditata `valida_al` e ritiro. Nessun hard delete dopo
approvazione.

Indici: UK public ID; FK protocollo; (`protocollo_id`,`stato_approvazione`,
`valida_dal`,`valida_al`); versione precedente. Writer: knowledge writer, mai
Planning.

### 4.4 `tpo.audit_eventi`

Aggiunge `planning_run_id bigint NULL` FK a `production_planning_runs(id)`
`ON DELETE RESTRICT` e `CHECK (num_nonnulls(run_id,planning_run_id) <= 1)`.
`run_id` resta esclusivamente Scheduling RUN; sono ammessi audit senza RUN.
Indici: `planning_run_id` e (`planning_run_id`,`occurred_at`).

### 4.5 `tpo.semine`

**CURRENT COLUMNS PRESERVED:** `id`, `public_id`, `varieta_id`, `cultivar_id`,
`cultivar_uso_id`, `lotto_seme_id`, `protocollo_versione_id`, `stato`,
`quantita_seme`, `unita_misura`, `data_avvio`, `causa_origine`, `esito_finale`,
snapshot storici, `created_at`, `created_by` e tutti i vincoli esistenti.

**NEW COLUMN:** `version bigint NOT NULL DEFAULT 0`, mutabile soltanto dal writer
autorevole SEMINE. **NEW CHECK:** `version >= 0`. Nessun nuovo indice.

La versione protegge stato, eleggibilità, resa prevista/allocabile e ogni dato
SEMINA osservabile da Planning. Incrementa per ogni mutazione autorevole di tali
dati; non incrementa per letture, log, note, Planning RUN o allocazioni che non
modificano SEMINA. Planning blocca SEMINA, confronta expected version e
riverifica stato/eleggibilità/quantità; mismatch produce
`CONCURRENCY_CONFLICT`, rollback completo e nessun retry cieco.

Il backfill deterministico `version = 0` per SEMINE preesistenti è sicuro: è un
token tecnico valido dall'attivazione del nuovo writer, non crea identità, non
modifica fatti biologici e non ricostruisce storia pregressa. È distinto dal
commissioning dei dati produttivi. Mutability, delete policy e writer authority
esistenti di SEMINE restano invariati.

## 5. Policy e Planning RUN

### 5.1 `tpo.production_planning_policy_versions`

PK `id bigint GENERATED BY DEFAULT AS IDENTITY`. Colonne `policy_set_code text
NOT NULL`, `numero_versione integer NOT NULL CHECK > 0`,
`harvest_target_strategy text NOT NULL CHECK = 'EARLIEST_APPROVED_WINDOW'`,
`buffer_quantitativo_tipo quantitative_buffer_policy_type NOT NULL`,
`buffer_quantitativo_valore numeric(20,6) NULL`, `priority_policy_code text NOT
NULL`, `planning_algorithm_version text NOT NULL`, `valida_dal date NOT NULL`,
`valida_al date NULL`, `provenance text NOT NULL`, `evidenze text NULL`,
`approved_at timestamptz NOT NULL`, `approved_by text NOT NULL`, `created_at
timestamptz NOT NULL`, `created_by text NOT NULL`.

`UNIQUE(policy_set_code,numero_versione)` ed exclusion su intervalli dello stesso
set. NONE richiede valore NULL; PERCENTAGE/ABSOLUTE_SET valore non negativo.
Nessun parametro protocollo è duplicato. Indici su code/validità e versione.
Immutabile, RESTRICT se usata, senza optimistic version. Writer: commissioning o
policy writer, mai runtime Planning ordinario.

### 5.2 `tpo.production_planning_runs`

PK `id bigint` identity; `public_id text NOT NULL UNIQUE` formato RPP;
`policy_version_id bigint NOT NULL` FK; `business_at timestamptz NOT NULL`;
`state production_planning_run_state NOT NULL DEFAULT 'OPEN'`; `started_at
timestamptz NOT NULL`; `completed_at timestamptz NULL`; contatori `bigint NOT
NULL DEFAULT 0 CHECK >= 0` per ordini letti, righe valutate, righe coperte
integralmente/parzialmente, righe piano, allocazioni, righe tardive, righe non
producibili ed elementi saltati; `created_by text NOT NULL`; `version bigint NOT
NULL DEFAULT 0 CHECK >= 0`.

OPEN richiede completion NULL; stato terminale completion non NULL e non
precedente allo start. Lifecycle OPEN→COMMITTED|FAILED|RECONCILIATION_REQUIRED,
nessuna riapertura. Indici: UK public ID; FK policy; (`state`,`started_at`);
`business_at`. Writer Run, CAS obbligatorio, delete vietato dopo apertura.

### 5.3 `tpo.production_planning_run_messaggi`

PK `id bigint` identity; `planning_run_id bigint NOT NULL` FK; `posizione integer
NOT NULL CHECK >0`; `tipo run_message_type NOT NULL`; `failure_category
planning_failure_category NULL`; `codice text NOT NULL`; `messaggio text NOT
NULL`; `created_at timestamptz NOT NULL`. UNIQUE (`planning_run_id`,`posizione`).
ERROR richiede categoria; WARNING la vieta. Indici FK e tipo/posizione.
Append-only, RESTRICT, messaggi sanitizzati. Writer Run/failure-finalizer.

### 5.4 `tpo.production_planning_run_log`

PK `id bigint` identity; FK run; `posizione bigint NOT NULL CHECK >0`; `livello
run_log_level NOT NULL`; `codice_evento text NOT NULL`; `messaggio text NOT
NULL`; `occurred_at timestamptz NOT NULL`. UNIQUE (run,posizione). Indici run e
(run,occurred_at,posizione). Append-only, RESTRICT, nessun dato sensibile.

## 6. Piano, revisione e righe

### 6.1 `tpo.piani_produzione`

PK `id bigint` identity; `public_id text NOT NULL UNIQUE` formato PP;
`current_revision_id bigint NULL`; `stato_complessivo text NOT NULL` non vuoto;
audit created/updated NOT NULL; `version bigint NOT NULL DEFAULT 0 CHECK >=0`.
Il current pointer cambia solo mediante CAS. UK sul current pointer non NULL.
Nessun hard delete dopo prima revisione. Writer Planning Commit Repository.

### 6.2 `tpo.piano_produzione_revisioni`

PK `id bigint` identity; `public_id text NOT NULL UNIQUE` formato RVP;
`piano_produzione_id bigint NOT NULL` FK; `planning_run_id bigint NOT NULL` FK;
`numero_revisione integer NOT NULL CHECK >0`; `revisione_precedente_id bigint
NULL` FK self; `policy_version_id bigint NOT NULL` FK; `business_at timestamptz
NOT NULL`; `replanning_reason_code replanning_reason_code NULL`;
`revision_request_key text NOT NULL`; `replanning_snapshot_id bigint NULL`;
`sostituita_at timestamptz NULL`;
`sostituita_by text NULL`; audit created NOT NULL; `version bigint NOT NULL
DEFAULT 0 CHECK >=0`.

UNIQUE (piano,numero), UNIQUE (precedente), UNIQUE (`revision_request_key`) e
UNIQUE (piano,id). La prima revisione deriva `revision_request_key` dalla
versione dello schema della chiave, dalla Planning Policy Set Version e dalla
lista ordinata delle `planning_key` delle righe. Le revisioni successive usano
come `revision_request_key` la `replanning_key_v1` e richiedono precedente,
reason e `replanning_snapshot_id`; la prima revisione li vieta. La precedente
appartiene allo stesso piano e ha numero immediatamente precedente. Payload
immutabile; soltanto `sostituita_at/by`
può essere valorizzato con CAS. Indici run, policy, piano/numero DESC, precedente
e chiavi.

La forma canonica della prima revisione è
il framing SHA-256 definito al §2.1. Per replanning `revision_request_key`
coincide esattamente con `replanning_key_v1`; non esiste una seconda chiave.

Ogni revisione è uno snapshot completo: contiene nuove RPS per tutte le righe
correnti, incluse quelle invariate, e non richiede composizione con la revisione
precedente. Righe invariate conservano la stessa equivalenza `planning_key_v1`
ma ricevono nuovo public ID RPS.

Dopo entrambe le tabelle si aggiunge la FK circolare:

```text
FOREIGN KEY (id,current_revision_id)
REFERENCES piano_produzione_revisioni (piano_produzione_id,id)
DEFERRABLE INITIALLY DEFERRED
```

Essa garantisce che la revisione corrente appartenga allo stesso piano. Il
pointer è valorizzato nello stesso commit della revisione. RESTRICT, append-only.

### 6.3 `tpo.righe_piano_semina`

PK `id bigint` identity; public ID RPS UNIQUE; FK revisione, riga ordine,
`varieta_id` verso `tpo.varieta(id)`, `cultivar_id` verso `tpo.cultivar(id)`,
`cultivar_uso_id` verso `tpo.cultivar_usi(id)` e protocollo versione;
`varieta_public_id_snapshot`, `cultivar_snapshot` e `uso_produttivo_snapshot`
sono `text NOT NULL` e preservano descrizioni storiche senza sostituire le FK;
`ordine_version_attesa` e `riga_ordine_version_attesa
bigint NOT NULL CHECK >=0`; domanda originaria `>0`; quantità consegnata,
residuo, coperture stock/in corso/raccolta, deficit, buffer calcolato,
pre-granularità, autorizzata, avviata e residua `numeric(20,6) NOT NULL CHECK
>=0`; tipo/valore buffer quantitativo; granularità `>0`; resa attesa `>0` e UOM;
grammi seme `>0`; UOM domanda; `data_consegna date`; harvest window start/end
`date`; `harvest_target_at`, `sowing_at`, `light_at`, `hydration_at timestamptz`;
timezone `text CHECK = 'Atlantic/Canary'`; snapshot degli orari locali;
`buffer_temporale_minuti integer CHECK >=0`; stato congelato; planning key;
provenance; audit created/updated; version CAS.

UNIQUE (revisione,riga ordine) e UNIQUE (revisione,planning key). Non esiste
UNIQUE globale sulla planning key. Residuo commerciale è
domanda meno consegnato; somma coperture non supera residuo; deficit è residuo
meno coperture; autorizzata è multiplo della granularità; avviata non supera
autorizzata; residuo da avviare è autorizzata meno avviata; window start ≤ target
locale ≤ window end < consegna. Istanti canonici hanno secondi e microsecondi
zero. Invarianti inter-riga sono riverificati dal writer. Sotto lock il writer
verifica che VARIETA coincida con RIGA_ORDINE, CULTIVAR appartenga a VARIETA,
CULTIVAR_USO appartenga alla CULTIVAR e PROTOCOLLO_VERSIONE appartenga allo
stesso CULTIVAR_USO. Nessun trigger contiene questa business logic.

Indici: FK revision/riga/protocollo; (`stato`,`sowing_at`);
(`stato`,`harvest_target_at`); consegna; planning key. Lifecycle esclusivamente
quello dell'enum; CAS su transizioni/quantità; nessun hard delete.

### 6.4 `tpo.risorse_seme_pianificate`

PK `id bigint` identity; `riga_piano_semina_id bigint NOT NULL` FK e UNIQUE;
`cultivar_uso_id bigint NOT NULL` FK; `protocollo_versione_id bigint NOT NULL`
FK; `grammi_richiesti numeric(20,6) NOT NULL CHECK >0`;
`grammi_seme_per_set numeric(20,6) NOT NULL CHECK >0`; `unita_misura
unit_of_measure NOT NULL CHECK = 'GRAM'`; audit created NOT NULL.

Snapshot immutabile coerente con riga e protocollo. Nessuna FK a SEMENTE o
LOTTO_SEME. Indici cultivar uso e protocollo. RESTRICT; writer Planning.

## 7. Allocazioni tipizzate

### 7.0 `tpo.allocazioni`

Registry parent e unica authority di identità, lifecycle, quantità, audit e
versione.

| colonna | tipo | nullabilità | default | authority/mutabilità |
|---|---|---|---|---|
| `id` | `bigint GENERATED BY DEFAULT AS IDENTITY` | NOT NULL | identity | PK immutabile |
| `public_id` | `text` | NOT NULL | NO DEFAULT | AllocazioneId immutabile |
| `allocation_type` | `allocation_type` | NOT NULL | NO DEFAULT | immutabile |
| `riga_piano_semina_id` | `bigint` | NOT NULL | NO DEFAULT | destinazione immutabile |
| `quantity` | `numeric(20,6)` | NOT NULL | NO DEFAULT | immutabile |
| `unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | immutabile |
| `state` | `planning_allocation_state` | NOT NULL | NO DEFAULT | lifecycle CAS |
| `created_at` | `timestamptz` | NOT NULL | NO DEFAULT | immutabile |
| `created_by` | `text` | NOT NULL | NO DEFAULT | immutabile |
| `updated_at` | `timestamptz` | NOT NULL | NO DEFAULT | lifecycle CAS |
| `updated_by` | `text` | NOT NULL | NO DEFAULT | lifecycle CAS |
| `version` | `bigint` | NOT NULL | `0` | lifecycle CAS |

PK `CONSTRAINT allocazioni_pkey PRIMARY KEY (id)`; UNIQUE
`CONSTRAINT uq_allocazioni_public_id UNIQUE (public_id)`; FK `CONSTRAINT
allocazioni_riga_piano_semina_id_fkey FOREIGN KEY (riga_piano_semina_id)
REFERENCES tpo.righe_piano_semina(id) ON UPDATE RESTRICT ON DELETE RESTRICT`.
CHECK formato `public_id ~ '^ALL-[0-9]{6,}$'`, `quantity > 0`, `version >= 0`,
`btrim(created_by) <> ''` e `btrim(updated_by) <> ''`.

`state` non ha DEFAULT: il writer fornisce esplicitamente `ATTIVA` all'INSERT.
`allocation_type`, `riga_piano_semina_id`, `quantity` e `unita_misura` sono
immutabili. Soltanto `state`, `updated_at`, `updated_by` e `version` mutano con
CAS durante il lifecycle. `created_at` e `created_by` restano immutabili;
`updated_at` e `updated_by` descrivono l'ultima transizione, mentre la storia
completa delle transizioni è conservata dagli audit event autorevoli.

Indici: `ix_allocazioni_riga_piano_state` (`riga_piano_semina_id`,`state`) e
`ix_allocazioni_type_state` (`allocation_type`,`state`). `allocation_type` è
enum `DOMANDA|STOCK|PRODUZIONE_IN_CORSO|RACCOLTA`. Lifecycle esclusivo
ATTIVA→CONSUMATA|RILASCIATA|SOSTITUITA|INVALIDA; gli stati terminali non sono
riattivabili. Nessun hard delete. Writer: Production Planning allocation writer.

Ogni parent possiede esattamente una child dello stesso tipo. Il constraint
trigger `ct_allocazioni_exactly_one_child`, DEFERRABLE INITIALLY DEFERRED e
puramente strutturale, verifica a fine transazione che esista esattamente una
child e che la sua tabella corrisponda ad `allocation_type`; non applica logica
quantitativa, lifecycle, eligibility o policy.

### 7.1 `tpo.allocazioni_domanda`

Aggiunge `allocation_id bigint NOT NULL` senza default, `CONSTRAINT
allocazioni_domanda_pkey PRIMARY KEY (allocation_id)` e `CONSTRAINT
allocazioni_domanda_allocation_id_fkey FOREIGN KEY (allocation_id) REFERENCES
tpo.allocazioni(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; aggiunge inoltre
`riga_ordine_id bigint NOT NULL` senza default e `CONSTRAINT
allocazioni_domanda_riga_ordine_id_fkey FOREIGN KEY (riga_ordine_id) REFERENCES
tpo.righe_ordine(id) ON UPDATE RESTRICT ON DELETE RESTRICT`. Nessun'altra
colonna, version o audit e nessun vincolo UNIQUE oltre alla PK: il vincolo
composto (`riga_ordine_id`,`allocation_id`) è ridondante perché `allocation_id`
è già PK e non esprime alcun ulteriore invariante di business. Indice
`ix_allocazioni_domanda_riga_ordine` (`riga_ordine_id`). Append-only; partecipa
a `ct_allocazioni_exactly_one_child` e richiede parent con `allocation_type =
'DOMANDA'`. Writer allocation. Il writer blocca ordine/riga e garantisce
copertura entro residuo.

### 7.2 `tpo.allocazioni_stock`

Aggiunge `allocation_id bigint NOT NULL` PK/FK parent RESTRICT e
`stock_varieta_id bigint NOT NULL` FK → `tpo.stock(varieta_id)` RESTRICT.
Nessun'altra colonna, version o audit. Indice `stock_varieta_id`. Parent tipo
STOCK. Append-only; writer allocation. Writer blocca STOCK e
garantisce ATTIVA+CONSUMATA entro disponibilità. Non modifica STOCK.

### 7.3 `tpo.allocazioni_produzione_in_corso`

Aggiunge `allocation_id bigint NOT NULL` PK/FK parent RESTRICT e `semina_id
bigint NOT NULL` FK → `tpo.semine(id)` RESTRICT. Nessun'altra colonna, version o
audit. Indice `semina_id`. Parent tipo PRODUZIONE_IN_CORSO. Append-only; writer
allocation. Writer blocca SEMINA, confronta `semine.version` e garantisce ATTIVA+CONSUMATA
entro resa allocabile. Non modifica SEMINA.

### 7.4 `tpo.allocazioni_raccolta`

Aggiunge `allocation_id bigint NOT NULL` PK/FK parent RESTRICT e `raccolta_id
bigint NOT NULL` FK → `tpo.raccolte(id)` RESTRICT. Nessun'altra colonna, version
o audit. Indice `raccolta_id`. Parent tipo RACCOLTA. Append-only; writer
allocation. Writer blocca RACCOLTA e garantisce
ATTIVA+CONSUMATA entro quantità reale. Non modifica RACCOLTA. SODDISFATTA è
ammessa solo quando allocazioni raccolta definitivamente CONSUMATE raggiungono
la quantità autorizzata, nella stessa transazione.

Le child non duplicano public ID, quantità, stato, audit o version. Il vincolo
UNIQUE PostgreSQL della parent rende AllocazioneId globalmente univoco. Nessuna
nuova Identity: la parent usa `ALLOCAZIONE_ID`; ID allocati e non usati non
vengono riutilizzati.

## 8. Piano → SEMINA

### `tpo.righe_piano_semina_semine`

PK `id bigint` identity; FK riga piano e semina; `quantita_avviata
numeric(20,6) NOT NULL CHECK >0`; UOM; audit created. UNIQUE (riga piano,semina)
e UNIQUE (semina): una SEMINA ha una sola causa piano. Append-only e RESTRICT.
Lotto e SEMENTE restano esclusivamente nella SEMINA.

Il writer operatore blocca riga piano e link, verifica expected version, crea
SEMINA e link, aggiorna quantità/stato e audit in un commit. Somma link uguale al
contatore e non superiore all'autorizzata. Indici riga piano, semina e data.

## 9. Snapshot replanning

### 9.1 `tpo.replanning_snapshots`

PK bigint identity; nessuna FK alla revisione; public ID riga ordine e ordine; stati e
version di entrambi; quantità ordinata/consegnata/residua; data consegna; public
ID varietà e protocollo; numero/versione e validità DATE protocollo; code e
version policy; tipo/valore buffer quantitativo; buffer temporale; granularità;
public ID e version revisione precedente; reason; `canonical_text text NOT NULL`;
`canonical_hash text NOT NULL`; audit created.

Quantità usano numeric(20,6), version non negative, date half-open. UNIQUE hash
non sostituisce UNIQUE replanning key; stessa hash con testo differente è
fail-closed. Indici revisione, hash, riga ordine, revisione precedente.

### 9.2 `tpo.replanning_snapshot_stock`

PK (`snapshot_id`,`posizione`); posizione positiva; resource public ID, variety
public ID, quantità eleggibile/allocata/residua non negative, resource version e
readiness code. UNIQUE (snapshot,resource ID). L'identità stock è il public ID
VARIETA, poiché STOCK ha una sola riga per varietà.

### 9.3 `tpo.replanning_snapshot_semine`

PK (`snapshot_id`,`posizione`); public ID semina/varietà/protocollo; quantità
utile prevista/allocata/residua; harvest window timestamptz; stato e version
SEMINA. UNIQUE (snapshot,semina ID).

### 9.4 `tpo.replanning_snapshot_allocazioni`

PK (`snapshot_id`,`posizione`); public ID allocazione; tipo text CHECK in
DOMANDA/STOCK/PRODUZIONE_IN_CORSO/RACCOLTA; source public ID; destination RO;
quantità/UOM; stato e version. UNIQUE (snapshot,allocation ID).

Le liste sono persistite già ordinate: stock per resource ID, semine per SeminaId,
allocazioni per AllocazioneId. Posizioni dense da 1. Testata e child sono
immutabili. Testo canonico e componenti normalizzate si verificano a vicenda;
nessuno dei due è sostituito da JSONB.

## 10. Audit e writer authority

Il Production Planning Commit Repository è l'unico writer di piani, revisioni,
righe, risorse e allocazioni nel commit Planning. Il Run writer apre/finalizza la
Planning RUN. Il comando operatore Piano→SEMINA è autorizzato solo alla propria
transizione. Planning non modifica ORDINI, STOCK, SEMINE esistenti, RACCOLTE,
CONSEGNE o MOVIMENTI.

INSERT e transizioni di piano, revisione, riga e allocazione producono audit con
`planning_run_id` quando originati da Planning. Audit e dati sono atomici.
RESTRICT su dati committati; nessun cascade operativo o riscrittura storica.

## 11. Enforcement e lock order

CHECK/UNIQUE/FK/exclusion proteggono invarianti locali. L'unico writer sotto row
lock garantisce: stock allocato ≤ disponibile; produzione allocata ≤ resa;
raccolta allocata ≤ quantità reale; domanda coperta ≤ residuo; quantità avviata
= somma link ≤ autorizzata; release/transfer solo non consumato; version/stati
correnti. Nessun trigger con business logic. Constraint trigger differibili
solo per invarianti strutturali già congelati.

Identity usa transazioni brevi separate; più sequence vengono bloccate per
`sequence_name` crescente e mai insieme ai lock business. Ordine commit Planning:

1. `production_planning_runs`, PK crescente;
2. `ordini`, PK crescente;
3. `righe_ordine`, PK crescente;
4. `stock`, `varieta_id` crescente;
5. `semine`, PK crescente;
6. `raccolte`, PK crescente;
7. `piani_produzione`, PK crescente;
8. revisioni correnti, PK crescente;
9. parent `allocazioni`, PK crescente;
10. child DOMANDA, STOCK, PRODUZIONE_IN_CORSO, RACCOLTA, poi `allocation_id` crescente;
11. righe piano già esistenti, PK crescente.

Nuovi record non richiedono lock prima dell'INSERT; UNIQUE è difesa finale.
Transazioni brevi, nessun I/O esterno, advisory lock globale o retry cieco.
Scheduling conserva il proprio lock order e non acquisisce risorse Planning.

## 12. `tpo.v_calendario_produzione`

View ricostruibile, non tabella, writer o authority. Espone almeno event
timestamp/date Atlantic/Canary, tipo, planned flag, public ID
piano/revisione/riga/SEMINA/RACCOLTA/CONSEGNA quando applicabili, stato
sorgente, varietà/cultivar/uso, quantità/UOM, data consegna e provenance.
`event_at` è `timestamptz NOT NULL`: ogni riga possiede un istante autorevole o
già deterministicamente calcolato e persistito nella sorgente.

Fonti: righe piano/revisioni, link e SEMINE, RACCOLTE e CONSEGNE. PROBLEMI entra
solo dopo una relazione fisica approvata. La view unisce eventi
`IDRATAZIONE_PIANIFICATA`, `SEMINA_PIANIFICATA`, `LUCE_PIANIFICATA`,
`RACCOLTA_TARGET` e fatti reali senza stato autonomo. Gli eventi pianificati
della RPS espongono `righe_piano_semina.data_consegna`, snapshot della data
commerciale autorevole `ordini.data_consegna_prevista`, esclusivamente come
colonna contestuale `data_consegna`: tale DATE non genera una riga calendario
autonoma.

È vietato convertire automaticamente `consegne.data_prevista` da DATE a
`timestamptz`: non sono ammessi mezzanotte convenzionale, timezone injection
implicita, orari hardcoded o conversioni provider-specific arbitrarie.
`tpo.consegne` contribuisce esclusivamente con `stato = 'CONSEGNATA'` e
`data_effettiva IS NOT NULL`; l'unico event type logistico V1 è
`CONSEGNA_EFFETTIVA`. `CONSEGNA_PIANIFICATA` e `CONSEGNA_PREVISTA` non esistono
in V1.

Per l'acceptance La Jaira, prima della consegna del 2026-08-15 tale DATE appare
come `data_consegna` degli eventi pianificati e non produce un `event_at`
artificiale. Dopo una consegna reale, `data_effettiva` produce
`CONSEGNA_EFFETTIVA`, `data_prevista` resta la `data_consegna` associata ed
`event_date` deriva da `data_effettiva` in Atlantic/Canary. Gli indici sono
quelli sulle sorgenti. Materializzazione futura richiede review di refresh e
staleness.

## 13. Strategia staged di migration e commissioning

**FASE A — Schema expansion/pre-validation.** Precheck schema/Alembic/dati;
creazione enum ed estensioni; nuove tabelle; aggiunta inizialmente nullable delle
colonne destinate a dati preesistenti; `semine.version` può essere valorizzata a
0; nessun default biologico o dato produttivo inventato.

**FASE B — Identity commissioning.** Commissioning separato e riconciliato di
RPP, PP, RVP, RPS, ALL, RO e PV. Nessuna scelta arbitraria di `next_value`.

**FASE C — Productive protocol commissioning.** Per ogni versione destinata a
Planning, procedura revisionata e operatore valorizzano stato, idratazione,
orari, germinazione, crescita, harvest window, grammi/SET, resa/UOM,
granularità, buffer temporale, provenance/evidenze e validità. Vietati fixture,
default fittizi, import Google implicito e deduzione non approvata dal legacy.

**FASE D — Postcheck.** Verifica completezza, validità, non sovrapposizione,
APPROVATA dove autorizzato, PV e provenance; verifica RO e version tecniche.

**FASE E — Constraint validation.** Solo dopo PASS: NOT NULL finali, VALIDATE
FK/CHECK, UNIQUE ed exclusion finali, FK circolare, audit e view.

**FASE F — Runtime activation.** Planning resta disabilitato finché schema,
Identity, protocolli reali e postcheck non sono tutti PASS. Migration monotone e
piccole; nessun reset Identity, import Google o modifica storica implicita.

## 14. Acceptance La Jaira

```text
ORDINE La Jaira — 2026-08-15
├── RO-* — 1 SET Guisante Afila
├── RO-* — 0.5 SET Rábano Morado
└── RO-* — 0.5 SET Cilantro

RO-* + versions → PV-* approvata/valida → RPP-* → PP-* → una RVP-*
→ tre RPS-* con tre planning_key_v1 → una revision_request_key → ALL-* globali
→ seme pianificato GRAM → SEMINE reali versionate
→ RACCOLTE → ALL-* raccolta CONSUMATA → SODDISFATTA
```

Le righe possono usare protocolli, timeline, granularità, resa e seme differenti.
Sono rappresentabili coperture parziali, più SEMINE, raccolte parziali e nuova
RVP senza riscrivere storia. Nessun valore produttivo reale è congelato qui.

### Acceptance — Complete revision snapshot and planning-key reuse

```text
PRIMA REVISIONE — RVP-000001
RPS-000001 | RO Afila    | planning_key = A
RPS-000002 | RO Rábano   | planning_key = B
RPS-000003 | RO Cilantro | planning_key = C

STOCK_CHANGED Afila

REPLANNING — RVP-000002
RPS-000004 | RO Afila    | planning_key = A2
RPS-000005 | RO Rábano   | planning_key = B
RPS-000006 | RO Cilantro | planning_key = C
```

Tutte le RPS della seconda revisione sono nuove entità fisiche: nessuna RPS
della revisione precedente viene riutilizzata. A diventa A2 perché è cambiato
un input materiale; B e C possono ricorrere in revisioni differenti.
`UNIQUE (piano_revisione_id, planning_key)` consente tale ricorrenza e vieta il
doppione nella stessa revisione; `UNIQUE (piano_revisione_id, riga_ordine_id)`
vieta due righe piano per la stessa riga ordine nella medesima revisione. Non
esiste `UNIQUE (planning_key)` globale.

RVP-000002 è uno snapshot completo e si legge senza composizione con
RVP-000001, che resta immutabile. La sua `revision_request_key` coincide con la
`replanning_key_v1` calcolata secondo §2.1.

L'acceptance quantitativa usa UOM produttiva `SET`: Afila `1 SET`, Rábano `0.5
SET`, Cilantro `0.5 SET`. Una RPS Afila autorizzata per `1 SET` può collegare
SEMINA A per `0.5 SET` e SEMINA B per `0.5 SET`; la somma writer-enforced è `1
SET`. I grammi corrispondenti persistono esclusivamente nel modello risorsa seme
e nella SEMINA reale, mai nel link Piano→SEMINA.

## 15. Acceptance criteria

Test obbligatori: formati/non riuso ID; commissioning separato; validità DATE e
non sovrapposizione; lifecycle/immutabilità protocollo; doppia version e lock;
una sola revisione corrente dello stesso piano; idempotenza; lifecycle righe e
allocazioni; nessuna sovra-allocazione; più SEMINE entro autorizzata;
SODDISFATTA dimostrata da RACCOLTE; snapshot canonico riproducibile; rollback
totale; audit Planning separato; calendario ricostruibile; scenario La Jaira.

## 16. Esclusioni e blocker

Fuori V1: risorse diverse dal seme, scelta automatica lotto, catalogo universale,
capacity optimization, trigger business, advisory lock globale, import Google,
codice Alembic e valori produttivi reali.

Non rimangono Architecture Blocker per la futura migration, purché commissioning
Identity e backfill RO/PV siano gate separati, verificati e fail-closed.

## 17. Catalogo fisico normativo table-by-table

Questa sezione è la forma direttamente traducibile in DDL. `identity` significa
`GENERATED BY DEFAULT AS IDENTITY`. Ogni FK elencata usa `ON UPDATE RESTRICT ON
DELETE RESTRICT`. Ogni actor ha CHECK `btrim(actor) <> ''`; ogni public ID ha
UNIQUE e CHECK sul prefisso congelato. “Immutabile” vieta UPDATE ordinari.

### TABLE: `tpo.protocollo_versioni`

**RESPONSIBILITY:** versione produttiva e genealogia del protocollo.

**CURRENT COLUMNS PRESERVED:** `id`, `protocollo_id`, `numero_versione`,
`valida_dal`, `valida_al`, `versione_precedente_id`, `contenuto`, `motivazione`,
`evidenze`, `created_at`, `created_by`.

**NEW COLUMNS:** `public_id`, `stato_approvazione`, `idratazione_ore`,
`orario_semina_previsto`, `orario_raccolta_target`, `germinazione_giorni`,
`crescita_luce_giorni`, `ciclo_produttivo_nominale_giorni`,
`grammi_seme_per_set`, `resa_attesa`, `resa_unita_misura`,
`granularita_produttiva`, `harvest_min_lead_giorni`,
`harvest_max_lead_giorni`, `buffer_temporale_minuti`, `provenance`,
`approvata_at`, `approvata_by`, `ritirata_at`, `ritirata_by`.

**COLUMNS (RESULTING PHYSICAL TABLE):**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | PV-* |
| `protocollo_id` | `bigint` | NOT NULL | NO DEFAULT | protocollo |
| `numero_versione` | `integer` | NOT NULL | NO DEFAULT | genealogia |
| `valida_dal` | `date` | NOT NULL | NO DEFAULT | validità inclusiva |
| `valida_al` | `date` | NULL | NO DEFAULT | validità esclusiva |
| `versione_precedente_id` | `bigint` | NULL | NO DEFAULT | predecessore |
| `contenuto` | `text` | NOT NULL | NO DEFAULT | descrizione legacy |
| `motivazione` | `text` | NOT NULL | NO DEFAULT | motivazione |
| `evidenze` | `text` | NULL | NO DEFAULT | evidenze |
| `stato_approvazione` | `protocollo_versione_approval_state` | NOT NULL | NO DEFAULT | lifecycle |
| `idratazione_ore` | `numeric(20,6)` | NOT NULL | NO DEFAULT | durata idratazione |
| `orario_semina_previsto` | `time without time zone` | NOT NULL | NO DEFAULT | ora locale semina |
| `orario_raccolta_target` | `time without time zone` | NOT NULL | NO DEFAULT | ora locale raccolta |
| `germinazione_giorni` | `integer` | NOT NULL | NO DEFAULT | germinazione |
| `crescita_luce_giorni` | `integer` | NOT NULL | NO DEFAULT | crescita luce |
| `ciclo_produttivo_nominale_giorni` | `integer GENERATED ALWAYS AS (germinazione_giorni + crescita_luce_giorni) STORED` | NOT NULL | NO DEFAULT | ciclo nominale |
| `grammi_seme_per_set` | `numeric(20,6)` | NOT NULL | NO DEFAULT | seme per SET |
| `resa_attesa` | `numeric(20,6)` | NOT NULL | NO DEFAULT | resa per SET |
| `resa_unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | UOM resa |
| `granularita_produttiva` | `numeric(20,6)` | NOT NULL | NO DEFAULT | granularità |
| `harvest_min_lead_giorni` | `integer` | NOT NULL | NO DEFAULT | lead minimo |
| `harvest_max_lead_giorni` | `integer` | NOT NULL | NO DEFAULT | lead massimo |
| `buffer_temporale_minuti` | `integer` | NOT NULL | NO DEFAULT | buffer temporale |
| `provenance` | `text` | NOT NULL | NO DEFAULT | provenienza |
| `approvata_at` | `timestamptz` | NULL | NO DEFAULT | istante approvazione |
| `approvata_by` | `text` | NULL | NO DEFAULT | approvatore |
| `ritirata_at` | `timestamptz` | NULL | NO DEFAULT | istante ritiro |
| `ritirata_by` | `text` | NULL | NO DEFAULT | actor ritiro |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |

**PRIMARY KEY:** `CONSTRAINT protocollo_versioni_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** `CONSTRAINT protocollo_versioni_protocollo_id_fkey FOREIGN KEY
(protocollo_id) REFERENCES tpo.protocolli(id) ON UPDATE RESTRICT ON DELETE
RESTRICT`; `CONSTRAINT protocollo_versioni_versione_precedente_id_fkey FOREIGN
KEY (versione_precedente_id) REFERENCES tpo.protocollo_versioni(id) ON UPDATE
RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_protocollo_versioni_public_id UNIQUE (public_id)`; `CONSTRAINT
uq_protocollo_versioni_protocollo_numero UNIQUE
(protocollo_id,numero_versione)`; `CONSTRAINT
uq_protocollo_versioni_precedente UNIQUE (versione_precedente_id)`. **CHECK
CONSTRAINTS:** `CONSTRAINT ck_protocollo_versioni_public_id CHECK (public_id ~
'^PV-[0-9]{6,}$')`; `CONSTRAINT ck_protocollo_versioni_numero CHECK
(numero_versione > 0)`; `CONSTRAINT ck_protocollo_versioni_durate CHECK
(idratazione_ore >= 0 AND germinazione_giorni >= 0 AND crescita_luce_giorni >=
0 AND buffer_temporale_minuti >= 0)`; `CONSTRAINT
ck_protocollo_versioni_quantita CHECK (grammi_seme_per_set > 0 AND resa_attesa
> 0 AND granularita_produttiva > 0)`; `CONSTRAINT
ck_protocollo_versioni_harvest_lead CHECK (harvest_min_lead_giorni >= 1 AND
harvest_max_lead_giorni >= harvest_min_lead_giorni)`; `CONSTRAINT
ck_protocollo_versioni_validita CHECK (valida_al IS NULL OR valida_al >
valida_dal)`; `CONSTRAINT ck_protocollo_versioni_testi CHECK (btrim(contenuto)
<> '' AND btrim(motivazione) <> '' AND btrim(provenance) <> '' AND
btrim(created_by) <> '')`; `CONSTRAINT ck_protocollo_versioni_lifecycle CHECK
((stato_approvazione='BOZZA' AND approvata_at IS NULL AND approvata_by IS NULL
AND ritirata_at IS NULL AND ritirata_by IS NULL) OR
(stato_approvazione='APPROVATA' AND approvata_at IS NOT NULL AND approvata_by IS
NOT NULL AND ritirata_at IS NULL AND ritirata_by IS NULL) OR
(stato_approvazione='RITIRATA' AND ritirata_at IS NOT NULL AND ritirata_by IS
NOT NULL AND ((approvata_at IS NULL AND approvata_by IS NULL) OR
(approvata_at IS NOT NULL AND approvata_by IS NOT NULL))))`. **OTHER
STRUCTURAL CONSTRAINTS:** `CONSTRAINT ex_protocollo_versioni_approvate_validita
EXCLUDE USING gist (protocollo_id WITH =, daterange(valida_dal,valida_al,'[)')
WITH &&) WHERE (stato_approvazione='APPROVATA')`. **INDEXES:** `CREATE INDEX
ix_protocollo_versioni_protocollo_stato_validita ON tpo.protocollo_versioni
(protocollo_id ASC,stato_approvazione ASC,valida_dal ASC,valida_al ASC)`;
`CREATE INDEX ix_protocollo_versioni_precedente ON tpo.protocollo_versioni
(versione_precedente_id ASC)`. **MUTABILITY:** §4.3, append-only payload.
**OPTIMISTIC CONCURRENCY:** non applicabile al payload immutabile; transizioni
auditabili sotto lock. **DELETE POLICY:** RESTRICT dopo approvazione. **WRITER AUTHORITY:**
knowledge writer.

### TABLE: `tpo.production_planning_policy_versions`

**RESPONSIBILITY:** policy-set Planning immutabile. **COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `policy_set_code` | `text` | NOT NULL | NO DEFAULT | natural identity |
| `numero_versione` | `integer` | NOT NULL | NO DEFAULT | versione |
| `harvest_target_strategy` | `text` | NOT NULL | NO DEFAULT | strategia |
| `buffer_quantitativo_tipo` | `quantitative_buffer_policy_type` | NOT NULL | NO DEFAULT | tipo buffer |
| `buffer_quantitativo_valore` | `numeric(20,6)` | NULL | NO DEFAULT | valore buffer |
| `priority_policy_code` | `text` | NOT NULL | NO DEFAULT | priorità |
| `planning_algorithm_version` | `text` | NOT NULL | NO DEFAULT | algoritmo |
| `valida_dal` | `date` | NOT NULL | NO DEFAULT | validità inclusiva |
| `valida_al` | `date` | NULL | NO DEFAULT | validità esclusiva |
| `provenance` | `text` | NOT NULL | NO DEFAULT | provenienza |
| `evidenze` | `text` | NULL | NO DEFAULT | evidenze |
| `approved_at` | `timestamptz` | NOT NULL | NO DEFAULT | approvazione |
| `approved_by` | `text` | NOT NULL | NO DEFAULT | approvatore |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |

**PRIMARY KEY:** `CONSTRAINT production_planning_policy_versions_pkey PRIMARY
KEY (id)`. **FOREIGN KEYS:** nessuna. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_production_planning_policy_versions_set_numero UNIQUE
(policy_set_code,numero_versione)`. **CHECK CONSTRAINTS:** `CONSTRAINT
ck_production_planning_policy_versions_numero CHECK (numero_versione > 0)`;
`CONSTRAINT ck_production_planning_policy_versions_strategy CHECK
(harvest_target_strategy='EARLIEST_APPROVED_WINDOW')`; `CONSTRAINT
ck_production_planning_policy_versions_buffer CHECK
((buffer_quantitativo_tipo='NONE' AND buffer_quantitativo_valore IS NULL) OR
(buffer_quantitativo_tipo='PERCENTAGE' AND buffer_quantitativo_valore BETWEEN 0
AND 100) OR (buffer_quantitativo_tipo='ABSOLUTE_SET' AND
buffer_quantitativo_valore >= 0))`; `CONSTRAINT
ck_production_planning_policy_versions_validita CHECK (valida_al IS NULL OR
valida_al > valida_dal)`; `CONSTRAINT
ck_production_planning_policy_versions_testi CHECK (btrim(policy_set_code) <> ''
AND btrim(priority_policy_code) <> '' AND btrim(planning_algorithm_version) <> ''
AND btrim(provenance) <> '' AND btrim(approved_by) <> '' AND btrim(created_by) <>
'')`. **OTHER STRUCTURAL CONSTRAINTS:** `CONSTRAINT
ex_production_planning_policy_versions_validita EXCLUDE USING gist
(policy_set_code WITH =, daterange(valida_dal,valida_al,'[)') WITH &&)`.
**INDEXES:** `CREATE INDEX ix_production_planning_policy_versions_set_validita
ON tpo.production_planning_policy_versions (policy_set_code ASC,valida_dal
ASC,valida_al ASC)`; `CREATE INDEX
ix_production_planning_policy_versions_set_numero ON
tpo.production_planning_policy_versions (policy_set_code ASC,numero_versione
ASC)`.
**MUTABILITY:** append-only. **OPTIMISTIC CONCURRENCY:** non applicabile; nessuna
colonna version. **DELETE POLICY:** RESTRICT se referenziata. **WRITER
AUTHORITY:** policy commissioning writer.

### TABLE: `tpo.production_planning_runs`

**RESPONSIBILITY:** esecuzione persistente del Planning. **COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | RPP-* |
| `policy_version_id` | `bigint` | NOT NULL | NO DEFAULT | policy |
| `business_at` | `timestamptz` | NOT NULL | NO DEFAULT | business instant |
| `state` | `production_planning_run_state` | NOT NULL | DEFAULT 'OPEN' | lifecycle |
| `started_at` | `timestamptz` | NOT NULL | NO DEFAULT | apertura |
| `completed_at` | `timestamptz` | NULL | NO DEFAULT | conclusione |
| `ordini_letti` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_ordine_valutate` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_coperte_integralmente` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_coperte_parzialmente` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_piano_generate` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `allocazioni_generate` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_tardive` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `righe_non_producibili` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `elementi_saltati` | `bigint` | NOT NULL | DEFAULT 0 | contatore |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS |

**PRIMARY KEY:** `CONSTRAINT production_planning_runs_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** `CONSTRAINT production_planning_runs_policy_version_id_fkey
FOREIGN KEY (policy_version_id) REFERENCES
tpo.production_planning_policy_versions(id) ON UPDATE RESTRICT ON DELETE
RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_production_planning_runs_public_id UNIQUE (public_id)`. **CHECK CONSTRAINTS:**
`CONSTRAINT ck_production_planning_runs_public_id CHECK (public_id ~
'^RPP-[0-9]{6,}$')`; `CONSTRAINT
ck_production_planning_runs_counters CHECK (ordini_letti >= 0 AND
righe_ordine_valutate >= 0 AND righe_coperte_integralmente >= 0 AND
righe_coperte_parzialmente >= 0 AND righe_piano_generate >= 0 AND
allocazioni_generate >= 0 AND righe_tardive >= 0 AND righe_non_producibili >= 0
AND elementi_saltati >= 0)`; `CONSTRAINT ck_production_planning_runs_version
CHECK (version >= 0)`; `CONSTRAINT ck_production_planning_runs_lifecycle CHECK
((state='OPEN' AND completed_at IS NULL) OR (state<>'OPEN' AND completed_at IS
NOT NULL AND completed_at >= started_at))`; `CONSTRAINT
ck_production_planning_runs_created_by CHECK (btrim(created_by) <> '')`.
**OTHER STRUCTURAL CONSTRAINTS:** lifecycle
OPEN→COMMITTED|FAILED|RECONCILIATION_REQUIRED. **INDEXES:** `CREATE INDEX
ix_production_planning_runs_state_started ON tpo.production_planning_runs (state
ASC,started_at ASC)`; `CREATE INDEX ix_production_planning_runs_business_at ON
tpo.production_planning_runs (business_at ASC)`; `CREATE INDEX
ix_production_planning_runs_policy_version ON tpo.production_planning_runs
(policy_version_id ASC)`.
**MUTABILITY:** state, completion, counters e version. **OPTIMISTIC CONCURRENCY:**
CAS su version. **DELETE POLICY:** nessun hard delete dopo apertura. **WRITER
AUTHORITY:** Planning Run writer; failure-finalizer conclude solo OPEN alla
expected version e non crea piano.

### TABLE: `tpo.production_planning_run_messaggi`

**RESPONSIBILITY:** sequenza persistente dei messaggi normativi di un Planning
RUN.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint GENERATED BY DEFAULT AS IDENTITY` | NOT NULL | identity | chiave fisica |
| `planning_run_id` | `bigint` | NOT NULL | NONE | Planning RUN proprietaria |
| `posizione` | `integer` | NOT NULL | NONE | ordine denso nel RUN |
| `tipo` | `run_message_type` | NOT NULL | NONE | severità normativa |
| `failure_category` | `planning_failure_category` | NULL | NONE | categoria solo per ERROR |
| `codice` | `text` | NOT NULL | NONE | codice stabile |
| `messaggio` | `text` | NOT NULL | NONE | testo privo di dati sensibili |
| `created_at` | `timestamptz` | NOT NULL | NONE | istante applicativo |

**PRIMARY KEY:** `pk_production_planning_run_messaggi` (`id`).
**FOREIGN KEYS:** `fk_production_planning_run_messaggi_run`:
`planning_run_id` → `tpo.production_planning_runs(id)` ON UPDATE RESTRICT ON
DELETE RESTRICT. **UNIQUE CONSTRAINTS:**
`uq_production_planning_run_messaggi_run_posizione`
(`planning_run_id`,`posizione`). **CHECK CONSTRAINTS:**
`ck_production_planning_run_messaggi_posizione` (`posizione > 0`),
`ck_production_planning_run_messaggi_codice` (`btrim(codice) <> ''`),
`ck_production_planning_run_messaggi_testo` (`btrim(messaggio) <> ''`),
`ck_production_planning_run_messaggi_category` (ERROR richiede categoria e ogni
altro tipo la vieta). **OTHER STRUCTURAL CONSTRAINTS:** nessuno. **INDEXES:**
`ix_production_planning_run_messaggi_run_tipo_posizione`
(`planning_run_id`,`tipo`,`posizione`). **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile; nessuna colonna `version`.
**DELETE POLICY:** RESTRICT dopo apertura del RUN. **WRITER AUTHORITY:** Planning
Run writer e failure-finalizer.

### TABLE: `tpo.production_planning_run_log`

**RESPONSIBILITY:** timeline persistente e ordinata degli eventi di un Planning
RUN.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint GENERATED BY DEFAULT AS IDENTITY` | NOT NULL | identity | chiave fisica |
| `planning_run_id` | `bigint` | NOT NULL | NONE | Planning RUN proprietaria |
| `posizione` | `bigint` | NOT NULL | NONE | ordine denso nel RUN |
| `livello` | `run_log_level` | NOT NULL | NONE | livello evento |
| `codice_evento` | `text` | NOT NULL | NONE | codice stabile |
| `messaggio` | `text` | NOT NULL | NONE | testo privo di dati sensibili |
| `occurred_at` | `timestamptz` | NOT NULL | NONE | istante evento applicativo |

**PRIMARY KEY:** `pk_production_planning_run_log` (`id`). **FOREIGN KEYS:**
`fk_production_planning_run_log_run`: `planning_run_id` →
`tpo.production_planning_runs(id)` ON UPDATE RESTRICT ON DELETE RESTRICT.
**UNIQUE CONSTRAINTS:** `uq_production_planning_run_log_run_posizione`
(`planning_run_id`,`posizione`). **CHECK CONSTRAINTS:**
`ck_production_planning_run_log_posizione` (`posizione > 0`),
`ck_production_planning_run_log_codice` (`btrim(codice_evento) <> ''`),
`ck_production_planning_run_log_testo` (`btrim(messaggio) <> ''`). **OTHER
STRUCTURAL CONSTRAINTS:** nessuno. **INDEXES:**
`ix_production_planning_run_log_run_occurred_posizione`
(`planning_run_id`,`occurred_at`,`posizione`). **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile; nessuna colonna `version`.
**DELETE POLICY:** RESTRICT dopo apertura del RUN. **WRITER AUTHORITY:** Planning
Run writer e failure-finalizer.

### TABLE: `tpo.piani_produzione`

**RESPONSIBILITY:** radice stabile del piano e puntatore alla revisione corrente.
**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | PP-* |
| `current_revision_id` | `bigint` | NULL | NO DEFAULT | revisione corrente |
| `stato_complessivo` | `text` | NOT NULL | NO DEFAULT | stato aperto |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor creazione |
| `updated_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit modifica |
| `updated_by` | `text` | NOT NULL | NO DEFAULT | actor modifica |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS |

**PRIMARY KEY:** `CONSTRAINT piani_produzione_pkey PRIMARY KEY (id)`. **FOREIGN
KEYS:** dopo la creazione di entrambe le tabelle: `CONSTRAINT
piani_produzione_current_revision_id_fkey FOREIGN KEY
(id,current_revision_id) REFERENCES tpo.piano_produzione_revisioni
(piano_produzione_id,id) ON UPDATE RESTRICT ON DELETE RESTRICT DEFERRABLE
INITIALLY DEFERRED`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_piani_produzione_public_id UNIQUE (public_id)`; `CREATE UNIQUE INDEX
uq_piani_produzione_current_revision ON tpo.piani_produzione
(current_revision_id ASC) WHERE current_revision_id IS NOT NULL`. **CHECK
CONSTRAINTS:** `CONSTRAINT ck_piani_produzione_public_id CHECK (public_id ~
'^PP-[0-9]{6,}$')`; `CONSTRAINT ck_piani_produzione_stato CHECK
(btrim(stato_complessivo) <> '')`; `CONSTRAINT ck_piani_produzione_actors CHECK
(btrim(created_by) <> '' AND btrim(updated_by) <> '')`; `CONSTRAINT
ck_piani_produzione_version CHECK (version >= 0)`; `CONSTRAINT
ck_piani_produzione_updated CHECK (updated_at >= created_at)`. **OTHER
STRUCTURAL CONSTRAINTS:** ordine DDL: creare piani senza FK circolare, creare
revisioni con `uq_piano_produzione_revisioni_piano_id`, poi aggiungere la FK
DEFERRABLE. **INDEXES:** `CREATE INDEX ix_piani_produzione_stato ON
tpo.piani_produzione (stato_complessivo ASC)`. **MUTABILITY:** soltanto current
pointer, stato e audit updated. **OPTIMISTIC CONCURRENCY:** CAS su version.
**DELETE POLICY:** RESTRICT dopo la prima revisione. **WRITER AUTHORITY:**
Planning Commit Repository.

### TABLE: `tpo.piano_produzione_revisioni`

**COLUMNS:** `id bigint NOT NULL identity`; `public_id text NOT NULL`;
`piano_produzione_id bigint NOT NULL`; `planning_run_id bigint NOT NULL`;
`numero_revisione integer NOT NULL`; `revisione_precedente_id bigint NULL`;
`policy_version_id bigint NOT NULL`; `business_at timestamptz NOT NULL`;
`replanning_reason_code replanning_reason_code NULL`; `revision_request_key text NOT
NULL`; `replanning_snapshot_id bigint NULL`; `sostituita_at timestamptz NULL`;
`sostituita_by text NULL`; `created_at timestamptz NOT NULL`; `created_by text
NOT NULL`; `version bigint NOT NULL DEFAULT 0`.
**PRIMARY KEY:** `CONSTRAINT piano_produzione_revisioni_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:**

- `CONSTRAINT piano_produzione_revisioni_piano_produzione_id_fkey FOREIGN KEY
  (piano_produzione_id) REFERENCES tpo.piani_produzione(id) ON UPDATE RESTRICT
  ON DELETE RESTRICT`;
- `CONSTRAINT piano_produzione_revisioni_planning_run_id_fkey FOREIGN KEY
  (planning_run_id) REFERENCES tpo.production_planning_runs(id) ON UPDATE
  RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT piano_produzione_revisioni_policy_version_id_fkey FOREIGN KEY
  (policy_version_id) REFERENCES tpo.production_planning_policy_versions(id) ON
  UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT piano_produzione_revisioni_revisione_precedente_id_fkey FOREIGN
  KEY (revisione_precedente_id) REFERENCES
  tpo.piano_produzione_revisioni(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
- `CONSTRAINT piano_produzione_revisioni_replanning_snapshot_id_fkey FOREIGN
  KEY (replanning_snapshot_id) REFERENCES tpo.replanning_snapshots(id) ON
  UPDATE RESTRICT ON DELETE RESTRICT`.

**UNIQUE CONSTRAINTS:**
`CONSTRAINT uq_piano_produzione_revisioni_public_id UNIQUE (public_id)`;
`CONSTRAINT uq_piano_produzione_revisioni_piano_numero UNIQUE
(piano_produzione_id,numero_revisione)`;
`CONSTRAINT uq_piano_produzione_revisioni_precedente UNIQUE
(revisione_precedente_id)`;
`CONSTRAINT uq_piano_produzione_revisioni_request_key UNIQUE
(revision_request_key)`; `CONSTRAINT uq_piano_produzione_revisioni_piano_id
UNIQUE (piano_produzione_id,id)`.

**UNIQUE PARTIAL INDEX:** `CREATE UNIQUE INDEX
uq_piano_produzione_revisioni_replanning_snapshot ON
tpo.piano_produzione_revisioni (replanning_snapshot_id ASC) WHERE
replanning_snapshot_id IS NOT NULL`.
**CHECK:** `ck_piano_produzione_revisioni_public_id` impone il formato RVP;
`ck_piano_produzione_revisioni_numero` impone numero>0;
`ck_piano_produzione_revisioni_version` impone version≥0;
`CONSTRAINT ck_piano_produzione_revisioni_kind CHECK
((numero_revisione = 1 AND revisione_precedente_id IS NULL AND
replanning_reason_code IS NULL AND replanning_snapshot_id IS NULL) OR
(numero_revisione > 1 AND revisione_precedente_id IS NOT NULL AND
replanning_reason_code IS NOT NULL AND replanning_snapshot_id IS NOT NULL))`;
`ck_piano_produzione_revisioni_request_key` impone
`revision_request_key ~ '^[0-9a-f]{64}$'`;
`ck_piano_produzione_revisioni_sostituzione` impone insieme i campi sostituita.
**OTHER STRUCTURAL CONSTRAINTS:** il writer verifica sotto lock che la revisione
precedente appartenga allo stesso piano e abbia numero immediatamente
precedente; `tpo.replanning_snapshots` non contiene FK inversa. **INDEXES:**
`ix_piano_produzione_revisioni_run` sulla tabella
`tpo.piano_produzione_revisioni` (`planning_run_id ASC`);
`ix_piano_produzione_revisioni_policy` (`policy_version_id ASC`);
`ix_piano_produzione_revisioni_piano_numero_desc`
(`piano_produzione_id ASC`,`numero_revisione DESC`);
`ix_piano_produzione_revisioni_precedente` (`revisione_precedente_id ASC`);
`ix_piano_produzione_revisioni_request_key` (`revision_request_key ASC`).
**MUTABILITY:** payload append-only;
solo sostituzione metadata con CAS. **DELETE:** RESTRICT. **WRITER:** Planning.

### TABLE: `tpo.righe_piano_semina`

**RESPONSIBILITY:** riga produttiva storica appartenente a una revisione.
**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | PK |
| `public_id` | `text` | NOT NULL | NO DEFAULT | RPS-* |
| `piano_revisione_id` | `bigint` | NOT NULL | NO DEFAULT | revisione |
| `riga_ordine_id` | `bigint` | NOT NULL | NO DEFAULT | domanda |
| `varieta_id` | `bigint` | NOT NULL | NO DEFAULT | varietà |
| `cultivar_id` | `bigint` | NOT NULL | NO DEFAULT | cultivar |
| `cultivar_uso_id` | `bigint` | NOT NULL | NO DEFAULT | uso |
| `protocollo_versione_id` | `bigint` | NOT NULL | NO DEFAULT | protocollo |
| `ordine_version_attesa` | `bigint` | NOT NULL | NO DEFAULT | expected version |
| `riga_ordine_version_attesa` | `bigint` | NOT NULL | NO DEFAULT | expected version |
| `varieta_public_id_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot |
| `cultivar_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot |
| `uso_produttivo_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot |
| `domanda_originaria` | `numeric(20,6)` | NOT NULL | NO DEFAULT | domanda |
| `quantita_consegnata_snapshot` | `numeric(20,6)` | NOT NULL | NO DEFAULT | consegnata |
| `domanda_residua_commerciale` | `numeric(20,6)` | NOT NULL | NO DEFAULT | residuo |
| `copertura_stock` | `numeric(20,6)` | NOT NULL | NO DEFAULT | stock |
| `copertura_produzione_in_corso` | `numeric(20,6)` | NOT NULL | NO DEFAULT | produzione |
| `copertura_raccolta_allocata` | `numeric(20,6)` | NOT NULL | NO DEFAULT | raccolta |
| `deficit_produttivo` | `numeric(20,6)` | NOT NULL | NO DEFAULT | deficit |
| `buffer_quantitativo_tipo` | `quantitative_buffer_policy_type` | NOT NULL | NO DEFAULT | tipo buffer |
| `buffer_quantitativo_valore` | `numeric(20,6)` | NULL | NO DEFAULT | valore buffer |
| `buffer_quantitativo_calcolato` | `numeric(20,6)` | NOT NULL | NO DEFAULT | buffer calcolato |
| `quantita_pre_granularita` | `numeric(20,6)` | NOT NULL | NO DEFAULT | pre-rounding |
| `granularita_produttiva` | `numeric(20,6)` | NOT NULL | NO DEFAULT | granularità |
| `quantita_produttiva_autorizzata` | `numeric(20,6)` | NOT NULL | NO DEFAULT | autorizzata |
| `quantita_avviata` | `numeric(20,6)` | NOT NULL | DEFAULT 0 | avviata |
| `quantita_residua_da_avviare` | `numeric(20,6)` | NOT NULL | NO DEFAULT | residua |
| `resa_attesa` | `numeric(20,6)` | NOT NULL | NO DEFAULT | resa |
| `resa_unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | UOM resa |
| `grammi_seme_richiesti` | `numeric(20,6)` | NOT NULL | NO DEFAULT | seme |
| `unita_domanda` | `unit_of_measure` | NOT NULL | NO DEFAULT | UOM domanda |
| `data_consegna` | `date` | NOT NULL | NO DEFAULT | consegna |
| `harvest_window_start` | `date` | NOT NULL | NO DEFAULT | finestra inizio |
| `harvest_window_end` | `date` | NOT NULL | NO DEFAULT | finestra fine |
| `harvest_target_at` | `timestamptz` | NOT NULL | NO DEFAULT | target |
| `sowing_at` | `timestamptz` | NOT NULL | NO DEFAULT | semina |
| `light_at` | `timestamptz` | NOT NULL | NO DEFAULT | luce |
| `hydration_at` | `timestamptz` | NOT NULL | NO DEFAULT | idratazione |
| `timezone` | `text` | NOT NULL | NO DEFAULT | Atlantic/Canary |
| `orario_semina_snapshot` | `time without time zone` | NOT NULL | NO DEFAULT | ora semina |
| `orario_raccolta_snapshot` | `time without time zone` | NOT NULL | NO DEFAULT | ora raccolta |
| `buffer_temporale_minuti` | `integer` | NOT NULL | NO DEFAULT | buffer |
| `stato` | `riga_piano_semina_state` | NOT NULL | NO DEFAULT | lifecycle |
| `planning_key` | `text` | NOT NULL | NO DEFAULT | equivalenza logica |
| `provenance` | `text` | NOT NULL | NO DEFAULT | provenienza |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |
| `updated_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `updated_by` | `text` | NOT NULL | NO DEFAULT | actor |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS |

**PRIMARY KEY:** `CONSTRAINT righe_piano_semina_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** `CONSTRAINT righe_piano_semina_piano_revisione_id_fkey
FOREIGN KEY (piano_revisione_id) REFERENCES
tpo.piano_produzione_revisioni(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
`CONSTRAINT righe_piano_semina_riga_ordine_id_fkey FOREIGN KEY (riga_ordine_id)
REFERENCES tpo.righe_ordine(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
`CONSTRAINT righe_piano_semina_varieta_id_fkey FOREIGN KEY (varieta_id)
REFERENCES tpo.varieta(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
righe_piano_semina_cultivar_id_fkey FOREIGN KEY (cultivar_id) REFERENCES
tpo.cultivar(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
righe_piano_semina_cultivar_uso_id_fkey FOREIGN KEY (cultivar_uso_id) REFERENCES
tpo.cultivar_usi(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
righe_piano_semina_protocollo_versione_id_fkey FOREIGN KEY
(protocollo_versione_id) REFERENCES tpo.protocollo_versioni(id) ON UPDATE
RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_righe_piano_semina_public_id UNIQUE (public_id)`; `CONSTRAINT
uq_righe_piano_semina_revisione_riga UNIQUE
(piano_revisione_id,riga_ordine_id)`; `CONSTRAINT
uq_righe_piano_semina_revisione_planning_key UNIQUE
(piano_revisione_id,planning_key)`; nessuna UNIQUE globale su planning_key.
**CHECK CONSTRAINTS:** `CONSTRAINT ck_righe_piano_semina_public_id CHECK
(public_id ~ '^RPS-[0-9]{6,}$')`; `CONSTRAINT
ck_righe_piano_semina_planning_key CHECK (planning_key ~ '^[0-9a-f]{64}$')`;
`CONSTRAINT ck_righe_piano_semina_versions CHECK (ordine_version_attesa >= 0
AND riga_ordine_version_attesa >= 0 AND version >= 0)`; `CONSTRAINT
ck_righe_piano_semina_quantities CHECK (domanda_originaria > 0 AND
quantita_consegnata_snapshot >= 0 AND domanda_residua_commerciale >= 0 AND
copertura_stock >= 0 AND copertura_produzione_in_corso >= 0 AND
copertura_raccolta_allocata >= 0 AND deficit_produttivo >= 0 AND
buffer_quantitativo_calcolato >= 0 AND quantita_pre_granularita >= 0 AND
granularita_produttiva > 0 AND quantita_produttiva_autorizzata >= 0 AND
quantita_avviata >= 0 AND quantita_residua_da_avviare >= 0 AND resa_attesa > 0
AND grammi_seme_richiesti > 0)`; `CONSTRAINT
ck_righe_piano_semina_commercial_residual CHECK
(quantita_consegnata_snapshot <= domanda_originaria AND
domanda_residua_commerciale = domanda_originaria -
quantita_consegnata_snapshot)`; `CONSTRAINT ck_righe_piano_semina_coverages CHECK
(copertura_stock + copertura_produzione_in_corso +
copertura_raccolta_allocata <= domanda_residua_commerciale AND
deficit_produttivo = domanda_residua_commerciale - copertura_stock -
copertura_produzione_in_corso - copertura_raccolta_allocata)`; `CONSTRAINT
ck_righe_piano_semina_buffer CHECK ((buffer_quantitativo_tipo='NONE' AND
buffer_quantitativo_valore IS NULL AND buffer_quantitativo_calcolato=0) OR
(buffer_quantitativo_tipo<>'NONE' AND buffer_quantitativo_valore IS NOT NULL AND
buffer_quantitativo_valore>=0))`; `CONSTRAINT
ck_righe_piano_semina_started_quantity CHECK (quantita_avviata <=
quantita_produttiva_autorizzata AND quantita_residua_da_avviare =
quantita_produttiva_autorizzata - quantita_avviata)`; `CONSTRAINT
ck_righe_piano_semina_window CHECK (harvest_window_end >=
harvest_window_start)`; `CONSTRAINT ck_righe_piano_semina_timeline CHECK
(hydration_at <= sowing_at AND sowing_at <= light_at AND light_at <=
harvest_target_at)`; `CONSTRAINT ck_righe_piano_semina_timezone CHECK
(timezone='Atlantic/Canary')`; `CONSTRAINT ck_righe_piano_semina_texts CHECK
(btrim(varieta_public_id_snapshot)<>'' AND btrim(cultivar_snapshot)<>'' AND
btrim(uso_produttivo_snapshot)<>'' AND btrim(provenance)<>'' AND
btrim(created_by)<>'' AND btrim(updated_by)<>'')`. **OTHER STRUCTURAL
CONSTRAINTS:** multiplo della granularità e coerenza identità sono
writer-enforced sotto lock. **INDEXES:** `CREATE INDEX
ix_righe_piano_semina_revisione ON tpo.righe_piano_semina
(piano_revisione_id ASC)`; `CREATE INDEX ix_righe_piano_semina_riga_ordine ON
tpo.righe_piano_semina (riga_ordine_id ASC)`; `CREATE INDEX
ix_righe_piano_semina_varieta ON tpo.righe_piano_semina (varieta_id ASC)`;
`CREATE INDEX ix_righe_piano_semina_cultivar ON tpo.righe_piano_semina
(cultivar_id ASC)`; `CREATE INDEX ix_righe_piano_semina_cultivar_uso ON
tpo.righe_piano_semina (cultivar_uso_id ASC)`; `CREATE INDEX
ix_righe_piano_semina_protocollo ON tpo.righe_piano_semina
(protocollo_versione_id ASC)`; `CREATE INDEX ix_righe_piano_semina_stato_sowing
ON tpo.righe_piano_semina (stato ASC,sowing_at ASC)`; `CREATE INDEX
ix_righe_piano_semina_stato_harvest ON tpo.righe_piano_semina
(stato ASC,harvest_target_at ASC)`; `CREATE INDEX
ix_righe_piano_semina_data_consegna ON tpo.righe_piano_semina
(data_consegna ASC)`. **MUTABILITY:** solo
lifecycle/avanzamento e audit updated. **OPTIMISTIC CONCURRENCY:** CAS su
version. **DELETE POLICY:** RESTRICT. **WRITER AUTHORITY:** Planning; comando
operatore soltanto per avanzamento congelato.

### TABLE: `tpo.risorse_seme_pianificate`

**RESPONSIBILITY:** risorsa seme pianificata V1, senza SEMENTE commerciale né
LOTTO_SEME. **COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | PK |
| `riga_piano_semina_id` | `bigint` | NOT NULL | NO DEFAULT | riga piano |
| `cultivar_uso_id` | `bigint` | NOT NULL | NO DEFAULT | uso produttivo |
| `protocollo_versione_id` | `bigint` | NOT NULL | NO DEFAULT | protocollo |
| `grammi_richiesti` | `numeric(20,6)` | NOT NULL | NO DEFAULT | quantità grammi |
| `grammi_seme_per_set` | `numeric(20,6)` | NOT NULL | NO DEFAULT | snapshot per SET |
| `unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | GRAM |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |

**PRIMARY KEY:** `CONSTRAINT risorse_seme_pianificate_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** `CONSTRAINT
risorse_seme_pianificate_riga_piano_semina_id_fkey FOREIGN KEY
(riga_piano_semina_id) REFERENCES tpo.righe_piano_semina(id) ON UPDATE RESTRICT
ON DELETE RESTRICT`; `CONSTRAINT risorse_seme_pianificate_cultivar_uso_id_fkey
FOREIGN KEY (cultivar_uso_id) REFERENCES tpo.cultivar_usi(id) ON UPDATE RESTRICT
ON DELETE RESTRICT`; `CONSTRAINT
risorse_seme_pianificate_protocollo_versione_id_fkey FOREIGN KEY
(protocollo_versione_id) REFERENCES tpo.protocollo_versioni(id) ON UPDATE
RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_risorse_seme_pianificate_riga UNIQUE (riga_piano_semina_id)`. **CHECK
CONSTRAINTS:** `CONSTRAINT ck_risorse_seme_pianificate_grammi CHECK
(grammi_richiesti > 0 AND grammi_seme_per_set > 0)`; `CONSTRAINT
ck_risorse_seme_pianificate_uom CHECK (unita_misura='GRAM')`; `CONSTRAINT
ck_risorse_seme_pianificate_created_by CHECK (btrim(created_by) <> '')`.
**OTHER STRUCTURAL CONSTRAINTS:** nessuno. **INDEXES:** `CREATE INDEX
ix_risorse_seme_pianificate_cultivar_uso ON tpo.risorse_seme_pianificate
(cultivar_uso_id ASC)`; `CREATE INDEX ix_risorse_seme_pianificate_protocollo ON
tpo.risorse_seme_pianificate (protocollo_versione_id ASC)`. **MUTABILITY:**
append-only. **OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:**
RESTRICT dopo commit della revisione. **WRITER AUTHORITY:** Planning writer.

### TABLE: `tpo.allocazioni`

**RESPONSIBILITY:** registro globale autorevole di ogni allocazione tipizzata.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint GENERATED BY DEFAULT AS IDENTITY` | NOT NULL | identity | chiave fisica |
| `public_id` | `text` | NOT NULL | NONE | identificativo `ALL-*` |
| `allocation_type` | `allocation_type` | NOT NULL | NONE | discriminante child |
| `riga_piano_semina_id` | `bigint` | NOT NULL | NONE | destinazione pianificata |
| `quantity` | `numeric(20,6)` | NOT NULL | NONE | quantità allocata |
| `unita_misura` | `unit_of_measure` | NOT NULL | NONE | unità quantità |
| `state` | `planning_allocation_state` | NOT NULL | NONE | lifecycle CAS |
| `created_at` | `timestamptz` | NOT NULL | NONE | istante applicativo |
| `created_by` | `text` | NOT NULL | NONE | actor applicativo |
| `updated_at` | `timestamptz` | NOT NULL | NONE | istante ultima transizione |
| `updated_by` | `text` | NOT NULL | NONE | actor ultima transizione |
| `version` | `bigint` | NOT NULL | `0` | token CAS lifecycle |

**PRIMARY KEY:** `allocazioni_pkey` (`id`). **FOREIGN KEYS:** `CONSTRAINT
allocazioni_riga_piano_semina_id_fkey FOREIGN KEY (riga_piano_semina_id)
REFERENCES tpo.righe_piano_semina(id) ON UPDATE RESTRICT ON DELETE RESTRICT`.
**UNIQUE CONSTRAINTS:** `uq_allocazioni_public_id` (`public_id`). **CHECK
CONSTRAINTS:** `ck_allocazioni_public_id` (`public_id ~ '^ALL-[0-9]{6,}$'`),
`ck_allocazioni_quantity` (`quantity > 0`), `ck_allocazioni_version` (`version
>= 0`), `ck_allocazioni_created_by` (`btrim(created_by) <> ''`),
`ck_allocazioni_updated_by` (`btrim(updated_by) <> ''`). **OTHER STRUCTURAL
CONSTRAINTS:** constraint trigger `ct_allocazioni_exactly_one_child`, DEFERRABLE
INITIALLY DEFERRED, verifica a fine transazione che esista esattamente una child
e che la sua tabella coincida con `allocation_type`; non applica logica
quantitativa, lifecycle, eligibility o policy. **INDEXES:**
`ix_allocazioni_riga_piano_state` (`riga_piano_semina_id`,`state`),
`ix_allocazioni_type_state` (`allocation_type`,`state`). **MUTABILITY:**
`allocation_type`, `riga_piano_semina_id`, `quantity`, `unita_misura`,
`created_at` e `created_by` sono immutabili; soltanto `state`, `updated_at`,
`updated_by` e `version` mutano con il lifecycle. `state` non ha DEFAULT e il
writer fornisce esplicitamente `ATTIVA` all'INSERT. `updated_at` e `updated_by`
descrivono l'ultima transizione; gli audit event autorevoli ne conservano la
storia completa. Gli stati terminali non sono riattivabili. **OPTIMISTIC
CONCURRENCY:** UPDATE con `WHERE id=:id AND version=:expected_version`, modifica
atomica di `state`, `updated_at`, `updated_by` e incremento di `version`.
**DELETE POLICY:** nessun hard delete; RESTRICT dopo creazione. **WRITER
AUTHORITY:** allocation writer del Planning Commit Repository.

### TABLE: `tpo.allocazioni_domanda`

**RESPONSIBILITY:** specializzazione domanda di una allocazione.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `allocation_id` | `bigint` | NOT NULL | NONE | parent globale |
| `riga_ordine_id` | `bigint` | NOT NULL | NONE | domanda destinazione |

**PRIMARY KEY:** `allocazioni_domanda_pkey` (`allocation_id`). **FOREIGN KEYS:**
`allocazioni_domanda_allocation_id_fkey`: `allocation_id` →
`tpo.allocazioni(id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`allocazioni_domanda_riga_ordine_id_fkey`: `riga_ordine_id` →
`tpo.righe_ordine(id)` ON UPDATE RESTRICT ON DELETE RESTRICT. **UNIQUE
CONSTRAINTS:** nessuna oltre PK; il vincolo composto
(`riga_ordine_id`,`allocation_id`) è ridondante perché `allocation_id` è già PK
e non esprime alcun ulteriore invariante di business. **CHECK CONSTRAINTS:**
nessuno. **OTHER STRUCTURAL CONSTRAINTS:** partecipa a
`ct_allocazioni_exactly_one_child` e richiede parent con `allocation_type =
'DOMANDA'`. **INDEXES:**
`ix_allocazioni_domanda_riga_ordine` (`riga_ordine_id`). **MUTABILITY:**
append-only. **OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:**
RESTRICT. **WRITER AUTHORITY:** allocation writer.

### TABLE: `tpo.allocazioni_stock`

**RESPONSIBILITY:** specializzazione stock di una allocazione.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `allocation_id` | `bigint` | NOT NULL | NONE | parent globale |
| `stock_varieta_id` | `bigint` | NOT NULL | NONE | risorsa stock sorgente |

**PRIMARY KEY:** `pk_allocazioni_stock` (`allocation_id`). **FOREIGN KEYS:**
`fk_allocazioni_stock_allocation`: `allocation_id` → `tpo.allocazioni(id)` ON
UPDATE RESTRICT ON DELETE RESTRICT; `fk_allocazioni_stock_stock_varieta`:
`stock_varieta_id` → `tpo.stock(varieta_id)` ON UPDATE RESTRICT ON DELETE
RESTRICT. **UNIQUE CONSTRAINTS:** nessuna oltre PK. **CHECK CONSTRAINTS:**
nessuno. **OTHER STRUCTURAL CONSTRAINTS:** partecipa a
`ct_allocazioni_exactly_one_child`. **INDEXES:**
`ix_allocazioni_stock_stock_varieta` (`stock_varieta_id`). **MUTABILITY:**
append-only. **OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:**
RESTRICT. **WRITER AUTHORITY:** allocation writer.

### TABLE: `tpo.allocazioni_produzione_in_corso`

**RESPONSIBILITY:** specializzazione produzione in corso di una allocazione.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `allocation_id` | `bigint` | NOT NULL | NONE | parent globale |
| `semina_id` | `bigint` | NOT NULL | NONE | semina sorgente |

**PRIMARY KEY:** `pk_allocazioni_produzione_in_corso` (`allocation_id`).
**FOREIGN KEYS:** `fk_allocazioni_produzione_in_corso_allocation`:
`allocation_id` → `tpo.allocazioni(id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_allocazioni_produzione_in_corso_semina`: `semina_id` → `tpo.semine(id)` ON
UPDATE RESTRICT ON DELETE RESTRICT. **UNIQUE CONSTRAINTS:** nessuna oltre PK.
**CHECK CONSTRAINTS:** nessuno. **OTHER STRUCTURAL CONSTRAINTS:** partecipa a
`ct_allocazioni_exactly_one_child`. **INDEXES:**
`ix_allocazioni_produzione_in_corso_semina` (`semina_id`). **MUTABILITY:**
append-only. **OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:**
RESTRICT. **WRITER AUTHORITY:** allocation writer.

### TABLE: `tpo.allocazioni_raccolta`

**RESPONSIBILITY:** specializzazione raccolta di una allocazione.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `allocation_id` | `bigint` | NOT NULL | NONE | parent globale |
| `raccolta_id` | `bigint` | NOT NULL | NONE | raccolta sorgente |

**PRIMARY KEY:** `pk_allocazioni_raccolta` (`allocation_id`). **FOREIGN KEYS:**
`fk_allocazioni_raccolta_allocation`: `allocation_id` → `tpo.allocazioni(id)`
ON UPDATE RESTRICT ON DELETE RESTRICT; `fk_allocazioni_raccolta_raccolta`:
`raccolta_id` → `tpo.raccolte(id)` ON UPDATE RESTRICT ON DELETE RESTRICT.
**UNIQUE CONSTRAINTS:** nessuna oltre PK. **CHECK CONSTRAINTS:** nessuno.
**OTHER STRUCTURAL CONSTRAINTS:** partecipa a
`ct_allocazioni_exactly_one_child`. **INDEXES:**
`ix_allocazioni_raccolta_raccolta` (`raccolta_id`). **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:** RESTRICT.
**WRITER AUTHORITY:** allocation writer.

### TABLE: `tpo.righe_piano_semina_semine`

**RESPONSIBILITY:** attribuzione immutabile Piano→SEMINA. **COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | PK |
| `riga_piano_semina_id` | `bigint` | NOT NULL | NO DEFAULT | riga piano |
| `semina_id` | `bigint` | NOT NULL | NO DEFAULT | semina reale |
| `quantita_avviata` | `numeric(20,6)` | NOT NULL | NO DEFAULT | quantità avviata |
| `unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | UOM produttiva SET |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |

**PRIMARY KEY:** `CONSTRAINT righe_piano_semina_semine_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** `CONSTRAINT
righe_piano_semina_semine_riga_piano_semina_id_fkey FOREIGN KEY
(riga_piano_semina_id) REFERENCES tpo.righe_piano_semina(id) ON UPDATE RESTRICT
ON DELETE RESTRICT`; `CONSTRAINT righe_piano_semina_semine_semina_id_fkey
FOREIGN KEY (semina_id) REFERENCES tpo.semine(id) ON UPDATE RESTRICT ON DELETE
RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_righe_piano_semina_semine_riga_semina UNIQUE
(riga_piano_semina_id,semina_id)`; `CONSTRAINT
uq_righe_piano_semina_semine_semina UNIQUE (semina_id)`. **CHECK CONSTRAINTS:**
`CONSTRAINT ck_righe_piano_semina_semine_quantita CHECK (quantita_avviata >
0)`; `CONSTRAINT ck_righe_piano_semina_semine_uom CHECK
(unita_misura='SET')`; `CONSTRAINT ck_righe_piano_semina_semine_created_by
CHECK (btrim(created_by) <> '')`. **OTHER STRUCTURAL CONSTRAINTS:** prima del
commit il writer verifica sotto lock che `unita_misura` coincida con
`righe_piano_semina.unita_domanda` e che la somma delle `quantita_avviata` dei
link della stessa RPS non superi `quantita_produttiva_autorizzata`; nessun
trigger business. **INDEXES:** `CREATE INDEX
ix_righe_piano_semina_semine_riga ON tpo.righe_piano_semina_semine
(riga_piano_semina_id ASC)`; `CREATE INDEX ix_righe_piano_semina_semine_semina
ON tpo.righe_piano_semina_semine (semina_id ASC)`; `CREATE INDEX
ix_righe_piano_semina_semine_riga_created ON tpo.righe_piano_semina_semine
(riga_piano_semina_id ASC,created_at ASC)`. **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:** RESTRICT.
**WRITER AUTHORITY:** writer della transizione Piano→SEMINA.

### TABLE: `tpo.replanning_snapshots`

**RESPONSIBILITY:** snapshot canonico autorevole degli input di una singola
ripianificazione.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | meaning / authority |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `order_line_public_id` | `text` | NOT NULL | NO DEFAULT | riga ordine osservata |
| `order_public_id` | `text` | NOT NULL | NO DEFAULT | ordine osservato |
| `order_state` | `ordine_state` | NOT NULL | NO DEFAULT | stato ordine |
| `order_version` | `bigint` | NOT NULL | NO DEFAULT | versione ordine |
| `order_line_version` | `bigint` | NOT NULL | NO DEFAULT | versione riga ordine |
| `ordered_quantity` | `numeric(20,6)` | NOT NULL | NO DEFAULT | quantità ordinata |
| `delivered_quantity` | `numeric(20,6)` | NOT NULL | NO DEFAULT | quantità consegnata |
| `commercial_residual_quantity` | `numeric(20,6)` | NOT NULL | NO DEFAULT | residuo commerciale |
| `delivery_date` | `date` | NOT NULL | NO DEFAULT | data consegna |
| `variety_public_id` | `text` | NOT NULL | NO DEFAULT | varietà osservata |
| `protocol_version_public_id` | `text` | NOT NULL | NO DEFAULT | protocollo osservato |
| `protocol_version_number` | `integer` | NOT NULL | NO DEFAULT | versione protocollo |
| `protocol_valid_from` | `date` | NOT NULL | NO DEFAULT | inizio validità |
| `protocol_valid_to` | `date` | NULL | NO DEFAULT | fine validità esclusiva |
| `policy_set_code` | `text` | NOT NULL | NO DEFAULT | policy set |
| `planning_policy_version` | `integer` | NOT NULL | NO DEFAULT | versione policy |
| `quantitative_buffer_policy_type` | `quantitative_buffer_policy_type` | NOT NULL | NO DEFAULT | tipo buffer |
| `quantitative_buffer_policy_value` | `numeric(20,6)` | NULL | NO DEFAULT | valore buffer |
| `temporal_buffer_minutes` | `integer` | NOT NULL | NO DEFAULT | buffer temporale |
| `production_granularity` | `numeric(20,6)` | NOT NULL | NO DEFAULT | granularità |
| `previous_plan_revision_public_id` | `text` | NOT NULL | NO DEFAULT | revisione precedente |
| `previous_plan_revision_version` | `bigint` | NOT NULL | NO DEFAULT | versione precedente |
| `replanning_reason_code` | `replanning_reason_code` | NOT NULL | NO DEFAULT | causa ripianificazione |
| `canonical_text` | `text` | NOT NULL | NO DEFAULT | framing canonico §2.1 |
| `canonical_hash` | `text` | NOT NULL | NO DEFAULT | unica authority hash |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit creazione |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |

**PRIMARY KEY:** `CONSTRAINT replanning_snapshots_pkey PRIMARY KEY (id)`.
**FOREIGN KEYS:** nessuna; in particolare nessuna FK inversa alla revisione.
**UNIQUE CONSTRAINTS:** `CONSTRAINT uq_replanning_snapshots_canonical_hash
UNIQUE (canonical_hash)`. **CHECK CONSTRAINTS:**
`CONSTRAINT ck_replanning_snapshots_canonical_hash CHECK (canonical_hash ~
'^[0-9a-f]{64}$')`; `CONSTRAINT ck_replanning_snapshots_versions CHECK
(order_version >= 0 AND order_line_version >= 0 AND
previous_plan_revision_version >= 0)`; `CONSTRAINT
ck_replanning_snapshots_quantities CHECK (ordered_quantity > 0 AND
delivered_quantity >= 0 AND commercial_residual_quantity >= 0 AND
commercial_residual_quantity = ordered_quantity - delivered_quantity AND
delivered_quantity <= ordered_quantity AND production_granularity > 0)`;
`CONSTRAINT ck_replanning_snapshots_protocol_validity CHECK
(protocol_valid_to IS NULL OR protocol_valid_to > protocol_valid_from)`;
`CONSTRAINT ck_replanning_snapshots_buffer CHECK
((quantitative_buffer_policy_type = 'NONE' AND
quantitative_buffer_policy_value IS NULL) OR
(quantitative_buffer_policy_type <> 'NONE' AND
quantitative_buffer_policy_value >= 0))`; `CONSTRAINT
ck_replanning_snapshots_texts CHECK (btrim(order_line_public_id) <> '' AND
btrim(order_public_id) <> '' AND btrim(variety_public_id) <> '' AND
btrim(protocol_version_public_id) <> '' AND btrim(policy_set_code) <> '' AND
btrim(previous_plan_revision_public_id) <> '' AND canonical_text <> '' AND
btrim(created_by) <> '')`. **OTHER STRUCTURAL CONSTRAINTS:** la proprietà è
unidirezionale dalla revisione. **INDEXES:** `ix_replanning_snapshots_hash` ON
`tpo.replanning_snapshots` (`canonical_hash ASC`);
`ix_replanning_snapshots_order_line` (`order_line_public_id ASC`);
`ix_replanning_snapshots_previous_revision`
(`previous_plan_revision_public_id ASC`). **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:** RESTRICT.
**WRITER AUTHORITY:** Planning writer.

### TABLE: `tpo.replanning_snapshot_stock`

**RESPONSIBILITY:** lista canonica delle risorse stock lette nello snapshot.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `snapshot_id` | `bigint` | NOT NULL | NONE | snapshot proprietario |
| `posizione` | `integer` | NOT NULL | NONE | posizione canonica densa |
| `stock_resource_public_id` | `text` | NOT NULL | NONE | public ID risorsa stock |
| `variety_public_id` | `text` | NOT NULL | NONE | varietà della risorsa |
| `eligible_quantity` | `numeric(20,6)` | NOT NULL | NONE | quantità eleggibile |
| `allocated_quantity` | `numeric(20,6)` | NOT NULL | NONE | quantità già allocata |
| `allocable_residual` | `numeric(20,6)` | NOT NULL | NONE | residuo allocabile |
| `resource_version` | `bigint` | NOT NULL | NONE | versione osservata |
| `readiness_code` | `text` | NOT NULL | NONE | stato readiness canonico |

**PRIMARY KEY:** `pk_replanning_snapshot_stock`
(`snapshot_id`,`posizione`). **FOREIGN KEYS:**
`fk_replanning_snapshot_stock_snapshot`: `snapshot_id` →
`tpo.replanning_snapshots(id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_stock_resource`: `stock_resource_public_id` →
`tpo.varieta(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_stock_variety`: `variety_public_id` →
`tpo.varieta(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT. **UNIQUE
CONSTRAINTS:** `uq_replanning_snapshot_stock_resource`
(`snapshot_id`,`stock_resource_public_id`). **CHECK CONSTRAINTS:**
`ck_replanning_snapshot_stock_posizione` (`posizione > 0`),
`ck_replanning_snapshot_stock_quantities` (tutte le quantità >= 0 e
`allocable_residual = eligible_quantity - allocated_quantity`),
`ck_replanning_snapshot_stock_version` (`resource_version >= 0`),
`ck_replanning_snapshot_stock_readiness` (`btrim(readiness_code) <> ''`).
**OTHER STRUCTURAL CONSTRAINTS:** constraint trigger
`ct_replanning_snapshot_stock_dense`, DEFERRABLE INITIALLY DEFERRED, impone
posizioni esattamente 1..N per snapshot. **INDEXES:**
`ix_replanning_snapshot_stock_resource` (`stock_resource_public_id`).
**MUTABILITY:** append-only. **OPTIMISTIC CONCURRENCY:** non applicabile.
**DELETE POLICY:** RESTRICT. **WRITER AUTHORITY:** Planning writer.

### TABLE: `tpo.replanning_snapshot_semine`

**RESPONSIBILITY:** lista canonica delle semine in corso lette nello snapshot.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `snapshot_id` | `bigint` | NOT NULL | NONE | snapshot proprietario |
| `posizione` | `integer` | NOT NULL | NONE | posizione canonica densa |
| `semina_public_id` | `text` | NOT NULL | NONE | semina osservata |
| `variety_public_id` | `text` | NOT NULL | NONE | varietà osservata |
| `protocol_version_public_id` | `text` | NOT NULL | NONE | protocollo osservato |
| `expected_useful_quantity` | `numeric(20,6)` | NOT NULL | NONE | resa utile attesa |
| `allocated_quantity` | `numeric(20,6)` | NOT NULL | NONE | quantità allocata |
| `allocable_residual` | `numeric(20,6)` | NOT NULL | NONE | residuo allocabile |
| `harvest_window_start` | `timestamptz` | NOT NULL | NONE | inizio finestra |
| `harvest_window_end` | `timestamptz` | NOT NULL | NONE | fine finestra |
| `semina_state` | `semina_state` | NOT NULL | NONE | stato osservato |
| `semina_version` | `bigint` | NOT NULL | NONE | versione osservata |

**PRIMARY KEY:** `pk_replanning_snapshot_semine`
(`snapshot_id`,`posizione`). **FOREIGN KEYS:**
`fk_replanning_snapshot_semine_snapshot`: `snapshot_id` →
`tpo.replanning_snapshots(id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_semine_semina`: `semina_public_id` →
`tpo.semine(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_semine_variety`: `variety_public_id` →
`tpo.varieta(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_semine_protocol`: `protocol_version_public_id` →
`tpo.protocollo_versioni(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT.
**UNIQUE CONSTRAINTS:** `uq_replanning_snapshot_semine_semina`
(`snapshot_id`,`semina_public_id`). **CHECK CONSTRAINTS:**
`ck_replanning_snapshot_semine_posizione` (`posizione > 0`),
`ck_replanning_snapshot_semine_quantities` (quantità >= 0 e
`allocable_residual = expected_useful_quantity - allocated_quantity`),
`ck_replanning_snapshot_semine_window`
(`harvest_window_end > harvest_window_start`),
`ck_replanning_snapshot_semine_version` (`semina_version >= 0`). **OTHER
STRUCTURAL CONSTRAINTS:** constraint trigger
`ct_replanning_snapshot_semine_dense`, DEFERRABLE INITIALLY DEFERRED, impone
posizioni esattamente 1..N per snapshot. **INDEXES:**
`ix_replanning_snapshot_semine_semina` (`semina_public_id`). **MUTABILITY:**
append-only. **OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:**
RESTRICT. **WRITER AUTHORITY:** Planning writer.

### TABLE: `tpo.replanning_snapshot_allocazioni`

**RESPONSIBILITY:** lista canonica delle allocazioni lette nello snapshot.

**COLUMNS:**

| column | PostgreSQL type | nullability | default | authority / meaning |
|---|---|---|---|---|
| `snapshot_id` | `bigint` | NOT NULL | NONE | snapshot proprietario |
| `posizione` | `integer` | NOT NULL | NONE | posizione canonica densa |
| `allocation_public_id` | `text` | NOT NULL | NONE | allocazione osservata |
| `allocation_type` | `allocation_type` | NOT NULL | NONE | tipo osservato |
| `source_public_id` | `text` | NOT NULL | NONE | sorgente canonica tipizzata |
| `destination_order_line_public_id` | `text` | NOT NULL | NONE | riga ordine destinazione |
| `allocated_quantity` | `numeric(20,6)` | NOT NULL | NONE | quantità allocata |
| `unita_misura` | `unit_of_measure` | NOT NULL | NONE | unità quantità |
| `allocation_state` | `planning_allocation_state` | NOT NULL | NONE | stato osservato |
| `allocation_version` | `bigint` | NOT NULL | NONE | versione osservata |

**PRIMARY KEY:** `pk_replanning_snapshot_allocazioni`
(`snapshot_id`,`posizione`). **FOREIGN KEYS:**
`fk_replanning_snapshot_allocazioni_snapshot`: `snapshot_id` →
`tpo.replanning_snapshots(id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_allocazioni_allocation`: `allocation_public_id` →
`tpo.allocazioni(public_id)` ON UPDATE RESTRICT ON DELETE RESTRICT;
`fk_replanning_snapshot_allocazioni_destination`:
`destination_order_line_public_id` → `tpo.righe_ordine(public_id)` ON UPDATE
RESTRICT ON DELETE RESTRICT. `source_public_id` non è una FK polimorfica: è il
valore snapshot autorevole interpretato con `allocation_type`. **UNIQUE
CONSTRAINTS:** `uq_replanning_snapshot_allocazioni_allocation`
(`snapshot_id`,`allocation_public_id`). **CHECK CONSTRAINTS:**
`ck_replanning_snapshot_allocazioni_posizione` (`posizione > 0`),
`ck_replanning_snapshot_allocazioni_quantity` (`allocated_quantity > 0`),
`ck_replanning_snapshot_allocazioni_version` (`allocation_version >= 0`),
`ck_replanning_snapshot_allocazioni_source` (`btrim(source_public_id) <> ''`).
**OTHER STRUCTURAL CONSTRAINTS:** constraint trigger
`ct_replanning_snapshot_allocazioni_dense`, DEFERRABLE INITIALLY DEFERRED,
impone posizioni esattamente 1..N per snapshot. **INDEXES:**
`ix_replanning_snapshot_allocazioni_allocation` (`allocation_public_id`),
`ix_replanning_snapshot_allocazioni_destination`
(`destination_order_line_public_id`). **MUTABILITY:** append-only.
**OPTIMISTIC CONCURRENCY:** non applicabile. **DELETE POLICY:** RESTRICT.
**WRITER AUTHORITY:** Planning writer.

### TABLE: `tpo.ordini` (existing, extended)

**RESPONSIBILITY:** ordine commerciale autorevole. **COLUMNS:**

| column | PostgreSQL type | nullability | default | meaning / authority |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | ORD-* |
| `cliente_id` | `bigint` | NOT NULL | NO DEFAULT | cliente |
| `programma_fornitura_id` | `bigint` | NULL | NO DEFAULT | programma automatico |
| `run_id` | `bigint` | NULL | NO DEFAULT | RUN scheduling |
| `data_ordine` | `date` | NOT NULL | NO DEFAULT | data ordine |
| `data_consegna_prevista` | `date` | NULL | NO DEFAULT | consegna prevista |
| `stato` | `ordine_state` | NOT NULL | NO DEFAULT | lifecycle |
| `tipo_creazione` | `ordine_creation_type` | NOT NULL | NO DEFAULT | origine |
| `chiave_idempotenza` | `text` | NULL | NO DEFAULT | chiave automatica |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS Planning |

**PRIMARY KEY:** `CONSTRAINT ordini_pkey PRIMARY KEY (id)`. **FOREIGN KEYS:**
`CONSTRAINT ordini_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES
tpo.clienti(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
ordini_programma_fornitura_id_fkey FOREIGN KEY (programma_fornitura_id)
REFERENCES tpo.programmi_fornitura(id) ON UPDATE RESTRICT ON DELETE RESTRICT`;
`CONSTRAINT ordini_run_id_fkey FOREIGN KEY (run_id) REFERENCES tpo.runs(id) ON
UPDATE RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
ordini_public_id_key UNIQUE (public_id)`; `CONSTRAINT
ordini_chiave_idempotenza_key UNIQUE (chiave_idempotenza)`. **CHECK
CONSTRAINTS:** `CONSTRAINT ck_ordini_consegna_not_before_ordine CHECK
(data_consegna_prevista IS NULL OR data_consegna_prevista >= data_ordine)`;
`CONSTRAINT ck_ordini_chiave_idempotenza_not_blank CHECK
(chiave_idempotenza IS NULL OR btrim(chiave_idempotenza) <> '')`; `CONSTRAINT
ck_ordini_tipo_creazione_metadati CHECK ((tipo_creazione = 'AUTOMATICO' AND
run_id IS NOT NULL AND programma_fornitura_id IS NOT NULL AND
data_consegna_prevista IS NOT NULL AND chiave_idempotenza IS NOT NULL) OR
(tipo_creazione = 'MANUALE' AND run_id IS NULL AND programma_fornitura_id IS
NULL AND chiave_idempotenza IS NULL))`; `CONSTRAINT
ck_ordini_created_by_not_blank CHECK (btrim(created_by) <> '')`; `CONSTRAINT
ck_ordini_public_id_format CHECK (public_id ~ '^ORD-[0-9]{6,}$')`; `CONSTRAINT
ck_ordini_version CHECK (version >= 0)`. **OTHER STRUCTURAL CONSTRAINTS:**
nessuno. **INDEXES:** `ix_ordini_cliente_id` (`cliente_id ASC`);
`ix_ordini_programma_fornitura_id` (`programma_fornitura_id ASC`);
`ix_ordini_run_id` (`run_id ASC`); `ix_ordini_stato_data_consegna_prevista`
(`stato ASC`,`data_consegna_prevista ASC`); `ix_ordini_cliente_data_ordine`
(`cliente_id ASC`,`data_ordine ASC`); `ix_ordini_programma_data_consegna`
(`programma_fornitura_id ASC`,`data_consegna_prevista ASC`). Tutti ON
`tpo.ordini`, non partial.
**MUTABILITY:** §4.1. **OPTIMISTIC CONCURRENCY:** CAS su `version`. **DELETE
POLICY:** §4.1. **WRITER AUTHORITY:** Order writer esistente.

### TABLE: `tpo.righe_ordine` (existing, extended)

**RESPONSIBILITY:** riga commerciale autorevole. **COLUMNS:**

| column | PostgreSQL type | nullability | default | meaning / authority |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | RO-* |
| `ordine_id` | `bigint` | NOT NULL | NO DEFAULT | ordine proprietario |
| `posizione` | `integer` | NOT NULL | NO DEFAULT | posizione ordine |
| `varieta_id` | `bigint` | NOT NULL | NO DEFAULT | varietà richiesta |
| `quantita` | `numeric(20,6)` | NOT NULL | NO DEFAULT | quantità richiesta |
| `unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | UOM |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS Planning |

**PRIMARY KEY:** `CONSTRAINT righe_ordine_pkey PRIMARY KEY (id)`. **FOREIGN
KEYS:** `CONSTRAINT righe_ordine_ordine_id_fkey FOREIGN KEY (ordine_id)
REFERENCES tpo.ordini(id) ON UPDATE RESTRICT ON DELETE CASCADE`; `CONSTRAINT
righe_ordine_varieta_id_fkey FOREIGN KEY (varieta_id) REFERENCES
tpo.varieta(id) ON UPDATE RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:**
`CONSTRAINT uq_righe_ordine_posizione UNIQUE (ordine_id,posizione)`;
`CONSTRAINT uq_righe_ordine_public_id UNIQUE (public_id)`. **CHECK
CONSTRAINTS:** `CONSTRAINT ck_righe_ordine_posizione_positive CHECK (posizione >
0)`; `CONSTRAINT ck_righe_ordine_quantita_positive CHECK (quantita > 0)`;
`CONSTRAINT ck_righe_ordine_public_id CHECK (public_id ~ '^RO-[0-9]{6,}$')`;
`CONSTRAINT ck_righe_ordine_version CHECK (version >= 0)`. **OTHER STRUCTURAL
CONSTRAINTS:** nessuno. **INDEXES:** `ix_righe_ordine_varieta_id` ON
`tpo.righe_ordine` (`varieta_id ASC`); `ix_righe_ordine_varieta_ordine`
(`varieta_id ASC`,`ordine_id ASC`); `ix_righe_ordine_public_id` (`public_id
ASC`), tutti non partial. **MUTABILITY:** §4.2. **OPTIMISTIC
CONCURRENCY:** CAS su `version`. **DELETE POLICY:** §4.2. **WRITER AUTHORITY:**
Order writer esistente.

### TABLE: `tpo.semine` (existing, extended)

**RESPONSIBILITY:** semina operativa autorevole. **COLUMNS:**

| column | PostgreSQL type | nullability | default | meaning / authority |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `public_id` | `text` | NOT NULL | NO DEFAULT | SEM-* |
| `varieta_id` | `bigint` | NOT NULL | NO DEFAULT | varietà |
| `cultivar_id` | `bigint` | NOT NULL | NO DEFAULT | cultivar |
| `cultivar_uso_id` | `bigint` | NOT NULL | NO DEFAULT | uso produttivo |
| `lotto_seme_id` | `bigint` | NOT NULL | NO DEFAULT | lotto |
| `protocollo_versione_id` | `bigint` | NOT NULL | NO DEFAULT | protocollo |
| `stato` | `semina_state` | NOT NULL | NO DEFAULT | lifecycle |
| `quantita_seme` | `numeric(20,6)` | NOT NULL | NO DEFAULT | seme impiegato |
| `unita_misura` | `unit_of_measure` | NOT NULL | NO DEFAULT | sempre GRAM |
| `data_avvio` | `timestamptz` | NOT NULL | NO DEFAULT | avvio reale |
| `causa_origine` | `text` | NOT NULL | NO DEFAULT | causa |
| `esito_finale` | `semina_esito` | NULL | NO DEFAULT | esito chiusura |
| `cultivar_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot cultivar |
| `uso_produttivo_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot uso |
| `lotto_seme_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot lotto |
| `protocollo_snapshot` | `text` | NOT NULL | NO DEFAULT | snapshot protocollo |
| `created_at` | `timestamptz` | NOT NULL | DEFAULT CURRENT_TIMESTAMP | audit |
| `created_by` | `text` | NOT NULL | NO DEFAULT | actor |
| `version` | `bigint` | NOT NULL | DEFAULT 0 | CAS |

**PRIMARY KEY:** `CONSTRAINT semine_pkey PRIMARY KEY (id)`. **FOREIGN KEYS:**
`CONSTRAINT semine_varieta_id_fkey FOREIGN KEY (varieta_id) REFERENCES
tpo.varieta(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
semine_cultivar_id_fkey FOREIGN KEY (cultivar_id) REFERENCES tpo.cultivar(id) ON
UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT semine_cultivar_uso_id_fkey
FOREIGN KEY (cultivar_uso_id) REFERENCES tpo.cultivar_usi(id) ON UPDATE RESTRICT
ON DELETE RESTRICT`; `CONSTRAINT semine_lotto_seme_id_fkey FOREIGN KEY
(lotto_seme_id) REFERENCES tpo.lotti_seme(id) ON UPDATE RESTRICT ON DELETE
RESTRICT`; `CONSTRAINT semine_protocollo_versione_id_fkey FOREIGN KEY
(protocollo_versione_id) REFERENCES tpo.protocollo_versioni(id) ON UPDATE
RESTRICT ON DELETE RESTRICT`. **UNIQUE CONSTRAINTS:** `CONSTRAINT
uq_semine_public_id UNIQUE (public_id)`. **CHECK CONSTRAINTS:** `CONSTRAINT
ck_semine_public_id CHECK (public_id ~ '^SEM-[0-9]{6,}$')`; `CONSTRAINT
ck_semine_quantita CHECK (quantita_seme > 0)`; `CONSTRAINT ck_semine_uom CHECK
(unita_misura = 'GRAM')`; `CONSTRAINT ck_semine_causa CHECK
(btrim(causa_origine) <> '')`; `CONSTRAINT ck_semine_esito CHECK ((stato =
'CHIUSA' AND esito_finale IS NOT NULL) OR (stato <> 'CHIUSA' AND esito_finale IS
NULL))`; `CONSTRAINT ck_semine_created_by CHECK (btrim(created_by) <> '')`;
`CONSTRAINT ck_semine_version CHECK (version >= 0)`. **OTHER STRUCTURAL
CONSTRAINTS:** coerenza cultivar/uso/lotto/protocollo verificata dal writer sotto
lock, senza trigger business. **INDEXES:** `ix_semine_varieta_id`
(`varieta_id ASC`); `ix_semine_cultivar_id` (`cultivar_id ASC`);
`ix_semine_cultivar_uso_id` (`cultivar_uso_id ASC`); `ix_semine_lotto_seme_id`
(`lotto_seme_id ASC`); `ix_semine_protocollo_versione_id`
(`protocollo_versione_id ASC`); `ix_semine_stato_data_avvio`
(`stato ASC`,`data_avvio ASC`); `ix_semine_causa_origine` (`causa_origine ASC`),
tutti ON `tpo.semine`, non partial. **MUTABILITY:** §4.4. **OPTIMISTIC
CONCURRENCY:** CAS su `version`.
**DELETE POLICY:** §4.4. **WRITER AUTHORITY:** SEMINA writer esistente.

### TABLE: `tpo.audit_eventi` (existing, extended)

**RESPONSIBILITY:** audit append-only condiviso. **COLUMNS:**

| column | PostgreSQL type | nullability | default | meaning / authority |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | GENERATED BY DEFAULT AS IDENTITY | chiave fisica |
| `occurred_at` | `timestamptz` | NOT NULL | NO DEFAULT | istante evento |
| `actor` | `text` | NOT NULL | NO DEFAULT | actor |
| `run_id` | `bigint` | NULL | NO DEFAULT | RUN scheduling |
| `planning_run_id` | `bigint` | NULL | NO DEFAULT | RUN Planning |
| `entity_type` | `text` | NOT NULL | NO DEFAULT | tipo entità |
| `entity_public_id` | `text` | NULL | NO DEFAULT | public ID entità |
| `operation` | `audit_operation` | NOT NULL | NO DEFAULT | operazione |
| `reason` | `text` | NOT NULL | NO DEFAULT | motivo |
| `before_data` | `jsonb` | NULL | NO DEFAULT | stato precedente |
| `after_data` | `jsonb` | NULL | NO DEFAULT | stato successivo |
| `correlation_id` | `text` | NULL | NO DEFAULT | correlazione |

**PRIMARY KEY:** `CONSTRAINT audit_eventi_pkey PRIMARY KEY (id)`. **FOREIGN
KEYS:** `CONSTRAINT audit_eventi_run_id_fkey FOREIGN KEY (run_id) REFERENCES
tpo.runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT`; `CONSTRAINT
audit_eventi_planning_run_id_fkey FOREIGN KEY (planning_run_id) REFERENCES
tpo.production_planning_runs(id) ON UPDATE RESTRICT ON DELETE RESTRICT`.
**UNIQUE CONSTRAINTS:** nessuno. **CHECK CONSTRAINTS:** `CONSTRAINT
ck_audit_eventi_actor_not_blank CHECK (btrim(actor) <> '')`; `CONSTRAINT
ck_audit_eventi_entity_type_not_blank CHECK (btrim(entity_type) <> '')`;
`CONSTRAINT ck_audit_eventi_entity_public_id_not_blank CHECK
(entity_public_id IS NULL OR btrim(entity_public_id) <> '')`; `CONSTRAINT
ck_audit_eventi_reason_not_blank CHECK (btrim(reason) <> '')`; `CONSTRAINT
ck_audit_eventi_correlation_id_not_blank CHECK (correlation_id IS NULL OR
btrim(correlation_id) <> '')`; `CONSTRAINT ck_audit_eventi_payload_present CHECK
(before_data IS NOT NULL OR after_data IS NOT NULL)`; `CONSTRAINT
ck_audit_eventi_delete_before CHECK (operation <> 'DELETE' OR before_data IS NOT
NULL)`; `CONSTRAINT ck_audit_eventi_insert_after CHECK (operation <> 'INSERT' OR
after_data IS NOT NULL)`; `CONSTRAINT ck_audit_eventi_before_object CHECK
(before_data IS NULL OR jsonb_typeof(before_data) = 'object')`; `CONSTRAINT
ck_audit_eventi_after_object CHECK (after_data IS NULL OR
jsonb_typeof(after_data) = 'object')`; `CONSTRAINT
ck_audit_eventi_single_run_owner CHECK
(num_nonnulls(run_id,planning_run_id) <= 1)`. **OTHER STRUCTURAL CONSTRAINTS:**
nessuno. **INDEXES:** `ix_audit_eventi_entity` ON `tpo.audit_eventi`
(`entity_type ASC`,`entity_public_id ASC`,`occurred_at ASC`);
`ix_audit_eventi_run_id` (`run_id ASC`); `ix_audit_eventi_actor` (`actor ASC`);
`ix_audit_eventi_occurred_at` (`occurred_at ASC`);
`ix_audit_eventi_planning_run` (`planning_run_id ASC`);
`ix_audit_eventi_planning_run_occurred`
(`planning_run_id ASC`,`occurred_at ASC`), tutti non partial.
**MUTABILITY:** append-only. **OPTIMISTIC CONCURRENCY:** non applicabile.
**DELETE POLICY:** RESTRICT. **WRITER AUTHORITY:** audit writer esistente e
Planning writer esclusivamente per eventi Planning.

### VIEW: `tpo.v_calendario_produzione`

**COLUMNS:** `event_at timestamptz NOT NULL`; `event_date date NOT NULL`;
`event_type text NOT NULL`; `planned boolean NOT NULL`; `piano_public_id text
NULL`; `revision_public_id text NULL`; `riga_piano_public_id text NULL`;
`semina_public_id text NULL`; `raccolta_public_id text NULL`;
`consegna_public_id text NULL`; `source_state text NOT NULL`; `varieta_id bigint
NULL`; `cultivar_id bigint NULL`; `cultivar_uso_id bigint NULL`; `quantita
numeric(20,6) NULL`; `unita_misura unit_of_measure NULL`; `data_consegna date
NULL`; `provenance text NOT NULL`. **SOURCES:** righe/revisioni piano, link,
SEMINE, RACCOLTE e CONSEGNE mediante `UNION ALL`. **PK/FK/UNIQUE/CHECK/VERSION/
AUDIT/DELETE/WRITER:** non applicabili: è read-only e ricostruibile. Quantità e
UOM sono entrambe NULL o entrambe valorizzate. PROBLEMI resta escluso finché non
esiste una FK approvata. Indici richiesti esclusivamente sulle sorgenti come
definiti nelle rispettive tabelle.

`event_at` è sempre un istante autorevole o già deterministicamente calcolato e
persistito nella sorgente. Gli eventi RPS `IDRATAZIONE_PIANIFICATA`,
`SEMINA_PIANIFICATA`, `LUCE_PIANIFICATA` e `RACCOLTA_TARGET` espongono
`righe_piano_semina.data_consegna` come contesto commerciale, senza convertirla
in `timestamptz` e senza creare un evento autonomo di consegna futura. Gli event
type `CONSEGNA_PIANIFICATA` e `CONSEGNA_PREVISTA` non esistono in V1.

**BRANCH CONSEGNE NORMATIVA:**

```sql
SELECT
    c.data_effettiva AS event_at,
    (c.data_effettiva AT TIME ZONE 'Atlantic/Canary')::date AS event_date,
    'CONSEGNA_EFFETTIVA'::text AS event_type,
    false AS planned,
    NULL::text AS piano_public_id,
    NULL::text AS revision_public_id,
    NULL::text AS riga_piano_public_id,
    NULL::text AS semina_public_id,
    NULL::text AS raccolta_public_id,
    c.public_id AS consegna_public_id,
    c.stato::text AS source_state,
    NULL::bigint AS varieta_id,
    NULL::bigint AS cultivar_id,
    NULL::bigint AS cultivar_uso_id,
    NULL::numeric(20,6) AS quantita,
    NULL::tpo.unit_of_measure AS unita_misura,
    c.data_prevista AS data_consegna,
    'tpo.consegne.data_effettiva'::text AS provenance
FROM tpo.consegne AS c
WHERE c.stato = 'CONSEGNATA'
  AND c.data_effettiva IS NOT NULL
```

La branch non promuove `data_prevista` a timestamp e non modifica il Register
`tpo.consegne`.
