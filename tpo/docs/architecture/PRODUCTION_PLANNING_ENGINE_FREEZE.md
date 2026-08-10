# Production Planning Engine Architecture Freeze V1 — Draft

## 1. Stato e autorità normativa

Il presente documento costituisce il draft del contratto architetturale V1 del bounded context **Production Planning** di Tower Power OS.

Fino all'approvazione della Freeze Review, questo documento non autorizza implementazioni, migrazioni, provisioning o attivazioni operative. Dopo l'approvazione, ogni implementazione del Production Planning Engine deve rispettarne integralmente gli invarianti.

Il Freeze congela il modello e il comportamento provider-neutral. Non congela valori produttivi reali di varietà, cultivar o protocolli.

## 2. Ambito e flusso autorevole

Il flusso operativo V1 è:

```text
ORDINI PostgreSQL committed
→ Production Planning
→ PIANO_SEMINE persistente
→ comando operatore
→ SEMINA fisica
→ RACCOLTA
→ CONSEGNA
```

Lo Scheduling Engine continua a creare esclusivamente ORDINI. Production Planning:

- non genera, modifica, annulla o corregge ORDINI;
- non modifica PROGRAMMI_FORNITURA;
- non crea automaticamente SEMINE;
- non registra automaticamente RACCOLTE o CONSEGNE;
- non usa Google Sheets come fonte autorevole o writer;
- non introduce dual-write Google/PostgreSQL.

PostgreSQL è l'unico datastore autorevole del runtime V1.

## 3. Responsabilità e confini

Production Planning è responsabile di:

- leggere la domanda commerciale committed;
- determinare domanda residua, coperture eleggibili e deficit;
- selezionare il Protocollo Standard approvato e la sua versione applicabile;
- applicare policy di priorità, buffer e granularità;
- convertire quantità produttive in seme e altre risorse;
- calcolare a ritroso la timeline produttiva;
- persistere piano, revisioni e allocazioni;
- mantenere idempotenza, provenance, audit e optimistic concurrency;
- segnalare condizioni tardive, non producibili o incoerenti;
- alimentare CALENDARIO_PRODUZIONE come read model derivato.

Non assume responsabilità di Scheduling, esecuzione fisica, raccolta o logistica.

## 4. Production Planning RUN

Production Planning utilizza una RUN dedicata e separata dalla Scheduling RUN. La tabella `runs` esistente non viene riutilizzata implicitamente.

Il lifecycle minimo concettuale è:

```text
OPEN
→ COMMITTED | FAILED | RECONCILIATION_REQUIRED
```

Una Planning RUN conclusa non viene riaperta. Il completamento usa optimistic concurrency e conserva contatori, messaggi ordinati, log e audit.

I contatori minimi sono:

- ORDINI letti;
- righe ORDINE valutate;
- righe coperte integralmente;
- righe coperte parzialmente;
- righe piano generate;
- allocazioni generate;
- righe tardive;
- righe non producibili;
- elementi saltati.

La separazione garantisce che un ORDINE committed resti valido se Planning fallisce e che lifecycle, ripianificazione, transazioni e lock siano indipendenti dallo Scheduling.

Una failure certa successiva all'apertura della RUN ma precedente al commit autorevole del piano viene conclusa mediante una transazione separata di failure-finalization. Tale transazione richiede RUN ancora `OPEN`, expected version coincidente e assenza di una conclusione precedente. Persiste esclusivamente stato `FAILED`, `completed_at`, errori provider-neutral ordinati, warning, audit e nuova versione; non crea piano o allocazioni e non costituisce retry.

`RECONCILIATION_REQUIRED` è riservato esclusivamente a un outcome fisico incerto del commit autorevole. Una RUN già conclusa non può essere conclusa nuovamente.

## 5. Input autorevoli

| Dato | Fonte autorevole |
|---|---|
| Domanda commerciale | ORDINI PostgreSQL committed nello stato APERTO o PARZIALMENTE_EVASO |
| Riga, quantità e VARIETA | RIGHE_ORDINE |
| Data richiesta | `data_consegna_prevista` dell'ORDINE |
| Cliente | ORDINE |
| Origine commerciale | provenance ORDINE/PROGRAMMA |
| Identità produttiva | CULTIVAR × USO PRODUTTIVO |
| Metodo produttivo | PROTOCOLLO STANDARD approvato |
| Parametri produttivi | PROTOCOLLO VERSIONE applicabile |
| Stock corrente | STOCK e MOVIMENTI_MAGAZZINO autorevoli |
| Produzione in corso | SEMINE reali non chiuse |
| Raccolte reali | RACCOLTE |
| Coperture impegnate | allocazioni persistenti di Production Planning |
| Istante di valutazione | business timestamp della Planning RUN |
| Regole di calcolo | versione esplicita della policy Planning |

Il motore non deduce dati da nomi liberi, ordine casuale delle query, default nascosti o valori legacy.

Production Planning elabora esclusivamente ORDINI `APERTO` o `PARZIALMENTE_EVASO`. ORDINI `EVASO` o `ANNULLATO` sono esclusi.

Per ogni riga:

```text
quantita_consegnata =
    somma delle quantità effettivamente consegnate
    e autorevolmente registrate per la riga ORDINE

domanda_residua_commerciale =
    quantita_ordinata - quantita_consegnata

0 ≤ domanda_residua_commerciale ≤ quantita_ordinata
```

Le allocazioni produttive non riducono la domanda commerciale residua. Determinano invece:

```text
domanda_residua_da_coprire =
    domanda_residua_commerciale
    - copertura_stock_attiva
    - copertura_produzione_in_corso_attiva
    - quantita_raccolta_utile_definitivamente_allocata
```

La PRENOTAZIONE LOGICA dell'ORDINE resta distinta dall'ALLOCAZIONE FISICA di Production Planning.

Prima del commit, stato ORDINE, quantità consegnata e versione attesa vengono riverificati sotto il confine concorrente. Se l'ORDINE diventa `EVASO` o `ANNULLATO`, oppure cambia la domanda residua, lo snapshot è obsoleto: rollback completo, outcome provider-neutral di input/concurrency changed e nessun retry cieco.

## 6. Conoscenza produttiva

La conoscenza produttiva appartiene a:

```text
CULTIVAR × USO PRODUTTIVO
→ PROTOCOLLO STANDARD
→ PROTOCOLLO VERSIONE
```

Non appartiene genericamente a VARIETA e non dipende dal provider della semente.

Ogni versione del protocollo è immutabile, storicizzata, temporalmente valida, collegata alla versione precedente quando presente e accompagnata da motivazione, provenance ed evidenza. Il runtime ordinario usa soltanto versioni approvate.

Il modello strutturato minimo contiene:

- `idratazione_ore`;
- `orario_semina_previsto`, local time `HH:MM`;
- `orario_raccolta_target`, local time `HH:MM`;
- `germinazione_giorni`;
- `crescita_luce_giorni`;
- `ciclo_produttivo_nominale_giorni` derivato;
- `grammi_seme_per_set`;
- resa attesa e relativa unità;
- granularità produttiva;
- finestra di raccolta rispetto alla consegna;
- `buffer_temporale_minuti`, durata in minuti interi non negativi;
- eventuale buffer quantitativo della policy associata;
- periodo di validità;
- stato di approvazione;
- provenance ed evidenza.

La formula normativa, espressa in giorni, è:

```text
ciclo_produttivo_nominale_giorni =
    germinazione_giorni + crescita_luce_giorni
```

Il ciclo nominale rappresenta esclusivamente l'intervallo SEMINA → RACCOLTA_TARGET. Non comprende `idratazione_ore`, buffer temporale, lead time post-raccolta, finestra di raccolta, attese o logistica. In V1 è derivato e non costituisce un'autorità persistita indipendente. Se materializzato per prestazioni, deve essere verificabile e non può divergere dalla somma delle fasi.

Valori assenti, vuoti, non approvati, fuori validità, negativi o incoerenti rendono la riga non pianificabile. Non esistono fallback verso il legacy o un lead time globale.

Gli orari previsti di semina e raccolta provengono esclusivamente dalla versione del protocollo. Non esiste un orario globale implicito. La loro assenza o invalidità produce `PRODUCTION_KNOWLEDGE_INVALID`.

La versione del protocollo è selezionata rispetto a `data_semina_target` usando l'intervallo half-open:

```text
valida_dal ≤ data_semina_target
AND
(valida_al IS NULL OR data_semina_target < valida_al)
```

Deve esistere esattamente una versione STANDARD, APPROVATA, appartenente alla combinazione CULTIVAR × USO PRODUTTIVO e valida alla data target. Zero versioni produce `PRODUCTION_KNOWLEDGE_INVALID / PROTOCOL_NOT_AVAILABLE`; più versioni producono `PRODUCTION_KNOWLEDGE_INVALID / PROTOCOL_AMBIGUOUS`.

Poiché `data_semina_target` dipende dai parametri della versione, la selezione è una valutazione deterministica dei candidati: per ogni versione STANDARD e APPROVATA della combinazione, il motore calcola la data target con i parametri di quella stessa versione e conserva il candidato soltanto se la data risultante ricade nel relativo intervallo di validità. Al termine deve rimanere esattamente un candidato. Non è ammessa selezione preliminare tramite business timestamp, data di consegna o ordine di lettura.

Il piano conserva `protocollo_versione_id`, numero di versione e snapshot strutturato dei parametri utilizzati. Una versione successiva non modifica retroattivamente una revisione già persistita.

## 7. Policy versionate

Ogni Planning RUN usa versioni esplicite e immutabili di:

- protocollo produttivo;
- policy di harvest target;
- policy di buffer temporale;
- policy di buffer quantitativo;
- policy di granularità;
- policy di allocazione e priorità.

Le versioni utilizzate sono conservate nella provenance. Una modifica successiva non riscrive piani, SEMINE o RUN precedenti. Nessun valore numerico globale di buffer, durata, resa o granularità è congelato dal presente Freeze.

## 8. Backplanning e harvest target

Il backplanning avviene per singola riga ORDINE e singola versione di protocollo.

La timeline normativa è:

```text
delivery_date
← harvest_window
← harvest_target_date / harvest_target_at
← sowing_at / sowing_date
← hydration_at / hydration_date

light_at = sowing_at + germinazione_giorni
light_date = local_date(light_at, Atlantic/Canary)
```

Per ogni timeline valida:

```text
harvest_window_start
≤ harvest_target
≤ harvest_window_end
< delivery_date
```

La versione del protocollo esprime:

- `harvest_min_lead`: anticipo minimo necessario rispetto alla consegna;
- `harvest_max_lead`: anticipo massimo ammesso, non inferiore al minimo.

V1 calcola:

```text
harvest_window_start = delivery_date - harvest_max_lead
harvest_window_end   = delivery_date - harvest_min_lead
harvest_target_date  = harvest_window_start
```

V1 sceglie quindi il primo istante approvato della finestra. La policy è deterministica e conservativa: massimizza il margine autorizzato prima della consegna senza uscire dalla finestra di readiness.

La raccolta non coincide automaticamente con la consegna. `harvest_target_date` è una DATE civile Atlantic/Canary. `harvest_target_at` è il timestamp operativo timezone-aware, con precisione al minuto, costruito senza default impliciti:

```text
harvest_target_at = combine(
    harvest_target_date,
    protocollo_versione.orario_raccolta_target,
    Atlantic/Canary
)

sowing_at_nominale = harvest_target_at
                     - germinazione_giorni
                     - crescita_luce_giorni

sowing_at = sowing_at_nominale - buffer_temporale_minuti

sowing_date = local_date(sowing_at, Atlantic/Canary)

light_at = sowing_at + germinazione_giorni
light_date = local_date(light_at, Atlantic/Canary)

hydration_at = sowing_at - idratazione_ore
hydration_date = local_date(hydration_at, Atlantic/Canary)
```

`sowing_date` è una DATE e non contiene ora. `sowing_at`, `harvest_target_at`, `light_at` e `hydration_at` sono timestamp timezone-aware in `Atlantic/Canary`, con precisione normativa al minuto; secondi e microsecondi sono zero nella rappresentazione canonica.

`sowing_at` deve inoltre corrispondere all'`orario_semina_previsto` della versione del protocollo. Se il calcolo a ritroso e tale orario non coincidono, i parametri sono incoerenti e producono `PRODUCTION_KNOWLEDGE_INVALID`; non è ammessa correzione automatica.

La combinazione degli orari locali usa le regole timezone reali della data. Un orario locale ambiguo o inesistente durante una transizione DST produce `PRODUCTION_KNOWLEDGE_INVALID`, senza normalizzazione automatica.

`idratazione_ore` è una durata non negativa, applicata una sola volta e sottratta da `sowing_at`; può attraversare il cambio data. Se è zero, un'attività separata non è richiesta. `buffer_temporale_minuti` è una durata separata, in minuti interi non negativi, precisione un minuto, mai float, applicata esattamente una volta e non inclusa nel ciclo nominale o nell'idratazione.

Tutti i calcoli usano `Atlantic/Canary`. Nessuna attività viene retrodatata.

La baseline legacy `data_semina = data_consegna - giorni_totali` coincide con V1 soltanto quando finestra e buffer approvati producono esattamente tale risultato.

## 9. Buffer temporale e quantitativo

Il buffer temporale:

- appartiene al protocollo e alla timeline versionata;
- è `buffer_temporale_minuti`, intero non negativo con precisione di un minuto;
- anticipa l'avvio rispetto al ciclo nominale;
- viene sottratto esattamente una volta da `sowing_at_nominale`;
- non comprende idratazione e non appartiene al ciclo nominale;
- non modifica la quantità.

Il buffer quantitativo:

- appartiene a una policy di produzione esplicita e versionata;
- si applica dopo il deficit e prima della granularità finale;
- non modifica le date salvo futura policy approvata.

Il legacy `+1 SET` non è una regola V1. In assenza di una policy quantitativa approvata, nessun buffer quantitativo viene inventato.

I soli tipi di policy quantitativa V1 sono:

```text
NONE
PERCENTAGE
ABSOLUTE_SET
```

Le formule sono:

```text
NONE:
    buffer_quantitativo = 0

PERCENTAGE:
    buffer_quantitativo = deficit × percentuale

ABSOLUTE_SET:
    buffer_quantitativo = quantita_set_esplicita

quantita_pre_granularita = deficit + buffer_quantitativo
quantita_da_produrre = ceil_to_granularity(quantita_pre_granularita)
```

Percentuale e quantità assoluta sono non negative. Il calcolo usa Decimal/numeric e precisione normativa; nessun arrotondamento intermedio riduce il risultato. L'arrotondamento finale verso l'alto appartiene esclusivamente alla granularità produttiva.

Ogni riga conserva tipo e versione della policy, input, buffer risultante, quantità pre-granularità e quantità finale. Una configurazione ambigua o incompleta produce `PRODUCTION_KNOWLEDGE_INVALID`.

## 10. Quantità e granularità

La quantità commerciale può essere frazionaria. Tutti i calcoli usano aritmetica decimale esatta; `float` non è ammesso.

```text
domanda_residua_commerciale
- copertura stock eleggibile
- copertura produzione in corso eleggibile
= domanda_residua_da_coprire / deficit
→ buffer quantitativo
→ arrotondamento alla granularità produttiva
→ quantità produttiva effettiva
→ conversione in risorse e seme
```

L'arrotondamento è verso l'alto al multiplo minimo della granularità approvata. Non è ammesso produrre meno del deficit comprensivo del buffer applicabile.

La quantità di seme usa `grammi_seme_per_set` sulla quantità produttiva effettiva. Le altre risorse derivano dalla stessa versione di ricetta/protocollo e conservano unità e precisione. Una granularità o conversione incoerente produce failure fail-closed.

## 11. Stock e produzione in corso

La formula normativa è:

```text
domanda_residua_commerciale
- stock eleggibile non allocato
- produzione in corso eleggibile non allocata
- quantità raccolta utile definitivamente allocata
= domanda_residua_da_coprire / deficit produttivo
```

`STOCK.disponibile` non è sufficiente. La disponibilità utilizzabile sottrae le allocazioni attive e verifica compatibilità, stato, quantità, unità e readiness.

Una SEMINA in corso è eleggibile soltanto se:

- non è chiusa o interrotta;
- usa cultivar, uso e protocollo compatibili;
- possiede resa residua prevista positiva;
- la finestra prevista è compatibile con la consegna;
- la resa non è già allocata integralmente;
- non è soggetta a un problema bloccante.

La copertura parziale è ammessa. Stock o resa prevista non possono coprire più domande oltre la quantità disponibile. Le allocazioni sono persistenti, versionate e transazionalmente protette.

### Lifecycle delle allocazioni

Il lifecycle si applica separatamente alle allocazioni DOMANDA, STOCK e PRODUZIONE_IN_CORSO. Gli stati normativi sono:

```text
ATTIVA
→ CONSUMATA
→ stato terminale

ATTIVA
→ RILASCIATA | SOSTITUITA | INVALIDA
```

- `ATTIVA`: creata esclusivamente nel commit autorevole della revisione; riduce la quantità ancora allocabile;
- `CONSUMATA`: quantità trasformata in SEMINA, raccolta o altrimenti consumata fisicamente e divenuta immutabile;
- `RILASCIATA`: quantità non consumata restituita alla disponibilità allocabile;
- `SOSTITUITA`: quantità non consumata trasferita o rimpiazzata da una revisione successiva con provenance esplicita;
- `INVALIDA`: sorgente non più eleggibile prima del consumo; richiede nuova valutazione e non può essere usata come copertura.

Transizioni ammesse:

```text
ATTIVA → CONSUMATA | RILASCIATA | SOSTITUITA | INVALIDA
```

Tutti gli stati diversi da `ATTIVA` sono terminali per quella registrazione. Sono vietate riattivazione, ritorno a uno stato precedente, cancellazione fisica ordinaria e rilascio di quantità `CONSUMATA`.

ANNULLAMENTO o SOSTITUZIONE di una parte non eseguita rilascia o trasferisce atomicamente soltanto la quantità non consumata. Quantità già trasformate in SEMINA, raccolte o consumate fisicamente non vengono liberate automaticamente.

Una revisione distingue per quantità:

- quota ATTIVA trasferibile;
- quota RILASCIABILE;
- quota CONSUMATA immutabile.

Ogni allocazione conserva sorgente tipizzata, domanda destinazione, quantità, unità, stato, provenance, versione e actor/timestamp di ogni transizione. Le coperture parziali sono preservate quantitativamente.

La semantica per tipo è:

- ALLOCAZIONE_DOMANDA: collega una quantità della domanda commerciale alla revisione; diventa CONSUMATA quando quella quantità è soddisfatta da raccolta utile definitivamente allocata; viene RILASCIATA o SOSTITUITA soltanto per la parte non soddisfatta;
- ALLOCAZIONE_STOCK: riserva stock eleggibile; diventa CONSUMATA quando un evento fisico autorevole utilizza o destina definitivamente la quantità; non modifica implicitamente STOCK e non sostituisce MOVIMENTI_MAGAZZINO;
- ALLOCAZIONE_PRODUZIONE_IN_CORSO: riserva una quota della resa prevista di una SEMINA; diventa CONSUMATA soltanto quando una RACCOLTA autorevole rende quella quota utile e definitivamente allocata; se la SEMINA non è più eleggibile prima del consumo diventa INVALIDA.

Per ogni risorsa, la somma delle allocazioni `ATTIVA` e `CONSUMATA` non può eccedere la quantità eleggibile. Il vincolo è verificato nel commit mediante lock e constraint; nessuna verifica preliminare lo sostituisce.

## 12. Priorità deterministica

Le domande concorrenti sono ordinate secondo:

1. data di consegna più vicina;
2. priorità commerciale esplicita, se presente;
3. public ID ORDINE;
4. posizione della riga ORDINE.

L'assenza della priorità commerciale non è errore. La priorità non dipende da PK interne, ordine di lettura o piano di esecuzione PostgreSQL.

## 13. Allarme Rosso

Resta valida la regola:

```text
DISPONIBILE < PRENOTATO
→ ALLARME ROSSO / PRIORITÀ ASSOLUTA
```

Production Planning la rende coerente con domanda residua, stock allocabile, produzione in corso allocabile, deficit e capacità di produrre entro la deadline. L'allarme non sostituisce il calcolo delle allocazioni e non autorizza fallback, correzioni o sovra-allocazioni.

## 14. Aggregate PIANO_SEMINE

PIANO_SEMINE è un aggregate PostgreSQL persistente, versionato, auditabile, con provenance e optimistic concurrency.

```text
PIANO_PRODUZIONE
└── RIGHE_PIANO_SEMINA
    ├── ALLOCAZIONI_DOMANDA
    └── ALLOCAZIONI_COPERTURA
```

PIANO_PRODUZIONE conserva almeno:

- public ID permanente;
- Planning RUN di origine;
- numero di revisione;
- versione della policy Planning;
- business timestamp;
- stato complessivo;
- riferimento alla revisione sostituita, quando presente;
- actor, timestamp, audit e optimistic version.

Ogni RIGA_PIANO_SEMINA conserva almeno:

- public ID permanente;
- piano e revisione;
- ORDINE e posizione/riga autorevole;
- domanda originaria e unità;
- varietà, cultivar e uso produttivo;
- versione del protocollo;
- copertura stock e copertura da produzione in corso;
- deficit, buffer, granularità e quantità produttiva effettiva;
- `quantita_produttiva_autorizzata`, `quantita_avviata` e `quantita_residua_da_avviare`;
- risorse calcolate, incluso il seme in grammi;
- idratazione, semina e luce previste;
- timezone, orari semina/raccolta usati e `buffer_temporale_minuti`;
- `harvest_target_at`, `sowing_at`, `light_at` e `hydration_at` canonici;
- inizio/fine finestra e target di raccolta;
- consegna richiesta e readiness prevista;
- stato, chiave idempotente, provenance e optimistic version.

Le ALLOCAZIONI_DOMANDA collegano quantitativamente il piano alla domanda. Le ALLOCAZIONI_COPERTURA collegano quantità determinate a stock o SEMINE in corso. Stock e SEMINE usano relazioni tipizzate distinte; non sono ammesse FK polimorfiche false.

La relazione RIGA_PIANO_SEMINA → SEMINA è 1:N. Ogni collegamento conserva la quantità effettivamente avviata. Per ogni riga:

```text
quantita_residua_da_avviare =
    quantita_produttiva_autorizzata - quantita_avviata

0 ≤ quantita_avviata ≤ quantita_produttiva_autorizzata
```

## 15. Lifecycle del piano

Gli stati V1 della riga piano sono:

```text
PIANIFICATA
→ PRONTA
→ AVVIATA
→ SODDISFATTA
```

Stati terminali o alternativi:

```text
ANNULLATA
SOSTITUITA
TARDIVA
```

- `PIANIFICATA`: calcolo persistito, non ancora autorizzato;
- `PRONTA`: validata e autorizzata all'esecuzione fisica;
- `AVVIATA`: almeno una SEMINA fisica è stata creata; può conservare quantità residua da avviare;
- `SODDISFATTA`: il fabbisogno produttivo è stato realmente ottenuto tramite RACCOLTE autorevoli e allocazioni definitive sufficienti;
- `ANNULLATA`: intenzione non eseguita annullata con motivazione;
- `SOSTITUITA`: revisione non eseguita superata da nuova revisione;
- `TARDIVA`: avvio teorico già trascorso e intervento richiesto.

Transizioni ammesse:

```text
PIANIFICATA → PRONTA | ANNULLATA | SOSTITUITA | TARDIVA
PRONTA      → AVVIATA | ANNULLATA | SOSTITUITA | TARDIVA
AVVIATA     → AVVIATA | SODDISFATTA
TARDIVA     → SOSTITUITA | ANNULLATA
```

I fatti storici e le quantità già avviate di una riga AVVIATA o SODDISFATTA non vengono riscritti, annullati o sostituiti retroattivamente. Gli ulteriori avvii aggiornano soltanto i contatori di avanzamento con optimistic concurrency e aggiungono nuovi collegamenti SEMINA immutabili. Le altre variazioni producono nuove entità e provenance.

`AVVIO_COMPLETATO` è un'invariante derivata, non un ulteriore stato pubblico:

```text
AVVIO_COMPLETATO ⇔ quantita_residua_da_avviare = 0
```

Non equivale a `SODDISFATTA`. Una riga può essere AVVIATA con avvio completato ma senza quantità raccolta utile sufficiente.

La condizione minima di soddisfacimento è:

```text
quantita_raccolta_utile_allocata
    ≥ quantita_produttiva_autorizzata
```

Le quantità devono essere convertite in unità coerenti mediante il protocollo applicato. La produzione deve essere realmente registrata in RACCOLTE, eleggibile, collegata alla riga piano/domanda e non allocata altrove.

Una raccolta parziale lascia la riga AVVIATA e conserva il residuo non soddisfatto. Resa inferiore o scarto rendono il deficit residuo pianificabile mediante nuova revisione, senza riscrivere SEMINE o RACCOLTE storiche. La CONSEGNA appartiene al lifecycle ORDINE e non determina direttamente `SODDISFATTA`.

## 16. Transizione alla SEMINA fisica

PIANO_SEMINE non equivale a SEMINA.

```text
riga piano PRONTA o AVVIATA con quantità residua
→ comando esplicito operatore
→ verifica expected version e precondizioni
→ selezione lotto di seme reale
→ registrazione quantità reale
→ allocazione SEMINA_ID
→ creazione SEMINA
→ collegamento piano-semina
→ incremento atomico quantita_avviata
→ ricalcolo quantita_residua_da_avviare
→ stato AVVIATA
→ audit
→ singolo commit atomico
```

Il primo avvio porta una riga PRONTA ad AVVIATA. Una riga AVVIATA può ricevere ulteriori avvii finché il residuo è positivo. Nessun singolo avvio e nessuna somma di avvii può superare il residuo o la quantità autorizzata.

Il Planning Engine non crea SEMINE automaticamente. La SEMINA conserva versione, snapshot del protocollo e quantità effettivamente avviata. Una SEMINA non può essere collegata due volte alla stessa riga piano.

## 17. CALENDARIO_PRODUZIONE

CALENDARIO_PRODUZIONE è una proiezione/read model rigenerabile derivata da:

- PIANO_SEMINE;
- SEMINE reali;
- RACCOLTE;
- CONSEGNE;
- PROBLEMI e alert rilevanti.

Non è un aggregate né un secondo writer business. Può essere materializzato per prestazioni, ma deve essere ricostruibile. Ogni evento indica origine, natura pianificata o reale, timestamp, stato e riferimenti pubblici.

## 18. Idempotenza e ripianificazione

L'idempotenza opera su due livelli.

### Request idempotency

La prima pianificazione usa la chiave canonica:

```text
planning_key_v1 = logical_hash(
    schema_version = "production-planning-v1",
    riga_ordine_public_id,
    quantita_domanda_residua_canonica,
    data_consegna,
    protocollo_versione_id,
    planning_policy_version
)
```

La forma canonica usa ordine dei campi fisso, UTF-8, date ISO 8601 e quantità Decimal normalizzata senza notazione esponenziale, separatore locale o zeri finali non significativi. L'algoritmo fisico di hash appartiene al Physical Schema Freeze, ma non può cambiare la stringa logica canonica V1.

Non sono inclusi request UUID, correlation ID, timestamp della RUN, ordine di query o PK occasionali. Una nuova RUN con gli stessi input logici produce la stessa chiave.

La ripianificazione usa:

```text
replanning_key_v1 = logical_hash(
    schema_version = "production-replanning-v1",
    previous_plan_revision_public_id,
    order_line_public_id,
    replanning_reason_code,
    canonical_authoritative_snapshot,
    planning_policy_version
)
```

I codici reason V1 sono esclusivamente:

```text
DEMAND_CHANGED
DELIVERY_CHANGED
STOCK_CHANGED
IN_PROGRESS_CHANGED
HARVEST_RESULT_CHANGED
PROTOCOL_CHANGED
PLAN_LATE
MANUAL_REPLAN_AUTHORIZED
```

Testo libero e note operatore restano provenance diagnostica e non entrano nella chiave.

`canonical_authoritative_snapshot` contiene esattamente, nel seguente ordine:

1. `order_line_public_id`;
2. `order_public_id`;
3. `order_state`;
4. `ordered_quantity`;
5. `delivered_quantity`;
6. `commercial_residual_quantity`;
7. `delivery_date`;
8. `variety_public_id`;
9. `protocol_version_public_id`;
10. `protocol_version_number`;
11. `protocol_valid_from`;
12. `protocol_valid_to` oppure NULL;
13. `planning_policy_version`;
14. `quantitative_buffer_policy_type`;
15. `quantitative_buffer_policy_value` oppure NULL per NONE;
16. `temporal_buffer_minutes`;
17. `production_granularity`;
18. `eligible_stock_snapshot`;
19. `eligible_in_progress_snapshot`;
20. `existing_active_allocations_snapshot`;
21. `previous_plan_revision_public_id`;
22. `previous_plan_revision_version`.

`eligible_stock_snapshot` è ordinato per `stock_resource_public_id` crescente. Ogni elemento contiene, in ordine: identità stabile autorevole della risorsa, `variety_public_id`, quantità eleggibile, quantità già allocata, residuo allocabile, versione della risorsa e discriminatore canonico di readiness/eleggibilità. Se STOCK non possiede public ID, il Physical Schema deve definire un'identità stabile autorevole; non sono ammessi ordine query o PK occasionale prive di contratto.

`eligible_in_progress_snapshot` è ordinato per `semina_public_id` crescente. Ogni elemento contiene, in ordine: `semina_public_id`, `variety_public_id`, `protocol_version_public_id`, quantità utile prevista, quantità già allocata, residuo allocabile, inizio e fine finestra prevista di raccolta, stato e versione della SEMINA.

`existing_active_allocations_snapshot` include esclusivamente allocazioni materialmente rilevanti ed è ordinato per `allocation_public_id` crescente. Ogni elemento contiene, in ordine: `allocation_public_id`, tipo, `source_public_id`, `destination_order_line_public_id`, quantità allocata, stato e versione.

La rappresentazione canonica V1 usa:

- Decimal base 10 in plain string, senza notazione scientifica, punto finale o trailing zero inutili: `1.000` → `1`, `0.500` → `0.5`, `12.3400` → `12.34`, zero → `0`;
- date `YYYY-MM-DD`;
- local time `HH:MM`;
- timestamp ISO 8601 timezone-aware con offset effettivo Atlantic/Canary e precisione al minuto;
- NULL come token canonico esplicito `NULL`;
- enum e codici con valore normativo esatto;
- liste nell'ordine esplicitamente congelato;
- mappe nell'ordine dei campi del presente contratto.

Non entrano nella chiave: timestamp della Planning RUN, actor, correlation ID, messaggi, warning, note libere, hostname, provider, connection information, PK interne non normative, ordine accidentale delle query o dati diagnostici non autorevoli.

Due richieste con stessa revisione precedente, riga ORDINE, reason code, snapshot canonico e planning policy version producono la stessa `replanning_key_v1`, indipendentemente da RUN, timestamp, caller, correlation ID o provider. Se cambia materialmente almeno un input incluso, la chiave cambia. Una nuova RUN con la stessa chiave non crea una revisione duplicata.

Ogni revisione possiede nuova identità permanente e conserva il riferimento alla precedente. Domanda, delivery, protocollo, policy, stock eleggibile, produzione eleggibile, allocazioni attive, versione precedente e reason code modificano l'identità; actor, note, messaggi, warning, timestamp RUN, durata e provider restano diagnostica.

### Database uniqueness

Constraint PostgreSQL impediscono:

- più risultati correnti per la stessa richiesta;
- allocazioni oltre domanda o disponibilità;
- due revisioni correnti dello stesso piano;
- duplicazione del collegamento piano-semina;
- duplicazione delle identità pubbliche.

La ripetizione restituisce il risultato già noto o una riconciliazione certa. La ripianificazione crea una revisione, conserva la precedente e sostituisce soltanto parti non eseguite. Nessun retry cieco è ammesso su conflitti CAS, versione o unicità.

## 19. Concurrency

Il commit protegge almeno:

- righe ORDINE interessate;
- righe STOCK interessate;
- SEMINE in corso candidate;
- piani e revisioni correnti;
- allocazioni;
- sequenze Identity;
- versione attesa della Planning RUN.

I lock sono acquisiti in ordine deterministico e mantenuti per una transazione breve. Nessun I/O esterno avviene mentre sono detenuti. V1 non usa advisory lock globale. Un conflitto produce rollback completo e failure/reconciliation provider-neutral, senza retry automatico.

## 20. Atomicità e writer authority

Scheduling e Production Planning non condividono una transazione.

Il flusso Planning è:

1. apertura Planning RUN;
2. lettura e calcolo;
3. preparazione e validazione;
4. singolo commit PostgreSQL autorevole.

Il commit comprende atomicamente:

- verifiche definitive e lock;
- allocazioni domanda/copertura;
- piano e revisione;
- righe piano e risorse;
- audit e messaggi;
- conclusione versionata della Planning RUN.

Il Production Planning Commit Repository è l'unico writer autorevole del piano. Non modifica ORDINI, SEMINE, RACCOLTE, CONSEGNE o MOVIMENTI_MAGAZZINO. Una failure certa causa rollback completo. Non sono ammesse persistenze parziali, compensazioni automatiche o dual-write.

Se una failure certa avviene dopo l'apertura ma prima del commit del piano, la failure-finalization definita al §4 usa una transazione distinta. Se l'esito fisico del commit autorevole non è determinabile con certezza, non viene tentata failure-finalization deduttiva: la RUN assume esclusivamente `RECONCILIATION_REQUIRED` mediante evidenza e procedura di riconciliazione.

## 21. Failure boundary

Le categorie provider-neutral V1 sono:

| Categoria | Condizioni minime | Persistenza e RUN | Nuova richiesta/intervento |
|---|---|---|---|
| `PLANNING_INPUT_INVALID` | ORDINE non eleggibile; quantità, unità o input incoerenti | rollback; RUN `FAILED`; errore ordinato | nuova richiesta soltanto dopo correzione input |
| `PRODUCTION_KNOWLEDGE_INVALID` | protocollo assente, ambiguo, incompleto, non approvato o fuori validità | rollback; RUN `FAILED`; errore ordinato | nuova richiesta dopo commissioning/approvazione conoscenza |
| `PLANNING_INFEASIBLE` | deadline impossibile; granularità senza copertura possibile; risorse/capacità insufficienti entro deadline | rollback; RUN `FAILED`; errore e alert | intervento operatore o nuova richiesta con condizioni mutate |
| `ALLOCATION_CONFLICT` | stock o produzione concorrente cambiata o già allocata | rollback; RUN `FAILED`; conflitto persistito | nuova richiesta esplicita ammessa; nessun retry automatico |
| `CONCURRENCY_CONFLICT` | ORDINE, piano, expected version o domanda residua cambiati | rollback; RUN `FAILED`; conflitto persistito | nuova richiesta esplicita su snapshot aggiornato |
| `COMMIT_FAILED_ROLLED_BACK` | errore PostgreSQL con rollback certo prima di commit confermato | nessun piano parziale; failure-finalization a `FAILED` | intervento tecnico o nuova richiesta esplicita |
| `RECONCILIATION_REQUIRED` | outcome fisico del commit incerto | nessuna dichiarazione deduttiva di rollback/successo; RUN omonima | riconciliazione manuale/operativa obbligatoria |
| `INTERNAL_ERROR` | esclusivamente bug o programming defect non classificato | rollback se certo; RUN `FAILED` quando finalizzabile | review tecnica obbligatoria |

Le failure note non vengono convertite in `INTERNAL_ERROR`. Ogni categoria conserva errori provider-neutral ordinati, warning, audit e contesto non sensibile sufficiente alla diagnosi.

Un ORDINE committed non viene annullato o modificato perché Planning fallisce. I messaggi non espongono dati sensibili. Nessun dato mancante diventa `DA CONFERMARE` dentro un commit autorevole.

## 22. Piano tardivo e readiness

Se semina o idratazione teorica precedono il business timestamp della Planning RUN:

- nessuna attività viene retrodatata;
- nessuna SEMINA viene simulata;
- la riga assume stato TARDIVA;
- viene prodotto un alert esplicito;
- è richiesto intervento operatore;
- nessun fallback temporale viene applicato.

La readiness prevista richiede congiuntamente:

- quantità allocata o pianificata sufficiente;
- raccolta prevista dentro la finestra approvata;
- nessun problema bloccante noto;
- nessuna attività critica già tardiva;
- compatibilità con la consegna.

La readiness prevista non equivale a una RACCOLTA reale e non garantisce automaticamente la CONSEGNA.

## 23. Persistenza PostgreSQL concettuale

Il modello fisico V1 deve prevedere almeno:

- struttura produttiva versionata del PROTOCOLLO;
- Production Planning RUN e relativi messaggi/log;
- PIANI_PRODUZIONE;
- RIGHE_PIANO_SEMINA;
- ALLOCAZIONI_DOMANDA;
- allocazioni tipizzate di STOCK;
- allocazioni tipizzate di SEMINE in corso;
- risorse pianificate;
- collegamento tipizzato piano-semina;
- audit;
- read model CALENDARIO_PRODUZIONE.

Nomi fisici, colonne e indici definitivi appartengono al successivo Physical Schema Freeze. Esso deve preservare FK reali, quantità positive, unità e date coerenti, unicità idempotente, una sola revisione corrente, optimistic version, allocazioni entro domanda/disponibilità, versioni append-only, delete RESTRICT e identificativi pubblici tramite Identity persistente.

## 24. Legacy boundary

Dal legacy vengono preservati:

- backplanning specifico per ciclo;
- fail-closed sui dati mancanti;
- idratazione, germinazione e passaggio a luce;
- conversione SET → seme/risorse;
- valutazione della produzione in corso;
- preview verificabile;
- calendario cronologico.

Vengono eliminati:

- Google come authority;
- nomi liberi come identità;
- aritmetica `float`;
- buffer universale `+1 SET`;
- raccolta automaticamente uguale alla consegna;
- piano senza ID, versione e lifecycle;
- calendario come seconda verità;
- Write Plan legacy;
- fallback e `DA CONFERMARE` nei commit autorevoli.

Il legacy è evidenza funzionale e baseline di test, non dipendenza runtime.

## 25. Acceptance scenario obbligatorio

```text
CLIENTE: La Jaira
DATA_CONSEGNA: 2026-08-15
RICORRENZA COMMERCIALE: QUINDICINALE

1 SET   Guisante Afila
0.5 SET Rábano Morado
0.5 SET Cilantro
```

Una volta commissionate le versioni approvate dei tre protocolli, il sistema deve determinare separatamente:

- domanda originaria e residua;
- stock eleggibile e copertura assegnata;
- produzione in corso eleggibile e copertura assegnata;
- deficit, buffer, granularità e quantità produttiva;
- grammi di seme e altre risorse;
- `harvest_target_at`, `sowing_at`, `sowing_date`, `light_at` e `hydration_at` senza orari impliciti;
- idratazione, semina e passaggio a luce;
- finestra e target di raccolta;
- readiness prevista e riferimento alla consegna.

Il caso deve inoltre poter rappresentare coperture parziali, più SEMINE per la stessa riga piano, lifecycle quantitativo delle allocazioni, RACCOLTE parziali, resa insufficiente e conseguente ripianificazione storicizzata.

Una ripianificazione `STOCK_CHANGED` deve produrre una chiave deterministica dal nuovo snapshot canonico e non deve duplicare la revisione se rieseguita con gli stessi input logici.

Il caso deve dimostrare protocolli, buffer, durate, granularità e quantità di seme differenti. Il Freeze non assegna valori reali: il loro inserimento richiede commissioning esplicito, provenance, approvazione e postcheck.

## 26. Obblighi di test

L'implementazione deve coprire almeno:

- protocolli approvati, assenti, incompleti, incoerenti e fuori validità;
- cicli differenti nella stessa consegna;
- quantità frazionarie e arrotondamento conservativo;
- buffer temporale e quantitativo distinti;
- copertura nulla, parziale e completa da stock e produzione in corso;
- impossibilità di doppia allocazione;
- lifecycle ATTIVA/CONSUMATA/RILASCIATA/SOSTITUITA/INVALIDA per ogni tipo di allocazione;
- rilascio esclusivo delle quote non consumate;
- ordine deterministico delle priorità;
- finestra e target di raccolta;
- piano tardivo;
- idempotenza e ripianificazione storicizzata;
- optimistic concurrency e lock PostgreSQL reali;
- collisione, rollback atomico e riconciliazione;
- transizione operatore a SEMINA;
- più SEMINE e avvii parziali per la stessa riga piano;
- vincoli sulle quantità autorizzata, avviata e residua;
- distinzione AVVIO_COMPLETATO/SODDISFATTA e RACCOLTE parziali;
- immutabilità delle parti AVVIATE;
- calendario rigenerabile;
- assenza di writer/dipendenze Google;
- scenario La Jaira.

## 27. Esclusioni V1

Restano fuori dal Freeze:

- valori produttivi reali;
- avvio automatico delle SEMINE;
- protocolli sperimentali nel runtime ordinario;
- ottimizzazione globale della capacità;
- previsione automatica della resa;
- advisory lock globale;
- retry automatici;
- dual-write o sincronizzazione Google;
- dettagli fisici definitivi di schema e indici;
- UI e workflow operatore;
- modifica automatica di ORDINI, RACCOLTE o CONSEGNE.

Qualunque introduzione richiede Architecture Review.

## 28. Decisioni congelate dal draft

1. Production Planning è separato dallo Scheduling.
2. Opera su ORDINI PostgreSQL committed.
3. Usa una Planning RUN dedicata.
4. La conoscenza produttiva è versionata per CULTIVAR × USO PRODUTTIVO.
5. Il backplanning è specifico per riga e protocollo.
6. La raccolta precede la consegna dentro la finestra approvata.
7. V1 sceglie deterministicamente l'inizio conservativo della finestra.
8. Buffer temporale e quantitativo sono separati e versionati.
9. Le quantità sono arrotondate verso l'alto alla granularità fisica.
10. Stock e produzione in corso richiedono allocazioni persistenti.
11. La priorità è deterministica.
12. PIANO_SEMINE è persistente, versionato e auditabile.
13. PIANO_SEMINE non equivale a SEMINA.
14. CALENDARIO_PRODUZIONE è una proiezione rigenerabile.
15. Request idempotency e database uniqueness sono obbligatorie.
16. La ripianificazione crea una revisione e non riscrive la storia.
17. Il commit Planning è unico, PostgreSQL e separato dal commit Scheduling.
18. Il motore è fail-closed e non retrodata attività.
19. Google e il Write Plan legacy sono esclusi dal runtime autorevole.
20. Nessun valore produttivo reale è congelato in questo documento.
