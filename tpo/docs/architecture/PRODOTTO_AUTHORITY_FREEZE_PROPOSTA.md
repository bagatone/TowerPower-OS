# PRODOTTO — DECISIONE OWNER: DEFERRED (2026-09-04)

**Stato:** PROPOSTA NON ADOTTATA PER V1 — DEFERRED, non respinta in modo
permanente. Non introduce alcuna autorità, non autorizza alcuna
implementazione.

## Decisione

Una proposta di introdurre PRODOTTO come Configuration Register distinto da
VARIETA (specializzando il contratto predecessore `docs/registers/PRODOTTI.md`,
mai approvato: `AUTHORITY_REGISTRY.yaml` lo segnava `status: UNKNOWN / OWNER
DECISION REQUIRED`) è stata sottoposta all'owner.

**Motivazione dell'owner:** oggi Tower Power vende la Varietà raccolta
stessa — non esiste ancora un bene commerciale trasformato/derivato che non
corrisponda 1:1 a una singola Varietà. In questa condizione, Prodotto e
Varietà coincidono nella pratica: introdurre una seconda entità oggi
aggiungerebbe complessità senza un beneficio corrispondente.

**Non è una chiusura definitiva.** L'owner ha esplicitamente indicato lo
scenario che farebbe tornare rilevante questa distinzione: un prodotto
derivato o trasformato che nasce da una o più Varietà senza esserne una
semplice raccolta diretta — ad esempio un pesto di basilico, o una polvere
ricavata da un mix di più microgreens. In quel caso Prodotto e Varietà
smettono di coincidere (un pesto non È una Varietà; può derivare da una o
combinarne più d'una), esattamente la relazione N:M che `PRODOTTI.md`
descriveva. Quando/se quello scenario si presenta, questa proposta va
ripresa e riportata all'owner — non reintrodotta silenziosamente.

## Conseguenze per ora

- VARIETA resta l'unico riferimento commerciale per RIGA_ORDINE, CONSEGNA e
  LISTINO/FATTURA. Nessuna migrazione di schema, nessuna nuova tabella.
- `AUTHORITY_REGISTRY.yaml`: la entry `PRODOTTO` è `status: DEFERRED` con la
  motivazione e la condizione di ripresa registrate in `preserved_rules`;
  l'entry `ORDINE` ha `conflicts`/`open_owner_decisions` risolti di
  conseguenza. `tests/architecture/test_authority_registry.py` aggiornato
  di pari passo (PRODOTTO rimosso dall'insieme `required_unresolved`, non
  essendo più uno status "UNKNOWN / OWNER DECISION REQUIRED").
- `docs/registers/PRODOTTI.md` resta preservato come materiale storico
  (PRINCIPIO 4: nessuna cancellazione dello storico) ed è già pronto a
  essere ripreso il giorno in cui servirà.

## Prossimo passo nella sequenza pre-gestionale

Il punto 2 della sequenza (`docs/reviews/GESTIONALE_TPO_ROADMAP.md` §8) è
chiuso da questa decisione. Si passa al punto 3: governo del
LISTINO_VARIETA (prezzi).
