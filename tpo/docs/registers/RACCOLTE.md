# TPO REGISTER — RACCOLTE

## 1. Register Name

**RACCOLTE**

## 2. Category

**Authoritative Registers**

RACCOLTE deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

RACCOLTE rappresenta esclusivamente il concetto **Raccolta** definito in `TPO_DATA_DICTIONARY.md`.

RACCOLTE deve utilizzare il riferimento al Lotto di origine.

RACCOLTE non deve rappresentare direttamente Lotto, Semina, Assegnazione, Consegna o Stock commerciale.

## 4. Purpose

RACCOLTE deve conservare la cronologia autorevole dei Facts che costituiscono e fanno evolvere i risultati produttivi effettivamente ottenuti dai Lotti.

## 5. Single Responsibility

RACCOLTE deve registrare una sola volta i Facts ufficiali relativi ai risultati produttivi effettivamente ottenuti dai Lotti.

RACCOLTE non deve mantenere direttamente lo State corrente della Raccolta.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento produttivo ufficiale relativo a una specifica Raccolta.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in RACCOLTE.

## 8. Readers

Possono leggere RACCOLTE:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance ai percorsi applicabili;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path, quando devono consultare la cronologia autorevole.

I Readers non devono modificare RACCOLTE.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact produttivo relativo a una Raccolta.

Ogni record deve inoltre riferirsi all'identità stabile della Raccolta cui appartiene.

L'identità del Fact e l'identità della Raccolta devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento;
- l'identità della Raccolta collega la cronologia allo stesso risultato produttivo ottenuto.

L'identità della Raccolta deve rimanere distinta dall'identità del Lotto di origine.

RACCOLTE non definisce identificativi implementativi.

## 10. Relationships and References

### Lotto

- La fonte autorevole del Lotto deve conservarne i Facts agronomici.
- RACCOLTE deve utilizzare soltanto il riferimento all'identità del Lotto di origine.
- La relazione è obbligatoria: ogni Raccolta deve derivare da un Lotto.
- Un Lotto può produrre zero o più Raccolte.
- RACCOLTE non deve duplicare Varietà, Semina, fase, ciclo produttivo o altri contenuti del Lotto.

### Semina

- La relazione con la Semina deve rimanere indiretta attraverso il Lotto.
- RACCOLTE non deve duplicare i Facts della Semina.

### Assegnazione

- ASSEGNAZIONI deve conservare i Facts autorevoli dell'allocazione.
- ASSEGNAZIONI deve utilizzare il riferimento alla Raccolta.
- Una Raccolta può alimentare zero o più Assegnazioni.
- RACCOLTE non deve contenere quantità allocate né Facts o State delle Assegnazioni.
- Quantità raccolta e quantità allocata devono rimanere concettualmente distinte.

### Stock commerciale

- Lo Stock commerciale deve rimanere una Derived View non autorevole.
- I Facts di RACCOLTE possono concorrere alla sua ricostruzione.
- RACCOLTE non deve conservare disponibilità corrente, quantità residua, Stock commerciale o copie persistenti di altre proiezioni derivate.

### Consegna

- La relazione con la Consegna deve rimanere indiretta attraverso l'Assegnazione.
- RACCOLTE non deve introdurre riferimenti diretti alla Consegna né duplicarne i contenuti.

### Riga Ordine

- La relazione con la Riga Ordine deve rimanere indiretta attraverso l'Assegnazione.
- RACCOLTE non deve contenere quantità richiesta o altri contenuti della Riga Ordine.

### Documenti commerciali e Incasso

- Le relazioni con la Raccolta devono rimanere indirette attraverso Assegnazione, Consegna e documentazione commerciale.
- RACCOLTE non deve contenere Documenti commerciali, Incassi o informazioni economiche.

## 11. Authorized Content

RACCOLTE può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di una specifica Raccolta;
- l'identità concettuale della Raccolta;
- il riferimento al Lotto di origine;
- la quantità ottenuta e la relativa Unità di misura;
- la qualità ottenuta;
- le rettifiche e le correzioni ufficiali collegate ai Facts precedenti;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

RACCOLTE non deve contenere:

- Facts o State del Lotto;
- Facts della Semina;
- copie di Varietà, Semina, fase o ciclo produttivo;
- quantità richiesta;
- quantità allocata;
- disponibilità corrente;
- quantità residua;
- Facts o State delle Assegnazioni;
- riferimenti diretti o Facts della Consegna;
- Stock commerciale;
- copie persistenti di altre proiezioni derivate;
- Righe Ordine;
- Documenti commerciali;
- Incassi o informazioni economiche;
- State corrente derivato della Raccolta;
- Configuration;
- copie descrittive di altre fonti autorevoli;
- logica, workflow o regole operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione riconosciuta deve essere rappresentata mediante un nuovo Fact conforme al ciclo della Raccolta.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** deve avvenire mediante l'aggiunta di un nuovo Fact relativo alla stessa Raccolta.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo.
- **Variazione riconosciuta:** deve essere rappresentata mediante un nuovo Fact e non deve riscrivere la cronologia precedente.
- **Correzione ufficiale di quantità o qualità:** deve avvenire mediante un nuovo Fact collegato al Fact precedente.

Il presente contratto non riconosce autonomamente l'annullamento della Raccolta come accadimento di dominio.

## 15. Rebuildability

**Non applicabile.**

RACCOLTE è un Authoritative Register e non è una proiezione rigenerabile.

L'eventuale State corrente delle Raccolte e le informazioni derivate applicabili devono essere ricostruibili dai Facts conservati in RACCOLTE e dagli altri Facts autorevoli applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- Ogni Raccolta deve derivare da un Lotto.
- Un Lotto può produrre zero o più Raccolte.
- Quantità ottenuta, qualità ottenuta e relativa Unità di misura devono appartenere alla Raccolta.
- Quantità raccolta, quantità richiesta, quantità allocata, disponibilità corrente e quantità residua devono rimanere concettualmente distinte.
- RACCOLTE deve costituire la fonte autorevole dei Facts della Raccolta, non del suo State derivato.
- La cancellazione fisica dei Facts non deve essere ammessa.
- I riferimenti non devono duplicare le informazioni delle fonti collegate.

## 17. Permanent Architectural Notes

L'entità Raccolta e i Facts relativi alla Raccolta non sono sinonimi: l'entità evolve nel tempo, mentre ciascun Fact che ne descrive la storia rimane immutabile.

RACCOLTE, ASSEGNAZIONI, RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte: conservano rispettivamente i Facts del risultato produttivo ottenuto, dell'allocazione fisica, del fabbisogno commerciale specifico e dell'impegno commerciale complessivo.

Scarti, deterioramenti, perdite, consumi, rettifiche inventariali e altre riduzioni successive della disponibilità non sono disciplinati dal presente contratto e non devono essere attribuiti automaticamente a RACCOLTE.

Questo documento non governa i nomi concreti degli eventi, il vocabolario dello State, la rappresentazione temporale dei Facts, i nomi dei futuri Registri o i dettagli implementativi delle chiavi.
