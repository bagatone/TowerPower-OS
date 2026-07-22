# TPO REGISTER — ASSEGNAZIONI

## 1. Register Name

**ASSEGNAZIONI**

## 2. Category

**Authoritative Registers**

ASSEGNAZIONI deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

ASSEGNAZIONI rappresenta esclusivamente il concetto **Assegnazione** definito in `TPO_DATA_DICTIONARY.md`.

ASSEGNAZIONI deve utilizzare riferimenti verso:

- Raccolta;
- Riga Ordine;
- Consegna, quando applicabile.

ASSEGNAZIONI non deve rappresentare direttamente tali concetti.

## 4. Purpose

ASSEGNAZIONI deve conservare la cronologia autorevole dei Facts che costituiscono e fanno evolvere le allocazioni fisiche tra produzione ottenuta e fabbisogni commerciali specifici.

## 5. Single Responsibility

ASSEGNAZIONI deve registrare una sola volta i Facts ufficiali relativi all'allocazione di una quantità fisica di una Raccolta verso una specifica Riga Ordine.

ASSEGNAZIONI non deve mantenere direttamente lo State corrente dell'Assegnazione.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento ufficiale relativo a una specifica Assegnazione.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in ASSEGNAZIONI.

## 8. Readers

Possono leggere ASSEGNAZIONI:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance ai percorsi applicabili;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path, quando devono consultare la cronologia autorevole.

I Readers non devono modificare ASSEGNAZIONI.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact di allocazione relativo a un'Assegnazione.

Ogni record deve inoltre riferirsi all'identità stabile dell'Assegnazione cui appartiene.

L'identità del Fact e l'identità dell'Assegnazione devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento;
- l'identità dell'Assegnazione collega la cronologia alla stessa allocazione fisica.

L'identità dell'Assegnazione deve rimanere distinta dalle identità della Raccolta e della Riga Ordine collegate.

ASSEGNAZIONI non definisce identificativi implementativi.

## 10. Relationships and References

### Riga Ordine

- RIGHE_ORDINE deve conservare i Facts autorevoli della Riga Ordine.
- ASSEGNAZIONI deve utilizzare soltanto il riferimento all'identità stabile della Riga Ordine.
- La relazione è obbligatoria: ogni Assegnazione deve riferirsi a una sola Riga Ordine.
- Un'Assegnazione non può esistere senza la Riga Ordine cui si riferisce.
- Una Riga Ordine può avere zero, una o più Assegnazioni.
- La quantità richiesta deve appartenere alla Riga Ordine e non deve essere copiata in ASSEGNAZIONI.

### Raccolta

- La fonte autorevole della Raccolta deve conservarne i Facts produttivi.
- ASSEGNAZIONI deve utilizzare soltanto il riferimento alla Raccolta.
- La relazione è obbligatoria: ogni Assegnazione deve riferirsi a una sola Raccolta.
- Un'Assegnazione non può esistere senza la Raccolta da cui proviene la quantità fisica.
- Una Raccolta può alimentare zero o più Assegnazioni.
- La relazione con la Raccolta deve rimanere coerente con quanto definito in `TPO_DATA_DICTIONARY.md`.

### Consegna

- La fonte autorevole della Consegna deve conservarne i Facts logistici.
- ASSEGNAZIONI può utilizzare il riferimento alla Consegna quando applicabile.
- La relazione è facoltativa nel ciclo di vita dell'Assegnazione.
- Una Consegna può comprendere più Assegnazioni.
- ASSEGNAZIONI non deve duplicare contenuti o State della Consegna.

### Stock commerciale

- Lo Stock commerciale deve rimanere una Derived View non autorevole.
- I Facts di ASSEGNAZIONI possono concorrere alla sua ricostruzione.
- ASSEGNAZIONI non deve conservare lo Stock commerciale né riferimenti persistenti diretti alla proiezione.

### Documenti commerciali e Incasso

- Le rispettive fonti autorevoli devono conservare i propri Facts.
- Le relazioni con l'Assegnazione devono rimanere indirette attraverso Consegna e documentazione commerciale.
- ASSEGNAZIONI non deve contenere Documenti commerciali o Incassi e non deve duplicarne le informazioni.

## 11. Authorized Content

ASSEGNAZIONI può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di una specifica allocazione fisica;
- l'identità concettuale dell'Assegnazione;
- il riferimento alla Raccolta;
- il riferimento alla Riga Ordine;
- la quantità allocata e la relativa Unità di misura;
- il riferimento alla Consegna, quando applicabile;
- gli accadimenti che fanno evolvere l'allocazione;
- le variazioni, le rettifiche e le riallocazioni collegate ai Facts precedenti;
- l'annullamento come nuovo Fact, quando ufficialmente registrato;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

ASSEGNAZIONI non deve contenere:

- Facts o State della Riga Ordine;
- quantità richiesta dalla Riga Ordine;
- Facts o State della Raccolta;
- Facts o State della Consegna;
- Documenti commerciali;
- Incassi;
- Stock commerciale;
- disponibilità corrente della Raccolta;
- State corrente derivato dell'Assegnazione;
- Configuration;
- copie descrittive di altre fonti autorevoli;
- logica, workflow o regole operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione deve essere rappresentata mediante un nuovo Fact conforme al ciclo dell'Assegnazione.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** deve avvenire mediante l'aggiunta di un nuovo Fact relativo alla stessa Assegnazione.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo.
- **Variazione:** deve essere rappresentata mediante un nuovo Fact e non deve riscrivere la cronologia precedente.
- **Riallocazione:** deve essere rappresentata mediante un nuovo Fact e deve mantenere ricostruibile l'allocazione precedente.
- **Annullamento:** deve costituire un nuovo Fact del ciclo dell'Assegnazione e non una rettifica o una modifica del Fact originario.

## 15. Rebuildability

**Non applicabile.**

ASSEGNAZIONI è un Authoritative Register e non è una proiezione rigenerabile.

L'eventuale State corrente delle Assegnazioni deve essere ricostruibile dai Facts conservati in ASSEGNAZIONI e dai Facts autorevoli delle relazioni applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- Ogni Assegnazione deve riferirsi a una sola Riga Ordine.
- Ogni Assegnazione deve riferirsi a una sola Raccolta.
- Un'Assegnazione non può esistere senza la Riga Ordine e la Raccolta cui si riferisce.
- Una Riga Ordine può avere zero, una o più Assegnazioni.
- Una Raccolta può alimentare zero o più Assegnazioni.
- La quantità allocata e la relativa Unità di misura devono appartenere all'Assegnazione.
- Quantità richiesta e quantità allocata devono rimanere concettualmente distinte.
- Il collegamento a una Consegna deve rimanere facoltativo.
- ASSEGNAZIONI deve costituire la fonte autorevole dei Facts dell'Assegnazione, non del suo State derivato.
- La cancellazione fisica dei Facts non deve essere ammessa.
- I riferimenti non devono duplicare le informazioni delle fonti collegate.

## 17. Permanent Architectural Notes

L'entità Assegnazione e i Facts relativi all'Assegnazione non sono sinonimi: l'entità evolve nel tempo, mentre ciascun Fact che ne descrive la storia rimane immutabile.

ASSEGNAZIONI, RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte: conservano rispettivamente i Facts dell'allocazione fisica, del fabbisogno commerciale specifico e dell'impegno commerciale complessivo.

Questo documento non governa i nomi concreti degli eventi, il vocabolario dello State, i nomi dei futuri Registri o i dettagli implementativi delle chiavi.
