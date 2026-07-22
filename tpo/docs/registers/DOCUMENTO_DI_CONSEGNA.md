# TPO REGISTER — DOCUMENTO_DI_CONSEGNA

## 1. Register Name

**DOCUMENTO_DI_CONSEGNA**

## 2. Category

**Authoritative Registers**

## 3. Data Dictionary Concepts Represented

Il Registro rappresenta esclusivamente il concetto **Documento di consegna** definito in `TPO_DATA_DICTIONARY.md`.

Il Documento di consegna è la specializzazione operativa primaria del concetto astratto **Documento commerciale**. Deriva da una Consegna, documenta i Prodotti e le quantità consegnate e può costituire l'origine di un Documento di vendita quando richiesto.

Il Registro deve utilizzare riferimenti ai concetti correlati senza rappresentarli né duplicarne i contenuti.

## 4. Purpose

Conservare la cronologia autorevole dei Facts documentali relativi ai Documenti di consegna che formalizzano le Consegne.

## 5. Single Responsibility

Registrare una sola volta i Facts documentali autorevoli di ciascun Documento di consegna, mantenendone identità, provenienza e tracciabilità.

## 6. Origin

**Facts**

DOCUMENTO_DI_CONSEGNA conserva Facts documentali autorevoli. Non conserva direttamente lo State corrente del Documento di consegna e non rappresenta una proiezione.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati. Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in DOCUMENTO_DI_CONSEGNA.

## 8. Readers

Possono leggere DOCUMENTO_DI_CONSEGNA:

- il Source Gate, per le verifiche semantiche di propria competenza;
- il Writer unico, per verificare le precondizioni di scrittura;
- i consumer autorizzati del Read Path;
- i componenti autorizzati che producono informazioni o proiezioni derivate.

I Readers non possono modificare il Registro.

## 9. Logical Key

Ogni Fact deve possedere una propria identità concettuale distinta dall'identità stabile del Documento di consegna cui appartiene.

L'identità stabile del Documento di consegna deve consentire di ricondurre alla stessa entità tutti i Facts che ne costituiscono la cronologia.

La chiave logica non definisce identificativi, numerazioni o formati implementativi.

## 10. Relationships and References

### Consegna

La fonte autorevole della Consegna deve conservare i Facts logistici.

DOCUMENTO_DI_CONSEGNA deve utilizzare il riferimento alla Consegna di origine senza duplicarne Facts o State. Un Documento di consegna deriva da una Consegna e non può esistere concettualmente senza la Consegna che formalizza.

Il presente contratto non definisce la cardinalità inversa, il momento della costituzione del Documento rispetto alla Consegna o il numero di Documenti associabili a una Consegna.

### Prodotto

La fonte autorevole del Prodotto deve conservarne la definizione.

DOCUMENTO_DI_CONSEGNA deve utilizzare i riferimenti ai Prodotti documentati senza duplicarne definizioni, Configuration o State.

### Documento di vendita

La fonte autorevole del Documento di vendita deve conservarne i Facts.

Quando richiesto, il Documento di vendita può derivare da uno o più Documenti di consegna e deve utilizzare i relativi riferimenti. DOCUMENTO_DI_CONSEGNA non deve conservare il Documento di vendita né i suoi contenuti.

### Incasso

La relazione con l'Incasso è esclusivamente indiretta attraverso il flusso dei Documenti commerciali. DOCUMENTO_DI_CONSEGNA non deve conservare Facts o State dell'Incasso.

### Cliente

La relazione con il Cliente è indiretta attraverso la Consegna. DOCUMENTO_DI_CONSEGNA non deve duplicare dati, Facts o State del Cliente.

### Assegnazione, Raccolta, Riga Ordine e Ordine

Le relazioni con Assegnazione, Raccolta, Riga Ordine e Ordine sono indirette attraverso la Consegna. Le rispettive fonti autorevoli devono conservarne i Facts; DOCUMENTO_DI_CONSEGNA non deve duplicarli.

### Stock commerciale

Lo Stock commerciale è una proiezione derivata. DOCUMENTO_DI_CONSEGNA non ne è fonte autorevole e non deve conservarlo o correggerlo direttamente.

## 11. Authorized Content

DOCUMENTO_DI_CONSEGNA può contenere esclusivamente:

- i Facts che costituiscono il Documento di consegna;
- l'identità concettuale del Documento di consegna;
- l'identità e la provenienza di ciascun Fact;
- il riferimento alla Consegna di origine;
- i riferimenti ai Prodotti documentati;
- le quantità consegnate documentate e le relative Unità di misura;
- le rettifiche e le correzioni ufficiali collegate ai Facts precedenti;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

DOCUMENTO_DI_CONSEGNA non deve contenere:

- Facts logistici o State della Consegna;
- Assegnazioni o quantità allocate;
- Raccolte, quantità raccolte o informazioni qualitative della Raccolta;
- Ordini, Righe Ordine o quantità richieste;
- dati, Facts o State del Cliente;
- definizioni, Configuration o State del Prodotto;
- Stock commerciale, disponibilità corrente o quantità residua;
- Documenti di vendita o relativi contenuti;
- Incassi, pagamenti, prezzi o importi;
- IVA, IGIC, dati fiscali o fatture;
- State derivato o altre proiezioni;
- Configuration;
- layout, formati, PDF, stampa, firma o numerazioni;
- workflow amministrativi, procedure operative o logica di dominio.

## 13. Direct Modifiability

**Non modificabile direttamente.**

I record esistenti non possono essere modificati dal Writer. Ogni variazione autorizzata deve essere rappresentata mediante nuovi Facts secondo il contratto del Registro.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** non può modificare record esistenti e può avvenire esclusivamente mediante nuovi Facts autorizzati dai documenti congelati.
- **Rettifica:** deve essere registrata come nuovo Fact collegato al Fact precedente, senza sostituirlo o eliminarlo.
- **Correzione ufficiale:** deve essere registrata come nuovo Fact tracciabile, preservando integralmente la cronologia.

Il presente contratto non riconosce autonomamente annullamento, sostituzione, revoca, riemissione o storno come accadimenti di dominio e non definisce modalità concrete di emissione.

## 15. Rebuildability

**Non applicabile.**

DOCUMENTO_DI_CONSEGNA è un Registro autorevole e non è rigenerabile da altre fonti. Lo State, i read model e le Derived Views costruiti dai suoi Facts devono invece essere ricostruibili dalle fonti autorevoli applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta e deve rimanere immutabile.
- Rettifiche e correzioni devono produrre nuovi Facts senza alterare quelli precedenti.
- Ogni Documento di consegna deve derivare da una Consegna e deve utilizzare il relativo riferimento.
- Un Documento di consegna non può esistere concettualmente senza la Consegna di origine.
- I Facts e lo State della Consegna non devono essere copiati in DOCUMENTO_DI_CONSEGNA.
- I Prodotti e le quantità consegnate documentate appartengono alla responsabilità documentale del Documento di consegna senza trasferire al Registro l'autorità sui Prodotti o sulla Consegna.
- Il Documento di vendita può derivare dal Documento di consegna soltanto quando richiesto, senza trasferire a DOCUMENTO_DI_CONSEGNA responsabilità sul Documento di vendita.
- Lo State corrente del Documento di consegna deve essere derivato dai Facts e non deve essere conservato direttamente.
- La cancellazione fisica dei Facts non è ammessa.

## 17. Permanent Architectural Notes

L'entità Documento di consegna, la sua identità stabile e i singoli Facts che ne costituiscono la cronologia sono concetti distinti.

La derivazione concettuale dalla Consegna non rende DOCUMENTO_DI_CONSEGNA una Derived View: il Registro conserva Facts documentali autorevoli propri, distinti dai Facts logistici di CONSEGNE.

Il presente contratto non definisce la cardinalità fra Consegne e Documenti di consegna, il momento concreto di emissione, il vocabolario dello State, le modalità di rettifica o la rappresentazione fisica del Registro.
