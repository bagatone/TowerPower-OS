"""Errori provider-neutral della query DISPONIBILITA_COMMERCIALE V1."""


class DisponibilitaCommercialeError(Exception):
    code = "DISPONIBILITA_COMMERCIALE_FAILED"


class InvalidDisponibilitaCommercialeQueryError(DisponibilitaCommercialeError):
    code = "DISPONIBILITA_COMMERCIALE_INPUT_INVALID"


class DisponibilitaCommercialeVarietaNotFoundError(DisponibilitaCommercialeError):
    code = "DISPONIBILITA_COMMERCIALE_VARIETA_NOT_FOUND"


class DisponibilitaCommercialeStockConflictError(DisponibilitaCommercialeError):
    """Piu' righe tpo.stock vive (o nessuna disponibile>0) per la stessa
    VARIETA: dal 19/9/2026 tpo.stock ha chiave composita (varieta_id,
    unita_misura) ed una VARIETA puo' avere piu' righe, una per unita'.
    La politica e' preferire l'unica riga con disponibile>0; se questo e'
    ambiguo (nessuna riga viva, o piu' di una viva insieme -- un'anomalia
    che non deve mai accadere in condizioni normali) si fallisce chiuso
    invece di indovinare quale riga rappresenta la disponibilita' reale."""

    code = "DISPONIBILITA_COMMERCIALE_STOCK_CONFLICT"
