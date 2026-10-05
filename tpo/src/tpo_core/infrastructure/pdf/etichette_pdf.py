"""Rendering PDF delle ETICHETTE DI TRACCIABILITA' (una per vaschetta).

Funzione pura: riceve i dati gia' letti e restituisce i byte del PDF, una
pagina 62x29 mm per etichetta (stampante termica). Compare solo cio' che esiste
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


def render_etichette_pdf(etichette: Sequence[Etichetta]) -> bytes:
    if not etichette:
        raise ValueError("nessuna etichetta da stampare")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(LARGHEZZA, ALTEZZA), pageCompression=1)
    pdf.setTitle("Etichette di tracciabilita - Tower Power")
    pdf.setAuthor("Tower Power OS")
    larghezza_utile = LARGHEZZA - 2 * MARGINE
    for e in etichette:
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
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
