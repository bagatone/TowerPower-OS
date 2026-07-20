# CHANGELOG

Registro ufficiale delle modifiche apportate al progetto Tower Power Operations.

Tutte le modifiche strutturali, funzionali e operative devono essere annotate in questo documento.

---

## [1.0.0] - 20/07/2026

### Aggiunto

- Definita e approvata l’architettura ERP completa.
- Creato il flusso operativo:

  CLIENTI  
  → ORDINI_RICORRENTI  
  → ORDINI  
  → PIANO_SEMINE  
  → SEMINE  
  → LOTTI  
  → RACCOLTI  
  → ASSEGNAZIONI  
  → CONSEGNE  
  → DOCUMENTI_CONSEGNE  
  → DOCUMENTI_VENDITA  
  → INCASSI

- Creato il foglio DOCUMENTI_CONSEGNE.
- Aggiunto il campo ATTIVA in MASTER_VARIETA.
- Aggiunto il campo STATO_ORDINE in ORDINI.
- Aggiunto il campo ID_PIANO in PIANO_SEMINE.
- Aggiunti i campi ID_PIANO e ID_SEMINA in SEMINE.
- Aggiunto il campo ID_SEMINA in LOTTI.
- Aggiunto il campo ID_RACCOLTA in ASSEGNAZIONI.
- Aggiunto il campo ID_CONSEGNA in ASSEGNAZIONI.
- Aggiunto il campo ESITO in CONSEGNE.
- Aggiunto il campo TIPO_DOCUMENTO in DOCUMENTI_VENDITA.
- Aggiunto il campo IMPORTO_INCASSATO in INCASSI.
- Creati i documenti:
  - PROJECT_SNAPSHOT_v1.0.md
  - CHANGELOG.md
  - TPO_DATA_DICTIONARY.md

### Modificato

- Standardizzati tutti gli ID cliente.
- Standardizzati tutti gli ID ordine.
- Rigenerati gli ID ordine nel formato:

  ORD-2026-0001  
  ORD-2026-0002  
  ...  
  ORD-2026-0008

- Validata la relazione tra raccolti, assegnazioni e consegne.
- Stabilito che una consegna può contenere più assegnazioni.
- Stabilito che una fattura può raggruppare più consegne.
- Stabilito che lo STOCK può essere aggiornato esclusivamente tramite MOVIMENTI_MAGAZZINO.

### Rimosso

- Rimosso ID_ASSEGNAZIONE dal foglio RACCOLTI.
- Rimosso ID_CONSEGNA dal foglio DOCUMENTI_VENDITA.

### Corretto

- Corretta la direzione delle relazioni tra RACCOLTI e ASSEGNAZIONI.
- Corretta la relazione tra DOCUMENTI_VENDITA e CONSEGNE tramite il foglio ponte DOCUMENTI_CONSEGNE.
- Corretta la struttura degli identificativi operativi.

### Stato

- Architettura approvata.
- Audit completato.
- Relazioni validate.
- Sistema pronto per lo sviluppo Apps Script.

---

## Regole di aggiornamento

Ogni nuova modifica dovrà indicare:

- Versione
- Data
- Elementi aggiunti
- Elementi modificati
- Elementi rimossi
- Correzioni
- Stato del progetto
