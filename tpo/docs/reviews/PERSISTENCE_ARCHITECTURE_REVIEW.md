# PERSISTENCE ARCHITECTURE REVIEW

**Stato:** ARCHITECTURE DECISION PROPOSED v1.0

## 1. Executive Summary

Il Tower Power Operations presenta un modello prevalentemente e fortemente relazionale, con componenti documentali circoscritti e viste tabellari operative. Le relazioni tra CLIENTI, PROGRAMMI_FORNITURA, ORDINI e CONSEGNE e tra VARIETÀ, SEMINE, RACCOLTE, MOVIMENTI_MAGAZZINO e STOCK richiedono integrità referenziale, vincoli univoci, transazioni, concorrenza controllata e storico verificabile.

La decisione proposta è:

**SUPABASE / POSTGRESQL**

PostgreSQL diventa la persistenza autorevole del Tower Power OS. Supabase è il provider gestito consigliato oggi per la combinazione di database PostgreSQL, strumenti operativi, dashboard, API, autenticazione, Row Level Security e possibile supporto alle future applicazioni.

Il Domain e le porte applicative non devono dipendere da Supabase. La dipendenza infrastrutturale deve essere esclusivamente da PostgreSQL e da adapter sostituibili. In futuro deve quindi essere possibile migrare a Neon, a un altro PostgreSQL gestito o a PostgreSQL self-managed senza modificare il Domain.

Google Sheets non viene eliminato. Il suo ruolo proposto diventa quello di vista operativa, export, report e interfaccia secondaria rigenerabile. Non deve più essere la sorgente autorevole dei Register né delle sequenze identificative.

La proposta non autorizza ancora la produzione. Autorizza esclusivamente la progettazione e la sperimentazione in un ambiente PostgreSQL sandbox separato.

## 2. Stato attuale

La baseline analizzata è il commit `f0dae84c84b8f6c838f12e7df502f32b2fb2bfd4`.

Al momento della review:

- la working tree è pulita;
- la suite Core contiene 723 test superati;
- Domain, Application, Infrastructure, Bootstrap e CLI sono separati;
- il Domain utilizza identificativi permanenti tipizzati e Value Object immutabili;
- lo Scheduling Engine produce ORDINI deterministici e chiavi idempotenti;
- Identity definisce una porta `IdentifierSequenceRepository` con compare-and-set;
- Run Tracking definisce il ciclo persistente della RUN;
- WritePlan e ValidatedWritePlan separano proposta e validazione;
- ApplicationCommitter separa preparazione, commit e riconciliazione;
- gli adapter correnti persistono PROGRAMMI_FORNITURA e ORDINI in Google Sheets;
- il Google Sheets Commit Adapter applica un append singolo e una riconciliazione successiva;
- la scrittura produttiva non è autorizzata.

La Milestone Review 1 autorizza soltanto controlled write in sandbox, con un solo operatore, una sola istanza e nessuna concorrenza. Restano blocker per la produzione la persistenza concorrente degli ID, la tracciabilità persistente della RUN, la protezione concorrente dell’idempotenza, la gestione completa degli esiti incerti e l’isolamento dei writer legacy.

Google Sheets rappresenta l’implementazione corrente della persistenza, ma i principi documentali esistenti dichiarano già che l’architettura concettuale non dipende dalla tecnologia fisica.

## 3. Requisiti

La persistenza autorevole deve supportare:

1. transazioni ACID;
2. allocazione concorrente e non riutilizzabile di RunId e OrdineId;
3. unique constraint sulle identità e sulle chiavi idempotenti;
4. foreign key coerenti con i riferimenti permanenti;
5. check constraint per quantità, stati e invarianti fisiche applicabili;
6. optimistic concurrency e locking quando necessari;
7. conservazione dello storico e audit trail;
8. commit coordinato di RUN, ORDINI e relativi metadati;
9. riconciliazione deterministica degli esiti;
10. migrazioni versionate dello schema;
11. backup, ripristino e ambienti separati;
12. accesso Python maturo;
13. consultazione manuale sicura;
14. dashboard e viste future;
15. credenziali non versionate e privilegi minimi;
16. portabilità del Core rispetto al provider;
17. comportamento esplicito in caso di rete assente o instabile.

Nessuna soluzione cloud valutata garantisce operatività autorevole offline. In assenza di rete, il sistema deve interrompere le scritture autorevoli, conservare localmente soltanto artefatti non committati quando previsto e riprendere tramite un flusso esplicito di nuova validazione. Non deve simulare un commit riuscito.

## 4. Modello dati

### 4.1 Relazioni principali

```text
CLIENTE
└── PROGRAMMA_FORNITURA
    └── ORDINE
        └── CONSEGNA
```

La relazione tra ORDINI e CONSEGNE è molti-a-molti: un ORDINE può essere soddisfatto da più CONSEGNE e una CONSEGNA può soddisfare più ORDINI.

```text
VARIETÀ
└── SEMINA
    └── RACCOLTA
        └── MOVIMENTO_MAGAZZINO
            └── STOCK
```

STOCK rappresenta lo stato corrente, mentre MOVIMENTI_MAGAZZINO costituisce lo storico ufficiale delle variazioni. La separazione richiede transazioni capaci di registrare l’evento e aggiornare coerentemente la proiezione corrente.

### 4.2 Componenti trasversali

- RUN conserva tracciabilità, tempi, errori ed esito dell’esecuzione.
- Le sequenze identificative richiedono aggiornamenti concorrenti atomici.
- WritePlan rappresenta la proposta applicativa immutabile.
- Le idempotency key devono essere univoche nel confine corretto.
- Commit e riconciliazione devono produrre prove persistenti e verificabili.
- L’audit trail deve preservare fatti storici senza sovrascrittura distruttiva.

### 4.3 Classificazione

Il modello TPO è:

- **fortemente relazionale** nel nucleo autorevole;
- **documentale** soltanto per payload variabili, snapshot semantici, log strutturati o metadati evolutivi;
- **tabellare** nelle viste operative e nei report;
- **ibrido** nel sistema complessivo, non nella sorgente autorevole primaria.

PostgreSQL consente di mantenere relazionale il nucleo e utilizzare JSONB soltanto dove la variabilità è realmente parte del modello, senza trasformare gli aggregati principali in documenti duplicati.

## 5. Opzioni analizzate

### 5.1 Supabase / PostgreSQL

Supabase fornisce un PostgreSQL gestito con dashboard, Table Editor, SQL Editor, API, autenticazione, storage e strumenti per applicazioni future. PostgreSQL offre transazioni ACID, sequence, primary key, unique constraint, foreign key, check constraint, indici, viste, trigger, locking e JSONB.

Punti di forza:

- corrispondenza diretta con il modello relazionale;
- transazioni multi-tabella per Identity, RUN, ORDINI, MOVIMENTI e STOCK;
- vincoli verificati dal database;
- idempotenza tramite unique constraint;
- allocazione ID mediante sequence o riga di sequenza bloccata transazionalmente;
- dashboard accessibile per l’operatività quotidiana;
- Row Level Security per una difesa aggiuntiva;
- API e autenticazione disponibili per future interfacce;
- migrazioni SQL standard e portabili;
- accesso Python tramite driver PostgreSQL e ORM opzionali.

Punti di attenzione:

- i servizi aggiuntivi aumentano la superficie operativa rispetto a un provider database-only;
- RLS e API non devono sostituire la separazione applicativa già esistente;
- il service role non deve essere esposto ai client;
- il Table Editor deve essere governato per impedire modifiche manuali ai Facts immutabili;
- branching e PITR possono aumentare i costi.

Supabase indica attualmente un piano Pro da 25 USD/mese, con un primo progetto incluso, backup giornalieri conservati sette giorni e costi aggiuntivi per PITR. I prezzi devono essere ricontrollati prima dell’attivazione. Fonti: [Supabase Pricing](https://supabase.com/pricing), [Supabase PITR](https://supabase.com/docs/guides/platform/manage-your-usage/point-in-time-recovery), [Supabase Branching](https://supabase.com/docs/guides/deployment/branching), [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

### 5.2 Neon / PostgreSQL

Neon fornisce PostgreSQL serverless con autoscaling, scale-to-zero, branching, restore temporale, read replica e connection pooling.

Punti di forza:

- stessa adeguatezza relazionale e transazionale di PostgreSQL;
- ottima portabilità SQL;
- branching naturale per sandbox, test e migrazioni;
- costi favorevoli per carichi intermittenti;
- scale-to-zero per ambienti non sempre attivi;
- approccio database-first semplice;
- separazione netta tra database e applicazione.

Punti di attenzione:

- esperienza quotidiana meno completa per un operatore non tecnico rispetto all’insieme dashboard/Table Editor/API/Auth di Supabase;
- autenticazione applicativa, storage e API richiedono componenti ulteriori se diventeranno necessari;
- il risveglio da scale-to-zero introduce una latenza iniziale;
- funzionalità di rete e compliance avanzate dipendono dal piano;
- l’operatività deve essere costruita maggiormente attorno a strumenti SQL e applicazioni dedicate.

Neon pubblica un piano gratuito e piani usage-based; il piano Launch riporta attualmente 0,106 USD per CU-hour e 0,35 USD per GB-mese, con branching e restore window dipendenti dal piano. I prezzi devono essere ricontrollati prima dell’attivazione. Fonti: [Neon Pricing](https://neon.com/pricing), [Neon Scale to Zero](https://neon.com/docs/introduction/scale-to-zero), [Neon Compute](https://neon.com/docs/manage/endpoints/).

Neon è la migliore alternativa a Supabase e può risultare preferibile se Tower Power sceglierà un’impostazione strettamente database-first, con dashboard applicative costruite separatamente.

### 5.3 Cloud Firestore

Firestore è un database documentale gestito con transazioni, batched writes, scalabilità automatica, Security Rules, backup e Point-in-Time Recovery.

Punti di forza:

- transazioni adatte a contatori e sequenze concorrenti;
- scalabilità e gestione operativa ridotta;
- integrazione con l’ecosistema Google;
- modello efficace per documenti autonomi e accessi per chiave;
- costi iniziali potenzialmente bassi per volumi ridotti.

Punti di attenzione:

- assenza di join relazionali e foreign key native;
- duplicazione necessaria per molte query operative;
- integrità referenziale affidata all’applicazione;
- query trasversali e audit relazionale più complessi;
- cardinalità molti-a-molti e aggregati con righe richiedono collezioni e indici duplicati;
- costi dipendenti da letture, scritture, cancellazioni, indici, storage e rete;
- evoluzione del modello più onerosa quando cambiano proiezioni duplicate;
- minore corrispondenza con il Core e con i Register approvati.

Firestore risolve bene il singolo problema delle sequenze, ma non è la scelta migliore per l’intera persistenza TPO. Sceglierlo soltanto per Identity introdurrebbe due fonti tecnologiche autorevoli e una transazione distribuita tra Identity e ORDINI. Sceglierlo per tutto il sistema imporrebbe una trasformazione documentale non giustificata dal dominio.

Firestore ritenta automaticamente una transazione quando un documento letto viene modificato concorrentemente. La tariffazione è basata principalmente su operazioni e storage; backup e PITR richiedono billing. Fonti: [Firestore Transactions](https://firebase.google.com/docs/firestore/manage-data/transactions), [Firestore Pricing](https://firebase.google.com/docs/firestore/pricing).

### 5.4 Google Sheets come database autorevole

Punti di forza:

- familiarità e accesso manuale immediato;
- ottima UX per visualizzazione, filtri e correzioni controllate;
- basso costo iniziale;
- condivisione semplice;
- infrastruttura e adapter già parzialmente implementati;
- utile per volumi ridotti e processi manuali non concorrenti.

Punti di attenzione:

- nessun vero compare-and-set tra lettura e scrittura;
- nessuna foreign key o unique constraint autorevole;
- schema fisico modificabile manualmente;
- nessuna transazione coordinata tra Register;
- rischio di modifiche manuali ai Facts storici;
- idempotenza concorrente non garantita;
- riconciliazione necessaria dopo append con esito incerto;
- query relazionali e migrazioni fragili;
- performance legata a scansioni e quote API;
- backup e rollback non equivalenti a un database transazionale.

Le batch request di Sheets sono atomiche internamente, ma non rendono atomico un precedente read con il successivo update. Le quote ufficiali sono per minuto e l’API può restituire timeout o `429`. Fonte: [Google Sheets API Usage Limits](https://developers.google.com/workspace/sheets/api/limits), [Google Sheets batchUpdate](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate).

Google Sheets non è adeguato come persistenza autorevole del TPO in produzione concorrente.

### 5.5 Google Sheets come vista operativa secondaria

Google Sheets rimane molto adatto come:

- vista operativa leggibile dagli utenti;
- export controllato;
- report e dashboard leggere;
- superficie di consultazione;
- input amministrativo sottoposto a importazione e validazione esplicita, quando autorizzato;
- strumento temporaneo di confronto durante la migrazione.

I fogli derivati devono essere rigenerabili dal database e chiaramente marcati come non autorevoli. Le modifiche manuali non devono essere sincronizzate implicitamente verso PostgreSQL. Qualunque import deve essere un caso d’uso esplicito, validato e auditato.

## 6. Matrice comparativa

Scala: 1 = insufficiente, 3 = adeguato con compromessi, 5 = molto adatto.

| Criterio | Supabase / PostgreSQL | Neon / PostgreSQL | Firestore | Google Sheets autorevole |
|---|---:|---:|---:|---:|
| Affidabilità | 5 | 5 | 5 | 3 |
| Semplicità | 5 | 4 | 3 | 5 |
| Modello dati | 5 | 5 | 3 | 2 |
| Transazioni | 5 | 5 | 4 | 2 |
| Concorrenza | 5 | 5 | 5 | 2 |
| UX quotidiana | 5 | 3 | 3 | 5 |
| Costi | 3 | 5 | 4 | 5 |
| Manutenibilità | 5 | 5 | 3 | 2 |
| Scalabilità | 5 | 5 | 5 | 2 |
| Compatibilità col codice esistente | 4 | 4 | 3 | 5 |
| **Totale / 50** | **47** | **46** | **38** | **33** |

La differenza tra Supabase e Neon è limitata e non riguarda PostgreSQL. Supabase prevale oggi per l’operatività complessiva e per gli strumenti utilizzabili nelle future applicazioni. Neon prevale sul costo elastico e sul branching database-first.

Il punteggio elevato di compatibilità attribuito a Google Sheets misura soltanto il riuso degli adapter già presenti, non l’adeguatezza alla produzione. I blocker di concorrenza e integrità hanno peso architetturale superiore al vantaggio di riuso infrastrutturale.

## 7. Rischi

### 7.1 Rischi della decisione PostgreSQL/Supabase

- Migrazione incompleta o incoerente dai fogli.
- Doppia autorità temporanea tra PostgreSQL e Google Sheets.
- Uso improprio del Table Editor sui Facts immutabili.
- Accoppiamento accidentale del Core alle API Supabase.
- Migrazioni SQL non versionate o applicate manualmente.
- Credenziali privilegiate esposte nella CLI o nel repository.
- Costi non monitorati per ambienti, backup, PITR, egress o branching.
- Eccessivo uso di trigger o RLS con logica di dominio duplicata.
- Dual-write non atomico tra PostgreSQL e Google Sheets.

Mitigazioni:

- un solo writer autorevole PostgreSQL;
- adapter PostgreSQL dietro le porte esistenti;
- migrazioni SQL versionate e revisionate;
- ruoli separati per runtime, migrazione, reporting e operatore;
- Google Sheets alimentato in modo asincrono e rigenerabile;
- nessun dual-write sincrono nel commit autorevole;
- audit delle operazioni amministrative;
- backup e restore provati periodicamente;
- metriche e limiti di spesa configurati.

### 7.2 Rischi di migrazione

- perdita di ordine delle righe durante la normalizzazione;
- riferimenti mancanti nei dati storici;
- duplicati oggi tollerati dai fogli ma vietati dai nuovi vincoli;
- differenze tra stato corrente e storico degli eventi;
- chiavi idempotenti duplicate;
- writer legacy ancora attivi durante il cutover;
- rollback che riattiva una copia Google Sheets non più aggiornata.

Ogni import deve produrre un report di riconciliazione e non deve correggere automaticamente ambiguità semantiche.

## 8. Compatibilità con il Core

### 8.1 Componenti che rimangono invariati

- Domain;
- Value Object e identificativi permanenti;
- Scheduling Engine;
- Application Services;
- Repository Ports;
- Identity e `PersistentIdAllocator`;
- Run Tracking;
- WritePlan e ValidatedWritePlan;
- protocollo ApplicationCommitter;
- regole di idempotenza;
- CLI come confine applicativo, salvo composizione e opzioni di configurazione.

### 8.2 Componenti da sostituire o affiancare

- nuovi repository PostgreSQL per PROGRAMMI_FORNITURA e ORDINI;
- adapter PostgreSQL per Identity e RUN;
- committer PostgreSQL transazionale;
- bootstrap e settings per il datasource PostgreSQL;
- CLI runtime per selezione ambiente e modalità;
- schema fisico PostgreSQL e migrazioni;
- pipeline di importazione e riconciliazione;
- adapter di reporting Google Sheets;
- isolamento o rimozione dei writer Google Sheets legacy.

### 8.3 Quantificazione del riuso

La baseline comprende approssimativamente:

- Domain: 15 file Python, 951 righe;
- Application: 28 file Python, 1.846 righe;
- Infrastructure Google Sheets: 8 file Python, 835 righe;
- Bootstrap: 4 file Python, 184 righe;
- CLI: 4 file Python, 486 righe.

Le 2.797 righe di Domain e Application sono riutilizzabili quasi integralmente. La maggior parte del lavoro nuovo è concentrata nell’Infrastructure, nello schema, nel bootstrap, nella migrazione e nei test di integrazione. In termini di logica Core, si stima riutilizzabile circa l’80–85%; la stima non comprende migrazioni SQL, tooling operativo e migrazione dati, che costituiscono lavoro nuovo significativo.

## 9. Strategia di migrazione

La migrazione deve essere incrementale e reversibile per fasi.

### Fase 1 — Sandbox PostgreSQL

- creare un progetto Supabase esclusivamente sandbox;
- definire ruoli, networking e gestione segreti;
- introdurre migrazioni versionate;
- vietare dati reali fino all’approvazione.

Rollback: eliminazione del progetto sandbox senza impatto sui fogli correnti.

### Fase 2 — Identity e RUN

- implementare sequenze o contatori transazionali;
- persistere RUN, log, warning, errori ed esiti;
- verificare concorrenza con doppie esecuzioni controllate.

Rollback: disabilitare il nuovo runtime; nessuna scrittura ORDINI autorizzata.

### Fase 3 — PROGRAMMI_FORNITURA e ORDINI

- normalizzare testate e righe;
- applicare foreign key, unique e check constraint;
- implementare repository PostgreSQL;
- confrontare output con gli adapter Google in sola lettura.

Rollback: mantenere Google Sheets come fonte corrente fino al cutover formale.

### Fase 4 — Commit PostgreSQL

- registrare RUN, ORDINI, righe e chiavi idempotenti in una sola transazione;
- eliminare la necessità di riconciliazione dell’append come condizione ordinaria;
- mantenere ricevute applicative e audit.

Rollback: nessun cutover produttivo prima della riuscita dei test end-to-end.

### Fase 5 — Import e confronto

- esportare i dati Google Sheets;
- validare duplicati, riferimenti e formati;
- importare nella sandbox;
- confrontare conteggi, aggregati e chiavi;
- produrre report di scarto senza correzioni implicite.

Rollback: ricreare la sandbox e ripetere l’import dalla stessa baseline congelata.

### Fase 6 — Cutover controllato

- bloccare i writer legacy;
- eseguire import finale;
- dichiarare PostgreSQL unica fonte autorevole;
- attivare Google Sheets soltanto come reporting;
- eseguire una prima RUN manuale controllata.

Rollback: consentito soltanto mediante una procedura approvata che consideri tutte le transazioni avvenute dopo il cutover. Non è ammesso riattivare semplicemente un foglio obsoleto.

## 10. Impatto sugli adapter Google

Gli adapter correnti non vengono eliminati immediatamente.

Durante la migrazione possono essere utilizzati per:

- leggere la baseline corrente;
- esportare dati verso il processo di importazione;
- confrontare risultati in modalità read-only;
- alimentare viste operative non autorevoli.

Dopo il cutover:

- `GoogleSheetsProgrammaFornituraRepository` non deve essere usato nel runtime autorevole;
- `GoogleSheetsOrdineRepository` non deve scrivere ORDINI autorevoli;
- `GoogleSheetsCommitRepository` deve essere dismesso dal write path autorevole;
- `GoogleApiSheetsGateway` può essere riutilizzato da un Reporting Adapter separato;
- i mapper fisici possono essere riutilizzati per export compatibili, ma non definiscono più lo schema autorevole;
- i fogli devono indicare chiaramente origine, data di aggiornamento e natura derivata.

La sincronizzazione PostgreSQL → Google Sheets deve essere unidirezionale, osservabile e ripetibile. Un errore di reporting non deve annullare né rendere incerto un commit PostgreSQL già completato.

## 11. Costi e gestione operativa

### Supabase

- costo base più prevedibile ma superiore a un database serverless inattivo;
- dashboard e servizi integrati riducono il lavoro operativo iniziale;
- backup giornalieri inclusi nel piano Pro secondo l’offerta corrente;
- PITR, branching e ambienti aggiuntivi richiedono controllo dei costi;
- adatto a un operatore che necessita consultazione visuale e future applicazioni.

### Neon

- modello usage-based favorevole a workload intermittenti;
- scale-to-zero e branching facilitano sandbox temporanee;
- richiede maggiore costruzione degli strumenti operativi circostanti;
- possibile latenza di riattivazione;
- ottima opzione se il costo elastico diventa prioritario.

### Firestore

- costi granulari e free quota iniziale;
- le letture moltiplicate dalla denormalizzazione possono rendere meno prevedibile il costo;
- backup, PITR e traffico hanno costi separati;
- console utile, ma meno naturale per relazioni e audit TPO.

### Google Sheets

- costo API iniziale basso e ottima accessibilità;
- costi nascosti elevati in controllo manuale, riconciliazione, rischio operativo e sviluppo di vincoli applicativi;
- non adeguato a sostituire un database transazionale.

Prima della produzione devono essere definiti budget mensile, alert di spesa, retention dei backup, Recovery Point Objective, Recovery Time Objective e prova periodica di restore.

## 12. Decisione finale

La decisione proposta è:

**SUPABASE / POSTGRESQL**

Motivazione:

1. il modello TPO è prevalentemente relazionale;
2. PostgreSQL fornisce nativamente le garanzie mancanti in Google Sheets;
3. una singola transazione può coordinare Identity, RUN, ORDINI e idempotenza;
4. vincoli e foreign key rendono esplicita l’integrità già prevista dai Register;
5. Supabase offre oggi la migliore combinazione tra operatività, accesso manuale governabile e strumenti per future applicazioni;
6. il Core già implementato è separato tramite porte e può essere riutilizzato;
7. Google Sheets può continuare a fornire valore come vista secondaria.

Provider consigliato oggi: **Supabase**.

Tecnologia autorevole: **PostgreSQL**.

Possibilità futura: migrazione a Neon o a un altro provider PostgreSQL mediante sostituzione di configurazione e adapter infrastrutturali, senza modificare il Domain.

Il Domain non deve importare SDK Supabase, tipi provider-specifici, API PostgREST o concetti di autenticazione del provider. Le regole di dominio restano nei modelli e servizi esistenti; il database applica integrità persistente e transazionale, non duplica la logica degli Engine.

## 13. Roadmap proposta

### Sprint 2.9 — PostgreSQL Physical Schema

- schema relazionale sandbox;
- tabelle, chiavi, vincoli, indici e migrazioni;
- schema per Identity, RUN, PROGRAMMI_FORNITURA, ORDINI e idempotenza;
- review del mapping tra Register e tabelle.

### Sprint 2.10 — PostgreSQL Identity and Run Adapters

- allocazione concorrente degli ID;
- persistenza completa della RUN;
- test transazionali e di concorrenza.

### Sprint 2.11 — PostgreSQL Programmi and Ordini Adapters

- repository PostgreSQL;
- mapping aggregati e righe;
- test di foreign key, unique e storico.

### Sprint 2.12 — PostgreSQL Commit Transaction

- commit atomico di RUN, ORDINI e idempotency key;
- ricevuta e gestione errori;
- nessun dual-write Google.

### Sprint 2.13 — Bootstrap and CLI PostgreSQL

- settings provider-neutral;
- dependency injection dei nuovi adapter;
- selezione esplicita di sandbox e produzione;
- nessun side effect all’import.

### Sprint 2.14 — Data Migration Sandbox

- export, validazione, import e riconciliazione;
- report delle anomalie;
- nessuna correzione automatica ambigua.

### Sprint 2.15 — First End-to-End Sandbox Run

- RUN manuale;
- doppia esecuzione e idempotenza;
- test di errori e rollback;
- verifica completa dell’audit trail.

### Sprint 2.16 — Google Sheets Reporting Adapter

- export unidirezionale;
- viste rigenerabili;
- marcatura non autorevole;
- nessuna scrittura inversa implicita.

### Sprint 2.17 — Production Readiness Review

- sicurezza;
- backup e restore;
- osservabilità;
- concorrenza;
- costi;
- isolamento writer legacy;
- piano di cutover e rollback.

## 14. Go / No-Go

**GO FOR POSTGRESQL SANDBOX ARCHITECTURE AND IMPLEMENTATION**

**NO-GO FOR PRODUCTION WRITE**

È autorizzabile, dopo approvazione finale della presente review, esclusivamente:

- la creazione di un ambiente Supabase/PostgreSQL sandbox;
- la definizione dello schema fisico;
- l’implementazione e il test degli adapter;
- l’importazione di dati sintetici o esplicitamente autorizzati;
- il confronto read-only con Google Sheets.

Non sono ancora autorizzati:

- scritture su dati produttivi;
- cutover della fonte autorevole;
- automazioni unattended;
- dual-write;
- migrazione di credenziali nel repository;
- dismissione dei fogli o dei writer legacy prima di una review dedicata.

## 15. Questioni ancora aperte

Prima del Freeze architetturale o dell’implementazione produttiva devono essere decisi:

1. regione Supabase e requisiti di residenza dei dati;
2. piano, budget e limiti di spesa;
3. RPO, RTO, retention e strategia PITR;
4. modello dei ruoli database e accesso amministrativo;
5. uso o esclusione delle API Supabase nel futuro frontend;
6. policy RLS e confine con i servizi backend;
7. meccanismo definitivo degli ID: sequence PostgreSQL oppure tabella di sequenze transazionale;
8. schema persistente completo della RUN e dei log;
9. confine transazionale tra MOVIMENTI_MAGAZZINO e STOCK;
10. strategia di audit per correzioni e Facts immutabili;
11. mapping delle relazioni molti-a-molti tra ORDINI e CONSEGNE;
12. gestione delle informazioni variabili tramite colonne relazionali o JSONB;
13. autorità documentale del nuovo Physical Schema PostgreSQL;
14. procedura di importazione, deduplicazione e riconciliazione;
15. frequenza e modalità del reporting verso Google Sheets;
16. isolamento definitivo dei writer legacy;
17. condizioni oggettive per il cutover e il rollback;
18. necessità di un ambiente staging distinto dalla sandbox;
19. policy per rete assente, timeout e ripetizione sicura delle operazioni;
20. prova operativa periodica di backup e restore.

La presente review propone la direzione architetturale. Non costituisce Architecture Freeze, non crea infrastruttura e non autorizza la produzione.
