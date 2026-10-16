"""Piano a sessioni di semina (16/10/2026): logica pura di raggruppamento, nessun database."""
from datetime import date
from decimal import Decimal

from src.tpo_core.diario_web import sessioni_semina as ss

GIOVEDI = date(2026, 10, 15)                 # oggi: giovedi'. Sessioni: dom 18/10, mer 21/10, dom 25/10


def _r(varieta="Afila", cliente="Abaluus", ideale=date(2026, 10, 18), quantita="1", consegna=date(2026, 10, 28),
       ordine="ORD-000001", ord_cons=None, grammi="30", riga="RPS-000001", stato="APERTO"):
    return ss.RigaSemina(riga, varieta, cliente, ordine, ord_cons or consegna, "PIANIFICATA", Decimal(quantita), "SET",
                         Decimal(grammi), ideale, consegna, stato)


def test_two_sowing_days_are_wednesday_and_sunday_by_default():
    assert ss.GIORNI_DEFAULT == (3, 7)
    assert date(2026, 10, 18).isoweekday() == 7 and date(2026, 10, 21).isoweekday() == 3


def test_a_line_goes_to_the_session_before_its_ideal_day_never_after():
    p = ss.assegna([_r(ideale=date(2026, 10, 18)), _r(ideale=date(2026, 10, 20), cliente="Splash"),
                    _r(ideale=date(2026, 10, 21), cliente="Bahia")], GIOVEDI)
    assert [s.data for s in p.sessioni] == [date(2026, 10, 18), date(2026, 10, 21)]
    dom, mer = p.sessioni
    assert [d.cliente for d in dom.varieta[0].destinatari] == ["Abaluus", "Splash"]      # mar 20 -> dom 18, anticipo 2
    assert dom.varieta[0].destinatari[1].anticipo_giorni == 2 and not dom.varieta[0].destinatari[1].note
    assert [d.cliente for d in mer.varieta[0].destinatari] == ["Bahia"]


def test_same_variety_is_summed_and_shows_who_it_is_for():
    p = ss.assegna([_r(cliente="Abaluus", quantita="1", grammi="30", consegna=date(2026, 10, 22)),
                    _r(cliente="Gringo", quantita="2", grammi="60", consegna=date(2026, 10, 21), riga="RPS-000002"),
                    _r(varieta="Cilantro", cliente="Abaluus", quantita="0.5", grammi="8", riga="RPS-000003")], GIOVEDI)
    dom = p.sessioni[0]
    assert [v.varieta for v in dom.varieta] == ["Afila", "Cilantro"]
    afila = dom.varieta[0]
    assert (afila.quantita, afila.grammi) == (Decimal(3), Decimal(90))
    assert [(d.cliente, d.quantita) for d in afila.destinatari] == [("Gringo", Decimal(2)), ("Abaluus", Decimal(1))]
    assert dom.quantita_per_unita == {"SET": Decimal("3.5")}


def test_past_session_or_past_ideal_day_goes_to_the_next_session_flagged_late():
    # mer 14/10 gia' passato: la riga con data ideale ven 16/10 (prima sessione utile: dom 18) e' in ritardo di 2 gg
    p = ss.assegna([_r(ideale=date(2026, 10, 16)), _r(ideale=date(2026, 10, 12), cliente="Splash")], GIOVEDI)
    dom = p.sessioni[0]
    assert dom.data == date(2026, 10, 18) and len(p.sessioni) == 1
    ritardi = {d.cliente: d.ritardo_giorni for d in dom.varieta[0].destinatari}
    assert ritardi == {"Abaluus": 2, "Splash": 6}
    assert all("in ritardo" in d.note[0] for d in dom.varieta[0].destinatari)


def test_today_counts_when_it_is_a_session_day():
    mercoledi = date(2026, 10, 21)
    p = ss.assegna([_r(ideale=mercoledi), _r(ideale=date(2026, 10, 20), cliente="Splash")], mercoledi)
    assert p.sessioni[0].data == mercoledi
    assert [d.ritardo_giorni for d in p.sessioni[0].varieta[0].destinatari] == [0, 1]    # Abaluus: ideale oggi; Splash: ideale mar 20 -> oggi (1 gg)
    assert "(OGGI)" in "\n".join(ss.testo(p))


def test_only_the_first_n_sessions_are_shown_and_the_rest_is_counted():
    righe = [_r(ideale=date(2026, 10, 18)), _r(ideale=date(2026, 10, 21), riga="a"), _r(ideale=date(2026, 10, 25), riga="b"),
             _r(ideale=date(2026, 11, 1), riga="c")]
    p = ss.assegna(righe, GIOVEDI, n_sessioni=2)
    assert len(p.sessioni) == 2 and p.piu_avanti == 2 and p.ultima_data_piu_avanti == date(2026, 11, 1)
    assert "Piu' avanti: altre 2 righe, fino alla sessione del 01/11" in "\n".join(ss.testo(p))


def test_long_advance_is_flagged():
    p = ss.assegna([_r(ideale=date(2026, 10, 20), cliente="Splash")], GIOVEDI, anticipo_max=1)
    assert "ANTICIPO di 2 gg" in p.sessioni[0].varieta[0].destinatari[0].note[0]


def test_expired_orders_and_hopeless_delays_are_listed_apart_per_order_not_in_the_sessions():
    scaduto = [_r(varieta="Afila", ideale=date(2026, 10, 1), ord_cons=date(2026, 10, 8), consegna=date(2026, 10, 8),
                  cliente="Alchimia", ordine="ORD-000021", stato="PARZIALMENTE_EVASO"),
               _r(varieta="Rabano", ideale=date(2026, 10, 1), ord_cons=date(2026, 10, 8), consegna=date(2026, 10, 8),
                  cliente="Alchimia", ordine="ORD-000021", riga="RPS-2", stato="PARZIALMENTE_EVASO")]
    vicino = [_r(varieta="Mizuna", ideale=date(2026, 10, 1), consegna=date(2026, 10, 16), cliente="Bahia", ordine="ORD-000039",
                 quantita="0.5")]
    buona = [_r(ideale=date(2026, 10, 18), cliente="Gringo")]
    p = ss.assegna(scaduto + vicino + buona, GIOVEDI)
    assert [d.cliente for d in p.sessioni[0].varieta[0].destinatari] == ["Gringo"] and len(p.sessioni) == 1
    assert [(o.ordine, o.voci) for o in p.scaduti] == [("ORD-000021", ("Afila 1 SET", "Rabano 1 SET"))]
    assert [(o.ordine, o.ritardo_giorni, o.voci) for o in p.da_verificare] == [("ORD-000039", 17, ("Mizuna 0.5 SET",))]
    testo = "\n".join(ss.testo(p))
    assert "ORDINI SCADUTI (1)" in testo and "chiudi_residuo_ordini.py --ordini ORD-000021" in testo and "[PARZIALMENTE_EVASO]" in testo
    assert "DA VERIFICARE (1 ordini)" in testo and "ORD-000039  Bahia  consegna 16/10  (piano in ritardo di 17 gg): Mizuna 0.5 SET" in testo
    d = ss.a_dizionario(p)
    assert d["scaduti"][0]["voci"] == ["Afila 1 SET", "Rabano 1 SET"] and d["da_verificare"][0]["ordine"] == "ORD-000039"


def test_only_expired_orders_means_no_sessions_but_they_are_still_shown():
    p = ss.assegna([_r(ideale=date(2026, 10, 1), consegna=date(2026, 10, 8))], GIOVEDI)
    assert p.sessioni == () and len(p.scaduti) == 1
    testo = "\n".join(ss.testo(p))
    assert "Nessuna semina da fare nelle sessioni" in testo and "ORDINI SCADUTI (1)" in testo


def test_expired_orders_get_the_right_command_for_their_state():
    righe = [_r(ideale=date(2026, 10, 1), consegna=date(2026, 10, 6), ordine="ORD-000016", stato="APERTO"),
             _r(ideale=date(2026, 10, 1), consegna=date(2026, 10, 8), ordine="ORD-000021", stato="PARZIALMENTE_EVASO", riga="b")]
    testo = "\n".join(ss.testo(ss.assegna(righe, GIOVEDI)))
    assert "[APERTO]" in testo and "2026-10-07_modifica_ordine.py annulla ORD-000016 --motivo" in testo
    assert "2026-10-05_chiudi_residuo_ordini.py --ordini ORD-000021" in testo and "annulla ORD-000021" not in testo


def test_custom_days_and_empty_plan():
    p = ss.assegna([_r(ideale=date(2026, 10, 20))], GIOVEDI, giorni=(2, 5))          # martedi' e venerdi'
    assert p.sessioni[0].data == date(2026, 10, 20) and p.sessioni[0].nome_giorno == "martedi"
    vuoto = ss.assegna([], GIOVEDI)
    assert vuoto.sessioni == () and "Nessuna semina da fare" in "\n".join(ss.testo(vuoto))


def test_text_and_dictionary_carry_the_who_and_the_grams():
    p = ss.assegna([_r(cliente="Gringo", quantita="2", grammi="60", consegna=date(2026, 10, 21))], GIOVEDI)
    testo = "\n".join(ss.testo(p))
    assert "SESSIONE domenica 18/10 - 1 varieta', 2 SET" in testo
    assert "Afila  2 SET   (60 g di seme)" in testo and "Gringo  2   consegna 21/10  (ORD-000001)" in testo
    d = ss.a_dizionario(p)
    assert d["sessioni"][0]["varieta"][0]["destinatari"][0]["cliente"] == "Gringo"
    assert d["sessioni"][0]["totali"] == {"SET": "2"} and d["giorni"] == ["mercoledi", "domenica"]
