# TPO REGISTER — ORDINI

## 1. Register Name

**ORDINI**

## 2. Category

**Authoritative Registers**

ORDINI deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

ORDINI rappresenta esclusivamente il concetto **Ordine** definito in `TPO_DATA_DICTIONARY.md`.

ORDINI può utilizzare riferimenti verso:

- Cliente;
- Ordine ricorrente, quando applicabile;
- Riga Ordine.

ORDINI non deve rappresentare direttamente tali concetti.

## 4. Purpose

ORDINI deve conservare la cronologia autorevole dei Facts che costituiscono e fanno evolvere gli Ordini.

## 5. Single Responsibility

ORDINI deve registrare una sola volta i Facts ufficiali relativi al ciclo di vita di ciascun Ordine.

ORDINI non deve mantenere direttamente lo State corrente dell'Ordine.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento commerciale ufficiale relativo a uno specifico Ordine.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in ORDINI.

## 8. Readers

Possono leggere ORDINI:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance ai percorsi applicabili;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path, quando devono consultare la cronologia autorevole.

I Readers non devono modificare ORDINI.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact commerciale relativo a un Ordine.

Ogni record deve inoltre riferirsi all'identità stabile dell'Ordine cui appartiene.

L'identità del Fact e l'identità dell'Ordine devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento;
- l'identità dell'Ordine collega la cronologia alla stessa richiesta commerciale concreta.

ORDINI non definisce identificativi implementativi.

## 10. Relationships and References

### Cliente

- La fonte autorevole dell'identità del Cliente deve conservarne l'autorità.
- ORDINI deve utilizzare soltanto il relativo riferimento.
- La relazione è obbligatoria: ogni Ordine appartiene a un Cliente.

### Ordine ricorrente

- La fonte autorevole dell'Ordine ricorrente deve conservarne i Facts.
- ORDINI può utilizzare il relativo riferimento quando l'Ordine ne deriva.
- La relazione è facoltativa.

### Riga Ordine

- La fonte autorevole delle Righe Ordine deve conservarne i Facts.
- Ogni Riga Ordine deve utilizzare il riferimento all'Ordine cui appartiene.
- La relazione concettuale è obbligatoria: ogni Ordine deve essere composto da una o più Righe Ordine.
- Prodotti e quantità devono appartenere alle Righe Ordine e non devono essere copiati in ORDINI.

### Consegna e Assegnazione

- Le rispettive fonti autorevoli devono conservare i Facts logistici e di allocazione.
- ORDINI non deve copiarne il contenuto.
- Il collegamento al soddisfacimento commerciale deve avvenire attraverso Righe Ordine e Assegnazioni secondo le relazioni definite nel Data Dictionary.
- Consegna e Assegnazione non sono necessarie alla nascita dell'Ordine.

### Documenti commerciali e Incasso

- Le rispettive fonti autorevoli devono conservare i propri Facts.
- ORDINI non deve contenere Documenti commerciali o Incassi e non deve duplicarne le informazioni.
- Le relazioni devono rispettare il flusso definito nel Data Dictionary attraverso Consegna e documentazione commerciale.

## 11. Authorized Content

ORDINI può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la nascita di una richiesta commerciale concreta;
- l'identità concettuale dell'Ordine;
- il riferimento al Cliente;
- il riferimento all'Ordine ricorrente, quando applicabile;
- gli accadimenti che fanno evolvere il ciclo commerciale dell'Ordine;
- le rettifiche collegate ai Facts precedenti;
- l'annullamento o la conclusione come nuovi Facts, quando ufficialmente registrati;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

ORDINI non deve contenere:

- Prodotti o quantità, che appartengono alle Righe Ordine;
- dati o State del Cliente;
- contenuto degli Ordini ricorrenti;
- Assegnazioni;
- Consegne;
- Documenti commerciali;
- Incassi;
- pianificazione o attività produttive;
- Stock commerciale;
- State corrente derivato dell'Ordine;
- Configuration;
- copie descrittive di altri Registri;
- logica, workflow o regole operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione deve essere rappresentata mediante un nuovo Fact conforme al ciclo dell'Ordine.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** deve avvenire mediante l'aggiunta di un nuovo Fact relativo allo stesso Ordine.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo.
- **Variazione:** deve essere rappresentata mediante un nuovo Fact e non deve riscrivere la cronologia precedente.
- **Annullamento:** deve costituire un nuovo Fact del ciclo commerciale e non una rettifica o una modifica del Fact originario.
- **Conclusione:** deve essere rappresentata dai Facts ufficiali applicabili e non deve modificare la cronologia precedente.

## 15. Rebuildability

**Non applicabile.**

ORDINI è un Authoritative Register e non è una proiezione rigenerabile.

L'eventuale State corrente degli Ordini deve essere ricostruibile dai Facts conservati in ORDINI e dai Facts autorevoli delle Righe Ordine e delle relazioni applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- Ogni Ordine deve appartenere a un Cliente.
- Ogni Ordine deve essere composto da una o più Righe Ordine.
- Un Ordine deve essere considerato costituito soltanto quando è associato ad almeno una Riga Ordine.
- Un Ordine può derivare da un Ordine ricorrente.
- Un Ordine può esistere prima di Assegnazione, Consegna, Documento commerciale e Incasso.
- Prodotti e quantità non devono appartenere direttamente all'Ordine.
- ORDINI deve costituire la fonte autorevole dei Facts dell'Ordine, non del suo State derivato.
- La cancellazione fisica dei Facts non deve essere ammessa.
- I riferimenti non devono duplicare le informazioni delle fonti collegate.
- L'Ordine deve costituire l'origine della domanda commerciale concreta da soddisfare.

## 17. Permanent Architectural Notes

L'entità Ordine e i Facts relativi all'Ordine non sono sinonimi: l'entità evolve nel tempo, mentre ciascun Fact che ne descrive la storia rimane immutabile.

Questo documento non governa i nomi concreti degli eventi, il vocabolario dello State, i nomi dei futuri Registri o i dettagli implementativi delle chiavi.
