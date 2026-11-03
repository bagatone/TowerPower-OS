from src.tpo_core.infrastructure.pdf.nomi_varieta import nome_spagnolo


def test_nomi_italiani_tradotti_in_spagnolo():
    assert nome_spagnolo("Lenticchia") == "Lenteja"
    assert nome_spagnolo("Cavolo rosso") == "Col roja"
    assert nome_spagnolo("Basilico") == "Albahaca"
    assert nome_spagnolo(" Broccolo ") == "Brócoli"


def test_nomi_gia_spagnoli_restano_invariati():
    for nome in ("Afila", "Rábano", "Cilantro", "Mizuna", "Hinojo"):
        assert nome_spagnolo(nome) == nome
