# TPO CORE PRINCIPLES

**Tower Power Operations**

**Versione:** 1.0  
**Data:** 21/07/2026  
**Stato:** Ufficiale

---

# PREFAZIONE

Il presente documento definisce i principi fondamentali che regolano la progettazione, lo sviluppo e l'evoluzione di Tower Power Operations (TPO).

Questi principi sono vincolanti per:

- il software;
- gli sviluppatori;
- gli agenti di intelligenza artificiale;
- le automazioni;
- qualsiasi futura evoluzione del progetto.

Le regole contenute in questo documento hanno priorità su qualsiasi decisione implementativa.

Se una soluzione tecnica entra in conflitto con uno dei principi qui definiti, dovrà essere modificata fino a rispettarlo.

Questo documento rappresenta la **Costituzione di Tower Power Operations**.

---

# PRINCIPIO ZERO

## Il sistema deve essere configurabile.

Nessuna decisione strutturale deve essere definita direttamente nel codice se può essere derivata dalla configurazione del sistema o dai dati ufficiali.

Il software deve leggere la propria configurazione dalle fonti ufficiali del TPO, evitando qualsiasi dipendenza da valori scritti manualmente nel codice.

Questo principio si applica, a titolo esemplificativo ma non esaustivo, a:

- sigle delle varietà;
- codici identificativi;
- nomi dei fogli;
- intestazioni delle colonne;
- workflow operativi;
- stati;
- parametri di produzione;
- automazioni;
- regole di business.

L'obiettivo è garantire che il sistema possa evolvere senza richiedere modifiche al codice sorgente ogni volta che cambia una configurazione operativa.

Qualsiasi valore che possa essere letto dalla configurazione o dai fogli ufficiali non deve essere duplicato nel codice.
---

# PRINCIPIO 1

## Il sistema non deve mai inventare dati.

L'affidabilità dei dati ha sempre priorità rispetto alla velocità di esecuzione.

Il software, gli agenti di intelligenza artificiale e qualsiasi automazione del TPO non devono mai creare, dedurre o completare informazioni prive di una fonte ufficiale.

In particolare, non devono mai essere inventati:

- codici identificativi;
- sigle delle varietà;
- clienti;
- lotti;
- quantità;
- stati;
- intestazioni di colonne;
- nomi di fogli;
- relazioni tra dati;
- qualsiasi altro dato operativo.

Se un'informazione non è disponibile, il sistema deve seguire esclusivamente uno dei seguenti comportamenti:

1. recuperarla dalla fonte ufficiale;
2. richiedere l'intervento dell'operatore;
3. interrompere l'operazione segnalando l'impossibilità di proseguire.

Le supposizioni non sono mai consentite.

La mancanza di un dato rappresenta una condizione da gestire, non un'informazione da inventare.
---

# PRINCIPIO 2

## Il sistema deve avere una sola fonte ufficiale dei dati.

Il database ufficiale di Tower Power Operations è costituito esclusivamente dai fogli Google che compongono il sistema TPO.

Ogni dato operativo deve essere letto da tali fogli o derivare da essi secondo le regole definite dal sistema.

Nessun componente del software può considerare come fonte ufficiale:

- memoria degli agenti di intelligenza artificiale;
- variabili permanenti non sincronizzate;
- copie locali dei dati;
- file temporanei;
- cache;
- valori hardcodati.

La memoria degli agenti di intelligenza artificiale ha esclusivamente lo scopo di migliorare il dialogo con l'utente e non deve mai essere utilizzata come riferimento per prendere decisioni operative.

Quando esiste una differenza tra qualsiasi altra fonte e i dati presenti nei fogli ufficiali del TPO, prevalgono sempre i dati contenuti nei fogli Google.

Ogni nuova componente del sistema dovrà rispettare questo principio ed evitare la creazione di copie permanenti delle stesse informazioni.
---

# PRINCIPIO 3

## Le modifiche al sistema devono essere generate dagli eventi operativi.

Le modifiche al sistema devono essere generate dagli eventi operativi.

Ogni modifica allo stato operativo del TPO deve essere generata dalla registrazione di un evento.

Gli eventi rappresentano la cronologia ufficiale delle attività svolte e costituiscono l'unico punto di ingresso delle modifiche ai dati operativi.

Nessun foglio operativo deve essere aggiornato direttamente da un operatore o da uno script, salvo i casi espressamente previsti dall'architettura del sistema.

La registrazione di un evento deve essere sufficiente affinché il software aggiorni automaticamente tutte le informazioni derivate.

Ad esempio, un singolo evento può generare l'aggiornamento di:

- LOTTI;
- SEMINE;
- RACCOLTI;
- ASSEGNAZIONI;
- CONSEGNE;
- STOCK;
- INVENTARIO;
- PROBLEMI;
- PHOTO_BANK_INDEX;
- qualsiasi altro foglio derivato.

L'operatore registra un solo evento.

Il sistema si occupa di propagare automaticamente tutte le modifiche necessarie.

Questo principio riduce gli errori manuali, elimina le duplicazioni e garantisce la coerenza dell'intero database.
---

# PRINCIPIO 4

## Gli eventi sono immutabili.

Una volta registrato, un evento operativo non deve essere modificato né eliminato.

Gli eventi costituiscono lo storico ufficiale delle attività svolte e rappresentano la base della tracciabilità del sistema.

Se un evento contiene un errore, la correzione deve avvenire mediante la registrazione di un nuovo evento di rettifica.

Il sistema deve sempre preservare la sequenza cronologica degli eventi realmente accaduti.

Nessuna informazione storica deve essere cancellata.

Questo principio garantisce:

- tracciabilità completa;
- possibilità di audit;
- ricostruzione dello storico;
- affidabilità del database;
- riproducibilità delle operazioni.

La cronologia degli eventi rappresenta la memoria permanente del TPO.
---

# PRINCIPIO 5

## Ogni informazione deve avere una sola fonte ufficiale.

Ogni dato del TPO deve avere un'unica fonte autorevole (Single Source of Truth).

Le stesse informazioni non devono essere duplicate in più fogli, tabelle o configurazioni, salvo quando costituiscano una rappresentazione derivata generata automaticamente dal sistema.

Quando un'informazione deriva da un'altra, il sistema deve rigenerarla automaticamente anziché mantenerne copie indipendenti.

Ad esempio:

- la sigla di una varietà appartiene esclusivamente a MASTER_VARIETA;
- lo stato di un lotto deriva dagli eventi registrati;
- lo stock deriva dai movimenti e dagli eventi operativi;
- le consegne derivano dalle assegnazioni e dagli ordini.

Ogni componente del sistema deve sapere quale sia la fonte ufficiale di ciascun dato.

La duplicazione manuale delle informazioni è vietata perché aumenta il rischio di incoerenze e rende più difficile la manutenzione del sistema.

---

# PRINCIPIO 6

## Ogni operazione deve essere validata prima di essere eseguita.

Nessuna operazione che modifica i dati del TPO deve essere eseguita senza aver superato tutte le verifiche previste.

Le validazioni hanno lo scopo di garantire la coerenza del database e prevenire errori operativi.

A seconda del tipo di operazione, il sistema deve verificare, ove applicabile:

- l'esistenza della varietà;
- l'esistenza del cliente;
- l'esistenza del lotto;
- la correttezza dei codici identificativi;
- il formato delle date;
- il formato delle quantità;
- la disponibilità dello stock;
- la coerenza della fase operativa;
- l'integrità delle relazioni tra i dati.

Se una qualsiasi validazione fallisce, l'operazione deve essere interrotta.

Il sistema non deve correggere automaticamente dati incerti né tentare di aggirare gli errori.

La validazione è parte integrante della logica del TPO e rappresenta una garanzia di affidabilità del sistema.
---

# PRINCIPIO 7

## Il sistema deve essere deterministico.

A parità di dati di ingresso, il sistema deve produrre sempre lo stesso risultato.

Le decisioni del software non devono dipendere da fattori casuali, dallo stato della conversazione, dalla memoria degli agenti di intelligenza artificiale o da informazioni non presenti nelle fonti ufficiali.

Ogni operazione deve essere riproducibile e verificabile.

Se le condizioni iniziali sono identiche, anche il risultato deve essere identico.

Questo principio garantisce:

- prevedibilità del comportamento;
- facilità di verifica;
- affidabilità delle automazioni;
- semplificazione del debug;
- riproducibilità delle elaborazioni.
---

# PRINCIPIO 8

## Ogni dato deve essere completamente tracciabile.

Ogni informazione presente nel sistema deve poter essere ricondotta alla propria origine.

Il TPO deve essere sempre in grado di spiegare:

- da quale evento deriva un dato;
- quando è stato generato;
- quale operazione lo ha modificato;
- quali effetti ha prodotto sul sistema.

Nessuna modifica ai dati deve risultare priva di una motivazione ricostruibile.

La tracciabilità deve consentire di ricostruire la sequenza completa degli eventi che hanno portato allo stato attuale del sistema.

Questo principio garantisce:

- trasparenza delle operazioni;
- possibilità di audit;
- analisi degli errori;
- ricostruzione dello storico;
- fiducia nei dati prodotti dal sistema.
---

# PRINCIPIO 9

## Il sistema deve essere progettato per evolvere.

L'architettura del TPO deve poter essere estesa senza richiedere la riprogettazione del sistema esistente.

Ogni nuova funzionalità deve integrarsi con i principi e i modelli già definiti, privilegiando l'estensione rispetto alla modifica del comportamento esistente.

Il sistema deve poter supportare, nel tempo:

- nuove varietà;
- nuovi prodotti;
- nuovi processi produttivi;
- nuovi magazzini;
- nuove sedi operative;
- nuovi clienti;
- nuovi documenti;
- nuove automazioni;
- nuove integrazioni con sistemi esterni.

L'evoluzione del TPO deve avvenire attraverso l'aggiunta di nuove componenti, evitando modifiche che compromettano il funzionamento delle funzionalità già esistenti.

Ogni scelta progettuale deve privilegiare la scalabilità, la manutenibilità e la compatibilità futura.
---

# PRINCIPIO 11

## Ogni componente software deve avere una responsabilità ben definita.

Il software del TPO deve essere progettato secondo il principio della responsabilità unica.

Ogni modulo, funzione o componente deve svolgere un compito preciso e chiaramente identificabile.

Una componente non deve contenere logiche appartenenti ad ambiti diversi né assumere responsabilità che competono ad altri moduli.

L'organizzazione del software deve favorire:

- chiarezza;
- riutilizzabilità;
- testabilità;
- semplicità di manutenzione;
- facilità di estensione.

La comunicazione tra i diversi componenti deve avvenire attraverso interfacce e regole ben definite, evitando dipendenze non necessarie.

Una struttura modulare riduce la complessità del sistema e rende più semplice l'evoluzione futura del TPO.
---

# PRINCIPIO 12

## Gli agenti di intelligenza artificiale sono soggetti agli stessi principi del sistema.

Gli agenti di intelligenza artificiale che operano all'interno del TPO non costituiscono una fonte decisionale autonoma.

Il loro compito è assistere l'operatore e il software nel rispetto dei principi definiti in questo documento.

In particolare, gli agenti devono:

- utilizzare esclusivamente le fonti ufficiali del TPO per le decisioni operative;
- rispettare la Single Source of Truth;
- non inventare dati;
- non modificare informazioni senza una fonte autorizzata;
- applicare le stesse validazioni previste dal sistema;
- segnalare eventuali incoerenze o anomalie;
- richiedere chiarimenti quando le informazioni disponibili non sono sufficienti.

Gli agenti possono supportare l'analisi, la pianificazione e la generazione di contenuti, ma non devono sostituire le regole operative del TPO.

Ogni comportamento degli agenti deve essere coerente con i principi architetturali del sistema e contribuire a preservarne l'affidabilità.
---

# PRINCIPIO 13

## Il TPO deve semplificare il lavoro dell'operatore, non aumentarlo.

Tower Power Operations nasce con l'obiettivo di trasformare le attività operative in un sistema semplice, affidabile e coerente.

L'operatore deve concentrarsi sul lavoro reale — coltivare, raccogliere, consegnare e prendere decisioni — mentre il sistema si occupa di gestire la complessità amministrativa e operativa.

Ogni nuova funzionalità del TPO deve contribuire a ridurre il lavoro manuale, diminuire il rischio di errore e migliorare la qualità delle informazioni disponibili.

Il principio guida è semplice:

**l'operatore registra un fatto; il sistema ne gestisce le conseguenze.**

Il TPO non deve richiedere all'utente di conoscere quali fogli aggiornare, quali relazioni mantenere o quali calcoli eseguire.

La complessità appartiene al software.

La semplicità appartiene all'operatore.

Ogni evoluzione futura del progetto dovrà essere valutata chiedendosi se rende il lavoro dell'utente più semplice, più sicuro e più efficiente.

Se una nuova funzionalità aumenta inutilmente la complessità operativa senza apportare un beneficio concreto, non è coerente con la filosofia del TPO.

# PRINCIPIO 10

## L'evoluzione del sistema deve preservare la compatibilità.

Ogni modifica al TPO deve essere progettata in modo da non compromettere il funzionamento delle funzionalità esistenti, salvo nei casi in cui una modifica incompatibile sia stata pianificata, documentata e approvata.

Le evoluzioni del sistema devono privilegiare l'estensione rispetto alla sostituzione.

La compatibilità con i dati storici deve essere sempre preservata.

---

**Nota**

I principi definiti in questo documento costituiscono il livello più alto della documentazione del TPO.

Ogni altro documento del progetto (architettura, data dictionary, regole operative, documentazione tecnica e codice sorgente) deve essere coerente con essi.

In caso di conflitto, prevalgono sempre i principi definiti nel presente documento.