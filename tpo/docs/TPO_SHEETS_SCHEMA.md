# TPO SHEETS SCHEMA — REGOLE DELLA PERSISTENZA

## 1. Scopo e responsabilità documentale

Questo documento definisce le regole architetturali con cui il modello concettuale di Tower Power Operations (TPO) viene rappresentato nel livello di persistenza basato su Google Sheets.

Governa:

- i criteri di persistenza;
- i criteri di creazione e separazione dei fogli;
- la classificazione dei fogli;
- le relazioni tra registri;
- la derivazione dello State;
- le responsabilità di lettura e scrittura;
- i vincoli per la futura definizione degli schemi fisici.

Non definisce il modello concettuale, le regole operative, il funzionamento dell'Event Engine, il catalogo definitivo dei fogli o i dettagli fisici dei loro contenuti.

L'architettura della persistenza descrive responsabilità, regole di conservazione dei dati e relazioni tra registri. Google Sheets rappresenta esclusivamente l'implementazione corrente della persistenza.

L'architettura non dipende dalla tecnologia utilizzata e rimane valida anche qualora la persistenza venga implementata mediante database relazionali, database documentali o altri sistemi equivalenti.

## 2. Autorità del modello concettuale

`TPO_DATA_DICTIONARY.md` è la fonte autorevole per entità, associazioni, proiezioni, significati e relazioni del dominio.

La rappresentazione fisica deve derivare dal modello concettuale e non può:

- introdurre entità o relazioni assenti dal modello approvato;
- alterare il significato o la responsabilità dei concetti;
- trasformare una proiezione in una fonte autorevole;
- fondere concetti distinti per convenienza di rappresentazione;
- attribuire autorità a una copia di dati già governati altrove.

L'esistenza di un concetto nel Data Dictionary non implica automaticamente l'esistenza di un foglio dedicato.

## 3. Principi della rappresentazione fisica

La rappresentazione fisica rispetta i seguenti principi:

1. Nel livello di persistenza autorevole, un foglio esiste solo se rappresenta Facts autorevoli oppure Configuration persistente.
2. Ogni Fact viene registrato una sola volta nella propria fonte autorevole.
3. Lo State non viene modificato direttamente: deriva sempre dai Facts applicabili.
4. Ogni foglio ha una sola responsabilità.
5. Le informazioni non vengono duplicate: i riferimenti sostituiscono la copia.
6. Le Derived Views sono completamente rigenerabili dalle proprie fonti.
7. Google Sheets persiste, rende consultabili e visualizza dati; non contiene logica di dominio.
8. Ogni registro dichiara un solo Writer e i propri Readers.

Le Derived Views possono essere materializzate in un foglio esclusivamente per consultazione o visualizzazione. Tale foglio non appartiene alla persistenza autorevole e non acquisisce autorità autonoma.

## 4. Criteri per la creazione di un foglio

La creazione di un foglio autorevole è giustificata soltanto quando il contenuto rappresenta:

- Facts che devono essere conservati come fonte ufficiale; oppure
- Configuration che deve persistere come definizione ufficiale del dominio.

Prima di creare un foglio deve essere possibile dichiararne:

- la responsabilità unica;
- la classificazione;
- l'autorità informativa;
- il concetto o i concetti del Data Dictionary rappresentati senza alterarne i confini;
- il Writer;
- i Readers;
- le relazioni con le altre fonti;
- la natura modificabile o immutabile del contenuto.

Le Derived Views possono essere materializzate come foglio solo quando servono alla consultazione o alla visualizzazione. La loro esistenza deve essere giustificata dall'uso del Read Path, non dalla necessità di conservare una nuova fonte ufficiale.

Non giustificano la creazione di un foglio:

- la sola comodità visuale;
- la copia di informazioni già autorevoli;
- la necessità di eseguire logica di dominio;
- l'esistenza di un'entità concettuale priva di una responsabilità persistente autonoma;
- la conservazione manuale di State ricostruibile.

## 5. Criteri di separazione

Due insiemi di informazioni devono essere separati quando differiscono per almeno uno dei seguenti aspetti:

- responsabilità;
- natura di Fact o Configuration oppure appartenenza alle Derived Views;
- autorità;
- ciclo di vita;
- regole di modificabilità;
- Writer autorizzato;
- origine e condizioni di rigenerazione.

La separazione preserva i confini concettuali e impedisce che un foglio assuma responsabilità eterogenee.

La condivisione dello stesso contesto operativo non è sufficiente per unire dati diversi. Al contrario, informazioni con la stessa responsabilità, autorità e ciclo di vita non devono essere frammentate senza necessità.

## 6. Classificazione dei fogli

Ogni foglio deve appartenere a una sola delle seguenti categorie.

### 6.1 Authoritative Registers

Gli **Authoritative Registers** sono le fonti ufficiali dei Facts.

Contengono esclusivamente Facts autorevoli.

Non contengono:

- State derivato;
- Configuration;
- logica;
- copie descrittive di altri registri.

Caratteristiche:

- conservano Facts registrati una sola volta;
- preservano la cronologia autorevole;
- non contengono copie autonome di informazioni governate da altri registri;
- forniscono le basi necessarie alla ricostruzione dello State;
- sono modificabili esclusivamente dal Writer dichiarato.

### 6.2 Configuration Registers

I **Configuration Registers** conservano la Configuration persistente che definisce il dominio e ne governa il comportamento.

Contengono esclusivamente definizioni e parametri persistenti.

Non contengono:

- Facts;
- State derivato;
- workflow operativo.

Caratteristiche:

- possiedono autorità propria;
- non rappresentano eventi o Facts operativi;
- non duplicano Configuration governata da un'altra fonte;
- sono modificabili secondo autorizzazioni amministrative e tramite il Writer dichiarato;
- mantengono separata la definizione del dominio dagli accadimenti operativi.

### 6.3 Derived Views

Le **Derived Views** rappresentano State o composizioni informative ottenuti da Authoritative Registers e Configuration Registers.

Contengono esclusivamente informazioni derivate.

Non contengono:

- Facts autorevoli;
- Configuration;
- dati modificabili direttamente.

Caratteristiche:

- non sono autorevoli;
- sono completamente rigenerabili;
- non sono modificabili direttamente;
- non possono correggere o sostituire i registri di origine;
- non introducono Facts, Configuration o regole proprie.

## 7. Persistenza dei Facts

Un Fact rappresentato nel livello di persistenza deve essere:

- registrato una sola volta;
- conservato nella propria fonte autorevole;
- immutabile;
- rettificabile esclusivamente mediante un nuovo Fact;
- riconducibile alla propria origine;
- sufficiente, insieme agli altri Facts applicabili, alla ricostruzione dello State.

La rettifica non modifica né elimina il Fact originario. Il nuovo Fact conserva la tracciabilità della correzione senza riscrivere la cronologia.

Uno stesso accadimento non può essere registrato come Fact autorevole in più fogli. Le altre rappresentazioni devono riferirsi alla fonte o derivare da essa.

## 8. Persistenza della Configuration

La Configuration definisce concetti, parametri e classificazioni ufficiali necessari al dominio.

La sua persistenza deve:

- mantenerla distinta dai Facts;
- identificarne una sola fonte autorevole;
- preservarne la responsabilità specifica;
- renderla disponibile ai componenti autorizzati senza duplicarla;
- consentire modifiche soltanto secondo le autorizzazioni amministrative previste.

Una modifica alla Configuration non rappresenta automaticamente un Fact operativo e non autorizza la riscrittura della cronologia. Gli effetti della Configuration sono determinati dai componenti architetturali competenti.

## 9. Derivazione dello State

Lo **State** rappresenta la condizione corrente ricostruita dai Facts e dalla Configuration applicabile.

Lo State:

- non viene modificato direttamente;
- non costituisce una fonte indipendente dai Facts;
- deve rimanere riconducibile alle fonti che lo determinano;
- può essere materializzato nelle Derived Views;
- deve poter essere rigenerato integralmente.

Qualsiasi variazione dello State deve conseguire alla registrazione di nuovi Facts autorevoli. Una correzione dello State avviene correggendone le cause mediante Facts di rettifica, non modificando la proiezione.

## 10. Relazioni e riferimenti

Le relazioni fisiche rappresentano le relazioni concettuali definite in `TPO_DATA_DICTIONARY.md`.

Un riferimento:

- collega informazioni appartenenti a fonti diverse;
- sostituisce la copia degli attributi del concetto collegato;
- non trasferisce autorità al registro che lo utilizza;
- deve preservare la tracciabilità verso la fonte autorevole;
- non può introdurre relazioni assenti dal modello concettuale.

Le associazioni dotate di significato proprio sono rappresentate secondo la loro natura concettuale e persistono come Facts quando costituiscono accadimenti autorevoli. Non vengono ridotte a copie descrittive distribuite fra registri diversi.

## 11. Regole contro la duplicazione

Ogni informazione persistente ha una sola fonte autorevole.

È vietato:

- registrare lo stesso Fact in più fonti;
- copiare attributi autorevoli al posto di un riferimento;
- mantenere manualmente copie dello State;
- duplicare Configuration in registri operativi;
- trattare le Derived Views come fonte di correzione;
- creare registri paralleli con la stessa responsabilità.

Una ripetizione è ammessa soltanto come risultato derivato per consultazione. Deve rimanere rigenerabile e non acquisisce autorità.

## 12. Rigenerabilità delle Derived Views

Per ciascuna delle Derived Views devono essere dichiarati:

- gli Authoritative Registers e i Configuration Registers sorgente;
- la natura derivata delle informazioni rappresentate;
- le condizioni che richiedono la rigenerazione;
- le condizioni necessarie per una rigenerazione completa;
- il Writer responsabile della materializzazione;
- i Readers autorizzati alla consultazione.

La rigenerazione deve produrre la vista esclusivamente dalle fonti dichiarate. Non può dipendere da modifiche manuali, informazioni non autorevoli o State conservato soltanto nella vista precedente.

Le Derived Views non possono:

- ricevere correzioni dirette;
- essere usata per riscrivere i registri sorgente;
- conservare l'unica copia di un'informazione necessaria al dominio;
- diventare fonte di Facts o Configuration.

## 13. Confine tra persistenza e logica

Google Sheets svolge esclusivamente le seguenti funzioni:

- persistenza;
- consultazione;
- visualizzazione.

Google Sheets non contiene logica di dominio e non decide:

- la validità semantica di un evento;
- le regole operative applicabili;
- la selezione delle pipeline;
- le transizioni dello State;
- gli effetti di un Fact;
- la produzione o l'applicazione del WritePlan.

Queste decisioni appartengono ai componenti architetturali governati da `SYSTEM_ARCHITECTURE.md` ed `EVENT_ENGINE.md` e alle regole governate da `OPERATING_RULES.md`.

## 14. Responsabilità di scrittura

Si applica il **Single Writer Principle**.

Ogni registro o vista materializzata deve dichiarare:

- **Writer:** l'unico componente autorizzato ad applicare modifiche;
- **Readers:** i componenti autorizzati alla lettura.

Il Google Sheets Writer è l'unico componente architetturale autorizzato ad applicare modifiche ai fogli ufficiali. I motori di dominio producono proposte nel WritePlan, ma non scrivono direttamente.

La modificabilità dipende dalla classificazione:

```text
AUTHORITATIVE REGISTERS
→ modificabili esclusivamente dal Writer

CONFIGURATION REGISTERS
→ modificabili secondo autorizzazioni amministrative e tramite il Writer

DERIVED VIEWS
→ mai modificabili direttamente; materializzabili o rigenerabili esclusivamente dal Writer
```

I Readers non modificano il contenuto letto. L'autorizzazione alla lettura non implica autorizzazione alla scrittura.

## 15. Criteri per la futura definizione degli schemi fisici

La futura definizione del catalogo dei fogli e dei relativi schemi fisici dovrà, per ogni foglio, dichiarare almeno:

- responsabilità unica;
- classificazione;
- concetti del Data Dictionary rappresentati;
- natura autorevole o derivata;
- fonte dei Facts o della Configuration;
- Writer;
- Readers;
- registri sorgente, per le Derived Views;
- condizioni di rigenerazione, per le Derived Views;
- relazioni e riferimenti verso le altre fonti;
- vincoli di immutabilità o modificabilità;
- contenuti esplicitamente esclusi.

Un futuro schema fisico può essere approvato soltanto se rispetta queste regole e non introduce duplicazioni, logica di dominio o nuove decisioni concettuali.

## 16. Autorità documentale

Questo documento è la fonte autorevole per le regole di rappresentazione fisica del modello TPO nel livello di persistenza Google Sheets.

Le autorità documentali restano separate:

- `TPO_CORE_PRINCIPLES.md` governa i principi fondamentali;
- `SYSTEM_ARCHITECTURE.md` governa architettura, componenti, confini e flussi;
- `EVENT_ENGINE.md` governa il comportamento logico dell'Event Engine;
- `TPO_DATA_DICTIONARY.md` governa il modello concettuale del dominio;
- `OPERATING_RULES.md` governa le regole operative;
- `PROJECT_SNAPSHOT_v1.0.md` governa la fotografia della baseline;
- `DOCUMENTATION_WORKFLOW.md` governa il ciclo di vita documentale.

Il catalogo definitivo dei fogli e i relativi dettagli fisici non sono definiti in questa versione del documento.
