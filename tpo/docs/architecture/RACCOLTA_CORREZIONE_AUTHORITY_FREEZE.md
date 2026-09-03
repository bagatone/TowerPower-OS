# RACCOLTA CORREZIONE / RETTIFICA AUTHORITY FREEZE V1

**Stato:** OWNER-APPROVED ARCHITECTURE FREEZE (approvato 2026-09-03).
**Prior-art gate:** PRIOR ART REVIEW PASSED
**Ambito:** chiude il punto lasciato esplicitamente aperto da
`RACCOLTA_AUTHORITY_FREEZE.md` §7 e da `AUTHORITY_REGISTRY.yaml`
(`raccolta_authority_v1.correction_implementation: DEFERRED`).
**Baseline:** branch `sprint-4.4-production-planning`, commit `ac71f21`.

## 1. Scopo

`RACCOLTA_AUTHORITY_FREEZE.md` ha congelato RACCOLTA come fatto fisico
append-only: `UPDATE` e `DELETE` sono vietati anche a livello database. Lo
stesso Freeze, §7, riserva esplicitamente un'autorità collegata di
correction/reversal/void per quantità, SEMINA o `effective_at` errati e per
eventi mai avvenuti, dichiarandola `DEFERRED` e fuori dallo Sprint 5.13.

Questa proposta costruisce quell'autorità. Non riapre né modifica alcuna
decisione già congelata in `RACCOLTA_AUTHORITY_FREEZE.md`: identità RAC-*,
cardinalità, UOM, tracciabilità e confine con STOCK/MOVIMENTO_MAGAZZINO
restano invariati.

## 2. Prior-art gate

Ricerca repository-wide su correzione/rettifica/annullamento/reversal/void,
come richiesto da `ARCHITECTURE_AUTHORITY_GOVERNANCE_FREEZE.md` §5.

| Fonte | Contenuto | Classificazione |
|---|---|---|
| `docs/TPO_CORE_PRINCIPLES.md` PRINCIPIO 4 | "Se un evento contiene un errore, la correzione deve avvenire mediante la registrazione di un nuovo evento di rettifica." Nessuna riscrittura, nessuna cancellazione. | **PRESERVED** — principio cardine repository-wide, si applica direttamente. |
| `docs/TPO_REGISTER_CATALOG.md` §5.14 | Per gli Authoritative Registers, rettifica esclusivamente mediante nuovi Facts, mai modifica/eliminazione degli originali. | **PRESERVED** — RACCOLTA è un Authoritative Register, si applica. |
| `docs/registers/CONSEGNE.md` §13-14, `DOCUMENTO_DI_VENDITA.md`, `DOCUMENTO_DI_CONSEGNA.md`, `INCASSI.md` | Stesso pattern ("nuovo Fact collegato al Fact errato, senza sovrascriverlo o eliminarlo") dichiarato per altri Register. | **PRESERVED** — conferma che il pattern è già lo standard di progetto, non va reinventato diversamente per RACCOLTA. |
| `tpo.righe_consegna.rettifica_riga_consegna_id` (migrazione `20260812_0009`), trigger `fn_righe_consegna_rettifica_coerente`, vincolo `ck_righe_consegna_ordinary_or_correction`, dominio `DeliveryFulfilmentLine.correction_of`/`is_correction` | Implementazione reale, collaudata, dello stesso pattern: riga di rettifica self-referenziata via FK, quantità di segno opposto, niente rettifica-di-rettifica, niente self-reference, stessa dimensione (riga/varietà/UOM) dell'originale, l'originale dev'essere già effettivo. | **PRESERVED — precedente diretto**, riusato come modello strutturale in questa proposta (§4). |
| `tpo.fatture.rettifica_di` (migrazione `20260903_0026`) | Colonna FK riservata per `RectifyFattura`, stesso principio "nuovo documento collegato al precedente". | **PRESERVED** — ulteriore conferma dello stesso pattern, non ancora implementato (fuori scope qui). |
| `MovimentoType.RETTIFICA` (`CARICO`/`SCARICO`/`RETTIFICA`) | Valore di un enum di *tipo di movimento di magazzino*, concetto distinto: classifica un movimento fisico di stock, non è il pattern strutturale "nuovo fact collegato". | **VERIFICATO, NON IN CONFLITTO** — stessa parola italiana, dominio diverso (MOVIMENTO_MAGAZZINO, non RACCOLTA); questa proposta non tocca `MovimentoType` e userà nomi di colonna/tabella specifici di RACCOLTA per evitare ambiguità (§4). |
| `AUTHORITY_REGISTRY.yaml` `raccolta_authority_v1.correction_implementation` | `DEFERRED` | **CONFERMA IL GATE** — questa proposta è esattamente l'implementazione mancante dichiarata. |
| `tests/architecture/test_authority_registry.py` (`test_owner_approved_raccolta_authority_is_exact_and_fail_closed`, `test_raccolta_freeze_preserves_all_owner_guards`) | Verificano che `correction_implementation` sia `DEFERRED` e che il Freeze contenga letteralmente la frase "correction/reversal/void". | **PRESERVED** — questi test andranno aggiornati (non contraddetti) quando l'implementazione reale sostituirà `DEFERRED`. |
| `SEMENTE_AUTHORITY_FREEZE.md`, `SEMENTE_IMPIEGO_AUTHORITY_FREEZE.md`, `SEED_LOT_COMMISSIONING_BOUNDARY_FREEZE.md` | Dichiarano a loro volta correzioni di metadati/attivazione/valutazione come "deferred", con lo stesso principio append-only. | **PRESERVED** — fuori scope di questo documento (riguarda solo RACCOLTA), ma stesso pattern da riusare quando si affronteranno quei tre boundary, come già anticipato nella roadmap. |

**Esito:** `PRIOR ART REVIEW PASSED`. Nessun predecessore non classificato,
nessun conflitto aperto sul concetto stesso di rettifica per RACCOLTA.

## 3. Principio adottato

La correzione di una RACCOLTA non riscrive né elimina l'originale. È un nuovo
fatto RACCOLTA, con una propria identità `RAC-*`, collegato in modo permanente
alla RACCOLTA che corregge. Non esiste un secondo meccanismo di
"annullamento": annullare una RACCOLTA registrata per errore è il caso
particolare in cui la rettifica riporta a zero la quantità netta di
quell'evento (§6).

## 4. Modello proposto (per analogia diretta con `righe_consegna`)

```text
tpo.raccolte.rettifica_raccolta_id  BIGINT NULL
  REFERENCES tpo.raccolte(id) RESTRICT/RESTRICT
```

Vincoli, per analogia diretta con `ct_righe_consegna_rettifica_coerente` e
`ck_righe_consegna_ordinary_or_correction`:

- riga ordinaria (`rettifica_raccolta_id IS NULL`): quantità positiva, come
  oggi (`RACCOLTA_AUTHORITY_FREEZE.md` §4, invariato);
- riga di rettifica (`rettifica_raccolta_id IS NOT NULL`): quantità con segno
  (può essere negativa, per correggere in meno, o positiva, per correggere in
  più); nessun vincolo di segno rigido come per l'ordinaria;
- **niente self-reference**: `id <> rettifica_raccolta_id`;
- **niente rettifica-di-rettifica concatenata**: l'originale referenziato non
  può a sua volta avere `rettifica_raccolta_id` valorizzato — ogni correzione
  successiva referenzia sempre l'evento RACCOLTA originario, mai un'altra
  rettifica (identico al vincolo già in vigore su `righe_consegna`);
- **stessa SEMINA**: `original.semina_id = new.semina_id` — una rettifica non
  può spostare la quantità corretta su un'altra SEMINA;
- **stessa UOM**: `SET` in entrambe, invariato;
- **la quantità netta non può diventare negativa**: `SUM(quantita)` per lo
  stesso evento RACCOLTA originario (originale + tutte le sue rettifiche)
  resta `>= 0`, analogo a "correction cannot make delivered negative";
- la rettifica riceve una **propria identità `RAC-*`**, allocata dalla stessa
  sequenza `RACCOLTA_ID` (a differenza delle righe di `righe_consegna`, che
  non hanno identità pubblica propria e vivono dentro una CONSEGNA
  contenitore, RACCOLTA è essa stessa l'unità pubblica: ogni evento, ordinario
  o di rettifica, è un `RAC-*` distinto).

## 5. Owner Decision — approvate 2026-09-03

- **D1 — Stato della SEMINA al momento della rettifica: APPROVATA.** La
  rettifica è ammessa indipendentemente dallo stato corrente della SEMINA
  (anche se nel frattempo è stata chiusa), perché corregge un fatto storico e
  non registra un nuovo evento fisico.
- **D2 — `effective_at` della rettifica: APPROVATA.** La rettifica accetta un
  proprio `effective_at` esplicito dal caller, come l'evento originale — mai
  derivato implicitamente.
- **D3 — Profondità massima delle correzioni: APPROVATA.** Come
  `righe_consegna`: nessuna rettifica-di-rettifica concatenata; ogni
  rettifica successiva referenzia sempre l'evento RACCOLTA originario.
- **D4 — Nome pubblico del comando: APPROVATA.** `CorreggiRaccolta` a livello
  applicativo; CLI `tpo raccolta correggi`, simmetrico a `tpo raccolta
  registra`.

## 6. Annullamento (void) come caso particolare

Non si introduce uno stato `ANNULLATA` per RACCOLTA (a differenza di
CONSEGNA/ORDINE, RACCOLTA non ha un ciclo di stati, è un fatto puntuale).
Annullare un evento mai avvenuto è una rettifica la cui quantità è uguale e di
segno opposto alla quantità netta corrente dell'evento originario, portandola
esattamente a zero. Il fatto resta interamente in audit e la RACCOLTA
originale resta leggibile: nulla scompare, coerentemente con PRINCIPIO 4.

## 7. Idempotenza, concorrenza, audit

Stessa disciplina già in vigore per RACCOLTA V1 (`RACCOLTA_AUTHORITY_FREEZE.md`
§8-9), estesa al nuovo comando:

- request identity immutabile dedicata, persistita in una tabella distinta
  (proposta: `tpo.raccolta_correzione_requests`, per non mischiare la
  semantica di idempotenza tra "registra" e "correggi");
- stessa request identity + stesso payload canonico → `COMPATIBLE_REPLAY`,
  stesso `RAC-*` restituito; payload diverso → typed conflict, nessuna
  mutazione;
- allocazione identità, insert RACCOLTA di rettifica, audit e request
  completion in un'unica transazione PostgreSQL atomica;
- un evento `tpo.audit_eventi` per ogni rettifica, con riferimento sia al
  nuovo `RAC-*` sia al `RAC-*` originale corretto, actor/reason/correlation
  dall'authority context Core (stesso principio di §9 del Freeze RACCOLTA).

## 8. Guardie permanenti (in aggiunta a quelle già in vigore)

- Vietato correggere una RACCOLTA modificandola in place: resta `UPDATE = FORBIDDEN`, `DELETE = FORBIDDEN` sull'originale, senza eccezioni.
- Vietata la rettifica-di-rettifica concatenata (salvo diversa Owner Decision D3).
- Vietato spostare la quantità corretta su una SEMINA diversa da quella originaria.
- Vietato che la quantità netta di un evento RACCOLTA (originale + rettifiche) diventi negativa.
- Vietato introdurre uno stato/enum `ANNULLATA` per RACCOLTA: l'annullamento resta una rettifica a somma zero (§6).
- Vietato riusare `MovimentoType.RETTIFICA` o code/nomi da MOVIMENTO_MAGAZZINO per questo boundary.

## 9. Fuori scope di questa proposta

- Estensione dello stesso pattern a SEMENTE, SEMENTE_IMPIEGO, SEED_LOT —
  prossimo passo della roadmap, non di questo documento.
- Propagazione della rettifica a STOCK o MOVIMENTO_MAGAZZINO — resta un
  confine separato (`RACCOLTA_AUTHORITY_FREEZE.md` §11), non toccato qui.
- UI/gestionale — nessuna interfaccia utente è autorizzata da questo
  documento.
- Metadati di qualità o motivazione strutturata dell'errore oltre al campo
  `reason` già previsto dall'audit standard.

## 10. Prossimo passo

Freeze approvato. Implementazione autorizzata: domain, application,
migrazione, writer, CLI e test, con lo stesso standard di copertura già
raggiunto per FATTURA. `AUTHORITY_REGISTRY.yaml` (`raccolta_authority_v1.correction_implementation`)
e `tests/architecture/test_authority_registry.py` vanno aggiornati a
implementazione completata, con `reviewed_at_commit` sul commit che la
introduce.
