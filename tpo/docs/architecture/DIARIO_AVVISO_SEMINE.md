# Avviso semine sul telefono (17/10/2026)

Richiesta di Matteo: ogni **mercoledi e domenica mattina** una notifica sul telefono con cosa seminare, il **totale per
varieta'** e il totale complessivo. Il "per chi" (clienti) resta nella schermata **Semine** del diario, che si apre
toccando la notifica: i nomi dei clienti non passano dal servizio esterno.

## Come funziona
1. **GitHub Actions** (workflow `tpo/deploy/github/avviso-semine.yml`, da copiare in `.github/workflows/`; gratuito) chiama alle 06:35 e 07:35 UTC
   `POST {DIARIO_URL}/api/avviso-semine` con la password del diario. Sveglia il servizio Render (che dorme) con nuovi tentativi.
2. Il diario (`diario_web/avviso_semine.py`) legge il piano con `sessioni_semina.piano` (sola lettura, nessuna scrittura sul
   database) e compone il messaggio. Parte solo mercoledi/domenica tra le 07:00 e le 10:00 ora delle Canarie.
3. Lo manda a **ntfy** (`https://ntfy.sh`) sul canale `NTFY_TOPIC`. Prima controlla nella cache di ntfy (12 ore) che l'avviso
   di oggi non sia gia' arrivato: i due tentativi in UTC non fanno mai doppioni.

Esempio:  `Semina di domenica 18/10: 4,5 SET` / `Afila 3 SET` / `Cilantro 1 SET` / `Rábano 0,5 SET` /
`Prossima, mercoledi 21/10: Mizuna 2 SET` / `Tocca per vedere per chi.`

## Messa in funzione (una volta)
1. **Telefono**: installa l'app **ntfy** (iPhone/Android) e iscriviti a un canale con un nome lungo e segreto
   (es. `tpo-semine-` + 12 caratteri a caso). Chi conosce il nome legge gli avvisi: trattalo come una password.
2. **Render** (pannello del servizio `tpo-diario` > Environment): `NTFY_TOPIC` = quel nome. (`NTFY_SERVER` e `DIARIO_URL`
   hanno gia' un valore predefinito.)
3. **GitHub** (Settings > Secrets and variables > Actions): `DIARIO_URL` (es. `https://tpo-diario.onrender.com`) e
   `DIARIO_PASSWORD` (la stessa del diario).
4. Copia il workflow: `mkdir -p .github/workflows && cp tpo/deploy/github/avviso-semine.yml .github/workflows/` (dalla cartella `towerpower-website`) e portalo sul ramo **main** (quelli con `schedule` partono solo da li).
5. **Prova**: GitHub > Actions > "Avviso semine" > Run workflow (manda un messaggio di prova), oppure da terminale:
   `curl -u x:PASSWORD -X POST "https://tpo-diario.onrender.com/api/avviso-semine?prova=1"`.
   Anteprima del messaggio vero senza mandarlo: `...?anteprima=1`. Forzare l'invio fuori orario: `...?forza=1`.

## Limiti dichiarati
- ntfy.sh e' un servizio gratuito di terzi: il messaggio contiene solo varieta' e SET, mai clienti ne' codici ordine.
  Volendo, ntfy si puo' ospitare in proprio.
- Gli orari dei workflow di GitHub possono slittare di qualche minuto (a volte di piu'): per questo la finestra 07:00-10:00.
- Se il servizio Render non si sveglia o la password e' sbagliata, il workflow fallisce e GitHub lo segnala nella pagina Actions.
