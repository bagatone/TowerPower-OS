# Tower Power Operations (TPO)

# PROJECT SNAPSHOT v1.0

**Versione:** 1.0  
**Data Snapshot:** 20/07/2026  
**Stato:** ARCHITETTURA APPROVATA - PRONTO PER LO SVILUPPO

---

# SCOPO DEL PROGETTO

Tower Power Operations (TPO) è il sistema ERP proprietario sviluppato per la gestione completa dell'azienda Tower Power.

Il sistema gestisce l'intero ciclo produttivo e commerciale:

- Clienti
- Ordini
- Produzione
- Lotti
- Raccolti
- Assegnazioni
- Consegne
- Documenti di vendita
- Incassi
- Magazzino
- Pianificazione
- Dashboard
- Automazioni

---

# STATO DEL PROGETTO

## Architettura

✅ Approvata

## Audit strutturale

✅ Completato

## Relazioni tra fogli

✅ Verificate

## Standard ID

✅ Uniformati

## Flusso ERP

✅ Approvato

## Google Sheets

✅ Struttura definitiva approvata

## Apps Script

⏳ Non ancora iniziato
---

# STRUTTURA ERP APPROVATA

CLIENTI

↓

ORDINI_RICORRENTI

↓

ORDINI

↓

PIANO_SEMINE

↓

SEMINE

↓

LOTTI

↓

RACCOLTI

↓

ASSEGNAZIONI

↓

CONSEGNE

↓

DOCUMENTI_CONSEGNE

↓

DOCUMENTI_VENDITA

↓

INCASSI

---

# DECISIONI ARCHITETTURALI DEFINITIVE

- Tutti gli ID sono univoci.
- Nessun ID viene modificato.
- Nessun ID viene riutilizzato.
- Tutte le relazioni tra i fogli sono state validate durante l'audit.
- Un ordine può generare più semine.
- Una semina può generare uno o più lotti.
- Un lotto può produrre più raccolti.
- Un raccolto può alimentare più assegnazioni.
- Una consegna può contenere più assegnazioni.
- Una fattura può raggruppare più consegne.
- I menu a tendina saranno creati automaticamente tramite Apps Script.
- Le validazioni dati saranno gestite automaticamente.
- Lo STOCK sarà aggiornato esclusivamente tramite MOVIMENTI_MAGAZZINO.
- Nessun record operativo verrà eliminato: le cancellazioni saranno logiche tramite il campo STATO.

---

# DOCUMENTAZIONE ESISTENTE

- AGENTS.md
- OPERATING_RULES.md
- SYSTEM_ARCHITECTURE.md
- TPO_BOOTSTRAP.md
- TPO_SHEETS_SCHEMA.md
- EVENT_ENGINE.md
- INSTALLAZIONE.md
- NOTE_OPERATIVE.md
- TPOL.md
---

# DOCUMENTAZIONE DA COMPLETARE

I seguenti documenti sono stati creati e rappresentano la documentazione ufficiale da completare durante lo sviluppo:

- PROJECT_SNAPSHOT_v1.0.md
- CHANGELOG.md
- TPO_DATA_DICTIONARY.md

---

# PROSSIMA FASE DI SVILUPPO

Lo sviluppo del sistema inizierà seguendo questo ordine:

1. TPO_DATA_DICTIONARY
2. Setup automatico del progetto
3. Costanti globali
4. Motore generazione ID
5. Gestione Master Data
6. Gestione Produzione
7. Gestione Commerciale
8. Dashboard
9. Event Engine
10. Automazioni

Ogni fase dovrà essere completata e testata prima di passare alla successiva.

---

# OBIETTIVI DEL SISTEMA

Il sistema dovrà garantire:

- Tracciabilità completa dal seme all'incasso.
- Eliminazione delle operazioni manuali ripetitive.
- Riduzione degli errori operativi.
- Pianificazione automatica della produzione.
- Controllo costante dello stock.
- Gestione documentale completa.
- Supporto alla crescita futura dell'azienda.

---

# PRINCIPI DI PROGETTAZIONE

Il progetto Tower Power Operations è stato progettato seguendo questi principi:

- Semplicità operativa.
- Massima tracciabilità.
- Automazione ove possibile.
- Nessuna duplicazione dei dati.
- Modularità del codice.
- Scalabilità.
- Manutenibilità nel tempo.

Ogni nuova funzionalità dovrà rispettare questi principi.

---

# STATO DEL PROGETTO AL 20/07/2026

✅ Architettura ERP approvata.

✅ Audit completato.

✅ Relazioni validate.

✅ Struttura Google Sheets definitiva.

✅ Sistema pronto per iniziare lo sviluppo.

---

# NOTE FINALI

Questo documento rappresenta la fotografia ufficiale del progetto alla conclusione della fase di progettazione.

Qualsiasi modifica futura all'architettura dovrà essere registrata nel CHANGELOG.md e riflessa nel TPO_DATA_DICTIONARY.md prima dell'implementazione nel codice.

---

**Fine Snapshot v1.0**

