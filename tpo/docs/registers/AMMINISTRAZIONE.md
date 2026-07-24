# TPO DOMAIN REGISTER — AMMINISTRAZIONE

## 1. Scopo e autorità

Il presente documento definisce il dominio **AMMINISTRAZIONE** di Tower Power Operations (TPO), il suo lessico ufficiale, le sue responsabilità e i suoi confini permanenti.

Le disposizioni contenute nel presente documento sono normative. Ogni componente, agente, automazione o futura estensione del TPO deve rispettarle.

AMMINISTRAZIONE governa le entità amministrative, i Facts amministrativi e le relazioni amministrative autorevoli, e definisce le regole per la derivazione degli State economici applicabili. Lo State economico rimane sempre Derived. AMMINISTRAZIONE non acquisisce autorità sui Facts, sulla Configuration o sulle entità appartenenti agli altri domini.

## 2. Classificazione delle informazioni

Nel dominio AMMINISTRAZIONE la natura informativa deve essere classificata in modo non ambiguo come Fact, Configuration oppure Derived.

State, Documenti e Rappresentazioni devono rimanere concetti distinti da tale classificazione: lo State è sempre Derived; un Documento è un'entità; una Rappresentazione manifesta un Documento o informazioni derivate. Nessuno di questi concetti deve essere confuso con un altro.

### 2.1 Facts

I **Facts** sono accadimenti amministrativi ufficialmente riconosciuti.

Ogni Fact deve essere:

- registrato una sola volta;
- immutabile;
- tracciabile alla propria origine;
- distinto dall'entità cui si riferisce;
- distinto dallo State che contribuisce a determinare.

La correzione, la rettifica, l'annullamento o la variazione di effetti amministrativi non deve alterare un Fact esistente. Deve produrre uno o più nuovi Facts collegati ai Facts precedenti.

### 2.2 Configuration

La **Configuration** comprende definizioni e parametri ufficiali che determinano l'interpretazione dei Facts amministrativi.

Aliquote, metodi, termini, anagrafiche e altre configurazioni applicabili non sono Facts amministrativi. La loro autorità appartiene al dominio CONFIGURATION.

AMMINISTRAZIONE deve utilizzare la Configuration ufficiale mediante riferimenti e non deve duplicarla, ridefinirla o assumerne l'autorità.

### 2.3 Derived

Le informazioni **Derived** risultano dall'elaborazione deterministica dei Facts e della Configuration ufficiale applicabile.

Le informazioni Derived:

- non sono Facts;
- non possiedono autorità autonoma;
- devono rimanere riconducibili alle fonti da cui derivano;
- devono essere completamente ricostruibili;
- non possono rettificare o sostituire le proprie fonti.

### 2.4 State

Lo **State** è la condizione corrente ricostruita di un'entità o di una relazione amministrativa.

Lo State economico è sempre Derived. Non deve essere registrato come Fact, modificato direttamente o trattato come fonte autonoma.

### 2.5 Documenti

Un **Documento** è un'entità documentale dotata di identità e significato nel proprio dominio.

Un Documento non coincide con:

- il Fact che ne registra la costituzione, l'emissione o un altro accadimento;
- i Facts che ne descrivono la storia;
- lo State ricostruito dai Facts che lo riguardano;
- una sua Rappresentazione.

Un Documento può rappresentare o attestare Facts, relazioni e obbligazioni secondo il significato attribuitogli dal presente documento. Tale funzione non trasforma il Documento nel Fact rappresentato o attestato.

### 2.6 Rappresentazioni

Una **Rappresentazione** è una manifestazione percepibile o trasmissibile di un Documento o di informazioni derivate.

Una Rappresentazione:

- non coincide con il Documento;
- non acquisisce autorità autonoma;
- deve rimanere riconducibile all'entità o alle informazioni che rappresenta;
- non può introdurre, correggere o sostituire Facts.

Il PDF di una Fattura è una Rappresentazione della Fattura e non è la Fattura.

## 3. Responsabilità del dominio

AMMINISTRAZIONE governa le entità amministrative, i Facts amministrativi e le relazioni amministrative autorevoli, e definisce le regole per la derivazione degli State economici applicabili. Lo State economico rimane sempre Derived.

In tale responsabilità rientrano:

- obbligazioni amministrative;
- Fatture;
- Righe Fattura;
- Pagamenti;
- Allocazioni dei Pagamenti;
- rettifiche amministrative;
- riferimenti documentali;
- scadenze documentate;
- State economici derivati.

AMMINISTRAZIONE deve preservare identità, autorità e tracciabilità distinte per ciascuno di tali concetti.

L'appartenenza di un concetto ad AMMINISTRAZIONE non autorizza la duplicazione di Facts appartenenti ad altri domini.

## 4. Confini di dominio

### 4.1 COMMERCIALE

COMMERCIALE governa esclusivamente:

- Ordini;
- Righe Ordine;
- domanda commerciale;
- impegni commerciali.

COMMERCIALE utilizza Clienti e Prodotti mediante riferimenti alle rispettive fonti autorevoli di Configuration.

AMMINISTRAZIONE può utilizzare riferimenti alle entità e ai Facts governati da COMMERCIALE, ma non deve governarne identità, contenuti o State.

### 4.2 OPERATIONS

OPERATIONS governa:

- Produzione;
- Raccolte;
- Assegnazioni;
- Consegne.

AMMINISTRAZIONE può utilizzare riferimenti ai Facts e alle entità operative quando necessari alla tracciabilità amministrativa, ma non deve duplicarli o reinterpretarli come Facts amministrativi.

### 4.3 CONFIGURATION

CONFIGURATION governa:

- Clienti;
- Fornitori;
- Prodotti;
- anagrafiche;
- aliquote;
- metodi;
- termini;
- altre definizioni configurative.

AMMINISTRAZIONE deve applicare esclusivamente la Configuration ufficiale pertinente e non deve incorporarla nei Facts amministrativi come autorità concorrente.

### 4.4 AMMINISTRAZIONE

AMMINISTRAZIONE governa le entità amministrative, i Facts amministrativi e le relazioni amministrative autorevoli, e definisce le regole per la derivazione degli State economici applicabili. Lo State economico rimane sempre Derived.

Le relazioni con COMMERCIALE, OPERATIONS e CONFIGURATION devono avvenire mediante riferimenti alle rispettive fonti autorevoli. Il riferimento non trasferisce l'autorità e non autorizza la copia del contenuto della fonte.

## 5. Vocabolario ufficiale

### 5.1 Documento commerciale

**DOCUMENTO COMMERCIALE** è la categoria generale dei documenti del dominio COMMERCIALE.

Non è un Fact, uno State o una Rappresentazione.

### 5.2 Documento di vendita

Nel modello Tower Power, il DOCUMENTO DI VENDITA è il documento che accompagna e attesta il trasporto e la consegna della merce.

Le espressioni "documento di trasporto" e "documento di consegna" descrivono funzioni del DOCUMENTO DI VENDITA e non identificano entità documentali autonome.

Quando l'operazione non richiede o non prevede l'emissione di una FATTURA, il DOCUMENTO DI VENDITA costituisce il documento amministrativo che attesta l'avvenuta vendita e la relativa consegna.

Il DOCUMENTO DI VENDITA rimane distinto dalla Consegna che attesta e dai Facts commerciali, operativi e amministrativi cui si riferisce.

### 5.3 Fattura

**FATTURA** coincide con il documento fiscale.

È l'entità amministrativa che documenta l'obbligazione economica e fiscale.

La FATTURA non coincide con l'Ordine, la Consegna, il DOCUMENTO DI VENDITA, il Pagamento, i Facts che ne descrivono la storia o una propria Rappresentazione.

### 5.4 Documento amministrativo

**DOCUMENTO AMMINISTRATIVO** è la categoria generale dei documenti del dominio AMMINISTRAZIONE.

Comprende la FATTURA e, nei casi definiti dal presente documento, il DOCUMENTO DI VENDITA che attesta la vendita e la consegna in assenza di FATTURA.

L'appartenenza funzionale del DOCUMENTO DI VENDITA alla categoria DOCUMENTO AMMINISTRATIVO non trasferisce ad AMMINISTRAZIONE l'autorità sui Facts commerciali o operativi rappresentati dal Documento.

### 5.5 Obbligazione amministrativa

L'**OBBLIGAZIONE AMMINISTRATIVA** è l'entità amministrativa che esprime un dovere economico documentato tra soggetti identificati.

La sua esistenza, il suo ammontare documentato, la sua scadenza documentata e il suo adempimento devono risultare da Facts e Documenti autorevoli pertinenti.

L'Obbligazione amministrativa non coincide con la Fattura che la documenta, con il Pagamento che la adempie o con lo State economico che ne rappresenta la condizione corrente.

### 5.6 Riga Fattura

La **RIGA FATTURA** è la componente documentale specifica di una Fattura che qualifica una parte dell'obbligazione documentata.

Ogni Riga Fattura appartiene a una sola Fattura. La sua identità deve rimanere distinta dall'identità della Fattura, del Prodotto, della Riga Ordine, della Consegna e del DOCUMENTO DI VENDITA eventualmente collegati.

I riferimenti utilizzati da una Riga Fattura non trasferiscono alla Riga Fattura l'autorità sui concetti referenziati.

### 5.7 Pagamento

**PAGAMENTO** è il concetto generale che rappresenta un trasferimento di valore ufficialmente riconosciuto con rilevanza amministrativa.

Il Pagamento è un'entità economica distinta:

- dall'Obbligazione amministrativa cui può essere allocato;
- dalla Fattura;
- dal Documento che può attestarlo;
- dalla Ricevuta;
- dai Facts che ne descrivono la storia;
- dallo State economico derivato.

### 5.8 Incasso

**INCASSO** è un Pagamento ricevuto.

INCASSO è una specializzazione di PAGAMENTO. Ogni Incasso è un Pagamento; non ogni Pagamento è necessariamente un Incasso.

La specializzazione qualifica la direzione economica del Pagamento e non modifica la separazione tra Pagamento, Documento, Fact e State.

Il Registro INCASSI costituisce la fonte autorevole dei Pagamenti ricevuti.

Eventuali future fonti generali relative ai PAGAMENTI dovranno riferirsi agli INCASSI senza duplicarne i Facts.

### 5.9 Allocazione del Pagamento

L'**ALLOCAZIONE DEL PAGAMENTO** è la relazione amministrativa che attribuisce, in tutto o in parte, il valore di un Pagamento a una o più Obbligazioni amministrative documentate.

Pagamento, Obbligazione amministrativa e Allocazione del Pagamento devono mantenere identità distinte.

L'Allocazione del Pagamento:

- non modifica il Pagamento originario;
- non modifica la Fattura o l'altro Documento pertinente;
- deve essere rappresentata da Facts amministrativi propri;
- deve poter essere rettificata esclusivamente mediante nuovi Facts;
- concorre alla derivazione degli State economici applicabili.

### 5.10 Rettifica

La **RETTIFICA** è un nuovo accadimento amministrativo ufficiale che corregge, integra, neutralizza o ridefinisce gli effetti di un accadimento precedente senza modificarne o eliminarne i Facts.

Una rettifica deve:

- produrre nuovi Facts;
- riferirsi in modo tracciabile ai Facts o ai Documenti cui si applica;
- preservare integralmente la cronologia precedente;
- concorrere alla nuova derivazione dello State applicabile.

Quando la rettifica richiede un Documento amministrativo, tale Documento deve possedere identità propria e non deve sostituire retroattivamente il Documento precedente.

### 5.11 Riferimento documentale

Il **RIFERIMENTO DOCUMENTALE** è un collegamento tracciabile fra un'entità o un Fact amministrativo e un Documento pertinente.

Il riferimento documentale non duplica il Documento, non ne trasferisce l'autorità e non trasforma il Documento nel Fact cui è collegato.

### 5.12 Scadenza documentata

La **SCADENZA DOCUMENTATA** è il termine temporale attestato da un Documento amministrativo autorevole secondo la Configuration ufficiale applicabile.

La Scadenza documentata appartiene alla responsabilità amministrativa del Documento che la attesta. Non coincide con lo State economico derivato rispetto a tale termine.

Una scadenza calcolata o prevista, ma non attestata da un Documento amministrativo autorevole, è Derived e non è una Scadenza documentata.

### 5.13 Ricevuta

La **RICEVUTA** è un Documento che attesta un Pagamento secondo il proprio significato documentale.

La Ricevuta non è il Pagamento. La sua esistenza non deve essere utilizzata per fondere l'identità del Documento con quella dell'accadimento economico attestato.

### 5.14 State economico

Lo **STATE ECONOMICO** è una condizione corrente derivata dai Facts amministrativi, dalle Allocazioni dei Pagamenti, dalle rettifiche e dalla Configuration ufficiale applicabile.

Ogni State economico:

- è Derived;
- non è un Fact;
- non è un Documento;
- non deve essere modificato direttamente;
- deve essere deterministico, tracciabile e completamente ricostruibile;
- non può correggere le fonti da cui deriva.

## 6. Regole di autorità e immutabilità

### 6.1 Facts amministrativi

I Facts amministrativi costituiscono la cronologia autorevole del dominio AMMINISTRAZIONE.

Nessun Fact amministrativo esistente deve essere modificato o eliminato. Ogni variazione, rettifica o correzione deve essere espressa mediante nuovi Facts collegati alla cronologia precedente.

### 6.2 Fatture definitive

Una Fattura definitiva è immutabile.

Non deve essere riscritta, sovrascritta o alterata. Qualsiasi correzione dei suoi effetti o dei contenuti documentati deve avvenire mediante nuovi Facts e, quando richiesto, mediante un nuovo Documento amministrativo collegato alla Fattura originaria.

L'immutabilità della Fattura definitiva non attribuisce immutabilità alle Rappresentazioni in quanto copie materiali; le Rappresentazioni devono tuttavia rimanere fedeli e riconducibili alla Fattura che rappresentano e non possono modificarne il contenuto autorevole.

### 6.3 Documenti e Facts

Documento e Fact devono rimanere distinti.

La costituzione, l'emissione, la ricezione, la rettifica o ogni altro accadimento relativo a un Documento può essere rappresentato da un Fact. Nessuno di tali Facts coincide con il Documento.

### 6.4 Pagamenti e documenti

Fattura, Pagamento e Ricevuta devono mantenere identità e autorità distinte.

La Fattura documenta un'Obbligazione amministrativa. Il Pagamento rappresenta un trasferimento di valore. La Ricevuta attesta un Pagamento. Nessuna di tali entità sostituisce le altre.

## 7. Principi fondamentali vincolanti

Nel TPO valgono in modo permanente le seguenti separazioni:

- Ordine non è Fattura.
- Consegna non è Fattura.
- Documento di Vendita non è Fattura.
- Fattura non è Pagamento.
- Pagamento non è Ricevuta.
- PDF non è la Fattura.
- Documento non è Fact.
- Gli State economici sono Derived.
- Le Fatture definitive sono immutabili.
- Le rettifiche producono nuovi Facts.

Tali separazioni devono essere preservate anche quando le entità sono collegate, quando una deriva informativamente dall'altra o quando una Rappresentazione le presenta congiuntamente.

## 8. Contenuto escluso

Sono esplicitamente fuori dal dominio AMMINISTRAZIONE:

- contabilità generale;
- piano dei conti;
- registri IVA o IGIC;
- liquidazioni;
- bilanci;
- dichiarazioni fiscali;
- tesoreria completa;
- controllo di gestione completo.

Il dominio non deve essere interpretato o esteso in modo da assumere tali responsabilità.

Il dominio non definisce inoltre:

- procedure operative;
- workflow;
- meccanismi di persistenza;
- strutture fisiche dei dati;
- formati implementativi;
- layout o modalità materiali delle Rappresentazioni;
- regole fiscali o contabili ulteriori rispetto alle distinzioni concettuali qui stabilite.

## 9. Vincoli concettuali permanenti

- Ogni informazione deve conservare una classificazione non ambigua come Fact, Configuration oppure Derived.
- State, Documento e Rappresentazione devono mantenere significati distinti e non devono essere confusi con la natura informativa della propria fonte.
- Ogni entità amministrativa deve mantenere un'identità distinta dai Facts che ne descrivono la storia.
- Ogni riferimento deve puntare alla fonte autorevole senza duplicarne il contenuto o trasferirne l'autorità.
- Ogni relazione tra domini deve preservare il boundary del dominio che governa la fonte.
- Nessun Documento deve essere trattato come prova dell'esistenza di Facts diversi da quelli che è autorizzato ad attestare.
- Nessuna Rappresentazione deve essere trattata come fonte autonoma.
- Nessuno State economico deve essere registrato o corretto come Fact.
- Ogni State economico deve essere ricostruibile dai Facts e dalla Configuration ufficiale applicabile.
- Ogni rettifica deve preservare i Facts e i Documenti precedenti e deve introdurre nuovi Facts tracciabili.
- Nessuna relazione fra Ordine, Consegna, Documento di Vendita, Fattura, Pagamento e Ricevuta deve annullarne le rispettive identità e responsabilità.

## 10. Note architetturali permanenti

AMMINISTRAZIONE è un dominio normativo e non un contenitore indistinto di informazioni economiche, commerciali, operative, fiscali o contabili.

La responsabilità amministrativa nasce dal significato dei Facts e delle entità governate, non dalla loro collocazione o dalla forma della loro Rappresentazione.

Il presente documento non autorizza nuovi Facts, nuovi State o nuove regole oltre a quelli esplicitamente definiti o resi necessari dalle distinzioni normative qui stabilite.
