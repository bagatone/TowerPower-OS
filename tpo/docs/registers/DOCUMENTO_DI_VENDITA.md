# TPO REGISTER — DOCUMENTO_DI_VENDITA

## 1. Register Name

**DOCUMENTO_DI_VENDITA**

## 2. Category

**Authoritative Registers**

DOCUMENTO_DI_VENDITA deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

DOCUMENTO_DI_VENDITA rappresenta esclusivamente il concetto **Documento di vendita** definito in `TPO_DATA_DICTIONARY.md`.

Il Documento di vendita è un Documento commerciale che può derivare dal Documento di consegna quando richiesto.

DOCUMENTO_DI_VENDITA deve utilizzare riferimenti verso i concetti collegati senza rappresentarli direttamente né duplicarne i contenuti.

DOCUMENTO_DI_VENDITA non deve rappresentare direttamente:

- Documento di consegna;
- Consegna;
- Assegnazione;
- Raccolta;
- Riga Ordine;
- Ordine;
- Incasso.

## 4. Purpose

DOCUMENTO_DI_VENDITA deve conservare la cronologia autorevole dei Facts documentali relativi ai Documenti di vendita.

## 5. Single Responsibility

DOCUMENTO_DI_VENDITA deve registrare una sola volta i Facts documentali ufficiali relativi a ciascun Documento di vendita.

DOCUMENTO_DI_VENDITA non deve mantenere direttamente lo State corrente del Documento di vendita.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento documentale ufficiale relativo a uno specifico Documento di vendita.

DOCUMENTO_DI_VENDITA non deve avere origine da una Projection e non deve materializzare direttamente State derivati.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati.

Il Writer non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in DOCUMENTO_DI_VENDITA.

## 8. Readers

Possono leggere DOCUMENTO_DI_VENDITA:

- Source Gate, per rendere disponibili i Facts documentali ufficiali e la relativa provenance;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path;
- i componenti autorizzati che producono informazioni o viste derivate.

I Readers non devono modificare DOCUMENTO_DI_VENDITA.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall'identità univoca dello specifico Fact documentale relativo a un Documento di vendita.

Ogni record deve inoltre riferirsi all'identità stabile del Documento di vendita cui appartiene.

L'identità del Fact e l'identità del Documento di vendita devono rimanere distinte:

- l'identità del Fact identifica il singolo accadimento documentale;
- l'identità del Documento di vendita collega la cronologia allo stesso documento.

DOCUMENTO_DI_VENDITA non definisce identificativi, numerazioni o formati implementativi.

## 10. Relationships and References

### Documento di consegna

- DOCUMENTO_DI_CONSEGNA conserva i Facts documentali del Documento di consegna.
- DOCUMENTO_DI_VENDITA può utilizzare il riferimento al Documento di consegna quando applicabile.
- Il Documento di vendita può derivare dal Documento di consegna quando richiesto.
- DOCUMENTO_DI_VENDITA non deve duplicare Facts logistici, quantità consegnate o contenuti del Documento di consegna.

### Incasso

- La relazione con INCASSI deve rimanere indiretta attraverso il flusso documentale applicabile.
- INCASSI deve conservare i propri Facts autorevoli.
- DOCUMENTO_DI_VENDITA non deve contenere Incassi, pagamenti o State economici.

### Cliente

- La relazione con il Cliente deve rimanere attraverso le fonti autorevoli applicabili.
- DOCUMENTO_DI_VENDITA non deve duplicare dati, Facts o State del Cliente.

### Consegna, Assegnazione e Raccolta

- Le relazioni devono rimanere indirette attraverso il ciclo logistico e documentale.
- DOCUMENTO_DI_VENDITA non deve contenere Facts logistici, produttivi o di allocazione.

### Riga Ordine e Ordine

- Le relazioni devono rimanere indirette attraverso il ciclo commerciale.
- DOCUMENTO_DI_VENDITA non deve contenere domanda commerciale, quantità richieste o Facts degli Ordini.

### Stock commerciale

- Lo Stock commerciale deve rimanere una Derived View non autorevole.
- DOCUMENTO_DI_VENDITA non deve conservare Stock commerciale né correggere direttamente proiezioni derivate.

## 11. Authorized Content

DOCUMENTO_DI_VENDITA può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di uno specifico Documento di vendita;
- l'identità concettuale del Documento di vendita;
- l'identità dei singoli Facts documentali;
- i riferimenti documentali approvati;
- il riferimento al Documento di consegna quando applicabile;
- le rettifiche e correzioni ufficiali collegate ai Facts precedenti;
- i riferimenti necessari a ricostruire le relazioni approvate.

## 12. Forbidden Content

DOCUMENTO_DI_VENDITA non deve contenere:

- Facts logistici della Consegna;
- Facts delle Assegnazioni;
- Facts delle Raccolte;
- Ordini o Righe Ordine;
- quantità richieste;
- quantità allocate;
- quantità raccolte;
- Stock commerciale;
- disponibilità corrente;
- Incassi;
- pagamenti;
- prezzi;
- importi;
- scadenze economiche;
- modalità di pagamento;
- dati fiscali non definiti;
- IVA;
- IGIC;
- contabilità;
- State corrente derivato;
- Configuration;
- layout;
- PDF;
- stampa;
- firma;
- workflow amministrativi;
- procedure operative.

## 13. Direct Modifiability

I record esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione deve essere rappresentata mediante nuovi Facts conformi al ciclo del Documento di vendita.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** non può modificare record esistenti e può avvenire esclusivamente mediante nuovi Facts autorizzati dai documenti congelati.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact precedente, senza eliminarlo o sostituirlo.
- **Correzione ufficiale:** deve essere rappresentata mediante un nuovo Fact mantenendo la cronologia precedente.

Il presente contratto non riconosce autonomamente annullamento, sostituzione, revoca, riemissione o storno come accadimenti di dominio.

## 15. Rebuildability

**Non applicabile.**

DOCUMENTO_DI_VENDITA è un Authoritative Register e non è una proiezione rigenerabile.

Lo State corrente del Documento di vendita, i Read Model e le viste derivate devono essere ricostruibili dai Facts autorevoli applicabili.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- DOCUMENTO_DI_VENDITA deve conservare Facts documentali propri.
- La derivazione dal Documento di consegna non rende DOCUMENTO_DI_VENDITA una Derived View.
- Il Documento di vendita non deve sostituire il Documento di consegna.
- Incassi e Documenti di vendita devono mantenere responsabilità distinte.
- DOCUMENTO_DI_VENDITA non deve conservare State derivati.
- La cancellazione fisica dei Facts non deve essere ammessa.

## 17. Permanent Architectural Notes

L'entità Documento di vendita e i Facts documentali relativi al Documento di vendita non sono sinonimi: l'entità evolve nel tempo mentre ciascun Fact che ne descrive la storia rimane immutabile.

DOCUMENTO_DI_VENDITA, DOCUMENTO_DI_CONSEGNA, CONSEGNE, ASSEGNAZIONI, RACCOLTE, RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte.

La derivazione dal Documento di consegna non trasferisce a DOCUMENTO_DI_VENDITA responsabilità logistiche, produttive o di incasso.

Questo documento non governa:

- nomi concreti degli eventi;
- vocabolario dello State;
- aspetti fiscali;
- normativa;
- modalità materiali del documento;
- identificativi o numerazioni implementative;
- nomi dei futuri Registri.
