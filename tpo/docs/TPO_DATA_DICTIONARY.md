# TPO DATA DICTIONARY — MODELLO CONCETTUALE

## 1. Scopo

Questo documento definisce il modello concettuale ufficiale del dominio Tower Power Operations (TPO).

Descrive:

- le entità del dominio;
- il loro significato e la loro responsabilità;
- la loro identità concettuale e il loro ciclo di vita ad alto livello;
- le relazioni e le associazioni;
- le proiezioni derivate;
- i concetti trasversali.

Il modello è indipendente dalla tecnologia e dalla rappresentazione fisica dei dati.

## 2. Principi del modello concettuale

Il dominio distingue:

- **entità:** concetti con identità, responsabilità e ciclo di vita propri;
- **Facts:** accadimenti operativi immutabili che spiegano l'evoluzione del dominio;
- **State:** condizione corrente di un'entità o di una proiezione;
- **Configuration:** definizioni e parametri ufficiali che governano il dominio;
- **associazioni:** relazioni dotate di significato proprio;
- **proiezioni derivate:** rappresentazioni ricostruibili dalle fonti autorevoli.

Un'entità non coincide con la sua rappresentazione. Calendari, riepiloghi e disponibilità calcolate non diventano fonti autorevoli autonome quando derivano da Facts o da altre entità.

## 3. Mappa dei domini

Il modello comprende:

- **dominio commerciale:** Cliente, Ordine ricorrente, Ordine, Riga Ordine e Consegna;
- **dominio produttivo:** Varietà, Prodotto, Pianificazione produttiva, Semina, Lotto, Raccolta e Torre;
- **dominio magazzino e risorse:** Articolo, Ricetta di produzione, Fornitore e Movimento di magazzino;
- **documenti commerciali:** Documento commerciale, Documento di consegna, Documento di vendita e Incasso;
- **associazioni:** Assegnazione;
- **proiezioni derivate:** Calendario di produzione, Inventario, Stock commerciale e viste operative;
- **concetti trasversali:** Actor, Problema Operativo, Quantità, Unità di misura, Stato, Qualità e Priorità.

## 4. Dominio commerciale

### 4.1 Cliente

**Definizione.** Il Cliente è la controparte commerciale che esprime una domanda e riceve Consegne.

**Responsabilità.** Rappresentare il soggetto commerciale cui appartengono Ordini e Ordini ricorrenti e cui sono destinate le Consegne.

**Identità concettuale.** È distinta dagli impegni commerciali, dalle attività produttive e dai documenti che la riguardano.

**Ciclo di vita ad alto livello.** Esiste come controparte riconosciuta e mantiene nel tempo la propria condizione commerciale.

**Principali relazioni.** Può definire Ordini ricorrenti, effettuare Ordini, ricevere Consegne ed essere oggetto di un Problema Operativo.

**Origine dello State.** Il suo State deriva dai Facts commerciali ufficiali che lo riguardano.

**Cosa non rappresenta.** Non rappresenta Ordini, pianificazione, produzione, disponibilità di prodotto o documenti commerciali.

### 4.2 Ordine ricorrente

**Definizione.** L'Ordine ricorrente è un impegno commerciale ripetitivo dal quale possono derivare Ordini nel tempo.

**Responsabilità.** Esprimere il Cliente, la periodicità e il fabbisogno commerciale concordato.

**Identità concettuale.** È l'impegno ricorrente, distinto da ciascun Ordine concreto che ne deriva.

**Ciclo di vita ad alto livello.** Viene definito, resta applicabile nel periodo previsto e può cessare di produrre nuova domanda.

**Principali relazioni.** Appartiene a un Cliente e può dare origine a più Ordini.

**Origine dello State.** Il suo State deriva dai Facts ufficiali relativi alla sua definizione e alla sua validità.

**Cosa non rappresenta.** Non rappresenta un singolo Ordine, una Riga Ordine o una Pianificazione produttiva.

### 4.3 Ordine

**Definizione.** L'Ordine è una richiesta commerciale concreta di un Cliente.

**Responsabilità.** Rappresentare l'impegno commerciale complessivo, raggruppare una o più Righe Ordine e costituire l'origine della domanda da soddisfare.

**Identità concettuale.** È l'unità commerciale che riunisce i fabbisogni specifici espressi dalle proprie Righe Ordine.

**Ciclo di vita ad alto livello.** Viene espresso, attraversa il proprio ciclo commerciale ed è progressivamente soddisfatto o concluso secondo i Facts ufficiali.

**Principali relazioni.** Appartiene a un Cliente, può derivare da un Ordine ricorrente ed è composto da una o più Righe Ordine.

**Origine dello State.** Il suo State deriva dai Facts ufficiali che riguardano l'Ordine e le sue Righe Ordine.

**Cosa non rappresenta.** Non contiene direttamente Prodotti e quantità e non coincide con Consegna, Assegnazione o Documento commerciale.

### 4.4 Riga Ordine

**Definizione.** La Riga Ordine è un fabbisogno commerciale specifico all'interno di un Ordine.

**Responsabilità.** Collegare l'Ordine a un Prodotto, esprimere la quantità richiesta e offrire il riferimento commerciale per Pianificazione produttiva e Assegnazioni.

**Identità concettuale.** È distinta dalle altre righe dello stesso Ordine e dal Prodotto cui si riferisce.

**Ciclo di vita ad alto livello.** Nasce con il fabbisogno commerciale e procede verso il soddisfacimento attraverso pianificazione, allocazione e consegna.

**Principali relazioni.** Appartiene a un solo Ordine, riguarda un Prodotto e può essere collegata a Pianificazione produttiva e Assegnazioni.

**Origine dello State.** Il suo State deriva dai Facts relativi al fabbisogno, alle Assegnazioni e alle Consegne applicabili.

**Cosa non rappresenta.** Non è un Ordine completo, un'allocazione fisica o una Consegna.

### 4.5 Consegna

**Definizione.** La Consegna è l'adempimento logistico di uno o più impegni commerciali.

**Responsabilità.** Raggruppare le Assegnazioni consegnate insieme, collegare la produzione allocata al destinatario commerciale e dare origine al Documento di consegna.

**Identità concettuale.** È l'attività logistica concreta, distinta dalla domanda, dall'allocazione e dai documenti che produce.

**Ciclo di vita ad alto livello.** Viene predisposta, eseguita e conclusa; il suo esito alimenta lo State commerciale.

**Principali relazioni.** È destinata a un Cliente, può comprendere più Assegnazioni, dà origine a un Documento di consegna e può essere oggetto di un Problema Operativo.

**Origine dello State.** Il suo State deriva dai Facts logistici ufficiali che ne descrivono avanzamento ed esito.

**Cosa non rappresenta.** Non coincide con Ordine, Assegnazione, Documento commerciale o Incasso.

## 5. Dominio produttivo

### 5.1 Varietà

**Definizione.** La Varietà rappresenta la coltura agronomica e ne definisce le caratteristiche biologiche e produttive.

**Responsabilità.** Fornire la definizione agronomica ufficiale utilizzata dal dominio produttivo.

**Identità concettuale.** È determinata dal concetto agronomico che rappresenta ed è distinta da Prodotto e Articolo.

**Ciclo di vita ad alto livello.** Viene riconosciuta come definizione di dominio e rimane utilizzabile finché appartiene alla Configuration ufficiale.

**Principali relazioni.** Può essere impiegata in Semine e Lotti, può dare origine a più Prodotti e può essere oggetto di un Problema Operativo.

**Origine dello State.** La sua condizione corrente deriva dalla Configuration ufficiale e dai Facts che ne modificano l'applicabilità.

**Cosa non rappresenta.** Non rappresenta ciò che viene venduto né una referenza generica gestita dal sistema.

### 5.2 Prodotto

**Definizione.** Il Prodotto rappresenta ciò che può essere ordinato, assegnato e consegnato.

**Responsabilità.** Esprimere l'oggetto del fabbisogno commerciale, collegare la produzione disponibile alla domanda e costituire il riferimento dello Stock commerciale.

**Identità concettuale.** È la definizione commerciale del bene vendibile ed è distinta da Varietà e Articolo.

**Ciclo di vita ad alto livello.** Entra nel dominio commerciale, resta ordinabile secondo la Configuration applicabile e può cessare di esserlo.

**Principali relazioni.** Può derivare da una o più Varietà, può essere richiesto da più Righe Ordine e alimenta lo Stock commerciale.

**Origine dello State.** La sua condizione commerciale deriva dalla Configuration ufficiale e dai Facts commerciali e produttivi applicabili.

**Cosa non rappresenta.** Non rappresenta una coltura agronomica, un Articolo generico o una quantità disponibile.

### 5.3 Pianificazione produttiva

**Definizione.** La Pianificazione produttiva rappresenta il fabbisogno futuro di produzione necessario a soddisfare la domanda e gli obiettivi approvati.

**Responsabilità.** Collegare domanda, disponibilità e fabbisogno produttivo e dare origine alle attività produttive previste.

**Identità concettuale.** È un'intenzione produttiva riconoscibile, distinta dalle attività realmente eseguite.

**Ciclo di vita ad alto livello.** Viene formulata, può evolvere con il fabbisogno e trova attuazione nelle attività produttive.

**Principali relazioni.** Può riferirsi a Righe Ordine, Prodotti e Varietà e può dare origine a una o più Semine.

**Origine dello State.** Il suo State deriva dai Facts di pianificazione e dalle attività produttive che la attuano.

**Cosa non rappresenta.** Non rappresenta una Semina eseguita, un Lotto, una Raccolta o il Calendario di produzione.

### 5.4 Semina

**Definizione.** La Semina rappresenta un'operazione produttiva reale che avvia una coltivazione.

**Responsabilità.** Registrare l'avvio produttivo, la Varietà coinvolta e l'origine dei Lotti risultanti.

**Identità concettuale.** È la specifica attività produttiva eseguita, distinta dalla Pianificazione produttiva e dai Lotti generati.

**Ciclo di vita ad alto livello.** Viene eseguita e produce i propri effetti produttivi attraverso i Lotti.

**Principali relazioni.** Può attuare una Pianificazione produttiva, riguarda una Varietà, può generare uno o più Lotti ed essere oggetto di un Problema Operativo.

**Origine dello State.** Il suo State deriva dai Facts produttivi ufficiali relativi alla sua esecuzione e ai suoi effetti.

**Cosa non rappresenta.** Non rappresenta un piano, un Lotto, una Raccolta o un Prodotto vendibile.

### 5.5 Lotto

**Definizione.** Il Lotto è l'unità minima di tracciabilità della coltura.

**Responsabilità.** Conservare il collegamento tra Semina, Varietà, ciclo della coltura, Raccolte, risultati ed eventuali istanze di Problema Operativo.

**Identità concettuale.** È la specifica unità produttiva tracciata a partire da una Semina.

**Ciclo di vita ad alto livello.** Origina da una Semina, attraversa il ciclo della coltura e può produrre zero o più Raccolte.

**Principali relazioni.** Deriva da una Semina, riguarda una Varietà, può produrre Raccolte ed essere oggetto di un Problema Operativo.

**Origine dello State.** Il suo State deriva dai Facts produttivi ufficiali che ne descrivono l'evoluzione.

**Cosa non rappresenta.** Non rappresenta un Prodotto venduto o una disponibilità commerciale.

### 5.6 Raccolta

**Definizione.** La Raccolta rappresenta il risultato di un'operazione di raccolta eseguita su un Lotto.

**Responsabilità.** Esprimere quantità e qualità ottenute, preservarne l'origine produttiva e alimentare disponibilità, Assegnazioni ed effetti di magazzino applicabili.

**Identità concettuale.** È lo specifico risultato produttivo ottenuto da un Lotto.

**Ciclo di vita ad alto livello.** Si forma con l'operazione di raccolta e viene progressivamente allocata o assorbita dagli altri Facts ufficiali.

**Principali relazioni.** Deriva da un Lotto, contribuisce alla disponibilità di Prodotto e può alimentare più Assegnazioni.

**Origine dello State.** Il suo State deriva dal Fact di raccolta e dai Facts successivi che ne impiegano la quantità.

**Cosa non rappresenta.** Non rappresenta una Riga Ordine, un'Assegnazione, una Consegna o lo Stock commerciale.

### 5.7 Torre

**Definizione.** La Torre è una struttura fisica di produzione alla quale possono riferirsi attività e istanze di Problema Operativo.

**Responsabilità.** Rappresentare il contesto produttivo fisico rilevante.

**Identità concettuale.** È la specifica struttura produttiva riconosciuta nel dominio.

**Ciclo di vita ad alto livello.** Entra nel perimetro produttivo, permane mentre è rilevante e può cambiare condizione attraverso Facts ufficiali.

**Principali relazioni.** Può essere collegata ad attività produttive e a un Problema Operativo.

**Origine dello State.** Il suo State deriva dai Facts ufficiali relativi alla struttura e alle attività che la interessano.

**Cosa non rappresenta.** Non rappresenta un modello organizzativo, una Semina, un Lotto o una risorsa di magazzino.

## 6. Dominio magazzino e risorse

### 6.1 Articolo

**Definizione.** L'Articolo rappresenta qualsiasi referenza gestita da TPO.

**Responsabilità.** Rappresentare in modo aperto e dinamico le referenze rilevanti per risorse, ricette, movimenti e fornitura.

**Identità concettuale.** È la specifica referenza di dominio ed è distinta da Varietà e Prodotto.

**Ciclo di vita ad alto livello.** Viene introdotto come dato di dominio, resta disponibile finché applicabile e può cessare di essere utilizzato senza cambiare il modello concettuale.

**Principali relazioni.** Può partecipare a Ricette di produzione, relazioni con Fornitori e Movimenti di magazzino, contribuire all'Inventario ed essere oggetto di un Problema Operativo.

**Origine dello State.** La sua condizione deriva dalla Configuration ufficiale e dai Facts che ne descrivono l'utilizzo.

**Cosa non rappresenta.** Non è un elenco fisso, un elemento dell'architettura, una Varietà o necessariamente un Prodotto.

### 6.2 Ricetta di produzione

**Definizione.** La Ricetta di produzione rappresenta la Configuration delle risorse necessarie a una produzione o a una sua fase.

**Responsabilità.** Collegare la produzione agli Articoli richiesti ed esprimerne il fabbisogno secondo una base produttiva.

**Identità concettuale.** È una definizione produttiva ufficiale distinta dalle singole attività e dai consumi effettivi.

**Ciclo di vita ad alto livello.** Viene definita, resta applicabile nel proprio ambito e può essere sostituita da una diversa definizione ufficiale.

**Principali relazioni.** Collega una produzione o una sua fase agli Articoli necessari e supporta Pianificazione produttiva e verifica delle risorse.

**Origine dello State.** La sua condizione deriva dalla Configuration ufficiale.

**Cosa non rappresenta.** Non rappresenta un Movimento di magazzino, l'Inventario o un'attività produttiva eseguita.

### 6.3 Fornitore

**Definizione.** Il Fornitore è il soggetto dal quale possono essere ottenuti Articoli o risorse.

**Responsabilità.** Rappresentare la controparte di approvvigionamento e il suo rapporto con gli Articoli fornibili.

**Identità concettuale.** È distinta dal Cliente e dagli Articoli cui è collegata.

**Ciclo di vita ad alto livello.** Viene riconosciuto come controparte di approvvigionamento e mantiene nel tempo la propria condizione.

**Principali relazioni.** Può fornire uno o più Articoli.

**Origine dello State.** Il suo State deriva dai Facts ufficiali di approvvigionamento e dalla Configuration applicabile.

**Cosa non rappresenta.** Non rappresenta un Cliente, un Articolo o l'Inventario.

### 6.4 Movimento di magazzino

**Definizione.** Il Movimento di magazzino è un Fact che modifica la quantità di una risorsa fisica.

**Responsabilità.** Esprimere la variazione di un Articolo, la relativa causa e la cronologia da cui deriva l'Inventario.

**Identità concettuale.** È lo specifico accadimento che determina una variazione di magazzino.

**Ciclo di vita ad alto livello.** Si forma quando avviene la variazione e permane come Fact immutabile.

**Principali relazioni.** Riguarda un Articolo, può derivare da Facts produttivi o logistici e contribuisce all'Inventario.

**Origine dello State.** In quanto Fact, non possiede uno State operativo modificabile; il suo riconoscimento deriva dalla registrazione ufficiale dell'accadimento.

**Cosa non rappresenta.** Non rappresenta la quantità corrente dell'Inventario o la disponibilità dello Stock commerciale.

## 7. Documenti commerciali

### 7.1 Documento commerciale

**Definizione.** Il Documento commerciale è il concetto astratto comune ai documenti che formalizzano un passaggio del flusso commerciale.

**Responsabilità.** Fornire il significato condiviso alle proprie specializzazioni e collegare ciascun documento al passaggio commerciale documentato.

**Identità concettuale.** È un'astrazione; le identità concrete appartengono al Documento di consegna e al Documento di vendita.

**Ciclo di vita ad alto livello.** Non ha un ciclo autonomo: il ciclo appartiene alle sue specializzazioni.

**Principali relazioni.** Generalizza Documento di consegna e Documento di vendita.

**Origine dello State.** Non possiede uno State autonomo separato da quello delle specializzazioni.

**Cosa non rappresenta.** Non è istanziato direttamente e non coincide con attività fisica, Consegna o Incasso.

### 7.2 Documento di consegna

**Definizione.** Il Documento di consegna è la specializzazione operativa primaria del Documento commerciale.

**Responsabilità.** Derivare dalla Consegna, documentare Prodotti e quantità consegnati e costituire la base del Documento di vendita quando richiesto.

**Identità concettuale.** È il documento specifico associato alla Consegna che formalizza.

**Ciclo di vita ad alto livello.** Origina dalla Consegna, documenta il relativo passaggio e può dare origine a un Documento di vendita.

**Principali relazioni.** Deriva da una Consegna ed è origine del Documento di vendita quando necessario.

**Origine dello State.** Il suo State deriva dai Facts documentali ufficiali e dalla Consegna di origine.

**Cosa non rappresenta.** Non rappresenta la Consegna fisica, un Documento di vendita o un Incasso.

### 7.3 Documento di vendita

**Definizione.** Il Documento di vendita è la specializzazione facoltativa del Documento commerciale richiesta per formalizzare la vendita.

**Responsabilità.** Derivare dal Documento di consegna quando necessario e rappresentare il passaggio documentale della vendita.

**Identità concettuale.** È il documento specifico di vendita, distinto dal Documento di consegna da cui deriva.

**Ciclo di vita ad alto livello.** Viene prodotto quando richiesto a partire dal Documento di consegna e segue il proprio ciclo documentale.

**Principali relazioni.** Deriva da uno o più Documenti di consegna ed è collegato agli Incassi pertinenti.

**Origine dello State.** Il suo State deriva dai Facts documentali e commerciali ufficiali che lo riguardano.

**Cosa non rappresenta.** Non è sempre richiesto, non è il Documento di consegna e non rappresenta l'Incasso.

### 7.4 Incasso

**Definizione.** L'Incasso rappresenta il pagamento ricevuto nel flusso commerciale.

**Responsabilità.** Rappresentare il valore effettivamente ricevuto e collegarlo al passaggio documentale cui si riferisce.

**Identità concettuale.** È il singolo fatto economico riconosciuto come pagamento ricevuto.

**Ciclo di vita ad alto livello.** Si forma al ricevimento del pagamento e permane come fatto distinto dai documenti commerciali.

**Principali relazioni.** Si collega al Documento di vendita quando presente e al passaggio documentale pertinente.

**Origine dello State.** In quanto fatto economico, deriva dal ricevimento ufficialmente riconosciuto del pagamento.

**Cosa non rappresenta.** Non rappresenta Consegna, Documento di consegna o Documento di vendita.

Il flusso documentale ufficiale è:

```text
CONSEGNA
↓
DOCUMENTO DI CONSEGNA
↓
DOCUMENTO DI VENDITA, QUANDO RICHIESTO
↓
INCASSO
```

## 8. Associazioni

### 8.1 Assegnazione

**Definizione.** L'Assegnazione è l'associazione che rappresenta l'allocazione fisica di una parte della produzione.

**Responsabilità.** Collegare una Raccolta a una Riga Ordine, esprimere la quantità allocata e collegarsi a una Consegna quando applicabile.

**Identità concettuale.** È la specifica allocazione fisica tra origine produttiva e fabbisogno commerciale.

**Ciclo di vita ad alto livello.** Nasce con l'allocazione della quantità e concorre alla Consegna quando applicabile.

**Principali relazioni.** Collega Raccolta, Riga Ordine, quantità allocata e, quando applicabile, Consegna.

**Origine dello State.** Il suo State deriva dai Facts ufficiali di allocazione e consegna.

**Cosa non rappresenta.** Non è soltanto una prenotazione e non coincide con Raccolta, Riga Ordine o Consegna.

## 9. Proiezioni derivate

### 9.1 Calendario di produzione

Il **Calendario di produzione** non è un'entità fondamentale. È una proiezione temporale derivata dalla Pianificazione produttiva e dalle attività operative. Organizza Facts e State rilevanti senza diventare fonte autorevole autonoma.

### 9.2 Inventario

L'**Inventario** è la proiezione dello State corrente delle risorse fisiche. Deriva dai Movimenti di magazzino e non sostituisce la loro cronologia autorevole.

### 9.3 Stock commerciale

Lo **Stock commerciale** rappresenta la disponibilità commerciale corrente del Prodotto vendibile. Deriva da Raccolte, Assegnazioni, Consegne e altri Facts ufficiali applicabili.

Lo Stock commerciale non costituisce un registro autorevole e non coincide con l'Inventario: il primo riguarda la disponibilità commerciale dei Prodotti, il secondo lo State delle risorse fisiche.

### 9.4 Viste operative

Briefing, riepiloghi e altre viste operative presentano informazioni derivate. Non sono entità fondamentali e non acquisiscono autorità autonoma.

## 10. Relazioni concettuali

### 10.1 Domanda commerciale

```text
CLIENTE
├── definisce → ORDINE RICORRENTE
└── effettua → ORDINE
                  ↓
             RIGA ORDINE
                  ↓
               PRODOTTO
```

- Un Cliente può definire Ordini ricorrenti ed effettuare Ordini.
- Un Ordine ricorrente può dare origine a più Ordini nel tempo.
- Un Ordine contiene una o più Righe Ordine.
- Ogni Riga Ordine esprime un fabbisogno riferito a un Prodotto.

### 10.2 Produzione

```text
RIGA ORDINE
↓
PIANIFICAZIONE PRODUTTIVA
↓
SEMINA
↓
LOTTO
↓
RACCOLTA
```

- La domanda contribuisce alla Pianificazione produttiva.
- Una Pianificazione produttiva può dare origine a una o più Semine.
- Una Semina può generare uno o più Lotti.
- Un Lotto può produrre zero o più Raccolte.
- Un Prodotto può derivare da una o più Varietà e una Varietà può dare origine a più Prodotti.

### 10.3 Allocazione e consegna

```text
RACCOLTA
↓
ASSEGNAZIONE
├── → RIGA ORDINE
└── → CONSEGNA, QUANDO APPLICABILE
```

- Una Raccolta può alimentare più Assegnazioni.
- Ogni Assegnazione collega una quantità fisica a una Riga Ordine.
- Una Consegna può comprendere più Assegnazioni.

### 10.4 Magazzino e disponibilità

```text
ARTICOLO
↓
MOVIMENTO DI MAGAZZINO
↓
INVENTARIO
```

```text
RACCOLTE + ASSEGNAZIONI + CONSEGNE + ALTRI FACTS UFFICIALI
↓
STOCK COMMERCIALE
```

- I Movimenti di magazzino determinano lo State dell'Inventario.
- I Facts commerciali e produttivi applicabili determinano lo Stock commerciale.

### 10.5 Documenti e incassi

Il flusso e le relazioni fra Consegna, Documento di consegna, Documento di vendita e Incasso sono definiti nella sezione “Documenti commerciali”.

## 11. Concetti trasversali

### 11.1 Actor

**Definizione.** L'Actor è il soggetto che compie o conferma un'attività.

**Responsabilità.** Attribuire l'attività al soggetto responsabile e contribuire alla tracciabilità.

**Identità concettuale.** È il soggetto riconoscibile, persona o sistema, cui viene attribuita l'attività.

**Ciclo di vita ad alto livello.** È riconosciuto nel dominio mentre può essere origine o conferma di attività.

**Principali relazioni.** Si collega alle attività che compie o conferma.

**Origine dello State.** La sua condizione deriva dai Facts ufficiali che ne determinano l'applicabilità come soggetto.

**Cosa non rappresenta.** Non introduce un modello organizzativo complesso di ruoli, gerarchie o operatori.

### 11.2 Problema Operativo

**Definizione.** Il Problema Operativo è un'entità trasversale che rappresenta un'anomalia, un impedimento o una condizione da gestire.

**Responsabilità.** Descrivere la condizione osservata, collegarla alle entità interessate e renderne tracciabili gestione ed effetti.

**Identità concettuale.** È la specifica condizione operativa riconosciuta, distinta dalle entità cui si riferisce.

**Ciclo di vita ad alto livello.** Viene rilevato, attraversa la gestione e viene chiuso.

**Principali relazioni.** Può riferirsi, fra gli altri, a Lotto, Semina, Torre, Articolo, Consegna, Cliente e Varietà.

**Origine dello State.** Il suo State deriva dai Facts ufficiali di rilevazione, gestione e chiusura.

**Cosa non rappresenta.** Non appartiene esclusivamente al Lotto e non sostituisce una diagnosi non confermata.

### 11.3 Quantità e Unità di misura

Una **Quantità** esprime un valore associato a un'**Unità di misura**. Sono concetti di valore condivisi da fabbisogni, produzione, allocazioni, movimenti e disponibilità; non sono entità operative autonome.

### 11.4 Stato, Qualità e Priorità

**Stato**, **Qualità** e **Priorità** sono classificazioni applicabili alle entità pertinenti. Non sono entità fondamentali e non possiedono un ciclo autonomo rispetto al concetto che qualificano.

## 12. Ambiguità ancora aperte

Il modello approvato non definisce ulteriormente:

- i criteri che determinano il collegamento tra Varietà e Prodotto;
- l'eventuale relazione concettuale tra Prodotto e Articolo;
- le condizioni di applicabilità del Documento di vendita;
- quali altri Facts ufficiali, oltre a Raccolte, Assegnazioni e Consegne, concorrano allo Stock commerciale.

Questi punti restano non specificati. Il presente documento non assume decisioni ulteriori.

## 13. Autorità documentale

Questo documento è la fonte autorevole per:

- significato e responsabilità delle entità del dominio;
- identità concettuali e cicli di vita ad alto livello;
- associazioni e relazioni concettuali;
- proiezioni derivate;
- concetti trasversali.

Principi architetturali, flussi di orchestrazione, regole operative, rappresentazione fisica dei dati e stato del progetto sono governati dai rispettivi documenti autorevoli.
