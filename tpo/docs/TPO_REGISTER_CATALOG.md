# TPO REGISTER CATALOG — CONTRATTO DEL REGISTRO

## 1. Scopo

Questo documento definisce il contratto standard con cui deve essere documentato qualsiasi Registro di Tower Power Operations (TPO).

Il contratto stabilisce una struttura obbligatoria e uniforme per dichiarare:

- il significato del Registro;
- la sua responsabilità;
- la sua classificazione;
- la sua autorità;
- le responsabilità di lettura e scrittura;
- le relazioni con gli altri Registri;
- le regole di modificabilità, rettifica, aggiornamento e rigenerazione.

Questo documento non descrive Registri specifici e non definisce la loro rappresentazione fisica.

## 2. Dipendenze e confini

Il Contratto del Registro dipende dai documenti architetturali già approvati e non ne modifica né estende le decisioni.

In particolare:

- `TPO_DATA_DICTIONARY.md` governa i concetti del dominio;
- `TPO_SHEETS_SCHEMA.md` governa le regole della persistenza;
- `SYSTEM_ARCHITECTURE.md` governa componenti, confini e responsabilità;
- `EVENT_ENGINE.md` governa il comportamento logico dell'Event Engine;
- `TPO_CORE_PRINCIPLES.md` governa i principi fondamentali.

Il Contratto del Registro è indipendente dalla tecnologia di persistenza. Descrive responsabilità, autorità, relazioni e comportamento informativo permanente senza imporre una realizzazione tecnica.

## 3. Principi del Contratto del Registro

Ogni Registro:

- possiede una sola responsabilità;
- appartiene a una sola categoria;
- possiede un solo Writer;
- dichiara i propri Readers;
- rappresenta esclusivamente concetti definiti nel Data Dictionary;
- non duplica informazioni autorevoli;
- utilizza riferimenti verso le fonti autorevoli;
- rispetta le regole definite in `TPO_SHEETS_SCHEMA.md`;
- distingue Facts, Configuration e State derivato;
- dichiara esplicitamente ciò che può e ciò che non può contenere.

Una descrizione è conforme soltanto se compila tutte le sezioni obbligatorie del contratto. Le Note architetturali permanenti sono l'unica sezione facoltativa.

## 4. Vincoli per categoria

### 4.1 Authoritative Registers

Gli **Authoritative Registers**:

- contengono esclusivamente Facts autorevoli;
- registrano ogni Fact una sola volta;
- sono immutabili;
- vengono rettificati esclusivamente mediante nuovi Facts;
- costituiscono la fonte autorevole dello State;
- non contengono State derivato, Configuration, logica o copie descrittive di altri Registri.

Il Writer non modifica o elimina un Fact esistente. Registra nuovi Facts e, quando necessario, nuovi Facts di rettifica.

### 4.2 Configuration Registers

I **Configuration Registers**:

- contengono esclusivamente definizioni e parametri persistenti;
- possiedono autorità propria;
- sono aggiornabili dal Writer secondo le autorizzazioni previste;
- non rappresentano eventi;
- non contengono Facts, State derivato o workflow operativo.

### 4.3 Derived Views

Le **Derived Views**:

- contengono esclusivamente informazioni derivate;
- non sono autorevoli;
- non sono modificabili direttamente;
- sono completamente rigenerabili;
- non possono correggere i Registri sorgente;
- non contengono Facts autorevoli, Configuration o dati modificabili direttamente.

La materializzazione o la rigenerazione delle Derived Views avviene esclusivamente tramite il Writer dichiarato.

## 5. Struttura obbligatoria del Contratto del Registro

Ogni Registro deve essere documentato utilizzando, nello stesso ordine, le sezioni seguenti.

### 5.1 Nome del Registro

Dichiara il nome ufficiale e univoco con cui il Registro è identificato nella documentazione.

Il nome non definisce la rappresentazione tecnica e non può alterare il significato dei concetti rappresentati.

### 5.2 Categoria

Dichiara una sola categoria tra:

- Authoritative Registers;
- Configuration Registers;
- Derived Views.

La categoria determina autorità, contenuti ammessi, modificabilità e requisiti di rigenerazione.

### 5.3 Concetti del Data Dictionary rappresentati

Elenca i concetti di `TPO_DATA_DICTIONARY.md` rappresentati dal Registro e chiarisce il ruolo di ciascuno nella responsabilità dichiarata.

Il Registro non può rappresentare concetti non definiti nel Data Dictionary né modificarne il significato.

### 5.4 Scopo

Spiega perché il Registro esiste e quale necessità informativa permanente soddisfa.

Lo Scopo non descrive procedure, soluzioni tecniche o utilizzi temporanei.

### 5.5 Responsabilità unica

Dichiara l'unica responsabilità informativa del Registro.

Qualsiasi contenuto estraneo a tale responsabilità deve essere escluso o ricondotto alla propria fonte autorevole.

### 5.6 Origine

Dichiara una sola natura informativa prevalente:

- Facts;
- Configuration;
- State derivato.

L'Origine deve essere coerente con la Categoria:

- Authoritative Registers corrispondono a Facts;
- Configuration Registers corrispondono a Configuration;
- Derived Views corrispondono a State derivato.

### 5.7 Writer

Identifica l'unico componente architetturale autorizzato alla scrittura.

La sezione deve precisare quali operazioni sono consentite al Writer in coerenza con Categoria, Modificabilità diretta e Rettifica o aggiornamento.

Nessun altro componente può modificare il Registro.

### 5.8 Readers

Identifica i componenti autorizzati alla consultazione e lo scopo architetturale della lettura.

La facoltà di lettura non attribuisce autorità sul contenuto e non implica facoltà di scrittura.

### 5.9 Chiave logica

Definisce come ogni record viene identificato concettualmente nel dominio.

La Chiave logica:

- descrive l'identità concettuale;
- deve essere coerente con il Data Dictionary;
- non definisce identificativi o meccanismi implementativi.

### 5.10 Relazioni e riferimenti

Elenca le relazioni con gli altri Registri.

Per ogni relazione dichiara:

- il significato concettuale;
- il Registro che conserva l'informazione autorevole;
- il Registro che utilizza soltanto il riferimento.

Il riferimento non copia gli attributi della fonte e non trasferisce autorità al Registro che lo utilizza.

### 5.11 Contenuto autorizzato

Dichiara i tipi di informazione che possono comparire nel Registro.

Il contenuto autorizzato deve essere:

- necessario alla Responsabilità unica;
- coerente con Categoria e Origine;
- derivato esclusivamente dai concetti dichiarati;
- privo di duplicazioni rispetto alle altre fonti autorevoli.

### 5.12 Contenuti esclusi

Dichiara le informazioni che non devono mai comparire nel Registro.

La sezione deve escludere almeno:

- informazioni appartenenti ad altre responsabilità;
- copie descrittive di dati autorevoli altrove;
- contenuti incompatibili con Categoria e Origine;
- logica, workflow e decisioni operative.

### 5.13 Modificabilità diretta

La modificabilità diretta indica se i record già esistenti possono essere modificati direttamente dal Writer autorizzato oppure se qualsiasi variazione deve essere rappresentata mediante nuovi Facts o altri meccanismi previsti dal Contratto del Registro.

La dichiarazione deve rispettare i vincoli di categoria:

- negli Authoritative Registers i Facts esistenti non sono modificabili direttamente;
- nei Configuration Registers le modifiche sono applicabili esclusivamente dal Writer secondo le autorizzazioni previste;
- le Derived Views non sono mai modificabili direttamente.

### 5.14 Rettifica o aggiornamento

Distingue esplicitamente:

- modificabilità diretta;
- rettifica;
- aggiornamento.

Per gli Authoritative Registers descrive la rettifica esclusivamente mediante nuovi Facts, senza modificare o eliminare quelli originari.

Per i Configuration Registers descrive l'aggiornamento tramite il Writer secondo le autorizzazioni previste.

Per le Derived Views dichiara che le variazioni conseguono esclusivamente alla rigenerazione dalle fonti.

### 5.15 Rigenerabilità

La sezione è obbligatoria per le Derived Views e dichiara:

- i Registri sorgente;
- la natura derivata delle informazioni;
- eventi o condizioni che richiedono la rigenerazione;
- le condizioni necessarie per una ricostruzione completa;
- la completa ricostruibilità senza modifiche manuali.

Per Authoritative Registers e Configuration Registers dichiara che il requisito non è applicabile, senza attribuire loro natura derivata.

### 5.16 Vincoli concettuali

Elenca i vincoli permanenti necessari a preservare significato, autorità, coerenza e relazioni del Registro.

I vincoli devono derivare dai documenti autorevoli e non possono descrivere meccanismi implementativi.

### 5.17 Note architetturali permanenti

Raccoglie esclusivamente osservazioni architetturali permanenti necessarie a comprendere il Registro.

La sezione è facoltativa e può essere omessa quando non esistono osservazioni permanenti da registrare.

Non può contenere:

- decisioni temporanee;
- regole operative;
- attività pianificate;
- dettagli implementativi.

## 6. Regola di conformità

La documentazione di un Registro è conforme al presente contratto soltanto quando:

- utilizza tutte le sezioni obbligatorie nello stesso ordine;
- assegna una sola Categoria e una sola Origine coerente;
- dichiara una Responsabilità unica e un solo Writer;
- identifica i Readers;
- riconduce ogni contenuto al Data Dictionary;
- distingue autorità, riferimenti e informazioni derivate;
- rispetta i vincoli della Categoria dichiarata;
- non introduce duplicazioni, logica o dettagli implementativi;
- dichiara la rigenerabilità completa quando appartiene alle Derived Views.

Una descrizione incompleta o incoerente non può essere considerata un Contratto del Registro approvato.

## 7. Autorità documentale

Questo documento è la fonte autorevole per la struttura con cui devono essere documentati i Registri del TPO.

Non governa:

- il modello concettuale del dominio;
- l'architettura del sistema;
- il comportamento dell'Event Engine;
- le regole operative;
- la rappresentazione fisica dei dati;
- il contenuto di Registri specifici.

In caso di conflitto, prevalgono i documenti autorevoli per il rispettivo ambito. Il presente contratto deve essere applicato senza reinterpretarli.
