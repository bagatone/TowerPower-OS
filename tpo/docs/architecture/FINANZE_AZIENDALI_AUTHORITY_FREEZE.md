# FINANZE AZIENDALI (INCASSO + USCITA) AUTHORITY FREEZE — PROPOSTA V1

**Stato:** FREEZE — OWNER APPROVED (2026-09-04).
**Ambito:** chiude il punto lasciato esplicitamente aperto da
`FATTURA_AUTHORITY_FREEZE.md` §17 ("PAGAMENTO/INCASSO... a distinct future
freeze") **e** introduce, su richiesta esplicita dell'owner, una sezione
gemella per le uscite dell'impresa (spese verso fornitori e altri
pagamenti effettuati), necessaria per tenere le finanze complessive di
Tower Power. È il punto 4 della sequenza pre-gestionale approvata
dall'owner (`docs/reviews/GESTIONALE_TPO_ROADMAP.md` §8), con perimetro
esteso rispetto alla proposta iniziale in base alla revisione owner del
2026-09-04.
**Baseline:** branch `sprint-4.4-production-planning`, commit `04bef3b`.

## 1. Scopo

Oggi non esiste alcuna implementazione: nessuna tabella, nessuna identità,
nessun comando. Questa proposta introduce due registri Fact paralleli e
governati allo stesso standard:

- **INCASSO** — un pagamento *ricevuto* da un cliente, collegato a una
  FATTURA (specializzazione già nominata da `AMMINISTRAZIONE.md` §5.8).
- **USCITA** — un pagamento *effettuato* da Tower Power (spese
  dell'impresa: fornitori, affitto, utenze, ecc.), non collegato a nessuna
  fattura (nessun registro fornitori/fatture-fornitore esiste oggi in
  TPO — vedi Owner Decision D1 originaria, confermata dall'owner: "ho
  bisogno anche della sezione uscite per tenere le finanze dell'impresa").

Entrambi restano Facts append-only, mai modificati né eliminati, corretti
solo tramite un nuovo Fact collegato (stesso pattern già collaudato per
RACCOLTA). Nessuno dei due introduce uno State economico derivato (saldo,
bilancio, dashboard) — resta esplicitamente fuori scope (§6).

## 2. Prior-art gate

| Fonte | Contenuto | Classificazione |
|---|---|---|
| `docs/registers/INCASSI.md` | Contratto Authoritative Register completo e già congelato per i pagamenti ricevuti: Facts immutabili, mai modificati né eliminati, rettifica solo tramite nuovo Fact collegato; identità del Fact distinta dall'identità dell'Incasso; nessun saldo, nessuno State economico, nessuna fiscalità conservati qui. | **PRESERVED — contratto direttamente vincolante** per la parte INCASSO di questa proposta. |
| `docs/registers/AMMINISTRAZIONE.md` §5.7-5.9 | PAGAMENTO è il concetto generale (trasferimento di valore ufficialmente riconosciuto); INCASSO è la specializzazione già nominata per i pagamenti *ricevuti*; ALLOCAZIONE DEL PAGAMENTO è una relazione distinta per ripartire un pagamento su più obbligazioni. Nessun documento nomina o vieta una specializzazione simmetrica per i pagamenti *effettuati*. | **PRESERVED, estensione coerente non in conflitto** — USCITA è qui introdotta come specializzazione di PAGAMENTO simmetrica a INCASSO (pagamento effettuato anziché ricevuto), non una modifica del vocabolario congelato: nessuna regola esistente viene riscritta. |
| `docs/registers/` (intera cartella) | Nessun registro "USCITE", "SPESE", "FORNITORI" o "FATTURA_FORNITORE" esiste oggi. | **MISSING FROM CORE** — USCITA è un concetto nuovo introdotto da questa proposta, non un'estensione di un registro già scritto altrove; nessun registro fornitori viene costruito (il beneficiario resta testo libero, §4). |
| `FATTURA_AUTHORITY_FREEZE.md` §9, §17 | `fatture.totale` esiste già; PAGAMENTO/INCASSO dichiarato esplicitamente deferred con nota owner "solo FATTURA per ora". | **CONFERMA IL GATE** per INCASSO; nessuna modifica a FATTURA (resta immutabile, nessuna colonna aggiunta). |
| Precedente diretto: `RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` | Pattern già implementato e testato per una correzione append-only: colonna `rettifica_X_id` self-referencing, riga di correzione con importo con segno, nessuna correzione incatenata. | **PRESERVED — precedente diretto**, riusato identico per la rettifica sia di INCASSO sia di USCITA, invece di inventare due schemi di correzione diversi. |
| Identità tipizzate esistenti (`domain/identifiers.py`) | Nessun `IncassoId`/`UscitaId` esiste oggi. | **MISSING FROM CORE** — due nuove identità, per analogia diretta con le identità già esistenti (`PermanentId`). |
| `ALLOCAZIONE DEL PAGAMENTO` (§5.9 AMMINISTRAZIONE.md) | Relazione distinta che permetterebbe un Incasso ripartito su più Fatture. | **MISSING FROM CORE, esplicitamente fuori scope qui** (Owner Decision D2, confermata). |

**Esito:** `PRIOR ART REVIEW PASSED`.

## 3. Identità e modello — INCASSO

```text
type     = IncassoId
format   = INC-[0-9]{6,}
prefix   = INC
sequence = INCASSO_ID
```

`tpo.incassi` (Authoritative Register, Facts append-only — `INCASSI.md` §7,
§13):

- `id`, `public_id` (`IncassoId`)
- `fattura_numero` — riferimento documentale alla FATTURA (FK a
  `tpo.fatture.numero_fattura`, RESTRICT/RESTRICT — nessuna duplicazione
  dei contenuti della Fattura)
- `importo` (NUMERIC positivo)
- `data_incasso`
- `metodo` — enum `BONIFICO`, `CONTANTI`, `CARTA`, `BIZUM`, `ALTRO`
  (Owner Decision D4, confermata: "tutti insieme")
- `note` (testo libero, opzionale)
- `rettifica_incasso_id` (self-referencing FK, NULL per un Incasso
  ordinario)
- `actor`, `reason`, `correlation_id`, `created_at`

**Nessuna guardia anti-sovrapagamento** (Owner Decision D3, confermata:
"non mi interessa, se ci sono più soldi in cassa del dovuto non è poi
così grave") — un Incasso può superare `fatture.totale` senza essere
rifiutato.

## 4. Identità e modello — USCITA (nuovo)

```text
type     = UscitaId
format   = USC-[0-9]{6,}
prefix   = USC
sequence = USCITA_ID
```

`tpo.uscite` (nuovo Fact register, stesso standard di governance di
INCASSI — append-only, mai modificato/eliminato):

- `id`, `public_id` (`UscitaId`)
- `importo` (NUMERIC positivo)
- `data_uscita`
- `categoria` — enum, vedi Owner Decision D5 sotto (**da confermare in
  via definitiva**)
- `beneficiario` — testo libero obbligatorio non vuoto (a chi è stato
  pagato: es. nome fornitore). Nessun registro fornitori viene creato:
  è un campo descrittivo, non un riferimento a un'entità con identità
  propria (Owner-confirmed: "sì, testo libero").
- `metodo` — stesso enum di INCASSO: `BONIFICO`, `CONTANTI`, `CARTA`,
  `BIZUM`, `ALTRO`
- `note` (testo libero, opzionale)
- `rettifica_uscita_id` (self-referencing FK, NULL per un'Uscita
  ordinaria)
- `actor`, `reason`, `correlation_id`, `created_at`

Nessuna guardia di importo (non c'è un "totale dovuto" con cui
confrontare un'uscita, a differenza di INCASSO/FATTURA).

## 5. Owner Decision D5 — categorie di spesa (USCITA) — RISOLTA

**Decisione owner (2026-09-04): confermata la lista proposta.**

```text
SEMENTI        — acquisto sementi e materiali di coltivazione
ATTREZZATURA    — attrezzature, strumenti, materiali durevoli
AFFITTO         — affitto locali/terreni
UTENZE          — luce, acqua, gas, connettività
STIPENDI        — retribuzioni e collaborazioni
TRASPORTO       — carburante, consegne, spedizioni
ALTRO           — qualunque spesa non coperta dalle categorie precedenti
```

## 5bis. Idempotenza — stesso standard già in uso per RACCOLTA/SEMENTE/FATTURA

Non è una nuova decisione dell'owner: è l'applicazione dello stesso
pattern già usato ovunque nel repository per la registrazione di un Fact
(non menzionato esplicitamente nella prima stesura di questa proposta, ma
necessario per coerenza — ometterlo sarebbe la vera deviazione). Sia
`RegistraIncasso` sia `RegistraUscita` richiedono un `idempotency_key`
esplicito e usano una tabella di reservation dedicata
(`tpo.incasso_recording_requests`, `tpo.uscita_recording_requests`, stesso
schema di `tpo.raccolta_recording_requests`), così un'eventuale ripetizione
della stessa richiesta (es. per un errore di rete) non registra due volte
lo stesso movimento di denaro. Le rettifiche (§6) hanno la propria
reservation table gemella (`tpo.incasso_correzione_requests`,
`tpo.uscita_correzione_requests`), stesso schema di
`tpo.raccolta_correzione_requests`.

## 6. Rettifica (correzione) — stesso pattern per entrambi i registri

Un Incasso o un'Uscita registrati per errore (importo sbagliato, mai
realmente avvenuti) si correggono con un nuovo Fact collegato
(`rettifica_incasso_id`/`rettifica_uscita_id`) con un `importo` con segno
(positivo = ulteriore movimento, negativo = storno), esattamente come già
implementato e testato per RACCOLTA: nessuna correzione incatenata (solo
il Fact originale può ricevere una rettifica, non una rettifica a sua
volta).

## 7. Fuori scope

- Registro fornitori proprio — il beneficiario di un'Uscita resta un
  campo di testo libero, non un'entità con identità e Configuration
  propria.
- `ALLOCAZIONE DEL PAGAMENTO` come concetto proprio (un Incasso ripartito
  su più Fatture) — Owner Decision D2, confermata ("sì, è possibile
  [rimandarlo]").
- Qualunque State economico derivato: saldo cliente, saldo di cassa,
  bilancio, conto economico, dashboard "entrate meno uscite" —
  `AMMINISTRAZIONE.md` §5.14 qualifica esplicitamente questi come
  Derived; potranno essere viste di sola lettura costruite sopra
  `tpo.incassi`/`tpo.uscite`/`tpo.fatture` in un momento successivo, non
  fanno parte di questa scrittura governata.
- Fatture fornitore / documenti di acquisto in ingresso.
- Qualunque modifica a FATTURA (resta immutabile, nessuna colonna
  aggiunta).

## 8. Prossimo passo

Tutte le Owner Decisions (D1-D5) sono risolte. Si procede con
l'implementazione: comandi tipizzati `RegistraIncasso`/`RettificaIncasso`
e `RegistraUscita`/`RettificaUscita`, migrazione (`tpo.incassi`,
`tpo.uscite`, nuove sequenze identità `INCASSO_ID`/`USCITA_ID`), writer
PostgreSQL, CLI, test a ogni livello — stesso standard già applicato a
FATTURA e RACCOLTA CORREZIONE.
