# PAGAMENTO CONSEGNA ("PAGATO") AUTHORITY FREEZE — V1

**Stato:** APPROVATO dall'owner il 2026-10-11 (richiesta di Matteo del 2026-10-10; decisioni D1-D4 in §6) e IMPLEMENTATO (migrazione `20261010_0038`).
**Ambito:** permettere di sapere, per ogni CONSEGNA (e quindi per ogni bolla), se e' stata pagata, senza
aspettare la FATTURA. Oggi il solo pagamento registrabile e' l'INCASSO su una FATTURA
(`FINANZE_AZIENDALI_AUTHORITY_FREEZE.md`); le consegne e le bolle non portano nessun segno di pagato, e
le fatture non sono ancora emesse dalle consegne di ottobre.
**Scelte gia' fatte da Matteo (2026-10-10):** livello = per consegna/bolla; i clienti pagano in modo diverso
(alla consegna o dopo: lo stato si decide consegna per consegna); il pagato si vede sulla bolla PDF e nel
diario/app web.

## 1. Prior-art gate

| Fonte | Contenuto | Classificazione |
|---|---|---|
| `FINANZE_AZIENDALI_AUTHORITY_FREEZE.md` §3, §6, §7 | INCASSO e' un Fact append-only legato a una FATTURA (`fattura_numero` FK), importo positivo obbligatorio, metodo `BONIFICO/CONTANTI/CARTA/BIZUM/ALTRO`, rettifica con nuovo Fact; nessuno State derivato (saldo) e nessuna ALLOCAZIONE. | **PRESERVED** per pattern, metodi e rettifica. NON esteso: non si tocca il contratto "un incasso appartiene a una fattura". |
| Trigger `tr_consegne_effective_immutable` (migrazione 0009) | Una CONSEGNA `CONSEGNATA` non si modifica. | **VINCOLO**: il "pagato" non puo' essere una colonna di `tpo.consegne`; deve essere un Fact separato che riferisce la consegna. |
| `RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` | Pattern di correzione append-only (`rettifica_X_id` self-referencing). | **PRESERVED**, riusato per annullare un pagamento registrato per errore. |
| Bolla (`cli/bolla.py`, reader `bolla_lettura`) | PDF da sola lettura sul DB, `generata_il` sul documento. | **ESTESO**: il reader legge anche lo stato di pagamento. |
| Diario/app web (`web/routers/fornitura.py`, `finanze_lettura`) | Pagine di sola lettura su ordini e consegne. | **ESTESO**: campo stato di pagamento sulla consegna. |
| Listino (`tpo.listino_varieta`) | Prezzi per varieta' come Configuration; il totale nasce solo in FATTURA. | **NON USATO**: una consegna non ha un importo calcolato, quindi l'importo del pagamento e' dichiarato, non dedotto. |
| Registri / `identifiers.py` | Nessun concetto di pagamento legato a una consegna. | **MISSING FROM CORE** — nuovo Fact + nuova identita'. |

**Esito:** `PRIOR ART REVIEW PASSED`.

## 2. Modello

Nuovo Fact **PAGAMENTO_CONSEGNA** (`tpo.pagamenti_consegna`), append-only:

- `public_id` `PGC-000001` (nuova identita' `PagamentoConsegnaId`, sequenza `PAGAMENTO_CONSEGNA_ID`)
- `consegna_id` FK a `tpo.consegne` (solo consegne `CONSEGNATA`)
- `data_pagamento` (data), `metodo` (stesso enum `MetodoPagamento`), `note` (opzionale)
- `importo` **facoltativo** (Decimal positivo, max 2 decimali): se Matteo lo dichiara viene mostrato, altrimenti
  la consegna e' "pagata per intero, importo non registrato"
- `storico` (booleano): vero per i pagamenti dichiarati all'avvio del controllo per le consegne gia' fatte (§5)
- `tipo` `PAGAMENTO` | `ANNULLAMENTO`; un ANNULLAMENTO richiama il pagamento annullato (`annulla_pagamento_id`, univoco: un solo annullamento per pagamento, niente annullamenti a catena) e non porta data, metodo, importo
- `actor` (`created_by`), `reason`, `correlation_id`, `idempotency_key` (UNIQUE) e `payload_hash`, `created_at`
- L'idempotenza vive nella riga stessa (chiave univoca + hash del payload: stessa chiave e stesso payload = `COMPATIBLE_REPLAY`, payload diverso = conflitto), senza tabelle di prenotazione: unica deviazione dal pattern INCASSO, voluta per semplicita'

**Stato di pagamento = DERIVATO, mai memorizzato**: una consegna e' `PAGATA` se ha un pagamento non annullato,
altrimenti `DA PAGARE`. Un solo pagamento valido per consegna (un secondo viene rifiutato, anche dal database: si annulla il primo
e se ne registra uno nuovo). Nessun pagamento parziale in V1.

Comandi (stesso stile degli altri, con anteprima prima della scrittura):
- `tpo pagamento-consegna registra --consegna CON-... --data AAAA-MM-GG --metodo CONTANTI [--importo 12.50] [--note ...]`
- `tpo pagamento-consegna annulla --originale PGC-... --reason ...`
- (entrambi con `--actor`, `--reason`, `--correlation-id`, `--idempotency-key`; `--storico` solo per §5)
- script `scripts/commissioning/2026-10-11_pagamenti_consegne.py` con anteprima/`--esegui` (`--storico`, `--pagata CON-...`,
  `--annulla PGC-...`), che dopo la registrazione rigenera la bolla (`--sovrascrivi`) nella cartella del cliente,
  cosi' il PDF dice PAGADO.

## 3. Dove si vede

- **Bolla PDF**: in alto `PAGADO el <data> - <metodo>[ - <importo> EUR]` oppure `PENDIENTE DE PAGO` (la bolla e in spagnolo). Il PDF e' una fotografia:
  riporta lo stato al momento della generazione (gia' c'e' "generata il ..."); dopo un pagamento va rigenerata,
  e lo script lo fa da solo.
- **Diario/app web**: colonna "pagamento" accanto a ogni consegna (PAGATA con data e metodo / DA PAGARE).

## 4. Pagamento alla consegna

Per un cliente che paga subito: dopo la consegna, `2026-10-11_pagamenti_consegne.py --pagata CON-... --metodo
CONTANTI --esegui` registra il pagamento e rigenera la bolla, che diventa PAGADO. Senza questo passo la consegna
resta DA PAGARE (nessun default per cliente: si decide consegna per consegna, come ha detto Matteo).

## 5. Consegne gia' fatte (CON-000001 ... CON-000011) — flag `storico`

Matteo (2026-10-11): tutte dichiarate pagate, stessa data e stesso metodo per tutte, "sono dati non rilevanti ora,
mi interessa tenere il controllo da ora". Regola di onesta' (Regola 1: nessun dato inventato): il sistema NON
presenta come reali una data e un metodo di incasso che non conosce. Questi pagamenti sono registrati con
`storico = true`: `data_pagamento` e' il giorno della DICHIARAZIONE (non dell'incasso), `metodo = ALTRO`
(segnaposto), nessun importo, e la nota lo dice. La bolla mostra "PAGADO - registrado el <data> (entrega anterior
al control de pagos)" senza metodo; il diario li mostra con `storico`. Da questo giorno in poi le date sono vere.

## 6. Owner Decisions (tutte risposte il 2026-10-11)

- **D1 — importo:** FACOLTATIVO.
- **D2 — rapporto con la FATTURA futura:** NESSUN collegamento automatico. Matteo: "quando emetto una fattura conto
  le bolle e emetto fattura". Quando le fatture verranno emesse dalle consegne, la regola per evitare doppi
  conteggi di cassa (pagamento di consegna gia' registrato vs INCASSO su fattura) si decide in un Freeze separato.
- **D3 — consegne storiche:** tutte e 11 dichiarate pagate, stessa data e stesso metodo, con flag `storico` (§5).
- **D4 — nome:** PAGAMENTO_CONSEGNA (`PGC-`).

## 7. Fuori scope

Pagamenti parziali o ripartiti su piu' consegne (ALLOCAZIONE), saldo cliente, scadenze e solleciti, riconciliazione
bancaria, ogni modifica a FATTURA, INCASSO o alla CONSEGNA, elenco "da incassare" per cliente.

## 8. Implementazione e verifica

Migrazione `20261010_0038` (tabella `tpo.pagamenti_consegna`, sequenza `PAGAMENTO_CONSEGNA_ID`, trigger di
immutabilita' e di coerenza: consegna `CONSEGNATA`, un solo pagamento attivo, annullamento coerente), writer
PostgreSQL, CLI `tpo pagamento-consegna`, reader bolla e consegne (stato derivato `PAGATA` / `DA_PAGARE` /
`NON_CONSEGNATA`), PDF bolla, pagina Consegne del diario/app web, script `2026-10-11_pagamenti_consegne.py`.
Test: `tests/integration/postgresql/test_pagamento_consegna.py`, `tests/cli/test_pagamento_consegna_cli.py`,
`tests/application/test_bolla_lettura.py`, `tests/infrastructure/postgresql/test_pagamenti_consegne_script.py`.
La migrazione la applica Matteo (`migrate_to_head.sh`); nessuna scrittura sul database reale prima.
