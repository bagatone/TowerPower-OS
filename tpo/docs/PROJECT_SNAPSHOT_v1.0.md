# TPO PROJECT SNAPSHOT — BASELINE v1.0

## 1. Identità della baseline

- **Versione della baseline:** 1.0
- **Data della baseline originaria:** 20/07/2026
- **Data dell'ultima verifica dello snapshot e del repository:** 21/07/2026
- **Natura della versione:** baseline architetturale e documentale pre-implementazione; non è una versione software operativa.

Questo snapshot fotografa la baseline originaria del 20/07/2026. Riporta separatamente la verifica successiva del repository, eseguita il 21/07/2026, senza modificare retroattivamente lo stato della baseline.

## 2. Scopo del progetto

Tower Power Operations (TPO) è il sistema aziendale progettato per gestire il ciclo produttivo e commerciale di Tower Power. La baseline descrive il perimetro progettato, non un insieme di funzionalità tutte implementate o operative.

## 3. Stato complessivo

| Ambito | Progettato | Approvato | Documentato | Implementato | Testato |
|---|---|---|---|---|---|
| Architettura logica | Sì | Registrata come approvata | Sì | Non attestato | Non attestato |
| Modello dati | Sì | Relazioni registrate come validate | Parzialmente | Non attestato | Non attestato |
| Schema Google Sheets | Sì | Registrato come approvato | Sì | Non verificato | Non verificato |
| Modello event-driven | Sì | Non dichiarato | Sì | Python presente; Apps Script assente | Python: 102 test superati |
| Apps Script | Previsto | Non applicabile | Citato | Non implementato | Nessun test rilevato |

Le qualifiche “approvato”, “validato” e “completato” sono riportate soltanto dove compaiono nei documenti esaminati. Non implicano ulteriori approvazioni o verifiche non documentate.

## 4. Componenti inclusi nel perimetro

Il perimetro progettato comprende, ad alto livello:

- gestione delle anagrafiche e degli ordini;
- pianificazione e registrazione della produzione;
- tracciabilità di semine, lotti, raccolti e assegnazioni;
- gestione di consegne, documenti di vendita e incassi;
- gestione di stock, inventario e movimenti di magazzino;
- coordinamento tramite eventi operativi;
- scrittura controllata nei fogli Google;
- briefing, dashboard e automazioni operative.

La struttura tecnica, i motori e il flusso dei dati sono definiti in `SYSTEM_ARCHITECTURE.md`. Le entità, i campi e le relazioni appartengono a `TPO_DATA_DICTIONARY.md` e `TPO_SHEETS_SCHEMA.md`.

## 5. Baseline documentale

| Documento | Responsabilità | Stato verificabile al 21/07/2026 |
|---|---|---|
| `TPO_CORE_PRINCIPLES.md` | Principi sovraordinati del TPO | Versione 1.0, datata 21/07/2026, stato dichiarato “Ufficiale” |
| `SYSTEM_ARCHITECTURE.md` | Architettura logica, componenti e flusso dati | Presente e sostanziale; si definisce architettura logica ufficiale, ma non riporta metadati espliciti di versione, data o stato |
| `EVENT_ENGINE.md` | Comportamento operativo dell'Event Engine v1 | Presente; documenta responsabilità, input, output, flusso e prima milestone; dichiara espressamente di non descrivere il codice |
| `TPO_DATA_DICTIONARY.md` | Struttura, campi e relazioni del modello dati | Versione 1.0, datata 20/07/2026; il contenuto arriva fino ad `ASSEGNAZIONI` e non copre tutti i fogli del perimetro dichiarato, quindi risulta parziale rispetto al proprio scopo dichiarato |
| `TPO_SHEETS_SCHEMA.md` | Intestazioni ufficiali dei fogli Google | Presente; definisce gli schemi ufficiali elencati, senza metadati espliciti di versione, data o stato |
| `OPERATING_RULES.md` | Regole operative ufficiali | Presente e dichiarato fonte ufficiale delle regole operative; non riporta metadati espliciti di versione o data complessiva |
| `CHANGELOG.md` | Registro dell'evoluzione del progetto | Presente; contiene la voce `[1.0.0] - 20/07/2026` e registra dichiarazioni di approvazione, audit e validazione riferite a quella data |
| `PROJECT_SNAPSHOT_v1.0.md` | Fotografia verificabile della baseline | Ristrutturato come baseline architetturale e documentale pre-implementazione |

## 6. Decisioni architetturali recepite

La baseline recepisce, senza riprodurne le regole tecniche:

- i fogli Google come datastore operativo ufficiale;
- un'architettura governata dagli eventi operativi;
- una fonte autorevole per ciascun dato e per ciascun ambito documentale;
- conservazione dello storico e tracciabilità; gli eventi sono immutabili e le correzioni avvengono mediante nuovi eventi;
- configurabilità del sistema tramite fonti ufficiali;
- stock come proiezione derivata governata dall'architettura event-driven.

I dettagli autorevoli sono contenuti rispettivamente in `TPO_CORE_PRINCIPLES.md`, `SYSTEM_ARCHITECTURE.md`, `EVENT_ENGINE.md`, `TPO_DATA_DICTIONARY.md`, `TPO_SHEETS_SCHEMA.md` e `OPERATING_RULES.md`.

## 7. Stato dell'implementazione

### Baseline originaria — 20/07/2026

- L'architettura e la documentazione di base erano state predisposte.
- Apps Script era dichiarato “non ancora iniziato”.
- La baseline non attestava un sistema software operativo.
- La baseline non attestava test dell'implementazione Apps Script.

### Verifica successiva del repository — 21/07/2026

- Sono presenti moduli Python per caricamento e validazione delle fonti, Source Gate, Event Engine, pianificazione, risorse, generazione di righe, scrittura controllata, stock alarm e briefing.
- Sono presenti test automatici Python per tali componenti e per i relativi flussi.
- La suite esistente, eseguita con il percorso del progetto configurato, ha prodotto `102 passed`.
- Non sono stati rilevati file Apps Script; Apps Script non risulta quindi implementato nel repository verificato.
- Non è stata verificata, nell'ambito di questo snapshot, l'operatività su fogli Google reali né un rilascio software in produzione.

L'implementazione Python rilevata non trasforma la baseline v1.0 in una versione software operativa.

## 8. Questioni aperte, dipendenze e rischi

- `TPO_DATA_DICTIONARY.md` non copre tutti i fogli presenti in `TPO_SHEETS_SCHEMA.md` e nel perimetro architetturale dichiarato.
- `TPO_DATA_DICTIONARY.md` e `TPO_SHEETS_SCHEMA.md` presentano strutture non allineate per fogli omonimi; la fonte applicabile deve essere chiarita nei rispettivi documenti autorevoli.
- `SYSTEM_ARCHITECTURE.md` usa anche la denominazione “TowerPower OS”, mentre gli altri documenti usano prevalentemente “Tower Power Operations (TPO)”.
- I documenti esaminati descrivono stati riferiti a momenti diversi: la baseline è pre-implementazione, mentre il repository verificato contiene codice Python e test.
- Lo schema è documentato, ma questa verifica non ha confrontato le intestazioni con fogli Google reali.
- I documenti non dimostrano l'assenza di blocchi complessivi; pertanto questa baseline non dichiara “nessun blocco”.

## 9. Prossimo milestone

Completare e allineare `TPO_DATA_DICTIONARY.md` al perimetro dei fogli e alle intestazioni ufficiali documentate, prima di usarlo come riferimento completo per ulteriori implementazioni.

## 10. Autorità documentale

La gerarchia delle responsabilità documentali della baseline è:

- principi: `TPO_CORE_PRINCIPLES.md`;
- architettura: `SYSTEM_ARCHITECTURE.md`;
- eventi: `EVENT_ENGINE.md`;
- modello e significato dei dati: `TPO_DATA_DICTIONARY.md`;
- intestazioni dei fogli: `TPO_SHEETS_SCHEMA.md`;
- regole operative: `OPERATING_RULES.md`;
- evoluzione del progetto: `CHANGELOG.md`.

In caso di conflitto, prevale la gerarchia stabilita da `TPO_CORE_PRINCIPLES.md`; le altre responsabilità restano circoscritte ai rispettivi documenti autorevoli.
