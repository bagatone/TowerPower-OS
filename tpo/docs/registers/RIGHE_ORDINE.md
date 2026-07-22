# TPO REGISTER — RIGHE_ORDINE

## 1. Register Name

**RIGHE_ORDINE**

## 2. Category

**Authoritative Registers**

RIGHE_ORDINE deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

RIGHE_ORDINE rappresenta esclusivamente il concetto **Riga Ordine** definito in `TPO_DATA_DICTIONARY.md`.

RIGHE_ORDINE deve utilizzare riferimenti verso:

- Ordine;
- Prodotto.

RIGHE_ORDINE non deve rappresentare direttamente tali concetti.

## 4. Purpose

RIGHE_ORDINE deve conservare la cronologia autorevole dei Facts che costituiscono e fanno evolvere i fabbisogni commerciali specifici compresi negli Ordini.

## 5. Single Responsibility

RIGHE_ORDINE deve registrare una sola volta i Facts ufficiali relativi al ciclo di vita di ciascuna Riga Ordine.

RIGHE_ORDINE non deve mantenere direttamente lo State corrente della Riga Ordine.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento commerciale ufficiale relativo a una specifica Riga Ordine.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in RIGHE_ORDINE.

## 8. Readers

Possono leggere RIGHE_ORDINE:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance ai percorsi applicabili;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path, quando devono consultare la cronologia autorevole.

I Readers non devono modificare RIGHE_ORDINE.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact commerciale relativo a una Riga Ordine.

Ogni record deve inoltre riferirsi all'identità stabile della Riga Ordine cui appartiene.

L'identità del Fact e l'identità della Riga Ordine devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento;
- l'identità della Riga Ordine collega la cronologia allo stesso fabbisogno commerciale specifico.

L'identità della Riga Ordine deve rimanere distinta dall'identità dell'Ordine cui appartiene.

RIGHE_ORDINE non definisce identificativi implementativi.

## 10. Relationships and References

### Ordine

- ORDINI deve conservare i Facts autorevoli dell'Ordine.
- RIGHE_ORDINE deve utilizzare soltanto il riferimento all'identità stabile dell'Ordine.
- La relazione è obbligatoria: ogni Riga Ordine deve appartenere a un solo Ordine.
- Una Riga Ordine non può esistere senza l'Ordine cui appartiene.
- ORDINI non deve duplicare i contenuti della Riga Ordine.

### Prodotto

- La fonte autorevole del Prodotto deve conservarne l'identità e la definizione commerciale.
- RIGHE_ORDINE deve utilizzare soltanto il relativo riferimento.
- La relazione è obbligatoria: ogni Riga Ordine deve riguardare un Prodotto.
- La Varietà non deve sostituire il Prodotto nella relazione commerciale.

### Pianificazione produttiva

- La fonte autorevole della Pianificazione produttiva deve conservare i propri Facts.
- La Pianificazione produttiva può utilizzare il riferimento alla Riga Ordine quando applicabile.
- La relazione è facoltativa.

### Assegnazione

- La fonte autorevole delle Assegnazioni deve conservare i Facts di allocazione.
- Ogni Assegnazione deve utilizzare il riferimento alla Riga Ordine interessata.
- La relazione è facoltativa nel ciclo di vita della Riga Ordine.
- La quantità allocata deve appartenere all'Assegnazione e non deve essere copiata in RIGHE_ORDINE.

### Consegna

- La fonte autorevole delle Consegne deve conservare i Facts logistici.
- La relazione con la Riga Ordine deve essere indiretta attraverso l'Assegnazione.
- RIGHE_ORDINE non deve duplicare contenuti della Consegna.

### Documento commerciale e Incasso

- Le rispettive fonti autorevoli devono conservare i propri Facts.
- Le relazioni con la Riga Ordine devono rimanere indirette attraverso Assegnazione, Consegna e documentazione commerciale.
- RIGHE_ORDINE non deve contenere Documenti commerciali o Incassi e non deve duplicarne le informazioni.

### Cliente

- La fonte autorevole dell'identità del Cliente deve conservarne l'autorità.
- La relazione con la Riga Ordine deve essere indiretta attraverso l'Ordine.
- RIGHE_ORDINE non deve duplicare l'identità o lo State del Cliente.

### Stock commerciale

- Lo Stock commerciale deve rimanere una Derived View non autorevole.
- RIGHE_ORDINE non deve conservarne copie o riferimenti persistenti diretti.
- Gli effetti commerciali applicabili devono rimanere ricostruibili dalle rispettive fonti autorevoli.

## 11. Authorized Content

RIGHE_ORDINE può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di un fabbisogno commerciale specifico;
- l'identità concettuale della Riga Ordine;
- il riferimento all'Ordine;
- il riferimento al Prodotto;
- la quantità richiesta e la relativa Unità di misura;
- gli accadimenti che fanno evolvere il fabbisogno commerciale;
- le variazioni e le rettifiche collegate ai Facts precedenti;
- l'annullamento come nuovo Fact, quando ufficialmente registrato;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

RIGHE_ORDINE non deve contenere:

- Facts o State complessivo dell'Ordine;
- dati o State del Cliente;
- Varietà in sostituzione del Prodotto;
- quantità allocate;
- Assegnazioni;
- Raccolte;
- Consegne;
- Documenti commerciali;
- Incassi;
- Stock commerciale;
- pianificazione o attività produttive;
- State corrente derivato della Riga Ordine;
- Configuration;
- richieste particolari non definite nel Data Dictionary;
- copie descrittive di altre fonti autorevoli;
- logica, workflow o regole operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione deve essere rappresentata mediante un nuovo Fact conforme al ciclo della Riga Ordine.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** deve avvenire mediante l'aggiunta di un nuovo Fact relativo alla stessa Riga Ordine.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo.
- **Variazione:** deve essere rappresentata mediante un nuovo Fact e non deve riscrivere la cronologia precedente.
- **Annullamento:** deve costituire un nuovo Fact del ciclo commerciale e non una rettifica o una modifica del Fact originario.

## 15. Rebuildability

**Non applicabile.**

RIGHE_ORDINE è un Authoritative Register e non è una proiezione rigenerabile.

L'eventuale State corrente delle Righe Ordine deve essere ricostruibile dai Facts conservati in RIGHE_ORDINE e dai Facts autorevoli delle Assegnazioni e delle Consegne applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- Ogni Riga Ordine deve appartenere a un solo Ordine.
- Una Riga Ordine non può esistere senza l'Ordine cui appartiene.
- Ogni Ordine deve essere considerato costituito soltanto quando è associato ad almeno una Riga Ordine.
- Ogni Riga Ordine deve riguardare un Prodotto.
- Prodotto e Varietà devono rimanere concettualmente distinti.
- Quantità richiesta e Unità di misura devono appartenere alla Riga Ordine.
- La quantità allocata deve appartenere all'Assegnazione.
- RIGHE_ORDINE deve costituire la fonte autorevole dei Facts della Riga Ordine, non del suo State derivato.
- La cancellazione fisica dei Facts non deve essere ammessa.
- I riferimenti non devono duplicare le informazioni delle fonti collegate.

## 17. Permanent Architectural Notes

L'entità Riga Ordine e i Facts relativi alla Riga Ordine non sono sinonimi: l'entità evolve nel tempo, mentre ciascun Fact che ne descrive la storia rimane immutabile.

RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte: il primo conserva i Facts del fabbisogno commerciale specifico; il secondo conserva i Facts dell'impegno commerciale complessivo.

Questo documento non governa i nomi concreti degli eventi, il vocabolario dello State, i nomi dei futuri Registri o i dettagli implementativi delle chiavi.
