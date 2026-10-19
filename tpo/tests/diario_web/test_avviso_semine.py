"""Avviso sul telefono delle sessioni di semina (17/10/2026). Nessun database, nessuna rete: il piano e ntfy sono finti.
Si verifica il testo (totale per varieta', nessun nome di cliente), il giorno/ora, il non-doppione, i due canali (ntfy e Telegram) e gli errori leggibili."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import app as app_module, avviso_semine as av, controlli, sessioni_semina as ss

AUTH = ("matteo", "segreta")
TZ = ZoneInfo("Atlantic/Canary")
DOMENICA = date(2026, 10, 18)
CLIENTI = ("Abaluus", "El Gringo", "Hotel Duna Blanca", "Sushi Tefia")


def _riga(i, varieta, cliente, quantita, ideale, consegna, grammi="30"):
    return ss.RigaSemina(f"RPS-{i}", varieta, cliente, f"ORD-{i:06d}", consegna, "PIANIFICATA", Decimal(quantita), "SET",
                         Decimal(grammi), ideale, consegna)


RIGHE = [
    _riga(1, "Afila", "Abaluus", "1", date(2026, 10, 18), date(2026, 10, 28)),
    _riga(2, "Afila", "El Gringo", "2", date(2026, 10, 18), date(2026, 10, 28)),
    _riga(3, "Cilantro", "Abaluus", "1", date(2026, 10, 19), date(2026, 10, 30)),
    _riga(4, "Rábano", "Hotel Duna Blanca", "0.5", date(2026, 10, 20), date(2026, 10, 29)),
    _riga(5, "Mizuna", "Sushi Tefia", "2", date(2026, 10, 21), date(2026, 10, 31)),
]


def _piano(righe=RIGHE, oggi=DOMENICA):
    return ss.assegna(list(righe), oggi, ss.GIORNI_DEFAULT, 2)


def test_il_testo_ha_il_totale_per_varieta_e_complessivo_senza_clienti() -> None:
    a = av.componi(_piano())
    assert a.titolo == "Semina di domenica 18/10: 4,5 SET"
    righe = a.corpo.splitlines()
    assert righe[:3] == ["Afila 3 SET", "Cilantro 1 SET", "Rábano 0,5 SET"]
    assert "Prossima, mercoledi 21/10: Mizuna 2 SET" in righe
    assert righe[-1] == "Tocca per vedere per chi."
    assert a.priorita == 4 and a.tag == "semine-2026-10-18"
    testo = a.titolo + a.corpo
    assert not any(cliente in testo for cliente in CLIENTI)      # i clienti non passano dal servizio esterno
    assert "ORD-" not in testo


def test_senza_semine_lo_dice_e_non_urla() -> None:
    a = av.componi(_piano([]))
    assert a.titolo == "Domenica 18/10: nessuna semina da fare" and a.priorita == 3
    assert a.corpo == "Tocca per vedere per chi."


def test_segnala_ordini_da_verificare_e_scaduti_senza_nominarli() -> None:
    o = ss.OrdineDaVerificare("ORD-000099", "Splash", date(2026, 10, 10), 0, ("Afila 1 SET",), "APERTO")
    p = replace(_piano(), scaduti=(o, o), da_verificare=(o,))
    corpo = av.componi(p).corpo
    assert "Attenzione: da verificare 1, ordini scaduti 2." in corpo and "Splash" not in corpo


@pytest.mark.parametrize("quando,atteso", [
    (datetime(2026, 10, 18, 7, 0, tzinfo=TZ), True),      # domenica
    (datetime(2026, 10, 21, 9, 59, tzinfo=TZ), True),     # mercoledi
    (datetime(2026, 10, 18, 6, 59, tzinfo=TZ), False),
    (datetime(2026, 10, 18, 10, 0, tzinfo=TZ), False),
    (datetime(2026, 10, 19, 8, 0, tzinfo=TZ), False),     # lunedi
])
def test_finestra_mercoledi_e_domenica_mattina(quando, atteso) -> None:
    assert av.finestra_ok(quando) is atteso


class _Risposta:
    def __init__(self, testo="", status=200):
        self._testo, self.status = testo, status

    def read(self):
        return self._testo.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Ntfy:
    """ntfy finto: GET = cache degli ultimi messaggi, POST = pubblicazione."""

    def __init__(self, cache=""):
        self.cache, self.inviati, self.letture, self.stato = cache, [], [], 200

    def __call__(self, richiesta, timeout=None):
        if isinstance(richiesta, str):
            self.letture.append(richiesta)
            return _Risposta(self.cache)
        self.inviati.append((richiesta.full_url, richiesta.get_method(), json.loads(richiesta.data.decode("utf-8"))))
        return _Risposta("", self.stato)


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "canale-segreto-xyz")
    monkeypatch.delenv("NTFY_SERVER", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("DIARIO_URL", raising=False)
    visti = []

    def finto_piano(settings, oggi=None, **kw):
        visti.append(oggi)
        return _piano(oggi=oggi)

    monkeypatch.setattr(ss, "piano", finto_piano)
    monkeypatch.setattr(controlli, "leggi", lambda settings, adesso=None: controlli.componi([], [], [], adesso))
    return visti


DOMENICA_7_30 = datetime(2026, 10, 18, 7, 30, tzinfo=TZ)


def test_invia_il_messaggio_giusto_a_ntfy(ambiente) -> None:
    ntfy = _Ntfy()
    esito = av.esegui(object(), DOMENICA_7_30, opener=ntfy)
    assert esito["inviato"] is True and esito["titolo"] == "Semina di domenica 18/10: 4,5 SET"
    (url, metodo, corpo), = ntfy.inviati
    assert url == "https://ntfy.sh" and metodo == "POST"          # il canale e' nel corpo, non nell'indirizzo
    assert corpo["topic"] == "canale-segreto-xyz" and corpo["priority"] == 4
    assert corpo["click"] == "https://tpo-diario.onrender.com/#semine"
    assert "semine-2026-10-18" in corpo["tags"] and "Afila 3 SET" in corpo["message"]
    assert ambiente == [date(2026, 10, 18)]


def test_non_rimanda_lo_stesso_avviso_due_volte(ambiente) -> None:
    gia = json.dumps({"event": "message", "tags": ["semine-2026-10-18", "seedling"]})
    ntfy = _Ntfy(cache="\n".join(["non json", gia]))
    esito = av.esegui(object(), DOMENICA_7_30, opener=ntfy)
    assert esito["inviato"] is False and "gia' inviato" in esito["motivo"] and ntfy.inviati == []
    altro_giorno = _Ntfy(cache=json.dumps({"tags": ["semine-2026-10-14"]}))
    assert av.esegui(object(), DOMENICA_7_30, opener=altro_giorno)["inviato"] is True


def test_se_non_riesce_a_controllare_la_cache_manda_comunque(ambiente) -> None:
    class Rotto(_Ntfy):
        def __call__(self, richiesta, timeout=None):
            if isinstance(richiesta, str):
                raise OSError("rete")
            return super().__call__(richiesta, timeout)

    ntfy = Rotto()
    assert av.esegui(object(), DOMENICA_7_30, opener=ntfy)["inviato"] is True and len(ntfy.inviati) == 1


def test_fuori_giorno_o_ora_non_legge_il_database_e_non_invia(ambiente) -> None:
    ntfy = _Ntfy()
    lunedi = datetime(2026, 10, 19, 7, 30, tzinfo=TZ)
    esito = av.esegui(object(), lunedi, opener=ntfy)
    assert esito["inviato"] is False and "Fuori orario" in esito["motivo"]
    assert ntfy.inviati == [] and ntfy.letture == [] and ambiente == []
    assert av.esegui(object(), lunedi, forza=True, opener=ntfy)["inviato"] is True     # forza = prova a mano


def test_anteprima_e_prova(ambiente) -> None:
    ntfy = _Ntfy()
    anteprima = av.esegui(object(), DOMENICA_7_30, anteprima=True, opener=ntfy)
    assert anteprima["inviato"] is False and anteprima["motivo"] == "anteprima" and "Afila 3 SET" in anteprima["messaggio"]
    assert ntfy.inviati == []
    prova = av.esegui(object(), datetime(2026, 10, 19, 15, 0, tzinfo=TZ), prova=True, opener=ntfy)   # a qualunque ora
    assert prova["inviato"] is True and ntfy.inviati[0][2]["title"] == "Prova avviso semine"
    assert ambiente == [date(2026, 10, 18)]                      # la prova non legge il piano (solo l'anteprima l'ha letto)


def test_errori_leggibili(ambiente, monkeypatch) -> None:
    ntfy = _Ntfy()
    ntfy.stato = 500
    with pytest.raises(av.AvvisoNonPossibile, match="500"):
        av.esegui(object(), DOMENICA_7_30, opener=ntfy)

    def giu(richiesta, timeout=None):
        if isinstance(richiesta, str):
            return _Risposta("")
        raise OSError("connessione rifiutata")

    with pytest.raises(av.AvvisoNonPossibile, match="Avviso non inviato: connessione rifiutata"):
        av.esegui(object(), DOMENICA_7_30, opener=giu)
    monkeypatch.delenv("NTFY_TOPIC")
    with pytest.raises(av.AvvisoNonPossibile, match="NTFY_TOPIC"):
        av.esegui(object(), DOMENICA_7_30, opener=_Ntfy())
    assert av.esegui(object(), DOMENICA_7_30, anteprima=True, opener=_Ntfy())["inviato"] is False   # l'anteprima non ne ha bisogno


def test_il_modulo_non_scrive_sul_database() -> None:
    sorgente = open(av.__file__, encoding="utf-8").read().upper()
    for vietato in ("INSERT ", "UPDATE ", "DELETE ", "_CONNECT(", "EXECUTE("):
        assert vietato not in sorgente


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_route_richiede_la_password_e_inoltra_le_opzioni(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.post("/api/avviso-semine").status_code == 401
    visti = []
    monkeypatch.setattr(av, "esegui", lambda settings, **kw: visti.append(kw) or {"inviato": False, "motivo": "anteprima"})
    r = client.post("/api/avviso-semine?anteprima=1&forza=1", auth=AUTH)
    assert r.status_code == 200 and r.json()["motivo"] == "anteprima"
    assert visti == [{"anteprima": True, "prova": False, "forza": True}]
    assert client.get("/api/avviso-semine", auth=AUTH).status_code == 405       # solo POST: nessun invio da un link


def test_route_errori_leggibili(monkeypatch) -> None:
    client = _client(monkeypatch)

    def senza_canale(settings, **kw):
        raise av.AvvisoNonPossibile("NTFY_TOPIC non impostata")

    monkeypatch.setattr(av, "esegui", senza_canale)
    r = client.post("/api/avviso-semine", auth=AUTH)
    assert r.status_code == 503 and r.json() == {"inviato": False, "errore": "NTFY_TOPIC non impostata"}

    def database_giu(settings, **kw):
        raise RuntimeError("database spento")

    monkeypatch.setattr(av, "esegui", database_giu)
    r = client.post("/api/avviso-semine", auth=AUTH)
    assert r.status_code == 503 and "database spento" in r.json()["errore"]


# ---- Telegram (canale preferito se configurato) ----

TOKEN = "123456:ABC-token-segretissimo"
DOMENICA_8_30 = datetime(2026, 10, 18, 8, 30, tzinfo=TZ)


@pytest.fixture
def telegram(ambiente, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")
    return ambiente


def test_il_canale_e_telegram_solo_se_ci_sono_token_e_chat(ambiente, monkeypatch) -> None:
    assert av.canale() == "ntfy"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert av.canale() == "ntfy"                                   # manca la chat
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")
    assert av.canale() == "telegram"
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "  ")
    assert av.canale() == "ntfy"


def test_telegram_manda_titolo_corpo_e_link_senza_clienti(telegram) -> None:
    ntfy = _Ntfy()
    esito = av.esegui(object(), DOMENICA_7_30, opener=ntfy)
    assert esito["inviato"] is True and esito["canale"] == "telegram"
    (url, metodo, corpo), = ntfy.inviati
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage" and metodo == "POST"
    assert corpo["chat_id"] == "987654" and corpo["disable_web_page_preview"] is True
    assert corpo["text"].startswith("Semina di domenica 18/10: 4,5 SET\n\nAfila 3 SET")
    assert corpo["text"].endswith("https://tpo-diario.onrender.com/#semine")
    assert not any(cliente in corpo["text"] for cliente in CLIENTI)
    assert ntfy.letture == []                                        # nessuna cache da consultare


def test_telegram_ha_la_stessa_finestra_07_10_e_non_chiede_la_cache(telegram) -> None:
    ntfy = _Ntfy()
    esito = av.esegui(object(), DOMENICA_8_30, opener=ntfy)          # un ritardo di GitHub non fa perdere l'avviso
    assert esito["inviato"] is True and esito["canale"] == "telegram" and ntfy.letture == []
    tardi = av.esegui(object(), datetime(2026, 10, 18, 10, 0, tzinfo=TZ), opener=ntfy)
    assert tardi["inviato"] is False and "07:00 e le 10:00" in tardi["motivo"] and len(ntfy.inviati) == 1
    assert av.esegui(object(), datetime(2026, 10, 18, 10, 0, tzinfo=TZ), forza=True, opener=ntfy)["inviato"] is True


def test_telegram_prova_e_anteprima(telegram) -> None:
    ntfy = _Ntfy()
    prova = av.esegui(object(), datetime(2026, 10, 19, 15, 0, tzinfo=TZ), prova=True, opener=ntfy)
    assert prova["inviato"] is True and prova["canale"] == "telegram"
    assert ntfy.inviati[0][2]["text"].startswith("Prova avviso semine")
    anteprima = av.esegui(object(), DOMENICA_7_30, anteprima=True, opener=ntfy)
    assert anteprima["inviato"] is False and anteprima["canale"] == "telegram" and len(ntfy.inviati) == 1


def test_telegram_errori_leggibili_senza_token(telegram) -> None:
    import io
    import urllib.error

    def rifiuta(richiesta, timeout=None):
        corpo = json.dumps({"ok": False, "description": "Forbidden: bot was blocked"}).encode("utf-8")
        raise urllib.error.HTTPError(richiesta.full_url, 403, "Forbidden", {}, io.BytesIO(corpo))

    with pytest.raises(av.AvvisoNonPossibile) as e:
        av.esegui(object(), DOMENICA_7_30, opener=rifiuta)
    assert "403" in str(e.value) and "bot was blocked" in str(e.value) and TOKEN not in str(e.value)

    def giu(richiesta, timeout=None):
        raise OSError(f"impossibile raggiungere {richiesta.full_url}")

    with pytest.raises(av.AvvisoNonPossibile) as e:
        av.esegui(object(), DOMENICA_7_30, opener=giu)
    assert TOKEN not in str(e.value) and "***" in str(e.value)


def test_ntfy_non_espone_il_nome_del_canale_negli_errori(ambiente) -> None:
    def giu(richiesta, timeout=None):
        if isinstance(richiesta, str):
            return _Risposta("")
        raise OSError("errore su canale-segreto-xyz")

    with pytest.raises(av.AvvisoNonPossibile) as e:
        av.esegui(object(), DOMENICA_7_30, opener=giu)
    assert "canale-segreto-xyz" not in str(e.value)


def test_senza_nessun_canale_dice_cosa_manca(ambiente, monkeypatch) -> None:
    monkeypatch.delenv("NTFY_TOPIC")
    with pytest.raises(av.AvvisoNonPossibile, match="TELEGRAM_BOT_TOKEN"):
        av.esegui(object(), DOMENICA_7_30, opener=_Ntfy())


# ---- righe del promemoria stadi (19/10/2026) ----

def _controllo_con_cose(settings, adesso=None):
    giorno = datetime(2026, 10, 15, 9, tzinfo=TZ)
    semine = [("SEM-1", "H-1", "Hinojo", "GERMINAZIONE", giorno, Decimal("1"), "SET", 3, 20, 0, None)]   # 15+3 = 18: oggi
    clienti = [("CLI-1", "Restaurante Salvaje", True), ("CLI-2", "Restaurante Selvaje", True)]
    return controlli.componi(semine, clienti, [], adesso)


def test_l_avviso_aggiunge_le_righe_del_promemoria_senza_nomi_di_clienti(ambiente, monkeypatch) -> None:
    monkeypatch.setattr(controlli, "leggi", _controllo_con_cose)
    prova = av.esegui(object(), DOMENICA_7_30, anteprima=True)
    righe = prova["messaggio"].split("\n")
    assert "Passano a luce: Hinojo 1." in righe
    assert "Da controllare: 1 (vedi Oggi)." in righe
    assert righe[-1] == "Tocca per vedere per chi."          # l'invito resta in fondo
    assert "Salvaje" not in prova["messaggio"] and "Selvaje" not in prova["messaggio"]


def test_se_il_controllo_si_rompe_l_avviso_parte_lo_stesso(ambiente, monkeypatch) -> None:
    def rotto(settings, adesso=None):
        raise RuntimeError("db lento")

    monkeypatch.setattr(controlli, "leggi", rotto)
    prova = av.esegui(object(), DOMENICA_7_30, anteprima=True)
    assert prova["titolo"].startswith("Semina di domenica 18/10") and "Passano a luce" not in prova["messaggio"]


def test_senza_nulla_da_segnalare_il_testo_resta_quello_di_prima(ambiente) -> None:
    prova = av.esegui(object(), DOMENICA_7_30, anteprima=True)
    assert "Passano a luce" not in prova["messaggio"] and "Da controllare" not in prova["messaggio"]
