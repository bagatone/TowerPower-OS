# TPO REGISTER — CONSEGNE

## 1. Register Name

**CONSEGNE**

## 2. Category

**Authoritative Registers**

CONSEGNE deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

CONSEGNE rappresenta esclusivamente il concetto **Consegna** definito in `TPO_DATA_DICTIONARY.md`.

CONSEGNE deve utilizzare riferimenti verso:

- Cliente destinatario;
- Assegnazioni applicabili.

CONSEGNE non deve rappresentare direttamente Cliente, Assegnazione, Ordine, Riga Ordine, Raccolta, Documento commerciale o Incasso.

## 4. Purpose

CONSEGNE deve conservare la cronologia autorevole dei Facts logistici relativi all'adempimento degli impegni commerciali mediante specifiche Consegne.

## 5. Single Responsibility

CONSEGNE deve registrare una sola volta i Facts logistici ufficiali relativi all'avanzamento e all'esito di ciascuna Consegna.

CONSEGNE non deve mantenere direttamente lo State corrente della Consegna.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento logistico ufficiale relativo a una specifica Consegna.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in CONSEGNE.

## 8. Readers

Possono leggere CONSEGNE:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance ai percorsi applicabili;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path, quando devono consultare la cronologia autorevole.

I Readers non devono modificare CONSEGNE.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact logistico relativo a una Consegna.

Ogni record deve inoltre riferirsi all'identità stabile della Consegna cui appartiene.

L'identità del Fact e l'identità della Consegna devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento;
- l'identità della Consegna collega la cronologia alla stessa attività logistica concreta.

L'identità della Consegna deve rimanere distinta dalle identità del Cliente, delle Assegnazioni e dei Documenti commerciali collegati.

CONSEGNE non definisce identificativi implementativi.

## 10. Relationships and References

### Assegnazione

- ASSEGNAZIONI deve conservare i Facts autorevoli dell'allocazione.
- CONSEGNE deve conservare i Facts autorevoli dell'adempimento logistico.
- Una Consegna può comprendere più Assegnazioni.
- ASSEGNAZIONI può utilizzare il riferimento alla Consegna quando applicabile.
- Il collegamento alla Consegna è facoltativo nel ciclo dell'Assegnazione.
- CONSEGNE deve utilizzare riferimenti alle Assegnazioni senza duplicarne quantità o altri contenuti.
- Quantità allocata ed esito logistico devono rimanere concettualmente distinti.

Il presente contratto non definisce la cardinalità da Assegnazione verso Consegna, la suddivisione di un'Assegnazione, il numero minimo di Assegnazioni o le condizioni temporali della relazione.

### Cliente

- La fonte autorevole del Cliente deve conservarne identità, Facts e State.
- CONSEGNE deve utilizzare soltanto il riferimento al Cliente destinatario.
- La relazione è obbligatoria: ogni Consegna deve essere destinata a un Cliente.
- CONSEGNE non deve duplicare informazioni appartenenti al Cliente.

### Ordine e Riga Ordine

- Le relazioni devono rimanere indirette attraverso l'Assegnazione.
- CONSEGNE non deve contenere Facts o State dell'Ordine o della Riga Ordine.
- CONSEGNE non deve contenere quantità richiesta o contenuti commerciali delle Righe Ordine.

### Raccolta

- La relazione deve rimanere indiretta attraverso l'Assegnazione.
- CONSEGNE non deve contenere quantità raccolta, qualità ottenuta, Facts produttivi o copie dei contenuti della Raccolta.
- CONSEGNE non deve introdurre riferimenti diretti obbligatori alla Raccolta.

### Documento di consegna e Documento di vendita

- Il Documento di consegna deve derivare dalla Consegna ed essere associato alla Consegna che formalizza.
- La Consegna deve dare origine al Documento di consegna.
- Il Documento di vendita può derivare dal Documento di consegna quando richiesto.
- CONSEGNE non deve conservare Documenti di consegna, Documenti di vendita o contenuti documentali.
- CONSEGNE non deve definire condizioni concrete di emissione o applicabilità.

### Incasso

- La relazione con l'Incasso deve rimanere indiretta attraverso il flusso documentale applicabile.
- CONSEGNE non deve contenere Incassi, pagamenti, prezzi, importi, scadenze economiche, modalità di pagamento o riferimenti economici diretti.

### Stock commerciale

- Lo Stock commerciale deve rimanere una Derived View non autorevole.
- I Facts di CONSEGNE possono concorrere alla sua ricostruzione.
- CONSEGNE non deve conservare Stock commerciale, disponibilità corrente o quantità residua.
- CONSEGNE non deve correggere direttamente una proiezione.
- Gli effetti sullo Stock commerciale devono essere ricostruiti dalle fonti autorevoli applicabili.

## 11. Authorized Content

CONSEGNE può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di una specifica Consegna;
- l'identità concettuale della Consegna;
- il riferimento al Cliente destinatario;
- i riferimenti alle Assegnazioni applicabili;
- l'avanzamento e l'esito logistico della Consegna al livello astratto definito nel Data Dictionary;
- le rettifiche e le correzioni ufficiali collegate ai Facts logistici precedenti;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

CONSEGNE non deve contenere:

- Facts, State, quantità o altri contenuti delle Assegnazioni;
- Facts o State dell'Ordine;
- Facts o State della Riga Ordine;
- quantità richiesta;
- Facts o State della Raccolta;
- quantità raccolta o qualità ottenuta;
- riferimenti diretti obbligatori alla Raccolta;
- Documenti di consegna;
- Documenti di vendita;
- altri Documenti commerciali;
- contenuti documentali;
- Incassi;
- pagamenti;
- prezzi o importi;
- scadenze economiche o modalità di pagamento;
- Stock commerciale;
- disponibilità corrente o quantità residua;
- State corrente derivato della Consegna;
- State complessivo dell'Ordine;
- Configuration;
- copie descrittive di altre fonti autorevoli;
- dettagli di trasporto;
- logica, workflow o regole operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Le rettifiche e le correzioni ufficiali devono essere rappresentate mediante nuovi Facts relativi alla stessa Consegna.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** non può modificare record esistenti e può avvenire esclusivamente mediante nuovi Facts autorizzati dai documenti congelati.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo.
- **Correzione ufficiale:** deve avvenire mediante un nuovo Fact collegato al Fact precedente.

Il presente contratto non riconosce autonomamente annullamento, fallimento, consegna parziale, mancata consegna, rifiuto, reso, tentativo di consegna, passaggio di custodia o altre modalità concrete di conclusione come Facts di dominio.

## 15. Rebuildability

**Non applicabile.**

CONSEGNE è un Authoritative Register e non è una proiezione rigenerabile.

Lo State corrente della Consegna, gli effetti sullo State commerciale, gli effetti sullo Stock commerciale, i read model e le viste operative autorizzate devono essere ricostruibili dai Facts ufficiali applicabili, senza modificare CONSEGNE.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- Ogni Consegna deve essere destinata a un Cliente.
- Una Consegna può comprendere più Assegnazioni.
- CONSEGNE deve utilizzare riferimenti alle Assegnazioni senza duplicarne i contenuti.
- Quantità allocata ed esito logistico devono rimanere concettualmente distinti.
- La Consegna deve dare origine al Documento di consegna.
- CONSEGNE deve costituire la fonte autorevole dei Facts della Consegna, non del suo State derivato.
- La cancellazione fisica dei Facts non deve essere ammessa.
- I riferimenti non devono duplicare le informazioni delle fonti collegate.

## 17. Permanent Architectural Notes

L'entità Consegna e i Facts logistici relativi alla Consegna non sono sinonimi: l'entità evolve nel tempo, mentre ciascun Fact che ne descrive la storia rimane immutabile.

CONSEGNE, ASSEGNAZIONI, RACCOLTE, RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte: conservano rispettivamente i Facts dell'adempimento logistico, dell'allocazione fisica, del risultato produttivo ottenuto, del fabbisogno commerciale specifico e dell'impegno commerciale complessivo.

Il momento concreto in cui la Consegna è considerata effettuata e le modalità concrete di conferma non sono disciplinati dal presente contratto.

Questo documento non governa i nomi concreti degli eventi, il vocabolario dello State, le modalità concrete di conclusione, le condizioni di emissione dei Documenti commerciali, i nomi dei futuri Registri o i dettagli implementativi delle chiavi.
