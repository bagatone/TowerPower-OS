# TPO REGISTER — INCASSI

## 1. Register Name

**INCASSI**

## 2. Category

**Authoritative Registers**

INCASSI deve rispettare tutti i vincoli applicabili agli Authoritative Registers definiti in `TPO_REGISTER_CATALOG.md` e `TPO_SHEETS_SCHEMA.md`.

## 3. Data Dictionary Concepts Represented

INCASSI rappresenta esclusivamente il concetto **Incasso** definito in `TPO_DATA_DICTIONARY.md`.

INCASSI conserva i Facts economici ufficiali relativi agli Incassi.

INCASSI deve utilizzare riferimenti verso i concetti collegati senza rappresentarli direttamente né duplicarne i contenuti.

INCASSI non deve rappresentare direttamente:

- Documento di vendita;
- Documento di consegna;
- Consegna;
- Cliente;
- Ordine;
- Riga Ordine;
- Stock commerciale.

L’Incasso non coincide con:

- Documento commerciale;
- Documento di vendita;
- saldo cliente;
- credito derivato;
- State economico corrente.

## 4. Purpose

INCASSI deve conservare la cronologia autorevole dei Facts economici relativi agli Incassi registrati.

## 5. Single Responsibility

INCASSI deve conservare una sola volta la cronologia autorevole dei Facts relativi agli accadimenti economici rappresentati dagli Incassi.

INCASSI non deve conservare:

- Facts commerciali;
- Facts logistici;
- Facts documentali;
- dati fiscali;
- procedure amministrative;
- State finanziari derivati.

## 6. Origin

**Facts**

Ogni record deve rappresentare un accadimento economico ufficiale relativo a uno specifico Incasso.

INCASSI non deve avere origine da una Projection e non deve materializzare direttamente lo State corrente.

## 7. Writer

Il Writer deve essere il Writer unico definito in `SYSTEM_ARCHITECTURE.md`.

Il Writer può aggiungere nuovi Facts autorizzati.

Non deve modificare o eliminare Facts esistenti.

Nessun altro componente può scrivere in INCASSI.

## 8. Readers

Possono leggere INCASSI:

- Source Gate, per rendere disponibili i Facts ufficiali e la relativa provenance;
- il Single Writer, per verificare le precondizioni necessarie alla persistenza;
- i consumer autorizzati del Read Path;
- componenti autorizzati che producono informazioni derivate.

I Readers non devono modificare INCASSI.

## 9. Logical Key

Ogni record deve essere identificato concettualmente dall’identità univoca dello specifico Fact economico relativo a un Incasso.

Ogni record deve inoltre riferirsi all’identità stabile dell’Incasso cui appartiene.

L’identità del Fact e l’identità dell’Incasso devono rimanere distinte:

- l’identità del Fact identifica il singolo accadimento;
- l’identità dell’Incasso collega la cronologia allo stesso accadimento economico.

INCASSI non definisce identificativi implementativi.

## 10. Relationships and References

### Documento di vendita

La relazione principale è con il Documento di vendita.

DOCUMENTO_DI_VENDITA conserva i Facts documentali commerciali.

INCASSI conserva i Facts relativi all’Incasso.

INCASSI deve utilizzare i riferimenti verso le fonti documentali applicabili senza duplicarne i contenuti.

INCASSI non deve duplicare contenuti del Documento di vendita.

Il presente contratto non definisce:

- il numero di Incassi associabili a un Documento;
- il numero di Documenti associabili a un Incasso;
- le condizioni temporali del pagamento.

### Documento di consegna

La relazione è indiretta:

```text
DOCUMENTO_DI_CONSEGNA
↓
DOCUMENTO_DI_VENDITA
↓
INCASSO
```

INCASSI non deve utilizzare la Consegna come fonte economica diretta.

### Cliente

La relazione con il Cliente deve utilizzare la fonte autorevole del Cliente quando applicabile.

INCASSI non deve duplicare:

- identità del Cliente;
- dati anagrafici;
- State del Cliente;
- condizioni commerciali.

### Ordini, Righe Ordine, Assegnazioni e Raccolte

Le relazioni sono indirette attraverso il flusso commerciale:

```text
ORDINE
↓
RIGA ORDINE
↓
ASSEGNAZIONE
↓
CONSEGNA
↓
DOCUMENTO_DI_CONSEGNA
↓
DOCUMENTO_DI_VENDITA
↓
INCASSO
```

INCASSI non deve contenere:

- quantità richieste;
- quantità allocate;
- quantità raccolte;
- dati produttivi.

### Stock commerciale

Lo Stock commerciale è una Derived View.

INCASSI:

- non è fonte autorevole dello Stock;
- non deve conservarlo;
- non deve correggerlo direttamente.

## 11. Authorized Content

INCASSI può contenere esclusivamente Facts autorevoli necessari a rappresentare:

- la costituzione di uno specifico Incasso;
- l’identità concettuale dell’Incasso;
- il riferimento al passaggio documentale pertinente;
- gli accadimenti economici ufficiali relativi all’Incasso;
- i riferimenti necessari a ricostruire le relazioni approvate;
- le rettifiche e correzioni ufficiali collegate ai Facts precedenti.

## 12. Forbidden Content

INCASSI non deve contenere:

- Ordini;
- Righe Ordine;
- Assegnazioni;
- Raccolte;
- Consegne;
- Documenti di consegna;
- contenuti duplicati del Documento di vendita;
- prezzi;
- condizioni commerciali;
- saldi cliente;
- esposizioni finanziarie;
- State economico derivato;
- Stock commerciale;
- disponibilità corrente;
- IVA;
- IGIC;
- dati fiscali;
- fatture;
- procedure amministrative;
- workflow;
- Configuration;
- logica applicativa.

## 13. Direct Modifiability

I Facts esistenti non devono essere modificati direttamente dal Writer autorizzato.

Qualsiasi variazione deve essere rappresentata mediante nuovi Facts conformi al ciclo dell’Incasso.

## 14. Rectification / Update

- **Modifica del record esistente:** non ammessa.
- **Aggiornamento autorizzato:** non può modificare record esistenti e può avvenire esclusivamente mediante nuovi Facts autorizzati dai documenti congelati.
- **Rettifica:** deve avvenire mediante un nuovo Fact collegato al Fact precedente, senza modificarlo o eliminarlo.
- **Correzione ufficiale:** deve essere rappresentata mediante un nuovo Fact tracciabile.

Il presente contratto non riconosce autonomamente come specifici accadimenti di dominio:

- insoluto;
- rimborso;
- storno;
- contestazione;
- recupero credito;
- annullamento pagamento.

## 15. Rebuildability

**Non applicabile.**

INCASSI è un Authoritative Register e non è una proiezione rigenerabile.

Gli eventuali State economici derivati devono essere ricostruibili dai Facts ufficiali applicabili senza modificare INCASSI.

## 16. Conceptual Constraints

- Ogni Fact deve essere registrato una sola volta.
- Ogni Fact deve essere immutabile.
- Ogni rettifica deve avvenire mediante un nuovo Fact.
- INCASSI deve costituire la fonte autorevole dei Facts dell’Incasso.
- Lo State corrente dell’Incasso non deve essere conservato direttamente.
- I riferimenti non devono duplicare informazioni delle fonti collegate.
- La cancellazione fisica dei Facts non deve essere ammessa.
- INCASSI non deve assumere responsabilità su Documenti commerciali, fiscalità o procedure amministrative.

## 17. Permanent Architectural Notes

L’entità Incasso e i Facts relativi all’Incasso non sono sinonimi.

L’entità rappresenta un concetto economico che evolve nel tempo, mentre ogni Fact che ne descrive la storia rimane immutabile.

INCASSI, DOCUMENTO_DI_VENDITA, DOCUMENTO_DI_CONSEGNA, CONSEGNE, ASSEGNAZIONI, RACCOLTE, RIGHE_ORDINE e ORDINI devono mantenere responsabilità distinte:

- INCASSI → Facts economici;
- DOCUMENTO_DI_VENDITA → Facts documentali commerciali;
- DOCUMENTO_DI_CONSEGNA → Facts documentali logistici;
- CONSEGNE → Facts logistici;
- ASSEGNAZIONI → Facts di allocazione;
- RACCOLTE → Facts produttivi;
- RIGHE_ORDINE → Facts del fabbisogno commerciale;
- ORDINI → Facts dell’impegno commerciale complessivo.

Questo documento non governa:

- nomi concreti degli eventi;
- vocabolario dello State;
- strumenti finanziari;
- modalità tecniche di pagamento;
- condizioni fiscali;
- procedure amministrative;
- dettagli implementativi delle chiavi.
