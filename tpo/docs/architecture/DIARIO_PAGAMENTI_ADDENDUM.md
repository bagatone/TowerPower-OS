# DIARIO — D6: registrazione del pagamento di una consegna

**Stato:** approvato da Matteo il 16/10/2026 ("si", alla proposta: il diario scrive i pagamenti con conferma
esplicita a schermo). Estende `handoff/diario-governance-addendum.md` (D4-bis, sei misure) al terzo comando
in perimetro; non riapre nessuna decisione precedente.

## Perimetro

Dentro: `pagamento-consegna registra` (una o piu' consegne dello STESSO cliente, un metodo, una data) e la
vista di sola lettura "Da incassare" (consegne effettuate non pagate, per cliente).
Fuori, resta da terminale: annullo di un pagamento (`2026-10-11_pagamenti_consegne.py --annulla`), dichiarazione
storica, fatture, rigenerazione delle bolle PDF (stanno sul Mac, non su Render).

## Come rispetta le sei misure

1. Password obbligatoria su ogni rotta (`/api/da-incassare`, `/api/pagamento/prepara`, `/api/conferma`).
2. Nessuna scrittura senza conferma: `/api/pagamento/prepara` e `/api/interpreta` propongono soltanto; scrive
   solo `/api/conferma` dopo il tocco sulla carta mostrata (cliente, consegne, metodo, data).
3. Nessun nuovo percorso di scrittura: `esegui_pagamento` chiama `run_pagamento_consegna_command`, lo stesso
   adapter CLI; nessuna SQL di scrittura.
4. `ActorId` fisso lato server (`DIARIO_ACTOR`).
5. Audit come ogni altro comando: reason "registrato tramite il diario", correlation/idempotency key
   `diario-pagamento-<consegna>-n<tentativo>` (il tentativo si rilegge dal database: un nuovo pagamento dopo un
   annullo ha chiave diversa).
6. Nessun segreto nei messaggi: gli errori mostrati sono quelli dell'adapter CLI.

## Guardie specifiche dei pagamenti

- Il metodo NON si indovina: se manca la proposta si ferma e lo chiede (BONIFICO, CONTANTI, CARTA, BIZUM, ALTRO).
- Senza codici consegna espliciti la frase libera propone TUTTE le consegne da incassare del cliente; nella pagina
  ogni consegna ha una casella da togliere prima di confermare.
- Rilettura live prima di ogni consegna: se nel frattempo risulta gia' pagata viene saltata e lo dice; se la
  seconda di due fallisce, l'esito dice cosa e' gia' stato registrato e cosa no.
- Data di pagamento: oggi (Canarie) se non detta; mai nel futuro, mai prima della consegna.
- Importo facoltativo e solo con una consegna. Il listino e' vuoto: il diario non mostra valori in euro.

## Test

`tests/infrastructure/postgresql/test_diario_incassi.py` (PostgreSQL usa-e-getta) e
`tests/diario_web/test_app_incassi.py` (rotte e interprete, senza database ne' modello).
