"""Rendering PDF delle ETICHETTE DI TRACCIABILITA' (una per vaschetta).

Funzione pura: riceve i dati gia' letti e restituisce i byte del PDF, una
pagina 62x29 mm per etichetta (stampante termica) oppure, con
``render_etichette_foglio_pdf``, tutte le etichette affiancate su fogli A4. Compare solo cio' che esiste
nel database: varieta', codice AAA-GGMM-L della semina di provenienza, data di
raccolta e numero della consegna. Nessuna data di scadenza, peso o lotto viene
inventato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Sequence

from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

LARGHEZZA = 62 * mm
ALTEZZA = 29 * mm
MARGINE = 2.5 * mm


@dataclass(frozen=True)
class Etichetta:
    varieta: str
    codice_tracciabilita: str
    data_raccolta: date
    consegna_id: str


def _fit(text: str, font: str, size: float, max_width: float) -> float:
    while size > 5 and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _disegna(pdf, e: Etichetta, x: float = 0, y: float = 0) -> None:
    """Disegna UNA etichetta 62x29 mm con l'angolo in basso a sinistra in (x, y)."""
    larghezza_utile = LARGHEZZA - 2 * MARGINE
    pdf.saveState()
    pdf.translate(x, y)
    pdf.setLineWidth(0.4)
    pdf.rect(1 * mm, 1 * mm, LARGHEZZA - 2 * mm, ALTEZZA - 2 * mm, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(MARGINE, ALTEZZA - 6 * mm, "TOWER POWER")
    pdf.setFont("Helvetica", 6)
    pdf.drawRightString(LARGHEZZA - MARGINE, ALTEZZA - 6 * mm, e.consegna_id)
    size = _fit(e.varieta, "Helvetica-Bold", 13, larghezza_utile)
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(MARGINE, ALTEZZA - 12 * mm, e.varieta)
    pdf.setFont("Helvetica", 6)
    pdf.drawString(MARGINE, ALTEZZA - 16 * mm, "Código de trazabilidad")
    size = _fit(e.codice_tracciabilita, "Helvetica-Bold", 16, larghezza_utile)
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(MARGINE, ALTEZZA - 22 * mm, e.codice_tracciabilita)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(MARGINE, ALTEZZA - 26 * mm, f"Cosecha: {e.data_raccolta:%d/%m/%Y}")
    pdf.restoreState()


def render_etichette_pdf(etichette: Sequence[Etichetta]) -> bytes:
    if not etichette:
        raise ValueError("nessuna etichetta da stampare")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(LARGHEZZA, ALTEZZA), pageCompression=1)
    pdf.setTitle("Etichette di tracciabilita - Tower Power")
    pdf.setAuthor("Tower Power OS")
    for e in etichette:
        _disegna(pdf, e)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# Foglio A4 verticale: le stesse etichette 62x29 mm affiancate (3 colonne x 9 righe = 27 per foglio), da stampare al
# 100% e ritagliare lungo i bordi; nessun adesivo prestampato richiesto.
FOGLIO_LARGHEZZA, FOGLIO_ALTEZZA = 210 * mm, 297 * mm
FOGLIO_COLONNE, FOGLIO_RIGHE = 3, 9
FOGLIO_MARGINE_X = (FOGLIO_LARGHEZZA - FOGLIO_COLONNE * LARGHEZZA) / 2
FOGLIO_MARGINE_Y = (FOGLIO_ALTEZZA - FOGLIO_RIGHE * ALTEZZA) / 2
ETICHETTE_PER_FOGLIO = FOGLIO_COLONNE * FOGLIO_RIGHE


def render_etichette_foglio_pdf(etichette: Sequence[Etichetta]) -> bytes:
    """Tutte le etichette sullo stesso foglio A4 (a partire dall'alto a sinistra, per righe)."""
    if not etichette:
        raise ValueError("nessuna etichetta da stampare")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(FOGLIO_LARGHEZZA, FOGLIO_ALTEZZA), pageCompression=1)
    pdf.setTitle("Etichette di tracciabilita - Tower Power (foglio A4)")
    pdf.setAuthor("Tower Power OS")
    for indice, e in enumerate(etichette):
        posto = indice % ETICHETTE_PER_FOGLIO
        colonna, riga = posto % FOGLIO_COLONNE, posto // FOGLIO_COLONNE
        x = FOGLIO_MARGINE_X + colonna * LARGHEZZA
        y = FOGLIO_ALTEZZA - FOGLIO_MARGINE_Y - (riga + 1) * ALTEZZA
        _disegna(pdf, e, x, y)
        if posto == ETICHETTE_PER_FOGLIO - 1 and indice < len(etichette) - 1:
            pdf.showPage()
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
