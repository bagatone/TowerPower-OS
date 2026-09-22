# DIARIO CONVERSAZIONALE — implementazione Fase 1

**Stato:** codice scritto e verificato per sintassi, non ancora eseguito né
testato con `pytest` (nessun accesso reale al database da questa sessione —
vedi `handoff/scoperta-tpo-roadmap-2026-09.md`, Fatto 26/27). Da far
passare da `pytest` reale e verificare manualmente prima di fidarsene,
come ogni altro pezzo di questo sistema.

**Governance:** copre solo il perimetro approvato in
`handoff/diario-governance-addendum.md` (semina commission + semina
transition, esposizione internet via Render autorizzata a condizione
delle sei misure lì elencate). Non riapre né sostituisce
`docs/architecture/OPERATIONAL_WEB_ADAPTER_GOVERNANCE_FREEZE.md`.

## Cosa fa

Una pagina web con un solo campo di testo. Si scrive in italiano cosa è
successo in campo ("Mizuna e Rábano sono passate in luce", "seminato 3
set di rábano"); il servizio interpreta la frase con un modello Claude,
mostra la proposta esatta (varietà, lotto seme, grammi, stadio di
arrivo — mai eseguita subito), e solo dopo un tocco di conferma esegue
il comando reale, lo stesso già usato da terminale finora
(`semina commission` / `semina transition`), tramite lo stesso codice
applicativo già testato — non un percorso nuovo.

## File aggiunti

```
src/tpo_core/diario_web/
  __init__.py
  app.py            # FastAPI: rotte, autenticazione, orchestrazione
  auth.py           # HTTP Basic Auth obbligatoria (DIARIO_PASSWORD)
  db_context.py      # sole letture: varietà, semine attive, lotti/protocolli
  interpreter.py     # chiamata al modello Claude, restituisce una proposta strutturata
  actions.py          # costruisce ed esegue i comandi reali via run_semina_command
  static/index.html   # unica pagina, nessuna libreria esterna
tests/diario_web/test_actions.py   # test di logica pura (nessun DB reale richiesto)
scripts/diario/run_diario_local.sh # avvio locale per un test manuale
render.yaml                        # blueprint di deploy
```

Aggiunta anche la dipendenza `anthropic` a `requirements.txt`.

## Come funziona sotto: le stesse garanzie usate a mano finora

- **Mai inventare un identificativo**: `db_context.py` legge sempre dal
  database vero, mai valori presunti. Il modello Claude in
  `interpreter.py` può proporre *solo* varietà tra quelle che gli vengono
  fornite come contesto — se non trova corrispondenza certa, restituisce
  una richiesta di chiarimento invece di indovinare (imposto nel prompt).
- **Doppia lettura**: la proposta mostrata all'utente (`/api/interpreta`)
  legge una volta lo stato reale; la conferma (`/api/conferma`, in
  `actions.py`) lo rilegge di nuovo un istante prima di scrivere — se nel
  frattempo qualcosa è cambiato (un altro movimento, un'altra sessione),
  non usa il valore vecchio.
- **Nessuna nuova regola di dominio**: l'esecuzione vera passa sempre da
  `run_semina_command` (lo stesso adapter CLI di
  `src/tpo_core/cli/semina.py`), costruendo solo l'oggetto `Namespace`
  che si aspetta — stessa logica, stessi controlli, stessi errori
  (`LSE_ANOMALY_BLOCKED`, `SEMINA_LIFECYCLE_TIMESTAMP_REGRESSION`, ecc.),
  solo mostrati nella pagina invece che nel terminale.
- **Passi di stadio mai saltati**: se serve passare da AVVIATA a CRESCITA,
  `actions.py` calcola da solo tutti i passaggi intermedi
  (GERMINAZIONE, LUCE) ed esegue uno alla volta, rileggendo la versione
  della semina prima di ciascuno — stessa logica già usata e corretta a
  mano nel Fatto 27 di oggi (bug del timestamp non monotono già risolto
  qui alla radice, orario ricalcolato a ogni passo).
- **Tracciato come sempre**: ogni scrittura genera `audit_eventi` con
  `actor` fisso (`DIARIO_ACTOR`, di norma `giulia@towerpower`),
  `correlation_id`/`idempotency_key` generati automaticamente,
  `reason` che dice esplicitamente "registrata tramite il diario".

## Cosa NON copre ancora (deliberatamente)

Solo `semina commission` e `semina transition`. Non raccolta, non
carico, non consegna, non correzione di anomalie (quella resta manuale
com'è oggi — un'anomalia richiede sempre di leggere il testo esatto e
decidere, non è nel perimetro approvato). Ampliare il perimetro è una
richiesta a parte, con lo stesso processo (proposta, Owner Decision,
poi codice).

## Prima di fidarsene: cosa deve verificare Matteo

1. **`pytest tests/diario_web/`** — i test scritti qui non toccano un
   database reale (usano dei doppi al posto delle letture), quindi non
   sostituiscono una prova reale, ma verificano che la logica di calcolo
   (passi di stadio, grammi, casi ambigui) sia corretta.
2. **Prova manuale in locale**, prima di mettere qualunque cosa online:
   ```
   export ANTHROPIC_API_KEY=...   # una chiave vera, da console.anthropic.com
   export DIARIO_PASSWORD=...     # una password a scelta, solo per la prova locale
   scripts/diario/run_diario_local.sh
   ```
   poi aprire `http://127.0.0.1:8766` (chiede utente/password — utente
   qualunque, password quella appena esportata), scrivere una frase di
   prova e verificare che la proposta mostrata sia quella giusta PRIMA
   di premere conferma. La prima prova reale, quando si preme conferma,
   scrive per davvero nel database di produzione — usare un caso vero e
   verificato, come per ogni comando finora.
3. **Deploy su Render** (dopo che 1 e 2 sono andati bene):
   - creare un nuovo Web Service su Render, collegato a questo
     repository GitHub (branch `sprint-4.4-production-planning`, o quella
     scelta);
   - Render legge `render.yaml` da solo (Blueprint);
   - impostare le variabili d'ambiente elencate lì (tutte con `sync: false`,
     quindi vanno inserite a mano nel pannello Render, mai nel repository):
     `TPO_DATABASE_*` (stessi valori di `runtime/secrets/`),
     `ANTHROPIC_API_KEY`, `DIARIO_PASSWORD` (una password vera, diversa da
     quella di prova locale);
   - verificare `https://<nome-servizio>.onrender.com/healthz` (senza
     password, conferma solo che il processo è partito) e poi
     `/api/salute` (con password, conferma che legge il database vero).
4. **Commit e push**, come sempre, a cura di Matteo/Giulia.
