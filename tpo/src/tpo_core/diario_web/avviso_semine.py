"""AVVISO SUL TELEFONO delle sessioni di semina (17/10/2026, richiesta di Matteo): mercoledi e domenica mattina arriva una
notifica con COSA seminare, il TOTALE PER VARIETA' e il totale complessivo. Il "per chi" (clienti) NON e' nel messaggio:
passa da un servizio esterno (Telegram o ntfy), quindi resta nella schermata "Semine" del diario (nel messaggio c'e' il link).

Sola lettura sul database: legge il piano con `sessioni_semina.piano` (lo stesso della schermata Semine). L'unica cosa che
"scrive" e' la notifica verso il servizio esterno. Mai scritture sul database (guardia D del freeze OPERATIONAL_WEB_ADAPTER).

Canale (variabili d'ambiente, mai nel repository):
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID   se ci sono entrambe, l'avviso va su Telegram (canale preferito)
  NTFY_TOPIC   in alternativa, nome del canale ntfy, lungo e segreto (ntfy.sh puo' rifiutare l'IP di Render con HTTP 429)
  NTFY_SERVER  default https://ntfy.sh
  DIARIO_URL   indirizzo del diario, nel messaggio / aperto toccando la notifica (default https://tpo-diario.onrender.com)

Quando parte: solo mercoledi e domenica (ora delle Canarie) tra le 07:00 e le 10:00, quindi un ritardo del servizio che lo
lancia (GitHub) non fa perdere l'avviso. Nessun doppione: con ntfy una seconda chiamata nella stessa mattina non rimanda
l'avviso (cache di ntfy); con Telegram, che non ha cache, il workflow fa partire una sola delle due chiamate in UTC
(quella giusta per ora legale o solare).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable
from zoneinfo import ZoneInfo

from ..infrastructure.postgresql.settings import PostgreSQLSettings
from . import sessioni_semina as ss

TZ = ZoneInfo("Atlantic/Canary")
NTFY_DEFAULT = "https://ntfy.sh"
DIARIO_URL_DEFAULT = "https://tpo-diario.onrender.com"
ORA_DA = 7
ORA_A = 10                                  # esclusa
TIMEOUT = 15

Opener = Callable[..., object]


class AvvisoNonPossibile(Exception):
    """Configurazione mancante o servizio di notifica non raggiungibile: il messaggio e' leggibile."""


@dataclass(frozen=True)
class Avviso:
    titolo: str
    corpo: str
    priorita: int                           # 1..5 come ntfy (3 = normale)
    tag: str                                # es. semine-2026-10-18: serve a non rimandare lo stesso avviso


def _n(value) -> str:
    """Quantita' all'italiana: 4.50 -> "4,5"."""
    text = format(Decimal(value).normalize(), "f")
    return text.replace(".", ",")


def _breve(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _riga_varieta(v: ss.VarietaDaSeminare) -> str:
    return f"{v.varieta} {_n(v.quantita)} {v.unita}"


def _totale(sessione: ss.Sessione) -> str:
    return ", ".join(f"{_n(q)} {u}" for u, q in sessione.quantita_per_unita.items())


def componi(piano: ss.PianoSessioni) -> Avviso:
    """Piano -> testo della notifica. Funzione pura. Nessun nome di cliente."""
    sessioni = list(piano.sessioni)
    oggi = next((s for s in sessioni if s.data == piano.oggi), None)
    prossime = [s for s in sessioni if s.data > piano.oggi]
    nome_oggi = ss.NOMI_GIORNO[piano.oggi.weekday()]
    righe: list[str] = []
    if oggi is not None:
        titolo = f"Semina di {nome_oggi} {_breve(oggi.data)}: {_totale(oggi)}"
        righe += [_riga_varieta(v) for v in oggi.varieta]
        priorita = 4
    else:
        titolo = f"{nome_oggi.capitalize()} {_breve(piano.oggi)}: nessuna semina da fare"
        priorita = 3
    if prossime:
        p = prossime[0]
        righe.append(f"Prossima, {p.nome_giorno} {_breve(p.data)}: {', '.join(_riga_varieta(v) for v in p.varieta)}")
    extra = []
    if piano.da_verificare:
        extra.append(f"da verificare {len(piano.da_verificare)}")
    if piano.scaduti:
        extra.append(f"ordini scaduti {len(piano.scaduti)}")
    if extra:
        righe.append("Attenzione: " + ", ".join(extra) + ".")
    righe.append("Tocca per vedere per chi.")
    return Avviso(titolo, "\n".join(righe), priorita, f"semine-{piano.oggi.isoformat()}")


def _diario_url() -> str:
    return os.environ.get("DIARIO_URL", DIARIO_URL_DEFAULT).strip().rstrip("/") or DIARIO_URL_DEFAULT


def canale() -> str:
    """"telegram" se sono impostati sia TELEGRAM_BOT_TOKEN sia TELEGRAM_CHAT_ID, altrimenti "ntfy"."""
    if os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip():
        return "telegram"
    return "ntfy"


def _config() -> tuple[str, str, str]:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        raise AvvisoNonPossibile(
            "Nessun canale configurato: servono TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (oppure NTFY_TOPIC).")
    server = os.environ.get("NTFY_SERVER", NTFY_DEFAULT).strip().rstrip("/") or NTFY_DEFAULT
    return topic, server, _diario_url()


def gia_inviato(server: str, topic: str, tag: str, opener: Opener = urllib.request.urlopen) -> bool:
    """Solo ntfy: guarda nella cache (ultime 12 ore) se un avviso con questo tag e' gia' arrivato. Se non si riesce a
    controllare risponde False: meglio un doppione di un avviso mancato."""
    try:
        with opener(f"{server}/{topic}/json?poll=1&since=12h", timeout=TIMEOUT) as risposta:
            for riga in risposta.read().decode("utf-8").splitlines():
                try:
                    if tag in (json.loads(riga).get("tags") or []):
                        return True
                except ValueError:
                    continue
    except Exception:  # noqa: BLE001 -- controllo best effort
        return False
    return False


def _pubblica(richiesta: urllib.request.Request, opener: Opener, segreti: tuple[str, ...] = ()) -> None:
    """Manda la richiesta. Gli errori sono leggibili e NON contengono mai token o nome del canale."""
    def pulito(testo: str) -> str:
        for segreto in segreti:
            if segreto:
                testo = testo.replace(segreto, "***")
        return testo

    try:
        with opener(richiesta, timeout=TIMEOUT) as risposta:
            if getattr(risposta, "status", 200) >= 300:
                raise AvvisoNonPossibile(f"Il servizio di notifica ha risposto {risposta.status}.")
    except AvvisoNonPossibile:
        raise
    except urllib.error.HTTPError as exc:
        dettaglio = ""
        try:
            dettaglio = str(json.loads(exc.read().decode("utf-8")).get("description") or "")
        except Exception:  # noqa: BLE001
            pass
        raise AvvisoNonPossibile(pulito(f"Avviso non inviato: HTTP {exc.code} {exc.reason}"
                                        + (f" - {dettaglio}" if dettaglio else ""))) from None
    except Exception as exc:  # noqa: BLE001 -- mostrato, mai un crash silenzioso
        raise AvvisoNonPossibile(pulito(f"Avviso non inviato: {exc}")) from None


def _invia_telegram(avviso: Avviso, opener: Opener) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    chat = os.environ["TELEGRAM_CHAT_ID"].strip()
    testo = f"{avviso.titolo}\n\n{avviso.corpo}\n\n{_diario_url()}/#semine"
    corpo = {"chat_id": chat, "text": testo, "disable_web_page_preview": True}
    richiesta = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    _pubblica(richiesta, opener, (token,))


def _invia_ntfy(avviso: Avviso, opener: Opener) -> None:
    topic, server, diario = _config()
    corpo = {"topic": topic, "title": avviso.titolo, "message": avviso.corpo, "priority": avviso.priorita,
             "tags": [avviso.tag, "seedling"], "click": f"{diario}/#semine"}
    richiesta = urllib.request.Request(
        server, data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    _pubblica(richiesta, opener, (topic,))


def invia(avviso: Avviso, opener: Opener = urllib.request.urlopen) -> None:
    if canale() == "telegram":
        _invia_telegram(avviso, opener)
    else:
        _invia_ntfy(avviso, opener)


def finestra_ok(ora: datetime) -> bool:
    """Mercoledi/domenica tra le 07:00 e le 10:00 (ora delle Canarie). Niente doppioni: con ntfy si guarda la cache; con
    Telegram ci pensa il workflow, che di due chiamate in UTC (ora legale / solare) ne fa partire una sola."""
    return ora.isoweekday() in ss.GIORNI_DEFAULT and ORA_DA <= ora.hour < ORA_A


def esegui(settings: PostgreSQLSettings, ora: datetime | None = None, *, anteprima: bool = False, prova: bool = False,
           forza: bool = False, opener: Opener = urllib.request.urlopen) -> dict:
    """Prepara e (se non e' anteprima) manda l'avviso. Ritorna sempre un dizionario leggibile, mai un'eccezione per
    "fuori orario" o "gia' mandato"."""
    ora = (ora or datetime.now(TZ)).astimezone(TZ)
    telegram = canale() == "telegram"
    if prova:
        avviso = Avviso("Prova avviso semine", "Se leggi questo, le notifiche del diario arrivano sul telefono.", 3,
                        "semine-prova")
        if not anteprima:
            invia(avviso, opener)
        return {"inviato": not anteprima, "motivo": "prova", "canale": canale(), "titolo": avviso.titolo,
                "messaggio": avviso.corpo}
    if not forza and not finestra_ok(ora):
        return {"inviato": False, "motivo": "Fuori orario: l'avviso parte solo mercoledi e domenica tra le 07:00 e le 10:00 "
                                            "(ora delle Canarie). Per provare: forza=1.", "titolo": None, "messaggio": None}
    avviso = componi(ss.piano(settings, oggi=ora.date()))
    base = {"titolo": avviso.titolo, "messaggio": avviso.corpo, "canale": canale()}
    if anteprima:
        return {**base, "inviato": False, "motivo": "anteprima"}
    if not telegram:
        topic, server, _ = _config()
        if not forza and gia_inviato(server, topic, avviso.tag, opener):
            return {**base, "inviato": False, "motivo": "Avviso di oggi gia' inviato."}
    invia(avviso, opener)
    return {**base, "inviato": True, "motivo": "inviato"}
