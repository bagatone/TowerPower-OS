# TPO REGISTER — PRODOTTI

## 1. Register Name

**PRODOTTI**

## 2. Category

**Configuration Registers**

PRODOTTI deve rispettare tutti i vincoli applicabili ai Configuration Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

PRODOTTI rappresenta esclusivamente il concetto **Prodotto** definito in `TPO_DATA_DICTIONARY.md`.

Il Prodotto è la definizione commerciale del bene vendibile che può essere ordinato, assegnato e consegnato. Esprime l'oggetto del fabbisogno commerciale, collega la produzione disponibile alla domanda e costituisce il riferimento dello Stock commerciale.

Il Prodotto è distinto da Varietà e Articolo e non rappresenta una quantità disponibile.

PRODOTTI deve utilizzare riferimenti verso i concetti collegati senza rappresentarli direttamente né duplicarne i contenuti.

## 4. Purpose

Conservare la definizione commerciale autorevole e persistente dei Prodotti utilizzati come riferimenti dagli altri domini TPO.

## 5. Single Responsibility

Conservare esclusivamente l'identità e la definizione commerciale ufficiale dei Prodotti come Configuration persistente.

PRODOTTI non deve conservare Facts operativi, State corrente, disponibilità, quantità, prezzi, origine produttiva o contenuti documentali.

## 6. Origin

**Configuration**

PRODOTTI conserva esclusivamente definizioni e parametri persistenti relativi al Prodotto.

Non rappresenta eventi, non contiene Facts e non materializza direttamente State derivato.

## 7. Writer

PRODOTTI è modificabile esclusivamente mediante operazioni autorizzate che aggiornano la Configuration persistente.

Il contratto definisce esclusivamente i vincoli architetturali e non identifica il componente software incaricato di eseguire tali operazioni.

## 8. Readers

Possono leggere PRODOTTI esclusivamente i componenti autorizzati a consultare la definizione commerciale dei Prodotti o a utilizzarne i riferimenti.

I Readers non possono modificare PRODOTTI mediante operazioni di lettura.

## 9. Logical Key

Ogni Prodotto deve possedere un'identità concettuale stabile che lo distingua dagli altri Prodotti e dai concetti Varietà e Articolo.

La chiave logica non definisce identificativi, codici, SKU o formati implementativi.

## 10. Relationships and References

### Varietà

La fonte autorevole delle Varietà deve conservarne la definizione agronomica.

PRODOTTI può utilizzare riferimenti alle Varietà dalle quali il Prodotto deriva, senza duplicarne caratteristiche biologiche, produttive, Configuration o State.

Una Varietà può dare origine a più Prodotti e un Prodotto può derivare da una o più Varietà, secondo quanto definito in `TPO_DATA_DICTIONARY.md`.

### Riga Ordine

RIGHE_ORDINE deve conservare i Facts del fabbisogno commerciale, il riferimento al Prodotto e la quantità richiesta.

PRODOTTI deve conservare la definizione del Prodotto e non deve contenere domanda commerciale o quantità richieste.

RIGHE_ORDINE deve utilizzare il riferimento al Prodotto senza duplicarne la definizione commerciale.

### Assegnazione

ASSEGNAZIONI deve conservare i Facts dell'allocazione tra Raccolta e Riga Ordine.

Il Prodotto è raggiungibile attraverso il riferimento della Riga Ordine.

I documenti congelati non definiscono per ASSEGNAZIONI un riferimento diretto obbligatorio al Prodotto. PRODOTTI non deve conservare quantità allocate, Facts delle Assegnazioni o regole di compatibilità e matching.

### Raccolta

La fonte autorevole delle Raccolte deve conservarne i Facts produttivi.

La relazione tra Prodotto e Raccolta non è definita come riferimento diretto. PRODOTTI non deve conservare quantità raccolte, qualità ottenuta o altri Facts produttivi.

### Consegna

La fonte autorevole delle Consegne deve conservarne i Facts logistici.

Il Prodotto è raggiungibile attraverso i riferimenti applicabili alle Assegnazioni e alle Righe Ordine.

I documenti congelati non definiscono per CONSEGNE un riferimento diretto obbligatorio al Prodotto. PRODOTTI non deve conservare Facts logistici o quantità consegnate.

### Documenti commerciali

DOCUMENTO_DI_CONSEGNA deve utilizzare i riferimenti ai Prodotti documentati e deve conservare le quantità consegnate documentate.

Le fonti autorevoli dei Documenti commerciali devono conservarne i Facts documentali. PRODOTTI non deve conservare contenuti documentali o Facts dei Documenti commerciali.

### Prezzi, listini e condizioni commerciali

I documenti congelati non attribuiscono prezzi, tariffe, listini o condizioni commerciali a PRODOTTI.

PRODOTTI non deve conservarli né anticiparne la futura fonte autorevole.

### Stock commerciale

Il Prodotto costituisce il riferimento dello Stock commerciale.

Lo Stock commerciale deve rimanere una Derived View non autorevole. PRODOTTI non deve conservarne disponibilità corrente, quantità prenotata, quantità residua, allarmi o altre proiezioni operative.

## 11. Authorized Content

PRODOTTI può contenere esclusivamente:

- l'identità concettuale stabile del Prodotto;
- la definizione commerciale autorevole del bene vendibile;
- la Configuration persistente del Prodotto;
- i riferimenti alle Varietà applicabili;
- le definizioni e i parametri persistenti già riconducibili alla Configuration del Prodotto.

## 12. Forbidden Content

PRODOTTI non deve contenere:

- Facts operativi;
- State corrente o altre informazioni derivate;
- quantità richieste;
- quantità raccolte;
- quantità allocate;
- quantità consegnate;
- Stock commerciale;
- disponibilità corrente, quantità prenotata o quantità residua;
- prezzi, importi, tariffe, listini o condizioni commerciali;
- Ordini o Righe Ordine;
- Assegnazioni o Raccolte;
- Consegne;
- Documenti commerciali;
- Incassi;
- caratteristiche agronomiche delle Varietà;
- Facts produttivi o dettagli di coltivazione;
- regole di compatibilità o matching;
- confezioni, formati di vendita, Set, voci di listino o SKU;
- workflow, procedure operative o logica applicativa.

## 13. Direct Modifiability

PRODOTTI è modificabile esclusivamente mediante operazioni autorizzate sulla Configuration persistente.

Le modifiche non possono trasformare PRODOTTI in una fonte di Facts o State derivato.

## 14. Rectification / Update

- **Modifica della Configuration:** può avvenire esclusivamente mediante operazioni autorizzate.
- **Aggiornamento:** riguarda soltanto la Configuration persistente del Prodotto.
- **Rettifica mediante Facts:** non applicabile a PRODOTTI.

Il presente contratto non disciplina attivazione, disattivazione, sostituzione, versionamento, archiviazione o cancellazione del Prodotto.

## 15. Rebuildability

**Non applicabile.**

PRODOTTI è una fonte autorevole di Configuration e non è una Projection rigenerabile.

Gli eventuali State e le Derived Views riferiti ai Prodotti devono invece essere ricostruibili dalle rispettive fonti autorevoli.

## 16. Conceptual Constraints

- Ogni Prodotto deve mantenere un'identità concettuale stabile.
- Prodotto, Varietà e Articolo devono rimanere concetti distinti.
- PRODOTTI deve conservare esclusivamente Configuration autorevole.
- PRODOTTI non deve contenere Facts o State derivato.
- Le relazioni devono essere rappresentate mediante riferimenti senza duplicare le fonti autorevoli.
- La definizione del Prodotto non deve incorporare domanda, produzione, allocazione, logistica, documentazione, disponibilità o informazioni economiche.
- Lo Stock commerciale deve rimanere una Derived View distinta da PRODOTTI.

## 17. Permanent Architectural Notes

La definizione autorevole del Prodotto e il suo eventuale State commerciale corrente sono concetti distinti.

La classificazione di PRODOTTI come Configuration Registers non attribuisce al Registro i Facts commerciali o produttivi che possono concorrere alla derivazione dello State del Prodotto.

Il presente contratto non definisce:

- la fonte dei Facts che concorrono allo State commerciale del Prodotto;
- il vocabolario dello State;
- la collocazione permanente dell'Unità di misura;
- regole di compatibilità tra Prodotto, Varietà, Raccolta e Assegnazione;
- prezzi, listini o condizioni commerciali;
- attivazione, disattivazione, sostituzione, versionamento, archiviazione o cancellazione;
- identificativi, codici, SKU o rappresentazioni implementative.
